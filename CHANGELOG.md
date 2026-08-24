# Changelog

This project follows an evidence-first pre-release process. “Unreleased” means
merged on `main`; it does not mean tagged, deployed, or production-approved.

## Unreleased

### Gateway and compatibility

- Expanded bounded Chat Completions and Responses behavior, including stored
  references, Conversations, input-token count, compact, selected multimodal
  input, local tools, streaming live-burn, and the separately fenced OpenAI
  Responses `web_search` path.
- Added bounded Audio, Embeddings, and Realtime client-secret endpoint families.
- Added reviewed generic OpenAI-compatible backend setup and module-provider
  foundations without granting generic provider/model qualification.

### Accounting and operations

- Added PostgreSQL external-tool fences/holds, provider-completed recovery,
  safe usage profiles, richer reservation facts, and operator reconciliation.
- Added production-style Compose with file-backed secrets, authenticated Redis,
  named PostgreSQL persistence, NGINX/TLS, worker/scheduler wiring, backup/
  restore guidance, and disposable appliance qualification.
- Expanded admin and CLI surfaces for key lifecycle, imports, providers, routes,
  pricing, FX, usage/audit exports, and explicit one-time key delivery.

### Post-MVP foundations

- Added organization/team/project, OIDC, service-account, RBAC, recurring-
  budget, policy-bundle, DLP, onboarding, provider-governance, audit-export, and
  observability service/schema foundations.
- These foundations are not uniformly wired into current API/dashboard/CLI
  entrypoints and do not redefine the original one-organization SME MVP. Their
  exact status is documented individually.

### Documentation and verification

- Added current-vs-target product scope, compatibility/security/accounting
  contracts, historical review indexes, and dated verification evidence.
- The project remains RC-beta and makes no production, penetration-test,
  compliance, invoice, support, or SLA certification claim.

## [v0.1.0-rc.1] — 2026-05-01

The first published release candidate. See the immutable
[release notes](docs/releases/v0.1.0-rc.1.md).

[v0.1.0-rc.1]: https://github.com/ulfe-lmi/slaif-api-gateway/releases/tag/v0.1.0-rc.1
