"""Admin usage endpoints and service."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from gateway.core.dependencies import get_admin_usage_service
from shared.schemas import DailyAggResponse, MonthlyAggResponse, UsageEventResponse

router = APIRouter(tags=["admin-usage"])


class AdminUsageService:
    def __init__(self, event_repo, agg_repo, rollup_service) -> None:  # type: ignore[no-untyped-def]
        self._event_repo = event_repo
        self._agg_repo = agg_repo
        self._rollup_service = rollup_service

    async def list_events(
        self,
        user_id: UUID | None,
        team_id: UUID | None,
        resolved_model_id: UUID | None,
        status: str | None,
        from_dt: datetime | None,
        to_dt: datetime | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        items, next_page = await self._event_repo.list_events(
            user_id=user_id,
            team_id=team_id,
            resolved_model_id=resolved_model_id,
            status=status,
            from_dt=from_dt,
            to_dt=to_dt,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [UsageEventResponse.model_validate(item).model_dump() for item in items],
            "next_page": next_page,
        }

    async def get_aggregates(
        self,
        period: str,
        user_id: UUID | None,
        team_id: UUID | None,
        model_id: UUID | None,
        from_date: date | None,
        to_date: date | None,
    ) -> dict[str, Any]:
        if period == "monthly":
            items = await self._agg_repo.get_monthly(
                user_id=user_id,
                team_id=team_id,
                model_id=model_id,
                from_date=from_date,
                to_date=to_date,
            )
            payload = [MonthlyAggResponse.model_validate(item).model_dump() for item in items]
        else:
            items = await self._agg_repo.get_daily(
                user_id=user_id,
                team_id=team_id,
                model_id=model_id,
                from_date=from_date,
                to_date=to_date,
            )
            payload = [DailyAggResponse.model_validate(item).model_dump() for item in items]
        return {"period": period, "items": payload}

    async def trigger_rollup(self) -> dict[str, str]:
        return await self._rollup_service.trigger_rollup()


@router.get("/usage/events")
async def list_usage_events(
    user_id: UUID | None = None,
    team_id: UUID | None = None,
    resolved_model_id: UUID | None = None,
    status: str | None = None,
    from_dt: datetime | None = Query(default=None, alias="from"),
    to_dt: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    service=Depends(get_admin_usage_service),  # type: ignore[assignment]
) -> dict[str, Any]:
    return await service.list_events(
        user_id, team_id, resolved_model_id, status, from_dt, to_dt, page, page_size
    )


@router.get("/usage/aggregates")
async def get_usage_aggregates(
    period: str = "daily",
    user_id: UUID | None = None,
    team_id: UUID | None = None,
    model_id: UUID | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    service=Depends(get_admin_usage_service),  # type: ignore[assignment]
) -> dict[str, Any]:
    return await service.get_aggregates(period, user_id, team_id, model_id, from_date, to_date)
