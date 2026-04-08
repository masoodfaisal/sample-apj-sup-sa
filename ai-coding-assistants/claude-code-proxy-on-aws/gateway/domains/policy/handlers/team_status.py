"""Team status handler."""

from __future__ import annotations

from gateway.core.exceptions import InternalError, TeamInactiveError
from gateway.domains.policy.context import PolicyContext
from gateway.domains.policy.engine import HandlerType
from gateway.repositories import TeamRepository
from shared.utils.constants import TeamStatus


class TeamStatusHandler:
    handler_type = HandlerType.TEAM_STATUS

    def __init__(self, repo: TeamRepository) -> None:
        self._repo = repo

    async def handle(self, context: PolicyContext) -> None:
        if context.user is None:
            raise InternalError("User must be resolved before team status check")
        if context.user.default_team_id is None:
            return
        team = await self._repo.get_by_id(context.user.default_team_id)
        if team is None or team.status != TeamStatus.ACTIVE:
            raise TeamInactiveError()
        context.team = team
