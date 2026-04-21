"""Tests for runtime logging behavior."""

from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gateway.domains.runtime.services import GatewayService
from gateway.domains.runtime.streaming import StreamProcessor
from gateway.domains.runtime.types import MessageRequest, UsageInfo
from gateway.domains.usage.services import UsageService
from shared.exceptions import BedrockError, BedrockThrottlingError


@pytest.fixture(autouse=True)
def _isolate_gateway_logging() -> None:
    gateway_logger = logging.getLogger("gateway")
    original = {
        "handlers": list(gateway_logger.handlers),
        "level": gateway_logger.level,
        "propagate": gateway_logger.propagate,
    }
    gateway_logger.handlers = []
    gateway_logger.setLevel(logging.NOTSET)
    gateway_logger.propagate = True
    try:
        yield
    finally:
        gateway_logger.handlers = original["handlers"]
        gateway_logger.setLevel(original["level"])
        gateway_logger.propagate = original["propagate"]


def _build_request() -> MessageRequest:
    return MessageRequest(
        model="claude-sonnet-4-6",
        max_tokens=128,
        messages=[{"role": "user", "content": "Hello"}],
    )


def _stub_metrics():
    return SimpleNamespace(
        emit_token_usage=Mock(),
        emit_cost_usage=Mock(),
        emit_request_duration=Mock(),
        emit_request_count=Mock(),
        emit_throttle=Mock(),
        emit_policy_block=Mock(),
        emit_active_request_start=Mock(),
        emit_active_request_end=Mock(),
        emit_budget_utilization=Mock(),
        emit_ttfb=Mock(),
    )


@pytest.mark.asyncio
async def test_usage_service_logs_runtime_request_completion(caplog) -> None:
    pricing_repo = SimpleNamespace(
        get_active_pricing=AsyncMock(
            return_value=SimpleNamespace(
                input_price_per_1k=Decimal("1"),
                output_price_per_1k=Decimal("1"),
                cache_read_price_per_1k=Decimal("1"),
                cache_write_5m_price_per_1k=Decimal("1"),
                cache_write_1h_price_per_1k=Decimal("1"),
            )
        )
    )
    budget_repo = SimpleNamespace(apply_costs=AsyncMock())
    event_repo = SimpleNamespace(create_event=AsyncMock(return_value=SimpleNamespace()))
    metrics = _stub_metrics()
    session = SimpleNamespace(commit=AsyncMock())
    service = UsageService(pricing_repo, budget_repo, event_repo, metrics, session)
    context = SimpleNamespace(
        request_id="req-success",
        selected_model="claude-sonnet-4-6",
        resolved_model=SimpleNamespace(
            id="model-id",
            bedrock_model_id="anthropic.claude-sonnet-4-6",
        ),
        user=SimpleNamespace(id="user-123"),
        virtual_key=SimpleNamespace(id="vk-123"),
        team=None,
        applicable_budgets=[],
        cache_policy="none",
        is_stream=False,
    )
    usage = UsageInfo(
        input_tokens=10,
        output_tokens=20,
        cached_read_tokens=30,
        cached_write_tokens=40,
    )

    with caplog.at_level(logging.INFO, logger="gateway.domains.usage.services"):
        await service.record_success(context, usage)

    assert "runtime request completed" in caplog.text
    assert "request_id=req-success" in caplog.text
    assert "selected_model=claude-sonnet-4-6" in caplog.text
    assert "resolved_model=anthropic.claude-sonnet-4-6" in caplog.text
    assert "user_id=user-123" in caplog.text
    assert "cache_read_input_tokens=30" in caplog.text
    assert "cache_creation_input_tokens=40" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_level"),
    [
        (BedrockError("bedrock failed"), logging.ERROR),
        (BedrockThrottlingError("rate limited"), logging.WARNING),
    ],
)
async def test_gateway_service_logs_bedrock_errors_with_context(
    caplog, error, expected_level
) -> None:
    policy_chain = SimpleNamespace(evaluate=AsyncMock())

    async def evaluate(context):
        context.user = SimpleNamespace(id="user-123")
        context.virtual_key = SimpleNamespace(id="vk-123")
        context.resolved_model = SimpleNamespace(
            id="model-id",
            bedrock_model_id="anthropic.claude-sonnet-4-6",
        )

    policy_chain.evaluate.side_effect = evaluate
    metrics = _stub_metrics()
    service = GatewayService(
        policy_chain=policy_chain,
        request_converter=SimpleNamespace(convert_request=Mock(return_value={})),
        response_converter=SimpleNamespace(
            convert_response=Mock(),
            extract_usage=Mock(),
        ),
        bedrock_client=SimpleNamespace(converse=AsyncMock(side_effect=error)),
        stream_processor=SimpleNamespace(stream_response=Mock()),
        usage_service=SimpleNamespace(
            record_success=AsyncMock(),
            record_blocked_request=AsyncMock(),
            record_error=AsyncMock(),
        ),
        session=SimpleNamespace(commit=AsyncMock()),
        model_catalog_repo=SimpleNamespace(),
        metrics=metrics,
    )

    with caplog.at_level(logging.WARNING, logger="gateway.domains.runtime.services"):
        with pytest.raises(type(error), match=str(error)):
            await service.process_message(_build_request(), "sk-test", "req-bedrock")

    matching_records = [
        record
        for record in caplog.records
        if record.name == "gateway.domains.runtime.services"
        and record.message.startswith("bedrock runtime request failed")
    ]
    assert matching_records
    assert matching_records[-1].levelno == expected_level
    assert "request_id=req-bedrock" in matching_records[-1].message
    assert "selected_model=claude-sonnet-4-6" in matching_records[-1].message
    assert "resolved_model=anthropic.claude-sonnet-4-6" in matching_records[-1].message
    assert "user_id=user-123" in matching_records[-1].message

    # Verify new metrics were emitted
    metrics.emit_active_request_start.assert_called_once()
    metrics.emit_active_request_end.assert_called_once()
    metrics.emit_policy_block.assert_not_called()
    if isinstance(error, BedrockThrottlingError):
        metrics.emit_throttle.assert_called_once()
    else:
        metrics.emit_throttle.assert_not_called()


@pytest.mark.asyncio
async def test_gateway_service_returns_resolved_bedrock_model_id_to_response_converter() -> None:
    policy_chain = SimpleNamespace(evaluate=AsyncMock())

    async def evaluate(context):
        context.user = SimpleNamespace(id="user-123")
        context.virtual_key = SimpleNamespace(id="vk-123")
        context.resolved_model = SimpleNamespace(
            id="model-id",
            bedrock_model_id="zai.glm-5",
        )

    policy_chain.evaluate.side_effect = evaluate
    response_converter = SimpleNamespace(
        convert_response=Mock(return_value=SimpleNamespace()),
        extract_usage=Mock(return_value=UsageInfo()),
    )
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_blocked_request=AsyncMock(),
        record_error=AsyncMock(),
    )
    service = GatewayService(
        policy_chain=policy_chain,
        request_converter=SimpleNamespace(convert_request=Mock(return_value={})),
        response_converter=response_converter,
        bedrock_client=SimpleNamespace(converse=AsyncMock(return_value={"output": {}})),
        stream_processor=SimpleNamespace(stream_response=Mock()),
        usage_service=usage_service,
        session=SimpleNamespace(commit=AsyncMock()),
        model_catalog_repo=SimpleNamespace(),
        metrics=_stub_metrics(),
    )

    await service.process_message(_build_request(), "sk-test", "req-model-id")

    assert response_converter.convert_response.call_args.args[1] == "zai.glm-5"


@pytest.mark.asyncio
async def test_gateway_service_injects_request_metadata_for_bedrock_converse() -> None:
    policy_chain = SimpleNamespace(evaluate=AsyncMock())

    async def evaluate(context):
        context.user = SimpleNamespace(id="user-123")
        context.team = SimpleNamespace(id="team-456")
        context.virtual_key = SimpleNamespace(id="vk-123")
        context.resolved_model = SimpleNamespace(
            id="model-id",
            bedrock_model_id="zai.glm-5",
        )

    policy_chain.evaluate.side_effect = evaluate
    response_converter = SimpleNamespace(
        convert_response=Mock(return_value=SimpleNamespace()),
        extract_usage=Mock(return_value=UsageInfo()),
    )
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_blocked_request=AsyncMock(),
        record_error=AsyncMock(),
    )
    bedrock_client = SimpleNamespace(
        converse=AsyncMock(return_value={"output": {"message": {"content": []}}})
    )
    service = GatewayService(
        policy_chain=policy_chain,
        request_converter=SimpleNamespace(
            convert_request=Mock(return_value={"modelId": "zai.glm-5"})
        ),
        response_converter=response_converter,
        bedrock_client=bedrock_client,
        stream_processor=SimpleNamespace(stream_response=Mock()),
        usage_service=usage_service,
        session=SimpleNamespace(commit=AsyncMock()),
        model_catalog_repo=SimpleNamespace(),
        metrics=_stub_metrics(),
    )

    await service.process_message(_build_request(), "sk-test", "req-metadata")

    assert bedrock_client.converse.call_args.args[0]["requestMetadata"] == {
        "request_id": "req-metadata",
        "user_id": "user-123",
        "team_id": "team-456",
    }


@pytest.mark.asyncio
async def test_gateway_service_injects_request_metadata_for_bedrock_stream() -> None:
    policy_chain = SimpleNamespace(evaluate=AsyncMock())

    async def evaluate(context):
        context.user = SimpleNamespace(id="user-123")
        context.team = SimpleNamespace(id="team-456")
        context.virtual_key = SimpleNamespace(id="vk-123")
        context.resolved_model = SimpleNamespace(
            id="model-id",
            bedrock_model_id="zai.glm-5",
        )

    policy_chain.evaluate.side_effect = evaluate
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_blocked_request=AsyncMock(),
        record_error=AsyncMock(),
    )
    bedrock_client = SimpleNamespace(
        converse_stream=AsyncMock(return_value={"stream": []}),
    )
    stream_processor = SimpleNamespace(stream_response=Mock(return_value=iter(())))
    service = GatewayService(
        policy_chain=policy_chain,
        request_converter=SimpleNamespace(
            convert_request=Mock(return_value={"modelId": "zai.glm-5"})
        ),
        response_converter=SimpleNamespace(
            convert_response=Mock(),
            extract_usage=Mock(return_value=UsageInfo()),
        ),
        bedrock_client=bedrock_client,
        stream_processor=stream_processor,
        usage_service=usage_service,
        session=SimpleNamespace(commit=AsyncMock()),
        model_catalog_repo=SimpleNamespace(),
        metrics=_stub_metrics(),
    )

    request = _build_request().model_copy(update={"stream": True})
    await service.process_message_stream(request, "sk-test", "req-stream-metadata")

    assert bedrock_client.converse_stream.call_args.args[0]["requestMetadata"] == {
        "request_id": "req-stream-metadata",
        "user_id": "user-123",
        "team_id": "team-456",
    }


@pytest.mark.asyncio
async def test_gateway_service_logs_full_payloads_when_enabled(caplog) -> None:
    policy_chain = SimpleNamespace(evaluate=AsyncMock())

    async def evaluate(context):
        context.user = SimpleNamespace(id="user-123")
        context.team = SimpleNamespace(id="team-456")
        context.virtual_key = SimpleNamespace(id="vk-123")
        context.resolved_model = SimpleNamespace(
            id="model-id",
            bedrock_model_id="zai.glm-5",
        )

    policy_chain.evaluate.side_effect = evaluate
    response_converter = SimpleNamespace(
        convert_response=Mock(return_value=SimpleNamespace()),
        extract_usage=Mock(return_value=UsageInfo()),
    )
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_blocked_request=AsyncMock(),
        record_error=AsyncMock(),
    )
    service = GatewayService(
        policy_chain=policy_chain,
        request_converter=SimpleNamespace(
            convert_request=Mock(return_value={"modelId": "zai.glm-5"})
        ),
        response_converter=response_converter,
        bedrock_client=SimpleNamespace(
            converse=AsyncMock(return_value={"output": {"message": {"content": []}}})
        ),
        stream_processor=SimpleNamespace(stream_response=Mock()),
        usage_service=usage_service,
        session=SimpleNamespace(commit=AsyncMock()),
        model_catalog_repo=SimpleNamespace(),
        metrics=_stub_metrics(),
        log_full_payloads=True,
    )

    with caplog.at_level(logging.INFO, logger="gateway.domains.runtime.services"):
        await service.process_message(_build_request(), "sk-test", "req-payloads")

    assert "runtime anthropic request payload request_id=req-payloads" in caplog.text
    assert '"model":"claude-sonnet-4-6"' in caplog.text
    assert "runtime bedrock request payload request_id=req-payloads" in caplog.text
    assert '"modelId":"zai.glm-5"' in caplog.text
    assert '"requestMetadata":{"request_id":"req-payloads","user_id":"user-123","team_id":"team-456"}' in caplog.text
    assert "runtime bedrock response payload request_id=req-payloads" in caplog.text


@pytest.mark.asyncio
async def test_stream_processor_logs_raw_bedrock_stream_events_when_enabled(caplog) -> None:
    converter = SimpleNamespace(
        convert_stream_event=Mock(return_value=[]),
        extract_usage=Mock(return_value=UsageInfo()),
        finalize_stream=Mock(return_value=[]),
    )
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_error=AsyncMock(),
    )
    processor = StreamProcessor(
        converter,
        usage_service,
        log_full_payloads=True,
        log_stream_events=True,
    )

    generator = processor.stream_response(
        {"stream": [{"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "hi"}}}]},
        SimpleNamespace(request_id="req-stream-payload"),
    )

    with caplog.at_level(logging.INFO, logger="gateway.domains.runtime.streaming"):
        async for _ in generator:
            pass

    assert "runtime bedrock stream event payload request_id=req-stream-payload" in caplog.text
    assert '"contentBlockDelta":{"contentBlockIndex":0,"delta":{"text":"hi"}}' in caplog.text
