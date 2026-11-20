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


def _route(provider: str = "synthetic-provider", provider_kind: str | None = "openai_compatible") -> RouteResolutionResult:
    # Default: the generic openai-compatible transport - the only server
    # module with a reviewed pair for the shipped Chat profiles.
    return RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        provider=provider,
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
        provider_kind=provider_kind,
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


# Presence-preserving dump: engine-level proof (the selected dump must
# preserve explicit nulls so the engine can reject smuggled unknowns)
# ----------------------------------------------------------------------


class TestPayloadDumpPresence:
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
# Actual-handler payload boundary (mocked policy seam; no DB/provider)
# ----------------------------------------------------------------------


async def _run_to_policy_boundary(
    monkeypatch: pytest.MonkeyPatch,
    *,
    entry_key: AuthenticatedGatewayKey,
    payload: ChatCompletionRequest,
    route: RouteResolutionResult | None = None,
) -> tuple[dict[str, object], list[str]]:
    """Drive the ACTUAL handle_chat_completion to the mocked quota seam.

    Rate limiting is faked OFF (no wait, no refreshed context) and the
    quota reservation seam raises a sentinel to mark that the request
    passed the policy boundary; quota_calls == [] proves denial happened
    before admission.
    """
    settings = Settings(OPENAI_UPSTREAM_API_KEY="unused")

    async def _fake_route(*, authenticated_key, effective_model, policy_result, request):
        return route if route is not None else _route()

    async def _fake_rate_limit(**kwargs):
        return None

    quota_calls: list[str] = []

    async def _fake_quota(**kwargs):
        quota_calls.append("quota")
        raise _QuotaSentinelReached()

    monkeypatch.setattr(gateway_module, "_resolve_chat_completion_route", _fake_route)
    monkeypatch.setattr(gateway_module, "_reserve_redis_rate_limit", _fake_rate_limit)
    monkeypatch.setattr(gateway_module, "_reserve_chat_completion_quota", _fake_quota)

    outcome: dict[str, object] = {}
    try:
        await gateway_module.handle_chat_completion(
            payload=payload,
            authenticated_key=entry_key,
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001 - asserted per test
        outcome["error"] = exc
    return outcome, quota_calls


class TestHandlerPayloadBoundary:
    @pytest.mark.asyncio
    async def test_selected_unknown_null_denied_before_policy(self, monkeypatch) -> None:
        # Regression guard: if the handler regressed to exclude_none=True
        # for selected profiles, this null-smuggled unknown field would be
        # silently deleted and the request would reach admission.
        outcome, quota_calls = await _run_to_policy_boundary(
            monkeypatch,
            entry_key=_auth(chat_client_module=_pin()),
            payload=_payload(unapproved_field=None),
        )
        error = outcome["error"]
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 400
        assert error.code == "agent_chat_unknown_field"
        assert quota_calls == []

    @pytest.mark.asyncio
    async def test_default_unknown_null_retains_historical_strip(self, monkeypatch) -> None:
        # Historical default-path behavior is preserved: exclude_none=True
        # deletes the unknown null and the request is accepted as before.
        outcome, quota_calls = await _run_to_policy_boundary(
            monkeypatch,
            entry_key=_auth(),
            payload=_payload(unapproved_field=None),
        )
        assert quota_calls == ["quota"]
        assert isinstance(outcome["error"], _QuotaSentinelReached)

    @pytest.mark.asyncio
    async def test_selected_explicit_null_declared_field_preserved(
        self, monkeypatch
    ) -> None:
        # An explicitly provided null on a declared field survives to the
        # engine and is handled per the profile dialect (accepted here).
        outcome, quota_calls = await _run_to_policy_boundary(
            monkeypatch,
            entry_key=_auth(chat_client_module=_pin()),
            payload=_payload(stream=None),
        )
        assert quota_calls == ["quota"]
        assert isinstance(outcome["error"], _QuotaSentinelReached)

    @pytest.mark.asyncio
    async def test_selected_omitted_optional_field_stays_absent(
        self, monkeypatch
    ) -> None:
        outcome, quota_calls = await _run_to_policy_boundary(
            monkeypatch,
            entry_key=_auth(chat_client_module=_pin()),
            payload=_payload(),
        )
        assert quota_calls == ["quota"]
        assert isinstance(outcome["error"], _QuotaSentinelReached)


# ----------------------------------------------------------------------
# Reviewed Chat client/server candidate pairs (order items 9/10)
# ----------------------------------------------------------------------


def _native_route() -> RouteResolutionResult:
    return _route(provider="openai", provider_kind=None)


def _local_coding_route() -> RouteResolutionResult:
    return RouteResolutionResult(
        requested_model="classroom-cheap",
        resolved_model="gpt-4.1-mini",
        provider="localhost",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="classroom-cheap",
        priority=100,
        provider_kind="openai_compatible",
        capabilities={
            "local_coding": {
                "contract_version": "local-coding-v1",
                "route_name": "codex-v1-signed",
                "tool_policy_version": "responses-tool-policy-v1",
                "identity_mode": "signed_identity_v1",
                "replay_mode": "process_local_inclusive_horizon_fail_closed",
                "deployment_mode": "single_worker",
                "clock_skew_seconds": 60,
                "replay_ttl_seconds": 60,
            }
        },
    )


class TestChatPairQualification:
    def test_reviewed_chat_pairs_are_declared(self) -> None:
        from slaif_gateway.modules.servers.registry import (
            ensure_client_server_pair,
        )

        for module_id in ("hermes-0.22.5-chat-v1", "opencode-1.19.3-chat-v1"):
            ensure_client_server_pair(module_id, "openai-compatible")

    def test_unreviewed_chat_pairs_are_denied(self) -> None:
        from slaif_gateway.modules.servers.registry import (
            ProviderConfigurationError,
            ensure_client_server_pair,
        )

        servers = (
            "openai",
            "openrouter",
            "local-coding-v1",
            "vllm-chat-video",
            "vllm",
            "upstream-llm",
            "configured-completion",
        )
        for module_id in ("hermes-0.22.5-chat-v1", "opencode-1.19.3-chat-v1"):
            for server in servers:
                with pytest.raises(ProviderConfigurationError):
                    ensure_client_server_pair(module_id, server)

    @pytest.mark.asyncio
    async def test_selected_pin_native_route_denied_before_admission(
        self, monkeypatch
    ) -> None:
        outcome, quota_calls = await _run_to_policy_boundary(
            monkeypatch,
            entry_key=_auth(chat_client_module=_pin()),
            payload=_payload(),
            route=_native_route(),
        )
        error = outcome["error"]
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 400
        assert error.code == "incompatible_client_server_pair"
        assert quota_calls == []

    @pytest.mark.asyncio
    async def test_selected_pin_signed_localcoding_route_denied_before_admission(
        self, monkeypatch
    ) -> None:
        # The signed LocalCoding transport is Responses-only for Chat
        # profiles: its Chat adapter is an explicit unsupported stub, so
        # the pair must fail closed before admission.
        outcome, quota_calls = await _run_to_policy_boundary(
            monkeypatch,
            entry_key=_auth(chat_client_module=_pin()),
            payload=_payload(),
            route=_local_coding_route(),
        )
        error = outcome["error"]
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 400
        assert error.code == "incompatible_client_server_pair"
        assert quota_calls == []

    @pytest.mark.asyncio
    async def test_selected_pin_openai_compatible_route_reaches_quota(
        self, monkeypatch
    ) -> None:
        outcome, quota_calls = await _run_to_policy_boundary(
            monkeypatch,
            entry_key=_auth(chat_client_module=_pin()),
            payload=_payload(),
            route=_route(),
        )
        assert quota_calls == ["quota"]
        assert isinstance(outcome["error"], _QuotaSentinelReached)

    @pytest.mark.asyncio
    async def test_default_pin_native_route_unchanged(self, monkeypatch) -> None:
        # The default dialect is never gated by the selected-profile pair
        # guard (its existing factory-side check is unchanged).
        outcome, quota_calls = await _run_to_policy_boundary(
            monkeypatch,
            entry_key=_auth(),
            payload=_payload(),
            route=_native_route(),
        )
        assert quota_calls == ["quota"]
        assert isinstance(outcome["error"], _QuotaSentinelReached)


# ----------------------------------------------------------------------
# R4: Chat binding revalidated after a real wait
# ----------------------------------------------------------------------


class _QuotaSentinelReached(Exception):
    """Raised by the faked quota reservation seam to prove reachability."""


class _FakeRateLimitService:
    """Records the ACTUAL service-level concurrency releases."""

    def __init__(self) -> None:
        self.release_calls: list[str] = []

    async def release_concurrency(self, *, gateway_key_id, request_id) -> None:
        self.release_calls.append(str(gateway_key_id))


async def _run_with_refreshed_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    entry_key: AuthenticatedGatewayKey,
    refreshed_key: AuthenticatedGatewayKey,
    refreshed_route: RouteResolutionResult | None = None,
    concurrency_reserved: bool = False,
) -> tuple[dict[str, object], list[str], list[str]]:
    """Drive handle_chat_completion to the R4 refresh block with faked seams.

    ``concurrency_reserved=True`` simulates a held Redis concurrency slot
    so release-exactly-once behavior on denials is observable; the REAL
    release helper runs against a fake reservation.service recorder, so
    non-held slots produce zero service releases and held slots produce
    exactly one per denial.
    """
    settings = Settings(OPENAI_UPSTREAM_API_KEY="unused")

    async def _fake_route(*, authenticated_key, effective_model, policy_result, request):
        return _route()

    fake_service = _FakeRateLimitService()

    async def _fake_rate_limit(**kwargs):
        from slaif_gateway.services.chat_completion_gateway import _RateLimitReservation

        return _RateLimitReservation(
            service=fake_service,
            policy=None,
            gateway_key_id=entry_key.gateway_key_id,
            request_id="gw-test",
            concurrency_reserved=concurrency_reserved,
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
        route=refreshed_route if refreshed_route is not None else _route(),
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
    return outcome, quota_calls, fake_service.release_calls


class TestR4ChatBindingRevalidation:
    @pytest.mark.asyncio
    async def test_binding_cleared_while_waiting_refuses(self, monkeypatch) -> None:
        entry = _auth(chat_client_module=_pin())
        refreshed = _auth(chat_client_module=None)
        outcome, quota_calls, release_calls = await _run_with_refreshed_context(
            monkeypatch, entry_key=entry, refreshed_key=refreshed
        )
        error = outcome["error"]
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 409
        assert error.code == "policy_changed_while_waiting"
        assert quota_calls == []
        assert release_calls == []

    @pytest.mark.asyncio
    async def test_binding_added_while_waiting_refuses(self, monkeypatch) -> None:
        entry = _auth(chat_client_module=None)
        refreshed = _auth(chat_client_module=_pin())
        outcome, quota_calls, release_calls = await _run_with_refreshed_context(
            monkeypatch, entry_key=entry, refreshed_key=refreshed
        )
        error = outcome["error"]
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 409
        assert error.code == "policy_changed_while_waiting"
        assert quota_calls == []
        assert release_calls == []

    @pytest.mark.asyncio
    async def test_malformed_refreshed_pin_fails_closed(self, monkeypatch) -> None:
        entry = _auth(chat_client_module=_pin())
        refreshed = _auth(chat_client_module={**_pin(), "extra": "x"})
        outcome, quota_calls, release_calls = await _run_with_refreshed_context(
            monkeypatch, entry_key=entry, refreshed_key=refreshed
        )
        error = outcome["error"]
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 400
        assert error.code == "chat_client_module_metadata_invalid"
        assert quota_calls == []
        assert release_calls == []

    @pytest.mark.asyncio
    async def test_unchanged_binding_reaches_quota_reservation(self, monkeypatch) -> None:
        entry = _auth(chat_client_module=_pin())
        refreshed = _auth(chat_client_module=_pin())
        outcome, quota_calls, release_calls = await _run_with_refreshed_context(
            monkeypatch, entry_key=entry, refreshed_key=refreshed
        )
        assert quota_calls == ["quota"]
        assert isinstance(outcome["error"], _QuotaSentinelReached)
        assert release_calls == []  # non-held slot: no service release

    # ---- held-concurrency cleanup boundary --------------------------------

    @pytest.mark.asyncio
    async def test_held_slot_pair_denied_on_refreshed_route_releases_once(
        self, monkeypatch
    ) -> None:
        entry = _auth(chat_client_module=_pin())
        refreshed = _auth(chat_client_module=_pin())
        outcome, quota_calls, release_calls = await _run_with_refreshed_context(
            monkeypatch,
            entry_key=entry,
            refreshed_key=refreshed,
            refreshed_route=_local_coding_route(),
            concurrency_reserved=True,
        )
        error = outcome["error"]
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 400
        assert error.code == "incompatible_client_server_pair"
        assert quota_calls == []
        assert len(release_calls) == 1

    @pytest.mark.asyncio
    async def test_held_slot_cleared_binding_releases_once(self, monkeypatch) -> None:
        entry = _auth(chat_client_module=_pin())
        refreshed = _auth(chat_client_module=None)
        outcome, quota_calls, release_calls = await _run_with_refreshed_context(
            monkeypatch,
            entry_key=entry,
            refreshed_key=refreshed,
            concurrency_reserved=True,
        )
        error = outcome["error"]
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 409
        assert error.code == "policy_changed_while_waiting"
        assert quota_calls == []
        assert len(release_calls) == 1

    @pytest.mark.asyncio
    async def test_held_slot_malformed_refreshed_pin_releases_once(
        self, monkeypatch
    ) -> None:
        entry = _auth(chat_client_module=_pin())
        refreshed = _auth(chat_client_module={**_pin(), "extra": "x"})
        outcome, quota_calls, release_calls = await _run_with_refreshed_context(
            monkeypatch,
            entry_key=entry,
            refreshed_key=refreshed,
            concurrency_reserved=True,
        )
        error = outcome["error"]
        assert isinstance(error, OpenAICompatibleError)
        assert error.status_code == 400
        assert error.code == "chat_client_module_metadata_invalid"
        assert quota_calls == []
        assert len(release_calls) == 1

    @pytest.mark.asyncio
    async def test_held_slot_unchanged_binding_releases_once_at_quota(
        self, monkeypatch
    ) -> None:
        entry = _auth(chat_client_module=_pin())
        refreshed = _auth(chat_client_module=_pin())
        outcome, quota_calls, release_calls = await _run_with_refreshed_context(
            monkeypatch,
            entry_key=entry,
            refreshed_key=refreshed,
            concurrency_reserved=True,
        )
        assert quota_calls == ["quota"]
        assert isinstance(outcome["error"], _QuotaSentinelReached)
        assert len(release_calls) == 1
