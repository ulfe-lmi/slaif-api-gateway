"""210-a GUI reviewed route configuration: owned PostgreSQL tests.

Real-app, real-PostgreSQL qualification for the 210-a reviewed
route-configuration workflow and the provider preparation additions,
against the qualified owned, labeled, loopback-bound, tmpfs-backed
PostgreSQL fixture (supplied as TEST_DATABASE_URL by the runner,
exactly like the 207/208/209 modules):

- the READ-ONLY preview (zero writes, zero audits, unrelated rows
  untouched);
- the reviewed apply (exact canonical final state persisted, ONE
  ``model_route_updated`` audit with actor + reason, unrelated control
  route preserved);
- the SAME-original-reviewed-plan repeat (refused stale, zero writes,
  zero new audits);
- the TRUE stale destination-provider context (provider modified
  between plan and apply -> refused, zero writes/audits);
- the late-failure rollback (injected failure after the provisional
  update rolls back the whole caller transaction: route state AND any
  provisional audit);
- the zero-diff no-op (fresh plan matching the current state: zero
  writes, zero audits);
- provider CREATE prepared DISABLED by default (explicit enable still
  works), provider EDIT lock-first full update with the notes intents
  (clear = real old notes -> null in ONE audited update);
- route CREATE intent: the shared read-only creation validation runs
  in the caller transaction before the write (the zero-retries
  completion rule refuses a retrying module provider with NO row
  written), and the legacy no-intent checkbox semantics persist
  unchanged.

Coexistence: this module inserts provider configs ONLY under
run-unique slugs (210-*); the seeded routes use run-unique requested
models, so the module shares the session database with the 207/208/
209 modules without touching their rows. All oracles are scoped to
THIS seed's admin user / route ids / provider slugs.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, ModelRoute, ProviderConfig
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.main import create_app
from slaif_gateway.services.model_route_service import ModelRouteService
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r'name="route_config_review_intent" value="([^"]+)"')

ADMIN_PASSWORD = "correct horse battery staple"
APPLY_REASON = "210 reviewed route normalization"
CLEAR_REASON = "210 reviewed route notes cleared"
NEW_NOTES = "210 updated route notes"
OLD_NOTES = "210 route notes"

CHAT_BLOCK = {
    "chat_text": True,
    "chat_streaming": True,
    "chat_function_tools": False,
}
CODEX_BLOCK = {
    "context_window_tokens": 1050000,
    "default_max_output_tokens": 32768,
    "max_output_tokens": 128000,
}


def _settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET=generate_secret_key(),
        TOKEN_HMAC_SECRET=generate_secret_key(),
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


def _engine(database_url: str):
    return create_async_engine(database_url, future=True)


def asyncio_run(coro):
    return asyncio.run(coro)


async def _seed(database_url: str) -> dict[str, Any]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC)
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui210-{suffix}@example.org",
                    display_name="210 Route GUI Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                providers = ProviderConfigsRepository(session)
                compatible = await providers.create_provider_config(
                    provider=f"210compat-{suffix}",
                    display_name="210 Compat",
                    kind="openai_compatible",
                    base_url=f"https://svc-210-{suffix}.example/v1",
                    api_key_env_var="GUI210_SVC_KEY",
                    enabled=True,
                    timeout_seconds=300,
                    max_retries=0,
                    notes="210 compatible provider notes",
                )
                module_retry = await providers.create_provider_config(
                    provider=f"210mod-{suffix}",
                    display_name="210 Module Retry",
                    kind="module",
                    base_url=f"https://mod-210-{suffix}.example",
                    api_key_env_var="GUI210_MOD_KEY",
                    enabled=False,
                    timeout_seconds=60,
                    max_retries=2,  # deliberately non-zero (zero-retries rule)
                    notes=None,
                )
                routes = ModelRoutesRepository(session)
                base_caps = {
                    "chat_completions": dict(CHAT_BLOCK),
                    "codex_limits": dict(CODEX_BLOCK),
                }

                def _route(name: str, provider: ProviderConfig, **extra: Any) -> dict[str, Any]:
                    return dict(
                        requested_model=f"210-{name}-{suffix}",
                        match_type="exact",
                        endpoint="/v1/chat/completions",
                        provider=provider.provider,
                        upstream_model=f"210-{name}-{suffix}",
                        priority=100,
                        enabled=True,
                        visible_in_models=True,
                        supports_streaming=True,
                        capabilities=dict(extra.pop("capabilities", base_caps)),
                        notes=extra.pop("notes", OLD_NOTES),
                        **extra,
                    )

                r1 = await routes.create_model_route(**_route("main", compatible))
                r2 = await routes.create_model_route(**_route("control", compatible))
                r3 = await routes.create_model_route(**_route("staleprov", compatible))
                r4 = await routes.create_model_route(**_route("latefail", compatible))
                return {
                    "suffix": suffix,
                    "admin_id": str(admin.id),
                    "admin_email": str(admin.email),
                    "compatible_slug": compatible.provider,
                    "module_slug": module_retry.provider,
                    "compatible_id": str(compatible.id),
                    "module_id": str(module_retry.id),
                    "r1": str(r1.id),
                    "r2": str(r2.id),
                    "r3": str(r3.id),
                    "r4": str(r4.id),
                    "now": now,
                }
    finally:
        await engine.dispose()


_SEED_CACHE: dict[str, dict[str, Any]] = {}


def _seed_sync(database_url: str) -> dict[str, Any]:
    if database_url not in _SEED_CACHE:
        _SEED_CACHE[database_url] = asyncio_run(_seed(database_url))
    return _SEED_CACHE[database_url]


# ---------------------------------------------------------------------------
# DB oracles (scoped to THIS seed)
# ---------------------------------------------------------------------------


async def _routes_snapshot(database_url: str, route_ids: tuple[str, ...]) -> dict[str, tuple]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(ModelRoute).where(ModelRoute.id.in_([uuid.UUID(r) for r in route_ids]))
                    )
                )
                .scalars()
                .all()
            )
        out = {}
        for row in rows:
            out[str(row.id)] = (
                row.requested_model,
                row.match_type,
                row.endpoint,
                row.provider,
                row.upstream_model,
                row.priority,
                row.enabled,
                row.visible_in_models,
                row.supports_streaming,
                tuple(sorted(row.capabilities.items(), key=lambda kv: str(kv[0]))),
                row.notes,
                row.created_at,
                row.updated_at,
            )
        return out
    finally:
        await engine.dispose()


async def _provider_snapshot(database_url: str, provider_id: str) -> tuple:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = (
                (
                    await session.execute(
                        select(ProviderConfig).where(
                            ProviderConfig.id == uuid.UUID(provider_id)
                        )
                    )
                )
                .scalars()
                .first()
            )
        if row is None:
            return ()
        return (
            row.provider,
            row.display_name,
            row.kind,
            row.base_url,
            row.api_key_env_var,
            row.enabled,
            row.timeout_seconds,
            row.max_retries,
            row.notes,
            row.updated_at,
        )
    finally:
        await engine.dispose()


async def _route_audits(database_url: str, route_id: str, admin_id: str) -> list[dict[str, Any]]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.entity_type == "model_route",
                            AuditLog.entity_id == uuid.UUID(route_id),
                            AuditLog.admin_user_id == uuid.UUID(admin_id),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return [
            {
                "action": r.action,
                "old": r.old_values,
                "new": r.new_values,
                "note": r.note,
            }
            for r in rows
        ]
    finally:
        await engine.dispose()


async def _provider_audits(database_url: str, provider_id: str, admin_id: str) -> list[dict[str, Any]]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.entity_type == "provider_config",
                            AuditLog.entity_id == uuid.UUID(provider_id),
                            AuditLog.admin_user_id == uuid.UUID(admin_id),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return [
            {
                "action": r.action,
                "old": r.old_values,
                "new": r.new_values,
                "note": r.note,
            }
            for r in rows
        ]
    finally:
        await engine.dispose()


def _snap(data: dict[str, Any]) -> dict[str, tuple]:
    ids = (data["r1"], data["r2"], data["r3"], data["r4"])
    return asyncio_run(_routes_snapshot(data["database_url"], ids))


# ---------------------------------------------------------------------------
# Module fixture: real app + real login on the owned PG
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def route_env(migrated_postgres_url: str) -> Iterator[dict[str, Any]]:
    data = _seed_sync(migrated_postgres_url)
    app = create_app(_settings(migrated_postgres_url))
    with TestClient(app) as client:
        _login(client, str(data["admin_email"]))
        data["client"] = client
        data["database_url"] = migrated_postgres_url
        yield data


def _login(client: TestClient, admin_email: str) -> None:
    login_page = client.get("/admin/login")
    csrf = CSRF_RE.search(login_page.text).group(1)
    response = client.post(
        "/admin/login",
        data={"email": admin_email, "password": ADMIN_PASSWORD, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _csrf(client: TestClient, page: str) -> str:
    html = client.get(page)
    assert html.status_code == 200, html.text[:400]
    return CSRF_RE.search(html.text).group(1)


def _plan_fields(data: dict[str, Any], csrf: str, route_id: str, **extra: Any) -> dict[str, str]:
    fields: dict[str, str] = {
        "csrf_token": csrf,
        "capabilities_source": "unchanged",
        "requested_model_action": "unchanged",
        "match_type_action": "unchanged",
        "endpoint_action": "unchanged",
        "provider_action": "unchanged",
        "upstream_model_action": "unchanged",
        "priority_action": "unchanged",
        "visible_in_models_action": "unchanged",
        "supports_streaming_action": "unchanged",
        "notes_intent": "preserve",
        "codex_context_action": "unchanged",
        "codex_default_output_action": "unchanged",
        "codex_max_output_action": "unchanged",
        "media_image_action": "unchanged",
        "media_video_tokens_action": "unchanged",
        "media_video_frames_action": "unchanged",
        "completion_action": "unchanged",
    }
    fields.update(extra)
    return fields


def _make_plan(data: dict[str, Any], route_id: str, **extra: Any) -> str:
    """POST the READ-ONLY plan and return the signed review token."""
    csrf = _csrf(data["client"], f"/admin/routes/{route_id}/configuration")
    response = data["client"].post(
        f"/admin/routes/{route_id}/configuration/plan",
        data=_plan_fields(data, csrf, route_id, **extra),
        follow_redirects=False,
    )
    assert response.status_code == 200, response.text[:600]
    match = TOKEN_RE.search(response.text)
    assert match is not None, "review token missing from plan page"
    return match.group(1)


def _apply(
    data: dict[str, Any], route_id: str, token: str, *, reason: str = APPLY_REASON
) -> Any:
    return data["client"].post(
        f"/admin/routes/{route_id}/configuration/apply",
        data={
            "csrf_token": _csrf(data["client"], f"/admin/routes/{route_id}/configuration"),
            "route_config_review_intent": token,
            "confirm_apply": "true",
            "reason": reason,
        },
        follow_redirects=False,
    )


# ---------------------------------------------------------------------------
# (a) READ-ONLY preview
# ---------------------------------------------------------------------------


def test_preview_is_read_only(route_env) -> None:
    data = route_env
    route_id = data["r1"]
    before = _snap(data)
    audits_before = asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    )
    provider_before = asyncio_run(
        _provider_snapshot(data["database_url"], data["compatible_id"])
    )
    assert len(before) == 4
    assert audits_before == []

    _make_plan(data, route_id, priority_action="set", priority="55")

    assert _snap(data) == before
    assert asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    ) == audits_before
    assert asyncio_run(
        _provider_snapshot(data["database_url"], data["compatible_id"])
    ) == provider_before


# ---------------------------------------------------------------------------
# (b) reviewed apply: exact state + one audit + unrelated rows preserved
# ---------------------------------------------------------------------------


def test_apply_persists_exact_canonical_state_with_one_audit(route_env) -> None:
    data = route_env
    route_id = data["r1"]
    token = _make_plan(
        data,
        route_id,
        priority_action="set",
        priority="55",
        notes_intent="replace",
        notes=NEW_NOTES,
    )
    response = _apply(data, route_id, token)
    assert response.status_code == 200, response.text[:600]
    assert "The reviewed plan was applied" in response.text

    after = _snap(data)
    row = after[route_id]
    # exact canonical final state: ONLY the requested leaves moved
    assert row[5] == 55  # priority
    assert row[10] == NEW_NOTES  # notes
    assert row[9] == tuple(
        sorted(
            {
                "chat_completions": dict(CHAT_BLOCK),
                "codex_limits": dict(CODEX_BLOCK),
            }.items(),
            key=lambda kv: str(kv[0]),
        )
    )
    assert row[0] == f"210-main-{data['suffix']}"
    # the unrelated control route is preserved byte-for-byte (except it
    # was never touched at all)
    control = after[data["r2"]]
    assert control[5] == 100
    assert control[10] == OLD_NOTES

    audits = asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    )
    assert len(audits) == 1
    assert audits[0]["action"] == "model_route_updated"
    assert audits[0]["note"] == APPLY_REASON
    # the control route has NO audits from this seed admin
    assert asyncio_run(
        _route_audits(data["database_url"], data["r2"], data["admin_id"])
    ) == []


def test_repeat_apply_of_same_reviewed_plan_is_stale(route_env) -> None:
    data = route_env
    route_id = data["r1"]
    # a FRESH plan over the now-changed state applies ONCE ...
    token = _make_plan(data, route_id, priority_action="set", priority="40")
    response = _apply(data, route_id, token)
    assert response.status_code == 200, response.text[:600]
    assert "The reviewed plan was applied" in response.text
    after_first = _snap(data)
    audits_after_first = asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    )
    # ... and the SAME reviewed plan repeated is refused stale (the
    # fresh pre-state no longer matches the reviewed expectation)
    response = _apply(data, route_id, token)
    assert response.status_code == 400
    assert "stale" in response.text.lower() or "no longer" in response.text.lower()
    assert _snap(data) == after_first
    assert asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    ) == audits_after_first


# ---------------------------------------------------------------------------
# (c) TRUE stale destination provider context
# ---------------------------------------------------------------------------


def test_stale_destination_provider_context_refused(route_env) -> None:
    data = route_env
    route_id = data["r3"]
    provider_id = data["compatible_id"]
    token = _make_plan(data, route_id, priority_action="set", priority="33")
    provider_before = asyncio_run(
        _provider_snapshot(data["database_url"], provider_id)
    )
    route_before = _snap(data)
    audits_before = asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    )

    # directly mutate the provider (a later change the review never saw)
    async def _mutate() -> None:
        engine = _engine(data["database_url"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    row = (
                        (
                            await session.execute(
                                select(ProviderConfig).where(
                                    ProviderConfig.id == uuid.UUID(provider_id)
                                )
                            )
                        )
                        .scalars()
                        .first()
                    )
                    row.timeout_seconds = 420
        finally:
            await engine.dispose()

    asyncio_run(_mutate())
    response = _apply(data, route_id, token)
    assert response.status_code == 400
    assert "no longer matches" in response.text

    assert _snap(data) == route_before
    assert asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    ) == audits_before
    # restore the provider for the other tests
    async def _restore() -> None:
        engine = _engine(data["database_url"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    row = (
                        (
                            await session.execute(
                                select(ProviderConfig).where(
                                    ProviderConfig.id == uuid.UUID(provider_id)
                                )
                            )
                        )
                        .scalars()
                        .first()
                    )
                    row.timeout_seconds = provider_before[6]
        finally:
            await engine.dispose()

    asyncio_run(_restore())


# ---------------------------------------------------------------------------
# (d) late-failure rollback of the whole caller transaction
# ---------------------------------------------------------------------------


def test_late_failure_rolls_back_route_state_and_audit(route_env, monkeypatch) -> None:
    data = route_env
    route_id = data["r4"]
    token = _make_plan(data, route_id, priority_action="set", priority="44")
    before = _snap(data)
    audits_before = asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    )

    original_update = ModelRouteService.update_model_route

    async def poisoned_update(self, route_id_arg, **kwargs: Any) -> Any:
        # perform the REAL provisional update (flushed into the caller
        # transaction) and then fail LATE: the caller transaction must
        # roll back both the row state and the provisional audit
        await original_update(self, route_id_arg, **kwargs)
        raise ValueError("injected late failure after provisional update")

    monkeypatch.setattr(ModelRouteService, "update_model_route", poisoned_update)
    response = _apply(data, route_id, token)
    assert response.status_code == 400
    assert _snap(data) == before
    assert asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    ) == audits_before


# ---------------------------------------------------------------------------
# (e) zero-diff no-op: zero writes, zero audits
# ---------------------------------------------------------------------------


def test_zero_diff_plan_is_noop_without_audit(route_env) -> None:
    data = route_env
    route_id = data["r2"]
    before = _snap(data)
    audits_before = asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    )
    token = _make_plan(data, route_id)  # no edits: zero-diff plan
    response = _apply(data, route_id, token)
    assert response.status_code == 200, response.text[:600]
    assert "zero-diff no-op" in response.text
    after = _snap(data)
    # no write at all: even updated_at is unchanged
    assert after == before
    assert asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    ) == audits_before


# ---------------------------------------------------------------------------
# (f) provider CREATE prepared disabled + provider EDIT notes intents
# ---------------------------------------------------------------------------


def test_provider_create_prepares_disabled_by_default(route_env) -> None:
    data = route_env
    csrf = _csrf(data["client"], "/admin/providers/new")
    slug = f"210new-{data['suffix']}"
    response = data["client"].post(
        "/admin/providers/new",
        data={
            "csrf_token": csrf,
            "provider": slug,
            "display_name": "210 New Provider",
            "kind": "openai_compatible",
            "base_url": f"https://new-210-{data['suffix']}.example/v1",
            "api_key_env_var": "GUI210_NEW_KEY",
            "timeout_seconds": "120",
            "max_retries": "1",
            "notes": "210 new provider notes",
            "reason": "210 add provider prepared disabled",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text[:400]

    async def _read() -> tuple:
        engine = _engine(data["database_url"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                row = (
                    (
                        await session.execute(
                            select(ProviderConfig).where(
                                ProviderConfig.provider == slug
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
            assert row is not None
            return (row.enabled, row.notes, row.max_retries)
        finally:
            await engine.dispose()

    enabled, notes, retries = asyncio_run(_read())
    assert enabled is False  # prepared disabled by default
    assert notes == "210 new provider notes"
    assert retries == 1
    audits = asyncio_run(
        _provider_audits_by_slug(data["database_url"], slug, data["admin_id"])
    )
    assert len(audits) == 1
    assert audits[0]["action"] == "provider_config_created"


async def _provider_audits_by_slug(database_url: str, slug: str, admin_id: str):
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            provider = (
                (
                    await session.execute(
                        select(ProviderConfig).where(ProviderConfig.provider == slug)
                    )
                )
                .scalars()
                .first()
            )
            rows = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.entity_type == "provider_config",
                            AuditLog.entity_id == provider.id,
                            AuditLog.admin_user_id == uuid.UUID(admin_id),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return [
            {
                "action": r.action,
                "old": r.old_values,
                "new": r.new_values,
                "note": r.note,
            }
            for r in rows
        ]
    finally:
        await engine.dispose()


def test_provider_edit_clear_notes_records_real_prior_in_one_audit(route_env) -> None:
    data = route_env
    provider_id = data["module_id"]
    before = asyncio_run(
        _provider_snapshot(data["database_url"], provider_id)
    )
    assert before[8] is None  # seeded module provider has no notes
    # give it notes first (replace), then clear them in a second edit
    def _edit(**extra: Any) -> Any:
        csrf = _csrf(
            data["client"], f"/admin/providers/{provider_id}/edit"
        )
        payload = {
            "csrf_token": csrf,
            "provider": data["module_slug"],
            "display_name": "210 Module Retry",
            "kind": "module",
            "base_url": f"https://mod-210-{data['suffix']}.example",
            "api_key_env_var": "GUI210_MOD_KEY",
            "enabled": "",
            "timeout_seconds": "60",
            "max_retries": "2",
            "notes": "",
            "notes_intent": "replace",
            "reason": "210 provider notes change",
        }
        payload.update(extra)
        return data["client"].post(
            f"/admin/providers/{provider_id}/edit",
            data=payload,
            follow_redirects=False,
        )

    response = _edit(notes="210 module notes")
    assert response.status_code == 303, response.text[:400]
    replaced = asyncio_run(_provider_snapshot(data["database_url"], provider_id))
    assert replaced[8] == "210 module notes"

    response = _edit(notes_intent="clear")
    assert response.status_code == 303, response.text[:400]
    cleared = asyncio_run(_provider_snapshot(data["database_url"], provider_id))
    assert cleared[8] is None

    audits = asyncio_run(
        _provider_audits(data["database_url"], provider_id, data["admin_id"])
    )
    assert [a["action"] for a in audits] == [
        "provider_config_updated",
        "provider_config_updated",
    ]
    clear_audit = audits[-1]
    assert clear_audit["note"] == "210 provider notes change"
    assert clear_audit["old"]["notes"] == "210 module notes"
    assert clear_audit["new"]["notes"] is None


# ---------------------------------------------------------------------------
# (g) route CREATE intent: real shared validation in the caller
# transaction; legacy checkbox preserved
# ---------------------------------------------------------------------------


def test_route_create_intent_refuses_retrying_module_provider(route_env) -> None:
    data = route_env
    csrf = _csrf(data["client"], "/admin/routes/new")
    response = data["client"].post(
        "/admin/routes/new",
        data={
            "csrf_token": csrf,
            "creation_intent": "automatic",
            "requested_model": f"210-refused-{data['suffix']}",
            "match_type": "exact",
            "endpoint": "chat.completions",
            "provider": data["module_slug"],
            "upstream_model": f"210-refused-{data['suffix']}",
            "priority": "100",
            "capabilities": (
                '{"completion_service": {"version": 1, '
                '"profile": "facial-scoring-v1"}}'
            ),
            "notes": "",
            "reason": "210 refused completion route",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "max_retries must be 0" in response.text

    async def _count() -> int:
        engine = _engine(data["database_url"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                return (
                    (
                        await session.execute(
                            select(ModelRoute).where(
                                ModelRoute.requested_model
                                == f"210-refused-{data['suffix']}"
                            )
                        )
                    )
                    .scalars()
                    .first()
                    is None
                )
        finally:
            await engine.dispose()

    assert asyncio_run(_count()) is True  # NO route row was written


def test_route_create_legacy_checkbox_semantics_preserved(route_env) -> None:
    data = route_env
    csrf = _csrf(data["client"], "/admin/routes/new")
    requested = f"210-legacy-{data['suffix']}"
    response = data["client"].post(
        "/admin/routes/new",
        data={
            "csrf_token": csrf,
            # NO creation_intent field: legacy enabled checkbox wins
            "enabled": "true",
            "requested_model": requested,
            "match_type": "exact",
            "endpoint": "chat.completions",
            "provider": data["compatible_slug"],
            "upstream_model": requested,
            "priority": "90",
            "capabilities": "",
            "notes": "",
            "reason": "210 legacy route creation",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text[:400]

    async def _read() -> tuple:
        engine = _engine(data["database_url"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                row = (
                    (
                        await session.execute(
                            select(ModelRoute).where(
                                ModelRoute.requested_model == requested
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
            assert row is not None
            return (row.enabled, row.priority, row.provider)
        finally:
            await engine.dispose()

    enabled, priority, provider = asyncio_run(_read())
    assert enabled is True  # the legacy checkbox still activates
    assert priority == 90
    assert provider == data["compatible_slug"]


# ---------------------------------------------------------------------------
# (k) native auth/CSRF denials on the new plan/apply endpoints
# ---------------------------------------------------------------------------


def test_plan_apply_native_auth_csrf_denials(route_env) -> None:
    """Real login/session/CSRF plumbing (no auth mocks): the new plan and
    apply endpoints refuse a missing session cookie and a wrong CSRF
    token BEFORE any planning or execution, with zero state/audit change.

    The apply denials carry a REAL valid reviewed token (reviewed data,
    never authority): authentication and CSRF are checked before the
    token is ever verified.
    """
    data = route_env
    route_id = data["r4"]
    client = data["client"]

    # A real, valid reviewed token for r4 (its own READ-ONLY plan).
    token = _make_plan(data, route_id, priority_action="set", priority="66")
    assert token

    before = _snap(data)
    audits_before = asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    )
    provider_before = asyncio_run(
        _provider_snapshot(data["database_url"], data["compatible_id"])
    )

    # (1) No session cookie at all: a fresh client (no login, no cookies)
    # is refused at the login boundary for BOTH endpoints.
    with TestClient(create_app(_settings(data["database_url"]))) as fresh:
        response = fresh.post(
            f"/admin/routes/{route_id}/configuration/plan",
            data=_plan_fields(
                data, "csrf-unchecked", route_id,
                priority_action="set", priority="77",
            ),
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"
        response = fresh.post(
            f"/admin/routes/{route_id}/configuration/apply",
            data={
                "csrf_token": "csrf-unchecked",
                "route_config_review_intent": token,
                "confirm_apply": "true",
                "reason": APPLY_REASON,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    # (2) Valid session, WRONG csrf token: the fixed 400 refusal fires
    # for BOTH endpoints, before any plan rendering or execution.
    response = client.post(
        f"/admin/routes/{route_id}/configuration/plan",
        data=_plan_fields(
            data, "stale-csrf-token", route_id,
            priority_action="set", priority="77",
        ),
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    response = client.post(
        f"/admin/routes/{route_id}/configuration/apply",
        data={
            "csrf_token": "stale-csrf-token",
            "route_config_review_intent": token,
            "confirm_apply": "true",
            "reason": APPLY_REASON,
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text

    # Zero writes: every route field, the audit state, and the provider
    # context are exactly as before the denials.
    assert _snap(data) == before
    assert asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    ) == audits_before
    assert asyncio_run(
        _provider_snapshot(data["database_url"], data["compatible_id"])
    ) == provider_before


# ---------------------------------------------------------------------------
# (l) native notes CLEAR-only: real old -> null, one audit, stale repeat,
#     fresh no-op
# ---------------------------------------------------------------------------


def test_route_notes_clear_only_native_law(route_env) -> None:
    data = route_env
    route_id = data["r4"]

    before = _snap(data)
    assert before[route_id][10] == OLD_NOTES  # notes present

    # Reviewed clear-only plan (no other field is touched).
    token = _make_plan(data, route_id, notes_intent="clear")
    response = _apply(data, route_id, token, reason=CLEAR_REASON)
    assert response.status_code == 200, response.text[:600]
    assert "The reviewed plan was applied" in response.text

    after = _snap(data)
    row = after[route_id]
    assert row[10] is None  # stored null
    # every other field is preserved exactly
    assert row[:10] == before[route_id][:10]
    assert row[11] == before[route_id][11]  # created_at

    audits = asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    )
    assert len(audits) == 1
    assert audits[0]["action"] == "model_route_updated"
    assert audits[0]["note"] == CLEAR_REASON
    assert audits[0]["old"]["notes"] == OLD_NOTES  # REAL prior
    assert audits[0]["new"]["notes"] is None  # real new null

    # The SAME reviewed plan repeated is refused stale (zero writes).
    response = _apply(data, route_id, token, reason=CLEAR_REASON)
    assert response.status_code == 400
    assert _snap(data) == after
    assert asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    ) == audits

    # A FRESH plan over the now-cleared state is a zero-diff no-op with
    # no audit and no write (even updated_at unchanged).
    token2 = _make_plan(data, route_id)
    response = _apply(data, route_id, token2, reason=CLEAR_REASON)
    assert response.status_code == 200, response.text[:600]
    assert "zero-diff no-op" in response.text
    assert _snap(data) == after
    assert asyncio_run(
        _route_audits(data["database_url"], route_id, data["admin_id"])
    ) == audits
