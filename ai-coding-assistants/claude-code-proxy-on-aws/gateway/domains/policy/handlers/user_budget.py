"""User budget pre-check handler."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from gateway.core.exceptions import BudgetExceededError, InternalError
from gateway.domains.policy.context import BudgetWarning, PolicyContext
from gateway.domains.policy.engine import HandlerType
from gateway.repositories import BudgetPolicyRepository


def _effective_spend(
    current_used_usd: Decimal, period: str, window_started_at: datetime
) -> Decimal:
    now = datetime.now(timezone.utc)
    if period == "DAILY":
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return Decimal("0") if window_started_at < period_start else current_used_usd


class UserBudgetPreCheckHandler:
    handler_type = HandlerType.USER_BUDGET

    def __init__(self, repo: BudgetPolicyRepository) -> None:
        self._repo = repo

    async def handle(self, context: PolicyContext) -> None:
        if context.user is None:
            raise InternalError("User must be resolved before budget pre-check")
        budgets = await self._repo.get_scope_policies(scope_type="USER", scope_id=context.user.id)
        for budget in budgets:
            effective_spend = _effective_spend(
                budget.current_used_usd,
                budget.period,
                budget.window_started_at,
            )
            if effective_spend >= budget.hard_limit_usd:
                raise BudgetExceededError()
            if effective_spend >= budget.soft_limit_usd:
                context.warnings.append(
                    BudgetWarning("USER", budget.period, "Soft budget limit exceeded")
                )
        context.applicable_budgets.extend(budgets)
