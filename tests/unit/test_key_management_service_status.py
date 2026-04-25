from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from slaif_gateway.schemas.keys import (
    ActivateGatewayKeyInput,
    RevokeGatewayKeyInput,
    SuspendGatewayKeyInput,
    UpdateGatewayKeyValidityInput,
)
from slaif_gateway.services.key_errors import (
    GatewayKeyAlreadyActiveError,
    GatewayKeyAlreadyRevokedError,
    GatewayKeyAlreadySuspendedError,
    InvalidGatewayKeyStatusTransitionError,
    InvalidGatewayKeyValidityError,
)
from tests.unit.key_management_fakes import FakeGatewayKeyRow, make_key_service


pytestmark = pytest.mark.asyncio


def _serialized_audit(audit_calls: list[dict[str, object]]) -> str:
    return json.dumps(audit_calls, default=str)


async def test_active_key_can_be_suspended_and_audited() -> None:
    row = FakeGatewayKeyRow(status="active")
    service, keys_repo, _, audit_repo, _ = make_key_service(row)

    result = await service.suspend_gateway_key(
        SuspendGatewayKeyInput(gateway_key_id=row.id, reason="maintenance")
    )

    assert result.status == "suspended"
    assert row.status == "suspended"
    assert keys_repo.status_calls[0]["status"] == "suspended"
    assert audit_repo.calls[0]["action"] == "suspend_key"
    assert audit_repo.calls[0]["old_values"]["status"] == "active"
    assert audit_repo.calls[0]["new_values"]["status"] == "suspended"
    assert row.token_hash not in _serialized_audit(audit_repo.calls)
    assert "sk-slaif-" not in _serialized_audit(audit_repo.calls)


async def test_suspended_key_can_be_activated_and_audited() -> None:
    row = FakeGatewayKeyRow(status="suspended")
    service, _, _, audit_repo, _ = make_key_service(row)

    result = await service.activate_gateway_key(ActivateGatewayKeyInput(gateway_key_id=row.id))

    assert result.status == "active"
    assert row.status == "active"
    assert audit_repo.calls[0]["action"] == "activate_key"
    assert audit_repo.calls[0]["old_values"]["status"] == "suspended"
    assert audit_repo.calls[0]["new_values"]["status"] == "active"


async def test_active_or_suspended_key_can_be_revoked_and_audited() -> None:
    active = FakeGatewayKeyRow(status="active")
    service, _, _, audit_repo, _ = make_key_service(active)

    result = await service.revoke_gateway_key(
        RevokeGatewayKeyInput(gateway_key_id=active.id, reason="course ended")
    )

    assert result.status == "revoked"
    assert active.status == "revoked"
    assert active.revoked_at is not None
    assert active.revoked_reason == "course ended"
    assert audit_repo.calls[0]["action"] == "revoke_key"
    assert audit_repo.calls[0]["new_values"]["status"] == "revoked"

    suspended = FakeGatewayKeyRow(status="suspended")
    service, _, _, audit_repo, _ = make_key_service(suspended)
    await service.revoke_gateway_key(RevokeGatewayKeyInput(gateway_key_id=suspended.id))
    assert suspended.status == "revoked"
    assert audit_repo.calls[0]["new_values"]["status"] == "revoked"


async def test_duplicate_status_operations_raise_explicit_errors() -> None:
    suspended = FakeGatewayKeyRow(status="suspended")
    service, _, _, _, _ = make_key_service(suspended)
    with pytest.raises(GatewayKeyAlreadySuspendedError):
        await service.suspend_gateway_key(SuspendGatewayKeyInput(gateway_key_id=suspended.id))

    active = FakeGatewayKeyRow(status="active")
    service, _, _, _, _ = make_key_service(active)
    with pytest.raises(GatewayKeyAlreadyActiveError):
        await service.activate_gateway_key(ActivateGatewayKeyInput(gateway_key_id=active.id))

    revoked = FakeGatewayKeyRow(status="revoked")
    service, _, _, _, _ = make_key_service(revoked)
    with pytest.raises(GatewayKeyAlreadyRevokedError):
        await service.revoke_gateway_key(RevokeGatewayKeyInput(gateway_key_id=revoked.id))


async def test_revoked_key_cannot_be_activated_or_suspended() -> None:
    revoked = FakeGatewayKeyRow(status="revoked")
    service, _, _, _, _ = make_key_service(revoked)

    with pytest.raises(GatewayKeyAlreadyRevokedError):
        await service.activate_gateway_key(ActivateGatewayKeyInput(gateway_key_id=revoked.id))

    with pytest.raises(GatewayKeyAlreadyRevokedError):
        await service.suspend_gateway_key(SuspendGatewayKeyInput(gateway_key_id=revoked.id))


async def test_validity_can_be_extended_and_shortened() -> None:
    now = datetime.now(UTC)
    row = FakeGatewayKeyRow(valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=10))
    service, _, _, audit_repo, _ = make_key_service(row)

    extended_until = now + timedelta(days=60)
    result = await service.update_gateway_key_validity(
        UpdateGatewayKeyValidityInput(gateway_key_id=row.id, valid_until=extended_until)
    )
    assert result.valid_until == extended_until
    assert audit_repo.calls[-1]["action"] == "extend_key"

    shortened_until = now + timedelta(days=5)
    result = await service.update_gateway_key_validity(
        UpdateGatewayKeyValidityInput(gateway_key_id=row.id, valid_until=shortened_until)
    )
    assert result.valid_until == shortened_until


async def test_invalid_or_revoked_validity_update_fails() -> None:
    now = datetime.now(UTC)
    row = FakeGatewayKeyRow(valid_from=now, valid_until=now + timedelta(days=1))
    service, _, _, _, _ = make_key_service(row)

    with pytest.raises(InvalidGatewayKeyValidityError):
        await service.update_gateway_key_validity(
            UpdateGatewayKeyValidityInput(gateway_key_id=row.id, valid_until=now)
        )

    revoked = FakeGatewayKeyRow(status="revoked")
    service, _, _, _, _ = make_key_service(revoked)
    with pytest.raises(InvalidGatewayKeyStatusTransitionError):
        await service.update_gateway_key_validity(
            UpdateGatewayKeyValidityInput(
                gateway_key_id=revoked.id,
                valid_until=revoked.valid_until + timedelta(days=1),
            )
        )
