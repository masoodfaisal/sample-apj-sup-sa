"""Usage rollup service."""

from __future__ import annotations


class UsageRollupService:
    """Placeholder manual rollup service for admin-triggered aggregation."""

    def __init__(self, usage_agg_repo) -> None:  # type: ignore[no-untyped-def]
        self._usage_agg_repo = usage_agg_repo

    async def trigger_rollup(self) -> dict[str, str]:
        return {"status": "STARTED"}
