"""
backend/evidence/sign.py

Ed25519 signing and verification for evidence packages.

Two audiences:
  - HMAC (packager.py): proves a package is ours to someone holding the service secret.
  - Ed25519 (this module): proves authenticity to anyone holding only the public key —
    the case that matters once a clip leaves this system.

Module-level key caching: keys are loaded from disk on first use and reused for the
lifetime of the process.  monkeypatch targets _private_key / _public_key to reset
between tests.
"""
import logging
import os
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)

from backend.config import ED25519_PRIVATE_KEY_PATH, ED25519_PUBLIC_KEY_PATH

logger = logging.getLogger(__name__)

# ── Module-level key cache (monkeypatched by tests) ──────────────────────────
_private_key: Optional[Ed25519PrivateKey] = None
_public_key: Optional[Ed25519PublicKey] = None


# ── Internal helpers ─────────────────────────────────────────────────────────

def _ensure_keys() -> None:
    """Load or generate the Ed25519 keypair.

    If the key files exist they are loaded; otherwise a fresh keypair is
    generated and written.  The private key file is created with restricted
    permissions (0o600) on POSIX systems.

    On a failed write, module globals are left as None so the next call retries
    rather than permanently caching a broken state.
    """
    global _private_key, _public_key

    if _private_key is not None and _public_key is not None:
        return

    priv_path: Path = ED25519_PRIVATE_KEY_PATH
    pub_path: Path = ED25519_PUBLIC_KEY_PATH

    if priv_path.exists() and pub_path.exists():
        # Load existing keypair.
        raw = priv_path.read_bytes()
        _private_key = load_pem_private_key(raw, password=None)
        _public_key = _private_key.public_key()
        logger.debug("Ed25519 keys loaded from %s", priv_path)
        return

    # Generate a fresh keypair.
    logger.info("Generating new Ed25519 keypair at %s", priv_path.parent)
    priv_path.parent.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    priv_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )
    pub_pem = public_key.public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )

    # Write files; if either write fails, leave module globals as None.
    priv_path.write_bytes(priv_pem)
    try:
        if os.name != "nt":
            os.chmod(priv_path, 0o600)
        pub_path.write_bytes(pub_pem)
    except Exception:
        # Don't half-cache: a failed key write must allow a retry next call.
        _private_key = None
        _public_key = None
        raise

    # Only set globals after both files are written successfully.
    _private_key = private_key
    _public_key = public_key
    logger.info("Ed25519 keypair generated and written")


# ── Public API ────────────────────────────────────────────────────────────────

def sign_digest(hex_digest: str) -> str:
    """Sign a SHA-256 hex digest and return the signature as a hex string.

    Args:
        hex_digest: Lower-case hex SHA-256 digest of the evidence clip.

    Returns:
        Lower-case hex Ed25519 signature over the digest bytes.

    Raises:
        OSError: If the key files cannot be written on first use.
    """
    _ensure_keys()
    assert _private_key is not None  # satisfied by _ensure_keys()
    sig_bytes = _private_key.sign(bytes.fromhex(hex_digest))
    return sig_bytes.hex()


def verify_digest(hex_digest: str, hex_signature: str) -> bool:
    """Verify an Ed25519 signature over a SHA-256 hex digest.

    Args:
        hex_digest:    Lower-case hex SHA-256 digest of the evidence clip.
        hex_signature: Lower-case hex Ed25519 signature to verify.

    Returns:
        True if the signature is valid, False otherwise.
    """
    _ensure_keys()
    assert _public_key is not None
    try:
        _public_key.verify(bytes.fromhex(hex_signature), bytes.fromhex(hex_digest))
        return True
    except Exception:
        return False


def public_key_pem() -> str:
    """Return the PEM-encoded public key as a string.

    Useful for distributing the public key to third parties who need to verify
    evidence packages produced by this system.
    """
    _ensure_keys()
    assert _public_key is not None
    return _public_key.public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    ).decode()
