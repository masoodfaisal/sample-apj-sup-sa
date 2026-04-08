"""Team membership repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from gateway.repositories.base import BaseRepository, paginate_window
from shared.models import TeamMembership


class TeamMembershipRepository(BaseRepository):
    async def get_by_user_and_team(self, user_id: UUID, team_id: UUID) -> TeamMembership | None:
        stmt = select(TeamMembership).where(
            TeamMembership.user_id == user_id,
            TeamMembership.team_id == team_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_default_team(self, user_id: UUID) -> TeamMembership | None:
        stmt = select(TeamMembership).where(TeamMembership.user_id == user_id).limit(1)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_by_team(
        self,
        team_id: UUID,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[TeamMembership], int | None]:
        stmt = (
            select(TeamMembership)
            .where(TeamMembership.team_id == team_id)
            .order_by(TeamMembership.created_at.desc())
            .limit(page_size + 1)
            .offset((page - 1) * page_size)
        )
        memberships = (await self.session.execute(stmt)).scalars().all()
        return paginate_window(memberships, page, page_size)

    async def add_member(self, membership: TeamMembership) -> TeamMembership:
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def remove_member(self, membership: TeamMembership) -> None:
        await self.session.delete(membership)
        await self.session.flush()
