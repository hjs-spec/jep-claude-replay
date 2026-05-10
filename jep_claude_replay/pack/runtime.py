"""Artifact pack export/import.

A `.jcrpack` is a zip bundle containing archive.jsonl, manifest.json,
evidence files, optional signatures.json, and verification-report.json.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable

from jep_claude_replay.archive.runtime import load_archive
from jep_claude_replay.artifacts.manifest import build_manifest
from jep_claude_replay.canonicalization.jcs import canonicalize
from jep_claude_replay.signature.keyring import Keyring
from jep_claude_replay.verification.profile import verify_profiles

PACK_VERSION = "jcr-pack-v1"


def export_pack(archive_path: str | Path, output_path: str | Path, *, evidence_paths: Iterable[str | Path] = (), keyring: Keyring | None = None) -> dict:
    archive = Path(archive_path)
    evidence = [Path(p) for p in evidence_paths]
    events = load_archive(archive)
    session_id = events[0].get("session_id", "unknown") if events else "unknown"
    manifest = build_manifest([archive, *evidence], session_id=session_id)
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
        for path in evidence:
            if path.exists() and path.is_file():
                shutil.copy2(path, evidence_dir / path.name)
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(tmp.rglob("*")):
                if file.is_file():
                    zf.write(file, file.relative_to(tmp).as_posix())
    return {"pack_path": str(out), "pack_index": pack_index, "verification": verification, "manifest": manifest}


def import_pack(pack_path: str | Path, output_dir: str | Path) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pack_path) as zf:
        zf.extractall(out)
    index = json.loads((out / "pack.json").read_text(encoding="utf-8"))
    archive = out / index["archive"]
    events = load_archive(archive)
    return {"output_dir": str(out), "pack_index": index, "events": events, "verification_report": json.loads((out / index["verification_report"]).read_text(encoding="utf-8"))}
