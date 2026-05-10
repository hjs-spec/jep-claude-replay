"""Append-only JSONL archive runtime."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from jep_claude_replay.canonicalization.jcs import canonicalize
from jep_claude_replay.events.model import JEPEvent


class JSONLArchive:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append_event(self, event: JEPEvent | dict) -> None:
        data = event.to_dict() if isinstance(event, JEPEvent) else event
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(canonicalize(data) + "\n")

    def export_jsonl(self, path: str | Path) -> None:
        Path(path).write_text(self.path.read_text(encoding="utf-8"), encoding="utf-8")

    def load(self) -> list[dict]:
        return load_archive(self.path)

    def list_events(self, session_id: str) -> list[dict]:
        return [e for e in self.load() if e.get("session_id") == session_id]

    def verify_chain(self, session_id: str | None = None) -> dict:
        from jep_claude_replay.verification.runtime import verify_archive_chain
        events = self.load()
        if session_id:
            events = [e for e in events if e.get("session_id") == session_id]
        return verify_archive_chain(events)


def append_event(path: str | Path, event: JEPEvent | dict) -> None:
    JSONLArchive(path).append_event(event)


def load_archive(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    events: list[dict] = []
    for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            event = json.loads(line)
            event["_archive_line"] = line_no
            events.append(event)
    return events


def list_events(path: str | Path, session_id: str) -> list[dict]:
    return [e for e in load_archive(path) if e.get("session_id") == session_id]


def export_jsonl(events: Iterable[JEPEvent | dict], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for event in events:
            data = event.to_dict() if isinstance(event, JEPEvent) else event
            data.pop("_archive_line", None)
            fh.write(canonicalize(data) + "\n")


def detect_tampering(path: str | Path) -> dict:
    from jep_claude_replay.verification.runtime import verify_archive_chain
    return verify_archive_chain(load_archive(path))
