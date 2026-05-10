"""Small pure-Python Ed25519 implementation for detached event signatures.

This is intentionally dependency-free for the prototype. It follows RFC 8032
Ed25519 equations and is suitable for test/prototype public-key verification;
production deployments should prefer audited crypto libraries or KMS.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Any

from jep_claude_replay.canonicalization.jcs import canonicalize

Q = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, Q - 2, Q) % Q
I = pow(2, (Q - 1) // 4, Q)
B = (15112221349535400772501151409588531511454012693041857206046113283949847762202,
     46316835694926478169428394003475163141307993866256225615783033603165251855960)


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _inv(x: int) -> int:
    return pow(x, Q - 2, Q)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(D * y * y + 1) % Q
    x = pow(xx, (Q + 3) // 8, Q)
    if (x * x - xx) % Q != 0:
        x = (x * I) % Q
    if x % 2 != 0:
        x = Q - x
    return x


def _isoncurve(p: tuple[int, int]) -> bool:
    x, y = p
    return (-x * x + y * y - 1 - D * x * x * y * y) % Q == 0


def _edwards(p: tuple[int, int], q: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = p
    x2, y2 = q
    den = D * x1 * x2 * y1 * y2
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + den) % Q
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - den) % Q
    return x3, y3


def _scalarmult(p: tuple[int, int], e: int) -> tuple[int, int]:
    if e == 0:
        return (0, 1)
    q = _scalarmult(p, e // 2)
    q = _edwards(q, q)
    if e & 1:
        q = _edwards(q, p)
    return q


def _encode_point(p: tuple[int, int]) -> bytes:
    x, y = p
    bits = y.to_bytes(32, "little")
    if x & 1:
        bits = bits[:-1] + bytes([bits[-1] | 0x80])
    return bits


def _decode_point(raw: bytes) -> tuple[int, int]:
    if len(raw) != 32:
        raise ValueError("Ed25519 points are 32 bytes")
    y = int.from_bytes(raw, "little") & ((1 << 255) - 1)
    x = _xrecover(y)
    if bool(x & 1) != bool(raw[31] & 0x80):
        x = Q - x
    p = (x, y)
    if not _isoncurve(p):
        raise ValueError("point is not on Ed25519 curve")
    return p


def _hint(data: bytes) -> int:
    return int.from_bytes(_sha512(data), "little")


def _clamped_scalar(seed: bytes) -> tuple[int, bytes]:
    h = _sha512(seed)
    a = bytearray(h[:32])
    a[0] &= 248
    a[31] &= 63
    a[31] |= 64
    return int.from_bytes(a, "little"), h[32:]


@dataclass(frozen=True)
class Ed25519KeyPair:
    kid: str
    seed: bytes

    @classmethod
    def generate(cls, kid: str = "ed25519-1") -> "Ed25519KeyPair":
        return cls(kid=kid, seed=secrets.token_bytes(32))

    @property
    def public_key(self) -> bytes:
        a, _ = _clamped_scalar(self.seed)
        return _encode_point(_scalarmult(B, a))

    def sign_bytes(self, message: bytes) -> bytes:
        a, prefix = _clamped_scalar(self.seed)
        public = self.public_key
        r = _hint(prefix + message) % L
        r_point = _encode_point(_scalarmult(B, r))
        h = _hint(r_point + public + message) % L
        s = (r + h * a) % L
        return r_point + s.to_bytes(32, "little")

    def sign_payload(self, payload: Any) -> dict[str, str]:
        sig = self.sign_bytes(canonicalize(payload).encode("utf-8"))
        return {"alg": "Ed25519", "kid": self.kid, "public_key": _b64u(self.public_key), "value": _b64u(sig)}


def verify_bytes(public_key: bytes, message: bytes, signature: bytes) -> bool:
    if len(public_key) != 32 or len(signature) != 64:
        return False
    try:
        a = _decode_point(public_key)
        r = _decode_point(signature[:32])
    except ValueError:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= L:
        return False
    h = _hint(signature[:32] + public_key + message) % L
    return _encode_point(_scalarmult(B, s)) == _encode_point(_edwards(r, _scalarmult(a, h)))


def verify_payload(payload: Any, signature: dict[str, str]) -> bool:
    if signature.get("alg") != "Ed25519":
        return False
    return verify_bytes(_b64u_decode(signature.get("public_key", "")), canonicalize(payload).encode("utf-8"), _b64u_decode(signature.get("value", "")))
