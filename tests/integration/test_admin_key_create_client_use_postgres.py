"""PostgreSQL-backed GUI evidence for 229-a client-use key creation.

Real authenticated/CSRF form posts against a disposable migrated
PostgreSQL database with mocked providers (routes/pricing only) and no
email delivery. Covers: the OpenCode Chat / Hermes / OpenCode Responses
presets persisting exact active pins, conflict and missing-route refusals
leaving zero side effects, and the rev16/rev17 fresh-process Codex create
that proves the root-cause repair end to end.
"""

from __future__ import annotations

import asyncio
import json
import pytest
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AuditLog,
    EmailDelivery,
    GatewayKey,
    ModelRoute,
    PricingRule,
    ProviderConfig,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.modules.clients.agent_chat import bootstrap_agent_chat_client_modules
from slaif_gateway.modules.clients.codex_0162 import build_codex_0162_client_module
from slaif_gateway.modules.clients.hermes_0225_chat import (
    HERMES_0225_CHAT_CLIENT_MODULE_ID,
)
from slaif_gateway.modules.clients.opencode_1193_chat import (
    OPENCODE_1193_CHAT_CLIENT_MODULE_ID,
)
from slaif_gateway.modules.clients.opencode_1193_responses import (
    OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID,
)
from slaif_gateway.modules.clients.registry import active_client_module_facts
from slaif_gateway.modules.codex_profile_data import load_codex_profile_file
from slaif_gateway.services.codex_profile_registry import (
    QWEN38_CODEX_PROFILE_ID,
    build_codex_profile_declaration,
    get_codex_profile,
)
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key

_PACKAGED_01671 = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "slaif_gateway"
    / "modules"
    / "clients"
    / "profiles"
    / "codex-0.167.1.json"
)

OPENCODE_RESPONSES_GATES = (
    "codex_request_envelope",
    "codex_client_tools",
    "codex_streaming_tool_events",
    "codex_encrypted_reasoning_replay",
)


def _csrf_from_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _flash_error(html: str) -> str:
    match = re.search(r"admin-flash-error[^>]*>(.*?)</div>", html, re.S)
    assert match is not None
    return re.sub(r"<[^>]+>", " ", match.group(1)).strip()


def _settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET="s" * 40,
        TOKEN_HMAC_SECRET="hmac-secret-for-client-use-tests",
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


async def _seed_admin_and_routes(
    database_url: str,
    *,
    with_codex_route: bool = False,
    with_gateless_responses_route: bool = False,
    with_chat_pricing: bool = True,
    chat_provider_enabled: bool = True,
    chat_provider_kind: str = "openai_compatible",
    responses_route_supports_streaming: bool = True,
) -> dict[str, object]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex[:8]
    profile = get_codex_profile(QWEN38_CODEX_PROFILE_ID)
    assert profile is not None
    try:
        async with session_factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"admin-{uuid.uuid4()}@example.org",
                    display_name="Client Use Admin",
                    password_hash=hash_admin_password("correct horse battery staple"),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"SLAIF Institute {uuid.uuid4()}", country="SI"
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"Cohort {uuid.uuid4()}",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )
                owner = await OwnersRepository(session).create_owner(
                    name="Ada",
                    surname="Lovelace",
                    email=f"owner-{uuid.uuid4()}@example.org",
                    institution_id=institution.id,
                )
                chat_provider = f"chat229-{suffix}"
                session.add(
                    ProviderConfig(
                        provider=chat_provider,
                        display_name="Chat 229 Provider",
                        kind=chat_provider_kind,
                        base_url=f"https://chat229-{suffix}.example/v1",
                        api_key_env_var=f"GUI229_CHAT_{suffix.upper()}_KEY",
                        enabled=chat_provider_enabled,
                    )
                )
                await session.flush()
                session.add(
                    ModelRoute(
                        requested_model="gpt-test",
                        provider=chat_provider,
                        upstream_model="gpt-test",
                        endpoint="/v1/chat/completions",
                        enabled=True,
                    )
                )
                if with_chat_pricing:
                    session.add(
                        PricingRule(
                            provider=chat_provider,
                            upstream_model="gpt-test",
                            endpoint="/v1/chat/completions",
                            input_price_per_1m=Decimal("1.000000000"),
                            cached_input_price_per_1m=Decimal("0.250000000"),
                            output_price_per_1m=Decimal("1.000000000"),
                            reasoning_price_per_1m=Decimal("2.000000000"),
                            request_price=Decimal("0.000000000"),
                            currency="EUR",
                            valid_from=now - timedelta(days=1),
                            enabled=True,
                        )
                    )
                codex_provider = f"syn229-{suffix}"
                session.add(
                    ProviderConfig(
                        provider=codex_provider,
                        display_name="Syn 229 Provider",
                        kind="openai_compatible",
                        base_url=f"https://syn229-{suffix}.example/v1",
                        api_key_env_var=f"GUI229_SYN_{suffix.upper()}_KEY",
                        enabled=True,
                    )
                )
                await session.flush()
                if with_codex_route:
                    session.add(
                        ModelRoute(
                            requested_model=profile.public_model,
                            provider=codex_provider,
                            upstream_model=profile.upstream_model,
                            match_type="exact",
                            endpoint="/v1/responses",
                            priority=1,
                            enabled=True,
                            visible_in_models=True,
                            supports_streaming=responses_route_supports_streaming,
                            capabilities={
                                "responses": {
                                    "text": True,
                                    "stateless": True,
                                    "streaming": True,
                                    **{gate: True for gate in OPENCODE_RESPONSES_GATES},
                                },
                                "codex_limits": {
                                    "context_window_tokens": profile.context_window_tokens,
                                    "default_max_output_tokens": profile.default_max_output_tokens,
                                    "max_output_tokens": profile.max_output_tokens,
                                },
                                "codex_profile": build_codex_profile_declaration(
                                    QWEN38_CODEX_PROFILE_ID
                                ),
                            },
                        )
                    )
                    session.add(
                        PricingRule(
                            provider=codex_provider,
                            upstream_model=profile.upstream_model,
                            endpoint="/v1/responses",
                            input_price_per_1m=Decimal("1.000000000"),
                            cached_input_price_per_1m=Decimal("0.250000000"),
                            output_price_per_1m=Decimal("1.000000000"),
                            reasoning_price_per_1m=Decimal("2.000000000"),
                            request_price=Decimal("0.000000000"),
                            currency="EUR",
                            valid_from=now - timedelta(days=1),
                            enabled=True,
                            pricing_metadata={
                                "codex_accounting": {
                                    "long_context_threshold_tokens": 98304,
                                    "long_context_input_multiplier": "2",
                                    "long_context_output_multiplier": "2",
                                    "cache_write_input_multiplier": "1",
                                }
                            },
                        )
                    )
                elif with_gateless_responses_route:
                    session.add(
                        ModelRoute(
                            requested_model=profile.public_model,
                            provider=codex_provider,
                            upstream_model=profile.upstream_model,
                            match_type="exact",
                            endpoint="/v1/responses",
                            priority=1,
                            enabled=True,
                            visible_in_models=True,
                            supports_streaming=True,
                            capabilities={"responses": {"text": True}},
                        )
                    )
                    session.add(
                        PricingRule(
                            provider=codex_provider,
                            upstream_model=profile.upstream_model,
                            endpoint="/v1/responses",
                            input_price_per_1m=Decimal("1.000000000"),
                            cached_input_price_per_1m=Decimal("0.250000000"),
                            output_price_per_1m=Decimal("1.000000000"),
                            reasoning_price_per_1m=Decimal("2.000000000"),
                            request_price=Decimal("0.000000000"),
                            currency="EUR",
                            valid_from=now - timedelta(days=1),
                            enabled=True,
                        )
                    )
                return {
                    "admin_email": admin.email,
                    "owner_id": owner.id,
                    "cohort_id": cohort.id,
                    "chat_provider": chat_provider,
                    "codex_provider": codex_provider,
                    "qwen_model": profile.public_model,
                }
    finally:
        await engine.dispose()


def _key_rows(database_url: str, owner_id: uuid.UUID) -> list[GatewayKey]:
    async def query() -> list[GatewayKey]:
        engine = create_async_engine(database_url, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                rows = (
                    (
                        await session.execute(
                            select(GatewayKey).where(GatewayKey.owner_id == owner_id)
                        )
                    )
                    .scalars()
                    .all()
                )
                return list(rows)
        finally:
            await engine.dispose()

    return asyncio.run(query())


def _count(database_url: str, model: object) -> int:
    async def query() -> int:
        engine = create_async_engine(database_url, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                result = await session.execute(
                    select(func.count()).select_from(model)  # type: ignore[arg-type]
                )
                return int(result.scalar_one())
        finally:
            await engine.dispose()

    return asyncio.run(query())


def _created_audit_count(database_url: str) -> int:
    async def query() -> int:
        engine = create_async_engine(database_url, future=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                result = await session.execute(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(
                        AuditLog.entity_type == "gateway_key",
                        AuditLog.action == "gateway_key_created",
                    )
                )
                return int(result.scalar_one())
        finally:
            await engine.dispose()

    return asyncio.run(query())


def _login(client: TestClient, admin_email: str) -> str:
    login_page = client.get("/admin/login")
    csrf = _csrf_from_html(login_page.text)
    login = client.post(
        "/admin/login",
        data={
            "email": admin_email,
            "password": "correct horse battery staple",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert login.status_code == 303
    create_page = client.get("/admin/keys/create")
    assert create_page.status_code == 200
    return _csrf_from_html(create_page.text)


def _base_form(csrf: str, data: dict[str, object]) -> dict[str, str]:
    return {
        "csrf_token": csrf,
        "owner_id": str(data["owner_id"]),
        "cohort_id": str(data["cohort_id"]),
        "valid_days": "30",
        "reason": "client-use integration",
        "rate_limit_requests_per_minute": "60",
        "rate_limit_tokens_per_minute": "12000",
        "rate_limit_concurrent_requests": "4",
        "rate_limit_window_seconds": "30",
    }


def test_gui_create_opencode_chat_preset_persists_active_pin(
    migrated_postgres_url: str,
) -> None:
    data = asyncio.run(
        _seed_admin_and_routes(migrated_postgres_url, with_codex_route=False)
    )
    owner_id = data["owner_id"]
    assert isinstance(owner_id, uuid.UUID)
    bootstrap_agent_chat_client_modules()
    expected_pin = active_client_module_facts(
        OPENCODE_1193_CHAT_CLIENT_MODULE_ID
    ).pin
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        csrf = _login(client, data["admin_email"])
        response = client.post(
            "/admin/keys/create",
            data={
                **_base_form(csrf, data),
                "client_use_opencode_chat": "true",
                "allowed_providers": data["chat_provider"],
                "allowed_models": "gpt-test",
                "allowed_endpoints": "/v1/chat/completions",
            },
        )
        assert response.status_code == 200
        assert "Chat client module" in response.text
        assert expected_pin["id"] in response.text
        assert "token_hash" not in response.text
    keys = _key_rows(migrated_postgres_url, owner_id)
    assert len(keys) == 1
    assert keys[0].metadata_json.get("chat_client_module") == expected_pin
    assert keys[0].metadata_json.get("responses_policy") is None
    assert "/v1/chat/completions" in keys[0].allowed_endpoints


def test_gui_create_hermes_preset_persists_active_pin(migrated_postgres_url: str) -> None:
    data = asyncio.run(
        _seed_admin_and_routes(migrated_postgres_url, with_codex_route=False)
    )
    owner_id = data["owner_id"]
    assert isinstance(owner_id, uuid.UUID)
    bootstrap_agent_chat_client_modules()
    expected_pin = active_client_module_facts(
        HERMES_0225_CHAT_CLIENT_MODULE_ID
    ).pin
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        csrf = _login(client, data["admin_email"])
        response = client.post(
            "/admin/keys/create",
            data={
                **_base_form(csrf, data),
                "client_use_hermes": "true",
                "allowed_providers": data["chat_provider"],
                "allowed_models": "gpt-test",
                "allowed_endpoints": "/v1/chat/completions",
            },
        )
        assert response.status_code == 200
        assert "Chat client module" in response.text
        assert expected_pin["id"] in response.text
    keys = _key_rows(migrated_postgres_url, owner_id)
    assert len(keys) == 1
    assert keys[0].metadata_json.get("chat_client_module") == expected_pin
    assert keys[0].metadata_json.get("responses_policy") is None


def test_gui_create_opencode_responses_preset_persists_gates_and_pin(
    migrated_postgres_url: str,
) -> None:
    data = asyncio.run(_seed_admin_and_routes(migrated_postgres_url, with_codex_route=True))
    owner_id = data["owner_id"]
    assert isinstance(owner_id, uuid.UUID)
    expected_policy = {
        "version": 1,
        "allowed_capabilities": list(OPENCODE_RESPONSES_GATES),
        "allowed_local_tool_types": ["function", "custom"],
        "client_module": active_client_module_facts(
            OPENCODE_1193_RESPONSES_CLIENT_MODULE_ID
        ).pin,
    }
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        csrf = _login(client, data["admin_email"])
        response = client.post(
            "/admin/keys/create",
            data={
                **_base_form(csrf, data),
                "client_use_opencode_responses": "true",
                "allowed_providers": data["codex_provider"],
                "allowed_models": data["qwen_model"],
                "allowed_endpoints": "/v1/responses",
            },
        )
        assert response.status_code == 200
        assert "Responses client module" in response.text
    keys = _key_rows(migrated_postgres_url, owner_id)
    assert len(keys) == 1
    assert keys[0].metadata_json.get("responses_policy") == expected_policy
    assert keys[0].metadata_json.get("chat_client_module") is None


def test_gui_create_conflicting_client_uses_fail_before_effects(
    migrated_postgres_url: str,
) -> None:
    data = asyncio.run(
        _seed_admin_and_routes(migrated_postgres_url, with_codex_route=False)
    )
    owner_id = data["owner_id"]
    assert isinstance(owner_id, uuid.UUID)
    emails_before = _count(migrated_postgres_url, EmailDelivery)
    audits_before = _created_audit_count(migrated_postgres_url)
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        csrf = _login(client, data["admin_email"])
        response = client.post(
            "/admin/keys/create",
            data={
                **_base_form(csrf, data),
                "client_use_opencode_chat": "true",
                "client_use_hermes": "true",
                "allowed_providers": data["chat_provider"],
                "allowed_models": "gpt-test",
                "allowed_endpoints": "/v1/chat/completions",
            },
        )
        assert response.status_code == 400
        assert "single Chat client binding" in response.text
        # The operator can correct the form; the entered values are kept.
        assert 'value="true"' in response.text
    assert _key_rows(migrated_postgres_url, owner_id) == []
    assert _count(migrated_postgres_url, EmailDelivery) == emails_before
    assert _created_audit_count(migrated_postgres_url) == audits_before


def test_gui_create_opencode_responses_gateless_route_fails_closed(
    migrated_postgres_url: str,
) -> None:
    data = asyncio.run(
        _seed_admin_and_routes(
            migrated_postgres_url, with_gateless_responses_route=True
        )
    )
    owner_id = data["owner_id"]
    assert isinstance(owner_id, uuid.UUID)
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        csrf = _login(client, data["admin_email"])
        response = client.post(
            "/admin/keys/create",
            data={
                **_base_form(csrf, data),
                "client_use_opencode_responses": "true",
                "allowed_providers": data["codex_provider"],
                "allowed_models": data["qwen_model"],
                "allowed_endpoints": "/v1/responses",
            },
        )
        assert response.status_code == 400
        assert "four OpenCode Responses gates" in _flash_error(response.text)
    assert _key_rows(migrated_postgres_url, owner_id) == []


def _run_rev_create_subprocess(
    migrated_postgres_url: str,
    profile_path: Path,
    combo: str | None = None,
) -> dict[str, object]:
    script = Path(__file__).with_name("_key_create_client_use_rev16_script.py")
    args = [str(script), migrated_postgres_url, str(profile_path)]
    if combo is not None:
        args.append(combo)
    completed = subprocess.run(
        [
            sys.executable,
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(script.parents[2]),
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    line = completed.stdout.strip().splitlines()[-1]
    return json.loads(line)


def _expected_pin_for_profile_file(profile_path: Path) -> dict[str, str]:
    module = build_codex_0162_client_module(load_codex_profile_file(profile_path))
    return {
        "id": module.module_id,
        "version": module.module_version,
        "fixture_sha256": module.fixture_sha256,
    }


def test_gui_create_codex_under_active_rev16_profile(migrated_postgres_url: str, tmp_path: Path) -> None:
    """Evidence 1a: the packaged codex-0.167.1 (revision 16) module is
    accepted for a route qualified against frozen v8 evidence, and the NEW
    key pins the ACTIVE rev16 identity. No GUI version constants patched."""
    rev16 = tmp_path / "codex-0.167.1.json"
    rev16.write_bytes(_PACKAGED_01671.read_bytes())
    expected = _expected_pin_for_profile_file(rev16)
    assert expected["version"] == "16"
    profile = get_codex_profile(QWEN38_CODEX_PROFILE_ID)
    assert profile is not None
    assert profile.client_module_version == "8"  # frozen evidence, not a gate

    outcome = _run_rev_create_subprocess(migrated_postgres_url, rev16)
    assert outcome["status"] == 200, outcome
    assert outcome["key_count"] == 1
    policy = outcome["responses_policy"]
    assert policy is not None
    assert policy["client_module"] == expected


def test_gui_create_codex_under_synthetic_later_revision(
    migrated_postgres_url: str, tmp_path: Path
) -> None:
    """Evidence 1b: a clearly synthetic later revision (17) using the same
    supported representation works through the same unpatched GUI path."""
    document = json.loads(_PACKAGED_01671.read_text(encoding="utf-8"))
    document["revision"] = "17"
    rev17 = tmp_path / "codex-0.167.1-rev17-synthetic.json"
    rev17.write_text(json.dumps(document), encoding="utf-8")
    expected = _expected_pin_for_profile_file(rev17)
    assert expected["version"] == "17"
    assert expected["fixture_sha256"] != _expected_pin_for_profile_file(_PACKAGED_01671)["fixture_sha256"]

    outcome = _run_rev_create_subprocess(migrated_postgres_url, rev17)
    assert outcome["status"] == 200, outcome
    assert outcome["key_count"] == 1
    assert outcome["responses_policy"] is not None
    assert outcome["responses_policy"]["client_module"] == expected


# ---------------------------------------------------------------------------
# 229-b: working Codex + Chat-client combinations and readiness negatives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("combo", ["hermes", "opencode_chat"])
def test_gui_create_codex_plus_chat_combo_under_active_rev16_profile(
    migrated_postgres_url: str, tmp_path: Path, combo: str
) -> None:
    """Codex plus one Chat client on one key: the server adds the Chat
    preset endpoint (the POST lists only the Codex endpoints) and pins BOTH
    client profiles (active rev16 Codex + the active Chat module)."""
    rev16 = tmp_path / "codex-0.167.1.json"
    rev16.write_bytes(_PACKAGED_01671.read_bytes())
    expected_codex = _expected_pin_for_profile_file(rev16)
    chat_module_id = (
        HERMES_0225_CHAT_CLIENT_MODULE_ID
        if combo == "hermes"
        else OPENCODE_1193_CHAT_CLIENT_MODULE_ID
    )
    expected_chat = active_client_module_facts(chat_module_id).pin

    outcome = _run_rev_create_subprocess(migrated_postgres_url, rev16, combo)
    assert outcome["status"] == 200, outcome
    assert outcome["key_count"] == 1
    policy = outcome["responses_policy"]
    assert policy is not None
    assert policy["client_module"] == expected_codex
    assert outcome["chat_client_module"] == expected_chat
    assert set(outcome["allowed_endpoints"]) == {
        "/v1/models",
        "/v1/responses",
        "/v1/chat/completions",
    }


def test_gui_create_hermes_without_chat_pricing_fails_before_effects(
    migrated_postgres_url: str,
) -> None:
    data = asyncio.run(
        _seed_admin_and_routes(
            migrated_postgres_url, with_chat_pricing=False
        )
    )
    owner_id = data["owner_id"]
    assert isinstance(owner_id, uuid.UUID)
    emails_before = _count(migrated_postgres_url, EmailDelivery)
    audits_before = _created_audit_count(migrated_postgres_url)
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        csrf = _login(client, data["admin_email"])
        response = client.post(
            "/admin/keys/create",
            data={
                **_base_form(csrf, data),
                "client_use_hermes": "true",
                "allowed_providers": data["chat_provider"],
                "allowed_models": "gpt-test",
                "allowed_endpoints": "/v1/chat/completions",
            },
        )
        assert response.status_code == 400
        assert "Pricing: no active pricing rule" in _flash_error(response.text)
    assert _key_rows(migrated_postgres_url, owner_id) == []
    assert _count(migrated_postgres_url, EmailDelivery) == emails_before
    assert _created_audit_count(migrated_postgres_url) == audits_before


def test_gui_create_hermes_with_disabled_provider_fails_before_effects(
    migrated_postgres_url: str,
) -> None:
    data = asyncio.run(
        _seed_admin_and_routes(
            migrated_postgres_url, chat_provider_enabled=False
        )
    )
    owner_id = data["owner_id"]
    assert isinstance(owner_id, uuid.UUID)
    emails_before = _count(migrated_postgres_url, EmailDelivery)
    audits_before = _created_audit_count(migrated_postgres_url)
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        csrf = _login(client, data["admin_email"])
        response = client.post(
            "/admin/keys/create",
            data={
                **_base_form(csrf, data),
                "client_use_hermes": "true",
                "allowed_providers": data["chat_provider"],
                "allowed_models": "gpt-test",
                "allowed_endpoints": "/v1/chat/completions",
            },
        )
        assert response.status_code == 400
        # The existing provider tri-state parser is the first line of
        # defense for a disabled provider (it only offers enabled
        # configs); it fails the create before any key/email/audit effect.
        assert "A selected provider is not available" in _flash_error(response.text)
    assert _key_rows(migrated_postgres_url, owner_id) == []
    assert _count(migrated_postgres_url, EmailDelivery) == emails_before
    assert _created_audit_count(migrated_postgres_url) == audits_before


def test_gui_create_hermes_with_unregistered_module_provider_fails_before_effects(
    migrated_postgres_url: str,
) -> None:
    data = asyncio.run(
        _seed_admin_and_routes(
            migrated_postgres_url, chat_provider_kind="module"
        )
    )
    owner_id = data["owner_id"]
    assert isinstance(owner_id, uuid.UUID)
    emails_before = _count(migrated_postgres_url, EmailDelivery)
    audits_before = _created_audit_count(migrated_postgres_url)
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        csrf = _login(client, data["admin_email"])
        response = client.post(
            "/admin/keys/create",
            data={
                **_base_form(csrf, data),
                "client_use_hermes": "true",
                "allowed_providers": data["chat_provider"],
                "allowed_models": "gpt-test",
                "allowed_endpoints": "/v1/chat/completions",
            },
        )
        assert response.status_code == 400
        assert "not a registered server module" in _flash_error(response.text)
    assert _key_rows(migrated_postgres_url, owner_id) == []
    assert _count(migrated_postgres_url, EmailDelivery) == emails_before
    assert _created_audit_count(migrated_postgres_url) == audits_before


def test_gui_create_opencode_responses_non_streaming_route_fails_before_effects(
    migrated_postgres_url: str,
) -> None:
    data = asyncio.run(
        _seed_admin_and_routes(
            migrated_postgres_url,
            with_codex_route=True,
            responses_route_supports_streaming=False,
        )
    )
    owner_id = data["owner_id"]
    assert isinstance(owner_id, uuid.UUID)
    emails_before = _count(migrated_postgres_url, EmailDelivery)
    audits_before = _created_audit_count(migrated_postgres_url)
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        csrf = _login(client, data["admin_email"])
        response = client.post(
            "/admin/keys/create",
            data={
                **_base_form(csrf, data),
                "client_use_opencode_responses": "true",
                "allowed_providers": data["codex_provider"],
                "allowed_models": data["qwen_model"],
                "allowed_endpoints": "/v1/responses",
            },
        )
        assert response.status_code == 400
        assert "does not support streaming" in _flash_error(response.text)
    assert _key_rows(migrated_postgres_url, owner_id) == []
    assert _count(migrated_postgres_url, EmailDelivery) == emails_before
    assert _created_audit_count(migrated_postgres_url) == audits_before
