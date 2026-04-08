"""User repository."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select, true, update

from gateway.repositories.base import BaseRepository, paginate_window
from shared.models import TeamMembership, User
from shared.utils.constants import UserStatus

IDENTITY_STORE_BATCH_SIZE = 500


class UserRepository(BaseRepository):
    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def list_all(self) -> list[User]:
        stmt = select(User)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_identity_store_ids(
        self,
        identity_store_user_ids: Sequence[str],
    ) -> list[User]:
        unique_ids = list(dict.fromkeys(identity_store_user_ids))
        if not unique_ids:
            return []

        users: list[User] = []
        for start in range(0, len(unique_ids), IDENTITY_STORE_BATCH_SIZE):
            chunk = unique_ids[start : start + IDENTITY_STORE_BATCH_SIZE]
            stmt = select(User).where(User.identity_store_user_id.in_(chunk))
            users.extend((await self.session.execute(stmt)).scalars().all())
        return users

    async def mark_missing_inactive(
        self,
        seen_identity_store_user_ids: Sequence[str],
        *,
        synced_at: datetime,
    ) -> int:
        missing_filter = true()
        if seen_identity_store_user_ids:
            missing_filter = ~User.identity_store_user_id.in_(seen_identity_store_user_ids)

        update_required = or_(
            User.status != UserStatus.INACTIVE,
            User.source_deleted_at.is_(None),
        )
        changed_count = (
            await self.session.execute(
                select(func.count()).select_from(User).where(missing_filter, update_required)
            )
        ).scalar_one()

        stmt = (
            update(User)
            .where(missing_filter)
            .values(
                status=UserStatus.INACTIVE,
                source_deleted_at=func.coalesce(User.source_deleted_at, synced_at),
                last_synced_at=synced_at,
            )
            .execution_options(synchronize_session=False)
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return int(changed_count)

    async def get_by_ids(self, user_ids: list[UUID]) -> list[User]:
        if not user_ids:
            return []
        stmt = select(User).where(User.id.in_(user_ids))
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_identity_store_id(self, identity_store_user_id: str) -> User | None:
        stmt = select(User).where(User.identity_store_user_id == identity_store_user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_user_name(self, user_name: str) -> User | None:
        stmt = select(User).where(User.user_name == user_name)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list(
        self,
        *,
        status: str | None = None,
        team_id: UUID | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[User], int | None]:
        stmt = select(User)
        if team_id:
            stmt = stmt.join(TeamMembership, TeamMembership.user_id == User.id).where(
                TeamMembership.team_id == team_id
            )
        if status:
            stmt = stmt.where(User.status == status)
        if q:
            pattern = f"%{q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.user_name).like(pattern),
                    func.lower(func.coalesce(User.display_name, "")).like(pattern),
                    func.lower(func.coalesce(User.email, "")).like(pattern),
                )
            )
        stmt = (
            stmt.order_by(User.created_at.desc())
            .limit(page_size + 1)
            .offset((page - 1) * page_size)
        )
        users = (await self.session.execute(stmt)).scalars().unique().all()
        return paginate_window(users, page, page_size)

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def update(self, user: User, **changes: object) -> User:
        for key, value in changes.items():
            setattr(user, key, value)
        await self.session.flush()
        return user
