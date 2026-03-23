"""
Model Integrity Utilities — HMAC-SHA256 signing and verification for ML artifacts.

Usage
-----
Training code (after saving a joblib artifact):

    from ml.utils.integrity import sign_model
    joblib.dump(scaler, path)
    sign_model(path)

Loading code (before calling joblib.load):

    from ml.utils.integrity import verify_model_integrity
    verify_model_integrity(path)
    scaler = joblib.load(path)

The HMAC key is read from the ``ML_MODEL_SIGNING_KEY`` environment variable.
Set it to a 32+ byte random hex string in production.  The key must be present
at both signing time and verification time — omitting it raises EnvironmentError
so that unsigned loading in production fails loudly rather than silently.

Signature storage
-----------------
Each model file ``<name>`` gets a companion ``<name>.sig`` file containing the
hex-encoded HMAC-SHA256 digest.  The .sig file sits alongside the model file
and must be deployed together with it.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

_ENV_KEY = "ML_MODEL_SIGNING_KEY"


def _get_signing_key() -> bytes:
    """Return the HMAC signing key, preferring centralised settings.

    Resolution order:

    1. ``config.settings.settings.ml_model_signing_key`` — the canonical source
       when running inside the backend (production validators enforced).
    2. ``os.environ["ML_MODEL_SIGNING_KEY"]`` — fallback for standalone ML
       training environments where the full backend settings module is not
       importable.

    Raises:
        EnvironmentError: if the key cannot be resolved from either source.
    """
    raw: str | None = None

    # 1. Try centralised settings (backend context)
    try:
        from config.settings import settings as _backend_settings

        raw = _backend_settings.ml_model_signing_key
    except (ImportError, Exception):
        # Backend not available (standalone ML env) — fall through to env var
        pass

    # 2. Fall back to direct env var lookup
    if not raw:
        raw = os.environ.get(_ENV_KEY, "")

    if not raw:
        raise EnvironmentError(
            f"{_ENV_KEY} is not set. "
            "Set it to a 32+ byte random hex string to enable model integrity checks."
        )
    try:
        return bytes.fromhex(raw)
    except ValueError:
        # Accept raw UTF-8 bytes for non-hex keys
        return raw.encode()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_hmac(file_path: str, key: bytes) -> str:
    """Return the HMAC-SHA256 hex digest of *file_path* using *key*."""
    mac = hmac.new(key, digestmod=hashlib.sha256)
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            mac.update(chunk)
    return mac.hexdigest()


def _sig_path(model_path: str) -> str:
    """Return the path to the companion .sig file for *model_path*."""
    return model_path + ".sig"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def sign_model(model_path: str) -> None:
    """Compute an HMAC-SHA256 over *model_path* and write it to ``<model_path>.sig``.

    Must be called immediately after saving any joblib (or other pickle-based)
    artifact so that the integrity can be verified before the next load.

    Args:
        model_path: Absolute or relative path to the model/artifact file.

    Raises:
        EnvironmentError: if ``ML_MODEL_SIGNING_KEY`` is unset.
        FileNotFoundError: if *model_path* does not exist.
    """
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")

    key = _get_signing_key()
    digest = _compute_hmac(model_path, key)
    sig_file = _sig_path(model_path)
    with open(sig_file, "w") as fh:
        fh.write(digest)
    logger.info("model_signed: %s -> %s", os.path.basename(model_path), sig_file)


def verify_model_integrity(model_path: str) -> None:
    """Verify the HMAC-SHA256 of *model_path* against its companion .sig file.

    Must be called before every ``joblib.load()`` (or similar deserialisation)
    to guard against tampered model files.

    Args:
        model_path: Path to the model/artifact file to verify.

    Raises:
        EnvironmentError: if ``ML_MODEL_SIGNING_KEY`` is unset.
        FileNotFoundError: if the .sig file is missing.
        ValueError: if the HMAC digest does not match (tamper detected).
    """
    key = _get_signing_key()

    sig_file = _sig_path(model_path)
    if not os.path.exists(sig_file):
        raise FileNotFoundError(
            f"Integrity signature file not found: {sig_file}. "
            "Sign the model with sign_model() before loading."
        )

    with open(sig_file) as fh:
        expected = fh.read().strip()

    actual = _compute_hmac(model_path, key)

    if not hmac.compare_digest(actual, expected):
        raise ValueError(
            f"Model integrity mismatch for {os.path.basename(model_path)}: "
            f"expected HMAC {expected[:16]}…, got {actual[:16]}…. "
            "The file may have been tampered with."
        )

    logger.info("model_integrity_verified: %s", os.path.basename(model_path))
