from pathlib import Path

import pytest

from jep_claude_replay.archive.runtime import export_jsonl, load_archive
from jep_claude_replay.canonicalization.jcs import canonicalize
from jep_claude_replay.claude.adapter import events_from_session
from jep_claude_replay.events.model import compute_event_hash, make_event
from jep_claude_replay.mcp.wrapper import MCPRecorder, shell_run
from jep_claude_replay.replay.engine import build_timeline, reconstruct_delegation_chain
from jep_claude_replay.verification.runtime import verify_archive_chain, verify_ext_crit, verify_nonce_uniqueness


def test_deterministic_canonicalization():
    assert canonicalize({"b": 1, "a": [2, 3]}) == canonicalize({"a": [2, 3], "b": 1})


def test_event_hash_stable():
    e = make_event("judgment", actor="Claude", subject="Human", session_id="s", intent="accept", timestamp="2026-01-01T00:00:00Z", nonce="n")
    assert e.event_hash == compute_event_hash(e.to_dict())


def test_previous_event_hash_chain_and_archive_pass(tmp_path):
    e1 = make_event("judgment", actor="Claude", subject="Human", session_id="s", intent="accept", nonce="n1")
    e2 = make_event("termination", actor="Claude", subject="Human", session_id="s", intent="done", previous_event_hash=e1.event_hash, nonce="n2")
    path = tmp_path / "a.jsonl"
    export_jsonl([e1, e2], path)
    assert verify_archive_chain(load_archive(path))["valid"] is True


def test_tampered_archive_verify_fail():
    res = verify_archive_chain(load_archive("examples/archives/tampered_session.jsonl"))
    assert res["valid"] is False
    assert "invalid_event_hash" in res["failure_codes"]


def test_duplicate_nonce_detection():
    e1 = make_event("judgment", actor="Claude", subject="Human", session_id="s", intent="a", nonce="same")
    e2 = make_event("judgment", actor="Claude", subject="Human", session_id="s", intent="b", previous_event_hash=e1.event_hash, nonce="same")
    assert "duplicate_nonce" in verify_nonce_uniqueness([e1.to_dict(), e2.to_dict()])["failure_codes"]


def test_unsupported_ext_crit_fail():
    e = make_event("judgment", actor="Claude", subject="Human", session_id="s", intent="a", ext_crit=["unknown.required"])
    assert "unsupported_critical_extension" in verify_ext_crit(e.to_dict())["failure_codes"]


def test_delegation_chain_reconstruction_and_timeline():
    events = [e.to_dict() for e in events_from_session("examples/mock_claude_session/simple_tool_session.json")]
    chains = reconstruct_delegation_chain(events)
    assert any("filesystem.read" in chain for chain in chains.values())
    timeline = build_timeline(events)
    assert timeline[0]["event_type"] == "judgment"
    assert any(item["tool_name"] == "filesystem.read" for item in timeline)


def test_mcp_wrapper_emits_correct_events():
    rec = MCPRecorder("mcp-test")
    tool = rec.wrap_tool("shell.run", shell_run, {"profile": "neutral", "limits": ["mock-shell-only"]})
    out = tool({"command": "rm -rf /"})
    assert out["mock"] is True
    assert [e.event_type for e in rec.events] == ["delegation", "verification"]
    assert rec.events[0].tool_name == "shell.run"
