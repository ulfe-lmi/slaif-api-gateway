# SME onboarding foundation

> **Status:** Standalone readiness state machine; no wired onboarding page or CLI
> **Audience:** Maintainers and operators planning manual setup

`services/onboarding.py` can classify prerequisite facts for organization,
OIDC, providers, policy bundles, budgets, service accounts, and key issuance as
implemented or blocked. No current API, dashboard route, template, or CLI
command renders that state machine as a guided wizard.

Use the current manual operator sequence instead:

1. Follow the [quickstart](quickstart.md) and create a local administrator.
2. Configure server-side provider secrets and safe provider metadata.
3. Create or import reviewed routes, pricing, and required FX rows.
4. Create owners/institutions/cohorts needed by the current key workflow.
5. Create a key with explicit endpoint/model/quota/rate limits.
6. Verify `/readyz`, `/v1/models`, one bounded request, usage metadata, and
   revocation before broader use.

Organization/team/project, OIDC, recurring-budget, policy-bundle, and service-
account modules are post-MVP extensions or foundations. Their presence does not
turn the one-organization SME MVP into an enterprise identity/tenancy product.
