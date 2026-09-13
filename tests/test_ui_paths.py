from pathlib import Path
import pytest
from jep_claude_replay.ui.server import Handler, confined_file


def test_static_paths_reject_plain_and_encoded_traversal():
    for path in ("/../../../sentinel", "/%2e%2e/%2e%2e/sentinel"):
        with pytest.raises(PermissionError):
            Handler.translate_path(None, path)
    assert Path(Handler.translate_path(None, "/ui?tab=replay")).name == "index.html"


def test_archive_paths_confined_including_symlinks(tmp_path):
    root = tmp_path / "archives"
    root.mkdir()
    outside = tmp_path / "secret.jsonl"
    outside.write_text("secret")
    (root / "alias.jsonl").symlink_to(outside)
    for path in ("../secret.jsonl", str(outside), "alias.jsonl"):
        with pytest.raises(PermissionError):
            confined_file(root, path)
    assert confined_file(root, "session.jsonl") == root / "session.jsonl"
