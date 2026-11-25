"""A small HTTP collector for playtests (standard library only).

POST /v1/events with a JSON array of telemetry rows; each row is appended to
<dir>/<sid>.jsonl. GET /health answers "ok". With a token set, requests must
carry X-Playtest-Token. Session ids are checked before they become file names,
bodies are capped, and nothing else on disk is touched.

For a playtest in the room, run it on your machine and point the game at
http://<your LAN address>:8787/v1/events. Over the internet, put it behind
HTTPS (any reverse proxy) and set a token.
"""

from __future__ import annotations

import hmac
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_BODY = 5 * 1024 * 1024


def make_handler(root: Path, token: str = ""):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "sga-playtest-collector/1"

        def _reply(self, code: int, body: str) -> None:
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._reply(200, "ok\n") if self.path == "/health" else self._reply(404, "not found\n")

        def do_POST(self):
            if self.path != "/v1/events":
                return self._reply(404, "not found\n")
            if token and not hmac.compare_digest(self.headers.get("X-Playtest-Token", ""), token):
                return self._reply(401, "bad token\n")
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_BODY:
                return self._reply(413, "body missing or too large\n")
            try:
                rows = json.loads(self.rfile.read(n))
            except json.JSONDecodeError:
                return self._reply(400, "not JSON\n")
            if not isinstance(rows, list):
                return self._reply(400, "expected a JSON array of events\n")
            by_sid: dict[str, list] = {}
            for r in rows:
                if isinstance(r, dict) and isinstance(r.get("sid"), str) and SID.match(r["sid"]) and "ev" in r:
                    by_sid.setdefault(r["sid"], []).append(r)
            with lock:
                root.mkdir(parents=True, exist_ok=True)
                for sid, rs in by_sid.items():
                    with open(root / f"{sid}.jsonl", "a", encoding="utf-8") as f:
                        for r in rs:
                            f.write(json.dumps(r, separators=(",", ":")) + "\n")
            self._reply(200, f"stored {sum(len(v) for v in by_sid.values())} of {len(rows)}\n")

        def log_message(self, fmt, *args):
            pass

    return Handler


def serve(root: Path, host: str, port: int, token: str = "") -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(root, token))
