"""Permanent admin GUI usability regressions for objective 192-a.

Real Chromium (default matched build) against a real uvicorn app on the
already-qualified owned PostgreSQL fixture, with the real stylesheet and
real HTTP lookup traffic. These are permanent regressions for the defects
actually discovered during 192-a review:

- hidden record-choice menus must not overlay other controls (the scoped
  ``.rc [hidden]`` rule): real, unforced table-header button clicks must
  succeed and stay sortable;
- keyboard (ArrowDown/Enter) selection closes the menu and writes the
  submitted id; mouse replacement behaves the same;
- the initial option batch is the server's latest eligible ~100; the menu
  search reaches OLDER records; re-opening shows the latest batch;
- natural-order text sort puts "2" before "10"; typed numeric
  ``data-sort-value`` columns sort numerically (2 keys before 10 keys);
- multi-value controls manage chips with ONE newline-serialized hidden
  field; Backspace on the focused empty textarea removes the last chip;
- dependent pickers (provider -> model; audit target_type -> target_id)
  refetch scoped options on the actual value change;
- validation redisplay retains the record selection;
- an XSS canary institution label stays inert: escaped inside the
  ``data-initial-options`` attribute, JSON round-trips, and never becomes
  a DOM element;
- no-JS fallback: single fields are plain text inputs submitting the raw
  value; multi fields are real newline-preserving textareas.

Safety: only opaque IDs and non-sensitive form values are read; session
and CSRF values are used transiently to submit forms and are never logged
or screenshotted.

Run:  python -m pytest tests/browser/test_admin_usability.py -m playwright
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse
from typing import Any

import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import (
    AuditLog,
    GatewayKey,
    ModelRoute,
    Owner,
    ProviderConfig,
    UsageLedger,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.main import create_app
from slaif_gateway.services.key_policy_validation import IMPLEMENTED_CLIENT_ENDPOINTS
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key

# Reuse the already-qualified owned, labeled, loopback-bound, tmpfs-backed
# PostgreSQL fixture (never an ambient TEST_DATABASE_URL fallback).
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
)

# Re-export the qualified fixture under the expected fixture name.
owned_pg_url = _owned_pg_url_fixture

pytestmark = pytest.mark.playwright

ADMIN_PASSWORD = "correct horse battery staple"
LOGIN_FORM = 'form[action="/admin/login"]'
OWNERS_CREATE_FORM = 'form[action="/admin/owners/new"]'
CANARY_INSTITUTION = "<img src=x onerror=alert(1)> Usab Inst"



@contextmanager
def _run_uvicorn_server(app, port: int) -> Iterator[None]:
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        lifespan="on",
        timeout_keep_alive=1,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive():
                raise RuntimeError("Uvicorn server thread exited before startup")
            if time.monotonic() > deadline:
                raise TimeoutError("Timed out waiting for Uvicorn server startup")
            time.sleep(0.05)
        yield
    finally:
        server.should_exit = True
        thread.join(timeout=15)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_in_thread(coro):
    """Run a DB coroutine on an owned worker loop (Playwright's sync API
    occupies the main thread, so asyncio.run there would fail)."""
    result: dict[str, object] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - re-raised verbatim
            result["error"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=60)
    assert not thread.is_alive(), "DB helper thread did not finish"
    if "error" in result:
        raise result["error"]
    return result["value"]


@contextmanager
def _chromium_browser() -> Iterator[object]:
    playwright_sync = pytest.importorskip("playwright.sync_api")
    manager = playwright_sync.sync_playwright()
    playwright = manager.start()
    try:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - a missing toolchain is a skip
            pytest.skip(f"Playwright Chromium is unavailable: {exc}")
        try:
            yield browser
        finally:
            browser.close()
    finally:
        playwright.stop()


def _settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        GATEWAY_KEY_PREFIX="sk-slaif-",
        GATEWAY_KEY_ACCEPTED_PREFIXES="sk-slaif-",
        ACTIVE_HMAC_KEY_VERSION="1",
        TOKEN_HMAC_SECRET_V1=generate_secret_key(),
        ADMIN_SESSION_SECRET=generate_secret_key(),
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        ENABLE_EMAIL_DELIVERY=False,
    )


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


async def _seed_usability_data(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"usab-admin-{suffix}@example.org",
                    display_name="Usab Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                institution_a = (
                    await InstitutionsRepository(session).create_institution(
                        name=f"Usab Inst A {suffix}", country="SI"
                    )
                )
                institution_x = (
                    await InstitutionsRepository(session).create_institution(
                        name=f"{CANARY_INSTITUTION} {suffix}", country="SI"
                    )
                )
                cohort = await CohortsRepository(session).create_cohort(
                    name=f"usab-cohort-{suffix}",
                    description="usab browser cohort",
                    starts_at=now - timedelta(days=1),
                    ends_at=now + timedelta(days=30),
                )

                # 105 owners with staggered created_at: owner 105 is the
                # newest, owner 99 is anonymized (excluded from choices),
                # owner 5 falls OUTSIDE the latest-100 eligible batch.
                # Owners 7 and 17 are "Num 2" / "Num 10" for the
                # natural-order text sort assertion.
                owners: list[Owner] = []
                for i in range(1, 106):
                    if i == 7:
                        name, surname = "Num", "2"
                    elif i == 17:
                        name, surname = "Num", "10"
                    else:
                        name, surname = f"Usab {i:03d}", "Owner"
                    created = now - timedelta(minutes=105 - i)
                    owner = Owner(
                        id=uuid.uuid4(),
                        name=name,
                        surname=surname,
                        email=f"u{i:03d}-{suffix}@example.org",
                        institution_id=institution_a.id,
                        is_active=True,
                        anonymized_at=(now - timedelta(hours=1)) if i == 99 else None,
                        created_at=created,
                        updated_at=created,
                    )
                    session.add(owner)
                    owners.append(owner)

                # 10 keys for owner 20, 2 keys for owner 21: the numeric
                # column must sort 2 before 10 (a lexicographic string sort
                # would put "10" first).
                keys: list[GatewayKey] = []
                # Divergent request limits: 2000 vs 900. Numeric sorting
                # must put 900 first; a lexicographic string sort would put
                # "2000" before "900".
                limit_plan = ((owners[19], 10, 2000), (owners[20], 2, 900))
                for k_i, (owner, count, limit) in enumerate(limit_plan):
                    for j in range(count):
                        key = await GatewayKeysRepository(session).create_gateway_key_record(
                            public_key_id=f"usab-{suffix[:6]}-{k_i}-{j}",
                            token_hash=f"token_hash_usab_{suffix}_{k_i}_{j}",
                            owner_id=owner.id,
                            cohort_id=cohort.id,
                            valid_from=now - timedelta(days=1),
                            valid_until=now + timedelta(days=30),
                            key_hint=f"sk-slaif-usab{suffix[:4]}{k_i}{j}",
                            cost_limit_eur=Decimal("10.000000000"),
                            token_limit_total=1000,
                            request_limit_total=limit,
                            allow_all_models=True,
                            allow_all_endpoints=True,
                            created_by_admin_user_id=admin.id,
                        )
                        keys.append(key)

                prov_a = f"usab-provider-a-{suffix}"
                prov_b = f"usab-provider-b-{suffix}"
                for slug, created in (
                    (prov_a, now - timedelta(days=2)),
                    (prov_b, now - timedelta(days=1)),
                ):
                    session.add(
                        ProviderConfig(
                            id=uuid.uuid4(),
                            provider=slug,
                            display_name=slug,
                            kind="openai_compatible",
                            base_url=f"https://{slug}.example.org/v1",
                            api_key_env_var=f"USAB_{slug.upper()}_API_KEY",
                            enabled=True,
                            created_at=created,
                        )
                    )
                model_a1 = f"usab-model-a1-{suffix}"
                model_a2 = f"usab-model-a2-{suffix}"
                model_b1 = f"usab-model-b1-{suffix}"
                session.add(
                    ModelRoute(
                        id=uuid.uuid4(),
                        requested_model=model_a1,
                        match_type="exact",
                        endpoint="/v1/chat/completions",
                        provider=prov_a,
                        upstream_model=model_a2,
                        enabled=True,
                        visible_in_models=True,
                        supports_streaming=True,
                        created_at=now - timedelta(hours=5),
                    )
                )
                session.add(
                    ModelRoute(
                        id=uuid.uuid4(),
                        requested_model=model_b1,
                        match_type="exact",
                        endpoint="/v1/chat/completions",
                        provider=prov_b,
                        upstream_model=model_b1,
                        enabled=True,
                        visible_in_models=True,
                        supports_streaming=True,
                        created_at=now - timedelta(hours=4),
                    )
                )
                # 105 OLDER policy routes for provider A: they push the
                # key-policy model catalog past its latest-100 cap so the
                # policy search regression can prove an older token is
                # outside the rendered batch but server-searchable. They
                # are older than the two seeded routes above, which keeps
                # those routes inside every record-choice latest-100 batch.
                for i in range(105):
                    session.add(
                        ModelRoute(
                            id=uuid.uuid4(),
                            requested_model=f"usab-policy-{i:03d}-{suffix}",
                            match_type="exact",
                            endpoint="/v1/chat/completions",
                            provider=prov_a,
                            upstream_model=f"usab-policy-up-{i:03d}-{suffix}",
                            enabled=True,
                            visible_in_models=True,
                            supports_streaming=True,
                            created_at=now - timedelta(hours=6, minutes=i),
                        )
                    )
                # 105 OLDER enabled providers: they push the policy
                # provider catalog past its latest-100 page so the policy
                # search regression can prove an older provider is outside
                # the rendered batch but server-searchable and still
                # submittable (the page is presentation, not authority).
                # Plus one recently created DISABLED provider that must
                # never appear as a known choice.
                for i in range(105):
                    session.add(
                        ProviderConfig(
                            id=uuid.uuid4(),
                            provider=f"usab-oldprov-{i:03d}-{suffix}",
                            display_name=f"Usab Old Provider {i:03d}",
                            kind="openai_compatible",
                            base_url=f"https://usab-oldprov-{i:03d}-{suffix}.example.org/v1",
                            api_key_env_var=f"USAB_OLDPROV_{i:03d}_{suffix.upper()}_API_KEY",
                            enabled=True,
                            created_at=now - timedelta(days=3, hours=i),
                        )
                    )
                disabled_prov = f"usab-disabledprov-{suffix}"
                session.add(
                    ProviderConfig(
                        id=uuid.uuid4(),
                        provider=disabled_prov,
                        display_name="Usab Disabled Provider",
                        kind="openai_compatible",
                        base_url=f"https://{disabled_prov}.example.org/v1",
                        api_key_env_var=f"USAB_DISABLED_{suffix.upper()}_API_KEY",
                        enabled=False,
                        created_at=now - timedelta(hours=4),
                    )
                )

                # Usage rows with values where numeric and lexicographic
                # orders DIVERGE (cost 9.50 vs 12.50 vs 0.99; tokens
                # 990 vs 1000 vs 25), plus display-fidelity cases:
                # a VALID actual cost of zero, an estimate-only row, and
                # a row with neither (must display n/a and sort last).
                usage_plan = (
                    (990, Decimal("9.50"), None),
                    (1000, Decimal("12.50"), None),
                    (25, Decimal("0.99"), None),
                    (75, Decimal("0"), Decimal("5.25")),
                    (80, None, Decimal("7.75")),
                    (90, None, None),
                )
                for n, (tokens, actual, estimated) in enumerate(usage_plan):
                    session.add(
                        UsageLedger(
                            id=uuid.uuid4(),
                            request_id=f"usab-usage-{n}-{suffix}",
                            gateway_key_id=keys[0].id,
                            endpoint="/v1/chat/completions",
                            provider=prov_a,
                            requested_model=model_a1,
                            success=True,
                            accounting_status="finalized",
                            http_status=200,
                            total_tokens=tokens,
                            actual_cost_eur=actual,
                            estimated_cost_eur=estimated,
                            started_at=now - timedelta(hours=2, minutes=n),
                            finished_at=now - timedelta(hours=2, minutes=n)
                            + timedelta(milliseconds=25),
                            created_at=now - timedelta(hours=2, minutes=n),
                        )
                    )

                # Audit history: 3 owner-entity events; 25 HOT events on
                # one gateway key plus 1 event on another — grouped
                # distinct targets BEFORE the limit must keep both keys in
                # the initial batch.
                for k, owner in enumerate((owners[0], owners[10], owners[20])):
                    session.add(
                        AuditLog(
                            id=uuid.uuid4(),
                            admin_user_id=admin.id,
                            action="admin_owner_create",
                            entity_type="owner",
                            entity_id=owner.id,
                            request_id=f"usab-audit-{suffix}-{k}",
                            note="usab browser audit seed",
                            created_at=now - timedelta(minutes=60 - k),
                        )
                    )
                hot_key = keys[0]
                for k in range(25):
                    session.add(
                        AuditLog(
                            id=uuid.uuid4(),
                            admin_user_id=admin.id,
                            action="admin_key_rotate",
                            entity_type="gateway_key",
                            entity_id=hot_key.id,
                            note="usab hot entity",
                            created_at=now - timedelta(seconds=k),
                        )
                    )
                session.add(
                    AuditLog(
                        id=uuid.uuid4(),
                        admin_user_id=admin.id,
                        action="admin_key_revoke",
                        entity_type="gateway_key",
                        entity_id=keys[1].id,
                        note="usab cold entity",
                        created_at=now - timedelta(seconds=25),
                    )
                )

                return {
                    "admin_email": admin.email,
                    "institution_a_id": str(institution_a.id),
                    "institution_a_name": institution_a.name,
                    "institution_x_id": str(institution_x.id),
                    "cohort_id": str(cohort.id),
                    "suffix": suffix,
                    "owner_ids": {f"u{i:03d}": str(owner.id) for i, owner in enumerate(owners, start=1)},
                    "hot_key_id": str(hot_key.id),
                    "cold_key_id": str(keys[1].id),
                    "provider_a": prov_a,
                    "provider_b": prov_b,
                    "model_a1": model_a1,
                    "model_a2": model_a2,
                    "model_b1": model_b1,
                    "oldprov_search": f"usab-oldprov-104-{suffix}",
                    "oldprov_second": f"usab-oldprov-103-{suffix}",
                    "disabled_prov": disabled_prov,
                }
    finally:
        await engine.dispose()


async def _owner_exists(database_url: str, email: str, institution_id: str) -> bool:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await session.execute(
                select(Owner.id, Owner.institution_id).where(Owner.email == email)
            )
            row = result.first()
            return row is not None and str(row[1]) == institution_id
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Module environment
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def usab_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    data = asyncio.run(_seed_usability_data(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    data["base_url"] = f"http://127.0.0.1:{port}"
    data["database_url"] = owned_pg_url
    with _run_uvicorn_server(app, port):
        yield data


@pytest.fixture(scope="module")
def chromium(usab_env) -> Iterator[object]:
    """Depends on ``usab_env`` on purpose: the Playwright sync session runs
    an asyncio loop on the main thread, so PostgreSQL readiness, seeding,
    and the uvicorn app must complete BEFORE it starts (and the browser
    closes before DB teardown)."""
    with _chromium_browser() as browser:
        yield browser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(page: object, env: dict[str, Any]) -> None:
    page.goto("/admin/login")  # type: ignore[attr-defined]
    page.fill(  # type: ignore[attr-defined]
        f'{LOGIN_FORM} input[name="email"]', str(env["admin_email"])
    )
    page.fill(f'{LOGIN_FORM} input[name="password"]', ADMIN_PASSWORD)  # type: ignore[attr-defined]
    page.click(f'{LOGIN_FORM} button[type="submit"]')  # type: ignore[attr-defined]
    page.wait_for_url("**/admin")  # type: ignore[attr-defined]


def _rc(page: object, selector: str) -> object:
    return page.locator(selector)  # type: ignore[attr-defined]


def _menu_visible(page: object, selector: str) -> bool:
    return bool(page.locator(f"{selector} .rc-menu").is_visible())  # type: ignore[attr-defined]


def _hidden_values(page: object, selector: str) -> list[str]:
    loc = page.locator(f"{selector} .rc-value")  # type: ignore[attr-defined]
    return [loc.nth(i).input_value() for i in range(loc.count())]


def _assert_menus_closed(page: object) -> None:
    menus = page.locator(".rc-menu")  # type: ignore[attr-defined]
    for i in range(menus.count()):
        assert not menus.nth(i).is_visible(), (
            f"record-choice menu #{i} is visible while it must stay hidden"
        )


# ---------------------------------------------------------------------------
# 1) Table sorting: real header clicks, not intercepted by hidden menus
# ---------------------------------------------------------------------------


def test_owner_table_sorting_not_intercepted(chromium, usab_env) -> None:
    """Real, unforced header-button clicks sort the owners table and the
    hidden record-choice menus never overlay/intercept them (the scoped
    ``.rc [hidden]`` regression)."""
    env = usab_env
    suffix = env["suffix"]
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        # The owners list defaults to 50 rows; the table sorts the
        # DISPLAYED result set, so load all 105 through the supported
        # limit parameter.
        page.goto("/admin/owners?limit=200")
        table = page.locator(".table-wrap table[data-sortable]")  # type: ignore[attr-defined]
        assert table.count() == 1
        rows = table.locator("tbody tr")
        count = rows.count()
        assert count == 105, f"expected all 105 seeded owners, got {count}"

        def th(i: int):
            return table.locator("thead th").nth(i)

        def header_click(i: int) -> None:
            # NO force=: an overlaying hidden menu would intercept this.
            th(i).locator("button").click(timeout=10000)

        def owner_names() -> list[str]:
            return [
                rows.nth(k).locator("td a").first.inner_text() for k in range(count)
            ]

        def row_emails() -> list[str]:
            return [
                rows.nth(k).locator("td").first.locator("div").first.inner_text()
                for k in range(count)
            ]

        def key_values() -> list[str]:
            return [
                rows.nth(k).locator("td").nth(3).get_attribute("data-sort-value")
                for k in range(count)
            ]

        _assert_menus_closed(page)

        # Natural-order text: "Num 2" before "Num 10" (lexicographic would
        # put "Num 10" first).
        header_click(0)
        assert th(0).get_attribute("aria-sort") == "ascending"
        assert th(1).get_attribute("aria-sort") == "none"
        names = owner_names()
        assert names.index("Num 2") < names.index("Num 10"), names[:12]
        header_click(0)
        assert th(0).get_attribute("aria-sort") == "descending"
        names = owner_names()
        assert names.index("Num 10") < names.index("Num 2")

        # Datetime column: ascending = oldest owner (u001) first.
        header_click(4)
        assert th(4).get_attribute("aria-sort") == "ascending"
        assert row_emails()[0] == f"u001-{suffix}@example.org"
        header_click(4)
        assert th(4).get_attribute("aria-sort") == "descending"
        assert row_emails()[0] == f"u105-{suffix}@example.org"

        # Typed numeric column: 2 keys before 10 keys (a string sort would
        # put "10" first).
        header_click(3)
        assert th(3).get_attribute("aria-sort") == "ascending"
        values = key_values()
        assert values.index("2") < values.index("10"), values[:20]
        header_click(3)
        assert th(3).get_attribute("aria-sort") == "descending"
        values = key_values()
        assert values.index("10") < values.index("2")

        # Keyboard activation of the header button (Enter / Space).
        # The date column is currently UNSORTED (the previous clicks moved
        # the sort to the numeric column), so the keyboard presses must
        # walk the exact cycle: none -> ascending -> descending.
        assert th(4).get_attribute("aria-sort") == "none"
        button = th(4).locator("button")
        button.focus()
        page.keyboard.press("Enter")  # type: ignore[attr-defined]
        assert th(4).get_attribute("aria-sort") == "ascending", (
            "Enter on the focused header button must sort ascending"
        )
        page.keyboard.press("Space")  # type: ignore[attr-defined]
        assert th(4).get_attribute("aria-sort") == "descending", (
            "Space must toggle the sort direction to descending"
        )

        # The hidden menus stayed hidden through every interaction, and a
        # further unforced click still works.
        _assert_menus_closed(page)
        header_click(0)


# ---------------------------------------------------------------------------
# 2) Record choice: latest-100 batch, older search, keyboard + mouse
# ---------------------------------------------------------------------------


def test_record_choice_batch_older_search_and_selection(chromium, usab_env) -> None:
    env = usab_env
    suffix = env["suffix"]
    email_rc = '.rc[data-rc-id="owners-email"]'
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/owners")

        # Initial batch: the latest 100 ELIGIBLE owners (eligibility
        # filtered before the limit) = owners 5..105 minus the anonymized
        # owner 99 -> exactly 100 options; u004 is OLDER than the batch.
        page.locator(f"{email_rc} .rc-open").click()  # type: ignore[attr-defined]
        assert _menu_visible(page, email_rc)
        options = page.locator(f"{email_rc} .rc-option")
        labels = [
            options.nth(i).locator(".rc-option-label").inner_text()
            for i in range(options.count())
        ]
        assert len(labels) == 100, f"expected 100 latest eligible emails, got {len(labels)}"
        assert f"u105-{suffix}@example.org" in labels
        assert f"u005-{suffix}@example.org" in labels
        assert f"u004-{suffix}@example.org" not in labels

        # Keyboard: ArrowDown + Enter selects the first (newest) option and
        # closes the menu.
        page.keyboard.press("ArrowDown")  # type: ignore[attr-defined]
        page.keyboard.press("Enter")  # type: ignore[attr-defined]
        assert not _menu_visible(page, email_rc), (
            "menu must close after keyboard selection"
        )
        assert _hidden_values(page, email_rc) == [f"u105-{suffix}@example.org"]
        assert (
            page.locator(f"{email_rc} .rc-input").input_value()  # type: ignore[attr-defined]
            == f"u105-{suffix}@example.org"
        )

        # Re-opening shows the latest batch again (search starts empty).
        page.locator(f"{email_rc} .rc-open").click()  # type: ignore[attr-defined]
        assert _menu_visible(page, email_rc)
        options = page.locator(f"{email_rc} .rc-option")
        labels = [
            options.nth(i).locator(".rc-option-label").inner_text()
            for i in range(options.count())
        ]
        assert len(labels) == 100
        assert f"u105-{suffix}@example.org" in labels

        # Server search reaches the OLDER record outside the batch.
        page.fill(  # type: ignore[attr-defined]
            f"{email_rc} .rc-search", f"u004-{suffix}@example.org"
        )
        page.wait_for_selector(  # type: ignore[attr-defined]
            f'{email_rc} .rc-option:has-text("u004-{suffix}@example.org")',
            timeout=15000,
        )
        # Exactly the older match PLUS the current selection (u105),
        # which the search deliberately re-hydrates alongside the q
        # match; no unrelated records may appear.
        older_labels = [
            page.locator(f"{email_rc} .rc-option").nth(i).locator(".rc-option-label").inner_text()  # type: ignore[attr-defined]
            for i in range(page.locator(f"{email_rc} .rc-option").count())  # type: ignore[attr-defined]
        ]
        assert set(older_labels) == {
            f"u004-{suffix}@example.org",
            f"u105-{suffix}@example.org",
        }, f"expected the older match plus the hydrated selection, got {older_labels}"
        # Mouse selection: exactly one managed hidden field, no duplicates.
        page.locator(f'{email_rc} .rc-option:has-text("u004-{suffix}@example.org")').click()  # type: ignore[attr-defined]
        assert not _menu_visible(page, email_rc), "menu must close after mouse selection"
        assert _hidden_values(page, email_rc) == [f"u004-{suffix}@example.org"]

        # The submitted value filters the real list to that one owner.
        # The real filter submit button — never a union of all filter-bar
        # buttons: the record-choice clear/open buttons sit inside the
        # same form and would clear/reopen the menu instead of submitting.
        page.get_by_role("button", name="Filter", exact=True).click()  # type: ignore[attr-defined]
        page.wait_for_url("**/admin/owners?email=*")  # type: ignore[attr-defined]
        rows = page.locator(".table-wrap table[data-sortable] tbody tr")  # type: ignore[attr-defined]
        assert rows.count() == 1
        assert f"u004-{suffix}@example.org" in rows.first.locator("td").first.inner_text()


# ---------------------------------------------------------------------------
# 3) Owner create: XSS canary, keyboard flow, redisplay, real create
# ---------------------------------------------------------------------------


def test_owner_create_dropdown_xss_redisplay_and_create(chromium, usab_env) -> None:
    env = usab_env
    suffix = env["suffix"]
    inst_rc = '.rc[data-input-name="institution_id"]'
    canary_name = f"{CANARY_INSTITUTION} {suffix}"
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/owners/new")

        # 1) The canary is escaped inside the attribute and round-trips as
        #    inert JSON — the literal tag must never reach the page source.
        html = page.content()
        assert "<img src=x" not in html, "unescaped canary tag in page source"
        assert "\\u003cimg" in html, "canary must be \\u003c-escaped in the attribute"
        parsed = page.evaluate(  # type: ignore[attr-defined]
            """() => JSON.parse(
                document.querySelector(
                    '.rc[data-input-name="institution_id"]'
                ).dataset.initialOptions
            )"""
        )
        canary = next((o for o in parsed if o.get("id") == env["institution_x_id"]), None)
        assert canary is not None, "canary institution missing from initial options"
        assert canary["label"] == canary_name

        # 2) Menu renders the canary as TEXT only.
        page.locator(f"{inst_rc} .rc-open").click()  # type: ignore[attr-defined]
        assert _menu_visible(page, inst_rc)
        menu = page.locator(f"{inst_rc} .rc-menu")
        assert menu.locator("img").count() == 0
        assert (
            menu.locator(f'.rc-option:has-text("{canary_name}")').count() == 1
        )

        # 3) Mouse replacement: select the canary, assert the chip text is
        #    inert, then replace with the real institution.
        menu.locator(f'.rc-option:has-text("{canary_name}")').click()  # type: ignore[attr-defined]
        assert not _menu_visible(page, inst_rc)
        selected = page.locator(f"{inst_rc} .rc-selected")
        assert selected.locator("img").count() == 0
        assert canary_name in selected.inner_text()
        page.locator(f"{inst_rc} .rc-open").click()  # type: ignore[attr-defined]
        page.locator(  # type: ignore[attr-defined]
            f'{inst_rc} .rc-option:has-text("Usab Inst A {suffix}")'
        ).click()
        assert _hidden_values(page, inst_rc) == [env["institution_a_id"]]

        # 4) Validation redisplay retains the selection and typed values.
        page.fill(f'{OWNERS_CREATE_FORM} input[name="name"]', "Redisp")  # type: ignore[attr-defined]
        page.fill(f'{OWNERS_CREATE_FORM} input[name="surname"]', "Owner")  # type: ignore[attr-defined]
        page.fill(f'{OWNERS_CREATE_FORM} input[name="email"]', "not-an-email")  # type: ignore[attr-defined]
        page.fill(f'{OWNERS_CREATE_FORM} textarea[name="reason"]', "usab redisplay test")  # type: ignore[attr-defined]
        page.click(f'{OWNERS_CREATE_FORM} button[type="submit"]')  # type: ignore[attr-defined]
        assert page.locator(".admin-flash-error").count() == 1
        assert (
            page.locator(f'{OWNERS_CREATE_FORM} input[name="email"]').input_value()  # type: ignore[attr-defined]
            == "not-an-email"
        )
        assert _hidden_values(page, inst_rc) == [env["institution_a_id"]]
        assert (
            page.locator(f"{inst_rc} .rc-input").input_value()  # type: ignore[attr-defined]
            == env["institution_a_name"]
        )

        # 5) Fix the email and create for real.
        new_email = f"new-usab-{suffix}@example.org"
        page.fill(f'{OWNERS_CREATE_FORM} input[name="email"]', new_email)  # type: ignore[attr-defined]
        page.click(f'{OWNERS_CREATE_FORM} button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_timeout(500)
        assert "not-an-email" not in page.content()
        assert _run_in_thread(
            _owner_exists(env["database_url"], new_email, env["institution_a_id"])
        ), "created owner must carry the dropdown-selected institution"


# ---------------------------------------------------------------------------
# 4) Multi chips + dependent pickers (provider -> model, target_type -> id)
# ---------------------------------------------------------------------------


def test_multi_chips_and_dependent_pickers(chromium, usab_env) -> None:
    env = usab_env
    lookups: list[str] = []

    # --- provider -> model on the route create form ---
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        page.on(  # type: ignore[attr-defined]
            "request",
            lambda req: lookups.append(req.url)
            if "/admin/record-choices" in req.url
            else None,
        )
        _login(page, env)
        page.goto("/admin/routes/new")

        provider_rc = '.rc[data-rc-id="route-provider"]'
        model_rc = '.rc[data-input-name="requested_model"]'

        # Unscoped initial batch: models of BOTH providers.
        page.locator(f"{model_rc} .rc-open").click()  # type: ignore[attr-defined]
        initial = [
            page.locator(f"{model_rc} .rc-option").nth(i).locator(".rc-option-label").inner_text()  # type: ignore[attr-defined]
            for i in range(page.locator(f"{model_rc} .rc-option").count())  # type: ignore[attr-defined]
        ]
        assert env["model_a1"] in initial and env["model_b1"] in initial
        page.keyboard.press("Escape")  # type: ignore[attr-defined]
        assert not _menu_visible(page, model_rc)

        # Select provider A -> the dependent control refetches scoped
        # options and clears its own (empty) selection.
        page.locator(f"{provider_rc} .rc-open").click()  # type: ignore[attr-defined]
        # Wait for the ACTUAL scoped lookup response: the dependent
        # control clears its options while the fetch is pending, so
        # observing the request alone does not prove completion.
        with page.expect_response(  # type: ignore[attr-defined]
            lambda r: (
                "/admin/record-choices" in r.url
                and f"provider={env['provider_a']}" in r.url
            ),
            timeout=15000,
        ):
            page.locator(f'{provider_rc} .rc-option:has-text("{env["provider_a"]}")').click()  # type: ignore[attr-defined]
        assert _hidden_values(page, provider_rc) == [env["provider_a"]]
        assert any(
            f"provider={env['provider_a']}" in url for url in lookups
        ), f"dependent refetch must send the provider parameter: {lookups}"

        page.locator(f"{model_rc} .rc-open").click()  # type: ignore[attr-defined]
        page.wait_for_selector(  # type: ignore[attr-defined]
            f'{model_rc} .rc-option:has-text("{env["model_a2"]}")', timeout=15000
        )
        scoped = [
            page.locator(f"{model_rc} .rc-option").nth(i).locator(".rc-option-label").inner_text()  # type: ignore[attr-defined]
            for i in range(page.locator(f"{model_rc} .rc-option").count())  # type: ignore[attr-defined]
        ]
        assert env["model_a1"] in scoped and env["model_a2"] in scoped
        assert env["model_b1"] not in scoped, (
            "provider-scoped model choices must exclude the other provider"
        )

        # Clearing the dependent control while a provider is SELECTED
        # must re-scope to the CURRENT parent: neither the initial
        # unscoped batch (which lists other providers' models) nor the
        # stale typed candidate may reappear after clear + reopen.
        page.locator(f"{model_rc} .rc-input").click()  # type: ignore[attr-defined]
        with page.expect_response(  # type: ignore[attr-defined]
            lambda r: "/admin/record-choices" in r.url and "q=zz-clear-candidate" in r.url,
            timeout=15000,
        ) as typed_lookup:
            page.keyboard.type("zz-clear-candidate")  # type: ignore[attr-defined]
        assert typed_lookup.value is not None
        assert _hidden_values(page, model_rc) == ["zz-clear-candidate"]
        with page.expect_response(  # type: ignore[attr-defined]
            lambda r: (
                "/admin/record-choices" in r.url
                and f"provider={env['provider_a']}" in r.url
                and "q=" not in r.url
                and "selected=" not in r.url
            ),
            timeout=15000,
        ) as clear_refetch:
            page.locator(f"{model_rc} .rc-clear").click()  # type: ignore[attr-defined]
        assert clear_refetch.value is not None, (
            "clearing a dependent control must issue a fresh scoped lookup"
        )
        assert _hidden_values(page, model_rc) == [""]
        # The clear handler preserves the menu state: only open it if the
        # clear happened while it was closed (clicking the open button
        # while open would toggle it closed). The primary input only ever
        # opens.
        if not _menu_visible(page, model_rc):
            page.locator(f"{model_rc} .rc-input").click()  # type: ignore[attr-defined]
        page.wait_for_selector(  # type: ignore[attr-defined]
            f'{model_rc} .rc-option:has-text("{env["model_a1"]}")', timeout=15000
        )
        cleared = [
            page.locator(f"{model_rc} .rc-option").nth(i).locator(".rc-option-label").inner_text()  # type: ignore[attr-defined]
            for i in range(page.locator(f"{model_rc} .rc-option").count())  # type: ignore[attr-defined]
        ]
        assert env["model_a1"] in cleared and env["model_a2"] in cleared
        assert env["model_b1"] not in cleared, (
            "clear must re-scope to the current provider, not the initial batch"
        )
        assert "zz-clear-candidate" not in cleared, (
            "stale typed candidate must not survive clear"
        )

    # --- multi chips on the openai-assisted route proposal form ---
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/openai-assisted/routes")
        multi_rc = '.rc[data-input-name="include_models"]'

        page.locator(f"{multi_rc} .rc-input").click()  # type: ignore[attr-defined]
        assert _menu_visible(page, multi_rc)
        page.locator(f'{multi_rc} .rc-option:has-text("{env["model_a1"]}")').click()  # type: ignore[attr-defined]
        page.locator(f'{multi_rc} .rc-option:has-text("{env["model_b1"]}")').click()  # type: ignore[attr-defined]
        chips = page.locator(f"{multi_rc} .rc-chip")
        assert chips.count() == 2
        # ONE newline-serialized hidden field (server parsing is preserved).
        assert _hidden_values(page, multi_rc) == [
            f"{env['model_a1']}\n{env['model_b1']}"
        ]

        # Backspace on the focused EMPTY textarea removes the last chip
        # (checks the real focused text, not a stale empty main input).
        page.locator(f"{multi_rc} .rc-input").click()  # type: ignore[attr-defined]
        page.locator(f"{multi_rc} .rc-input").focus()  # type: ignore[attr-defined]
        page.keyboard.press("Backspace")  # type: ignore[attr-defined]
        assert page.locator(f"{multi_rc} .rc-chip").count() == 1
        assert _hidden_values(page, multi_rc) == [env["model_a1"]]

    # --- audit target_type -> target_id (grouped before the limit) ---
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        audit_lookups: list[str] = []
        page = context.new_page()
        page.on(  # type: ignore[attr-defined]
            "request",
            lambda req: audit_lookups.append(req.url)
            if "/admin/record-choices" in req.url
            else None,
        )
        _login(page, env)
        page.goto("/admin/audit")

        type_rc = '.rc[data-rc-id="audit-target-type"]'
        target_rc = '.rc[data-rc-id="audit-target-id"]'
        page.locator(f"{type_rc} .rc-open").click()  # type: ignore[attr-defined]
        # Same completion law: wait for the scoped target lookup
        # response before reading the dependent options.
        with page.expect_response(  # type: ignore[attr-defined]
            lambda r: "/admin/record-choices" in r.url and "target_type=gateway_key" in r.url,
            timeout=15000,
        ):
            page.locator(f'{type_rc} .rc-option:has-text("gateway_key")').click()  # type: ignore[attr-defined]
        assert _hidden_values(page, type_rc) == ["gateway_key"]
        assert any("target_type=gateway_key" in url for url in audit_lookups), (
            f"audit target lookup must send target_type: {audit_lookups}"
        )

        page.locator(f"{target_rc} .rc-open").click()  # type: ignore[attr-defined]
        page.wait_for_selector(  # type: ignore[attr-defined]
            f'{target_rc} .rc-option:has-text("{env["cold_key_id"]}")', timeout=15000
        )
        labels = [
            page.locator(f"{target_rc} .rc-option").nth(i).locator(".rc-option-label").inner_text()  # type: ignore[attr-defined]
            for i in range(page.locator(f"{target_rc} .rc-option").count())  # type: ignore[attr-defined]
        ]
        # The hot entity (25 recent events) must NOT crowd out the cold
        # one from the initial batch.
        assert any(env["hot_key_id"] in label for label in labels)
        assert any(env["cold_key_id"] in label for label in labels)


# ---------------------------------------------------------------------------
# 5) No-JS fallback
# ---------------------------------------------------------------------------


def test_nojs_fallback_plain_fields(chromium, usab_env) -> None:
    env = usab_env
    suffix = env["suffix"]
    with chromium.new_context(  # type: ignore[attr-defined]
        base_url=env["base_url"], java_script_enabled=False
    ) as context:
        page = context.new_page()
        _login(page, env)

        # Single field: a plain visible text input submits the raw value.
        page.goto("/admin/owners/new")
        inst_input = page.locator(f'{OWNERS_CREATE_FORM} input[name="institution_id"]')
        assert inst_input.count() == 1
        assert inst_input.is_visible()
        assert page.locator(".rc-value").count() == 0

        # Multi field: a REAL textarea preserves newlines.
        page.goto("/admin/openai-assisted/routes")
        textarea = page.locator('textarea[name="include_models"]')
        assert textarea.count() == 1
        textarea.fill("gpt-usab-*\nold-model-line")  # type: ignore[attr-defined]
        assert textarea.input_value() == "gpt-usab-*\nold-model-line"

        # No-JS owner create with a raw institution UUID still works.
        page.goto("/admin/owners/new")
        page.fill(f'{OWNERS_CREATE_FORM} input[name="name"]', "Nojs")  # type: ignore[attr-defined]
        page.fill(f'{OWNERS_CREATE_FORM} input[name="surname"]', "Owner")  # type: ignore[attr-defined]
        nojs_email = f"nojs-usab-{suffix}@example.org"
        page.fill(f'{OWNERS_CREATE_FORM} input[name="email"]', nojs_email)  # type: ignore[attr-defined]
        page.fill(  # type: ignore[attr-defined]
            f'{OWNERS_CREATE_FORM} input[name="institution_id"]',
            env["institution_a_id"],
        )
        page.fill(f'{OWNERS_CREATE_FORM} textarea[name="reason"]', "usab nojs create")  # type: ignore[attr-defined]
        page.click(f'{OWNERS_CREATE_FORM} button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_timeout(500)
        assert _run_in_thread(
            _owner_exists(env["database_url"], nojs_email, env["institution_a_id"])
        ), "no-JS raw-UUID owner create must succeed"


# ---------------------------------------------------------------------------
# 6) Import preview/result + related-record table families (runtime proof)
# ---------------------------------------------------------------------------

PREVIEW_FORM = 'form[action="/admin/keys/bulk-import/preview"]'
EXECUTE_FORM = 'form[action="/admin/keys/bulk-import/execute"]'


async def _key_count(database_url: str) -> int:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await session.execute(select(GatewayKey.id))
            return len(result.scalars().all())
    finally:
        await engine.dispose()


async def _latest_key(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await session.execute(
                select(
                    GatewayKey.id,
                    GatewayKey.owner_id,
                    GatewayKey.allow_all_models,
                    GatewayKey.allow_all_endpoints,
                    GatewayKey.metadata_json,
                )
                .order_by(GatewayKey.created_at.desc(), GatewayKey.id.desc())
                .limit(1)
            )
            row = result.first()
            return {
                "id": str(row[0]),
                "owner_id": str(row[1]),
                "allow_all_models": bool(row[2]),
                "allow_all_endpoints": bool(row[3]),
                "metadata_json": dict(row[4] or {}),
            }
    finally:
        await engine.dispose()

def _import_csv(env: dict[str, Any]) -> str:
    suffix = env["suffix"]
    return (
        "owner_email,valid_days,cost_limit_eur,email_delivery_mode,allowed_endpoints,allowed_models\n"
        f"u020-{suffix}@example.org,30,10.00,none,/v1/chat/completions,{env['model_a1']}\n"
        f"u021-{suffix}@example.org,30,2.00,none,/v1/chat/completions,{env['model_a1']}\n"
        f"u001-{suffix}@example.org,45,5.50,none,/v1/chat/completions,{env['model_a1']}\n"
    )


def test_import_preview_execute_and_related_tables(chromium, usab_env) -> None:
    """Real-browser sorting of the import preview/result table families and
    the related-record list tables (usage, keys). Row associations
    (request id / public key id travel with their row) are asserted
    after sorting. The one-time plaintext key column is never read."""
    env = usab_env
    suffix = env["suffix"]
    before_count = _run_in_thread(_key_count(env["database_url"]))
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)

        # --- usage list: numeric cost/tokens where string order differs,
        # plus faithful display of a valid actual zero, an estimate, and
        # neither (n/a sorts last as missing).
        page.goto("/admin/usage")
        table = page.locator(".table-wrap table[data-sortable]")  # type: ignore[attr-defined]
        rows = table.locator("tbody tr")
        assert rows.count() == 6
        costs = [
            rows.nth(i).locator("td").nth(5).get_attribute("data-sort-value")
            for i in range(6)
        ]
        tokens = [
            rows.nth(i).locator("td").nth(4).get_attribute("data-sort-value")
            for i in range(6)
        ]
        assert sorted(float(c) for c in costs if c) == [0.0, 0.99, 7.75, 9.5, 12.5]
        assert sum(1 for c in costs if not c) == 1, "exactly one cost-missing row"
        assert sorted(tokens) == ["1000", "25", "75", "80", "90", "990"]
        cost_header = table.locator("thead th").filter(has_text="Cost (EUR)")
        cost_header.locator("button").click()
        assert cost_header.get_attribute("aria-sort") == "ascending"
        rows = table.locator("tbody tr")
        ascending_costs = [
            rows.nth(i).locator("td").nth(5).get_attribute("data-sort-value")
            for i in range(6)
        ]
        assert [float(c) for c in ascending_costs if c] == [
            0.0,
            0.99,
            7.75,
            9.5,
            12.5,
        ], f"numeric money sort wrong (lexicographic would lead with 12.50): {ascending_costs}"
        assert not ascending_costs[5], "missing cost must sort last"
        # Association: the 12.50 row is the usab-usage-1 request row.
        target = ascending_costs.index(ascending_costs[4])
        link_text = rows.nth(target).locator("td a").first.inner_text()
        assert link_text == f"usab-usage-1-{suffix}"
        # Display fidelity: the actual-zero row shows "0 EUR" (not the
        # estimate and not n/a); the estimate-only row shows the estimate;
        # the neither row shows n/a.
        for i in range(6):
            cell = rows.nth(i).locator("td").nth(5)
            value = ascending_costs[i]
            visible = cell.inner_text().strip()
            if value == "":
                assert visible == "n/a EUR", f"neither-cost row must show n/a: {visible!r}"
            elif float(value) == 0.0:
                assert visible.startswith("0 EUR"), (
                    f"valid actual zero must display 0, not estimate: {visible!r}"
                )
            elif float(value) == 7.75:
                assert visible.startswith("7.75 EUR"), (
                    f"estimate-only row must show the estimate: {visible!r}"
                )
        token_header = table.locator("thead th").filter(has_text="Tokens (total)")
        token_header.locator("button").click()
        rows = table.locator("tbody tr")
        ascending_tokens = [
            rows.nth(i).locator("td").nth(4).get_attribute("data-sort-value")
            for i in range(6)
        ]
        assert ascending_tokens == ["25", "75", "80", "90", "990", "1000"], (
            f"numeric token sort wrong (lexicographic would lead with 1000): "
            f"{ascending_tokens}"
        )

        # --- keys list: 900-limited keys before 2000-limited (numeric) ---
        page.goto("/admin/keys")
        table = page.locator(".table-wrap table[data-sortable]")  # type: ignore[attr-defined]
        rows = table.locator("tbody tr")
        assert rows.count() == before_count == 12
        limits_header = table.locator("thead th").filter(has_text="Limits (requests)")
        limits_header.locator("button").click()
        assert limits_header.get_attribute("aria-sort") == "ascending"
        rows = table.locator("tbody tr")
        limits = [
            rows.nth(i).locator("td").nth(5).get_attribute("data-sort-value")
            for i in range(12)
        ]
        assert limits[:2] == ["900", "900"], (
            f"numeric limits sort wrong (lexicographic would lead with 2000): {limits[:6]}"
        )
        assert all(limit == "2000" for limit in limits[2:])

        # --- bulk import PREVIEW (dry run: no key writes) ---
        page.goto("/admin/keys/bulk-import")
        page.fill(f'{PREVIEW_FORM} textarea[name="import_text"]', _import_csv(env))  # type: ignore[attr-defined]
        page.click(f'{PREVIEW_FORM} button[type="submit"]')  # type: ignore[attr-defined]
        page.wait_for_selector("#bulk-key-preview-heading", timeout=20000)  # type: ignore[attr-defined]
        table = page.locator(".table-wrap table[data-sortable]")  # type: ignore[attr-defined]
        rows = table.locator("tbody tr")
        assert rows.count() == 3
        assert page.locator(".summary-card strong").nth(0).inner_text() == "3"
        quotas_header = table.locator("thead th").filter(has_text="Quotas")
        quotas_header.locator("button").click()
        assert quotas_header.get_attribute("aria-sort") == "ascending"
        rows = table.locator("tbody tr")
        preview_costs = [
            rows.nth(i).locator("td").nth(5).get_attribute("data-sort-value")
            for i in range(3)
        ]
        assert [float(c) for c in preview_costs] == [2.0, 5.5, 10.0], (
            f"preview money sort wrong: {preview_costs}"
        )
        # Association: the 2.00 row is u021's row.
        for i in range(3):
            if float(preview_costs[i]) == 2.0:
                assert f"u021-{suffix}@example.org" in rows.nth(i).locator("td").nth(2).inner_text()
        # Dry run must not create keys.
        assert _run_in_thread(_key_count(env["database_url"])) == before_count

        # --- confirmed EXECUTION: the result table keeps row associations ---
        page.fill(f'{EXECUTE_FORM} textarea[name="import_text"]', _import_csv(env))  # type: ignore[attr-defined]
        page.check(f'{EXECUTE_FORM} input[name="confirm_import"]')  # type: ignore[attr-defined]
        page.check(f'{EXECUTE_FORM} input[name="confirm_plaintext_display"]')  # type: ignore[attr-defined]
        page.fill(f'{EXECUTE_FORM} input[name="reason"]', "usab browser bulk import")  # type: ignore[attr-defined]
        with page.expect_response(
            lambda response: response.request.method == "POST"
            and response.url.endswith("/admin/keys/bulk-import/execute")
        ) as info:
            page.click(f'{EXECUTE_FORM} button[type="submit"]')  # type: ignore[attr-defined]
        execute_response = info.value
        page.wait_for_selector(".table-wrap table[data-sortable] tbody tr td", timeout=30000)  # type: ignore[attr-defined]
        table = page.locator(".table-wrap table[data-sortable]")  # type: ignore[attr-defined]
        rows = table.locator("tbody tr")

        def _execute_diagnostics() -> str:
            # Evidence hygiene: read ONLY the overall flash error, the
            # per-row action pill (td 1) and the errors cell (td 9).
            # The one-time plaintext key cell (td 4) and any full row or
            # page HTML are never read, so a failure cannot log a key.
            flash = page.locator(".admin-flash-error")  # type: ignore[attr-defined]
            flash_text = flash.first.inner_text().strip() if flash.count() else ""
            action_texts = [
                rows.nth(i).locator("td").nth(1).inner_text().strip()
                for i in range(rows.count())
            ]
            error_texts: list[str] = []
            for i in range(rows.count()):
                items = rows.nth(i).locator("td").nth(9).locator("li")  # type: ignore[attr-defined]
                error_texts.extend(
                    items.nth(j).inner_text().strip() for j in range(items.count())
                )
            return (
                f"status={execute_response.status} flash={flash_text!r} "
                f"actions={action_texts} errors={error_texts}"
            )

        assert execute_response.status == 200, (
            f"execute POST must return 200 on success: {_execute_diagnostics()}"
        )
        assert rows.count() == 3, (
            f"expected 3 created result rows: {_execute_diagnostics()}"
        )
        created = [
            rows.nth(i).locator("td").nth(1).inner_text() for i in range(3)
        ]
        assert all("created" in action.lower() for action in created), created
        # Row numbers sort numerically descending (3, 2, 1).
        row_header = table.locator("thead th").filter(has_text="Row")
        row_header.locator("button").click()
        assert row_header.get_attribute("aria-sort") == "ascending"
        rows = table.locator("tbody tr")
        assert [
            rows.nth(i).locator("td").nth(0).inner_text().strip() for i in range(3)
        ] == ["1", "2", "3"]
        row_header.locator("button").click()
        assert row_header.get_attribute("aria-sort") == "descending"
        rows = table.locator("tbody tr")
        assert [
            rows.nth(i).locator("td").nth(0).inner_text().strip() for i in range(3)
        ] == ["3", "2", "1"]
        # Quotas sort: the 2.00 row still carries u021's created public key.
        # Evidence hygiene: read ONLY the owner cell (2) and key-metadata
        # cell (3) + quota cell (6); the one-time plaintext key cell (4)
        # is never read, so an assertion failure cannot log it.
        quotas_header = table.locator("thead th").filter(has_text="Quotas")
        quotas_header.locator("button").click()
        rows = table.locator("tbody tr")
        result_costs = [
            rows.nth(i).locator("td").nth(6).get_attribute("data-sort-value")
            for i in range(3)
        ]
        assert [float(c) for c in result_costs] == [2.0, 5.5, 10.0], (
            f"result money sort wrong: {result_costs}"
        )
        owner_cell = rows.nth(0).locator("td").nth(2).inner_text()
        key_cell = rows.nth(0).locator("td").nth(3).inner_text()
        assert f"u021-{suffix}@example.org" in owner_cell
        assert "Public ID:" in key_cell, (
            "created row association lost: the 2.00 row must keep its key cell"
        )
        assert _run_in_thread(_key_count(env["database_url"])) == before_count + 3


# ---------------------------------------------------------------------------
# 7) Institution / cohort NAME filters: known-option pickers that submit
#    the NAME (never a UUID), with latest-100 options + older-name search.
# ---------------------------------------------------------------------------


def test_institution_cohort_name_filters_submit_names(chromium, usab_env) -> None:
    """The institution and cohort list NAME filters are known-option
    record choices (latest-first, server-searchable) that submit the NAME
    itself; the list then filters on that name. The no-JS fallback keeps a
    plain name input."""
    env = usab_env
    suffix = env["suffix"]
    inst_a = env["institution_a_name"]
    cohort_name = f"usab-cohort-{suffix}"
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)

        # --- institutions list: name picker offers the known names ---
        page.goto("/admin/institutions")
        inst_rc = '.rc[data-rc-id="institutions-name-filter"]'
        page.locator(f"{inst_rc} .rc-open").click()  # type: ignore[attr-defined]
        assert _menu_visible(page, inst_rc)
        options = page.locator(f"{inst_rc} .rc-option")
        labels = [
            options.nth(i).locator(".rc-option-label").inner_text()
            for i in range(options.count())
        ]
        assert inst_a in labels, f"known institution name missing: {labels}"
        # Server search reaches a name by partial match.
        page.fill(f"{inst_rc} .rc-search", "Inst A")  # type: ignore[attr-defined]
        page.wait_for_selector(  # type: ignore[attr-defined]
            f'{inst_rc} .rc-option:has-text("{inst_a}")', timeout=15000
        )
        # Mouse select: the submitted value is the NAME, never a UUID.
        page.locator(f'{inst_rc} .rc-option:has-text("{inst_a}")').click()  # type: ignore[attr-defined]
        assert not _menu_visible(page, inst_rc), "menu must close after mouse selection"
        submitted = _hidden_values(page, inst_rc)
        assert submitted == [inst_a], f"name filter must submit the name: {submitted}"
        assert env["institution_a_id"] not in submitted, "a UUID must never be submitted"

        # Submitting the filter narrows the real list to that institution.
        # The real filter submit button — never a union of all filter-bar
        # buttons: the record-choice clear/open buttons sit inside the
        # same form and would clear/reopen the menu instead of submitting.
        page.get_by_role("button", name="Filter", exact=True).click()  # type: ignore[attr-defined]
        page.wait_for_url("**/admin/institutions?name=*")  # type: ignore[attr-defined]
        rows = page.locator(".table-wrap table[data-sortable] tbody tr")  # type: ignore[attr-defined]
        assert rows.count() == 1
        assert inst_a in rows.first.locator("td").first.inner_text()

        # --- cohorts list: same contract for the cohort name filter ---
        page.goto("/admin/cohorts")
        cohort_rc = '.rc[data-rc-id="cohorts-name-filter"]'
        page.locator(f"{cohort_rc} .rc-open").click()  # type: ignore[attr-defined]
        assert _menu_visible(page, cohort_rc)
        page.fill(f"{cohort_rc} .rc-search", cohort_name)  # type: ignore[attr-defined]
        page.wait_for_selector(  # type: ignore[attr-defined]
            f'{cohort_rc} .rc-option:has-text("{cohort_name}")', timeout=15000
        )
        page.locator(f'{cohort_rc} .rc-option:has-text("{cohort_name}")').click()  # type: ignore[attr-defined]
        assert not _menu_visible(page, cohort_rc), "menu must close after mouse selection"
        assert _hidden_values(page, cohort_rc) == [cohort_name]
        # The real filter submit button — never a union of all filter-bar
        # buttons: the record-choice clear/open buttons sit inside the
        # same form and would clear/reopen the menu instead of submitting.
        page.get_by_role("button", name="Filter", exact=True).click()  # type: ignore[attr-defined]
        page.wait_for_url("**/admin/cohorts?name=*")  # type: ignore[attr-defined]
        rows = page.locator(".table-wrap table[data-sortable] tbody tr")  # type: ignore[attr-defined]
        assert rows.count() == 1
        assert cohort_name in rows.first.locator("td").first.inner_text()


# ---------------------------------------------------------------------------
# 9) Allow-new controls: PHYSICAL keystrokes (not fill()) on the real
#    macro/JS/CSS + Chromium. Atomic fill() masks focus/value bugs in the
#    typed-entry path; this regression uses page.keyboard.type and
#    asserts the authoritative value end to end.
# ---------------------------------------------------------------------------


def test_allow_new_physical_keystroke_typed_value_is_authoritative(
    chromium, usab_env
) -> None:
    env = usab_env
    suffix = env["suffix"]
    inst_rc = '.rc[data-rc-id="institutions-name-filter"]'
    new_name = f"Usab Typed Inst {suffix} 042"
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/institutions")

        # 1) Click the primary field and type a NEW name with real
        #    keystrokes: focus must STAY on the authoritative input,
        #    the whole typed value must be carried by the managed
        #    hidden field, and the popup candidate lookup must search
        #    the typed text.
        page.locator(f"{inst_rc} .rc-input").click()  # type: ignore[attr-defined]
        # The debounced candidate lookup must search the typed text;
        # match on the DECODED query (URLSearchParams encodes spaces as
        # "+", not "%20").
        with page.expect_request(  # type: ignore[attr-defined]
            lambda r: "/admin/record-choices" in r.url
            and parse_qs(urlparse(r.url).query).get("q") == [new_name],
            timeout=15000,
        ) as lookup_info:
            page.keyboard.type(new_name)  # type: ignore[attr-defined]
        assert lookup_info.value is not None
        focused_class = page.evaluate("document.activeElement.className")
        assert "rc-input" in focused_class, (
            f"focus left the primary input while typing: {focused_class!r}"
        )
        assert (
            page.locator(f"{inst_rc} .rc-input").input_value()  # type: ignore[attr-defined]
            == new_name
        )
        assert _hidden_values(page, inst_rc) == [new_name]

        # 2) Escape closes the menu (if open) but PRESERVES the typed
        #    value in both the visible field and the managed field.
        page.keyboard.press("Escape")  # type: ignore[attr-defined]
        assert (
            page.locator(f"{inst_rc} .rc-input").input_value()  # type: ignore[attr-defined]
            == new_name
        )
        assert _hidden_values(page, inst_rc) == [new_name]

        # 3) Clear, reopen, and pick an EXPLICIT known database name by
        #    keyboard on the primary input: the submitted value is the
        #    known option's value (the name itself), never stale typed
        #    text. The reopened menu must show the latest batch again —
        #    the previously typed NEW name must not linger as a stale
        #    search option (the clear handler cancels the pending
        #    debounce, invalidates the in-flight response, and resets
        #    the option set to the server-rendered batch).
        page.locator(f"{inst_rc} .rc-clear").click()  # type: ignore[attr-defined]
        assert _hidden_values(page, inst_rc) == [""]
        page.locator(f"{inst_rc} .rc-input").click()  # type: ignore[attr-defined]
        assert _menu_visible(page, inst_rc)
        assert (
            page.locator(f'{inst_rc} .rc-option:has-text("{new_name}")').count()  # type: ignore[attr-defined]
            == 0
        ), "stale typed value must not be a menu option after clear"
        known_name = str(env["institution_a_name"])
        # Physical typing filters the menu and issues the fresh scoped
        # lookup; wait for BOTH the request and its response so the
        # rendered list is the server's, not a mid-flight re-render.
        with page.expect_request(  # type: ignore[attr-defined]
            lambda r: "/admin/record-choices" in r.url
            and parse_qs(urlparse(r.url).query).get("q") == [known_name],
            timeout=15000,
        ) as known_lookup, page.expect_response(  # type: ignore[attr-defined]
            lambda r: "/admin/record-choices" in r.url,
            timeout=15000,
        ) as known_response:
            page.keyboard.type(known_name)  # type: ignore[attr-defined]
        assert known_lookup.value is not None
        assert known_response.value is not None
        known_option = page.locator(f'{inst_rc} .rc-option:has-text("{known_name}")')  # type: ignore[attr-defined]
        known_option.wait_for(timeout=15000)
        page.keyboard.press("ArrowDown")  # type: ignore[attr-defined]
        page.keyboard.press("Enter")  # type: ignore[attr-defined]
        assert not _menu_visible(page, inst_rc), "menu must close after keyboard selection"
        assert (
            page.locator(f"{inst_rc} .rc-input").input_value()  # type: ignore[attr-defined]
            == known_name
        )
        assert _hidden_values(page, inst_rc) == [known_name]
        assert new_name not in _hidden_values(page, inst_rc)


# ---------------------------------------------------------------------------
# 10) Policy selector: latest-100 page, server search, scope semantics,
#     and real submission of an older (off-page) provider
# ---------------------------------------------------------------------------


def test_policy_provider_model_search_and_older_submit(
    chromium, usab_env
) -> None:
    env = usab_env
    suffix = env["suffix"]
    prov_a = str(env["provider_a"])
    prov_b = str(env["provider_b"])
    model_a1 = str(env["model_a1"])
    model_b1 = str(env["model_b1"])
    oldprov = str(env["oldprov_search"])
    oldprov_second = str(env["oldprov_second"])
    disabled = str(env["disabled_prov"])
    old_model = f"usab-policy-104-{suffix}"  # OLDEST seeded provider-A route

    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys/create")

        provider_available = page.locator('[data-policy-available="providers"]')  # type: ignore[attr-defined]
        provider_selected = page.locator('[data-policy-selected="providers"]')  # type: ignore[attr-defined]
        endpoint_available = page.locator('[data-policy-available="endpoints"]')  # type: ignore[attr-defined]
        provider_search = page.locator('[data-policy-provider-search]')  # type: ignore[attr-defined]
        provider_results = page.locator('[data-policy-provider-search-results]')  # type: ignore[attr-defined]
        model_search = page.locator('[data-policy-model-search]')  # type: ignore[attr-defined]
        model_results = page.locator('[data-policy-model-search-results]')  # type: ignore[attr-defined]
        provider_manual = page.locator('[data-policy-manual="providers"]')  # type: ignore[attr-defined]

        def _select_values(locator: object) -> list[str]:
            return locator.locator("option").evaluate_all(  # type: ignore[attr-defined]
                "els => els.map(e => e.value)"
            )

        # 1) The provider page is EXACTLY the latest 100 enabled providers,
        #    newest first. The two newest (prov_b, prov_a) lead, then the
        #    98 newest of the 105 seeded older providers; the 7 oldest
        #    and the recently-created DISABLED provider are off-page and
        #    must never appear as choices.
        batch = _select_values(provider_available)
        assert len(batch) == 100, f"provider page must cap at 100: {len(batch)}"
        assert batch[0] == prov_b and batch[1] == prov_a
        for i in range(98):
            assert f"usab-oldprov-{i:03d}-{suffix}" in batch
        assert oldprov not in batch
        assert oldprov_second not in batch
        assert disabled not in batch

        # The create form defaults to "allow all enabled providers"
        # (checked), which disables the available-providers select.
        # Switch to an explicit selection to exercise the picker; the
        # submission later sends the unchecked toggle plus the explicit
        # allow-list.
        page.uncheck('[data-policy-toggle="providers"]')  # type: ignore[attr-defined]

        # 2) A plain click on the multiple select REPLACES the highlight;
        #    the Add button moves it into the policy and the JS syncs the
        #    manual textarea (newline-separated).
        provider_available.locator(f"option[value='{prov_a}']").click()  # type: ignore[attr-defined]
        page.click('[data-policy-add="providers"]')  # type: ignore[attr-defined]
        assert _select_values(provider_selected) == [prov_a]
        assert provider_manual.input_value() == prov_a

        # 3) Model search with an EXPLICITLY EMPTY endpoint scope (nothing
        #    selected, allow-all off) must send a blank endpoint parameter
        #    and return no choices, not an unscoped search.
        def _model_empty_scope(url: str) -> bool:
            params = parse_qs(urlparse(url).query, keep_blank_values=True)
            return (
                "/admin/record-choices" in url
                and params.get("kind") == ["policy_model"]
                and params.get("provider") == [prov_a]
                and params.get("endpoint") == [""]
                and params.get("q") == ["usab-model"]
            )

        with page.expect_request(lambda r: _model_empty_scope(r.url), timeout=15000) as empty_scope:  # type: ignore[attr-defined]
            model_search.fill("usab-model")  # type: ignore[attr-defined]
        assert empty_scope.value is not None
        page.wait_for_selector(  # type: ignore[attr-defined]
            '[data-policy-model-search-results] li:has-text("No matching enabled route models.")',
            timeout=15000,
        )
        model_search.fill("")  # type: ignore[attr-defined]
        # 4) Server search finds the OLDEST seeded provider (outside the
        #    page) and choosing it APPENDS to the current selection while
        #    keeping the manual textarea in sync.
        with page.expect_request(  # type: ignore[attr-defined]
            lambda r: "/admin/record-choices" in r.url
            and parse_qs(urlparse(r.url).query).get("kind") == ["policy_provider"]
            and parse_qs(urlparse(r.url).query).get("q") == [oldprov],
            timeout=15000,
        ) as provider_lookup:
            provider_search.fill(oldprov)  # type: ignore[attr-defined]
        assert provider_lookup.value is not None
        old_option = provider_results.locator(f'li:has-text("{oldprov}")')  # type: ignore[attr-defined]
        old_option.wait_for(timeout=15000)
        assert disabled not in old_option.inner_text()
        old_option.click()
        assert _select_values(provider_selected) == [prov_a, oldprov]
        assert provider_manual.input_value() == f"{prov_a}\n{oldprov}"

        # 5) The endpoint page is exactly the canonical implemented set.
        endpoints = _select_values(endpoint_available)
        assert len(endpoints) == 22
        assert set(endpoints) == set(IMPLEMENTED_CLIENT_ENDPOINTS)

        # 6) With the chat endpoint selected, the model search is scoped to
        #    BOTH selected providers and the model-backed endpoint: the
        #    provider-A model token appears, the provider-B token is
        #    excluded by the provider scope.
        endpoint_available.locator("option[value='/v1/chat/completions']").click()  # type: ignore[attr-defined]
        page.click('[data-policy-add="endpoints"]')  # type: ignore[attr-defined]

        def _model_scoped(url: str) -> bool:
            params = parse_qs(urlparse(url).query, keep_blank_values=True)
            return (
                "/admin/record-choices" in url
                and params.get("kind") == ["policy_model"]
                and sorted(params.get("provider", [])) == sorted([prov_a, oldprov])
                and params.get("endpoint") == ["/v1/chat/completions"]
                and params.get("q") == ["usab-model"]
            )

        with page.expect_request(lambda r: _model_scoped(r.url), timeout=15000) as scoped_lookup:  # type: ignore[attr-defined]
            model_search.fill("usab-model")  # type: ignore[attr-defined]
        assert scoped_lookup.value is not None
        model_results.locator(f'li:has-text("{model_a1}")').wait_for(timeout=15000)  # type: ignore[attr-defined]
        result_text = model_results.inner_text()
        assert model_a1 in result_text
        assert model_b1 not in result_text, (
            "model search must respect the selected provider scope"
        )

        # 6b) The OLDEST seeded provider-A route (outside the initial
        #     latest-100 model page) must be reachable by search under the
        #     SAME provider/endpoint scope, and choosing it stores the
        #     exact token in the model selection and manual textarea.
        model_tokens = page.locator(  # type: ignore[attr-defined]
            '[data-policy-available="models"] option'
        ).evaluate_all("els => els.map(e => e.dataset.modelToken || '')")
        assert old_model not in model_tokens, (
            "oldest route must be outside the initial latest-100 model page"
        )

        def _model_old_scoped(url: str) -> bool:
            params = parse_qs(urlparse(url).query, keep_blank_values=True)
            return (
                "/admin/record-choices" in url
                and params.get("kind") == ["policy_model"]
                and sorted(params.get("provider", [])) == sorted([prov_a, oldprov])
                and params.get("endpoint") == ["/v1/chat/completions"]
                and params.get("q") == [old_model]
            )

        with page.expect_request(lambda r: _model_old_scoped(r.url), timeout=15000) as old_model_lookup:  # type: ignore[attr-defined]
            model_search.fill(old_model)  # type: ignore[attr-defined]
        assert old_model_lookup.value is not None
        old_model_option = model_results.locator(f'li:has-text("{old_model}")')  # type: ignore[attr-defined]
        old_model_option.wait_for(timeout=15000)
        old_model_option.click()
        model_selected = page.locator('[data-policy-selected="models"]')  # type: ignore[attr-defined]
        assert _select_values(model_selected) == [old_model]
        assert (
            page.locator('[data-policy-manual="models"]').input_value()  # type: ignore[attr-defined]
            == old_model
        )

        # 7) The page is presentation, NOT authority: an older provider
        #    found by search must still submit. The manual textarea is the
        #    submitted field and the JS re-syncs the selection from it, so
        #    rewriting it to ONLY the older provider scopes the new key to
        #    exactly that provider. The owner is chosen through the record
        #    picker (u005 is outside its latest-100 eligible batch, so it
        #    is reached by search, proving the picker's older search on
        #    this form too).
        before_keys = _run_in_thread(_key_count(env["database_url"]))
        # The manual textareas live inside the collapsed <details>
        # fallback panel; expand it before editing.
        page.click('details.policy-manual-details summary')  # type: ignore[attr-defined]
        provider_manual.fill(oldprov)  # type: ignore[attr-defined]
        assert _select_values(provider_selected) == [oldprov]
        # Step 6b left the older model token in the model list; reset it
        # so the submitted policy is "allow all models" again.
        model_manual = page.locator('[data-policy-manual="models"]')  # type: ignore[attr-defined]
        model_manual.fill("")  # type: ignore[attr-defined]
        assert _select_values(page.locator('[data-policy-selected="models"]')) == []  # type: ignore[attr-defined]

        owner_rc = '.rc:has(input[name="owner_id"])'
        page.locator(f"{owner_rc} .rc-open").click()  # type: ignore[attr-defined]
        assert _menu_visible(page, owner_rc)
        page.locator(f"{owner_rc} .rc-search").fill(f"u005-{suffix}@example.org")  # type: ignore[attr-defined]
        page.locator(f'{owner_rc} .rc-option:has-text("u005-{suffix}@example.org")').click()  # type: ignore[attr-defined]
        assert _hidden_values(page, owner_rc) == [str(env["owner_ids"]["u005"])]

        page.check('[data-policy-toggle="endpoints"]')  # type: ignore[attr-defined]
        page.check('[data-policy-toggle="models"]')  # type: ignore[attr-defined]
        page.fill('input[name="valid_days"]', "30")  # type: ignore[attr-defined]
        page.fill('input[name="reason"]', "usab policy older-provider key")  # type: ignore[attr-defined]
        page.click('form[action="/admin/keys/create"] button[type="submit"]')  # type: ignore[attr-defined]
        # Result page shows the one-time plaintext notice; the plaintext
        # key cell itself is never read by this test.
        page.wait_for_selector('text=Copy this key now', timeout=30000)  # type: ignore[attr-defined]

        after_keys = _run_in_thread(_key_count(env["database_url"]))
        assert after_keys == before_keys + 1
        row = _run_in_thread(_latest_key(env["database_url"]))
        assert row["owner_id"] == str(env["owner_ids"]["u005"])
        assert row["metadata_json"].get("allowed_providers") == [oldprov]
        assert row["allow_all_models"] is True
        assert row["allow_all_endpoints"] is True
