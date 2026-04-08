"""OpenTelemetry MeterProvider initialization and instrument registry."""

from __future__ import annotations

import logging

from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import Counter, Histogram, UpDownCounter, set_meter_provider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

logger = logging.getLogger(__name__)

_meter_provider: MeterProvider | None = None

# --- Instruments (populated by init_meter_provider) ---
token_counter: Counter
cost_counter: Counter
request_counter: Counter
latency_histogram: Histogram
throttle_counter: Counter
policy_block_counter: Counter
active_requests: UpDownCounter
budget_utilization_gauge: Histogram
ttfb_histogram: Histogram


def init_meter_provider(otlp_endpoint: str, export_interval_millis: int = 60_000) -> None:
    """Initialize MeterProvider with OTLP gRPC exporter targeting the ADOT sidecar."""
    global _meter_provider
    global token_counter, cost_counter, request_counter, latency_histogram
    global throttle_counter, policy_block_counter, active_requests
    global budget_utilization_gauge, ttfb_histogram

    readers = []
    if otlp_endpoint:
        exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
        readers.append(
            PeriodicExportingMetricReader(
                exporter,
                export_interval_millis=export_interval_millis,
            )
        )
    else:
        logger.info("OTEL metrics export disabled because OTLP_GRPC_ENDPOINT is empty")

    _meter_provider = MeterProvider(metric_readers=readers)
    set_meter_provider(_meter_provider)

    meter = _meter_provider.get_meter("com.anthropic.claude_code")

    token_counter = meter.create_counter(
        name="claude_code.token.usage",
        unit="tokens",
        description="Tokens consumed per request",
    )
    cost_counter = meter.create_counter(
        name="claude_code.cost.usage",
        unit="USD",
        description="Estimated cost per request",
    )
    request_counter = meter.create_counter(
        name="gateway.request.count",
        description="Total gateway requests",
    )
    latency_histogram = meter.create_histogram(
        name="gateway.request.duration",
        unit="ms",
        description="End-to-end Bedrock call latency",
    )

    throttle_counter = meter.create_counter(
        name="gateway.throttle.count",
        description="Bedrock throttling events",
    )
    policy_block_counter = meter.create_counter(
        name="gateway.policy_block.count",
        description="Requests blocked by policy engine",
    )
    active_requests = meter.create_up_down_counter(
        name="gateway.active_requests",
        description="In-flight requests currently being processed",
    )
    budget_utilization_gauge = meter.create_histogram(
        name="gateway.budget.utilization",
        unit="percent",
        description="Budget spend as percentage of hard limit (0-100+)",
    )
    ttfb_histogram = meter.create_histogram(
        name="gateway.stream.ttfb",
        unit="ms",
        description="Time to first byte for streaming responses",
    )

    logger.info(
        "OTEL MeterProvider initialized, endpoint=%s export_interval_millis=%s",
        otlp_endpoint,
        export_interval_millis,
    )


def shutdown_meter_provider() -> None:
    """Flush and shut down the MeterProvider."""
    if _meter_provider is not None:
        _meter_provider.shutdown()
