from __future__ import annotations

from dataclasses import replace

from jep_claude_replay.events.model import JEPEvent
from jep_claude_replay.signature.keyring import Keyring


def sign_event(event: JEPEvent, keyring: Keyring, *, alg: str | None = None) -> JEPEvent:
    return replace(event, signature=keyring.sign(_signature_payload(event.to_dict()), alg=alg))


def _signature_payload(event: dict) -> dict:
    payload = {k: v for k, v in event.items() if not k.startswith("_")}
    payload["signature"] = {"alg": None, "kid": None, "value": None}
    return payload


def verify_event_signature(event: dict, keyring: Keyring) -> bool:
    return keyring.verify(_signature_payload(event), event.get("signature") or {})


def sign_events(events: list[dict], keyring: Keyring, *, alg: str | None = None) -> list[dict]:
    signed: list[dict] = []
    for event in events:
        payload = _signature_payload(event)
        event = dict(event)
        event.pop("_archive_line", None)
        event["signature"] = keyring.sign(payload, alg=alg)
        signed.append(event)
    return signed


def verify_archive_signatures(events: list[dict], keyring: Keyring) -> dict:
    failures = [] if events else ["empty_archive"]
    tampered = []
    for event in events:
        if not verify_event_signature(event, keyring):
            failures.append("invalid_signature")
            tampered.append(event.get("event_id", "<unknown>"))
    return {"valid": not failures, "validation_level": "signature", "failure_codes": sorted(set(failures)), "warnings": [], "tampered_events": sorted(set(tampered))}
