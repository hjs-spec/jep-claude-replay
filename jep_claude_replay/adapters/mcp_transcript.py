"""Importer for MCP JSON-RPC transcript captures."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jep_claude_replay.claude.adapter import record_session


def load_mcp_transcript(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    return data.get("messages", data.get("events", data if isinstance(data, list) else []))


def normalize_mcp_transcript(records: list[dict], *, session_id: str = "mcp-import") -> dict:
    requests: dict[Any, dict] = {}
    tool_calls: list[dict] = []
    for rec in records:
        msg = rec.get("message", rec)
        method = msg.get("method")
        if method == "tools/call":
            params = msg.get("params", {})
            requests[msg.get("id")] = {"tool_name": params.get("name", "mcp.tool"), "intent": f"MCP tools/call {params.get('name', 'mcp.tool')}", "input": params.get("arguments", {}), "authority_scope": {"profile": "neutral", "authorized_by": "mcp-client", "limits": ["imported-mcp"]}}
        elif "result" in msg and msg.get("id") in requests:
            call = requests.pop(msg.get("id"))
            call.update({"output": msg.get("result"), "verification_intent": "MCP result matched tools/call id.", "verification_state": "passed"})
            tool_calls.append(call)
        elif "error" in msg and msg.get("id") in requests:
            call = requests.pop(msg.get("id"))
            call.update({"status": "failed", "failure_code": "mcp_error", "error": str(msg.get("error"))})
            tool_calls.append(call)
    for call in requests.values():
        call.update({"status": "aborted", "failure_code": "missing_mcp_result", "error": "No matching MCP result."})
        tool_calls.append(call)
    return {"session_id": session_id, "user": "Human", "user_prompt": "Imported MCP transcript", "reasoning_checkpoints": [], "tool_calls": tool_calls, "final_answer": "Imported MCP transcript replay generated.", "status": "completed"}


def record_mcp_transcript(input_path: str | Path, output_path: str | Path, *, session_id: str = "mcp-import"):
    return record_session(normalize_mcp_transcript(load_mcp_transcript(input_path), session_id=session_id), output_path)
