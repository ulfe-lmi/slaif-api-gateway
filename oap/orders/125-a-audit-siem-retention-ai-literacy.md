# OAP Work Order — 125-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/125-audit-siem-retention-ai-literacy`
Base: main @ b486229704d3

## Objective and reason

Add audit/SIEM exports, retention governance, and AI-literacy evidence so SMEs
can prove who used which AI capability under which policy without storing
content by default. Creates safe metadata-only export streams, enforceable
retention/anonymization policies, and organization reports for governance review.

## Verified state

- main = b486229704d3; no open non-Dependabot PR.
- Objectives 118–124 merged (org model, OIDC, RBAC, service accounts, budgets, policy bundles, onboarding).
- Existing `usage_ledger` and `audit_log` tables provide raw event data.
- PostgreSQL remains the sole accounting truth source.

## Scope

1. Safe audit/usage export schemas:
   - Finance: cost per org/team/project/user/key with timestamps.
   - Security: auth events, policy changes, key lifecycle.
   - Project reporting: model/provider/tool usage by unit.
   - SIEM (CEF/JSON): auth failures, permission denials, fence acquisitions.
2. Retention and anonymization:
   - Configurable retention periods per event category.
   - Anonymize/pseudonymize owner identities after retention window.
   - Deletion constraints that preserve ledger integrity.
3. Organization reports:
   - Models used, providers accessed, tools invoked.
   - Budget consumption, holds, policy changes over time.
   - AI-literacy training/governance review checklist.

## Exact requirements

1. Reports answer identity/policy/model/provider/tool/quota questions from safe metadata.
2. Retention and anonymization are enforceable and preserve required history.
3. Exports resist spreadsheet injection and integrate through documented stable formats.
4. No prompt/response content is stored or exported by default.
5. No legal compliance certification claim.

## Allowed paths

```
app/slaif_gateway/services/audit_export.py
app/slaif_gateway/api/admin.py
app/slaif_gateway/cli/
tests/unit/test_audit_export*.py
tests/integration/test_audit_export*_postgres.py
docs/audit-export.md
oap/orders/125-a-audit-siem-retention-ai-literacy.md
oap/reports/125-a-audit-siem-retention-ai-literacy.md
oap/active
```

## Non-goals

No prompt/response archive. No compliance certification. No employee surveillance product. No raw secret/content export.

## Observable acceptance

- Export streams produce valid CSV/JSON/CEF for each category.
- Retention anonymization runs correctly and preserves ledger integrity.
- Spreadsheet injection tests pass (formula injection prevented).
- Dashboard reports render correctly for each role.
- All required final-head CI checks green.

## Verification commands

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_audit_export*.py
PYTHONPATH=.:app .venv/bin/pytest -q tests/integration/test_audit_export*_postgres.py
git diff --check
```

## Boundaries

PostgreSQL-only truth. No content storage. Provider credentials never exposed. Non-production only.

## OAP contract

Objective 125-a creates one PR; remediation uses 125-b–z same PR.
Coding agent never merges.
