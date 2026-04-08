"""Base SQLAlchemy model definitions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, Uuid, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

UUID_SQL = Uuid(as_uuid=True)
TIMESTAMPTZ_SQL = DateTime(timezone=True)


class Base(DeclarativeBase):
    """Declarative base with a deterministic naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Shared created/updated timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ_SQL,
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ_SQL,
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """Shared UUID primary key."""

    id: Mapped[UUID] = mapped_column(UUID_SQL, primary_key=True, default=uuid4)
