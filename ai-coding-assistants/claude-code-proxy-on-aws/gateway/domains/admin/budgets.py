"""Admin budget endpoints and service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from gateway.core.dependencies import get_admin_budget_service
from gateway.core.exceptions import NotFoundError
from shared.models import AuditEvent, BudgetPolicy
from shared.schemas import BudgetPolicyCreate, BudgetPolicyResponse, BudgetPolicyUpdate
from shared.utils.constants import (
    AuditActorType,
    AuditEventType,
    AuditObjectType,
    BudgetPeriod,
    ScopeType,
)

router = APIRouter(tags=["admin-budgets"])


class AdminBudgetService:
    def __init__(
        self, budget_repo, usage_agg_repo, audit_repo, admin_ctx, session
    ) -> None:  # type: ignore[no-untyped-def]
        self._budget_repo = budget_repo
        self._usage_agg_repo = usage_agg_repo
        self._audit_repo = audit_repo
        self._admin_ctx = admin_ctx
        self._session = session

    async def list_budgets(
        self,
        scope_type: ScopeType | None,
        scope_id: UUID | None,
        period: BudgetPeriod | None,
        model_id: UUID | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        items, next_page = await self._budget_repo.list(
            scope_type=scope_type,
            scope_id=scope_id,
            period=period,
            model_id=model_id,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [BudgetPolicyResponse.model_validate(item).model_dump() for item in items],
            "next_page": next_page,
        }

    async def create_budget(self, payload: BudgetPolicyCreate) -> BudgetPolicyResponse:
        budget = await self._budget_repo.create(
            BudgetPolicy(
                **payload.model_dump(exclude_none=True),
                window_started_at=datetime.now(timezone.utc),
            )
        )
        await self._audit_repo.create_event(
            AuditEvent(
                actor_type=AuditActorType.IAM_PRINCIPAL,
                actor_id=self._admin_ctx.principal,
                event_type=AuditEventType.BUDGET_CREATED,
                object_type=AuditObjectType.BUDGET_POLICY,
                object_id=str(budget.id),
                request_id=self._admin_ctx.request_id,
                payload_json=payload.model_dump(mode="json", exclude_none=True),
            )
        )
        await self._session.commit()
        return BudgetPolicyResponse.model_validate(budget)

    async def update_budget(
        self, budget_id: UUID, payload: BudgetPolicyUpdate
    ) -> BudgetPolicyResponse:
        budget = await self._budget_repo.get_by_id(budget_id)
        if budget is None:
            raise NotFoundError("Budget not found", code="budget_not_found")
        updated = await self._budget_repo.update(budget, **payload.model_dump(exclude_unset=True))
        await self._audit_repo.create_event(
            AuditEvent(
                actor_type=AuditActorType.IAM_PRINCIPAL,
                actor_id=self._admin_ctx.principal,
                event_type=AuditEventType.BUDGET_UPDATED,
                object_type=AuditObjectType.BUDGET_POLICY,
                object_id=str(budget_id),
                request_id=self._admin_ctx.request_id,
                payload_json=payload.model_dump(mode="json", exclude_unset=True),
            )
        )
        await self._session.commit()
        return BudgetPolicyResponse.model_validate(updated)

    async def get_budget_status(
        self,
        scope_type: ScopeType,
        scope_id: UUID,
        period: BudgetPeriod,
        model_id: UUID | None,
    ) -> dict[str, Any]:
        items, _ = await self._budget_repo.list(
            scope_type=scope_type,
            scope_id=scope_id,
            period=period,
            model_id=model_id,
            page=1,
            page_size=1,
        )
        policy = items[0] if items else None
        daily = await self._usage_agg_repo.get_daily(
            user_id=scope_id if scope_type == ScopeType.USER else None,
            team_id=scope_id if scope_type == ScopeType.TEAM else None,
            model_id=model_id,
        )
        estimated_cost = sum((item.estimated_cost_usd for item in daily), start=0)
        remaining_soft = (policy.soft_limit_usd - estimated_cost) if policy else None
        remaining_hard = (policy.hard_limit_usd - estimated_cost) if policy else None
        return {
            "scope_type": scope_type,
            "scope_id": str(scope_id),
            "period": period,
            "model_id": str(model_id) if model_id else None,
            "policy": BudgetPolicyResponse.model_validate(policy).model_dump() if policy else None,
            "usage": {"estimated_cost_usd": estimated_cost},
            "remaining": {"soft_limit_usd": remaining_soft, "hard_limit_usd": remaining_hard},
            "status": "WITHIN_LIMIT",
        }


@router.get("/budgets")
async def list_budgets(
    scope_type: str | None = None,
    scope_id: UUID | None = None,
    period: str | None = None,
    model_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    service=Depends(get_admin_budget_service),  # type: ignore[assignment]
) -> dict[str, Any]:
    return await service.list_budgets(scope_type, scope_id, period, model_id, page, page_size)


@router.post("/budgets", response_model=BudgetPolicyResponse)
async def create_budget(payload: BudgetPolicyCreate, service=Depends(get_admin_budget_service)):  # type: ignore[assignment]
    return await service.create_budget(payload)


@router.patch("/budgets/{budget_id}", response_model=BudgetPolicyResponse)
async def update_budget(
    budget_id: UUID,
    payload: BudgetPolicyUpdate,
    service=Depends(get_admin_budget_service),  # type: ignore[assignment]
) -> BudgetPolicyResponse:
    return await service.update_budget(budget_id, payload)


@router.get("/budget-status")
async def get_budget_status(
    scope_type: str,
    scope_id: UUID,
    period: str,
    model_id: UUID | None = None,
    service=Depends(get_admin_budget_service),  # type: ignore[assignment]
) -> dict[str, Any]:
    return await service.get_budget_status(scope_type, scope_id, period, model_id)
