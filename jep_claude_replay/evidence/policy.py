"""Fine-grained evidence handling policies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jep_claude_replay.canonicalization.jcs import payload_digest, redacted_preview


@dataclass(frozen=True)
class EvidencePolicy:
    mode: str = "digest-preview"  # digest-only | digest-preview | allow-raw
    preview_limit: int = 160
    allow_raw_fields: tuple[str, ...] = ()

    def apply(self, value: Any, *, field_name: str = "payload") -> dict[str, Any]:
        digest = payload_digest(value)
        if self.mode == "digest-only":
            return {"digest": digest, "preview": None, "raw": None, "policy": self.mode}
        if self.mode == "allow-raw" and field_name in self.allow_raw_fields:
            return {"digest": digest, "preview": redacted_preview(value, self.preview_limit), "raw": value, "policy": self.mode}
        return {"digest": digest, "preview": redacted_preview(value, self.preview_limit), "raw": None, "policy": self.mode}
