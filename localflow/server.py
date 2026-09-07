from __future__ import annotations

import json
import mimetypes
import sqlite3
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine import WorkflowEngine, WorkflowError, validate

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
DATA = ROOT / ".localflow"
DB = DATA / "localflow.db"


def db() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("create table if not exists workflows (id text primary key, name text not null, body text not null, updated real not null)")
    con.execute("create table if not exists runs (id integer primary key autoincrement, workflow_id text, preview integer, status text, outputs text, created real)")
    return con


def seed() -> None:
    example = json.loads((ROOT / "examples" / "workflow.json").read_text())
    with db() as con:
        con.execute("insert or ignore into workflows values (?,?,?,?)", ("invoice-register", "Invoice register", json.dumps(example), time.time()))


def send_json(handler: BaseHTTPRequestHandler, payload, status=200):
    data = json.dumps(payload, indent=2).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalFlow/0.1"

    def log_message(self, fmt, *args):
        pass

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise WorkflowError("Request is too large.")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/status":
            return send_json(self, {"ok": True, "version": "0.1.0", "local": True})
        if path == "/api/workflows":
            with db() as con:
                rows = con.execute("select id,name,body,updated from workflows order by updated desc").fetchall()
            return send_json(self, [dict(r) | {"body": json.loads(r["body"])} for r in rows])
        if path == "/api/runs":
            with db() as con:
                rows = con.execute("select * from runs order by id desc limit 30").fetchall()
            return send_json(self, [dict(r) | {"outputs": json.loads(r["outputs"])} for r in rows])
        rel = "index.html" if path == "/" else path.lstrip("/")
        target = (WEB / rel).resolve()
        if WEB.resolve() not in target.parents and target != WEB.resolve():
            return self.send_error(404)
        if not target.is_file():
            return self.send_error(404)
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            body = self._body()
            if self.path == "/api/workflows":
                workflow = body["workflow"]
                validate(workflow)
                wid = str(body.get("id", "workflow"))[:48]
                name = str(body.get("name", "Workflow"))[:80]
                with db() as con:
                    con.execute("insert or replace into workflows values (?,?,?,?)", (wid, name, json.dumps(workflow), time.time()))
                return send_json(self, {"ok": True, "id": wid})
            if self.path in {"/api/preview", "/api/run"}:
                workflow = body["workflow"]
                workspace = Path(body.get("workspace") or ROOT / "examples" / "inbox")
                out = DATA / "outputs" / str(int(time.time() * 1000))
                preview = self.path.endswith("preview")
                result = WorkflowEngine(workspace, None if preview else out).run(workflow, preview=preview)
                with db() as con:
                    cur = con.execute("insert into runs(workflow_id,preview,status,outputs,created) values(?,?,?,?,?)",
                                      (body.get("id", "adhoc"), int(preview), "ok", json.dumps(result.outputs), time.time()))
                return send_json(self, {"ok": True, "run_id": cur.lastrowid, "records": result.records, "steps": result.steps, "outputs": result.outputs})
            return send_json(self, {"error": "Not found"}, 404)
        except (KeyError, json.JSONDecodeError, WorkflowError, OSError) as exc:
            return send_json(self, {"ok": False, "error": str(exc)}, 400)


def serve(host="127.0.0.1", port=8761):
    seed()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"LocalFlow Studio: http://{host}:{httpd.server_port}")
    print("Press Ctrl+C to stop.")
    httpd.serve_forever()
