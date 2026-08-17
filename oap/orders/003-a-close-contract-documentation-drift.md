# OAP Work Order — 003-a

## Objective

Close the verified API, Responses, route-registry, verification, security, and
readiness documentation drift on current `main`, and add a focused automated
contract test that makes future route/status contradictions fail visibly.

This objective changes documentation and a documentation-contract test only.
Do not change runtime behavior to make old prose true.

## GitHub objective state

- Numeric objective: `003`
- Execution round: `003-a`
- PR mode: `CREATE_NEW_PR`
- Repository: `ulfe-lmi/slaif-api-gateway`
- Base branch: `main`
- Starting authoritative `main`:
  `bf957a0166c03b4007fe228f1cff638d4ac7e0b8`
- Starting state: OAP objective 002 is merged as PR #227.
- Required new branch: `oap/003-close-contract-documentation-drift`
- Required PR title: `[OAP 003] Close current contract documentation drift`
- Expected unrelated open PR: Dependabot PR #224 on its existing branch.
- Published release/tag: `v0.1.0-rc.1` only; it is a historical artifact and
  must not be retagged or rewritten as current state.

Create exactly one new PR for objective 003. Any continuation `003-b` through
`003-z` must amend that same PR and branch.

## Reconciled current-state findings

The canonical current endpoint and Responses contracts are substantially
accurate:

- `docs/rc2-feature-scope.md` has 27 required-implemented rows and zero
  required-missing rows;
- `docs/openai-compatibility.md`, `docs/responses-compatibility.md`,
  `docs/compatibility-matrix.md`, `docs/accounting.md`, and
  `docs/provider-forwarding-contract.md` describe the merged bounded
  Conversations, standalone Audio, Embeddings, Realtime client-secret,
  Responses lifecycle/template, and streaming live-burn slices;
- `IMPLEMENTED_CLIENT_ENDPOINTS` in
  `app/slaif_gateway/services/key_policy_validation.py` contains the registered
  gateway-key `/v1` surfaces, including method-qualified Responses and
  Conversations resources;
- the actual FastAPI routes live in
  `app/slaif_gateway/api/openai_compat.py`;
- `KNOWN_RESPONSES_CAPABILITIES` in
  `app/slaif_gateway/services/responses_route_capabilities.py` is the live
  Responses route-capability vocabulary.

Verified drift that must be fixed:

1. `docs/rc-beta.md`, `docs/beta-readiness.md`, and
   `docs/security-model.md` still say `Embeddings API is not implemented`,
   despite the bounded implemented `/v1/embeddings` route.
2. `docs/rc-beta.md`, `docs/releases/README.md`, and the objective-001
   verification record stop at implementation-head CI being pending/unknown.
   GitHub now proves PR #226 merged at
   `adaefdc45ddd13e172955c14e02cb6c97d49b629`, its report head was
   `24431512a993df81f15de4e0268c40ad61e0ad57`, and all ten final-head checks
   succeeded. This does not turn the original full matrix from FAIL into PASS.
3. The post-adoption section of `AGENTS.md` still describes standard PR CI as
   a possibility rather than the now-observed green/merged outcome.
4. `docs/beta-readiness.md` mixes a dated/historical RC1 evidence snapshot with
   later current-state amendments. Its RC1 no-Embeddings/no-Audio statements
   need an explicit historical label, while its current Known Limitations and
   Remaining Pre-GA text must stop treating already implemented Embeddings and
   broader Responses lifecycle as future work.
5. Sections 17–19 of `docs/streaming-live-burn-margin.md` are the original
   staged documentation/Chat/Responses acceptance plan. The document header
   correctly says both bounded slices are implemented, but those staged
   sections are not clearly labeled historical and contain superseded future
   wording.
6. The current route/policy/capability documentation alignment is not enforced
   by one focused registry-backed test.

Historical `docs/releases/v0.1.0-rc.1.md` correctly records the capabilities of
that tagged release and may continue to say Embeddings was not implemented in
that release. Archived security reviews are also historical evidence. Do not
rewrite either category.

## Governing instructions

Before editing, read and obey:

1. `AGENTS.md`, especially Sections 0, 5.1, 9, 10.5, and 13;
2. `OAP-COMMUNICATION-coding-agent.md` in full;
3. this work order;
4. `app/slaif_gateway/api/openai_compat.py`;
5. `app/slaif_gateway/services/key_policy_validation.py`;
6. `app/slaif_gateway/services/responses_route_capabilities.py`;
7. all documents named in the reconciled findings;
8. existing focused RC2, product-scope, and OAP governance tests.

Fetch and verify that `origin/main` still matches the starting SHA, PR #227 is
merged, no objective-003 PR exists, the tag/release state is unchanged, and no
new state materially conflicts with this order. GitHub is authoritative. If a
material conflict exists, publish a truthful blocked report rather than
guessing.

## Required start sequence

The strategic model has atomically published this order and
`oap/active=003-a` in the shared checkout.

1. Verify the only uncommitted tracked paths are `oap/active` and this order.
2. Preserve those exact strategic-authored bytes; do not discard, overwrite,
   reformat, or edit them.
3. Preserve `.local-provider-catalog/`, linked worktrees, local secrets, and
   all unrelated state.
4. Create the required branch from current `origin/main`.

Any additional unexplained dirty tracked path is a blocker.

## Allowed path scope

Implementation/governance commits may change only:

```text
AGENTS.md
docs/beta-readiness.md
docs/rc-beta.md
docs/releases/README.md
docs/security-model.md
docs/streaming-live-burn-margin.md
docs/verification/2026-08-17-current-main-baseline.md
oap/active
oap/orders/003-a-close-contract-documentation-drift.md
tests/unit/test_documentation_contract_drift.py
```

The final report-publication commit may add only:

```text
oap/reports/003-a-close-contract-documentation-drift.md
```

Do not edit application runtime, API routes, policy/capability registries,
schemas, migrations, dependencies, lock files, configuration, CI, scripts,
deployment assets, provider catalogs, pricing, README, the new product-scope
contract, canonical endpoint/Responses/accounting/forwarding documents that
already match code, tagged release notes, archived security reviews, or prior
OAP orders/reports.

## Required implementation

### A. Record the final objective-001 outcome without rewriting history

Update the post-adoption evidence paragraph in `AGENTS.md` to state:

- the focused governance repair remained separate from the original matrix;
- PR #226/report head `24431512a993df81f15de4e0268c40ad61e0ad57`
  completed all ten final-head checks successfully;
- PR #226 merged as
  `adaefdc45ddd13e172955c14e02cb6c97d49b629`;
- no second full harness was run;
- the original 2,533/2,534 `RESULT=FAIL` evidence and unrun 128-worker
  qualification remain unchanged;
- no release, RC2, production, security, or compliance claim follows.

Append a clearly dated post-publication outcome to
`docs/verification/2026-08-17-current-main-baseline.md`. Do not delete or alter
the earlier “CI had not started at documentation time” observation; it was true
at that moment. The appendix must distinguish later GitHub evidence from the
original full-matrix result.

Update `docs/releases/README.md` and the opening evidence discussion in
`docs/rc-beta.md` consistently. Do not call the failed matrix green.

### B. Correct current Embeddings status

Replace the stale current-facing `Embeddings API is not implemented` statements
in:

- `docs/rc-beta.md`;
- `docs/beta-readiness.md` current Known Limitations/current-state material;
- `docs/security-model.md`.

Describe only the implemented bounded surface:

- `POST /v1/embeddings`;
- separate key endpoint permission;
- explicit route/model `embeddings` capability;
- optional `dimensions` only with explicit capability;
- PostgreSQL reservation/finalization;
- canonical OpenAI forwarding and OpenRouter fail-closed behavior;
- no local storage/logging of input strings, token arrays, vectors, or raw
  JSON/provider bodies.

Do not imply support for every Embeddings field/provider or weaken the current
privacy/accounting boundary.

Do not edit `docs/releases/v0.1.0-rc.1.md`: its unimplemented statement is true
for the historical tagged release.

### C. Separate the historical RC1 snapshot from current readiness

In `docs/beta-readiness.md`:

- add a prominent early note explaining that the date, PR #120 SHA, original
  verification counts, Review 5.0 closure, and original RC1 non-goals are a
  historical evidence snapshot, not the current repository inventory;
- preserve those historical counts and evidence rather than silently updating
  them to current numbers;
- rename or preface the RC1 non-goals section so its no-Audio/no-Embeddings
  statements cannot be mistaken for current `main`;
- keep current Known Limitations current, including bounded implemented
  Embeddings;
- remove Embeddings and already implemented owned Conversations/lifecycle
  slices from current Remaining Pre-GA/future-work prose;
- keep genuinely deferred Responses hosted tools, background/cancel/list,
  stateful streaming, files, multimodal output, MFA/RBAC, native providers,
  production rehearsal, and formal assurance explicit;
- keep `Feature-full RC2: no` tied to missing current-main qualification and
  release decision, not to a nonexistent required-missing feature row.

In `docs/rc-beta.md`, make the tag guidance current: `v0.1.0-rc.1` already
exists and must not be recreated or moved; any future tag/version is a human
maintainer decision after its own gate.

### D. Label staged live-burn prose accurately

In `docs/streaming-live-burn-margin.md`, add a clear note before Sections 17–19
that they preserve the original staged implementation acceptance record:

- documentation-only phase;
- Chat implementation phase;
- bounded Responses implementation phase.

Make their headings/intros past tense or explicitly historical so phrases such
as “future live-burn” cannot override the current implemented status at the top
and in Sections 13, 14, and 20. Preserve useful acceptance detail. Do not rewrite
the current behavior or add new live-burn scope.

### E. Add one registry-backed documentation drift test

Create `tests/unit/test_documentation_contract_drift.py`. Keep it focused and
read-only. It may import production constants/routers, but must not change
runtime code or require a database, Redis, browser, Docker, network, or real
provider.

The test must enforce these durable relationships:

1. Every actual `/v1` route and HTTP method registered by the
   `openai_compat` router resolves to either a plain or method-qualified member
   of `IMPLEMENTED_CLIENT_ENDPOINTS`.
2. Every member of `IMPLEMENTED_CLIENT_ENDPOINTS` resolves to an actual
   registered `/v1` route, allowing the intentional plain and
   method-qualified `/v1/conversations` aliases.
3. Every member of `IMPLEMENTED_CLIENT_ENDPOINTS` appears verbatim in the
   combined canonical current endpoint documents
   `docs/compatibility-matrix.md` and `docs/responses-compatibility.md`.
4. Every member of `KNOWN_RESPONSES_CAPABILITIES` is named in
   `docs/responses-compatibility.md`, so adding/removing registry vocabulary
   forces a documentation review. This is vocabulary coverage, not a claim
   that every known capability is enabled; the document must continue to
   distinguish supported and fail-closed capabilities.
5. The RC2 scope document marks these key merged surfaces as implemented:
   Conversations resources/items, all three standalone Audio endpoints,
   Embeddings, Realtime client-secret foundation, key templates, and Responses
   streaming live-burn.
6. Current-facing readiness/security documents no longer contain the exact
   stale positive sentence `Embeddings API is not implemented`.
7. Historical tagged release notes are intentionally excluded from that stale
   current-doc assertion.
8. The objective-001 evidence documents contain both the original failed
   matrix classification and the later all-ten-green/merged PR #226 outcome.
9. The live-burn milestone contains the explicit historical staged-record
   label before the old phase acceptance sections.

Use semantic helpers where useful. Avoid scanning archived reviews, tagged
release notes, or all Markdown for words like `future`; accurate future and
historical statements must remain possible.

### F. Confirm accurate contracts need no changes

Inspect but do not edit these unless a new material contradiction makes this
order impossible:

```text
README.md
docs/product-scope.md
docs/rc2-feature-scope.md
docs/openai-compatibility.md
docs/responses-compatibility.md
docs/compatibility-matrix.md
docs/accounting.md
docs/provider-forwarding-contract.md
docs/configuration.md
docs/key-templates.md
docs/releases/v0.1.0-rc.1.md
```

The report must state why each category remains correct: current endpoint
contract, current Responses vocabulary/status, current accounting/forwarding
invariants, true bulk-template future boundary, or historical tagged evidence.

## Explicit non-goals

- No runtime/API/policy/capability behavior change.
- No new endpoint, field, provider, accounting, quota, tool, or admin feature.
- No registry edit merely to make a test pass.
- No schema, migration, dependency, config, CI, script, or deployment change.
- No rewrite of tagged release notes or archived reviews.
- No reclassification of the original objective-001 full matrix from FAIL.
- No claim that post-PR-220 128-worker qualification ran.
- No release/tag creation, movement, deletion, or GitHub setting change.
- No production/staging/provider/database/email/catalog action.
- No real upstream call and no secret access.
- No full local unit, integration, E2E, browser, Docker, or HPC suite.
- No second PR, merge, or auto-merge by the coding agent.

## Human test-economy instruction

The human explicitly instructed that full suites must not be routine. This is a
documentation-contract objective with one small read-only unit test.

Run only the focused checks below. Do not run the full unit suite, integration,
E2E, browser, Docker, or HPC harness locally. Normal GitHub CI supplies broad
regression evidence. If a focused check fails, repair only an in-scope cause
and rerun that focused check.

## Required focused local verification only

```bash
python -m pytest tests/unit/test_documentation_contract_drift.py -q
python -m pytest tests/unit/test_rc2_feature_scope_docs.py -q
python -m pytest tests/unit/test_product_scope_docs.py -q
python -m pytest tests/unit/test_oap_governance.py -q
python -m ruff check tests/unit/test_documentation_contract_drift.py
git diff --check
```

Also run and report these bounded read-only scans:

```bash
rg -n "Embeddings API is not implemented" docs/rc-beta.md docs/beta-readiness.md docs/security-model.md
rg -n "RESULT=FAIL|PR #226|24431512a993df81f15de4e0268c40ad61e0ad57|all ten" AGENTS.md docs/rc-beta.md docs/releases/README.md docs/verification/2026-08-17-current-main-baseline.md
rg -n "historical|staged|implemented" docs/beta-readiness.md docs/streaming-live-burn-margin.md
git status --short
```

The Embeddings stale scan must return no matches in those three current-facing
documents. Do not broaden it to the historical tagged release note.

## GitHub CI and merge gate

After pushing all non-report commits and creating the PR, inspect real GitHub
checks. The usual final-head set currently has ten checks:

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
Do not call pending or missing checks green. The coding agent must not merge or
enable auto-merge. The strategic model independently verifies the final report
head, diff, parent relation, evidence, and all required final-head checks.

## Acceptance criteria

1. The three current-facing Embeddings contradictions are corrected without
   overclaiming provider/field scope.
2. Objective-001 evidence retains `RESULT=FAIL` history and records the later
   green/merged PR #226 outcome distinctly.
3. RC1 historical counts/non-goals and current readiness claims are visibly
   separated.
4. Current Remaining Pre-GA text does not list implemented Embeddings or owned
   Conversations lifecycle as future work.
5. Historical live-burn phase acceptance prose cannot be mistaken for current
   feature status.
6. The new focused test aligns actual `/v1` routes, gateway-key endpoint
   registry, canonical endpoint docs, and Responses capability vocabulary.
7. Unsupported/deferred and maintainer-decision surfaces remain explicit.
8. Tagged release notes and archived historical evidence remain unchanged.
9. All focused local checks pass and no broad local suite runs.
10. Exactly one objective-003 PR contains only allowed paths, its final report
    commit satisfies OAP invariants, and the coding agent does not merge.

## Commit, PR, and immutable report requirements

Commit the unchanged strategic order and `oap/active` with the implementation
commit set. Stage only explicit paths; never use broad staging in a mixed
worktree.

Push the required branch and create exactly one PR with the required title and
base. The PR description must summarize concrete drift fixed, historical-vs-
current treatment, registry-backed test, focused verification, and lack of
runtime changes.

Before reporting, push every intended non-report commit and record the literal
implementation head SHA. Publish exactly one immutable report:

```text
oap/reports/003-a-close-contract-documentation-drift.md
```

Use the full report structure in `OAP-COMMUNICATION-coding-agent.md`. Include:

- authoritative PR/branch/SHA state and every implementation commit;
- literal `Implementation head SHA: <40 hex>`;
- literal `Report publication commit: SELF`;
- exact files and acceptance evidence;
- every focused command/result and explicit broad-suite NOT RUN list;
- implementation-head GitHub check state;
- documentation-impact line;
- historical files inspected but deliberately unchanged;
- no production/secrets/provider access;
- no scope deviation or an exact explanation;
- `Merge performed: NO`.

The final report-only commit must have the recorded implementation head as its
first parent and change only the new report. Push and verify the remote head,
parent, path, and report bytes. Then send exactly two ASCII bytes `OK` with no
newline to `response.fifo` and return to the listener.

## Failure and blocker handling

Publish a truthful `PARTIAL`, `BLOCKED`, or `FAILED` report rather than
broadening scope or hiding a contradiction. Never conceal changed GitHub state,
dirty unrelated files, route/registry mismatch, focused-test failure, an
accidental broad-suite run, pending/failed checks, historical-evidence damage,
publication failure, or report-parent mismatch.

Do not merge under any circumstance.
