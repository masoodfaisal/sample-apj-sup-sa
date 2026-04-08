"""Tests for KMS helper."""

from __future__ import annotations

import boto3

from shared.utils import kms as kms_module
from shared.utils.kms import KmsHelper


class _FakeKmsClient:
    def encrypt(self, *, KeyId: str, Plaintext: bytes) -> dict[str, bytes]:
        return {"CiphertextBlob": KeyId.encode("utf-8") + b":" + Plaintext}

    def decrypt(self, *, CiphertextBlob: bytes) -> dict[str, bytes]:
        _, plaintext = CiphertextBlob.split(b":", maxsplit=1)
        return {"Plaintext": plaintext}


def _clear_kms_client() -> None:
    if hasattr(kms_module._thread_local, "kms_client"):
        delattr(kms_module._thread_local, "kms_client")


def test_kms_helper_round_trip(monkeypatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("KMS_KEY_ID", "kms-key")
    monkeypatch.setattr(boto3, "client", lambda service: _FakeKmsClient())
    _clear_kms_client()

    ciphertext = KmsHelper.encrypt_key("secret-value")
    plaintext = KmsHelper.decrypt_key(ciphertext)

    assert plaintext == "secret-value"
    assert KmsHelper.generate_fingerprint("secret-value")


def test_kms_helper_uses_local_fallback(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("KMS_KEY_ID", "local-dev-placeholder")
    monkeypatch.setattr(
        boto3,
        "client",
        lambda service: (_ for _ in ()).throw(AssertionError("boto3 KMS should not be used")),
    )
    _clear_kms_client()

    ciphertext = KmsHelper.encrypt_key("secret-value")

    assert ciphertext.startswith(b"local-kms:v1:")
    assert KmsHelper.decrypt_key(ciphertext) == "secret-value"


def test_kms_helper_supports_legacy_local_placeholder(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("KMS_KEY_ID", "local-dev-placeholder")
    monkeypatch.setenv("LOCAL_BOOTSTRAP_API_KEY", "sk-local-dev")
    _clear_kms_client()

    assert KmsHelper.decrypt_key(b"local-dev-placeholder") == "sk-local-dev"
