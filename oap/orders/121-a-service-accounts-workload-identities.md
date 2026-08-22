# OAP Work Order — 121-a

PR mode: CREATE_NEW_PR
Branch: oap/121-service-accounts-workload-identities
Base: main @ 8726333

## Objective and reason

Add service accounts and application workload identities to separate
machine credentials from human gateway keys, with accountable ownership,
rotation, and audit semantics.

## Verified current state

- main = 8726333; no 121 branch or PR exists.
- Dependencies (118, 119, 120) are all merged.
- RBAC module exists with role-based permission checks.
- GatewayKey model already has key_purpose field.

## Requirements

1. Add `key_purpose` validation: restrict to {"human", "service", "calibration", "workshop"}.
2. Add `service_account` fields to `gateway_keys`:
   - `service_owner_id` UUID FK to owners (accountable human)
   - `service_name` text (application name)
   - `rotated_at` timestamptz nullable
   - `max_validity_days` int (default 90)
3. Migration 0019 (idempotent).
4. Enforce in service layer:
   - Service keys cannot be created without an accountable owner
   - Service keys have a maximum validity period
   - Rotation resets validity window
5. Distinguish human vs service in admin CLI output.
6. Tests for lifecycle, rotation, cross-identity rejection.

## Non-goals

No cloud workload identity federation, SCIM, provider key exposure,
browser login for service accounts, or plaintext credential recovery/resend.

## Allowed paths

docs/database-schema.md
migrations/versions/0019_service_accounts.py (new)
app/slaif_gateway/db/models.py
app/slaif_gateway/services/key_service.py
tests/unit/test_service_accounts.py (new)
oap/active
oap/orders/121-a-service-accounts-workload-identities.md
oap/reports/121-a-service-accounts-workload-identities.md

## Verification commands

PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_service_accounts.py

## Acceptance criteria

1. Service keys require accountable owner and max validity period.
2. Rotation resets the validity clock.
3. Human vs service distinguishable in key metadata.
4. Cross-identity operations rejected with clear error codes.

## Security

PostgreSQL remains accounting truth. No plaintext recovery.

## OAP contract

Objective 121-a creates exactly one new PR. Remediations use 121-b through 121-z.
