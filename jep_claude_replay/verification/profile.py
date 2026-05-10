"""Layered verification profiles for replay archives."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jep_claude_replay.archive.runtime import load_archive
from jep_claude_replay.signature.keyring import Keyring
from jep_claude_replay.signature.runtime import verify_archive_signatures
from jep_claude_replay.verification.runtime import (
    verify_archive_chain,
    verify_event_hash,
    verify_ext_crit,
    verify_required_fields,
)


def _merge(results: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    tampered: list[str] = []
    for item in results:
        failures.extend(item.get("failure_codes", []))
        warnings.extend(item.get("warnings", []))
        tampered.extend(item.get("tampered_events", []))
    return {"valid": not failures, "failure_codes": sorted(set(failures)), "warnings": warnings, "tampered_events": sorted(set(tampered))}


def verify_basic(events: list[dict]) -> dict:
    checks = []
    for event in events:
        checks.extend([verify_required_fields(event), verify_event_hash(event), verify_ext_crit(event)])
    return {"validation_level": "basic", **_merge(checks)}


def verify_chain(events: list[dict]) -> dict:
    res = verify_archive_chain(events)
    return {**res, "validation_level": "chain"}


def verify_signature(events: list[dict], keyring: Keyring | None = None) -> dict:
    if keyring is None:
        signed = [e for e in events if (e.get("signature") or {}).get("value")]
        if not signed:
            return {"valid": True, "validation_level": "signature", "failure_codes": [], "warnings": ["archive has no signatures"], "tampered_events": []}
        return {"valid": False, "validation_level": "signature", "failure_codes": ["missing_keyring"], "warnings": [], "tampered_events": [e.get("event_id", "<unknown>") for e in signed]}
    return verify_archive_signatures(events, keyring)


def verify_replay(events: list[dict]) -> dict:
    from jep_claude_replay.replay.engine import replay_session
    replay = replay_session(events)
    warnings = [] if replay.get("timeline") else ["empty replay timeline"]
    return {"valid": bool(replay.get("timeline")), "validation_level": "replay", "failure_codes": [] if replay.get("timeline") else ["empty_replay"], "warnings": warnings, "tampered_events": []}


def verify_evidence(events: list[dict], *, base_path: str | Path = ".") -> dict:
    failures: list[str] = []
    warnings: list[str] = []
    root = Path(base_path)
    for event in events:
        for ref in event.get("evidence_refs", []) or []:
            uri = ref.get("uri", "")
            if uri.startswith("file://"):
                candidate = Path(uri.removeprefix("file://"))
                if not candidate.is_absolute():
                    candidate = root / candidate
                if not candidate.exists():
                    failures.append("missing_evidence")
                    warnings.append(f"missing evidence for {event.get('event_id')}: {uri}")
    return {"valid": not failures, "validation_level": "evidence", "failure_codes": sorted(set(failures)), "warnings": warnings, "tampered_events": []}


def verify_policy(events: list[dict]) -> dict:
    failures: list[str] = []
    warnings: list[str] = []
    for event in events:
        if event.get("redacted_input_preview") and event.get("tool_input_digest") is None:
            failures.append("policy_digest_missing")
        if event.get("redacted_output_preview") and event.get("tool_output_digest") is None:
            failures.append("policy_digest_missing")
        if "raw_input" in event or "raw_output" in event:
            failures.append("policy_raw_payload_forbidden")
            warnings.append(f"raw payload found in {event.get('event_id')}")
    return {"valid": not failures, "validation_level": "policy", "failure_codes": sorted(set(failures)), "warnings": warnings, "tampered_events": []}


def verify_profiles(events: list[dict], *, keyring: Keyring | None = None, base_path: str | Path = ".") -> dict:
    profiles = {
        "basic": verify_basic(events),
        "chain": verify_chain(events),
        "signature": verify_signature(events, keyring),
        "replay": verify_replay(events),
        "evidence": verify_evidence(events, base_path=base_path),
        "policy": verify_policy(events),
    }
    failures = sorted({code for profile in profiles.values() for code in profile.get("failure_codes", [])})
    return {"valid": all(p["valid"] for p in profiles.values()), "validation_level": "profile", "failure_codes": failures, "profiles": profiles}


def verify_archive_profiles(path: str | Path, *, keyring: Keyring | None = None) -> dict:
    return verify_profiles(load_archive(path), keyring=keyring, base_path=Path(path).parent.parent.parent if len(Path(path).parts) > 2 else ".")
