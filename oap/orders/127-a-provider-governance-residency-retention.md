# OAP Work Order — 127-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/127-provider-governance-residency-retention`
Base: main @ 1d59818af634

## Objective and reason

Add provider governance, residency, retention, and tool-destination policy so
provider choice becomes an organizational data-governance decision rather than
just a route. Records reviewed provider metadata and constrains routing by
approved governance attributes.

## Verified state

- main = 1d59818af634; no open non-Dependabot PR.
- Objectives 118–126 merged (org model through DLP/PII).
- Existing `provider_configs` table has base_url, api_key_env_var, enabled.
- Policy bundle framework from 123-a provides scope/composition infrastructure.

## Scope

1. Provider governance metadata:
   - Residency region, data-retention policy, training-use flag, ZDR claim.
   - Endpoint/tool destinations (which external services are contacted).
   - Evidence date and reviewer for each attribute.
2. Policy bundle constraint integration:
   - Org/team/project bundles can restrict providers by governance attributes.
   - Stale/unknown evidence requires reapproval before routing.
3. Admin dashboard:
   - Show provider governance status per route.
   - Highlight stale/missing evidence requiring reapproval.
4. Audit records for all governance metadata changes.

## Exact requirements

1. Requests are only routed to providers whose governance attributes satisfy the active policy bundle.
2. Stale/unknown evidence produces a clear error rather than silent routing.
3. No legal warranty or automated interpretation of provider terms.
4. No provider secret storage in governance metadata.
5. All governance changes produce audit records.

## Allowed paths

```
app/slaif_gateway/db/models.py
migrations/versions/0022_*.py
app/slaif_gateway/services/provider_governance.py
app/slaif_gateway/api/admin.py
tests/unit/test_provider_governance*.py
tests/integration/test_provider_governance*_postgres.py
docs/provider-governance.md
oap/orders/127-a-provider-governance-residency-retention.md
oap/reports/127-a-provider-governance-residency-retention.md
oap/active
```

## Non-goals

No legal warranty. No automated interpretation of provider terms. No provider secret storage. No unverifiable compliance badge.

## Observable acceptance

- Provider governance attributes are stored and queryable.
- Policy bundle constraints correctly restrict routing.
- Stale evidence triggers reapproval requirement with clear message.
- Dashboard shows governance status per provider/route.
- All required final-head CI checks green.

## Verification commands

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_provider_governance*.py
PYTHONPATH=.:app .venv/bin/pytest -q tests/integration/test_provider_governance*_postgres.py
git diff --check
```

## Boundaries

PostgreSQL-only truth. No content storage. Provider credentials never exposed. Non-production only.

## OAP contract

Objective 127-a creates one PR; remediation uses 127-b–z same PR.
Coding agent never merges.
