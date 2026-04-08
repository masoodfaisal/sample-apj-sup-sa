"""Team repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from gateway.repositories.base import BaseRepository, paginate_window
from shared.models import Team


class TeamRepository(BaseRepository):
    async def get_by_id(self, team_id: UUID) -> Team | None:
        return await self.session.get(Team, team_id)

    async def get_by_name(self, name: str) -> Team | None:
        stmt = select(Team).where(Team.name == name)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list(self, *, page: int = 1, page_size: int = 100) -> tuple[list[Team], int | None]:
        stmt = (
            select(Team)
            .order_by(Team.created_at.desc())
            .limit(page_size + 1)
            .offset((page - 1) * page_size)
        )
        teams = (await self.session.execute(stmt)).scalars().all()
        return paginate_window(teams, page, page_size)

    async def create(self, team: Team) -> Team:
        self.session.add(team)
        await self.session.flush()
        return team

    async def update(self, team: Team, **changes: object) -> Team:
        for key, value in changes.items():
            setattr(team, key, value)
        await self.session.flush()
        return team
