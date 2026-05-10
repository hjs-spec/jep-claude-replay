"""Tiny stdlib UI/API server."""
from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from jep_claude_replay.archive.runtime import load_archive
from jep_claude_replay.replay.engine import replay_session
from jep_claude_replay.verification.runtime import verify_archive_chain

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
REPO = Path(__file__).resolve().parents[2]

class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path == "/" or path.startswith("/ui"):
            return str((DIST / "index.html") if (DIST / "index.html").exists() else (ROOT / "index.html"))
        return str(ROOT / path.lstrip("/"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/archive":
            qs = parse_qs(parsed.query)
            archive = Path(qs.get("path", ["examples/archives/simple_tool_session.jsonl"])[0])
            if not archive.is_absolute():
                archive = REPO / archive
            events = load_archive(archive)
            body = {"events": events, "verification": verify_archive_chain(events), "replay": replay_session(events)}
            data = json.dumps(body).encode()
            self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(data); return
        return super().do_GET()


def serve(host="127.0.0.1", port=8765):
    print(f"Serving Claude Replay UI at http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
