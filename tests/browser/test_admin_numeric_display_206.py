"""206-a/206-b admin numeric display: real Chromium on the owned PostgreSQL.

Actual uvicorn app, real stylesheet, and real HTTP admin pages against
the already-qualified owned, labeled, loopback-bound, tmpfs-backed
PostgreSQL fixture. Verifies the locale-stable readouts end to end:
comma/dot grouping without scientific notation, exponent-zero rendering
(0E-9 -> 0), token quantities in millions with the exact comma-grouped
count in the accessible title, actual-zero cost preference over the
estimate, and raw exact units in editable inputs. Sorting clicks stay on
the typed raw ``data-sort-value`` keys, including distinct values that
share a rounded M label and None-last in both directions.

206-b adds the finished human-readable policy surfaces on the same
fixture: the key-detail rate-limit summary (grouped req/min, M
tokens/min with the exact raw string in the title), the Chat live-burn
summary (9-dp zero money, M token margin), the direct token-margin
readout in M with the exact count in the title, and the usage-detail
cached/reasoning exact-count title. The editable token-margin input
keeps its exact raw units (no comma/M parser).

Safety: only synthetic fixture values are read; session and CSRF values
are used transiently for login and never logged or screenshotted.
Screenshots (synthetic data only) go under /tmp/slaif206/.

Run:  python -m pytest tests/browser/test_admin_numeric_display_206.py -m playwright
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
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import GatewayKey, Owner, UsageLedger
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.main import create_app
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
SCREENSHOT_DIR = Path("/tmp/slaif206")

BIG_TOKENS = 937_826_734
TWIN_A = 937_826_700  # same rounded 937.827M label as BIG/TWIN_B
TWIN_B = 937_826_749  # distinct raw value, same rounded label


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


async def _seed_numeric_display_data(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"numadmin-{suffix}@example.org",
                    display_name="Numeric Display Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                institution = await InstitutionsRepository(session).create_institution(
                    name=f"Numeric Inst {suffix}", country="SI"
                )
                owner = Owner(
                    id=uuid.uuid4(),
                    name="Num",
                    surname="Display",
                    email=f"numdisplay-{suffix}@example.org",
                    institution_id=institution.id,
                    is_active=True,
                    anonymized_at=None,
                    created_at=now - timedelta(hours=2),
                    updated_at=now - timedelta(hours=2),
                )
                session.add(owner)
                session.flush()

                async def make_key(
                    name: str,
                    *,
                    tokens_used: int,
                    requests_used: int,
                    cost_used: Decimal,
                    token_limit: int | None,
                    request_limit: int | None,
                    cost_limit: Decimal | None,
                    live_burn: bool = False,
                    rate_requests: int | None = None,
                    rate_tokens: int | None = None,
                    token_margin: int = 0,
                ) -> GatewayKey:
                    metadata: dict[str, object] | None = None
                    if live_burn:
                        metadata = {
                            "chat_streaming_live_burn": {
                                "version": 1,
                                "enabled": True,
                                "cost_margin_eur": "0",
                                "token_margin": token_margin,
                            }
                        }
                    key = await GatewayKeysRepository(session).create_gateway_key_record(
                        public_key_id=f"num-{name}-{suffix}",
                        token_hash=f"token_hash_num_{suffix}_{name}",
                        owner_id=owner.id,
                        valid_from=now - timedelta(days=1),
                        valid_until=now + timedelta(days=30),
                        key_hint=f"sk-slaif-num{suffix[:4]}{name}",
                        cost_limit_eur=cost_limit,
                        token_limit_total=token_limit,
                        request_limit_total=request_limit,
                        rate_limit_requests_per_minute=rate_requests,
                        rate_limit_tokens_per_minute=rate_tokens,
                        allow_all_models=True,
                        allow_all_endpoints=True,
                        created_by_admin_user_id=admin.id,
                        metadata_json=metadata,
                    )
                    key.requests_used_total = requests_used
                    key.tokens_used_total = tokens_used
                    key.cost_used_eur = cost_used
                    return key

                keys: dict[str, GatewayKey] = {}
                keys["big"] = await make_key(
                    "big",
                    tokens_used=BIG_TOKENS,
                    requests_used=BIG_TOKENS,
                    cost_used=Decimal("7.750000000"),
                    token_limit=None,
                    request_limit=None,
                    cost_limit=None,
                )
                keys["twinA"] = await make_key(
                    "twinA",
                    tokens_used=TWIN_A,
                    requests_used=11,
                    cost_used=Decimal("0"),
                    token_limit=None,
                    request_limit=None,
                    cost_limit=None,
                )
                keys["twinB"] = await make_key(
                    "twinB",
                    tokens_used=TWIN_B,
                    requests_used=12,
                    cost_used=Decimal("0"),
                    token_limit=None,
                    request_limit=None,
                    cost_limit=None,
                )
                keys["zero"] = await make_key(
                    "zero",
                    tokens_used=0,
                    requests_used=0,
                    # the production exponent-zero shape (9-dp quantized
                    # stored zero) must render 0, never 0E-9
                    cost_used=Decimal("0E-9"),
                    token_limit=None,
                    request_limit=None,
                    cost_limit=None,
                )
                keys["small"] = await make_key(
                    "small",
                    tokens_used=1000,
                    requests_used=7,
                    cost_used=Decimal("0"),
                    token_limit=1500,
                    request_limit=900,
                    cost_limit=Decimal("100.000000000"),
                )
                keys["lb"] = await make_key(
                    "lb",
                    tokens_used=0,
                    requests_used=3,
                    cost_used=Decimal("0"),
                    token_limit=999_999_500,
                    request_limit=None,
                    cost_limit=None,
                    live_burn=True,
                    # 206-b: the same big token quantity in the rate
                    # summary and a NEGATIVE token margin so the M
                    # display/sign and the raw editable units are both
                    # demonstrated on the real page.
                    rate_requests=BIG_TOKENS,
                    rate_tokens=BIG_TOKENS,
                    token_margin=-250,
                )

                usage: dict[str, UsageLedger] = {}
                usage_plan = (
                    # (name, total_tokens, actual, estimated)
                    ("u0", BIG_TOKENS, Decimal("0E-9"), Decimal("9.990000000")),
                    ("u1", TWIN_A, None, Decimal("0.010000000")),
                    ("u2", 1000, None, None),
                )
                usage_cached_reasoning = {
                    "u0": (BIG_TOKENS, 1000000),
                }
                for n, (name, tokens, actual, estimated) in enumerate(usage_plan):
                    row = UsageLedger(
                        id=uuid.uuid4(),
                        request_id=f"num-{name}-{suffix}",
                        gateway_key_id=keys["big"].id,
                        endpoint="/v1/chat/completions",
                        provider="num-provider",
                        requested_model="num-model",
                        success=True,
                        accounting_status="finalized",
                        http_status=200,
                        total_tokens=tokens,
                        cached_tokens=usage_cached_reasoning.get(name, (0, 0))[0],
                        reasoning_tokens=usage_cached_reasoning.get(name, (0, 0))[1],
                        actual_cost_eur=actual,
                        estimated_cost_eur=estimated,
                        started_at=now - timedelta(hours=2, minutes=n),
                        finished_at=now
                        - timedelta(hours=2, minutes=n)
                        + timedelta(milliseconds=25),
                        created_at=now - timedelta(hours=2, minutes=n),
                    )
                    session.add(row)
                    usage[name] = row

                return {
                    "admin_email": admin.email,
                    "suffix": suffix,
                    "key_ids": {name: str(key.id) for name, key in keys.items()},
                    "usage_ids": {name: str(row.id) for name, row in usage.items()},
                }
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Module environment
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def num_env(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    data = asyncio.run(_seed_numeric_display_data(owned_pg_url))
    app = create_app(_settings(owned_pg_url))
    port = _free_port()
    data["base_url"] = f"http://127.0.0.1:{port}"
    with _run_uvicorn_server(app, port):
        yield data


@pytest.fixture(scope="module")
def chromium(num_env) -> Iterator[object]:
    """Depends on ``num_env`` on purpose: the Playwright sync session runs
    an asyncio loop on the main thread, so PostgreSQL readiness, seeding,
    and the uvicorn app must complete BEFORE it starts (and the browser
    closes before DB teardown)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        yield pw.chromium.launch()


def _login(page: object, env: dict[str, Any]) -> None:
    page.goto("/admin/login")  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="email"]', str(env["admin_email"]))  # type: ignore[attr-defined]
    page.fill(f'{LOGIN_FORM} input[name="password"]', ADMIN_PASSWORD)  # type: ignore[attr-defined]
    page.click(f'{LOGIN_FORM} button[type="submit"]')  # type: ignore[attr-defined]
    page.wait_for_url("**/admin")  # type: ignore[attr-defined]


def _row_by_link(page: object, link_text: str) -> object:
    """Row whose cell link text ENDS with ``link_text`` (keys list links
    prepend the configured key prefix)."""
    table = page.locator(".table-wrap table[data-sortable]")  # type: ignore[attr-defined]
    rows = table.locator("tbody tr")
    for i in range(rows.count()):
        text = rows.nth(i).locator("td a").first.inner_text()  # type: ignore[attr-defined]
        if text.endswith(link_text):
            return rows.nth(i)
    raise AssertionError(f"row with link ending {link_text!r} not found")


def _raw(row: object, column: int) -> str | None:
    return row.locator("td").nth(column).get_attribute("data-sort-value")  # type: ignore[attr-defined]


def _visible(row: object, column: int) -> str:
    return row.locator("td").nth(column).inner_text().strip()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 1) Keys list: grouped/M readouts, titles, raw sorts
# ---------------------------------------------------------------------------


def test_keys_list_display_and_raw_sorts(chromium, num_env) -> None:
    env = num_env
    suffix = env["suffix"]
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/keys")
        page.wait_for_selector(".table-wrap table[data-sortable] tbody tr")  # type: ignore[attr-defined]
        table = page.locator(".table-wrap table[data-sortable]")  # type: ignore[attr-defined]
        assert table.locator("tbody tr").count() == 6

        body = page.content()
        # No scientific/exponent notation anywhere on the page.
        assert "0E-9" not in body

        # --- formatted readouts + accessible exact counts
        big = _row_by_link(page, f"num-big-{suffix}")
        assert _visible(big, 7) == "937,826,734"  # requests, comma-grouped
        assert _visible(big, 8) == "937.827M"  # tokens in millions
        assert big.locator("td").nth(8).get_attribute("title") == "937,826,734"  # type: ignore[attr-defined]
        assert _visible(big, 9) == "7.75"
        assert _raw(big, 7) == "937826734"  # raw sort key unscaled/ungrouped
        assert _raw(big, 8) == "937826734"
        assert _visible(big, 10) == "Unlimited"
        assert _raw(big, 10) == ""

        zero = _row_by_link(page, f"num-zero-{suffix}")
        assert _visible(zero, 9) == "0"  # exponent zero renders 0
        assert _raw(zero, 9) == "0"

        small = _row_by_link(page, f"num-small-{suffix}")
        assert _visible(small, 8) == "0.001M"  # below-1M exact scaling
        assert _visible(small, 10) == "900"
        assert _visible(small, 11) == "0.0015M"
        assert small.locator("td").nth(11).get_attribute("title") == "1,500"  # type: ignore[attr-defined]
        assert _visible(small, 12) == "100"  # 9-dp limit without padded zeros
        assert _raw(small, 12) == "100"  # canonical ungrouped dec raw key

        lb = _row_by_link(page, f"num-lb-{suffix}")
        assert _visible(lb, 11) == "1,000M"  # half-up rounding boundary
        assert lb.locator("td").nth(11).get_attribute("title") == "999,999,500"  # type: ignore[attr-defined]
        assert _raw(lb, 11) == "999999500"

        # --- raw typed sorting on the tokens-used column: the three
        # distinct values that all display 937.827M must keep their exact
        # order (a display-text sort would tie them).
        leaf_ths = table.locator("thead tr:not(.group-row) th")
        token_header = leaf_ths.filter(has_text="Tokens").nth(0)
        assert token_header.get_attribute("data-sort-type") == "number"
        token_header.locator("a.ts-link").click()
        rows = table.locator("tbody tr")
        raws = [
            rows.nth(i).locator("td").nth(8).get_attribute("data-sort-value")  # type: ignore[attr-defined]
            for i in range(6)
        ]
        assert raws == ["0", "0", "1000", str(TWIN_A), str(BIG_TOKENS), str(TWIN_B)], raws
        token_header.locator("a.ts-link").click()
        rows = table.locator("tbody tr")
        raws_desc = [
            rows.nth(i).locator("td").nth(8).get_attribute("data-sort-value")  # type: ignore[attr-defined]
            for i in range(6)
        ]
        assert raws_desc == [
            str(TWIN_B),
            str(BIG_TOKENS),
            str(TWIN_A),
            "1000",
            "0",
            "0",
        ], raws_desc

        # --- token limit column: set values first, None (Unlimited) last
        # in BOTH directions.
        # Quota group "Tokens" leaf header (the usage leaf is the first).
        limit_header = leaf_ths.filter(has_text="Tokens").nth(1)
        assert limit_header.get_attribute("data-sort-type") == "number"
        limit_header.locator("a.ts-link").click()
        rows = table.locator("tbody tr")
        limit_raws = [
            rows.nth(i).locator("td").nth(11).get_attribute("data-sort-value")  # type: ignore[attr-defined]
            for i in range(6)
        ]
        assert sorted(limit_raws) == ["", "", "", "", "1500", "999999500"], limit_raws
        assert limit_raws[:2] == ["1500", "999999500"], limit_raws
        assert all(v == "" for v in limit_raws[2:]), limit_raws
        limit_header.locator("a.ts-link").click()
        rows = table.locator("tbody tr")
        limit_raws_desc = [
            rows.nth(i).locator("td").nth(11).get_attribute("data-sort-value")  # type: ignore[attr-defined]
            for i in range(6)
        ]
        assert limit_raws_desc[:2] == ["999999500", "1500"], limit_raws_desc
        assert all(v == "" for v in limit_raws_desc[2:]), limit_raws_desc

        # --- cost column: five valid zeros stay real zeros, 7.75 last.
        cost_header = leaf_ths.filter(has_text="Cost (EUR)").nth(0)
        assert cost_header.get_attribute("data-sort-type") == "money"
        cost_header.locator("a.ts-link").click()
        rows = table.locator("tbody tr")
        cost_raws = [
            rows.nth(i).locator("td").nth(9).get_attribute("data-sort-value")  # type: ignore[attr-defined]
            for i in range(6)
        ]
        assert [float(v) for v in cost_raws] == [0.0, 0.0, 0.0, 0.0, 0.0, 7.75], cost_raws
        # The exponent-zero row displays 0 (not n/a, not the padded form).
        zero_row = _row_by_link(page, f"num-zero-{suffix}")
        assert _visible(zero_row, 9) == "0"

        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SCREENSHOT_DIR / "keys-numeric-display.png"))  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 2) Key detail: live-burn exponent zero + raw editable units
# ---------------------------------------------------------------------------


def test_key_detail_live_burn_zero_and_raw_inputs(chromium, num_env) -> None:
    env = num_env
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto(f"/admin/keys/{env['key_ids']['lb']}")
        page.wait_for_selector("#key-chat-streaming-live-burn-heading")  # type: ignore[attr-defined]

        assert "0E-9" not in page.content()
        # Readout: the 9-dp quantized zero margin is readable as 0.
        margin_dd = page.locator("dt:has-text('Cost margin EUR') + dd")  # type: ignore[attr-defined]
        assert margin_dd.inner_text().strip() == "0"
        # Editable controls keep the exact raw value in the same units
        # (0, not 0M and not 0E-9); the token margin input is raw too
        # (the negative margin stays the exact raw -250, never -0.00025M).
        cost_input = page.locator(
            "input[name='chat_streaming_live_burn_cost_margin_eur']"  # type: ignore[attr-defined]
        )
        assert cost_input.input_value() == "0"
        token_input = page.locator(
            "input[name='chat_streaming_live_burn_token_margin']"  # type: ignore[attr-defined]
        )
        assert token_input.input_value() == "-250"

        # Quota readouts: millions display with the exact grouped title.
        token_limit_dd = page.locator("dt:has-text('Token limit') + dd")  # type: ignore[attr-defined]
        assert token_limit_dd.inner_text().strip() == "1,000M"
        assert token_limit_dd.get_attribute("title") == "999,999,500"

        # 206-b: the service-built rate-limit summary renders grouped
        # req/min and M tokens/min; the exact unrounded service string
        # stays in the accessible title.
        rate_dd = page.locator("dt:has-text('Rate limits') + dd")  # type: ignore[attr-defined]
        assert rate_dd.inner_text().strip() == "937,826,734 req/min, 937.827M tokens/min"
        assert rate_dd.get_attribute("title") == "937826734 req/min, 937826734 tokens/min"

        # 206-b: the Chat live-burn summary shows the 9-dp zero money as
        # 0 and the negative token margin in M, exact raw values in the
        # title; the direct readout is M with the exact count in title.
        burn_dd = page.locator("dt:has-text('Chat streaming live-burn') + dd")  # type: ignore[attr-defined]
        assert burn_dd.inner_text().strip() == "Chat live-burn: on, cost margin EUR 0, token margin -0.00025M"
        assert burn_dd.get_attribute("title") == "Chat live-burn: on, cost margin EUR 0.000000000, token margin -250"
        token_margin_dd = page.locator("dt:has-text('Output token margin') + dd")  # type: ignore[attr-defined]
        assert token_margin_dd.inner_text().strip() == "-0.00025M"
        assert token_margin_dd.get_attribute("title") == "-250 tokens"

        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(  # type: ignore[attr-defined]
            path=str(SCREENSHOT_DIR / "key-detail-numeric-policy.png"),
            full_page=False,
        )

# ---------------------------------------------------------------------------
# 3) Usage list + detail: M readouts, actual-zero cost preference
# ---------------------------------------------------------------------------


def test_usage_list_and_detail_numeric_display(chromium, num_env) -> None:
    env = num_env
    suffix = env["suffix"]
    with chromium.new_context(base_url=env["base_url"]) as context:  # type: ignore[attr-defined]
        page = context.new_page()
        _login(page, env)
        page.goto("/admin/usage")
        page.wait_for_selector(".table-wrap table[data-sortable] tbody tr")  # type: ignore[attr-defined]

        u0 = _row_by_link(page, f"num-u0-{suffix}")
        assert _visible(u0, 5) == "937.827M total"
        assert u0.locator("td").nth(5).get_attribute("title") == "937,826,734"  # type: ignore[attr-defined]
        # A present actual zero beats the positive estimate.
        assert _visible(u0, 6) == "0 EUR"
        assert "9.99" not in _visible(u0, 6)

        u1 = _row_by_link(page, f"num-u1-{suffix}")
        assert _visible(u1, 6) == "0.01 EUR"  # 9-dp estimate without padding

        u2 = _row_by_link(page, f"num-u2-{suffix}")
        assert _visible(u2, 6) == "n/a EUR"

        # Usage detail: M readouts with exact accessible counts; the
        # actual zero cost is shown in preference to the estimate.
        page.goto(f"/admin/usage/{env['usage_ids']['u0']}")
        page.wait_for_selector("h2:has-text('Accounting')")  # type: ignore[attr-defined]
        total_dd = page.locator("dt:has-text('Total tokens') + dd")  # type: ignore[attr-defined]
        assert total_dd.inner_text().strip() == "937.827M"
        assert total_dd.get_attribute("title") == "937,826,734 tokens"
        # 206-b: cached/reasoning each keep their exact count in the
        # accessible title next to the rounded M values.
        cached_dd = page.locator("dt:has-text('Cached / reasoning') + dd")  # type: ignore[attr-defined]
        assert cached_dd.inner_text().strip() == "937.827M / 1M"
        assert cached_dd.get_attribute("title") == "937,826,734 / 1,000,000"
        cost_dd = page.locator("dt:has-text('Cost EUR') + dd")  # type: ignore[attr-defined]
        assert cost_dd.inner_text().strip() == "0"
        assert "9.99" not in page.content()

        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SCREENSHOT_DIR / "usage-numeric-display.png"))  # type: ignore[attr-defined]
