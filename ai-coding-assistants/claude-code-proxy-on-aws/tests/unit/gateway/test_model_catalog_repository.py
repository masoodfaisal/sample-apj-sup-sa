"""Tests for model catalog repository pagination ordering."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from gateway.repositories.model_catalog import (
    ModelAliasMappingRepository,
    ModelPricingRepository,
)


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
async def test_list_mappings_orders_by_priority_then_id_for_stable_pagination() -> None:
    first = SimpleNamespace(id=uuid4())
    second = SimpleNamespace(id=uuid4())
    overflow = SimpleNamespace(id=uuid4())
    captured = {}

    async def execute(statement):
        captured["statement"] = statement
        return _FakeExecuteResult([first, second, overflow])

    repo = ModelAliasMappingRepository(
        session=SimpleNamespace(execute=AsyncMock(side_effect=execute))
    )

    items, next_page = await repo.list(page=1, page_size=2)

    assert items == [first, second]
    assert next_page == 2
    assert (
        "ORDER BY model_alias_mappings.priority DESC, model_alias_mappings.id DESC"
        in str(captured["statement"])
    )


@pytest.mark.asyncio
async def test_list_pricing_orders_by_effective_from_then_id_for_stable_pagination() -> None:
    model_id = uuid4()
    first = SimpleNamespace(id=uuid4())
    overflow = SimpleNamespace(id=uuid4())
    captured = {}

    async def execute(statement):
        captured["statement"] = statement
        return _FakeExecuteResult([first, overflow])

    repo = ModelPricingRepository(
        session=SimpleNamespace(execute=AsyncMock(side_effect=execute))
    )

    items, next_page = await repo.list(model_id=model_id, page=2, page_size=1)

    assert items == [first]
    assert next_page == 3
    statement = str(captured["statement"])
    assert "WHERE model_pricing.model_id =" in statement
    assert "ORDER BY model_pricing.effective_from DESC, model_pricing.id DESC" in statement
