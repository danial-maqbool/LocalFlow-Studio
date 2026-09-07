"""Workflow storage, execution history, and explicit in-app triggers."""

from __future__ import annotations
import json
import hashlib
import secrets
import time
import re
import threading
import uuid
from pathlib import Path
from localdesk.base import BaseApplication
from localdesk.jobs import utcnow
from localdesk.safety import InputError, checked_path, integer, unique_write, walk_files, within
from .engine import Engine, NODE_TYPES, validate


def starter_workflow() -> dict:
    return {
        "id": "invoice-register",
        "name": "Invoice register",
        "version": 1,
        "description": "Read invoice text, extract an ID, create named copies, and write a CSV register.",
        "nodes": [
            {
                "id": "input",
                "type": "scan",
                "label": "Read invoice folder",
                "x": 36,
                "y": 52,
                "config": {"pattern": "invoice-*.txt"},
            },
            {
                "id": "read",
                "type": "read",
                "label": "Read invoice text",
                "x": 292,
                "y": 52,
                "config": {},
            },
            {
                "id": "id",
                "type": "extract",
                "label": "Extract invoice ID",
                "x": 548,
                "y": 52,
                "config": {"field": "invoice_id", "pattern": r"Invoice:\s*(INV-\d+)"},
            },
            {
                "id": "name",
                "type": "name",
                "label": "Set clean file names",
                "x": 548,
                "y": 225,
                "config": {"template": "${invoice_id}${ext}"},
            },
            {
                "id": "copy",
                "type": "copy",
                "label": "Create new copies",
                "x": 292,
                "y": 225,
                "config": {},
            },
            {
                "id": "table",
                "type": "csv",
                "label": "Write invoice register",
                "x": 36,
                "y": 225,
                "config": {
                    "filename": "invoice-register.csv",
                    "fields": ["invoice_id", "name", "copied_as", "sha256"],
                },
            },
        ],
        "edges": [
            {"from": a, "to": b}
            for a, b in [
                ("input", "read"),
                ("read", "id"),
                ("id", "name"),
                ("name", "copy"),
                ("copy", "table"),
            ]
        ],
    }


class Application(BaseApplication):
    def setup(self):
        from .legacy import upgrade_schema

        upgrade_schema(self.store)
        with self.store.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows(id TEXT PRIMARY KEY,name TEXT,body TEXT,revision INTEGER,updated TEXT);
                CREATE TABLE IF NOT EXISTS workflow_versions(id INTEGER PRIMARY KEY,workflow_id TEXT,revision INTEGER,body TEXT,created TEXT);
            """
            )
        if not self.store.one("SELECT id FROM workflows LIMIT 1"):
            self.save(starter_workflow())
            self.save(
                {
                    "id": "folder-backup",
                    "name": "Folder backup",
                    "nodes": [
                        {
                            "id": "read",
                            "type": "scan",
                            "label": "Read workspace",
                            "x": 45,
                            "y": 85,
                            "config": {"pattern": "*"},
                        },
                        {
                            "id": "zip",
                            "type": "archive",
                            "label": "Create ZIP backup",
                            "x": 330,
                            "y": 85,
                            "config": {"filename": "workspace-backup.zip"},
                        },
                    ],
                    "edges": [{"from": "read", "to": "zip"}],
                }
            )
        self.desktop_tokens = {}
        self.desktop_run_lock = threading.Lock()
        self.trigger_lock = threading.Lock()
        self.trigger_stop = threading.Event()
        self.trigger_thread = None
        self.trigger = {"enabled": False, "mode": "watch", "last_error": "", "last_job": None}

    def save(self, workflow: dict) -> dict:
        from .legacy import convert

        workflow = convert(workflow)
        validate(workflow)
        ident = str(workflow.get("id") or uuid.uuid4().hex)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", ident):
            raise InputError("The workflow ID is invalid.")
        name = str(workflow.get("name", "Untitled workflow")).strip()[:100]
        if not name:
            raise InputError("Enter a workflow name.")
        old = self.store.one("SELECT revision FROM workflows WHERE id=?", (ident,))
        revision = old["revision"] + 1 if old else 1
        workflow = {**workflow, "id": ident, "name": name, "version": revision}
        raw = json.dumps(workflow, ensure_ascii=False)
        if len(raw) > 100_000:
            raise InputError("The workflow definition exceeds 100,000 characters.")
        with self.store.connection() as db:
            db.execute(
                "INSERT INTO workflows(id,name,body,revision,updated) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name,body=excluded.body,revision=excluded.revision,updated=excluded.updated",
                (ident, name, raw, revision, utcnow()),
            )
            db.execute(
                "INSERT INTO workflow_versions(workflow_id,revision,body,created) VALUES(?,?,?,?)",
                (ident, revision, raw, utcnow()),
            )
        return workflow

    def load(self, ident: str) -> dict:
        row = self.store.one("SELECT body FROM workflows WHERE id=?", (ident,))
        if row is None:
            raise InputError("The workflow does not exist.")
        return json.loads(row["body"])

    def state(self):
        return {
            "jobs": self.jobs.recent(),
            "workflows": self.store.rows(
                "SELECT id,name,revision,updated FROM workflows ORDER BY name"
            ),
            "trigger": dict(self.trigger),
            "node_types": NODE_TYPES,
            "desktop_allowed": self.allow_desktop,
            "stats": {
                "workflows": self.store.one("SELECT COUNT(*) AS n FROM workflows")["n"],
                "runs": self.store.one("SELECT COUNT(*) AS n FROM jobs")["n"],
                "finished": self.store.one("SELECT COUNT(*) AS n FROM jobs WHERE status='done'")[
                    "n"
                ],
            },
        }

    def get(self, action, query):
        if action == "workflow":
            return self.load(query.get("id", "invoice-register"))
        if action == "versions":
            return {
                "versions": self.store.rows(
                    "SELECT revision,created FROM workflow_versions WHERE workflow_id=? "
                    "ORDER BY revision DESC LIMIT 40",
                    (query.get("id", ""),),
                )
            }
        return super().get(action, query)

    def run_workflow(
        self, workflow: dict, workspace: Path, dry: bool = True, stop_after=None, desktop_token=""
    ):
        validate(workflow)
        workspace = checked_path(workspace, directory=True)
        desktop_permitted = False
        desktop_expires = None
        if any(n["type"] == "desktop" for n in workflow["nodes"]):
            from localdesk.desktop import validate_actions

            for node in workflow["nodes"]:
                if node["type"] == "desktop":
                    validate_actions(node.get("config", {}).get("actions", []))
            if not dry:
                expected = self.desktop_tokens.pop(desktop_token, None)
                fingerprint = hashlib.sha256(
                    json.dumps(
                        {"workflow": workflow, "workspace": str(workspace)}, sort_keys=True
                    ).encode()
                ).hexdigest()
                if (
                    not self.allow_desktop
                    or not expected
                    or expected["expires"] < time.monotonic()
                    or expected["hash"] != fingerprint
                ):
                    raise InputError(
                        "Desktop actions need fresh confirmation for this exact workflow and workspace."
                    )
                desktop_permitted = True
                desktop_expires = expected["expires"]
        # Snapshot the definition before the UI can edit it during a run.
        snapshot = json.loads(json.dumps(workflow))

        def work(context):
            output = None if dry else self.new_output("workflow")
            engine = Engine(
                workspace,
                output,
                context,
                self.data,
                desktop_permitted=desktop_permitted,
                desktop_deadline=desktop_expires,
            )
            locked = False
            try:
                if desktop_permitted:
                    locked = self.desktop_run_lock.acquire(blocking=False)
                    if not locked:
                        raise InputError(
                            "Another desktop workflow is running. Do not run concurrent mouse or keyboard workflows."
                        )
                result = engine.run(snapshot, stop_after=stop_after)
            finally:
                if locked:
                    self.desktop_run_lock.release()
            result["workflow"] = {
                "id": snapshot.get("id"),
                "name": snapshot.get("name"),
                "version": snapshot.get("version"),
            }
            if output:
                export_snapshot = json.loads(json.dumps(snapshot))
                for node in export_snapshot["nodes"]:
                    if node["type"] == "desktop":
                        for action in node.get("config", {}).get("actions", []):
                            if "text" in action:
                                action["text"] = "[typed text omitted from run manifest]"
                unique_write(
                    output / "run-manifest.json",
                    json.dumps(
                        {"workflow": export_snapshot, "run": result}, ensure_ascii=False, indent=2
                    ).encode("utf-8"),
                )
                engine.artifacts.append(output / "run-manifest.json")
            result["artifacts"] = [self.artifact(p) for p in engine.artifacts]
            return result

        return self.jobs.submit("Preview workflow" if dry else "Run workflow", work)

    def stop_trigger(self):
        self.trigger_stop.set()
        if self.trigger_thread:
            self.trigger_thread.join(timeout=3)
        self.trigger["enabled"] = False

    def start_trigger(self, body):
        self.stop_trigger()
        if self.trigger_thread and self.trigger_thread.is_alive():
            raise InputError("The previous trigger is still stopping. Try again shortly.")
        mode = body.get("mode", "watch")
        if mode not in {"watch", "schedule"}:
            raise InputError("Choose a folder watch or an interval schedule.")
        seconds = integer(body.get("seconds", 30), 15, 86400, "Trigger interval")
        workflow = self.load(str(body.get("id", "invoice-register")))
        if any(n["type"] == "desktop" for n in workflow["nodes"]):
            raise InputError("Desktop workflows cannot run from automatic triggers.")
        workspace = checked_path(body.get("workspace", ""), directory=True)
        self.trigger_stop = threading.Event()
        self.trigger = {
            "enabled": True,
            "mode": mode,
            "seconds": seconds,
            "workspace": str(workspace),
            "workflow": workflow["name"],
            "last_error": "",
            "last_job": None,
        }

        def snapshot():
            return tuple(
                (str(p), p.stat().st_mtime_ns, p.stat().st_size)
                for p in walk_files(workspace, limit=5000)
                if not within(p, self.data)
            )

        current_signature = snapshot()
        identity = hashlib.sha256(
            json.dumps({"workspace": str(workspace), "workflow": workflow}, sort_keys=True).encode()
        ).hexdigest()
        saved = self.store.get("trigger_signature", {})
        baseline = (
            tuple(tuple(row) for row in saved.get("files", []))
            if self.resuming_background and saved.get("identity") == identity
            else current_signature
        )
        self.store.set("trigger_signature", {"identity": identity, "files": baseline})

        def loop():
            nonlocal baseline
            while not self.trigger_stop.wait(seconds) and not self.shutdown.is_set():
                try:
                    current = snapshot()
                    changed = current != baseline
                    previous = self.trigger.get("last_job")
                    busy = previous and self.jobs.get(previous)["status"] in {"running", "queued"}
                    if (changed or mode == "schedule") and not busy:
                        self.trigger["last_job"] = self.run_workflow(workflow, workspace, False)
                        baseline = current
                        self.store.set(
                            "trigger_signature", {"identity": identity, "files": baseline}
                        )
                    self.trigger["last_error"] = ""
                except Exception as exc:
                    self.trigger["last_error"] = str(exc)[:300]
            self.trigger["enabled"] = False

        self.trigger_thread = threading.Thread(target=loop, daemon=True, name="workflow-trigger")
        self.trigger_thread.start()
        return dict(self.trigger)

    def post(self, action, body):
        if action == "desktop/arm":
            if not self.allow_desktop or body.get("confirmed") is not True:
                raise InputError(
                    "Enable --allow-desktop and review the desktop actions before confirming a run."
                )
            workflow = body.get("workflow", {})
            validate(workflow)
            workspace = checked_path(body.get("workspace", ""), directory=True)
            fingerprint = hashlib.sha256(
                json.dumps(
                    {"workflow": workflow, "workspace": str(workspace)}, sort_keys=True
                ).encode()
            ).hexdigest()
            self.desktop_tokens = {
                k: v for k, v in self.desktop_tokens.items() if v["expires"] >= time.monotonic()
            }
            if len(self.desktop_tokens) >= 10:
                raise InputError("Too many desktop confirmations are pending.")
            token = secrets.token_urlsafe(24)
            self.desktop_tokens[token] = {"hash": fingerprint, "expires": time.monotonic() + 60}
            return {"desktop_token": token, "expires_in": 60}
        if action == "save":
            return self.save(body.get("workflow", {}))
        if action == "delete":
            self.store.execute("DELETE FROM workflows WHERE id=?", (str(body.get("id", "")),))
            return {"deleted": True}
        if action == "run":
            workflow = body.get("workflow") or self.load(str(body.get("id", "invoice-register")))
            return {
                "job_id": self.run_workflow(
                    workflow,
                    checked_path(body.get("workspace", ""), directory=True),
                    bool(body.get("dry_run", True)),
                    body.get("stop_after"),
                    str(body.get("desktop_token", "")),
                )
            }
        if action == "export":
            workflow = self.load(str(body.get("id", "invoice-register")))
            output = self.new_output("workflow-definition") / "workflow.json"
            unique_write(output, json.dumps(workflow, indent=2, ensure_ascii=False).encode("utf-8"))
            return self.artifact(output)
        if action == "restore":
            row = self.store.one(
                "SELECT body FROM workflow_versions WHERE workflow_id=? AND revision=?",
                (str(body.get("id", "")), integer(body.get("revision"), 1, 100000)),
            )
            if not row:
                raise InputError("This workflow revision does not exist.")
            return self.save(json.loads(row["body"]))
        if action == "trigger/start":
            return self.start_trigger(body)
        if action == "trigger/stop":
            self.stop_trigger()
            return dict(self.trigger)
        return super().post(action, body)

    def close(self):
        self.stop_trigger()
        super().close()
