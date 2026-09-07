from __future__ import annotations

import csv
import fnmatch
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

MAX_FILE_BYTES = 25 * 1024 * 1024
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,48}$")


class WorkflowError(ValueError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_inside(path: Path, root: Path) -> Path:
    path = path.resolve()
    root = root.resolve()
    if path != root and root not in path.parents:
        raise WorkflowError("Path is outside the selected workspace.")
    return path


def validate(workflow: dict) -> list[dict]:
    steps = workflow.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 30:
        raise WorkflowError("Workflow must contain 1 to 30 steps.")
    allowed = {"scan", "filter", "read", "extract", "rename", "copy", "csv", "zip"}
    seen = set()
    for step in steps:
        if not isinstance(step, dict) or not SAFE_ID.fullmatch(str(step.get("id", ""))):
            raise WorkflowError("Each step needs a short unique id.")
        if step["id"] in seen:
            raise WorkflowError("Step ids must be unique.")
        seen.add(step["id"])
        if step.get("type") not in allowed:
            raise WorkflowError(f"Unsupported step: {step.get('type')}")
        if not isinstance(step.get("config", {}), dict):
            raise WorkflowError("Step config must be an object.")
    if steps[0]["type"] != "scan":
        raise WorkflowError("The first step must be scan.")
    return steps


@dataclass
class RunResult:
    records: list[dict]
    outputs: list[str]
    steps: list[dict]


class WorkflowEngine:
    def __init__(self, workspace: Path, output: Path | None = None):
        self.workspace = workspace.resolve()
        if not self.workspace.is_dir():
            raise WorkflowError("Workspace folder does not exist.")
        self.output = output.resolve() if output else None
        if self.output:
            self.output.mkdir(parents=True, exist_ok=True)
        self.outputs: list[str] = []

    def _write(self, name: str, data: bytes) -> None:
        if self.output is None:
            return
        safe = Path(name).name
        if safe != name or safe in {"", ".", ".."}:
            raise WorkflowError("Invalid output file name.")
        target = ensure_inside(self.output / safe, self.output)
        stem, suffix = target.stem, target.suffix
        n = 2
        while target.exists():
            target = self.output / f"{stem}-{n}{suffix}"
            n += 1
        target.write_bytes(data)
        self.outputs.append(target.name)

    def run(self, workflow: dict, *, preview: bool = False) -> RunResult:
        steps = validate(workflow)
        records: list[dict] = []
        trace: list[dict] = []
        for step in steps:
            cfg = step.get("config", {})
            kind = step["type"]
            if kind == "scan":
                records = []
                for p in sorted(self.workspace.rglob("*")):
                    if p.is_symlink() or not p.is_file():
                        continue
                    ensure_inside(p, self.workspace)
                    if p.stat().st_size > MAX_FILE_BYTES:
                        continue
                    records.append({"source": str(p), "name": p.name, "sha256": sha256(p)})
            elif kind == "filter":
                pattern = str(cfg.get("pattern", "*"))[:120]
                records = [r for r in records if fnmatch.fnmatch(r["name"], pattern)]
            elif kind == "read":
                for r in records:
                    p = ensure_inside(Path(r["source"]), self.workspace)
                    if sha256(p) != r["sha256"]:
                        raise WorkflowError(f"Source changed during run: {p.name}")
                    r["text"] = p.read_text(encoding="utf-8", errors="replace")[:200_000]
            elif kind == "extract":
                pattern = str(cfg.get("pattern", ""))
                field = str(cfg.get("field", "value"))
                if len(pattern) > 256 or not SAFE_ID.fullmatch(field):
                    raise WorkflowError("Invalid extraction settings.")
                try:
                    rx = re.compile(pattern)
                except re.error as exc:
                    raise WorkflowError(f"Invalid regular expression: {exc}") from exc
                for r in records:
                    m = rx.search(r.get("text", ""))
                    r[field] = (m.group(1) if m and m.lastindex else m.group(0) if m else "")
            elif kind == "rename":
                template = str(cfg.get("template", "${name}"))[:200]
                for r in records:
                    r["output_name"] = re.sub(
                        r"\$\{([A-Za-z0-9_]+)\}",
                        lambda m: str(r.get(m.group(1), "")),
                        template,
                    )
                    if Path(r["output_name"]).name != r["output_name"]:
                        raise WorkflowError("Output name cannot contain a folder path.")
            elif kind == "copy":
                if not preview:
                    for r in records:
                        p = ensure_inside(Path(r["source"]), self.workspace)
                        self._write(r.get("output_name", r["name"]), p.read_bytes())
            elif kind == "csv":
                fields = cfg.get("fields", ["name", "output_name"])
                if not isinstance(fields, list) or not fields:
                    raise WorkflowError("CSV fields must be a non-empty list.")
                out = io.StringIO()
                writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for r in records:
                    row = {k: str(r.get(k, "")) for k in fields}
                    for k, v in row.items():
                        if v.lstrip().startswith(("=", "+", "-", "@")):
                            row[k] = "'" + v
                    writer.writerow(row)
                if not preview:
                    self._write(str(cfg.get("name", "register.csv")), out.getvalue().encode())
            elif kind == "zip":
                if not preview:
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                        for r in records:
                            p = ensure_inside(Path(r["source"]), self.workspace)
                            z.write(p, arcname=r.get("output_name", r["name"]))
                    self._write(str(cfg.get("name", "bundle.zip")), buf.getvalue())
            trace.append({"id": step["id"], "type": kind, "records": len(records)})
        return RunResult(records=records, outputs=list(self.outputs), steps=trace)


def load_workflow(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
