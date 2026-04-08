"""Virtual key model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, LargeBinary, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import TIMESTAMPTZ_SQL, UUID_SQL, Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from shared.models.usage import UsageEvent
    from shared.models.user import User


class VirtualKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "virtual_keys"

    user_id: Mapped[UUID] = mapped_column(
        UUID_SQL,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    key_fingerprint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    key_last4: Mapped[str] = mapped_column(Text, nullable=False)
    kms_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ACTIVE'"))
    issued_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ_SQL, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ_SQL)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ_SQL)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ_SQL)

    user: Mapped["User"] = relationship(back_populates="virtual_keys")
    usage_events: Mapped[list["UsageEvent"]] = relationship(back_populates="virtual_key")

    __table_args__ = (
        Index(
            "uq_virtual_keys_active_user",
            user_id,
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )
