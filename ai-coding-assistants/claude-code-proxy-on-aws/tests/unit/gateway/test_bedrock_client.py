"""Tests for the Bedrock runtime client wrapper."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from botocore.exceptions import ParamValidationError

from gateway.core.config import Settings
from gateway.domains.runtime.bedrock_client import BedrockClient
from shared.exceptions import BedrockError


@pytest.mark.asyncio
async def test_converse_stream_wraps_param_validation_errors(monkeypatch) -> None:
    def fake_client(*_args, **_kwargs):
        return SimpleNamespace(
            converse_stream=lambda **_: (_ for _ in ()).throw(
                ParamValidationError(report="bad payload")
            )
        )

    monkeypatch.setattr("gateway.domains.runtime.bedrock_client.boto3.client", fake_client)
    client = BedrockClient(Settings(aws_region="ap-northeast-2"))

    with pytest.raises(BedrockError, match="bad payload"):
        await client.converse_stream({"messages": []})


@pytest.mark.asyncio
async def test_converse_uses_resolved_model_bedrock_region(monkeypatch) -> None:
    captured_regions: list[str] = []

    def fake_client(*_args, **kwargs):
        captured_regions.append(kwargs["region_name"])
        return SimpleNamespace(converse=lambda **_: {"output": {}})

    monkeypatch.setattr("gateway.domains.runtime.bedrock_client.boto3.client", fake_client)
    client = BedrockClient(Settings(aws_region="ap-northeast-2"))

    await client.converse(
        {"messages": []},
        SimpleNamespace(bedrock_region="us-east-1"),
    )
    await client.converse(
        {"messages": []},
        SimpleNamespace(bedrock_region="us-east-1"),
    )

    assert captured_regions == ["us-east-1"]


@pytest.mark.asyncio
async def test_converse_falls_back_to_settings_region_when_model_region_missing(
    monkeypatch,
) -> None:
    captured_regions: list[str] = []

    def fake_client(*_args, **kwargs):
        captured_regions.append(kwargs["region_name"])
        return SimpleNamespace(converse=lambda **_: {"output": {}})

    monkeypatch.setattr("gateway.domains.runtime.bedrock_client.boto3.client", fake_client)
    client = BedrockClient(Settings(aws_region="ap-northeast-1"))

    await client.converse({"messages": []}, SimpleNamespace(bedrock_region=None))

    assert captured_regions == ["ap-northeast-1"]
