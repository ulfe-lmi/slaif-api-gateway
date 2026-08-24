# Boundary invariant matrix

> **Status:** Focused post-MVP extension snapshot
> **Boundary:** These tests do not redefine the original one-organization SME MVP

| Boundary | Negative test | Code reference |
|---|---|---|
| Cross-unit catalog access | `test_cross_unit_policy_drift_fails_closed` | `PolicyBundleService.check_drift` |
| Stale provider governance | `test_stale_governance_evidence_blocks_alternate_provider_route` | `provider_governance.route_allowed` |
| Abuse/privilege retry ceiling | `test_abuse_tracker_prevents_privilege_grant_retry_after_lockout` | `security.AbuseTracker` |
| Admin redirect escape | `test_open_redirect_cannot_escape_admin_boundary` | `security.safe_admin_redirect` |
| UUID alias/scope confusion | `test_uuid_alias_does_not_bypass_scope_lookup` | explicit allow-list comparison |
| Role ceilings | `test_role_ceilings_are_negative` | role permission sets |
| Non-negative accounting limit | `test_budget_period_tables_enforce_nonnegative_limits` | PostgreSQL CHECK constraints |

## Honest post-MVP limits

This suite does not claim hostile public multi-tenancy, PostgreSQL row-level
security, complete authorization proof, or production certification. The SME
MVP remains one organization per deployment.
