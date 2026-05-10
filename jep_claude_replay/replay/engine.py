"""Replay engine for timelines, delegation chains, and tool flow."""
from __future__ import annotations

from collections import defaultdict


def build_timeline(events: list[dict]) -> list[dict]:
    items = []
    for e in events:
        valid = e.get("validation_result", {}).get("valid")
        items.append({
            "time": e.get("timestamp"),
            "event_id": e.get("event_id"),
            "event_type": e.get("event_type"),
            "verb": e.get("verb"),
            "actor": e.get("actor"),
            "action": e.get("intent"),
            "tool_name": e.get("tool_name"),
            "authority_scope": e.get("authority_scope"),
            "verification_state": e.get("verification_state"),
            "event_hash": e.get("event_hash"),
            "previous_event_hash": e.get("previous_event_hash"),
            "status": "fail" if e.get("failure_code") or valid is False else "pass" if valid is True or e.get("event_type") != "termination" else e.get("verification_state", "unknown"),
        })
    return items


def build_lineage_graph(events: list[dict]) -> dict:
    nodes = {"Human": {"id": "Human", "type": "human"}, "Claude": {"id": "Claude", "type": "agent"}}
    edges = []
    for e in events:
        actor = e.get("actor") or "unknown"
        subject = e.get("subject") or e.get("tool_name") or "unknown"
        nodes.setdefault(actor, {"id": actor, "type": "actor"})
        nodes.setdefault(subject, {"id": subject, "type": _node_type(subject)})
        rel = {"delegation": "delegated", "judgment": "judged", "verification": "verified", "termination": "terminated"}.get(e.get("event_type"), "linked")
        edges.append({"source": actor, "target": subject, "label": rel, "event_id": e.get("event_id")})
        if e.get("tool_name"):
            res = _resource_node(e["tool_name"])
            nodes.setdefault(res, {"id": res, "type": res.lower()})
            edges.append({"source": subject, "target": res, "label": "invoked", "event_id": e.get("event_id")})
    return {"nodes": list(nodes.values()), "edges": edges}


def _node_type(name: str) -> str:
    if name.startswith("filesystem"):
        return "file"
    if name.startswith("shell"):
        return "shell"
    if name.startswith("browser"):
        return "browser"
    if name.startswith("api"):
        return "api"
    return "mcp_tool"


def _resource_node(tool_name: str) -> str:
    return {"filesystem.read": "File", "filesystem.write": "File", "shell.run": "Shell", "browser.search": "Browser", "api.call": "API"}.get(tool_name, "MCP Tool")


def reconstruct_delegation_chain(events: list[dict]) -> dict:
    return {e.get("event_id"): e.get("delegation_chain", []) for e in events}


def reconstruct_tool_flow(events: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for e in events:
        if e.get("tool_name"):
            grouped[e.get("tool_name")].append(e.get("event_id"))
    return [{"tool_name": k, "events": v} for k, v in grouped.items()]


def replay_session(events: list[dict], session_id: str | None = None) -> dict:
    selected = [e for e in events if session_id is None or e.get("session_id") == session_id]
    from jep_claude_replay.verification.runtime import verify_archive_chain
    return {
        "session_id": session_id or (selected[0].get("session_id") if selected else None),
        "timeline": build_timeline(selected),
        "lineage_graph": build_lineage_graph(selected),
        "delegation_chains": reconstruct_delegation_chain(selected),
        "tool_flow": reconstruct_tool_flow(selected),
        "verification": verify_archive_chain(selected),
    }
