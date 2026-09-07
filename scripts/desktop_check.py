"""Test real mouse and keyboard input in a disposable desktop window.

Run only on a test desktop. Linux CI uses xvfb-run, not the user's desktop.
The test does not open a terminal or run commands through desktop input.
"""

import json
from pathlib import Path
import sys
import threading
import time
import tkinter as tk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from localdesk.desktop import execute


def main():
    root = tk.Tk()
    root.title("LocalFlow synthetic desktop test")
    root.geometry("700x320+80+80")
    label = tk.Label(root, text="Synthetic input target. No private data.", font=("sans", 16))
    label.pack(pady=20)
    field = tk.Entry(root, width=40)
    field.pack(pady=20)
    clicked = []
    button = tk.Button(root, text="Record test click", command=lambda: clicked.append(True))
    button.pack(pady=20)
    root.update()
    field.focus_force()
    x = field.winfo_rootx() + 50
    y = field.winfo_rooty() + 10
    bx = button.winfo_rootx() + 40
    by = button.winfo_rooty() + 12
    failures = []
    done = threading.Event()
    outputs = []

    class Context:
        def check(self):
            pass

    def drive():
        try:
            execute(
                [
                    {"type": "click", "x": x, "y": y},
                    {"type": "write", "text": "local-only-7316"},
                    {"type": "click", "x": bx, "y": by},
                ],
                Context(),
                lambda name, raw: outputs.append((name, len(raw))),
                permitted=True,
                dry_run=False,
            )
        except BaseException as exc:
            failures.append(repr(exc))
        finally:
            done.set()

    thread = threading.Thread(target=drive, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not done.is_set() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.02)
    root.update()
    text = field.get()
    root.destroy()
    thread.join(timeout=2)
    assert done.is_set(), "Desktop check timed out"
    assert not failures, failures
    assert text == "local-only-7316", repr(text)
    assert clicked, "The button did not receive a real mouse click"
    report = {
        "backend": "PyAutoGUI and Tk",
        "typed_text_verified": True,
        "mouse_click_verified": True,
        "fail_safe_enabled": True,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
