from __future__ import annotations

import pytest

from slaif_gateway.db import schema_status


class _ScalarRows:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def all(self) -> list[str]:
        return self._values


class _Result:
    def __init__(self, *, scalar_value: bool | None = None, rows: list[str] | None = None) -> None:
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar(self) -> bool | None:
        return self._scalar_value

    def scalars(self) -> _ScalarRows:
        return _ScalarRows(self._rows)


class _FakeConnection:
    def __init__(self, *, table_exists: bool, revisions: list[str] | None = None) -> None:
        self._table_exists = table_exists
        self._revisions = revisions or []
        self.statements: list[str] = []

    async def execute(self, statement) -> _Result:
        sql = str(statement)
        self.statements.append(sql)
        if "information_schema.tables" in sql:
            return _Result(scalar_value=self._table_exists)
        if "SELECT version_num FROM alembic_version" in sql:
            return _Result(rows=self._revisions)
        raise AssertionError(f"Unexpected SQL: {sql}")


def test_get_alembic_head_revision_reads_single_head() -> None:
    head = schema_status.get_alembic_head_revision()

    assert head == "0006_email_delivery_attempt_state"


@pytest.mark.asyncio
async def test_check_schema_current_detects_current_revision(monkeypatch) -> None:
    monkeypatch.setattr(schema_status, "get_alembic_heads", lambda: ("head",))
    connection = _FakeConnection(table_exists=True, revisions=["head"])

    status = await schema_status.check_schema_current(connection)

    assert status.status == "ok"
    assert status.current_revision == "head"
    assert status.head_revision == "head"
    assert status.is_current


@pytest.mark.asyncio
async def test_check_schema_current_handles_missing_alembic_version_table(monkeypatch) -> None:
    monkeypatch.setattr(schema_status, "get_alembic_heads", lambda: ("head",))
    connection = _FakeConnection(table_exists=False)

    status = await schema_status.check_schema_current(connection)

    assert status.status == "missing"
    assert status.current_revision is None
    assert status.head_revision == "head"


@pytest.mark.asyncio
async def test_check_schema_current_detects_outdated_revision(monkeypatch) -> None:
    monkeypatch.setattr(schema_status, "get_alembic_heads", lambda: ("head",))
    connection = _FakeConnection(table_exists=True, revisions=["old"])

    status = await schema_status.check_schema_current(connection)

    assert status.status == "outdated"
    assert status.current_revision == "old"
    assert status.head_revision == "head"


@pytest.mark.asyncio
async def test_check_schema_current_handles_multiple_heads_defensively(monkeypatch) -> None:
    monkeypatch.setattr(schema_status, "get_alembic_heads", lambda: ("head-a", "head-b"))
    connection = _FakeConnection(table_exists=True, revisions=["head-a"])

    status = await schema_status.check_schema_current(connection)

    assert status.status == "unknown"
    assert status.head_revision == "head-a,head-b"
    assert connection.statements == []


@pytest.mark.asyncio
async def test_schema_check_is_read_only(monkeypatch) -> None:
    monkeypatch.setattr(schema_status, "get_alembic_heads", lambda: ("head",))
    connection = _FakeConnection(table_exists=True, revisions=["head"])

    await schema_status.check_schema_current(connection)

    combined_sql = "\n".join(connection.statements).upper()
    assert "CREATE " not in combined_sql
    assert "DROP " not in combined_sql
    assert "ALTER " not in combined_sql
    assert "DELETE " not in combined_sql
    assert "UPDATE " not in combined_sql
