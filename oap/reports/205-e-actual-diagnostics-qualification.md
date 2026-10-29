# OAP Coding-Agent Report — 205-e

## Work order
- Identifier: 205-e
- Work-order file: `oap/orders/205-e-actual-diagnostics-qualification.md`
  (committed unchanged in IMPL `0b25707`; sha256
  `3091e35f41653ffce3c72bad3c458852aecfb0f2435a10b259e22d206d43d5f9`)
- `oap/active` pointer: value `205-e` (5 bytes, no trailing newline),
  committed unchanged in IMPL `0b25707`; sha256
  `7ab4ab70ff2826744de8e821b72c6a96458ed48a96a6cdcd1bbff4a3a138444f`
- Numeric objective: 205
- PR mode: CONTINUE_EXISTING_PR (unique PR #361)

## Status
PARTIAL

## Executive summary
Executed the bounded 205-e round on the unique objective-205 PR #361 with
ALL product bytes frozen at `420fb8f6d9377f569d126d08f4c9e4146fc7250b`
(root E baseline `205-e-product-baseline.json` binds D-SELF `9309606`
with 466 product paths, 1736 non-allowed existing paths, and the 2
protected untracked hashes); only the allowed test and documentation paths
changed. Outcome 10 (an operator investigates ACTUAL
installed-gateway-recorded compatibility failures through ACTUAL installed
`diagnostics` commands, with request content capture OFF and NO planted
diagnostic rows) was proven end to end through one real installed
`slaif_gateway.main:app` uvicorn child driving real HTTP, with each failure
correlated by its OWN `X-SLAIF-Diagnostic-ID` header into the installed
`diagnostics` CLI:

1. **Pre-auth 401** from an invalid/no bearer — an actual observer record
   with `http_rejection`, `gateway_key_id` null, and NO row claiming any
   labeled key / owner / route / ledger attribution (zero
   ledger/reservation side effects);
2. **Authenticated endpoint denial** — a chat-only key hitting
   `/v1/responses` returned the expected public `endpoint_not_allowed`
   code and wire status with the resolved key UUID present but NO
   prematurely resolved route facts and zero admission/ledger side effects;
3. **Unsupported function-tool capability** — a real bounded declaration
   rejected through normal policy with
   `responses_function_tool_capability_not_supported`, precise code, the
   trusted actual route facts (route UUID + configured pattern), and no
   quota/ledger mutation (function/local-vs-hosted gates preserved);
4. **Codex context rejection** — `responses_codex_context_window_exceeded`
   from the real decision with `source=responses_route_limits`, context
   ceiling, estimated input above the limit, the configured
   `{default_output, context, max_output}` ceilings, and the output
   allowance; no inferred byte-size facts and no admission mutation;
5. **Expired retained reference** — a GENUINE service-persisted same-key
   replay reference (finalized ledger via
   `UsageLedgerRepository.create_success_record` +
   `CodexReplayService.persist_validated_references`, seeded at now-60s
   within key validity) first produced a positive 200 through owned
   SYNTHETIC provider IO (never recorded; ledger +1), then the fixture
   expired ONLY that selected reference to created+30s and the actual
   gateway denied with the deliberately opaque
   `responses_codex_replay_reference_not_found`, no route facts, no
   accounting change;
6. **Unsupported provider stream event** — mock SSE
   `response.created` then `response.not_a_supported_event` yielded actual
   wire HTTP 200 PLUS a terminal failure (code exactly once); the record
   is `stream_failure` / `http_status=200` /
   `responses_stream_failure` / `responses_stream_event_not_supported`,
   with the ledger finalized `failed`/`success=False` and the reservation
   RELEASED (no residual reserved counters/fence/hold).

The CLI surface was driven through the installed
`diagnostics status --json` / `request show --request-id ... --namespace
gateway --json`: retained count equals the actual row count (with
`write_timeout_ms=1000` reflecting the CLI process's own override); a
text-mode `status`; an absent ID resolving to `not_found` (exit 0, no
historical guessing); two genuine failures sharing one safe client
`X-Request-ID` demonstrating honest `ambiguous` (match_count 2) with both
gateway-ID candidates disambiguating; and a TYPED `unavailable` produced by
a controlled CLI process/env pointing at an unreachable loopback DB URL
(fake credential-bearing value registered), with `status` exit 0
`store_available=false` and `show` exit 1 `outcome=unavailable`.

Privacy: distinct generated body/response canaries, the generated fake
upstream provider key, and the raw replay `item_id` were asserted ABSENT
from the ENTIRE `request_diagnostics` store, all CLI outputs, and the
persisted transcript; the owned capture directory is asserted empty
(content capture OFF throughout).

Final E DoD10 slice on the final test bytes: 1 PASS, 0 failures, 0 errors,
0 skipped, 80.531 s, pytest exit 0.

DEFERRED (honest, per root's latest direction): the order §6 "Final E
qualification" combined **DoD5 + DoD10** execution was NOT run in this
round. The `start_gateway` prior-OWNED-process stop/join replacement path
is in place in the fixture (IMPL), but it is exercised only by a
two-gateway combined run, which is deferred to the single final fresh
all-thirteen-case run (which also carries the full original-brief
audit/docs/upgrades/status and the COMPLETE indexed actual transcript).
The changed HTTP/`start_gateway` consumer compatibility and exact
prior-process cleanup are therefore verified by code review plus the
standalone DoD10 run only — NOT by an actual combined run yet. The fresh
all-13 run, the complete transcript, the full original-brief P0/P1/common
audit, and the final-head/review/merge/actual-main gates all remain. No
merge, no auto-merge.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 361
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/361
- PR state at report time: OPEN (MERGEABLE, CLEAN), no auto-merge
- Base branch: `main` at `5e59a023154bfebc998ef4e0a7089a3151fda0e2`
- Head branch: `oap/205-cli-field-workflow-qualification`
- Starting remote SHA (205-d SELF): `9309606d1f63cdd0a737fdb445b2196d20ee509d`
- Implementation head SHA (IMPL): `0b25707627be4021e6ef5f3970e01535b5d73148`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  - `0b25707627be4021e6ef5f3970e01535b5d73148` — outcome 10 installed
    diagnostics case + minimal HTTP/ProviderMock/GatewayServer/fixture/
    transcript wiring + verification/fixture docs + unchanged 205-e order
    + exact `oap/active` (6 files)

## Changes made
Allowed paths only (order §3):
1. `tests/integration/test_cli_field_installed_workflow.py` —
   (final sha256
   `d70ef1639a016d6af925d83ff7a108cd56941f4313b0ccafd970cfe9c10c8508`)
   - DoD10 `test_dod10_actual_gateway_recorded_diagnostics` (15 labeled
     records, 1 negative exit): starts ONE actual installed
     `slaif_gateway.main:app` uvicorn child with explicit owned overrides
     (`REQUEST_DIAGNOSTICS_ENABLED=true`, `REQUEST_CAPTURE_ENABLED=false`
     with the owned capture directory asserted empty,
     `REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS=1000` the valid maximum; Redis
     and email stay off) plus a generated fake upstream provider key
     (registered before retention); `_plant_dod10_world` re-points the
     provider base URL at the owned loopback mock and creates 4
     clearly-labeled fictional routes/pricing (with `codex_accounting`
     metadata) and 4 `KeyService` keys — labeled fixture setup, NEVER
     diagnostics rows; then drives the six real HTTP→CLI outcomes above,
     each correlated by its OWN `X-SLAIF-Diagnostic-ID` with a bounded
     labeled CLI poll against the actual correlation ID (no arbitrary
     sleep), and asserts every actual code/param/status/identity/route/
     limit against the received HTTP and the actual typed CLI projection;
   - fixture/IO wiring (strictly necessary, minimal, existing seams only):
     `ProviderMock` extended with a `response_canary` and a `/responses`
     dispatch (`_send_responses` exact success JSON,
     `_send_responses_stream`, `_send_responses_stream_failure`) on tiny
     synthetic bodies, chat behavior unchanged, retained log limited to
     path/model/stream/status/count or safe header-check booleans (never
     body/Authorization/key values); `FieldEnvironment.
     gateway_request_with_headers(...)` returning
     `(status, parsed-or-text, lowercased headers)` while the existing
     two-value `gateway_request` stays compatible; `_OwnedFieldEnvironment.
     start_gateway(env_overrides=None)` merging overrides over the CLI env
     AND, on replacement, stopping/joining the EXACT prior owned gateway
     and asserting `proc.poll() is not None` before replacing it (order §4
     CRITICAL fix; combined DoD5+10 execution deferred to the final 13 —
     the replacement path is in place but not yet exercised by an actual
     combined run); the second `ProviderMock`'s full lifetime (seeding +
     gateway startup + body) is wrapped in ONE try/finally so a startup
     failure cannot leak it; the planting boundary raises a fixed-detail
     AssertionError with no raw driver/SQL/subprocess exception chain;
   - constants/helpers: `M10_*`/`U10_*` synthetic IDs, `M10_CHAT`,
     `DIAG_ID_HEADER` (`X-SLAIF-Diagnostic-ID`), `DIAG_CLI_ENV` (the CLI
     process-scope `REQUEST_DIAGNOSTICS_ENABLED`/
     `REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS=1000`), `CODEX_POLICY_0147`,
     `_D10ReplayCandidate`, `_d10_settings`, `_plant_dod10_world`,
     `_seed_dod10_replay_reference`, `_diag_cli_lookup` (bounded labeled
     CLI poll), `_dod10_key_state` (positional `$1` — never `:k`),
     `_dod10_store_contains` (boolean full-store scan);
   - privacy assertions computed as booleans first, then asserted by fixed
     safe labels (canary/fake-key/raw replay `item_id` absence from the
     whole store, CLI outputs, and transcript); no value echo.
2. `tests/fixtures/cli_field_workflow/README.md` — 205-e handoff state
   (DoD10 case, mock-lifetime lifetime, `start_gateway` replacement path,
   combined-DoD5+10 deferral to the final 13).
3. `docs/verification/2026-10-29-cli-field-installed-workflow.md` — new
   205-e section: per-outcome evidence, the JUnit chronology with fixture/
   oracle causes (no product defects), the literal E-run installation
   identity, the 15-record transcript evidence, root evidence, and
   limitations/carry-forward; the 205-d carry-forward line for outcome 10
   marked SUPERSEDED.
4. `docs/verification/README.md` — 205 entry extended with the 205-e
   continuation.
5. `oap/orders/205-e-actual-diagnostics-qualification.md`
   (unchanged strategic bytes) and `oap/active` (exact `205-e`).

No app/service/repository/schema/migration/settings/default/dependency/
lockfile/workflow/adapter/client-profile/product/UI byte changed; no
previous unit/native tests or orders/reports edited; the optional
`tests/fixtures/cli_field_workflow/operator_data.json` was not touched.

## Acceptance-criteria evidence (order §1, eleven outcomes)
Final E DoD10 slice (`205e-dod10-4`, JUnit authoritative; 1 test, 0
failures, 0 errors, 0 skipped, 80.531 s, pytest exit 0; sha256
`94aa0cedf256ed35519fe809a9beeb86168031c2752282f95d0796227021f91c`):

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
| 9 | One-time delivery lifecycle (loopback SMTP) | EXECUTED PASSED | 205-d (unchanged) |
| 10 | Gateway-recorded failure investigations | EXECUTED PASSED (205-e) | `test_dod10_actual_gateway_recorded_diagnostics` (the six HTTP→CLI outcomes + CLI status/show/not-found/ambiguous/unavailable + privacy) |
| 11 | Reviewed replay maintenance | EXECUTED PASSED | 205-d (unchanged) |

The replay outcome 10 case exercises replay as one of the six gateway-
recorded failure investigations (genuine service-persisted reference →
positive → selected-only expiry → opaque 404), distinct from outcome 11's
operator replay-reference expiry maintenance (205-d).

## JUnit evidence (agent pytest; overlapping slice runs never summed)
All runs: `tests/integration/test_cli_field_installed_workflow.py`
(`-k "test_dod10"`), zero skips in every run, UTC 2026-10-29 (JUnit XML
authoritative; repository addopts suppress the console summary). All four
failures are fixture/oracle issues, NO product defects:

| Artifact (time, duration) | tests | failures | sha256 (prefix) |
|---|---|---|---|
| `205e-dod10-1` 18:31:41 (38.280 s) | 1 | 1 | `5d798f07` — fixture SQL: `_dod10_key_state` used a named `:k` parameter against the positional helper before any HTTP |
| `205e-dod10-2` 18:33:15 (42.273 s) | 1 | 1 | `c14df3a5` — over-asserted `client_request_id is None`; the actual field is a middleware-generated `req-<uuid>` safe correlation ID (retained, safe) |
| `205e-dod10-3` 18:35:12 (72.473 s) | 1 | 1 | `5a9b1307` — CLI `status` reports the CLI PROCESS's own `write_timeout_ms` (default 100) unless the same override is declared in the CLI env (process-scope law); added `DIAG_CLI_ENV` |
| `205e-dod10-4` 18:39:01 (80.531 s) | 1 | 0 | `94aa0ced` — FINAL green slice of the final test bytes (SHA `d70ef163…`) |

Failed artifacts contain only fixed fakes (the literal `sk-slaif-`+40-zeros
placeholder shape, `req-<uuid>` correlation shape); no real secrets or full
gateway-key shapes; retained as-is with their original hashes.

## Installation identity (executed; literal final E-run identity)
- Source frozen at `420fb8f6d9377f569d126d08f4c9e4146fc7250b`
  (git-archive pristine copy under the per-run pytest temp tree).
- FINAL E run: FRESH wheel
  `slaif_api_gateway-0.1.0-py3-none-any.whl`, actual SHA256
  `e83dbc0614a4e84fb97c73a14ad4495ff205bf3662582e4260f02f2b1664ef76`,
  payload 432 files verified against the pinned source; the stale reused
  venv was REJECTED by the payload gate ("installed payload differs from
  the selected wheel") and a FRESH owned venv was created
  (`/tmp/pytest-of-janezp/pytest-1587/slaif205-field0/venv`),
  Python 3.12.15; installed payload 432 files verified against the
  selected wheel (`wheel_reused: false`).
- Installed console
  `/tmp/pytest-of-janezp/pytest-1587/slaif205-field0/venv/bin/slaif-gateway`,
  executed with neutral cwd and `PYTHONPATH` absent, outside the checkout.
- Owned PostgreSQL 16 container per run, unique run-token name/labels,
  loopback-only port, tmpfs data dir, ownership inspected BEFORE
  migrations, exact-ID/label cleanup after. Final run container
  `9da0cf15b96617b7b85ca9505409be2fb8bb4beabe1b2cc52f36673fc8d7b058`
  (port 44393) removed in teardown; `docker ps -a --filter name=slaif205`
  is empty after the round (re-verified at report time).
- Wheel SHAs differ per build (wheel metadata); payload identity against
  `420fb8f` is the binding fact. The 205-c wheel `cf7e114f…` and the
  205-d wheel `f2f77aa1…` must NOT be attributed to 205-e (E is
  `e83dbc06…`). No schema, key-policy, or migration of any kind in 205.

## Persisted operator transcript (order §7, executed)
Final run `fe92daf1677148f7` (outside the checkout):
`/tmp/slaif205/transcripts/fe92daf1677148f7/` — directory 0700,
`transcript.json` 0600, `identity.json` 0600; 15 labeled command records,
0 unlabeled, 1 negative exit (the typed `unavailable` `show`); transcript
sha256 `048fb568274d0869bae0af131be5b58fba26be60905f1de2469cd89e145590c0`;
identity sha256
`5ebfeb6be3dc28a0aa582b1a534eafe9c387131b190f726b5924f6f10f4f53bc`.
Records carry the actual requirement-indexed `run_cli` argv boundaries /
output projections / exit codes with meaningful outcome labels plus safe
run/installation identity; canary-absence assertions cover the body/response
canaries, the generated fake upstream provider key, and the raw replay
`item_id`, with safe substitutions re-applied at serialization. This is a
PARTIAL transcript (outcome 10 only); the final fresh all-thirteen-case run
must export every outcome. Source/tests/fixture-setup SQL and ORM plants are
separately explained in the verification record and are never presented as
operator CLI actions.

## ROOT independent evidence (root runs / directions — credited honestly)
- Root E baseline `review-artifacts/cli-feature-round/205-e-product-baseline.json`
  (head `9309606`) independently binds the frozen `420fb8f` tree for the
  round: 466 product paths, 1736 non-allowed existing paths, 2 protected
  untracked hashes.
- Root material review accepted the actual `205e-dod10-4` (1 PASS,
  0 skip, 80.531 s) and independently parsed 15 actual CLI records /
  8 retained rows: all six statuses/codes, the authenticated key +
  trusted-route facts, the HTTP-200 `stream_failure`, the genuine replay
  positive then opaque 404, ambiguity/disambiguation/not-found/
  unavailable, the private artifact modes, the source/wheel identity, and
  exact PG cleanup — all verified; the full mock-lifetime try/finally
  source fix was confirmed.
- HONEST LIMIT: root's contribution this round is the baseline + the
  material review / mock-lifetime cleanup-correction directions. NO
  independent root owned-PG / final-combined receipt artifact exists yet
  for 205-e; none is claimed. The combined DoD5+DoD10 execution and any
  root final-combined review are deferred with the final 13.

## Local verification
- `205e-dod10-4`: 1 PASS, 0 failures, 0 errors, 0 skipped, 80.531 s, pytest exit 0
- `205e-dod10-1`/`2`/`3`: 1 FAIL each (fixture/oracle causes above; no
  product defects; superseded by the final run)
- `python -m ruff check` (touched test file): PASSED (clean, exit 0)
- `git diff --check`: PASSED (clean)
- `python scripts/check_documentation.py`: PASSED
  (`DOCUMENTATION_CHECK=OK files=132`)
- `pytest tests/unit/test_oap_governance.py`: PASSED (9/9)
- Test collection of the module: 13 tests
- Container cleanup after the final run: verified — `docker ps -a
  --filter name=slaif205` empty; no scratch resources used in 205-e
- Generated credentials: random, memory/0600-only, registered before
  retention, substituted/masked in every retained projection; retained
  artifacts carry booleans/hashes and fixed fakes only. No real
  OpenAI/OpenRouter, real client, real SMTP, or Redis.

## GitHub CI / required checks
- Starting head 205-d SELF `9309606`: ALL 10 required checks / 3 workflows
  SUCCESS (re-observed green at this report's refresh: Unit/lint/
  migration-head, PostgreSQL integration, E2E, Playwright, Docker Compose
  smoke, Documentation hygiene, Analyze ×2, CodeQL).
- IMPL `0b25707` / SELF: check state at report drafting NOT CONCLUDED
  (fresh runs triggered by the push); no pass is inferred from pending
  state. The strategic model must verify the `SELF` commit without
  rewriting this report.

## Local setup / dependencies
- Packages/tools/services: per-run owned Python 3.12 venvs (build env +
  fresh installed venv under the per-run pytest temp tree) with the built
  wheel + package dependencies; Docker (owned labeled PostgreSQL 16
  containers only); the installed uvicorn child gateway; the owned
  loopback mock provider. No apt/system mutation.
- `sudo`-level setup performed: none
- Durable setup changes committed/documented: none (owned /tmp artifacts only)

## Documentation
Documentation updated: docs/verification/2026-10-29-cli-field-installed-
workflow.md, docs/verification/README.md, tests/fixtures/cli_field_
workflow/README.md
- The verification record's 205-e section carries the per-outcome
  evidence, the JUnit chronology with fixture/oracle causes, the literal
  final E-run installation identity, the 15-record transcript evidence,
  the honest ROOT-evidence scope, and the carry-forward. The order's
  broader remaining duties (the combined DoD5+DoD10 execution, the fresh
  ALL-THIRTEEN run with the COMPLETE indexed actual transcript, the full
  original-brief P0/P1/common/discoverability/upgrade audit, and the
  final operator-doc consolidation) are NOT complete; they accompany the
  single final same-PR completion order.

## Safety and scope confirmations
- Unrelated files changed: no (only the paths listed under Changes made;
  protected untracked `CODEX-SESSIONS.md` / `codex.sh` preserved uncommitted
  at their order-stated hashes
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda` /
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`;
  ignored catalogs/worktrees untouched)
- Production secrets accessed: no
- Production systems accessed: no
- Required tests skipped/not run: yes — the combined DoD5+DoD10
  execution and the fresh all-thirteen run are not executed yet (see
  Status and Known limitations); no test was skipped within the executed
  runs (0 skips in every JUnit row above)
- Scope deviation: no product, framework, or extra path touched; no
  diagnostic-row planting, no provider-request capture, no permissive
  passthrough, no auth/policy override. The disclosed deviation is the
  DEFERRED combined DoD5+DoD10 run (order §6), explicitly deferred to the
  final 13 per root's latest direction.
- Extra PR created for same numeric objective: NO (single PR #361)
- PR merged by coding agent: NO
- Activated order and `oap/active` edited by coding agent: NO (committed
  byte-unchanged)
- Report-publication commit changes only this report file: yes (verified
  via staged diff before committing)

## Known limitations / blockers
1. The order §6 combined **DoD5 + DoD10** execution was NOT run this
   round (deferred to the final fresh all-thirteen-case run per root's
   latest direction). The `start_gateway` prior-process stop/join
   replacement path is in place in the fixture but has NOT been exercised
   by an actual two-gateway combined run, so the changed
   HTTP/`start_gateway` consumer compatibility and exact prior-process
   cleanup are verified only by code review plus the standalone DoD10 run.
2. The fresh ALL-THIRTEEN module run and the complete all-thirteen
   transcript are NOT executed; the E transcript covers outcome 10 only
   (15 records).
3. The DoD10 replay reference and the world keys/routes/pricing are
   clearly-labeled product-equivalent ORM/service fixture setup (the
   replay reference is a genuine service-persisted one, NOT 205-d's
   synthetic history digests); the provider layer is owned SYNTHETIC loopback
   IO (no real Codex/backend/provider qualification, no authentication
   claim); the positive 200 replay is synthetic IO, never recorded.
4. No independent root owned-PG / final-combined receipt exists yet for
   205-e (see ROOT evidence); root's contribution is the baseline +
   material review / cleanup-correction directions.
5. No schema, key-policy, or migration of any kind in 205; no merge, no
   tag/release, no real provider/client/mail, no Redis, no
   production/security/compliance claim. The whole objective 205 remains
   PARTIAL until the combined DoD5+DoD10 run, the fresh all-thirteen run,
   the complete transcript, the full original-brief audit, and the
   final-head/strategic merge gates pass.

## Recommended strategic follow-up
- Root: verify the `SELF` commit (report-only; first parent = IMPL
  `0b25707`) and its fresh required checks on PR #361.
- One final same-PR completion order: the combined DoD5+DoD10 execution,
  the full original-brief P0/P1/common/discoverability/upgrade audit, the
  consolidated operator documentation, and ONE complete fresh
  all-thirteen-case installed run (identity + all 11 + config) with the
  COMPLETE indexed actual transcript, then the final-head checks, guarded
  strategic merge, and actual-main three-workflow checks.
