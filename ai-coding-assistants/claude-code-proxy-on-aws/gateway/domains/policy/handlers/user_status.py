"""User status handler."""

from __future__ import annotations

from gateway.core.exceptions import InternalError, UserInactiveError
from gateway.domains.policy.context import PolicyContext
from gateway.domains.policy.engine import HandlerType
from gateway.repositories import UserRepository
from shared.utils.constants import UserStatus


class UserStatusHandler:
    handler_type = HandlerType.USER_STATUS

    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    async def handle(self, context: PolicyContext) -> None:
        if context.virtual_key is None:
            raise InternalError("Virtual key must be resolved before user status check")
        user = await self._repo.get_by_id(context.virtual_key.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise UserInactiveError()
        context.user = user
