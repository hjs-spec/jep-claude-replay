from pathlib import Path

from jep_claude_replay.adapters.claude_code import normalize_claude_code_transcript, record_claude_code_transcript
from jep_claude_replay.adapters.mcp_transcript import normalize_mcp_transcript
from jep_claude_replay.adapters.provenance import api_provenance, browser_provenance
from jep_claude_replay.archive.runtime import export_jsonl, load_archive
from jep_claude_replay.artifacts.manifest import build_manifest
from jep_claude_replay.canonicalization.jcs import canonicalize
from jep_claude_replay.evidence.policy import EvidencePolicy
from jep_claude_replay.events.model import make_event
from jep_claude_replay.plugins.diff_verifier import verify_diff
from jep_claude_replay.signature.keyring import Keyring
from jep_claude_replay.signature.runtime import sign_events, verify_archive_signatures
from jep_claude_replay.verification.runtime import verify_archive_chain


def test_rfc8785_canonicalization_vector():
    assert canonicalize({"numbers": [333333333.3333333, 1e30, 4.5], "string": "€$\u000f\n"}) == '{"numbers":[333333333.3333333,1e+30,4.5],"string":"€$\\u000f\\n"}'


def test_claude_code_importer_maps_tool_use_and_result(tmp_path):
    out = tmp_path / "cc.jsonl"
    events = record_claude_code_transcript("examples/transcripts/claude_code_transcript.jsonl", out, session_id="cc-test")
    assert out.exists()
    assert any(e.tool_name == "filesystem.read" for e in events)
    assert verify_archive_chain(load_archive(out))["valid"] is True


def test_mcp_importer_maps_json_rpc_tools_call():
    session = normalize_mcp_transcript([
        {"id": 1, "method": "tools/call", "params": {"name": "api.call", "arguments": {"endpoint": "https://api.example.test"}}},
        {"id": 1, "result": {"status": 200}},
    ], session_id="mcp-test")
    assert session["tool_calls"][0]["tool_name"] == "api.call"
    assert session["tool_calls"][0]["verification_state"] == "passed"


def test_detached_signatures_and_key_rotation(tmp_path):
    e = make_event("judgment", actor="Claude", subject="Human", session_id="signed", intent="accept")
    path = tmp_path / "archive.jsonl"
    export_jsonl([e], path)
    keyring = Keyring.generate("k1")
    signed = sign_events(load_archive(path), keyring)
    assert verify_archive_signatures(signed, keyring)["valid"] is True
    keyring.rotate("k2")
    signed2 = sign_events(signed, keyring)
    assert signed2[0]["signature"]["kid"] == "k2"
    assert verify_archive_signatures(signed2, keyring)["valid"] is True


def test_artifact_manifest_and_evidence_policy():
    manifest = build_manifest(["examples/mock_claude_session/simple_tool_session.json"], session_id="s")
    assert manifest["manifest_digest"].startswith("sha256:")
    policy = EvidencePolicy(mode="digest-only")
    handled = policy.apply({"secret": "value"})
    assert handled["digest"].startswith("sha256:") and handled["preview"] is None and handled["raw"] is None


def test_diff_verifier_and_provenance_adapters():
    diff = verify_diff("a\n", "a\nb\n", required_additions=["b"])
    assert diff["valid"] is True and "+b" in diff["diff"]
    browser = browser_provenance("query", [{"url": "https://example.com/a"}])
    assert browser["origins"] == ["example.com"]
    api = api_provenance("post", "https://api.example.com/v1", {"x": 1}, {"status": 201})
    assert api["endpoint_origin"] == "api.example.com"

from jep_claude_replay.pack.runtime import export_pack, import_pack
from jep_claude_replay.verification.profile import verify_profiles


def test_rfc8785_number_and_unicode_edge_vectors():
    assert canonicalize([1e30, 4.5, 0.002, 1e-27]) == '[1e+30,4.5,0.002,1e-27]'
    assert canonicalize({"\u20ac": "Euro", "\r": "Carriage Return", "1": "One"}) == '{"\\r":"Carriage Return","1":"One","€":"Euro"}'
    assert canonicalize({"emoji": "😃", "control": "\u000f"}) == '{"control":"\\u000f","emoji":"😃"}'


def test_ed25519_detached_signatures_verify_with_public_key(tmp_path):
    e = make_event("judgment", actor="Claude", subject="Human", session_id="ed", intent="accept")
    path = tmp_path / "ed.jsonl"
    export_jsonl([e], path)
    keyring = Keyring.generate("ed1", alg="Ed25519")
    signed = sign_events(load_archive(path), keyring, alg="Ed25519")
    sig = signed[0]["signature"]
    assert sig["alg"] == "Ed25519" and sig["public_key"]
    assert verify_archive_signatures(signed, Keyring())["valid"] is False
    verifier = keyring.public_verifier()
    assert verify_archive_signatures(signed, verifier)["valid"] is True


def test_layered_verification_profiles_and_artifact_pack(tmp_path):
    events = load_archive("examples/archives/simple_tool_session.signed.jsonl")
    keyring = Keyring.load("examples/keyrings/example_keyring.json")
    profiles = verify_profiles(events, keyring=keyring)
    assert profiles["profiles"]["basic"]["valid"] is True
    assert profiles["profiles"]["signature"]["valid"] is True
    pack_path = tmp_path / "session.jcrpack"
    export_pack("examples/archives/simple_tool_session.signed.jsonl", pack_path, evidence_paths=["examples/mock_claude_session/simple_tool_session.json"], keyring=keyring)
    imported = import_pack(pack_path, tmp_path / "unpacked")
    assert imported["pack_index"]["pack_version"] == "jcr-pack-v1"
    assert len(imported["events"]) == len(events)


def test_golden_archive_hash_signature_and_replay_outputs():
    golden = load_archive("tests/golden/golden_archive.jsonl")
    hashes = [e["event_hash"] for e in golden]
    assert hashes == [
        "sha256:e281847535ca3a6682a84399921331382927a9abce36d2ede483d7f518e53781",
        "sha256:b9f794a1a8f673ae78cd206179f4617710b067eeea0d2add36a803ce1b15f048",
        "sha256:18892e52d850af6ebbf0d588603f0b46f7f9ba661e608795260abddf05fe0d6a",
    ]
    assert verify_archive_chain(golden)["valid"] is True
    from pathlib import Path
    from jep_claude_replay.replay.engine import replay_session
    assert canonicalize(replay_session(golden)) == Path("tests/golden/golden_replay.json").read_text(encoding="utf-8").strip()
    ed_keyring = Keyring.load("tests/golden/golden_ed25519_keyring.json")
    assert verify_archive_signatures(load_archive("tests/golden/golden_archive.ed25519.jsonl"), ed_keyring)["valid"] is True


def test_claude_code_fixture_matrix_imports_all_dialects():
    from pathlib import Path
    from jep_claude_replay.adapters.claude_code import record_claude_code_transcript
    for fixture in Path("examples/transcripts/claude_code_matrix").glob("*.jsonl"):
        events = record_claude_code_transcript(fixture, Path("/tmp") / f"{fixture.stem}.jsonl", session_id=f"test-{fixture.stem}")
        assert events[0].event_type == "judgment"
        assert events[-1].event_type == "termination"
        assert any(e.event_type in {"delegation", "termination", "verification"} for e in events)
