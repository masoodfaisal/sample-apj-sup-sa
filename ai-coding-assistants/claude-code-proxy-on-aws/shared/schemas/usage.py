"""Usage DTOs."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.utils.constants import RequestStatus


class UsageEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: str
    user_id: UUID
    team_id: UUID | None
    virtual_key_id: UUID
    resolved_model_id: UUID
    budget_policy_id: UUID | None
    selected_model: str
    request_status: RequestStatus
    stop_reason: str | None
    is_stream: bool
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_read_tokens: int
    cached_write_tokens: int
    cache_details_json: dict[str, object] | None
    estimated_cost_usd: Decimal
    latency_ms: int | None
    bedrock_invocation_id: str | None
    trace_id: str | None
    occurred_at: datetime


class DailyAggResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agg_date: date
    user_id: UUID
    team_id: UUID | None
    model_id: UUID
    request_count: int
    success_count: int
    blocked_count: int
    error_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_read_tokens: int
    cached_write_tokens: int
    estimated_cost_usd: Decimal
    updated_at: datetime


class MonthlyAggResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    month_start: date
    user_id: UUID
    team_id: UUID | None
    model_id: UUID
    request_count: int
    success_count: int
    blocked_count: int
    error_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_read_tokens: int
    cached_write_tokens: int
    estimated_cost_usd: Decimal
    updated_at: datetime
