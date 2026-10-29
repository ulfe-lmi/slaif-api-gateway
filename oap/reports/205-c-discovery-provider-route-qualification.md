# OAP Coding-Agent Report — 205-c

## Work order
- Identifier: 205-c
- Work-order file: `oap/orders/205-c-discovery-provider-route-qualification.md`
  (committed unchanged in IMPL `4e444ac`; sha256
  `d8efecab5eaf8e980fd675abb33ee18edd0c0898c74bdc1aeeee08d14d1129b3`)
- `oap/active` pointer: value `205-c` (5 bytes, no trailing newline),
  committed unchanged in IMPL `4e444ac`; sha256
  `1f919adba9c4fe983c47620425801a3fecc3b646d2f56fe64443b3a9bc25d0da`
- Numeric objective: 205
- PR mode: CONTINUE_EXISTING_PR (unique PR #361)

## Status
PARTIAL

## Executive summary
Executed the bounded 205-c round on the unique objective-205 PR #361 with
ALL product bytes frozen at `420fb8f` (466 product paths byte-identical per
root baseline `205-c-product-baseline.json`); only the allowed test and
documentation paths changed. Completed the three missing outcome
qualifications through the ACTUAL installed `slaif-gateway` console and the
ACTUAL installed `slaif_gateway.main:app` on the owned loopback against the
owned labeled PostgreSQL 16 container:
(1) outcome 5 — real filtered `GET /v1/models` discovery: denied
OpenAI-shaped before the grant, then exactly the enabled permitted model
after installed `keys policy update`, with meaningful model-allowlist,
provider allow-list (`--allowed-provider` / `--provider-none` /
`--provider-all`) and provider/route disable-enable controls, plus
preserved policy/material/metadata;
(2) outcome 7 — TWO fictional module completion services and TWO
capabilities-file routes prepared disabled via installed
`providers add` / `routes add`, inspected (`show`/`list`, exact
`Decimal == Decimal` pricing semantics), three fixed-message refusals,
then SEPARATE explicit `providers enable` + `routes enable` for BOTH
pairs, and a partial provider update preserving siblings;
(3) outcome 8 — stable-ID context/media route updates via installed
`routes update --dry-run`/`--execute` reviewed plans (context
105000 → 400000; media leaves; a separate plan for the second route at
420000), stale-plan refusal with zero mutation/audit, native mixed-mode
usage refusal, stable UUID/created_at, preserved key policy export +
material, installed completion-service profile data, route-linked
fictional history, and every unrelated route/provider. Also closed the
confirmed evidence gap: the safe persisted 0600/0700 requirement-indexed
operator transcript/identity export (final run: 66 labeled records,
canary-clean). Outcomes 9, 10, 11, the `config show` evidence, the
complete all-eleven transcript, and the final fresh all-eleven run are NOT
executed and remain mandatory; carried forward to later same-PR suffixes.
No merge, no auto-merge.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 361
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/361
- PR state at report time: OPEN (MERGEABLE), no auto-merge
- Base branch: `main` at `5e59a023154bfebc998ef4e0a7089a3151fda0e2`
- Head branch: `oap/205-cli-field-workflow-qualification`
- Starting remote SHA (205-b SELF): `39b6beb9b9f59c5a36ad5457064e6aa127c1e281`
- Implementation head SHA (IMPL): `4e444ac1f77e440f68ec2e5e0e36a48e6792342b`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  - `4e444ac1f77e440f68ec2e5e0e36a48e6792342b` — outcomes 5/7/8 +
    persisted transcript (test file) + fixture/verification docs +
    unchanged 205-c order + exact `oap/active` (6 files)

## Changes made
Allowed paths only (order §3):
1. `tests/integration/test_cli_field_installed_workflow.py` —
   - wired the EXISTING `GatewayServer` minimally (daemon transient log
     drain, fixed safe readiness message only — no raw subprocess output
     in assertions/reports, bounded stop with drainer join);
   - DoD5 `test_dod5_filtered_model_discovery` (14 labeled records):
     installed `keys create --secret-output-file` (generated value
     registered before retention), pre-grant 403 OpenAI-shaped denial,
     canary-bearing `keys show` refusal (fixed no-echo message),
     `keys policy update` with explicit endpoint retention, filtered
     `GET /v1/models` == exactly the enabled permitted model,
     meaningful allow-list/provider/route controls, preservation of
     effective policy sections, canonical export delta limited to
     `allowed_endpoints`, metadata column, and key material/expiry
     (boolean compares);
   - DoD7 `test_dod7_two_configured_completion_services` (26 labeled
     records): both services/routes prepared disabled, inspected,
     separately activated; Decimal-scale pricing oracle; three
     fixed-message refusals; partial update preservation;
   - DoD8 `test_dod8_stable_route_context_media_updates` (26 labeled
     records): two dedicated routes, reviewed plans (dry-run then
     execute), second-route separate plan, stale-plan and mixed-mode
     refusals, stable identifiers and preserved policy/material/profile/
     history/unrelated state;
   - `_plant_dod8_history`: fictional history planted through the
     product-equivalent ORM inside the pytest process (199 reference
     pattern; typed UUID/datetime parameters; constant synthetic
     digests; `pending` ledger) — fixture setup, NOT an operator action.
     This replaced a broken raw string-bound asyncpg SQL draft (see
     failure chronology and resource-deviation sections);
   - `FieldEnvironment.persist_transcript(outcome)`: per-run 0600
     `transcript.json`/`identity.json` in a 0700 per-run directory outside
     the checkout, unique run token, never overwrites another run,
     persistence failure surfaces as an evidence failure while teardown
     always completes.
2. `tests/fixtures/cli_field_workflow/README.md` — 205-c state, wired
   gateway, non-operator fixture setup boundaries, transcript persistence
   contract (preserving the 205-a/205-b content).
3. `docs/verification/2026-10-29-cli-field-installed-workflow.md` — new
   205-c section (identity, per-outcome evidence, transcript evidence,
   13-run JUnit chronology, root evidence, scratch deviation + volume
   inference, carry-forward, limitations) and the A-section correction
   34 public tables = 33 product (including `request_diagnostics`) +
   `alembic_version`; live header updated.
4. `docs/verification/README.md` — 205 entry extended with the 205-c
   continuation.
5. `oap/orders/205-c-discovery-provider-route-qualification.md` (unchanged
   strategic bytes) and `oap/active` (exact `205-c`).

No app/service/repository/schema/migration/settings/default/dependency/
lockfile/workflow/adapter/client-profile/product/UI byte changed; no
previous unit/native tests or orders/reports edited.

## Acceptance-criteria evidence (order section 12, eleven outcomes)
Final combined run (`205c-final-1`, JUnit authoritative; 3 tests, 0
failures, 0 errors, 0 skipped, 184.77 s, pytest exit 0; sha256
`fd8f167eb7ccb856b204bcb5cf3f135e3f4584b12c4cad38b682cbb94a27f9cb`):

| # | Outcome (order title) | Status | Evidence |
|---|-----------------------|--------|----------|
| 1 | Identities / lookup / bounded paging | EXECUTED PASSED | 205-a/B (unchanged, not re-run this round) |
| 2 | Effective policy + route explanation | EXECUTED PASSED | 205-a/B (unchanged) |
| 3 | Record operations | EXECUTED PASSED | 205-a/B (unchanged) |
| 4 | Exact student/beta + two chat clones | EXECUTED PASSED | 205-a/B (unchanged) |
| 5 | Discovery grant + real filtered `GET /v1/models` | EXECUTED PASSED (205-c) | `test_dod5_filtered_model_discovery` |
| 6 | Rates, bounded lazy config, exact-37 batch | EXECUTED PASSED | 205-a/B (unchanged) |
| 7 | Two configured completion services + routes | EXECUTED PASSED (205-c) | `test_dod7_two_configured_completion_services` |
| 8 | Explicit activation + stable route edit | EXECUTED PASSED (205-c) | `test_dod8_stable_route_context_media_updates` |
| 9 | One-time delivery lifecycle (loopback SMTP) | UNPROVEN | not executed (carried forward) |
| 10 | Gateway-recorded failure investigations | UNPROVEN | not executed (carried forward) |
| 11 | Reviewed replay maintenance | UNPROVEN | not executed (carried forward) |

Additional order requirement — `config show --json`/text snapshot +
invalid-Settings no-echo probe: NOT EXECUTED in this module (carried
forward).

## JUnit evidence (agent pytest; overlapping slice runs never summed)
All runs: `tests/integration/test_cli_field_installed_workflow.py`, zero
skips in every run, UTC 2026-10-29 (JUnit XML authoritative; repository
addopts suppress the console summary):

| Artifact (time) | tests | failures | sha256 (prefix) |
|---|---|---|---|
| `205c-dod5-1` 15:41 | 1 | 1 | 7b7e9018 — draft `GatewayServer` not wired (`start_gateway` AttributeError) |
| `205c-dod5-2` 15:47 | 1 | 0 | 01b85d54 — green before provider controls added |
| `205c-dod5-3` 15:55 | 1 | 0 | e277aa3c — final DoD5 (14 labels; root-verified) |
| `205c-dod7-1` 15:57 | 1 | 1 | 3b36a7d0 — money oracle: `Numeric(18,9)` scale; corrected to `Decimal == Decimal` |
| `205c-dod7-2` 15:59 | 1 | 0 | 12df8ebc — final DoD7 (26 labels) |
| `205c-dod8-1` 16:00 | 1 | 1 | 7bd52dd0 — mixed-mode oracle: native Typer usage error (exit 2, fixed stderr, no JSON) |
| `205c-dod8-2` 16:02 | 1 | 0 | 93095a4d — DoD8 v1 (pre extension) |
| `205c-dod8-3` 16:10 | 1 | 1 | ea9e11ef — extended DoD8: raw string-bound asyncpg SQL fixture defect |
| `205c-dod8-4` 16:12 | 1 | 1 | 44ade823 — same fixture defect, variant SQL |
| `205c-dod8-5` 16:13 | 1 | 1 | 65e49cf2 — same fixture defect, `make_interval` variant |
| `205c-dod8-6` 16:25 | 1 | 0 | 7e1b97bc — extended DoD8 with ORM planting (root-verified) |
| `205c-combined-1` 16:05 | 3 | 0 | cae0c207 — first combined run on PRE-EXTENSION bytes (weaker outcome 8; superseded) |
| `205c-final-1` 16:29 | 3 | 0 | fd8f167e — FINAL combined run of final test bytes + transcript |

The intermediate failures are NEW-test-file fixture/oracle corrections
(gateway wiring; Decimal-scale money oracle; native-usage-error oracle;
raw-SQL fixture binding). They are not product failures and are not summed
as unique cases.

## Installation identity (executed)
- Source frozen at `420fb8f6d9377f569d126d08f4c9e4146fc7250b` (pinned
  shallow-safely in the owned pristine archive).
- Final combined run: FRESH wheel
  `slaif_api_gateway-0.1.0-py3-none-any.whl`, actual selected SHA256
  `cf7e114f1ebdcb8d8f22cccd4f106c08bcb061268fac14dac67eebf97c0db9c1`,
  built from that exact pinned source; 432 wheel payload files verified;
  FRESH owned venv under the pytest temp tree
  (`/tmp/pytest-of-janezp/pytest-1575/slaif205-field0/venv`), Python
  3.12.15, installed console `.../venv/bin/slaif-gateway`, outside the
  checkout, `PYTHONPATH` absent; installed payload 432 files verified.
- Owned PostgreSQL 16 container, unique per run: run-token name/labels,
  loopback-only port, 512 MiB tmpfs data dir, ownership/labels inspected
  BEFORE migrations, exact-ID/label cleanup after. Final run container
  `b6259642ed72af21eec139bd7d941e3265b702a9ae29c41a0c5dabcea93c6c13`
  (port 55845) removed in teardown; no `slaif205*` container remains.
- No schema, key-policy, or migration of any kind in 205; objective 196–205
  upgrade includes the 201 migration 0026 (34 public tables at head).

## Persisted operator transcript (order §7, executed)
Final run `29b67e22ffd54baf` (outside the checkout):
`/tmp/slaif205/transcripts/29b67e22ffd54baf/` — directory 0700,
`transcript.json` 0600, `identity.json` 0600; 66 records (14 DoD5 + 26
DoD7 + 26 DoD8), 0 unlabeled; transcript sha256
`549a089680d10ddbae597ca1c93639057c99cd8abcfa31c714c843bb45d67fde`;
identity sha256
`94a2aa1411298b780b387e0a6a4063dbbc7660f293e1dc12dae72b6c35c09021`.
Records carry the actual requirement-indexed `run_cli` argv boundaries /
output projections / exit codes with meaningful outcome labels plus safe
run/installation identity; the refused-bearer record shows argv masking
(`<REFUSED-BEARER-SHAPE>`); canary checks assert every generated secret
absent from the persisted files. This is a PARTIAL transcript (NEW C
cases only); the final fresh all-eleven run must export every outcome.
Source/tests/fixture-setup SQL and ORM plants are separately explained in
the verification record and never presented as operator CLI actions.

## Resource deviation: unlabeled scratch container + volume (corrected, disclosed)
While investigating the `205c-dod8-3/4/5` fixture SQL defect, a throwaway
PostgreSQL 16 container `slaif205-scratch` (exact ID
`f4e53597cc085cedeb9e163dcb2e6666314d73513434d6d74c4292da251bc8f5`) was
temporarily created on a fixed loopback port WITHOUT the required
run/owner labels and tmpfs data dir — a deviation from the owned
unique-run/labeled/tmpfs setup contract. Root detected it by
metadata-only inspection.

- Container: the exact container was stopped and removed (ONLY that
  container; unrelated containers untouched); no Config.Env/password
  content retained in any artifact.
- Volume ownership: an INFERENCE, not an independently verified
  mount/event mapping (no docker event record or prior-mount record for
  the volume exists; the root bounded volume-event query returned no
  matching records). Basis: (a) the logged creation command (agent
  session record, 2026-10-29T16:14:34.804Z: `docker run -d --name
  slaif205-scratch -e POSTGRES_USER=u -e POSTGRES_PASSWORD=<REDACTED> -e
  POSTGRES_DB=d -p 127.0.0.1:55432:5432 postgres:16` — no tmpfs, no named
  volume, no `--rm`) combined with the data VOLUME declared by the
  `postgres:16` image, under which the engine necessarily created exactly
  one anonymous volume at container creation (16:14:34Z); (b) of all 120
  host volumes, exactly ONE
  (`f95b26cf1c21e0b7b38fb6b72fcf17ea35e243d8c1c47bb6177f77f283497080`)
  was created at that exact second — newest volume on the host, none
  created in the 16:00–17:00 window; (c) it carries the
  `com.docker.volume.anonymous` label and had no mount points after
  container removal, so no other candidate exists.
- Volume cleanup: that exact volume was removed (no `volume prune`, no
  timestamp-only guesses, no unrelated deletion); host volume count
  120 → 119; remaining volumes untouched. Limit: the ownership
  determination rests on the creation command + declared image VOLUME +
  unique anonymous CreatedAt — an inference with a single candidate, not
  a direct provenance record.
- The fixture SQL was NOT "fixed" by changing product/schema: the final
  DoD8 history planting uses the existing 199 ORM reference pattern
  inside the owned fixture; no scratch container or volume is used by the
  final test bytes.

## ROOT independent evidence (root runs — credited as root, not agent pytest)
- `205-c-product-baseline.json` — product/preserved-path baseline (466
  product paths, 1732 non-allowed existing paths, protected untracked
  hashes) binding the frozen `420fb8f` tree for the round.
- `205-c-final-combined-root-review.json` — root re-verified the final
  combined JUnit (3 PASS, 0 skip, 184.77 s; sha256
  `fd8f167eb7ccb856b204bcb5cf3f135e3f4584b12c4cad38b682cbb94a27f9cb`)
  with the actual cumulative 66-record transcript (14 + 26 + 26, all
  indexed, 0700/0600 private), and independently byte-verified ALL 432
  source/wheel/installed application files at `420fb8f` after the run —
  INCLUDING the installed client-compatibility JSON (the client-data
  boundary) — against actual wheel SHA256
  `cf7e114f1ebdcb8d8f22cccd4f106c08bcb061268fac14dac67eebf97c0db9c1`;
  exact owned PG container absent after teardown.
- Expanded DoD8 recheck (root): 1 PASS 0 skip; 26 actual records, 0 blank
  labels; two route UUIDs at 400000/420000; stale + mixed refusals;
  proper PG cleanup.

## Local verification
- `205c-final-1`: 3 PASS, 0 failures, 0 errors, 0 skipped, 184.77 s, pytest exit 0
- `205c-dod8-6`: 1 PASS, 0 skip (extended DoD8 slice on final bytes)
- `python -m ruff check` (touched test file): PASSED (clean)
- `git diff --check`: PASSED (clean)
- `python scripts/check_documentation.py`: PASSED
  (`DOCUMENTATION_CHECK=OK files=132`)
- Container cleanup after the final run: verified — no `slaif205*`
  container remains; scratch container + inferred scratch volume removed
  (sections above)
- Generated credentials: random, memory/0600-only, registered before
  retention, substituted/masked in every retained projection; retained
  artifacts carry booleans/hashes only. No real OpenAI/OpenRouter, real
  client, real SMTP, or Redis.

## GitHub CI / required checks
- B SELF `39b6beb` (starting head): ALL 10 required checks / 3 workflows
  SUCCESS (root receipt `205-b-final-SELF-checks.json`, CI run
  40898756651; re-observed green at this report's refresh).
- IMPL `4e444ac` / SELF: check state at report drafting NOT CONCLUDED
  (fresh runs triggered by the push); no pass is inferred from pending
  state. The report-only SELF commit may trigger additional checks; the
  strategic model must verify the `SELF` commit without rewriting this
  report.

## Local setup / dependencies
- Packages/tools/services: owned Python 3.12 venvs (build venv + fresh
  installed venv under the pytest temp tree) with the built wheel +
  package dependencies; Docker (owned labeled PostgreSQL 16 containers
  only); no apt/system mutation
- `sudo`-level setup performed: none
- Durable setup changes committed/documented: none (owned /tmp artifacts
  only)

## Documentation
Documentation updated: docs/verification/2026-10-29-cli-field-installed-workflow.md, docs/verification/README.md, tests/fixtures/cli_field_workflow/README.md
- The verification record's 205-c section carries the per-outcome
  evidence, identity facts, transcript persistence contract, 13-run
  JUnit chronology, root evidence, the scratch-container/volume
  deviation with its inference basis and limits, the carry-forward table,
  and the A-section 34-table correction. The order's broader remaining
  duties (outcomes 9-11, config-show evidence, portable
  environment/Compose-recreate/proxy guidance, P0/P1 audit, stale
  202-204 doc corrections, final fresh all-eleven with complete
  transcript) are NOT complete; they accompany later same-PR
  continuations.

## Safety and scope confirmations
- Unrelated files changed: no (only the paths listed under Changes made;
  protected untracked `CODEX-SESSIONS.md` / `codex.sh` preserved
  uncommitted at their order-stated hashes
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda` /
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`;
  ignored catalogs/worktrees untouched)
- Production secrets accessed: no
- Production systems accessed: no
- Required tests skipped/not run: yes — outcomes 9, 10, 11 and the
  config-show evidence are not executed yet (see Status and Known
  limitations); no test was skipped within the executed runs (0 skips in
  every JUnit row above)
- Scope deviation: yes — bounded and disclosed: an unlabeled non-tmpfs
  scratch container was temporarily created during fixture-SQL debugging
  and violates the owned setup contract; it and its inferred anonymous
  volume were removed, and the final test bytes use no scratch resources
  (see Resource deviation section). No product, framework, or extra path
  was touched.
- Extra PR created for same numeric objective: NO (single PR #361)
- PR merged by coding agent: NO
- Activated order and `oap/active` edited by coding agent: NO (committed
  byte-unchanged)
- Report-publication commit changes only this report file: yes (verified
  via staged diff before committing)

## Known limitations / blockers
1. Outcomes 9, 10, 11 and the runtime-configuration (`config show`)
   evidence are UNPROVEN — not executed; the one-time delivery,
   diagnostics, and replay workflows remain later same-PR work.
2. The persisted transcript covers the NEW C cases only (66 records);
   NO all-eleven transcript exists. The final fresh-installation
   all-eleven module run is NOT executed and must export every outcome.
3. The C evidence is installed-CLI + owned-gateway + owned-PG proof with
   synthetic HTTP/provider/SMTP IO and fictional historical setup; it is
   not real-provider/client/backend qualification, not measured
   performance, and not a compatibility/certification claim.
4. The DoD8 history linkage is fixture setup via product-equivalent ORM
   (pending ledger), never an operator action or replay-eligibility
   proof; `_profile_data_fingerprint` covers completion-service server
   data only (installed client data covered by the root 432 comparison).
5. No schema, key-policy, or migration of any kind in 205; no merge, no
   tag/release, no real provider/client/mail, no Redis.

## Recommended strategic follow-up
- Root: verify the `SELF` commit (report-only; first parent = IMPL
  `4e444ac`) and its fresh required checks on PR #361.
- Next same-PR continuation: outcomes 9 (one-time delivery lifecycle on
  the armed loopback SMTP), 10 (gateway-recorded failure diagnostics via
  installed `diagnostics request show`), 11 (reviewed replay
  maintenance), the `config show` valid/invalid-Settings evidence, then
  the final fresh-installation all-eleven run with the complete
  requirement-indexed transcript, the portable environment /
  Compose-recreate / proxy guidance, the whole P0/P1/common/
  discoverability audit, and stale 202-204 live-doc corrections — after
  which final-head checks, guarded strategic merge, and actual-main
  three-workflow checks remain.
