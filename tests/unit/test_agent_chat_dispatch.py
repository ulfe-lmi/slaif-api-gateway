"""Focused unit tests for the 227-a Chat profile dispatch wiring.

Covers the process bootstrap of the finite static Chat registry, the
presence-preserving payload dump for selected profiles versus the
historical default dump, the gateway selection helpers, and the R4
post-wait Chat-binding revalidation inside ``handle_chat_completion``.
Pure: no database, no network, no real client, no real provider.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

import slaif_gateway.services.chat_completion_gateway as gateway_module
from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.agent_chat import (
    AGENT_CHAT_CLIENT_MODULE_REGISTRY,
    AgentChatModuleSelectionError,
    AgentChatRequestError,
    agent_chat_profile_metadata,
    bootstrap_agent_chat_client_modules,
    get_agent_chat_client_module,
)
from slaif_gateway.modules.clients.hermes_0225_chat import HERMES_0225_CHAT_CLIENT_MODULE
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ChatCompletionRequest
from slaif_gateway.schemas.routing import RouteResolutionResult

_HERMES_ID = "hermes-0.22.5-chat-v1"


def _pin() -> dict[str, str]:
    return dict(agent_chat_profile_metadata(HERMES_0225_CHAT_CLIENT_MODULE))


def _auth(chat_client_module: object = None) -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public1234abcd",
        status="active",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
        chat_client_module=chat_client_module,
    )


def _payload(**extra: object) -> ChatCompletionRequest:
    base: dict[str, object] = {
        "model": "classroom-cheap",
        "messages": [{"role": "user", "content": "hello"}],
    }
    base.update(extra)
    return ChatCompletionRequest(**base)  # type: ignore[arg-type]


def _route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
    )


# ----------------------------------------------------------------------
# Finite static bootstrap
# ----------------------------------------------------------------------


class TestBootstrap:
    def test_bootstrap_registers_shipped_hermes_binding(self) -> None:
        bootstrap_agent_chat_client_modules()
        assert get_agent_chat_client_module(_HERMES_ID) is HERMES_0225_CHAT_CLIENT_MODULE

    def test_bootstrap_is_idempotent(self) -> None:
        bootstrap_agent_chat_client_modules()
        first = AGENT_CHAT_CLIENT_MODULE_REGISTRY[_HERMES_ID]
        bootstrap_agent_chat_client_modules()
        assert AGENT_CHAT_CLIENT_MODULE_REGISTRY[_HERMES_ID] is first


# ----------------------------------------------------------------------
# Presence-preserving dump: selected profiles vs historical default
# ----------------------------------------------------------------------


class TestPayloadDumpPresence:
    def test_default_dump_strips_explicit_null_extra(self) -> None:
        # Historical default-path behavior: exclude_none=True silently
        # deletes an unknown field provided as null.
        dumped = _payload(unapproved_field=None).model_dump(
            mode="python", exclude_none=True
        )
        assert "unapproved_field" not in dumped

    def test_selected_dump_preserves_explicit_null_extra(self) -> None:
        dumped = _payload(unapproved_field=None).model_dump(
            mode="python", exclude_unset=True
        )
        assert dumped["unapproved_field"] is None

    def test_selected_engine_denies_null_smuggled_unknown_field(self) -> None:
        dumped = _payload(unapproved_field=None).model_dump(
            mode="python", exclude_unset=True
        )
        with pytest.raises(AgentChatRequestError) as excinfo:
            HERMES_0225_CHAT_CLIENT_MODULE.normalize("/v1/chat/completions", dumped)
        assert excinfo.value.error_code == "agent_chat_unknown_field"

    def test_selected_engine_accepts_omitted_unknown_field(self) -> None:
        dumped = _payload().model_dump(mode="python", exclude_unset=True)
        assert "unapproved_field" not in dumped
        request = HERMES_0225_CHAT_CLIENT_MODULE.normalize(
            "/v1/chat/completions", dumped
        )
        assert request.body["model"] == "classroom-cheap"

    def test_selected_dump_preserves_explicit_null_declared_field(self) -> None:
        dumped = _payload(stream=None).model_dump(mode="python", exclude_unset=True)
        assert "stream" in dumped and dumped["stream"] is None


# ----------------------------------------------------------------------
# Gateway selection helpers
# ----------------------------------------------------------------------


class TestSelectionHelpers:
    def test_resolve_absent_pin_returns_none(self) -> None:
        assert gateway_module._resolve_chat_client_module(_auth()) is None

    def test_resolve_valid_pin_returns_module(self) -> None:
        module = gateway_module._resolve_chat_client_module(_auth(chat_client_module=_pin()))
        assert module is HERMES_0225_CHAT_CLIENT_MODULE

    def test_resolve_malformed_pin_fails_closed(self) -> None:
        with pytest.raises(AgentChatModuleSelectionError) as excinfo:
            gateway_module._resolve_chat_client_module(
                _auth(chat_client_module={**_pin(), "messages": [{"role": "user"}]})
            )
        assert excinfo.value.error_code == "chat_client_module_metadata_invalid"

    def test_selection_error_maps_to_fixed_openai_shape(self) -> None:
        exc = AgentChatModuleSelectionError(
            "x", error_code="unsupported_client_module"
        )
        error = gateway_module._openai_error_from_chat_module_selection_error(exc)
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 400
        assert error.error_type == "invalid_request_error"
        assert error.code == "unsupported_client_module"

    def test_request_error_maps_to_fixed_openai_shape_with_param(self) -> None:
        exc = AgentChatRequestError(
            "x", error_code="agent_chat_unknown_field", param="top_level"
        )
        error = gateway_module._openai_error_from_chat_request_error(exc)
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 400
        assert error.code == "agent_chat_unknown_field"
        assert error.param == "top_level"

    def test_module_identity_none_and_module(self) -> None:
        assert gateway_module._chat_module_identity(None) is None
        assert gateway_module._chat_module_identity(HERMES_0225_CHAT_CLIENT_MODULE) == (
            _HERMES_ID,
            "1",
            HERMES_0225_CHAT_CLIENT_MODULE.fixture_sha256,
        )


# ----------------------------------------------------------------------
# R4: Chat binding revalidated after a real wait
# ----------------------------------------------------------------------


class _QuotaSentinelReached(Exception):
    """Raised by the faked quota reservation seam to prove reachability."""


async def _run_with_refreshed_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    entry_key: AuthenticatedGatewayKey,
    refreshed_key: AuthenticatedGatewayKey,
) -> tuple[dict[str, object], list[str]]:
    """Drive handle_chat_completion to the R4 refresh block with faked seams."""
    settings = Settings(OPENAI_UPSTREAM_API_KEY="unused")

    async def _fake_route(*, authenticated_key, effective_model, policy_result, request):
        return _route()

    async def _fake_rate_limit(**kwargs):
        from slaif_gateway.services.chat_completion_gateway import _RateLimitReservation

        return _RateLimitReservation(
            service=None,
            policy=None,
            gateway_key_id=entry_key.gateway_key_id,
            request_id="gw-test",
            concurrency_reserved=False,
            refreshed_context=refreshed_context,
        )

    quota_calls: list[str] = []

    async def _fake_quota(**kwargs):
        quota_calls.append("quota")
        raise _QuotaSentinelReached()

    from slaif_gateway.services.request_policy import ChatCompletionRequestPolicy

    normalized = HERMES_0225_CHAT_CLIENT_MODULE.normalize(
        "/v1/chat/completions",
        _payload().model_dump(mode="python", exclude_unset=True),
    ).body
    policy_result = ChatCompletionRequestPolicy(settings=settings).apply(
        normalized,
        defer_media_limit=True,
        capability_policy_mode=entry_key.capability_policy_mode,
    )
    refreshed_context = SimpleNamespace(
        authenticated_key=refreshed_key,
        policy_result=policy_result,
        route=_route(),
    )

    monkeypatch.setattr(gateway_module, "_resolve_chat_completion_route", _fake_route)
    monkeypatch.setattr(gateway_module, "_reserve_redis_rate_limit", _fake_rate_limit)
    monkeypatch.setattr(gateway_module, "_reserve_chat_completion_quota", _fake_quota)

    outcome: dict[str, object] = {}
    try:
        await gateway_module.handle_chat_completion(
            payload=_payload(),
            authenticated_key=entry_key,
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001 - asserted per test
        outcome["error"] = exc
    return outcome, quota_calls


class TestR4ChatBindingRevalidation:
    @pytest.mark.asyncio
    async def test_binding_cleared_while_waiting_refuses(self, monkeypatch) -> None:
        entry = _auth(chat_client_module=_pin())
        refreshed = _auth(chat_client_module=None)
        outcome, quota_calls = await _run_with_refreshed_context(
            monkeypatch, entry_key=entry, refreshed_key=refreshed
        )
        error = outcome["error"]
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 409
        assert error.code == "policy_changed_while_waiting"
        assert quota_calls == []

    @pytest.mark.asyncio
    async def test_binding_added_while_waiting_refuses(self, monkeypatch) -> None:
        entry = _auth(chat_client_module=None)
        refreshed = _auth(chat_client_module=_pin())
        outcome, quota_calls = await _run_with_refreshed_context(
            monkeypatch, entry_key=entry, refreshed_key=refreshed
        )
        error = outcome["error"]
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 409
        assert error.code == "policy_changed_while_waiting"
        assert quota_calls == []

    @pytest.mark.asyncio
    async def test_malformed_refreshed_pin_fails_closed(self, monkeypatch) -> None:
        entry = _auth(chat_client_module=_pin())
        refreshed = _auth(chat_client_module={**_pin(), "extra": "x"})
        outcome, quota_calls = await _run_with_refreshed_context(
            monkeypatch, entry_key=entry, refreshed_key=refreshed
        )
        error = outcome["error"]
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 400
        assert error.code == "chat_client_module_metadata_invalid"
        assert quota_calls == []

    @pytest.mark.asyncio
    async def test_unchanged_binding_reaches_quota_reservation(self, monkeypatch) -> None:
        entry = _auth(chat_client_module=_pin())
        refreshed = _auth(chat_client_module=_pin())
        outcome, quota_calls = await _run_with_refreshed_context(
            monkeypatch, entry_key=entry, refreshed_key=refreshed
        )
        assert quota_calls == ["quota"]
        assert isinstance(outcome["error"], _QuotaSentinelReached)
