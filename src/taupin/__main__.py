"""Taupin command line.

  python -m taupin                 serve web/ on 127.0.0.1 (first free port from 8780), open the browser
  python -m taupin --demo          same, opening the scripted demo (?demo=1)
  taupin classify <photo> [...]    classify photos with model/taupin.onnx (needs the `classify` extra)
  taupin sync-model                copy model/ into web/model/ so any static server can serve it

The web app loads its model from web/model/. The source of truth is model/ (written by train/),
so `serve` copies it there first; copies work on every OS, symlinks need admin rights on Windows.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import shutil
import socket
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
MODEL_SRC = ROOT / "model"
MODEL_DST = WEB / "model"
MODEL_FILES = ["taupin.onnx", "labels.json", "metrics.json", "MODEL_CARD.md"]
FIRST_PORT = 8780
RESERVED = {8765, 8770}   # used by other local work


def sync_model(src: Path = MODEL_SRC, dst: Path = MODEL_DST) -> list[str]:
    """Copy finished model files into the served tree when they are missing or newer."""
    copied = []
    if not (src / "labels.json").exists() or not (src / "taupin.onnx").exists():
        return copied
    dst.mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        s, d = src / name, dst / name
        if s.exists() and (not d.exists() or s.stat().st_mtime > d.stat().st_mtime or s.stat().st_size != d.stat().st_size):
            shutil.copy2(s, d)
            copied.append(name)
    return copied


def free_port(start: int = FIRST_PORT, host: str = "127.0.0.1", tries: int = 50) -> int:
    for port in range(start, start + tries):
        if port in RESERVED:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(f"no free port in {start}-{start + tries - 1}")


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm",
                      ".webmanifest": "application/manifest+json", ".json": "application/json",
                      ".onnx": "application/octet-stream", ".svg": "image/svg+xml"}

    def end_headers(self):
        # Revalidate on every load; the service worker provides the offline copy.
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, fmt, *args):   # quiet: one line per error only
        if args and str(args[1])[:1] in "45":
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


def make_server(port: int, host: str = "127.0.0.1") -> http.server.ThreadingHTTPServer:
    return http.server.ThreadingHTTPServer((host, port), functools.partial(Handler, directory=str(WEB)))


def serve(port: int | None, open_browser: bool, demo: bool) -> None:
    copied = sync_model()
    if copied:
        print("model: copied", ", ".join(copied), "into web/model/")
    elif not (MODEL_DST / "taupin.onnx").exists():
        print("model: not installed (the app runs without it; see README, Obtaining the model)")
    port = port or free_port()
    httpd = make_server(port)
    url = f"http://127.0.0.1:{port}/" + ("?demo=1" if demo else "")
    print(f"Taupin at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.4, webbrowser.open, (url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def classify_cmd(photos: list[Path], model_dir: Path | None) -> int:
    try:
        from .classify import classify, format_answer
    except ImportError:   # pragma: no cover - message only
        print("needs the classify extra: uv run --extra classify taupin classify <photo>", file=sys.stderr)
        return 2
    d = model_dir or (MODEL_SRC if (MODEL_SRC / "taupin.onnx").exists() else MODEL_DST)
    if not (d / "taupin.onnx").exists() or not (d / "labels.json").exists():
        print(f"model not installed: {d}/taupin.onnx and labels.json are missing", file=sys.stderr)
        return 2
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        print("needs the classify extra: uv run --extra classify taupin classify <photo>", file=sys.stderr)
        return 2
    for p in photos:
        r = classify(p, d)
        print(f"{p.name}: {format_answer(r)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="taupin", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, help=f"port (default: first free from {FIRST_PORT})")
    p.add_argument("--no-browser", action="store_true", help="do not open a browser")
    p.add_argument("--demo", action="store_true", help="open the scripted demo (?demo=1)")
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("classify", help="classify one or more photos")
    c.add_argument("photos", nargs="+", type=Path)
    c.add_argument("--model", type=Path, help="directory with taupin.onnx and labels.json")
    sub.add_parser("sync-model", help="copy model/ into web/model/")
    a = p.parse_args(argv)
    if a.cmd == "classify":
        return classify_cmd(a.photos, a.model)
    if a.cmd == "sync-model":
        copied = sync_model()
        print("copied:", ", ".join(copied) if copied else "nothing (missing or up to date)")
        return 0
    serve(a.port, not a.no_browser, a.demo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
