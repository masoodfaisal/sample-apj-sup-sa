"""Tests for CachePolicyHandler prompt-cache logic."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.core.exceptions import InternalError
from gateway.domains.policy.context import PolicyContext
from gateway.domains.policy.handlers.cache_policy import CachePolicyHandler
from gateway.domains.policy.handlers.team_model_policy import TeamModelPolicyHandler
from gateway.domains.policy.handlers.user_model_policy import UserModelPolicyHandler
from gateway.domains.runtime.types import MessageRequest


def _make_context(cache_policy: str = "none", resolved_model=None) -> PolicyContext:
    ctx = PolicyContext(
        api_key="test-key",
        request_id="req-1",
        request=MessageRequest(
            model="test",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        ),
    )
    ctx.resolved_model = resolved_model
    ctx.cache_policy = cache_policy
    return ctx


async def test_cache_policy_preserves_policy_when_model_supports_cache() -> None:
    ctx = _make_context(
        cache_policy="5m",
        resolved_model=SimpleNamespace(supports_prompt_cache=True),
    )
    await CachePolicyHandler().handle(ctx)
    assert ctx.cache_policy == "5m"
    assert ctx.cache_policy_source == "default"


async def test_cache_policy_forces_none_when_model_does_not_support_cache() -> None:
    ctx = _make_context(
        cache_policy="1h",
        resolved_model=SimpleNamespace(supports_prompt_cache=False),
    )
    ctx.cache_policy_source = "team"
    await CachePolicyHandler().handle(ctx)
    assert ctx.cache_policy == "none"
    assert ctx.cache_policy_source == "model-capability"


async def test_cache_policy_raises_when_resolved_model_is_none() -> None:
    ctx = _make_context(cache_policy="5m", resolved_model=None)
    with pytest.raises(InternalError):
        await CachePolicyHandler().handle(ctx)


async def test_user_model_policy_sets_cache_policy_source() -> None:
    handler = UserModelPolicyHandler(
        repo=SimpleNamespace(
            get_policy=lambda *_: None,
        )
    )

    async def get_policy(*_args):
        return SimpleNamespace(allow=True, cache_policy="1h", max_tokens_override=2048)

    handler._repo.get_policy = get_policy
    ctx = _make_context(cache_policy="5m", resolved_model=SimpleNamespace(id="model-id"))
    ctx.user = SimpleNamespace(id="user-id")

    await handler.handle(ctx)

    assert ctx.cache_policy == "1h"
    assert ctx.cache_policy_source == "user"
    assert ctx.max_tokens_override == 2048


async def test_team_model_policy_sets_cache_policy_source() -> None:
    handler = TeamModelPolicyHandler(
        repo=SimpleNamespace(
            get_policy=lambda *_: None,
        )
    )

    async def get_policy(*_args):
        return SimpleNamespace(allow=True, cache_policy="1h", max_tokens_override=1024)

    handler._repo.get_policy = get_policy
    ctx = _make_context(cache_policy="5m", resolved_model=SimpleNamespace(id="model-id"))
    ctx.team = SimpleNamespace(id="team-id")

    await handler.handle(ctx)

    assert ctx.cache_policy == "1h"
    assert ctx.cache_policy_source == "team"
    assert ctx.max_tokens_override == 1024
