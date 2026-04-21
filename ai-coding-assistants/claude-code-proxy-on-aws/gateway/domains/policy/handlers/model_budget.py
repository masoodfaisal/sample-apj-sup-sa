"""Model-specific budget pre-check handler."""

from __future__ import annotations

from gateway.core.exceptions import BudgetExceededError, InternalError
from gateway.domains.policy.context import BudgetWarning, PolicyContext
from gateway.domains.policy.engine import HandlerType
from gateway.domains.policy.handlers.user_budget import _effective_spend
from gateway.repositories import BudgetPolicyRepository


class ModelBudgetPreCheckHandler:
    handler_type = HandlerType.MODEL_BUDGET

    def __init__(self, repo: BudgetPolicyRepository) -> None:
        self._repo = repo

    async def handle(self, context: PolicyContext) -> None:
        if context.resolved_model is None or context.user is None:
            raise InternalError("User and resolved model must be available for model budget check")
        budgets = await self._repo.get_scope_policies(
            scope_type="USER",
            scope_id=context.user.id,
            model_id=context.resolved_model.id,
        )
        if context.team is not None:
            budgets.extend(
                await self._repo.get_scope_policies(
                    scope_type="TEAM",
                    scope_id=context.team.id,
                    model_id=context.resolved_model.id,
                )
            )
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
                    BudgetWarning(
                        budget.scope_type, budget.period, "Soft model budget limit exceeded"
                    )
                )
        context.applicable_budgets.extend(budgets)
