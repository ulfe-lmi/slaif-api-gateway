# SLAIF API Gateway documentation

> **Status:** Current documentation home
> **Audience:** Evaluators, operators, API integrators, security reviewers, and maintainers
> **Product boundary:** RC-beta, one organization per deployment, not production-certified

This page is the entry point for current SLAIF API Gateway documentation.
Historical reviews, releases, and verification records are indexed separately
and do not override current contracts or merged code.

## Getting started

- [QUICKSTART](../QUICKSTART.md) — the canonical short quickstart:
  provider-free boot to admin login, then the first OpenAI-client request.
- [INSTALL](../INSTALL.md) — installation overview: prerequisites,
  persistence, production topology, upgrades, stop/cleanup.
- [First-time operator guide](first-time-operator-guide.md) — the detailed
  tutorial: real-provider wiring, Mailpit email, testing, refresh workflows,
  troubleshooting.
- [Legacy quickstart path (compatibility stub)](quickstart.md) — historical
  link target only; the canonical quickstart now lives at the repository root.
- [Product scope](product-scope.md) — what SLAIF is, the deployment boundary,
  and the current/approved-target/non-goal labels.
- [Compatibility matrix](compatibility-matrix.md) — exact endpoint-family
  support levels.

## Using SLAIF

- [OpenAI compatibility](openai-compatibility.md) — request, response, SSE,
  and error behavior.
- [Responses compatibility](responses-compatibility.md) — the bounded
  Responses surface.
- [Codex compatibility](codex-compatibility.md) — the bounded Codex
  request-envelope slice.
- [Provider forwarding contract](provider-forwarding-contract.md) — headers,
  bodies, endpoints, credential replacement.
- [Pricing catalog and bounded overrun](pricing-catalog.md) — pricing
  metadata and cost behavior.
- [Provider catalog proposals](provider-catalog-proposals.md) — proposal-only
  catalog tooling.
- [Gateway key templates](key-templates.md) — template metadata and
  single-key creation.
- [CLI reference](cli-reference.md) — the operator command index.

## Operating SLAIF

- [Development deployment](deployment.md) — the local Compose reference.
- [Production Compose deployment](deployment-production.md) — the hardened
  appliance procedure.
- [Configuration reference](configuration.md) — every supported setting.
- [Backup and restore](backup-restore.md) — durable-truth protection.
- [Upgrade and recovery](upgrade-runbook.md) — controlled upgrades.
- [Operator runbooks](runbooks/README.md) — ongoing operation and incident
  procedures.
- [Incident response](incident-response.md) — response overview.
- [SME sizing guidance](sizing.md) — capacity planning boundary.
- [Observability boundaries](observability.md) — metrics and SLO foundation.
- [Support policy](support-policy.md) — the support boundary.
- [Clean-clone qualification journey](demo-journey.md) — the disposable
  production-appliance harness wrapper.

## Security

- [Security model](security-model.md) — threat, privacy, key, session, and
  logging boundaries.
- [Security hardening controls](security-hardening.md) — the implemented
  hardening surface.
- [Audit and export surfaces](audit-export.md) — audit records and exports.
- [Security-review archive](security/reviews/README.md) — dated external
  reviews (historical evidence).
- Security vulnerability reporting lives in
  [SECURITY.md](../SECURITY.md) at the repository root.

## Development and architecture

- [Module architecture](module-architecture.md) — the static
  client/server module layout.
- [Database schema](database-schema.md) — tables, columns, relationships,
  constraints.
- [Accounting contract](accounting.md) — reservation, finalization, cost,
  reconciliation.
- [Streaming live-burn contract](streaming-live-burn-margin.md) — admission
  and live-burn behavior.
- [Chat custom-tools investigation](chat-completions-custom-tools-investigation.md)
  and [Chat multimodal investigation](chat-completions-multimodal-investigation.md)
  — bounded investigations.
- [Test parallelism](testing-parallelism.md) and
  [HPC test preparation](testing-hpc.md) — verification harnesses.
- [CONTRIBUTING](../CONTRIBUTING.md) — development environment and focused
  checks.

Foundations and investigations (bounded code exists; not claims that a
feature is wired into every Gateway entrypoint):

- [SME onboarding foundation](onboarding.md)
- [Optional DLP foundation](dlp-policy.md)
- [Provider-governance foundation](provider-governance.md)
- [Audit findings snapshot](audit-findings.md)
- [SME audit matrix snapshot](audit-matrix.md)
- [Boundary invariant snapshot](boundary-invariant-matrix.md)
- [Real-provider qualification boundary](real-provider-qualification.md)
- [Supply-chain evidence](supply-chain.md)

## Project status and evidence

- [RC-beta checklist and history](rc-beta.md) — release checklist plus dated
  evidence pointers.
- [RC2 target classifications](rc2-feature-scope.md) — the
  implemented/deferred/unsupported classification.
- [Verification index](verification/README.md) — dated verification and
  identity records, newest first.
- [Release archive](releases/README.md) — published release notes and
  verification evidence references.
- [Beta readiness record (dated 2026-08-24)](beta-readiness.md) — historical
  readiness evidence as-of its named commit.
- [Release-decision draft](release-decision-brief.md) — superseded draft for
  an untagged candidate.
- [Untagged RC2 release-notes draft](release-notes.md) — draft only.
- [Security-review remediation history](security/reviews/remediation-matrix.md)
- [Documentation truth audit](verification/2026-08-24-documentation-audit.md)

## Authority map

When two documents appear to overlap, use this ownership order for the
specific domain. Merged code remains implementation truth.

| Domain | Owning document |
|---|---|
| Product identity, current/target/non-goal boundary | [Product scope](product-scope.md) |
| RC2 target classification | [RC2 feature scope](rc2-feature-scope.md) |
| Current endpoint-family status | [Compatibility matrix](compatibility-matrix.md) |
| OpenAI request, response, SSE, and error behavior | [OpenAI compatibility](openai-compatibility.md) |
| Responses-specific fields and lifecycle | [Responses compatibility](responses-compatibility.md) |
| Provider headers, bodies, endpoints, and credential replacement | [Provider forwarding contract](provider-forwarding-contract.md) |
| Reservation, finalization, cost, and reconciliation | [Accounting](accounting.md) |
| Streaming admission and live-burn behavior | [Streaming live-burn contract](streaming-live-burn-margin.md) |
| Threat, privacy, key, session, and logging boundaries | [Security model](security-model.md) |
| Environment settings and defaults | [Configuration](configuration.md) |
| Tables, columns, relationships, and constraints | [Database schema](database-schema.md) |
| Dated verification and readiness records | [Verification index](verification/README.md) |

## Reading rules

- “Implemented” means reachable merged behavior, not merely a class, table, or
  isolated unit test.
- “Foundation” means bounded code exists but product wiring or qualification
  is incomplete.
- “Qualified” names the exact provider/model/path/evidence that was exercised;
  it is not a general accuracy or production claim.
- “Historical” records what was true for a dated commit and must not be read
  as current implementation status.
- Unsupported or unknown input fails closed unless a current contract
  explicitly states otherwise.
