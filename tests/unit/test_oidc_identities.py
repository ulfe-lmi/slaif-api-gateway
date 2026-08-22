"""Tests for OIDC identity model validation."""

import uuid

from slaif_gateway.db.models import OidcIdentity


def test_oidc_identity_fields():
    identity = OidcIdentity(
        owner_id=uuid.uuid4(),
        issuer_url="https://idp.example.com",
        subject="user-sub-123",
        email="user@example.com",
    )
    assert identity.issuer_url == "https://idp.example.com"
    assert identity.subject == "user-sub-123"
    assert identity.email == "user@example.com"


def test_oidc_identity_unique_per_issuer_subject():
    """The unique constraint is (issuer_url, subject)."""
    # This validates the model definition, not the DB constraint.
    from slaif_gateway.db.models import OidcIdentity
    constraints = [c for c in OidcIdentity.__table_args__ if hasattr(c, "name")]
    unique_constraints = [c for c in constraints if "issuer_subject" in str(getattr(c, "name", ""))]
    assert len(unique_constraints) == 1
