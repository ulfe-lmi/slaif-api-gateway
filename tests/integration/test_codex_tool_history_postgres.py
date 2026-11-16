"""PostgreSQL qualification for the Codex positional tool-history lifecycle.

Objective 226-b secondary scope.  Exercises the public gateway entry
(``handle_response_create``) and the audited key-profile migration against
the real PostgreSQL fixture on the committed fixed runtime.  All
key/route/provider rows are synthetic test rows inside the rollback-only
session transaction; the exact rev-16 profile module is served from the
client-module registry by a test-scoped fixture with complete restoration.
"""

from __future__ import annotations

import copy
import json
import uuid
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AuditLog,
    CodexReplayReference,
    GatewayKey,
    QuotaReservation,
    UsageLedger,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.codex_replay import CodexReplayReferencesRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.modules.clients.codex_0162 import (
    CODEX_0162_CLIENT_MODULE_ID,
    build_codex_0162_client_module,
)
from slaif_gateway.modules.codex_profile_data import load_codex_profile_file
from slaif_gateway.modules.servers.local_coding_vllm.adapter import LocalCodingVLLMAdapter
from slaif_gateway.modules.servers.local_coding_vllm.codec import vllm_wire_name
from slaif_gateway.modules.servers.upstream_llm.adapter import ConfiguredUpstreamLLMAdapter
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.openai import ResponsesCreateRequest
from slaif_gateway.services import responses_gateway
from slaif_gateway.services.responses_gateway import handle_response_create
from slaif_gateway.services.codex_module_upgrade import (
    CodexModuleUpgradeError,
    migrate_codex_0162_key_profile,
)
from slaif_gateway.services.codex_replay_service import CodexReplayService
from slaif_gateway.services.responses_request_policy import CodexReplayRequestCandidate
from tests.unit.test_codex_tool_history_replay_wiring import (
    base_model,
    call,
    decl,
    fn,
    ns,
    notice,
    out,
    user,
)
from tests.unit.test_local_coding_vllm import CAPS as VLLM_CAPS
from tests.unit.test_upstream_llm_adapter import (
    capabilities as upstream_route_capabilities,
)

_PROFILE_DIR = Path(__file__).resolve().parents[2] / "app/slaif_gateway/modules/clients/profiles"
# The two consecutive shipped profiles under qualification: revision 15 is
# the previous production pin, revision 16 adds the positional tool-history
# dialect feature.  Digests are the canonical profile-data digests.
_PROFILE_REV15 = load_codex_profile_file(_PROFILE_DIR / "codex-0.167.0.json")
_PROFILE_REV16 = load_codex_profile_file(_PROFILE_DIR / "codex-0.167.1.json")

_REV15_VERSION = "15"
_REV15_DIGEST = "9634f95de985d8c06fd0b09af3358ae589a14b828d4d4c357d4f98bcafec6a5d"
_REV16_VERSION = "16"
_REV16_DIGEST = "cff9f7b56966eb2068fdbeb203fe04ac32890e34524200372c2d3f2a30e566ed"

assert _PROFILE_REV15.module_id == CODEX_0162_CLIENT_MODULE_ID
assert _PROFILE_REV15.revision == _REV15_VERSION
assert _PROFILE_REV15.digest == _REV15_DIGEST
assert _PROFILE_REV16.module_id == CODEX_0162_CLIENT_MODULE_ID
assert _PROFILE_REV16.revision == _REV16_VERSION
assert _PROFILE_REV16.digest == _REV16_DIGEST


@pytest.fixture
def rev16_client_module(monkeypatch: pytest.MonkeyPatch):
    """Serve the exact rev-16 profile module from the registry for one test.

    Swaps the registry backing entry (visible through the immutable proxy
    used by ``get_client_module``) and restores the prior entry, instance
    global, and bootstrap flag on teardown.  No process bootstrap is
    mutated or consumed.
    """
    from slaif_gateway.modules.clients import registry as client_registry

    module = build_codex_0162_client_module(_PROFILE_REV16)
    assert module.module_version == _REV16_VERSION
    assert module.fixture_sha256 == _REV16_DIGEST
    old_entry = client_registry._CLIENT_MODULE_REGISTRY_ENTRIES[
        CODEX_0162_CLIENT_MODULE_ID
    ]
    old_instance = client_registry.CODEX_0162_CLIENT_MODULE_INSTANCE
    old_bound = client_registry._CODEX_0162_BOOTSTRAP_BOUND
    client_registry._CLIENT_MODULE_REGISTRY_ENTRIES[
        CODEX_0162_CLIENT_MODULE_ID
    ] = module
    client_registry.CODEX_0162_CLIENT_MODULE_INSTANCE = module
    try:
        yield module
    finally:
        client_registry._CLIENT_MODULE_REGISTRY_ENTRIES[
            CODEX_0162_CLIENT_MODULE_ID
        ] = old_entry
        client_registry.CODEX_0162_CLIENT_MODULE_INSTANCE = old_instance
        client_registry._CODEX_0162_BOOTSTRAP_BOUND = old_bound


_HMAC_SECRET = "oap226-qualification-replay-hmac-secret"
_TTL_SECONDS = 86400


def _replay_settings() -> Settings:
    return Settings(
        APP_ENV="development",
        TOKEN_HMAC_SECRET=_HMAC_SECRET,
        ACTIVE_HMAC_KEY_VERSION="1",
        CODEX_REPLAY_REFERENCE_TTL_SECONDS=_TTL_SECONDS,
    )


def _pin(version: str, digest: str) -> dict[str, object]:
    return {
        "id": CODEX_0162_CLIENT_MODULE_ID,
        "version": version,
        "fixture_sha256": digest,
    }


def _responses_policy(pin: dict[str, object]) -> dict[str, object]:
    return {
        "version": 1,
        "allowed_capabilities": [
            "codex_request_envelope",
            "codex_client_tools",
            "codex_streaming_tool_events",
        ],
        "client_module": pin,
    }


async def _seed_key(
    session: AsyncSession, *, pin: dict[str, object], allowed_providers: tuple[str, ...]
) -> tuple[object, object, object]:
    """Create owner/cohort/key with non-default restrictions, limits, and usage."""
    unique = uuid.uuid4().hex
    now = datetime.now(UTC)
    owners = OwnersRepository(session)
    cohorts = CohortsRepository(session)
    keys = GatewayKeysRepository(session)
    owner = await owners.create_owner(
        name="Codex",
        surname="Qualification",
        email=f"codex-226b-{unique}@example.org",
    )
    cohort = await cohorts.create_cohort(name=f"codex-226b-{unique}")
    key = await keys.create_gateway_key_record(
        public_key_id=f"codex226b_{unique}",
        token_hash=uuid.uuid4().hex,
        owner_id=owner.id,
        cohort_id=cohort.id,
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(days=30),
        cost_limit_eur=Decimal("50.00"),
        token_limit_total=1_000_000,
        request_limit_total=10_000,
        rate_limit_requests_per_minute=60,
        rate_limit_tokens_per_minute=120_000,
        max_concurrent_requests=4,
        allow_all_models=False,
        allowed_models=["synthetic-codex-model"],
        allow_all_endpoints=False,
        allowed_endpoints=["/v1/responses"],
        metadata_json={
            "responses_policy": _responses_policy(pin),
            "allowed_providers": list(allowed_providers),
        },
    )
    # Pre-existing settled usage consistent with the ledger row seeded below.
    key.cost_used_eur = Decimal("7.250000000")
    key.tokens_used_total = 12_345
    key.requests_used_total = 9
    await session.flush()
    return owner, cohort, key


async def _seed_ledger(
    session: AsyncSession, *, key: object, owner: object, cohort: object, now: datetime
) -> object:
    usage = UsageLedgerRepository(session)
    return await usage.create_success_record(
        request_id=f"req-226b-{uuid.uuid4().hex}",
        gateway_key_id=key.id,
        owner_id=owner.id,
        cohort_id=cohort.id,
        endpoint="/v1/responses",
        provider="synthetic-native",
        started_at=now,
        finished_at=now,
        requested_model="synthetic-codex-model",
        resolved_model="synthetic-upstream",
        streaming=False,
        input_tokens=1_200,
        output_tokens=300,
        total_tokens=1_500,
        cached_tokens=400,
        actual_cost_eur=Decimal("0.007250000"),
        native_currency="EUR",
    )


def _seed_candidates(call_suffix: str) -> tuple[CodexReplayRequestCandidate, ...]:
    return (
        CodexReplayRequestCandidate(
            item_kind="function_call",
            item_id=f"fc_226b_{call_suffix}",
            call_id=f"call_226b_{call_suffix}",
            tool_namespace="mcp__codex_apps__space",
            tool_name="read",
        ),
        CodexReplayRequestCandidate(
            item_kind="reasoning",
            item_id=f"rs_226b_{call_suffix}",
            call_id=None,
            tool_namespace=None,
            tool_name=None,
        ),
    )


async def _seed_replay_refs(
    session: AsyncSession,
    *,
    settings: Settings,
    key: object,
    ledger: object,
    candidates: tuple[CodexReplayRequestCandidate, ...],
    route: object,
    now: datetime,
) -> int:
    service = CodexReplayService(
        repository=CodexReplayReferencesRepository(session),
        settings=settings,
    )
    return await service.persist_validated_references(
        candidates=candidates,
        gateway_key_id=key.id,
        usage_ledger_id=ledger.id,
        source_request_id=ledger.request_id,
        provider=route.provider,
        route_id=route.id,
        upstream_model=route.upstream_model,
        now=now,
    )


_KEY_SNAPSHOT_EXCLUDED = frozenset({"updated_at"})


async def _key_column_snapshot(session: AsyncSession, key_id: uuid.UUID) -> dict[str, object]:
    """Every GatewayKey column plus full metadata, except the client_module pin."""
    row = (
        await session.execute(select(GatewayKey).where(GatewayKey.id == key_id))
    ).scalar_one()
    columns = [
        column.key
        for column in sa_inspect(GatewayKey).columns
        if column.key not in _KEY_SNAPSHOT_EXCLUDED
    ]
    snapshot = {column: getattr(row, column) for column in columns}
    metadata = copy.deepcopy(dict(row.metadata_json))
    policy = metadata.get("responses_policy")
    if isinstance(policy, dict):
        policy.pop("client_module", None)
    snapshot["metadata_json"] = metadata
    return snapshot


async def _stored_pin(session: AsyncSession, key_id: uuid.UUID) -> dict[str, str]:
    row = (
        await session.execute(select(GatewayKey).where(GatewayKey.id == key_id))
    ).scalar_one()
    return dict(row.metadata_json["responses_policy"]["client_module"])


async def _ledger_facts(
    session: AsyncSession, key_id: uuid.UUID
) -> tuple[int, int, int, int, int, Decimal, tuple[object, ...]]:
    rows = list(
        (
            await session.execute(
                select(UsageLedger)
                .where(UsageLedger.gateway_key_id == key_id)
                .order_by(UsageLedger.started_at)
            )
        ).scalars()
    )
    return (
        len(rows),
        sum(row.input_tokens for row in rows),
        sum(row.output_tokens for row in rows),
        sum(row.total_tokens for row in rows),
        sum(row.cached_tokens for row in rows),
        sum((row.actual_cost_eur or Decimal("0")) for row in rows),
        tuple(
            sorted(
                (
                    row.request_id,
                    row.accounting_status,
                    row.success,
                    row.provider,
                    row.endpoint,
                    row.requested_model,
                    row.resolved_model,
                )
                for row in rows
            )
        ),
    )


async def _ref_fingerprints(
    session: AsyncSession, key_id: uuid.UUID
) -> tuple[tuple[object, ...], ...]:
    rows = list(
        (
            await session.execute(
                select(CodexReplayReference)
                .where(CodexReplayReference.gateway_key_id == key_id)
                .order_by(CodexReplayReference.created_at)
            )
        ).scalars()
    )
    return tuple(
        sorted(
            (
                row.item_kind,
                row.item_id_hmac,
                row.call_id_hmac,
                row.provider,
                str(row.route_id),
                row.upstream_model,
                row.hmac_key_version,
                row.expires_at,
            )
            for row in rows
        )
    )


async def _audit_count(session: AsyncSession, key_id: uuid.UUID) -> int:
    return await session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == key_id)
    )


# --- Group A: gateway ownership law against real PostgreSQL -----------------


def _auth_key(row: object) -> AuthenticatedGatewayKey:
    """Authenticated context for a seeded key row, mirroring the API auth mapping."""
    meta = row.metadata_json or {}
    return AuthenticatedGatewayKey(
        gateway_key_id=row.id,
        owner_id=row.owner_id,
        cohort_id=row.cohort_id,
        public_key_id=row.public_key_id,
        status=row.status,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        allow_all_models=row.allow_all_models,
        allowed_models=tuple(row.allowed_models),
        allow_all_endpoints=row.allow_all_endpoints,
        allowed_endpoints=tuple(row.allowed_endpoints),
        allowed_providers=(
            tuple(meta["allowed_providers"]) if meta.get("allowed_providers") else None
        ),
        cost_limit_eur=row.cost_limit_eur,
        token_limit_total=row.token_limit_total,
        request_limit_total=row.request_limit_total,
        cost_used_eur=row.cost_used_eur or Decimal("0"),
        tokens_used_total=row.tokens_used_total or 0,
        cost_reserved_eur=row.cost_reserved_eur or Decimal("0"),
        tokens_reserved_total=row.tokens_reserved_total or 0,
        rate_limit_policy={
            "requests_per_minute": row.rate_limit_requests_per_minute,
            "tokens_per_minute": row.rate_limit_tokens_per_minute,
            "max_concurrent_requests": row.max_concurrent_requests,
            "window_seconds": None,
        },
        responses_policy=meta.get("responses_policy"),
        key_purpose=getattr(row, "key_purpose", "standard"),
        capability_policy_mode=getattr(row, "capability_policy_mode", "standard"),
    )


def _deny_before_ownership_sentinel(timeline: list[str], name: str):
    def _hook(*args: object, **kwargs: object) -> None:
        timeline.append(name)
        raise AssertionError(f"{name} ran before ownership denial")

    return _hook


def _assert_key_route_consistency(auth_key: AuthenticatedGatewayKey, provider: str) -> None:
    """The seeded key must actually permit the provider the mock route resolves.

    The resolver is mocked in these cases, so the real permission check is
    bypassed; assert fixture consistency instead of hiding a mismatch.
    """
    assert auth_key.allowed_providers is None or provider in auth_key.allowed_providers
    assert "synthetic-codex-model" in auth_key.allowed_models


@pytest.mark.asyncio
async def test_group_a_ambiguity_candidate_denied_before_route_without_reference(
    async_test_session: AsyncSession,
    rev16_client_module: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Positional identity binds the call to its earlier declaration.

    Root ambiguity shape: ``mcp__codex_apps__space.read`` is declared, the
    ID-bearing historical call omits the namespace, and a later approved
    namespace declares another ``read``.  The extracted candidate must hit
    the real PostgreSQL HMAC table (empty for this key) and be denied
    before routing, Redis, quota, or the provider run.
    """
    session = async_test_session
    settings = _replay_settings()
    _, _, key = await _seed_key(
        session, pin=_pin(_REV16_VERSION, _REV16_DIGEST), allowed_providers=("local-coding",)
    )
    auth_key = _auth_key(key)
    _assert_key_route_consistency(auth_key, "local-coding")

    body = base_model()
    body["model"] = "synthetic-codex-model"
    body["store"] = False
    body["input"] = [
        decl(ns("mcp__codex_apps__space", fn("read")), item_id="d1"),
        call("read", "call-1", id_="fc-1"),
        decl(ns("mcp__codex_apps__space2", fn("read")), item_id="d2"),
        out("call-1"),
    ]

    timeline: list[str] = []
    extracted: list[CodexReplayRequestCandidate] = []
    real_verify = responses_gateway._verify_owned_codex_replay_references

    async def _record_and_verify(**kwargs: object) -> object:
        extracted.extend(kwargs.get("candidates") or ())
        return await real_verify(**kwargs)

    async def _db_session(request: object | None = None):
        yield session

    monkeypatch.setattr(
        responses_gateway, "_get_db_session_after_auth_header_check", _db_session
    )
    monkeypatch.setattr(
        responses_gateway, "_verify_owned_codex_replay_references", _record_and_verify
    )
    monkeypatch.setattr(
        responses_gateway,
        "_resolve_responses_route",
        _deny_before_ownership_sentinel(timeline, "route"),
    )
    monkeypatch.setattr(
        responses_gateway,
        "_reserve_redis_rate_limit",
        _deny_before_ownership_sentinel(timeline, "redis"),
    )
    monkeypatch.setattr(
        responses_gateway,
        "_reserve_responses_quota",
        _deny_before_ownership_sentinel(timeline, "quota"),
    )
    monkeypatch.setattr(
        responses_gateway,
        "get_provider_adapter",
        _deny_before_ownership_sentinel(timeline, "provider"),
    )

    before_reservations = await session.scalar(
        select(func.count()).select_from(QuotaReservation)
    )
    before_ledger = await session.scalar(select(func.count()).select_from(UsageLedger))

    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=ResponsesCreateRequest.model_validate(body),
            authenticated_key=auth_key,
            settings=settings,
        )

    error = exc_info.value
    assert error.status_code == 404
    assert error.code == "responses_codex_replay_reference_not_found"
    # The positional identity must survive the later same-name namespace:
    # exactly one call candidate, bound to the earlier declaration.
    calls = [c for c in extracted if c.item_kind in ("function_call", "custom_tool_call")]
    assert len(calls) == 1
    candidate = calls[0]
    assert (candidate.tool_namespace, candidate.tool_name, candidate.call_id) == (
        "mcp__codex_apps__space",
        "read",
        "call-1",
    )
    assert candidate.item_id == "fc-1"
    # Ownership denial precedes every later side effect.
    assert timeline == []
    after_reservations = await session.scalar(
        select(func.count()).select_from(QuotaReservation)
    )
    after_ledger = await session.scalar(select(func.count()).select_from(UsageLedger))
    assert after_reservations == before_reservations
    assert after_ledger == before_ledger


def _local_coding_route(route_id: uuid.UUID, resolved_model: str = "synthetic-upstream"):
    """Static-identity Local Coding route row compatible with the rev-16 pair."""
    return SimpleNamespace(
        provider="local-coding",
        provider_kind="openai_compatible",
        provider_base_url="http://127.0.0.1:18031/v1",
        provider_api_key_env_var="LOCAL_CODING_SERVICE_TOKEN",
        provider_timeout_seconds=10,
        provider_max_retries=0,
        route_id=route_id,
        resolved_model=resolved_model,
        requested_model=resolved_model,
        route_match_type="exact",
        route_pattern=resolved_model,
        priority=1,
        supports_streaming=True,
        capabilities={
            "responses": {"text": True, "stateless": True, "streaming": True},
            "local_coding": {
                "contract_version": "local-coding-v1",
                "route_name": "vision",
                "tool_policy_version": "responses-tool-policy-v1",
                "identity_mode": "static",
                "replay_mode": "process_local_inclusive_horizon_fail_closed",
                "deployment_mode": "single_worker",
                "clock_skew_seconds": 60,
                "replay_ttl_seconds": 60,
            },
        },
    )


async def _seed_owned_reference(
    session: AsyncSession,
    *,
    settings: Settings,
    suffix: str,
    provider: str = "local-coding",
) -> tuple[object, object]:
    """Seed owner/cohort/key/ledger/route plus matching HMAC references."""
    now = datetime.now(UTC)
    owner, cohort, key = await _seed_key(
        session,
        pin=_pin(_REV16_VERSION, _REV16_DIGEST),
        allowed_providers=(provider,),
    )
    ledger = await _seed_ledger(session, key=key, owner=owner, cohort=cohort, now=now)
    route = await ModelRoutesRepository(session).create_model_route(
        requested_model=f"codex-226b-{uuid.uuid4().hex}",
        provider=provider,
        upstream_model="synthetic-upstream",
        endpoint="/v1/responses",
    )
    persisted = await _seed_replay_refs(
        session,
        settings=settings,
        key=key,
        ledger=ledger,
        candidates=_seed_candidates(suffix),
        route=route,
        now=now,
    )
    assert persisted == len(_seed_candidates(suffix))
    return key, route


@pytest.mark.asyncio
async def test_group_a_other_key_reference_denied_before_route(
    async_test_session: AsyncSession,
    rev16_client_module: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A matching HMAC row owned by another key still denies (404) the caller.

    The candidate is extracted from the real gateway flow and must be looked
    up in real PostgreSQL rows: the only matching reference belongs to a
    different gateway key, so ownership must deny before any later hook.
    """
    session = async_test_session
    settings = _replay_settings()
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex[:12]

    # The authenticated key owns no replay references at all.
    _, _, key = await _seed_key(
        session, pin=_pin(_REV16_VERSION, _REV16_DIGEST), allowed_providers=("local-coding",)
    )
    auth_key = _auth_key(key)
    _assert_key_route_consistency(auth_key, "local-coding")

    # The only matching references belong to a different key.
    forger_owner, forger_cohort, forger_key = await _seed_key(
        session,
        pin=_pin(_REV16_VERSION, _REV16_DIGEST),
        allowed_providers=("synthetic-native",),
    )
    forger_ledger = await _seed_ledger(
        session, key=forger_key, owner=forger_owner, cohort=forger_cohort, now=now
    )
    forger_route = await ModelRoutesRepository(session).create_model_route(
        requested_model=f"codex-226b-{uuid.uuid4().hex}",
        provider="synthetic-native",
        upstream_model="synthetic-upstream",
        endpoint="/v1/responses",
    )
    persisted = await _seed_replay_refs(
        session,
        settings=settings,
        key=forger_key,
        ledger=forger_ledger,
        candidates=_seed_candidates(suffix),
        route=forger_route,
        now=now,
    )
    assert persisted == len(_seed_candidates(suffix))

    body = base_model()
    body["model"] = "synthetic-codex-model"
    body["store"] = False
    body["input"] = [
        decl(ns("mcp__codex_apps__space", fn("read")), item_id="d1"),
        call("read", f"call_226b_{suffix}", id_=f"fc_226b_{suffix}"),
        out(f"call_226b_{suffix}"),
    ]

    timeline: list[str] = []
    extracted: list[CodexReplayRequestCandidate] = []
    real_verify = responses_gateway._verify_owned_codex_replay_references

    async def _record_and_verify(**kwargs: object) -> object:
        extracted.extend(kwargs.get("candidates") or ())
        return await real_verify(**kwargs)

    async def _db_session(request: object | None = None):
        yield session

    monkeypatch.setattr(
        responses_gateway, "_get_db_session_after_auth_header_check", _db_session
    )
    monkeypatch.setattr(
        responses_gateway, "_verify_owned_codex_replay_references", _record_and_verify
    )
    for name in ("_resolve_responses_route", "_reserve_redis_rate_limit", "_reserve_responses_quota"):
        monkeypatch.setattr(
            responses_gateway, name, _deny_before_ownership_sentinel(timeline, name)
        )
    monkeypatch.setattr(
        responses_gateway,
        "get_provider_adapter",
        _deny_before_ownership_sentinel(timeline, "get_provider_adapter"),
    )

    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=ResponsesCreateRequest.model_validate(body),
            authenticated_key=auth_key,
            settings=settings,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "responses_codex_replay_reference_not_found"
    calls = [c for c in extracted if c.item_kind in ("function_call", "custom_tool_call")]
    assert len(calls) == 1
    assert (calls[0].tool_namespace, calls[0].tool_name, calls[0].call_id) == (
        "mcp__codex_apps__space",
        "read",
        f"call_226b_{suffix}",
    )
    assert timeline == []


@pytest.mark.asyncio
async def test_group_a_wrong_route_denied_before_redis_quota_and_provider(
    async_test_session: AsyncSession,
    rev16_client_module: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owned references must match the SELECTED route; a different route denies."""
    session = async_test_session
    settings = _replay_settings()
    suffix = uuid.uuid4().hex[:12]

    key, owned_route = await _seed_owned_reference(session, settings=settings, suffix=suffix)
    auth_key = _auth_key(key)
    _assert_key_route_consistency(auth_key, "local-coding")

    body = base_model()
    body["model"] = "synthetic-codex-model"
    body["store"] = False
    body["input"] = [
        decl(ns("mcp__codex_apps__space", fn("read")), item_id="d1"),
        call("read", f"call_226b_{suffix}", id_=f"fc_226b_{suffix}"),
        out(f"call_226b_{suffix}"),
    ]

    timeline: list[str] = []

    async def _resolve_wrong_route(**_kwargs: object):
        return _local_coding_route(uuid.uuid4())  # not the owned route

    async def _db_session(request: object | None = None):
        yield session

    monkeypatch.setattr(
        responses_gateway, "_get_db_session_after_auth_header_check", _db_session
    )
    monkeypatch.setattr(responses_gateway, "_resolve_responses_route", _resolve_wrong_route)
    for name in ("_reserve_redis_rate_limit", "_reserve_responses_quota"):
        monkeypatch.setattr(
            responses_gateway, name, _deny_before_ownership_sentinel(timeline, name)
        )
    monkeypatch.setattr(
        responses_gateway,
        "get_provider_adapter",
        _deny_before_ownership_sentinel(timeline, "get_provider_adapter"),
    )

    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=ResponsesCreateRequest.model_validate(body),
            authenticated_key=auth_key,
            settings=settings,
        )

    assert exc_info.value.code == "responses_codex_replay_route_mismatch"
    assert timeline == []


@pytest.mark.asyncio
async def test_group_a_idless_owned_candidate_passes_deferred_verification(
    async_test_session: AsyncSession,
    rev16_client_module: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ID-less call owned by the key passes deferred call-id verification.

    The reference row was persisted with an item id; the request omits the
    id, so only the real PostgreSQL call-id HMAC lookup can authorize it.
    Verification is deferred until after local route resolution and then
    succeeds, letting the flow reach quota admission.
    """
    session = async_test_session
    settings = Settings(
        APP_ENV="development",
        TOKEN_HMAC_SECRET=_HMAC_SECRET,
        ACTIVE_HMAC_KEY_VERSION="1",
        CODEX_REPLAY_REFERENCE_TTL_SECONDS=_TTL_SECONDS,
        ENABLE_REDIS_RATE_LIMITS=False,
    )
    suffix = uuid.uuid4().hex[:12]

    key, owned_route = await _seed_owned_reference(session, settings=settings, suffix=suffix)
    auth_key = _auth_key(key)
    _assert_key_route_consistency(auth_key, "local-coding")

    body = base_model()
    body["model"] = "synthetic-codex-model"
    body["store"] = False
    body["input"] = [
        decl(ns("mcp__codex_apps__space", fn("read")), item_id="d1"),
        call("read", f"call_226b_{suffix}"),  # ID omitted
        out(f"call_226b_{suffix}"),
    ]

    timeline: list[str] = []

    async def _resolve_owned_route(**_kwargs: object):
        return _local_coding_route(owned_route.id)

    async def _db_session(request: object | None = None):
        yield session

    monkeypatch.setattr(
        responses_gateway, "_get_db_session_after_auth_header_check", _db_session
    )
    monkeypatch.setattr(responses_gateway, "_resolve_responses_route", _resolve_owned_route)
    monkeypatch.setattr(
        responses_gateway,
        "_reserve_responses_quota",
        _deny_before_ownership_sentinel(timeline, "_reserve_responses_quota"),
    )
    monkeypatch.setattr(
        responses_gateway,
        "get_provider_adapter",
        _deny_before_ownership_sentinel(timeline, "get_provider_adapter"),
    )

    with pytest.raises(AssertionError, match="_reserve_responses_quota"):
        await handle_response_create(
            payload=ResponsesCreateRequest.model_validate(body),
            authenticated_key=auth_key,
            settings=settings,
        )

    # Ownership (deferred, ID-less, real PG) passed; the flow reached quota
    # admission and no provider hook ran.
    assert timeline == ["_reserve_responses_quota"]


@pytest.mark.parametrize("mode", ["unowned", "other-key", "wrong-route"])
@pytest.mark.asyncio
async def test_group_a_idless_negatives_denied_before_quota_and_provider(
    async_test_session: AsyncSession,
    rev16_client_module: object,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    """ID-less deferred verification denies unowned, other-key, and wrong-route.

    The call omits its item id, so only the deferred call-id HMAC lookup on
    real PostgreSQL rows can authorize it.  Every denial variant must land
    before quota reservation and before any provider hook.
    """
    session = async_test_session
    settings = _group_b_settings()
    suffix = uuid.uuid4().hex[:12]

    if mode == "unowned":
        _, _, key = await _seed_key(
            session,
            pin=_pin(_REV16_VERSION, _REV16_DIGEST),
            allowed_providers=("local-coding",),
        )
        probe_route_id = uuid.uuid4()
        expected_code = "responses_codex_replay_reference_not_found"
    elif mode == "other-key":
        now = datetime.now(UTC)
        _, _, key = await _seed_key(
            session,
            pin=_pin(_REV16_VERSION, _REV16_DIGEST),
            allowed_providers=("local-coding",),
        )
        # The only matching call-id reference belongs to a different key.
        forger_owner, forger_cohort, forger_key = await _seed_key(
            session,
            pin=_pin(_REV16_VERSION, _REV16_DIGEST),
            allowed_providers=("local-coding",),
        )
        forger_ledger = await _seed_ledger(
            session, key=forger_key, owner=forger_owner, cohort=forger_cohort, now=now
        )
        forger_route = await ModelRoutesRepository(session).create_model_route(
            requested_model=f"codex-226b-{uuid.uuid4().hex}",
            provider="local-coding",
            upstream_model="synthetic-upstream",
            endpoint="/v1/responses",
        )
        persisted = await _seed_replay_refs(
            session,
            settings=settings,
            key=forger_key,
            ledger=forger_ledger,
            candidates=_seed_candidates(suffix),
            route=forger_route,
            now=now,
        )
        assert persisted == len(_seed_candidates(suffix))
        probe_route_id = forger_route.id
        expected_code = "responses_codex_replay_reference_not_found"
    else:
        key, _owned_route = await _seed_owned_reference(
            session, settings=settings, suffix=suffix
        )
        probe_route_id = uuid.uuid4()  # a different route than the owned one
        expected_code = "responses_codex_replay_route_mismatch"

    auth_key = _auth_key(key)
    _assert_key_route_consistency(auth_key, "local-coding")

    body = base_model()
    body["model"] = "synthetic-codex-model"
    body["store"] = False
    body["input"] = [
        decl(ns("mcp__codex_apps__space", fn("read")), item_id="d1"),
        call("read", f"call_226b_{suffix}"),  # ID omitted
        out(f"call_226b_{suffix}"),
    ]

    timeline: list[str] = []

    async def _resolve_probe(**_kwargs: object):
        return _local_coding_route(probe_route_id)

    async def _db_session(request: object | None = None):
        yield session

    monkeypatch.setattr(
        responses_gateway, "_get_db_session_after_auth_header_check", _db_session
    )
    monkeypatch.setattr(responses_gateway, "_resolve_responses_route", _resolve_probe)
    monkeypatch.setattr(
        responses_gateway,
        "_reserve_responses_quota",
        _deny_before_ownership_sentinel(timeline, "quota"),
    )
    monkeypatch.setattr(
        responses_gateway,
        "get_provider_adapter",
        _deny_before_ownership_sentinel(timeline, "provider"),
    )

    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=ResponsesCreateRequest.model_validate(body),
            authenticated_key=auth_key,
            settings=settings,
        )

    assert exc_info.value.code == expected_code
    if expected_code == "responses_codex_replay_reference_not_found":
        assert exc_info.value.status_code == 404
    # Denial precedes quota reservation and the provider hook.
    assert timeline == []


# --- Group B: real codec boundary -> real PostgreSQL settlement -------------

_GROUP_B_PROVIDER = "local-coding"
_GROUP_B_UPSTREAM_MODEL = "synthetic-upstream"
_GROUP_B_SERVICE_TOKEN = "synthetic-upstream-service-token-226b-0123456789"
_GROUP_B_INPUT_PRICE = Decimal("2.00")
_GROUP_B_OUTPUT_PRICE = Decimal("8.00")


def _group_b_settings() -> Settings:
    return Settings(
        APP_ENV="development",
        TOKEN_HMAC_SECRET=_HMAC_SECRET,
        ACTIVE_HMAC_KEY_VERSION="1",
        CODEX_REPLAY_REFERENCE_TTL_SECONDS=_TTL_SECONDS,
        ENABLE_REDIS_RATE_LIMITS=False,
    )


def _group_b_body() -> dict:
    # Empty catalog (no tool declaration, no historical call): the positional
    # lifecycle mode is still active, so codec transports run in explicit
    # lifecycle mode and the core output guard sees the final active set.
    body = base_model()
    body["model"] = "synthetic-codex-model"
    body["store"] = False
    body["input"] = [user("bounded")]
    return body


def _wire_transport(output_items: list, usage: dict) -> httpx.AsyncClient:
    return _wire_transport_captured(output_items, usage)


def _wire_transport_captured(
    output_items: list, usage: dict, captured: dict | None = None
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured["request_json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"id": "resp-226b", "output": output_items, "usage": usage},
            headers={"content-type": "application/json"},
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _collect_tool_names(tools: object) -> set[str]:
    names: set[str] = set()
    if not isinstance(tools, list):
        return names
    for entry in tools:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "namespace" and isinstance(entry.get("tools"), list):
            names |= _collect_tool_names(entry["tools"])
        if isinstance(entry.get("name"), str):
            names.add(entry["name"])
    return names


async def _seed_group_b_world(
    session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> AuthenticatedGatewayKey:
    """rev-16 key + real EUR pricing + owned local-coding route probe."""
    _, _, key = await _seed_key(
        session,
        pin=_pin(_REV16_VERSION, _REV16_DIGEST),
        allowed_providers=(_GROUP_B_PROVIDER,),
    )
    await PricingRulesRepository(session).create_pricing_rule(
        provider=_GROUP_B_PROVIDER,
        upstream_model=_GROUP_B_UPSTREAM_MODEL,
        valid_from=datetime.now(UTC) - timedelta(minutes=1),
        endpoint="/v1/responses",
        currency="EUR",
        input_price_per_1m=_GROUP_B_INPUT_PRICE,
        output_price_per_1m=_GROUP_B_OUTPUT_PRICE,
    )
    route = await ModelRoutesRepository(session).create_model_route(
        requested_model=f"codex-226b-{uuid.uuid4().hex}",
        provider=_GROUP_B_PROVIDER,
        upstream_model=_GROUP_B_UPSTREAM_MODEL,
        endpoint="/v1/responses",
    )

    async def _resolve_owned_route(**_kwargs: object):
        return _local_coding_route(route.id, _GROUP_B_UPSTREAM_MODEL)

    async def _db_session(request: object | None = None):
        yield session

    monkeypatch.setattr(
        responses_gateway, "_get_db_session_after_auth_header_check", _db_session
    )
    monkeypatch.setattr(
        responses_gateway, "_resolve_responses_route", _resolve_owned_route
    )
    return _auth_key(key)


async def _group_b_settlement_facts(session: AsyncSession, key_id: uuid.UUID):
    ledger_facts = await _ledger_facts(session, key_id)
    key_row = await session.get(GatewayKey, key_id)
    reservations = list(
        (
            await session.execute(
                select(QuotaReservation)
                .where(QuotaReservation.gateway_key_id == key_id)
                .order_by(QuotaReservation.created_at)
            )
        ).scalars()
    )
    replay_refs = await session.scalar(
        select(func.count())
        .select_from(CodexReplayReference)
        .where(CodexReplayReference.gateway_key_id == key_id)
    )
    return (
        ledger_facts,
        (key_row.tokens_used_total, key_row.requests_used_total, key_row.cost_used_eur),
        len(reservations),
        reservations,
        replay_refs,
    )


@pytest.mark.parametrize(
    "adapter_kind",
    ["native-vllm", "configured-native-vllm", "configured-portable"],
)
@pytest.mark.asyncio
async def test_group_b_codec_rejection_settles_usage_once_then_refuses(
    async_test_session: AsyncSession,
    rev16_client_module: object,
    monkeypatch: pytest.MonkeyPatch,
    adapter_kind: str,
) -> None:
    """Removed-wire-tool refusal at the real adapter codec boundary.

    The underlying HTTP transport is mocked; the adapter codec parses the
    genuine wire response, rejects the removed tool, and keeps the parsed
    usage.  The gateway settles that usage exactly once in PostgreSQL and
    only then refuses with the fixed safe code (no release, no denied
    replay references).
    """
    session = async_test_session
    settings = _group_b_settings()
    auth_key = await _seed_group_b_world(session, settings, monkeypatch)
    key_id = auth_key.gateway_key_id

    portable = adapter_kind == "configured-portable"
    wire_name = vllm_wire_name("functions", "removed", portable_names=portable)
    client = _wire_transport(
        [{"type": "function_call", "name": wire_name, "arguments": "{}"}],
        {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    )
    if adapter_kind == "native-vllm":
        adapter = LocalCodingVLLMAdapter(
            settings,
            route_capabilities=VLLM_CAPS,
            api_key=_GROUP_B_SERVICE_TOKEN,
            http_client=client,
        )
    elif adapter_kind == "configured-native-vllm":
        adapter = ConfiguredUpstreamLLMAdapter(
            settings,
            route_capabilities=upstream_route_capabilities("native-vllm-v1"),
            api_key=_GROUP_B_SERVICE_TOKEN,
            http_client=client,
        )
    else:
        adapter = ConfiguredUpstreamLLMAdapter(
            settings,
            route_capabilities=upstream_route_capabilities("responses-functions-v1"),
            api_key=_GROUP_B_SERVICE_TOKEN,
            http_client=client,
        )
    monkeypatch.setattr(
        responses_gateway, "get_provider_adapter", lambda route, cfg: adapter
    )

    before = await _group_b_settlement_facts(session, key_id)

    with pytest.raises(OpenAICompatibleError) as exc_info:
        await handle_response_create(
            payload=ResponsesCreateRequest.model_validate(_group_b_body()),
            authenticated_key=auth_key,
            settings=settings,
        )

    error = exc_info.value
    assert error.status_code == 502
    assert error.code == "vllm_tool_protocol_invalid"

    after = await _group_b_settlement_facts(session, key_id)
    expected_cost = (
        Decimal(7) * _GROUP_B_INPUT_PRICE + Decimal(3) * _GROUP_B_OUTPUT_PRICE
    ) / Decimal(1_000_000)
    # The actual parsed wire usage was settled exactly once.
    assert after[0][0] == before[0][0] + 1
    assert after[0][1] == before[0][1] + 7
    assert after[0][2] == before[0][2] + 3
    assert after[0][3] == before[0][3] + 10
    assert after[0][5] == before[0][5] + expected_cost
    # Key counters moved exactly once by the same amounts.
    assert after[1][0] == before[1][0] + 10
    assert after[1][1] == before[1][1] + 1
    assert after[1][2] == before[1][2] + expected_cost
    # The reservation was finalized, never released.
    assert after[2] == before[2] + 1
    reservation = after[3][-1]
    assert reservation.status == "finalized"
    assert reservation.finalized_at is not None
    assert reservation.released_at is None
    # The denied output produced no replay references.
    assert after[4] == before[4]
    await client.aclose()


@pytest.mark.asyncio
async def test_group_b_preserve_passthrough_settles_success(
    async_test_session: AsyncSession,
    rev16_client_module: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The preserve profile has no codec: the wire response passes through.

    A compliant assistant message is returned to the client with real
    PostgreSQL settlement; nothing is refused or released.
    """
    session = async_test_session
    settings = _group_b_settings()
    auth_key = await _seed_group_b_world(session, settings, monkeypatch)
    key_id = auth_key.gateway_key_id

    client = _wire_transport(
        [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "bounded"}],
            }
        ],
        {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
    )
    adapter = ConfiguredUpstreamLLMAdapter(
        settings,
        route_capabilities=upstream_route_capabilities("responses-passthrough-v1"),
        api_key=_GROUP_B_SERVICE_TOKEN,
        http_client=client,
    )
    monkeypatch.setattr(
        responses_gateway, "get_provider_adapter", lambda route, cfg: adapter
    )

    before = await _group_b_settlement_facts(session, key_id)

    response = await handle_response_create(
        payload=ResponsesCreateRequest.model_validate(_group_b_body()),
        authenticated_key=auth_key,
        settings=settings,
    )

    assert response.status_code == 200
    content = json.loads(response.body)
    assert content["output"] == [
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "bounded"}],
        }
    ]

    after = await _group_b_settlement_facts(session, key_id)
    expected_cost = (
        Decimal(4) * _GROUP_B_INPUT_PRICE + Decimal(2) * _GROUP_B_OUTPUT_PRICE
    ) / Decimal(1_000_000)
    assert after[0][0] == before[0][0] + 1
    assert after[0][1] == before[0][1] + 4
    assert after[0][2] == before[0][2] + 2
    assert after[0][3] == before[0][3] + 6
    assert after[0][5] == before[0][5] + expected_cost
    assert after[1][0] == before[1][0] + 6
    assert after[1][1] == before[1][1] + 1
    assert after[1][2] == before[1][2] + expected_cost
    assert after[2] == before[2] + 1
    assert after[3][-1].status == "finalized"
    assert after[4] == before[4]
    await client.aclose()


# --- Group B extension: owned nonempty history -> full gateway workflow -----

_RESPONSES_CAPS = {"text": True, "stateless": True, "streaming": True}

# kind -> (route provider, upstream profile id or None, codec wire mode,
#          historical call wire name, current kept wire name, removal notice)
_SUCCESS_KINDS = {
    "vllm": (
        "local-coding-vLLM",
        None,
        vllm_wire_name("functions", "read", portable_names=False),
        vllm_wire_name("functions", "kept", portable_names=False),
        True,
    ),
    "llama-preserve": (
        "synthetic-llama",
        "llama-cpp-qwen-v1",
        "read",
        "kept",
        # The registered llama profile uses leading_system_developer
        # placement; a removal notice after the history it describes is
        # deliberately NOT representable there (order-changing placement is
        # refused), so this kind carries a still-active owned history.
        False,
    ),
    "configured-native": (
        "synthetic-native-vllm",
        "native-vllm-v1",
        vllm_wire_name("functions", "read", portable_names=False),
        vllm_wire_name("functions", "kept", portable_names=False),
        True,
    ),
    "configured-portable": (
        "synthetic-portable",
        "responses-functions-v1",
        vllm_wire_name("functions", "read", portable_names=True),
        vllm_wire_name("functions", "kept", portable_names=True),
        True,
    ),
}

_SUCCESS_USAGE = {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}
_SUCCESS_OUTPUT = [
    {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "bounded"}],
    }
]


def _success_items(with_removal_notice: bool) -> list:
    items = [
        decl(ns("functions", fn("read"), fn("kept")), item_id="d1"),
        call("read", "call-1", id_="fc-1"),
        out("call-1"),
    ]
    if with_removal_notice:
        items.append(notice(tools={("functions", "read")}))
    items.append(user("bounded"))
    return items


def _route_probe(route_id: uuid.UUID, provider: str, capabilities: dict):
    return SimpleNamespace(
        provider=provider,
        provider_kind="openai_compatible",
        provider_base_url="http://127.0.0.1:18031/v1",
        provider_api_key_env_var="UPSTREAM_SERVICE_TOKEN",
        provider_timeout_seconds=10,
        provider_max_retries=0,
        route_id=route_id,
        resolved_model="synthetic-upstream",
        requested_model="synthetic-upstream",
        route_match_type="exact",
        route_pattern="synthetic-upstream",
        priority=1,
        supports_streaming=True,
        capabilities=capabilities,
    )


@pytest.mark.parametrize("kind", sorted(_SUCCESS_KINDS))
@pytest.mark.asyncio
async def test_group_b_owned_history_success_settles_through_real_workflow(
    async_test_session: AsyncSession,
    rev16_client_module: object,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    """Owned nonempty history completes the real gateway workflow.

    The historical completed tool call is HMAC-owned in PostgreSQL, the
    request reaches the real adapter over a mocked HTTP transport, and the
    wire request carries the exact historical identity/call-output linkage
    plus current-only declarations.  A valid 200 response settles actual
    usage exactly once.  Route capabilities match the selected adapter
    (vLLM / upstream-LLM / static local transport), not a forced codec.
    """
    session = async_test_session
    settings = _group_b_settings()
    provider, profile_id, removed_name, kept_name, with_notice = _SUCCESS_KINDS[kind]

    now = datetime.now(UTC)
    owner, cohort, key = await _seed_key(
        session,
        pin=_pin(_REV16_VERSION, _REV16_DIGEST),
        allowed_providers=(provider,),
    )
    ledger = await _seed_ledger(session, key=key, owner=owner, cohort=cohort, now=now)
    route = await ModelRoutesRepository(session).create_model_route(
        requested_model=f"codex-226b-{uuid.uuid4().hex}",
        provider=provider,
        upstream_model="synthetic-upstream",
        endpoint="/v1/responses",
    )
    await PricingRulesRepository(session).create_pricing_rule(
        provider=provider,
        upstream_model="synthetic-upstream",
        valid_from=now - timedelta(minutes=1),
        endpoint="/v1/responses",
        currency="EUR",
        input_price_per_1m=_GROUP_B_INPUT_PRICE,
        output_price_per_1m=_GROUP_B_OUTPUT_PRICE,
    )
    # The exact historical identity from this body, owned by this key.
    candidate = (
        CodexReplayRequestCandidate(
            item_kind="function_call",
            item_id="fc-1",
            call_id="call-1",
            tool_namespace="functions",
            tool_name="read",
        ),
    )
    persisted = await _seed_replay_refs(
        session, settings=settings, key=key, ledger=ledger, candidates=candidate, route=route, now=now
    )
    assert persisted == 1

    auth_key = _auth_key(key)
    _assert_key_route_consistency(auth_key, provider)

    if profile_id is None:
        capabilities = {**VLLM_CAPS, "responses": _RESPONSES_CAPS}
    else:
        capabilities = {**upstream_route_capabilities(profile_id), "responses": _RESPONSES_CAPS}

    captured: dict = {}
    client = _wire_transport_captured(_SUCCESS_OUTPUT, _SUCCESS_USAGE, captured)
    if profile_id is None:
        adapter = LocalCodingVLLMAdapter(
            settings,
            route_capabilities=VLLM_CAPS,
            api_key=_GROUP_B_SERVICE_TOKEN,
            http_client=client,
        )
    else:
        adapter = ConfiguredUpstreamLLMAdapter(
            settings,
            route_capabilities=upstream_route_capabilities(profile_id),
            api_key=_GROUP_B_SERVICE_TOKEN,
            http_client=client,
        )

    async def _resolve_owned_route(**_kwargs: object):
        return _route_probe(route.id, provider, capabilities)

    async def _db_session(request: object | None = None):
        yield session

    monkeypatch.setattr(
        responses_gateway, "_get_db_session_after_auth_header_check", _db_session
    )
    monkeypatch.setattr(
        responses_gateway, "_resolve_responses_route", _resolve_owned_route
    )
    monkeypatch.setattr(
        responses_gateway, "get_provider_adapter", lambda route, cfg: adapter
    )

    before = await _group_b_settlement_facts(session, auth_key.gateway_key_id)

    body = base_model()
    body["model"] = "synthetic-codex-model"
    body["store"] = False
    body["input"] = _success_items(with_notice)

    response = await handle_response_create(
        payload=ResponsesCreateRequest.model_validate(body),
        authenticated_key=auth_key,
        settings=settings,
    )

    assert response.status_code == 200
    content = json.loads(response.body)
    assert content["output"] == _SUCCESS_OUTPUT

    # Wire request: exact historical identity/call-output linkage and
    # current-only declarations.
    wire = captured["request_json"]
    input_items = wire.get("input")
    assert isinstance(input_items, list)
    hist_calls = [
        item
        for item in input_items
        if isinstance(item, dict)
        and item.get("type") == "function_call"
        and item.get("call_id") == "call-1"
    ]
    assert len(hist_calls) == 1
    assert hist_calls[0]["name"] == removed_name
    if kind == "llama-preserve":
        # The preserve identity fix materializes the validated namespace
        # on the provider copy for namespace-less historical calls.
        assert hist_calls[0].get("namespace") == "functions"
    else:
        # Codec transports carry the identity in the wire name itself.
        assert hist_calls[0].get("namespace") is None
    hist_outputs = [
        item
        for item in input_items
        if isinstance(item, dict)
        and item.get("type") == "function_call_output"
        and item.get("call_id") == "call-1"
    ]
    assert len(hist_outputs) == 1
    tool_names = _collect_tool_names(wire.get("tools"))
    assert kept_name in tool_names
    if with_notice:
        # The removed tool is excluded from the current declarations.
        assert removed_name not in tool_names

    # Actual usage settled exactly once.
    after = await _group_b_settlement_facts(session, auth_key.gateway_key_id)
    expected_cost = (
        Decimal(5) * _GROUP_B_INPUT_PRICE + Decimal(2) * _GROUP_B_OUTPUT_PRICE
    ) / Decimal(1_000_000)
    assert after[0][0] == before[0][0] + 1
    assert after[0][1] == before[0][1] + 5
    assert after[0][2] == before[0][2] + 2
    assert after[0][3] == before[0][3] + 7
    assert after[0][5] == before[0][5] + expected_cost
    assert after[1][0] == before[1][0] + 7
    assert after[1][1] == before[1][1] + 1
    assert after[1][2] == before[1][2] + expected_cost
    assert after[2] == before[2] + 1
    assert after[3][-1].status == "finalized"
    # The plain message response adds no new replay references.
    assert after[4] == before[4]
    await client.aclose()


@pytest.mark.asyncio
async def test_profile_migration_15_to_16_preserves_key_replay_and_usage(
    async_test_session: AsyncSession,
    rev16_client_module: object,
) -> None:
    settings = _replay_settings()
    session = async_test_session
    now = datetime.now(UTC)

    owner, cohort, key = await _seed_key(
        session,
        pin=_pin(_REV15_VERSION, _REV15_DIGEST),
        allowed_providers=("synthetic-native",),
    )
    ledger = await _seed_ledger(session, key=key, owner=owner, cohort=cohort, now=now)
    route = await ModelRoutesRepository(session).create_model_route(
        requested_model=f"codex-226b-{uuid.uuid4().hex}",
        provider="synthetic-native",
        upstream_model="synthetic-upstream",
        endpoint="/v1/responses",
    )
    candidates = _seed_candidates(key.public_key_id[-12:])
    persisted = await _seed_replay_refs(
        session,
        settings=settings,
        key=key,
        ledger=ledger,
        candidates=candidates,
        route=route,
        now=now,
    )
    assert persisted == len(candidates)

    before_columns = await _key_column_snapshot(session, key.id)
    assert await _stored_pin(session, key.id) == _pin(_REV15_VERSION, _REV15_DIGEST)
    before_ledger = await _ledger_facts(session, key.id)
    before_refs = await _ref_fingerprints(session, key.id)
    before_audit = await _audit_count(session, key.id)
    assert before_audit == 0
    assert len(before_refs) == len(candidates)
    assert before_ledger[0] == 1
    assert before_ledger[1] == 1_200 and before_ledger[2] == 300

    keys_repo = GatewayKeysRepository(session)
    audit_repo = AuditRepository(session)
    reason = "OAP 226-b qualification: codex profile rev15 to rev16 upgrade"

    def _migrate(apply: bool):
        return migrate_codex_0162_key_profile(
            session=session,
            keys_repository=keys_repo,
            audit_repository=audit_repo,
            gateway_key_id=key.id,
            from_version=_REV15_VERSION,
            from_digest=_REV15_DIGEST,
            target="active",
            action="upgrade",
            actor_admin_id=None,
            reason=reason,
            apply=apply,
        )

    # Negative: a drifted source digest on the same revision must fail
    # closed before any row write.
    with pytest.raises(CodexModuleUpgradeError) as drifted:
        await migrate_codex_0162_key_profile(
            session=session,
            keys_repository=keys_repo,
            audit_repository=audit_repo,
            gateway_key_id=key.id,
            from_version=_REV15_VERSION,
            from_digest="e" * 64,
            target="active",
            action="upgrade",
            actor_admin_id=None,
            reason=reason,
            apply=True,
        )
    assert drifted.value.error_code == "codex_module_upgrade_identity_mismatch"
    assert await _stored_pin(session, key.id) == _pin(_REV15_VERSION, _REV15_DIGEST)
    assert await _key_column_snapshot(session, key.id) == before_columns
    assert await _ref_fingerprints(session, key.id) == before_refs

    # Dry run: no write, no audit.
    dry = await _migrate(apply=False)
    assert dry.status == "dry_run"
    assert dry.changed is False
    assert dry.target_module["version"] == _REV16_VERSION
    assert dry.target_module["fixture_sha256"] == _REV16_DIGEST
    assert await _stored_pin(session, key.id) == _pin(_REV15_VERSION, _REV15_DIGEST)
    assert await _key_column_snapshot(session, key.id) == before_columns
    assert await _ledger_facts(session, key.id) == before_ledger
    assert await _ref_fingerprints(session, key.id) == before_refs
    assert await _audit_count(session, key.id) == 0

    # Apply: only the client_module pin moves; every other material field,
    # the full metadata, usage, and replay rows are preserved.
    applied = await _migrate(apply=True)
    assert applied.status == "applied"
    assert applied.changed is True
    assert await _stored_pin(session, key.id) == _pin(_REV16_VERSION, _REV16_DIGEST)
    assert await _key_column_snapshot(session, key.id) == before_columns
    assert await _ledger_facts(session, key.id) == before_ledger
    assert await _ref_fingerprints(session, key.id) == before_refs
    assert await _audit_count(session, key.id) == 1
    audit_row = (
        (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.entity_id == key.id)
                .order_by(AuditLog.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert audit_row is not None
    assert audit_row.action == "upgrade"
    assert audit_row.old_values["client_module"]["fixture_sha256"] == _REV15_DIGEST
    assert audit_row.new_values["client_module"]["fixture_sha256"] == _REV16_DIGEST

    # Existing same-key HMAC references survive and still verify, including
    # route/provider compatibility against the stored route facts.
    service = CodexReplayService(
        repository=CodexReplayReferencesRepository(session),
        settings=settings,
    )
    authorization = await service.verify_owned_replay(
        candidates=candidates,
        gateway_key_id=key.id,
        now=datetime.now(UTC),
    )
    assert len(authorization.references) == len(candidates)
    service.verify_route_compatibility(
        authorization,
        provider=route.provider,
        route_id=route.id,
        upstream_model=route.upstream_model,
    )

    # Idempotency: repeating the exact target is a no-op without audit.
    repeat = await _migrate(apply=True)
    assert repeat.status == "already_at_target"
    assert repeat.changed is False
    assert await _audit_count(session, key.id) == 1
    assert await _stored_pin(session, key.id) == _pin(_REV16_VERSION, _REV16_DIGEST)
    assert await _key_column_snapshot(session, key.id) == before_columns
    assert await _ledger_facts(session, key.id) == before_ledger
    assert await _ref_fingerprints(session, key.id) == before_refs

@pytest.mark.asyncio
async def test_preserve_wire_bodies_distinct_for_distinct_validated_namespaces(
    async_test_session: AsyncSession,
    rev16_client_module: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two namespace-less histories with distinct validated namespaces differ.

    Regression for the preserve identity loss: a client item that omits the
    namespace must be materialized on the provider copy from the VALIDATED
    binding, so two histories bound to different namespaces can no longer
    produce identical preserve wire bodies.
    """
    session = async_test_session
    settings = _group_b_settings()
    provider = "synthetic-llama"
    capabilities = {
        **upstream_route_capabilities("llama-cpp-qwen-v1"),
        "responses": _RESPONSES_CAPS,
    }

    captured_bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"id": "resp-226b", "output": _SUCCESS_OUTPUT, "usage": _SUCCESS_USAGE},
            headers={"content-type": "application/json"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ConfiguredUpstreamLLMAdapter(
        settings,
        route_capabilities=upstream_route_capabilities("llama-cpp-qwen-v1"),
        api_key=_GROUP_B_SERVICE_TOKEN,
        http_client=client,
    )

    async def _db_session(request: object | None = None):
        yield session

    monkeypatch.setattr(
        responses_gateway, "_get_db_session_after_auth_header_check", _db_session
    )
    monkeypatch.setattr(
        responses_gateway, "get_provider_adapter", lambda route, cfg: adapter
    )

    for namespace in ("functions", "clock"):
        now = datetime.now(UTC)
        owner, cohort, key = await _seed_key(
            session,
            pin=_pin(_REV16_VERSION, _REV16_DIGEST),
            allowed_providers=(provider,),
        )
        ledger = await _seed_ledger(session, key=key, owner=owner, cohort=cohort, now=now)
        route = await ModelRoutesRepository(session).create_model_route(
            requested_model=f"codex-226b-{uuid.uuid4().hex}",
            provider=provider,
            upstream_model="synthetic-upstream",
            endpoint="/v1/responses",
        )
        await PricingRulesRepository(session).create_pricing_rule(
            provider=provider,
            upstream_model="synthetic-upstream",
            valid_from=now - timedelta(minutes=1),
            endpoint="/v1/responses",
            currency="EUR",
            input_price_per_1m=_GROUP_B_INPUT_PRICE,
            output_price_per_1m=_GROUP_B_OUTPUT_PRICE,
        )
        candidate = (
            CodexReplayRequestCandidate(
                item_kind="function_call",
                item_id="fc-1",
                call_id="call-1",
                tool_namespace=namespace,
                tool_name="read",
            ),
        )
        persisted = await _seed_replay_refs(
            session, settings=settings, key=key, ledger=ledger, candidates=candidate, route=route, now=now
        )
        assert persisted == 1

        async def _resolve_owned_route(_route_id=route.id, **_kwargs: object):
            return _route_probe(_route_id, provider, capabilities)

        monkeypatch.setattr(
            responses_gateway, "_resolve_responses_route", _resolve_owned_route
        )

        body = base_model()
        body["model"] = "synthetic-codex-model"
        body["store"] = False
        body["input"] = [
            decl(ns(namespace, fn("read")), item_id="d1"),
            call("read", "call-1", id_="fc-1"),  # namespace omitted by the client
            out("call-1"),
            user("bounded"),
        ]

        response = await handle_response_create(
            payload=ResponsesCreateRequest.model_validate(body),
            authenticated_key=_auth_key(key),
            settings=settings,
        )
        assert response.status_code == 200

    assert len(captured_bodies) == 2

    def _hist_call(wire_body: dict) -> dict:
        matches = [
            item
            for item in wire_body["input"]
            if isinstance(item, dict)
            and item.get("type") == "function_call"
            and item.get("call_id") == "call-1"
        ]
        assert len(matches) == 1
        return matches[0]

    assert _hist_call(captured_bodies[0])["namespace"] == "functions"
    assert _hist_call(captured_bodies[1])["namespace"] == "clock"
    # Distinct validated identities must give distinct preserve wire bodies.
    assert captured_bodies[0] != captured_bodies[1]
    await client.aclose()
