"""Verification runtime for event hashes, chains, extensions, and replay safety."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from jep_claude_replay.events.model import REQUIRED_FIELDS, compute_event_hash

SUPPORTED_CRITICAL_EXTENSIONS = {"jep_claude_replay.v0"}


def result(valid: bool, level: str, failure_codes: list[str] | None = None, warnings: list[str] | None = None, tampered_events: list[str] | None = None) -> dict:
    return {
        "valid": valid,
        "validation_level": level,
        "failure_codes": sorted(set(failure_codes or [])),
        "warnings": warnings or [],
        "tampered_events": tampered_events or [],
    }


def verify_event_hash(event: dict) -> dict:
    expected = compute_event_hash(event)
    ok = event.get("event_hash") == expected
    return result(ok, "basic", [] if ok else ["invalid_event_hash"], tampered_events=[] if ok else [event.get("event_id", "<unknown>")])


def verify_required_fields(event: dict) -> dict:
    missing = [f for f in REQUIRED_FIELDS if f not in event]
    return result(not missing, "basic", ["missing_required_field"] if missing else [], [f"missing: {missing}"] if missing else [])


def verify_ext_crit(event: dict) -> dict:
    unsupported = [x for x in event.get("ext_crit", []) if x not in SUPPORTED_CRITICAL_EXTENSIONS]
    return result(not unsupported, "basic", ["unsupported_critical_extension"] if unsupported else [], [f"unsupported ext_crit: {unsupported}"] if unsupported else [])


def verify_nonce_uniqueness(events: Iterable[dict]) -> dict:
    nonces = [e.get("nonce") for e in events if e.get("nonce")]
    dupes = [n for n, c in Counter(nonces).items() if c > 1]
    return result(not dupes, "chain", ["duplicate_nonce"] if dupes else [], [f"duplicate nonces: {dupes}"] if dupes else [])


def verify_delegation_consistency(events: Iterable[dict]) -> dict:
    failures: list[str] = []
    warnings: list[str] = []
    by_id = {e.get("event_id"): e for e in events}
    for e in events:
        if e.get("event_type") in {"delegation", "verification"} and e.get("tool_name"):
            chain = e.get("delegation_chain") or []
            if not chain:
                failures.append("delegation_chain_missing")
                warnings.append(f"{e.get('event_id')} has no delegation_chain")
            for ref in chain:
                if ref not in by_id and ref not in {"Human", "Claude", "MCP", e.get("tool_name")}:
                    failures.append("delegation_chain_missing")
                    warnings.append(f"{e.get('event_id')} references missing chain element {ref}")
    return result(not failures, "replay", failures, warnings)


def verify_archive_chain(events: list[dict]) -> dict:
    failures: list[str] = []
    warnings: list[str] = []
    tampered: list[str] = []
    previous_by_session: dict[str, str | None] = defaultdict(lambda: None)

    for e in events:
        for check in (verify_required_fields(e), verify_event_hash(e), verify_ext_crit(e)):
            failures.extend(check["failure_codes"])
            warnings.extend(check["warnings"])
            tampered.extend(check.get("tampered_events", []))
        sid = e.get("session_id")
        expected_prev = previous_by_session[sid]
        if e.get("previous_event_hash") != expected_prev:
            failures.append("broken_hash_chain")
            tampered.append(e.get("event_id", "<unknown>"))
            warnings.append(f"broken chain at {e.get('event_id')}: expected {expected_prev}, got {e.get('previous_event_hash')}")
        previous_by_session[sid] = e.get("event_hash")

    for check in (verify_nonce_uniqueness(events), verify_delegation_consistency(events)):
        failures.extend(check["failure_codes"])
        warnings.extend(check["warnings"])
    return result(not failures, "replay", failures, warnings, sorted(set(tampered)))
