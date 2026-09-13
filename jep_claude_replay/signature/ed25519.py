"""Ed25519 detached signatures backed by cryptography/OpenSSL.

The archive's existing payload canonicalization is retained for compatibility.
Key trust is resolved by Keyring, independently of embedded public key material.
"""
from __future__ import annotations
import base64
import secrets
from dataclasses import dataclass
from typing import Any
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from jep_claude_replay.canonicalization.jcs import canonicalize


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass(frozen=True)
class Ed25519KeyPair:
    kid: str
    seed: bytes

    @classmethod
    def generate(cls, kid: str = "ed25519-1") -> "Ed25519KeyPair":
        return cls(kid, secrets.token_bytes(32))

    @property
    def public_key(self) -> bytes:
        return Ed25519PrivateKey.from_private_bytes(self.seed).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    def sign_bytes(self, message: bytes) -> bytes:
        return Ed25519PrivateKey.from_private_bytes(self.seed).sign(message)

    def sign_payload(self, payload: Any) -> dict[str, str]:
        sig = self.sign_bytes(canonicalize(payload).encode("utf-8"))
        return {"alg": "Ed25519", "kid": self.kid, "public_key": _b64u(self.public_key), "value": _b64u(sig)}


def verify_bytes(public_key: bytes, message: bytes, signature: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def verify_payload(payload: Any, signature: dict[str, str]) -> bool:
    """Check mathematical integrity only; callers must independently trust the key."""
    try:
        if signature.get("alg") != "Ed25519":
            return False
        return verify_bytes(_b64u_decode(signature.get("public_key", "")), canonicalize(payload).encode("utf-8"), _b64u_decode(signature.get("value", "")))
    except (ValueError, TypeError, AttributeError):
        return False
