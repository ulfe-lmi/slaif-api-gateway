"""Tests for team model validation."""

import uuid

from slaif_gateway.db.models import Team


def test_team_fields():
    team = Team(organization_id=uuid.uuid4(), name="Engineering", slug="engineering")
    assert team.name == "Engineering"
    assert team.slug == "engineering"
