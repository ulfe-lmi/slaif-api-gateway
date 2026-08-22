"""Tests for service account model field definitions."""

from slaif_gateway.db.models import GatewayKey


def test_gateway_key_has_service_fields():
    """Verify the GatewayKey model defines service account columns."""
    columns = {c.name for c in GatewayKey.__table__.columns}
    assert "service_owner_id" in columns
    assert "service_name" in columns
    assert "rotated_at" in columns
    assert "max_validity_days" in columns
    assert "key_purpose" in columns


def test_gateway_key_purpose_check_constraint():
    """Verify the purpose check constraint exists."""
    constraints = [c.name for c in GatewayKey.__table_args__ if hasattr(c, "name")]
    assert any("key_purpose_allowed_values" in name for name in constraints if name)
