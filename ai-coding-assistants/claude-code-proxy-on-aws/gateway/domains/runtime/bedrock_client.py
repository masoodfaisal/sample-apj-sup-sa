"""Bedrock runtime client wrapper."""

from __future__ import annotations

import asyncio
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ParamValidationError

from gateway.core.config import Settings
from gateway.core.exceptions import BedrockError, BedrockThrottlingError


class BedrockClient:
    """Thin async wrapper over boto3 Bedrock runtime methods."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._config = Config(retries={"max_attempts": 1, "mode": "standard"})
        self._clients: dict[str, Any] = {}

    async def converse(
        self,
        request: dict[str, Any],
        resolved_model: Any | None = None,
    ) -> dict[str, Any]:
        return await self._call("converse", request, resolved_model)

    async def converse_stream(
        self,
        request: dict[str, Any],
        resolved_model: Any | None = None,
    ) -> dict[str, Any]:
        return await self._call("converse_stream", request, resolved_model)

    def _get_client(self, resolved_model: Any | None = None) -> Any:
        region_name = getattr(resolved_model, "bedrock_region", None) or self._settings.aws_region
        client = self._clients.get(region_name)
        if client is None:
            client = boto3.client(
                self._settings.bedrock_runtime_service,
                region_name=region_name,
                config=self._config,
            )
            self._clients[region_name] = client
        return client

    async def _call(
        self,
        method: str,
        request: dict[str, Any],
        resolved_model: Any | None = None,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        client = self._get_client(resolved_model)
        try:
            return await loop.run_in_executor(
                None, lambda: getattr(client, method)(**request)
            )
        except ParamValidationError as exc:
            raise BedrockError(str(exc)) from exc
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"ThrottlingException", "TooManyRequestsException"}:
                raise BedrockThrottlingError(str(exc)) from exc
            raise BedrockError(str(exc)) from exc
