import pytest
from jep_claude_replay.signature.ed25519 import verify_bytes
from jep_claude_replay.signature.keyring import Keyring


def test_identity_key_forgery_rejected():
    assert not verify_bytes(bytes([1])+bytes(31), b"forged message", bytes([1])+bytes(63))


def test_keyring_save_is_private_and_rotation_preserves_old_identifiers(tmp_path):
    keys = Keyring.generate("first", alg="Ed25519")
    signature = keys.sign({"claim":"old"})
    with pytest.raises(ValueError): keys.rotate("first", alg="Ed25519")
    keys.rotate("second", alg="Ed25519")
    path = tmp_path / "keys.json"
    keys.save(path)
    assert path.stat().st_mode & 0o077 == 0
    assert Keyring.load(path).verify({"claim":"old"}, signature)
    with pytest.raises(ValueError): keys.sign({}, alg="unknown")
