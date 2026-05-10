from __future__ import annotations

from dataclasses import replace

from jep_claude_replay.events.model import JEPEvent
from jep_claude_replay.signature.keyring import Keyring


def sign_event(event: JEPEvent, keyring: Keyring, *, alg: str | None = None) -> JEPEvent:
    return replace(event, signature=keyring.sign(event.hash_payload(), alg=alg))


def verify_event_signature(event: dict, keyring: Keyring) -> bool:
    payload = dict(event)
    payload.pop("_archive_line", None)
    sig = payload.get("signature") or {}
    payload["signature"] = {"alg": None, "kid": None, "value": None}
    # The event model hashes mock signatures with value None. For HS256, sign the
    # same detached payload with signature value omitted.
    return keyring.verify(payload, sig)


def sign_events(events: list[dict], keyring: Keyring, *, alg: str | None = None) -> list[dict]:
    signed: list[dict] = []
    for event in events:
        payload = {k: v for k, v in event.items() if not k.startswith("_")}
        payload["signature"] = {"alg": None, "kid": None, "value": None}
        event = dict(event)
        event.pop("_archive_line", None)
        event["signature"] = keyring.sign(payload, alg=alg)
        signed.append(event)
    return signed


def verify_archive_signatures(events: list[dict], keyring: Keyring) -> dict:
    failures = []
    tampered = []
    for event in events:
        if not verify_event_signature(event, keyring):
            failures.append("invalid_signature")
            tampered.append(event.get("event_id", "<unknown>"))
    return {"valid": not failures, "validation_level": "signature", "failure_codes": sorted(set(failures)), "warnings": [], "tampered_events": sorted(set(tampered))}
