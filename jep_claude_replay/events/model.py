"""JEP-style immutable accountability event model."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from jep_claude_replay.canonicalization.jcs import sha256_digest, payload_digest, redacted_preview

EventType = Literal["judgment", "delegation", "termination", "verification"]
VERBS = {"judgment": "J", "delegation": "D", "termination": "T", "verification": "V"}
REQUIRED_FIELDS = [
    "event_id", "event_type", "verb", "actor", "subject", "session_id", "previous_event_hash",
    "event_hash", "timestamp", "nonce", "intent", "authority_scope", "delegation_chain",
    "verification_state", "validation_result", "ext", "ext_crit",
]


@dataclass(frozen=True)
class JEPEvent:
    event_id: str
    event_type: EventType
    verb: str
    actor: str
    subject: str
    session_id: str
    parent_event_id: str | None
    previous_event_hash: str | None
    event_hash: str | None
    timestamp: str
    nonce: str
    intent: str
    tool_name: str | None = None
    tool_input_digest: str | None = None
    tool_output_digest: str | None = None
    authority_scope: dict[str, Any] = field(default_factory=dict)
    delegation_chain: list[str] = field(default_factory=list)
    verification_state: str = "unchecked"
    validation_result: dict[str, Any] = field(default_factory=lambda: {"valid": None, "failure_codes": [], "warnings": []})
    failure_code: str | None = None
    ext: dict[str, Any] = field(default_factory=dict)
    ext_crit: list[str] = field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    redacted_input_preview: str | None = None
    redacted_output_preview: str | None = None
    signature: dict[str, Any] = field(default_factory=lambda: {"alg": "mock-detached", "kid": None, "value": None})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def hash_payload(self) -> dict[str, Any]:
        data = self.to_dict()
        data["event_hash"] = None
        data["signature"] = {"alg": None, "kid": None, "value": None}
        return data


def compute_event_hash(event_or_dict: JEPEvent | dict[str, Any]) -> str:
    data = event_or_dict.hash_payload() if isinstance(event_or_dict, JEPEvent) else {k: v for k, v in dict(event_or_dict).items() if not k.startswith("_")}
    data["event_hash"] = None
    if isinstance(data.get("signature"), dict):
        data["signature"] = {"alg": None, "kid": None, "value": None}
    return "sha256:" + sha256_digest(data)


def make_event(
    event_type: EventType,
    *,
    actor: str,
    subject: str,
    session_id: str,
    intent: str,
    previous_event_hash: str | None = None,
    parent_event_id: str | None = None,
    tool_name: str | None = None,
    tool_input: Any = None,
    tool_output: Any = None,
    authority_scope: dict[str, Any] | None = None,
    delegation_chain: list[str] | None = None,
    verification_state: str = "unchecked",
    validation_result: dict[str, Any] | None = None,
    failure_code: str | None = None,
    ext: dict[str, Any] | None = None,
    ext_crit: list[str] | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
    timestamp: str | None = None,
    nonce: str | None = None,
    event_id: str | None = None,
    include_previews: bool = False,
) -> JEPEvent:
    event = JEPEvent(
        event_id=event_id or str(uuid4()),
        event_type=event_type,
        verb=VERBS[event_type],
        actor=actor,
        subject=subject,
        session_id=session_id,
        parent_event_id=parent_event_id,
        previous_event_hash=previous_event_hash,
        event_hash=None,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        nonce=nonce or str(uuid4()),
        intent=intent,
        tool_name=tool_name,
        tool_input_digest=payload_digest(tool_input),
        tool_output_digest=payload_digest(tool_output),
        authority_scope=authority_scope or {"profile": "neutral", "limits": []},
        delegation_chain=delegation_chain or [],
        verification_state=verification_state,
        validation_result=validation_result or {"valid": None, "failure_codes": [], "warnings": []},
        failure_code=failure_code,
        ext=ext or {},
        ext_crit=ext_crit or [],
        evidence_refs=evidence_refs or [],
        redacted_input_preview=redacted_preview(tool_input) if include_previews else None,
        redacted_output_preview=redacted_preview(tool_output) if include_previews else None,
    )
    h = compute_event_hash(event)
    return JEPEvent(**{**event.to_dict(), "event_hash": h})
