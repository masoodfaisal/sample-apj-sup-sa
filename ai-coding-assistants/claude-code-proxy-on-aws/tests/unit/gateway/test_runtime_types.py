"""Tests for runtime request/response types."""

from __future__ import annotations

from gateway.domains.runtime.types import MessageRequest


def test_message_request_ignores_unknown_top_level_fields() -> None:
    request = MessageRequest(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": "hello"}],
        experimental_flag={"enabled": True},
    )

    assert request.model_dump() == {
        "model": "claude-sonnet-4-6",
        "max_tokens": 256,
        "system": None,
        "messages": [{"role": "user", "content": "hello"}],
        "tools": None,
        "tool_choice": None,
        "stream": False,
        "temperature": None,
        "top_p": None,
        "stop_sequences": None,
        "thinking": None,
        "metadata": None,
    }
