"""OTEL-backed metrics service."""

from __future__ import annotations

import logging
from decimal import Decimal

from gateway.core import telemetry
from gateway.domains.runtime.types import UsageInfo

logger = logging.getLogger(__name__)


class MetricsService:
    """Emit metrics via OpenTelemetry instruments."""

    # ------------------------------------------------------------------
    # Attribute helpers
    # ------------------------------------------------------------------

    def _common_attributes(self, context) -> dict[str, str]:  # type: ignore[no-untyped-def]
        resolved_model_name = "unknown"
        if context.resolved_model:
            resolved_model_name = (
                getattr(context.resolved_model, "canonical_name", None)
                or getattr(context.resolved_model, "bedrock_model_id", None)
                or "unknown"
            )
        return {
            # Retained for backward compatibility with existing dashboards.
            "model": context.selected_model if context.resolved_model else "unknown",
            "selected_model": context.selected_model if context.resolved_model else "unknown",
            "resolved_model": resolved_model_name,
            "user.id": str(context.user.id) if context.user else "unknown",
            "team.id": str(context.team.id) if context.team else "unknown",
            "stream": str(context.is_stream).lower(),
            "cache_policy": context.cache_policy,
        }

    def emit_token_usage(self, context, usage: UsageInfo) -> None:  # type: ignore[no-untyped-def]
        attrs = self._common_attributes(context)
        telemetry.token_counter.add(usage.input_tokens, {**attrs, "type": "input"})
        telemetry.token_counter.add(usage.output_tokens, {**attrs, "type": "output"})
        telemetry.token_counter.add(usage.cached_read_tokens, {**attrs, "type": "cacheRead"})
        telemetry.token_counter.add(usage.cached_write_tokens, {**attrs, "type": "cacheCreation"})

    def emit_cost_usage(self, context, cost: Decimal) -> None:  # type: ignore[no-untyped-def]
        attrs = self._common_attributes(context)
        telemetry.cost_counter.add(float(cost), attrs)

    def emit_request_duration(self, context, latency_ms: int | None) -> None:  # type: ignore[no-untyped-def]
        if latency_ms is None:
            return
        attrs = self._common_attributes(context)
        telemetry.latency_histogram.record(latency_ms, attrs)

    def emit_request_count(self, context, status: str) -> None:  # type: ignore[no-untyped-def]
        attrs = self._common_attributes(context)
        attrs["status"] = status
        telemetry.request_counter.add(1, attrs)

    def emit_throttle(self, context) -> None:  # type: ignore[no-untyped-def]
        attrs = self._common_attributes(context)
        telemetry.throttle_counter.add(1, attrs)

    def emit_policy_block(self, context, block_reason: str) -> None:  # type: ignore[no-untyped-def]
        attrs = self._common_attributes(context)
        attrs["block_reason"] = block_reason
        telemetry.policy_block_counter.add(1, attrs)

    def emit_active_request_start(self, context) -> None:  # type: ignore[no-untyped-def]
        attrs = self._common_attributes(context)
        telemetry.active_requests.add(1, attrs)

    def emit_active_request_end(self, context) -> None:  # type: ignore[no-untyped-def]
        attrs = self._common_attributes(context)
        telemetry.active_requests.add(-1, attrs)

    def emit_budget_utilization(self, budget) -> None:  # type: ignore[no-untyped-def]
        if budget.hard_limit_usd <= 0:
            return
        pct = float(budget.current_used_usd / budget.hard_limit_usd * 100)
        attrs = {
            "scope_type": budget.scope_type,
            "period": budget.period,
            "budget.id": str(budget.id),
        }
        telemetry.budget_utilization_gauge.record(pct, attrs)

    def emit_ttfb(self, context, ttfb_ms: float) -> None:  # type: ignore[no-untyped-def]
        attrs = self._common_attributes(context)
        telemetry.ttfb_histogram.record(ttfb_ms, attrs)
