"""User and team membership models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import TIMESTAMPTZ_SQL, UUID_SQL, Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from shared.models.policy import BudgetPolicy, UserModelPolicy
    from shared.models.team import Team
    from shared.models.usage import UsageEvent
    from shared.models.virtual_key import VirtualKey


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    identity_store_user_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    user_name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'INACTIVE'"))
    source_deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ_SQL, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ_SQL, nullable=True)
    default_team_id: Mapped[UUID | None] = mapped_column(
        UUID_SQL,
        ForeignKey("teams.id", ondelete="SET NULL"),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ_SQL, nullable=True)

    team_memberships: Mapped[list["TeamMembership"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    virtual_keys: Mapped[list["VirtualKey"]] = relationship(back_populates="user")
    model_policies: Mapped[list["UserModelPolicy"]] = relationship(back_populates="user")
    budget_policies: Mapped[list["BudgetPolicy"]] = relationship(
        back_populates="scope_user",
        foreign_keys="BudgetPolicy.scope_user_id",
    )
    usage_events: Mapped[list["UsageEvent"]] = relationship(back_populates="user")
    default_team: Mapped["Team | None"] = relationship(
        back_populates="default_for_users",
        foreign_keys=[default_team_id],
    )

    __table_args__ = (
        Index("ix_users_status", status),
        Index("ix_users_last_synced_at", last_synced_at.desc()),
        Index("ix_users_last_login_at", last_login_at.desc()),
    )


class TeamMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "team_memberships"

    user_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ADMIN'"))
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'MEMBER'"))

    user: Mapped["User"] = relationship(back_populates="team_memberships")
    team: Mapped["Team"] = relationship(back_populates="team_memberships")

    __table_args__ = (
        UniqueConstraint("user_id", "team_id", name="uq_team_memberships_user_team"),
    )
