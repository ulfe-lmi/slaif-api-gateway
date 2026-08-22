# OAP Work Order — 126-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/126-optional-dlp-pii-policy`
Base: main @ 1acbfa9db7eb

## Objective and reason

Implement optional bounded DLP and PII policy so organizations can block or
flag sensitive egress while keeping content-minimizing defaults. Integrates
pluggable detectors with policy bundles, route/provider decisions, and audit
metadata without default content retention.

## Verified state

- main = 1acbfa9db7eb; no open non-Dependabot PR.
- Objectives 118–125 merged (org model, OIDC, RBAC, service accounts, budgets,
  policy bundles, onboarding, audit/SIEM exports).
- Policy bundle framework from 123-a provides scope/composition infrastructure.
- PostgreSQL remains the sole accounting truth source.

## Scope

1. Pluggable DLP detector interface:
   - Local/simple regex-based detectors (email, phone, credit card, SSN patterns).
   - Action modes: block, flag (allow with audit), monitor (audit only).
   - Timeout/failure posture: fail-closed for block mode, fail-open for monitor.
2. Integration points:
   - Request/response scanning hooks in the gateway pipeline.
   - Policy bundle assignment per org/team/project/key.
   - Route/provider decision integration.
3. Audit metadata:
   - Redacted findings (pattern type + confidence, never raw matched content).
   - Bounded ephemeral buffers that are never persisted as prompt logging.
4. Admin preview:
   - Show which detectors would fire on a sample payload without storing it.

## Exact requirements

1. Scanning buffers are bounded, ephemeral, and never become default prompt logging.
2. No claim of complete PII detection or legal compliance.
3. Block mode fails closed on detector timeout/failure.
4. Redacted findings only (no raw matched content in audit).
5. All DLP decisions produce audit records.

## Allowed paths

```
app/slaif_gateway/services/dlp.py
app/slaif_gateway/api/admin.py
app/slaif_gateway/templates/
tests/unit/test_dlp*.py
tests/integration/test_dlp*_postgres.py
docs/dlp-policy.md
oap/orders/126-a-optional-dlp-pii-policy.md
oap/reports/126-a-optional-dlp-pii-policy.md
oap/active
```

## Non-goals

No complete PII detection claim. No legal compliance certification. No semantic guardrail correctness. No mandatory hosted DLP service.

## Observable acceptance

- Regex-based detectors correctly identify test patterns.
- Block mode prevents request forwarding when pattern detected.
- Flag/monitor modes allow but audit with redacted findings.
- Admin preview shows detector results without persisting content.
- All required final-head CI checks green.

## Verification commands

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_dlp*.py
PYTHONPATH=.:app .venv/bin/pytest -q tests/integration/test_dlp*_postgres.py
git diff --check
```

## Boundaries

PostgreSQL-only truth. No content storage by default. Provider credentials never exposed. Non-production only.

## OAP contract

Objective 126-a creates one PR; remediation uses 126-b–z same PR.
Coding agent never merges.
