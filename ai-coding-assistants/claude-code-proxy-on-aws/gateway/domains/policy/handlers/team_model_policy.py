"""Team model policy handler."""

from __future__ import annotations

from gateway.core.exceptions import InternalError, ModelNotAllowedError
from gateway.domains.policy.context import PolicyContext
from gateway.domains.policy.engine import HandlerType
from gateway.repositories import TeamModelPolicyRepository


class TeamModelPolicyHandler:
    handler_type = HandlerType.TEAM_MODEL_POLICY

    def __init__(self, repo: TeamModelPolicyRepository) -> None:
        self._repo = repo

    async def handle(self, context: PolicyContext) -> None:
        if context.resolved_model is None:
            raise InternalError("Resolved model must be available for team policy check")
        if context.team is None or context.max_tokens_override is not None:
            return
        policy = await self._repo.get_policy(context.team.id, context.resolved_model.id)
        if policy is None:
            return
        if not policy.allow:
            raise ModelNotAllowedError()
        if policy.cache_policy is not None:
            context.cache_policy = policy.cache_policy
            context.cache_policy_source = "team"
        context.max_tokens_override = policy.max_tokens_override
