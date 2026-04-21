"""Usage and aggregate models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, BigInteger, Date, ForeignKey, Index, Numeric, Text, func, literal, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import TIMESTAMPTZ_SQL, UUID_SQL, Base, UUIDPrimaryKeyMixin
from shared.utils.constants import ZERO_UUID

if TYPE_CHECKING:
    from shared.models.model_catalog import ModelCatalog
    from shared.models.policy import BudgetPolicy
    from shared.models.team import Team
    from shared.models.user import User
    from shared.models.virtual_key import VirtualKey


class UsageEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "usage_events"

    request_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    team_id: Mapped[UUID | None] = mapped_column(
        UUID_SQL,
        ForeignKey("teams.id", ondelete="RESTRICT"),
    )
    virtual_key_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("virtual_keys.id", ondelete="RESTRICT"),
        nullable=False,
    )
    resolved_model_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("model_catalog.id", ondelete="RESTRICT"),
        nullable=False,
    )
    budget_policy_id: Mapped[UUID | None] = mapped_column(
        UUID_SQL,
        ForeignKey("budget_policies.id", ondelete="RESTRICT"),
    )
    selected_model: Mapped[str] = mapped_column(Text, nullable=False)
    request_status: Mapped[str] = mapped_column(Text, nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(Text)
    is_stream: Mapped[bool] = mapped_column(nullable=False)
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    cached_read_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    cached_write_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    cache_details_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        server_default=text("0"),
    )
    latency_ms: Mapped[int | None]
    bedrock_invocation_id: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ_SQL, nullable=False)

    user: Mapped["User"] = relationship(back_populates="usage_events")
    team: Mapped["Team | None"] = relationship(back_populates="usage_events")
    virtual_key: Mapped["VirtualKey"] = relationship(back_populates="usage_events")
    resolved_model: Mapped["ModelCatalog"] = relationship(back_populates="usage_events")
    budget_policy: Mapped["BudgetPolicy | None"] = relationship(back_populates="usage_events")

    __table_args__ = (
        Index("ix_usage_events_user_occurred_at", user_id, occurred_at.desc()),
        Index("ix_usage_events_team_occurred_at", team_id, occurred_at.desc()),
        Index("ix_usage_events_model_occurred_at", resolved_model_id, occurred_at.desc()),
        Index("ix_usage_events_status_occurred_at", request_status, occurred_at.desc()),
    )


class UsageDailyAgg(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "usage_daily_agg"

    agg_date: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    team_id: Mapped[UUID | None] = mapped_column(
        UUID_SQL,
        ForeignKey("teams.id", ondelete="RESTRICT"),
    )
    model_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("model_catalog.id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    success_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    blocked_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    error_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    cached_read_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    cached_write_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        server_default=text("0"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ_SQL,
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )

    user: Mapped["User"] = relationship()
    team: Mapped["Team | None"] = relationship()
    model: Mapped["ModelCatalog"] = relationship(back_populates="daily_aggregates")

    __table_args__ = (
        Index(
            "uq_usage_daily_agg_grain",
            agg_date,
            user_id,
            model_id,
            func.coalesce(team_id, literal(ZERO_UUID, type_=UUID_SQL)),
            unique=True,
        ),
    )


class UsageMonthlyAgg(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "usage_monthly_agg"

    month_start: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    team_id: Mapped[UUID | None] = mapped_column(
        UUID_SQL,
        ForeignKey("teams.id", ondelete="RESTRICT"),
    )
    model_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("model_catalog.id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    success_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    blocked_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    error_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    cached_read_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    cached_write_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        server_default=text("0"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ_SQL,
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )

    user: Mapped["User"] = relationship()
    team: Mapped["Team | None"] = relationship()
    model: Mapped["ModelCatalog"] = relationship(back_populates="monthly_aggregates")

    __table_args__ = (
        Index(
            "uq_usage_monthly_agg_grain",
            month_start,
            user_id,
            model_id,
            func.coalesce(team_id, literal(ZERO_UUID, type_=UUID_SQL)),
            unique=True,
        ),
    )
