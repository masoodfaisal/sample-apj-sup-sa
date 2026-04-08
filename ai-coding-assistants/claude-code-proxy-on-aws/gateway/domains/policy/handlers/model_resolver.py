"""Model resolution handler."""

from __future__ import annotations

from gateway.core.exceptions import ValidationError
from gateway.domains.policy.context import PolicyContext
from gateway.domains.policy.engine import HandlerType
from gateway.repositories import ModelAliasMappingRepository

class ModelResolverHandler:
    handler_type = HandlerType.MODEL_RESOLVER

    def __init__(self, repo: ModelAliasMappingRepository) -> None:
        self._repo = repo

    async def handle(self, context: PolicyContext) -> None:
        mapping = await self._repo.resolve_mapping(context.selected_model)
        if mapping is None:
            raise ValidationError("No model mapping matched the selected model")
        context.resolved_model = mapping.target_model
