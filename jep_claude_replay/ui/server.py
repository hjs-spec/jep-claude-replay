"""Tiny stdlib UI/API server."""
from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote

from jep_claude_replay.archive.runtime import load_archive
from jep_claude_replay.replay.engine import replay_session
from jep_claude_replay.verification.runtime import verify_archive_chain

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
REPO = Path(__file__).resolve().parents[2]
ARCHIVES = REPO / "examples" / "archives"


def confined_file(root, relative):
    root = Path(root).resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise PermissionError("path is outside the configured directory")
    return candidate

class Handler(SimpleHTTPRequestHandler):
    archive_root = ARCHIVES

    def translate_path(self, path):
        path = unquote(urlparse(path).path)
        if path in ("/", "/ui", "/ui/"):
            return str((DIST / "index.html") if (DIST / "index.html").exists() else (ROOT / "index.html"))
        return str(confined_file(ROOT, path.lstrip("/")))

    def list_directory(self, path):
        self.send_error(403, "Directory listing is disabled")
        return None

    def do_HEAD(self):
        try:
            return super().do_HEAD()
        except PermissionError:
            self.send_error(403, "Path is outside the configured directory")

    def do_GET(self):
        try:
            self._get()
        except PermissionError:
            self.send_error(403, "Path is outside the configured directory")
        except (FileNotFoundError, IsADirectoryError):
            self.send_error(404, "Archive not found")
        except (ValueError, TypeError, KeyError, UnicodeError):
            self.send_error(400, "Invalid archive")

    def _get(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/archive":
            qs = parse_qs(parsed.query)
            requested = qs.get("path", ["simple_tool_session.jsonl"])[0]
            # Retain the shipped UI's old relative links within the archive root.
            requested = requested.removeprefix("examples/archives/")
            archive = confined_file(self.archive_root, requested)
            if archive.suffix != ".jsonl" or archive.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("unsupported or oversized archive")
            events = load_archive(archive)
            body = {"events": events, "verification": verify_archive_chain(events), "replay": replay_session(events)}
            data = json.dumps(body).encode()
            self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(data); return
        return super().do_GET()


def serve(host="127.0.0.1", port=8765, *, archive_root=None):
    class ConfiguredHandler(Handler):
        pass
    ConfiguredHandler.archive_root = Path(archive_root).resolve() if archive_root else ARCHIVES
    print(f"Serving Claude Replay UI at http://{host}:{port}")
    ThreadingHTTPServer((host, port), ConfiguredHandler).serve_forever()
