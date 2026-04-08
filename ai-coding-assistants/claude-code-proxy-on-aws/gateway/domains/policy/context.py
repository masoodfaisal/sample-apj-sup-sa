"""Policy evaluation context objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gateway.domains.runtime.types import MessageRequest
from shared.models import BudgetPolicy, ModelCatalog, Team, User, VirtualKey


@dataclass(slots=True)
class BudgetWarning:
    """Soft-limit warning emitted during policy evaluation."""

    scope_type: str
    period: str
    message: str


@dataclass(slots=True)
class PolicyContext:
    """Request-scoped policy evaluation state."""

    api_key: str
    request_id: str
    request: MessageRequest
    virtual_key: VirtualKey | None = None
    user: User | None = None
    team: Team | None = None
    resolved_model: ModelCatalog | None = None
    cache_policy: str = "5m"
    cache_policy_source: str = "default"
    max_tokens_override: int | None = None
    applicable_budgets: list[BudgetPolicy] = field(default_factory=list)
    warnings: list[BudgetWarning] = field(default_factory=list)

    @property
    def is_stream(self) -> bool:
        return self.request.stream

    @property
    def selected_model(self) -> str:
        return self.request.model

    def metadata(self) -> dict[str, Any]:
        return {"warnings": [warning.__dict__ for warning in self.warnings]}
