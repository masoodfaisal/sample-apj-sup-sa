"""Admin request context."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdminRequestContext:
    principal: str
    request_id: str
