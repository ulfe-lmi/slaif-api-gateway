"""Unit tests for the read-only effective key-policy inspection service."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey, ModelRoute, ProviderConfig
from slaif_gateway.modules.clients.codex_0162 import CODEX_0162_V1_CLIENT_MODULE
from slaif_gateway.services.chat_completion_route_capabilities import (
    CHAT_CAPABILITY_TEXT,
    CHAT_COMPLETIONS_CAPABILITIES_KEY,
)
from slaif_gateway.services.key_policy_inspection import (
    KeyPolicyInspectionContext,
    build_inspection_key,
    build_key_policy_inspection,
    explain_model_route_access,
    safe_calibration_metadata_projection,
    safe_provider_policy_projection,
    safe_responses_policy_projection,
)
from slaif_gateway.services.endpoint_policy import canonical_endpoint_id

NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)

KNOWN_SECRET_CANARY = "SyntheticCanary197b" * 3
KNOWN_PROVIDER_SECRET = f"sk-proj-{KNOWN_SECRET_CANARY}"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _gateway_key(**overrides: object) -> GatewayKey:
    base: dict[str, object] = {
        "public_key_id": "publicid1234567890abcdefghijkl",
        "token_hash": "deadbeef",
        "owner_id": uuid.uuid4(),
        "valid_from": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=30),
        "status": "active",
        "metadata_json": {},
        "allowed_models": ["model-a", "model-b"],
        "allowed_endpoints": ["/v1/models", "/v1/chat/completions"],
        "allow_all_models": False,
        "allow_all_endpoints": False,
        "key_purpose": "standard",
        "capability_policy_mode": "standard",
        "created_at": NOW - timedelta(hours=2),
        "updated_at": NOW - timedelta(hours=1),
        "calibration_metadata": {},
    }
    base.update(overrides)
    return GatewayKey(**base)  # type: ignore[arg-type]


def _route(
    requested_model: str,
    *,
    provider: str = "openai",
    enabled: bool = True,
    endpoint: str = "/v1/chat/completions",
    priority: int = 100,
    match_type: str = "exact",
    upstream_model: str | None = None,
    supports_streaming: bool = True,
    capabilities: dict[str, object] | None = None,
) -> ModelRoute:
    return ModelRoute(
        requested_model=requested_model,
        match_type=match_type,
        endpoint=endpoint,
        provider=provider,
        upstream_model=upstream_model or f"upstream-{requested_model}",
        priority=priority,
        enabled=enabled,
        visible_in_models=True,
        supports_streaming=supports_streaming,
        capabilities=capabilities or {},
    )


def _provider(provider: str, *, enabled: bool = True) -> ProviderConfig:
    return ProviderConfig(
        provider=provider,
        display_name=provider.title(),
        kind="openai_compatible",
        base_url=f"https://canary-{provider}.example.invalid/v1",
        api_key_env_var=f"CANARY_{provider.upper()}_API_KEY",
        enabled=enabled,
    )


class _FakeModelRoutes:
    def __init__(self, routes: list[ModelRoute]) -> None:
        self._routes = routes

    async def list_model_routes(self, *, endpoint: str | None = None, limit: int = 100):
        rows = [
            route
            for route in self._routes
            if endpoint is None or route.endpoint == endpoint
        ]
        return rows[:limit]

    async def list_visible_model_routes(self, *, endpoint: str | None = None):
        return [r for r in self._routes if r.enabled][:100]


class _FakeProviderConfigs:
    def __init__(self, providers: list[ProviderConfig]) -> None:
        self._providers = providers

    async def list_provider_configs(self, **kwargs: object):
        return list(self._providers)


def _context(
    routes: list[ModelRoute], providers: list[ProviderConfig]
) -> KeyPolicyInspectionContext:
    return KeyPolicyInspectionContext(
        model_routes=_FakeModelRoutes(routes),
        provider_configs=_FakeProviderConfigs(providers),
    )


def _explain(
    key: GatewayKey,
    *,
    model: str,
    endpoint: str,
    context: KeyPolicyInspectionContext,
    now: datetime | None = None,
    **settings: object,
) -> dict[str, object]:
    return asyncio.run(
        explain_model_route_access(
            gateway_key=key,
            settings=_settings(**settings),
            requested_model=model,
            endpoint=endpoint,
            context=context,
            now=now or NOW,
        )
    )


# --- build_inspection_key (parity of derivation, no authentication) ----------


def test_inspection_key_uses_scalar_rate_columns_and_metadata_window() -> None:
    key = _gateway_key(
        rate_limit_requests_per_minute=3,
        rate_limit_tokens_per_minute=None,
        max_concurrent_requests=1,
        metadata_json={"rate_limit_policy": {"window_seconds": 10}},
    )
    inspection = build_inspection_key(gateway_key=key, settings=_settings())
    assert inspection.rate_limit_policy == {
        "requests_per_minute": 3,
        "tokens_per_minute": None,
        "max_concurrent_requests": 1,
        "window_seconds": 10,
    }


def test_inspection_key_bool_window_never_becomes_window() -> None:
    key = _gateway_key(metadata_json={"rate_limit_policy": {"window_seconds": True}})
    inspection = build_inspection_key(gateway_key=key, settings=_settings())
    assert inspection.rate_limit_policy["window_seconds"] is None


def test_inspection_key_malformed_stored_lazy_never_grants_waiting() -> None:
    key = _gateway_key(
        metadata_json={
            "lazy_throttling_policy": {
                "mode": "wait",
                "max_wait_seconds": 1.5,
                "max_waiting_requests": 2,
            }
        }
    )
    inspection = build_inspection_key(gateway_key=key, settings=_settings())
    assert inspection.lazy_throttling is None


def test_inspection_key_trusted_calibration_promotes_allow_all() -> None:
    key = _gateway_key(
        key_purpose="trusted_calibration",
        capability_policy_mode="trusted_calibration_discovery",
    )
    inspection = build_inspection_key(gateway_key=key, settings=_settings())
    assert inspection.allow_all_models is True
    assert inspection.allow_all_endpoints is True


def test_inspection_key_preserves_deny_all_provider_list() -> None:
    key = _gateway_key(metadata_json={"allowed_providers": []})
    inspection = build_inspection_key(gateway_key=key, settings=_settings())
    assert inspection.allowed_providers == ()
    unrestricted = build_inspection_key(
        gateway_key=_gateway_key(metadata_json={}), settings=_settings()
    )
    assert unrestricted.allowed_providers is None


# --- build_key_policy_inspection ---------------------------------------------


def test_effective_rate_sources_key_deployment_and_none() -> None:
    key = _gateway_key(rate_limit_requests_per_minute=1, max_concurrent_requests=None)
    report = build_key_policy_inspection(
        gateway_key=key,
        settings=_settings(DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE=500),
        now=NOW,
    )
    rates = report["rate_limits"]
    assert rates["requests_per_window"] == {
        "configured": 1,
        "effective": 1,
        "source": "key",
    }
    assert rates["tokens_per_window"] == {
        "configured": None,
        "effective": 500,
        "source": "deployment",
    }
    assert rates["concurrency"] == {
        "configured": None,
        "effective": None,
        "source": "none",
    }
    assert rates["count_semantics"] == "counts per selected window"


def test_window_member_source_and_ten_second_window_rendering() -> None:
    key = _gateway_key(
        rate_limit_requests_per_minute=1,
        metadata_json={"rate_limit_policy": {"window_seconds": 10}},
    )
    report = build_key_policy_inspection(gateway_key=key, settings=_settings(), now=NOW)
    window = report["rate_limits"]["window_seconds"]
    assert window == {"configured": 10, "effective": 10, "source": "key"}
    assert report["rate_limits"]["requests_per_window"]["effective"] == 1


def test_window_defaults_to_sixty_when_unconfigured() -> None:
    key = _gateway_key()
    report = build_key_policy_inspection(gateway_key=key, settings=_settings(), now=NOW)
    assert report["rate_limits"]["window_seconds"] == {
        "configured": None,
        "effective": 60,
        "source": "default",
    }


def test_inherited_rate_with_unlimited_quota_warns() -> None:
    key = _gateway_key(request_limit_total=None, token_limit_total=None)
    report = build_key_policy_inspection(
        gateway_key=key,
        settings=_settings(
            DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE=10,
            DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE=20,
        ),
        now=NOW,
    )
    warnings = report["rate_limits"]["warnings"]
    assert len(warnings) == 2
    assert any("request" in w for w in warnings)
    assert any("token" in w for w in warnings)


def test_no_warning_when_quota_configured_or_rate_key_owned() -> None:
    limited = _gateway_key(
        rate_limit_requests_per_minute=1,
        request_limit_total=10,
        token_limit_total=None,
    )
    report = build_key_policy_inspection(
        gateway_key=limited,
        settings=_settings(DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE=20),
        now=NOW,
    )
    assert report["rate_limits"]["warnings"] == [
        "Inherited deployment token rate still applies despite an unlimited "
        "lifetime token quota."
    ]
    unlimited_but_no_default = _gateway_key(request_limit_total=None)
    report2 = build_key_policy_inspection(gateway_key=unlimited_but_no_default, settings=_settings(), now=NOW)
    assert report2["rate_limits"]["warnings"] == []


def test_quotas_unlimited_and_remaining_math() -> None:
    key = _gateway_key(
        cost_limit_eur=None,
        token_limit_total=1000,
        request_limit_total=100,
        cost_used_eur=Decimal("1.5"),
        tokens_used_total=250,
        requests_used_total=10,
        cost_reserved_eur=Decimal("0.5"),
        tokens_reserved_total=50,
        requests_reserved_total=2,
    )
    quotas = build_key_policy_inspection(
        gateway_key=key, settings=_settings(), now=NOW
    )["quotas"]
    assert quotas["cost_eur"] == {
        "configured": None,
        "unlimited": True,
        "used": "1.5",
        "reserved": "0.5",
        "remaining": None,
    }
    assert quotas["tokens"]["remaining"] == 700
    assert quotas["requests"]["remaining"] == 88


def test_lazy_states_absent_reject_invalid_wait() -> None:
    settings = _settings()
    absent = build_key_policy_inspection(
        gateway_key=_gateway_key(metadata_json={}), settings=settings, now=NOW
    )["lazy_throttling"]
    assert absent["stored_state"] == "absent"
    assert absent["mode"] == "reject"
    assert absent["source"] == "default"

    reject = build_key_policy_inspection(
        gateway_key=_gateway_key(
            metadata_json={"lazy_throttling_policy": {"mode": "reject"}}
        ),
        settings=settings,
        now=NOW,
    )["lazy_throttling"]
    assert reject["stored_state"] == "reject-configured"
    assert reject["mode"] == "reject"
    # A VALID stored reject is KEY-configured (source key), not the default.
    assert reject["source"] == "key"

    invalid = build_key_policy_inspection(
        gateway_key=_gateway_key(
            metadata_json={
                "lazy_throttling_policy": {
                    "mode": "wait",
                    "max_wait_seconds": -5,
                    "max_waiting_requests": 2,
                }
            }
        ),
        settings=settings,
        now=NOW,
    )["lazy_throttling"]
    assert invalid["stored_state"] == "invalid-stored"
    assert invalid["mode"] == "reject"

    waiting = build_key_policy_inspection(
        gateway_key=_gateway_key(
            metadata_json={
                "lazy_throttling_policy": {
                    "mode": "wait",
                    "max_wait_seconds": 30,
                    "max_waiting_requests": 2,
                }
            }
        ),
        settings=settings,
        now=NOW,
    )["lazy_throttling"]
    assert waiting["stored_state"] == "wait-configured"
    assert waiting["mode"] == "wait"
    assert waiting["max_wait_seconds"] == 30
    assert waiting["source"] == "key"
    assert waiting["applicable_endpoints"] == [
        "/v1/chat/completions",
        "/v1/responses",
    ]


def test_stored_wait_above_installation_ceiling_is_invalid_not_granted() -> None:
    key = _gateway_key(
        metadata_json={
            "lazy_throttling_policy": {
                "mode": "wait",
                "max_wait_seconds": 30,
                "max_waiting_requests": 2,
            }
        }
    )
    report = build_key_policy_inspection(
        gateway_key=key,
        settings=_settings(LAZY_THROTTLING_MAX_WAIT_SECONDS=20),
        now=NOW,
    )["lazy_throttling"]
    assert report["stored_state"] == "invalid-stored"
    assert report["mode"] == "reject"


def test_status_notes_for_blocked_states() -> None:
    suspended = build_key_policy_inspection(
        gateway_key=_gateway_key(status="suspended"), settings=_settings(), now=NOW
    )["key"]
    assert suspended["status_note"] == "suspended"

    expired = build_key_policy_inspection(
        gateway_key=_gateway_key(
            valid_from=NOW - timedelta(days=2), valid_until=NOW - timedelta(days=1)
        ),
        settings=_settings(),
        now=NOW,
    )["key"]
    assert expired["status_note"] == "expired"

    not_yet = build_key_policy_inspection(
        gateway_key=_gateway_key(
            valid_from=NOW + timedelta(days=1), valid_until=NOW + timedelta(days=2)
        ),
        settings=_settings(),
        now=NOW,
    )["key"]
    assert not_yet["status_note"] == "not-yet-valid"

    fenced = build_key_policy_inspection(
        gateway_key=_gateway_key(external_tool_fence_state="active"),
        settings=_settings(),
        now=NOW,
    )["key"]
    assert fenced["status_note"] == "external-tool-fence-active"

    active = build_key_policy_inspection(
        gateway_key=_gateway_key(), settings=_settings(), now=NOW
    )["key"]
    assert active["status_note"] is None


def test_redis_configuration_is_configuration_not_health() -> None:
    report = build_key_policy_inspection(
        gateway_key=_gateway_key(), settings=_settings(), now=NOW
    )["redis_configuration"]
    assert report["enabled"] is False
    assert report["fail_closed"] is False  # non-production default
    assert report["has_limits"] is False
    assert "configuration" in report["note"]

    fail_closed = build_key_policy_inspection(
        gateway_key=_gateway_key(rate_limit_requests_per_minute=1),
        settings=_settings(
            ENABLE_REDIS_RATE_LIMITS=True,
            REDIS_URL="redis://127.0.0.1:6379/0",
            RATE_LIMIT_FAIL_CLOSED=True,
        ),
        now=NOW,
    )["redis_configuration"]
    assert fail_closed["enabled"] is True
    assert fail_closed["fail_closed"] is True
    assert fail_closed["has_limits"] is True

    # Non-production default is fail-OPEN unless explicitly overridden.
    dev = build_key_policy_inspection(
        gateway_key=_gateway_key(rate_limit_requests_per_minute=1),
        settings=_settings(
            ENABLE_REDIS_RATE_LIMITS=True, REDIS_URL="redis://127.0.0.1:6379/0"
        ),
        now=NOW,
    )["redis_configuration"]
    assert dev["enabled"] is True
    assert dev["fail_closed"] is False


def test_responses_profile_absent_state() -> None:
    absent = build_key_policy_inspection(
        gateway_key=_gateway_key(), settings=_settings(), now=NOW
    )["responses_profile"]
    assert absent["policy_state"] == "absent"
    assert absent["client_module"] == {"state": "absent"}
    assert absent["capabilities"] == []
    assert absent["local_tool_types"] == []


def test_responses_profile_valid_grants_and_module_identity() -> None:
    from slaif_gateway.modules.clients.codex_0162 import (
        CODEX_0162_CLIENT_MODULE,
        CODEX_0162_CLIENT_MODULE_ID,
    )

    profile = build_key_policy_inspection(
        gateway_key=_gateway_key(
            metadata_json={
                "responses_policy": {
                    "version": 1,
                    "allowed_capabilities": ["function_tools", "custom_tools"],
                    "allowed_local_tool_types": ["function", "custom"],
                    "client_module": {
                        "id": CODEX_0162_CLIENT_MODULE_ID,
                        "version": CODEX_0162_CLIENT_MODULE.module_version,
                        "fixture_sha256": CODEX_0162_CLIENT_MODULE.fixture_sha256,
                    },
                }
            }
        ),
        settings=_settings(),
        now=NOW,
    )["responses_profile"]
    assert profile["policy_state"] == "valid"
    assert profile["capabilities"] == ["custom_tools", "function_tools"]
    assert profile["local_tool_types"] == ["function", "custom"]
    assert profile["client_module"]["state"] == "bound"
    assert profile["client_module"]["id"] == CODEX_0162_CLIENT_MODULE_ID
    assert (
        profile["client_module"]["version"] == CODEX_0162_CLIENT_MODULE.module_version
    )


def test_responses_profile_unknown_module_is_invalid_without_canary_echo() -> None:
    canary = "PRIVATE_UNSUPPORTED_METADATA_197"
    report = build_key_policy_inspection(
        gateway_key=_gateway_key(
            metadata_json={
                "responses_policy": {
                    "version": 1,
                    "client_module": {
                        "id": canary,
                        "version": canary,
                        "fixture_sha256": canary,
                    },
                }
            }
        ),
        settings=_settings(),
        now=NOW,
    )
    profile = report["responses_profile"]
    assert profile["policy_state"] == "invalid"
    assert profile["client_module"]["state"] == "unavailable"
    assert profile["capabilities"] == []
    assert canary not in str(report)


def test_responses_profile_stale_module_pin_is_unavailable() -> None:
    profile = build_key_policy_inspection(
        gateway_key=_gateway_key(
            metadata_json={
                "responses_policy": {
                    "version": 1,
                    "client_module": dict(CODEX_0162_V1_CLIENT_MODULE),
                }
            }
        ),
        settings=_settings(),
        now=NOW,
    )["responses_profile"]
    assert profile["policy_state"] == "invalid"
    assert profile["client_module"]["state"] == "unavailable"


def test_provider_policy_preserves_none_and_deny_all() -> None:
    unrestricted = build_key_policy_inspection(
        gateway_key=_gateway_key(metadata_json={}), settings=_settings(), now=NOW
    )["allowlists"]
    assert unrestricted["state"] == "unrestricted"
    assert unrestricted["allowed_providers"] is None
    assert unrestricted["allow_all_providers"] is True

    deny_all = build_key_policy_inspection(
        gateway_key=_gateway_key(metadata_json={"allowed_providers": []}),
        settings=_settings(),
        now=NOW,
    )["allowlists"]
    assert deny_all["state"] == "deny-all"
    assert deny_all["allowed_providers"] == []
    assert deny_all["allow_all_providers"] is False

    allow_list = build_key_policy_inspection(
        gateway_key=_gateway_key(metadata_json={"allowed_providers": ["openai"]}),
        settings=_settings(),
        now=NOW,
    )["allowlists"]
    assert allow_list["state"] == "allow-list"
    assert allow_list["allowed_providers"] == ["openai"]


def test_provider_policy_malformed_member_never_echoed() -> None:
    canary = "PRIVATE_UNSUPPORTED_METADATA_197"
    report = build_key_policy_inspection(
        gateway_key=_gateway_key(
            metadata_json={"allowed_providers": [{"private": canary}]}
        ),
        settings=_settings(),
        now=NOW,
    )
    allowlists = report["allowlists"]
    assert allowlists["state"] == "invalid"
    assert allowlists["allowed_providers"] is None
    assert allowlists["allow_all_providers"] is False
    assert canary not in str(report)


def test_report_never_dumps_provider_or_secret_material() -> None:
    key = _gateway_key(metadata_json={"allowed_providers": ["openai"]})
    text = str(build_key_policy_inspection(gateway_key=key, settings=_settings(), now=NOW))
    assert "provider_base_url" not in text
    assert "api_key_env_var" not in text
    assert "CANARY_" not in text


def test_provider_policy_known_secret_shape_redacted_not_echoed() -> None:
    """KNOWN auth/provider secret shapes are redacted at the display boundary."""
    report = build_key_policy_inspection(
        gateway_key=_gateway_key(
            metadata_json={"allowed_providers": [KNOWN_PROVIDER_SECRET, "openai"]}
        ),
        settings=_settings(),
        now=NOW,
    )
    allowlists = report["allowlists"]
    assert allowlists["state"] == "allow-list"
    assert allowlists["allowed_providers"] == ["***", "openai"]
    assert KNOWN_SECRET_CANARY not in str(report)


def test_responses_policy_projection_helper_states() -> None:
    assert safe_responses_policy_projection(None) is None
    assert safe_responses_policy_projection({"version": 1}) == {"version": 1}
    assert safe_responses_policy_projection(
        {"version": 1, "unsupported_field": "x"}
    ) == {"state": "invalid"}
    assert safe_responses_policy_projection("junk") == {"state": "invalid"}
    # valid block with a free-form note: known secret shapes redacted
    noted = safe_responses_policy_projection(
        {"version": 1, "notes": f"note {KNOWN_PROVIDER_SECRET} end"}
    )
    assert noted == {"version": 1, "notes": "note *** end"}
    legit = safe_responses_policy_projection({"version": 1, "notes": "legit note"})
    assert legit == {"version": 1, "notes": "legit note"}


def test_provider_policy_projection_helper_redacts_known_shapes() -> None:
    projected = safe_provider_policy_projection(
        {"allowed_providers": [KNOWN_PROVIDER_SECRET, "openai"]}
    )
    assert projected == {
        "state": "allow-list",
        "allowed_providers": ["***", "openai"],
        "allow_all_providers": False,
    }
    # legitimate members pass through unchanged
    assert safe_provider_policy_projection(
        {"allowed_providers": ["openai"]}
    ) == {
        "state": "allow-list",
        "allowed_providers": ["openai"],
        "allow_all_providers": False,
    }


def test_calibration_metadata_projection_known_members_only() -> None:
    assert safe_calibration_metadata_projection({}) == {}
    assert safe_calibration_metadata_projection("junk") == {}
    projected = safe_calibration_metadata_projection(
        {
            "creation_channel": "cli",
            "created_from": "admin_web",
            "operator_review_required": True,
            "secret_internal": KNOWN_SECRET_CANARY,
            "operator_review_required_alt": "yes",
        }
    )
    assert projected == {
        "creation_channel": "cli",
        "created_from": "admin_web",
        "operator_review_required": True,
    }
    assert KNOWN_SECRET_CANARY not in str(projected)
    # wrong-type known members are dropped, never coerced
    assert safe_calibration_metadata_projection(
        {"creation_channel": 5, "operator_review_required": "yes"}
    ) == {}
    # known secret shapes inside kept strings are redacted
    redacted = safe_calibration_metadata_projection(
        {"creation_channel": KNOWN_PROVIDER_SECRET}
    )
    assert redacted == {"creation_channel": "***"}
    assert KNOWN_SECRET_CANARY not in str(redacted)


def test_report_revoked_reason_preserved_and_known_shapes_redacted() -> None:
    normal = build_key_policy_inspection(
        gateway_key=_gateway_key(
            status="revoked", revoked_at=NOW, revoked_reason="quota breach"
        ),
        settings=_settings(),
        now=NOW,
    )
    assert normal["key"]["revoked_reason"] == "quota breach"

    secret = f"bad {KNOWN_PROVIDER_SECRET}"
    report = build_key_policy_inspection(
        gateway_key=_gateway_key(
            status="revoked", revoked_at=NOW, revoked_reason=secret
        ),
        settings=_settings(),
        now=NOW,
    )
    assert report["key"]["revoked_reason"] == "bad ***"
    assert KNOWN_SECRET_CANARY not in str(report)


# --- canonical_endpoint_id -----------------------------------------------------


def test_canonical_endpoint_id_aliases() -> None:
    assert canonical_endpoint_id("/v1/chat/completions") == "chat.completions"
    assert canonical_endpoint_id("chat.completions") == "chat.completions"
    assert canonical_endpoint_id("POST /v1/chat/completions") == "chat.completions"
    assert canonical_endpoint_id("get /v1/models") == "models.list"
    assert canonical_endpoint_id("/v1/responses") == "responses"
    assert canonical_endpoint_id("nope") is None
    assert canonical_endpoint_id("") is None


# --- explain_model_route_access -------------------------------------------------


def test_explain_resolved_with_safe_projection_only() -> None:
    key = _gateway_key(allowed_models=["model-a"], allowed_endpoints=["/v1/chat/completions"])
    context = _context(
        routes=[_route("model-a")], providers=[_provider("openai")]
    )
    report = _explain(key, model="model-a", endpoint="/v1/chat/completions", context=context)
    assert report["verdict"] == "resolved"
    resolution = report["resolution"]
    assert resolution["provider"] == "openai"
    assert resolution["route_match_type"] == "exact"
    assert resolution["supports_streaming"] is True
    text = str(report)
    assert "canary-openai" not in text
    assert "api_key_env_var" not in text
    assert "CANARY_OPENAI_API_KEY" not in text
    assert report["bounds"] == {
        "route_candidate_bound": 1000,
        "routes_examined": 1,
        "possible_unexamined_routes": False,
    }
    intersection = report["allowlist_intersection"]
    assert intersection["allowed_models_with_candidate_route"] == ["model-a"]
    assert report["key_state"] == {
        "status": "active",
        "status_note": None,
        "usable_for_requests": True,
    }
    assert report["capability_checks"]["base_request_supported"] is True


def test_explain_expired_and_fenced_keys_are_explicitly_blocked() -> None:
    context = _context(routes=[_route("model-a")], providers=[_provider("openai")])
    expired = _explain(
        _gateway_key(
            valid_from=NOW - timedelta(days=2), valid_until=NOW - timedelta(seconds=10)
        ),
        model="model-a",
        endpoint="/v1/chat/completions",
        context=context,
    )
    assert expired["verdict"] == "blocked"
    assert expired["blocker"] == "key-expired"
    assert expired["resolution"] is None
    assert expired["key_state"]["usable_for_requests"] is False

    fenced = _explain(
        _gateway_key(external_tool_fence_state="held"),
        model="model-a",
        endpoint="/v1/chat/completions",
        context=context,
    )
    assert fenced["blocker"] == "key-external-tool-fence-active"
    assert "not currently usable" in fenced["message"]

    suspended = _explain(
        _gateway_key(status="suspended"),
        model="model-a",
        endpoint="/v1/chat/completions",
        context=context,
    )
    assert suspended["blocker"] == "key-suspended"


def test_explain_route_missing_base_text_capability_is_blocked() -> None:
    key = _gateway_key(allowed_models=["model-a"])
    route = _route(
        "model-a",
        capabilities={CHAT_COMPLETIONS_CAPABILITIES_KEY: {CHAT_CAPABILITY_TEXT: False}},
    )
    context = _context(routes=[route], providers=[_provider("openai")])
    report = _explain(key, model="model-a", endpoint="/v1/chat/completions", context=context)
    assert report["verdict"] == "blocked"
    assert report["blocker"] == "route-capability-not-supported"
    assert report["capability_checks"]["base_request_supported"] is False
    assert (
        report["capability_checks"]["capability_error_code"]
        == "chat_capability_not_supported"
    )
    # Route facts remain truthful alongside the known capability blocker.
    assert report["resolution"]["provider"] == "openai"


def test_explain_disabled_provider_excluded_from_candidates() -> None:
    key = _gateway_key(allowed_models=["model-a"])
    context = _context(
        routes=[_route("model-a")], providers=[_provider("openai", enabled=False)]
    )
    report = _explain(key, model="model-a", endpoint="/v1/chat/completions", context=context)
    assert report["blocker"] == "provider-disabled"
    assert report["allowlist_intersection"]["allowed_models_with_candidate_route"] == []


def test_explain_prefix_route_matches_candidate_models() -> None:
    key = _gateway_key(allowed_models=["model-a"])
    context = _context(
        routes=[_route("model-", match_type="prefix")], providers=[_provider("openai")]
    )
    report = _explain(key, model="model-a", endpoint="/v1/chat/completions", context=context)
    assert report["verdict"] == "resolved"
    assert report["allowlist_intersection"]["allowed_models_with_candidate_route"] == [
        "model-a"
    ]


def test_explain_provider_deny_all_excluded_from_candidates() -> None:
    key = _gateway_key(
        allowed_models=["model-a"], metadata_json={"allowed_providers": []}
    )
    context = _context(routes=[_route("model-a")], providers=[_provider("openai")])
    report = _explain(key, model="model-a", endpoint="/v1/chat/completions", context=context)
    assert report["blocker"] == "provider-not-allowed-for-key"
    assert report["allowlist_intersection"]["allowed_models_with_candidate_route"] == []


def test_explain_required_example_three_allowed_one_enabled_route() -> None:
    key = _gateway_key(
        allowed_models=["model-a", "model-b", "model-c"],
        allowed_endpoints=["/v1/chat/completions"],
    )
    context = _context(
        routes=[
            _route("model-a"),
            _route("model-b", enabled=False),
            _route("model-c", enabled=False),
        ],
        providers=[_provider("openai")],
    )
    report = _explain(key, model="model-a", endpoint="/v1/chat/completions", context=context)
    intersection = report["allowlist_intersection"]
    assert intersection["allowed_models"] == ["model-a", "model-b", "model-c"]
    assert intersection["allowed_models_with_candidate_route"] == ["model-a"]
    assert report["verdict"] == "resolved"


def test_explain_model_not_allowed_for_key() -> None:
    key = _gateway_key(allowed_models=["model-a"])
    context = _context(routes=[_route("model-z")], providers=[_provider("openai")])
    report = _explain(key, model="model-z", endpoint="/v1/chat/completions", context=context)
    assert report["verdict"] == "blocked"
    assert report["blocker"] == "model-not-allowed-for-key"


def test_explain_only_disabled_route() -> None:
    key = _gateway_key(allowed_models=["model-a"])
    context = _context(
        routes=[_route("model-a", enabled=False)], providers=[_provider("openai")]
    )
    report = _explain(key, model="model-a", endpoint="/v1/chat/completions", context=context)
    assert report["blocker"] == "model-route-disabled"


def test_explain_model_not_found() -> None:
    key = _gateway_key(allowed_models=["model-a"])
    context = _context(routes=[], providers=[_provider("openai")])
    report = _explain(key, model="model-a", endpoint="/v1/chat/completions", context=context)
    assert report["blocker"] == "model-not-found"


def test_explain_provider_disabled() -> None:
    key = _gateway_key(allowed_models=["model-a"])
    context = _context(
        routes=[_route("model-a")], providers=[_provider("openai", enabled=False)]
    )
    report = _explain(key, model="model-a", endpoint="/v1/chat/completions", context=context)
    assert report["blocker"] == "provider-disabled"


def test_explain_provider_deny_all_key() -> None:
    key = _gateway_key(allowed_models=["model-a"], metadata_json={"allowed_providers": []})
    context = _context(routes=[_route("model-a")], providers=[_provider("openai")])
    report = _explain(key, model="model-a", endpoint="/v1/chat/completions", context=context)
    assert report["blocker"] == "provider-not-allowed-for-key"


def test_explain_ambiguous_routes() -> None:
    key = _gateway_key(allowed_models=["model-a"], allow_all_endpoints=True)
    context = _context(
        routes=[
            _route("model-a", provider="openai", priority=100),
            _route("model-a", provider="openrouter", priority=100),
        ],
        providers=[_provider("openai"), _provider("openrouter")],
    )
    report = _explain(key, model="model-a", endpoint="/v1/chat/completions", context=context)
    assert report["blocker"] == "ambiguous-route"


def test_explain_endpoint_not_allowed_stops_before_route_facts() -> None:
    key = _gateway_key(allowed_models=["model-a"], allowed_endpoints=["/v1/models"])
    context = _context(routes=[_route("model-a")], providers=[_provider("openai")])
    report = _explain(key, model="model-a", endpoint="/v1/chat/completions", context=context)
    assert report["verdict"] == "blocked"
    assert report["blocker"] == "endpoint-not-allowed"
    assert report["resolution"] is None


def test_explain_discovery_is_separately_authorized() -> None:
    key = _gateway_key(allowed_endpoints=["/v1/models"])
    context = _context(routes=[_route("model-a")], providers=[_provider("openai")])
    report = _explain(key, model="model-a", endpoint="/v1/models", context=context)
    assert report["verdict"] == "discovery-separately-authorized"
    assert report["endpoint_allowed"] is True
    assert "separately authorized" in report["message"]

    denied = _explain(
        _gateway_key(allowed_endpoints=["/v1/chat/completions"]),
        model="model-a",
        endpoint="/v1/models",
        context=context,
    )
    assert denied["verdict"] == "discovery-separately-authorized"
    assert denied["blocker"] == "endpoint-not-allowed"


def test_explain_unknown_endpoint() -> None:
    key = _gateway_key()
    context = _context(routes=[], providers=[])
    report = _explain(key, model="model-a", endpoint="/v1/batch", context=context)
    assert report["verdict"] == "not-evaluated"
    assert report["endpoint_known"] is False
    assert "unknown-endpoint" in report["unevaluated"]


def test_explain_payload_dependent_endpoint_not_evaluated() -> None:
    key = _gateway_key(allow_all_endpoints=True)
    context = _context(routes=[], providers=[])
    report = _explain(key, model="model-a", endpoint="/v1/audio/speech", context=context)
    assert report["verdict"] == "not-evaluated"
    assert report["endpoint_known"] is True
    assert "endpoint-payload-dependent" in report["unevaluated"]


def test_explain_allow_all_models_shows_finite_patterns() -> None:
    key = _gateway_key(allow_all_models=True, allowed_models=[], allow_all_endpoints=True)
    context = _context(
        routes=[
            _route("gpt-*", match_type="glob"),
            _route("model-a"),
        ],
        providers=[_provider("openai")],
    )
    report = _explain(key, model="model-a", endpoint="/v1/chat/completions", context=context)
    intersection = report["allowlist_intersection"]
    assert intersection["allowed_models"] == "all"
    assert intersection["candidate_route_patterns"] == ["gpt-*", "model-a"]
    assert "candidate" in intersection["note"].lower()


def test_explain_responses_endpoint_path() -> None:
    key = _gateway_key(
        allowed_models=["model-a"], allowed_endpoints=["/v1/responses"]
    )
    context = _context(
        routes=[
            _route(
                "model-a",
                endpoint="/v1/responses",
                capabilities={"responses": {"text": True, "stateless": True}},
            )
        ],
        providers=[_provider("openai")],
    )
    report = _explain(key, model="model-a", endpoint="/v1/responses", context=context)
    assert report["verdict"] == "resolved"
    assert report["endpoint_stable_id"] == "responses"
