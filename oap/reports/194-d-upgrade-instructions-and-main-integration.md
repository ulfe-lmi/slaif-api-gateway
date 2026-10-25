# OAP Objective 194-d — final report: operator upgrade instructions and current-main integration

Work order: `oap/orders/194-d-upgrade-instructions-and-main-integration.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `194-d`; order sha256
`c28ab1024ec7de5c12e021e97618d03abc8d94e2e8e3f3fdb6f20908c87962d5`).
Activation-correction record: `oap/orders/194-c-upgrade-instructions-
and-main-integration.md` (sha256
`f71d9d957e92ce69e5cc5b10c70682ed1f3f81f8cea544e4ba1adbc050234a81`)
was published but NEVER control-signaled or executed — root governance
preflight caught its incorrect first-line work-order format (8pass/
1fail). Its bytes were committed unchanged as an orchestration record
alongside this 194-d order; 194-d supersedes that unexecuted
activation. No report exists or is expected for unexecuted 194-c; no
completion is claimed for it.
Branch: `oap/194-numbered-tables-and-metric-columns`, continuation
base: the 194-b report SELF
`bdfc32a47205e9570fba06b37e2e1c7ae9f654da`; remote `main` at
activation `7a1b67360a3a7c816c27c6b6f36f39dbae088677` (human merges
of PR #343 and PR #345; re-verified unchanged at execution start).
PR mode: AMEND_EXISTING_PR (Objective 194 = exactly one PR, #346,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/346).
The coding agent never merges; no auto-merge is enabled; root reviews
independently and guard-merges.

Implementation head SHA: 224a7d75e1d9234d500a7659095b35e149e32cfc
Report publication commit: SELF

## Implementation commits (branch order, this round)

1. `f48483d59ee37d26182192737d3219f98dd399f7` — "Merge current main
   (PR #343 nginx body limit, PR #345 configured completion services)
   into objective 194 (194-d)": normal non-rewriting merge (parents
   `bdfc32a…` and `7a1b673…`); both upstream human changes preserved
   byte-for-byte as the upstream commits; zero conflict, zero path
   overlap with 194 changed paths (verified by diff before merging).
2. `cd407f2a00ca8dd4e4510e97561e2b2e1eb7012e` — "Correct renderer-
   upgrade output-root instructions and record root CLI proof (194-d)":
   the doc corrections (R1–R4) plus the unchanged 194-c/194-d orders
   and `oap/active` (6 files).
3. `224a7d75e1d9234d500a7659095b35e149e32cfc` — "Clarify run_dir URI
   vs filesystem path in upgrade docs (194-d)": root's final-review
   R2 wording clarification (1 file, docs only).

## Process honesty

This report closes the SAME continuously activated objective-194
execution: the 194-b handoff was accepted (root response terminal
85717 CLOSED exact OK); the 194-d order + `oap/active` bytes were
published to the shared filesystem before the single control OK, which
was consumed exactly once by the one mandated control waiter
(`CONTROL_OK_EXACT`) — no re-signal, no duplicate control reader, no
profile/model/effort change, no 195 activation. The 194-a/194-b
orders and reports remain immutable and verified unchanged at the
remote head. After the main integration, the updated `AGENTS.md` was
re-read: only the Nginx body-size note changed (upstream PR #343:
`client_max_body_size 128m` inside `location /v1/`); no governance
change affects this round.

**Process deviation (transient, unpublished, honestly recorded):**
while committing the R2 clarification, a local-only commit
`6d1fce7…` was briefly created with a mistyped author address and
placeholder message BEFORE any push. It was corrected with
`git reset --soft HEAD~1` and re-committed as `224a7d7…` with the
correct author/message; the corrected commit is what was pushed. No
published/remote history was ever altered and no immutable OAP
artifact was touched — but a local soft reset DID occur; it is not
claimed otherwise.

## What changed (documentation + integration only; ZERO functional change)

1. **R1 upgrade-instruction repair.** The `docs/catalog-refresh.md`
   "Renderer version upgrade (183.1 → 194.1)" section now states that
   an unchanged source keeps its `run_id`, so regeneration MUST use an
   explicitly NEW output root (`--run-root`); reusing the root that
   already contains that run's directory is refused (exit 65, existing
   run output) with the old bytes preserved — the no-overwrite
   safeguard, not an error to work around by deleting/renaming the old
   run. The canonical source filenames are shown
   (`catalog-refresh.json`; refresh mode pairs
   `catalog-baseline.json` via the existing `--baseline-file`;
   first-install uses `--first-install`). The old sealed SOURCE JSON
   may be read AS SOURCE from the archived run; the archived run's
   review output and seal (`REVIEW.html`, `manifest.json`,
   `receipt.json`, sealed validation) are never edited, re-derived, or
   re-sealed, and its run directory is never overwritten. The new run
   directory is taken from the command's own `run_dir:` output (not
   inferred from a renamed archive directory), with no silent change
   of source run_id/provenance/dates. A fresh `collect` remains the
   alternative; re-review does NOT refresh source freshness.
2. **R2 command accuracy.** Examples use `verify --run-dir` and the
   existing `apply` / `apply-status` syntax (all flags checked against
   the live CLI `--help` this round). Review exit semantics are stated
   (0 READY; 10 READY_WITH_WARNINGS — sealed, verifiable, read the
   report before applying; 20 BLOCKED — never apply; 65 data error —
   nothing to apply) with no `&&`/`set -e` chaining that discards the
   expected 10 or lets a 20/65 outcome flow into apply. The new root
   must be operator-restrictive and outside the repository; examples
   use inspectable placeholders/config variables, no invented flags.
   Per root's final review: `review` prints the `run_dir:` line as a
   `file://` URI while `--run-dir` takes a filesystem path — the doc
   now says to pass the corresponding path, not the URI literally.
3. **R3 rollback wording.** Restore the previous PRODUCING
   code/image together with the compatible archive: merely sharing the
   `183.1` renderer label does not guarantee byte-stable replay
   (historical presentation variants reused that label); no `183.1`
   binary is promised to replay every `183.1` archive; no renderer
   fleet/fallback; no archive edits/re-sealing; `194.1` archives are
   NOT promised replayable under the old CLI; no schema/key/policy
   migration.
4. **R4 evidence wording.**
   `docs/verification/2026-10-25-catalog-renderer-upgrade.md` Layer 2
   is now characterized as OFFLINE CLI evidence (real installed CLI,
   synthetic fixture, real local filesystem + sealing cryptography; no
   PG/provider/network) — NOT unit/mock-CLI evidence; a fresh current
   `verify` proves CURRENT byte-correspondence only, not genuine
   cross-version byte preservation. Root's independent actual
   previous/current CLI proof is separately recorded with the exact
   receipt facts (previous-source commit
   `90a114a236a80469780fb9341b751520d5a3f964`; previous CLI review
   exit 10 / verify exit 0; current CLI verify of the old run exit 30
   with `digests: ok`, `hmac: ok` and the fixed unsupported-renderer
   reason; current CLI review of the SAME unchanged source into a NEW
   root exit 10 / verify exit 0 binding `194.1`; supplied revision
   `181.1` historical provenance vs authenticated `183.1`/`194.1`;
   old archive bytes and canonical source bytes/semantic SHA
   unchanged; same-run-root re-review exit 65 with old bytes
   preserved), explicitly distinguished from the unit-layer
   forged+re-signed context and the one real-PG node, and explicitly
   NOT counted as a newly agent-run test. The layer-separation bullet
   now states the real-PG node proves the NEW current identity through
   real CLI / atomic apply only and does NOT itself prove the `183.1`
   refusal. Old results preserved; the immutable 194-b OAP report was
   NOT edited.
5. **R5 current-main integration.** Normal non-rewriting merge of
   `origin/main` `7a1b673…` (PR #343 API Nginx 128MiB transport
   allowance; PR #345 configured completion adapter): both upstream
   changes preserved byte-for-byte; all 194 history, immutable
   reports, and orders preserved; no reset/clean/stash/history rewrite
   of branch history (the single local soft reset in the process-
   deviation note above corrected an unpublished local commit only).
   New functional change scope: ZERO.

## Explicit non-changes

No app product code, no test, no schema/model/migration, no
dependency, no adapter/transport/auth/admission/accounting/permission,
no CLI behavior change in this round (the merge carries ONLY the
upstream human commits). Protected untracked artifacts
(`CODEX-SESSIONS.md`, `codex.sh`; gitignored `.codex/`,
`.local-provider-catalog/`) preserved. Unrelated open PR #319
preserved. No production DB/SSH/deploy/release/tag; no real
provider/model/email/credential use; root's synthetic operator seal
key was never printed or copied (the agent-run proof used a fresh
operator-created key in its own restricted directory).

## Verification (this round; bounded; ALL synthetic; no DB/provider)

- **Command syntax:** bounded offline `--help` checks of `review`,
  `verify`, `apply`, `apply-status` confirm the documented
  argument/option surface exactly (real exits 0).
- **One targeted synthetic review+verify (real CLI, offline)** using
  root's archived legacy run's canonical `catalog-refresh.json` read
  AS SOURCE (fresh restricted directory, fresh seal key; no
  DB/network/provider):
  - `review --first-install` into an EXPLICITLY NEW run root:
    exit 10 (READY_WITH_WARNINGS); `run_dir:` taken from the CLI
    output;
  - `verify --run-dir <new run>`: exit 0 — `valid: yes`,
    `digests: ok`, `hmac: ok`, `validation: ok`;
  - the new run's authenticated execution context binds
    `{"extractor_version": "slaif-collector/181.1",
    "policy_version": 1, "renderer_version": "194.1",
    "schema_version": "1"}`; the source `run_id` is unchanged;
  - re-review of the unchanged source into the SAME new run root:
    exit 65 — "run directory already exists; refusing to overwrite
    completed output" — the documented no-overwrite refusal;
  - all nine legacy-run files byte-identical before/after (sha256
    diff clean) — the old archive is preserved.
- **Root receipts** (strategic filesystem, cited with exact facts in
  the verification record): `legacy-1831-baseline.json`,
  `independent-renderer-upgrade-cli-proof.json`,
  `independent-upgrade-existing-root-refusal.json` under
  `/home/janezp/codex-supervision/slaif-api-gateway/review-artifacts/
  194-review/` — recorded as root's independent evidence, not
  re-run by the agent.
- **Static:** `python scripts/check_documentation.py` →
  `DOCUMENTATION_CHECK=OK files=119` (exit 0; re-run after the R2
  clarification); `git diff --check` clean; `ruff check app tests`
  clean (exit 0); `tests/unit/test_oap_governance.py` 9 passed (real
  exit 0).
- **Retained:** the 194-b focused unit group (167 passed), the one
  real-PG atomic-apply node, and all 194-a functional evidence stand
  as recorded — NOT re-run (wording/integration round, order A2).

## CI status at the implementation head (224a7d7)

Observed 2026-10-25 at 19:06:58 UTC via the GitHub check-runs API:
nine of ten check-runs SUCCESS (CodeQL; Unit, lint, and migration
head; Docker Compose smoke; Playwright browser smoke; Documentation
hygiene; OpenAI-compatible E2E tests; Analyze Python; Analyze
(python); Analyze (javascript-typescript)); PostgreSQL integration
tests still `in_progress`; no failures, cancelled, or missing checks
observed. Root owns the final-head CI; pushing the report-only commit
triggers a new run at the report head, and final SELF-head check
verification remains the strategic/root gate before
acceptance/merge. This report claims no check state beyond what was
observed.

## Honest limits / skips

- No full local unit/integration/browser matrix (wording/integration
  round only); routine CI supplies the broad matrix.
- The agent-run proof is one targeted offline CLI case plus `--help`
  checks; it proves the documented regeneration pattern and the
  documented same-root refusal, not provider/DB qualification.
- Screenshot/review directories (`/tmp/slaif194d/`,
  `/tmp/slaif194-legacy-upgrade-vkfzmayk/`) are local/strategic review
  artifacts, not repository content.

## Docs impact statement

Updated: `docs/catalog-refresh.md` (upgrade section: new-output-root
regeneration with canonical filenames, read-source-never-touch-seal
wording, exact review/verify/apply/apply-status syntax and exit
semantics, URI-vs-path clarification, corrected rollback wording),
`docs/verification/2026-10-25-catalog-renderer-upgrade.md` (Layer-2
offline-CLI characterization; separately recorded root CLI proof;
corrected refusal-proof attribution), `docs/verification/README.md`
(194-b entry crossnote). Deployment: unchanged — a normal
image/code upgrade and service restart; no database migration, no
schema or field-shape change, no key/policy change. The merge brings
the upstream human changes (Nginx 128MiB transport allowance;
configured completion adapter) with their own documentation.

## Safe boundary statement

- No schema/migration/model/field-shape change; no quota/accounting/
  reservation/cost/ledger change; no provider/adapter, Responses-
  compatibility, transport, content-capture, dependency, auth/
  admission, or CLI-behavior change; the upstream merge is preserved
  unchanged.
- No secrets printed or committed; root's synthetic operator key was
  never copied; all data synthetic; the fixed error text never echoes
  the sealed value.
- The 194-a/194-b orders and reports are immutable and verified
  unchanged; the 194-c order is preserved as an orchestration record
  (unexecuted; no completion claimed). The coding agent never merged
  and did not enable auto-merge; PR #346 remains a draft for
  strategic review, final-head check verification, and guarded merge.
  Objective 195 is NOT activated by this execution.
