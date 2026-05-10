"""Mock Claude session adapter: Claude JSON -> JEP-style events."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jep_claude_replay.archive.runtime import export_jsonl
from jep_claude_replay.events.model import JEPEvent, make_event


def parse_claude_session(session_json: str | Path | dict) -> dict:
    if isinstance(session_json, (str, Path)):
        return json.loads(Path(session_json).read_text(encoding="utf-8"))
    return session_json


def _append(events: list[JEPEvent], event: JEPEvent) -> JEPEvent:
    events.append(event)
    return event


def emit_judgment_event(session: dict, events: list[JEPEvent], intent: str, **kwargs: Any) -> JEPEvent:
    return _append(events, make_event("judgment", actor="Claude", subject=session.get("user", "Human"), session_id=session["session_id"], intent=intent, previous_event_hash=events[-1].event_hash if events else None, delegation_chain=["Human", "Claude"], **kwargs))


def emit_delegation_event(session: dict, events: list[JEPEvent], tool_call: dict, parent: JEPEvent | None = None) -> JEPEvent:
    return _append(events, make_event("delegation", actor="Claude", subject=tool_call.get("tool_name", "MCP Tool"), session_id=session["session_id"], parent_event_id=parent.event_id if parent else None, previous_event_hash=events[-1].event_hash if events else None, intent=tool_call.get("intent", "Delegate tool execution"), tool_name=tool_call.get("tool_name"), tool_input=tool_call.get("input"), authority_scope=tool_call.get("authority_scope", {"profile": "neutral", "limits": ["mock-only"]}), delegation_chain=["Human", "Claude", tool_call.get("tool_name", "MCP Tool")], evidence_refs=tool_call.get("evidence_refs", [])))


def emit_verification_event(session: dict, events: list[JEPEvent], tool_call: dict, parent: JEPEvent | None = None) -> JEPEvent:
    state = tool_call.get("verification_state", "passed")
    return _append(events, make_event("verification", actor="Claude", subject=tool_call.get("tool_name", "MCP Tool"), session_id=session["session_id"], parent_event_id=parent.event_id if parent else None, previous_event_hash=events[-1].event_hash if events else None, intent=tool_call.get("verification_intent", "Verify tool result"), tool_name=tool_call.get("tool_name"), tool_input=tool_call.get("input"), tool_output=tool_call.get("output"), authority_scope=tool_call.get("authority_scope", {"profile": "neutral", "limits": ["mock-only"]}), delegation_chain=["Human", "Claude", tool_call.get("tool_name", "MCP Tool")], verification_state=state, validation_result={"valid": state == "passed", "failure_codes": [], "warnings": []}, evidence_refs=tool_call.get("evidence_refs", [])))


def emit_termination_event(session: dict, events: list[JEPEvent], status: str | None = None, failure_code: str | None = None) -> JEPEvent:
    return _append(events, make_event("termination", actor="Claude", subject=session.get("user", "Human"), session_id=session["session_id"], previous_event_hash=events[-1].event_hash if events else None, intent=session.get("final_answer", "Session terminated"), authority_scope={"profile": "neutral", "limits": ["session-end"]}, delegation_chain=["Human", "Claude"], verification_state=status or session.get("status", "completed"), failure_code=failure_code or session.get("failure_code"), validation_result={"valid": session.get("status", "completed") == "completed", "failure_codes": [failure_code] if failure_code else [], "warnings": []}))


def events_from_session(session_json: str | Path | dict) -> list[JEPEvent]:
    session = parse_claude_session(session_json)
    events: list[JEPEvent] = []
    root = emit_judgment_event(session, events, session.get("user_prompt", "Task accepted"), authority_scope={"profile": "neutral", "authorized_by": session.get("user", "Human")})
    for checkpoint in session.get("reasoning_checkpoints", []):
        emit_judgment_event(session, events, checkpoint.get("summary", "Reasoning checkpoint"), parent_event_id=root.event_id, authority_scope={"profile": "neutral", "reasoning": "redacted-summary"})
    for call in session.get("tool_calls", []):
        d = emit_delegation_event(session, events, call, root)
        if call.get("status") in {"denied", "aborted", "failed"}:
            _append(events, make_event("termination", actor="MCP", subject=call.get("tool_name", "tool"), session_id=session["session_id"], parent_event_id=d.event_id, previous_event_hash=events[-1].event_hash, intent=call.get("error", "Tool execution terminated"), tool_name=call.get("tool_name"), authority_scope=call.get("authority_scope", {"profile": "neutral"}), delegation_chain=["Human", "Claude", call.get("tool_name", "MCP Tool")], verification_state="failed", failure_code=call.get("failure_code", "tool_failed"), validation_result={"valid": False, "failure_codes": [call.get("failure_code", "tool_failed")], "warnings": []}))
        else:
            emit_verification_event(session, events, call, d)
    emit_termination_event(session, events)
    return events


def record_session(session_json: str | Path | dict, output_path: str | Path) -> list[JEPEvent]:
    events = events_from_session(session_json)
    export_jsonl(events, output_path)
    return events
