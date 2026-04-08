"""Identity sync service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from gateway.core.exceptions import GatewayError, NotFoundError
from shared.models import AuditEvent, IdentitySyncRun, User
from shared.utils.constants import (
    AuditActorType,
    AuditEventType,
    AuditObjectType,
    SyncRunStatus,
)


class IdentitySyncService:
    """Manual identity sync workflow."""

    def __init__(
        self,
        sync_repo,
        user_repo,
        audit_repo,
        identity_store,
        admin_ctx,
        session,
    ) -> None:  # type: ignore[no-untyped-def]
        self._sync_repo = sync_repo
        self._user_repo = user_repo
        self._audit_repo = audit_repo
        self._identity_store = identity_store
        self._admin_ctx = admin_ctx
        self._session = session

    async def run_sync(self) -> dict[str, Any]:
        started_at = datetime.now(timezone.utc)
        run = await self._sync_repo.create_run(
            IdentitySyncRun(
                started_at=started_at,
                finished_at=None,
                status=SyncRunStatus.STARTED,
                users_scanned=0,
                users_created=0,
                users_updated=0,
                users_inactivated=0,
                error_summary=None,
            )
        )
        await self._session.commit()

        try:
            records = await self._identity_store.list_users()
            counts = await self._sync_users(records, synced_at=started_at)
        except Exception as exc:
            await self._session.rollback()
            persisted_run = await self._sync_repo.update_run_by_id(
                run.id,
                status=SyncRunStatus.FAILED,
                finished_at=datetime.now(timezone.utc),
                error_summary=str(exc),
            )
            if persisted_run is None:
                raise GatewayError(
                    f"Sync run {run.id} could not be marked as failed",
                    code="identity_sync_run_state_error",
                    status_code=500,
                ) from exc
            await self._session.commit()
            raise

        await self._sync_repo.update_run(
            run,
            status=SyncRunStatus.SUCCEEDED,
            finished_at=datetime.now(timezone.utc),
            error_summary=None,
            **counts,
        )
        await self._audit_repo.create_event(
            AuditEvent(
                actor_type=AuditActorType.IAM_PRINCIPAL,
                actor_id=self._admin_ctx.principal,
                event_type=AuditEventType.IDENTITY_SYNC_TRIGGERED,
                object_type=AuditObjectType.IDENTITY_SYNC_RUN,
                object_id=str(run.id),
                request_id=self._admin_ctx.request_id,
                sync_run_id=run.id,
                payload_json={"status": SyncRunStatus.SUCCEEDED, **counts},
            )
        )
        await self._session.commit()
        return {
            "sync_run_id": str(run.id),
            "status": SyncRunStatus.SUCCEEDED,
            "sync_scope": "USERS_ONLY",
            **counts,
        }

    async def get_sync_status(self, run_id) -> IdentitySyncRun:  # type: ignore[no-untyped-def]
        run = await self._sync_repo.get_by_id(run_id)
        if run is None:
            raise NotFoundError("Sync run not found", code="sync_run_not_found")
        return run

    async def _sync_users(self, records, *, synced_at: datetime) -> dict[str, int]:  # type: ignore[no-untyped-def]
        seen_ids = [record.user_id for record in records]
        existing_users = await self._user_repo.get_by_identity_store_ids(seen_ids)
        existing_by_identity_id = {
            user.identity_store_user_id: user for user in existing_users
        }
        users_created = 0
        users_updated = 0

        for record in records:
            user = existing_by_identity_id.get(record.user_id)
            if user is None:
                await self._user_repo.create(
                    User(
                        identity_store_user_id=record.user_id,
                        user_name=record.user_name,
                        display_name=record.display_name,
                        email=record.email,
                        status=record.status,
                        source_deleted_at=None,
                        last_synced_at=synced_at,
                        default_team_id=None,
                        last_login_at=None,
                    )
                )
                users_created += 1
                continue

            update_payload = {
                "user_name": record.user_name,
                "display_name": record.display_name,
                "email": record.email,
                "status": record.status,
                "source_deleted_at": None,
                "last_synced_at": synced_at,
            }
            if _user_requires_update(user, update_payload):
                users_updated += 1
            await self._user_repo.update(user, **update_payload)

        users_inactivated = await self._user_repo.mark_missing_inactive(
            seen_ids,
            synced_at=synced_at,
        )

        return {
            "users_scanned": len(records),
            "users_created": users_created,
            "users_updated": users_updated,
            "users_inactivated": users_inactivated,
        }


def _user_requires_update(user: User, changes: dict[str, object]) -> bool:
    return any(
        getattr(user, field) != value
        for field, value in changes.items()
        if field != "last_synced_at"
    )
