"""Audit and sync run models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import TIMESTAMPTZ_SQL, UUID_SQL, Base, UUIDPrimaryKeyMixin


class IdentitySyncRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "identity_sync_runs"

    started_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ_SQL, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ_SQL)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    users_scanned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    users_created: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    users_updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    users_inactivated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ_SQL,
        server_default=text("now()"),
        nullable=False,
    )

    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="sync_run")


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"

    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    object_type: Mapped[str] = mapped_column(Text, nullable=False)
    object_id: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(Text)
    sync_run_id: Mapped[UUID | None] = mapped_column(
        UUID_SQL,
        ForeignKey("identity_sync_runs.id", ondelete="SET NULL"),
    )
    payload_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ_SQL,
        server_default=text("now()"),
        nullable=False,
    )

    sync_run: Mapped["IdentitySyncRun | None"] = relationship(back_populates="audit_events")
