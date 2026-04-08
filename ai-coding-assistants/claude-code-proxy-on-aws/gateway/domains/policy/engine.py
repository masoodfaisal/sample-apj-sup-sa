"""Policy chain orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from gateway.domains.policy.context import PolicyContext


class HandlerType(StrEnum):
    """Policy handler type identifiers."""

    VIRTUAL_KEY = "virtual_key"
    USER_STATUS = "user_status"
    TEAM_STATUS = "team_status"
    MODEL_RESOLVER = "model_resolver"
    CACHE_POLICY = "cache_policy"
    USER_BUDGET = "user_budget"
    TEAM_BUDGET = "team_budget"
    USER_MODEL_POLICY = "user_model_policy"
    TEAM_MODEL_POLICY = "team_model_policy"
    MODEL_BUDGET = "model_budget"


class PolicyChain:
    """Sequential policy evaluation engine."""

    def __init__(self, handlers: Sequence[object]) -> None:
        self._handlers = list(handlers)

    async def evaluate(self, context: PolicyContext) -> PolicyContext:
        for handler in self._handlers:
            await handler.handle(context)
        return context

    def get_handler(self, handler_type: HandlerType) -> object | None:
        """Get handler by type identifier."""
        for handler in self._handlers:
            if getattr(handler, "handler_type", None) == handler_type:
                return handler
        return None

    def get_handlers_by_type(self, handler_types: list[HandlerType]) -> list[object]:
        """Get multiple handlers by type identifiers."""
        result = []
        for htype in handler_types:
            handler = self.get_handler(htype)
            if handler:
                result.append(handler)
        return result
