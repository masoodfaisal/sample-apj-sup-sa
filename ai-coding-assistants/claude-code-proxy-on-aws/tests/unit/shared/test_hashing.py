"""Tests for hashing helpers."""

from hypothesis import given
from hypothesis import strategies as st

from shared.utils.hashing import generate_api_key, sha256_hex


@given(st.text())
def test_sha256_hex_is_deterministic(value: str) -> None:
    digest = sha256_hex(value)
    assert digest == sha256_hex(value)
    assert len(digest) == 64


def test_generate_api_key_format_and_uniqueness() -> None:
    keys = {generate_api_key() for _ in range(32)}
    assert len(keys) == 32
    assert all(key.startswith("sk-") for key in keys)
