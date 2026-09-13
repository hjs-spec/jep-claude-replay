"""Artifact pack export/import.

A `.jcrpack` is a zip bundle containing archive.jsonl, manifest.json,
evidence files, optional signatures.json, and verification-report.json.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from hashlib import sha256
from dataclasses import asdict
import stat
from tempfile import TemporaryDirectory
from typing import Iterable

from jep_claude_replay.archive.runtime import load_archive
from jep_claude_replay.artifacts.manifest import artifact_ref
from jep_claude_replay.canonicalization.jcs import canonicalize, sha256_digest
from jep_claude_replay.signature.keyring import Keyring
from jep_claude_replay.verification.profile import verify_profiles

PACK_VERSION = "jcr-pack-v1"


def export_pack(archive_path: str | Path, output_path: str | Path, *, evidence_paths: Iterable[str | Path] = (), keyring: Keyring | None = None) -> dict:
    archive = Path(archive_path)
    evidence = [Path(p) for p in evidence_paths]
    events = load_archive(archive)
    session_id = events[0].get("session_id", "unknown") if events else "unknown"
    refs = []
    for index, path in enumerate([archive, *evidence]):
        item = asdict(artifact_ref(path))
        item["source_uri"] = item["uri"]
        item["uri"] = "file://archive.jsonl" if index == 0 else f"file://evidence/{index:04d}-{path.name}"
        refs.append(item)
    manifest = {"manifest_version": "jcr-artifacts-v1", "session_id": session_id, "artifacts": refs}
    manifest["manifest_digest"] = "sha256:" + sha256_digest(manifest)
    verification = verify_profiles(events, keyring=keyring, base_path=archive.parent.parent.parent if len(archive.parts) > 2 else ".")
    signatures = [{"event_id": e.get("event_id"), "event_hash": e.get("event_hash"), "signature": e.get("signature")} for e in events if (e.get("signature") or {}).get("value")]
    pack_index = {"pack_version": PACK_VERSION, "archive": "archive.jsonl", "manifest": "manifest.json", "verification_report": "verification-report.json", "evidence_dir": "evidence", "signature_bundle": "signatures.json"}

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        shutil.copy2(archive, tmp / "archive.jsonl")
        (tmp / "manifest.json").write_text(canonicalize(manifest) + "\n", encoding="utf-8")
        (tmp / "verification-report.json").write_text(canonicalize(verification) + "\n", encoding="utf-8")
        (tmp / "signatures.json").write_text(canonicalize({"signatures": signatures}) + "\n", encoding="utf-8")
        (tmp / "pack.json").write_text(canonicalize(pack_index) + "\n", encoding="utf-8")
        evidence_dir = tmp / "evidence"
        evidence_dir.mkdir()
        for index, path in enumerate(evidence, 1):
            shutil.copy2(path, evidence_dir / f"{index:04d}-{path.name}")
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(tmp.rglob("*")):
                if file.is_file():
                    zf.write(file, file.relative_to(tmp).as_posix())
    return {"pack_path": str(out), "pack_index": pack_index, "verification": verification, "manifest": manifest}


def _member_path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or "\\" in name or ":" in name:
        raise ValueError("invalid pack member path")
    member = PurePosixPath(name)
    if member.is_absolute() or ".." in member.parts:
        raise ValueError("pack path escapes output directory")
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("pack path escapes output directory")
    return candidate


def import_pack(pack_path: str | Path, output_dir: str | Path, *, keyring: Keyring | None = None) -> dict:
    """Extract a bounded pack, then verify its actual contents with trusted keys.

    The embedded verification report is untrusted provenance and is never used
    as the current verification result. Signed event bytes are not rewritten.
    """
    out = Path(output_dir).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("pack output directory must be empty")
    with zipfile.ZipFile(pack_path) as zf:
        entries = zf.infolist()
        if len(entries) > 10000 or sum(item.file_size for item in entries) > 512 * 1024 * 1024:
            raise ValueError("pack exceeds extraction limits")
        seen = set()
        for item in entries:
            target = _member_path(out, item.filename)
            if target in seen or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("duplicate or symlink pack member")
            seen.add(target)
        out.mkdir(parents=True, exist_ok=True)
        zf.extractall(out)
    index = json.loads((out / "pack.json").read_text(encoding="utf-8"))
    if index.get("pack_version") != PACK_VERSION:
        raise ValueError("unsupported pack version")
    archive = _member_path(out, index["archive"])
    manifest = json.loads(_member_path(out, index["manifest"]).read_text(encoding="utf-8"))
    failures = []
    expected_manifest_digest = manifest.get("manifest_digest")
    unsigned_manifest = {k: v for k, v in manifest.items() if k != "manifest_digest"}
    if expected_manifest_digest != "sha256:" + sha256_digest(unsigned_manifest):
        failures.append("manifest_digest_mismatch")
    evidence_map = {}
    for ref in manifest.get("artifacts", []):
        uri = ref.get("uri", "")
        if not uri.startswith("file://"):
            failures.append("unsupported_manifest_uri")
            continue
        try:
            candidate = _member_path(out, uri.removeprefix("file://"))
            raw = candidate.read_bytes()
        except (ValueError, OSError):
            failures.append("missing_or_unsafe_manifest_artifact")
            continue
        if ref.get("digest") != "sha256:" + sha256(raw).hexdigest() or ref.get("size") != len(raw):
            failures.append("manifest_artifact_mismatch")
        if ref.get("source_uri"):
            evidence_map[ref["source_uri"]] = uri
    events = load_archive(archive)
    verification = verify_profiles(events, keyring=keyring, base_path=out, evidence_map=evidence_map)
    if failures:
        verification["valid"] = False
        verification["failure_codes"] = sorted(set(verification["failure_codes"] + failures))
    embedded = json.loads(_member_path(out, index["verification_report"]).read_text(encoding="utf-8"))
    return {"output_dir": str(out), "pack_index": index, "events": events,
            "verification_report": verification, "embedded_report_untrusted": embedded}
