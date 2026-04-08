"""Usage repositories."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select

from gateway.repositories.base import BaseRepository, paginate_window
from shared.models import UsageDailyAgg, UsageEvent, UsageMonthlyAgg


class UsageEventRepository(BaseRepository):
    async def create_event(self, event: UsageEvent) -> UsageEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_events(
        self,
        *,
        user_id: UUID | None = None,
        team_id: UUID | None = None,
        resolved_model_id: UUID | None = None,
        status: str | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[UsageEvent], int | None]:
        stmt = select(UsageEvent)
        if user_id:
            stmt = stmt.where(UsageEvent.user_id == user_id)
        if team_id:
            stmt = stmt.where(UsageEvent.team_id == team_id)
        if resolved_model_id:
            stmt = stmt.where(UsageEvent.resolved_model_id == resolved_model_id)
        if status:
            stmt = stmt.where(UsageEvent.request_status == status)
        if from_dt:
            stmt = stmt.where(UsageEvent.occurred_at >= from_dt)
        if to_dt:
            stmt = stmt.where(UsageEvent.occurred_at <= to_dt)
        stmt = (
            stmt.order_by(UsageEvent.occurred_at.desc())
            .limit(page_size + 1)
            .offset((page - 1) * page_size)
        )
        events = (await self.session.execute(stmt)).scalars().all()
        return paginate_window(events, page, page_size)


class UsageAggRepository(BaseRepository):
    async def get_daily(
        self,
        *,
        user_id: UUID | None = None,
        team_id: UUID | None = None,
        model_id: UUID | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[UsageDailyAgg]:
        stmt = select(UsageDailyAgg)
        if user_id:
            stmt = stmt.where(UsageDailyAgg.user_id == user_id)
        if team_id:
            stmt = stmt.where(UsageDailyAgg.team_id == team_id)
        if model_id:
            stmt = stmt.where(UsageDailyAgg.model_id == model_id)
        if from_date:
            stmt = stmt.where(UsageDailyAgg.agg_date >= from_date)
        if to_date:
            stmt = stmt.where(UsageDailyAgg.agg_date <= to_date)
        stmt = stmt.order_by(UsageDailyAgg.agg_date.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_monthly(
        self,
        *,
        user_id: UUID | None = None,
        team_id: UUID | None = None,
        model_id: UUID | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[UsageMonthlyAgg]:
        stmt = select(UsageMonthlyAgg)
        if user_id:
            stmt = stmt.where(UsageMonthlyAgg.user_id == user_id)
        if team_id:
            stmt = stmt.where(UsageMonthlyAgg.team_id == team_id)
        if model_id:
            stmt = stmt.where(UsageMonthlyAgg.model_id == model_id)
        if from_date:
            stmt = stmt.where(UsageMonthlyAgg.month_start >= from_date)
        if to_date:
            stmt = stmt.where(UsageMonthlyAgg.month_start <= to_date)
        stmt = stmt.order_by(UsageMonthlyAgg.month_start.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def upsert_daily(self, rows: list[UsageDailyAgg]) -> list[UsageDailyAgg]:
        for row in rows:
            self.session.add(row)
        await self.session.flush()
        return rows

    async def upsert_monthly(self, rows: list[UsageMonthlyAgg]) -> list[UsageMonthlyAgg]:
        for row in rows:
            self.session.add(row)
        await self.session.flush()
        return rows
