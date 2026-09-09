# OAP Work Order — 161-m

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend Objective-161 PR #298 to correct the verifier's exact provider
environment-key mismatch: make its manual/default command request only the
pinned capture helper key `SLAIF_CODEX_CAPTURE_API_KEY`, which is the key its
isolated environment actually populates. Add authoritative before/after
PostgreSQL accounting/replay snapshots for the rejected resumed request, then
run exactly one fresh full-image/resumed-crop pre-fix reproduction.

This remains verifier-only prove-before-fix. Do not change Gateway production
behavior or docs and do not implement assistant `output_text` acceptance. If
the expected rejection and no-side-effect predicates are proved, publish
PASSED and stop. Any failure is FAILED and stops without retry or same-round
correction.

## Exact reconciled state and evidence

- Repository/PR: `ulfe-lmi/slaif-api-gateway`, PR #298.
- Branch/base: `oap/161-codex-assistant-output-history` onto exact current
  `main` `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- 161-l governance implementation head:
  `24b666dad0b60f66117d7f7b0b978f06c3ce3dec`.
- Immutable 161-l FAILED report/current PR head:
  `0ee52f4441970656f12b1600f7776929558f6807`.
- Report: `oap/reports/161-l-correct-161-k-report-topology.md`.
- 161-l report literal implementation SHA exists, equals report first parent,
  and its report commit changes only that report. Activation changes only its
  order/active pointer. `OAP-TOPOLOGY-CORRECTED=YES` is independently verified.
- All ten checks pass on 161-l activation and report heads. PR #298 is open,
  non-draft, CLEAN/mergeable, has no reviews/threads/auto-merge, and is the
  unique Objective-161 PR.
- 161-l contains one lesser contradictory sentence: it records the required
  governance pytest as 8/8 passed, then says no test command ran. Preserve the
  report; 161-m must state accurately that governance tests ran while no
  verifier/product/reproduction command ran in 161-l.
- Remote main, release `v0.1.0-rc.1`, unrelated PRs #224/#250, historical PR
  #291, and frozen Local PR #7 are unchanged/out of scope. Local PR #7 remains
  at report head `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation
  parent `64e50172ee02563e2b021554f6b0d345cc7dfdec`.
- Objective 161 still changes only OAP transcript, one verifier, and its tests;
  no app/dependency/schema/migration/CI/contract/docs path has changed.

161-k's technical evidence was preserved through the topology correction:

- manual `_codex_profile_args()` declares
  `env_key="SLAIF_CAPTURE_API_KEY"`;
- exact pinned `scripts.capture_codex_protocol.CAPTURE_API_KEY_ENV` is
  `SLAIF_CODEX_CAPTURE_API_KEY`;
- `capture._isolated_environment()` creates that canonical key and the verifier
  overwrites that same canonical entry with the synthetic Gateway key;
- the verifier never populates `SLAIF_CAPTURE_API_KEY`;
- the helper/manual provider semantic comparison therefore fails before run;
- all prior image and no-image target/control runs used a provider declaration
  whose required env key was absent, explaining their identical pre-HTTP
  `turn.failed` behavior.

The correction is exact and verifier-owned: use the already pinned canonical
capture env name in command and environment, with no fallback or dual alias.
Abort on any topology/constant/environment/frozen-Local discrepancy. Never
create a replacement PR.

## Exact allowed paths

Only these may change:

- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-m-canonical-provider-env-and-prefixed-reproduction.md`
- `oap/reports/161-m-canonical-provider-env-and-prefixed-reproduction.md`

Do not change app, accepted/capture helper/fixtures, Objective-160 files,
Local, replay/HMAC production code, DB/schema/migrations, dependencies/
requirements/lockfiles, CI, contracts, doctrine, or docs.

## Required provider-env correction

1. Introduce or use one fixed verifier constant equal to exact
   `capture.CAPTURE_API_KEY_ENV` value `SLAIF_CODEX_CAPTURE_API_KEY`. Bind it to
   the pinned helper constant in pure/source tests and fail closed on drift.
2. Replace only the manual command provider `env_key` value. Default target,
   no-image diagnostic, and every manual `_codex_profile_args()` consumer must
   declare the canonical key. Preserve all other argv bytes/order and config.
3. Require the isolated environment contains exactly one canonical capture
   entry with the synthetic Gateway key before catalog/command execution.
   Require stale `SLAIF_CAPTURE_API_KEY` absent. Do not accept aliases, copy to
   both names, fall back, read inherited values, or print the value.
4. Require bounded semantic comparison against
   `capture._exec_command_0149()` now passes for provider env/name/base/wire and
   all previously projected command facts.
5. Add pure negatives for canonical key missing, stale key present, both keys,
   helper-constant drift, wrong env declaration, inherited value, and raw
   secret/name-value leakage. Preserve every existing diagnostic mode and
   default target except this env-name correction.

## Required accounting/no-side-effect proof

Use current SQLAlchemy models and the already disposable PostgreSQL database;
add no schema/repository/product write.

1. Add a safe immutable snapshot for the synthetic key containing only bounded
   counts/classes: total/finalized/pending/released reservation counts,
   total/finalized/pending/failed ledger counts, successful-ledger count,
   Codex replay-reference count, and query-success boolean.
2. After the first Codex session completes its two admitted Gateway requests
   and before resume, require exactly two reservations and two ledgers, both
   terminal/finalized and successful, zero pending/failed, and a bounded replay
   count. Record that as the pre-rejection snapshot.
3. After the resumed request is rejected and before cleanup, query again.
   Require every count equal to the pre-rejection snapshot, especially zero new
   reservation/ledger/replay row and zero pending state.
4. Reject query failure, malformed status, unexpected cardinality, or any
   difference with fixed codes. Never report UUIDs/request IDs, HMACs, amounts,
   token counts, content, DB URLs, or row representations.
5. Add pure snapshot/equality tests and a focused disposable-PostgreSQL test if
   needed to prove the actual model query/status logic. DB tests must execute,
   not skip; use only the verifier's generated test DB.

## Tests and preflight

Starting focused collection is exactly 107 cases because 161-k/l added no
source tests. Collect this before edits. Add and report the exact final
machine-collected count; do not reuse prior counts.

Before the one reproduction:

- run complete verifier and active-governance tests;
- compile changed Python and run Ruff check/format;
- run provider-env/helper-semantic/privacy negatives and accounting snapshot/
  equality/DB tests;
- run all retained source/diagnostic/provenance/catalog/image/command/observer
  tests;
- run `git diff --check`, exact allowed-path proof, no report collision;
- push final non-report implementation head and require all ten normal checks
  successful on that exact head;
- create a fresh private Python 3.12 `.[dev]` environment and pass `pip check`,
  combined imports, module resolution/`--help`, package/native provenance, and
  canonical environment preflight.

Skipped, xfailed, missing, cancelled, pending, stale, or blocked evidence is
not a pass. Repair in-scope verifier/tests only before the run. Once the run
begins, no mutation, control mode, alternate env alias, or second process.

## One exact full reproduction

Run exactly once from the clean implementation head with the default target
mode and canonical provider env:

```text
env -u TEST_DATABASE_URL -u DATABASE_URL -u RUN_UPSTREAM_TESTS
  ENABLE_EMAIL_DELIVERY=false PYTHONPATH=app
  <task-python> -m scripts.verify_codex_0149_assistant_output_history
```

PASSED requires all environment/provenance gates, exact Gateway statuses
`200,200,400`, zero retries, first full-image and rejected resumed crop-image
wire classes, one prior assistant `output_text` with exact fields/bounded
Unicode, exact rejection `responses_input_content_part_not_supported` at
`input[5].content[0].type`, fake Local exactly two signed requests with one
function and message lifecycle, exact pre/post accounting equality with zero
rejected-turn side effects/pending state, fixed success line, and cleanup.

Any failure publishes existing closed stage/turn/Gateway/Local/accounting
evidence and stops. No second run or same-round production correction.

## Boundaries and immutable report

Routine private Python/npm and disposable PostgreSQL setup are authorized.
Never mutate global state or use `DATABASE_URL` destructively. No protected
credential/service, Local mutation, Qwen, real provider, hosted tool,
deployment, release, or production system is authorized. PostgreSQL remains
accounting truth.

Never retain/report prompts, completions, reasoning, media, bodies/JSONL,
turn-failure text, tool payloads, raw IDs/HMACs, secrets, endpoints, DB URLs,
amounts, private paths, environment/package output, tracebacks, or diagnostic
hashes. Docs need no update because this is verifier-only evidence.

Commit unchanged 161-m order/active with verifier/tests to the same PR. Run
only from its exact clean implementation head after ten green checks. Publish
exactly one immutable report afterward:

`oap/reports/161-m-canonical-provider-env-and-prefixed-reproduction.md`

Report `RESULT=PASSED|FAILED`, literal implementation SHA, `Report publication
commit: SELF`, topology/diff, 161-k/l correction facts, exact test counts,
preflight/checks, exactly-one-run result, all target and pre/post accounting
predicates, privacy/cleanup/docs/skips/deviations, and:

```text
PREFX-PROVIDER-ENV-ACCEPTED = YES|NO
PREFX-ACCOUNTING-NO-SIDE-EFFECT-ACCEPTED = YES|NO
PREFX-REPRODUCTION-ACCEPTED = YES|NO
PREFX-ENVIRONMENT-ACCEPTED = YES|NO
PREFX-PROVENANCE-ACCEPTED = YES|NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

Final commit changes only that report, has implementation first parent, and is
remote PR #298 head before response `OK`. Report-head checks may be pending;
strategic verifies them. Coding never merges/auto-merges and returns to the
permanent control-wake helper.
