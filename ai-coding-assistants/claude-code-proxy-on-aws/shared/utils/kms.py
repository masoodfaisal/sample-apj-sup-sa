"""Minimal KMS helper."""

from __future__ import annotations

import base64
import os
import threading
from typing import Any

import boto3

from shared.utils.hashing import sha256_hex

_thread_local = threading.local()
_LOCAL_KMS_PREFIX = b"local-kms:v1:"
_LEGACY_LOCAL_PLACEHOLDER = b"local-dev-placeholder"


class KmsHelper:
    """Thin wrapper around boto3 KMS operations."""

    @staticmethod
    def _use_local_fallback() -> bool:
        return (
            os.getenv("ENVIRONMENT") == "local"
            and os.getenv("KMS_KEY_ID") == "local-dev-placeholder"
        )

    @classmethod
    def _get_client(cls) -> Any:
        client = getattr(_thread_local, "kms_client", None)
        if client is None:
            client = boto3.client("kms")
            _thread_local.kms_client = client
        return client

    @classmethod
    def encrypt_key(cls, plaintext_key: str) -> bytes:
        if cls._use_local_fallback():
            return _LOCAL_KMS_PREFIX + base64.urlsafe_b64encode(plaintext_key.encode("utf-8"))
        response = cls._get_client().encrypt(
            KeyId=os.environ["KMS_KEY_ID"],
            Plaintext=plaintext_key.encode("utf-8"),
        )
        return response["CiphertextBlob"]

    @classmethod
    def decrypt_key(cls, ciphertext: bytes) -> str:
        if cls._use_local_fallback():
            if ciphertext == _LEGACY_LOCAL_PLACEHOLDER:
                return os.getenv("LOCAL_BOOTSTRAP_API_KEY", "sk-local-dev")
            if not ciphertext.startswith(_LOCAL_KMS_PREFIX):
                msg = "Unsupported local KMS ciphertext"
                raise ValueError(msg)
            return base64.urlsafe_b64decode(ciphertext.removeprefix(_LOCAL_KMS_PREFIX)).decode(
                "utf-8"
            )
        response = cls._get_client().decrypt(CiphertextBlob=ciphertext)
        return response["Plaintext"].decode("utf-8")

    @staticmethod
    def generate_fingerprint(plaintext_key: str) -> str:
        return sha256_hex(plaintext_key)
