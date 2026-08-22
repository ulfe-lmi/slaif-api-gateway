# OAP Work Order — 124-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/124-sme-onboarding-admin-experience`
Base: main @ 8ee243392c2e

## Objective and reason

Build the guided SME onboarding and administration experience so an SME
administrator can operate the control plane without bespoke database or CLI
expertise. Creates guided flows for organization setup, OIDC/provider/
catalog/policy/budget/service-account configuration with safe status checks,
role-appropriate dashboards, and clear remediation explanations.

## Verified state

- main = 8ee243392c2e; no open non-Dependabot PR.
- Objectives 118–123 merged (org model, OIDC, RBAC, service accounts, budgets, policy bundles).
- Admin dashboard exists with basic CRUD; needs guided onboarding flow.
- PostgreSQL remains the sole accounting truth source.

## Scope

1. Guided organization setup wizard:
   - Step-by-step org creation → OIDC config → provider setup → catalog import → policy assignment → budget definition → key issuance.
   - Each step validates prerequisites before advancing.
   - Safe status checks (no provider secret display).
2. Role-appropriate dashboards:
   - Administrator: full control + audit trail.
   - Team/project manager: scoped to assigned units.
   - Auditor: read-only with export capability.
3. Clear explanations for quota mode, external-tool risk, Codex profile, health status, and remediation steps.
4. No SPA rewrite; enhance existing server-rendered templates.

## Exact requirements

1. A clean SME operator can reach a usable strict-mode key through the documented GUI path.
2. Every dangerous action has confirmation, reason, preview, and audit.
3. The UI states implemented, blocked, held, and deferred conditions honestly.
4. Provider secrets are never displayed or logged.
5. Role-appropriate access is enforced server-side.

## Allowed paths

```
app/slaif_gateway/api/admin.py
app/slaif_gateway/templates/
app/slaif_gateway/services/onboarding.py
tests/unit/test_onboarding*.py
tests/integration/test_onboarding*_postgres.py
docs/onboarding.md
oap/orders/124-a-sme-onboarding-admin-experience.md
oap/reports/124-a-sme-onboarding-admin-experience.md
oap/active
```

## Non-goals

No SPA rewrite. No provider secret display. No automatic production decisions.
No hidden defaults. No compliance badge.

## Observable acceptance

- Guided setup wizard completes end-to-end in browser test.
- Role-appropriate dashboards enforce permissions correctly.
- All dangerous actions require confirmation + reason + audit.
- Playwright browser smoke covers the guided path.
- All required final-head CI checks green.

## Verification commands

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_onboarding*.py
PYTHONPATH=.:app .venv/bin/pytest -q tests/integration/test_onboarding*_postgres.py
PYTHONPATH=.:app .venv/bin/pytest -q tests/browser/test_admin_onboarding.py
git diff --check
```

## Boundaries

PostgreSQL-only truth. Provider credentials never exposed. Non-production only.

## OAP contract

Objective 124-a creates one PR; remediation uses 124-b–z same PR.
Coding agent never merges.
