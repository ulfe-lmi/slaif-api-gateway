# SLAIF API Gateway documentation

> **Status:** Current documentation home
> **Audience:** Evaluators, operators, API integrators, security reviewers, and maintainers
> **Product boundary:** RC-beta, one organization per deployment, not production-certified

This page is the entry point for current SLAIF API Gateway documentation.
Historical reviews, releases, and verification records are indexed separately
and do not override current contracts or merged code.

## Choose a path

| Goal | Start here |
|---|---|
| Understand the product and its limits | [Product scope](product-scope.md) → [current readiness](beta-readiness.md) |
| Run the Gateway locally | [Quickstart](quickstart.md) → [configuration](configuration.md) → [development deployment](deployment.md) |
| Prepare a production-style appliance | [Production Compose](deployment-production.md) → [security model](security-model.md) → [operator runbooks](runbooks/README.md) |
| Integrate an OpenAI client | [Compatibility matrix](compatibility-matrix.md) → [OpenAI compatibility](openai-compatibility.md) |
| Integrate Responses or Codex | [Responses contract](responses-compatibility.md) → [Codex compatibility](codex-compatibility.md) |
| Configure providers and pricing | [Provider forwarding](provider-forwarding-contract.md) → [catalog proposals](provider-catalog-proposals.md) → [pricing catalog](pricing-catalog.md) |
| Review quota and privacy controls | [Accounting](accounting.md) → [streaming live-burn](streaming-live-burn-margin.md) → [security model](security-model.md) |
| Diagnose an incident | [Runbook index](runbooks/README.md) → [incident response](incident-response.md) |
| Verify or contribute | [Test parallelism](testing-parallelism.md) → [HPC testing](testing-hpc.md) → [verification archive](verification/README.md) |

## Authority map

When two documents appear to overlap, use this ownership order for the specific
domain. Merged code remains implementation truth.

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
| Current verification and release-readiness evidence | [Beta readiness](beta-readiness.md) |

## Start and evaluate

- [Product scope](product-scope.md)
- [Current beta readiness](beta-readiness.md)
- [Compatibility matrix](compatibility-matrix.md)
- [RC-beta checklist and history](rc-beta.md)
- [RC2 target classifications](rc2-feature-scope.md)
- [Release archive](releases/README.md)
- [Verification archive](verification/README.md)

## Deploy and operate

- [First-time quickstart](quickstart.md)
- [Configuration reference](configuration.md)
- [Development deployment](deployment.md)
- [Production Compose deployment](deployment-production.md)
- [Backup and restore](backup-restore.md)
- [Upgrade and recovery](upgrade-runbook.md)
- [SME sizing guidance](sizing.md)
- [Observability boundaries](observability.md)
- [Support policy](support-policy.md)
- [Incident response overview](incident-response.md)
- [Operator runbooks](runbooks/README.md)
- [Clean-clone qualification journey](demo-journey.md)

## Integrate and configure

- [OpenAI compatibility](openai-compatibility.md)
- [Responses compatibility](responses-compatibility.md)
- [Provider forwarding contract](provider-forwarding-contract.md)
- [Codex compatibility](codex-compatibility.md)
- [Real-provider qualification boundary](real-provider-qualification.md)
- [Provider catalog proposals](provider-catalog-proposals.md)
- [Pricing catalog and bounded overrun](pricing-catalog.md)
- [Gateway key templates](key-templates.md)
- [CLI reference](cli-reference.md)

## Security, accounting, and governance

- [Security model](security-model.md)
- [Security hardening controls](security-hardening.md)
- [Accounting contract](accounting.md)
- [Streaming live-burn contract](streaming-live-burn-margin.md)
- [Database schema](database-schema.md)
- [Audit/export surfaces](audit-export.md)
- [Optional DLP foundation](dlp-policy.md)
- [Provider-governance foundation](provider-governance.md)
- [Supply-chain evidence](supply-chain.md)

## Foundation and design references

These files describe bounded service foundations or investigations. They are
not independent claims that a feature is wired into every Gateway entrypoint.

- [SME onboarding foundation](onboarding.md)
- [Observability/SLO foundation](observability.md)
- [Audit findings snapshot](audit-findings.md)
- [SME audit matrix snapshot](audit-matrix.md)
- [Boundary invariant snapshot](boundary-invariant-matrix.md)
- [Chat custom-tools investigation](chat-completions-custom-tools-investigation.md)
- [Chat multimodal investigation](chat-completions-multimodal-investigation.md)

## Project verification and maintenance

- [Test parallelism](testing-parallelism.md)
- [HPC test preparation](testing-hpc.md)
- [Verification records](verification/README.md)
- [Security-review archive](security/reviews/README.md)
- [Security-review remediation history](security/reviews/remediation-matrix.md)
- [Documentation truth audit](verification/2026-08-24-documentation-audit.md)

## Draft and historical project artifacts

- [Release-decision draft](release-decision-brief.md)
- [Untagged RC2 release-notes draft](release-notes.md)
- [Published release notes](releases/README.md)
- [Historical security reviews](security/reviews/README.md)
- [Historical verification evidence](verification/README.md)

## Reading rules

- “Implemented” means reachable merged behavior, not merely a class, table, or
  isolated unit test.
- “Foundation” means bounded code exists but product wiring or qualification is
  incomplete.
- “Qualified” names the exact provider/model/path/evidence that was exercised;
  it is not a general accuracy or production claim.
- “Historical” records what was true for a dated commit and must not be read as
  current implementation status.
- Unsupported or unknown input fails closed unless a current contract explicitly
  states otherwise.
