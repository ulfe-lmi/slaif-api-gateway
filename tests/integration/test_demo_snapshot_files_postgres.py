"""PostgreSQL 16 integration handoff test for the 223 demo file stage.

Scope (objective 223 test economy): prove the 221 -> 222 -> 223 STATE
HANDOFF, worker custody behavior and web-role denial on owned,
loopback-only PostgreSQL 16 services. Configured file sources for this
handoff are the fixed branding and completion-profile fixtures; the
sealed catalog custody artifact shapes are covered by focused unit
tests (a full valid run_review/RefreshBundle generation belongs to the
225 installed acceptance).

Requires:

    DEMO_223_TEST_SOURCE_URL=postgresql+asyncpg://user:pw@127.0.0.1:PORT/slaif_gateway_test
    DEMO_223_TEST_TARGET_URL=postgresql+asyncpg://user:pw@127.0.0.1:PORT2/postgres

Both URLs must be 127.0.0.1 loopback with the exact allowlisted database
names; anything else skips. The pg_dump/pg_restore/psql on PATH must be
PostgreSQL 16 (the owned servers are 16; a newer host client fails the
restore with the known SET transaction_timeout harness mismatch, which
is a test-environment gap, not a product defect).

Only synthetic run-tagged canary rows are seeded; cleanup is exact and
run-owned (recorded row IDs, recorded target database, run-tagged
roles). No ambient DATABASE_URL, production data, provider or mail
access.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services import demo_snapshot as ds
from slaif_gateway.services import demo_snapshot_files as dsf
from slaif_gateway.services import demo_snapshot_sanitize as dsan
from tests.integration.db_test_utils import run_alembic_upgrade_head

_ALLOWED_SOURCE_DB = "slaif_gateway_test"
_ALLOWED_TARGET_DB = "postgres"
_ALLOWED_HOST = "127.0.0.1"

_CANARY_SOURCE_PW = "canary-src-pw-223-11e0aa"
_CANARY_WEB_PW = "canary-web-pw-223-94b2c7"

_RUN_TAG = uuid.uuid4().hex[:8]
CN = f"223CNX-{_RUN_TAG}"
_BRAND_CANARY = f"223BRND-{_RUN_TAG}"

READER_ROLE = f"demo_fs_reader_{_RUN_TAG}"
WEB_ROLE = f"demo_fs_web_{_RUN_TAG}"

_T0 = datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc)

_CANARY_SVG = (
    f'<svg xmlns="http://www.w3.org/2000/svg"><title>{_BRAND_CANARY}</title></svg>'
).encode("utf-8")


def _uid(label: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"https://slaif.demo.invalid/223/{_RUN_TAG}/{label}")


def _ident(name: str, allowed_db: str) -> dict[str, object] | None:
    raw = os.getenv(name, "")
    if not raw:
        return None
    parsed = urlparse(raw)
    db_name = (parsed.path or "").lstrip("/").lower()
    if parsed.scheme != "postgresql+asyncpg" or parsed.hostname != _ALLOWED_HOST:
        return None
    if db_name != allowed_db:
        return None
    return {
        "host": parsed.hostname,
        "port": parsed.port,
        "user": parsed.username,
        "password": parsed.password,
        "database": db_name,
        "url": raw,
    }


def _require_pg16_tools() -> None:
    for tool in ("pg_dump", "pg_restore", "psql"):
        if shutil.which(tool) is None:
            pytest.skip(f"PostgreSQL client tooling ({tool}) is unavailable")
    try:
        out = subprocess.run(
            ["pg_dump", "--version"], capture_output=True, text=True, check=True
        ).stdout
    except Exception:
        pytest.skip("pg_dump --version failed")
    match = re.search(r"(\d+)\.", out)
    if match is None or int(match.group(1)) != 16:
        pytest.skip(
            f"owned servers are PostgreSQL 16; pg_dump reports {out.strip()!r} "
            "(newer host clients hit the known 17/18->16 restore harness "
            "mismatch). Run with PG16 client binaries on PATH."
        )


async def _connect(url: dict[str, object]) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=str(url["host"]),
        port=int(url["port"]),
        user=str(url["user"]),
        password=str(url["password"]),
        database=str(url["database"]),
    )


# ---------------------------------------------------------------------------
# Small run-owned canary seed (four rows; enough for a meaningful 221/222
# chain and a source-invariance fingerprint).
# ---------------------------------------------------------------------------

# Run-owned seed rows in FK-safe delete order (referencing before referenced).
# model_routes holds TWO rows: an ordinary openrouter nested route (``route``)
# and a synthetic module-provider completion-service route
# (``route_completion``) carrying the operator completion-profile selector for
# the 223-b DB/files link proof.
_SEED_ROWS: list[tuple[str, str]] = [
    ("model_routes", "route"),
    ("model_routes", "route_completion"),
    ("provider_configs", "mprovider"),
    ("owners", "owner"),
    ("institutions", "inst"),
    ("organizations", "org"),
]


async def _seed_canaries(source: dict[str, object]) -> dict[str, uuid.UUID]:
    ids = {label: _uid(label) for (_t, label) in _SEED_ROWS}
    conn = await _connect(source)
    try:
        await conn.execute("BEGIN")
        try:
            await conn.execute(
                "INSERT INTO organizations (id, name, slug, notes, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, $5)",
                ids["org"], f"CanaryOrg{CN}", f"canary-org-{_RUN_TAG}",
                f"org notes {CN}", _T0,
            )
            await conn.execute(
                "INSERT INTO institutions (id, name, country, notes, created_at, updated_at, organization_id) "
                "VALUES ($1, $2, 'SI', $3, $4, $4, $5)",
                ids["inst"], f"CanaryInstitute{CN}", f"institution notes {CN}",
                _T0, ids["org"],
            )
            await conn.execute(
                "INSERT INTO owners (id, name, surname, email, institution_id, external_id, notes, is_active, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, true, $8, $8)",
                ids["owner"], f"CanaryOwnerFirst{CN}", f"CanaryOwnerLast{CN}",
                f"canary-owner-{CN}@canary.invalid", ids["inst"],
                f"canary-external-{CN}", f"owner notes {CN}", _T0,
            )
            # Synthetic module provider for the completion-service route
            # (kind='module', max_retries=0, per the installed completion
            # route law). Mirrors the proven 222 provider_configs INSERT.
            await conn.execute(
                "INSERT INTO provider_configs (id, provider, display_name, kind, base_url, api_key_env_var, enabled, timeout_seconds, max_retries, notes, created_at, updated_at, governance_region, retention_policy, training_use, zdr_claimed, tool_destinations, evidence_date, reviewer) "
                "VALUES ($1, $2, $3, 'module', $4, $5, true, 60, 0, $6, $7, $7, $8, $9, false, false, '[]', $10, $11)",
                ids["mprovider"], f"canary-module-{_RUN_TAG}",
                f"CanaryModule {CN}",
                f"https://canary-module-{_RUN_TAG}.example.invalid/v1",
                f"CANARY_MODULE_KEY_{_RUN_TAG.upper()}",
                f"module provider notes {CN}", _T0,
                f"canary-region-{CN}", f"canary-retention-{CN}",
                _T0, f"CanaryReviewer {CN}",
            )
            # Ordinary openrouter nested route: a normal valid nested
            # capability document (boolean flags + compaction reference),
            # WITHOUT a completion-service selector.
            await conn.execute(
                "INSERT INTO model_routes (id, requested_model, match_type, endpoint, provider, upstream_model, priority, enabled, visible_in_models, supports_streaming, capabilities, notes, created_at, updated_at) "
                "VALUES ($1, $2, 'exact', $3, $4, $5, 100, true, true, true, $6, $7, $8, $8)",
                ids["route"], f"canary-model-{CN}", "/v1/chat/completions",
                "openrouter", f"canary-model-{CN}-up",
                json.dumps({
                    "chat_completions": {"chat_text": True, "chat_streaming": True},
                    "codex_compaction_compatible_route_ids": [str(ids["route"])],
                }),
                f"route notes {CN}", _T0,
            )
            # Synthetic module-provider completion-service route: carries the
            # operator completion-profile selector for the 223-b link proof
            # (no streaming, per the installed completion-service law).
            await conn.execute(
                "INSERT INTO model_routes (id, requested_model, match_type, endpoint, provider, upstream_model, priority, enabled, visible_in_models, supports_streaming, capabilities, notes, created_at, updated_at) "
                "VALUES ($1, $2, 'exact', $3, $4, $5, 100, true, true, false, $6, $7, $8, $8)",
                ids["route_completion"], f"canary-cs-{CN}", "/v1/chat/completions",
                f"canary-module-{_RUN_TAG}", f"canary-cs-{CN}-up",
                json.dumps({
                    "completion_service": {
                        "version": 1, "profile": "alpha-profile-223",
                    },
                }),
                f"completion route notes {CN}", _T0,
            )
        except BaseException:
            await conn.execute("ROLLBACK")
            raise
        await conn.execute("COMMIT")
    finally:
        await conn.close()
    return ids


async def _delete_seed_rows(source: dict[str, object], ids: dict[str, uuid.UUID]) -> dict[str, int]:
    conn = await _connect(source)
    leftover: dict[tuple[str, str], int] = {}
    try:
        await conn.execute("BEGIN")
        for table, label in _SEED_ROWS:
            cur = await conn.execute(f"DELETE FROM {table} WHERE id = $1", ids[label])
            leftover[(table, label)] = 0 if cur.endswith("1") else 1
        await conn.execute("COMMIT")
    except BaseException:
        await conn.execute("ROLLBACK")
        raise
    finally:
        await conn.close()
    return leftover


async def _run_row_fingerprint(
    source: dict[str, object], ids: dict[str, uuid.UUID]
) -> str:
    conn = await _connect(source)
    try:
        parts: list[str] = []
        for table, label in _SEED_ROWS:
            value = await conn.fetchval(
                f"SELECT string_agg(row_to_json(t)::text, ',' ORDER BY id) "
                f"FROM {table} t WHERE id = $1",
                ids[label],
            )
            parts.append(f"{table}:{label}={value}")
        return "\n".join(parts)
    finally:
        await conn.close()


async def _web_connect_refused(env: "_FilesEnv", db: str) -> str:
    try:
        conn = await asyncpg.connect(
            host=str(env.target["host"]),
            port=int(env.target["port"]),
            user=WEB_ROLE,
            password=_CANARY_WEB_PW,
            database=db,
            timeout=10.0,
        )
    except asyncpg.PostgresError as exc:
        return exc.sqlstate or ""
    except Exception:
        return "unexpected"
    try:
        # A successful connect is itself the failure signal (no 42501).
        return "connected"
    finally:
        await conn.close()


async def _fetch_route_capabilities(
    target: dict[str, object], db: str, route_id: uuid.UUID
) -> dict[str, object] | None:
    """Read the STORED capabilities of one copied route (link proof)."""
    # Connect to the COPIED database (not the target service's default db).
    conn = await _connect({**target, "database": db})
    try:
        row = await conn.fetchrow(
            "SELECT capabilities::text AS c FROM public.model_routes WHERE id = $1",
            route_id,
        )
    finally:
        await conn.close()
    if row is None:
        return None
    return json.loads(row["c"])


# ---------------------------------------------------------------------------
# Module fixture: owned services + fixed file fixtures + exact cleanup
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _FilesEnv:
    source: dict[str, object]
    target: dict[str, object]
    custody: Path
    passfile: Path
    ids: dict[str, uuid.UUID]
    branding_dir: Path
    profile_dir: Path

    @property
    def absence_tokens(self) -> tuple[str, ...]:
        return (CN, _BRAND_CANARY, "canary.invalid", "alpha-profile-223", "beta-profile-223")


def _settings_for(env: _FilesEnv, custody: Path) -> dict[str, object]:
    return {
        "DEMO_SNAPSHOT_ENABLED": True,
        "DEMO_SNAPSHOT_SOURCE_HOST": env.source["host"],
        "DEMO_SNAPSHOT_SOURCE_PORT": env.source["port"],
        "DEMO_SNAPSHOT_SOURCE_DATABASE": env.source["database"],
        "DEMO_SNAPSHOT_SOURCE_USER": READER_ROLE,
        "DEMO_SNAPSHOT_TARGET_HOST": env.target["host"],
        "DEMO_SNAPSHOT_TARGET_PORT": env.target["port"],
        "DEMO_SNAPSHOT_TARGET_USER": env.target["user"],
        "DEMO_SNAPSHOT_PGPASSFILE": str(env.passfile),
        "DEMO_SNAPSHOT_CUSTODY_DIR": str(custody),
        "DEMO_SNAPSHOT_MAX_EXPORT_BYTES": 512 * 1024 * 1024,
        "DEMO_SNAPSHOT_MAX_ELAPSED_SECONDS": 120,
        "DEMO_SNAPSHOT_RETENTION_SECONDS": 3600,
        "DEMO_SNAPSHOT_MAX_COPIES": 4,
        # 223 file-stage sources (fixed fixtures for this handoff).
        "SLAIF_BRANDING_DIR": str(env.branding_dir),
        "COMPLETION_SERVICE_PROFILE_DIR": str(env.profile_dir),
        "CATALOG_REFRESH_ROOT": "",
        "CATALOG_REFRESH_SEAL_KEY": "",
        "UPSTREAM_LLM_PROFILES_FILE": "",
    }


@pytest.fixture(scope="module")
def files_env(tmp_path_factory: pytest.TempPathFactory) -> _FilesEnv:
    source = _ident("DEMO_223_TEST_SOURCE_URL", _ALLOWED_SOURCE_DB)
    target = _ident("DEMO_223_TEST_TARGET_URL", _ALLOWED_TARGET_DB)
    if source is None or target is None:
        pytest.skip(
            "DEMO_223_TEST_SOURCE_URL / DEMO_223_TEST_TARGET_URL must be owned "
            "127.0.0.1 PostgreSQL 16 test URLs with the allowlisted database names"
        )
    _require_pg16_tools()

    tmp_root = tmp_path_factory.mktemp("demo_files")
    custody_root = tmp_root / "custody"
    custody_root.mkdir(mode=0o700)

    passfile = tmp_root / "pgpass"
    passfile.write_text(
        f"{source['host']}:{source['port']}:{source['database']}:{READER_ROLE}:{_CANARY_SOURCE_PW}\n"
        f"{target['host']}:{target['port']}:*:{target['user']}:{target['password']}\n",
        encoding="utf-8",
    )
    os.chmod(passfile, 0o600)

    branding_dir = tmp_root / "branding"
    branding_dir.mkdir(mode=0o700)
    (branding_dir / "logo.svg").write_bytes(_CANARY_SVG)
    profile_dir = tmp_root / "profiles"
    profile_dir.mkdir(mode=0o700)
    (profile_dir / "alpha-profile-223.json").write_text(json.dumps({"org": CN}))
    (profile_dir / "beta-profile-223.json").write_text(json.dumps({"org": CN}))
    for path in (
        profile_dir / "alpha-profile-223.json",
        profile_dir / "beta-profile-223.json",
    ):
        os.chmod(path, 0o600)

    run_alembic_upgrade_head(str(source["url"]))

    async def setup() -> dict[str, uuid.UUID]:
        s = await _connect(source)
        try:
            await s.execute(f'DROP ROLE IF EXISTS "{READER_ROLE}"')
            await s.execute(
                f"CREATE ROLE \"{READER_ROLE}\" LOGIN PASSWORD '{_CANARY_SOURCE_PW}'"
            )
            await s.execute(f'GRANT USAGE ON SCHEMA public TO "{READER_ROLE}"')
            await s.execute(
                f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{READER_ROLE}"'
            )
        finally:
            await s.close()
        t = await _connect(target)
        try:
            datnames = {
                r["datname"] for r in await t.fetch("SELECT datname FROM pg_database")
            }
            foreign = datnames - {"postgres", "template0", "template1"}
            assert not foreign, (
                "target service must be dedicated; foreign databases: "
                + ", ".join(sorted(foreign))
            )
            await t.execute(f'DROP ROLE IF EXISTS "{WEB_ROLE}"')
            await t.execute(
                f"CREATE ROLE \"{WEB_ROLE}\" LOGIN PASSWORD '{_CANARY_WEB_PW}' NOCREATEDB"
            )
        finally:
            await t.close()
        return await _seed_canaries(source)

    try:
        ids = asyncio.run(setup())
    except BaseException as setup_exc:
        failures: list[str] = []

        async def cleanup_setup() -> None:
            for name, url, roles in (
                ("source", source, (READER_ROLE,)),
                ("target", target, (WEB_ROLE,)),
            ):
                for role in roles:
                    try:
                        c = await _connect(url)
                    except Exception as exc:
                        failures.append(f"{name} connect: {exc!r}")
                        continue
                    try:
                        if name == "source":
                            await c.execute(
                                f'REVOKE ALL ON ALL TABLES IN SCHEMA public '
                                f'FROM "{role}"'
                            )
                            await c.execute(
                                f'REVOKE USAGE ON SCHEMA public FROM "{role}"'
                            )
                        await c.execute(f'DROP ROLE IF EXISTS "{role}"')
                    except Exception as exc:
                        failures.append(f"{name} drop {role}: {exc!r}")
                    finally:
                        await c.close()

        try:
            asyncio.run(cleanup_setup())
        except Exception as exc:
            failures.append(f"cleanup loop: {exc!r}")
        if failures:
            raise AssertionError(
                "223 fixture setup failed and cleanup is incomplete: "
                + "; ".join(failures)
            ) from setup_exc
        raise

    env = _FilesEnv(
        source=source,
        target=target,
        custody=custody_root,
        passfile=passfile,
        ids=ids,
        branding_dir=branding_dir,
        profile_dir=profile_dir,
    )
    yield env

    failures: list[str] = []

    def recorded_target_dbs() -> set[str]:
        names: set[str] = set()
        for case_dir in sorted(custody_root.iterdir()):
            if case_dir.is_symlink() or not case_dir.is_dir():
                continue
            for job_dir in ds._list_job_dirs(case_dir):
                manifest = ds._read_manifest(job_dir)
                if manifest is not None and manifest.target_db:
                    names.add(manifest.target_db)
        return names

    _TEARDOWN_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

    async def drop_recorded_dbs() -> None:
        t = await _connect(target)
        try:
            for name in sorted(recorded_target_dbs()):
                if not _TEARDOWN_IDENT_RE.fullmatch(name):
                    continue
                await t.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            remaining = {
                r["datname"]
                for r in await t.fetch("SELECT datname FROM pg_database")
            }
            assert remaining == {"postgres", "template0", "template1"}, (
                "target not system-only after cleanup: "
                + ", ".join(sorted(remaining))
            )
        finally:
            await t.close()

    async def drop_roles() -> None:
        s = await _connect(source)
        try:
            await s.execute(
                f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{READER_ROLE}"'
            )
            await s.execute(f'REVOKE USAGE ON SCHEMA public FROM "{READER_ROLE}"')
            await s.execute(f'DROP ROLE IF EXISTS "{READER_ROLE}"')
        finally:
            await s.close()
        t = await _connect(target)
        try:
            await t.execute(f'DROP ROLE IF EXISTS "{WEB_ROLE}"')
        finally:
            await t.close()

    async def drop_rows() -> None:
        leftover = await _delete_seed_rows(source, ids)
        bad = {t: n for t, n in leftover.items() if n}
        if bad:
            raise AssertionError(f"run-tag rows remain after cleanup: {bad}")

    try:
        asyncio.run(drop_recorded_dbs())
    except Exception as exc:
        failures.append(f"target-database cleanup: {exc!r}")
    try:
        asyncio.run(drop_rows())
    except Exception as exc:
        failures.append(f"source-row cleanup: {exc!r}")
    try:
        asyncio.run(drop_roles())
    except Exception as exc:
        failures.append(f"role cleanup: {exc!r}")
    if failures:
        pytest.fail("223 fixture cleanup incomplete: " + "; ".join(failures))


# ---------------------------------------------------------------------------
# Full chain: 221 raw copy -> 222 sanitize -> 223 files (handoff proof)
# ---------------------------------------------------------------------------


def test_files_chain_handoff_and_privacy(files_env: _FilesEnv) -> None:
    env = files_env
    custody = env.custody / f"case-{uuid.uuid4().hex[:12]}"
    custody.mkdir(mode=0o700)

    def scenario_sync() -> str:
        settings = Settings(**_settings_for(env, custody))
        config = ds.config_from_settings(settings)
        result = ds.run_snapshot_job(config)
        assert result.state == ds.STATE_RAW_UNVERIFIED, result.failure_code
        raw_db = result.target_db
        assert raw_db
        return raw_db

    async def scenario() -> None:
        before = await _run_row_fingerprint(env.source, env.ids)

        raw_db = await asyncio.to_thread(scenario_sync)

        # Web role cannot connect to the raw private copy (221 law).
        assert await _web_connect_refused(env, raw_db) == "42501"

        after_raw = await _run_row_fingerprint(env.source, env.ids)
        assert after_raw == before, "source DML during raw snapshot"

        settings = Settings(**_settings_for(env, custody))
        config = ds.config_from_settings(settings)
        san_result = await asyncio.to_thread(dsan.sanitize_copies, config)
        assert san_result.state == "SANITIZED", (
            san_result.state, san_result.failure_code
        )
        assert san_result.copies_sanitized == 1
        assert san_result.copies_failed == 0

        # --- 223 file stage -------------------------------------------------
        fconfig = dsf.files_config_from_settings(settings)
        files_result = await asyncio.to_thread(
            dsf.run_files_job, fconfig, settings
        )
        assert files_result.state == "FILES_VERIFIED", files_result
        assert files_result.copies_files_verified == 1
        assert files_result.copies_failed == 0

        job_dirs = ds._list_job_dirs(custody)
        assert len(job_dirs) == 1
        manifest = ds._read_manifest(job_dirs[0])
        assert manifest is not None
        assert manifest.state == ds.STATE_DB_AND_FILES_VERIFIED_UNPUBLISHED
        assert manifest.files_state == dsf.FILES_STATE_VERIFIED
        # Five branding slot leaves (all neutral substitutes) + the
        # completion choices projection.
        assert manifest.files_count == 6
        assert manifest.files_bytes > 0

        # Web role still cannot connect after the file stage.
        assert await _web_connect_refused(env, raw_db) == "42501"

        # No source DML across the whole chain (read-only file capture).
        after = await _run_row_fingerprint(env.source, env.ids)
        assert after == before, "source DML during file capture"

        # --- display tree: privacy + exact neutral substitutes --------------
        files_manifest = json.loads(
            (job_dirs[0] / dsf.FILES_DIR_NAME / dsf.FILES_MANIFEST_NAME).read_text()
        )
        leaves = files_manifest["files"]
        assert len(leaves) == manifest.files_count
        by_logical = {}
        for entry in leaves:
            data = (
                job_dirs[0] / dsf.FILES_DIR_NAME / entry["leaf"]
            ).read_bytes()
            by_logical[entry["logical_name"]] = data
            text = data.decode("utf-8", errors="replace")
            for token in env.absence_tokens:
                assert token not in text, (
                    f"absence token in display leaf {entry['logical_name']}"
                )
                assert token not in entry["logical_name"]
                assert token not in str(entry.get("source_ref", ""))
        assert set(by_logical) == {
            "branding/style.css",
            "branding/logo",
            "branding/logo-compact",
            "branding/favicon",
            "branding/hero",
            "profiles/completion-choices.json",
        }
        from slaif_gateway.web import branding as web_branding

        # Every branding slot displays the packaged neutral substitute
        # (the configured operator SVG was replaced, absent slots are
        # neutral too).
        for slot in (
            "style.css",
            "logo",
            "logo-compact",
            "favicon",
            "hero",
        ):
            expected, _ct = web_branding.fallback_asset(slot)
            assert by_logical[f"branding/{slot}"] == expected, slot
        choices = json.loads(by_logical["profiles/completion-choices.json"])
        profiles = choices["profiles"]
        assert len(profiles) == 2
        for item in profiles:
            assert re.fullmatch(r"demo-profile-[0-9a-f]{24}", item)

        # --- 223-b: copied completion-service route links to the leaf -----
        seed = manifest.job_id.encode("utf-8")
        expected_profile = dsan.demo_profile_id(seed, "alpha-profile-223")
        assert re.fullmatch(r"demo-profile-[0-9a-f]{24}", expected_profile)
        # The captured choices leaf carries the copied route's fictional
        # profile (same per-copy derivation, same job seed).
        assert expected_profile in profiles
        assert "alpha-profile-223" not in json.dumps(choices)
        # The STORED DB value (independent of the worker success flag)
        # matches the leaf, proving the combined DB/files link on real PG.
        copied_cs_route = dsan.remap_uuid(seed, env.ids["route_completion"])
        stored_cs = await _fetch_route_capabilities(
            env.target, raw_db, copied_cs_route
        )
        assert stored_cs is not None, "completion-service route missing from copy"
        assert stored_cs["completion_service"]["profile"] == expected_profile
        assert "alpha-profile-223" not in json.dumps(stored_cs)
        # The ordinary nested route's compaction list is remapped to its
        # copied id (list meaning preserved); provider slug is preserved.
        copied_route = dsan.remap_uuid(seed, env.ids["route"])
        stored_route = await _fetch_route_capabilities(
            env.target, raw_db, copied_route
        )
        assert stored_route is not None, "ordinary nested route missing from copy"
        assert str(copied_route) in stored_route[
            "codex_compaction_compatible_route_ids"
        ]
        assert stored_route["chat_completions"]["chat_text"] is True

        # The private source records may retain the custody-private id
        # map, but the DISPLAY leaves never do (asserted above via the
        # absence tokens in every leaf byte).

        # --- safe worker result (CLI emits only this fixed vocabulary) ------
        safe_repr = str(files_result)
        for token in env.absence_tokens:
            assert token not in safe_repr
        assert raw_db not in safe_repr

        # --- target: exactly the system databases + the one recorded copy ---
        t = await _connect(env.target)
        try:
            datnames = {
                r["datname"] for r in await t.fetch("SELECT datname FROM pg_database")
            }
        finally:
            await t.close()
        assert datnames == {"postgres", "template0", "template1", raw_db}

    asyncio.run(scenario())
