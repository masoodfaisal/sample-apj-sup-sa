"""Tests for shared enums and constants."""

from shared.utils.constants import (
    ZERO_UUID,
    BudgetPeriod,
    CachePolicy,
    MembershipRole,
    MembershipSource,
    ModelStatus,
    RequestStatus,
    ScopeType,
    SyncRunStatus,
    TeamStatus,
    UserStatus,
    VirtualKeyStatus,
)


def test_expected_enum_values() -> None:
    assert UserStatus.ACTIVE.value == "ACTIVE"
    assert TeamStatus.INACTIVE.value == "INACTIVE"
    assert VirtualKeyStatus.ROTATED.value == "ROTATED"
    assert ModelStatus.ACTIVE.value == "ACTIVE"
    assert ScopeType.TEAM.value == "TEAM"
    assert BudgetPeriod.MONTHLY.value == "MONTHLY"
    assert RequestStatus.ERROR_INTERNAL.value == "ERROR_INTERNAL"
    assert SyncRunStatus.SUCCEEDED.value == "SUCCEEDED"
    assert CachePolicy.ONE_HOUR.value == "1h"
    assert MembershipSource.ADMIN.value == "ADMIN"
    assert MembershipRole.MEMBER.value == "MEMBER"


def test_zero_uuid_constant() -> None:
    assert str(ZERO_UUID) == "00000000-0000-0000-0000-000000000000"
