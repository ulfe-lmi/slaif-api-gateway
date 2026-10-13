"""Atomic-apply pre-database contract (objective 182, A1/A3).

Covers what is provable without a database: intent validation before any
authentication, seal/state/plan refusals BEFORE any database contact, exact
plan identity against the authenticated sealed bytes, the fixed-order lock
prelude with bounded waits, and the lock-free read-only status path. The
in-transaction gates (committed-outcome lookup, freshness, staleness, close
guards, rollback, idempotent retry) are proven on real PostgreSQL in
tests/integration/test_catalog_refresh_apply_postgres.py.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.services.catalog_refresh import apply as apply_mod
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError
from slaif_gateway.services.catalog_refresh.filesystem import (
    load_seal_key_bytes,
    open_anchored_handle,
)
from slaif_gateway.services.catalog_refresh.sealing import CatalogRefreshSealError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "catalog_refresh"
runner = CliRunner()

_LEAK_USER = "leak_user"
LEAK_PASS = "s3cr3t-apply-pw"
LEAK_DB_URL = f"postgresql+asyncpg://{_LEAK_USER}:{LEAK_PASS}@leak-host:5432/leakdb"


class _Absent:
    pass


_ABSENT = _Absent()


def _sealed_doc(plan: dict[str, Any] | None) -> dict[str, Any]:
    doc: dict[str, Any] = {"state": "READY", "warnings": []}
    if plan is not None:
        doc["apply_plan"] = plan
    return doc


def _fake_capture(
    *,
    state: str = "READY",
    plan: dict[str, Any] | None | _Absent = _ABSENT,
    mode: str = "first_install",
    target: SimpleNamespace | None = None,
    bundle_sha: str = "b" * 64,
    hmac: str = "h" * 64,
):
    if plan is _ABSENT:
        plan = {
            "schema_version": "1",
            "plan_sha256": "p" * 64,
            "operations": [
                {
                    "type": "create_provider",
                    "provider": "openrouter",
                    "display_name": "openrouter",
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key_env_var": "OPENROUTER_API_KEY",
                    "kind": "openai_compatible",
                    "enabled": True,
                    "timeout_seconds": 300,
                    "max_retries": 2,
                }
            ],
        }
    if target is None:
        target = SimpleNamespace(server_host="reviewed-host", server_port=5432, database="reviewed_db")
    baseline = SimpleNamespace(mode=mode, target=target)
    bundle = SimpleNamespace(run_id="fixture-first-install-001", baseline=baseline)
    execution_context = SimpleNamespace(acquisition=None, generator=None)
    return SimpleNamespace(
        result=SimpleNamespace(state=state),
        content={"validation.json": json.dumps(_sealed_doc(plan)).encode("utf-8")},
        receipt={"semantic_bundle_sha256": bundle_sha, "hmac_sha256": hmac},
        bundle=bundle,
        baseline=baseline,
        policy=SimpleNamespace(),
        report=SimpleNamespace(),
        artifacts={},
        execution_context=execution_context,
    )


def _no_db_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("apply must not open a database engine for this refusal")

    monkeypatch.setattr(apply_mod, "create_async_engine", _boom)


class _FakeResult:
    def __init__(self, value: Any = None) -> None:
        self._value = value

    def scalar_one(self) -> Any:
        return self._value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalars(self) -> "_FakeResult":
        return self

    def all(self) -> list[Any]:
        return []


class _FakeConnection:
    def __init__(self, statements: list[str]) -> None:
        self._statements = statements

    async def execute(self, statement: Any) -> _FakeResult:
        rendered = str(statement)
        self._statements.append(rendered)
        if "current_user" in rendered:
            return _FakeResult("apply_test_role")
        return _FakeResult(None)

    def begin(self) -> "_FakeBegin":
        return _FakeBegin(self._statements)


class _FakeBegin:
    def __init__(self, statements: list[str]) -> None:
        self._statements = statements

    async def __aenter__(self) -> _FakeConnection:
        return _FakeConnection(self._statements)

    async def __aexit__(self, *_exc: Any) -> bool:
        return False  # any error rolls the (fake) transaction back


class _FakeConnect(_FakeBegin):
    pass


class _FakeEngine:
    def __init__(self, statements: list[str]) -> None:
        self.statements = statements
        self.disposed = False

    def begin(self) -> _FakeBegin:
        return _FakeBegin(self.statements)

    def connect(self) -> _FakeConnect:
        return _FakeConnect(self.statements)

    async def dispose(self) -> None:
        self.disposed = True


@pytest.mark.asyncio
async def test_blank_actor_or_reason_refuses_before_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []

    def _record(_run_dir: Path, _key: bytes) -> None:
        calls.append(_run_dir)
        raise AssertionError("intent must be validated before any capture")

    monkeypatch.setattr(apply_mod, "load_verified_capture", _record)
    for actor, reason in (("", "why"), ("who", "   ")):
        with pytest.raises(CatalogRefreshBlockedError) as excinfo:
            await apply_mod.apply_reviewed_run(
                run_dir=Path("/nonexistent/run"),
                seal_key=b"k" * 32,
                database_url=LEAK_DB_URL,
                reason=reason,
                actor=actor,
            )
        assert excinfo.value.code == "apply_intent_incomplete"
        assert LEAK_PASS not in str(excinfo.value)
    assert calls == []


@pytest.mark.asyncio
async def test_blocked_sealed_state_refuses_before_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        apply_mod, "load_verified_capture", lambda _d, _k, run_handle=None: _fake_capture(state="BLOCKED")
    )
    _no_db_contact(monkeypatch)
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        await apply_mod.apply_reviewed_run(
            run_dir=Path("/nonexistent/run"),
            seal_key=b"k" * 32,
            database_url=LEAK_DB_URL,
            reason="why",
            actor="who",
        )
    assert excinfo.value.code == "apply_state_not_applicable"
    assert LEAK_PASS not in str(excinfo.value)


@pytest.mark.asyncio
async def test_run_without_executable_plan_refuses_before_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        apply_mod, "load_verified_capture", lambda _d, _k, run_handle=None: _fake_capture(plan=None)
    )
    _no_db_contact(monkeypatch)
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        await apply_mod.apply_reviewed_run(
            run_dir=Path("/nonexistent/run"),
            seal_key=b"k" * 32,
            database_url=LEAK_DB_URL,
            reason="why",
            actor="who",
        )
    assert excinfo.value.code == "apply_no_plan"
    assert LEAK_PASS not in str(excinfo.value)
    assert "leak-host" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_unsupported_sealed_plan_schema_refuses_before_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = {
        "schema_version": "999",
        "plan_sha256": "p" * 64,
        "operations": [{"type": "create_provider", "provider": "openrouter"}],
    }
    monkeypatch.setattr(
        apply_mod, "load_verified_capture", lambda _d, _k, run_handle=None: _fake_capture(plan=plan)
    )
    _no_db_contact(monkeypatch)
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        await apply_mod.apply_reviewed_run(
            run_dir=Path("/nonexistent/run"),
            seal_key=b"k" * 32,
            database_url=LEAK_DB_URL,
            reason="why",
            actor="who",
        )
    assert excinfo.value.code == "apply_plan_unsupported"


def _make_first_install_run(tmp_path: Path) -> tuple[Path, bytes]:
    result = runner.invoke(
        app,
        ["catalog-refresh", "review", str(FIXTURES / "bundle-first-install.json"),
         "--first-install", "--run-root", str(tmp_path / "runs"),
         "--seal-key", str(tmp_path / "seal.key")],
    )
    assert result.exit_code == 10, result.output  # RWW: new-model exposure
    run_dir = tmp_path / "runs" / "fixture-first-install-001"
    return run_dir, load_seal_key_bytes(tmp_path / "seal.key")


@pytest.mark.asyncio
async def test_apply_uses_the_sealed_plan_identity_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, key = _make_first_install_run(tmp_path)
    sealed_doc = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    sealed_plan = sealed_doc["apply_plan"]
    receipt = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))

    recorded: dict[str, Any] = {}

    async def _fake_execute(
        _capture: Any,
        *,
        operations: list[dict[str, Any]],
        plan_sha256: str,
        bundle_sha256: str,
        database_url: str,
        reason: str,
        actor: str,
        admin_id: Any,
        ack_warnings: tuple[str, ...] = (),
    ) -> apply_mod.ApplyResult:
        recorded["operations"] = operations
        recorded["plan_sha256"] = plan_sha256
        recorded["bundle_sha256"] = bundle_sha256
        recorded["database_url"] = database_url
        recorded["reason"] = reason
        recorded["actor"] = actor
        recorded["admin_id"] = admin_id
        recorded["ack_warnings"] = ack_warnings
        return apply_mod.ApplyResult(
            status="committed",
            run_id="fixture-first-install-001",
            bundle_sha256=bundle_sha256,
            plan_sha256=plan_sha256,
            effective_at=None,
            counts={},
        )

    monkeypatch.setattr(apply_mod, "_execute_transaction", _fake_execute)
    result = await apply_mod.apply_reviewed_run(
        run_dir=run_dir,
        seal_key=key,
        database_url=LEAK_DB_URL,
        reason="apply the reviewed first install",
        actor="ops@ulfe",
        ack_warnings=("new_model_exposure",),
    )

    assert result.status == "committed"
    # the operations, plan hash, and bundle hash are exactly the sealed
    # authenticated bytes -- not re-derived from run files at apply time
    assert recorded["operations"] == sealed_plan["operations"]
    assert recorded["plan_sha256"] == sealed_plan["plan_sha256"]
    assert recorded["bundle_sha256"] == receipt["semantic_bundle_sha256"]
    assert recorded["ack_warnings"] == ("new_model_exposure",)
    assert recorded["reason"] == "apply the reviewed first install"
    assert recorded["actor"] == "ops@ulfe"
    assert recorded["admin_id"] is None


@pytest.mark.asyncio
async def test_wrong_seal_key_refuses_before_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, _key = _make_first_install_run(tmp_path)
    _no_db_contact(monkeypatch)
    with pytest.raises(CatalogRefreshSealError):
        await apply_mod.apply_reviewed_run(
            run_dir=run_dir,
            seal_key=b"z" * 32,  # wrong runner-owned key
            database_url=LEAK_DB_URL,
            reason="why",
            actor="who",
        )


@pytest.mark.asyncio
async def test_refresh_target_mismatch_locks_then_refuses_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements: list[str] = []
    fake_engine = _FakeEngine(statements)

    def _fake_create_engine(*_args: Any, **_kwargs: Any) -> _FakeEngine:
        return fake_engine

    monkeypatch.setattr(apply_mod, "create_async_engine", _fake_create_engine)
    monkeypatch.setattr(
        apply_mod,
        "load_verified_capture",
        lambda _d, _k, run_handle=None: _fake_capture(
            mode="refresh",
            target=SimpleNamespace(
                server_host="reviewed-host", server_port=5432, database="reviewed_db"
            ),
        ),
    )
    with pytest.raises(CatalogRefreshBlockedError) as excinfo:
        await apply_mod.apply_reviewed_run(
            run_dir=Path("/nonexistent/run"),
            seal_key=b"k" * 32,
            database_url=(
                "postgresql+asyncpg://other_user:other_pw@other-host:5433/other_db"
            ),
            reason="why",
            actor="who",
        )
    assert excinfo.value.code == "apply_target_mismatch"
    assert "other_pw" not in str(excinfo.value)
    assert "other-host" not in str(excinfo.value)
    # bounded waits first, then the fixed-order SHARE ROW EXCLUSIVE catalog
    # locks, then the actual database actor, and NO mutation statement.
    assert statements[:2] == [
        "SET LOCAL lock_timeout = '10s'",
        "SET LOCAL statement_timeout = '60s'",
    ]
    assert statements[2:6] == [
        "LOCK TABLE fx_rates IN SHARE ROW EXCLUSIVE MODE",
        "LOCK TABLE model_routes IN SHARE ROW EXCLUSIVE MODE",
        "LOCK TABLE pricing_rules IN SHARE ROW EXCLUSIVE MODE",
        "LOCK TABLE provider_configs IN SHARE ROW EXCLUSIVE MODE",
    ]
    assert statements[6] == "SELECT current_user"
    assert len(statements) == 7
    for statement in statements:
        upper = statement.upper()
        assert not (
            upper.startswith("INSERT")
            or upper.startswith("UPDATE")
            or upper.startswith("DELETE")
        )
    assert fake_engine.disposed is True


@pytest.mark.asyncio
async def test_apply_status_is_lock_free_and_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Status wiring: authenticate, look up by canonical bundle identity
    ONLY (the read-only lookup SQL itself is exercised on real PostgreSQL
    in the integration proof), never take catalog locks, always dispose."""
    run_dir, key = _make_first_install_run(tmp_path)
    receipt = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))

    statements: list[str] = []
    fake_engine = _FakeEngine(statements)
    monkeypatch.setattr(
        apply_mod, "create_async_engine", lambda *_a, **_k: fake_engine
    )

    lookups: list[dict[str, Any]] = []

    async def _fake_lookup(engine: Any, *, bundle_sha256: str) -> list[Any]:
        lookups.append({"engine": engine, "bundle_sha256": bundle_sha256})
        return []

    def _lock_boom(_connection: Any) -> None:
        raise AssertionError("status must never take catalog table locks")

    monkeypatch.setattr(apply_mod, "_lookup_committed_by_bundle", _fake_lookup)
    monkeypatch.setattr(apply_mod, "lock_catalog_tables", _lock_boom)

    status = await apply_mod.apply_status(
        run_dir=run_dir, seal_key=key, database_url=LEAK_DB_URL
    )
    assert status.run_id == "fixture-first-install-001"
    assert status.committed is False
    assert status.records == []
    # the lookup is by the authenticated receipt identity, on the engine
    # created for the operator URL -- and nothing else touched the engine
    assert len(lookups) == 1
    assert lookups[0]["bundle_sha256"] == receipt["semantic_bundle_sha256"]
    assert lookups[0]["engine"] is fake_engine
    assert statements == []
    assert fake_engine.disposed is True

# ---------------------------------------------------------------------------
# Lifecycle binding: the CLI's already-checked run/key-parent handles carry
# the apply and status paths -- key read and authenticated capture reuse the
# held descriptors (no path reopen), the boundary is re-asserted hop by hop
# before each sensitive phase, and a swapped directory is refused before any
# database contact.
# ---------------------------------------------------------------------------


def _write_seal_key(parent: Path, name: str = "seal.key") -> tuple[Path, bytes]:
    key = bytes.fromhex("ab" * 32)
    path = parent / name
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key.hex().encode("ascii"))
    return path, key


def _no_reanchor(_path: Path) -> None:
    raise AssertionError("a checked lifecycle handle must not be re-anchored by name")


@pytest.mark.asyncio
async def test_run_binding_change_before_capture_refuses_without_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run directory swapped after the check is refused at the
    capture boundary re-check -- before authentication and before any
    database contact."""
    run_dir, key = _make_first_install_run(tmp_path)
    _no_db_contact(monkeypatch)
    handle = open_anchored_handle(run_dir)
    try:
        run_dir.rename(run_dir.parent / "swapped-first-install-001")
        with pytest.raises(CatalogRefreshSealError) as excinfo:
            await apply_mod.apply_reviewed_run(
                run_dir=run_dir,
                seal_key=key,
                database_url=LEAK_DB_URL,
                reason="why",
                actor="who",
                run_handle=handle,
            )
        assert "checked directory binding changed" in str(excinfo.value)
    finally:
        handle.close()


@pytest.mark.asyncio
async def test_capture_through_held_run_handle_reuses_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With an intact checked handle the REAL authenticated capture runs
    through the HELD descriptor (no re-anchor, no database engine) and the
    exact captured receipt identity reaches the transaction."""
    run_dir, key = _make_first_install_run(tmp_path)
    receipt = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))
    _no_db_contact(monkeypatch)
    import slaif_gateway.services.catalog_refresh.filesystem as fs_mod

    monkeypatch.setattr(fs_mod, "_open_anchored", _no_reanchor)
    recorded: dict[str, Any] = {}

    async def _fake_execute(
        _capture: Any,
        *,
        operations: list[dict[str, Any]],
        plan_sha256: str,
        bundle_sha256: str,
        database_url: str,
        reason: str,
        actor: str,
        admin_id: Any,
        ack_warnings: tuple[str, ...] = (),
    ) -> apply_mod.ApplyResult:
        _ = (operations, plan_sha256, database_url, reason, actor, admin_id, ack_warnings)
        recorded["capture"] = _capture
        recorded["bundle_sha256"] = bundle_sha256
        return apply_mod.ApplyResult(
            status="committed",
            run_id="fixture-first-install-001",
            bundle_sha256=bundle_sha256,
            plan_sha256=plan_sha256,
            effective_at=None,
            counts={},
        )

    monkeypatch.setattr(apply_mod, "_execute_transaction", _fake_execute)
    handle = open_anchored_handle(run_dir)
    try:
        await apply_mod.apply_reviewed_run(
            run_dir=run_dir,
            seal_key=key,
            database_url=LEAK_DB_URL,
            reason="why",
            actor="who",
            run_handle=handle,
        )
    finally:
        handle.close()
    # the capture that reached the transaction is the real authenticated
    # capture read through the held descriptor
    assert recorded["capture"].receipt["semantic_bundle_sha256"] == receipt["semantic_bundle_sha256"]
    assert recorded["bundle_sha256"] == receipt["semantic_bundle_sha256"]


@pytest.mark.asyncio
async def test_status_through_held_run_handle_reuses_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, key = _make_first_install_run(tmp_path)
    statements: list[str] = []
    fake_engine = _FakeEngine(statements)
    monkeypatch.setattr(apply_mod, "create_async_engine", lambda *_a, **_k: fake_engine)
    import slaif_gateway.services.catalog_refresh.filesystem as fs_mod

    monkeypatch.setattr(fs_mod, "_open_anchored", _no_reanchor)

    lookups: list[str] = []

    async def _fake_lookup(engine: Any, *, bundle_sha256: str) -> list[Any]:
        lookups.append(bundle_sha256)
        return []

    monkeypatch.setattr(apply_mod, "_lookup_committed_by_bundle", _fake_lookup)
    handle = open_anchored_handle(run_dir)
    try:
        status = await apply_mod.apply_status(
            run_dir=run_dir,
            seal_key=key,
            database_url=LEAK_DB_URL,
            run_handle=handle,
        )
    finally:
        handle.close()
    assert status.committed is False
    assert len(lookups) == 1
    assert statements == []
    assert fake_engine.disposed is True


def test_key_binding_change_refuses_before_key_read(tmp_path: Path) -> None:
    """A seal-key parent swapped after the check is refused by the loader
    boundary re-check, before any key byte is read."""
    key_parent = tmp_path / "seal-parent"
    key_parent.mkdir(mode=0o700)
    key_path, _key = _write_seal_key(key_parent)
    handle = open_anchored_handle(key_parent)
    try:
        key_parent.rename(tmp_path / "seal-parent-swapped")
        with pytest.raises(CatalogRefreshSealError) as excinfo:
            load_seal_key_bytes(key_path, parent_handle=handle)
        assert "checked directory binding changed" in str(excinfo.value)
    finally:
        handle.close()


def test_key_read_through_held_parent_reuses_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_parent = tmp_path / "seal-parent"
    key_parent.mkdir(mode=0o700)
    key_path, key = _write_seal_key(key_parent)
    import slaif_gateway.services.catalog_refresh.filesystem as fs_mod

    monkeypatch.setattr(fs_mod, "_open_anchored", _no_reanchor)
    handle = open_anchored_handle(key_parent)
    try:
        assert load_seal_key_bytes(key_path, parent_handle=handle) == key
    finally:
        handle.close()


def test_apply_cli_lifecycle_reuses_checked_handles_without_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end CLI apply without a database: the CLI's checked run and
    key-parent handles carry the whole lifecycle -- key read and
    authenticated capture both run through the held descriptors (no
    re-anchor) and no database engine is ever created."""
    run_dir, _key = _make_first_install_run(tmp_path)
    _no_db_contact(monkeypatch)
    import slaif_gateway.services.catalog_refresh.filesystem as fs_mod

    monkeypatch.setattr(fs_mod, "_open_anchored", _no_reanchor)

    async def _fake_execute(
        _capture: Any,
        *,
        operations: list[dict[str, Any]],
        plan_sha256: str,
        bundle_sha256: str,
        database_url: str,
        reason: str,
        actor: str,
        admin_id: Any,
        ack_warnings: tuple[str, ...] = (),
    ) -> apply_mod.ApplyResult:
        _ = (operations, database_url, reason, actor, admin_id, ack_warnings)
        return apply_mod.ApplyResult(
            status="committed",
            run_id="fixture-first-install-001",
            bundle_sha256=bundle_sha256,
            plan_sha256=plan_sha256,
            effective_at=None,
            counts={},
        )

    monkeypatch.setattr(apply_mod, "_execute_transaction", _fake_execute)
    result = runner.invoke(
        app,
        [
            "catalog-refresh",
            "apply",
            "--run-dir",
            str(run_dir),
            "--seal-key",
            str(tmp_path / "seal.key"),
            "--db-url",
            LEAK_DB_URL,
            "--confirm",
            "--reason",
            "why",
            "--actor",
            "who",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "status: committed" in result.output
    assert LEAK_PASS not in result.output


def test_status_cli_lifecycle_reuses_checked_handles_without_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end CLI status without a database: checked handles carry the
    lifecycle (no re-anchor), the read-only lookup runs on the created
    engine and the engine is always disposed."""
    run_dir, _key = _make_first_install_run(tmp_path)
    statements: list[str] = []
    fake_engine = _FakeEngine(statements)
    monkeypatch.setattr(apply_mod, "create_async_engine", lambda *_a, **_k: fake_engine)
    import slaif_gateway.services.catalog_refresh.filesystem as fs_mod

    monkeypatch.setattr(fs_mod, "_open_anchored", _no_reanchor)

    async def _fake_lookup(engine: Any, *, bundle_sha256: str) -> list[Any]:
        _ = engine, bundle_sha256
        return []

    monkeypatch.setattr(apply_mod, "_lookup_committed_by_bundle", _fake_lookup)
    result = runner.invoke(
        app,
        [
            "catalog-refresh",
            "status",
            "--run-dir",
            str(run_dir),
            "--seal-key",
            str(tmp_path / "seal.key"),
            "--db-url",
            LEAK_DB_URL,
        ],
    )
    assert result.exit_code == 0, result.output
    assert "committed: false" in result.output
    assert statements == []
    assert fake_engine.disposed is True
