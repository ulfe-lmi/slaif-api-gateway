"""Unit tests for the content-free request-failure diagnostics service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.schemas.request_diagnostics import (
    DIAGNOSTIC_MAX_RECORD_BYTES,
    DiagnosticsWriteOutcome,
)
from slaif_gateway.services.request_diagnostics import (
    DiagnosticsProjectionError,
    RequestDiagnosticsService,
    build_client_id_masker,
    build_diagnostic_record,
    _serialize_record,
)

CANARY = "private_prompt_canary"


@pytest.fixture()
def settings() -> Settings:
    return Settings(_env_file=None)


def _base_facts(**overrides: Any) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "gateway_request_id": "gw-00000000-0000-4000-8000-000000000001",
        "client_request_id": "req-legit-id",
        "method": "POST",
        "occurred_at": datetime.now(UTC),
        "stream_outcome": "http_rejection",
        "http_status": 400,
    }
    facts.update(overrides)
    return facts


# -- finite reviewed vocabularies -------------------------------------------


def test_unknown_source_reason_code_become_unavailable(settings: Settings) -> None:
    record = build_diagnostic_record(
        _base_facts(
            source=CANARY,
            reason_code=CANARY,
            error_code=CANARY,
            replay_error_code=CANARY,
        ),
        settings=settings,
    )
    assert record.source is None
    assert record.reason_code is None
    assert record.error_code is None
    assert record.replay_error_code is None


def test_known_source_reason_code_are_retained(settings: Settings) -> None:
    record = build_diagnostic_record(
        _base_facts(
            source="responses_route_limits",
            reason_code="responses_codex_context_window_exceeded",
            error_code="responses_codex_context_window_exceeded",
        ),
        settings=settings,
    )
    assert record.source == "responses_route_limits"
    assert record.reason_code == "responses_codex_context_window_exceeded"
    assert record.error_code == "responses_codex_context_window_exceeded"


def test_taxonomy_reasons_and_http_status_codes_are_retained(settings: Settings) -> None:
    record = build_diagnostic_record(
        _base_facts(
            source="codex_additional_tools_taxonomy",
            reason_code="tool_type_invalid",
            error_code="418",
        ),
        settings=settings,
    )
    assert record.reason_code == "tool_type_invalid"
    assert record.error_code == "418"


def test_error_param_requires_finite_known_components(settings: Settings) -> None:
    unknown = build_diagnostic_record(
        _base_facts(error_param=CANARY), settings=settings
    )
    assert unknown.error_param is None

    indexed = build_diagnostic_record(
        _base_facts(error_param="input[3].tools"), settings=settings
    )
    assert indexed.error_param == "input[3].tools"

    path = build_diagnostic_record(
        _base_facts(error_param="model.max_output_tokens"), settings=settings
    )
    assert path.error_param == "model.max_output_tokens"

    for bad in (
        "Input[3].Tools",
        "input[9999999].tools",
        "a.b.c.d.e.f.g.h.i",
        "input[0].private_prompt_canary",
        "../../etc/passwd",
        "input[0].",
        "input[-1]",
        "input[]",
    ):
        record = build_diagnostic_record(_base_facts(error_param=bad), settings=settings)
        assert record.error_param is None, bad


def test_error_param_overlong_known_path_is_unavailable_with_facts_preserved(
    settings: Settings,
) -> None:
    # 71 characters, ALL known components: passes the component grammar but
    # exceeds the 64-byte error_param column.  The root-owned PG16 probe
    # proved this exact value used to make the INSERT fail and drop the
    # whole diagnostic; it must now project to unavailable instead.
    overlong = (
        "max_output_tokens.max_output_tokens.max_output_tokens.max_output_tokens"
    )
    assert len(overlong) == 71
    record = build_diagnostic_record(
        _base_facts(
            error_param=overlong,
            source="responses_route_limits",
            reason_code="responses_codex_context_window_exceeded",
            error_code="responses_codex_context_window_exceeded",
            counts={"count": 2, "limit": 10},
        ),
        settings=settings,
    )
    # the optional path value is unavailable...
    assert record.error_param is None
    # ...but the remaining failure facts survive in a storable record
    assert record.source == "responses_route_limits"
    assert record.reason_code == "responses_codex_context_window_exceeded"
    assert record.error_code == "responses_codex_context_window_exceeded"
    assert record.counts == {"count": 2, "limit": 10}
    assert record.gateway_request_id == "gw-00000000-0000-4000-8000-000000000001"

    # the boundary is exactly the column width: 64 chars fit, 65 do not
    fit = "max_output_tokens.max_output_tokens.max_output_tokens.input[123]"
    assert len(fit) == 64
    assert (
        build_diagnostic_record(
            _base_facts(error_param=fit), settings=settings
        ).error_param
        == fit
    )
    over = "max_output_tokens.max_output_tokens.max_output_tokens.input[1234]"
    assert len(over) == 65
    assert (
        build_diagnostic_record(
            _base_facts(error_param=over), settings=settings
        ).error_param
        is None
    )

def test_counts_and_limits_use_closed_key_vocabulary(settings: Settings) -> None:
    record = build_diagnostic_record(
        _base_facts(
            counts={"count": 2, CANARY: 1, "limit": 10},
            limits={"max_output_tokens": 1050000, CANARY: 7},
        ),
        settings=settings,
    )
    assert record.counts == {"count": 2, "limit": 10}
    assert record.limits == {"max_output_tokens": 1050000}

    rejected = build_diagnostic_record(
        _base_facts(counts={CANARY: 1}, limits={CANARY: 2}), settings=settings
    )
    assert rejected.counts is None
    assert rejected.limits is None


def test_positions_use_known_classifier_index_names_only(settings: Settings) -> None:
    record = build_diagnostic_record(
        _base_facts(positions={"namespace_index": 0, "tool_index": 2, "line": 11}),
        settings=settings,
    )
    assert record.positions == {"namespace_index": 0, "tool_index": 2, "line": 11}

    for bad in (
        {CANARY: 1},
        [0, 1, 2],
        {"line": -1},
        {"line": 1_000_001},
        {"line": "3"},
    ):
        rejected = build_diagnostic_record(_base_facts(positions=bad), settings=settings)
        assert rejected.positions is None, bad


def test_unknown_field_is_a_fixed_projection_error(settings: Settings) -> None:
    with pytest.raises(DiagnosticsProjectionError) as excinfo:
        build_diagnostic_record(
            _base_facts(error_message=CANARY), settings=settings
        )
    assert excinfo.value.reason == "unknown_field"


def test_missing_identity_and_unsafe_shapes_are_rejected(settings: Settings) -> None:
    for bad in (
        {k: v for k, v in _base_facts().items() if k != "gateway_request_id"},
        _base_facts(method="post GET"),
        _base_facts(stream_outcome="success"),
        _base_facts(occurred_at="not-a-datetime"),
    ):
        with pytest.raises(DiagnosticsProjectionError):
            build_diagnostic_record(bad, settings=settings)


# -- 8 KiB whole-record cap ---------------------------------------------------


def test_bounded_record_is_under_the_whole_record_cap(settings: Settings) -> None:
    record = build_diagnostic_record(
        _base_facts(
            client_request_id="a" * 128,
            endpoint_template="/v1/responses",
            route_pattern="gpt-4o",
            deployment_revision="r" * 128,
            error_param="input[1000000].max_output_tokens",
            positions={"namespace_index": 999999, "tool_index": 999999, "line": 999999, "column": 999999, "pos": 999999},
            counts={"count": 999999999, "limit": 999999999},
            limits={"max_output_tokens": 999999999, "max_input_tokens": 999999999, "context_window_tokens": 999999999},
            estimated_input_tokens=999999999,
            output_allowance_tokens=999999999,
            context_window_tokens=999999999,
        ),
        settings=settings,
    )
    assert len(_serialize_record(record)) <= DIAGNOSTIC_MAX_RECORD_BYTES


def test_over_cap_whole_record_payload_is_detected(settings: Settings) -> None:
    # The cap is a whole-record backstop: a payload over 8 KiB (beyond the
    # current field bounds) must be detected by the same canonical
    # serialization the service enforces.
    import dataclasses

    base = build_diagnostic_record(_base_facts(), settings=settings)
    oversized = dataclasses.replace(base, client_request_id="a" * 9000)
    assert len(_serialize_record(oversized)) > DIAGNOSTIC_MAX_RECORD_BYTES
    assert len(_serialize_record(base)) <= DIAGNOSTIC_MAX_RECORD_BYTES


def test_unsafe_deployment_revision_becomes_unavailable_not_dropped(settings: Settings) -> None:
    record = build_diagnostic_record(
        _base_facts(deployment_revision="operator revision with spaces"),
        settings=settings,
    )
    assert record.deployment_revision is None
    # the rest of the record is unaffected
    assert record.gateway_request_id == _base_facts()["gateway_request_id"]

    safe = build_diagnostic_record(
        _base_facts(deployment_revision="2026.10.29-rc1+build.7"),
        settings=settings,
    )
    assert safe.deployment_revision == "2026.10.29-rc1+build.7"


# -- client ID secret-alias detection ----------------------------------------


def _scope_with_headers(headers: list[tuple[bytes, bytes]]) -> dict[str, Any]:
    return {"headers": headers, "query_string": b""}


def test_client_id_equal_to_known_credentials_is_omitted(settings: Settings) -> None:
    scope = _scope_with_headers(
        [
            (b"authorization", b"Bearer bearer_canary_0123456789"),
            (b"x-api-key", b"header_secret_canary"),
            (b"cookie", b"session=session_secret_canary"),
            (b"proxy-authorization", b"Bearer proxy_secret_canary"),
        ]
    )
    masker, complete = build_client_id_masker(
        scope, accepted_prefixes=settings.get_gateway_key_accepted_prefixes()
    )
    assert complete is True
    assert masker is not None
    for secret in (
        "bearer_canary_0123456789",
        "header_secret_canary",
        "session_secret_canary",
        "proxy_secret_canary",
    ):
        record = build_diagnostic_record(
            _base_facts(client_request_id=secret),
            settings=settings,
            client_id_masker=masker,
        )
        assert record.client_request_id is None
        assert record.client_id_unavailable_reason == "secret_alias"


def test_embedded_credential_alias_is_omitted(settings: Settings) -> None:
    scope = _scope_with_headers([(b"cookie", b"session=session_secret_canary")])
    masker, complete = build_client_id_masker(
        scope, accepted_prefixes=settings.get_gateway_key_accepted_prefixes()
    )
    assert complete is True
    record = build_diagnostic_record(
        _base_facts(client_request_id="prefix-session_secret_canary-suffix"),
        settings=settings,
        client_id_masker=masker,
    )
    assert record.client_request_id is None
    assert record.client_id_unavailable_reason == "secret_alias"


def test_known_credential_shape_anywhere_is_omitted(settings: Settings) -> None:
    # No headers needed: the existing known-shape redaction catches an
    # embedded provider-key-shaped value anywhere in the ID.
    record = build_diagnostic_record(
        _base_facts(client_request_id="xx-sk-proj-abcdefgh1234-suffix"),
        settings=settings,
    )
    assert record.client_request_id is None
    assert record.client_id_unavailable_reason == "secret_alias"


def test_gateway_prefix_and_absent_and_unsafe_ids(settings: Settings) -> None:
    prefix = settings.GATEWAY_KEY_PREFIX
    prefixed = build_diagnostic_record(
        _base_facts(client_request_id=prefix + "abc123"), settings=settings
    )
    assert prefixed.client_request_id is None
    assert prefixed.client_id_unavailable_reason == "secret_alias"

    absent = build_diagnostic_record(
        _base_facts(client_request_id=None), settings=settings
    )
    assert absent.client_request_id is None
    assert absent.client_id_unavailable_reason == "absent"

    unsafe = build_diagnostic_record(
        _base_facts(client_request_id="bad id with spaces"), settings=settings
    )
    assert unsafe.client_request_id is None
    assert unsafe.client_id_unavailable_reason == "unsafe"

    legit = build_diagnostic_record(
        _base_facts(client_request_id="req-legit-id"), settings=settings
    )
    assert legit.client_request_id == "req-legit-id"
    assert legit.client_id_unavailable_reason is None


def test_credential_query_alias_is_omitted_without_storing_the_query(settings: Settings) -> None:
    scope = {
        "headers": [],
        "query_string": b"api_key=query_secret_canary",
    }
    masker, complete = build_client_id_masker(
        scope, accepted_prefixes=settings.get_gateway_key_accepted_prefixes()
    )
    assert complete is True
    assert masker is not None
    record = build_diagnostic_record(
        _base_facts(client_request_id="query_secret_canary"),
        settings=settings,
        client_id_masker=masker,
    )
    assert record.client_request_id is None
    assert record.client_id_unavailable_reason == "secret_alias"


def test_masker_discovery_is_fail_closed_never_partial(settings: Settings) -> None:
    # 33 distinct cookie values exceed the 32-value bound: discovery is
    # incomplete, so the client ID is omitted fail-closed (never silently
    # masked only a subset).
    cookie_value = b";".join(
        f"c{n}=cookie_secret_canary_{n}".encode() for n in range(33)
    )
    scope = _scope_with_headers([(b"cookie", cookie_value)])
    masker, complete = build_client_id_masker(
        scope, accepted_prefixes=settings.get_gateway_key_accepted_prefixes()
    )
    assert complete is False
    assert masker is None
    record = build_diagnostic_record(
        _base_facts(client_request_id="cookie_secret_canary_32"),
        settings=settings,
        client_id_masker=masker,
        client_id_mask_complete=False,
    )
    assert record.client_request_id is None
    assert record.client_id_unavailable_reason == "secret_alias"


def test_oversized_credential_value_fails_closed(settings: Settings) -> None:
    huge = b"x" * 600
    scope = _scope_with_headers([(b"x-api-key", huge)])
    masker, complete = build_client_id_masker(
        scope, accepted_prefixes=settings.get_gateway_key_accepted_prefixes()
    )
    assert complete is False
    assert masker is None


def test_no_credentials_yields_no_masker_but_complete(settings: Settings) -> None:
    scope = _scope_with_headers([(b"accept", b"application/json")])
    masker, complete = build_client_id_masker(
        scope, accepted_prefixes=settings.get_gateway_key_accepted_prefixes()
    )
    assert complete is True
    assert masker is None


# -- best-effort write outcomes ----------------------------------------------


class _RecordingSession:
    def __init__(self) -> None:
        self.committed = 0

    async def __aenter__(self) -> "_RecordingSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _RecordingFactory:
    def __init__(self) -> None:
        self.session = _RecordingSession()

    def __call__(self) -> _RecordingSession:
        return self.session


def test_disabled_recording_never_touches_the_store() -> None:
    settings = Settings(_env_file=None)
    factory = _RecordingFactory()
    service = RequestDiagnosticsService(settings=settings, session_factory=factory)  # type: ignore[arg-type]

    async def _run() -> DiagnosticsWriteOutcome:
        return await service.record_failure(_base_facts())

    outcome = _run_sync(_run())
    assert outcome is DiagnosticsWriteOutcome.DROPPED_DISABLED
    assert factory.session.committed == 0


def _run_sync(coro: Any) -> Any:
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# -- gateway resolution-boundary route facts ----------------------------------


def test_resolution_boundary_records_route_facts_before_capability_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The trusted resolved route is noted on the scope BEFORE capability
    enforcement, so pre-stream rejections cite the actually resolved route
    (no request-model inference)."""
    import asyncio

    from types import SimpleNamespace

    from slaif_gateway.schemas.routing import RouteResolutionResult
    from slaif_gateway.services import responses_gateway as gateway
    from slaif_gateway.services.request_diagnostics import get_scope_diagnostics

    route = RouteResolutionResult(
        requested_model="m",
        resolved_model="m",
        provider="openrouter",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="m",
        priority=1,
    )

    class _FakeRouteService:
        def __init__(self, **kwargs: object) -> None:
            return None

        async def resolve_model(self, model: str, key: object, *, endpoint: str) -> object:
            return route

    async def _fake_session_iterator(request: object) -> object:
        yield object()

    monkeypatch.setattr(gateway, "RouteResolutionService", _FakeRouteService)
    monkeypatch.setattr(
        gateway, "_db_session_iterator", lambda request: _fake_session_iterator(request)
    )

    scope: dict = {"state": {}}
    request = SimpleNamespace(scope=scope)

    with pytest.raises(Exception):
        asyncio.run(
            gateway._resolve_responses_route(
                authenticated_key=object(),
                effective_model="m",
                endpoint="responses",
                streaming_requested=False,
                text_format_type=None,
                function_tools_requested=True,
                custom_tools_requested=False,
                image_input_requested=False,
                file_input_requested=False,
                input_token_count_requested=False,
                stored_responses_requested=False,
                previous_response_id_requested=False,
                compact_requested=False,
                conversations_requested=False,
                request=request,
            )
        )
    facts = get_scope_diagnostics(scope)
    assert facts is not None
    assert facts["route_id"] == route.route_id
    assert facts["route_pattern"] == "m"


# -- route-limit diagnostic facts (operator ceiling attribution) --------------


def _codex_limit_policy(settings: Settings | None = None) -> object:
    from slaif_gateway.modules.clients.codex_0147 import CODEX_0147_POLICY_SPEC
    from slaif_gateway.services.responses_request_policy import ResponsesRequestPolicy

    return ResponsesRequestPolicy(settings or Settings(), client_spec=CODEX_0147_POLICY_SPEC)


def _codex_route_capabilities(**limits: object) -> dict[str, object]:
    from slaif_gateway.services.responses_route_capabilities import (
        default_responses_capabilities,
    )

    responses = default_responses_capabilities()
    responses.update(
        {
            "codex_request_envelope": True,
            "codex_client_tools": True,
            "codex_streaming_tool_events": True,
            "codex_encrypted_reasoning_replay": True,
        }
    )
    return {
        "responses": responses,
        "codex_limits": {
            "context_window_tokens": 1_050_000,
            "default_max_output_tokens": 32_768,
            "max_output_tokens": 128_000,
            **limits,
        },
    }


def _codex_policy_result(
    settings: Settings | None = None, *, max_output_tokens: int | None = None
) -> object:
    body: dict[str, object] = {
        "model": "gpt-5.6-sol",
        "input": "bounded",
        "prompt_cache_key": "safe-session-key",
    }
    if max_output_tokens is not None:
        body["max_output_tokens"] = max_output_tokens
    return _codex_limit_policy(settings).apply(
        body,
        allow_codex_request_envelope=True,
        allow_codex_extended_limits=True,
    )


def test_operator_output_ceiling_recorded_when_it_is_the_rejecting_ceiling() -> None:
    from slaif_gateway.services.responses_request_policy import (
        ResponsesRequestPolicyError,
        apply_codex_route_limits,
    )

    settings = Settings(CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS=100_000)
    # route max is 128_000, request asks 120_000: within the route max but
    # beyond the operator ceiling, so the operator ceiling rejects.
    with pytest.raises(ResponsesRequestPolicyError) as excinfo:
        apply_codex_route_limits(
            _codex_policy_result(max_output_tokens=120_000),
            route_capabilities=_codex_route_capabilities(),
            settings=settings,
        )
    facts = excinfo.value.diagnostics_facts
    assert facts is not None
    # the distinct operator ceiling is retained under its own finite key,
    # alongside the (non-rejecting) route max
    assert facts["limits"]["max_output_tokens"] == 128_000
    assert facts["limits"]["absolute_max_output_tokens"] == 100_000


def test_route_default_beyond_operator_ceiling_records_operator_ceiling() -> None:
    from slaif_gateway.services.responses_request_policy import (
        ResponsesRequestPolicyError,
        apply_codex_route_limits,
    )

    settings = Settings(CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS=30_000)
    with pytest.raises(ResponsesRequestPolicyError) as excinfo:
        apply_codex_route_limits(
            _codex_policy_result(),
            route_capabilities=_codex_route_capabilities(default_max_output_tokens=40_000),
            settings=settings,
        )
    facts = excinfo.value.diagnostics_facts
    assert facts is not None
    assert facts["limits"]["absolute_max_output_tokens"] == 30_000
    assert facts["limits"]["max_output_tokens"] == 128_000


def test_route_max_rejection_does_not_claim_operator_ceiling() -> None:
    from slaif_gateway.services.responses_request_policy import (
        ResponsesRequestPolicyError,
        apply_codex_route_limits,
    )

    settings = Settings(CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS=200_000)
    # request beyond the route max (128_000) but below the operator ceiling:
    # the route max is the rejecting ceiling, so no operator-ceiling fact.
    # The policy itself must be built with the higher ceiling so it does not
    # reject first.
    policy_result = _codex_policy_result(settings, max_output_tokens=150_000)
    with pytest.raises(ResponsesRequestPolicyError) as excinfo:
        apply_codex_route_limits(
            policy_result,
            route_capabilities=_codex_route_capabilities(),
            settings=settings,
        )
    facts = excinfo.value.diagnostics_facts
    assert facts is not None
    assert facts["limits"]["max_output_tokens"] == 128_000
    assert "absolute_max_output_tokens" not in facts["limits"]
