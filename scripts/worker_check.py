"""Exercise a real encrypted worker across process restarts.

Use only a temporary synthetic workspace. This does not install an OS service
or read a real credential store. It verifies the worker used by that service.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=ROOT / "docs")
    args = parser.parse_args()
    report_dir = args.report_dir.expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "worker-report.json").unlink(missing_ok=True)
    checks = []
    with tempfile.TemporaryDirectory(prefix="localflow-worker-check-") as temp:
        work = Path(temp)
        inputs = work / "inputs"
        shutil.copytree(ROOT / "examples", inputs)
        data = work / "data"
        process = None
        log_handle = None
        url = token = ""

        def start():
            nonlocal process, log_handle, url, token
            log = work / "worker.log"
            log_handle = log.open("w")
            env = dict(os.environ, LOCALFLOW_TEST_KEY="synthetic-worker-check-passphrase")
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-u",
                    str(ROOT / "run.py"),
                    "worker",
                    "--port",
                    "0",
                    "--data-dir",
                    str(data),
                    "--passphrase-env",
                    "LOCALFLOW_TEST_KEY",
                ],
                cwd=ROOT,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                text = log.read_text()
                match = re.search(r"http://127\.0\.0\.1:\d+", text)
                if match:
                    url = match.group(0)
                    try:
                        with urllib.request.urlopen(url, timeout=2) as response:
                            html = response.read().decode()
                        token = re.search(r'name="local-session" content="([^"]+)"', html).group(1)
                        return
                    except OSError:
                        pass
                if process.poll() is not None:
                    raise AssertionError("Worker exited: " + text)
                time.sleep(0.1)
            raise AssertionError("Worker startup timed out")

        def stop():
            nonlocal process, log_handle
            if process:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                process = None
            if log_handle:
                log_handle.close()
                log_handle = None

        def api(action, body=None):
            request = urllib.request.Request(
                url + "/api/" + action,
                data=None if body is None else json.dumps(body).encode(),
                headers={"X-Local-Token": token, "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.load(response)

        try:
            start()
            state = api(
                "trigger/start",
                {
                    "id": "invoice-register",
                    "workspace": str(inputs),
                    "mode": "watch",
                    "seconds": 15,
                },
            )
            assert state["enabled"]
            checks.append("A real worker accepts an explicit folder trigger")
            time.sleep(0.2)
            assert process.poll() is None
            assert api("state")["trigger"]["enabled"]
            checks.append("Client disconnect does not stop the worker")
            stop()
            changed = inputs / "invoice-099.txt"
            changed.write_text("Invoice: INV-099\nAmount: 99.00\n")
            before = hashlib.sha256(changed.read_bytes()).hexdigest()
            start()
            assert api("state")["trigger"]["enabled"]
            checks.append("Encrypted trigger configuration resumes after restart")
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                state = api("state")
                if any(job["status"] == "done" for job in state["jobs"]):
                    break
                time.sleep(0.3)
            else:
                raise AssertionError("Change made while stopped was not processed: " + repr(state))
            assert list((data / "exports").rglob("invoice-register.csv"))
            assert hashlib.sha256(changed.read_bytes()).hexdigest() == before
            checks.append("A change made while stopped creates new outputs after restart")
            assert b"Invoice register" not in (data / "app.vault").read_bytes()
            checks.append("The durable database is ciphertext")
            api("trigger/stop", {})
            stop()
            start()
            assert not api("state")["trigger"]["enabled"]
            checks.append("An explicitly stopped trigger stays stopped after restart")
        finally:
            stop()
    report = {"checks": checks, "passed": len(checks), "native_service_installation_tested": False}
    (report_dir / "worker-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
