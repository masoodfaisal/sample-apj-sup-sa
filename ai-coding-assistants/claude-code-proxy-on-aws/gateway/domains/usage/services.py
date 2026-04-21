"""Usage and cost recording."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from gateway.core.exceptions import (
    BudgetExceededError,
    InternalError,
    ModelNotAllowedError,
    TeamInactiveError,
    UserInactiveError,
)
from gateway.domains.runtime.types import UsageInfo
from shared.models import UsageEvent
from shared.utils.constants import RequestStatus

logger = logging.getLogger(__name__)
TOKENS_PER_PRICING_UNIT = Decimal("1000")


class UsageService:
    """Persist usage events and emit best-effort metrics."""

    def __init__(self, pricing_repo, budget_repo, event_repo, metrics, session) -> None:  # type: ignore[no-untyped-def]
        self._pricing_repo = pricing_repo
        self._budget_repo = budget_repo
        self._event_repo = event_repo
        self._metrics = metrics
        self._session = session

    async def record_success(self, context, usage_info: UsageInfo) -> UsageEvent | None:  # type: ignore[no-untyped-def]
        if context.resolved_model is None or context.user is None or context.virtual_key is None:
            raise InternalError("Missing runtime context for usage persistence")
        pricing = await self._pricing_repo.get_active_pricing(context.resolved_model.id)
        if pricing is None:
            raise InternalError("Active pricing is required for successful usage recording")
        cost = self._calculate_cost(usage_info, pricing, context.cache_policy)
        await self._budget_repo.apply_costs(context.applicable_budgets, cost)
        for budget in context.applicable_budgets:
            refreshed = await self._budget_repo.get_by_id(budget.id)
            if refreshed:
                self._metrics.emit_budget_utilization(refreshed)
        event = await self._event_repo.create_event(
            UsageEvent(
                request_id=context.request_id,
                user_id=context.user.id,
                team_id=context.team.id if context.team else None,
                virtual_key_id=context.virtual_key.id,
                resolved_model_id=context.resolved_model.id,
                budget_policy_id=context.applicable_budgets[0].id
                if context.applicable_budgets
                else None,
                selected_model=context.selected_model,
                request_status=RequestStatus.SUCCESS,
                stop_reason=usage_info.stop_reason,
                is_stream=context.is_stream,
                input_tokens=usage_info.input_tokens,
                output_tokens=usage_info.output_tokens,
                total_tokens=usage_info.total_tokens,
                cached_read_tokens=usage_info.cached_read_tokens,
                cached_write_tokens=usage_info.cached_write_tokens,
                cache_details_json=usage_info.cache_details,
                estimated_cost_usd=cost,
                latency_ms=usage_info.latency_ms,
                bedrock_invocation_id=usage_info.bedrock_invocation_id,
                trace_id=None,
                occurred_at=datetime.now(timezone.utc),
            )
        )
        await self._session.commit()
        logger.info(
            "runtime request completed request_id=%s selected_model=%s resolved_model=%s user_id=%s cache_read_input_tokens=%s cache_creation_input_tokens=%s",
            context.request_id,
            context.selected_model,
            context.resolved_model.bedrock_model_id,
            str(context.user.id),
            usage_info.cached_read_tokens,
            usage_info.cached_write_tokens,
        )
        self._metrics.emit_token_usage(context, usage_info)
        self._metrics.emit_cost_usage(context, cost)
        self._metrics.emit_request_duration(context, usage_info.latency_ms)
        self._metrics.emit_request_count(context, "success")
        return event

    async def record_blocked_request(self, context, error) -> UsageEvent | None:  # type: ignore[no-untyped-def]
        self._metrics.emit_request_count(context, self._status_for_error(error))
        if not self._can_persist(context):
            return None
        event = await self._event_repo.create_event(
            self._build_error_event(context, error, UsageInfo())
        )
        await self._session.commit()
        return event

    async def record_error(
        self, context, error, usage_info: UsageInfo | None = None
    ) -> UsageEvent | None:  # type: ignore[no-untyped-def]
        self._metrics.emit_request_count(context, self._status_for_error(error))
        if not self._can_persist(context):
            return None
        event = await self._event_repo.create_event(
            self._build_error_event(context, error, usage_info or UsageInfo())
        )
        await self._session.commit()
        return event

    def _can_persist(self, context) -> bool:  # type: ignore[no-untyped-def]
        return bool(context.user and context.virtual_key and context.resolved_model)

    def _build_error_event(self, context, error, usage_info: UsageInfo) -> UsageEvent:  # type: ignore[no-untyped-def]
        return UsageEvent(
            request_id=context.request_id,
            user_id=context.user.id,
            team_id=context.team.id if context.team else None,
            virtual_key_id=context.virtual_key.id,
            resolved_model_id=context.resolved_model.id,
            budget_policy_id=context.applicable_budgets[0].id
            if context.applicable_budgets
            else None,
            selected_model=context.selected_model,
            request_status=self._status_for_error(error),
            stop_reason=usage_info.stop_reason,
            is_stream=context.is_stream,
            input_tokens=usage_info.input_tokens,
            output_tokens=usage_info.output_tokens,
            total_tokens=usage_info.total_tokens,
            cached_read_tokens=usage_info.cached_read_tokens,
            cached_write_tokens=usage_info.cached_write_tokens,
            cache_details_json=usage_info.cache_details,
            estimated_cost_usd=Decimal("0"),
            latency_ms=usage_info.latency_ms,
            bedrock_invocation_id=usage_info.bedrock_invocation_id,
            trace_id=None,
            occurred_at=datetime.now(timezone.utc),
        )

    def _status_for_error(self, error) -> str:  # type: ignore[no-untyped-def]
        if isinstance(error, BudgetExceededError):
            return RequestStatus.BLOCKED_BUDGET
        if isinstance(error, ModelNotAllowedError):
            return RequestStatus.BLOCKED_MODEL_POLICY
        if isinstance(error, UserInactiveError):
            return RequestStatus.BLOCKED_USER_INACTIVE
        if isinstance(error, TeamInactiveError):
            return RequestStatus.BLOCKED_TEAM_INACTIVE
        return RequestStatus.ERROR_INTERNAL

    def _calculate_cost(self, usage_info: UsageInfo, pricing, cache_policy: str) -> Decimal:  # type: ignore[no-untyped-def]
        input_cost = (
            Decimal(usage_info.input_tokens) * pricing.input_price_per_1k / TOKENS_PER_PRICING_UNIT
        )
        output_cost = (
            Decimal(usage_info.output_tokens)
            * pricing.output_price_per_1k
            / TOKENS_PER_PRICING_UNIT
        )
        cache_read_cost = (
            Decimal(usage_info.cached_read_tokens)
            * pricing.cache_read_price_per_1k
            / TOKENS_PER_PRICING_UNIT
        )
        cache_write_price = pricing.cache_write_5m_price_per_1k
        if cache_policy == "1h":
            cache_write_price = pricing.cache_write_1h_price_per_1k
        cache_write_cost = (
            Decimal(usage_info.cached_write_tokens) * cache_write_price / TOKENS_PER_PRICING_UNIT
        )
        return input_cost + output_cost + cache_read_cost + cache_write_cost
