# OAP Work Order — 118-a

PR mode: `CREATE_NEW_PR`
Branch: oap/118-organization-team-project-data-model
Base: main @ ffe1a899bd03b6dd3120eefaa482235241fb01b9

## Objective and reason

Establish the single-organization team and project model by evolving the
workshop-era institution/cohort records into an explicit SME organizational
structure. This is the first objective of Architecture Phase 3 (SME
organization control) and unblocks all subsequent Phase 3 objectives (119–124).

## Verified current state

- main = ffe1a899bd03b6dd3120eefaa482235241fb01b9; no 118 branch or PR exists.
- Dependencies (002, 003, 023) are all merged.
- Existing schema has `institutions` (id, name, country, notes) and `cohorts`
  (id, name, description, starts_at, ends_at) with FK references from
  `owners`, `gateway_keys`, and `usage_ledger`.
- Admin CLI (`slaif-gateway institutions` / `slaif-gateway cohorts`) and admin
  web pages already manage these records.
- No organization/team/project tables exist yet.

## Requirements

1. Schema documentation first (`docs/database-schema.md`):
   - Add `organizations` table (id, name, slug, notes, created_at, updated_at).
   - Add `teams` table (id, organization_id FK, name, slug, notes, created_at, updated_at).
   - Add `projects` table (id, team_id FK, name, slug, description,
     starts_at, ends_at, created_at, updated_at).
   - Add `team_members` junction table (team_id FK, owner_id FK, role, created_at).
   - Document one-organization-per-deployment constraint explicitly.
   - Map existing institution→organization and cohort→project for migration context.

2. Alembic migration:
   - Create `organizations`, `teams`, `projects`, `team_members` tables.
   - Add `organization_id` FK to `institutions` (nullable, for backward compat).
   - Add `project_id` FK to `cohorts` (nullable, for backward compat).
   - Migration must be reversible (downgrade drops new tables and FK columns).
   - Preserve all existing data and audit/accounting references.

3. Repositories and services:
   - Add `OrganizationsRepository`, `TeamsRepository`, `ProjectsRepository`,
     `TeamMembersRepository` following the existing repository patterns.
   - Add corresponding service layer classes.
   - Add CLI commands under `slaif-gateway organizations`, `slaif-gateway teams`,
     `slaif-gateway projects`.

4. Admin API/pages:
   - Add admin endpoints for CRUD on organizations, teams, projects.
   - Follow existing admin page patterns (CSRF, audit reason, safe metadata only).

5. Cross-unit authorization:
   - Gateway keys can be scoped to a project (via cohort→project link).
   - Cross-team/project authorization rules must be explicit and tested.
   - One-organization-per-deployment enforced at the service layer.

## Non-goals

- No hostile public multi-tenancy or RLS tenant guarantee.
- No SCIM, billing system, or cross-deployment control plane.
- No OIDC/RBAC/MFA (these are 119–120).
- No destruction or silent reinterpretation of existing historical records.

## Allowed paths

docs/database-schema.md
migrations/versions/0016_organization_team_project.py
app/slaif_gateway/db/models.py
app/slaif_gateway/db/repositories/organizations.py (new)
app/slaif_gateway/db/repositories/teams.py (new)
app/slaif_gateway/db/repositories/projects.py (new)
app/slaif_gateway/services/organization_service.py (new)
app/slaif_gateway/services/team_service.py (new)
app/slaif_gateway/services/project_service.py (new)
app/slaif_gateway/cli/organizations.py (new)
app/slaif_gateway/cli/teams.py (new)
app/slaif_gateway/cli/projects.py (new)
app/slaif_gateway/api/admin.py
tests/unit/test_organizations.py (new)
tests/unit/test_teams.py (new)
tests/unit/test_projects.py (new)
tests/unit/test_team_authorization.py (new)
oap/active
oap/orders/118-a-organization-team-project-data-model.md
oap/reports/118-a-organization-team-project-data-model.md

## Verification commands

PYTHONPATH=.:app .venv/bin/pytest -q \
  tests/unit/test_organizations.py \
  tests/unit/test_teams.py \
  tests/unit/test_projects.py \
  tests/unit/test_team_authorization.py

DATABASE_URL="postgresql+asyncpg://slaif:slaif@localhost:15432/test_slaif_gateway" \
.venv/bin/python -m alembic upgrade head
DATABASE_URL="postgresql+asyncpg://slaif:slaif@localhost:15432/test_slaif_gateway" \
.venv/bin/python -m alembic downgrade 0015

git diff --check
Ruff on changed paths

## Acceptance criteria

- All new tables created with proper FK constraints and indexes.
- Migration upgrade/downgrade verified against test DB.
- Every gateway key can be attributed to the organizational hierarchy.
- Cross-team authorization rules tested with negative evidence.
- One-organization-per-deployment constraint enforced and tested.
- All CI checks green on final head.

## Security and documentation

- Preserve provider-secret isolation and PostgreSQL accounting truth.
- Update docs/database-schema.md with complete schema documentation.
- State one-organization-per-deployment in deployment docs.

## OAP contract

- Objective 118-a creates exactly one new PR for numeric objective 118.
- Remediations use 118-b through 118-z on the same PR.
- The coding agent never merges or enables auto-merge.

## Boundaries

Non-production only. No production data or credentials. PostgreSQL remains
accounting truth.
