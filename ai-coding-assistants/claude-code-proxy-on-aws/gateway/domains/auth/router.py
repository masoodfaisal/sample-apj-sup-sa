"""Auth token issuance endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from gateway.core.dependencies import get_auth_principal, get_token_issuance_service
from gateway.domains.auth.schemas import TokenIssuanceRequest, TokenIssuanceResponse

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/token")
async def issue_token(
    request: Request,
    body: TokenIssuanceRequest,
    principal_arn: str = Depends(get_auth_principal),
    service=Depends(get_token_issuance_service),  # type: ignore[assignment]
) -> TokenIssuanceResponse:
    return await service.issue_token(principal_arn, body, request.state.request_id)
