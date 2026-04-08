"""Smoke tests for gateway helpers that do not require external services."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import gateway.core.dependencies as dependencies
import gateway.main as gateway_main
from gateway.core import telemetry
from gateway.core.config import get_settings
from gateway.core.dependencies import get_bedrock_client, get_identity_store_gateway, get_policy_chain
from gateway.domains.runtime.converter.response_converter import BedrockToAnthropicConverter
from gateway.domains.runtime.types import StreamState


def test_settings_have_expected_defaults() -> None:
    settings = get_settings()
    assert settings.admin_origin_header == "x-admin-origin"
    assert settings.request_id_header == "x-request-id"
    assert settings.otlp_export_interval_millis == 60_000


def test_stream_converter_emits_message_start_before_content() -> None:
    converter = BedrockToAnthropicConverter()
    events = converter.convert_stream_event({"contentBlockStart": {}}, StreamState())
    assert events[0].event == "message_start"
    assert events[1].event == "content_block_start"


def test_identity_store_gateway_reuses_cached_boto3_client(monkeypatch) -> None:
    fake_client = MagicMock()
    boto_factory = MagicMock(return_value=fake_client)
    settings = get_settings()

    dependencies._get_identity_store_client.cache_clear()
    monkeypatch.setattr(dependencies.boto3, "client", boto_factory)

    first = get_identity_store_gateway(settings)
    second = get_identity_store_gateway(settings)

    assert boto_factory.call_count == 1
    assert first._client is second._client
    dependencies._get_identity_store_client.cache_clear()


def test_bedrock_client_dependency_reuses_cached_client(monkeypatch) -> None:
    import gateway.domains.runtime.bedrock_client as bedrock_client_module

    fake_client = MagicMock()
    boto_factory = MagicMock(return_value=fake_client)
    settings = get_settings()

    dependencies._get_bedrock_client.cache_clear()
    monkeypatch.setattr(bedrock_client_module.boto3, "client", boto_factory)

    first = get_bedrock_client(settings)
    second = get_bedrock_client(settings)

    assert first is second
    assert boto_factory.call_count == 0

    first._get_client()

    assert boto_factory.call_count == 1
    assert first._get_client() is second._get_client()
    dependencies._get_bedrock_client.cache_clear()


def test_metrics_service_dependency_is_cached() -> None:
    dependencies.get_metrics_service.cache_clear()

    first = dependencies.get_metrics_service()
    second = dependencies.get_metrics_service()

    assert first is second
    dependencies.get_metrics_service.cache_clear()


def test_policy_chain_uses_read_policy_repositories() -> None:
    key_repo = object()
    user_repo = object()
    team_repo = object()
    mapping_repo = object()
    user_policy_repo = object()
    team_policy_repo = object()
    budget_repo = object()

    chain = get_policy_chain(
        key_repo=key_repo,
        user_repo=user_repo,
        team_repo=team_repo,
        mapping_repo=mapping_repo,
        user_policy_repo=user_policy_repo,
        team_policy_repo=team_policy_repo,
        budget_repo=budget_repo,
    )

    assert chain._handlers[4]._repo is user_policy_repo
    assert chain._handlers[5]._repo is team_policy_repo


def test_app_lifespan_disposes_database_engines(monkeypatch) -> None:
    engine = MagicMock()
    engine.dispose = AsyncMock()
    read_engine = MagicMock()
    read_engine.dispose = AsyncMock()

    monkeypatch.setattr(gateway_main, "ENGINE", engine)
    monkeypatch.setattr(gateway_main, "READ_ENGINE", read_engine)

    async def run_lifespan() -> None:
        async with gateway_main.app_lifespan(gateway_main.FastAPI()):
            pass

    asyncio.run(run_lifespan())

    read_engine.dispose.assert_awaited_once()
    engine.dispose.assert_awaited_once()


def test_init_meter_provider_skips_otlp_exporter_when_endpoint_blank(monkeypatch) -> None:
    exporter_factory = MagicMock()
    set_provider = MagicMock()
    meter = MagicMock()
    provider = MagicMock()
    provider.get_meter.return_value = meter
    meter_provider_factory = MagicMock(return_value=provider)

    monkeypatch.setattr(telemetry, "OTLPMetricExporter", exporter_factory)
    monkeypatch.setattr(telemetry, "set_meter_provider", set_provider)
    monkeypatch.setattr(telemetry, "MeterProvider", meter_provider_factory)

    telemetry.init_meter_provider("")

    exporter_factory.assert_not_called()
    meter_provider_factory.assert_called_once_with(metric_readers=[])
    set_provider.assert_called_once_with(provider)


def test_init_meter_provider_uses_configured_export_interval(monkeypatch) -> None:
    exporter = MagicMock()
    exporter_factory = MagicMock(return_value=exporter)
    reader_factory = MagicMock(return_value="reader")
    set_provider = MagicMock()
    meter = MagicMock()
    provider = MagicMock()
    provider.get_meter.return_value = meter
    meter_provider_factory = MagicMock(return_value=provider)

    monkeypatch.setattr(telemetry, "OTLPMetricExporter", exporter_factory)
    monkeypatch.setattr(telemetry, "PeriodicExportingMetricReader", reader_factory)
    monkeypatch.setattr(telemetry, "set_meter_provider", set_provider)
    monkeypatch.setattr(telemetry, "MeterProvider", meter_provider_factory)

    telemetry.init_meter_provider("http://otel-collector:4317", 30_000)

    exporter_factory.assert_called_once_with(
        endpoint="http://otel-collector:4317",
        insecure=True,
    )
    reader_factory.assert_called_once_with(exporter, export_interval_millis=30_000)
    meter_provider_factory.assert_called_once_with(metric_readers=["reader"])
