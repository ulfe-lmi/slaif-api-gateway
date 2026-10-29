# 205-a verification record — installed CLI field administration workflows

**Status: COMPLETE for the objective-205 CLI field qualification
(final 205-f single complete 13-case run, final section below).** This
record documents what was actually executed through the installed
`slaif-gateway` console for work order
`oap/orders/205-a-cli-field-workflow-qualification.md` (unique PR for
objective 205; same-PR continuations 205-b, 205-c, 205-d, 205-e, and
205-f on the same PR). The original 205-a header text — "outcomes 9,
10, 11 and the runtime-configuration evidence are NOT yet executed and
remain mandatory for the final 205 PR" and "Objective 205 as a whole
remains PARTIAL" — is SUPERSEDED by the 205-f section below: ALL eleven
outcomes, installation identity, and runtime-configuration inspection
were executed in ONE fresh complete 13-case installed run with the
complete 206-record indexed operator transcript. Objective 205's
implementation/qualification scope is complete; the strategic merge and
the actual-main verification remain pending (root-owned), and no
release/tag claim follows. The per-outcome rows in the 205-a table that
read "NOT EXECUTED" are historical state at the 205-a point and were
each subsequently executed as recorded in the 205-c, 205-d, 205-e, and
205-f sections.
Nothing in the historical sections below claims an unexecuted outcome
as current.

## Installation and identity (executed)

- Source: accepted objective-204 merge commit
  `5e59a023154bfebc998ef4e0a7089a3151fda0e2` (remote `main` at qualification
  time), pinned shallow-safely in an owned pristine archive.
- Wheel: `slaif_api_gateway-0.1.0-py3-none-any.whl`, actual selected
  SHA256 `5c5bbdb405c7b84f4434a3cfc28f6c15cae2c4947f61d32540149e61b3f6ec55`
  (built from that exact source in the setup slice; the fixture records the
  ACTUAL selected wheel SHA, not a manual ZIP hash, and re-verifies the
  payload for any reuse or fresh build).
- Owned venv: `/tmp/slaif205/venv2` (Python 3.12.15); console
  `/tmp/slaif205/venv2/bin/slaif-gateway`; package resolves to
  `/tmp/slaif205/venv2/lib/python3.12/site-packages/slaif_gateway/__init__.py`.
  Installed payload file set verified exactly against the selected wheel
  payload. Root independently verified the installed package bytes against
  the accepted source (root evidence, not an agent run).
- Migrations: run from the pristine pinned source (the wheel does not ship
  migrations) to the `0026` head; the fixture asserts 34 public tables
  (= 33 product tables, including `request_diagnostics`, plus
  `alembic_version`) before seeding.
- Every operator action under test is a subprocess of the venv console from an
  owned operator directory OUTSIDE the checkout, with `PYTHONPATH` unset and
  inherited credentials scrubbed. DoD0 asserts the installed identity facts
  (console path, package path, Python version, wheel SHA, payload verification
  booleans) for every run.
- Owned PostgreSQL 16 container, unique per run: name `slaif205a-<RUN_TOKEN>`,
  labels `slaif205a.run=<RUN_TOKEN>` / `slaif205a.owner=uid<uid>` /
  `slaif205a.purpose=field-workflow-qualification` / `slaif205a.order=205-a`,
  loopback-only published port, 512 MiB tmpfs data directory. Ownership,
  labels, loopback binding, and tmpfs are inspected BEFORE migrations; only
  the exact owned container ID is removed in teardown after re-checking its
  label. Verified after the final run: no container with label
  `slaif205a.order=205-a` remains.
- Generated credentials (PG password, HMAC secret, one-time-secret encryption
  key, key secrets) are random, kept in memory or 0600 files, and
  substituted/masked in every retained projection; retained artifacts carry
  booleans/hashes only. No real OpenAI/OpenRouter backend, no real client,
  no real SMTP, no Redis anywhere in this record.

## IO substitutions (executed layer)

- SMTP: loopback synthetic sink (`127.0.0.1`, owned port) is armed in the
  fixture. The one-time key-delivery lifecycle (outcome 9) is NOT yet
  exercised against it by the module.
- Provider upstream: the test module contains DRAFT, not-yet-wired
  `ProviderMock` / `GatewayServer` helpers for outcomes 5–11; the current
  seed uses a fictional provider `base_url`
  (`https://openai-fixture.example.invalid/v1`) and NO gateway process is
  started. Outcomes 5, 7, 8, 10 therefore have no executed evidence here.

## Per-outcome evidence (order section 12, eleven outcomes)

Final module run (`205a-final2`, JUnit authoritative, 2026-10-29T13:55Z,
6 tests, 0 failures, 0 errors, 0 skipped, exit 0, 216.98 s) — the only run
whose test bytes equal the committed test file:

| # | Outcome (order title) | Status | Evidence |
|---|-----------------------|--------|----------|
| 1 | Identities: list/show by UUID/public-ID/exact owner email, complete bounded paging, full-bearer lookup refusal without echo | EXECUTED PASSED | `test_dod1_lookup_and_bounded_paging` |
| 2 | Effective policy + route explanation: configured vs inherited rate members/sources, unlimited quotas vs inherited operational limits, allow-list/enabled-route intersection | EXECUTED PASSED | `test_dod2_effective_policy_and_route_explanation` |
| 3 | Record operations: institution/owner/cohort create/list/show exactly once, normalized duplicate refusal, owner move preserving omitted fields/member key state, cohort edit omission/clear rules, bad UUID/no-reason/conflict negatives | EXECUTED PASSED | `test_dod3_record_operations` |
| 4 | Exact standard student/beta + TWO chat clones: dry-run plans, one secure channel per execute, canonical configuration parity (incl. nontrivial Codex/Responses pin), inherited members as inheritance, zero copied usage/ownership, source unchanged, exact-repeat dedup, stale/unknown-field refusals, deny-all providers distinct | EXECUTED PASSED | `test_dod4_exact_student_beta_and_chat_clones` |
| 5 | Discovery grant: `keys policy update` + real filtered `GET /v1/models` through the installed gateway | NOT EXECUTED | gateway not started; draft helper not wired (205-b) |
| 6 | Rates, bounded lazy configuration (within actual ceilings, overbound refusal, reject/clear), exact-37 cohort batch with stale refusal after new-member create, UUID re-review, exact 37 audits | EXECUTED PASSED | `test_dod6_rates_lazy_and_exact37_batch` |
| 7 | Two configured completion services via `providers add` (disabled, distinct origins/profiles/timeouts/zero retries) | NOT EXECUTED | 205-b |
| 8 | Explicit activation + stable route edit (`routes update` dry-run/execute, ceiling/media changes, stale-plan refusal) | NOT EXECUTED | 205-b |
| 9 | One-time delivery lifecycle: real send to loopback SMTP, consumption, repeat refusal, sent/failed/pending/expired/ambiguous inspection and safe retry semantics | NOT EXECUTED | SMTP sink armed, flow not yet in module (205-b) |
| 10 | Gateway-recorded failure investigations via installed `diagnostics request show` | NOT EXECUTED | no gateway process/diagnostics arming yet (205-b) |
| 11 | Reviewed replay maintenance via installed `codex replay inspect/extend` | NOT EXECUTED | 205-b |

Additional order requirement: `config show --json`/text with a valid
override/default/source/restart snapshot plus an invalid-Settings no-echo
probe — NOT EXECUTED in this module (205-b).

Qualification: these are installed-CLI workflow proofs on a fictional owned
fixture. They are not real-provider/client/backend qualification, not a
measured performance claim, and not evidence for the unexecuted outcomes.

## JUnit chronology (overlapping slice runs; never summed)

All runs: same module path, JUnit XML authoritative (repository addopts
suppress the console summary), zero skips in every run.

| Artifact (UTC 2026-10-29) | tests | failures | failing cases |
|---|---|---|---|
| `205a-slice1` 12:45 | 4 (DoD0–3) | 0 | — (first green slice) |
| `205a-slice2` 12:53 | 6 | 2 | DoD4, DoD6 |
| `205a-slice3` 13:04 | 6 | 2 | DoD4, DoD6 |
| `205a-slice4` 13:16 | 6 | 2 | DoD4, DoD6 |
| `205a-slice5` 13:21 | 6 | 2 | DoD4, DoD6 |
| `205a-slice6` 13:25 | 6 | 2 | DoD4, DoD6 |
| `205a-slice7` 13:32 | 6 | 2 | DoD4, DoD6 |
| `205a-slice8` 13:37 | 6 | 1 | DoD6 |
| `205a-slice9` 13:45 | 6 | 1 | DoD6 (stale-batch error-code oracle: installed boundary reports `key_batch_stale`, not generic `command_failed`) |
| `205a-final` 13:50 | 6 | 0 | — (post oracle fix) |
| `205a-final2` 13:55 | 6 | 0 | — (final byte-matched run; the only delta after `205a-final` was removal of one unused local assignment, non-behavioral hygiene) |

The intermediate failures are draft-iteration harness/oracle corrections in
the NEW test file (seed field fidelity, clone source fixtures, metadata
column names, error-code mapping, lazy stored-state assertions); each was
corrected in the test file and re-run. They are not product failures and are
not summed as unique cases.

## ROOT independent evidence (root runs, not agent runs)

Credited separately from the pytest evidence above:

- `205-qualification-baseline.json` — product/preserved-path baseline
  (466 product paths, 1724 existing non-allowed paths) deriving the accepted
  tree; cited by the order.
- `205-installed-lazy-numeric-canary-probe.json` — actual installed CLI
  probe: both `set-lazy-throttling` numeric flags echo a complete generated
  credential-shaped canary in usage stderr, exit 2 (boolean-only receipt).
- `205-installed-new-numeric-surface-canary-probe.json` — actual installed
  CLI probe: 17 argument positions across the SELECTED new/extended
  lookup/clone/lazy/provider/route/replay command families echo complete
  generated credential-shaped values, all exit 2 (boolean metadata only, no
  raw outputs). This is a bounded probe of the selected families, NOT a
  blanket legacy-CLI audit claim.
- `205-numeric-privacy-scope-decision.json` — root scope decision reserving a
  narrow 205-b numeric-parsing fix (preserving retry-0/offset-0/signed
  priority/None handling, existing validators, and all eleven outcomes) on
  the same 205 PR.
- Root-verified wheel/venv installation: 432 application files byte-identical
  to accepted source `5e59a02` (only 4 empty `.gitkeep` placeholders omitted),
  installed console at the owned venv path; root also enforced private
  creation for generated fixture credentials (final fixture asserts 0600).
- Root review aids: `/tmp/slaif205-root/early-installed-workflow-review.md`
  (fixture items 1–9) and `/tmp/slaif205-root/clone-batch-slice-review.md`
  (clone/batch slice corrections), plus the source command map
  `205-cli-command-planning-checkpoint-20261029.json`.

## Product scope boundary (deferred to same-PR 205-b)

The confirmed NEW CLI privacy gap — credential-shaped numeric input echoed
completely in `set-lazy-throttling` usage stderr before the command body
runs — requires product edits, which active 205-a explicitly does not
permit. It is reported, not fixed, in this handoff. The ordinary usage-error
law itself (native Typer `BadParameter` → exit 2, stderr, no JSON payload,
even with `--json`) is documented 197 behavior: the module asserts the fixed
refusal and unchanged state, and does NOT treat non-JSON usage output alone
as a defect or weaken actual bounds. No product, runtime, schema, migration,
settings/CI byte was changed under 205-a.

## Limitations

- No gateway process is started by the current fixture; outcomes 5, 7, 8,
  10, 11 and the config-show evidence have NO executed proof yet.
- The provider mock and gateway server helpers are drafted in the module but
  not wired into the fixture; the seed's provider `base_url` is fictional and
  never contacted.
- SMTP sink is armed but the one-time delivery lifecycle (outcome 9) is not
  yet exercised.
- No merge, no tag/release, no real provider/client/mail, no Redis.

## 205-b continuation (bounded numeric repair + re-qualified first slices)

**Status: bounded round complete for its numeric repair + first slices; full
205 remains PARTIAL** (outcomes 5, 7-11, config-show, and the final fresh
all-eleven run are carried forward to later same-PR suffixes) —
SUPERSEDED: every carried-forward item was completed by the 205-d,
205-e, and 205-f sections below (outcomes 9/11 + config in 205-d,
outcome 10 in 205-e, and the single final fresh 13-case run + complete
transcript + full-scope audit in 205-f).

### Product fix (implementation commit `420fb8f`)

The 205-confirmed defect (complete credential-shaped numeric input echoed in
native usage errors before the command body) is fixed by ONE shared
no-echo whole-number conversion helper
(`app/slaif_gateway/cli/common.py::parse_int_option`), applied at the 17
observed positions in `app/slaif_gateway/cli/keys.py` (clone
`--validity-duration-seconds`; list `--limit`/`--offset`;
`set-lazy-throttling` `--max-wait-seconds`/`--max-waiting-requests`),
`app/slaif_gateway/cli/providers.py` (add/update `--timeout-seconds`/
`--max-retries`), `app/slaif_gateway/cli/routes.py` (update-only:
`--codex-context-window-tokens`, `--codex-default-max-output-tokens`,
`--codex-max-output-tokens`, `--media-image-tokens`, `--media-video-tokens`,
`--media-video-frames`, `--priority`), and
`app/slaif_gateway/cli/codex_replay.py` (extend `--ttl-seconds`).

Semantics: conversion mirrors the installed Typer/Click `int` conversion
exactly (same int payload for every previously accepted value); omitted flags
still yield their documented defaults; explicit `0` is distinct from omitted
(`None`); signed route priority incl. 0/negative is preserved; existing
domain constraints, ceilings, mixed-mode/clear guards, flag spellings,
defaults, and help are unchanged. Invalid values (non-numeric text, floats,
bool-like words, blanks, recognized credential shapes, over-limit digit
strings) are refused with the fixed message
`<option> must be a whole number` — never echoing the value — before any
database, provider, queue, or SMTP access.

Bounded malformed-value error difference (documented, tested):

| Command / option(s) | Channel | Exit |
|---|---|---|
| `keys clone --validity-duration-seconds` | JSON `{"error":{"code":"invalid_parameter",...}}` inside the command's existing safe error handler | 1 |
| all other 16 positions above | native Typer usage refusal, fixed message, stderr, no JSON payload (even with `--json`) | 2 |

Missing/unknown-option errors and all other error channels are unchanged;
this is not a promise that all Typer usage errors become JSON.

### Unit evidence (agent pytest, JUnit authoritative)

- NEW `tests/unit/test_cli_numeric_privacy.py`: 110 PASS, 0 failures, 0
  errors, 0 skipped, 33.13 s (JUnit `205b-numeric-privacy-2`,
  sha256 `33e7d67b7c59267307d18f7117ecbcc8f67c90f40ec412e3c910691794385715`).
  Coverage: 17 canary positions (fixed refusal, complete canary absent from
  stdout/stderr/logs, no traceback, no operation-layer reach) + invalid-shape
  refusals with boolean-only failure representations + valid payload controls
  (limit lookahead, explicit-0 domain refusals, lazy 30/4, clone 3600,
  providers 45/0 + omitted `None`, routes signed `-5`/400000 + omitted
  `None`, extend 3600 + omitted `None`) + 17 shared-helper
  Click-parity/fixed-error cases.
- Affected existing CLI units (7 files, unchanged bytes): 136 PASS, 0
  failures, 0 skipped, 62.79 s (JUnit `205b-existing-cli`, sha256
  `ab70adace897ca02343c50f42d5eeaa7623a89020b544a2479518aa30c3503c2`):
  `test_cli_keys_clone.py`, `test_cli_keys_effective_policy.py`,
  `test_cli_keys_status.py`, `test_cli_provider_route_configuration.py`,
  `test_cli_providers.py`, `test_cli_routes.py`,
  `test_cli_codex_replay.py`.

CI renderer chronology (test-only repair, commit `99989fe`): the
implementation head's CI job "Unit, lint, and migration head" failed 76
of the 110 new cases under the GHA colored narrow terminal (75
fixed-message substrings + 1 positive-limit literal); all other CI jobs
were green. The app renders Click usage errors through a rich error
panel whose ANSI styling and width-dependent wrapping are terminal
properties, not product behavior; the local NO_COLOR wide-terminal run
had passed. The module was repaired in place with the established
project renderer-stable pattern (TERM_ENV COLUMNS=220/NO_COLOR=1 per
invocation + ANSI-strip/whitespace-normalized fixed-reason comparison),
keeping the raw canary/exit/no-op/no-echo/caplog assertions intact; no
product message or behavior changed. Focused module re-verified 110
PASS 0 skip under a forced-color narrow CI-like terminal (JUnit
`205b-ci-fixed`, sha256
`035b279f4994038523bd8e9133f339f3963680025660574bcaf0e85a51aa29f0`) and
under the normal NO_COLOR local env (JUnit `205b-numeric-privacy-3`,
sha256 `aeaf706f350a8bd4a2b7e1fbcb0f0bbb5a9155f9da0fb1bf007c9dcd604d76bb`).
Chronology: CI run 40892694064 (head `420fb8f`) 76 failed / 6434 passed
/ 1 skipped (172.49 s); CI run 40896109400 (head `0e4c229`) same unit
job 76 failed / 6434 passed / 1 skipped (162.64 s); local forced-color
narrow reproduction (JUnit `205b-ci-repro`, sha256
`bed28b5cedece4d28f514e97dee0533c718ea0043f681b99b96602159962d9f0`)
76 failed / 34 passed.

### Installation identity for the 205-b slice (executed)

- Source: `420fb8f6d9377f569d126d08f4c9e4146fc7250b` (the 205-b
  implementation commit), pinned shallow-safely; shallow archival verified in
  owned scratch (fresh depth-1 clone of origin lacks the commit; narrow
  `git fetch --depth 1 origin <SHA>`; `git archive` payload tree
  `1213f89b985f514204821790d79ddb2b24710b76` equals the local commit tree).
- Wheel: `slaif_api_gateway-0.1.0-py3-none-any.whl`, actual selected
  SHA256 `042eb23ac7042d2e77c4af4dca6d80d52f0968a328b33d03c8d0f825c07dad6f`,
  built from that exact committed source; installed into a FRESH owned venv
  (Python 3.12.15) under the pytest temp tree, outside the checkout,
  `PYTHONPATH` absent. The stale 205-a venv was rejected by the new
  installed-payload-vs-selected-wheel gate and replaced.
- Root independently verified the fixed installation: all 432
  wheel/source/installed application files match committed `420fb8f` (root
  evidence, not an agent run).
- Schema clarification: at the `0026` migration head the database holds
  34 public tables = 33 product tables (including `request_diagnostics`) +
  `alembic_version`. Objective 205 adds NO new schema, NO key-policy
  migration, and NO migration of any kind.

### Installed first-six-case slice (executed, owned PG 16)

JUnit `205b-installed-slice` (2026-10-29T14:39:06Z, sha256
`f4d7d6fcf9d471cfa3748bb652b5b509250917ffb8799d02246cfd0bc83b8db3`):
6 tests, 0 failures, 0 errors, 0 skipped, 242.46 s, pytest exit 0 —
`test_dod0_installed_identity`, `test_dod1_lookup_and_bounded_paging`,
`test_dod2_effective_policy_and_route_explanation`,
`test_dod3_record_operations`, `test_dod4_exact_student_beta_and_chat_clones`,
`test_dod6_rates_lazy_and_exact37_batch` — i.e. outcomes 1-4 and 6 plus the
DoD0 installed-identity acceptance, re-qualified on the fixed wheel.

Failed-run chronology (preserved, not summed, not passes): before the green
run, two earlier attempts each produced 6 setup ERRORs — (a)
`FileExistsError` in the wheel-extraction step on the stale-candidate
-> fresh-build path (fixture needed `exist_ok` on the owned extraction dir),
and (b) the fresh owned venv failing its identity check because the setup
subprocesses inherited `PYTHONPATH=app`, making pip treat the same-version
wheel as already installed. Both were fixture-setup defects corrected in the
NEW test file; the original failed XML/log paths were subsequently REUSED by
the green run (overwritten), so the failed-run metadata/hash/cause is
preserved in the root receipt `205-b-setup-and-interim-evidence.json` rather
than in local artifacts. No reconstruction or repeat was performed.

### ROOT independent evidence for 205-b (root runs, not agent runs)

- `205-b-early-root-helper-probe.json` — source-level helper probe: 8
  Click-parity + 2 omission/default + 8 fixed-error controls (no DB; not
  installed proof).
- `205-b-root-fixed-wheel-installed-identity.json` — fixed installed
  identity: 432 wheel/source/installed app files match committed `420fb8f`,
  Python 3.12.15, outside-checkout with `PYTHONPATH` absent.
- `205-b-root-fixed-installed-numeric-probe.json` — actual installed
  17-position canary probe on the fixed wheel: ALL PASS (fixed numeric
  refusal, nonzero exit, complete canary absent, no traceback, no
  `command_failed`).
- `205-b-installed-slice-evidence.json` — final six-PASS slice receipt with
  actual selected wheel SHA256 and identity facts.
- `205-b-setup-and-interim-evidence.json` — preserved failed first-six
  setup-ERROR metadata/hash/cause and the adjusted 110-PASS unit run.

### Carry-forward to later SAME-205-PR suffixes

| Item | State after 205-b |
|---|---|
| Outcome 5 (discovery grant + real filtered `GET /v1/models`) | UNPROVEN — not executed |
| Outcome 7 (two configured completion services) | UNPROVEN — not executed |
| Outcome 8 (explicit activation + stable route edit) | UNPROVEN — not executed |
| Outcome 9 (one-time delivery lifecycle, loopback SMTP) | UNPROVEN — not executed |
| Outcome 10 (gateway-recorded failure investigations) | UNPROVEN — not executed |
| Outcome 11 (reviewed replay maintenance) | UNPROVEN — not executed |
| `config show` evidence (valid snapshot + invalid-Settings no-echo) | UNPROVEN — not executed |
| Persisted safe requirement-indexed operator transcript (argv/output/exit/identity export) | NOT IMPLEMENTED — in-memory projections only for assertions; next qualifier persists, final fresh all-eleven exports |
| Final fresh-installation all-eleven module run | NOT EXECUTED — mandatory for objective completion |

State-table note: the rows marked UNPROVEN / NOT IMPLEMENTED / NOT DONE
/ PARTIAL / NOT EXECUTED above describe the state at the point of that
section only. The carried-forward items were subsequently completed by
the 205-c (outcomes 5/7/8 + persisted transcript), 205-d (outcomes 9/11
+ config), 205-e (outcome 10), and 205-f (final fresh 13-case run,
complete transcript, full-scope audit) sections.
## 205-c continuation (outcomes 5, 7, 8 + persisted operator transcript)

**Status: bounded round complete for outcomes 5, 7, 8 and the safe
persisted transcript/identity export; full 205 remains PARTIAL**
(outcomes 9, 10, 11, config-show, and the final fresh all-eleven run are
carried forward to later same-PR suffixes) — SUPERSEDED: all
carried-forward items were completed by the 205-d (outcomes 9/11 +
config), 205-e (outcome 10), and 205-f (single final fresh 13-case run,
complete transcript, full-scope audit) sections below. No product byte
changed in
205-c: source stayed frozen at `420fb8f` (466 product paths byte-identical
per root baseline `205-c-product-baseline.json`); only the allowed test and
documentation paths changed.

### Installation identity for the 205-c runs (executed)

- Source: `420fb8f6d9377f569d126d08f4c9e4146fc7250b` (the 205-b
  implementation commit; B-later commits are product-equivalent), pinned
  shallow-safely in the owned pristine archive.
- Final combined run (`205c-final-1`): FRESH wheel
  `slaif_api_gateway-0.1.0-py3-none-any.whl`, actual selected SHA256
  `cf7e114f1ebdcb8d8f22cccd4f106c08bcb061268fac14dac67eebf97c0db9c1`,
  built from that exact pinned source; the fixture records the ACTUAL
  selected wheel SHA (not a manual ZIP hash) and re-verifies the payload
  (432 wheel payload files) for both reuse and fresh builds. FRESH owned
  venv under the pytest temp tree, outside the checkout, `PYTHONPATH`
  absent, Python 3.12.15, installed console
  `.../pytest-1575/slaif205-field0/venv/bin/slaif-gateway`; installed
  payload verified 432 files. Each slice run recorded its own selected
  wheel SHA the same way.
- Owned PostgreSQL 16 container, unique per run: run-token name/labels,
  loopback-only published port, 512 MiB tmpfs data dir, ownership/labels
  inspected BEFORE migrations, exact-ID/label cleanup after. Final run
  container `b6259642ed72af21eec139bd7d941e3265b702a9ae29c41a0c5dabcea93c6c13`
  (port 55845) removed in teardown. Verified after the final run: no
  `slaif205*` container remains.
- The installed gateway (outcome 5) is the ACTUAL installed
  `slaif_gateway.main:app` on an owned loopback port against the owned PG,
  scrubbed explicit fictional settings, capture explicitly OFF. Synthetic
  HTTP stimulus only: no provider inference, no real client, no real
  credentials, no Redis, no real mail.

### Outcome 5 — actual filtered model discovery (EXECUTED PASSED)

`test_dod5_filtered_model_discovery` (14 labeled transcript records):
installed console issues a dedicated synthetic standard key with ONE
explicit secure output channel (`keys create --secret-output-file`; the
generated value is registered before retention); actual `GET /v1/models`
is denied OpenAI-shaped before the grant; a canary-bearing `keys show`
lookup is refused with the fixed no-echo message; installed
`keys policy update` adds `/v1/models` while explicitly retaining the
inference endpoint (endpoint arrays REPLACE); the filtered `GET /v1/models`
then succeeds with exactly the enabled permitted model and meaningful
controls: model-allowlist exclusion, `--allowed-provider openai` /
`--provider-none` / `--provider-all`, and `providers disable/enable` plus
`routes disable/enable` each flipping the returned list. Preservation is
asserted on the effective policy sections, the canonical export (differs
ONLY in `allowed_endpoints` in the final state), the key metadata column,
and key material/expiry (boolean compares). Read-only discovery is not
provider inference or cost qualification.

### Outcome 7 — two configured completion services (EXECUTED PASSED)

`test_dod7_two_configured_completion_services` (26 labeled records):
TWO fictional module providers (`svc-a`/`svc-b`) prepared via installed
`providers add` DISABLED (distinct origins/env-reference NAMES only,
custom timeouts 30/180, zero retries; bundled profiles `zap-it-v1` /
`facial-scoring-v1` with their exact public/upstream/profile mappings,
module kind, non-streaming, zero-retry contracts) and TWO capabilities-file
routes prepared disabled (`--no-streaming`); both pairs inspected via
`providers show/list`, `routes show/list`, `pricing list` (exact
`Decimal == Decimal` money semantics at the `Numeric(18,9)` scale); three
fixed-message refusals exercised (streaming on a non-streaming profile,
kind mismatch, retry provider `max_retries 1` → must-not-retry); then
SEPARATE explicit `providers enable` + `routes enable` for BOTH pairs; a
partial `providers update svc-a --timeout-seconds 45` preserves omitted
siblings, explicit zero, and the unrelated `openai` provider
byte-identical. No provider HTTP, no real credentials, no generalized
compatibility claim.

### Outcome 8 — stable route context/media updates (EXECUTED PASSED)

`test_dod8_stable_route_context_media_updates` (26 labeled records):
two dedicated exact-match routes (`slaif205a-model-e`/`fixture-e` and
`slaif205a-model-f`/`fixture-f`) prepared disabled with coherent LOW
codex/media capability data. A clearly separated fictional historical
linkage (pre-existing key + usage-ledger row + replay reference bound to
the first route) is planted by `_plant_dod8_history`: a FIXTURE SETUP
helper running the product-equivalent ORM (same committed `420fb8f`
source bytes) inside the pytest process — NOT an installed operator CLI
action — with constant synthetic digests only; the planted ledger row is
`pending`, NOT a successful-finalized replay-eligibility record.
Snapshots before mutation: the meaningful existing key's canonical policy
export + full row + material/expiry, the installed COMPLETION-SERVICE
SERVER profile data fingerprint
(`modules/servers/completion_service/profiles/*.json` — server data, not
an external Codex client catalog; the client-module pin is a separate
matter not covered by the canonical key export), every unrelated
route/provider, and the audit count. Then:
`routes update <uuid> --dry-run PLAN` (read-only, private 0600 plan) then
`--execute PLAN --reason` moving the selected context genuinely
105000 → 400000 (+1 audit, sibling route untouched); a second plan moving
media image/video token and frame leaves (codex preserved, +1 audit); a
SEPARATE plan for the second route (context 420000 + media image 1200,
+1 audit, first route untouched). Re-applying the stale first plan is
refused with JSON `invalid_value` ("no longer matches") and zero
additional mutation/audit; mixed edit-flag + plan mode is a native Typer
usage refusal (exit 2, fixed renderer-normalized stderr, no JSON). Stable
route UUID/`created_at`, pre-existing ledger/replay ROUTE-link rows,
key policy export + material, profile-data fingerprint, and all unrelated
routes/providers are asserted unchanged. No delete/recreate, no raw-SQL
mutation, no shared-service bypass.

### Persisted operator transcript and identity (order §7, executed)

`FieldEnvironment.persist_transcript` writes per-run, outside the
checkout, into a 0700 directory:
`/tmp/slaif205/transcripts/<RUN_TOKEN>/transcript.json` and
`identity.json`, both 0600, never overwriting another run; the paths,
SHA256, and record/label counts are asserted by the test. Final combined
run `29b67e22ffd54baf`: 66 records (14 + 26 + 26), 0 unlabeled,
transcript SHA256
`549a089680d10ddbae597ca1c93639057c99cd8abcfa31c714c843bb45d67fde`,
identity SHA256
`94a2aa1411298b780b387e0a6a4063dbbc7660f293e1dc12dae72b6c35c09021`.
Records carry actual requirement-indexed argv boundaries/output
projections/exit codes plus safe run/installation identity; the
refused-bearer record shows argv masking (`<REFUSED-BEARER-SHAPE>`), and
canary checks prove every generated secret absent from the persisted
files. Source/tests/fixture-setup SQL and ORM plants are separately
explained in this record and never presented as operator CLI actions.
This is a PARTIAL transcript: only the NEW C cases are recorded. The
previously executed six outcomes are not retroactively re-transcribed,
and NO all-eleven transcript exists yet; the final fresh all-eleven run
must export every outcome.

### JUnit chronology (205-c slice runs; overlapping, never summed)

All runs: `tests/integration/test_cli_field_installed_workflow.py`,
JUnit XML authoritative (repository addopts suppress the console
summary), zero skips in every run, UTC 2026-10-29:

| Artifact (time) | tests | failures | note (sha256 prefix) |
|---|---|---|---|
| `205c-dod5-1` 15:41 | 1 | 1 | draft `GatewayServer` not yet wired (`start_gateway` AttributeError) — fixture wiring gap (7b7e9018) |
| `205c-dod5-2` 15:47 | 1 | 0 | green before the provider allow-list/disable controls were added (01b85d54) |
| `205c-dod5-3` 15:55 | 1 | 0 | final DoD5 with meaningful provider/allow-list controls, 14 labels; root independently verified (e277aa3c) |
| `205c-dod7-1` 15:57 | 1 | 1 | money oracle: `Numeric(18,9)` renders `0.010000000`; corrected to `Decimal == Decimal` (no float/tolerance) (3b36a7d0) |
| `205c-dod7-2` 15:59 | 1 | 0 | final DoD7, 26 labels (12df8ebc) |
| `205c-dod8-1` 16:00 | 1 | 1 | mixed-mode oracle: a `typer.BadParameter` raised in the command body is a NATIVE Typer usage error (exit 2, fixed stderr, no JSON); oracle corrected to the installed behavior (7bd52dd0) |
| `205c-dod8-2` 16:02 | 1 | 0 | DoD8 v1 (pre multi-route/key-policy extension) (93095a4d) |
| `205c-dod8-3` 16:10 | 1 | 1 | extended DoD8: raw string-bound asyncpg SQL fixture defect in the history planting (fixture defect, not product) (ea9e11ef) |
| `205c-dod8-4` 16:12 | 1 | 1 | same fixture defect, variant SQL (44ade823) |
| `205c-dod8-5` 16:13 | 1 | 1 | same fixture defect, `make_interval` variant (65e49cf2) |
| `205c-dod8-6` 16:25 | 1 | 0 | extended DoD8 with ORM planting (`_plant_dod8_history`, 199 reference pattern); root-verified expanded case: 26 records, 0 blank labels, two UUIDs at 400000/420000, stale + mixed refusals, proper PG cleanup (7e1b97bc) |
| `205c-combined-1` 16:05 | 3 | 0 | first combined run on the PRE-EXTENSION test bytes (weaker outcome 8); superseded by the final run, NOT evidence for the final DoD8 (cae0c207) |
| `205c-final-1` 16:29 | 3 | 0 | FINAL combined run of the final test bytes + persisted transcript: `test_dod5_filtered_model_discovery`, `test_dod7_two_configured_completion_services`, `test_dod8_stable_route_context_media_updates` (fd8f167e) |

The intermediate failures are NEW-test-file fixture/oracle corrections
(gateway wiring, Decimal-scale money oracle, native-usage-error oracle,
raw-SQL fixture binding); each was corrected in the allowed test file and
re-run. They are not product failures and are not summed as unique cases.

### ROOT independent evidence for 205-c (root runs, not agent runs)

- `205-c-product-baseline.json` — product/preserved-path baseline (466
  product paths, 1732 non-allowed existing paths, protected untracked
  hashes) binding the frozen `420fb8f` tree for the round.
- `205-c-final-combined-root-review.json` — root re-verified the final
  combined JUnit (3 PASS, 0 skip, 184.77 s, SHA256
  `fd8f167eb7ccb856b204bcb5cf3f135e3f4584b12c4cad38b682cbb94a27f9cb`)
  with the actual cumulative 66-record transcript (14 + 26 + 26, all
  indexed, 0700/0600 private), and independently byte-verified ALL 432
  source/wheel/installed application files at `420fb8f` after the run —
  INCLUDING the installed client-compatibility JSON (the client-data
  boundary) — against actual wheel SHA256
  `cf7e114f1ebdcb8d8f22cccd4f106c08bcb061268fac14dac67eebf97c0db9c1`;
  exact owned PG container absent after teardown.

### Scratch-container deviation (corrected, disclosed)

While investigating the `205c-dod8-3/4/5` fixture SQL defect, a throwaway
PostgreSQL 16 container `slaif205-scratch` (exact ID
`f4e53597cc085cedeb9e163dcb2e6666314d73513434d6d74c4292da251bc8f5`) was
temporarily created on a fixed loopback port WITHOUT the required
run/owner labels and tmpfs data dir — a deviation from the owned
unique-run/labeled/tmpfs setup contract. Root detected it by
metadata-only inspection.

Container cleanup: the exact container was stopped and removed (ONLY that
container; unrelated containers untouched), and no Config.Env/password
content was retained in any artifact. Because it was removed with
`docker rm` (no `-v`) while the `postgres:16` image declares a data
VOLUME, the attached anonymous volume survived container removal.

Volume ownership is an INFERENCE, not an independently verified
mount/event mapping (no docker event record or prior-mount record for the
volume exists; the root bounded volume-event query returned no matching
records). The inference basis: (a) the logged creation command (agent
session record, 2026-10-29T16:14:34.804Z: `docker run -d --name
slaif205-scratch -e POSTGRES_USER=u -e POSTGRES_PASSWORD=<REDACTED> -e
POSTGRES_DB=d -p 127.0.0.1:55432:5432 postgres:16` — no tmpfs, no named
volume, no `--rm`) combined with the data VOLUME declared by the
`postgres:16` image, under which the Docker engine necessarily created
exactly one anonymous volume at container creation (2026-10-29T16:14:34Z);
(b) of all 120 host volumes, exactly ONE volume
(`f95b26cf1c21e0b7b38fb6b72fcf17ea35e243d8c1c47bb6177f77f283497080`) was
created at that exact second — the newest volume on the host, with no
other volume created in the 16:00–17:00 window; (c) it carries the
`com.docker.volume.anonymous` label and had no mount points after the
container removal, so no other candidate exists.

Volume cleanup: given (a)–(c) with a unique candidate, that exact volume
was removed (no `volume prune`, no timestamp-only guesses, no unrelated
deletion); the host volume count returned from 120 to 119 and the
remaining volumes are untouched. Limit: without an independent
mount/event record, the ownership determination rests on the creation
command + declared image VOLUME + unique anonymous CreatedAt — an
inference with a single candidate, not a direct provenance record.

After both cleanups, no `slaif205*` container and no attributable scratch
storage remain. The fixture SQL was NOT "fixed" by changing
product/schema: the final DoD8 history planting uses the existing 199 ORM
reference pattern inside the owned fixture, and no scratch container or
volume is used by the final test bytes.

### Carry-forward to later SAME-205-PR suffixes

| Item | State after 205-c |
|---|---|
| Outcome 5 (discovery grant + real filtered `GET /v1/models`) | EXECUTED PASSED (this section) |
| Outcome 7 (two configured completion services) | EXECUTED PASSED (this section) |
| Outcome 8 (explicit activation + stable route edit) | EXECUTED PASSED (this section) |
| Outcome 9 (one-time delivery lifecycle, loopback SMTP) | UNPROVEN — not executed |
| Outcome 10 (gateway-recorded failure investigations) | UNPROVEN — not executed |
| Outcome 11 (reviewed replay maintenance) | UNPROVEN — not executed |
| `config show` evidence (valid snapshot + invalid-Settings no-echo) | UNPROVEN — not executed |
| Portable environment / Compose-recreate / proxy guidance + P0/P1 audit + stale 202-204 doc corrections | NOT DONE — order §9 remainder |
| Persisted all-eleven transcript (every outcome + identity) | PARTIAL — new C cases only (66 records); final fresh run must export all |
| Final fresh-installation all-eleven module run | NOT EXECUTED — mandatory for objective completion |

State-table note: the rows marked UNPROVEN / NOT IMPLEMENTED / NOT DONE
/ PARTIAL / NOT EXECUTED above describe the state at the point of that
section only. The carried-forward items were subsequently completed by
the 205-c (outcomes 5/7/8 + persisted transcript), 205-d (outcomes 9/11
+ config), 205-e (outcome 10), and 205-f (final fresh 13-case run,
complete transcript, full-scope audit) sections.
### Limitations (205-c)

- The C evidence is installed-CLI + owned-gateway + owned-PG proof with
  synthetic HTTP/provider/SMTP IO and fictional historical setup; it is
  not real-provider/client/backend qualification, not measured
  performance, and not evidence for the unexecuted outcomes.
- `_profile_data_fingerprint` covers installed completion-service server
  data only; the installed client data is covered separately by the root
  post-run 432 payload comparison (ROOT independent evidence above).
- The outcome-8 planted history is fixture setup via product-equivalent
  ORM (pending ledger), never an operator action or replay-eligibility
  proof.
- No schema, key-policy, or migration of any kind in 205; no merge, no
  tag/release, no real provider/client/mail, no Redis.

## 205-d continuation (outcomes 9 and 11 + installed config inspection)

Recorded 2026-10-29. Tests/documentation only; the product remains
frozen at `420fb8f` (root baseline `205-d-product-baseline.json`: 466
product + 1734 non-allowed paths byte-identical across the round). All
evidence below is through per-run FRESH wheels built from that pinned
source (payload-verified, 432 files) and installed into FRESH owned
venvs under the per-run pytest temp tree — literal final-run identity
below; wheel SHAs differ per build (wheel metadata), payload identity
against `420fb8f` is the binding fact, and no run reused the 205-b/c
venv bytes. The owned labeled PostgreSQL 16 + loopback SMTP sink
fixture is unchanged; no product edits, no scratch Docker, no real
provider/client/mail.

### Outcome 9 (one-time delivery lifecycle, loopback SMTP) — EXECUTED PASSED

`test_dod9_mail_delivery_and_inspection`, every operator action a
subprocess of the installed console:

- Clone from the fully-routable positive source `k_student`
  (dry-run 0600 plan; execute with EXACTLY ONE channel,
  `--email-delivery pending`; no plaintext, and the pending channel
  reports no delivery-status key — the prepared row's `pending` state
  is proven by installed `email show`, not by a send result).
- Installed `email show`/`email list` inspect the prepared pending
  delivery: flat item payload + `one_time_secret` lifecycle;
  recipient bound to the owner's CURRENT email.
- Actual `send-pending-key --send-now`: ONE SMTP DATA acceptance on the
  owned loopback sink; the FULL generated key is read from the MIME
  transfer-decoded body (the wire key line is longer than the MIME
  generator's wrap width, so a raw wire fragment is not the complete
  key) and registered before any retention; the secret is consumed and
  the sent row shows `one_time_secret.status = consumed`.
- Exact repeat: refused, no second SMTP send, no re-consumption.
- Second clone plus a minimal deterministic fixture 550 refusal:
  `smtp_send_error` failed state with `last_recorded_failure`; no
  automatic retry (missing flag refused), blank `--reason` refused, and
  an explicit `--retry-failed` with a nonblank reason retries safely
  (same secret, key material unchanged; the distinct key observed in
  the second accepted message is registered from the decoded body).
- Clearly labeled PRE-EXISTING fixture states (a `sending` delivery, an
  `ambiguous` delivery, and a `pending` delivery bound to an EXPIRED
  secret; ORM setup only, recipients bound to the owner's current
  email) are first inspected through the installed read-only commands
  (fixed per-state blocking reasons and lifecycle statuses), THEN each
  unsafe send is refused with ZERO additional SMTP; the expired-secret
  post-state is delivery `failed` +
  `last_recorded_failure = one_time_secret_expired`.
- Invariants: `usage_ledger` unchanged, +5 keys / +5 deliveries, the
  clone source row unchanged; 25 labeled records persisted for the case.

### Outcome 11 (reviewed replay-reference expiry maintenance) — EXECUTED PASSED

`test_dod11_replay_expiry_maintenance` under an explicitly configured
`CODEX_REPLAY_REFERENCE_TTL_SECONDS = 2592000` (exactly 30 days) in the
installed CLI subprocess environment:

- Five schema-valid planted references (all `reasoning` kind;
  provider/upstream matching the ACTUAL route; the
  `codex_replay_references` CHECK constraints are preserved, never
  relaxed), each with its own ledger: an eligible short-expiry row, an
  eligible no-shorten row, a default-excluded expired row, an
  unavailable-HMAC-v2 row, and a non-finalized-ledger row.
- Installed `inspect` (5 references, 4 active, 1 expired, 1 active
  in-validity key) → reviewed `extend` dry-run under the CONFIGURED
  default TTL (new 0600 plan; 2 eligible; exact exclusion counts) →
  mixed-mode `--execute` + edit-flag refusal (exit 2, fixed stderr, no
  echo) → `--execute` applies EXACTLY ONE value change (the extended
  row lands exactly on created+TTL, monotonic, original creation time
  preserved) → the exact repeat reports `already_applied` with zero
  writes and zero duplicate audits.
- Column-level preservation: ONLY `expires_at` changes, and only on the
  extended row(s); digests, route, model, source linkage, bound ledger
  rows, and the full key row (policy/quotas/material) are unchanged.
- A SECOND reviewed plan with explicit `--include-expired` previews and
  applies ONLY the previously excluded expired reference (exactly
  created+TTL); final inspection: 5 active, 0 expired.
- Every planted private identifier/digest is registered before any
  retained projection. The FINAL fixture behavior converts any
  planting driver failure into a fixed safe assertion with no
  exception chain, so the final bytes retain no raw SQL in evidence.
  Qualification: the FIRST failed artifact
  (`205d-dod11-cfg-1`, predating that boundary) DID retain the planted
  synthetic `item_id_hmac` three times through raw driver parameters
  in its failure text; it was sanitized in place after root review and
  is reported only as a sanitized derivative (see chronology).

### Installed `config show` evidence — EXECUTED PASSED

`test_dod_config_process_inspection` (every invocation a FRESH installed
subprocess, so per-call overrides are process-local by construction):
the EXACT 45-field allowlist with the fixed per-entry restart scope;
the fixed process-local `snapshot_scope`; the exact fixed limitations;
configured-vs-default provenance per entry; explicit overrides through
the subprocess environment (30-day TTL and 311 tokens report
`configured` with the overridden values); the fixed text-mode scope
header; and a generated credential-shaped canary in a numeric setting
yields the fixed `configuration_unavailable` payload, exit 1, NO value
echo, and NO raw traceback.

### JUnit chronology (205-d; overlapping slice runs; never summed)

| Artifact | Cases | Result | Notes |
|---|---|---|---|
| `205d-dod9-1.xml` | 1 | 1 FAIL | Fixture source choice: `k_policy` carries deliberately disabled M2/M3 routes; clone CREATE's enabled-model validation refused it (root-confirmed fixture issue, not a product defect) |
| `205d-dod9-2.xml` | 1 | 1 FAIL | Draft oracle: the pending-channel payload carries no `email_delivery_status` key |
| `205d-dod9-3.xml` (SHA `b8ccb884a96eded49a5d53c9557c608104e2905f12c5d3520977f0fb0facaf31`) | 1 | 1 PASS, 95.610 s | First green mail slice; root accepted as INTERMEDIATE |
| `205d-dod11-cfg-1.xml` (original SHA `0ea3c78ef7a31fc30a80c267b108a99f3143db8b610f11ef625b245fdcfe3cef`) | 2 | 1 FAIL + 1 PASS, 0 skip, 41.195 s | The replay case failed on the `function_call` insertion (the `kind_shape` CHECK requires call/tool fields for that kind); the draft's `note` item kind was a separate invalid row never reached. The config case passed. The raw failure retained the planted synthetic `item_id_hmac` three times through raw driver parameters; after root review the artifact was sanitized IN PLACE (fixed placeholder), re-ordered to valid XML (declaration first, provenance comment after; sanitized SHA `c90319460e2a627fab1ea60b0726fa24d589574276d1ac0794c5dad4be94fc7a`), and is reported as a SANITIZED derivative, not raw JUnit |
| `205d-dod11-cfg-2.xml` (SHA `61261643babefc0b2b554d76fe6de05862845c5d9e881e50b9ffcab37963c7b2`) | 2 | 2 PASS, 68.681 s | Schema-valid replay + strengthened config checks |
| `205d-final-1.xml` (SHA `0785c368733445d8854217ca9672607aeccdefb3ee2e92aebc8cd7259617739c`) | 3 | 3 PASS, 0 skip, 126.858 s | Final D combined run on final bytes: DoD9 92.140 s + DoD11 25.177 s + config 9.200 s |

### Final D-run installation identity (literal)

- Source: `420fb8f6d9377f569d126d08f4c9e4146fc7250b` (git-archive
  pristine copy under the per-run pytest temp tree).
- FRESH wheel `slaif_api_gateway-0.1.0-py3-none-any.whl`, SHA256
  `f2f77aa1b98e887a186ae1fcfcae42bba93e0ae5f77205d931010130eeb3f1c7`
  (rebuilt per run; 432 payload files verified against the pinned
  source — the 205-c wheel `cf7e114f…` must NOT be attributed to D).
- The stale reused venv was rejected by the payload gate and a FRESH
  owned venv was created:
  `/tmp/pytest-of-janezp/pytest-1583/slaif205-field0/venv` (Python
  3.12.15); installed payload 432 files verified against the selected
  wheel.
- Installed console
  `/tmp/pytest-of-janezp/pytest-1583/slaif205-field0/venv/bin/slaif-gateway`,
  executed with neutral cwd and `PYTHONPATH` absent, outside the
  checkout.
- Owned PostgreSQL 16 container
  `9a857a02a0c1d45a13d6042d0ffc2d5992b3e40aab1f3fd9492960e38b41bbdc`
  (loopback port 38111, run-token name/labels, tmpfs) removed in
  teardown; verified absent (`docker ps -a --filter name=slaif205`
  empty after the round).
- Per-run tokens (each with its own fresh wheel/venv): dod9-3
  `694007033c6945be`, dod11-cfg-1 `ad11a1afa9874eab`, dod11-cfg-2
  `3118cfd99f284964`, final `140866e465ea4fe2`.

### Final D-run transcript (run `140866e465ea4fe2`)

37 actual labeled records (25 dod9 + 8 dod11 + 4 dodcfg), 9 negative
exits, persisted 0600 under an owned 0700 per-run directory outside the
checkout (transcript SHA `4ce929a4155b86a59b2a7cb65754fa28b7dad8430d619d5a34d6eb40c1497674`,
identity SHA `2dfe9ba906d54782a905fcd0110e17a8fe38ff1b4a6c383ae2695e3bbaf93c09`);
canary-absence assertions cover both generated keys, all planted replay
identifiers/digests, and the config canary.

### ROOT independent evidence (root runs, not agent runs)

- Root parsed `205d-dod9-3` and the run transcript `694007033c6945be`:
  25 actual labeled records / 7 negative exits, private modes and
  canary shape clean, 432 source/wheel/installed bytes independently
  matching `420fb8f`, all 466 product paths unchanged, exact PG absent;
  two sink acceptances + one definite 550 refusal proven by the source
  assertions.
- Root independently verified the original failed
  `205d-dod11-cfg-1` XML (2 cases: replay 1 FAIL / config 1 PASS,
  0 skip, 41.195 s, SHA `0ea3c78e…`; no full gateway-key shapes or DB
  URL passwords present) and its sanitized form (SHA `c9031946…`).
- Root parsed the config artifact `ad11a1afa9874eab`: 4 actual CLI
  records, the exact 45 allowlist fields, default TTL 31536000 vs
  configured 2592000, rate 100 vs 311, all-45 recreate scopes, fixed
  `configuration_unavailable` / exit 1 / empty stderr / no traceback —
  accepted as INTERMEDIATE actual config evidence.
- The root draft reviews drove the fixture source choice (`k_student`),
  the pre-probe lifecycle inspection, the schema-valid replay rows, the
  explicit `--include-expired` plan, full-row preservation, planted
  ID/digest registration, the safe planting boundary, and the
  strengthened config assertions.

### Limitations (205-d) / carry-forward

- Outcome 10 (gateway-recorded failure investigations): UNPROVEN at the
  205-d point — SUPERSEDED by the 205-e section below, where outcome 10
  was executed and PASSED.
- The final fresh-installation ALL-ELEVEN run and the complete
  all-eleven transcript remain mandatory; this D transcript covers only
  the three D outcomes (37 records) — SUPERSEDED by the 205-f section
  below: the final fresh ALL-13 run was executed (13/13 PASS, 0 skip)
  and the complete 206-record indexed transcript was exported.
- The mail/replay history rows are labeled ORM fixture setup (synthetic
  payloads, constant digests), not operator actions; the SMTP layer is
  an owned loopback synthetic (no real mail); the replay rows do not
  prove replay playback, provider qualification, or authentication.
- No schema, migration, or settings change in 205-d; no merge, no
  release, no production, security, or compliance claim.

## 205-e continuation (outcome 10: actual gateway-recorded diagnostics)

Recorded 2026-10-29. Tests/documentation only; the product remains
frozen at `420fb8f`. This section proves outcome 10: an operator
investigates ACTUAL installed-gateway-recorded compatibility failures
through ACTUAL installed `diagnostics status` / `diagnostics request
show` commands, with request content capture OFF. No diagnostic rows are
planted: every stored record comes from the real middleware observer on
an actual HTTP response of the ACTUAL installed
`slaif_gateway.main:app`.

### Outcome 10 — EXECUTED PASSED

`test_dod10_actual_gateway_recorded_diagnostics` (final run: 1 PASS, 0
skip, 80.531 s; JUnit `205e-dod10-4`, sha256
`94aa0cedf256ed35519fe809a9beeb86168031c2752282f95d0796227021f91c`):

Gateway process (owned loopback, real uvicorn child of the installed
console venv) with explicit owned overrides:
`REQUEST_DIAGNOSTICS_ENABLED=true`, `REQUEST_CAPTURE_ENABLED=false`
(deterministic OFF with an owned capture directory that is asserted
empty afterwards), `REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS=1000` (the
valid maximum, to tolerate cold writes; production default 100 ms
unchanged), and a generated fake value for the actual configured
server-credential env name (`OPENAI_UPSTREAM_API_KEY`, registered before
retention).

Labeled fixture setup (product-equivalent ORM/services in the pytest
process — clearly NOT operator business work, and never a
`request_diagnostics` plant): the seeded `openai` provider config's
`base_url` re-pointed at the owned loopback `ProviderMock`; four labeled
routes + pricing (a plain responses route with function/custom tools
OFF, a responses stream-failure route, and two Codex routes with the
exact numeric `codex_limits` contract 400/64/256 plus
`codex_accounting` pricing metadata); four labeled keys via
`KeyService` (responses key, chat-only endpoint key, Codex-context key
and Codex-replay key carrying the pinned historical 0147 five-gate
policy tuple); and, for the replay case, a genuine service-persisted
reference: a successful FINALIZED ledger (`UsageLedgerRepository.
create_success_record`) plus `CodexReplayService.
persist_validated_references` at now-60 s inside key validity with the
long default lifetime (same deterministic chronology law as native 201
and the 205-d replay case).

Every stored record is correlated by its OWN response
`X-SLAIF-Diagnostic-ID` header (never time/IP/body-length/prefix
guesses), with a bounded labeled CLI retry poll (the observer writes
after the forwarded response; network completion can precede the DB
commit). The six actual HTTP-to-CLI outcomes:

1. **Pre-auth 401** (invalid bearer): recorded
   (`http_rejection`, 401) with NO key identity — `gateway_key_id`
   null, no row claims any labeled key (never guess an owner), zero
   ledger/reservation side effects; the client sent no `X-Request-ID`,
   so the retained client ID is only the middleware-generated
   `req-<uuid>` safe correlation ID.
2. **Authenticated endpoint denial** (chat-only key →
   `/v1/responses`): public `endpoint_not_allowed`, 403; resolved key
   UUID present but NO route facts (endpoint policy rejects before
   route resolution); zero ledger/reservation rows.
3. **Unsupported function-tool capability**: public
   `responses_function_tool_capability_not_supported`; the ACTUALLY
   RESOLVED route identity (route UUID + configured pattern) at the
   trusted resolution boundary; key UUID; no quota/ledger mutation.
4. **Codex context-window rejection**: public
   `responses_codex_context_window_exceeded`, 400; actual decision
   facts from the real decision (`source=responses_route_limits`,
   `context_window_tokens=400`, `estimated_input_tokens` > 336,
   `output_allowance_tokens=64`, exact `limits` dict with the
   configured ceilings) — no inferred byte-size facts, no admission
   mutation.
5. **Expired retained reference**: the genuine service-persisted
   reference first AUTHORIZES a real API replay (200 against the owned
   synthetic provider — synthetic IO, not backend qualification; a
   successful 200 never records; +1 ledger). Then ONLY the selected
   reference's expiry moves to created+30 s (after creation, already
   before the gateway's current time; chronology CHECK preserved), and
   the same request is denied 404 with the deliberately opaque public
   `responses_codex_replay_reference_not_found`: the CLI reports only
   retained safe facts (no route facts — replay verification precedes
   route resolution; key UUID present; no accounting change). No
   missing-vs-expired certainty is invented.
6. **Unsupported provider stream event**: the owned mock emits
   `response.created` then `response.not_a_supported_event`; actual
   wire HTTP 200 PLUS the terminal failure in the stream (the fixed
   failure code exactly once); the CLI record keeps the ACTUAL wire
   status (`stream_failure`, `http_status=200`,
   `source=responses_stream_failure`,
   `error_code=responses_stream_event_not_supported`); accounting
   finalizes exactly one `failed`/success=False ledger row and one
   `released` reservation with zero residual reserved counters.

CLI surface (installed `diagnostics` commands, each an indexed
transcript record): `status --json` (recording enabled, store
available, retained count equals the actual store row count,
`write_timeout_ms=1000` from the CLI process's OWN declared overrides
— the 205-c process-scope law), `status` text (`recording enabled;`),
an absent ID → typed `not_found` (exit 0), two GENUINE failures
sharing one safe client `X-Request-ID` → `ambiguous` with
`match_count=2` and the two gateway diagnostic IDs offered as
candidates, each disambiguating to its exact row; and a TYPED
`unavailable` via a controlled CLI process with a syntactically valid
but unreachable owned-loopback DB URL (status: exit 0 with
`store_available=false`; `request show`: `outcome=unavailable`, exit 1)
— the shared PG was never stopped or mutated to simulate it.

Privacy: content capture OFF with the owned capture directory asserted
empty; distinct generated body/response canaries (plus the generated
fake upstream credential and the raw replay item ID) asserted absent
from the ENTIRE stored `request_diagnostics` table, the CLI outputs,
and the persisted transcript/identity (safe substitutions re-applied at
serialization). The retained safe correlation IDs (diagnostic /
`req-<uuid>` / client IDs) are deliberately retained and are not
canaries.

### JUnit chronology (205-e; overlapping slice runs; never summed)

| Artifact (time) | tests | failures | sha256 (prefix) |
|---|---|---|---|
| `205e-dod10-1` 18:32 | 1 | 1 | 5d798f07 — fixture SQL inspection used named `:k` placeholders against the positional-arg helper (failure before any HTTP) |
| `205e-dod10-2` 18:33 | 1 | 1 | c14df3a5 — draft over-assertion: `client_request_id` retains the middleware-generated `req-<uuid>` safe correlation ID when the client sends none (not null) |
| `205e-dod10-3` 18:36 | 1 | 1 | 5a9b1307 — CLI `status` reports the CLI process's OWN `write_timeout_ms` (100 default) unless the same override is declared in the CLI env (205-c process-scope law) |
| `205e-dod10-4` 18:40 (SHA `94aa0cedf256ed35519fe809a9beeb86168031c2752282f95d0796227021f91c`) | 1 | 0 | 94aa0ced — FINAL DoD10, 1 PASS 0 skip, 80.531 s |

All failures are NEW-test fixture/oracle corrections against the actual
existing law; no product defect was demonstrated and none was patched.

### Installation identity (final DoD10 run; literal)

- Source `420fb8f6d9377f569d126d08f4c9e4146fc7250b`; FRESH wheel SHA256
  `e83dbc0614a4e84fb97c73a14ad4495ff205bf3662582e4260f02f2b1664ef76`
  (432 payload files verified; per-run fresh build, same law as
  205-d).
- FRESH owned venv `/tmp/pytest-of-janezp/pytest-1587/slaif205-field0/venv`
  (Python 3.12.15); installed payload 432 files verified; neutral cwd,
  `PYTHONPATH` absent, outside the checkout.
- Owned PostgreSQL 16 container `9da0cf15b96617b7b85ca9505409be2fb8bb4beabe1b2cc52f36673fc8d7b058`
  (loopback port 44393, run-token name/labels, tmpfs) removed in
  teardown; `docker ps -a --filter name=slaif205` empty after the
  round.

### Gateway lifecycle fixture correction (order 205-e §4)

`_OwnedFieldEnvironment.start_gateway` previously overwrote its single
`self._gateway` handle: in a combined module run DoD5's live gateway
would have leaked. It now (a) accepts optional `env_overrides` merged
over the default process environment (default behavior unchanged) and
(b) stops AND joins the EXACT prior owned process before replacement,
asserting actual termination. The combined DoD5+DoD10 execution that
exercises this path is deferred to the final fresh 13-case run per the
root direction (not repeated here); the cleanup code is in place in
this round's bytes.

### Transcript (run `fe92daf1677148f7`)

15 actual labeled CLI records (all outcome-10 operator actions; 0
unlabeled, 1 negative exit — the typed-unavailable `request show`),
persisted 0600 under an owned 0700 per-run directory outside the
checkout (transcript sha256
`048fb568274d0869bae0af131be5b58fba26be60905f1de2469cd89e145590c0`,
identity sha256
`5ebfeb6be3dc28a0aa582b1a534eafe9c387131b190f726b5924f6f10f4f53bc`).
This is a PARTIAL transcript (outcome 10 only in this focused run);
the final fresh all-eleven-plus run must export every outcome.

### Limitations (205-e) / carry-forward

- The FOCUSED run executes DoD10 alone; the combined DoD5+DoD10 module
  run (exercising the exact prior-gateway stop/replace path and the
  changed HTTP/start_gateway consumer compatibility) is deferred to the
  final fresh 13-case run (identity + all 11 + config + DoD10) —
  SUPERSEDED by the 205-f section below: the single final 13-case run
  executed DoD5 and DoD10 together, actually exercising the
  prior-owned-gateway stop/join/replace path.
- The final fresh-installation ALL-13 run and the complete indexed
  transcript remain mandatory; no all-eleven/all-thirteen claim follows
  from this section — SUPERSEDED by the 205-f section below: the final
  fresh ALL-13 run executed 13/13 PASS, 0 skip, and exported the
  complete 206-record indexed transcript.
- The HTTP stimuli are synthetic (owned loopback gateway + owned
  ProviderMock IO substitution); the replay positive 200 is synthetic
  IO, not real Codex/backend qualification; the fixture keys/routes/
  pricing/reference are labeled ORM/service setup, never operator
  business work and never `request_diagnostics` plants.
- No product, schema, migration, or settings change in 205-e; no
  merge, release, production, security, or compliance claim. The whole
  objective 205 remains PARTIAL until the fresh all-13 run, the
  complete transcript, the full original-brief audit, and the
  final-head/strategic merge gates pass — the first three conditions
  are satisfied by the 205-f section below; the final-head/strategic
  merge gates remain pending (root-owned).

## 205-f continuation (final completion — single complete 13-case run)

Recorded 2026-10-29. Tests/documentation only; the product remains
frozen at `420fb8f`. Single final completion per work order
`oap/orders/205-f-final-cli-completion.md` (same PR #361): one planned
fresh complete installed workflow of the current 13 cases (installation
identity + all eleven outcomes + configuration), the complete indexed
operator transcript, and the single full-scope coverage audit (order
§4). No new infrastructure, no duplicated evidence, no repeated
inventories, no rerun of unchanged suites; accepted 196-204 and
205-a..e component evidence is reused where cited.

### Labeling the old six cases (order §5)

The ACTUAL `run_cli` / `_export_policy` / `_policy_view` invocations of
the historical six cases (DoD0-4, 6) now carry requirement-indexed
labels `dodN-<token>-<NN>` (new: DoD1 12, DoD2 4, DoD3 16, DoD4 22,
DoD6 24; DoD4's 32 run records include pre-existing labels). Every
business assertion, identity gate, and privacy boundary unchanged; the
explicit DoD5/7/8/9/10/11/config labels preserved; no record cleared or
reconstructed. Test-file SHA256
`e2d297dbd4517c57da711f851de9b9b82d7e6a6164f86f0402149f7782f3ffde`
(pre-label E bytes documented in the 205-e section).

### Final 13-case run — EXECUTED PASSED

JUnit `/tmp/slaif205/205f-final-1.xml` SHA256
`aa1dac6adee04598a9c46ec1e281c7705985ad2fe0ef96907259c36fc17db164`:
**13 tests, 0 failures, 0 errors, 0 skipped, 527.933 s, exit 0**
(JUnit authoritative; addopts suppress the console summary). Execution
order / seconds: DoD0 33.601, DoD1 27.550, DoD2 9.086, DoD3 38.192,
DoD4 78.379, DoD6 56.207, DoD5 33.977, DoD7 58.473, DoD8 59.930, DoD9
58.370, DoD11 24.565, config 8.136, DoD10 40.799. DoD5 and DoD10 both
executed in this single run, so the prior-owned-gateway stop/join/
replace path (205-e fixture correction) was ACTUALLY exercised; no
separate DoD5+DoD10 run was performed.

Outcome coverage in the single run: DoD0 installed identity (actual
installation/help probes + `identity.json`; no pretend CLI command);
DoD1 lookup/bounded paging/full-bearer refusal; DoD2 effective policy +
route explanation; DoD3 record operations; DoD4 exact student/beta +
TWO chat clones; DoD5 filtered model-discovery grant; DoD6 rates/lazy/
exact-37 batch; DoD7 two configured completion services; DoD8 stable-
route context/media updates; DoD9 mail delivery + inspection; DoD10
actual gateway-recorded diagnostics; DoD11 replay expiry maintenance;
config process inspection.

### Installation identity (final run; literal)

- Source `420fb8f6d9377f569d126d08f4c9e4146fc7250b` → pristine `git
  archive`; FRESH wheel SHA256
  `4e4c76fbeab1b271cac34d62b082fc2afb9849bcdfad4405699e0ee1be8dff3e`
  (`wheel_reused=false`; 432 payload files verified against the
  pristine source and the installed venv payload).
- FRESH owned venv
  `/tmp/pytest-of-janezp/pytest-1588/slaif205-field0/venv` (Python
  3.12.15); a stale reused-venv candidate was rejected by the payload
  gate (recorded in `artifact_steps`).
- Console `…/venv/bin/slaif-gateway`; neutral outside-checkout cwd,
  `PYTHONPATH` absent, inherited credentials scrubbed.
- Owned PG16 container
  `8de527ee9a74165700fd05c468497c8a9a19eaa10a56a377f29ea595579c1db3`
  (loopback 54487, run-token name/labels, tmpfs) — verified ABSENT
  after the run.

### Persisted operator transcript (run `f222c484261f49de`; COMPLETE)

`/tmp/slaif205/transcripts/f222c484261f49de/` outside the checkout:
directory 0700, `transcript.json` 0600, `identity.json` 0600;
**206 actual CLI records, 0 unlabeled, 33 expected negative exits**
(DoD1 12, DoD2 4, DoD3 16, DoD4 32, DoD5 14, DoD6 24, DoD7 26, DoD8
26, DoD9 25, DoD10 15, DoD11 8, config 4; DoD0 is identity-probe-based
and contributes no CLI records). `transcript.json` SHA256
`ed95d03ce2fc5e3c954945625e9dc5b75f5488e2212f19da99c764bdf37f0405`;
`identity.json` SHA256
`8832d6032498efdc2062a4008850b82f36b37fb52fb8ad56cf80749186592c97`.
Each record retains the actual safe argv/exit/stdout/stderr
projection; known-secret substitution (both full SMTP-generated keys,
all known credential/private replay values, request/response canaries)
is re-applied at final serialization and asserted absent; no
body/header/password/SQL exception dumps; discarded gateway logs are
NOT claimed to have been scanned (log privacy reuses the native 201
proof).

### Full-scope coverage audit (order §4; single table)

| Brief section | What the final delivery must establish | Final-run evidence (this section) | Reused component evidence and honest limitations |
|---|---|---|---|
| §3 existing functionality | Reuse the actually supported owner/institution/cohort CRUD, lifecycle/limits, policy endpoint grants, email, provider/route activation, codex profile/preset/migration, request-capture controls, password-stdin and usage filters; make the supported path discoverable (the 48 reconstructed interventions are not 48 new commands) | All 13 cases drive ONLY real installed `slaif-gateway` commands (transcript argv is the actual argv); `docs/cli-field-administration.md` maps every field group to its implemented command/objective; `docs/cli-reference.md` cross-references it | Reused existing commands plus the implemented actual gaps — not 48 new commands; nothing re-implemented for this qualification |
| §4 typed policy and cloning | Strict versioned create/update/export; provider `None` vs `[]`; omission-preserving updates; lifetime NULL quota = unlimited vs rate NULL override = inherit; unknown/conflicting inputs and unsupported module/hosted authority fail closed; canonical standard-key clone preserves every reviewed dimension + inherited overrides with explicit validity/fingerprints/audit, independent new material/IDs/zero usage/replay ownership, safe retry/post-commit delivery | DoD2 (configured vs effective + route explanation, members/sources, unlimited vs inherited), DoD4 (exact student/beta + TWO independent chat clones into ONE existing cohort: dry-run plans, one secure channel per execute, canonical export parity incl. nontrivial Codex/Responses pin + bounded lazy policy, inherited members, zero copied usage, source unchanged, exact-repeat dedup by source+operation, stale/unknown-field refusals, deny-all provider distinct), DoD3 (create-once + normalized duplicate refusal + owner move preserving omissions) | Native 198 clone/retry/rollback proofs (merged); calibration/template limitations remain explicit; cloning is an explicit typed channel |
| §5 waiting | Dedicated shared audited lazy setter; one request/10 s, concurrency 1, bounded wait/reject/clear; installation ceilings; untouched quota/material/expiry; configuration proof is not a live-Redis admission qualification | DoD6 (rates + lazy: within-ceiling apply, overbound refusal, `--mode reject` and `--clear` transitions from valid waiting states preserving rates/quotas/material/expiry) | Process-local proof on the owned fixture; no Redis exists anywhere in this record; no live-Redis admission claim follows |
| §6 providers/routes | Two disabled completion-service preparations (safe ENV-variable NAMES, custom timeout/zero retries/pricing), explicit separate activation; stable route UUID; deep partial merge vs full replacement; context 400000 plus second-route/media changes; output/key/client-data/unrelated state preserved; stale/mixed-mode safeguards; gateway ceiling distinct from physical model/client context | DoD7 (two providers via actual `providers add` prepared disabled, inspected, separately activated, canonical policy export) + DoD8 (stable-UUID context/media updates via reviewed plans, stale/mixed-mode refusal, second explicit route, unchanged key policy/material/client-module/profile data and pre-existing ledger/replay route linkage, Decimal price equality) | 199-qualified fictional completion provider/profile shapes reused as data; provider IO is the synthetic loopback seam; no named-service branch or credential-auth claim from enabling metadata |
| §7 replay maintenance | Content-free inspect/review/apply; target the ORIGINAL created_at + selected TTL; monotonic/no shortening; expired only explicit; same-key finalized-ledger/HMAC eligibility and ownership/route/model/source preserved; idempotency/audit/caps/atomicity; reuse accepted native 200 scale/concurrency/rollback proof | DoD11 (schema-valid planted rows; configured-default-TTL dry-run; mixed-mode refusal; monotonic apply; already-applied repeat no-op; explicit `--include-expired` second plan; column-level preservation of digest/route/model/source/quotas) | Native 200 scale/concurrency/rollback proofs (merged, in main); no new 20k-row run; no reconstruction/transfer/shortening command exists or is claimed |
| §8 effective/lookup/diagnostics/mail | Configured vs effective/source and actual enabled pairs; safe exact lookup/complete bounded paging; actual correlated failures before admission and after HTTP 200; auth-only key attribution; no guessing/content capture; honest ambiguous/notfound/unavailable and retention limits; mail list/show over pending/sent/failed/expired/sending/ambiguous with exactly-once consumed secret and explicit safe failed retry; enqueue intent != SMTP acceptance != inbox delivery | DoD1 (list/show by UUID/public ID/exact owner email, complete bounded paging, full-bearer lookup refusal without echo), DoD2, DoD9 (pending channel, real send-now with full MIME-decoded key observation, exact repeat refusal, definite 550 refusal + safe explicit retry, planted sending/ambiguous/expired inspected before any unsafe probe), DoD10 (six actual HTTP-to-CLI failures: pre-auth 401, endpoint denial, capability, context window, expired-reference positive-then-opaque-404, HTTP-200 stream failure with failed-ledger/released-reservation accounting; CLI not_found/ambiguous/disambiguation/typed-unavailable; capture OFF + empty owned capture dir + content-free store/transcript canaries) | Synthetic SMTP/provider seams; prepared-recipient guarantee scoped to attempts prepared by this code after upgrade (202-b); historical rows may retain creation-time metadata |
| §9 batch and edits | Reviewed exact-37 scope; active defaults; new/revoked membership/stale refusal; bounded complete selection; shared-service atomic updates/audit and untouched usage; editing existing keys is not a cohort default for future keys; owner/cohort edits preserve omissions and supported institution-on-owner semantics | DoD6 (exact-37 cohort batch: READ-ONLY preview, zero writes/audits, atomic apply with exact 37 audits, stale refusal after new-member creation, bounded complete selection) + DoD3 (owner/cohort partial edits with omission/clear rules and conflict/negative refusals) | 203 (batch) and 204 (record edits + late-audit rollback) proofs, merged; no invented cohort-institution relation; edit scope is per-record, not cohort default |
| §10-11 runtime/common | Safe finite 45-field process-local configuration values/source/restart; invalid-Settings fixed no-echo errors; portable env/file/Compose guidance; API/worker/scheduler recreation only as applicable; proxy 128m example distinct from endpoint/media limits; stable JSON, documented usage/error exits, audit consistency, secret protection | config case (exact 45-field allowlist, configured-vs-default provenance, all-45 recreate scopes, fixed `configuration_unavailable`/exit 1/empty stderr/no traceback) + DoD0 identity; `docs/upgrade-runbook.md` "CLI field-configuration round" section (Alembic 0026 from 201, no 205 schema, runtime recreation for env changes, safe read-only CLI checks, "rollback is not undo" + pre-420 numeric-parser note) | 204 config-inspection proof, merged; `config show` is the CALLING process's snapshot — it does not observe live workers; no `MAX_REQUEST_BODY` invented; shipped nginx 128m example kept distinct from real proxy settings and gateway endpoint/media ceilings; the no-echo numeric fix covers the 17 NEW typed positions (205-b) only — no claim that every legacy usage error is JSON or every legacy key-creation path secret-free |

§12 outcomes: all eleven literal outcomes plus identity/configuration
are established by the single complete 13-case run and the complete
actual indexed transcript above (per-outcome counts in the transcript
subsection; hashes in the run/identity subsections); no Python/SQL
business bypass is presented as operator action — every operator
action is a subprocess of the installed console, and fixture seeding is
clearly labeled product-equivalent ORM/service setup kept separate from
operator actions.

### ROOT independent evidence (credited as root, not agent pytest)

- Root independently verified all 432 files of the FRESH wheel
  `4e4c76fb…` against committed source `420fb8f…`, the current
  application tree, and the installed pytest-1588 venv (exact
  file-set/hash PASS; outside checkout, `PYTHONPATH` absent).
- Root confirmed the final JUnit (13 PASS / 0 fail / 0 error / 0 skip),
  the 206-record / 33-negative-exit / 0-blank-label artifact
  `f222c484261f49de` (0700/0600, canary-clean), and the independent
  absence of the exact owned PG `8de527ee…`. No additional identity
  run, PG suite, or duplicated evidence file was produced in this
  round.

### Superseded carry-forward claims

The 205-a header ("outcomes 9, 10, 11 and the runtime-configuration
evidence are NOT yet executed"; "Objective 205 as a whole remains
PARTIAL"), the 205-b/205-c "full 205 remains PARTIAL" status lines and
state-table rows, the 205-d "the final fresh-installation ALL-ELEVEN
run and the complete all-eleven transcript remain mandatory" bullet,
and the 205-e carry-forward bullets (combined DoD5+DoD10 run; final
fresh ALL-13 run + complete indexed transcript; "whole objective 205
remains PARTIAL until …") are SUPERSEDED by this section (marked
inline above).

### Local verification (final, pre-publication)

Ruff on the touched Python (clean), `git diff --check` (OK),
`scripts/check_documentation.py` (`DOCUMENTATION_CHECK=OK files=132`),
focused OAP governance units (9/9), module collection (13 tests). No
product diff in the IMPL commit (zero changes under `app/`,
`alembic/`, `pyproject.toml`, `Dockerfile`, `.env.example`).

### Limitations (final)

- Every provider/client/SMTP interaction in this record is an owned
  synthetic loopback seam; no real provider/client/mail/Redis/
  production/HPC claim; no performance/scale claim (native 200/201
  proofs reused, not rerun).
- Strategic merge, final-head GitHub checks, and the actual-main
  three-workflow verification remain PENDING (root-owned); no
  release/tag or goal-completion claim — goal completion follows the
  actual-main verification.
- The transcript is the complete indexed run of THIS module (206
  records); it is not a claim about discarded gateway logs or any
  deployment outside this run.
- The historical 205-d synthetic-digest failure redaction remains as
  disclosed in the immutable 205-d report; nothing here rewrites it or
  claims private execution history universally secret-free.
