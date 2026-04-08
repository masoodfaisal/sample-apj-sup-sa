"""Admin user endpoints and service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from gateway.core.dependencies import get_admin_user_service
from gateway.core.exceptions import NotFoundError, ValidationError
from shared.models import AuditEvent
from shared.schemas import UserResponse, UserUpdate

router = APIRouter(tags=["admin-users"])


class RuntimePolicyUpdate(BaseModel):
    allowed_models: list[str]
    cache_policy: str | None = None
    max_tokens_overrides: dict[str, int] | None = None


class AdminUserService:
    def __init__(
        self,
        user_repo,
        user_policy_repo,
        model_repo,
        audit_repo,
        admin_ctx,
        session,
    ) -> None:  # type: ignore[no-untyped-def]
        self._user_repo = user_repo
        self._user_policy_repo = user_policy_repo
        self._model_repo = model_repo
        self._audit_repo = audit_repo
        self._admin_ctx = admin_ctx
        self._session = session

    async def list_users(
        self, status: str | None, team_id: UUID | None, q: str | None, page: int, page_size: int
    ) -> dict[str, Any]:
        items, next_page = await self._user_repo.list(
            status=status,
            team_id=team_id,
            q=q,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [UserResponse.model_validate(item).model_dump() for item in items],
            "next_page": next_page,
        }

    async def get_user(self, user_id: UUID) -> UserResponse:
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found", code="user_not_found")
        return UserResponse.model_validate(user)

    async def update_user(self, user_id: UUID, payload: UserUpdate) -> UserResponse:
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found", code="user_not_found")
        updated = await self._user_repo.update(user, **payload.model_dump(exclude_unset=True))
        await self._audit_repo.create_event(
            AuditEvent(
                actor_type="IAM_PRINCIPAL",
                actor_id=self._admin_ctx.principal,
                event_type="USER_UPDATED",
                object_type="USER",
                object_id=str(user_id),
                request_id=self._admin_ctx.request_id,
                payload_json=payload.model_dump(mode="json", exclude_unset=True),
            )
        )
        await self._session.commit()
        return UserResponse.model_validate(updated)

    async def set_runtime_policy(
        self, user_id: UUID, payload: RuntimePolicyUpdate
    ) -> dict[str, Any]:
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found", code="user_not_found")
        models = await self._model_repo.get_by_canonical_names(payload.allowed_models)
        models_by_name = {m.canonical_name: m for m in models}
        model_ids: list[UUID] = []
        overrides: dict[UUID, int] = {}
        for name in payload.allowed_models:
            model = models_by_name.get(name)
            if model is None:
                raise ValidationError(f"Unknown model: {name}")
            model_ids.append(model.id)
            if payload.max_tokens_overrides and name in payload.max_tokens_overrides:
                overrides[model.id] = payload.max_tokens_overrides[name]
        await self._user_policy_repo.replace_policies(
            user_id,
            model_ids,
            cache_policy=payload.cache_policy,
            max_tokens_overrides=overrides,
        )
        await self._audit_repo.create_event(
            AuditEvent(
                actor_type="IAM_PRINCIPAL",
                actor_id=self._admin_ctx.principal,
                event_type="USER_RUNTIME_POLICY_SET",
                object_type="USER",
                object_id=str(user_id),
                request_id=self._admin_ctx.request_id,
                payload_json=payload.model_dump(mode="json"),
            )
        )
        await self._session.commit()
        return {"status": "ok", "request_id": self._admin_ctx.request_id}


@router.get("/users")
async def list_users(
    status: str | None = None,
    team_id: UUID | None = None,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    service=Depends(get_admin_user_service),  # type: ignore[assignment]
) -> dict[str, Any]:
    return await service.list_users(status, team_id, q, page, page_size)


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, service=Depends(get_admin_user_service)):  # type: ignore[assignment]
    return await service.get_user(user_id)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: UUID, payload: UserUpdate, service=Depends(get_admin_user_service)):  # type: ignore[assignment]
    return await service.update_user(user_id, payload)


@router.put("/users/{user_id}/runtime-policy")
async def set_runtime_policy(
    user_id: UUID,
    payload: RuntimePolicyUpdate,
    service=Depends(get_admin_user_service),  # type: ignore[assignment]
) -> dict[str, Any]:
    return await service.set_runtime_policy(user_id, payload)
