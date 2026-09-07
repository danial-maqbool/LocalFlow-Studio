import argparse
import threading
import webbrowser
from localflow.server import serve

p = argparse.ArgumentParser(description="Run LocalFlow Studio on this PC.")
p.add_argument("--host", default="127.0.0.1")
p.add_argument("--port", type=int, default=8761)
p.add_argument("--no-browser", action="store_true")
a = p.parse_args()
if a.host not in {"127.0.0.1", "localhost"}:
    raise SystemExit("LocalFlow only binds to localhost in this release.")
if not a.no_browser:
    threading.Timer(0.6, lambda: webbrowser.open(f"http://127.0.0.1:{a.port}")).start()
serve(a.host, a.port)
