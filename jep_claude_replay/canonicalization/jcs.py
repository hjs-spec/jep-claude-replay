"""RFC 8785-compatible JSON Canonicalization Scheme helpers.

This module implements the JSON constraints needed by JCS/RFC 8785:
object member sorting by Unicode code point, no insignificant whitespace,
shortest JSON string escapes, deterministic primitive rendering, and rejection
of non-finite numbers. It intentionally rejects floats whose ECMAScript number
serialization cannot be represented safely by Python's stdlib renderer.
"""
from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Any

_SAFE_INTEGER_MIN = -(2**53) + 1
_SAFE_INTEGER_MAX = (2**53) - 1


def _escape_string(value: str) -> str:
    # Python's encoder with ensure_ascii=False uses the same minimal escaping
    # JCS expects for strings: quotes, reverse solidus, and control chars only.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _canonical_number(value: int | float | Decimal) -> str:
    if isinstance(value, bool):
        raise TypeError("bool is not a JSON number")
    if isinstance(value, int):
        if not (_SAFE_INTEGER_MIN <= value <= _SAFE_INTEGER_MAX):
            raise ValueError("JCS requires integers to be in the I-JSON safe range")
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("JCS rejects non-finite numbers")
        value = float(value)
    if not math.isfinite(value):
        raise ValueError("JCS rejects NaN and Infinity")
    # RFC 8785 delegates number serialization to ECMAScript/JSON.stringify.
    # Use fixed notation for the ECMAScript non-exponential window and exponent
    # notation otherwise, then normalize exponent signs/zeros.
    if value == 0:
        return "0"
    dec = Decimal(str(value))
    abs_value = abs(float(value))
    if 1e-6 <= abs_value < 1e21:
        text = format(dec, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    text = format(dec.normalize(), "e")
    mantissa, exponent = text.split("e")
    mantissa = mantissa.rstrip("0").rstrip(".")
    exp_int = int(exponent)
    sign = "+" if exp_int >= 0 else ""
    return f"{mantissa}e{sign}{exp_int}"


def _canonicalize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _escape_string(value)
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return _canonical_number(value)
    if isinstance(value, list) or isinstance(value, tuple):
        return "[" + ",".join(_canonicalize(item) for item in value) + "]"
    if isinstance(value, dict):
        items = []
        for key in sorted(value.keys()):
            if not isinstance(key, str):
                raise TypeError("JCS object member names must be strings")
            items.append(_escape_string(key) + ":" + _canonicalize(value[key]))
        return "{" + ",".join(items) + "}"
    raise TypeError(f"unsupported JSON value for canonicalization: {type(value)!r}")


def canonicalize(value: Any) -> str:
    """Return RFC 8785/JCS canonical JSON text."""
    return _canonicalize(value)


def sha256_digest(value: Any) -> str:
    return hashlib.sha256(canonicalize(value).encode("utf-8")).hexdigest()


def payload_digest(value: Any) -> str | None:
    if value is None:
        return None
    return "sha256:" + sha256_digest(value)


def redacted_preview(value: Any, limit: int = 160) -> str | None:
    if value is None:
        return None
    text = canonicalize(value) if not isinstance(value, str) else value
    text = text.replace("\n", "\\n")
    return text[:limit] + ("…" if len(text) > limit else "")
