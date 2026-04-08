"""Admin team endpoints and service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from gateway.core.dependencies import get_admin_team_service
from gateway.core.exceptions import ConflictError, NotFoundError, ValidationError
from shared.models import AuditEvent, Team, TeamMembership
from shared.schemas import TeamCreate, TeamResponse, TeamUpdate, UserResponse
from shared.utils.constants import AuditActorType, AuditEventType, AuditObjectType

router = APIRouter(tags=["admin-teams"])


class TeamRuntimePolicyUpdate(BaseModel):
    allowed_models: list[str]
    cache_policy: str | None = None
    max_tokens_overrides: dict[str, int] | None = None


class TeamMemberCreate(BaseModel):
    user_id: UUID
    role: str = "MEMBER"
    is_default: bool = False


class AdminTeamService:
    def __init__(
        self,
        team_repo,
        membership_repo,
        user_repo,
        team_policy_repo,
        model_repo,
        audit_repo,
        admin_ctx,
        session,
    ) -> None:  # type: ignore[no-untyped-def]
        self._team_repo = team_repo
        self._membership_repo = membership_repo
        self._user_repo = user_repo
        self._team_policy_repo = team_policy_repo
        self._model_repo = model_repo
        self._audit_repo = audit_repo
        self._admin_ctx = admin_ctx
        self._session = session

    async def list_teams(self, page: int, page_size: int) -> dict[str, Any]:
        items, next_page = await self._team_repo.list(page=page, page_size=page_size)
        return {
            "items": [TeamResponse.model_validate(item).model_dump() for item in items],
            "next_page": next_page,
        }

    async def get_team(self, team_id: UUID) -> dict[str, Any]:
        team = await self._team_repo.get_by_id(team_id)
        if team is None:
            raise NotFoundError("Team not found", code="team_not_found")
        members, _ = await self._membership_repo.list_by_team(team_id, page=1, page_size=1000)
        user_ids = [m.user_id for m in members]
        users_list = await self._user_repo.get_by_ids(user_ids)
        users_by_id = {u.id: u for u in users_list}
        users = [
            UserResponse.model_validate(users_by_id[m.user_id]).model_dump()
            for m in members
            if m.user_id in users_by_id
        ]
        return {"team": TeamResponse.model_validate(team).model_dump(), "members": users}

    async def create_team(self, payload: TeamCreate) -> TeamResponse:
        if await self._team_repo.get_by_name(payload.name):
            raise ConflictError("Team already exists", code="team_exists")
        team = await self._team_repo.create(Team(**payload.model_dump()))
        await self._audit_repo.create_event(
            AuditEvent(
                actor_type=AuditActorType.IAM_PRINCIPAL,
                actor_id=self._admin_ctx.principal,
                event_type=AuditEventType.TEAM_CREATED,
                object_type=AuditObjectType.TEAM,
                object_id=str(team.id),
                request_id=self._admin_ctx.request_id,
                payload_json=payload.model_dump(mode="json"),
            )
        )
        await self._session.commit()
        return TeamResponse.model_validate(team)

    async def update_team(self, team_id: UUID, payload: TeamUpdate) -> TeamResponse:
        team = await self._team_repo.get_by_id(team_id)
        if team is None:
            raise NotFoundError("Team not found", code="team_not_found")
        updated = await self._team_repo.update(team, **payload.model_dump(exclude_unset=True))
        await self._audit_repo.create_event(
            AuditEvent(
                actor_type=AuditActorType.IAM_PRINCIPAL,
                actor_id=self._admin_ctx.principal,
                event_type=AuditEventType.TEAM_UPDATED,
                object_type=AuditObjectType.TEAM,
                object_id=str(team_id),
                request_id=self._admin_ctx.request_id,
                payload_json=payload.model_dump(mode="json", exclude_unset=True),
            )
        )
        await self._session.commit()
        return TeamResponse.model_validate(updated)

    async def set_runtime_policy(
        self, team_id: UUID, payload: TeamRuntimePolicyUpdate
    ) -> dict[str, Any]:
        team = await self._team_repo.get_by_id(team_id)
        if team is None:
            raise NotFoundError("Team not found", code="team_not_found")
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
        await self._team_policy_repo.replace_policies(
            team_id,
            model_ids,
            cache_policy=payload.cache_policy,
            max_tokens_overrides=overrides,
        )
        await self._audit_repo.create_event(
            AuditEvent(
                actor_type=AuditActorType.IAM_PRINCIPAL,
                actor_id=self._admin_ctx.principal,
                event_type=AuditEventType.TEAM_RUNTIME_POLICY_SET,
                object_type=AuditObjectType.TEAM,
                object_id=str(team_id),
                request_id=self._admin_ctx.request_id,
                payload_json=payload.model_dump(mode="json"),
            )
        )
        await self._session.commit()
        return {"status": "ok", "request_id": self._admin_ctx.request_id}

    async def add_member(self, team_id: UUID, payload: TeamMemberCreate) -> dict[str, Any]:
        team = await self._team_repo.get_by_id(team_id)
        user = await self._user_repo.get_by_id(payload.user_id)
        if team is None:
            raise NotFoundError("Team not found", code="team_not_found")
        if user is None:
            raise NotFoundError("User not found", code="user_not_found")
        if await self._membership_repo.get_by_user_and_team(payload.user_id, team_id):
            raise ConflictError("Membership already exists", code="membership_exists")
        membership = await self._membership_repo.add_member(
            TeamMembership(user_id=payload.user_id, team_id=team_id, role=payload.role)
        )
        if payload.is_default:
            await self._user_repo.update(user, default_team_id=team_id)
        await self._audit_repo.create_event(
            AuditEvent(
                actor_type=AuditActorType.IAM_PRINCIPAL,
                actor_id=self._admin_ctx.principal,
                event_type=AuditEventType.TEAM_MEMBER_ADDED,
                object_type=AuditObjectType.TEAM_MEMBERSHIP,
                object_id=str(membership.id),
                request_id=self._admin_ctx.request_id,
                payload_json=payload.model_dump(mode="json"),
            )
        )
        await self._session.commit()
        return {"membership_id": str(membership.id), "request_id": self._admin_ctx.request_id}

    async def remove_member(self, team_id: UUID, user_id: UUID) -> dict[str, Any]:
        membership = await self._membership_repo.get_by_user_and_team(user_id, team_id)
        if membership is None:
            raise NotFoundError("Membership not found", code="membership_not_found")
        user = await self._user_repo.get_by_id(user_id)
        default_team_cleared = bool(user and user.default_team_id == team_id)
        if user and user.default_team_id == team_id:
            await self._user_repo.update(user, default_team_id=None)
        await self._membership_repo.remove_member(membership)
        await self._audit_repo.create_event(
            AuditEvent(
                actor_type=AuditActorType.IAM_PRINCIPAL,
                actor_id=self._admin_ctx.principal,
                event_type=AuditEventType.TEAM_MEMBER_REMOVED,
                object_type=AuditObjectType.TEAM_MEMBERSHIP,
                object_id=str(membership.id),
                request_id=self._admin_ctx.request_id,
                payload_json={
                    "team_id": str(team_id),
                    "user_id": str(user_id),
                    "default_team_cleared": default_team_cleared,
                },
            )
        )
        await self._session.commit()
        return {"status": "ok", "request_id": self._admin_ctx.request_id}


@router.get("/teams")
async def list_teams(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    service=Depends(get_admin_team_service),  # type: ignore[assignment]
) -> dict[str, Any]:
    return await service.list_teams(page, page_size)


@router.post("/teams", response_model=TeamResponse)
async def create_team(payload: TeamCreate, service=Depends(get_admin_team_service)):  # type: ignore[assignment]
    return await service.create_team(payload)


@router.get("/teams/{team_id}")
async def get_team(team_id: UUID, service=Depends(get_admin_team_service)):  # type: ignore[assignment]
    return await service.get_team(team_id)


@router.patch("/teams/{team_id}", response_model=TeamResponse)
async def update_team(team_id: UUID, payload: TeamUpdate, service=Depends(get_admin_team_service)):  # type: ignore[assignment]
    return await service.update_team(team_id, payload)


@router.put("/teams/{team_id}/runtime-policy")
async def set_team_runtime_policy(
    team_id: UUID,
    payload: TeamRuntimePolicyUpdate,
    service=Depends(get_admin_team_service),  # type: ignore[assignment]
) -> dict[str, Any]:
    return await service.set_runtime_policy(team_id, payload)


@router.post("/teams/{team_id}/members")
async def add_member(
    team_id: UUID,
    payload: TeamMemberCreate,
    service=Depends(get_admin_team_service),  # type: ignore[assignment]
) -> dict[str, Any]:
    return await service.add_member(team_id, payload)


@router.delete("/teams/{team_id}/members/{user_id}")
async def remove_member(
    team_id: UUID,
    user_id: UUID,
    service=Depends(get_admin_team_service),  # type: ignore[assignment]
) -> dict[str, Any]:
    return await service.remove_member(team_id, user_id)
