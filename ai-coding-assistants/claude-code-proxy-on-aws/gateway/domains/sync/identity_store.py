"""Identity Store client helpers for manual sync."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from gateway.core.exceptions import GatewayError
from shared.utils.constants import UserStatus


@dataclass(frozen=True, slots=True)
class IdentityStoreUserRecord:
    """Normalized subset of Identity Store user data used by the gateway."""

    user_id: str
    user_name: str
    display_name: str | None
    email: str | None
    status: UserStatus


class IdentityStoreGateway:
    """Thin async wrapper over the boto3 Identity Store client."""

    def __init__(self, client, identity_store_id: str) -> None:  # type: ignore[no-untyped-def]
        self._client = client
        self._identity_store_id = identity_store_id

    async def list_users(self) -> list[IdentityStoreUserRecord]:
        """Return all users from the configured Identity Store."""

        self._validate_identity_store_id()
        try:
            return await asyncio.to_thread(self._list_users_sync)
        except ClientError as exc:
            raise self._translate_client_error(exc) from exc
        except BotoCoreError as exc:
            raise GatewayError(
                "Identity Store request failed",
                code="identity_store_error",
                status_code=502,
                retryable=True,
            ) from exc

    def _list_users_sync(self) -> list[IdentityStoreUserRecord]:
        paginator = self._client.get_paginator("list_users")
        records: list[IdentityStoreUserRecord] = []
        for page in paginator.paginate(
            IdentityStoreId=self._identity_store_id,
            PaginationConfig={"PageSize": 100},
        ):
            for user in page.get("Users", []):
                records.append(_normalize_user(user))
        return records

    def _validate_identity_store_id(self) -> None:
        if not self._identity_store_id or self._identity_store_id == "placeholder":
            raise GatewayError(
                "Identity Store is not configured",
                code="identity_store_not_configured",
                status_code=500,
            )

    @staticmethod
    def _translate_client_error(exc: ClientError) -> GatewayError:
        error_code = exc.response.get("Error", {}).get("Code", "ClientError")
        if error_code == "AccessDeniedException":
            return GatewayError(
                "Gateway is not authorized to access the Identity Store",
                code="identity_store_access_denied",
                status_code=500,
            )
        if error_code == "ResourceNotFoundException":
            return GatewayError(
                "Configured Identity Store was not found",
                code="identity_store_not_found",
                status_code=500,
            )
        if error_code == "ThrottlingException":
            return GatewayError(
                "Identity Store request was throttled",
                code="identity_store_throttled",
                status_code=502,
                retryable=True,
            )
        return GatewayError(
            "Identity Store request failed",
            code="identity_store_error",
            status_code=502,
            retryable=True,
        )


def _normalize_user(user: dict[str, Any]) -> IdentityStoreUserRecord:
    user_id = str(user["UserId"])
    email = _select_email(user.get("Emails"))
    user_name = str(user.get("UserName") or email or user_id)
    return IdentityStoreUserRecord(
        user_id=user_id,
        user_name=user_name,
        display_name=_display_name(user),
        email=email,
        status=_map_user_status(user.get("UserStatus")),
    )


def _display_name(user: dict[str, Any]) -> str | None:
    display_name = user.get("DisplayName")
    if display_name:
        return str(display_name)

    name = user.get("Name") or {}
    formatted = name.get("Formatted")
    if formatted:
        return str(formatted)

    parts = [name.get("GivenName"), name.get("FamilyName")]
    joined = " ".join(str(part).strip() for part in parts if part)
    return joined or None


def _select_email(emails: Any) -> str | None:
    if not emails:
        return None

    primary = next((item for item in emails if item.get("Primary") and item.get("Value")), None)
    if primary is not None:
        return str(primary["Value"])

    first = next((item for item in emails if item.get("Value")), None)
    if first is not None:
        return str(first["Value"])

    return None


def _map_user_status(status: Any) -> UserStatus:
    return UserStatus.ACTIVE if status != "DISABLED" else UserStatus.INACTIVE
