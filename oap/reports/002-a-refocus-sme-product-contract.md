# OAP Coding-Agent Report — 002-a

## Work order

- Identifier: 002-a
- Work-order file: `oap/orders/002-a-refocus-sme-product-contract.md`
- Numeric objective: 002
- PR mode: CREATED_NEW_PR
- Active-pointer SHA-256:
  `08c07120a52c62f5de320c046b90d8a1a313ded310c8bd8c0b3b7c2f9daeb904`
- Active-order SHA-256:
  `cad006b4ea126c2f615d04746e8fe566674e4d85a188b6e6a6ecd935c7b433a8`

## Status

COMPLETE

## Executive summary

Created PR #227 to refocus SLAIF's repository-facing identity from a
workshop-first gateway to an open-source, self-hosted organizational AI access
control plane for SMEs, institutions, and bounded teams. Workshop use remains
supported as one of five documented policy/deployment profiles. The new
canonical product contract clearly distinguishes current behavior, approved
target behavior, and non-goals without claiming that the profiles are five
implemented one-click modes, tenants, or RBAC roles.

The contract preserves the one-organization-per-deployment boundary; honest
PostgreSQL reservation/finalization, later-request blocking, and provisional
streaming live-burn semantics; current fail-closed hosted/external-tool policy;
the conditional future external-tool contract; and explicit readiness,
accounting, security, and privacy limitations. No runtime behavior or release
status changed.

All required focused checks passed after repairing a newly added test's own
two brittle string assertions. No broad local suite ran. All ten standard
GitHub checks passed on the implementation head. PR #227 remains open,
non-draft, and unmerged for strategic review.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 227
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/227
- PR title: `[OAP 002] Refocus gateway on SME AI control`
- PR state at report time: OPEN, non-draft
- PR merge state at report time: CLEAN and MERGEABLE
- Base branch: `main`
- Head branch: `oap/002-sme-product-contract`
- Starting remote SHA: `adaefdc45ddd13e172955c14e02cb6c97d49b629`
- Implementation head SHA: `f12544905a2a00bf64947a5eafcf3fa904e91b27`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  - `f12544905a2a00bf64947a5eafcf3fa904e91b27`
    (`Refocus product contract on SME AI control`)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes, PR #227 only
- Amended existing PR this turn: no
- Objective-002 PR count at implementation-head verification: exactly one
- Merge performed: NO
- Auto-merge enabled: NO

## Starting-state reconciliation

- Local `main` and `origin/main` both resolved to
  `adaefdc45ddd13e172955c14e02cb6c97d49b629`, the merge commit for PR #226.
- PR #226 was independently confirmed merged, and its final report head was an
  ancestor of current `main` with all ten final-head checks successful.
- The only open unrelated PR was Dependabot PR #224; it was not reused or
  modified.
- No objective-002 PR, required local/remote branch, or 002-a report existed.
- The pre-implementation working tree contained only the strategic-authored
  `oap/active=002-a` pointer and uniquely matching 002-a order.
- `origin` was the canonical
  `https://github.com/ulfe-lmi/slaif-api-gateway.git`, and `gh` authentication
  was active as `jpers1`.

## Changes made

- Submitted the strategic-authored 002-a active pointer and work order
  unchanged.
- Reframed README and durable repository governance around self-hosted
  organizational AI access control for SMEs/institutions, while retaining
  OpenAI-compatible client variables and Workshop as a supported profile.
- Added `docs/product-scope.md` as the canonical current-vs-target product
  contract.
- Documented one organization per deployment and the Workshop, Organization,
  Research, Agent/Codex, and Trusted Evaluation profiles.
- Preserved honest quota, live-burn, external-tool, provider-content,
  readiness, security, and accounting boundaries.
- Added a short product-contract link to the RC-beta status document without
  rewriting its historical results or release claims.
- Added one focused semantic documentation contract test.

## Files changed

Implementation commit:

- `AGENTS.md`
- `README.md`
- `docs/product-scope.md`
- `docs/rc-beta.md`
- `oap/active` (strategic-authored bytes committed unchanged)
- `oap/orders/002-a-refocus-sme-product-contract.md`
  (strategic-authored bytes committed unchanged)
- `tests/unit/test_product_scope_docs.py`

Report-publication commit:

- `oap/reports/002-a-refocus-sme-product-contract.md`

No application, configuration, schema, migration, dependency, lock, CI,
script, deployment, provider-catalog, pricing, historical release-note,
archived-review, or prior OAP path changed.

## Acceptance-criteria evidence

### Criterion 1 — Primary product identity

- Result: PASSED
- Evidence: README, AGENTS, RC-beta, and the new product contract make
  self-hosted organizational AI access control for SMEs/institutions primary;
  Workshop remains a first-class supported profile rather than the whole
  product identity.

### Criterion 2 — Current, target, and non-goal separation

- Result: PASSED
- Evidence: `docs/product-scope.md` defines and consistently uses `Current`,
  `Approved target`, and `Non-goal / not current` labels, and defers detailed
  endpoint status to the existing canonical contracts.

### Criterion 3 — Deployment boundary and five profiles

- Result: PASSED
- Evidence: the current SME MVP is explicitly one organization per deployment.
  Workshop, Organization, Research, Agent/Codex, and Trusted Evaluation are
  all defined, with explicit language that they are not five fully implemented
  one-click modes, separate tenants, or new RBAC roles.

### Criterion 4 — Honest security and readiness boundaries

- Result: PASSED
- Evidence: the contract preserves server-side upstream credentials, HMAC-only
  gateway-key storage, encrypted one-time delivery secrets, content-minimizing
  defaults, fail-closed unknowns, and the fact that permitted content is
  forwarded upstream. Enterprise-readiness, production certification,
  compliance attestation, penetration-test, and invoice-grade claims are
  explicitly denied.

### Criterion 5 — Honest quota and external-tool contract

- Result: PASSED
- Evidence: PostgreSQL remains authoritative; admission reserves, final usage
  finalizes, an accepted request may overrun, and later requests are blocked
  after finalized counters exceed limits. Streaming live-burn is identified as
  provisional. Hosted/provider-side tools and external MCP/connectors remain
  currently unsupported and fail closed. Future external-tool permission is
  conditional, per-key prohibitable, accounted after provider results, and not
  represented as exact mid-request enforcement.

### Criterion 6 — README compatibility and brand preservation

- Result: PASSED
- Evidence: the exact opening SLAIF logo/link block is unchanged, and README
  continues to direct ordinary clients to standard `OPENAI_API_KEY` and
  `OPENAI_BASE_URL` variables.

### Criterion 7 — Contract links and historical evidence

- Result: PASSED
- Evidence: AGENTS and RC-beta link the new product contract.
  `docs/beta-readiness.md`, historical release notes, and archived reviews were
  deliberately left untouched because they accurately describe historical
  baselines and the order explicitly excluded rewriting them.

### Criterion 8 — Focused verification only

- Result: PASSED
- Evidence: the three required focused pytest commands, changed-test Ruff, and
  diff whitespace checks passed. Required document scans passed. No full unit,
  integration, E2E, browser, Docker, or HPC/supercomputer suite ran locally.

### Criterion 9 — One PR and exact scope

- Result: PASSED
- Evidence: exactly one objective-002 PR exists. PR #227 has the required title,
  base, head branch, non-draft state, implementation-head SHA, and exactly the
  seven allowed implementation paths.

### Criterion 10 — Immutable report and merge authority

- Result: PASSED by publication protocol
- Evidence: this report is the sole path in the `SELF` commit; its remote head,
  first parent, changed path, and exact bytes are verified before FIFO `OK`.
  The coding agent did not merge or enable auto-merge.

## Focused local verification only

- Initial `python -m pytest tests/unit/test_product_scope_docs.py -q`:
  FAILED — 2 failed, 2 passed. The newly added test had two brittle assertions
  that accidentally compared contract prose against strings containing literal
  patch-artifact `+` characters. Product documentation was not the cause.
- Focused repair: normalized Markdown/whitespace in only the two affected
  assertions; no product requirement or negative assertion was removed.
- Final `python -m pytest tests/unit/test_product_scope_docs.py -q`:
  PASSED — 4 passed.
- `python -m pytest tests/unit/test_rc2_feature_scope_docs.py -q`:
  PASSED — 4 passed.
- `python -m pytest tests/unit/test_oap_governance.py -q`:
  PASSED — 8 passed.
- Initial and final
  `python -m ruff check tests/unit/test_product_scope_docs.py`:
  PASSED — `All checks passed!`.
- Initial and final `git diff --check`: PASSED.
- `sed -n '1,5p' README.md`: PASSED — exact SLAIF logo/link opening block
  remained present.
- Required product-term `rg` scan: PASSED — the product-scope link,
  one-organization boundary, and all five profile names were present in the
  required current documents.
- Required readiness/accounting negative-claim `rg` scan: PASSED — matches were
  explicit negations, limitations, or non-goals; none was a positive marketing
  claim.
- Required `git status --short`: PASSED — before staging it listed exactly the
  seven expected implementation paths; after commit it was clean.
- Allowed-path scan: PASSED — exactly seven implementation paths.
- Documentation link-target scan: PASSED.
- Changed-path control/merge-instruction scan: PASSED.
- Changed-path credential/secret-pattern scan: PASSED.
- Protected contract hashes: PASSED — `docs/beta-readiness.md`,
  `docs/rc2-feature-scope.md`, `docs/accounting.md`, `docs/security-model.md`,
  `docs/responses-compatibility.md`, `docs/streaming-live-burn-margin.md`, and
  the two existing focused governance tests retained their baseline hashes.
- Staged-path and whitespace checks: PASSED — exactly the seven allowed paths.
- `.local-provider-catalog/`: present, ignored, unstaged, and untouched.

No other local pytest command or harness/wrapper command ran during 002-a.

## Broad local suites explicitly not run

- Full unit suite: NOT RUN — prohibited by this docs-only order.
- Integration suite: NOT RUN — prohibited by this docs-only order.
- E2E suite: NOT RUN — prohibited by this docs-only order.
- Browser/Playwright suite: NOT RUN — prohibited by this docs-only order.
- Docker/Compose smoke: NOT RUN locally — prohibited by this docs-only order.
- HPC/supercomputer harness: NOT RUN — prohibited by this docs-only order.
- Real-upstream smoke: NOT RUN — prohibited; no provider secrets were accessed.

Normal GitHub CI supplied broad regression evidence without broadening the
local execution scope.

## GitHub CI / required checks

Check state observed for implementation head
`f12544905a2a00bf64947a5eafcf3fa904e91b27`: 10 SUCCESS, 0 FAILURE,
0 PENDING.

- `Analyze (javascript-typescript)`: SUCCESS — 45s.
- `Analyze (python)`: SUCCESS — 1m43s.
- `Analyze Python`: SUCCESS — 1m6s.
- `CodeQL`: SUCCESS — 2s.
- `Docker Compose smoke`: SUCCESS — 53s.
- `Documentation hygiene`: SUCCESS — 6s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m25s.
- `Playwright browser smoke`: SUCCESS — 1m14s.
- `PostgreSQL integration tests`: SUCCESS — 1m52s.
- `Unit, lint, and migration head`: SUCCESS — 1m42s.
- CI workflow run:
  https://github.com/ulfe-lmi/slaif-api-gateway/actions/runs/32067447509
- CodeQL workflow run:
  https://github.com/ulfe-lmi/slaif-api-gateway/actions/runs/32067445363
- All required checks green for the implementation head at report drafting: yes.
- Report-only commit may trigger fresh checks: strategic model must verify the
  `SELF` commit without rewriting this report.

## Documentation impact

- Added one canonical current-vs-target product contract and linked it from the
  repository's primary current-facing identity/governance/status documents.
- Repositioned workshops as one durable profile inside the broader SME and
  institutional control-plane proposition.
- Preserved exact OpenAI-compatible client environment-variable guidance and
  the README logo/link block.
- Historical documentation decision: `docs/beta-readiness.md`, historical
  release notes, and archived reviews remain unchanged because they accurately
  record historical baselines and are outside this current-product contract.
- Runtime behavior, endpoint status, and release status are unchanged.

## Local setup / dependencies

- Packages/tools/services installed or configured in 002-a: none.
- `sudo`-level setup performed in 002-a: none.
- Database, Redis, browser, Docker, provider, email, or catalog setup: none.
- Existing ignored provider-catalog artifacts were not modified or committed.
- GitHub publication used local Git for the commit/push, the connected GitHub
  app to create the non-draft PR, and authenticated `gh` to independently
  verify PR/check state.
- The `github:yeet` publication skill guided intentional path staging, commit,
  push, and PR verification; the active OAP order's required non-draft PR and
  immutable-report protocol overrode the skill's general draft-PR default.

## Safety and scope confirmations

- Unrelated files changed: no.
- Application/runtime code changed: no.
- Configuration, schema, migration, dependency, lock, CI, script, or deployment
  asset changed: no.
- Provider catalog or pricing changed: no.
- Historical release note, readiness record, or archived review changed: no.
- Production secrets accessed: no.
- Production systems accessed: no.
- Production/staging database, deployment, provider, email, or catalog action:
  no.
- Real upstream API call: no.
- Required focused tests skipped/not run: no.
- Broad local tests not run: yes — explicitly prohibited for this docs-only
  objective and itemized above.
- Scope deviation: no.
- Extra PR created for same numeric objective: NO.
- PR #224 modified: NO.
- Release, tag, issue, milestone, or repository setting changed: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- Activated order or `oap/active` content edited by coding agent: NO; exact
  strategic-authored bytes were submitted unchanged.
- Report-publication commit changes only this report file: yes.

## Known limitations / residual risk

- This is a documentation-contract change; it does not implement the approved
  target workflows, new tenancy, RBAC, hosted/external tools, or runtime
  behavior.
- The current project remains an RC-beta foundation, not enterprise-ready,
  production-certified, compliance-attested, penetration-tested, or
  invoice-grade.
- An accepted provider request can still exceed its reservation before final
  usage becomes known; PostgreSQL finalization blocks later admission after
  finalized counters exceed limits.
- Hosted/provider-side tools and external MCP/connectors remain unsupported and
  fail closed.
- The 128-worker post-PR-220 qualification remains NOT RUN.
- The report-containing `SELF` head may trigger fresh checks and requires
  independent strategic verification.

## Recommended strategic follow-up

Independently verify the `SELF` report commit, its first parent, sole changed
path, exact report bytes, final-head check state, and the seven-path
documentation-only scope. If all required final-head checks succeed and the
current-vs-target product contract is satisfactory, the strategic model may
exercise its OAP merge authority for PR #227. Future profile presets,
multi-organization tenancy, stronger RBAC, or external-tool permissions require
separate explicit objectives. The coding agent did not merge or enable
auto-merge.
