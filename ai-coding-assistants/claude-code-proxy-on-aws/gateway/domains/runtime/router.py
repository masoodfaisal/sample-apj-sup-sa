"""Runtime API routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from gateway.core.dependencies import get_gateway_service
from gateway.domains.runtime.types import MessageRequest, ModelListResponse

router = APIRouter(prefix="/v1", tags=["runtime"])
logger = logging.getLogger(__name__)


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/models", response_model=ModelListResponse)
async def list_models(
    request: Request,
    x_api_key: str = Header(alias="x-api-key"),
    service=Depends(get_gateway_service),  # type: ignore[assignment]
) -> ModelListResponse:
    return await service.list_models(x_api_key, request.state.request_id)


@router.post("/messages")
async def post_messages(
    payload: MessageRequest,
    request: Request,
    x_api_key: str = Header(alias="x-api-key"),
    service=Depends(get_gateway_service),  # type: ignore[assignment]
):
    logger.info(
        "runtime request received request_id=%s selected_model=%s stream=%s beta=%s",
        request.state.request_id,
        payload.model,
        payload.stream,
        request.query_params.get("beta"),
    )
    if payload.stream:
        generator = await service.process_message_stream(
            payload, x_api_key, request.state.request_id
        )
        return StreamingResponse(generator, media_type="text/event-stream")
    return await service.process_message(payload, x_api_key, request.state.request_id)
