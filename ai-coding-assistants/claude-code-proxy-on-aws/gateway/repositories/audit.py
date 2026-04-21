"""Audit repositories."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update

from gateway.repositories.base import BaseRepository, paginate_window
from shared.models import AuditEvent, IdentitySyncRun


class AuditEventRepository(BaseRepository):
    async def create_event(self, event: AuditEvent) -> AuditEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_events(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[AuditEvent], int | None]:
        stmt = (
            select(AuditEvent)
            .order_by(AuditEvent.created_at.desc())
            .limit(page_size + 1)
            .offset((page - 1) * page_size)
        )
        events = (await self.session.execute(stmt)).scalars().all()
        return paginate_window(events, page, page_size)


class IdentitySyncRunRepository(BaseRepository):
    async def get_by_id(self, run_id: UUID) -> IdentitySyncRun | None:
        return await self.session.get(IdentitySyncRun, run_id)

    async def get_latest(self) -> IdentitySyncRun | None:
        stmt = select(IdentitySyncRun).order_by(IdentitySyncRun.started_at.desc()).limit(1)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_run(self, run: IdentitySyncRun) -> IdentitySyncRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def update_run(self, run: IdentitySyncRun, **changes: object) -> IdentitySyncRun:
        for key, value in changes.items():
            setattr(run, key, value)
        await self.session.flush()
        return run

    async def update_run_by_id(self, run_id: UUID, **changes: object) -> IdentitySyncRun | None:
        stmt = (
            update(IdentitySyncRun)
            .where(IdentitySyncRun.id == run_id)
            .values(**changes)
            .returning(IdentitySyncRun)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
