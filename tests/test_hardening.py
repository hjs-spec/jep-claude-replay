import json
import zipfile
from hashlib import sha256

import pytest
from jep_claude_replay.events.model import make_event
from jep_claude_replay.signature.keyring import Keyring
from jep_claude_replay.signature.runtime import sign_event, sign_events, verify_event_signature
from jep_claude_replay.verification.profile import verify_signature, verify_evidence
from jep_claude_replay.archive.runtime import export_jsonl
from jep_claude_replay.pack.runtime import export_pack, import_pack


def event():
    return make_event("judgment", actor="agent", subject="task", session_id="s", intent="test")


def test_single_and_bulk_signatures_use_same_payload():
    keyring = Keyring.generate(alg="Ed25519")
    source = event()
    single = sign_event(source, keyring).to_dict()
    bulk = sign_events([source.to_dict()], keyring)[0]
    assert single["signature"] == bulk["signature"]
    assert verify_event_signature(single, keyring.public_verifier())
    assert not verify_event_signature(single, Keyring())
    attacker = Keyring.generate(single["signature"]["kid"], alg="Ed25519")
    forged = sign_events([source.to_dict()], attacker)[0]
    assert not verify_event_signature(forged, keyring.public_verifier())


def test_unsigned_archive_is_not_signature_verified():
    assert verify_signature([event().to_dict()])["valid"] is False


def test_evidence_checks_content_digest(tmp_path):
    path = tmp_path / "evidence.txt"
    path.write_bytes(b"original")
    e = {"evidence_refs": [{"uri": "file://evidence.txt", "digest": "sha256:" + sha256(b"original").hexdigest()}]}
    assert verify_evidence([e], base_path=tmp_path)["valid"]
    path.write_bytes(b"changed")
    assert verify_evidence([e], base_path=tmp_path)["failure_codes"] == ["evidence_digest_mismatch"]


def test_new_events_do_not_store_secret_previews():
    e = make_event("judgment", actor="agent", subject="task", session_id="s", intent="test", tool_input={"password": "secret"})
    assert "secret" not in json.dumps(e.to_dict())
    assert e.redacted_input_preview is None
    assert e.tool_input_digest.startswith("sha256:")


def test_import_recomputes_verification_and_rejects_forged_report(tmp_path):
    keyring = Keyring.generate(alg="Ed25519")
    archive = tmp_path / "archive.jsonl"
    export_jsonl([sign_event(event(), keyring)], archive)
    pack = tmp_path / "original.jcrpack"
    export_pack(archive, pack, keyring=keyring)
    assert import_pack(pack, tmp_path / "valid", keyring=keyring.public_verifier())["verification_report"]["valid"]
    with zipfile.ZipFile(pack) as source:
        members = {n: source.read(n) for n in source.namelist()}
    record = json.loads(members["archive.jsonl"])
    record["actor"] = "attacker"
    members["archive.jsonl"] = (json.dumps(record) + "\n").encode()
    members["verification-report.json"] = b'{"valid": true}'
    forged = tmp_path / "forged.jcrpack"
    with zipfile.ZipFile(forged, "w") as target:
        for name, content in members.items():
            target.writestr(name, content)
    result = import_pack(forged, tmp_path / "invalid", keyring=keyring.public_verifier())
    assert result["verification_report"]["valid"] is False
    assert result["embedded_report_untrusted"]["valid"] is True


def test_pack_path_cannot_escape_output_directory(tmp_path):
    path = tmp_path / "unsafe.jcrpack"
    with zipfile.ZipFile(path, "w") as target:
        target.writestr("../escape", "bad")
    with pytest.raises(ValueError, match="escapes"):
        import_pack(path, tmp_path / "output")
    assert not (tmp_path / "escape").exists()
