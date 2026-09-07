"""Deterministic file workflow engine with a validated directed acyclic graph.

Nodes exchange lists of JSON-compatible records. There is no eval(), shell
execution or arbitrary Python node. File operations create new copies.
Explicitly confirmed desktop steps can change files through the target app.
"""
from __future__ import annotations
import csv
import fnmatch
import io
import json
import re
import subprocess
import sys
import time
import zipfile
from collections import deque
from pathlib import Path
from localdesk.parsers import extract
from localdesk.safety import (DEFAULT_EXCLUDES, InputError, MAX_FILE_BYTES,
                              checked_path, clean_name, digest, unique_write,
                              walk_files, within)

NODE_TYPES = {
    'ocr': {'label': 'Read scanned document', 'detail': 'Read images and scanned PDFs with local Tesseract OCR.'},
    'tables': {'label': 'Extract PDF tables', 'detail': 'Create records from PDF table rows. Choose lines, text, or OCR.'},
    'semantic': {'label': 'Semantic filter', 'detail': 'Rank records with a locally trained model or local neural weights.'},
    'summary': {'label': 'Summarize text', 'detail': 'Select source sentences with a local statistical model.'},
    'desktop': {'label': 'Desktop actions', 'detail': 'Run explicitly confirmed mouse and keyboard actions. Never in a background trigger.'},
    'scan': {'label': 'Read folder', 'detail': 'List files in the chosen workspace.'},
    'filter': {'label': 'Filter files', 'detail': 'Keep files that match a name or extension.'},
    'read': {'label': 'Read text', 'detail': 'Read text or a supported document.'},
    'extract': {'label': 'Extract field', 'detail': 'Extract one field with a bounded regular expression.'},
    'condition': {'label': 'Check field', 'detail': 'Keep records that pass a field test.'},
    'name': {'label': 'Set output name', 'detail': 'Build a file name from record fields.'},
    'copy': {'label': 'Copy files', 'detail': 'Write new copies. Never change the source.'},
    'csv': {'label': 'Write CSV', 'detail': 'Write selected record fields to a table.'},
    'json': {'label': 'Write JSON', 'detail': 'Export records as structured data.'},
    'archive': {'label': 'Create ZIP', 'detail': 'Pack source files into a new archive.'},
    'merge': {'label': 'Merge branches', 'detail': 'Merge parent records and remove repeated sources.'},
    'note': {'label': 'Add log note', 'detail': 'Add a message to the run report.'},
}


def validate(workflow: dict) -> tuple[list[dict], dict[str, list[str]]]:
    if not isinstance(workflow, dict):
        raise InputError('A workflow must be a JSON object.')
    nodes, edges = workflow.get('nodes'), workflow.get('edges', [])
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 40:
        raise InputError('A workflow must contain between 1 and 40 nodes.')
    if not isinstance(edges, list) or len(edges) > 120:
        raise InputError('A workflow cannot contain more than 120 connections.')
    lookup, parents, children = {}, {}, {}
    for node in nodes:
        if not isinstance(node, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', str(node.get('id', ''))):
            raise InputError('Each node needs a short, unique ID.')
        if node['id'] in lookup:
            raise InputError('Two nodes have the same ID.')
        if node.get('type') not in NODE_TYPES:
            raise InputError(f"Unknown node type: {node.get('type')}")
        if not isinstance(node.get('config', {}), dict):
            raise InputError('Node settings must be a JSON object.')
        lookup[node['id']] = node
        parents[node['id']], children[node['id']] = [], []
    pairs = set()
    for edge in edges:
        if not isinstance(edge, dict):
            raise InputError('A connection must be an object with from and to fields.')
        a, b = edge.get('from'), edge.get('to')
        if a not in lookup or b not in lookup:
            raise InputError('A connection points to a missing node.')
        if (a, b) in pairs:
            raise InputError('A connection occurs more than once.')
        pairs.add((a, b))
        parents[b].append(a)
        children[a].append(b)
    for node in nodes:
        if node['type'] == 'scan' and parents[node['id']]:
            raise InputError('A Read folder node cannot have an input connection.')
        if node['type'] != 'scan' and not parents[node['id']]:
            raise InputError(f"Connect an input to {node.get('label', node['id'])}.")
    degrees = {key: len(value) for key, value in parents.items()}
    queue = deque(key for key in lookup if degrees[key] == 0)
    ordered = []
    while queue:
        current = queue.popleft()
        ordered.append(lookup[current])
        for child in children[current]:
            degrees[child] -= 1
            if degrees[child] == 0:
                queue.append(child)
    if len(ordered) != len(nodes):
        raise InputError('This workflow has a cycle. Remove the circular connection.')
    return ordered, parents


def regex_field(pattern: str, text: str) -> str:
    if not isinstance(pattern, str) or len(pattern) > 256:
        raise InputError('An extraction pattern cannot exceed 256 characters.')
    try:
        re.compile(pattern)
    except re.error as exc:
        raise InputError(f'The extraction pattern is invalid: {exc}') from exc
    try:
        result = subprocess.run([sys.executable, '-m', 'localdesk.regex_worker'],
                                input=json.dumps({'pattern': pattern, 'text': text[:16_000]}),
                                text=True, capture_output=True, timeout=1.5, check=False,
                                cwd=Path(__file__).resolve().parents[1])
    except subprocess.TimeoutExpired as exc:
        raise InputError('The extraction pattern exceeded its time limit. Use a simpler pattern.') from exc
    if result.returncode:
        raise InputError('The extraction pattern could not be evaluated.')
    return json.loads(result.stdout)


def format_name(template: str, record: dict) -> str:
    if len(template) > 300:
        raise InputError('An output name template cannot exceed 300 characters.')
    def replacement(match):
        key = match.group(1)
        if key not in record:
            raise InputError(f'The name template uses a missing field: {key}')
        return str(record[key])
    result = re.sub(r'\$\{([A-Za-z0-9_]+)\}', replacement, template)
    if '/' in result or '\\' in result or result in {'.', '..'}:
        raise InputError('An output name cannot contain a folder path.')
    return clean_name(result)


def csv_safe(value: object) -> str:
    value = str(value if value is not None else '')
    # Prevent formula evaluation when someone opens an export in Excel.
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value


class Engine:
    def __init__(self, workspace: Path, output: Path | None, context, private_data: Path, *, desktop_permitted=False, desktop_deadline=None):
        self.workspace = checked_path(workspace, directory=True)
        self.output, self.context, self.private_data = output, context, private_data
        self.desktop_permitted = desktop_permitted
        self.desktop_deadline = desktop_deadline
        self.desktop_used = False
        self.artifacts: list[Path] = []
        self.planned: list[str] = []
        self.reserved: set[str] = set()

    def source(self, record: dict) -> Path:
        path = checked_path(record['source'])
        if not within(path, self.workspace) or within(path, self.private_data):
            raise InputError('A workflow tried to read outside its selected workspace.')
        if digest(path) != record['sha256']:
            raise InputError(f'{path.name} changed after the scan. Run the workflow again.')
        return path

    def reserve(self, name: str) -> str:
        name = clean_name(name)
        candidate = name
        number = 2
        while candidate.casefold() in self.reserved:
            p = Path(name)
            candidate = f'{p.stem}-{number}{p.suffix}'
            number += 1
        self.reserved.add(candidate.casefold())
        self.planned.append(candidate)
        return candidate

    def write(self, name: str, content: bytes) -> str:
        if len(content) > MAX_FILE_BYTES:
            raise InputError('A workflow output exceeds the 25 MiB limit.')
        name = self.reserve(name)
        if self.output:
            path = unique_write(self.output / name, content)
            self.artifacts.append(path)
        return name

    def run(self, workflow: dict, *, stop_after: str | None = None) -> dict:
        nodes, parents = validate(workflow)
        if stop_after and stop_after not in {n['id'] for n in nodes}:
            raise InputError('The selected stop node does not exist.')
        records, steps = {}, []
        started = time.monotonic()
        for index, node in enumerate(nodes):
            self.context.check()
            self.context.progress(int(100 * index / len(nodes)), f"Running {node.get('label', node['type'])}")
            data = [dict(row) for key in parents[node['id']] for row in records[key]]
            mark = time.monotonic()
            data, note = self.step(node, data)
            if len(data) > 500:
                raise InputError('This run exceeds 500 records. Add a narrower input filter.')
            records[node['id']] = data
            steps.append({'id': node['id'], 'type': node['type'],
                          'label': node.get('label', NODE_TYPES[node['type']]['label']),
                          'records': len(data), 'seconds': round(time.monotonic() - mark, 4),
                          'note': note, 'preview': [{k: v for k, v in row.items() if k != 'text'}
                                                   for row in data[:5]]})
            if stop_after == node['id']:
                break
        last = records[steps[-1]['id']] if steps else []
        return {'dry_run': self.output is None, 'steps': steps,
                'record_count': len(last), 'planned_files': self.planned,
                'seconds': round(time.monotonic() - started, 4),
                'stopped_after': stop_after, 'source_files_changed': None if self.desktop_used else False,
                'desktop_actions_executed': self.desktop_used}

    def step(self, node: dict, rows: list[dict]) -> tuple[list[dict], str]:
        kind, config = node['type'], node.get('config', {})
        if kind == 'scan':
            pattern = str(config.get('pattern', '*'))
            rows = []
            for path in walk_files(self.workspace, limit=5000):
                self.context.check()
                if within(path, self.private_data) or path.stat().st_size > MAX_FILE_BYTES:
                    continue
                if not fnmatch.fnmatch(path.name, pattern):
                    continue
                rows.append({'source': str(path), 'name': path.name, 'stem': path.stem,
                             'ext': path.suffix, 'relative': path.relative_to(self.workspace).as_posix(),
                             'size': path.stat().st_size, 'sha256': digest(path)})
                if len(rows) > 500:
                    raise InputError('More than 500 files match. Use a more specific file pattern.')
            return rows, 'Read-only scan. Source hashes recorded.'
        if kind == 'filter':
            pattern = str(config.get('pattern', '*'))
            extension = str(config.get('extension', '')).lower()
            return [r for r in rows if fnmatch.fnmatch(r['name'], pattern) and
                    (not extension or r['ext'].lower() == extension)], 'Files filtered.'
        if kind == 'ocr':
            from localdesk.documents import document_request
            for row in rows:
                self.context.check()
                parsed = document_request(self.source(row), 'text', ocr=True,
                                          language=str(config.get('language', 'eng')))
                self.source(row)  # Recheck the reviewed bytes after parser work.
                row['text'] = parsed['text']
                row['text_method'] = parsed['method']
                row['text_warnings'] = parsed['warnings']
            return rows, 'Local OCR complete. Review recognition errors before using extracted values.'
        if kind == 'tables':
            from localdesk.documents import document_request
            output = []
            for row in rows:
                self.context.check()
                parsed = document_request(self.source(row), 'tables', strategy=config.get('strategy', 'lines'),
                                          language=config.get('language', 'eng'), column_edges=config.get('column_edges'))
                self.source(row)
                for table in parsed['tables']:
                    for index, values in enumerate(table['rows']):
                        result = {**row, 'page': table['page'], 'table': table['table'], 'row': index + 1,
                                  'text': ' | '.join(values), 'table_method': table['method']}
                        result.update({f'column_{i+1}': value for i, value in enumerate(values)})
                        output.append(result)
                        if len(output) > 500:
                            raise InputError('This workflow has more than 500 table rows. Split the PDF input.')
            return output, 'PDF table rows extracted. Review cell boundaries and OCR values.'
        if kind == 'semantic':
            from localdesk.semantic import SemanticModel
            if not rows:
                return rows, 'No records to rank.'
            model = SemanticModel([str(r.get('text', r['name'])) for r in rows], str(config.get('model_path', '')))
            threshold = config.get('minimum_score', 0.15)
            if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not -1 <= threshold <= 1:
                raise InputError('Minimum similarity must be a number from -1 to 1.')
            scores = model.scores(str(config.get('query', '')))
            ranked = [{**r, 'semantic_score': score} for r, score in zip(rows, scores) if score >= threshold]
            ranked.sort(key=lambda r: -r['semantic_score'])
            return ranked, model.method + '. Scores are similarities, not probabilities.'
        if kind == 'summary':
            from localdesk.semantic import extractive_summary
            for row in rows:
                self.context.check()
                row['summary'] = extractive_summary(row.get('text', ''), config.get('sentences', 3))
            return rows, 'Selected existing source sentences. No generated claims or external model calls.'
        if kind == 'desktop':
            if self.output is not None and (self.desktop_deadline is None or time.monotonic() > self.desktop_deadline):
                raise InputError('Desktop confirmation expired before this step started. Preview first, then confirm a fresh run.')
            from localdesk.desktop import execute
            note = execute(config.get('actions', []), self.context, self.write,
                           permitted=self.desktop_permitted, dry_run=self.output is None)
            self.desktop_used = self.output is not None
            return rows, note
        if kind == 'read':
            for row in rows:
                self.context.check()
                parsed = extract(self.source(row), ocr=bool(config.get('ocr', False)))
                self.source(row)  # Recheck the reviewed bytes after parser work.
                row['text'] = parsed['text']
                row['text_method'] = parsed['method']
                row['text_truncated'] = parsed['truncated']
            return rows, 'Read supported text. Original files remain unchanged.'
        if kind == 'extract':
            field = str(config.get('field', 'value'))
            if not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,30}', field) or field in {'source', 'sha256', 'name', 'stem', 'ext', 'size'}:
                raise InputError('Choose a new field name, such as invoice_id or amount.')
            for row in rows:
                self.context.check()
                row[field] = regex_field(str(config.get('pattern', '')), row.get('text', ''))
            return rows, f'Extracted {field}. An empty value means no match.'
        if kind == 'condition':
            field, operator, value = str(config.get('field', 'value')), config.get('operator', 'not_empty'), str(config.get('value', ''))
            if operator not in {'not_empty', 'empty', 'equals', 'contains'}:
                raise InputError('Choose not_empty, empty, equals, or contains.')
            def keep(row):
                actual = str(row.get(field, ''))
                return {'not_empty': bool(actual), 'empty': not actual,
                        'equals': actual == value, 'contains': value in actual}[operator]
            return [row for row in rows if keep(row)], f'Kept records that pass {field}: {operator}.'
        if kind == 'name':
            for row in rows:
                row['output_name'] = format_name(str(config.get('template', '${stem}${ext}')), row)
            return rows, 'Output names set. No source file was renamed.'
        if kind == 'copy':
            for row in rows:
                self.context.check()
                path = self.source(row)
                name = self.write(row.get('output_name', row['name']), path.read_bytes())
                row['copied_as'] = name
            return rows, f'{len(rows)} copies planned.' if not self.output else f'{len(rows)} new copies written.'
        if kind == 'csv':
            fields = config.get('fields', ['name', 'size', 'sha256'])
            if isinstance(fields, str):
                fields = [x.strip() for x in fields.split(',') if x.strip()]
            if not isinstance(fields, list) or not fields or len(fields) > 40:
                raise InputError('A CSV node needs between 1 and 40 fields.')
            text = io.StringIO(newline='')
            writer = csv.writer(text)
            writer.writerow([csv_safe(f) for f in fields])
            for row in rows:
                writer.writerow([csv_safe(row.get(f, '')) for f in fields])
            name = self.write(str(config.get('filename', 'records.csv')), text.getvalue().encode('utf-8-sig'))
            return rows, f'Table: {name}'
        if kind == 'json':
            public = [{k: v for k, v in r.items() if k != 'text'} for r in rows]
            name = self.write(str(config.get('filename', 'records.json')),
                              json.dumps(public, indent=2, ensure_ascii=False).encode('utf-8'))
            return rows, f'Records: {name}. Extracted document text is omitted.'
        if kind == 'archive':
            if sum(int(r['size']) for r in rows) > MAX_FILE_BYTES:
                raise InputError('An archive input exceeds 25 MiB. Split the workflow.')
            buffer = io.BytesIO()
            used = set()
            with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for row in rows:
                    self.context.check()
                    path = self.source(row)
                    name = clean_name(row.get('output_name', row['name']))
                    if name.casefold() in used:
                        name = f"{row['sha256'][:10]}-{name}"
                    if name.casefold() in used:
                        continue
                    used.add(name.casefold())
                    zf.writestr(name, path.read_bytes())
            name = self.write(str(config.get('filename', 'archive.zip')), buffer.getvalue())
            return rows, f'Archive: {name}'
        if kind == 'merge':
            unique = {}
            for row in rows:
                unique.setdefault(row['source'], {}).update(row)
            return list(unique.values()), 'Merged branches by source path.'
        if kind == 'note':
            return rows, str(config.get('message', 'Step complete.'))[:400]
        raise InputError('Unsupported workflow node.')
