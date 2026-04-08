"""Runtime policy repositories."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from gateway.repositories.base import BaseRepository, paginate_window
from shared.models import BudgetPolicy, TeamModelPolicy, UserModelPolicy

from gateway.core.exceptions import BudgetExceededError


def _period_start(period: str, now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if period == "DAILY":
        return current.replace(hour=0, minute=0, second=0, microsecond=0)
    return current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class UserModelPolicyRepository(BaseRepository):
    async def get_policy(self, user_id: UUID, model_id: UUID) -> UserModelPolicy | None:
        stmt = select(UserModelPolicy).where(
            UserModelPolicy.user_id == user_id,
            UserModelPolicy.model_id == model_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def replace_policies(
        self,
        user_id: UUID,
        model_ids: list[UUID],
        *,
        cache_policy: str | None,
        max_tokens_overrides: dict[UUID, int] | None = None,
    ) -> list[UserModelPolicy]:
        stmt = select(UserModelPolicy).where(UserModelPolicy.user_id == user_id)
        existing = list((await self.session.execute(stmt)).scalars().all())
        for policy in existing:
            await self.session.delete(policy)
        policies: list[UserModelPolicy] = []
        for model_id in model_ids:
            policy = UserModelPolicy(
                user_id=user_id,
                model_id=model_id,
                allow=True,
                cache_policy=cache_policy,
                max_tokens_override=(max_tokens_overrides or {}).get(model_id),
            )
            self.session.add(policy)
            policies.append(policy)
        await self.session.flush()
        return policies


class TeamModelPolicyRepository(BaseRepository):
    async def get_policy(self, team_id: UUID, model_id: UUID) -> TeamModelPolicy | None:
        stmt = select(TeamModelPolicy).where(
            TeamModelPolicy.team_id == team_id,
            TeamModelPolicy.model_id == model_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def replace_policies(
        self,
        team_id: UUID,
        model_ids: list[UUID],
        *,
        cache_policy: str | None,
        max_tokens_overrides: dict[UUID, int] | None = None,
    ) -> list[TeamModelPolicy]:
        stmt = select(TeamModelPolicy).where(TeamModelPolicy.team_id == team_id)
        existing = list((await self.session.execute(stmt)).scalars().all())
        for policy in existing:
            await self.session.delete(policy)
        policies: list[TeamModelPolicy] = []
        for model_id in model_ids:
            policy = TeamModelPolicy(
                team_id=team_id,
                model_id=model_id,
                allow=True,
                cache_policy=cache_policy,
                max_tokens_override=(max_tokens_overrides or {}).get(model_id),
            )
            self.session.add(policy)
            policies.append(policy)
        await self.session.flush()
        return policies


class BudgetPolicyRepository(BaseRepository):
    async def get_by_id(self, budget_id: UUID) -> BudgetPolicy | None:
        return await self.session.get(BudgetPolicy, budget_id)

    async def list(
        self,
        *,
        scope_type: str | None = None,
        scope_id: UUID | None = None,
        period: str | None = None,
        model_id: UUID | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[BudgetPolicy], int | None]:
        stmt = select(BudgetPolicy).where(BudgetPolicy.active.is_(True))
        if scope_type:
            stmt = stmt.where(BudgetPolicy.scope_type == scope_type)
            if scope_type == "USER" and scope_id:
                stmt = stmt.where(BudgetPolicy.scope_user_id == scope_id)
            if scope_type == "TEAM" and scope_id:
                stmt = stmt.where(BudgetPolicy.scope_team_id == scope_id)
        if period:
            stmt = stmt.where(BudgetPolicy.period == period)
        if model_id is not None:
            stmt = stmt.where(BudgetPolicy.model_id == model_id)
        stmt = (
            stmt.order_by(BudgetPolicy.created_at.desc())
            .limit(page_size + 1)
            .offset((page - 1) * page_size)
        )
        budgets = (await self.session.execute(stmt)).scalars().all()
        return paginate_window(budgets, page, page_size)

    async def get_scope_policies(
        self,
        *,
        scope_type: str,
        scope_id: UUID,
        model_id: UUID | None = None,
    ) -> list[BudgetPolicy]:
        stmt = select(BudgetPolicy).where(
            BudgetPolicy.scope_type == scope_type, BudgetPolicy.active.is_(True)
        )
        if scope_type == "USER":
            stmt = stmt.where(BudgetPolicy.scope_user_id == scope_id)
        else:
            stmt = stmt.where(BudgetPolicy.scope_team_id == scope_id)
        if model_id is None:
            stmt = stmt.where(BudgetPolicy.model_id.is_(None))
        else:
            stmt = stmt.where(BudgetPolicy.model_id == model_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def create(self, budget: BudgetPolicy) -> BudgetPolicy:
        self.session.add(budget)
        await self.session.flush()
        return budget

    async def update(self, budget: BudgetPolicy, **changes: object) -> BudgetPolicy:
        for key, value in changes.items():
            setattr(budget, key, value)
        await self.session.flush()
        return budget

    async def apply_costs(
        self, budgets: list[BudgetPolicy], cost: Decimal
    ) -> list[BudgetPolicy]:
        from sqlalchemy import case, update

        now = datetime.now(timezone.utc)

        for budget in budgets:
            period_start = _period_start(budget.period, now)
            # Atomic UPDATE: reset window if stale, add cost, enforce hard limit
            new_spend = case(
                (BudgetPolicy.window_started_at < period_start, cost),
                else_=BudgetPolicy.current_used_usd + cost,
            )
            new_window = case(
                (BudgetPolicy.window_started_at < period_start, period_start),
                else_=BudgetPolicy.window_started_at,
            )
            stmt = (
                update(BudgetPolicy)
                .where(
                    BudgetPolicy.id == budget.id,
                    # Guard: only apply if spend + cost <= hard_limit
                    case(
                        (BudgetPolicy.window_started_at < period_start, cost),
                        else_=BudgetPolicy.current_used_usd + cost,
                    )
                    <= BudgetPolicy.hard_limit_usd,
                )
                .values(current_used_usd=new_spend, window_started_at=new_window)
                .execution_options(synchronize_session=False)
            )
            result = await self.session.execute(stmt)
            if result.rowcount == 0:
                # Row not updated = budget would be exceeded
                raise BudgetExceededError()

        return budgets
