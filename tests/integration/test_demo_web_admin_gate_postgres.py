"""Real owned-PostgreSQL-16 evidence for the 224-e demo-admin core read gate.

Runs on the same owned fixture pair as the 224-c web evidence
(``webenv``: one fake-admin account with known credentials, run-tagged
web/worker roles, run-owned reader role on the target). Two concurrent
logins yield two DISTINCT 224-a requests; each is processed by the real
224-b worker CLI (real worker role, real 221/222/23 chain). A marker row
inserted into the SOURCE between the two copies then proves the two
sessions read DISTINCT copies (and no per-visitor app-global factory
leakage): 222 fictionalizes institution names, so the marker row exists in
copy B only under a rewritten name - copy B holds exactly one more
institution (proven directly in the copy DBs and as one extra rendered
list row), and the raw marker string never appears in either page.

Proves, behind the real reader role (SELECT-only, database-side
read-only transactions):

- EVERY admitted GET family renders 200 from the session's copy:
  dashboard, all four list pages, each UUID detail type, and the
  record-choices lookup;
- the demo banner + five-section nav appear; unreviewed sections are
  absent from the nav;
- every operational POST family (key create/revoke/rotate,
  owner/institution/cohort create/edit) and an unknown path are quiet
  204 no-ops with the body never parsed, and leave BOTH copies and the
  source unchanged (gateway_keys, institutions, audit_log counts);
- source tables/counts are unchanged by the whole read phase;
- demo sign-out (CSRF-verified through the gate) revokes the session,
  after which admitted pages bounce to the demo entry;
- no copy DB name, DSN fragment or credential ever appears in page
  output;
- a second real-Chromium smoke (loopback uvicorn) proves packaged CSS/JS
  loading, demo banner/nav, table sorting, the 224-f no-store guard and
  CSRF sign-out on a real verified copy, saving one screenshot to a
  run-owned /tmp path.

No provider HTTP, no email, no normal admin auth. Synthetic data only.
"""

from __future__ import annotations

import asyncio
import os
import re
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import asyncpg
import pytest
import uvicorn
from httpx import ASGITransport, AsyncClient

from slaif_gateway.api.demo_admin_gate import _demo_csrf_token
from slaif_gateway.demo_web import PgDemoWebFacade, create_demo_app
from tests.integration.test_demo_snapshot_sanitize_postgres import _Env
from tests.integration.test_demo_web_postgres import (
    _parse_pending,
    _request_row,
    _run_worker_cli,
    _web_config,
    _worker_cli_env,
)

# Fixture registration by name (webenv -> _wenv_base -> san_env/custody):
# no fixture-name imports (F811 avoidance), same pattern as 224-c.
pytest_plugins = ("tests.integration.test_demo_web_postgres",)

# Read-phase invariance set (copied public tables).
_COUNT_TABLES = (
    "gateway_keys",
    "owners",
    "institutions",
    "cohorts",
    "admin_users",
    "audit_log",
    "usage_ledger",
    # 224-f: the seven newly admitted database-backed families.
    "provider_configs",
    "pricing_rules",
    "key_templates",
    "fx_rates",
    "email_deliveries",
)


def _conn_kwargs(host: str, port: int, user: str, password: str, database: str) -> dict[str, Any]:
    return {
        "host": str(host),
        "port": int(port),
        "user": str(user),
        "password": str(password),
        "database": str(database),
    }


def _table_counts(url_parts: dict[str, Any], database: str) -> dict[str, int]:
    async def run() -> dict[str, int]:
        s = await asyncpg.connect(**_conn_kwargs(
            url_parts["host"], url_parts["port"],
            url_parts["user"], url_parts["password"], database,
        ))
        try:
            out: dict[str, int] = {}
            for table in _COUNT_TABLES:
                out[table] = (await s.fetchrow(f"SELECT count(*)::int AS c FROM public.{table}"))["c"]
            return out
        finally:
            await s.close()

    return asyncio.run(run())


def _source_counts(san: _Env) -> dict[str, int]:
    src = san.source
    return _table_counts(
        {
            "host": src["host"],
            "port": src["port"],
            "user": src["user"],
            "password": src["password"],
        },
        str(src["database"]),
    )


def _copy_counts(san: _Env, copy_db: str) -> dict[str, int]:
    tgt = san.target
    return _table_counts(
        {
            "host": tgt["host"],
            "port": tgt["port"],
            "user": tgt["user"],
            "password": tgt["password"],
        },
        copy_db,
    )


def _rows_shown(html: str) -> int:
    """Institution rows rendered by the list page (rows-shown counter)."""
    m = re.search(r'id="institutions-rows-shown">(\d+) rows? shown', html)
    assert m is not None
    return int(m.group(1))


async def _first_id(san: _Env, copy_db: str, table: str) -> str:
    s = await asyncpg.connect(**_conn_kwargs(
        san.target["host"], san.target["port"],
        san.target["user"], san.target["password"], copy_db,
    ))
    try:
        row = await s.fetchrow(f"SELECT id::text AS id FROM public.{table} ORDER BY created_at LIMIT 1")
        assert row is not None
        return row["id"]
    finally:
        await s.close()


async def _login_phase(cfg, env: dict[str, Any]) -> tuple[uuid.UUID, str]:
    """HTTP login as the known account; return (request_id, pending cookie)."""
    facade = PgDemoWebFacade(cfg)
    try:
        app = create_demo_app(cfg, facade=facade)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://demo.test"
        ) as client:
            r = await client.get("/fakeadmin/login")
            csrf = r.cookies["slaif_demo_csrf"]
            r = await client.post(
                "/fakeadmin/login",
                data={"username": env["username"], "password": env["password"], "csrf": csrf},
            )
            assert r.status_code == 303, r.text
            pending = r.cookies["slaif_demo_pending"]
            return _parse_pending(cfg.cookie_secret, pending), pending
    finally:
        await facade.close()


async def _wait_phase(cfg, pending_cookie: str) -> str:
    """Wait surface: issue the session; return the raw session token."""
    facade = PgDemoWebFacade(cfg)
    try:
        app = create_demo_app(cfg, facade=facade)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://demo.test"
        ) as client:
            client.cookies.set(
                "slaif_demo_pending", pending_cookie,
                domain="demo.test", path="/fakeadmin",
            )
            r = await client.get("/fakeadmin/wait")
            assert r.status_code == 303, r.text
            assert r.headers["location"] == "/fakeadmin/ready"
            token = client.cookies.get("slaif_demo_session")
            assert token
            return token
    finally:
        await facade.close()


def test_e2e_admin_gate_two_sessions_distinct_copies(
    san_env: _Env, webenv: dict[str, Any], custody: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    env = webenv
    cfg = _web_config(env, san_env)

    # Phase 1: TWO concurrent logins -> two DISTINCT requests (224-a law).
    rid_a, pending_a = asyncio.run(_login_phase(cfg, env))
    rid_b, pending_b = asyncio.run(_login_phase(cfg, env))
    assert rid_a != rid_b

    # Phase 2: worker processes copy A (real worker role, real chain).
    cli_env = _worker_cli_env(san_env, env, custody)
    out_a = _run_worker_cli(["process-request", str(rid_a), "--json"], cli_env, monkeypatch)
    assert "verified_unpublished" in out_a
    row_a = _request_row(env, rid_a)
    target_a = row_a["worker_target_db"]
    assert isinstance(target_a, str) and target_a.startswith("demo_snap_")

    # Phase 3: a marker row in the SOURCE now: copy A predates it, copy B
    # will include it - the distinct-copy proof.
    marker = f"demo224e-marker-{uuid.uuid4().hex[:10]}"

    def _insert_marker() -> None:
        async def run() -> None:
            s = await asyncpg.connect(**_conn_kwargs(
                san_env.source["host"], san_env.source["port"],
                san_env.source["user"], san_env.source["password"],
                str(san_env.source["database"]),
            ))
            try:
                now = "now()"
                await s.execute(
                    "INSERT INTO public.institutions "
                    "(id, name, created_at, updated_at) "
                    "VALUES ($1, $2, " + now + ", " + now + ")",
                    str(uuid.uuid4()),
                    marker,
                )
            finally:
                await s.close()

        asyncio.run(run())

    def _remove_marker() -> None:
        async def run() -> None:
            s = await asyncpg.connect(**_conn_kwargs(
                san_env.source["host"], san_env.source["port"],
                san_env.source["user"], san_env.source["password"],
                str(san_env.source["database"]),
            ))
            try:
                await s.execute(
                    "DELETE FROM public.institutions WHERE name = $1", marker
                )
            finally:
                await s.close()

        asyncio.run(run())

    _insert_marker()
    # Exact run-owned teardown on ANY later failure: this test's marker
    # row is the only source mutation and is removed after the invariance
    # checks (finalizers run after the test body completes).
    request.addfinalizer(_remove_marker)

    # Phase 4: worker processes copy B (includes the marker).
    out_b = _run_worker_cli(["process-request", str(rid_b), "--json"], cli_env, monkeypatch)
    assert "verified_unpublished" in out_b
    row_b = _request_row(env, rid_b)
    target_b = row_b["worker_target_db"]
    assert target_b and target_b != target_a

    # Phase 5: wait surfaces issue one session each.
    token_a = asyncio.run(_wait_phase(cfg, pending_a))
    token_b = asyncio.run(_wait_phase(cfg, pending_b))

    # Phase 6: invariance baselines (before any admin read): source AND
    # both copies.
    src_before = _source_counts(san_env)
    copy_before = {
        target_a: _copy_counts(san_env, target_a),
        target_b: _copy_counts(san_env, target_b),
    }
    # DB-level distinct-copy proof: the marker row entered the source after
    # worker A's dump and before worker B's, so only copy B holds it - under
    # a 222-fictionalized institution name, never the raw marker string.
    assert copy_before[target_b]["institutions"] == (
        copy_before[target_a]["institutions"] + 1
    ), copy_before

    async def admin_phase() -> None:
        facade = PgDemoWebFacade(cfg)
        try:
            app = create_demo_app(cfg, facade=facade)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="https://demo.test"
            ) as client_a:
                client_a.cookies.set(
                    "slaif_demo_session", token_a, domain="demo.test", path="/"
                )
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="https://demo.test"
                ) as client_b:
                    client_b.cookies.set(
                        "slaif_demo_session", token_b, domain="demo.test", path="/"
                    )

                    def _assert_demo_page(name: str, r) -> None:
                        assert r.status_code == 200, (name, r.status_code)
                        # 224-f: every admitted dynamic response is no-store.
                        assert r.headers["cache-control"] == "private, no-store"
                        assert "Demo preview:" in r.text
                        assert "Read-only" in r.text
                        # restricted nav: admitted sections only
                        # (224-f: the seven new families are in; the
                        # still-gated families are out).
                        assert 'href="/admin/keys"' in r.text
                        assert 'href="/admin/providers"' in r.text
                        assert 'href="/admin/usage"' in r.text
                        assert 'href="/admin/routes"' not in r.text
                        assert 'href="/admin/operations"' not in r.text
                        assert 'href="/admin/openai-assisted"' not in r.text
                        # canaries: no copy name, DSN fragment or credential.
                        assert target_a not in r.text
                        assert target_b not in r.text
                        assert str(env["reader_role"]) not in r.text

                    # --- EVERY admitted GET family (both sessions) --------
                    for client, target in ((client_a, target_a), (client_b, target_b)):
                        key_id = await _first_id(san_env, target, "gateway_keys")
                        owner_id = await _first_id(san_env, target, "owners")
                        inst_id = await _first_id(san_env, target, "institutions")
                        cohort_id = await _first_id(san_env, target, "cohorts")
                        provider_id = await _first_id(san_env, target, "provider_configs")
                        pricing_id = await _first_id(san_env, target, "pricing_rules")
                        template_id = await _first_id(san_env, target, "key_templates")
                        fx_id = await _first_id(san_env, target, "fx_rates")
                        usage_id = await _first_id(san_env, target, "usage_ledger")
                        audit_id = await _first_id(san_env, target, "audit_log")
                        email_id = await _first_id(san_env, target, "email_deliveries")
                        r = await client.get("/admin")
                        _assert_demo_page("dashboard", r)
                        for list_path in (
                            "/admin/keys",
                            "/admin/owners",
                            "/admin/institutions",
                            "/admin/cohorts",
                            # 224-f: the seven new database-backed families.
                            "/admin/providers",
                            "/admin/pricing",
                            "/admin/templates",
                            "/admin/fx",
                            "/admin/usage",
                            "/admin/audit",
                            "/admin/email-deliveries",
                        ):
                            r = await client.get(list_path)
                            _assert_demo_page(list_path, r)
                        # every UUID detail family (closed one-segment law)
                        r = await client.get(f"/admin/keys/{key_id}")
                        _assert_demo_page("key detail", r)
                        r = await client.get(f"/admin/owners/{owner_id}")
                        _assert_demo_page("owner detail", r)
                        r = await client.get(f"/admin/institutions/{inst_id}")
                        _assert_demo_page("institution detail", r)
                        r = await client.get(f"/admin/cohorts/{cohort_id}")
                        _assert_demo_page("cohort detail", r)
                        r = await client.get(f"/admin/providers/{provider_id}")
                        _assert_demo_page("provider detail", r)
                        r = await client.get(f"/admin/pricing/{pricing_id}")
                        _assert_demo_page("pricing detail", r)
                        r = await client.get(f"/admin/templates/{template_id}")
                        _assert_demo_page("template detail", r)
                        r = await client.get(f"/admin/fx/{fx_id}")
                        _assert_demo_page("fx detail", r)
                        r = await client.get(f"/admin/usage/{usage_id}")
                        _assert_demo_page("usage detail", r)
                        r = await client.get(f"/admin/audit/{audit_id}")
                        _assert_demo_page("audit detail", r)
                        r = await client.get(f"/admin/email-deliveries/{email_id}")
                        _assert_demo_page("email delivery detail", r)
                        for kind in ("institution", "owner"):
                            r = await client.get(f"/admin/record-choices?kind={kind}&q=")
                            assert r.status_code == 200
                            assert r.headers["cache-control"] == "private, no-store"
                            body = r.json()
                            assert isinstance(body, dict)
                            assert body["kind"] == kind
                            assert isinstance(body["choices"], list)
                        # 224-f: real usage quantities survive the copy -
                        # the rendered row count equals the copied table's
                        # count (within the page limit), and the label is
                        # grammatically singular/plural.
                        r = await client.get("/admin/usage")
                        m = re.search(r'id="usage-rows-shown">([\d]+) rows? shown', r.text)
                        assert m is not None
                        shown = int(m.group(1))
                        db_usage = await _count_table(san_env, target, "usage_ledger")
                        assert shown == min(db_usage, 50), (shown, db_usage)
                        assert re.search(r">1 row shown<", r.text) is not None or shown != 1
                        # still-gated families stay 404 behind the same session
                        for gated in (
                            "/admin/routes",
                            "/admin/operations",
                            "/admin/reports",
                            f"/admin/providers/{provider_id}/edit",
                            f"/admin/usage/{usage_id}/export.csv",
                        ):
                            assert (await client.get(gated)).status_code == 404, gated

                    # --- distinct copies: B renders exactly one more -----
                    # institution row than A (the 222-fictionalized marker).
                    r_a = await client_a.get("/admin/institutions")
                    r_b = await client_b.get("/admin/institutions")
                    shown_a = _rows_shown(r_a.text)
                    shown_b = _rows_shown(r_b.text)
                    assert shown_b == shown_a + 1, (shown_a, shown_b)
                    # privacy canary: the raw source marker name is
                    # fictionalized by 222 and must not leak into either
                    # rendered page.
                    assert marker not in r_a.text
                    assert marker not in r_b.text

                    # --- operational POST families: quiet 204 no-ops -----
                    key_id = await _first_id(san_env, target_b, "gateway_keys")
                    for client in (client_a, client_b):
                        for p in (
                            "/admin/keys/create",
                            f"/admin/keys/{key_id}/revoke",
                            f"/admin/keys/{key_id}/rotate",
                            "/admin/owners/new",
                            "/admin/institutions/new",
                            "/admin/cohorts/new",
                            "/admin/definitely-not-a-route",
                        ):
                            r = await client.post(
                                p,
                                content=b"x" * 200_000,
                                headers={"content-type": "text/garbage"},
                            )
                            assert r.status_code == 204, p
                            assert r.content == b""

                    # --- CSRF-verified demo sign-out (session A) ---------
                    csrf_a = _demo_csrf_token(cfg.cookie_secret, token_a)
                    r = await client_a.post(
                        "/admin/logout", data={"csrf_token": csrf_a}
                    )
                    assert r.status_code == 303
                    assert r.headers["location"] == "/fakeadmin/login"
                    assert client_a.cookies.get("slaif_demo_session") is None
                    # the revoked session can no longer reach the copy.
                    r = await client_a.get("/admin/keys")
                    assert r.status_code == 303
                    # a WRONG csrf is refused without revoking session B.
                    r = await client_b.post("/admin/logout", data={"csrf_token": "wrong" * 10})
                    assert r.status_code == 400
                    r = await client_b.get("/admin/keys")
                    assert r.status_code == 200
        finally:
            await facade.close()

    asyncio.run(admin_phase())

    # Phase 7: exact invariance - source and BOTH copies unchanged by the
    # whole read/POST/logout phase (marker still exactly once in source).
    src_after = _source_counts(san_env)
    assert src_after == src_before, (src_before, src_after)
    for target in (target_a, target_b):
        copy_after = _copy_counts(san_env, target)
        assert copy_after == copy_before[target], (
            target, copy_before[target], copy_after
        )

    def _marker_count() -> int:
        async def run() -> int:
            s = await asyncpg.connect(**_conn_kwargs(
                san_env.source["host"], san_env.source["port"],
                san_env.source["user"], san_env.source["password"],
                str(san_env.source["database"]),
            ))
            try:
                row = await s.fetchrow(
                    "SELECT count(*)::int AS c FROM public.institutions "
                    "WHERE name = $1",
                    marker,
                )
                return row["c"]
            finally:
                await s.close()

        return asyncio.run(run())

    assert _marker_count() == 1


# ---------------------------------------------------------------------------
# 224-e browser smoke: real Chromium against a real verified copy over
# loopback uvicorn. Packaged CSS/JS, demo banner/nav, table sorting and
# CSRF-verified sign-out. Synthetic data only; the screenshot goes to a
# run-owned /tmp path, is never committed and never enters normal logs.
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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


async def _count_table(san: _Env, copy_db: str, table: str) -> int:
    s = await asyncpg.connect(**_conn_kwargs(
        san.target["host"], san.target["port"],
        san.target["user"], san.target["password"], copy_db,
    ))
    try:
        row = await s.fetchrow(f"SELECT count(*)::int AS c FROM public.{table}")
        return row["c"]
    finally:
        await s.close()


async def _inst_names(san: _Env, copy_db: str) -> list[str]:
    s = await asyncpg.connect(**_conn_kwargs(
        san.target["host"], san.target["port"],
        san.target["user"], san.target["password"], copy_db,
    ))
    try:
        rows = await s.fetch("SELECT name FROM public.institutions")
        return [str(r["name"]) for r in rows]
    finally:
        await s.close()


@pytest.mark.playwright
def test_browser_smoke_demo_copy_pages(
    san_env: _Env, webenv: dict[str, Any], custody: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pw = pytest.importorskip("playwright.sync_api")

    env = webenv
    cfg = _web_config(env, san_env)

    # One login -> one real worker-processed copy -> one demo session.
    rid, pending = asyncio.run(_login_phase(cfg, env))
    cli_env = _worker_cli_env(san_env, env, custody)
    out = _run_worker_cli(["process-request", str(rid), "--json"], cli_env, monkeypatch)
    assert "verified_unpublished" in out
    target = _request_row(env, rid)["worker_target_db"]
    assert isinstance(target, str) and target.startswith("demo_snap_")
    token = asyncio.run(_wait_phase(cfg, pending))
    names = asyncio.run(_inst_names(san_env, target))

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    facade = PgDemoWebFacade(cfg)
    app = create_demo_app(cfg, facade=facade)

    with _run_uvicorn_server(app, port), pw.sync_playwright() as manager:
        browser = manager.chromium.launch()
        try:
            context = browser.new_context(base_url=base_url)
            page = context.new_page()
            context.add_cookies([
                {"name": "slaif_demo_session", "value": token, "url": f"{base_url}/"},
            ])

            all_responses: list[tuple[str, int, str | None]] = []

            def _track(response: object) -> None:
                all_responses.append(
                    (
                        str(getattr(response, "url", "")),
                        int(response.status),  # type: ignore[attr-defined]
                        response.headers.get(  # type: ignore[attr-defined]
                            "cache-control"
                        ),
                    )
                )

            page.on("response", _track)

            def _static() -> list[tuple[str, int]]:
                return [(u, st) for u, st, _ in all_responses if "/admin/static/" in u]

            # --- /admin/keys: banner, restricted nav, packaged CSS/JS ----
            response = page.goto("/admin/keys")
            assert response is not None and response.status == 200
            content = page.content()
            assert "Demo preview:" in content
            assert 'href="/admin/keys"' in content
            assert 'href="/admin/providers"' in content
            assert 'href="/admin/usage"' in content
            assert 'href="/admin/routes"' not in content
            assert 'href="/admin/operations"' not in content
            nav_labels = [a.inner_text() for a in page.locator("nav a").all()]
            assert nav_labels == [
                "Dashboard", "Keys", "Owners", "Institutions", "Cohorts",
                "Providers", "Pricing", "Templates", "FX", "Usage",
                "Audit", "Email",
            ]
            # asset_url appends ?v=<digest>: judge by URL path, not suffix.
            static_by_path = {urlparse(u).path: st for u, st in _static()}
            assert any(pth.endswith(".css") and st == 200 for pth, st in static_by_path.items())
            assert any(pth.endswith(".js") and st == 200 for pth, st in static_by_path.items())
            assert all(st < 400 for st in static_by_path.values())
            # canaries: no copy DB name, reader role or credential material.
            assert target not in content
            assert str(env["reader_role"]) not in content

            shot = Path(f"/tmp/slaif-224e-browser-{os.getpid()}-{uuid.uuid4().hex[:10]}.png")
            page.screenshot(path=str(shot))
            print(f"DEMO_BROWSER_SCREENSHOT={shot}")

            # --- /admin/institutions: packaged table-sort JS --------------
            page.goto("/admin/institutions")
            page.wait_for_selector("table[data-sortable]")
            row_sel = "table[data-sortable] tbody tr td:nth-child(2) a"
            initial = [a.inner_text() for a in page.locator(row_sel).all()]
            assert set(initial) == set(names)
            sort_link = page.locator('th:has-text("Institution") a[href="#ts-sort"]')
            sort_link.wait_for(state="attached")
            sort_link.click()
            page.wait_for_timeout(100)
            asc = [a.inner_text() for a in page.locator(row_sel).all()]
            assert set(asc) == set(initial)
            assert page.locator('th[aria-sort="ascending"]').count() >= 1
            sort_link.click()
            page.wait_for_timeout(100)
            desc = [a.inner_text() for a in page.locator(row_sel).all()]
            assert set(desc) == set(initial)
            assert page.locator('th[aria-sort="descending"]').count() >= 1
            if len(set(names)) >= 2:
                assert asc != desc

            # --- 224-f: one new DB-backed section (providers) -----------
            r = page.goto("/admin/providers")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            content = page.content()
            assert "Demo preview:" in content
            # the still-gated create form link is hidden in demo mode
            assert 'href="/admin/providers/new"' not in content
            prov_sel = "table[data-sortable] tbody tr td:nth-child(2) a"
            prov_initial = [a.inner_text() for a in page.locator(prov_sel).all()]
            prov_link = page.locator('th:has-text("Provider") a[href="#ts-sort"]')
            prov_link.wait_for(state="attached")
            prov_link.click()
            page.wait_for_timeout(100)
            prov_asc = [a.inner_text() for a in page.locator(prov_sel).all()]
            assert set(prov_asc) == set(prov_initial)
            assert page.locator('th[aria-sort="ascending"]').count() >= 1

            # --- CSRF-verified sign-out back to the demo entry ------------
            page.click("button.signout")
            page.wait_for_url("**/fakeadmin/login")
            cookie_names = {c["name"] for c in context.cookies()}
            assert "slaif_demo_session" not in cookie_names

            # --- 224-f: after sign-out a fresh reload of the same dynamic
            # page re-checks authorization (the no-store chain means a
            # normally-cached snapshot is not served). History/BFCache
            # erasure is NOT claimed.
            page.goto("/admin/providers")
            page.wait_for_url("**/fakeadmin/login")
            bounced = [
                (u, st, cc)
                for (u, st, cc) in all_responses
                if "/admin/providers" in u and st in (303, 404, 503)
            ]
            assert bounced, "no reauthorization response after sign-out"
            assert all(cc == "private, no-store" for _, _, cc in bounced)
            assert "Demo preview:" not in page.content()
        finally:
            browser.close()
