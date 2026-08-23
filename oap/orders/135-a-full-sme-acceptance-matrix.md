# OAP Work Order — 135-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/135-full-sme-acceptance-matrix`
Base: main @ cbe39bd6d1df

## Objective and reason

Run the full SME compatibility, security, browser, and packaging acceptance
matrix on the exact candidate commit. No feature work; verification only.
This is the first Phase 6 objective.

## Verified state

- main = cbe39bd6d1df; no open non-Dependabot PR.
- Objectives 118–134 merged. Phase 5 gate passed.

## Scope

Run the complete acceptance matrix:
- All unit/integration/browser tests on clean checkout of the candidate SHA.
- Codex CLI E2E with local tools through gateway (mocked provider).
- OpenAI-compatible client E2E (mocked).
- Playwright browser smoke for admin/onboarding flows.
- PostgreSQL integration tests including boundary invariants.
- Docker Compose smoke with production profile.
- Backup/restore verification.
- Documentation hygiene checks.

## Exact requirements

1. Every test passes on the exact candidate commit — no cherry-picking.
2. No feature work, test weakening, release/tag, or production deployment in this PR.
3. Results published as a structured acceptance report mapped to requirements.

## Allowed paths

```
docs/acceptance-report.md
oap/orders/135-a-full-sme-acceptance-matrix.md
oap/reports/135-a-full-sme-acceptance-matrix.md
oap/active
```

## Non-goals

No feature work. No release/tag decision. No production deployment.

## Observable acceptance

- Full acceptance matrix passes on the exact candidate commit.
- Acceptance report maps each requirement to passing evidence.
- All required final-head CI checks green.

## Verification commands

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/
git diff --check
```

## OAP contract

Objective 135-a creates one PR; remediation uses 135-b–z same PR.
Coding agent never merges.
