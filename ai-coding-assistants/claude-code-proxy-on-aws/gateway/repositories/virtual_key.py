"""Virtual key repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from gateway.repositories.base import BaseRepository, paginate_window
from shared.models import VirtualKey
from shared.utils.constants import VirtualKeyStatus


class VirtualKeyRepository(BaseRepository):
    async def get_by_id(self, key_id: UUID) -> VirtualKey | None:
        return await self.session.get(VirtualKey, key_id)

    async def get_active_by_user(
        self,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> VirtualKey | None:
        stmt = select(VirtualKey).where(
            VirtualKey.user_id == user_id,
            VirtualKey.status == VirtualKeyStatus.ACTIVE,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_fingerprint(self, fingerprint: str) -> VirtualKey | None:
        stmt = select(VirtualKey).where(VirtualKey.key_fingerprint == fingerprint)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list(
        self,
        *,
        user_id: UUID | None = None,
        status: VirtualKeyStatus | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[VirtualKey], int | None]:
        stmt = select(VirtualKey)
        if user_id:
            stmt = stmt.where(VirtualKey.user_id == user_id)
        if status:
            stmt = stmt.where(VirtualKey.status == status)
        stmt = (
            stmt.order_by(VirtualKey.issued_at.desc())
            .limit(page_size + 1)
            .offset((page - 1) * page_size)
        )
        keys = (await self.session.execute(stmt)).scalars().all()
        return paginate_window(keys, page, page_size)

    async def create(self, key: VirtualKey) -> VirtualKey:
        self.session.add(key)
        await self.session.flush()
        return key

    async def update_status(
        self, key: VirtualKey, status: VirtualKeyStatus, **changes: object
    ) -> VirtualKey:
        key.status = status
        for attr, value in changes.items():
            setattr(key, attr, value)
        await self.session.flush()
        return key
