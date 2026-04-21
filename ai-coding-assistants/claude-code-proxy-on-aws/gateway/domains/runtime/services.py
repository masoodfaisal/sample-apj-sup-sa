"""Gateway orchestration service."""

from __future__ import annotations

import json
import logging

from gateway.domains.policy.context import PolicyContext
from gateway.domains.policy.engine import HandlerType
from gateway.domains.runtime.types import (
    MessageRequest,
    MessageResponse,
    ModelData,
    ModelListResponse,
)
from gateway.domains.usage.metrics import MetricsService
from shared.exceptions import (
    AppError,
    BedrockError,
    BedrockThrottlingError,
    BudgetExceededError,
    ModelNotAllowedError,
    TeamInactiveError,
    UserInactiveError,
)

logger = logging.getLogger(__name__)


class GatewayService:
    """Orchestrate runtime requests."""

    def __init__(
        self,
        policy_chain,
        request_converter,
        response_converter,
        bedrock_client,
        stream_processor,
        usage_service,
        session,
        model_catalog_repo,
        metrics: MetricsService | None = None,
        log_full_payloads: bool = False,
    ) -> None:  # type: ignore[no-untyped-def]
        self._policy_chain = policy_chain
        self._request_converter = request_converter
        self._response_converter = response_converter
        self._bedrock_client = bedrock_client
        self._stream_processor = stream_processor
        self._usage_service = usage_service
        self._session = session
        self._model_catalog_repo = model_catalog_repo
        self._metrics = metrics
        self._log_full_payloads = log_full_payloads

    def _log_bedrock_error(self, context: PolicyContext, error: AppError) -> None:
        level = logging.WARNING if isinstance(error, BedrockThrottlingError) else logging.ERROR
        logger.log(
            level,
            "bedrock runtime request failed request_id=%s "
            "selected_model=%s resolved_model=%s user_id=%s error=%s",
            context.request_id,
            context.selected_model,
            context.resolved_model.bedrock_model_id if context.resolved_model else None,
            str(context.user.id) if context.user else None,
            str(error),
        )

    @staticmethod
    def _response_model_name(context: PolicyContext, fallback_model: str) -> str:
        if context.resolved_model and context.resolved_model.bedrock_model_id:
            return context.resolved_model.bedrock_model_id
        return fallback_model

    @staticmethod
    def _serialize_payload(payload: object) -> str:
        return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))

    def _log_request_payload(self, request_id: str, request: MessageRequest) -> None:
        if not self._log_full_payloads:
            return
        logger.info(
            "runtime anthropic request payload request_id=%s payload=%s",
            request_id,
            self._serialize_payload(request.model_dump(exclude_none=True)),
        )

    def _log_bedrock_request_payload(self, request_id: str, payload: dict[str, object]) -> None:
        if not self._log_full_payloads:
            return
        logger.info(
            "runtime bedrock request payload request_id=%s payload=%s",
            request_id,
            self._serialize_payload(payload),
        )

    def _log_bedrock_response_payload(self, request_id: str, payload: dict[str, object]) -> None:
        if not self._log_full_payloads:
            return
        logger.info(
            "runtime bedrock response payload request_id=%s payload=%s",
            request_id,
            self._serialize_payload(payload),
        )

    @staticmethod
    def _inject_bedrock_request_metadata(
        request: dict[str, object], context: PolicyContext
    ) -> dict[str, object]:
        existing = request.get("requestMetadata")
        request_metadata = dict(existing) if isinstance(existing, dict) else {}
        request_metadata["request_id"] = context.request_id
        if context.user is not None and getattr(context.user, "id", None) is not None:
            request_metadata["user_id"] = str(context.user.id)
        if context.team is not None and getattr(context.team, "id", None) is not None:
            request_metadata["team_id"] = str(context.team.id)
        request["requestMetadata"] = request_metadata
        return request

    async def process_message(
        self,
        request: MessageRequest,
        api_key: str,
        request_id: str,
    ) -> MessageResponse:
        context = PolicyContext(api_key=api_key, request_id=request_id, request=request)
        self._log_request_payload(request_id, request)
        if self._metrics:
            self._metrics.emit_active_request_start(context)
        try:
            await self._policy_chain.evaluate(context)
            await self._session.commit()
            bedrock_request = self._request_converter.convert_request(
                request,
                context.resolved_model,
                context.cache_policy,
                context.max_tokens_override,
            )
            bedrock_request = self._inject_bedrock_request_metadata(bedrock_request, context)
            self._log_bedrock_request_payload(request_id, bedrock_request)
            response = await self._bedrock_client.converse(bedrock_request, context.resolved_model)
            self._log_bedrock_response_payload(request_id, response)
            message = self._response_converter.convert_response(
                response,
                self._response_model_name(context, request.model),
            )
            usage = self._response_converter.extract_usage(response)
            await self._usage_service.record_success(context, usage)
            return message
        except AppError as error:
            if isinstance(error, BedrockThrottlingError):
                self._log_bedrock_error(context, error)
                if self._metrics:
                    self._metrics.emit_throttle(context)
            elif isinstance(error, BedrockError):
                self._log_bedrock_error(context, error)
            if self._metrics and isinstance(
                error,
                (BudgetExceededError, ModelNotAllowedError, UserInactiveError, TeamInactiveError),
            ):
                self._metrics.emit_policy_block(context, type(error).__name__)
            if context.resolved_model and context.user and context.virtual_key:
                await self._usage_service.record_blocked_request(context, error)
            raise
        except Exception as error:
            if context.resolved_model and context.user and context.virtual_key:
                await self._usage_service.record_error(context, BedrockError(str(error)))
            raise
        finally:
            if self._metrics:
                self._metrics.emit_active_request_end(context)

    async def process_message_stream(
        self,
        request: MessageRequest,
        api_key: str,
        request_id: str,
    ):
        context = PolicyContext(api_key=api_key, request_id=request_id, request=request)
        self._log_request_payload(request_id, request)
        if self._metrics:
            self._metrics.emit_active_request_start(context)
        try:
            await self._policy_chain.evaluate(context)
            await self._session.commit()
            bedrock_request = self._request_converter.convert_request(
                request,
                context.resolved_model,
                context.cache_policy,
                context.max_tokens_override,
            )
            bedrock_request = self._inject_bedrock_request_metadata(bedrock_request, context)
            self._log_bedrock_request_payload(request_id, bedrock_request)
            bedrock_stream = await self._bedrock_client.converse_stream(
                bedrock_request,
                context.resolved_model,
            )
            return self._stream_processor.stream_response(
                bedrock_stream,
                context,
                on_done=(
                    lambda: self._metrics.emit_active_request_end(context)
                    if self._metrics
                    else None
                ),
            )
        except AppError as error:
            if isinstance(error, BedrockThrottlingError):
                self._log_bedrock_error(context, error)
                if self._metrics:
                    self._metrics.emit_throttle(context)
            elif isinstance(error, BedrockError):
                self._log_bedrock_error(context, error)
            if self._metrics and isinstance(
                error,
                (BudgetExceededError, ModelNotAllowedError, UserInactiveError, TeamInactiveError),
            ):
                self._metrics.emit_policy_block(context, type(error).__name__)
            if self._metrics:
                self._metrics.emit_active_request_end(context)
            if context.resolved_model and context.user and context.virtual_key:
                await self._usage_service.record_blocked_request(context, error)
            raise

    async def list_models(self, api_key: str, request_id: str) -> ModelListResponse:
        request = MessageRequest(
            model="models", max_tokens=1, messages=[{"role": "user", "content": ""}]
        )
        context = PolicyContext(api_key=api_key, request_id=request_id, request=request)
        auth_handlers = self._policy_chain.get_handlers_by_type(
            [
                HandlerType.VIRTUAL_KEY,
                HandlerType.USER_STATUS,
                HandlerType.TEAM_STATUS,
            ]
        )
        for handler in auth_handlers:
            await handler.handle(context)  # type: ignore[attr-defined]
        models = await self._model_catalog_repo.get_active_list()
        return ModelListResponse(
            data=[
                ModelData(
                    id=model.canonical_name,
                    family=model.family,
                    supports_streaming=model.supports_streaming,
                    supports_tools=model.supports_tools,
                    supports_prompt_cache=model.supports_prompt_cache,
                )
                for model in models
            ]
        )
