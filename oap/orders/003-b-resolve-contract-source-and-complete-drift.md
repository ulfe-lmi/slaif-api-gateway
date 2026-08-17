# OAP Work Order — 003-b

## Objective

Resolve the strategic specification contradiction reported in `003-a`, then
complete the originally intended current-contract documentation reconciliation
and registry-backed drift test on the existing PR #228.

Do not create a new PR. Do not edit the immutable `003-a` order/report. Do not
run any broad local suite.

## GitHub objective state

- Numeric objective: `003`
- Execution round: `003-b`
- PR mode: `AMEND_EXISTING_PR`
- Existing PR: `#228`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/228`
- Required head branch: `oap/003-close-contract-documentation-drift`
- Base branch: `main`
- Starting remote PR head:
  `ce15ffd22423760620424e5ff165db0c4cb69594`
- Prior transcript-only implementation head:
  `d64b490a3fa8c246d964afe2ae0965be29f97229`
- Prior round: `003-a`, truthfully `BLOCKED`
- Starting base SHA:
  `bf957a0166c03b4007fe228f1cff638d4ac7e0b8`
- Repository: `ulfe-lmi/slaif-api-gateway`

PR #228 is the one and only PR for objective 003. Amend it in place. Never
create a replacement or second objective-003 PR.

## Strategic resolution of the 003-a blocker

The coding agent correctly found that `003-a` Section E.5 required
`docs/rc2-feature-scope.md` to mark key templates implemented even though:

- that endpoint/feature scope document contains no key-template row;
- the allowed-path list prohibited editing it; and
- `docs/compatibility-matrix.md` already carries the authoritative current
  Key templates implementation row.

The strategic resolution is option 2 from the `003-a` report:

- `docs/rc2-feature-scope.md` remains unchanged and remains the source for
  endpoint/Responses/Audio/Embeddings/Realtime RC2 classifications;
- `docs/compatibility-matrix.md` remains unchanged and is the source for the
  implemented Key templates status;
- the new drift test must assert each status against the correct existing
  contract;
- there is no missing RC2 key-template row and no summary count change.

This correction does not weaken the intended coverage. It makes the test follow
the repository's existing separation of contract ownership.

## Governing instructions and required start

Re-read and obey:

1. repository `AGENTS.md`;
2. `OAP-COMMUNICATION-coding-agent.md`;
3. immutable `003-a` order/report;
4. this `003-b` order;
5. the runtime route and policy/capability registry files named in `003-a`;
6. all current/historical documents named below.

Verify PR #228 remains open, non-draft, on the required branch, and its remote
head matches the starting head. The strategic model has atomically published
this order and `oap/active=003-b` in the shared checkout. Those must be the only
dirty paths. Preserve their exact bytes and continue from the existing PR
branch. Any additional dirty tracked path or changed remote PR topology is a
blocker.

Preserve `.local-provider-catalog/`, linked worktrees, local secrets, PR #224,
and all unrelated state.

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
oap/orders/003-b-resolve-contract-source-and-complete-drift.md
tests/unit/test_documentation_contract_drift.py
```

The final report-publication commit may add only:

```text
oap/reports/003-b-resolve-contract-source-and-complete-drift.md
```

Do not edit `003-a` history, application runtime, API routes, endpoint/policy/
capability registries, `docs/rc2-feature-scope.md`,
`docs/compatibility-matrix.md`, `docs/responses-compatibility.md`, README,
product scope, accounting/forwarding contracts, schemas, migrations,
dependencies, configuration, CI, scripts, deployment, tagged release notes,
archived reviews, or unrelated files.

## Required implementation

### A. Finish objective-001 evidence reconciliation

Update the post-adoption evidence paragraph in `AGENTS.md`, append a clearly
dated post-publication outcome to
`docs/verification/2026-08-17-current-main-baseline.md`, and update
`docs/releases/README.md` plus the opening evidence discussion in
`docs/rc-beta.md`.

Preserve these two separate truths:

1. the one 24-worker matrix remains `RESULT=FAIL`, 2,533/2,534 passed, and was
   never rerun; and
2. the focused repair later completed all ten final-head GitHub checks on PR
   #226 report head `24431512a993df81f15de4e0268c40ad61e0ad57`, and
   PR #226 merged as `adaefdc45ddd13e172955c14e02cb6c97d49b629`.

The post-PR-220 128-worker qualification remains NOT RUN. Do not derive a
release, production, security, or compliance claim.

Do not erase the verification record's earlier observation that CI had not
started at its documentation time. Add the later outcome as later evidence.

### B. Correct current Embeddings status without broadening it

Remove the stale exact sentence `Embeddings API is not implemented` from the
current-facing sections of:

- `docs/rc-beta.md`;
- `docs/beta-readiness.md`;
- `docs/security-model.md`.

Replace it with the bounded implemented contract: `POST /v1/embeddings`,
separate key permission, explicit route/model capability, optional dimensions
only with its capability, PostgreSQL reservation/finalization, canonical
OpenAI forwarding, OpenRouter fail closed, and no local storage/logging of
inputs, token arrays, vectors, or raw JSON/provider bodies.

Do not edit `docs/releases/v0.1.0-rc.1.md`; its statement is historical truth
for that tag.

### C. Separate current readiness from historical RC1 evidence

In `docs/beta-readiness.md`:

- prominently label the date, PR #120 SHA, original counts, Review 5.0
  closure, and original RC1 non-goals as a historical evidence snapshot;
- preserve the historical counts rather than replacing them;
- rename/preface the RC1 non-goals section so no-Audio/no-Embeddings text is
  unmistakably historical;
- make current Known Limitations state bounded implemented Embeddings;
- remove implemented Embeddings and owned Responses/Conversations lifecycle
  slices from current Remaining Pre-GA future work;
- retain genuinely deferred hosted tools, background/cancel/list, stateful
  streaming, files, multimodal output, MFA/RBAC, native providers, production
  rehearsal, and formal assurance;
- explain that `Feature-full RC2: no` follows from missing clean current-main
  qualification/release decision, not a required-missing scope row.

In `docs/rc-beta.md`, record that `v0.1.0-rc.1` already exists and must not be
recreated or moved. A future version/tag remains a human decision after a new
release gate.

### D. Label the staged live-burn acceptance record

In `docs/streaming-live-burn-margin.md`, add a clear note immediately before
Sections 17–19 and adjust their headings/intros so they are explicitly the
historical staged documentation, Chat, and bounded Responses implementation
acceptance record. Preserve useful detail. Current implemented status at the
top and in the current behavior/status sections remains authoritative.

### E. Add the corrected registry-backed drift test

Create `tests/unit/test_documentation_contract_drift.py` as a small read-only
unit test with no external services.

It must assert:

1. every actual method/path in the `openai_compat` `/v1` router resolves to a
   plain or method-qualified member of `IMPLEMENTED_CLIENT_ENDPOINTS`;
2. every registry member resolves to an actual route, including the intentional
   plain and `POST` `/v1/conversations` aliases;
3. every registry member appears verbatim in the combined current endpoint
   contracts `docs/compatibility-matrix.md` and
   `docs/responses-compatibility.md`;
4. every `KNOWN_RESPONSES_CAPABILITIES` member is named in
   `docs/responses-compatibility.md`, as vocabulary coverage without implying
   every capability is enabled;
5. `docs/rc2-feature-scope.md` marks these endpoint/RC2 surfaces implemented:
   Responses streaming live-burn, Conversations resources/items, all three
   standalone Audio endpoints, Embeddings, and the bounded Realtime
   client-secret foundation;
6. separately, `docs/compatibility-matrix.md` marks Key templates implemented
   for calibration-derived snapshots and single-key creation;
7. the three current-facing readiness/security docs do not contain the exact
   stale Embeddings sentence; historical tagged notes are excluded;
8. objective-001 evidence retains `RESULT=FAIL` and records the later PR #226
   report head/all-ten-green/merge outcome;
9. the live-burn document contains the explicit historical staged-record label.

Do not assert that Key templates appear in `docs/rc2-feature-scope.md`. Do not
edit either canonical source just to satisfy string matching. Keep assertions
semantic and bounded rather than scanning all historical Markdown.

### F. Preserve already-correct contracts

Inspect and report no-update reasons for README/product positioning,
RC2/OpenAI/Responses/compatibility endpoint truth, accounting/forwarding,
configuration, the true future bulk-from-template boundary, historical
`v0.1.0-rc.1`, and archived reviews. Do not edit them.

## Explicit non-goals

- No runtime, route, registry, policy, capability, API, schema, migration,
  dependency, configuration, CI, script, deployment, provider, quota,
  accounting, or tool behavior change.
- No RC2 scope row/count change.
- No tagged release-note or archived-review rewrite.
- No change to prior OAP orders/reports.
- No change of the original matrix from FAIL and no claim the 128-worker run
  happened.
- No release/tag/GitHub setting action.
- No production/staging/provider/database/email/catalog action or secret access.
- No full local unit, integration, E2E, browser, Docker, or HPC suite.
- No second PR, merge, or auto-merge by the coding agent.

## Human test-economy instruction

Run only the focused checks below. The human explicitly prohibited routine
broad local suites. GitHub CI supplies broad regression evidence.

```bash
python -m pytest tests/unit/test_documentation_contract_drift.py -q
python -m pytest tests/unit/test_rc2_feature_scope_docs.py -q
python -m pytest tests/unit/test_product_scope_docs.py -q
python -m pytest tests/unit/test_oap_governance.py -q
python -m ruff check tests/unit/test_documentation_contract_drift.py
git diff --check
```

Run and report these bounded scans:

```bash
rg -n "Embeddings API is not implemented" docs/rc-beta.md docs/beta-readiness.md docs/security-model.md
rg -n "RESULT=FAIL|PR #226|24431512a993df81f15de4e0268c40ad61e0ad57|all ten" AGENTS.md docs/rc-beta.md docs/releases/README.md docs/verification/2026-08-17-current-main-baseline.md
rg -n "historical|staged|implemented" docs/beta-readiness.md docs/streaming-live-burn-margin.md
git status --short
```

The stale Embeddings scan must return no matches. If a focused check fails,
repair only the in-scope cause and rerun only that focused check. Do not run a
broad local suite.

## Acceptance criteria

1. The `003-a` contract-source blocker is resolved exactly as stated, with no
   RC2 scope edit.
2. Current-facing Embeddings contradictions are fixed honestly.
3. Original objective-001 FAIL history and later green/merged PR evidence are
   both explicit.
4. Historical RC1 and current readiness prose are visibly separated.
5. Implemented Embeddings/owned lifecycle work is absent from current future
   lists; genuinely deferred work remains.
6. Historical staged live-burn sections cannot override current status.
7. The focused test ties routes, endpoint registry, current endpoint docs,
   Responses vocabulary, RC2 endpoint status, and compatibility-matrix
   template status to their correct sources.
8. All focused checks pass and no broad local suite runs.
9. PR #228 contains only allowed objective paths and no second PR exists.
10. The final immutable report commit satisfies OAP parent/path rules and the
    coding agent does not merge.

## GitHub CI and merge gate

Inspect and report the real final-head state of the usual ten checks. Pending,
missing, cancelled, skipped, or failed is not green. Do not merge or enable
auto-merge. The strategic model independently verifies the final head and all
checks before merge.

## Commit and immutable report requirements

Commit the unchanged `003-b` order and active pointer with the remaining
implementation. Stage only explicit paths. Push to the existing branch/PR.

Before reporting, push all non-report commits and record the literal
implementation head. Publish exactly one immutable report:

```text
oap/reports/003-b-resolve-contract-source-and-complete-drift.md
```

Use the full protocol report structure. Include the `003-a` blocker resolution,
exact diff/test/check evidence, broad-suite NOT RUN list, documentation impact,
historical files preserved, no production/secret access, no extra PR, and
`Merge performed: NO`.

The final report-only commit must have the new literal implementation head as
its first parent and change only the new report. Push and verify remote head,
parent, path, and bytes, then send exactly `OK` without newline to
`response.fifo` and return to the listener.

## Failure handling

Do not broaden scope or weaken source-of-truth assertions to appear complete.
Publish truthful partial/failed/blocked evidence for any remaining material
problem. Never hide a focused failure, broad-suite run, historical rewrite,
remote-state mismatch, or report invariant failure.

Do not merge under any circumstance.
