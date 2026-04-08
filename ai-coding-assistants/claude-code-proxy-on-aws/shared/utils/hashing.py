"""Hashing helpers for API key material."""

from __future__ import annotations

import hashlib
import secrets


def sha256_hex(data: str) -> str:
    """Return a SHA-256 hex digest for the provided string."""

    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    """Generate a Claude-proxy API key."""

    return f"sk-{secrets.token_urlsafe(32)}"
