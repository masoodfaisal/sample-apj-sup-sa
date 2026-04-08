"""Tests for model alias resolution priority ordering."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.repositories.model_catalog import ModelAliasMappingRepository


class _FakeScalarResult:
    def __init__(self, values) -> None:
        self._values = values

    def all(self):
        return self._values


class _FakeExecuteResult:
    def __init__(self, values) -> None:
        self._values = values

    def scalars(self):
        return _FakeScalarResult(self._values)


@pytest.mark.asyncio
async def test_resolve_mapping_prefers_higher_priority_specific_pattern() -> None:
    fallback = SimpleNamespace(
        selected_model_pattern="*",
        priority=100,
        is_fallback=True,
        target_model=SimpleNamespace(bedrock_model_id="global.anthropic.claude-sonnet-4-6"),
    )
    specific = SimpleNamespace(
        selected_model_pattern="claude-sonnet-4-6*",
        priority=300,
        is_fallback=False,
        target_model=SimpleNamespace(bedrock_model_id="global.anthropic.claude-sonnet-4-6"),
    )
    captured = {}

    async def execute(statement):
        captured["statement"] = statement
        return _FakeExecuteResult([specific, fallback])

    repo = ModelAliasMappingRepository(
        session=SimpleNamespace(execute=AsyncMock(side_effect=execute))
    )

    resolved = await repo.resolve_mapping("claude-sonnet-4-6")

    assert resolved is specific
    assert "ORDER BY model_alias_mappings.priority DESC" in str(captured["statement"])
