"""OCR/table/model integration and desktop consent adversarial checks."""

import json
import shutil
import time
from pathlib import Path
from unittest.mock import patch
from app.service import Application
from localdesk.desktop import execute, validate_actions
from localdesk.safety import InputError, digest
from tests.support import AppCase, Context, ROOT
from tests.fixtures import make_pdf, make_image


def flow(*nodes):
    result = [
        {"id": str(i), "type": kind, "config": config} for i, (kind, config) in enumerate(nodes)
    ]
    return {
        "id": "upgrade-test",
        "name": "Upgrade test",
        "nodes": result,
        "edges": [{"from": str(i), "to": str(i + 1)} for i in range(len(result) - 1)],
    }


class UpgradeTests(AppCase):
    def test_pdf_table_to_csv_end_to_end(self):
        source = make_pdf(self.workspace / "invoice.pdf", table=True)
        before = digest(source)
        workflow = flow(
            ("scan", {"pattern": "*.pdf"}),
            ("tables", {"strategy": "lines"}),
            ("csv", {"filename": "table.csv", "fields": ["column_1", "column_2"]}),
        )
        result = self.finish(
            "run", {"workflow": workflow, "workspace": str(self.workspace), "dry_run": False}
        )
        csv = next(a for a in result["artifacts"] if a["name"] == "table.csv")
        self.assertIn(b"Invoice A,42", self.output(csv))
        self.assertEqual(digest(source), before)

    @__import__("unittest").skipUnless(
        shutil.which("tesseract"), "Tesseract integration dependency."
    )
    def test_ocr_to_extracted_field(self):
        make_image(self.workspace / "invoice.png")
        workflow = flow(
            ("scan", {"pattern": "*.png"}),
            ("ocr", {}),
            ("extract", {"field": "reference", "pattern": r"REF\s+(\d+)"}),
            ("csv", {"filename": "ocr.csv", "fields": ["reference"]}),
        )
        result = self.finish(
            "run", {"workflow": workflow, "workspace": str(self.workspace), "dry_run": False}
        )
        self.assertIn(
            b"7316", self.output(next(a for a in result["artifacts"] if a["name"] == "ocr.csv"))
        )

    def test_local_model_filter_and_summary(self):
        self.file(
            "bill.txt",
            "The supplier invoice needs payment. The supplier total is due next week. The invoice includes a receipt.",
        )
        self.file(
            "game.txt",
            "Football players train at the stadium. The match includes two teams. Players score goals.",
        )
        workflow = flow(
            ("scan", {"pattern": "*.txt"}),
            ("read", {}),
            ("semantic", {"query": "supplier invoice payment", "minimum_score": 0.1}),
            ("summary", {"sentences": 1}),
        )
        result = self.finish("run", {"workflow": workflow, "workspace": str(self.workspace)})
        self.assertEqual(result["record_count"], 1)
        self.assertIn("supplier", result["steps"][-1]["preview"][0]["summary"].lower())

    def desktop_flow(self):
        return flow(
            ("scan", {"pattern": "*.txt"}),
            ("desktop", {"actions": [{"type": "write", "text": "SYNTHETIC_TYPED_VALUE"}]}),
        )

    def test_desktop_locked_by_default(self):
        with self.assertRaises(InputError):
            self.app.common_post(
                "desktop/arm",
                {
                    "workflow": self.desktop_flow(),
                    "workspace": str(self.workspace),
                    "confirmed": True,
                },
            )

    def test_desktop_preview_never_imports_or_controls_gui(self):
        result = self.finish(
            "run",
            {"workflow": self.desktop_flow(), "workspace": str(self.workspace), "dry_run": True},
        )
        self.assertFalse(result["desktop_actions_executed"])
        self.assertEqual(result["artifacts"], [])

    def test_desktop_token_binds_exact_definition(self):
        self.app.allow_desktop = True
        workflow = self.desktop_flow()
        token = self.app.common_post(
            "desktop/arm",
            {"workflow": workflow, "workspace": str(self.workspace), "confirmed": True},
        )["desktop_token"]
        workflow["nodes"][1]["config"]["actions"][0]["text"] = "changed"
        with self.assertRaises(InputError):
            self.app.common_post(
                "run",
                {
                    "workflow": workflow,
                    "workspace": str(self.workspace),
                    "dry_run": False,
                    "desktop_token": token,
                },
            )

    def test_desktop_token_expiry_and_replay(self):
        self.app.allow_desktop = True
        workflow = self.desktop_flow()
        token = self.app.common_post(
            "desktop/arm",
            {"workflow": workflow, "workspace": str(self.workspace), "confirmed": True},
        )["desktop_token"]
        self.app.desktop_tokens[token]["expires"] = 0
        with self.assertRaises(InputError):
            self.app.common_post(
                "run",
                {
                    "workflow": workflow,
                    "workspace": str(self.workspace),
                    "dry_run": False,
                    "desktop_token": token,
                },
            )
        self.assertNotIn(token, self.app.desktop_tokens)

    def test_confirmed_desktop_run_omits_typed_text_from_manifest(self):
        self.app.allow_desktop = True
        workflow = self.desktop_flow()
        token = self.app.common_post(
            "desktop/arm",
            {"workflow": workflow, "workspace": str(self.workspace), "confirmed": True},
        )["desktop_token"]
        with patch("localdesk.desktop.execute", return_value="simulated test backend"):
            result = self.finish(
                "run",
                {
                    "workflow": workflow,
                    "workspace": str(self.workspace),
                    "dry_run": False,
                    "desktop_token": token,
                },
            )
        manifest = self.output(
            next(a for a in result["artifacts"] if a["name"] == "run-manifest.json")
        )
        self.assertNotIn(b"SYNTHETIC_TYPED_VALUE", manifest)
        with self.assertRaises(InputError):
            self.app.common_post(
                "run",
                {
                    "workflow": workflow,
                    "workspace": str(self.workspace),
                    "dry_run": False,
                    "desktop_token": token,
                },
            )

    def test_background_trigger_cannot_execute_desktop_nodes(self):
        self.app.save(self.desktop_flow())
        with self.assertRaises(InputError):
            self.app.common_post(
                "trigger/start", {"id": "upgrade-test", "workspace": str(self.workspace)}
            )

    def test_invalid_desktop_actions_are_rejected(self):
        for actions in [
            [{"type": "shell", "command": "anything"}],
            [{"type": "click", "x": -1, "y": 3}],
            [{"type": "wait", "seconds": float("nan")}],
            [{"type": "write", "text": "x" * 4001}],
        ]:
            with self.subTest(actions=actions[0]["type"]):
                with self.assertRaises(InputError):
                    validate_actions(actions)

    def test_desktop_failure_stop_is_not_disabled(self):
        class Backend:
            KEYBOARD_KEYS = ["enter"]
            FAILSAFE = False

            def size(self):
                return (800, 600)

            def failSafeCheck(self):
                raise RuntimeError("synthetic corner stop")

        backend = Backend()
        with self.assertRaisesRegex(RuntimeError, "corner stop"):
            execute(
                [{"type": "wait", "seconds": 0}],
                Context(),
                lambda *a: None,
                permitted=True,
                dry_run=False,
                backend=backend,
            )
        self.assertTrue(backend.FAILSAFE)

    def test_trigger_configuration_resumes_after_unlock(self):
        path = self.base / "durable"
        password = "synthetic trigger password"
        app = Application(ROOT, path, passphrase=password)
        try:
            app.common_post(
                "trigger/start",
                {"id": "invoice-register", "workspace": str(self.workspace), "seconds": 15},
            )
        finally:
            app.close()
        app = Application(ROOT, path, passphrase=password)
        try:
            self.assertTrue(app.trigger["enabled"])
            self.assertFalse(app.resume_error)
            app.common_post("trigger/stop", {})
        finally:
            app.close()
        app = Application(ROOT, path, passphrase=password)
        try:
            self.assertFalse(app.trigger["enabled"])
        finally:
            app.close()

    def test_legacy_public_database_migrates_and_runs(self):
        import sqlite3
        from localdesk.vault import migrate_plaintext

        password = "synthetic migration passphrase"
        original = self.base / "legacy.db"
        data = self.base / "migrated"
        workflow = {
            "steps": [
                {"id": "scan", "type": "scan", "config": {"pattern": "*.txt"}},
                {"id": "read", "type": "read", "config": {}},
                {
                    "id": "out",
                    "type": "csv",
                    "config": {"name": "register.csv", "fields": ["name"]},
                },
            ]
        }
        connection = sqlite3.connect(original)
        connection.execute(
            "CREATE TABLE workflows (id TEXT PRIMARY KEY, name TEXT NOT NULL, body TEXT NOT NULL, updated REAL NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE runs (id INTEGER PRIMARY KEY, workflow_id TEXT, preview INTEGER, status TEXT, outputs TEXT, created REAL)"
        )
        connection.execute(
            "INSERT INTO workflows VALUES (?,?,?,?)",
            ("legacy", "Old workflow", json.dumps(workflow), 1.0),
        )
        connection.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?,?)", (1, "legacy", 1, "ok", "[]", 1.0)
        )
        connection.commit()
        connection.close()
        before = digest(original)
        migrate_plaintext(original, data / "app.vault", password)
        app = Application(ROOT, data, passphrase=password)
        try:
            converted = app.load("legacy")
            self.assertEqual(converted["nodes"][-1]["config"]["filename"], "register.csv")
            app.save(converted)
            self.assertEqual(app.load("legacy")["version"], 2)
            self.assertEqual(app.store.one("SELECT COUNT(*) AS n FROM runs")["n"], 1)
            self.assertEqual(digest(original), before)
        finally:
            app.close()
