"""Tests for project model validation."""

import uuid

from slaif_gateway.db.models import Project


def test_project_fields():
    project = Project(team_id=uuid.uuid4(), name="Gateway", slug="gateway")
    assert project.name == "Gateway"
    assert project.slug == "gateway"
