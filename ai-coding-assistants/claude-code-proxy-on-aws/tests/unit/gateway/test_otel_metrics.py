"""Unit tests for OTEL-backed MetricsService."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from gateway.core import telemetry
from gateway.domains.runtime.types import UsageInfo
from gateway.domains.usage.metrics import MetricsService


@pytest.fixture()
def metric_reader():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    set_meter_provider(provider)

    meter = provider.get_meter("com.anthropic.claude_code")
    telemetry.token_counter = meter.create_counter("claude_code.token.usage", unit="tokens")
    telemetry.cost_counter = meter.create_counter("claude_code.cost.usage", unit="USD")
    telemetry.request_counter = meter.create_counter("gateway.request.count")
    telemetry.latency_histogram = meter.create_histogram("gateway.request.duration", unit="ms")
    telemetry.throttle_counter = meter.create_counter("gateway.throttle.count")
    telemetry.policy_block_counter = meter.create_counter("gateway.policy_block.count")
    telemetry.active_requests = meter.create_up_down_counter("gateway.active_requests")
    telemetry.budget_utilization_gauge = meter.create_histogram(
        "gateway.budget.utilization",
        unit="percent",
    )
    telemetry.ttfb_histogram = meter.create_histogram("gateway.stream.ttfb", unit="ms")

    yield reader
    provider.shutdown()


def _make_context(
    *,
    model: str = "claude-sonnet-4-6",
    resolved_model: str | None = None,
    user_id: str | None = None,
    team_id: str | None = None,
    is_stream: bool = False,
    cache_policy: str = "5m",
):
    ctx = MagicMock()
    ctx.selected_model = model
    ctx.resolved_model = MagicMock()
    ctx.resolved_model.canonical_name = resolved_model or model
    ctx.resolved_model.bedrock_model_id = f"global.anthropic.{model}"
    ctx.is_stream = is_stream
    ctx.cache_policy = cache_policy

    if user_id:
        ctx.user = MagicMock()
        ctx.user.id = user_id
    else:
        ctx.user = None

    if team_id:
        ctx.team = MagicMock()
        ctx.team.id = team_id
    else:
        ctx.team = None

    return ctx


def _get_metrics(reader: InMemoryMetricReader) -> dict[str, list]:
    data = reader.get_metrics_data()
    if data is None:
        return {}
    result: dict[str, list] = {}
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                points = []
                for dp in metric.data.data_points:
                    value = getattr(dp, "value", None) or getattr(dp, "sum", None)
                    points.append({"value": value, "attributes": dict(dp.attributes)})
                result[metric.name] = points
    return result


class TestEmitTokenUsage:
    def test_records_all_token_types(self, metric_reader):
        svc = MetricsService()
        ctx = _make_context(user_id=str(uuid4()), team_id=str(uuid4()))
        usage = UsageInfo(
            input_tokens=100, output_tokens=50,
            cached_read_tokens=30, cached_write_tokens=10,
        )

        svc.emit_token_usage(ctx, usage)
        metrics = _get_metrics(metric_reader)

        token_points = metrics["claude_code.token.usage"]
        assert len(token_points) == 4
        by_type = {p["attributes"]["type"]: p["value"] for p in token_points}
        assert by_type["input"] == 100
        assert by_type["output"] == 50
        assert by_type["cacheRead"] == 30
        assert by_type["cacheCreation"] == 10


class TestEmitCostUsage:
    def test_records_cost(self, metric_reader):
        svc = MetricsService()
        ctx = _make_context(user_id=str(uuid4()))

        svc.emit_cost_usage(ctx, Decimal("0.0042"))
        metrics = _get_metrics(metric_reader)

        cost_points = metrics["claude_code.cost.usage"]
        assert len(cost_points) == 1
        assert abs(cost_points[0]["value"] - 0.0042) < 1e-6
        assert cost_points[0]["attributes"]["model"] == "claude-sonnet-4-6"
        assert cost_points[0]["attributes"]["selected_model"] == "claude-sonnet-4-6"
        assert cost_points[0]["attributes"]["resolved_model"] == "claude-sonnet-4-6"


class TestEmitRequestDuration:
    def test_records_latency(self, metric_reader):
        svc = MetricsService()
        ctx = _make_context()

        svc.emit_request_duration(ctx, 1234)
        metrics = _get_metrics(metric_reader)

        latency_points = metrics["gateway.request.duration"]
        assert len(latency_points) == 1
        assert latency_points[0]["value"] == 1234

    def test_skips_when_none(self, metric_reader):
        svc = MetricsService()
        ctx = _make_context()

        svc.emit_request_duration(ctx, None)
        metrics = _get_metrics(metric_reader)
        assert "gateway.request.duration" not in metrics


class TestEmitRequestCount:
    def test_records_success(self, metric_reader):
        svc = MetricsService()
        ctx = _make_context(user_id=str(uuid4()))

        svc.emit_request_count(ctx, "success")
        metrics = _get_metrics(metric_reader)

        count_points = metrics["gateway.request.count"]
        assert len(count_points) == 1
        assert count_points[0]["value"] == 1
        assert count_points[0]["attributes"]["status"] == "success"

    def test_records_error_status(self, metric_reader):
        svc = MetricsService()
        ctx = _make_context()

        svc.emit_request_count(ctx, "blocked_budget")
        svc.emit_request_count(ctx, "blocked_budget")
        metrics = _get_metrics(metric_reader)

        count_points = metrics["gateway.request.count"]
        assert count_points[0]["value"] == 2
        assert count_points[0]["attributes"]["status"] == "blocked_budget"


class TestCommonAttributes:
    def test_includes_model_user_team(self, metric_reader):
        svc = MetricsService()
        user_id = str(uuid4())
        team_id = str(uuid4())
        ctx = _make_context(
            model="claude-haiku-4-5-20251001",
            resolved_model="glm-5",
            user_id=user_id,
            team_id=team_id,
        )

        svc.emit_request_count(ctx, "success")
        metrics = _get_metrics(metric_reader)

        attrs = metrics["gateway.request.count"][0]["attributes"]
        assert attrs["model"] == "claude-haiku-4-5-20251001"
        assert attrs["selected_model"] == "claude-haiku-4-5-20251001"
        assert attrs["resolved_model"] == "glm-5"
        assert attrs["user.id"] == user_id
        assert attrs["team.id"] == team_id

    def test_unknown_when_context_missing(self, metric_reader):
        svc = MetricsService()
        ctx = _make_context()

        svc.emit_request_count(ctx, "success")
        metrics = _get_metrics(metric_reader)

        attrs = metrics["gateway.request.count"][0]["attributes"]
        assert attrs["selected_model"] == "claude-sonnet-4-6"
        assert attrs["resolved_model"] == "claude-sonnet-4-6"
        assert attrs["user.id"] == "unknown"
        assert attrs["team.id"] == "unknown"

    def test_includes_stream_and_cache_policy(self, metric_reader):
        svc = MetricsService()
        ctx = _make_context(is_stream=True, cache_policy="1h")

        svc.emit_request_count(ctx, "success")
        metrics = _get_metrics(metric_reader)

        attrs = metrics["gateway.request.count"][0]["attributes"]
        assert attrs["stream"] == "true"
        assert attrs["cache_policy"] == "1h"


class TestEmitThrottle:
    def test_records_throttle(self, metric_reader):
        svc = MetricsService()
        ctx = _make_context(model="claude-sonnet-4-6")

        svc.emit_throttle(ctx)
        svc.emit_throttle(ctx)
        metrics = _get_metrics(metric_reader)

        points = metrics["gateway.throttle.count"]
        assert points[0]["value"] == 2
        assert points[0]["attributes"]["model"] == "claude-sonnet-4-6"
        assert points[0]["attributes"]["selected_model"] == "claude-sonnet-4-6"
        assert points[0]["attributes"]["resolved_model"] == "claude-sonnet-4-6"


class TestEmitPolicyBlock:
    def test_records_block_reason(self, metric_reader):
        svc = MetricsService()
        ctx = _make_context()

        svc.emit_policy_block(ctx, "BudgetExceededError")
        metrics = _get_metrics(metric_reader)

        points = metrics["gateway.policy_block.count"]
        assert points[0]["value"] == 1
        assert points[0]["attributes"]["block_reason"] == "BudgetExceededError"


class TestEmitActiveRequests:
    def test_increment_decrement(self, metric_reader):
        svc = MetricsService()
        ctx = _make_context()

        svc.emit_active_request_start(ctx)
        svc.emit_active_request_start(ctx)
        svc.emit_active_request_end(ctx)
        metrics = _get_metrics(metric_reader)

        points = metrics["gateway.active_requests"]
        assert points[0]["value"] == 1  # 2 starts - 1 end = net 1


class TestEmitBudgetUtilization:
    def test_records_percentage(self, metric_reader):
        svc = MetricsService()
        budget = MagicMock()
        budget.id = uuid4()
        budget.scope_type = "TEAM"
        budget.period = "MONTHLY"
        budget.current_used_usd = Decimal("90")
        budget.hard_limit_usd = Decimal("100")

        svc.emit_budget_utilization(budget)
        metrics = _get_metrics(metric_reader)

        points = metrics["gateway.budget.utilization"]
        assert len(points) == 1
        assert abs(points[0]["value"] - 90.0) < 0.01
        assert points[0]["attributes"]["scope_type"] == "TEAM"
        assert points[0]["attributes"]["period"] == "MONTHLY"

    def test_skips_zero_limit(self, metric_reader):
        svc = MetricsService()
        budget = MagicMock()
        budget.hard_limit_usd = Decimal("0")

        svc.emit_budget_utilization(budget)
        metrics = _get_metrics(metric_reader)
        assert "gateway.budget.utilization" not in metrics


class TestEmitTTFB:
    def test_records_ttfb(self, metric_reader):
        svc = MetricsService()
        ctx = _make_context(is_stream=True)

        svc.emit_ttfb(ctx, 245.7)
        metrics = _get_metrics(metric_reader)

        points = metrics["gateway.stream.ttfb"]
        assert len(points) == 1
        assert abs(points[0]["value"] - 245.7) < 0.1
        assert points[0]["attributes"]["stream"] == "true"
