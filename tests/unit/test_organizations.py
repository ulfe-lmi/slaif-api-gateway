"""Tests for organization model validation."""

from slaif_gateway.db.models import Organization


def test_organization_fields():
    org = Organization(name="Test Org", slug="test-org")
    assert org.name == "Test Org"
    assert org.slug == "test-org"
