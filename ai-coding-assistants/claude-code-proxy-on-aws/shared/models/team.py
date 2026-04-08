"""Team model definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from shared.models.policy import BudgetPolicy, TeamModelPolicy
    from shared.models.usage import UsageEvent
    from shared.models.user import TeamMembership, User


class Team(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ACTIVE'"))

    team_memberships: Mapped[list["TeamMembership"]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
    )
    model_policies: Mapped[list["TeamModelPolicy"]] = relationship(back_populates="team")
    budget_policies: Mapped[list["BudgetPolicy"]] = relationship(
        back_populates="scope_team",
        foreign_keys="BudgetPolicy.scope_team_id",
    )
    usage_events: Mapped[list["UsageEvent"]] = relationship(back_populates="team")
    default_for_users: Mapped[list["User"]] = relationship(
        back_populates="default_team",
        foreign_keys="User.default_team_id",
    )

    __table_args__ = (Index("ix_teams_status", status),)
