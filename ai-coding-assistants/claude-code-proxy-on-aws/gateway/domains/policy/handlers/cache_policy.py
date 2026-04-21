"""Cache policy resolver."""

from __future__ import annotations

from gateway.core.exceptions import InternalError
from gateway.domains.policy.context import PolicyContext
from gateway.domains.policy.engine import HandlerType


class CachePolicyHandler:
    handler_type = HandlerType.CACHE_POLICY

    async def handle(self, context: PolicyContext) -> None:
        if context.resolved_model is None:
            raise InternalError("Resolved model must be available for cache policy check")
        if not context.resolved_model.supports_prompt_cache:
            context.cache_policy = "none"
            context.cache_policy_source = "model-capability"
