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
  dashboard, every list page, each UUID detail type, the 224-i routes
  list/detail, the 224-i core form GETs (create/import/edit/discover),
  and the record-choices lookup;
- the demo banner + restricted nav appear (224-i adds Routes);
  unreviewed sections are absent from the nav;
- 224-i: the route detail renders only the 222-fictionalized provider
  base_url / api_key_env_var (the copied values), never the raw SOURCE
  values;
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
    # 224-i: the routes list/detail family.
    "model_routes",
    "pricing_rules",
    "key_templates",
    "fx_rates",
    "email_deliveries",
    # 224-j: the accounting candidate views read quota_reservations
    # (fence/hold facts live on gateway_keys rows, already counted).
    "quota_reservations",
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


async def _provider_by_slug(
    san: _Env, which: str, slug: str, copy_db: str | None = None
) -> tuple[str, str, str] | None:
    """(row_id, base_url, api_key_env_var) for one preserved provider slug.

    The 222 law preserves ``provider_configs.provider`` (P) while
    remapping ``id`` (U) and fictionalizing ``base_url`` /
    ``api_key_env_var`` (F), so the slug is the exact source/copy join.
    """
    src = san.source if which == "source" else san.target
    database = copy_db if which == "copy" else str(san.source["database"])
    assert database is not None
    s = await asyncpg.connect(**_conn_kwargs(
        src["host"], src["port"], src["user"], src["password"], database,
    ))
    try:
        row = await s.fetchrow(
            "SELECT id::text, base_url, api_key_env_var "
            "FROM public.provider_configs WHERE provider = $1 "
            "ORDER BY created_at LIMIT 1",
            slug,
        )
        return (row["id"], row["base_url"], row["api_key_env_var"]) if row else None
    finally:
        await s.close()


async def _copy_route_provider_slug(san: _Env, copy_db: str, route_id: str) -> str:
    """The route's preserved provider slug (222: model_routes.provider = P)."""
    s = await asyncpg.connect(**_conn_kwargs(
        san.target["host"], san.target["port"],
        san.target["user"], san.target["password"], copy_db,
    ))
    try:
        row = await s.fetchrow(
            "SELECT provider FROM public.model_routes WHERE id = $1",
            route_id,
        )
        assert row is not None
        return str(row["provider"])
    finally:
        await s.close()


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
                        # 224-i: the routes list/detail is admitted.
                        assert 'href="/admin/routes"' in r.text
                        # 224-j: the administrator accounts section is in.
                        assert 'href="/admin/accounts"' in r.text
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
                            # 224-i: the routes list.
                            "/admin/routes",
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
                        # 224-i: route detail + fictionalized provider facts.
                        route_id = await _first_id(san_env, target, "model_routes")
                        r = await client.get(f"/admin/routes/{route_id}")
                        _assert_demo_page("route detail", r)
                        slug = await _copy_route_provider_slug(san_env, target, route_id)
                        src = await _provider_by_slug(san_env, "source", slug)
                        cp = await _provider_by_slug(san_env, "copy", slug, target)
                        # both rows exist and the 222 law holds: the row
                        # ID was remapped and the URL/env-name
                        # fictionalized, so source and copy differ.
                        assert src is not None, slug
                        assert cp is not None, slug
                        src_pid, src_url, src_env = src
                        cp_pid, cp_url, cp_env = cp
                        assert src_pid != cp_pid, (src_pid, cp_pid)
                        assert src_url != cp_url, (src_url, cp_url)
                        assert src_env != cp_env, (src_env, cp_env)
                        # the rendered values are the COPIED
                        # (fictionalized) ones, never the raw SOURCE
                        # URL or env-var name.
                        assert cp_url in r.text, (cp_url, r.text[:400])
                        assert cp_env in r.text, (cp_env, r.text[:400])
                        assert src_url not in r.text
                        assert src_env not in r.text
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
                        # 224-i: the twelve fixed core form GETs.
                        for form_path in (
                            "/admin/keys/create",
                            "/admin/keys/bulk-import",
                            "/admin/owners/new",
                            "/admin/institutions/new",
                            "/admin/cohorts/new",
                            "/admin/providers/new",
                            "/admin/routes/new",
                            "/admin/routes/import",
                            "/admin/pricing/new",
                            "/admin/pricing/import",
                            "/admin/fx/new",
                            "/admin/fx/import",
                        ):
                            r = await client.get(form_path)
                            _assert_demo_page(form_path, r)
                        # 224-i: the seven canonical-UUID edit forms.
                        for edit_path in (
                            f"/admin/owners/{owner_id}/edit",
                            f"/admin/institutions/{inst_id}/edit",
                            f"/admin/cohorts/{cohort_id}/edit",
                            f"/admin/providers/{provider_id}/edit",
                            f"/admin/routes/{route_id}/edit",
                            f"/admin/pricing/{pricing_id}/edit",
                            f"/admin/fx/{fx_id}/edit",
                        ):
                            r = await client.get(edit_path)
                            _assert_demo_page(edit_path, r)
                        # 224-i: the provider discover read-only form.
                        r = await client.get(f"/admin/providers/{provider_id}/discover")
                        _assert_demo_page("provider discover", r)
                        for kind in ("institution", "owner"):
                            r = await client.get(f"/admin/record-choices?kind={kind}&q=")
                            assert r.status_code == 200
                            assert r.headers["cache-control"] == "private, no-store"
                            body = r.json()
                            assert isinstance(body, dict)
                            assert body["kind"] == kind
                            assert isinstance(body["choices"], list)
                        # 224-j: the fourteen exact reporting/accounting/
                        # accounts/key-batch read GETs (frozen copied rows).
                        admin_id = await _first_id(san_env, target, "admin_users")
                        for get_path in (
                            "/admin/reports/",
                            "/admin/reports/live-burn",
                            "/admin/reports/export",
                            "/admin/reports/pricing-disable",
                            "/admin/reports/fx-lookup",
                            "/admin/accounting-operations/",
                            "/admin/accounting-operations/expired-reservations",
                            "/admin/accounting-operations/external-tool-fences",
                            "/admin/accounting-operations/external-tool-holds",
                            "/admin/accounting-operations/provider-completed-recovery",
                            "/admin/accounts",
                            "/admin/accounts/create",
                            f"/admin/accounts/reset?admin_id={admin_id}",
                            "/admin/key-batch",
                        ):
                            r = await client.get(get_path)
                            _assert_demo_page(get_path, r)
                        # 224-j: copied (222-anonymized) account identities
                        # ARE shown; SOURCE emails and credential material
                        # (copied dummy hashes) are NOT rendered.
                        src_admin = await _admin_creds(san_env, "source")
                        cp_admin = await _admin_creds(san_env, "copy", target)
                        assert cp_admin, "no copied admin accounts"
                        r = await client.get("/admin/accounts")
                        for email, _name, _phash in cp_admin:
                            assert email in r.text, (email, r.text[:400])
                        for email, _name, _phash in src_admin:
                            assert email not in r.text, email
                        for _email, _name, phash in cp_admin:
                            assert phash not in r.text, "credential hash rendered"
                        # 224-j: report row count matches the copied data
                        # (distinct provider:model groups, page limit 50).
                        r = await client.get("/admin/reports/")
                        m = re.search(
                            r'id="usage-summary-rows-shown">(\d+) groups shown', r.text
                        )
                        assert m is not None, r.text[:400]
                        shown = int(m.group(1))
                        db_groups = await _usage_group_count(san_env, target)
                        assert shown == min(db_groups, 50), (shown, db_groups)
                        # The owned fixture has one group: compare the report's
                        # exact sortable amounts with this session's COPY.
                        assert db_groups == 1
                        db_tokens, db_cost = await _usage_amounts(san_env, target)
                        assert db_tokens == 200 and db_cost > 0
                        assert f'data-sort-value="{db_tokens}" title="{db_tokens}"' in r.text
                        assert f'data-sort-value="{format(db_cost.normalize(), "f")}"' in r.text
                        # 224-j: accounting candidate row count matches the
                        # copied quota rows (view limit 200).
                        r = await client.get(
                            "/admin/accounting-operations/expired-reservations"
                        )
                        shown = r.text.count('name="target_id"')
                        db_expired = await _expired_pending_count(san_env, target)
                        assert shown == min(db_expired, 200), (shown, db_expired)
                        # 224-j: the request-time pages carry the demo-only
                        # current-time hint (normal labels are unchanged).
                        assert "calculated at view time against the snapshot" in r.text
                        r = await client.get("/admin/reports/fx-lookup")
                        assert "resolved at view time against the snapshot" in r.text
                        # 224-k: the ONE exact catalog index path renders
                        # from the real target-only reader against this
                        # session's exact verified copy. The owned
                        # fixture has NO configured catalog source, so
                        # the honest state is the empty-catalog note -
                        # no real catalog artifact is displayed or
                        # claimed (the full configured-file installed
                        # workflow is objective 225).
                        r = await client.get("/admin/operations/catalog/")
                        _assert_demo_page("catalog index", r)
                        cat_text = " ".join(r.text.split())
                        assert "Catalog snapshot index" in cat_text
                        assert "0 captured catalog artifacts" in cat_text
                        assert "This copy has no captured catalog artifacts." in cat_text
                        # No inference about operator storage.
                        assert (
                            "does not establish whether operator catalog "
                            "storage was configured"
                        ) in cat_text
                        # Bounded index + separate file-capture phase +
                        # no seal/apply authority wording.
                        assert "at most 4,096 entries" in cat_text
                        assert "no completeness claim" in cat_text
                        assert "separate, bounded phase" in cat_text
                        assert "no original seal or apply authority" in cat_text
                        # Source-side canaries: the source database, the
                        # custody path and the worker credential never
                        # appear (copy/reader canaries are in
                        # _assert_demo_page).
                        assert str(san_env.source["database"]) not in r.text
                        assert str(custody) not in r.text
                        assert env["worker_pw"] not in r.text
                        # 224-i: the routes list row count equals the
                        # copied model_routes count (within the page limit).
                        r = await client.get("/admin/routes")
                        m = re.search(r'id="routes-rows-shown">([\d]+) rows? shown', r.text)
                        assert m is not None
                        shown = int(m.group(1))
                        db_routes = await _count_table(san_env, target, "model_routes")
                        assert shown == min(db_routes, 50), (shown, db_routes)
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
                        # still-gated families stay 404 behind the same
                        # session (224-i: keys/templates have no edit forms;
                        # route action/download GETs stay denied).
                        for gated in (
                            "/admin/operations",
                            # 224-k near-misses: missing slash and every
                            # deeper catalog GET stay default-denied.
                            "/admin/operations/catalog",
                            "/admin/operations/catalog/proposals",
                            "/admin/operations/catalog/collect",
                            "/admin/operations/catalog/export-baseline",
                            f"/admin/operations/catalog/runs/{uuid.uuid4()}/",
                            f"/admin/operations/catalog/runs/{uuid.uuid4()}/apply-status",
                            f"/admin/operations/catalog/jobs/{'a' * 32}/artifact/x",
                            # 224-j near-misses: missing slash, extra
                            # suffix, export attachment, unknown action.
                            "/admin/reports",
                            "/admin/reports/export.csv",
                            "/admin/reports/usage",
                            "/admin/accounting-operations",
                            "/admin/accounting-operations/expired-reservations/preview",
                            "/admin/accounts/",
                            "/admin/accounts/reset/",
                            "/admin/accounts/revoke",
                            "/admin/key-batch/plan",
                            f"/admin/keys/{key_id}/edit",
                            f"/admin/templates/{template_id}/edit",
                            f"/admin/routes/{route_id}/configuration",
                            f"/admin/routes/{route_id}/codex-profile/profile",
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

                    # --- 224-l: sanitized display-copy artifact download ---
                    # TARGET-SIDE INSERTION (honest label): the test
                    # inserts ONE synthetic leaf into copy A's
                    # worker-published demo_display.leaves through the
                    # owned target-owner connection. This proves REAL
                    # transport/binding through the target-only table,
                    # the restricted reader role and the gate-bound
                    # session - NOT 223 source-file capture or
                    # sanitization (the full configured-file installed
                    # workflow remains objective 225).
                    import hashlib as _art_hashlib

                    _art_job = "c3" * 16
                    _art_name = f"catalog/jobs/{_art_job}.json"
                    _art_body = b'{"demo": "224-l transport leaf"}'
                    _art_sha = _art_hashlib.sha256(_art_body).hexdigest()

                    def _target_conn():
                        return asyncpg.connect(**_conn_kwargs(
                            san_env.target["host"], san_env.target["port"],
                            san_env.target["user"], san_env.target["password"],
                            target_a,
                        ))

                    try:
                        s = await _target_conn()
                        await s.execute(
                            "INSERT INTO demo_display.leaves "
                            "(logical_name, kind, sha256, byte_count, "
                            "captured_at, body) "
                            "VALUES ($1, $2, $3, $4, $5, $6)",
                            _art_name, "job_record", _art_sha,
                            len(_art_body), 1750000000.0, _art_body,
                        )
                        await s.close()
                        # Session A: the byte-accurate sanitized display
                        # copy from its OWN exact copy, forced attachment
                        # with the full privacy header set.
                        r = await client_a.get(
                            "/admin/operations/catalog/artifact",
                            params={"name": _art_name},
                        )
                        assert r.status_code == 200
                        assert r.content == _art_body
                        assert r.headers["content-type"] == "application/octet-stream"
                        assert r.headers["content-disposition"] == (
                            f'attachment; filename="{_art_job}.json"'
                        )
                        assert r.headers["x-content-type-options"] == "nosniff"
                        assert r.headers["content-security-policy"] == (
                            "default-src 'none'"
                        )
                        assert r.headers["cache-control"] == "private, no-store"
                        # Stored digest, copy name, DSN or credential
                        # never appear in the public response.
                        assert _art_sha.encode() not in r.content
                        assert target_a.encode() not in r.content
                        # Session B: the SAME selector against its OWN
                        # exact copy is a fixed safe 404 (copy
                        # isolation; no cross-copy read).
                        r = await client_b.get(
                            "/admin/operations/catalog/artifact",
                            params={"name": _art_name},
                        )
                        assert r.status_code == 404
                        assert r.content == b"Not Found"
                        # Duplicate/unknown query parameters are refused
                        # with the same fixed 404.
                        r = await client_a.get(
                            "/admin/operations/catalog/artifact",
                            params=[("name", _art_name), ("name", _art_name)],
                        )
                        assert r.status_code == 404
                        r = await client_a.get(
                            "/admin/operations/catalog/artifact",
                            params={"name": _art_name, "x": "1"},
                        )
                        assert r.status_code == 404
                        # A traversal/source-like selector is a fixed
                        # 404 with no echo, even while the leaf exists.
                        r = await client_a.get(
                            "/admin/operations/catalog/artifact",
                            params={"name": f"../{target_a}/leaves"},
                        )
                        assert r.status_code == 404
                        assert target_a not in r.text
                        # Integrity corruption in copy A: a wrong stored
                        # SHA is one fixed safe 503, never the body.
                        s = await _target_conn()
                        await s.execute(
                            "UPDATE demo_display.leaves SET sha256 = $2 "
                            "WHERE logical_name = $1",
                            _art_name, "f" * 64,
                        )
                        await s.close()
                        r = await client_a.get(
                            "/admin/operations/catalog/artifact",
                            params={"name": _art_name},
                        )
                        assert r.status_code == 503
                        assert r.headers["cache-control"] == "private, no-store"
                        assert _art_body not in r.content
                        assert "f" * 64 not in r.text
                        # ...and a wrong claimed byte_count (with a
                        # matching actual length) is the SAME cut.
                        s = await _target_conn()
                        await s.execute(
                            "UPDATE demo_display.leaves "
                            "SET sha256 = $2, byte_count = $3 "
                            "WHERE logical_name = $1",
                            _art_name, _art_sha, len(_art_body) + 1,
                        )
                        await s.close()
                        r = await client_a.get(
                            "/admin/operations/catalog/artifact",
                            params={"name": _art_name},
                        )
                        assert r.status_code == 503
                        assert _art_body not in r.content
                        # The exact catalog index path and a deeper
                        # catalog path are the SAME quiet 204 cut.
                        for p in (
                            "/admin/operations/catalog/artifact",
                            f"/admin/operations/catalog/jobs/{_art_job}/artifact/x",
                        ):
                            r = await client_a.post(
                                p,
                                params={"name": _art_name},
                                content=b"x" * 200_000,
                                headers={"content-type": "text/garbage"},
                            )
                            assert r.status_code == 204, p
                            assert r.content == b""
                    finally:
                        # Delete the synthetic leaf; copy A returns to
                        # the exact worker-published state.
                        s = await _target_conn()
                        await s.execute(
                            "DELETE FROM demo_display.leaves "
                            "WHERE logical_name = $1",
                            _art_name,
                        )
                        await s.close()
                        # Cleanup proven: session A 404s again.
                        r = await client_a.get(
                            "/admin/operations/catalog/artifact",
                            params={"name": _art_name},
                        )
                        assert r.status_code == 404

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
                            # 224-j: report export, accounting review,
                            # account create/reset and batch plan stay
                            # silent no-ops, body never parsed.
                            "/admin/reports/export",
                            "/admin/accounting-operations/expired-reservations",
                            "/admin/accounts/create",
                            "/admin/accounts/reset",
                            "/admin/key-batch",
                            # 224-k: the exact catalog index path and a
                            # deeper catalog path are the SAME quiet cut.
                            "/admin/operations/catalog/",
                            "/admin/operations/catalog/proposals",
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


async def _admin_creds(
    san: _Env, which: str, copy_db: str | None = None
) -> list[tuple[str, str, str]]:
    """(email, display_name, password_hash) for the 224-j canaries."""
    t = san.source if which == "source" else san.target
    db = copy_db if which == "copy" else str(t["database"])
    s = await asyncpg.connect(**_conn_kwargs(
        t["host"], t["port"], t["user"], t["password"], db,
    ))
    try:
        rows = await s.fetch(
            "SELECT email, display_name, password_hash FROM public.admin_users"
        )
        return [
            (str(r["email"]), str(r["display_name"]), str(r["password_hash"]))
            for r in rows
        ]
    finally:
        await s.close()


async def _usage_group_count(san: _Env, copy_db: str) -> int:
    """Distinct provider:model groups (the report's grouping law)."""
    s = await asyncpg.connect(**_conn_kwargs(
        san.target["host"], san.target["port"],
        san.target["user"], san.target["password"], copy_db,
    ))
    try:
        row = await s.fetchrow(
            "SELECT count(*)::int AS c FROM (SELECT DISTINCT "
            "(CASE WHEN provider IS NULL THEN 'None' ELSE provider END) || ':' || "
            "COALESCE(resolved_model, requested_model, 'unknown') AS k "
            "FROM public.usage_ledger) g"
        )
        return row["c"]
    finally:
        await s.close()


async def _usage_amounts(san: _Env, copy_db: str):
    """Exact token and EUR cost totals from the selected disposable COPY."""
    s = await asyncpg.connect(**_conn_kwargs(
        san.target["host"], san.target["port"],
        san.target["user"], san.target["password"], copy_db,
    ))
    try:
        row = await s.fetchrow(
            "SELECT COALESCE(sum(total_tokens), 0)::bigint AS tokens, "
            "COALESCE(sum(actual_cost_eur), 0)::numeric AS cost "
            "FROM public.usage_ledger"
        )
        return int(row["tokens"]), row["cost"]
    finally:
        await s.close()


async def _expired_pending_count(san: _Env, copy_db: str) -> int:
    """Copied quota rows the expired-reservations view would list."""
    s = await asyncpg.connect(**_conn_kwargs(
        san.target["host"], san.target["port"],
        san.target["user"], san.target["password"], copy_db,
    ))
    try:
        row = await s.fetchrow(
            "SELECT count(*)::int AS c FROM public.quota_reservations "
            "WHERE status = 'pending' AND expires_at <= now()"
        )
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
            # 224-i: the routes list/detail is in the demo nav.
            assert 'href="/admin/routes"' in content
            assert 'href="/admin/operations"' not in content
            nav_labels = [a.inner_text() for a in page.locator("nav a").all()]
            assert nav_labels == [
                "Dashboard", "Keys", "Owners", "Institutions", "Cohorts",
                "Providers", "Routes", "Pricing", "Templates", "FX", "Usage",
                "Audit", "Email", "Accounts",
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
            # 224-i: the provider create form is admitted (read-only demo).
            assert 'href="/admin/providers/new"' in content
            prov_sel = "table[data-sortable] tbody tr td:nth-child(2) a"
            prov_initial = [a.inner_text() for a in page.locator(prov_sel).all()]
            prov_link = page.locator('th:has-text("Provider") a[href="#ts-sort"]')
            prov_link.wait_for(state="attached")
            prov_link.click()
            page.wait_for_timeout(100)
            prov_asc = [a.inner_text() for a in page.locator(prov_sel).all()]
            assert set(prov_asc) == set(prov_initial)
            assert page.locator('th[aria-sort="ascending"]').count() >= 1

            # --- 224-i: follow the NEW nav link (Routes) -----------------
            page.click('nav a[href="/admin/routes"]')
            page.wait_for_selector("#routes-heading")
            content = page.content()
            assert "Demo preview:" in content
            assert re.search(r"rows? shown", content) is not None
            # ephemeral desktop-layout screenshot of the new Routes list
            # (run-owned /tmp path; never committed, not in app logs).
            shot_routes = Path(
                f"/tmp/slaif-224i-browser-routes-{os.getpid()}-{uuid.uuid4().hex[:10]}.png"
            )
            page.screenshot(path=str(shot_routes))
            print(f"DEMO_BROWSER_ROUTES_SCREENSHOT={shot_routes}")
            # route detail via the first row link
            detail_link = page.locator(
                'table[data-sortable] tbody tr td a[href^="/admin/routes/"]'
            ).first
            if detail_link.count():
                detail_link.click()
                page.wait_for_selector("#route-heading")
                assert "Demo preview:" in page.content()

            # --- 224-j: one report, one accounting page, accounts and
            # key-batch navigation (desktop layout, no-store) -------------
            page.click('nav a[href="/admin/accounts"]')
            page.wait_for_selector("#admin-main")
            content = page.content()
            assert "Demo preview:" in content
            assert 'href="/admin/accounts"' in content
            r = page.goto("/admin/reports/")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            content = page.content()
            assert "Demo preview:" in content
            assert "groups shown" in content
            # ephemeral desktop-layout screenshot of the new report page
            # (run-owned /tmp path; never committed, not in app logs).
            shot_reports = Path(
                f"/tmp/slaif-224j-browser-reports-{os.getpid()}-{uuid.uuid4().hex[:10]}.png"
            )
            page.screenshot(path=str(shot_reports))
            print(f"DEMO_BROWSER_REPORTS_SCREENSHOT={shot_reports}")
            r = page.goto("/admin/accounting-operations/expired-reservations")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            assert "calculated at view time against the snapshot" in page.content()
            r = page.goto("/admin/key-batch")
            assert r is not None and r.status == 200
            assert "Demo preview:" in page.content()

            # --- 224-k: dashboard Catalog snapshot card -> index page --
            page.goto("/admin")
            card = page.locator('a[href="/admin/operations/catalog/"]')
            assert card.count() == 1, "demo dashboard card must appear once"
            card.click()
            page.wait_for_selector("#demo-catalog-heading")
            tracked_cat = [
                (u, st, cc)
                for (u, st, cc) in all_responses
                if u.endswith("/admin/operations/catalog/")
            ]
            assert tracked_cat, "no tracked response for the catalog index"
            assert tracked_cat[-1][1] == 200
            assert tracked_cat[-1][2] == "private, no-store"
            content = page.content()
            assert "Demo preview:" in content
            assert "Catalog snapshot index" in content
            # Desktop-width layout check (default 1280x720 context): the
            # bounded-index note, the empty-state table row and the
            # no-storage-inference note are all visible in one screen.
            assert "0 captured catalog artifacts" in content
            assert "This copy has no captured catalog artifacts." in content
            assert "does not establish whether operator catalog storage was configured" in " ".join(content.split())
            assert "at most 4,096 entries" in content
            assert "separate, bounded phase" in content
            assert "no original seal or apply authority" in content
            # 224-l: the owned browser fixture has NO configured
            # catalog leaf, so the honest empty page renders NO
            # download link at all (the positive link is proven by the
            # mocked-ASGI follow test; the configured-file installed
            # workflow is objective 225).
            assert 'href="/admin/operations/catalog/artifact' not in content
            # ...and the exact artifact path is a fixed safe 404 for
            # any selector in the real browser.
            r = page.goto(
                "/admin/operations/catalog/artifact"
                "?name=catalog/jobs/" + "c3" * 16 + ".json"
            )
            assert r is not None and r.status == 404
            assert r.headers["cache-control"] == "private, no-store"
            assert target not in content
            assert 'href="/admin/operations"' not in content  # still no nav item
            # ephemeral desktop-layout screenshot (run-owned /tmp path;
            # never committed, not in app logs).
            shot_cat = Path(
                f"/tmp/slaif-224k-browser-catalog-{os.getpid()}-{uuid.uuid4().hex[:10]}.png"
            )
            page.screenshot(path=str(shot_cat))
            print(f"DEMO_BROWSER_CATALOG_SCREENSHOT={shot_cat}")

            # --- 224-i: an admitted form renders; the operational submit
            # is a quiet 204 no-op that changes nothing -------------------
            page.goto("/admin/cohorts")
            rows_before = page.locator("table[data-sortable] tbody tr").count()
            page.goto("/admin/cohorts/new")
            assert "Demo preview:" in page.content()
            page.fill('input[name="name"]', "224i-browser-probe")
            page.fill('textarea[name="reason"]', "224-i no-op probe")
            page.click('button[type="submit"]:has-text("Create cohort")')
            page.wait_for_timeout(300)
            posted = [
                (u, st)
                for (u, st, _cc) in all_responses
                if u.endswith("/admin/cohorts/new") and st == 204
            ]
            assert posted, "no 204 no-op recorded for the demo form POST"
            page.goto("/admin/cohorts")
            rows_after = page.locator("table[data-sortable] tbody tr").count()
            assert rows_after == rows_before

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
