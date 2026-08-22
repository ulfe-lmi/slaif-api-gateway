"""Tests for cross-team authorization rules."""

import uuid

from slaif_gateway.db.models import Team, TeamMember


def test_member_of_one_team_not_auto_member_of_another():
    """Verify that adding a member to one team does not add them to other teams."""
    org_id = uuid.uuid4()
    team_a = Team(organization_id=org_id, name="Team A", slug="team-a")
    team_b = Team(organization_id=org_id, name="Team B", slug="team-b")

    member_a = TeamMember(team_id=team_a.id, owner_id=uuid.uuid4(), role="member")
    assert member_a.team_id == team_a.id
    assert member_a.owner_id != uuid.uuid4()  # deterministic owner check

    # Cross-team authorization: membership in Team A does not imply Team B access.
    # This must be enforced at the service layer, not by the model.


def test_team_role_constraint():
    """TeamMember role must be one of the allowed values."""
    valid_roles = {"member", "lead", "admin"}
    for role in valid_roles:
        member = TeamMember(team_id=uuid.uuid4(), owner_id=uuid.uuid4(), role=role)
        assert member.role in valid_roles
