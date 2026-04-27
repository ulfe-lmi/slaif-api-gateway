from __future__ import annotations

from types import SimpleNamespace

import pytest

from slaif_gateway.db.repositories.audit import AuditRepository


class FakeSession:
    def __init__(self) -> None:
        self.row = None

    def add(self, row) -> None:
        self.row = row

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_audit_repository_sanitizes_old_new_values_and_note(monkeypatch) -> None:
    created_rows: list[SimpleNamespace] = []

    def _fake_audit_log(**kwargs):
        row = SimpleNamespace(**kwargs)
        created_rows.append(row)
        return row

    monkeypatch.setattr("slaif_gateway.db.repositories.audit.AuditLog", _fake_audit_log)
    session = FakeSession()
    repo = AuditRepository(session)  # type: ignore[arg-type]

    row = await repo.add_audit_log(
        action="dangerous",
        entity_type="gateway_key",
        old_values={
            "tokenHash": "hash-secret",
            "nested": {"authorizationHeader": "Bearer sk-or-providersecret123"},
            "safe": "kept",
        },
        new_values={
            "encrypted-payload": "payload-secret",
            "request_body": {"prompt": "prompt secret"},
            "provider": "openai",
        },
        note="rotated key sk-acme-prod-public123.secretsecretsecret",
    )

    serialized = str(row.old_values) + str(row.new_values) + str(row.note)

    assert "hash-secret" not in serialized
    assert "providersecret" not in serialized
    assert "payload-secret" not in serialized
    assert "prompt secret" not in serialized
    assert "secretsecretsecret" not in serialized
    assert row.old_values["safe"] == "kept"
    assert row.new_values["provider"] == "openai"
