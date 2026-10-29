# 205-a verification record — installed CLI field administration workflows

**Status: PARTIAL (205-a scope-boundary handoff; 205-b and 205-c
continuations recorded below).** This record documents what was actually
executed through the installed `slaif-gateway` console for work order
`oap/orders/205-a-cli-field-workflow-qualification.md` (unique PR for
objective 205; same-PR 205-b and 205-c continuations on the same PR).
Outcomes 5, 7, 8 are now EXECUTED by the 205-c continuation (final section);
outcomes 9, 10, 11 and the runtime-configuration evidence are NOT yet
executed and remain mandatory for the final 205 PR. The safe persisted
operator transcript/identity export is implemented by 205-c for the NEW C
cases (the complete all-eleven export is deferred to the final fresh run).
Nothing above claims any unexecuted outcome. Objective 205 as a whole
remains PARTIAL.

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
all-eleven run are carried forward to later same-PR suffixes).

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

## 205-c continuation (outcomes 5, 7, 8 + persisted operator transcript)

**Status: bounded round complete for outcomes 5, 7, 8 and the safe
persisted transcript/identity export; full 205 remains PARTIAL**
(outcomes 9, 10, 11, config-show, and the final fresh all-eleven run are
carried forward to later same-PR suffixes). No product byte changed in
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

- Outcome 10 (gateway-recorded failure investigations) remains UNPROVEN
  and mandatory in a later same-PR suffix.
- The final fresh-installation ALL-ELEVEN run and the complete
  all-eleven transcript remain mandatory; this D transcript covers only
  the three D outcomes (37 records).
- The mail/replay history rows are labeled ORM fixture setup (synthetic
  payloads, constant digests), not operator actions; the SMTP layer is
  an owned loopback synthetic (no real mail); the replay rows do not
  prove replay playback, provider qualification, or authentication.
- No schema, migration, or settings change in 205-d; no merge, no
  release, no production, security, or compliance claim.
