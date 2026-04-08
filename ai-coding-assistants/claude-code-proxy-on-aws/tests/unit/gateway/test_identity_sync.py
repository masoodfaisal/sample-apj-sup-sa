"""Tests for Identity Center sync behavior."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from gateway.core.exceptions import GatewayError
from gateway.domains.sync.identity_store import IdentityStoreGateway, IdentityStoreUserRecord
from gateway.domains.sync.services import IdentitySyncService
from shared.models import AuditEvent, IdentitySyncRun, User
from shared.schemas import SyncRunTriggerResponse
from shared.utils.constants import SyncRunStatus, UserStatus


class SyncHarness(SimpleNamespace):
    @property
    def run(self) -> IdentitySyncRun:
        return self.state["run"]


@pytest.mark.asyncio
async def test_identity_store_gateway_collects_pages_and_normalizes_users() -> None:
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {
            "Users": [
                {
                    "UserId": "user-1",
                    "UserName": "alice",
                    "DisplayName": "Alice Example",
                    "Emails": [
                        {"Value": "secondary@example.com", "Primary": False},
                        {"Value": "alice@example.com", "Primary": True},
                    ],
                    "UserStatus": "ENABLED",
                }
            ]
        },
        {
            "Users": [
                {
                    "UserId": "user-2",
                    "Name": {"GivenName": "Bob", "FamilyName": "Example"},
                    "Emails": [{"Value": "bob@example.com", "Primary": False}],
                    "UserStatus": "DISABLED",
                },
                {
                    "UserId": "user-3",
                    "Name": {"Formatted": "Charlie Example"},
                    "UserStatus": "ENABLED",
                },
            ]
        },
    ]
    client = MagicMock()
    client.get_paginator.return_value = paginator

    gateway = IdentityStoreGateway(client, "d-1234567890")

    users = await gateway.list_users()

    assert users == [
        IdentityStoreUserRecord(
            user_id="user-1",
            user_name="alice",
            display_name="Alice Example",
            email="alice@example.com",
            status=UserStatus.ACTIVE,
        ),
        IdentityStoreUserRecord(
            user_id="user-2",
            user_name="bob@example.com",
            display_name="Bob Example",
            email="bob@example.com",
            status=UserStatus.INACTIVE,
        ),
        IdentityStoreUserRecord(
            user_id="user-3",
            user_name="user-3",
            display_name="Charlie Example",
            email=None,
            status=UserStatus.ACTIVE,
        ),
    ]
    paginator.paginate.assert_called_once_with(
        IdentityStoreId="d-1234567890",
        PaginationConfig={"PageSize": 100},
    )


@pytest.mark.asyncio
async def test_identity_store_gateway_rejects_placeholder_identity_store_id() -> None:
    gateway = IdentityStoreGateway(MagicMock(), "placeholder")

    with pytest.raises(GatewayError, match="Identity Store is not configured"):
        await gateway.list_users()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "expected_code", "expected_message", "retryable"),
    [
        (
            "AccessDeniedException",
            "identity_store_access_denied",
            "not authorized",
            False,
        ),
        (
            "ResourceNotFoundException",
            "identity_store_not_found",
            "was not found",
            False,
        ),
        (
            "ThrottlingException",
            "identity_store_throttled",
            "was throttled",
            True,
        ),
        (
            "InternalServerException",
            "identity_store_error",
            "request failed",
            True,
        ),
    ],
)
async def test_identity_store_gateway_translates_client_errors(
    error_code: str,
    expected_code: str,
    expected_message: str,
    retryable: bool,
) -> None:
    paginator = MagicMock()
    paginator.paginate.side_effect = ClientError(
        {"Error": {"Code": error_code, "Message": "boom"}},
        "ListUsers",
    )
    client = MagicMock()
    client.get_paginator.return_value = paginator

    gateway = IdentityStoreGateway(client, "d-1234567890")

    with pytest.raises(GatewayError, match=expected_message) as exc_info:
        await gateway.list_users()

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is retryable


@pytest.mark.asyncio
async def test_run_sync_creates_new_user() -> None:
    harness = build_sync_harness(
        existing_users=[],
        records=[
            make_record(
                user_id="user-1",
                user_name="alice",
                display_name="Alice Example",
                email="alice@example.com",
                status=UserStatus.ACTIVE,
            )
        ],
    )

    result = await harness.service.run_sync()

    created_user = harness.created_users[0]
    response = SyncRunTriggerResponse.model_validate(result)
    assert result["users_scanned"] == 1
    assert result["users_created"] == 1
    assert result["users_updated"] == 0
    assert result["users_inactivated"] == 0
    assert response.sync_scope == "USERS_ONLY"
    assert created_user.identity_store_user_id == "user-1"
    assert created_user.user_name == "alice"
    assert created_user.display_name == "Alice Example"
    assert created_user.email == "alice@example.com"
    assert created_user.status == UserStatus.ACTIVE
    assert created_user.source_deleted_at is None
    assert created_user.default_team_id is None
    assert created_user.last_login_at is None
    assert created_user.last_synced_at == harness.run.started_at


@pytest.mark.asyncio
async def test_run_sync_updates_existing_user_and_reactivates_soft_deleted_user() -> None:
    existing_user = make_user(
        identity_store_user_id="user-1",
        user_name="old-name",
        display_name="Old Name",
        email="old@example.com",
        status=UserStatus.INACTIVE,
        source_deleted_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    harness = build_sync_harness(
        existing_users=[existing_user],
        records=[
            make_record(
                user_id="user-1",
                user_name="alice",
                display_name="Alice Example",
                email="alice@example.com",
                status=UserStatus.ACTIVE,
            )
        ],
    )

    result = await harness.service.run_sync()

    assert result["users_created"] == 0
    assert result["users_updated"] == 1
    assert result["users_inactivated"] == 0
    assert existing_user.user_name == "alice"
    assert existing_user.display_name == "Alice Example"
    assert existing_user.email == "alice@example.com"
    assert existing_user.status == UserStatus.ACTIVE
    assert existing_user.source_deleted_at is None
    assert existing_user.last_synced_at == harness.run.started_at


@pytest.mark.asyncio
async def test_run_sync_refreshes_last_synced_at_without_counting_unchanged_user_as_updated(
) -> None:
    existing_user = make_user(identity_store_user_id="user-1")
    harness = build_sync_harness(
        existing_users=[existing_user],
        records=[
            make_record(
                user_id="user-1",
                user_name=existing_user.user_name,
                display_name=existing_user.display_name,
                email=existing_user.email,
                status=existing_user.status,
            )
        ],
    )

    result = await harness.service.run_sync()

    assert result["users_created"] == 0
    assert result["users_updated"] == 0
    assert result["users_inactivated"] == 0
    assert existing_user.last_synced_at == harness.run.started_at
    harness.user_repo.get_by_identity_store_ids.assert_awaited_once_with(["user-1"])
    harness.user_repo.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_sync_marks_missing_user_inactive_instead_of_deleting() -> None:
    missing_user = make_user(identity_store_user_id="user-1", status=UserStatus.ACTIVE)
    present_user = make_user(identity_store_user_id="user-2")
    harness = build_sync_harness(
        existing_users=[missing_user, present_user],
        records=[
            make_record(
                user_id="user-2",
                user_name=present_user.user_name,
                display_name=present_user.display_name,
                email=present_user.email,
                status=present_user.status,
            )
        ],
    )

    result = await harness.service.run_sync()

    assert result["users_created"] == 0
    assert result["users_updated"] == 0
    assert result["users_inactivated"] == 1
    assert missing_user.status == UserStatus.INACTIVE
    assert missing_user.source_deleted_at == harness.run.started_at
    assert missing_user.last_synced_at == harness.run.started_at
    assert missing_user in harness.existing_users
    harness.user_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_sync_preserves_existing_source_deleted_at_for_already_inactive_missing_user(
) -> None:
    deleted_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    missing_user = make_user(
        identity_store_user_id="user-1",
        status=UserStatus.INACTIVE,
        source_deleted_at=deleted_at,
    )
    harness = build_sync_harness(existing_users=[missing_user], records=[])

    result = await harness.service.run_sync()

    assert result["users_created"] == 0
    assert result["users_updated"] == 0
    assert result["users_inactivated"] == 0
    assert missing_user.status == UserStatus.INACTIVE
    assert missing_user.source_deleted_at == deleted_at
    assert missing_user.last_synced_at == harness.run.started_at


@pytest.mark.asyncio
async def test_run_sync_reports_mixed_counts_and_audit_payload() -> None:
    unchanged_user = make_user(identity_store_user_id="user-1")
    updated_user = make_user(
        identity_store_user_id="user-2",
        display_name="Old Display",
        email="old@example.com",
    )
    missing_user = make_user(identity_store_user_id="user-4", status=UserStatus.ACTIVE)
    harness = build_sync_harness(
        existing_users=[unchanged_user, updated_user, missing_user],
        records=[
            make_record(
                user_id="user-1",
                user_name=unchanged_user.user_name,
                display_name=unchanged_user.display_name,
                email=unchanged_user.email,
                status=unchanged_user.status,
            ),
            make_record(
                user_id="user-2",
                user_name="updated-user",
                display_name="Updated Display",
                email="updated@example.com",
                status=UserStatus.ACTIVE,
            ),
            make_record(
                user_id="user-3",
                user_name="new-user",
                display_name="New User",
                email="new@example.com",
                status=UserStatus.ACTIVE,
            ),
        ],
    )

    result = await harness.service.run_sync()

    audit_event = harness.audit_repo.create_event.await_args.args[0]
    assert isinstance(audit_event, AuditEvent)
    assert result["users_scanned"] == 3
    assert result["users_created"] == 1
    assert result["users_updated"] == 1
    assert result["users_inactivated"] == 1
    assert audit_event.sync_run_id == harness.run.id
    assert audit_event.payload_json == {
        "status": SyncRunStatus.SUCCEEDED,
        "users_scanned": 3,
        "users_created": 1,
        "users_updated": 1,
        "users_inactivated": 1,
    }


@pytest.mark.asyncio
async def test_run_sync_marks_run_failed_and_rolls_back_partial_changes() -> None:
    harness = build_sync_harness(
        existing_users=[],
        identity_store_error=GatewayError(
            "bad config",
            code="identity_store_not_configured",
            status_code=500,
        ),
    )

    with pytest.raises(GatewayError, match="bad config"):
        await harness.service.run_sync()

    assert harness.run.status == SyncRunStatus.FAILED
    assert harness.run.error_summary == "bad config"
    harness.session.rollback.assert_awaited_once()
    harness.sync_repo.update_run_by_id.assert_awaited_once()
    assert harness.session.commit.await_count == 2
    harness.audit_repo.create_event.assert_not_awaited()


def build_sync_harness(
    *,
    existing_users: list[User],
    records: list[IdentityStoreUserRecord] | None = None,
    identity_store_error: Exception | None = None,
):
    """Create a fully wired sync service with stateful fakes."""

    state: dict[str, IdentitySyncRun] = {}
    created_users: list[User] = []

    async def create_run(run: IdentitySyncRun) -> IdentitySyncRun:
        if run.id is None:
            run.id = uuid4()
        state["run"] = run
        return run

    async def get_by_id(_run_id) -> IdentitySyncRun | None:  # type: ignore[no-untyped-def]
        return state.get("run")

    async def update_run_by_id(_run_id, **changes: object) -> IdentitySyncRun | None:
        run = state.get("run")
        if run is None:
            return None
        return _apply_changes(run, changes)

    async def create_user(user: User) -> User:
        created_users.append(user)
        return user

    async def update_user(user: User, **changes: object) -> User:
        return _apply_changes(user, changes)

    async def get_users_by_identity_store_ids(identity_store_user_ids: list[str]) -> list[User]:
        seen_ids = set(identity_store_user_ids)
        return [user for user in existing_users if user.identity_store_user_id in seen_ids]

    async def mark_missing_inactive(
        seen_identity_store_user_ids: list[str],
        *,
        synced_at: datetime,
    ) -> int:
        seen_ids = set(seen_identity_store_user_ids)
        changed_count = 0
        for user in existing_users:
            if user.identity_store_user_id in seen_ids:
                continue

            if user.status != UserStatus.INACTIVE or user.source_deleted_at is None:
                changed_count += 1
            _apply_changes(
                user,
                {
                    "status": UserStatus.INACTIVE,
                    "source_deleted_at": user.source_deleted_at or synced_at,
                    "last_synced_at": synced_at,
                },
            )
        return changed_count

    sync_repo = SimpleNamespace(
        create_run=AsyncMock(side_effect=create_run),
        update_run=AsyncMock(side_effect=lambda obj, **changes: _apply_changes(obj, changes)),
        update_run_by_id=AsyncMock(side_effect=update_run_by_id),
        get_by_id=AsyncMock(side_effect=get_by_id),
    )
    user_repo = SimpleNamespace(
        list_all=AsyncMock(return_value=existing_users),
        get_by_identity_store_ids=AsyncMock(side_effect=get_users_by_identity_store_ids),
        mark_missing_inactive=AsyncMock(side_effect=mark_missing_inactive),
        create=AsyncMock(side_effect=create_user),
        update=AsyncMock(side_effect=update_user),
    )
    audit_repo = SimpleNamespace(create_event=AsyncMock())
    if identity_store_error is None:
        identity_store = SimpleNamespace(list_users=AsyncMock(return_value=records or []))
    else:
        identity_store = SimpleNamespace(list_users=AsyncMock(side_effect=identity_store_error))

    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    admin_ctx = SimpleNamespace(
        principal="arn:aws:iam::123456789012:user/admin",
        request_id="req-1",
    )
    service = IdentitySyncService(
        sync_repo,
        user_repo,
        audit_repo,
        identity_store,
        admin_ctx,
        session,
    )
    return SyncHarness(
        service=service,
        sync_repo=sync_repo,
        user_repo=user_repo,
        audit_repo=audit_repo,
        session=session,
        state=state,
        created_users=created_users,
        existing_users=existing_users,
    )


def make_record(
    *,
    user_id: str,
    user_name: str,
    display_name: str | None,
    email: str | None,
    status: UserStatus,
) -> IdentityStoreUserRecord:
    return IdentityStoreUserRecord(
        user_id=user_id,
        user_name=user_name,
        display_name=display_name,
        email=email,
        status=status,
    )


def make_user(
    *,
    identity_store_user_id: str,
    user_name: str = "alice",
    display_name: str | None = "Alice Example",
    email: str | None = "alice@example.com",
    status: UserStatus = UserStatus.ACTIVE,
    source_deleted_at: datetime | None = None,
    last_synced_at: datetime | None = None,
) -> User:
    return User(
        id=uuid4(),
        identity_store_user_id=identity_store_user_id,
        user_name=user_name,
        display_name=display_name,
        email=email,
        status=status,
        source_deleted_at=source_deleted_at,
        last_synced_at=last_synced_at,
        default_team_id=None,
        last_login_at=None,
    )


def _apply_changes(obj, changes):  # type: ignore[no-untyped-def]
    for key, value in changes.items():
        setattr(obj, key, value)
    return obj
