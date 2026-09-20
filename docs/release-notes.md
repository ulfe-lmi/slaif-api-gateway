# Release notes — 0.1.0rc2 SME control-plane candidate

> **Status:** Untagged draft; not a published release
> **Published archive:** [`v0.1.0-rc.1`](releases/v0.1.0-rc.1.md)

These notes describe a proposed candidate assembled during post-MVP extension
work. They do not establish that `0.1.0rc2` was tagged, released, or approved.

This release candidate is drafted around the wired OpenAI-compatible gateway
scope — the supported endpoint families documented in the compatibility
matrix — plus a set of bounded post-MVP service foundations: organizational
governance, identity, budgets, policy bundles, DLP, provider governance,
observability, recoverability, deployment hardening, and supply-chain gates.
Foundation modules are documented bounded code with their stated readiness
state; they are not claims that every listed capability is deployed or wired
into every gateway entrypoint.

Operators should read:

- `docs/deployment-production.md`
- `docs/onboarding.md`
- `docs/security-hardening.md`
- `docs/incident-response.md`
- `docs/backup-restore.md`
- `docs/upgrade-runbook.md`
- `docs/support-policy.md`

This candidate is not certified, not production-approved by this repository, and
does not claim multi-tenant isolation, penetration testing, legal compliance, or
an SLA. Tagging/publication requires explicit human authority.
