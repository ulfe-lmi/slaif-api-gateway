# OAP Work Order — 002-a

## Objective

Refocus the repository-facing product contract from a workshop-first gateway to
an honest self-hosted organizational AI access-control proposition for SMEs and
institutions, while preserving workshops as one supported deployment profile
and making no runtime behavior claims beyond the current implementation.

This documentation-contract objective creates one new PR. It does not implement
features, change release status, or authorize production use.

## GitHub objective state

- Numeric objective: `002`
- Execution round: `002-a`
- PR mode: `CREATE_NEW_PR`
- Repository: `ulfe-lmi/slaif-api-gateway`
- Base branch: `main`
- Starting authoritative `main`:
  `adaefdc45ddd13e172955c14e02cb6c97d49b629`
- Starting state: OAP objective 001 is merged as PR #226.
- Required new branch: `oap/002-sme-product-contract`
- Required PR title: `[OAP 002] Refocus gateway on SME AI control`
- Expected unrelated open PR: Dependabot PR #224 on
  `dependabot/github_actions/github-actions-e91bde37dc`
- Prior objective PR: #226, merged; do not reuse its branch or PR.

Create exactly one new PR for objective 002. Any continuation `002-b` through
`002-z` must amend that same PR and branch.

## Current-state findings and reason for the objective

The live implementation has grown into a serious self-hosted control plane:
gateway-owned keys, per-key policy and quotas, model/provider routing,
PostgreSQL-authoritative accounting, audit data, an operator dashboard/CLI,
OpenAI-compatible clients, and content-minimizing defaults. The opening
repository language still identifies workshops, courses, and training events
as the primary product, which understates the implemented platform and no
longer reflects the human-approved direction.

The approved target audience is European SMEs and institutions that need to
govern organizational use of provider-hosted AI without distributing upstream
provider credentials. Workshop use remains valuable, but it is one policy
profile rather than the entire product identity.

The current product is not an enterprise multi-tenant SaaS, is not production
certified, and has no compliance attestation. The current SME deployment model
is one organization per deployment. Hosted/provider-side tools and external
MCP/connectors remain unsupported by current policy. Documentation must keep
those facts explicit.

## Governing instructions

Before editing, read and obey:

1. `AGENTS.md`, especially Sections 0, 1, 5.1, 9, 10.5, and 13;
2. `OAP-COMMUNICATION-coding-agent.md` in full;
3. `README.md` and its preserved top SLAIF logo/link block;
4. `docs/rc-beta.md`, `docs/beta-readiness.md`, and
   `docs/rc2-feature-scope.md` for current status boundaries;
5. `docs/accounting.md`, `docs/security-model.md`,
   `docs/responses-compatibility.md`, and
   `docs/streaming-live-burn-margin.md` for exact current promises;
6. the existing focused documentation and OAP governance tests;
7. this active work order.

GitHub is authoritative. Fetch and verify that `origin/main` still matches the
starting SHA, PR #226 is merged, no objective-002 PR already exists, and no new
state materially conflicts with this order. If it does, publish a truthful
blocked report rather than guessing.

## Required start sequence

The strategic model has atomically published this order and
`oap/active=002-a` in the shared checkout.

1. Verify the only uncommitted tracked paths are `oap/active` and this order.
2. Preserve those exact strategic-authored bytes; do not discard, overwrite,
   reformat, or edit them.
3. Preserve `.local-provider-catalog/`, linked worktrees, local secrets, and
   other unrelated state.
4. Fetch GitHub and create the required branch from current `origin/main`.
5. If the starting SHA has changed, determine whether it is a harmless remote
   synchronization difference or a material contract change. Do not silently
   base this objective on an unrelated open PR.

Any additional unexplained dirty tracked path is a blocker.

## Allowed path scope

Implementation/governance commits may change only:

```text
AGENTS.md
README.md
docs/product-scope.md
docs/rc-beta.md
oap/active
oap/orders/002-a-refocus-sme-product-contract.md
tests/unit/test_product_scope_docs.py
```

The final report-publication commit may add only:

```text
oap/reports/002-a-refocus-sme-product-contract.md
```

Do not edit historical security reviews or release notes merely to replace
accurate historical workshop/institutional wording. Do not change application
code, configuration, schemas, migrations, dependencies, lock files, CI,
scripts, deployment assets, provider catalogs, pricing, or existing OAP
orders/reports.

## Required implementation

### A. Create the canonical product-scope contract

Create `docs/product-scope.md` as the durable repository-facing product
positioning and boundary document. It must be easy for an SME operator,
contributor, and reviewer to distinguish what exists now from what is planned.

It must define all of the following.

#### Primary proposition and users

- SLAIF API Gateway is a self-hosted, OpenAI-compatible organizational AI
  access control plane for SMEs, institutions, and bounded teams.
- It keeps provider credentials server-side and lets ordinary OpenAI-compatible
  clients use gateway-issued keys.
- Operators govern provider/model/endpoint access, quotas/budgets, routing,
  pricing/accounting, and audit metadata.
- The initial commercial/operational focus is European SMEs and institutions;
  do not claim legal or regulatory compliance from geography or design intent.
- The repository remains open source and self-hostable.

#### Current deployment boundary

- The current SME MVP assumes one organization per deployment.
- Institutions, cohorts, owners, and keys are administrative/accounting
  groupings inside that deployment, not cryptographically isolated tenants.
- Current admin roles are full operators; `superadmin` metadata is not an
  enforced RBAC boundary.
- Multi-organization tenancy, tenant isolation, SSO/SCIM, MFA, full RBAC,
  compliance attestations, enterprise support/SLA, and production
  certification are not current claims.

#### Five policy profiles

Document these five operator/deployment profiles:

1. **Workshop** — short-lived participant keys, narrow models/endpoints, small
   quotas, and organizer-controlled access.
2. **Organization** — ordinary staff/team access with approved providers,
   models, endpoints, quotas, and auditable safe usage metadata.
3. **Research** — project/cohort budgets and controlled broader model access
   while preserving provider-secret and content-minimization boundaries.
4. **Agent/Codex** — bounded unattended or developer-agent use with explicit
   endpoint/tool policy, conservative budgets, and fail-closed unknowns.
5. **Trusted Evaluation** — short-lived, tightly bounded calibration/discovery
   use by trusted operators, distinct from participant/employee keys.

State explicitly that these are documented policy/deployment profiles composed
from current primitives and future roadmap capabilities. They are not five
fully implemented one-click product modes, separate tenants, or new RBAC roles.
Where a profile mentions a capability not currently implemented, label it as
target behavior.

#### Honest quota and external-tool contract

State the current and target semantics without blurring them:

- PostgreSQL is authoritative for hard per-key quota/accounting state.
- Admission reserves a bounded request; final provider usage/cost is
  authoritative when available.
- A single accepted non-streaming request may finalize above its reservation or
  cross a quota before the gateway sees final provider usage; following
  requests are blocked once finalized counters exceed limits.
- Implemented supported Chat/Responses streaming has a provisional
  gateway-side live-burn interruption brake, but it is not a provider billing
  guarantee.
- Current hosted/provider-side tools, external MCP/connectors, web/file search,
  code interpreter, computer use, and similar remote execution are unsupported
  and fail closed.
- The approved future external-tool contract is conditional: every key must be
  able to prohibit external tools; if explicitly allowed, the gateway may be
  unable to stop provider-side tool activity inside an already accepted
  Responses request before final usage becomes known, but it must account for
  the result and block later requests once the key is over quota.
- Do not claim exact mid-request tool-budget enforcement, invoice-grade
  accounting, or prevention of all upstream spend overruns.

#### Security/privacy and status boundaries

- Provider-secret isolation, HMAC-only gateway-key storage, no plaintext
  one-time secrets at rest, content-minimizing defaults, fail-closed unknowns,
  PostgreSQL accounting truth, and human release authority remain durable
  promises.
- Do not claim that SLAIF never sends content to providers; permitted requests
  necessarily forward content upstream.
- Do not claim production-ready, production-certified, formally secure,
  penetration-tested, compliant, enterprise-ready, or released RC2.
- Link the canonical implementation/status contracts rather than duplicating
  their detailed endpoint matrices.
- Separate current implemented facts, approved target behavior, and explicit
  non-goals visually and unambiguously.

### B. Refocus the README opening without rewriting implementation status

Preserve the exact SLAIF logo/link block at the top of `README.md`.

Rewrite the introductory proposition so organizational AI governance for SMEs
and institutions is primary. Keep OpenAI-compatible environment-variable usage
and upstream provider-secret protection clear. Make workshops one named profile
rather than the only intended market.

Add a prominent link to `docs/product-scope.md` near the existing status and
contract links. Briefly name the one-organization-per-deployment boundary and
the fact that this is not an enterprise-readiness or compliance claim.

Do not rewrite the long implemented/not-implemented endpoint lists except for
the minimum link/context edits needed for consistency. Do not remove legitimate
workshop examples; they demonstrate one supported profile.

### C. Update durable contributor governance

Update the opening project identity in `AGENTS.md` so future agents treat the
SME organizational control-plane proposition and five profiles as durable
product intent. Add `docs/product-scope.md` to the documentation-contract list
in Section 5.1.

Preserve current implementation/release truth. Do not rewrite the dated OAP
adoption or verification history. Do not turn the product positioning into a
claim that unimplemented external tools, tenant isolation, or enterprise
controls exist.

### D. Add a minimal status-document link

Add a short current-product-boundary link near the opening of
`docs/rc-beta.md`. Keep that release/status document focused on verification
and implemented scope. Do not rewrite its historical result, counts, commits,
or release claims.

No update is required to `docs/beta-readiness.md`, historical release notes, or
archived reviews because those documents correctly describe historical
baselines. Record that explicit documentation decision in the report.

### E. Add one focused documentation contract test

Add `tests/unit/test_product_scope_docs.py`. Keep it small and semantic rather
than duplicating the prose document.

The focused test must verify at least:

- `docs/product-scope.md` exists;
- README retains its exact top SLAIF brand block and links the scope document;
- README and product scope identify organizational AI control for SMEs or
  institutions and one organization per deployment;
- all five profile names occur in the product scope;
- the product scope distinguishes documented profiles from five fully
  implemented one-click modes;
- current hosted/external tools are unsupported and per-key external-tool
  prohibition is an approved future contract;
- later requests are blocked after finalized counters put a key over quota;
- prohibited readiness/compliance claims appear only as explicit negations or
  non-goals, not positive marketing claims.

Prefer exact stable contract phrases and bounded assertions. Do not scan every
historical file for old workshop language and do not create brittle assertions
that force all future orders/docs to repeat arbitrary prose.

## Explicit non-goals

- No application, API, schema, migration, config, dependency, CI, deployment,
  or runtime behavior change.
- No hosted/external-tool implementation or permission field.
- No quota/accounting behavior change.
- No new organizations/tenants, SSO/SCIM, MFA, RBAC, billing, license, pricing,
  commercial SLA, support plan, or compliance feature.
- No repository rename or GitHub repository description/settings change.
- No claim that current profiles are one-click modes.
- No production, staging, provider, database, email, or catalog action.
- No real upstream API calls and no secret access.
- No historical review/release-note rewrite.
- No release/tag/issue/milestone creation.
- No full local test suite, integration suite, E2E suite, browser suite,
  Docker smoke, or HPC/supercomputer harness.
- No second PR, merge, or auto-merge by the coding agent.

## Human test-economy instruction

The human explicitly instructed that broad/full local suites must not become
routine. This is a documentation-contract PR.

Run only the focused documentation/governance checks below. Do not run the full
unit suite, integration, E2E, browser, Docker, or HPC harness locally. Normal
GitHub CI supplies broad regression evidence. A CI failure may be repaired only
within this objective's allowed scope; do not start a broad local rerun to
reproduce unrelated coverage.

## Required focused local verification only

Run exactly these bounded checks after implementation:

```bash
python -m pytest tests/unit/test_product_scope_docs.py -q
python -m pytest tests/unit/test_rc2_feature_scope_docs.py -q
python -m pytest tests/unit/test_oap_governance.py -q
python -m ruff check tests/unit/test_product_scope_docs.py
git diff --check
```

Also run these read-only document checks and report their exact result:

```bash
sed -n '1,5p' README.md
rg -n "product-scope.md|one organization per deployment|Workshop|Organization|Research|Agent/Codex|Trusted Evaluation" README.md docs/product-scope.md AGENTS.md docs/rc-beta.md
rg -n -i "enterprise-ready|production-certified|compliance attestation|invoice-grade" README.md docs/product-scope.md AGENTS.md docs/rc-beta.md
git status --short
```

The final negative-claim scan may find explicit statements such as “not
enterprise-ready”; classify context honestly rather than treating every match
as a failure.

Do not run additional broad local tests. If one of the focused checks fails,
repair only an in-scope cause and rerun that focused check.

## GitHub CI and merge gate

After pushing all non-report commits and creating the PR, inspect real GitHub
checks. The usual final-head check set currently includes:

- `Unit, lint, and migration head`
- `PostgreSQL integration tests`
- `OpenAI-compatible E2E tests`
- `Playwright browser smoke`
- `Docker Compose smoke`
- `Documentation hygiene`
- `Analyze Python`
- `Analyze (python)`
- `Analyze (javascript-typescript)`
- `CodeQL`

Report actual success, failure, pending, cancelled, skipped, or missing state.
Do not call pending or missing checks green. If a check name/topology changes,
report the current GitHub truth rather than fabricating the old set.

The coding agent must not merge or enable auto-merge. The strategic model will
independently verify the final report head, diff, parent relation, acceptance
evidence, and all required final-head checks before deciding whether to merge.

## Acceptance criteria

1. Repository-facing identity consistently makes organizational AI access
   control for SMEs/institutions primary, while workshop use remains supported.
2. `docs/product-scope.md` clearly separates current implementation, target
   behavior, and non-goals.
3. The current one-organization-per-deployment SME boundary and absence of
   enterprise tenancy/RBAC/compliance promises are explicit.
4. All five profiles are defined without presenting them as five implemented
   one-click modes.
5. Quota language accurately distinguishes admission/finalization, later-call
   blocking, streaming live-burn, current remote-tool denial, and the approved
   future conditional external-tool contract.
6. README brand block and OpenAI-compatible client contract are preserved.
7. `AGENTS.md` and `docs/rc-beta.md` link and respect the new product contract;
   historical documents remain untouched.
8. All required focused local checks pass, and no broad/full local suite is
   run.
9. The PR contains only allowed paths and exactly one objective-002 PR exists.
10. The immutable final report and its report-only commit satisfy the OAP
    publication contract; the coding agent does not merge.

## Commit, PR, and immutable report requirements

Commit the unchanged strategic order and `oap/active` with the implementation
commit set. Stage only explicit paths; never use `git add .`, `git add -A`, or
`git add --all` in a mixed worktree.

Push the required branch and create exactly one PR with the required title and
base. The PR description must summarize the refocus, current-vs-target honesty,
focused verification, documentation impact, and lack of runtime changes.

Before the report, ensure every intended non-report change is committed and
pushed. Record the literal implementation head SHA.

Publish exactly one immutable report:

```text
oap/reports/002-a-refocus-sme-product-contract.md
```

Use the full report structure in `OAP-COMMUNICATION-coding-agent.md`, including:

- `Status`;
- authoritative PR/branch/SHA state;
- every implementation commit;
- literal `Implementation head SHA: <40 hex>`;
- literal `Report publication commit: SELF`;
- exact changed files and acceptance evidence;
- every focused command and result;
- explicit list of broad suites not run because this is a docs-only objective;
- implementation-head CI state at report drafting;
- documentation-impact line;
- no production/secrets/provider access;
- no scope deviation or an exact explanation;
- `Merge performed: NO`.

The final report-only commit must have the recorded implementation head as its
first parent and change only the new report file. Push it, verify it is the
remote PR head and the report bytes match, then send exactly two ASCII bytes
`OK` with no newline to `response.fifo` and return to the listener.

## Failure and blocker handling

Do not broaden scope to make this round appear successful. Publish a truthful
`PARTIAL`, `BLOCKED`, or `FAILED` report if necessary. Never conceal:

- changed GitHub/base state;
- an existing objective-002 PR;
- unrelated dirty tracked files;
- focused-test failures;
- positive enterprise/compliance overclaims;
- an accidental broad-suite run;
- pending, missing, cancelled, or failed checks;
- inability to create/push the required PR;
- a report-parent or final-head mismatch.

Do not merge under any circumstance.
