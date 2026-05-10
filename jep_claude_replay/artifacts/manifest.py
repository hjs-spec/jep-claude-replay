"""Replay-safe artifact manifest generation."""
from __future__ import annotations

import mimetypes
from dataclasses import dataclass, asdict
from pathlib import Path

from jep_claude_replay.canonicalization.jcs import sha256_digest


@dataclass(frozen=True)
class ArtifactRef:
    uri: str
    digest: str
    size: int
    media_type: str
    role: str = "evidence"
    redaction: str = "digest-only"


def artifact_ref(path: str | Path, *, role: str = "evidence", redaction: str = "digest-only") -> ArtifactRef:
    p = Path(path)
    raw = p.read_bytes()
    digest = "sha256:" + __import__("hashlib").sha256(raw).hexdigest()
    media_type = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    return ArtifactRef(uri=p.as_uri() if p.is_absolute() else f"file://{p.as_posix()}", digest=digest, size=len(raw), media_type=media_type, role=role, redaction=redaction)


def build_manifest(paths: list[str | Path], *, session_id: str) -> dict:
    refs = [asdict(artifact_ref(path)) for path in paths]
    manifest = {"manifest_version": "jcr-artifacts-v1", "session_id": session_id, "artifacts": refs}
    return {**manifest, "manifest_digest": "sha256:" + sha256_digest(manifest)}


def write_manifest(paths: list[str | Path], output_path: str | Path, *, session_id: str) -> dict:
    from jep_claude_replay.canonicalization.jcs import canonicalize
    manifest = build_manifest(paths, session_id=session_id)
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(canonicalize(manifest) + "\n", encoding="utf-8")
    return manifest
