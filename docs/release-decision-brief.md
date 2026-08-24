# Release decision brief

> **Status:** Superseded draft for an untagged `0.1.0rc2` candidate
> **Not:** A current GO decision, published release, or production approval

This document preserves a proposal tied to PR #277. The only published GitHub
release is `v0.1.0-rc.1`. Current release decisions must be made from the latest
[readiness report](beta-readiness.md), [verification archive](verification/README.md),
and exact candidate checks.

Candidate commit: see implementation head recorded on PR #277.
Proposed version: `0.1.0rc2`.

## Historical recommendation

Conditioned GO for human review as a **release candidate**, subject to the two
major audit findings below being explicitly risk-accepted or remediated before
publication. This is not an autonomous release decision.

## Evidence summary

- Objectives 000–137 are represented in accepted OAP reports and merged history.
- Full SME acceptance matrix ran on exact candidate cbe39bd (objective 135).
- All ten required CI checks are green on each closure round's final head.
- Boundary invariant suite proves cross-unit drift, stale governance, abuse
  ceilings, redirect escape, UUID aliasing, role ceilings, and accounting checks.
- Production Compose, backup/restore, concurrency profiles, clean-clone journey,
  SBOM, support policy, security headers/secrets validation, OIDC/RBAC/service
  accounts, budgets, policy bundles, DLP, provider governance, and observability
  are documented and tested at their stated scope.

## Known unresolved major findings

1. No independent penetration test/formal vulnerability assessment exists.
   Resolution requires external engagement or explicit maintainer risk acceptance.
2. Retention/anonymization lacks independently verified scheduled enforcement.
   Resolution requires enforceable scheduling/tests or explicit risk acceptance.

## Honest limits

No production certification, SLA, public multi-tenancy guarantee, RLS guarantee,
provider-term interpretation, or legal compliance claim is made. The human
maintainer owns the final publish/tag decision.
