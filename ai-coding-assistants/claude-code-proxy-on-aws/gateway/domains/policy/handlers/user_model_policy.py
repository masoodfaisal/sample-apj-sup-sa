"""User model policy handler."""

from __future__ import annotations

from gateway.core.exceptions import InternalError, ModelNotAllowedError
from gateway.domains.policy.context import PolicyContext
from gateway.domains.policy.engine import HandlerType
from gateway.repositories import UserModelPolicyRepository


class UserModelPolicyHandler:
    handler_type = HandlerType.USER_MODEL_POLICY

    def __init__(self, repo: UserModelPolicyRepository) -> None:
        self._repo = repo

    async def handle(self, context: PolicyContext) -> None:
        if context.user is None or context.resolved_model is None:
            raise InternalError("User and resolved model must be available for user policy check")
        policy = await self._repo.get_policy(context.user.id, context.resolved_model.id)
        if policy is None:
            return
        if not policy.allow:
            raise ModelNotAllowedError()
        if policy.cache_policy is not None:
            context.cache_policy = policy.cache_policy
            context.cache_policy_source = "user"
        context.max_tokens_override = policy.max_tokens_override
