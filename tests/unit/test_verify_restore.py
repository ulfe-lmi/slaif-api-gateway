from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location("verify_restore", Path("scripts/verify_restore.py"))
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


class FakeConnection:
    def __init__(self, *, missing: str | None = None, wrong_schema: bool = False) -> None:
        self.missing = missing
        self.wrong_schema = wrong_schema
        self.queries: list[str] = []

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    async def scalar(self, statement, params=None):
        query = str(statement)
        self.queries.append(query)
        if "COUNT(*)" in query:
            if "gateway_keys" in query:
                return 7
            if "usage_ledger" in query:
                return 11
        if "SELECT EXISTS" in query:
            return True
        raise AssertionError(query)

    async def execute(self, statement, params=None):
        query = str(statement)
        self.queries.append(query)
        if "information_schema.tables" in query:
            tables = [table for table in _MODULE.REQUIRED_TABLES if table != self.missing]
            if self.wrong_schema:
                return self.Result([])
            return self.Result([(table,) for table in tables])
        if "gateway_keys" in query:
            raise AssertionError("gateway_keys should use scalar")
        raise AssertionError(query)


def test_validate_restore_target_preserves_safe_boundary() -> None:
    assert _MODULE.validate_restore_target(None) == (False, "RESTORE_DATABASE_URL missing")
    assert _MODULE.validate_restore_target("sqlite+aiosqlite:///local_test") == (
        False,
        "unsafe restore target",
    )
    valid, database = _MODULE.validate_restore_target(
        "postgresql+asyncpg://user:password@localhost/restore_local_123"
    )
    assert valid is True
    assert database == "restore_local_123"


def test_validate_restore_target_uses_explicit_disposable_database_grammar() -> None:
    for database in ("restore_test", "test_slaif_gateway", "slaif_gateway_test", "slaif_test"):
        valid, selected = _MODULE.validate_restore_target(f"postgresql+asyncpg://user@localhost/{database}")
        assert valid is True
        assert selected == database

    for database in ("contest", "production_test", "locality", "restore_local", "restore_local_bad-name"):
        valid, detail = _MODULE.validate_restore_target(f"postgresql+asyncpg://user@localhost/{database}")
        assert valid is False
        assert detail == "unsafe restore target"


def test_verify_database_checks_tables_and_safe_counts() -> None:
    connection = FakeConnection()
    counts = asyncio.run(_MODULE.verify_database(connection))

    assert dict(counts) == {"gateway_keys": 7, "usage_ledger": 11}
    assert all("PRAGMA" not in query for query in connection.queries)
    assert all(f'"public"."{table}"' in " ".join(connection.queries) for table in ("institutions", "owners", "gateway_keys", "usage_ledger", "audit_log"))
    assert _MODULE.format_success(counts) == (
        "RESULT=OK required_tables=institutions,owners,gateway_keys,usage_ledger,audit_log "
        "row_counts=gateway_keys:7,usage_ledger:11"
    )


def test_verify_database_reports_missing_table_without_swallowing_sql() -> None:
    connection = FakeConnection(missing="usage_ledger")

    try:
        asyncio.run(_MODULE.verify_database(connection))
    except LookupError as exc:
        assert str(exc) == "missing table: usage_ledger"
    else:
        raise AssertionError("missing table was not rejected")


def test_verify_database_rejects_required_table_in_wrong_schema() -> None:
    connection = FakeConnection(wrong_schema=True)

    try:
        asyncio.run(_MODULE.verify_database(connection))
    except LookupError as exc:
        assert str(exc) == "missing table: institutions"
    else:
        raise AssertionError("wrong-schema table was not rejected")


def test_restore_verifier_source_has_no_sqlite_integrity_check() -> None:
    source = Path("scripts/verify_restore.py").read_text(encoding="utf-8")
    assert "PRAGMA integrity_check" not in source
    assert "information_schema.tables" in source
