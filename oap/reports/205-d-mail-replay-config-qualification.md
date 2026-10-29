# OAP Coding-Agent Report — 205-d

## Work order
- Identifier: 205-d
- Work-order file: `oap/orders/205-d-mail-replay-config-qualification.md`
  (committed unchanged in IMPL `0d77a47`; sha256
  `fe10af158962622fe6b6fab212a70dcbf66418160210bc3059dbaa4f4d248fa7`)
- `oap/active` pointer: value `205-d` (5 bytes, no trailing newline),
  committed unchanged in IMPL `0d77a47`; sha256
  `4f99b691dcb417f261443ccb0f99cf1e68ee2a03d4b8887b1427b9e76448e86e`
- Numeric objective: 205
- PR mode: CONTINUE_EXISTING_PR (unique PR #361)

## Status
PARTIAL

## Executive summary
Executed the bounded 205-d round on the unique objective-205 PR #361
with ALL product bytes frozen at `420fb8f` (466 product paths + 1734
non-allowed paths byte-identical per root baseline
`205-d-product-baseline.json`); only the allowed test and documentation
paths changed. Completed the three remaining installed qualifications
through the ACTUAL installed `slaif-gateway` console against the owned
labeled PostgreSQL 16 container and the owned loopback SMTP sink:
(1) outcome 9 — installed once-only mail delivery/inspection: a cloned
key prepared with EXACTLY ONE explicit `pending` channel, `email
show`/`list` inspection of the prepared pending delivery (flat item
payload + one-time-secret lifecycle, recipient bound to the owner's
current email), one actual `send-pending-key --send-now` SMTP DATA
acceptance with the FULL generated key read from the MIME
transfer-decoded body and registered before any retention, exact
repeat refusal with no second send, a second clone against the
sink's armed deterministic 550 fault (failed state, no automatic
retry, missing-flag and blank-reason refusals, then one safe explicit
`--retry-failed` retry with unchanged key material), and clearly
labeled PRE-EXISTING sending/ambiguous/expired fixture states
inspected read-only BEFORE any unsafe-send probe (each probe refused
with zero additional SMTP; expired post-state
`failed` + `one_time_secret_expired`), plus invariants (ledger
unchanged, +5 keys / +5 deliveries, source row unchanged);
(2) outcome 11 — installed reviewed replay-reference expiry
maintenance: five schema-valid planted `reasoning` references (CHECK
constraints preserved), `inspect` → configured-default-TTL (explicit
30-day) dry-run with exact eligibility and exclusion counts →
mixed-mode refusal (exit 2, fixed stderr) → `--execute` applying
exactly ONE monotonic extension (created+TTL, creation preserved) →
column-level preservation (only `expires_at` on the extended row;
digests/route/model/source/ledgers/full key row unchanged) → exact
repeat `already_applied` with zero writes/audits → a SECOND explicit
`--include-expired` plan applying only the excluded expired reference
(created+TTL) → final inspection 5 active / 0 expired;
(3) installed `config show` finite process-configuration inspection:
exact 45-field allowlist with fixed restart scopes, the fixed
process-local snapshot scope and limitations, configured-vs-default
provenance (30-day TTL and 311 tokens report `configured`), the fixed
text-mode header, and a generated credential-shaped canary in a
numeric setting yielding the fixed `configuration_unavailable`
payload, exit 1, no echo, no traceback.

Final D COMBINED three-case run on the final test bytes: 3 PASS,
0 skip, 126.858 s, with the 37-record requirement-indexed safe
transcript (25 mail + 8 replay + 4 config, 9 negative exits). Outcome
10 (gateway-recorded failure investigations), the fresh
ALL-ELEVEN run, and the complete all-eleven transcript are NOT
executed and remain mandatory; the full original-brief audit and the
final-head/review/merge/actual-main gates remain. No merge, no
auto-merge.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 361
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/361
- PR state at report time: OPEN (MERGEABLE, CLEAN), no auto-merge
- Base branch: `main` at `5e59a023154bfebc998ef4e0a7089a3151fda0e2`
- Head branch: `oap/205-cli-field-workflow-qualification`
- Starting remote SHA (205-c SELF): `630e251bfc36d92b3b63d3ee4ba9b220de4452fa`
- Implementation head SHA (IMPL): `0d77a47fa051dab14d7cef2a49e2acf8f753f303`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  - `0d77a47fa051dab14d7cef2a49e2acf8f753f303` — outcomes 9/11 +
    installed config inspection (test file) + fixture/verification
    docs + unchanged 205-d order + exact `oap/active` (6 files)

## Changes made
Allowed paths only (order §3):
1. `tests/integration/test_cli_field_installed_workflow.py` —
   (final sha256
   `7ad01a6ea98c113eeb7b8de621d37edff5dbdf188cc77022299c36e025a8f8d5`)
   - DoD9 `test_dod9_mail_delivery_and_inspection` (25 labeled
     records): clone from the fully-routable positive source
     `k_student` (dry-run 0600 plan; execute with exactly one
     `--email-delivery pending` channel — no `email_delivery_status`
     key in the pending payload; pending state proven by installed
     `email show`), pending delivery inspection, one real
     `--send-now` acceptance with full MIME-decoded key registered
     before retention, exact repeat refusal (no second send),
     second clone + armed 550 fault → failed state with
     `last_recorded_failure = smtp_send_error`, no automatic retry,
     missing-flag / blank-reason refusals (zero SMTP while the latch
     is armed), explicit `--retry-failed` retry to success with
     unchanged key material, labeled sending/ambiguous/expired
     fixture states inspected before each unsafe probe (zero
     additional SMTP per refusal; expired post-state
     `failed` + `one_time_secret_expired`), and invariants
     (usage ledger unchanged; +5 keys / +5 deliveries; clone source
     row unchanged);
   - DoD11 `test_dod11_replay_expiry_maintenance` (8 labeled
     records): explicit `CODEX_REPLAY_REFERENCE_TTL_SECONDS =
     2592000` in the installed CLI subprocess environment, five
     schema-valid planted `reasoning` references each with its own
     ledger (eligible short-expiry, eligible no-shorten,
     default-excluded expired, unavailable-HMAC-v2,
     non-finalized-ledger; provider/upstream matching the ACTUAL
     route), `inspect` (5 / 4 active / 1 expired / 1 active
     in-validity key) → dry-run under the configured default TTL
     (2 eligible; exact exclusion counts) → mixed-mode refusal
     (exit 2, fixed stderr, no echo) → `--execute` (exactly one
     value change; extended row lands exactly on created+TTL) →
     exact repeat `already_applied` (zero writes/audits) → column
     diff proving ONLY `expires_at` changed on the extended row
     (digests, route, model, source linkage, ledgers, full key row
     unchanged) → second explicit `--include-expired` plan
     (eligible 3; applies only the expired row to created+TTL) →
     final inspection 5 active / 0 expired;
   - `test_dod_config_process_inspection` (4 labeled records):
     fresh installed subprocess per call — exact 45-field allowlist
     with the fixed per-entry restart scope, fixed
     `snapshot_scope`, exact fixed limitations, configured-vs-
     default provenance, explicit overrides (30-day TTL / 311
     tokens report `configured`), fixed text-mode header, and the
     invalid-Settings canary (credential-shaped value in a numeric
     setting → fixed `configuration_unavailable`, exit 1, no value
     echo, no raw traceback);
   - fixture/IO wiring (strictly necessary, minimal): `SmtpSink`
     deterministic 550 fault (`refuse_data` is a LATCH until
     explicitly cleared — not one-shot — counted in `refusals`,
     never recorded as an acceptance); `_smtp_data_body` (MIME
     transfer-decoded DATA body) + `_extract_key_token` (the wire
     key line exceeds the generator's MIME wrap width, so the raw
     wire fragment is not the complete key); `run_cli(..., env=)`
     per-call environment merge; `MAIL_ENV` (email enabled only for
     the mail cases) and `REPLAY_ENV` (explicit 30-day TTL);
     `_plant_dod9_history` / `_plant_dod11_history` labeled fixture
     setup with constant synthetic payloads/digests (product-
     equivalent ORM; recipients bound to the owner's CURRENT
     email), whose callers convert any driver failure into a fixed
     safe assertion with no exception chain (FINAL fixture
     behavior — see the failure-chronology qualification);
     generated keys and planted replay identifiers/digests
     registered as secrets before any retention; `persist_transcript`
     re-applies safe substitutions at serialization.
2. `tests/fixtures/cli_field_workflow/README.md` — 205-d handoff
   state (mail/replay/config cases, latch semantics, planting
   boundary, DoD10 still mandatory).
3. `docs/verification/2026-10-29-cli-field-installed-workflow.md` —
   new 205-d section: per-outcome evidence, JUnit chronology with
   the sanitized-derivative provenance, the literal final D-run
   installation identity, the 37-record transcript evidence, root
   evidence, and limitations/carry-forward.
4. `docs/verification/README.md` — 205 entry extended with the
   205-d continuation.
5. `oap/orders/205-d-mail-replay-config-qualification.md`
   (unchanged strategic bytes) and `oap/active` (exact `205-d`).

No app/service/repository/schema/migration/settings/default/dependency/
lockfile/workflow/adapter/client-profile/product/UI byte changed; no
previous unit/native tests or orders/reports edited.

## Acceptance-criteria evidence (order §1, eleven outcomes)
Final combined run (`205d-final-1`, JUnit authoritative; 3 tests, 0
failures, 0 errors, 0 skipped, 126.858 s, pytest exit 0; sha256
`0785c368733445d8854217ca9672607aeccdefb3ee2e92aebc8cd7259617739c`):

| # | Outcome (order title) | Status | Evidence |
|---|-----------------------|--------|----------|
| 1 | Identities / lookup / bounded paging | EXECUTED PASSED | 205-a/B (unchanged, not re-run this round) |
| 2 | Effective policy + route explanation | EXECUTED PASSED | 205-a/B (unchanged) |
| 3 | Record operations | EXECUTED PASSED | 205-a/B (unchanged) |
| 4 | Exact student/beta + two chat clones | EXECUTED PASSED | 205-a/B (unchanged) |
| 5 | Discovery grant + real filtered `GET /v1/models` | EXECUTED PASSED | 205-c (unchanged) |
| 6 | Rates, bounded lazy config, exact-37 batch | EXECUTED PASSED | 205-a/B (unchanged) |
| 7 | Two configured completion services + routes | EXECUTED PASSED | 205-c (unchanged) |
| 8 | Explicit activation + stable route edit | EXECUTED PASSED | 205-c (unchanged) |
| 9 | One-time delivery lifecycle (loopback SMTP) | EXECUTED PASSED (205-d) | `test_dod9_mail_delivery_and_inspection` |
| 10 | Gateway-recorded failure investigations | UNPROVEN | not executed (carried forward) |
| 11 | Reviewed replay maintenance | EXECUTED PASSED (205-d) | `test_dod11_replay_expiry_maintenance` |

Additional order requirement — installed `config show --json`/text
snapshot + invalid-Settings no-echo probe: EXECUTED PASSED (205-d),
`test_dod_config_process_inspection`.

## JUnit evidence (agent pytest; overlapping slice runs never summed)
All runs: `tests/integration/test_cli_field_installed_workflow.py`,
zero skips in every run, UTC 2026-10-29 (JUnit XML authoritative;
repository addopts suppress the console summary):

| Artifact (time) | tests | failures | sha256 (prefix) |
|---|---|---|---|
| `205d-dod9-1` 17:23 | 1 | 1 | c00c5e1f — fixture source choice: `k_policy` carries deliberately disabled M2/M3 routes; clone CREATE's enabled-model validation refused it (root-confirmed fixture issue, not a product defect) |
| `205d-dod9-2` 17:26 | 1 | 1 | 2e6059f5 — draft oracle: the pending-channel payload carries no `email_delivery_status` key |
| `205d-dod9-3` 17:28 (SHA `b8ccb884a96eded49a5d53c9557c608104e2905f12c5d3520977f0fb0facaf31`) | 1 | 0 | b8ccb884 — first green mail slice, 95.610 s (root accepted as INTERMEDIATE) |
| `205d-dod11-cfg-1` 17:36 (ORIGINAL SHA `0ea3c78ef7a31fc30a80c267b108a99f3143db8b610f11ef625b245fdcfe3cef`) | 2 | 1 | SANITIZED DERIVATIVE, not raw JUnit — see provenance below; 1 FAIL + 1 PASS, 41.195 s |
| `205d-dod11-cfg-2` 17:45 (SHA `61261643babefc0b2b554d76fe6de05862845c5d9e881e50b9ffcab37963c7b2`) | 2 | 0 | 61261643 — schema-valid replay + strengthened config, 68.681 s |
| `205d-final-1` 17:46 (SHA `0785c368733445d8854217ca9672607aeccdefb3ee2e92aebc8cd7259617739c`) | 3 | 0 | 0785c368 — FINAL combined run of final test bytes, 126.858 s (DoD9 92.140 s + DoD11 25.177 s + config 9.200 s) |

`205d-dod11-cfg-1` sanitized-derivative provenance: the replay case
failed on the `function_call` insertion (the `kind_shape` CHECK
requires call/tool fields for that kind); the draft's `note` item
kind was a separate invalid row never reached. The raw failure text
retained the planted synthetic `item_id_hmac` three times through
raw driver parameters (no full gateway-key shapes or DB URL
passwords were present — root verified). After root review the
artifact was sanitized IN PLACE (fixed placeholder) and re-ordered to
valid XML (declaration first, provenance comment after). The
original raw artifact no longer exists in its original form; the
CURRENT file SHA256 is
`c90319460e2a627fab1ea60b0726fa24d589574276d1ac0794c5dad4be94fc7a`
and it is reported here as a SANITIZED derivative with its original
hash preserved, never as raw JUnit.

## Installation identity (executed; literal final D-run identity)
- Source frozen at `420fb8f6d9377f569d126d08f4c9e4146fc7250b`
  (git-archive pristine copy under the per-run pytest temp tree).
- FINAL D combined run: FRESH wheel
  `slaif_api_gateway-0.1.0-py3-none-any.whl`, actual SHA256
  `f2f77aa1b98e887a186ae1fcfcae42bba93e0ae5f77205d931010130eeb3f1c7`,
  payload 432 files verified against the pinned source; the stale
  reused venv was REJECTED by the payload gate and a FRESH owned
  venv was created (`/tmp/pytest-of-janezp/pytest-1583/slaif205-field0/venv`),
  Python 3.12.15; installed payload 432 files verified against the
  selected wheel.
- Installed console
  `/tmp/pytest-of-janezp/pytest-1583/slaif205-field0/venv/bin/slaif-gateway`,
  executed with neutral cwd and `PYTHONPATH` absent, outside the
  checkout.
- Every 205-d pytest run followed the same per-run fresh build/verify
  path (each run's transcript identity records its own fresh wheel
  SHA, `wheel_reused: false`, and its own venv under its pytest temp
  tree); wheel SHAs differ per build (wheel metadata), and payload
  identity against `420fb8f` is the binding fact. The 205-c wheel
  `cf7e114f…` (pytest-1575 venv) must NOT be attributed to 205-d.
- Owned PostgreSQL 16 container per run, unique run-token
  name/labels, loopback-only port, tmpfs data dir, ownership
  inspected BEFORE migrations, exact-ID/label cleanup after. Final
  run container `9a857a02a0c1d45a13d6042d0ffc2d5992b3e40aab1f3fd9492960e38b41bbdc`
  (port 38111) removed in teardown; `docker ps -a --filter
  name=slaif205` is empty after the round.
- No schema, key-policy, or migration of any kind in 205.

## Persisted operator transcript (order §7, executed)
Final run `140866e465ea4fe2` (outside the checkout):
`/tmp/slaif205/transcripts/140866e465ea4fe2/` — directory 0700,
`transcript.json` 0600, `identity.json` 0600; 37 records (25 DoD9 +
8 DoD11 + 4 config), 0 unlabeled, 9 negative exits; transcript sha256
`4ce929a4155b86a59b2a7cb65754fa28b7dad8430d619d5a34d6eb40c1497674`;
identity sha256
`2dfe9ba906d54782a905fcd0110e17a8fe38ff1b4a6c383ae2695e3bbaf93c09`.
Records carry the actual requirement-indexed `run_cli` argv
boundaries / output projections / exit codes with meaningful outcome
labels plus safe run/installation identity; canary-absence
assertions cover both generated keys, all planted replay
identifiers/digests, and the config canary, with safe substitutions
re-applied at serialization. This is a PARTIAL transcript (the three
D outcomes only); the final fresh all-eleven run must export every
outcome. Source/tests/fixture-setup SQL and ORM plants are separately
explained in the verification record and never presented as operator
CLI actions.

## ROOT independent evidence (root runs — credited as root, not agent pytest)
- `205-d-product-baseline.json` — product/preserved-path baseline
  (466 product paths, 1734 non-allowed existing paths, protected
  untracked hashes) binding the frozen `420fb8f` tree for the round.
- Root parsed `205d-dod9-3` and the run transcript
  `694007033c6945be`: 25 actual labeled records / 7 negative exits,
  private modes and canary shape clean, 432 source/wheel/installed
  bytes independently matching `420fb8f`, all 466 product paths
  unchanged, exact PG absent; two sink acceptances + one definite
  550 refusal proven by the source assertions — accepted as
  INTERMEDIATE evidence.
- Root independently verified the ORIGINAL failed
  `205d-dod11-cfg-1` (replay 1 FAIL / config 1 PASS, 0 skip,
  41.195 s, SHA `0ea3c78e…`; no full gateway-key shapes or DB URL
  passwords present) and its sanitized form (SHA `c9031946…`).
- Root parsed the config artifact `ad11a1afa9874eab`: 4 actual CLI
  records, the exact 45 allowlist fields, default TTL 31536000 vs
  configured 2592000, rate 100 vs 311, all-45 recreate scopes, fixed
  `configuration_unavailable` / exit 1 / empty stderr / no traceback
  — accepted as INTERMEDIATE actual config evidence.
- Root FINAL combined review: accepted `205d-final-1` (3 PASS,
  0 skip, 126.858 s) with the actual 37-record artifact
  `140866e465ea4fe2` (25 mail / 8 replay / 4 config), private
  modes / canary-clean, ALL 432 source/wheel/installed bytes
  independently matching `420fb8f`, 466 product paths unchanged,
  exact PG absent; the actual `--include-expired` apply,
  created+30-day target, long-expiry keep, two audits, repeat
  no-op, and full-row preservation were source-reviewed; the
  current test SHA `7ad01a6e…` precedes the final run.
- The root draft reviews drove the fixture source choice
  (`k_student`), the pre-probe lifecycle inspection, the
  schema-valid replay rows, the explicit `--include-expired` plan,
  full-row preservation, planted ID/digest registration, the safe
  planting boundary, and the strengthened config assertions.

## Local verification
- `205d-final-1`: 3 PASS, 0 failures, 0 errors, 0 skipped, 126.858 s, pytest exit 0
- `205d-dod9-3`: 1 PASS, 0 skip (mail slice on pre-final bytes; superseded by the final run)
- `205d-dod11-cfg-2`: 2 PASS, 0 skip (replay + config slice on pre-final bytes; superseded by the final run)
- `python -m ruff check` (touched test file): PASSED (clean)
- `git diff --check`: PASSED (clean)
- `python scripts/check_documentation.py`: PASSED
  (`DOCUMENTATION_CHECK=OK files=132`)
- Container cleanup after the final run: verified — `docker ps -a
  --filter name=slaif205` empty; no scratch resources used in 205-d
- Generated credentials: random, memory/0600-only, registered before
  retention, substituted/masked in every retained projection;
  retained artifacts carry booleans/hashes only. No real
  OpenAI/OpenRouter, real client, real SMTP, or Redis.

## GitHub CI / required checks
- Starting head 205-c SELF `630e251`: ALL 10 required checks / 3
  workflows SUCCESS (re-observed green at this report's refresh:
  Unit/lint/migration-head, PostgreSQL integration, E2E, Playwright,
  Docker Compose smoke, Documentation hygiene, Analyze ×2, CodeQL).
- IMPL `0d77a47` / SELF: check state at report drafting NOT
  CONCLUDED (fresh runs triggered by the push); no pass is inferred
  from pending state. The strategic model must verify the `SELF`
  commit without rewriting this report.

## Local setup / dependencies
- Packages/tools/services: per-run owned Python 3.12 venvs (build
  env + fresh installed venv under the per-run pytest temp tree)
  with the built wheel + package dependencies; Docker (owned labeled
  PostgreSQL 16 containers only); no apt/system mutation
- `sudo`-level setup performed: none
- Durable setup changes committed/documented: none (owned /tmp
  artifacts only)

## Documentation
Documentation updated: docs/verification/2026-10-29-cli-field-installed-workflow.md, docs/verification/README.md, tests/fixtures/cli_field_workflow/README.md
- The verification record's 205-d section carries the per-outcome
  evidence, the literal final D-run installation identity, the
  sanitized-derivative failure chronology (with the qualification
  that "raw SQL never retained" describes FINAL fixture behavior
  while the first failed artifact DID retain the synthetic digest
  and was sanitized in place), the `refuse_data` latch semantics,
  the transcript evidence, the root evidence, and the
  carry-forward. The order's broader remaining duties (outcome 10,
  the fresh all-eleven run with the complete transcript, the full
  original-brief P0/P1/common/discoverability/upgrade audit, the
  final CLI-field-administration/help/status/deployment documents)
  are NOT complete; they accompany later same-PR continuations.

## Safety and scope confirmations
- Unrelated files changed: no (only the paths listed under Changes
  made; protected untracked `CODEX-SESSIONS.md` / `codex.sh`
  preserved uncommitted at their order-stated hashes
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`
  / `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`;
  ignored catalogs/worktrees untouched)
- Production secrets accessed: no
- Production systems accessed: no
- Required tests skipped/not run: yes — outcome 10 and the fresh
  all-eleven run are not executed yet (see Status and Known
  limitations); no test was skipped within the executed runs
  (0 skips in every JUnit row above)
- Scope deviation: no product, framework, or extra path touched.
  One disclosed evidence-artifact deviation: the first failed
  `205d-dod11-cfg-1` JUnit retained the synthetic digest in its raw
  failure text before the safe-planting boundary existed; it was
  sanitized in place after root review and is reported as a
  sanitized derivative (original hash preserved; see JUnit evidence)
- Extra PR created for same numeric objective: NO (single PR #361)
- PR merged by coding agent: NO
- Activated order and `oap/active` edited by coding agent: NO
  (committed byte-unchanged)
- Report-publication commit changes only this report file: yes
  (verified via staged diff before committing)

## Known limitations / blockers
1. Outcome 10 (gateway-recorded failure investigations via
   installed `diagnostics request show`) is UNPROVEN — not executed;
   it remains later same-PR work.
2. The fresh ALL-ELEVEN module run and the complete all-eleven
   transcript are NOT executed; the D transcript covers the three D
   outcomes only (37 records).
3. The mail/replay history rows are labeled ORM fixture setup
   (synthetic payloads, constant digests, recipients bound to the
   owner's current email), never operator actions; the SMTP layer is
   an owned loopback synthetic (no real mail); the replay rows prove
   expiry maintenance, not replay playback, provider
   qualification, or authentication.
4. The `205d-dod11-cfg-1` raw failure artifact was sanitized in
   place (see JUnit evidence); its original form no longer exists
   and is represented only by its preserved hash and the sanitized
   derivative.
5. No schema, key-policy, or migration of any kind in 205; no
   merge, no tag/release, no real provider/client/mail, no Redis,
   no production/security/compliance claim. The whole objective
   205 remains PARTIAL until the fresh all-eleven run, the
   complete transcript, the full original-brief audit, and the
   final-head/strategic merge gates pass.

## Recommended strategic follow-up
- Root: verify the `SELF` commit (report-only; first parent = IMPL
  `0d77a47`) and its fresh required checks on PR #361.
- Next same-PR continuation: outcome 10 (gateway-recorded failure
  investigations), then the final fresh-installation ALL-ELEVEN run
  with the complete requirement-indexed transcript, the full
  original-brief P0/P1/common/discoverability/upgrade audit and
  CLI-field-administration/help/status/deployment documentation, and
  the final-head checks, guarded strategic merge, and actual-main
  three-workflow checks.
