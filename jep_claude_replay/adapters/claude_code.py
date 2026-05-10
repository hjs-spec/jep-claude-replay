"""Importers for real-world Claude Code style transcripts.

The importer accepts JSON or JSONL exports containing common transcript shapes:
messages with `role`, content blocks with `tool_use`/`tool_result`, and shell/file
operation records emitted by Claude Code-like runtimes. It normalizes them into
the mock session schema consumed by the core adapter.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jep_claude_replay.claude.adapter import record_session


def load_transcript(path: str | Path) -> list[dict[str, Any]] | dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


def _content_blocks(message: dict) -> list[dict]:
    content = message.get("content", [])
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def normalize_claude_code_transcript(transcript: list[dict] | dict, *, session_id: str | None = None) -> dict:
    records = transcript.get("messages", transcript.get("events", [])) if isinstance(transcript, dict) else transcript
    sid = session_id or (transcript.get("session_id") if isinstance(transcript, dict) else None) or "claude-code-import"
    user_prompt = "Imported Claude Code transcript"
    checkpoints: list[dict] = []
    tool_calls: list[dict] = []
    pending: dict[str, dict] = {}
    final_answer = "Imported transcript completed."

    for record in records:
        role = record.get("role") or record.get("type")
        if role == "user" and not record.get("is_tool_result"):
            blocks = _content_blocks(record)
            text = " ".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
            if text:
                user_prompt = text
        if role == "assistant":
            text = " ".join(b.get("text", "") for b in _content_blocks(record) if b.get("type") == "text").strip()
            if text:
                checkpoints.append({"summary": text[:240]})
                final_answer = text
        for block in _content_blocks(record):
            if block.get("type") in {"tool_use", "server_tool_use"}:
                call_id = block.get("id") or block.get("tool_use_id") or f"tool-{len(pending)+1}"
                tool = block.get("name") or block.get("tool_name") or "mcp.tool"
                pending[call_id] = {"tool_name": tool, "intent": f"Imported Claude Code tool use: {tool}", "input": block.get("input", {}), "authority_scope": {"profile": "neutral", "authorized_by": "transcript", "limits": ["imported"]}, "verification_state": "unchecked"}
            if block.get("type") == "tool_result":
                call_id = block.get("tool_use_id") or block.get("id")
                call = pending.get(call_id) or {"tool_name": block.get("name", "mcp.tool"), "intent": "Imported tool result", "input": {}}
                call["output"] = block.get("content")
                call["verification_intent"] = "Imported transcript contains tool result."
                call["verification_state"] = "failed" if block.get("is_error") else "passed"
                tool_calls.append(call)
        if record.get("tool_name") or record.get("tool"):
            tool = record.get("tool_name") or record.get("tool")
            tool_calls.append({"tool_name": tool, "intent": record.get("intent", f"Imported action {tool}"), "input": record.get("input", record.get("args", {})), "output": record.get("output", record.get("result")), "authority_scope": record.get("authority_scope", {"profile": "neutral", "authorized_by": "transcript", "limits": ["imported"]}), "verification_intent": "Imported record result available.", "verification_state": "failed" if record.get("error") else "passed"})

    # Add pending calls without explicit result as aborted tool calls.
    for call in pending.values():
        if call not in tool_calls and "output" not in call:
            call.update({"status": "aborted", "failure_code": "missing_tool_result", "error": "Transcript ended before tool result."})
            tool_calls.append(call)

    return {"session_id": sid, "user": "Human", "user_prompt": user_prompt, "reasoning_checkpoints": checkpoints[:8], "tool_calls": tool_calls, "final_answer": final_answer, "status": "completed"}


def record_claude_code_transcript(input_path: str | Path, output_path: str | Path, *, session_id: str | None = None):
    return record_session(normalize_claude_code_transcript(load_transcript(input_path), session_id=session_id), output_path)
