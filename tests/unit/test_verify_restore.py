from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location("verify_restore", Path("scripts/verify_restore.py"))
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


class FakeConnection:
    def __init__(self, *, missing: str | None = None) -> None:
        self.missing = missing
        self.queries: list[str] = []

    async def scalar(self, statement, params=None):
        query = str(statement)
        self.queries.append(query)
        if "information_schema.tables" in query:
            return params["table"] != self.missing
        if "gateway_keys" in query:
            return 7
        if "usage_ledger" in query:
            return 11
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


def test_verify_database_checks_tables_and_safe_counts() -> None:
    connection = FakeConnection()
    counts = asyncio.run(_MODULE.verify_database(connection))

    assert dict(counts) == {"gateway_keys": 7, "usage_ledger": 11}
    assert all("PRAGMA" not in query for query in connection.queries)
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


def test_restore_verifier_source_has_no_sqlite_integrity_check() -> None:
    source = Path("scripts/verify_restore.py").read_text(encoding="utf-8")
    assert "PRAGMA integrity_check" not in source
    assert "information_schema.tables" in source
