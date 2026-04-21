"""Shared repository helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class BaseRepository:
    """Base class for request-scoped repositories."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session


def paginate_window(items: Sequence[T], page: int, page_size: int) -> tuple[list[T], int | None]:
    """Return one page plus next page pointer from an over-fetched window."""

    has_next = len(items) > page_size
    page_items = list(items[:page_size])
    return page_items, (page + 1 if has_next else None)
