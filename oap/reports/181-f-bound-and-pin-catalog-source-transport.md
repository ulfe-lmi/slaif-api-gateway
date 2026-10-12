# OAP Execution Report — 181-f: Bound and pin catalog source transport

## Identity

- Objective: 181 — authoritative catalog collection (SAME PR 318, branch `oap/181-authoritative-catalog-collection`)
- Round: **181-f** (AMEND_EXISTING_PR), selected by `oap/active` = `181-f`
- Order: `oap/orders/181-f-bound-and-pin-catalog-source-transport.md` (strategic-authored; committed byte-unchanged in the implementation commit; file sha256 `3ce0853b6da9edaccfca0f5ba2984370bccf946b8352e24aa64377ac69b3e99e`)
- `oap/active` exact bytes (verified with `od -c` before publication): `1 8 1 - f` — 5 bytes, no newline; sha256 `534f3d0428f0c153672dea38d4b175ec9b4c3559f8c1f92e2f61d0e73c4953e9`; committed byte-unchanged
- Starting PR/local head (181-e immutable report head, pre-round): `b0cdb0019c31a744d464c2502b7f98ffb5d7b839`; its first parent `2913321669d4c51251aaa5079fe6a3d5e1515462` is the 181-e implementation
- Implementation head: `bfc59921e3f50b2d050369c8aa0a8bedb0185808` (8 files, +1713/−217)
- Report publication commit: SELF (first parent = implementation head `bfc59921e3f50b2d050369c8aa0a8bedb0185808`)
- Canonical `main`: `6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf` (unchanged)
- PR 318 at report time: OPEN, MERGEABLE, head `bfc59921e3f50b2d050369c8aa0a8bedb0185808` (verified via `gh pr view 318 --json headRefOid` after push), `autoMergeRequest: null` (preserved; no merge, no auto-merge)
- Strategic inputs (read-only): `workorders/OBJECTIVE-181-TRANSPORT-CAPTURE-ASSESSMENT.md`, `review-artifacts/181-c-review/transport_probe.py` + `transport-results.json`, `review-artifacts/181-transport-supplement/probe.py` + `results.json`, `workorders/OBJECTIVE-181-D-STRATEGIC-REVIEW.md`, `workorders/OBJECTIVE-181-E-STRATEGIC-REVIEW.md`, `workorders/CATALOG-REFRESH-IMPLEMENTATION-MANDATE.md`; plus the in-round strategic clarification that AP-F5 must qualify on the LITERAL implementation head (pre-commit smoke labeled as pre-commit, bounded head smoke re-run and retained) and that the green focused suite must not be re-executed merely to recover its count (saved output + collect-only used).

## Status

**COMPLETE** — F1 (one acquisition-owned budget/cache), F2 (connection binding, exact URL families, no implicit proxies), and F3 (identity-only transfer bound before expansion) are implemented, tested against the actual connection primitive, and verified; the bounded AP-F5 production-transport smoke was executed on the literal implementation head; GitHub CI at the implementation head is 10/10 SUCCESS. Objective 181 remains NOT closed: runner-measured acquisition versus supplied/replayed data and exact installed tooling identity remain REQUIRED in a later same-PR continuation.

## Executive summary

The independently reproduced transport gaps (pre-fix `sources.py` sha256 `55015631a6a85f0da0ad3e29382e28a66d687cf9adf9aca829980672bc380482`, unchanged through 181-e) are closed in one bounded transport delta:

1. **F1 — one real finite budget.** A collection-owned `AcquisitionContext` (128 attempts / 32 MiB / **120 s monotonic deadline** / cross-phase URL success-OR-failure cache) is created before acquisition starts and threaded through the catalog, model-docs, and ECB phases, every redirect and retry. Every real HTTP attempt (initial, redirect hop, 429 wait, 5xx/transport retry) and every wire body byte (successful, failed, interrupted, overflow) is charged with no refunds; exhaustion fails closed as deterministic `collection_budget_exhausted` / `acquisition_deadline_exceeded` → BLOCKED.
2. **F2 — bind the actual connection.** A new `source_transport.py` (no new dependency) installs `VettedNetworkBackend`/`VettedHTTPTransport`: the connect-time DNS answer set is re-resolved and re-vetted on **every new TCP connection** and the connection is bound only to vetted PUBLIC NUMERIC destinations; mixed public/non-public answer sets are rejected; the original approved hostname, Host, SNI, and verified certificate policy (certifi bundle, `check_hostname=True`, `CERT_REQUIRED`) are preserved; `trust_env=False` disables environment proxies; UDS is forbidden. URL admission is reduced to exact registry path families with no arbitrary same-host path/query/fragment/credential/port expansion.
3. **F3 — identity before expansion.** The production client sends `Accept-Encoding: identity`; any non-identity `Content-Encoding` is refused **before** any decoding/expansion (no decoder is ever constructed on the acquisition path); bodies are read as raw wire bytes with per-read budget charging; `Content-Length` is never trusted.

The 359-test focused 10-file suite passes with a zero-uninjected-default-DNS audit; the bounded AP-F5 smoke ran through this exact production transport against the official OpenAI/OpenRouter/ECB endpoints (15 real HTTP attempts at the implementation head, all 200, identity honored) and produced a sealed READY run that verifies `valid: true` offline with HTTP/DNS/socket forbidden.

Objective 181 remains NOT closed by this round: actual collection versus intact replay (runner-measured acquisition versus supplied/replayed data) and exact installed tooling identity remain REQUIRED in a later same-PR continuation; 182/183/184 unchanged.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 318
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/318
- PR state at report time: OPEN
- Base branch: `main` (`6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf`)
- Head branch: `oap/181-authoritative-catalog-collection`
- Starting remote SHA: `b0cdb0019c31a744d464c2502b7f98ffb5d7b839`
- Implementation head SHA: `bfc59921e3f50b2d050369c8aa0a8bedb0185808`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `bfc59921e3f50b2d050369c8aa0a8bedb0185808` (single commit; push `b0cdb00..bfc5992`)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes (PR 318)
- Merge performed: NO

## Confirmed pre-fix failures (from the order; reproduced by strategic probes)

- Aggregate request budget of 2 permitted 6 actual HTTP attempts (retries counted as one).
- Two phases with 1 request/256 bytes each permitted 2 requests/400 bytes in aggregate (phase-local resets).
- Failed body reads consumed 200 bytes on each of 3 retries, then another 200-byte successful request: 800 actual mock bytes under a 256 aggregate limit, only 200 counted.
- gzip 8,175 wire bytes expanded to 8 MiB with a traced 25,218,022-byte allocation BEFORE a 256-byte cap reported `body_too_large` (`iter_bytes` chunked AFTER decoding).
- A synthetic `HTTPS_PROXY` enabled an implicit proxy pool (no traffic was sent).
- Mixed public+loopback DNS answers and arbitrary non-document path/query on an approved host passed the current guards; the DNS guard and actual httpx resolution were separate (a preflight-only vetting was not a fix).
- No private service was contacted by the probes; the malformed-port redirect already returned a safe `transport_error` (the withdrawn uncaught-exception claim was not revived).

## Changes made

1. `app/slaif_gateway/services/catalog_refresh/sources.py` (rewritten acquisition core, 535 changed lines): exact path-family constants + `validate_source_url` (https only, no credentials, exact approved host, port None/443, non-empty path, **no query**, **no fragment**, exact path family, source-kind match, OpenAI model-page slug pattern); `guard_public_destination`; `AcquisitionContext` (monotonic deadline, attempt/byte budgets, cross-phase identity-revalidated cache) with `new_acquisition_context` (defaults: 120 s, 128 attempts, 32 MiB); `fetch_source` (reserve-before-attempt, per-attempt URL revalidation, ≤3 redirects revalidated per hop, finite `Retry-After` ≤30 s 429 waits that consume the deadline, ≤3 total-attempt 5xx bound, encoding gate before any read, raw bounded streaming reads with per-read deadline checks and pre-cap byte charging); `fetch_sources` (per-spec deadline check → cache lookup (success OR failure reuse, zero budget) → pre-reservation → fetch → cache store; the previous per-call `seen_urls` reset path is removed); `new_client` (production client now sends `Accept: */*` + `Accept-Encoding: identity`, `follow_redirects=False`, `trust_env=False`, connect 10 s / read 30 s / write 10 s / pool 10 s timeouts, and the vetted transport).
2. `app/slaif_gateway/services/catalog_refresh/source_transport.py` (NEW, 179 lines): `vet_public_destination` (resolve → all addresses public; all non-public → `destination_not_public`; **mixed** → `destination_mixed_or_not_public`; failure/empty → `dns_resolution_failed`); `VettedNetworkBackend` (re-resolves + re-vets the connect-time answer set on every new TCP connection and connects only to vetted public numeric destinations in order; `TCP_NODELAY`; `destination_connect_failed` when all fail; UDS → `uds_forbidden`); `VettedHTTPTransport` (`trust_env=False`, certifi default bundle with `check_hostname=True`/`CERT_REQUIRED`, pool swapped for the vetted backend, stdlib/httpx-only).
3. `app/slaif_gateway/services/catalog_refresh/collection.py` (budget/client lifecycle only, 24 changed lines): `collect_bundle` accepts an optional caller-supplied `acquisition` context (caller JSON may not own the context; CLI path is byte-unchanged and uses the default), creates the context before acquisition starts, and all three fetch call sites (phase-1 catalog, model pages, ECB) pass the SAME context — no phase can reset any allowance.
4. `tests/unit/test_catalog_refresh_sources.py` (rewritten, 45 tests): AP-F1 budget/deadline/cache suite including real slow-DNS, slow-drip, and 429-sleep negatives; AP-F2 connection-binding suite that monkeypatches the ACTUAL `socket.create_connection` primitive and the TLS `wrap_socket` call (vetted numeric binds, SNI/`check_hostname`/`CERT_REQUIRED`, mixed DNS, rebinding, `HTTPS_PROXY` inert under `trust_env=False`, spec-cache reuse with no second connection, UDS forbidden); AP-F3 encoding suite (real gzip 8 MiB-expansion wire refused before the stream is touched, `br` refused, misleading `Content-Length`, interrupted-stream byte charging).
5. `tests/unit/test_catalog_refresh_collection.py` (+4 tests): cross-phase budget-reset regression (3-attempt context exhausted at the page phase), cross-phase byte-budget exhaustion, expired-context blocks before any fetch, and CLI deadline exhaustion publishing a BLOCKED run (exit 20) with the safe code in both the JSON summary and `validation.json`.
6. `docs/catalog-refresh.md` (96 changed lines): registry table now states the exact URL path families; guarantees updated (no query/fragment, mixed-DNS refusal, identity-only encoding, 429 waits consume the deadline); new subsection "Transport and budget guarantees (181-f)" documenting the one-whole-invocation budget semantics, the 120 s deadline with the honest in-flight-operation limit, the cross-phase cache with identity revalidation, and the vetted connection binding.
7. Committed the strategic-authored 181-f order and the exact 5-byte `oap/active` (`181-f`) unchanged with the implementation.

`app/slaif_gateway/cli/catalog_refresh.py` was NOT modified (its `new_client()`/`collect_bundle(...)` call sites work unchanged); `docs/cli-reference.md` and `admin/catalog-refresh/README.md` needed no transport wording (verified by inspection); `tests/unit/test_cli_catalog_refresh.py` unchanged (28 tests re-verified green).

## Files changed

Implementation commit `bfc59921e3f50b2d050369c8aa0a8bedb0185808` only (8 files, +1713/−217):

- `app/slaif_gateway/services/catalog_refresh/sources.py` (535 ±)
- `app/slaif_gateway/services/catalog_refresh/source_transport.py` (179 +, new)
- `app/slaif_gateway/services/catalog_refresh/collection.py` (24 ±)
- `tests/unit/test_catalog_refresh_sources.py` (815 ±)
- `tests/unit/test_catalog_refresh_collection.py` (78 +)
- `docs/catalog-refresh.md` (96 ±)
- `oap/orders/181-f-bound-and-pin-catalog-source-transport.md` (201 +, strategic-authored, committed unchanged)
- `oap/active` (exact strategic bytes `181-f`, committed unchanged)

No other tracked path changed (verified by `git diff --stat` between the starting head and the implementation head). Safe failure-code list of the acquisition subsystem (all deterministic, no raw exception text ever exposed): `url_not_https`, `url_credentials`, `url_host_not_approved`, `url_nondefault_port`, `url_missing_path`, `url_query_forbidden`, `url_fragment_forbidden`, `url_path_not_approved`, `url_path_kind_mismatch`, `model_page_slug_invalid`, `unknown_provider`, `dns_resolution_failed`, `destination_not_public`, `destination_mixed_or_not_public`, `destination_connect_failed`, `uds_forbidden`, `unexpected_encoding`, `header_too_large`, `body_too_large`, `http_<status>` (dynamic), `http_5xx`, `rate_limited`, `transport_error`, `redirect_missing_location`, `redirect_unbounded`, `collection_budget_exhausted`, `acquisition_deadline_exceeded`, `duplicate_url_planned`.

## Acceptance-criteria evidence

### AP-F1 — one whole-invocation attempt/byte/deadline budget and cross-phase cache
- Result: PASS.
- Evidence (design, verified in code): the context is created in `collect_bundle` before acquisition (only a non-None explicitly injected context is accepted — no caller JSON owns it) and passed by the same object to all three fetch call sites (phase 1, model pages, ECB). `reserve_attempt()` checks the deadline and attempt budget BEFORE each real request; `charge_body_bytes` runs on every raw read BEFORE the per-source cap check, so failed, interrupted, and overflow bytes are charged with no refunds. The cross-phase cache key is the full spec identity (provider/source_kind/model/max_bytes/required) plus URL-family revalidation; a mismatch raises `duplicate_url_planned`; a hit reuses the identical captured result object with zero further budget.
- Evidence (tests, named): cross-call attempt/byte budgets survive a second `fetch_sources` call (no reset); a failed read consumes budget and blocks the next spec; attempts are counted per REAL HTTP request (one redirect + one 5xx + success = 4 charged); cross-phase cache reuse of BOTH success and failure (identical result object, zero additional attempts/bytes); a real slow-DNS negative (0.35 s injected sleeps, 0.6 s deadline → wall < 2 s, exactly 2 HTTP attempts + 2 DNS resolutions, no later activity after expiry); a slow-drip mid-body negative (1 KiB per 0.2 s, 0.6 s deadline → 2–5 KiB charged, no completion); a 429 retry-sleep bounded by the remaining deadline (wall < 1.5 s, exactly 1 HTTP attempt).
- Honest limit (documented in `docs/catalog-refresh.md`): the deadline is checked before every new attempt, DNS resolution, raw read, and 429 sleep, but ONE in-flight operation already started may complete slightly past expiry; that in-flight bound is the client's 10 s connect / 30 s read timeouts.

### AP-F2 — vetted numeric connection binding, exact URL families, no implicit proxies
- Result: PASS (tests intercept the ACTUAL connection primitive; a guard-only test is explicitly insufficient and was not used).
- Evidence (URL families): `validate_source_url` runs before the first request and on every redirect hop and cache reuse: https, no credentials, exact approved host, port None/443, non-empty path, no query (`url_query_forbidden`), no fragment (`url_fragment_forbidden`), exact family (OpenRouter `/api/v1/models`; OpenAI `/api/docs/pricing.md`, `/api/docs/models.md`, `/api/docs/models/<slug>.md` with the strict slug pattern; ECB `/stats/eurofxref/eurofxref-daily.xml`), source-kind match (`url_path_kind_mismatch`). Rejected redirect targets never leak credentials/query into outcomes (only the safe code is recorded).
- Evidence (connection binding): the tests monkeypatch `socket.create_connection` (the actual connect primitive used by the vetted backend) and record every `(ip, port)` pair: a three-connection run produced exactly three vetted NUMERIC connects to the approved public address on 443; a TLS spy on `ssl.SSLContext.wrap_socket` recorded `server_hostname == "openrouter.ai"` with `check_hostname=True` and `CERT_REQUIRED` across three fresh-socket attempts (original SNI + verified certificate policy preserved).
- Evidence (negatives): mixed public+loopback DNS → `destination_mixed_or_not_public` before ANY connection (exactly 1 attempt charged, 0 connects); rebinding (preflight answer public, connect-time answer mixed) → refused with 0 connects (the connect-time set is the bound set); `HTTPS_PROXY` set in the environment with `trust_env=False` → connects still go to the vetted IP, never the proxy; spec-cache reuse performs no second connection; the pool's network backend is asserted to be the vetted backend; UDS → `uds_forbidden`.
- Library facts (from the installed venv sources, no external doc read): httpcore 1.0.9 calls `backend.connect_tcp(host, port, timeout, local_address, socket_options)` per new connection and backend exceptions propagate unwrapped through httpx; `httpx.Client` uses environment proxies only when `trust_env and transport is None` — both disabled here.

### AP-F3 — identity-only transfer, refused before expansion
- Result: PASS.
- Evidence: the production client sends `Accept-Encoding: identity`; `fetch_source` refuses any `Content-Encoding` that is not exactly `identity` (`unexpected_encoding`) BEFORE the stream is read, and the acquisition path performs raw wire reads only (no decoder is ever constructed), so decompressor allocation cannot precede refusal; `Content-Length` is never trusted — the body cap is enforced on counted raw reads.
- Evidence (tests, real compressed bytes, not pre-decoded fixtures): a real gzip wire stream whose plaintext would expand to 8 MiB is refused with `unexpected_encoding` before the stream is touched (generator flag proves no read) with 0 bytes charged; `br` is refused the same way; a misleading `Content-Length: 10` over a 200-byte body yields `body_too_large` at the per-source cap; a partial stream failure charges exactly the interrupted chunks (3 × 64 KiB across three retry attempts).
- Evidence (real endpoints, AP-F5): identity support measured live — all four official hosts (developers.openai.com ×3, openrouter.ai, ecb.europa.eu) returned HTTP 200 to the identity-only production client; bytes were read raw with no decoding (content sha256s match the wire).

### AP-F4 — collector/CLI → validation → sealed report regressions retain accepted semantics
- Result: PASS.
- Evidence: the focused 10-file suite (below) passes 359/359 with all unit HTTP/DNS mocked and a zero-uninjected-default-DNS audit; the 28 CLI tests are unchanged and green (pricing/authority/baseline/seal/HMAC semantics untouched); the four new collection regressions prove cross-phase budget integrity and BLOCKED publication (exit 20, safe code in the JSON summary `reason` and in `validation.json`).
- Evidence (live safe failures, AP-F5): the first two real candidates (`babbage-002`, `davinci-002`) are legacy pages without chat capability; the production collector classified them `incomplete`/`page_no_chat` and validation returned BLOCKED with the accepted safe codes (`collection_empty_bootstrap`, `gate:completeness`, `missing_required_selection`), pipeline exit 20 — deterministic failure-to-BLOCKED with no false disappearance or bootstrap on real data.

### AP-F5 — bounded official unauthenticated GET smoke through the production transport, literal final implementation
- Result: PASS (qualified at the implementation head; a pre-commit run is separately recorded and labeled as such).
- Qualifying run on the LITERAL implementation head: the working tree was verified equal to HEAD `bfc59921e3f50b2d050369c8aa0a8bedb0185808` before the run; the SHA is recorded in the retained artifacts (`smoke-run-head-bfc5992.out` header line, `smoke-evidence-HEAD-bfc5992.json`). The run used the production `new_client()` (fingerprint recorded in the evidence: transport `VettedHTTPTransport`, backend `VettedNetworkBackend`, `trust_env: false`, `Accept-Encoding: identity` sent) and `collect_bundle(...)` with the production CLI review tail (`validate_bundle` → `_finalize_review_pipeline` at stage "live collection") — no ad-hoc alternate HTTP client.
- Scope selection from FETCHED current facts (not stale prices): scope prefetch fetched `pricing.md` (23,231 B, sha256 `e0767b50…fc28`) and `models.md` (12,144 B, sha256 `150ad20e…0234`) in 2 attempts / 0.248 s; 120 pricing rows, 102 index IDs, 40 standard candidates, 29 eligible (23 index-eligible); candidate order `[babbage-002, davinci-002, gpt-3.5-turbo, gpt-4.1, gpt-4.1-mini]` (first-install collector B1 logic).
- Candidate attempts (each a fresh bounded invocation with its own ≤24-attempt / ≤8 MiB / ≤120 s context; pre-fetched scope docs re-fetched once per invocation by design):
  - Attempt 1 `babbage-002`: 4 attempts / 807,923 B / 0.691 s; sources 200: `models.md`, `models/babbage-002.md` (3,077 B, `2bf7fd23…02802`), `pricing.md`, OpenRouter catalog (769,471 B, `4e80515b…db517`); BLOCKED (`page_no_chat` → `collection_empty_bootstrap`, `gate:completeness`, `missing_required_selection`), exit 20; sealed run `collect-20261012-184814-eb38e0d91502`.
  - Attempt 2 `davinci-002`: 4 attempts / 807,917 B / 0.622 s; same set with `models/davinci-002.md` (3,071 B, `b7334cd0…06cf2`); BLOCKED with the same safe codes, exit 20; sealed run `collect-20261012-184815-2fed0a27ec74`.
  - Attempt 3 `gpt-3.5-turbo`: 5 attempts / 809,651 B / 0.793 s; adds `www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml` (1,547 B, `569019b3…a078`) plus `models/gpt-3.5-turbo.md` (3,258 B, `b4c0d862…f4e7`); **READY** — "all recomputed gates verified; no review findings", 0 blockers, 0 review findings, exit 0; proposed `openai/gpt-3.5-turbo`; sealed run `collect-20261012-184816-a7fd81b0d3c2` (9 files: REVIEW.html, catalog-baseline.json, catalog-refresh.json, fx-proposal.json, manifest.json, pricing-proposal.tsv, receipt.json, routes-proposal.tsv, validation.json).
- All real requests: HTTP 200, exactly 1 attempt each, 0 redirects, 0 retries. Totals across the head run: 15 real HTTP attempts (scope 2 + 4 + 4 + 5), 2,460,866 charged body bytes, 2.354 s network wall; every invocation stayed far inside the 24-attempt / 8 MiB / 120 s smoke caps (max per invocation: 5 attempts, 809,651 B, 0.793 s).
- Offline verification (HTTP/DNS/socket forbidden — `socket.getaddrinfo`/`connect`/`connect_ex` replaced by refusal counters): `verify_run` on all three sealed runs returned `valid: true` with checks `digests: ok`, `hmac: ok`, `sql_evidence: replayed from sealed bytes (no SQL executed during verification)`, `artifacts: ok`, `validation: ok`, `report: ok`, `correspondence: ok`; the selected READY run additionally reports `state: READY`. 0 refusal events (no network primitive was invoked). The seal key is a synthetic external 32-byte HMAC key loaded through the sanctioned `load_seal_key_bytes` (anchored, 0600, 64-hex). No inference, no auth, no DB writes.
- Pre-commit run (recorded separately, NOT the literal-head qualification): the same design ran once before the implementation commit (artifacts `smoke-evidence-PRECOMMIT.json`, `smoke-run3.out.PRECOMMIT`) and reached the same READY outcome. Its deterministic per-bundle run suffixes (`eb38e0d91502` / `2fed0a27ec74` / `a7fd81b0d3c2`) and all 15 content sha256 values are IDENTICAL to the head run — byte-identical official-source collection across the two runs. An earlier first-design run (18:27Z, 6 attempts) exercised the same production transport and is superseded by these two records.
- Scratch-harness transparency (both issues were in the SCRATCH script, not the implementation; both found, fixed, and re-verified before publication): (1) the pre-commit script's first-pass `verify_run` call passed the raw 64-byte hex key file as HMAC key material instead of the sanctioned loader's hex-decoded 32-byte key, so the first-pass verify showed HMAC failure; after correction the re-verification (offline, refusal-patched) of all three published runs returned `valid: true`. The literal-head script uses the sanctioned loader from the start (first-pass `valid: true`, above). (2) the pre-commit script attributed run directories by lexicographic-last name, which misattributed attempt 2 to attempt 1's directory (run names embed second-resolution timestamps plus a deterministic per-bundle suffix); the literal-head script attributes by exact before/after directory diff (all three head-run attributions match the pipeline-reported run_ids).
- Deferred (explicitly UNCLOSED, reported not hidden): intact replay's misleading live label and tooling identity — runner-measured acquisition versus supplied/replayed data and exact installed tooling identity are NOT closed by this transport smoke; they remain REQUIRED in a later same-PR continuation.

## Local verification

- Focused 10-file suite (saved run `/tmp/slaif-181f-agent/final-suite.out`; count recovered by collect-only, not by re-execution, per the in-round clarification): **359 passed, 0 failed, 0 skipped** — collect-only total 359 equals the executed count. Per file: `test_catalog_refresh_source_evidence.py` 79, `test_catalog_refresh_bundle.py` 30, `test_catalog_refresh_policy.py` 41, `test_catalog_refresh_report.py` 11, `test_catalog_refresh_seal.py` 28, `test_catalog_refresh_collection.py` 72, `test_catalog_refresh_sources.py` 45, `test_cli_catalog_refresh.py` 28, `test_provider_catalog_proposal.py` 17, `test_oap_governance.py` 8. (The 181-d report recorded 333 at head `1ae62c3`; the +26 delta is this round's rewritten transport suite and the four new collection regressions.)
- Zero-default-DNS audit (strategic-identical external guard, 3 transport/CLI files, 145 tests): exit 0, `{"exitstatus": 0, "uninjected_dns_calls": []}` — zero uninjected default-DNS calls and zero real connections in the unit surface.
- `ruff check app tests`: **All checks passed**.
- `scripts/check_documentation.py`: **DOCUMENTATION_CHECK=OK files=91**.
- `git diff --check b0cdb0019c31a744d464c2502b7f98ffb5d7b839`: **CLEAN**.
- Full local DB/Redis/Docker/HPC/browser matrix: **NOT RUN** — explicitly out of scope for this transport-only delta per the order; GitHub CI ran the full matrix at the implementation head (10/10 SUCCESS).

## GitHub CI / required checks

Check state observed for implementation head `bfc59921e3f50b2d050369c8aa0a8bedb0185808` (all resolved before report drafting):

- `Docker Compose smoke`: **SUCCESS** (1m0s) — run 38293329420, job 114958384203
- `Unit, lint, and migration head`: **SUCCESS** (1m30s) — run 38293329420, job 114958384091
- `PostgreSQL integration tests`: **SUCCESS** (2m24s) — run 38293329420, job 114958384153
- `OpenAI-compatible E2E tests`: **SUCCESS** (1m26s) — run 38293329420, job 114958384031
- `Playwright browser smoke`: **SUCCESS** (2m46s) — run 38293329420, job 114958384193
- `Documentation hygiene`: **SUCCESS** (8s) — run 38293329420, job 114958383789
- `Analyze Python`: **SUCCESS** (1m5s) — run 38293329426, job 114958383875
- `CodeQL`: **SUCCESS** — `Analyze (python)` SUCCESS (2m22s, run 38293325837, job 114958377525), `Analyze (javascript-typescript)` SUCCESS (37s, run 38293325837, job 114958377051)
- All required checks green for the implementation head at report drafting: **yes — 10/10**
- Report-only commit may trigger fresh checks: strategic model must verify the `SELF` commit without rewriting this report.

## Local setup / dependencies

- Packages/tools/services installed or configured: none. The strategic dev venv (`/tmp/slaif-181c-strategic-venv`, Python 3.12.15, httpx 0.28.1 / httpcore 1.0.9, pytest, ruff) was used for tests/lint/docs only; no package was installed, upgraded, downgraded, or removed anywhere.
- Owned scratch: `/tmp/slaif-181f-agent` (mode 700) holding the smoke script, the synthetic external seal key (0600), the sealed run directories, and the retained evidence artifacts (`smoke-evidence-PRECOMMIT.json`, `smoke-evidence-HEAD-bfc5992.json`, `smoke-run3.out.PRECOMMIT`, `smoke-run-head-bfc5992.out`, `final-suite.out`, `dns-audit.out`). Scratch only; nothing outside the allowed repo paths was changed.
- Network usage: ONLY the bounded AP-F5 smoke — 34 unauthenticated official GETs across the three bounded smoke records (first-design 4, pre-commit 15, literal-head 15), all HTTP 200, no auth headers, no inference, no DB. Library/stdlib design facts were taken from the installed venv sources (httpx 0.28.1, httpcore 1.0.9); no external documentation read was needed this round.
- No `.env`, no protected credentials, no private files, no production database/import, no real email, no deploy/tag/release. No `sudo`-level setup.

## Documentation

`docs/catalog-refresh.md` now states the exact registry URL path families and the 181-f transport/budget guarantees: one whole-invocation budget (an attempt is one real HTTP request; a byte is every wire body byte charged before cap checks; no refunds; fail-closed `collection_budget_exhausted`), the 120 s monotonic acquisition deadline with the honest in-flight-operation limit (one in-flight operation may complete slightly past expiry, bounded by the 10 s/30 s connect/read timeouts), the cross-phase success-or-failure cache with registry-identity revalidation, and the vetted connection binding (connect-time DNS vetting including mixed-answer refusal, original hostname/SNI and verified certificate policy, `trust_env` disabled, UDS forbidden). `docs/cli-reference.md` and `admin/catalog-refresh/README.md` required no transport wording (verified by inspection; both unchanged). `scripts/check_documentation.py` OK (91 files).

## Safety and scope confirmations

- Unrelated files changed: no — the implementation commit touches exactly the eight allowed paths; untracked `CODEX-SESSIONS.md`, `codex.sh` preserved (not committed); ignored `.codex/`, `.local-provider-catalog/`, unrelated worktrees, and historical reports 181-a…181-e untouched.
- Allowed-path discipline: the CLI file `app/slaif_gateway/cli/catalog_refresh.py`, dependencies, Dockerfile/Compose, workflows, schema/bundle/capture/seal/rendering, `source_evidence` pricing/parser policy, and all runtime gateway surfaces are unchanged; the delta is confined to the acquisition subsystem plus its tests/docs/order/active.
- Production secrets accessed: no. Production systems accessed: no. No secrets, DB URLs, or raw exception text appear in this report (safe status/counts/hashes/timestamps/codes only).
- Required tests skipped/not run: yes — full local DB/Redis/Docker/HPC/browser matrix not run locally (out of scope per the order); GitHub CI ran the full matrix at the implementation head (10/10 SUCCESS).
- Scope deviation: no — no merge or auto-merge of any kind; no new PR; PR 318 amended only; no release/tag/production authority exercised.
- Extra PR created for same numeric objective: NO
- PR merged by coding agent: NO (`autoMergeRequest: null` preserved)
- Activated order and `oap/active` edited by coding agent: NO (order sha256 `3ce0853b6da9edaccfca0f5ba2984370bccf946b8352e24aa64377ac69b3e99e` and exact 5-byte active `181-f` verified at commit and at publication; committed byte-unchanged)
- Report-publication commit changes only this report file: yes (verified by staged diff before the commit)
- Real upstream/provider calls: only the bounded AP-F5 smoke described above. No real email. No inference. No production DB. No tags/releases.
- Report layout redesign: none — follows the established 181-x report structure

## Known limitations / blockers

- No CI blockers remain: all ten required checks are SUCCESS at the implementation head.
- Objective 181 is NOT closed by this round: runner-measured acquisition versus supplied/replayed data (intact replay's misleading live label) and exact installed tooling identity remain REQUIRED in a later same-PR continuation and are reported here as deferred, not hidden. Objectives 182 (isolated Codex), 183 (atomic audited apply/accounting), 184 (final administrator workflow) remain pending; no 182 while 181 is unresolved.
- The 120 s deadline is enforced before every new network operation; one already in-flight operation may complete slightly past expiry (bounded by the 10 s connect / 30 s read timeouts) — documented as an honest limit, not claimed as a hard stop mid-byte.
- The first two alphabetically-first eligible OpenAI models in current official facts (`babbage-002`, `davinci-002`) are legacy pages without chat capability; the smoke's bounded candidate loop handled them as deterministic BLOCKED runs (safe codes, exit 20) before reaching the READY candidate — this is correct fail-closed behavior, not a defect.
- The pre-commit smoke run is explicitly NOT the literal-head qualification; the qualifying record is the head-bound run described in AP-F5.

## Recommended strategic follow-up

Factual recommendation only: the next same-PR continuation can proceed to the remaining REQUIRED 181 items — actual collection versus intact replay (runner-measured acquisition versus supplied/replayed data, including the misleading live label) and exact installed tooling identity — per the strategic plan. Merge of PR 318 remains the strategic model's delegated decision after independent verification of the final (report) head and its fresh checks.
