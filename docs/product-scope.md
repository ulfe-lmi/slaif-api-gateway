# Product Scope

SLAIF API Gateway is an open-source, self-hosted, OpenAI-compatible
**organizational AI access control plane** for SMEs, institutions, and bounded
teams. Its initial commercial and operational focus is European SMEs and
institutions, but that geography and design intent do not establish legal or
regulatory compliance.

Operators keep upstream provider credentials server-side. Users and software
use gateway-issued keys through ordinary OpenAI-compatible clients, while the
operator governs providers, models, endpoints, per-key policy, quotas and
budgets, routing, pricing/accounting, and safe audit metadata.

## How to read this contract

| Label | Meaning |
| --- | --- |
| **Current** | Implemented behavior, still subject to the detailed endpoint and status contracts linked below. |
| **Approved target** | Product direction that is not a claim of current implementation. It requires separately reviewed implementation, safety, tests, and documentation. |
| **Non-goal / not current** | A capability or assurance the project does not presently claim. |

The detailed endpoint matrix remains in
[`rc2-feature-scope.md`](rc2-feature-scope.md). This document defines product
identity and boundaries; it does not override implementation/status contracts.

## Primary proposition and users

### Current

- Self-hosted organizational control for provider-hosted AI access.
- Gateway-issued keys for ordinary OpenAI-compatible clients without exposing
  upstream provider credentials to users.
- Explicit provider, model, endpoint, route/capability, and key policy.
- PostgreSQL-backed quota/accounting truth, routing/pricing metadata, safe usage
  metadata, audit records, and operator dashboard/CLI workflows.
- Open-source deployment controlled by the adopting organization.
- Workshops, research groups, staff teams, and trusted evaluation operators as
  supported use cases inside the same deployment boundary.

### Approved target

- A clearer SME/institution operator experience built from the same fail-closed
  policy, provider-secret, accounting, and audit foundations.
- Reviewed profile presets and guided workflows where they can be implemented
  without weakening the explicit per-key policy contract.

### Non-goals / not current

- SLAIF is not an enterprise multi-tenant SaaS and is not enterprise-ready.
- SLAIF is not production-certified and has no compliance attestation.
- It does not claim that an SME deployment is legally compliant merely because
  it is self-hosted or aimed at European organizations.

## Current deployment boundary

The current SME MVP assumes **one organization per deployment**.

Institutions, cohorts, owners, templates, and gateway keys are
administrative/accounting groupings inside that deployment. They are not
cryptographically isolated tenants. Every active admin is currently a full
operator; `superadmin` is metadata and future-proofing, not an enforced RBAC
boundary.

### Approved target

Future work may add multi-organization tenancy, tenant isolation, SSO/SCIM,
MFA, full RBAC, enterprise support/SLA, or stronger operator separation only
through explicit architecture, threat-model, schema, migration, test, and
documentation objectives.

### Non-goals / not current

- No multi-organization tenant-isolation claim.
- No SSO/SCIM, MFA, or full RBAC claim.
- No enterprise support or commercial SLA claim.
- No production certification, formal security certification, penetration-test
  claim, or compliance attestation.

## Five policy and deployment profiles

These are documented policy/deployment profiles composed from current
primitives and future roadmap capabilities. They are **not five fully
implemented one-click modes**, separate tenants, or new RBAC roles. Any
capability marked as target behavior remains unimplemented until a separate
approved change proves otherwise.

### 1. Workshop

**Current:** organizers can issue short-lived participant keys with narrow
model/endpoint allowlists, small per-key quotas, validity windows, cohorts, and
organizer-controlled access. This remains a first-class supported profile.

**Approved target:** reviewed workshop presets and bounded bulk participant
workflows that preserve explicit policy, audit, secret-delivery, and accounting
semantics.

### 2. Organization

**Current:** staff or team keys can be limited to approved providers, models,
and endpoints with per-key quotas/budgets and auditable content-minimizing usage
metadata.

**Approved target:** guided organization policy baselines, reviewable template
application, and operator reporting suited to a single-organization deployment.

### 3. Research

**Current:** owners, cohorts, templates, route policy, and per-key budgets can
represent bounded projects with controlled broader model access while retaining
provider-secret isolation and content-minimizing defaults.

**Approved target:** clearer project/cohort budget views and reviewed research
presets. Cross-project tenancy or content capture is not implied.

### 4. Agent/Codex

**Current:** unattended or developer-agent use can receive a gateway key with
explicit endpoint/model/provider/capability policy, conservative request/token/
cost budgets, and fail-closed handling of unknown or unsupported fields. Current
hosted/provider-side tools and external connectors remain denied.

**Approved target:** narrowly reviewed agent presets and conditional external-
tool policy only after its permission, accounting, privacy, and overrun contract
is implemented. An Agent/Codex profile is not authorization for unrestricted
remote execution.

### 5. Trusted Evaluation

**Current:** trusted calibration keys support short-lived, low-request-count
discovery by trusted organizers/admins through normal gateway authentication,
provider-secret isolation, policy, reservation/finalization, safe usage
profiling, and audit. They are not participant or ordinary employee keys.

**Approved target:** stronger reviewed recommendation workflows while retaining
short validity, bounded exposure, and explicit human confirmation before normal
participant/staff policy is created.

## Quota and accounting contract

### Current

- PostgreSQL is authoritative for hard per-key quota/accounting state.
- Admission estimates and atomically reserves a bounded request. Final provider
  usage and cost are authoritative when available.
- A single accepted non-streaming request may finalize above its reservation or
  cross a quota before the gateway sees final provider usage. Following
  requests are blocked once finalized counters exceed key limits.
- Implemented supported Chat Completions and Responses streaming use a
  provisional gateway-side live-burn interruption brake. It estimates visible
  output and may stop forwarding, but it is not a provider billing guarantee.
- Accounting records safe usage/cost metadata; it does not become invoice-grade
  merely because provider usage was available.

### Non-goals / not current

- No exact mid-request cost or tool-budget enforcement guarantee.
- No guarantee that every accepted request remains below its reservation.
- No invoice-grade accounting claim and no guarantee that all upstream spend
  overruns can be prevented.

See [`accounting.md`](accounting.md) and
[`streaming-live-burn-margin.md`](streaming-live-burn-margin.md) for the detailed
implemented invariants and failure behavior.

## Hosted and external tool contract

### Current

Current: hosted/provider-side tools and external MCP/connectors are unsupported
in the runtime. It is deny-only for those surfaces, provider URL fetch
authority, and unknown/ambiguous authority. Objective 012 adds the version-1
taxonomy and policy/admission contract. Objective 013 stores canonical policy
on keys, immutable template snapshots, and routes, and adds narrowed settings
plus audited admin/CLI controls; objective 013 storage adds no request
forwarding, fence, hold, or provider integration. Objective 014 implements the
fence and full-remaining-balance reservation foundation on the locked key row
(no forwarding, no hold): the reservation binds the exact provider and
route identity, the fence is exclusive against any committed pending
reservation or unreconciled counter in either lock order, and only exact
zero-counter terminal evidence clears it. The runtime remains deny-only for
provider-hosted/external tools, external forwarding and the unknown-cost hold
are still not implemented, fence expiry never means safe release, and the
exact overrun promise remains conditional on the later provider activation
owned by objectives 015 and 016. Implemented local/client-side function, custom,
namespace, local-shell, and client-side apply-patch workflows keep their
existing independent gates and do not grant SLAIF provider/external authority.

### Approved target

Approved target: every key must be able to prohibit external tools.
`strict_bounded` is the default approved mode and denies provider-hosted/
external authority. `external_tool_fenced` is the only approved future opt-in
mode for a standard key with exact route support, operator ceilings, positive
finite request/token/EUR limits, and explicit acknowledgement.

Its promise is exact: one admitted provider-hosted external-tool request may
exceed the key's remaining token or cost quota before SLAIF regains control.
SLAIF will reject concurrent requests for that key while the request is
unresolved, finalize authoritative provider usage/cost when available, reject
following requests after exhaustion, and retain a blocking accounting hold
when final cost is missing, ambiguous, interrupted, or awaiting reconciliation.

Any such implementation requires explicit per-key permissions, fail-closed
unknowns, route/model/tool capability, pricing and bounded exposure, privacy and
storage rules, negative tests, auditability, and operator-visible limits.

### Non-goals / not current

- No stored hosted-tool, MCP, or external-tool policy is consumed by runtime
  request admission. The objective-014 fence and reservation foundation is
  implemented, but external forwarding and the unknown-cost hold are still
  not implemented; objectives 015 and 016 own the hold/reconciliation and
  selected provider execution before activation.
- No claim of exact mid-request external-tool interruption or tool-budget
  enforcement.
- No claim that local function/custom tool support authorizes provider-hosted
  execution.

See [`responses-compatibility.md`](responses-compatibility.md) for the current
Responses subset and explicit hosted-tool exclusions.

## Security and privacy boundaries

### Current durable promises

- Upstream provider credentials stay server-side and client authorization is
  replaced before provider forwarding.
- Gateway keys are stored as HMAC values with key-version metadata, not as
  recoverable plaintext.
- One-time delivery secrets are encrypted rather than stored as plaintext at
  rest, expire, and are consumed or rendered unusable after delivery handling.
- Content-minimizing defaults avoid local prompt, completion, media, raw body,
  and provider-response storage for the documented request paths.
- Unknown endpoints, fields, capabilities, prices, and unsupported tool types
  fail closed according to their detailed contracts.
- PostgreSQL remains authoritative for quota/accounting state.
- Human maintainer/strategic authority retains release and risk-acceptance
  decisions.

Content minimization does not mean content never leaves the deployment.
Permitted inference requests necessarily forward user content to the selected
upstream provider under that provider relationship. Operators remain
responsible for provider choice, data-processing terms, deployment security,
retention, access control, and applicable law.

### Non-goals / not current

SLAIF is not enterprise-ready, is not production-certified, has no compliance
attestation, and does not provide invoice-grade accounting. It has no formal
security certification or current penetration-test claim. These are explicit
boundaries, not positive marketing claims.

## Canonical implementation and status contracts

- [`rc2-feature-scope.md`](rc2-feature-scope.md) — canonical endpoint/feature
  classification.
- [`openai-compatibility.md`](openai-compatibility.md) and
  [`compatibility-matrix.md`](compatibility-matrix.md) — supported client/API
  behavior.
- [`provider-forwarding-contract.md`](provider-forwarding-contract.md) —
  outbound provider boundary.
- [`accounting.md`](accounting.md) and
  [`streaming-live-burn-margin.md`](streaming-live-burn-margin.md) — quota,
  finalization, and live-burn behavior.
- [`security-model.md`](security-model.md) — secret, content, operator, Redis,
  email, and logging boundaries.
- [`responses-compatibility.md`](responses-compatibility.md) — current Responses
  lifecycle/tool support and exclusions.
- [`rc-beta.md`](rc-beta.md) and [`verification/README.md`](verification/README.md)
  — release-candidate status and commit/environment-specific verification
  evidence.

Nothing in this product contract changes runtime behavior or release status.
