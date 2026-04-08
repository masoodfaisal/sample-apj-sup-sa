"""Tests for runtime streaming behavior."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gateway.domains.runtime.streaming import StreamProcessor
from gateway.domains.runtime.types import SSEEvent, UsageInfo
from shared.exceptions import BedrockError


class ExplodingIterator:
    """Sync iterator that raises after yielding configured events."""

    def __init__(self, events: list[dict], error: Exception) -> None:
        self._events = iter(events)
        self._error = error

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self._events)
        except StopIteration as exc:
            raise self._error from exc


class IterableOnlyStream:
    """Sync iterable that is not itself an iterator."""

    def __init__(self, events: list[dict]) -> None:
        self._events = list(events)

    def __iter__(self):
        return iter(self._events)


class CloseTrackingStream(IterableOnlyStream):
    """Sync iterable that tracks whether the caller closes the stream."""

    def __init__(self, events: list[dict]) -> None:
        super().__init__(events)
        self.close = Mock()


class CloseTrackingExplodingStream:
    """Sync iterable that raises after yielding configured events and tracks close."""

    def __init__(self, events: list[dict], error: Exception) -> None:
        self._iterator = ExplodingIterator(events, error)
        self.close = Mock()

    def __iter__(self):
        return self._iterator


@pytest.mark.asyncio
async def test_stream_response_records_error_when_stream_fails_before_metadata() -> None:
    converter = Mock()
    converter.convert_stream_event.return_value = [
        SSEEvent("content_block_delta", {"type": "content_block_delta"})
    ]
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_error=AsyncMock(),
    )
    processor = StreamProcessor(converter, usage_service)

    generator = processor.stream_response(
        {
            "stream": ExplodingIterator(
                [{"contentBlockDelta": {"delta": {"text": "hi"}}}],
                RuntimeError("boom"),
            )
        },
        SimpleNamespace(),
    )

    chunks = []
    async for chunk in generator:
        chunks.append(chunk)

    usage_service.record_success.assert_not_awaited()
    usage_service.record_error.assert_awaited_once()
    error = usage_service.record_error.await_args.args[1]
    assert isinstance(error, BedrockError)
    assert chunks[-1] == SSEEvent(
        "error",
        {"type": "error", "error": {"type": "api_error", "message": "boom"}},
    ).encode()


@pytest.mark.asyncio
async def test_stream_response_closes_bedrock_stream_after_error() -> None:
    converter = Mock()
    converter.convert_stream_event.return_value = [
        SSEEvent("content_block_delta", {"type": "content_block_delta"})
    ]
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_error=AsyncMock(),
    )
    processor = StreamProcessor(converter, usage_service)
    stream = CloseTrackingExplodingStream(
        [{"contentBlockDelta": {"delta": {"text": "hi"}}}],
        RuntimeError("boom"),
    )

    generator = processor.stream_response({"stream": stream}, SimpleNamespace())

    async for _ in generator:
        pass

    stream.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_stream_response_does_not_duplicate_error_after_success_persistence() -> None:
    converter = Mock()
    converter.convert_stream_event.return_value = [
        SSEEvent("message_delta", {"type": "message_delta"})
    ]
    converter.extract_usage.return_value = UsageInfo(input_tokens=1, output_tokens=2)
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_error=AsyncMock(),
    )
    processor = StreamProcessor(converter, usage_service)

    generator = processor.stream_response(
        {
            "stream": ExplodingIterator(
                [{"metadata": {"usage": {"inputTokens": 1, "outputTokens": 2}}}],
                RuntimeError("boom"),
            )
        },
        SimpleNamespace(),
    )

    chunks = []
    async for chunk in generator:
        chunks.append(chunk)

    usage_service.record_success.assert_awaited_once()
    usage_service.record_error.assert_not_awaited()
    assert chunks[-1] == SSEEvent(
        "error",
        {"type": "error", "error": {"type": "api_error", "message": "boom"}},
    ).encode()


@pytest.mark.asyncio
async def test_stream_response_accepts_iterable_bedrock_streams() -> None:
    converter = Mock()
    converter.convert_stream_event.side_effect = [
        [SSEEvent("content_block_delta", {"type": "content_block_delta"})],
        [],
    ]
    converter.extract_usage.return_value = UsageInfo(input_tokens=1, output_tokens=2)
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_error=AsyncMock(),
    )
    processor = StreamProcessor(converter, usage_service)

    generator = processor.stream_response(
        {
            "stream": IterableOnlyStream(
                [
                    {"contentBlockDelta": {"delta": {"text": "hi"}}},
                    {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 2}}},
                ]
            )
        },
        SimpleNamespace(),
    )

    events = []
    async for chunk in generator:
        events.append(chunk)

    assert events == [
        SSEEvent("content_block_delta", {"type": "content_block_delta"}).encode()
    ]
    usage_service.record_success.assert_awaited_once()
    usage_service.record_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_response_closes_bedrock_stream_after_success() -> None:
    converter = Mock()
    converter.convert_stream_event.side_effect = [
        [SSEEvent("content_block_delta", {"type": "content_block_delta"})],
        [],
    ]
    converter.extract_usage.return_value = UsageInfo(input_tokens=1, output_tokens=2)
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_error=AsyncMock(),
    )
    processor = StreamProcessor(converter, usage_service)
    stream = CloseTrackingStream(
        [
            {"contentBlockDelta": {"delta": {"text": "hi"}}},
            {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 2}}},
        ]
    )

    generator = processor.stream_response({"stream": stream}, SimpleNamespace())

    async for _ in generator:
        pass

    stream.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_stream_response_finalizes_message_delta_when_message_stop_has_no_metadata() -> None:
    from gateway.domains.runtime.converter.response_converter import BedrockToAnthropicConverter

    converter = BedrockToAnthropicConverter()
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_error=AsyncMock(),
    )
    processor = StreamProcessor(converter, usage_service)

    generator = processor.stream_response(
        {
            "stream": IterableOnlyStream(
                [
                    {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}},
                    {"messageStop": {"stopReason": "tool_use"}},
                ]
            )
        },
        SimpleNamespace(),
    )

    events = []
    async for chunk in generator:
        events.append(chunk)

    assert events[-2] == SSEEvent(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
    ).encode()
    assert events[-1] == SSEEvent("message_stop", {"type": "message_stop"}).encode()
    usage_service.record_success.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_response_records_success_for_compact_patch_metadata_events() -> None:
    from gateway.domains.runtime.converter.response_converter import BedrockToAnthropicConverter

    converter = BedrockToAnthropicConverter()
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_error=AsyncMock(),
    )
    processor = StreamProcessor(converter, usage_service)

    generator = processor.stream_response(
        {
            "stream": IterableOnlyStream(
                [
                    {"p": "/message", "role": "assistant"},
                    {"p": "/message/stop", "stopReason": "end_turn"},
                    {
                        "p": "/message/metadata",
                        "usage": {"inputTokens": 3, "outputTokens": 7},
                        "metrics": {"latencyMs": 42},
                    },
                ]
            )
        },
        SimpleNamespace(
            request_id="req-compact-metadata",
            request=SimpleNamespace(model="claude-test"),
        ),
    )

    events = []
    async for chunk in generator:
        events.append(chunk)

    usage_service.record_success.assert_awaited_once()
    usage = usage_service.record_success.await_args.args[1]
    assert isinstance(usage, UsageInfo)
    assert usage.input_tokens == 3
    assert usage.output_tokens == 7
    assert usage.latency_ms == 42
    assert events[-2] == SSEEvent(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {
                "input_tokens": 3,
                "output_tokens": 7,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
    ).encode()
    assert events[-1] == SSEEvent("message_stop", {"type": "message_stop"}).encode()
    usage_service.record_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_response_uses_resolved_bedrock_model_id_in_message_start() -> None:
    from gateway.domains.runtime.converter.response_converter import BedrockToAnthropicConverter

    converter = BedrockToAnthropicConverter()
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_error=AsyncMock(),
    )
    processor = StreamProcessor(converter, usage_service)

    generator = processor.stream_response(
        {
            "stream": IterableOnlyStream(
                [
                    {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}},
                ]
            )
        },
        SimpleNamespace(
            request_id="req-model-id",
            request=SimpleNamespace(model="claude-haiku-4-5-20251001"),
            resolved_model=SimpleNamespace(bedrock_model_id="zai.glm-5"),
        ),
    )

    events = []
    async for chunk in generator:
        events.append(chunk)

    assert '"model":"zai.glm-5"' in events[0]


@pytest.mark.asyncio
async def test_stream_response_does_not_log_anthropic_sse_payload(caplog) -> None:
    converter = Mock()
    converter.convert_stream_event.return_value = [
        SSEEvent(
            "content_block_delta",
            {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "hi"},
            },
        )
    ]
    usage_service = SimpleNamespace(
        record_success=AsyncMock(),
        record_error=AsyncMock(),
    )
    processor = StreamProcessor(converter, usage_service)

    generator = processor.stream_response(
        {
            "stream": IterableOnlyStream(
                [
                    {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "hi"}}},
                ]
            )
        },
        SimpleNamespace(request_id="req-stream-raw"),
    )

    with caplog.at_level(logging.INFO, logger="gateway.domains.runtime.streaming"):
        async for _ in generator:
            pass

    assert "runtime anthropic stream event raw" not in caplog.text
