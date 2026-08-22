# SME onboarding

The admin dashboard provides a guided, server-rendered setup path:

1. Create the deployment's single organization.
2. Configure OIDC for human sign-in; local admin fallback remains documented.
3. Add provider metadata and its server-side API-key environment name.
4. Import a reviewed catalog into an approved policy-bundle revision.
5. Preview and confirm the exact policy before assignment.
6. Define a PostgreSQL recurring budget period.
7. Prepare a service account for automated workloads.
8. Issue a strict-mode gateway key.

Every dangerous action requires confirmation and an audit reason. Statuses are
reported honestly as implemented, blocked, held, or deferred. Provider secrets
are never displayed or logged.
