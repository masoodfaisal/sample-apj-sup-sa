"""Tests for admin virtual key routing contracts."""

from __future__ import annotations

import asyncio
from typing import get_args, get_type_hints

import pytest

from gateway.domains.admin.virtual_keys import list_virtual_keys
from shared.utils.constants import VirtualKeyStatus


class _StubAdminVirtualKeyService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object, object, object]] = []

    async def list_keys(self, user_id, status, page, page_size):  # type: ignore[no-untyped-def]
        self.calls.append((user_id, status, page, page_size))
        return {"items": [], "next_page": None}


def test_list_virtual_keys_status_annotation_is_enum() -> None:
    status_hint = get_type_hints(list_virtual_keys)["status"]

    assert VirtualKeyStatus in get_args(status_hint)
    assert type(None) in get_args(status_hint)


def test_list_virtual_keys_passes_enum_status_to_service() -> None:
    service = _StubAdminVirtualKeyService()

    response = asyncio.run(
        list_virtual_keys(status=VirtualKeyStatus.ACTIVE, page=1, page_size=100, service=service)
    )

    assert response == {"items": [], "next_page": None}
    assert service.calls == [(None, VirtualKeyStatus.ACTIVE, 1, 100)]


def test_virtual_key_status_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        VirtualKeyStatus("BROKEN")
