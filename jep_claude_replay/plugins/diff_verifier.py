"""Diff-aware verification plugin."""
from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass(frozen=True)
class DiffVerificationResult:
    valid: bool
    failure_codes: list[str]
    warnings: list[str]
    diff: str


def unified_diff(before: str, after: str, *, fromfile: str = "before", tofile: str = "after") -> str:
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=fromfile, tofile=tofile))


def verify_diff(before: str, after: str, *, required_additions: list[str] | None = None, forbidden_additions: list[str] | None = None) -> dict:
    diff = unified_diff(before, after)
    failures: list[str] = []
    warnings: list[str] = []
    required_additions = required_additions or []
    forbidden_additions = forbidden_additions or []
    for addition in required_additions:
        if f"+{addition}" not in diff:
            failures.append("diff_required_addition_missing")
            warnings.append(f"required addition missing: {addition}")
    for addition in forbidden_additions:
        if f"+{addition}" in diff:
            failures.append("diff_forbidden_addition_present")
            warnings.append(f"forbidden addition present: {addition}")
    return {"valid": not failures, "validation_level": "diff", "failure_codes": failures, "warnings": warnings, "diff": diff}
