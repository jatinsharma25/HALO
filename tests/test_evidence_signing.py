"""
tests/test_evidence_signing.py
The evidence chain carries two signatures for two audiences: an HMAC that
proves a package is ours to anyone holding the service secret, and an Ed25519
signature that proves it to anyone holding only the public key — which is the
case that matters once a clip leaves this system.
Run with: pytest tests/ -v
"""
import hashlib
import sys

import pytest

from backend.evidence import sign


@pytest.fixture(autouse=True)
def keys_in_tmp(tmp_path, monkeypatch):
    """Each test signs with a throwaway keypair, never the deployment's."""
    monkeypatch.setattr(sign, "ED25519_PRIVATE_KEY_PATH", tmp_path / "keys" / "ed25519.key")
    monkeypatch.setattr(sign, "ED25519_PUBLIC_KEY_PATH", tmp_path / "keys" / "ed25519.pub")
    monkeypatch.setattr(sign, "_private_key", None)
    monkeypatch.setattr(sign, "_public_key", None)
    yield


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_signature_verifies():
    d = _digest(b"clip bytes")
    assert sign.verify_digest(d, sign.sign_digest(d))


def test_a_different_digest_does_not_verify():
    # This is the whole point: a tampered clip hashes differently, so the
    # signature over the original digest must not accept it.
    signature = sign.sign_digest(_digest(b"original clip"))
    assert not sign.verify_digest(_digest(b"tampered clip"), signature)


def test_keys_are_created_on_first_use():
    sign.sign_digest(_digest(b"x"))
    assert sign.ED25519_PRIVATE_KEY_PATH.exists()
    assert sign.ED25519_PUBLIC_KEY_PATH.exists()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "NTFS has no POSIX permission-bit concept — chmod(0o600) on Windows "
        "cannot make a file owner-only readable the way it does on Unix, so "
        "st_mode never reflects 0o600 there regardless of what the code did. "
        "The real ACL-based equivalent isn't a single stat() check; this "
        "assertion is only meaningful on POSIX."
    ),
)
def test_private_key_is_not_world_readable():
    sign.sign_digest(_digest(b"x"))
    mode = sign.ED25519_PRIVATE_KEY_PATH.stat().st_mode & 0o777
    assert mode == 0o600, f"private key mode is {oct(mode)}"


def test_key_is_reused_across_calls():
    # A regenerated key would silently invalidate every signature already
    # issued against the persisted one.
    first = sign.sign_digest(_digest(b"same"))
    sign._private_key = None  # force a reload from disk
    sign._public_key = None
    assert sign.verify_digest(_digest(b"same"), first)


def test_public_key_is_exportable_pem():
    sign.sign_digest(_digest(b"x"))
    pem = sign.public_key_pem()
    assert pem.startswith("-----BEGIN PUBLIC KEY-----")


def test_a_failed_first_run_does_not_poison_the_module(tmp_path, monkeypatch):
    # Assigning the module global before the key files are written turned a
    # transient error into a permanent one: later calls returned early with
    # the public key still unset.
    monkeypatch.setattr(sign, "ED25519_PRIVATE_KEY_PATH", tmp_path / "nope" / "k.key")
    monkeypatch.setattr(sign, "ED25519_PUBLIC_KEY_PATH", tmp_path / "nope" / "k.pub")
    monkeypatch.setattr(sign, "_private_key", None)
    monkeypatch.setattr(sign, "_public_key", None)

    original = sign.ED25519_PRIVATE_KEY_PATH.parent.mkdir
    monkeypatch.setattr(
        type(sign.ED25519_PRIVATE_KEY_PATH), "write_bytes",
        lambda self, data: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(OSError):
        sign.sign_digest(_digest(b"x"))
    assert sign._private_key is None, "a failed run must leave the module unset"
    del original
