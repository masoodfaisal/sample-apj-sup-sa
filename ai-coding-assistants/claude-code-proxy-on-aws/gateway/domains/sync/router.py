"""Identity sync routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from gateway.core.dependencies import get_identity_sync_service
from shared.schemas import SyncRunResponse, SyncRunTriggerResponse

router = APIRouter(prefix="/v1/admin/sync", tags=["admin-sync"])


@router.post("/identity-center", response_model=SyncRunTriggerResponse)
async def run_identity_sync(service=Depends(get_identity_sync_service)):  # type: ignore[assignment]
    return SyncRunTriggerResponse.model_validate(await service.run_sync())


@router.get("/identity-center/runs/{run_id}", response_model=SyncRunResponse)
async def get_sync_run(run_id: UUID, service=Depends(get_identity_sync_service)):  # type: ignore[assignment]
    run = await service.get_sync_status(run_id)
    return SyncRunResponse.model_validate(run)
