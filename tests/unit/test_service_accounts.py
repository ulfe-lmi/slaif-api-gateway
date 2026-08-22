"""Tests for service account lifecycle."""

import uuid
from datetime import UTC, datetime, timedelta

from slaif_gateway.db.models import GatewayKey


def test_service_key_has_accountable_owner():
    owner_id = uuid.uuid4()
    key = GatewayKey(
        key_purpose="service",
        service_owner_id=owner_id,
        service_name="ci-pipeline",
        max_validity_days=90,
    )
    assert key.service_owner_id == owner_id
    assert key.service_name == "ci-pipeline"


def test_service_key_max_validity():
    key = GatewayKey(key_purpose="service", max_validity_days=90)
    assert key.max_validity_days == 90


def test_human_key_no_service_fields():
    key = GatewayKey(key_purpose="standard")
    assert key.service_owner_id is None
    assert key.service_name is None


def test_rotation_updates_timestamp():
    now = datetime.now(UTC)
    key = GatewayKey(key_purpose="service", rotated_at=now)
    assert key.rotated_at == now


def test_key_purpose_values():
    """All valid purposes are recognized."""
    valid = {"human", "service", "calibration", "workshop", "standard"}
    for purpose in valid:
        key = GatewayKey(key_purpose=purpose)
        assert key.key_purpose in valid
