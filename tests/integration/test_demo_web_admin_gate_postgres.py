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
import json
import os
import re
import shutil
import socket
import tempfile
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
from tests.integration.test_demo_snapshot_sanitize_postgres import (
    PROVIDER,
    _Env,
    _FLOW_AFFECTED_TABLES,
    _flow_delete_ids,
    _flow_table_ids,
)
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
    # 224-t: copy A's worker captures a CUSTOM non-default
    # process-configuration projection (canaries, not secrets): the
    # per-login page must show these captured values, and copy B (built
    # WITHOUT them) must show the built-in defaults - copy isolation
    # for the worker-observed projection.
    _T_CANARY_ENV = {
        "CHAT_MAX_IMAGES_PER_REQUEST": "7",
        "DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE": "99",
    }
    # 224-u: the two workers each capture a DISTINCT configured source
    # branding (canary tokens, not secrets): after sanitization BOTH
    # copies must show the SAME packaged neutral bytes, no source
    # token may ever appear, and each session must read only its own
    # copy (cross-read proven by corrupting copy A's leaf).
    _U_BRAND_A = Path(tempfile.mkdtemp(prefix="slaif224u-a-"))
    _U_BRAND_B = Path(tempfile.mkdtemp(prefix="slaif224u-b-"))
    _U_TOK_A = "demo224u-token-" + uuid.uuid4().hex[:12]
    _U_TOK_B = "demo224u-token-" + uuid.uuid4().hex[:12]
    for _dir, _tok in ((_U_BRAND_A, _U_TOK_A), (_U_BRAND_B, _U_TOK_B)):
        (_dir / "style.css").write_bytes(
            f"/* {_tok} */\nbody {{ color: rgb(1, 1, 1); }}".encode()
        )
        (_dir / "logo.svg").write_bytes(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="8" '
            f'height="8" data-token="{_tok}">'
            f'<rect width="8" height="8" fill="#ff0000"/></svg>'.encode()
        )
        _dir.chmod(0o700)
    request.addfinalizer(
        lambda: shutil.rmtree(_U_BRAND_A, ignore_errors=True)
    )
    request.addfinalizer(
        lambda: shutil.rmtree(_U_BRAND_B, ignore_errors=True)
    )
    cli_env_a = {
        **cli_env,
        **_T_CANARY_ENV,
        "SLAIF_BRANDING_DIR": str(_U_BRAND_A),
    }
    out_a = _run_worker_cli(
        ["process-request", str(rid_a), "--json"], cli_env_a, monkeypatch
    )
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
    # 224-t: the canary env vars were set for worker A's call only;
    # remove them from the ambient environment so worker B captures
    # the BUILT-IN defaults (copy isolation for the projection).
    for _k in _T_CANARY_ENV:
        monkeypatch.delenv(_k, raising=False)
    # 224-u: worker B captures its OWN distinct source branding.
    cli_env_b = {**cli_env, "SLAIF_BRANDING_DIR": str(_U_BRAND_B)}
    out_b = _run_worker_cli(
        ["process-request", str(rid_b), "--json"], cli_env_b, monkeypatch
    )
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
                            # 224-n: the exact /proposals GET is now
                            # ADMITTED (proven just below); its
                            # near-misses stay denied.
                            "/admin/operations/catalog/proposals/extra",
                            # 224-o: the exact /collect GET is now
                            # ADMITTED (proven just below); its
                            # subpaths stay denied.
                            "/admin/operations/catalog/collect/submit",
                            # 224-p: the exact /review,
                            # /export-baseline and /jobs/ GETs are now
                            # ADMITTED (proven just below); their
                            # near-misses stay denied.
                            "/admin/operations/catalog/review/submit",
                            "/admin/operations/catalog/export-baseline/submit",
                            "/admin/operations/catalog/jobs",  # no slash
                            "/admin/operations/catalog/jobs/extra",
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
                            # 224-q: the exact /calibration, /clone and
                            # /clone/receipts GETs are now ADMITTED
                            # (proven just below); near-misses and the
                            # POST/JSON subpaths stay denied.
                            f"/admin/keys/{key_id}/clones",
                            f"/admin/keys/{key_id}/calibrations",
                            f"/admin/keys/{key_id}/calibration/",
                            f"/admin/keys/{key_id}/calibration/preview",
                            f"/admin/keys/{key_id}/calibration/summary.json",
                            f"/admin/keys/{key_id}/calibration/create-template",
                            f"/admin/keys/{key_id}/configuration.json",
                            f"/admin/keys/{key_id}/clone/",
                            f"/admin/keys/{key_id}/clone/review",
                            f"/admin/keys/{key_id}/clone/apply",
                            f"/admin/keys/{key_id}/clone/receipts/",
                            f"/admin/keys/{key_id}/clone/receipts/extra",
                            f"/admin/templates/{template_id}/edit",
                            f"/admin/routes/{route_id}/configuration",
                            f"/admin/routes/{route_id}/codex-profile/profile",
                            f"/admin/usage/{usage_id}/export.csv",
                        ):
                            assert (await client.get(gated)).status_code == 404, gated

                    # 224-n: the admitted captured-proposals page renders
                    # for this verified session; the worker-published
                    # fixture carries NO configured catalog leaves, so
                    # this is the honest empty artifact-group state
                    # (before the 224-n test-only insertion further
                    # down).
                    r = await client.get("/admin/operations/catalog/proposals")
                    assert r.status_code == 200
                    assert r.headers["cache-control"] == "private, no-store"
                    assert (
                        "No captured proposal artifact groups in this snapshot"
                        in " ".join(r.text.split())
                    )

                    # 224-o: the admitted collect page renders for this
                    # verified session; the worker-published fixture
                    # carries NO configured catalog leaves, so this is
                    # the honest empty complete-run state (before the
                    # 224-o test-only insertion further down).
                    r = await client.get("/admin/operations/catalog/collect")
                    assert r.status_code == 200
                    assert r.headers["cache-control"] == "private, no-store"
                    assert (
                        "No captured complete runs in this snapshot"
                        in " ".join(r.text.split())
                    )

                    # 224-p: the admitted review/export/jobs pages
                    # render for this verified session; the
                    # worker-published fixture carries NO configured
                    # catalog leaves, so the jobs page is the honest
                    # empty state (before the 224-p test-only
                    # insertion further down).
                    for _pp_page in (
                        "/admin/operations/catalog/review",
                        "/admin/operations/catalog/export-baseline",
                    ):
                        r = await client.get(_pp_page)
                        assert r.status_code == 200, _pp_page
                        assert r.headers["cache-control"] == "private, no-store"
                        assert (
                            "ILLUSTRATIVE demo-only form"
                            in " ".join(r.text.split())
                        ), _pp_page
                    r = await client.get("/admin/operations/catalog/jobs/")
                    assert r.status_code == 200
                    assert r.headers["cache-control"] == "private, no-store"
                    assert (
                        "No captured job records in this snapshot"
                        in " ".join(r.text.split())
                    )

                    # 224-q: the three admitted key read GETs for this
                    # fixture's copied key. The clone form and the
                    # receipts page render for ANY existing copied key;
                    # the calibration page is purpose-gated and shows
                    # the existing safe 400 refusal for non-trusted
                    # copied keys (a safe refusal, never a false
                    # success).
                    async def _q_base_purpose(copy_db: str) -> str:
                        s = await asyncpg.connect(**_conn_kwargs(
                            san_env.target["host"], san_env.target["port"],
                            san_env.target["user"], san_env.target["password"],
                            copy_db,
                        ))
                        try:
                            return (await s.fetchrow(
                                "SELECT key_purpose FROM gateway_keys "
                                "WHERE id = $1",
                                key_id,
                            ))["key_purpose"]
                        finally:
                            await s.close()

                    base_purpose = await _q_base_purpose(target)
                    r = await client.get(f"/admin/keys/{key_id}/clone")
                    assert r.status_code == 200
                    assert r.headers["cache-control"] == "private, no-store"
                    assert (
                        "Sanitized demo snapshot display"
                        in " ".join(r.text.split())
                    )
                    r = await client.get(f"/admin/keys/{key_id}/clone/receipts")
                    assert r.status_code == 200
                    assert r.headers["cache-control"] == "private, no-store"
                    assert (
                        "Sanitized demo snapshot display"
                        in " ".join(r.text.split())
                    )
                    r = await client.get(f"/admin/keys/{key_id}/calibration")
                    if base_purpose == "trusted_calibration":
                        assert r.status_code == 200
                        assert (
                            "Sanitized demo snapshot display"
                            in " ".join(r.text.split())
                        )
                    else:
                        assert r.status_code == 400
                        assert "trusted calibration keys" in r.text
                    # The query law through the REAL gate: unexpected
                    # queries are fixed 404s, the receipts selector is
                    # bounded (extra/duplicate/overlong refuse).
                    for q in (
                        f"/admin/keys/{key_id}/calibration?x=1",
                        f"/admin/keys/{key_id}/calibration?operation=x",
                        f"/admin/keys/{key_id}/clone?x=1",
                        f"/admin/keys/{key_id}/clone/receipts?x=1",
                        f"/admin/keys/{key_id}/clone/receipts"
                        "?operation=12345678-9abc-4def-8123-456789abcdef"
                        "&operation=12345678-9abc-4def-8123-456789abcdef",
                        f"/admin/keys/{key_id}/clone/receipts"
                        "?operation=12345678-9abc-4def-8123-456789abcdef"
                        "&x=1",
                        f"/admin/keys/{key_id}/clone/receipts?operation="
                        + "a" * 65,
                    ):
                        r = await client.get(q)
                        assert r.status_code == 404, q

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

                    # --- 224-m: sanitized run-detail transport ---------
                    # TARGET-SIDE INSERTION (honest label): the test
                    # inserts ONE synthetic run's seven test-only leaves
                    # into copy A's worker-published demo_display.leaves
                    # through the owned target-owner connection. Only
                    # validation.json carries an ACTUAL 223 sanitizer
                    # output (for a synthetic original document); the
                    # other six bodies are harmless b"{}" test-only
                    # placeholders and are NOT valid typed outputs for
                    # their kinds (this route loads only validation.json
                    # as a body). This proves route/reader/inventory
                    # transport/binding through the real target-only
                    # table, the restricted reader role and the
                    # gate-bound session - NOT complete worker
                    # publication, artifact content validation, 223
                    # source-file capture or sanitization of a real run
                    # (the configured-file installed workflow remains
                    # objective 225).
                    import json as _rd_json

                    from slaif_gateway.services import (
                        demo_snapshot_files as _rd_dsf,
                    )

                    _rd_seed = b"224m-pg-seed"
                    _rd_orig_id = "e5" * 16  # ORIGINAL id (never stored)
                    _rd_run = _rd_dsf._demo_run_id(_rd_seed, _rd_orig_id)
                    _rd_doc = {
                        "state": "VALID",
                        "state_reason": "free text never displayed",
                        "run_id": _rd_orig_id,
                        "generated_at": "2025-06-15T15:06:40+00:00",
                        "policy_version": 7,
                        "counts": {"routes": 3, "pricing": 2},
                        "per_provider": {"openai": {"models": 2}},
                        "dispositions": [
                            {
                                "provider": "openai",
                                "model": "gpt-test",
                                "disposition": "kept",
                            }
                        ],
                        "price_comparisons": [],
                        "warnings": [
                            {
                                "severity": "info",
                                "code": "demo-warning",
                                "provider": "openai",
                            }
                        ],
                        "gates": [{"name": "schema"}],
                        "import_gates": [],
                        "baseline": {"a": 1},
                        "research": {},
                        "artifacts": {"b": 1},
                        "sql_checks": {},
                        "baseline_metadata": [],
                        "sources": [],
                        "source_evidence": {},
                        "fx_comparisons": [],
                        "execution_context": {},
                        "apply_plan": {"plan": "never displayed"},
                    }
                    _rd_body = _rd_dsf._san_validation_json(
                        _rd_json.dumps(_rd_doc).encode(), _rd_seed
                    )
                    _rd_files = (
                        ("catalog-refresh.json", "refresh_bundle", b"{}"),
                        ("catalog-baseline.json", "baseline_document", b"{}"),
                        ("routes-proposal.tsv", "route_tsv", b"{}"),
                        ("pricing-proposal.tsv", "pricing_tsv", b"{}"),
                        ("fx-proposal.json", "fx_json", b"{}"),
                        ("validation.json", "validation_json", _rd_body),
                        ("REVIEW.html", "review_html", b"{}"),
                    )
                    _rd_url = f"/admin/operations/catalog/runs/{_rd_run}/"
                    try:
                        s = await _target_conn()
                        for name, kind, data in _rd_files:
                            await s.execute(
                                "INSERT INTO demo_display.leaves "
                                "(logical_name, kind, sha256, byte_count, "
                                "captured_at, body) "
                                "VALUES ($1, $2, $3, $4, $5, $6)",
                                f"catalog/runs/{_rd_run}/{name}",
                                kind,
                                _art_hashlib.sha256(data).hexdigest(),
                                len(data),
                                1750000000.0,
                                data,
                            )
                        await s.close()
                        # Session A: the sanitized run-detail page from
                        # its OWN exact copy (banner, bounded fields,
                        # seven artifact links, no seal/live/apply
                        # authority, no copy name or credential).
                        r = await client_a.get(_rd_url)
                        assert r.status_code == 200
                        assert r.headers["cache-control"] == "private, no-store"
                        rd_text = " ".join(r.text.split())
                        assert "Sanitized snapshot display" in rd_text
                        assert "no original seal" in rd_text
                        assert "no live status" in rd_text
                        assert "no apply authority" in rd_text
                        assert "historical at capture time" in rd_text
                        assert "VALID" in rd_text
                        assert "2025-06-15T15:06:40+00:00" in rd_text
                        assert "demo-warning" in rd_text
                        assert "gpt-test" in rd_text
                        for name, _kind, _data in _rd_files:
                            assert (
                                f'href="/admin/operations/catalog/artifact'
                                f'?name=catalog/runs/{_rd_run}/{name}"'
                            ) in r.text, name
                        assert target_a not in r.text
                        assert _rd_orig_id not in r.text
                        # Session B: the SAME canonical path against its
                        # OWN exact copy (which has NO run leaves) is a
                        # fixed safe 404 (copy isolation).
                        r = await client_b.get(_rd_url)
                        assert r.status_code == 404
                        assert r.content == b"Not Found"
                        # Near miss: the same id WITHOUT the required
                        # trailing slash stays gate-denied 404.
                        r = await client_a.get(_rd_url.rstrip("/"))
                        assert r.status_code == 404
                        # Corruption: a wrong stored SHA on
                        # validation.json is the fixed safe 503.
                        s = await _target_conn()
                        await s.execute(
                            "UPDATE demo_display.leaves SET sha256 = $2 "
                            "WHERE logical_name = $1",
                            f"catalog/runs/{_rd_run}/validation.json",
                            "f" * 64,
                        )
                        await s.close()
                        r = await client_a.get(_rd_url)
                        assert r.status_code == 503
                        assert r.headers["cache-control"] == "private, no-store"
                        assert _rd_body not in r.content
                        # Incomplete run: six of the seven files is the
                        # SAME fixed safe 503.
                        s = await _target_conn()
                        await s.execute(
                            "DELETE FROM demo_display.leaves "
                            "WHERE logical_name = $1",
                            f"catalog/runs/{_rd_run}/REVIEW.html",
                        )
                        await s.close()
                        r = await client_a.get(_rd_url)
                        assert r.status_code == 503
                        # The run-detail path is the SAME quiet 204 cut
                        # (body never parsed).
                        r = await client_a.post(
                            _rd_url,
                            content=b"x" * 200_000,
                            headers={"content-type": "text/garbage"},
                        )
                        assert r.status_code == 204
                        assert r.content == b""
                    finally:
                        # Remove EXACTLY the seven test-inserted run
                        # leaves (exact names, never a prefix match -
                        # a pre-existing run sharing a prefix must
                        # never be touched); copy A returns to the
                        # exact worker-published state.
                        s = await _target_conn()
                        await s.execute(
                            "DELETE FROM demo_display.leaves "
                            "WHERE logical_name = ANY($1::text[])",
                            [
                                f"catalog/runs/{_rd_run}/{name}"
                                for name, _kind, _data in _rd_files
                            ],
                        )
                        await s.close()
                        # Cleanup proven: session A 404s again.
                        r = await client_a.get(_rd_url)
                        assert r.status_code == 404

                    # --- 224-n: captured-proposals transport -----------
                    # TARGET-SIDE INSERTION (honest label): the test
                    # inserts ONE test-only captured proposal job into
                    # copy A's worker-published demo_display.leaves
                    # through the owned target-owner connection: two
                    # proposal artifact leaves whose bodies are b"{}"
                    # test-only placeholders (NOT valid TSV content for
                    # their kinds - the page reads ONLY their metadata,
                    # never artifact bodies) and one sanitized job
                    # record whose body is the ACTUAL 223 sanitizer
                    # output for a synthetic original record. This
                    # proves route/reader/inventory transport/binding
                    # through the real target-only table, the
                    # restricted reader role and the gate-bound session
                    # - NOT 223 source capture, worker publication or
                    # sanitization of a real job (the configured-file
                    # installed workflow remains objective 225).
                    _pn_orig_job = "e6" * 16  # ORIGINAL id (never stored)
                    _pn_job = _rd_dsf._demo_job_id(b"224n-pg-seed", _pn_orig_job)
                    _pn_record = _rd_dsf._sanitize_job_record(
                        _rd_json.dumps(
                            {
                                "job_id": _pn_orig_job,
                                "family": "proposal",
                                "status": "ready",
                                "progress": "free text never displayed",
                                "dispatch": None,
                                "run_id": None,
                                "artifact_name": None,
                                "cancel_requested": False,
                                "created_at": "2025-06-15T15:00:00+00:00",
                                "updated_at": "2025-06-15T15:06:40+00:00",
                            }
                        ).encode(),
                        b"224n-pg-seed",
                    )
                    _pn_files = (
                        (
                            f"catalog/proposals/{_pn_job}/routes-proposal.tsv",
                            "route_tsv",
                            b"{}",
                        ),
                        (
                            f"catalog/proposals/{_pn_job}"
                            "/packages/openrouter-chat-text/pricing-proposal.tsv",
                            "pricing_tsv",
                            b"{}",
                        ),
                        (
                            f"catalog/jobs/{_pn_job}.json",
                            "job_record",
                            _pn_record,
                        ),
                    )
                    _pn_url = "/admin/operations/catalog/proposals"
                    try:
                        s = await _target_conn()
                        for _pn_name, _pn_kind, _pn_data in _pn_files:
                            await s.execute(
                                "INSERT INTO demo_display.leaves "
                                "(logical_name, kind, sha256, byte_count, "
                                "captured_at, body) "
                                "VALUES ($1, $2, $3, $4, $5, $6)",
                                _pn_name,
                                _pn_kind,
                                _art_hashlib.sha256(_pn_data).hexdigest(),
                                len(_pn_data),
                                1750000200.0,
                                _pn_data,
                            )
                        await s.close()
                        # Session A: the captured-proposals page from
                        # its OWN exact copy (demo banner, the one
                        # captured artifact group with both forced-
                        # download hrefs, the typed HISTORICAL status,
                        # no original id and no copy name).
                        r = await client_a.get(_pn_url)
                        assert r.status_code == 200
                        assert r.headers["cache-control"] == "private, no-store"
                        _pn_text = " ".join(r.text.split())
                        assert "Sanitized demo snapshot display" in _pn_text
                        assert "ILLUSTRATIVE demo-only form" in _pn_text
                        assert "Captured proposal artifact groups (historical)" in _pn_text
                        assert f'value="{_pn_job}" selected' in r.text
                        for _pn_name, _pn_kind, _pn_data in _pn_files[:2]:
                            assert (
                                f'href="/admin/operations/catalog/artifact'
                                f'?name={_pn_name}"'
                            ) in r.text, _pn_name
                        assert "historical at capture time" in _pn_text
                        assert ">ready<" in r.text
                        assert "2025-06-15T15:00:00+00:00" in r.text
                        assert _pn_orig_job not in r.text
                        assert target_a not in r.text
                        # Explicit selection of the same group.
                        r = await client_a.get(_pn_url + "?job=" + _pn_job)
                        assert r.status_code == 200
                        # Unknown canonical job id: fixed 404, no
                        # fallback to another group.
                        r = await client_a.get(_pn_url + "?job=" + "e5" * 16)
                        assert r.status_code == 404
                        assert _pn_job not in r.text
                        # Duplicate/extra query parameters: fixed 404.
                        r = await client_a.get(
                            _pn_url + "?job=" + _pn_job + "&job=" + _pn_job
                        )
                        assert r.status_code == 404
                        r = await client_a.get(_pn_url + "?x=1")
                        assert r.status_code == 404
                        # Session B: the SAME page against its OWN exact
                        # copy (which has NO proposal leaves) renders
                        # the honest empty state (copy isolation).
                        r = await client_b.get(_pn_url)
                        assert r.status_code == 200
                        assert (
                            "No captured proposal artifact groups in this snapshot"
                            in " ".join(r.text.split())
                        )
                        assert f'value="{_pn_job}"' not in r.text
                        # Corruption: a wrong stored SHA on the job
                        # record is the fixed safe 503, no body echo.
                        s = await _target_conn()
                        await s.execute(
                            "UPDATE demo_display.leaves SET sha256 = $2 "
                            "WHERE logical_name = $1",
                            f"catalog/jobs/{_pn_job}.json",
                            "f" * 64,
                        )
                        await s.close()
                        r = await client_a.get(_pn_url)
                        assert r.status_code == 503
                        assert r.headers["cache-control"] == "private, no-store"
                        assert _pn_record not in r.content
                        # The page path is the SAME quiet 204 cut.
                        r = await client_a.post(
                            _pn_url,
                            content=b"x" * 200_000,
                            headers={"content-type": "text/garbage"},
                        )
                        assert r.status_code == 204
                        assert r.content == b""
                    finally:
                        # Remove EXACTLY the three test-inserted names
                        # (never a prefix match); the worker-published
                        # state returns exactly.
                        s = await _target_conn()
                        await s.execute(
                            "DELETE FROM demo_display.leaves "
                            "WHERE logical_name = ANY($1::text[])",
                            [_pn_name for _pn_name, _k, _d in _pn_files],
                        )
                        await s.close()
                        # Cleanup proven: copy A returns to its exact
                        # worker-published state -> the honest empty
                        # artifact-group state, no group link. (The
                        # missing-record "status unavailable" behavior
                        # is covered by the mocked-ASGI unit test.)
                        r = await client_a.get(_pn_url)
                        assert r.status_code == 200
                        assert (
                            "No captured proposal artifact groups in this snapshot"
                            in " ".join(r.text.split())
                        )
                        assert f'value="{_pn_job}"' not in r.text

                    # --- 224-o: captured complete runs (collect) -------
                    # TARGET-SIDE INSERTION (honest label): the test
                    # inserts ONE test-only captured COMPLETE run's
                    # seven sealed-run content leaves into copy A's
                    # worker-published demo_display.leaves through the
                    # owned target-owner connection. ALL seven bodies
                    # are b"{}" test-only placeholders (NOT valid
                    # sealed-run content for their kinds) - the collect
                    # page reads ONLY their metadata, never any run
                    # body. This proves route/reader/inventory
                    # transport/binding through the real target-only
                    # table, the restricted reader role and the
                    # gate-bound session - NOT 223 source capture,
                    # worker publication or sanitization of a real run
                    # (the configured-file installed workflow remains
                    # objective 225).
                    _co_orig_run = "c7" * 16  # ORIGINAL id (never stored)
                    _co_run = _rd_dsf._demo_run_id(b"224o-pg-seed", _co_orig_run)
                    _co_files = [
                        (
                            f"catalog/runs/{_co_run}/{filename}",
                            kind,
                            b"{}",
                        )
                        for filename, kind in (
                            ("catalog-refresh.json", "refresh_bundle"),
                            ("catalog-baseline.json", "baseline_document"),
                            ("routes-proposal.tsv", "route_tsv"),
                            ("pricing-proposal.tsv", "pricing_tsv"),
                            ("fx-proposal.json", "fx_json"),
                            ("validation.json", "validation_json"),
                            ("REVIEW.html", "review_html"),
                        )
                    ]
                    _co_url = "/admin/operations/catalog/collect"
                    try:
                        s = await _target_conn()
                        for _co_index, (_co_name, _co_kind, _co_data) in enumerate(_co_files):
                            await s.execute(
                                "INSERT INTO demo_display.leaves "
                                "(logical_name, kind, sha256, byte_count, "
                                "captured_at, body) "
                                "VALUES ($1, $2, $3, $4, $5, $6)",
                                _co_name,
                                _co_kind,
                                _art_hashlib.sha256(_co_data).hexdigest(),
                                len(_co_data),
                                1750000300.0 + _co_index,
                                _co_data,
                            )
                        await s.close()
                        # Session A: the collect page from its OWN exact
                        # copy (demo banner, the ONE captured complete
                        # run group linked to the exact 224-m run-detail
                        # page, the stated bound, no original run id and
                        # no copy name, no false live-availability claim).
                        r = await client_a.get(_co_url)
                        assert r.status_code == 200
                        assert r.headers["cache-control"] == "private, no-store"
                        _co_text = " ".join(r.text.split())
                        assert "Sanitized demo snapshot display" in _co_text
                        assert "ILLUSTRATIVE demo-only form" in _co_text
                        assert "shown as" not in r.text
                        assert "Captured complete runs (historical, all acquisition paths)" in _co_text
                        assert "NOT attributed to this collect form" in _co_text
                        assert (
                            f'href="/admin/operations/catalog/runs/{_co_run}/"'
                        ) in r.text
                        assert "7 files" in _co_text
                        assert _co_orig_run not in r.text
                        assert target_a not in r.text
                        # Session B: the SAME page against its OWN exact
                        # copy (which has NO run leaves) renders the
                        # honest empty complete-run state (copy
                        # isolation) with the no-inference note.
                        r = await client_b.get(_co_url)
                        assert r.status_code == 200
                        assert (
                            "No captured complete runs in this snapshot"
                            in " ".join(r.text.split())
                        )
                        assert (
                            "This does not establish that no collect jobs exist or that live catalog storage is unconfigured"
                            in " ".join(r.text.split())
                        )
                        assert f'runs/{_co_run}/' not in r.text
                        # Partial run group (six of the seven files) is
                        # the fixed safe 503, never a silent omission.
                        s = await _target_conn()
                        await s.execute(
                            "DELETE FROM demo_display.leaves "
                            "WHERE logical_name = $1",
                            f"catalog/runs/{_co_run}/REVIEW.html",
                        )
                        await s.close()
                        r = await client_a.get(_co_url)
                        assert r.status_code == 503
                        assert r.headers["cache-control"] == "private, no-store"
                        assert _co_run not in r.text
                        # The page path is the SAME quiet 204 cut.
                        r = await client_a.post(
                            _co_url,
                            content=b"x" * 200_000,
                            headers={"content-type": "text/garbage"},
                        )
                        assert r.status_code == 204
                        assert r.content == b""
                    finally:
                        # Remove EXACTLY the seven test-inserted run
                        # leaves (exact names, never a prefix match -
                        # a pre-existing run sharing a prefix must
                        # never be touched); the worker-published state
                        # returns exactly.
                        s = await _target_conn()
                        await s.execute(
                            "DELETE FROM demo_display.leaves "
                            "WHERE logical_name = ANY($1::text[])",
                            [_co_name for _co_name, _k, _d in _co_files],
                        )
                        await s.close()
                        # Cleanup proven: the honest empty state returns.
                        r = await client_a.get(_co_url)
                        assert r.status_code == 200
                        assert (
                            "No captured complete runs in this snapshot"
                            in " ".join(r.text.split())
                        )

                    # --- 224-p: captured job records (jobs page) -------
                    # TARGET-SIDE INSERTION (honest label): the test
                    # inserts ONE test-only captured job record plus
                    # its captured run's seven sealed-run content
                    # leaves and its captured upload leaf into copy A's
                    # worker-published demo_display.leaves through the
                    # owned target-owner connection. The job record
                    # body is the ACTUAL 223 sanitizer output for a
                    # synthetic original record (family
                    # review_supplied, with a remapped run reference
                    # and a remapped upload reference); the seven run
                    # content bodies and the upload body are b"{}"
                    # test-only placeholders (the jobs page reads ONLY
                    # their metadata, never any run/upload body). This
                    # proves route/reader/inventory transport/binding
                    # through the real target-only table, the
                    # restricted reader role and the gate-bound session
                    # - NOT 223 source capture, worker publication or
                    # sanitization of a real job (the configured-file
                    # installed workflow remains objective 225).
                    _pp_orig_job = "e8" * 16  # ORIGINAL id (never stored)
                    _pp_job = _rd_dsf._demo_job_id(b"224p-pg-seed", _pp_orig_job)
                    _pp_orig_run = "f8" * 16
                    _pp_run = _rd_dsf._demo_run_id(b"224p-pg-seed", _pp_orig_run)
                    _pp_orig_upload = "bundle-" + "a8" * 16
                    _pp_upload = _rd_dsf._remap_upload_name(
                        b"224p-pg-seed", _pp_orig_upload
                    )
                    _pp_record = _rd_dsf._sanitize_job_record(
                        _rd_json.dumps(
                            {
                                "job_id": _pp_orig_job,
                                "family": "review_supplied",
                                "status": "ready",
                                "progress": "free text never displayed",
                                "dispatch": None,
                                "run_id": _pp_orig_run,
                                "artifact_name": _pp_orig_upload,
                                "cancel_requested": False,
                                "created_at": "2025-06-15T15:00:00+00:00",
                                "updated_at": "2025-06-15T15:06:40+00:00",
                            }
                        ).encode(),
                        b"224p-pg-seed",
                    )
                    _pp_files = [
                        (
                            f"catalog/runs/{_pp_run}/{filename}",
                            kind,
                            b"{}",
                        )
                        for filename, kind in (
                            ("catalog-refresh.json", "refresh_bundle"),
                            ("catalog-baseline.json", "baseline_document"),
                            ("routes-proposal.tsv", "route_tsv"),
                            ("pricing-proposal.tsv", "pricing_tsv"),
                            ("fx-proposal.json", "fx_json"),
                            ("validation.json", "validation_json"),
                            ("REVIEW.html", "review_html"),
                        )
                    ]
                    _pp_files.append(
                        (
                            f"catalog/uploads/{_pp_job}/{_pp_upload}",
                            "refresh_bundle",
                            b"{}",
                        )
                    )
                    _pp_files.append(
                        (f"catalog/jobs/{_pp_job}.json", "job_record", _pp_record)
                    )
                    _pp_url = "/admin/operations/catalog/jobs/"
                    try:
                        s = await _target_conn()
                        for _pp_index, (_pp_name, _pp_kind, _pp_data) in enumerate(
                            _pp_files
                        ):
                            await s.execute(
                                "INSERT INTO demo_display.leaves "
                                "(logical_name, kind, sha256, byte_count, "
                                "captured_at, body) "
                                "VALUES ($1, $2, $3, $4, $5, $6)",
                                _pp_name,
                                _pp_kind,
                                _art_hashlib.sha256(_pp_data).hexdigest(),
                                len(_pp_data),
                                1750000400.0 + _pp_index,
                                _pp_data,
                            )
                        await s.close()
                        # Session A: the jobs page from its OWN exact
                        # copy (one captured record, the sanitized
                        # HISTORICAL fields, BOTH independently
                        # verified references linked, no original ids
                        # and no copy name).
                        r = await client_a.get(_pp_url)
                        assert r.status_code == 200
                        assert r.headers["cache-control"] == "private, no-store"
                        _pp_text = " ".join(r.text.split())
                        assert "Captured job records (historical, all job families)" in _pp_text
                        assert "1 shown" in _pp_text
                        assert ">review_supplied<" in r.text
                        assert ">ready<" in r.text
                        assert "2025-06-15T15:00:00+00:00" in r.text
                        assert "free text never displayed" not in r.text
                        # The verified references link to the exact
                        # 224-m run-detail page and the 224-l forced
                        # download (never the original custody).
                        assert (
                            f'href="/admin/operations/catalog/runs/{_pp_run}/"'
                        ) in r.text
                        assert (
                            f'href="/admin/operations/catalog/artifact'
                            f'?name=catalog/uploads/{_pp_job}/{_pp_upload}"'
                        ) in r.text
                        assert _pp_orig_job not in r.text
                        assert _pp_orig_run not in r.text
                        assert _pp_orig_upload not in r.text
                        assert target_a not in r.text
                        # Explicit selection of the same record.
                        r = await client_a.get(_pp_url + "?job=" + _pp_job)
                        assert r.status_code == 200
                        # Unknown canonical job id: fixed 404, no
                        # fallback, no echo.
                        r = await client_a.get(_pp_url + "?job=" + "e7" * 16)
                        assert r.status_code == 404
                        assert _pp_job not in r.text
                        # Duplicate / extra query parameters: 404.
                        r = await client_a.get(
                            _pp_url + "?job=" + _pp_job + "&job=" + _pp_job
                        )
                        assert r.status_code == 404
                        r = await client_a.get(_pp_url + "?x=1")
                        assert r.status_code == 404
                        # Session B: the SAME page against its OWN
                        # exact copy (which has NO job leaves) renders
                        # the honest empty state (copy isolation).
                        r = await client_b.get(_pp_url)
                        assert r.status_code == 200
                        assert (
                            "No captured job records in this snapshot"
                            in " ".join(r.text.split())
                        )
                        assert _pp_job not in r.text
                        # Corruption: a wrong stored SHA on the job
                        # record is the fixed safe 503, no body echo.
                        s = await _target_conn()
                        await s.execute(
                            "UPDATE demo_display.leaves SET sha256 = $2 "
                            "WHERE logical_name = $1",
                            f"catalog/jobs/{_pp_job}.json",
                            "f" * 64,
                        )
                        await s.close()
                        r = await client_a.get(_pp_url)
                        assert r.status_code == 503
                        assert r.headers["cache-control"] == "private, no-store"
                        assert _pp_record not in r.content
                        # The page path is the SAME quiet 204 cut.
                        r = await client_a.post(
                            _pp_url,
                            content=b"x" * 200_000,
                            headers={"content-type": "text/garbage"},
                        )
                        assert r.status_code == 204
                        assert r.content == b""
                    finally:
                        # Remove EXACTLY the nine test-inserted names
                        # (exact names, never a prefix match - a
                        # pre-existing run/job sharing a prefix must
                        # never be touched); the worker-published
                        # state returns exactly.
                        s = await _target_conn()
                        await s.execute(
                            "DELETE FROM demo_display.leaves "
                            "WHERE logical_name = ANY($1::text[])",
                            [_pp_name for _pp_name, _k, _d in _pp_files],
                        )
                        await s.close()
                        # Cleanup proven: the honest empty state
                        # returns.
                        r = await client_a.get(_pp_url)
                        assert r.status_code == 200
                        assert (
                            "No captured job records in this snapshot"
                            in " ".join(r.text.split())
                        )

                    # --- 224-q: key read pages over the verified copy ---
                    # TARGET-SIDE INSERTION (honest label): the test
                    # inserts TWO test-only key rows into copy A's
                    # gateway_keys through the owned target-owner
                    # connection. Each row is copied structurally from
                    # an already-sanitized fixture key row (SELECT *
                    # with id/public_key_id/token_hash/purpose
                    # overrides): one trusted_calibration key (for the
                    # calibration page) and one standard key (for the
                    # clone/receipts pages). This proves real
                    # route/handler/READ-ONLY transport over the
                    # verified copy and the gate-bound request-local
                    # session - NOT 223/222 source capture or worker
                    # publication (the configured-file installed proof
                    # remains objective 225).
                    _q_cal_key = str(uuid.uuid4())
                    _q_std_key = str(uuid.uuid4())

                    async def _q_insert_key(new_id: str, purpose: str) -> None:
                        s = await _target_conn()
                        try:
                            row = await s.fetchrow(
                                "SELECT * FROM gateway_keys "
                                "ORDER BY created_at, id LIMIT 1"
                            )
                            assert row is not None
                            vals = dict(row)
                            vals["id"] = new_id
                            vals["public_key_id"] = f"224q-{purpose}-public"
                            vals["token_hash"] = (
                                "224q-" + _art_hashlib.sha256(
                                    new_id.encode()
                                ).hexdigest()
                            )
                            vals["key_purpose"] = purpose
                            # The closed purpose/policy-mode pair
                            # constraint: a trusted_calibration key
                            # must carry the discovery mode.
                            vals["capability_policy_mode"] = (
                                "trusted_calibration_discovery"
                                if purpose == "trusted_calibration"
                                else "standard"
                            )
                            cols = list(vals.keys())
                            ph = ", ".join(
                                f"${i + 1}" for i in range(len(cols))
                            )
                            await s.execute(
                                f"INSERT INTO gateway_keys "
                                f"({', '.join(cols)}) VALUES ({ph})",
                                *[vals[c] for c in cols],
                            )
                        finally:
                            await s.close()

                    try:
                        await _q_insert_key(_q_cal_key, "trusted_calibration")
                        await _q_insert_key(_q_std_key, "standard")
                        # Session A: the trusted-calibration key detail
                        # shows the admitted calibration read link...
                        r = await client_a.get(f"/admin/keys/{_q_cal_key}")
                        assert r.status_code == 200
                        assert (
                            f'href="/admin/keys/{_q_cal_key}/calibration"'
                        ) in r.text
                        # ...and the calibration page renders with the
                        # demo banner (frozen copy data, illustrative
                        # preview form, no live configuration claim).
                        r = await client_a.get(
                            f"/admin/keys/{_q_cal_key}/calibration"
                        )
                        assert r.status_code == 200
                        assert r.headers["cache-control"] == "private, no-store"
                        _q_text = " ".join(r.text.split())
                        assert "Sanitized demo snapshot display" in _q_text
                        assert "frozen at snapshot time" in _q_text
                        assert "ILLUSTRATIVE" in _q_text
                        assert "no live configuration is read" in _q_text
                        # The standard key's clone form carries the
                        # view-time eligibility label; the eligibility
                        # VALUE is derived by the core build_plan over
                        # the frozen copied rows (whatever it reports
                        # is honest historical display state).
                        r = await client_a.get(f"/admin/keys/{_q_std_key}/clone")
                        assert r.status_code == 200
                        _q_text = " ".join(r.text.split())
                        assert "Sanitized demo snapshot display" in _q_text
                        assert (
                            "computed for this copied snapshot AT VIEW TIME"
                            in _q_text
                        )
                        assert (
                            "not a live operational eligibility decision"
                            in _q_text
                        )
                        assert "Eligibility:" in _q_text
                        # The receipts page (no selector): the demo
                        # banner over the operation form...
                        r = await client_a.get(
                            f"/admin/keys/{_q_std_key}/clone/receipts"
                        )
                        assert r.status_code == 200
                        assert (
                            "HISTORICAL, recovered from this copy"
                            in " ".join(r.text.split())
                        )
                        # ...and with an operation selector: the honest
                        # historical not-found (NO receipt rows exist
                        # in the copy; nothing is implied about source
                        # operations outside the snapshot).
                        r = await client_a.get(
                            f"/admin/keys/{_q_std_key}/clone/receipts"
                            f"?operation={uuid.uuid4()}"
                        )
                        assert r.status_code == 200
                        assert (
                            "NOTHING is assumed" in " ".join(r.text.split())
                        )
                        # Canaries: copy name, reader role and DSN
                        # fragments never appear.
                        assert target_a not in r.text
                        assert str(env["reader_role"]) not in r.text
                        # Session B: the SAME paths against its OWN copy
                        # (which has NO inserted rows) are honest
                        # handler-level 404s (copy isolation).
                        for p in (
                            f"/admin/keys/{_q_cal_key}",
                            f"/admin/keys/{_q_cal_key}/calibration",
                            f"/admin/keys/{_q_std_key}/clone",
                            f"/admin/keys/{_q_std_key}/clone/receipts",
                        ):
                            r = await client_b.get(p)
                            assert r.status_code == 404, p
                        assert _q_cal_key not in r.text
                        # The page paths are the SAME quiet 204 cut.
                        for p in (
                            f"/admin/keys/{_q_cal_key}/calibration",
                            f"/admin/keys/{_q_std_key}/clone",
                            f"/admin/keys/{_q_std_key}/clone/receipts",
                        ):
                            r = await client_a.post(
                                p,
                                content=b"x" * 200_000,
                                headers={"content-type": "text/garbage"},
                            )
                            assert r.status_code == 204, p
                            assert r.content == b""
                    finally:
                        # Remove EXACTLY the two test-inserted ids
                        # (exact ids, never a prefix match - a
                        # pre-existing key sharing nothing with them
                        # must never be touched); the
                        # worker-published state returns exactly.
                        s = await _target_conn()
                        await s.execute(
                            "DELETE FROM gateway_keys "
                            "WHERE id = ANY($1::uuid[])",
                            [
                                uuid.UUID(_q_cal_key),
                                uuid.UUID(_q_std_key),
                            ],
                        )
                        await s.close()
                        # Cleanup proven: session A 404s again.
                        r = await client_a.get(f"/admin/keys/{_q_cal_key}")
                        assert r.status_code == 404

                    # --- 224-t: operations index + captured
                    # process-configuration (worker-built copies) ---
                    # Copy A's worker ran with CUSTOM non-default canary
                    # env vars; copy B's worker ran WITHOUT them. Each
                    # session's page must show ONLY its own copy's
                    # captured values (captured at copy time, frozen for
                    # the session - no live fallback).
                    for client, target, is_a in (
                        (client_a, target_a, True),
                        (client_b, target_b, False),
                    ):
                        r = await client.get("/admin/operations/")
                        assert r.status_code == 200
                        assert r.headers["cache-control"] == "private, no-store"
                        assert "Demo preview:" in r.text
                        assert "FROZEN copied data" in r.text
                        assert "unavailable in this demo" in r.text
                        assert (
                            'href="/admin/operations/process-configuration"'
                            in r.text
                        )
                        # 224-v: diagnostics + replay maintenance are
                        # now admitted and linked in the demo branch.
                        assert 'href="/admin/operations/diagnostics"' in r.text
                        assert (
                            'href="/admin/operations/replay-maintenance/"'
                            in r.text
                        )
                        # 224-u: the compatibility page is now admitted
                        # and linked (with the illustrative note).
                        assert 'href="/admin/operations/compatibility/"' in r.text
                        assert target not in r.text
                        r = await client.get(
                            "/admin/operations/process-configuration"
                        )
                        assert r.status_code == 200
                        assert r.headers["cache-control"] == "private, no-store"
                        assert "Demo preview:" in r.text
                        text = " ".join(r.text.split())
                        assert (
                            "worker-observed deployment configuration" in text
                        )
                        assert "Captured at (copy time)" in r.text
                        assert "not recorded in this demo snapshot" in text
                        # The package version is explicitly the LIVE
                        # demo-web build; captured identities not yet
                        # displayed are labeled as such.
                        assert "demo web process, live build" in r.text
                        assert "not displayed on this page yet" in text
                        if is_a:
                            # The custom non-default canary value +
                            # configured provenance come from A's own
                            # per-login capture...
                            m = re.search(
                                r"CHAT_MAX_IMAGES_PER_REQUEST</code>.*?"
                                r'title="(\d+) count"',
                                r.text,
                                re.S,
                            )
                            assert m is not None and m.group(1) == "7", r.text[:800]
                            assert (
                                re.search(
                                    r"DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE"
                                    r"</code>.*?"
                                    r'title="99 requests/minute or none"',
                                    r.text,
                                    re.S,
                                )
                                is not None
                            )
                        else:
                            # ...and copy B (built WITHOUT the canaries)
                            # shows the built-in defaults + default
                            # provenance: copy B never borrows copy A's
                            # projection.
                            m = re.search(
                                r"CHAT_MAX_IMAGES_PER_REQUEST</code>.*?"
                                r'title="(\d+) count"',
                                r.text,
                                re.S,
                            )
                            assert m is not None and m.group(1) == "8", r.text[:800]
                            assert (
                                re.search(
                                    r"DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE"
                                    r"</code>.*?\(none\)",
                                    r.text,
                                    re.S,
                                )
                                is not None
                            )
                        assert target not in r.text
                        assert "postgresql" not in r.text.lower()
                    # Ambient changes AFTER capture must not change the
                    # frozen page (no live fallback): different values,
                    # cleared settings cache, byte-identical re-read.
                    r = await client_a.get(
                        "/admin/operations/process-configuration"
                    )
                    assert r.status_code == 200
                    before = r.text
                    monkeypatch.setenv("CHAT_MAX_IMAGES_PER_REQUEST", "999")
                    monkeypatch.setenv(
                        "DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE", "42"
                    )
                    from slaif_gateway.config import (
                        get_settings as _t_get_settings,
                    )

                    _t_get_settings.cache_clear()
                    try:
                        r2 = await client_a.get(
                            "/admin/operations/process-configuration"
                        )
                    finally:
                        _t_get_settings.cache_clear()
                    assert r2.status_code == 200
                    assert r2.text == before
                    # Near misses and queries stay default-denied; the
                    # newly admitted exact paths are the SAME pre-body
                    # quiet 204 cut for unsafe methods.
                    for client in (client_a, client_b):
                        for p in (
                            "/admin/operations",
                            "/admin/operations//",
                            # 224-v: the exact diagnostics + replay
                            # paths are ADMITTED (proven in the 224-v
                            # block); only these alternate shapes and
                            # queries stay default-denied.
                            "/admin/operations/diagnostics/",
                            "/admin/operations/diagnostics/lookup",
                            "/admin/operations/replay-maintenance",
                            "/admin/operations/replay-maintenance/?x=1",
                            "/admin/operations/replay-maintenance/key/",
                            # 224-u: /admin/operations/compatibility/
                            # is now ADMITTED (proven in the 224-u
                            # block); its near misses are proven there.
                            "/admin/operations/compatibility",
                            "/admin/operations/process-configuration/",
                            "/admin/operations/process-configuration?x=1",
                            "/admin/operations/?x=1",
                        ):
                            r = await client.get(p)
                            assert r.status_code == 404, p
                        for method in ("POST", "PUT", "DELETE"):
                            r = await client.request(
                                method,
                                "/admin/operations/process-configuration",
                                content=b"x" * 200_000,
                                headers={"content-type": "text/garbage"},
                            )
                            assert r.status_code == 204, method
                            assert r.content == b""

                    # --- 224-u: neutral branding + compatibility -------
                    import hashlib as _u_hashlib

                    from slaif_gateway.modules.codex_profile_data import (
                        list_codex_presets as _u_list_presets,
                        read_codex_preset as _u_read_preset,
                    )
                    from slaif_gateway.web import branding as _u_branding

                    _U_SLOTS = ("style.css", "logo", "logo-compact", "favicon", "hero")

                    def _u_target_conn(target):
                        return asyncpg.connect(**_conn_kwargs(
                            san_env.target["host"], san_env.target["port"],
                            san_env.target["user"], san_env.target["password"],
                            target,
                        ))

                    # Both simultaneous copies (DISTINCT source
                    # branding) serve the SAME packaged neutral bytes
                    # for every fixed slot - the source canary tokens
                    # never appear.
                    for client, target, tok in (
                        (client_a, target_a, _U_TOK_A),
                        (client_b, target_b, _U_TOK_B),
                    ):
                        for slot in _U_SLOTS:
                            r = await client.get(f"/admin/branding/{slot}")
                            assert r.status_code == 200, (slot, r.status_code)
                            data, content_type = _u_branding.fallback_asset(slot)
                            assert r.content == data, slot
                            assert r.headers["content-type"].startswith(
                                content_type.split(";")[0]
                            ), slot
                            assert r.headers.get("x-content-type-options") == "nosniff", slot
                            assert r.headers.get("cache-control") == "private, no-store", slot
                            assert tok not in r.content.decode("latin-1"), slot
                        for p in (
                            "/admin/branding/",
                            "/admin/branding/style.css/",
                            "/admin/branding/logos",
                            "/admin/branding/logo?x=1",
                        ):
                            assert (await client.get(p)).status_code == 404, p
                    # Each copy holds the COMPLETE finite five-slot
                    # leaf set, all neutral and self-consistent.
                    for target in (target_a, target_b):
                        s = await _u_target_conn(target)
                        try:
                            rows = await s.fetch(
                                "SELECT logical_name, kind, byte_count, sha256, "
                                "octet_length(body) AS actual "
                                "FROM demo_display.leaves "
                                "WHERE logical_name IN "
                                "('branding/style.css','branding/logo',"
                                "'branding/logo-compact','branding/favicon',"
                                "'branding/hero')"
                            )
                        finally:
                            await s.close()
                        assert len(rows) == 5, (target, len(rows))
                        for row in rows:
                            expected = _u_branding.fallback_asset(
                                row["logical_name"].rsplit("/", 1)[1]
                            )[0]
                            assert row["kind"] == "branding", target
                            assert row["byte_count"] == len(expected), target
                            assert row["sha256"] == _u_hashlib.sha256(expected).hexdigest(), target
                            assert row["actual"] == row["byte_count"], target
                    # Cross-read/corruption proof (TARGET-SIDE mutation,
                    # restored in finally): corrupting COPY A's logo
                    # leaf makes A's slot a fixed safe 503 while B's
                    # identical slot stays 200 (B never reads A's
                    # copy); deleting one of A's five leaves (a
                    # PARTIAL set) is the same fixed safe 503.
                    s = await _u_target_conn(target_a)
                    await s.execute(
                        "UPDATE demo_display.leaves SET sha256 = $2 "
                        "WHERE logical_name = $1",
                        "branding/logo",
                        "f" * 64,
                    )
                    row_a_hero = await s.fetchrow(
                        "SELECT captured_at FROM demo_display.leaves "
                        "WHERE logical_name = 'branding/hero'"
                    )
                    await s.execute(
                        "DELETE FROM demo_display.leaves "
                        "WHERE logical_name = 'branding/hero'"
                    )
                    await s.close()
                    assert row_a_hero is not None
                    try:
                        r = await client_a.get("/admin/branding/logo")
                        assert r.status_code == 503
                        assert r.headers.get("cache-control") == "private, no-store"
                        assert _U_TOK_A not in r.text
                        # Copy B is untouched by A's corruption.
                        r = await client_b.get("/admin/branding/logo")
                        assert r.status_code == 200
                        # A PARTIAL five-slot set refuses too.
                        r = await client_a.get("/admin/branding/hero")
                        assert r.status_code == 503
                    finally:
                        logo_body = _u_branding.fallback_asset("logo")[0]
                        hero_body = _u_branding.fallback_asset("hero")[0]
                        s = await _u_target_conn(target_a)
                        await s.execute(
                            "UPDATE demo_display.leaves SET sha256 = $2, "
                            "byte_count = $3, body = $4 "
                            "WHERE logical_name = $1",
                            "branding/logo",
                            _u_hashlib.sha256(logo_body).hexdigest(),
                            len(logo_body),
                            logo_body,
                        )
                        await s.execute(
                            "INSERT INTO demo_display.leaves "
                            "(logical_name, kind, sha256, byte_count, "
                            "captured_at, body) VALUES ($1, $2, $3, $4, $5, $6)",
                            "branding/hero",
                            "branding",
                            _u_hashlib.sha256(hero_body).hexdigest(),
                            len(hero_body),
                            row_a_hero["captured_at"],
                            hero_body,
                        )
                        await s.close()
                        # Restored: A's slots are 200 again.
                        r = await client_a.get("/admin/branding/logo")
                        assert r.status_code == 200
                        r = await client_a.get("/admin/branding/hero")
                        assert r.status_code == 200
                    # --- 224-u: the read-only compatibility family ---
                    _U_SHIPPED = tuple(n for n, _p, _pr in _u_list_presets())
                    for client, target in (
                        (client_a, target_a),
                        (client_b, target_b),
                    ):
                        r = await client.get("/admin/operations/compatibility/")
                        assert r.status_code == 200
                        assert r.headers["cache-control"] == "private, no-store"
                        assert "Demo preview:" in r.text
                        comp_text = " ".join(r.text.split())
                        assert "Compatibility operations are illustrative" in comp_text
                        assert "have no effect" in comp_text
                        assert "no compatibility or replay authority" in comp_text
                        assert "adopts no API startup compatibility profile" in comp_text
                        assert "not published as display data to this page yet" in comp_text
                        # No runnable profile artifact is offered...
                        assert "/codex-profile/" not in r.text
                        # ...and the package-owned shipped presets are
                        # listed with their exact demo hrefs.
                        for name in _U_SHIPPED:
                            assert (
                                f'href="/admin/operations/compatibility/preset/{name}"'
                                in r.text
                            )
                        assert target not in r.text
                        name = _U_SHIPPED[0]
                        r = await client.get(
                            f"/admin/operations/compatibility/preset/{name}"
                        )
                        assert r.status_code == 200
                        assert (
                            "package-owned credential-free reference material"
                            in " ".join(r.text.split())
                        )
                        # The exact canonical credential-free bytes.
                        r = await client.get(
                            f"/admin/operations/compatibility/preset/{name}/download"
                        )
                        assert r.status_code == 200
                        assert r.content == _u_read_preset(name).encode("utf-8")
                        assert f'attachment; filename="{name}.json"' in r.headers[
                            "content-disposition"
                        ]
                        # The key page for this copy's OWN (per-copy
                        # remapped) canonical key UUID.
                        ukey = await _first_id(san_env, target, "gateway_keys")
                        r = await client.get(
                            f"/admin/operations/compatibility/key/{ukey}"
                        )
                        assert r.status_code == 200, (target, r.status_code)
                        key_text = " ".join(r.text.split())
                        assert "Demo snapshot: the key binding shown is a FROZEN read" in key_text
                        assert "the form has no effect" in key_text
                        assert target not in r.text
                        # Near misses stay gate-denied with the session.
                        for p in (
                            "/admin/operations/compatibility",
                            "/admin/operations/compatibility//",
                            "/admin/operations/compatibility/extra",
                            "/admin/operations/compatibility/preset/",
                            "/admin/operations/compatibility/preset/unknown",
                            f"/admin/operations/compatibility/preset/{name}/download/extra",
                            f"/admin/operations/compatibility/preset/{name}/downloads",
                            "/admin/operations/compatibility/key/",
                            f"/admin/operations/compatibility/key/{ukey.upper()}",
                            f"/admin/operations/compatibility/key/{ukey}/extra",
                            "/admin/operations/compatibility/?x=1",
                        ):
                            assert (await client.get(p)).status_code == 404, p
                        # The review/apply POSTs and the index POST are
                        # the SAME pre-body quiet 204 cut (no review is
                        # signed, nothing is applied).
                        for p in (
                            f"/admin/operations/compatibility/key/{ukey}/review",
                            f"/admin/operations/compatibility/key/{ukey}/apply",
                            "/admin/operations/compatibility/",
                        ):
                            r = await client.post(
                                p,
                                content=b"x" * 200_000,
                                headers={"content-type": "text/garbage"},
                            )
                            assert r.status_code == 204, p
                            assert r.content == b""

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
                            # 224-v: the exact diagnostics + replay
                            # GET family is the SAME quiet cut for
                            # every unsafe method.
                            "/admin/operations/diagnostics",
                            "/admin/operations/replay-maintenance/",
                            "/admin/operations/replay-maintenance/all-active",
                            "/admin/definitely-not-a-route",
                        ):
                            r = await client.post(
                                p,
                                content=b"x" * 200_000,
                                headers={"content-type": "text/garbage"},
                            )
                            assert r.status_code == 204, p
                            assert r.content == b""

                    # --- 224-v: diagnostics + replay over the verified
                    # copies (worker-built, SELECT-only) ---------------
                    # TARGET-SIDE INSERTION (honest label): the test
                    # inserts ONE content-free request_diagnostics row
                    # and ONE codex_replay_references row into COPY A
                    # only, through the owned target-owner connection.
                    # This proves REAL route/gate/reader transport
                    # through a real worker-built copy - NOT source
                    # capture (no worker wrote these rows), and the
                    # rows are deleted before the invariance phase.
                    import uuid as _v_uuid

                    _v_gwid = "gw-224v-pg-" + _v_uuid.uuid4().hex[:12]
                    _v_diag_id = _v_uuid.uuid4()
                    _v_ref_id = _v_uuid.uuid4()
                    _v_item_hmac = _v_uuid.uuid4().hex * 2  # 64-hex
                    _v_key = await _first_id(san_env, target_a, "gateway_keys")
                    _v_usage = await _first_id(san_env, target_a, "usage_ledger")
                    _v_route = await _first_id(san_env, target_a, "model_routes")

                    def _v_target_conn():
                        return asyncpg.connect(**_conn_kwargs(
                            san_env.target["host"], san_env.target["port"],
                            san_env.target["user"], san_env.target["password"],
                            target_a,
                        ))

                    try:
                        s = await _v_target_conn()
                        await s.execute(
                            "INSERT INTO request_diagnostics "
                            "(id, gateway_request_id, client_request_id, "
                            "client_id_unavailable_reason, method, "
                            "endpoint_template, occurred_at, http_status, "
                            "stream_outcome, source, reason_code, "
                            "error_code, error_param, positions, counts, "
                            "limits, gateway_key_id, route_id, "
                            "route_pattern, deployment_revision, "
                            "estimated_input_tokens, replay_error_code, "
                            "recorded_at) "
                            "VALUES ($1, $2, NULL, 'absent', 'POST', "
                            "'/v1/chat/completions', now(), 429, "
                            "'http_rejection', 'quota', 'rate_limit', "
                            "'rate_limit_exceeded', 'requests', "
                            "jsonb_build_object('line', 3)::jsonb, "
                            "jsonb_build_object('count', 5)::jsonb, "
                            "NULL, $3::uuid, $4::uuid, "
                            "'/v1/chat/completions', 'rev-224v', 120, "
                            "NULL, now())",
                            _v_diag_id, _v_gwid, _v_key, _v_route,
                        )
                        await s.execute(
                            "INSERT INTO codex_replay_references "
                            "(id, gateway_key_id, usage_ledger_id, "
                            "source_request_id, provider, route_id, "
                            "upstream_model, item_kind, item_id_hmac, "
                            "call_id_hmac, hmac_key_version, "
                            "tool_namespace, tool_name, created_at, "
                            "expires_at) "
                            "VALUES ($1, $2::uuid, $3::uuid, "
                            "'src-224v-pg', 'openai', $4::uuid, "
                            "'gpt-224v-transport', 'reasoning', $5, "
                            "NULL, 1, NULL, NULL, now(), now() + "
                            "interval '1 hour')",
                            _v_ref_id, _v_key, _v_usage, _v_route,
                            _v_item_hmac,
                        )
                        await s.close()
                        # Session A: the copied recent row renders in
                        # the bounded newest-first list...
                        r = await client_a.get(
                            "/admin/operations/diagnostics"
                        )
                        assert r.status_code == 200
                        assert (
                            r.headers["cache-control"]
                            == "private, no-store"
                        )
                        assert "FROZEN copied content-free" in r.text
                        assert _v_gwid in r.text
                        assert "rate_limit_exceeded" in r.text
                        # ...and the exact safe-ID lookup renders the
                        # FOUND typed facts (percent-encoded colon
                        # form through httpx).
                        r = await client_a.get(
                            "/admin/operations/diagnostics",
                            params={
                                "lookup": _v_gwid,
                                "namespace": "gateway",
                            },
                        )
                        assert r.status_code == 200
                        assert f"<code>{_v_gwid}</code>" in r.text
                        assert "rate_limit_exceeded" in r.text
                        assert target_a not in r.text
                        # Session B: the SAME lookup against its OWN
                        # copy is NOT_FOUND (copy isolation; no
                        # cross-copy read).
                        r = await client_b.get(
                            "/admin/operations/diagnostics",
                            params={
                                "lookup": _v_gwid,
                                "namespace": "gateway",
                            },
                        )
                        assert r.status_code == 200
                        assert "No retained record matches" in r.text
                        # Session A: the one-key scope shows the
                        # copied reference (view-time active split of
                        # the copied expiries, worker-captured TTL).
                        r = await client_a.get(
                            f"/admin/operations/replay-maintenance/"
                            f"key/{_v_key}"
                        )
                        assert r.status_code == 200
                        assert (
                            r.headers["cache-control"]
                            == "private, no-store"
                        )
                        # (the fixture also seeds one function_call
                        # reference per copy, so the exact active count
                        # is asserted only through the unique 224-v
                        # upstream model string.)
                        assert "gpt-224v-transport" in r.text
                        assert "worker-observed at copy time" in r.text
                        assert "31,536,000 seconds" in r.text
                        assert target_a not in r.text
                        # The explicit every-active scope renders for
                        # both sessions (no implicit default exists).
                        r = await client_a.get(
                            "/admin/operations/replay-maintenance/"
                            "all-active"
                        )
                        assert r.status_code == 200
                        assert "Copied retained references" in r.text
                        assert "gpt-224v-transport" in r.text
                        # Session B: its own every-active scope shows
                        # no 224-v reference (copy isolation; copy B's
                        # key IDs are independently remapped, so the
                        # cross-copy proof uses the explicit scope, not
                        # a copy-A key ID).
                        r = await client_b.get(
                            "/admin/operations/replay-maintenance/"
                            "all-active"
                        )
                        assert r.status_code == 200
                        assert "gpt-224v-transport" not in r.text
                        # Gate boundary over the real copy: a
                        # credential-shaped lookup is the gate's
                        # fixed 404 before any copy read.
                        r = await client_a.get(
                            "/admin/operations/diagnostics",
                            params={"lookup": "sk-slaif-224v-pg"},
                        )
                        assert r.status_code == 404
                        assert "sk-slaif-224v-pg" not in r.text
                        # Exact cleanup: the two inserted rows only.
                        s = await _v_target_conn()
                        await s.execute(
                            "DELETE FROM codex_replay_references "
                            "WHERE id = $1",
                            _v_ref_id,
                        )
                        await s.execute(
                            "DELETE FROM request_diagnostics "
                            "WHERE id = $1",
                            _v_diag_id,
                        )
                        await s.close()
                    except BaseException:
                        # Exact cleanup on failure too (the
                        # invariance phase must see untouched copies).
                        try:
                            s = await _v_target_conn()
                            await s.execute(
                                "DELETE FROM codex_replay_references "
                                "WHERE id = $1",
                                _v_ref_id,
                            )
                            await s.execute(
                                "DELETE FROM request_diagnostics "
                                "WHERE id = $1",
                                _v_diag_id,
                            )
                            await s.close()
                        finally:
                            raise

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


# ---------------------------------------------------------------------------
# 224-r browser proof helpers: a clone receipt WRITTEN BY THE SUPPORTED
# CLONE FLOW (208) in the source -> worker copy A -> projected receipt
# (remapped links) -> Chromium chooser + positive selection; then the flow
# rows leave the source before copy B is processed, so copy B must not
# carry them (copy isolation). Flow-owned rows are removed by exact
# id-set diff (children first) so the shared module seed is byte-identical.
# ---------------------------------------------------------------------------


def _r_source_url(san: _Env) -> str:
    return (
        f"postgresql+asyncpg://{san.source['user']}:{san.source['password']}"
        f"@{san.source['host']}:{san.source['port']}/{san.source['database']}"
    )


async def _r_flow_baseline(san: _Env) -> dict[str, set[str]]:
    s = await asyncpg.connect(**_conn_kwargs(
        san.source["host"], san.source["port"],
        san.source["user"], san.source["password"],
        str(san.source["database"]),
    ))
    try:
        return {t: await _flow_table_ids(s, t) for t in _FLOW_AFFECTED_TABLES}
    finally:
        await s.close()


async def _r_source_flow_cleanup(san: _Env, flow: dict[str, object]) -> None:
    """Remove exactly the flow-owned rows (id-set diff vs the baseline)."""
    baseline = flow.get("baseline")
    if not baseline:
        return
    s = await asyncpg.connect(**_conn_kwargs(
        san.source["host"], san.source["port"],
        san.source["user"], san.source["password"],
        str(san.source["database"]),
    ))
    try:
        for table in _FLOW_AFFECTED_TABLES:
            current = await _flow_table_ids(s, table)
            await _flow_delete_ids(s, table, current - baseline[table])
    finally:
        await s.close()


async def _r_source_flow(san: _Env) -> dict[str, object]:
    """Run the SUPPORTED clone flow on the shared source DB.

    Creates a login-able admin and drives the live guided flow (create
    key -> review -> apply) for the SAME owner as the seeded canary key;
    returns the flow ground truth (source2/target ids + the receipt the
    flow itself persisted - never a hand-built seed).
    """
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
    from slaif_gateway.main import create_app
    from slaif_gateway.utils.passwords import hash_admin_password

    from tests.integration.test_admin_key_clone_208_postgres import (
        ADMIN_PASSWORD,
        TOKEN_RE,
        _apply,
        _create_key,
        _login,
        _review,
        _settings,
    )

    s = await asyncpg.connect(**_conn_kwargs(
        san.source["host"], san.source["port"],
        san.source["user"], san.source["password"],
        str(san.source["database"]),
    ))
    try:
        url = _r_source_url(san)
        engine = create_async_engine(url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    admin = await AdminUsersRepository(session).create_admin_user(
                        email=f"clone-flow-{uuid.uuid4().hex[:8]}@example.org",
                        display_name="224r Flow Admin",
                        password_hash=hash_admin_password(ADMIN_PASSWORD),
                        role="superadmin",
                        is_active=True,
                    )
        finally:
            await engine.dispose()

        app = create_app(_settings(url))
        with TestClient(app) as client:
            _login(client, {"admin_email": str(admin.email)})
            pre = await _flow_table_ids(s, "gateway_keys")
            _create_key(
                client,
                owner_id=san.ids["owner"],
                extra={
                    "reason": "224-r browser clone flow source key",
                    # The canary seed's single provider row: the create
                    # form refuses an empty provider selection.
                    "allowed_providers": PROVIDER,
                },
            )
            new_src = (await _flow_table_ids(s, "gateway_keys")) - pre
            assert len(new_src) == 1
            source2 = uuid.UUID(next(iter(new_src)))
            review = _review(
                client,
                source2,
                validity_mode="duration-from-now",
                duration_value="3601",
                duration_unit="seconds",
                delivery_mode="none",
                target_owner_id=str(san.ids["owner"]),
            )
            assert review.status_code == 200, review.text[:800]
            token_match = TOKEN_RE.search(review.text)
            assert token_match is not None
            applied = _apply(
                client, source2, token_match.group(1), "224-r browser clone flow"
            )
            assert applied.status_code == 200, applied.text[:800]

        post = await _flow_table_ids(s, "gateway_keys")
        new_tgt = post - pre - new_src
        assert len(new_tgt) == 1
        target_id = uuid.UUID(next(iter(new_tgt)))
        receipt_row = await s.fetchrow(
            "SELECT metadata FROM gateway_keys WHERE id = $1", target_id
        )
        receipt = json.loads(receipt_row["metadata"])["clone_receipt"]
        return {
            "source2": source2,
            "target": target_id,
            "receipt": receipt,
        }
    finally:
        await s.close()


async def _r_copy_receipt_info(san: _Env, copy_db: str) -> dict[str, str]:
    """The copied receipt's remapped links in one copy (target/source/op)."""
    s = await asyncpg.connect(**_conn_kwargs(
        san.target["host"], san.target["port"],
        san.target["user"], san.target["password"], copy_db,
    ))
    try:
        row = await s.fetchrow(
            "SELECT id, metadata FROM public.gateway_keys "
            "WHERE metadata IS NOT NULL AND metadata <> '{}'::jsonb"
        )
        assert row is not None, f"copy {copy_db} carries no receipt row"
        receipt = json.loads(row["metadata"])["clone_receipt"]
        return {
            "target": str(row["id"]),
            "source": str(receipt["source_gateway_key_id"]),
            "op": str(receipt["operation_uuid"]),
        }
    finally:
        await s.close()


async def _r_copy_single_key(san: _Env, copy_db: str) -> str:
    s = await asyncpg.connect(**_conn_kwargs(
        san.target["host"], san.target["port"],
        san.target["user"], san.target["password"], copy_db,
    ))
    try:
        row = await s.fetchrow("SELECT id FROM public.gateway_keys")
        assert row is not None
        return str(row["id"])
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
    request: pytest.FixtureRequest,
) -> None:
    pw = pytest.importorskip("playwright.sync_api")

    env = webenv
    cfg = _web_config(env, san_env)

    # 224-r: the positive chooser/projection proof needs a REAL clone
    # receipt in the source, written by the supported clone flow (208)
    # for the same owner as the canary key. Copy A is built while the
    # flow rows exist; they leave the source before copy B is built, so
    # copy B must not carry them (copy isolation). Exact id-set-diff
    # cleanup is finalizer-guarded for any later failure.
    flow: dict[str, object] = {}
    flow["baseline"] = asyncio.run(_r_flow_baseline(san_env))
    request.addfinalizer(
        lambda: asyncio.run(_r_source_flow_cleanup(san_env, flow))
    )
    flow.update(asyncio.run(_r_source_flow(san_env)))

    # One login -> one real worker-processed copy -> one demo session.
    rid, pending = asyncio.run(_login_phase(cfg, env))
    cli_env = _worker_cli_env(san_env, env, custody)
    # 224-t: copy A's worker captures a CUSTOM non-default
    # process-configuration projection (canaries, not secrets); copy
    # B (built below WITHOUT them) must show the defaults.
    _T_CANARY_BROWSER_ENV = {
        "CHAT_MAX_IMAGES_PER_REQUEST": "7",
        "DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE": "99",
    }
    cli_env_a = {**cli_env, **_T_CANARY_BROWSER_ENV}
    out = _run_worker_cli(
        ["process-request", str(rid), "--json"], cli_env_a, monkeypatch
    )
    assert "verified_unpublished" in out
    target = _request_row(env, rid)["worker_target_db"]
    assert isinstance(target, str) and target.startswith("demo_snap_")
    token = asyncio.run(_wait_phase(cfg, pending))
    names = asyncio.run(_inst_names(san_env, target))

    # 224-r: copy B - the flow rows leave the source NOW (copy A already
    # includes them), so copy B's snapshot must not carry the flow keys
    # or the receipt.
    asyncio.run(_r_source_flow_cleanup(san_env, flow))
    rid_b, pending_b = asyncio.run(_login_phase(cfg, env))
    # 224-t: remove the canary env vars so copy B's worker captures
    # the BUILT-IN defaults (copy isolation for the projection).
    for _k in _T_CANARY_BROWSER_ENV:
        monkeypatch.delenv(_k, raising=False)
    out_b = _run_worker_cli(
        ["process-request", str(rid_b), "--json"], cli_env, monkeypatch
    )
    assert "verified_unpublished" in out_b
    target_b = _request_row(env, rid_b)["worker_target_db"]
    assert isinstance(target_b, str) and target_b.startswith("demo_snap_")
    assert target_b != target
    token_b = asyncio.run(_wait_phase(cfg, pending_b))

    # 224-r pre-computed copy facts: the async DB reads must stay OUT of
    # the sync_playwright greenlet block (asyncio.run cannot run there).
    a_info = asyncio.run(_r_copy_receipt_info(san_env, target))
    b_key = asyncio.run(_r_copy_single_key(san_env, target_b))
    b_key_count = asyncio.run(_count_table(san_env, target_b, "gateway_keys"))

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
            # 224-m: the owned browser fixture has NO configured run,
            # so the canonical run-detail shape is a fixed safe 404 in
            # the real browser (honest empty state; the positive page
            # is proven by owned-PG transport + mocked-ASGI unit
            # coverage, and the configured-file installed browser
            # workflow remains objective 225).
            r = page.goto(
                "/admin/operations/catalog/runs/demo-run-" + "d4" * 12 + "/"
            )
            assert r is not None and r.status == 404
            assert r.headers["cache-control"] == "private, no-store"
            # 224-n: the owned browser fixture has NO configured
            # proposal leaves, so the captured-proposals page renders
            # the honest empty artifact-group state in the real
            # browser (demo banner + illustrative form; the positive
            # page is proven by owned-PG transport + mocked-ASGI unit
            # coverage; the configured-file installed browser workflow
            # remains objective 225).
            r = page.goto("/admin/operations/catalog/proposals")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            _pn_page = page.content()
            assert "Sanitized demo snapshot display" in " ".join(_pn_page.split())
            assert "No captured proposal artifact groups in this snapshot" in " ".join(_pn_page.split())
            assert 'name="provider_scope"' in _pn_page  # illustrative form
            # 224-o: the owned browser fixture has NO configured run
            # leaves, so the collect page renders the honest empty
            # complete-run state in the real browser (demo banner +
            # illustrative form; the positive page is proven by owned-PG
            # transport + mocked-ASGI unit coverage; the configured-file
            # installed browser workflow remains objective 225).
            r = page.goto("/admin/operations/catalog/collect")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            _co_page = page.content()
            assert "Sanitized demo snapshot display" in " ".join(_co_page.split())
            assert "No captured complete runs in this snapshot" in " ".join(_co_page.split())
            assert 'name="mode"' in _co_page  # illustrative form
            # 224-p: the owned browser fixture has NO configured job
            # records, so the jobs page renders the honest empty state
            # in the real browser and the review/export pages render
            # their illustrative demo forms (the positive jobs page is
            # proven by owned-PG transport + mocked-ASGI unit
            # coverage; the configured-file installed browser workflow
            # remains objective 225).
            r = page.goto("/admin/operations/catalog/jobs/")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            _pp_page = page.content()
            assert "No captured job records in this snapshot" in " ".join(_pp_page.split())
            assert "This does not establish that live catalog storage was unconfigured or that no job ran" in " ".join(_pp_page.split())
            r = page.goto("/admin/operations/catalog/review")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            _pr_page = page.content()
            assert "ILLUSTRATIVE demo-only form" in " ".join(_pr_page.split())
            assert 'name="bundle"' in _pr_page  # illustrative form
            r = page.goto("/admin/operations/catalog/export-baseline")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            _ex_page = page.content()
            assert "ILLUSTRATIVE demo-only form" in " ".join(_ex_page.split())
            assert "Database target" not in _ex_page  # no live claim
            # 224-q: the admitted key read pages in the real browser.
            # The fixture's copied key detail shows the admitted demo
            # read links (clone + receipts; calibration only for
            # trusted-calibration keys); the receipts page renders the
            # honest help/banner state (the owned fixture carries no
            # clone receipt rows; the positive projection is proven by
            # owned-PG transport + mocked-ASGI unit coverage).
            page.goto("/admin/keys")
            _qk_href = page.locator(
                'tbody a[href^="/admin/keys/"]'
            ).first.get_attribute("href")
            assert _qk_href, "the owned fixture must carry one copied key"
            r = page.goto(_qk_href)
            assert r is not None and r.status == 200
            _qk_page = page.content()
            assert "Demo preview:" in _qk_page
            assert _qk_href + "/clone" in _qk_page
            assert _qk_href + "/clone/receipts" in _qk_page
            assert (
                "read-only views of data frozen at snapshot time"
                in " ".join(_qk_page.split())
            )
            r = page.goto(_qk_href + "/clone/receipts")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            _qr_page = page.content()
            assert (
                "Sanitized demo snapshot display"
                in " ".join(_qr_page.split())
            )
            assert (
                "HISTORICAL, recovered from this copy"
                in " ".join(_qr_page.split())
            )
            assert target not in _qr_page
            assert target not in content
            assert 'href="/admin/operations"' not in content  # still no nav item
            # ephemeral desktop-layout screenshot (run-owned /tmp path;
            # never committed, not in app logs).
            shot_cat = Path(
                f"/tmp/slaif-224k-browser-catalog-{os.getpid()}-{uuid.uuid4().hex[:10]}.png"
            )
            page.screenshot(path=str(shot_cat))
            print(f"DEMO_BROWSER_CATALOG_SCREENSHOT={shot_cat}")

            # --- 224-t: operations index + captured process
            # configuration in the real browser ------------------------
            # Copy A's worker ran with custom non-default canary env
            # vars: the real Chromium page must show the captured
            # worker-observed values (frozen at copy time, never the
            # live process settings), plus the demo index with its
            # unavailable markers.
            r = page.goto("/admin/operations/")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            content = page.content()
            assert "Demo preview:" in content
            assert "FROZEN copied data" in content
            assert "unavailable in this demo" in content
            assert 'href="/admin/operations/process-configuration"' in content
            # 224-v: the admitted pages are linked in the demo branch.
            assert 'href="/admin/operations/diagnostics"' in content
            assert (
                'href="/admin/operations/replay-maintenance/"' in content
            )
            assert target not in content
            r = page.goto("/admin/operations/process-configuration")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            content = page.content()
            assert "Demo preview:" in content
            _t_flat = " ".join(content.split())
            assert (
                "worker-observed deployment configuration" in _t_flat
            )
            assert "Captured at (copy time)" in content
            assert "not recorded in this demo snapshot" in _t_flat
            assert "demo web process, live build" in content
            assert "not displayed on this page yet" in _t_flat
            # The canary value + configured provenance from copy A's
            # own per-login capture (never the live process settings).
            assert (
                re.search(
                    r"CHAT_MAX_IMAGES_PER_REQUEST</code>.*?"
                    r'title="7 count"',
                    content,
                    re.S,
                )
                is not None
            )
            assert (
                re.search(
                    r"DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE</code>.*?"
                    r'title="99 requests/minute or none"',
                    content,
                    re.S,
                )
                is not None
            )
            assert target not in content
            assert "postgresql" not in content.lower()
            shot_t = Path(
                f"/tmp/slaif-224t-browser-procconfig-{os.getpid()}-{uuid.uuid4().hex[:10]}.png"
            )
            page.screenshot(path=str(shot_t))
            print(f"DEMO_BROWSER_224T_SCREENSHOT={shot_t}")

            # --- 224-v: diagnostics + replay in the real browser ----
            # Read-only pages over the verified copy: the demo banner,
            # the bounded recent table (which carries the fixture's
            # seeded canary diagnostic row) and the visible no-op
            # cleanup form.
            r = page.goto("/admin/operations/diagnostics")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            content = page.content()
            assert "FROZEN copied content-free" in content
            assert "Recent copied diagnostic records" in content
            # the fixture's seeded diagnostic row renders in the
            # bounded recent list under its sanitizer-remapped
            # demo-prefixed gateway ID (copy-backed transport in the
            # real browser; the remap proves no source value leaks).
            assert "rate_limited / rate_limit_exceeded" in content
            assert 'lookup=demo' in content
            assert "canary-diagreq-" not in content
            assert "quiet" in content  # visible no-op cleanup note
            r = page.goto("/admin/operations/replay-maintenance/")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            content = page.content()
            assert "NO effect in this demo" in content
            assert (
                'href="/admin/operations/replay-maintenance/all-active"'
                in content
            )
            assert "HMAC maintenance eligibility is NOT shown" in content
            r = page.goto(
                "/admin/operations/replay-maintenance/all-active"
            )
            assert r is not None and r.status == 200
            content = page.content()
            assert "Copied retained references" in content
            assert "quiet" in content  # visible no-op inspect/preview notes
            # The worker-captured TTL from copy A's per-login
            # process-configuration leaf renders (never the demo
            # process's dummy configured default).
            assert "31,536,000 seconds" in content
            assert target not in content
            assert "postgresql" not in content.lower()
            shot_v = Path(
                f"/tmp/slaif-224v-browser-replay-{os.getpid()}-"
                f"{uuid.uuid4().hex[:10]}.png"
            )
            page.screenshot(path=str(shot_v))
            print(f"DEMO_BROWSER_224V_SCREENSHOT={shot_v}")

            # --- 224-u: neutral branding slots + read-only
            # compatibility views in the real browser -------------
            from slaif_gateway.modules.codex_profile_data import (
                list_codex_presets as _u_list_presets,
            )
            from slaif_gateway.web import branding as _u_branding

            # The demo base header references the FIVE exact fixed
            # slot URLs: the icon and stylesheet links plus the wide
            # and compact logo images (hero renders only on the
            # public page). Assert the rendered href/src values, then
            # explicitly request EVERY fixed slot and compare the
            # exact neutral bytes + safety headers (no reliance on
            # the browser auto-fetching favicon/hero).
            page.goto("/admin/keys")
            content = page.content()
            for slot in ("favicon", "style.css"):
                assert f'href="/admin/branding/{slot}"' in content, slot
            for slot in ("logo", "logo-compact"):
                assert f'src="/admin/branding/{slot}"' in content, slot
            for slot in ("style.css", "logo", "logo-compact", "favicon", "hero"):
                r = page.goto(f"/admin/branding/{slot}")
                assert r is not None and r.status == 200, slot
                data, content_type = _u_branding.fallback_asset(slot)
                assert r.body() == data, slot
                assert r.headers["content-type"].startswith(
                    content_type.split(";")[0]
                ), slot
                assert r.headers.get("x-content-type-options") == "nosniff", slot
                assert r.headers.get("cache-control") == "private, no-store", slot
            for pth in (
                "/admin/branding/",
                "/admin/branding/logos",
                "/admin/branding/style.css?x=1",
            ):
                r = page.goto(pth)
                assert r is not None and r.status == 404, pth
            # The operations index renders the admitted compatibility
            # index link (demo reads only).
            r = page.goto("/admin/operations/")
            assert r is not None and r.status == 200
            assert 'href="/admin/operations/compatibility/"' in page.content()
            r = page.goto("/admin/operations/compatibility/")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            content = page.content()
            assert "Demo preview:" in content
            _u_flat = " ".join(content.split())
            assert "Compatibility operations are illustrative" in _u_flat
            assert "have no effect" in _u_flat
            assert "no compatibility or replay authority" in _u_flat
            assert "adopts no API startup compatibility profile" in _u_flat
            assert "not published as display data to this page yet" in _u_flat
            assert "/codex-profile/" not in content
            assert target not in content
            _u_presets = tuple(n for n, _p, _pr in _u_list_presets())
            assert _u_presets
            for name in _u_presets:
                assert (
                    f'href="/admin/operations/compatibility/preset/{name}"'
                    in content
                )
            _u_preset = _u_presets[0]
            r = page.goto(
                f"/admin/operations/compatibility/preset/{_u_preset}"
            )
            assert r is not None and r.status == 200
            assert (
                "package-owned credential-free reference material"
                in " ".join(page.content().split())
            )
            # The key page for this copy's own copied key; the demo
            # form has no effect (the review POST below is the quiet
            # pre-body 204 cut in the real browser context).
            page.goto("/admin/keys")
            _u_key_href = page.locator(
                'tbody a[href^="/admin/keys/"]'
            ).first.get_attribute("href")
            assert _u_key_href
            _u_key_id = _u_key_href.rsplit("/", 1)[-1]
            r = page.goto(
                f"/admin/operations/compatibility/key/{_u_key_id}"
            )
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            _u_k_flat = " ".join(page.content().split())
            assert (
                "Demo snapshot: the key binding shown is a FROZEN read"
                in _u_k_flat
            )
            assert "the form has no effect" in _u_k_flat
            assert target not in _u_k_flat
            # Desktop-width screenshot of the SUCCESSFUL compatibility
            # key render (taken before the near-miss loop navigates
            # away; run-owned /tmp path, never committed).
            shot_u = Path(
                f"/tmp/slaif-224u-browser-compat-{os.getpid()}-{uuid.uuid4().hex[:10]}.png"
            )
            page.screenshot(path=str(shot_u))
            print(f"DEMO_BROWSER_224U_SCREENSHOT={shot_u}")
            for pth in (
                "/admin/operations/compatibility",
                "/admin/operations/compatibility/extra",
                f"/admin/operations/compatibility/preset/{_u_preset}/extra",
                "/admin/operations/compatibility/key/",
                f"/admin/operations/compatibility/key/{_u_key_id}/extra",
                "/admin/operations/compatibility/?x=1",
            ):
                r = page.goto(pth)
                assert r is not None and r.status == 404, pth
            resp = context.request.post(
                f"/admin/operations/compatibility/key/{_u_key_id}/review",
                data=b"x" * 2000,
                headers={"content-type": "text/garbage"},
            )
            assert resp.status == 204
            assert resp.body() == b""

            # --- 224-r: chooser + positive selection against copy A,
            # then copy-B isolation --------------------------------------
            # Copy A carries the flow's copied receipt: the copied
            # SOURCE key's receipts page lists the copied operation in
            # the SELECT-only chooser (real SQLAlchemy Row transport),
            # and selecting it renders the read-only projection of the
            # copied receipt (remapped links, never raw source values).
            r = page.goto(f"/admin/keys/{a_info['source']}/clone/receipts")
            assert r is not None and r.status == 200
            assert r.headers["cache-control"] == "private, no-store"
            _ra_page = " ".join(page.content().split())
            assert "Historical clone operations" in _ra_page
            _ra_href = (
                f"/admin/keys/{a_info['source']}/clone/receipts"
                f"?operation={a_info['op']}"
            )
            assert _ra_href in page.content()
            page.click(f'a[href="{_ra_href}"]')
            page.wait_for_url(_ra_href)
            _rp_page = page.content()
            _rp_flat = " ".join(_rp_page.split())
            assert "This operation completed and created exactly one target key" in _rp_flat
            assert a_info["target"] in _rp_page
            assert "duration-from-now" in _rp_page
            # Raw source identifiers never render: only per-copy remapped
            # values (the raw receipt UUIDs/public id are absent).
            _raw_receipt = flow["receipt"]
            assert str(_raw_receipt["operation_uuid"]) not in _rp_page
            assert str(_raw_receipt["source_public_key_id"]) not in _rp_page
            assert str(flow["source2"]) not in _rp_page
            assert target not in _rp_page
            # Copy-B isolation: a fresh session over the SECOND copy
            # (built after the flow rows left the source) must not see
            # the flow keys or the receipt - honest empty chooser state.
            assert b_key_count == 1
            context_b = browser.new_context(base_url=base_url)
            page_b = context_b.new_page()
            context_b.add_cookies([
                {"name": "slaif_demo_session", "value": token_b, "url": f"{base_url}/"},
            ])
            r = page_b.goto(f"/admin/keys/{b_key}/clone/receipts")
            assert r is not None and r.status == 200
            _rb_page = " ".join(page_b.content().split())
            assert (
                "No historical clone receipts are visible for this source "
                "in this snapshot"
            ) in _rb_page
            assert a_info["op"] not in _rb_page
            assert a_info["target"] not in _rb_page
            context_b.close()
            shot_r = Path(
                f"/tmp/slaif-224r-browser-receipt-{os.getpid()}-{uuid.uuid4().hex[:10]}.png"
            )
            page.screenshot(path=str(shot_r))
            print(f"DEMO_BROWSER_224R_SCREENSHOT={shot_r}")

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
