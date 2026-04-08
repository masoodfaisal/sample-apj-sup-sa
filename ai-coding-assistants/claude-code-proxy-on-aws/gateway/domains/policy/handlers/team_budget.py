"""Team budget pre-check handler."""

from __future__ import annotations

from gateway.core.exceptions import BudgetExceededError
from gateway.domains.policy.context import BudgetWarning, PolicyContext
from gateway.domains.policy.engine import HandlerType
from gateway.domains.policy.handlers.user_budget import _effective_spend
from gateway.repositories import BudgetPolicyRepository


class TeamBudgetPreCheckHandler:
    handler_type = HandlerType.TEAM_BUDGET

    def __init__(self, repo: BudgetPolicyRepository) -> None:
        self._repo = repo

    async def handle(self, context: PolicyContext) -> None:
        if context.team is None:
            return
        budgets = await self._repo.get_scope_policies(scope_type="TEAM", scope_id=context.team.id)
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
                    BudgetWarning("TEAM", budget.period, "Soft budget limit exceeded")
                )
        context.applicable_budgets.extend(budgets)
