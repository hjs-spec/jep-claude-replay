"""Detached signature helpers with HMAC and Ed25519 key rotation.

HS256 is retained for local/dev mode. Ed25519 provides public-key detached
verification for replay archives without requiring shared verification secrets.
"""
from __future__ import annotations

import base64
import hmac
import json
import secrets
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

from jep_claude_replay.canonicalization.jcs import canonicalize
from jep_claude_replay.signature.ed25519 import Ed25519KeyPair, verify_payload as verify_ed25519_payload


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass
class Keyring:
    keys: dict[str, bytes] = field(default_factory=dict)
    active_kid: str | None = None
    ed25519_seeds: dict[str, bytes] = field(default_factory=dict)
    active_ed25519_kid: str | None = None

    @classmethod
    def generate(cls, kid: str = "local-1", *, alg: str = "HS256") -> "Keyring":
        if alg == "Ed25519":
            pair = Ed25519KeyPair.generate(kid)
            return cls(ed25519_seeds={kid: pair.seed}, active_ed25519_kid=kid)
        return cls(keys={kid: secrets.token_bytes(32)}, active_kid=kid)

    @classmethod
    def load(cls, path: str | Path) -> "Keyring":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        keys = {kid: _b64u_decode(raw) for kid, raw in data.get("keys", {}).items()}
        ed = {kid: _b64u_decode(raw) for kid, raw in data.get("ed25519_seeds", {}).items()}
        return cls(keys, data.get("active_kid"), ed, data.get("active_ed25519_kid"))

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "active_kid": self.active_kid,
            "active_ed25519_kid": self.active_ed25519_kid,
            "keys": {kid: _b64u(key) for kid, key in self.keys.items()},
            "ed25519_seeds": {kid: _b64u(seed) for kid, seed in self.ed25519_seeds.items()},
        }
        p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def rotate(self, kid: str, *, alg: str = "HS256") -> None:
        if alg == "Ed25519":
            self.ed25519_seeds[kid] = Ed25519KeyPair.generate(kid).seed
            self.active_ed25519_kid = kid
            return
        self.keys[kid] = secrets.token_bytes(32)
        self.active_kid = kid

    def sign(self, payload: Any, kid: str | None = None, *, alg: str | None = None) -> dict[str, str]:
        chosen_alg = alg or ("Ed25519" if self.active_ed25519_kid and not self.active_kid else "HS256")
        if chosen_alg == "Ed25519":
            active = kid or self.active_ed25519_kid
            if not active or active not in self.ed25519_seeds:
                raise KeyError("no active Ed25519 signing key")
            return Ed25519KeyPair(active, self.ed25519_seeds[active]).sign_payload(payload)
        active = kid or self.active_kid
        if not active or active not in self.keys:
            raise KeyError("no active HS256 signing key")
        mac = hmac.new(self.keys[active], canonicalize(payload).encode("utf-8"), sha256).digest()
        return {"alg": "HS256", "kid": active, "value": _b64u(mac)}

    def verify(self, payload: Any, signature: dict[str, str]) -> bool:
        if signature.get("alg") == "Ed25519":
            return verify_ed25519_payload(payload, signature)
        kid = signature.get("kid")
        if signature.get("alg") != "HS256" or kid not in self.keys:
            return False
        expected = self.sign(payload, kid, alg="HS256")["value"]
        return hmac.compare_digest(expected, signature.get("value", ""))
