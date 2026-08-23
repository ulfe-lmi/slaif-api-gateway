# Changelog

## 0.1.0rc2 — SME control-plane release candidate

### Added

- Single-organization team/project model with explicit hierarchy and provenance.
- OIDC human sign-in with controlled identity linking; local admin fallback retained.
- Enforceable SME RBAC, permission ceilings, MFA direction, and service accounts.
- Hierarchical recurring PostgreSQL budgets with atomic reservations.
- Versioned policy bundles, approved catalogs, drift detection, and immutable revisions.
- Guided SME onboarding/status experience.
- Metadata-only audit/SIEM/finance/project exports.
- Optional bounded DLP/PII policy with redacted findings only.
- Provider governance for residency, retention, training use, ZDR claims, destinations, and stale-evidence fail-closed routing.
- Security hardening: headers, abuse throttling, redirect boundary, secret validation, incident runbooks.
- Boundary invariant suite, observability SLOs, backup/restore runbook, concurrency correctness profiles.
- Production Compose profile with TLS/Nginx, secrets preflight, resource limits, and internal networking.
- Clean-clone operator journey, full acceptance matrix, audit findings, SBOM/support gate.

### Changed

- Alembic head advanced through `0022_provider_governance`.
- Compatibility matrix now records model qualification evidence and limitations.

### Security

- No plaintext provider or gateway keys are stored.
- Content-minimizing defaults remain in place; no prompt/completion storage by default.

### Known limitations

- No hostile public multi-tenancy or RLS guarantee.
- One organization per deployment remains the SME MVP boundary.
- No penetration test, compliance certification, SLA, or production approval is claimed.
