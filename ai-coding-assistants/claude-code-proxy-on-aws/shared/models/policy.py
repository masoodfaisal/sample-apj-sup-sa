"""Policy model definitions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    literal,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import TIMESTAMPTZ_SQL, UUID_SQL, Base, TimestampMixin, UUIDPrimaryKeyMixin
from shared.utils.constants import ZERO_UUID

if TYPE_CHECKING:
    from shared.models.model_catalog import ModelCatalog
    from shared.models.team import Team
    from shared.models.usage import UsageEvent
    from shared.models.user import User


class UserModelPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_model_policies"

    user_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("model_catalog.id", ondelete="CASCADE"),
        nullable=False,
    )
    allow: Mapped[bool] = mapped_column(nullable=False)
    cache_policy: Mapped[str | None] = mapped_column(Text)
    max_tokens_override: Mapped[int | None]

    user: Mapped["User"] = relationship(back_populates="model_policies")
    model: Mapped["ModelCatalog"] = relationship(back_populates="user_policies")

    __table_args__ = (UniqueConstraint("user_id", "model_id", name="uq_user_model_policies_pair"),)


class TeamModelPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "team_model_policies"

    team_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("model_catalog.id", ondelete="CASCADE"),
        nullable=False,
    )
    allow: Mapped[bool] = mapped_column(nullable=False)
    cache_policy: Mapped[str | None] = mapped_column(Text)
    max_tokens_override: Mapped[int | None]

    team: Mapped["Team"] = relationship(back_populates="model_policies")
    model: Mapped["ModelCatalog"] = relationship(back_populates="team_policies")

    __table_args__ = (UniqueConstraint("team_id", "model_id", name="uq_team_model_policies_pair"),)


class BudgetPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "budget_policies"

    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_user_id: Mapped[UUID | None] = mapped_column(
        UUID_SQL,
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    scope_team_id: Mapped[UUID | None] = mapped_column(
        UUID_SQL,
        ForeignKey("teams.id", ondelete="RESTRICT"),
    )
    model_id: Mapped[UUID | None] = mapped_column(
        UUID_SQL,
        ForeignKey("model_catalog.id", ondelete="RESTRICT"),
    )
    period: Mapped[str] = mapped_column(Text, nullable=False)
    soft_limit_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    hard_limit_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    current_used_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        server_default=text("0"),
    )
    window_started_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ_SQL, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'USD'"))
    active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))

    scope_user: Mapped["User | None"] = relationship(
        back_populates="budget_policies",
        foreign_keys=[scope_user_id],
    )
    scope_team: Mapped["Team | None"] = relationship(
        back_populates="budget_policies",
        foreign_keys=[scope_team_id],
    )
    model: Mapped["ModelCatalog | None"] = relationship(back_populates="budget_policies")
    usage_events: Mapped[list["UsageEvent"]] = relationship(back_populates="budget_policy")

    __table_args__ = (
        CheckConstraint(
            "("
            "(scope_type = 'USER' AND scope_user_id IS NOT NULL AND scope_team_id IS NULL)"
            " OR "
            "(scope_type = 'TEAM' AND scope_team_id IS NOT NULL AND scope_user_id IS NULL)"
            ")",
            name="scope_xor",
        ),
        CheckConstraint("soft_limit_usd <= hard_limit_usd", name="budget_limit_order"),
        Index(
            "ix_budget_policies_scope_lookup",
            scope_type,
            scope_user_id,
            scope_team_id,
            period,
            active,
        ),
        Index("ix_budget_policies_window_started_at", window_started_at),
        Index(
            "uq_budget_policies_user_active",
            scope_user_id,
            period,
            func.coalesce(model_id, literal(ZERO_UUID, type_=UUID_SQL)),
            unique=True,
            postgresql_where=text("scope_type = 'USER' AND active = true"),
        ),
        Index(
            "uq_budget_policies_team_active",
            scope_team_id,
            period,
            func.coalesce(model_id, literal(ZERO_UUID, type_=UUID_SQL)),
            unique=True,
            postgresql_where=text("scope_type = 'TEAM' AND active = true"),
        ),
    )
