"""Regression tests for daily and monthly budget window boundaries."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from gateway.domains.policy.handlers import user_budget as user_budget_module
from gateway.repositories.policy import _period_start


def test_period_start_handles_monthly_budget_on_31st_day() -> None:
    now = datetime(2026, 3, 31, 15, 45, tzinfo=timezone.utc)

    assert _period_start("MONTHLY", now) == datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)


def test_effective_spend_handles_monthly_budget_on_31st_day(monkeypatch) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 31, 15, 45, tzinfo=tz or timezone.utc)

    monkeypatch.setattr(user_budget_module, "datetime", FrozenDateTime)

    effective_spend = user_budget_module._effective_spend(
        Decimal("42"),
        "MONTHLY",
        datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
    )

    assert effective_spend == Decimal("42")
