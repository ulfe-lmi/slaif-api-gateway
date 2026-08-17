# OAP Work Order — 003-c

## Objective

Remove the final historical/current ambiguity found in independent strategic
review of `docs/beta-readiness.md`, strengthen the focused drift assertion, and
amend PR #228 only.

This is a minimal wording/test continuation. Do not create a new PR and do not
run a broad local suite.

## GitHub objective state

- Numeric objective: `003`
- Execution round: `003-c`
- PR mode: `AMEND_EXISTING_PR`
- Existing PR: `#228`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/228`
- Required head branch: `oap/003-close-contract-documentation-drift`
- Base branch: `main`
- Starting remote PR head:
  `feaf5c0636f06a0ed27f43fe284f0ec6e56f8386`
- Prior implementation head:
  `4905af63ff20dfcf5b7f67eb36f797a9b1151da4`
- Prior rounds: `003-a` blocked, `003-b` complete
- Repository: `ulfe-lmi/slaif-api-gateway`

PR #228 remains the sole objective-003 PR. Amend it; never create a second PR.

## Why 003-b needs this narrow continuation

The `003-b` implementation correctly reconciled endpoint, Embeddings,
objective-001, live-burn, and contract-source drift. Independent strategic
review found three residual phrases in `docs/beta-readiness.md` that can still
mislead a reader despite the new historical snapshot callout:

1. `Status: RC-beta readiness candidate after verification fixes.` appears
   before the historical boundary and reads like current status.
2. `It records a release-candidate beta verification pass for the current
   implemented scope.` uses “current” for a historical 2026-05-01 result.
3. The current Remaining Pre-GA list says `Continue Responses API as scoped RC2
   work` even though the canonical matrix has zero `RC2_REQUIRED_MISSING` rows;
   the listed hosted/background/files/multimodal expansions are separately
   deferred work, not missing required RC2 scope.

These are documentation wording issues only. No behavior or broader document
reconciliation is authorized.

## Governing instructions and start sequence

Re-read `AGENTS.md`, the full coding-agent protocol, immutable `003-a`/`003-b`
orders and reports, this order, `docs/beta-readiness.md`, the new drift test,
and `docs/rc2-feature-scope.md` as read-only truth.

Verify PR #228 remains open/non-draft on the required branch and exact starting
head. The strategic model has atomically published this order and
`oap/active=003-c`; those must be the only dirty paths. Preserve them unchanged.
Do not modify PR #224 or unrelated local state.

## Allowed path scope

Implementation/governance commits may change only:

```text
docs/beta-readiness.md
oap/active
oap/orders/003-c-remove-final-readiness-ambiguity.md
tests/unit/test_documentation_contract_drift.py
```

The final report-publication commit may add only:

```text
oap/reports/003-c-remove-final-readiness-ambiguity.md
```

Do not edit prior OAP history, other documentation, runtime, registries,
dependencies, CI, configuration, schemas, scripts, or any unrelated path.

## Required implementation

Make only these semantic changes in `docs/beta-readiness.md`:

1. Change the opening status label to make it explicitly historical and dated,
   for example `Historical status (2026-05-01): ...`.
2. Change the certification disclaimer sentence so it says the report records
   the release-candidate verification pass for the scope implemented and
   documented at that historical baseline—not “the current implemented scope”.
3. Rewrite the current Remaining Pre-GA Responses bullet to say that further
   expansion beyond the current implemented RC2 boundary is separately scoped
   work. Preserve the genuinely deferred list: hosted tools,
   background/cancel/list, stateful streaming, files, multimodal output, bulk
   send-now, and native provider adapters.
4. Make the final release-note link call `v0.1.0-rc.1` the historical first
   RC-beta tag rather than a still-recommended future tag.

Preserve the historical counts, current bounded Embeddings text, final verdict,
zero-required-missing statement, missing qualification/release decision, and
all other 003-b corrections.

Update `tests/unit/test_documentation_contract_drift.py` minimally to assert:

- the explicit historical status label exists;
- the exact misleading phrase `for the current implemented scope` is absent;
- the current Remaining Pre-GA section contains the separate-expansion wording
  and does not contain `Continue Responses API as scoped RC2 work`.

Keep all existing drift tests. Do not scan historical release notes or weaken
endpoint/registry/capability coverage.

## Focused verification only

Run only:

```bash
python -m pytest tests/unit/test_documentation_contract_drift.py -q
python -m pytest tests/unit/test_rc2_feature_scope_docs.py -q
python -m pytest tests/unit/test_oap_governance.py -q
python -m ruff check tests/unit/test_documentation_contract_drift.py
git diff --check
rg -n "Historical status|current implemented scope|Continue Responses API as scoped RC2 work|beyond the current implemented RC2 boundary|historical first RC-beta" docs/beta-readiness.md
git status --short
```

No full unit, product-contract, integration, E2E, browser, Docker, or HPC suite.
Normal GitHub CI supplies broad evidence.

## Acceptance criteria

1. All four ambiguous phrases are corrected exactly within the historical/
   current contract described above.
2. Existing `003-b` corrections remain intact.
3. The focused drift test guards the new boundary and passes.
4. RC2 docs/governance focused tests, Ruff, and whitespace pass.
5. No broad local suite runs and no unrelated path changes.
6. PR #228 is amended without a second PR, merge, or auto-merge.
7. The immutable report-only commit has the literal implementation head as its
   first parent and changes only the new `003-c` report.

## GitHub, report, and merge requirements

Push all non-report commits to the existing branch and inspect actual GitHub
checks. Pending/missing/failed is not green. Never merge or enable auto-merge.

Publish exactly one immutable report at
`oap/reports/003-c-remove-final-readiness-ambiguity.md` using the full protocol
format, literal implementation SHA, and `Report publication commit: SELF`.
List exact focused results, broad suites not run, documentation impact, path
scope, GitHub state, and no production/secret access.

The report-only commit must have the implementation head as its first parent
and contain only the new report. Push and verify it, then signal exactly `OK`
without newline and return to the listener.

If any material new conflict appears, report it truthfully rather than
broadening scope. Do not merge under any circumstance.
