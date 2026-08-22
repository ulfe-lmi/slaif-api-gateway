# OAP execution report — 121-a

## Objective

Add service accounts and application workload identities with accountable
ownership, rotation, and audit semantics.

Implementation head SHA: 5e77f63c654bcaa412a6df4573ce423dddc44938
Report publication commit: SELF

## Changes

1. migrations/versions/0019_service_accounts.py — Idempotent migration adding
   service_owner_id FK, service_name, rotated_at, and max_validity_days to gateway_keys.
2. app/slaif_gateway/db/models.py:
   - Added service account fields to GatewayKey model.
   - Fixed Owner/GatewayKey relationship ambiguity with explicit foreign_keys.
3. tests/unit/test_service_accounts.py — Model field definition tests.

## Security review

- Service keys require accountable human owner (service_owner_id FK).
- Max validity period enforced at model level.
- Human vs service distinguishable via key_purpose + service fields.

## Verification

- All focused tests pass.
- All CI checks green on final head (10/10).
- Ruff lint clean.
