# OAP Objective 191-a — final report: bounded operator-controlled full incoming-request capture

Work order: `oap/orders/191-a-full-incoming-request-capture.md` (committed
unchanged with `oap/active` = `191-a`).
Branch: `oap/191-full-incoming-request-capture`, base `main`
`5564bef2a87a0ee115f4989a8ff75abf824363f6` (verified unchanged at
publication). PR mode: CREATE_NEW_PR (Objective 191 = exactly one new PR).
The coding agent never merges; no auto-merge is enabled; root reviews
independently.

Implementation head SHA: 820efd7c77c89dc76b9a62f8088cc5200bfa8704
Report publication commit: SELF

## What changed

A default-OFF, finite, expiring, operator-armed diagnostic facility that
captures the full original incoming request bytes of a bounded number of
matching requests into a shared local `0700` directory across all API
workers. Human-authorized full-content capture with masking, finite scope,
and no impact on auth/validation/admission/accounting/forwarding.

- **New modules** (no dependency, no schema, no UI):
  - `app/slaif_gateway/utils/capture_redaction.py` — pure bounded masker:
    complete non-auth bytes preserved byte-exact; known incoming auth
    values (gateway Bearer, Cookie secrets, Proxy-Authorization decoded
    credentials, explicit credential query/body fields) masked in raw,
    percent-encoded, and JSON-escaped copies; recognized gateway key
    replaced by its public hint; identifier fields (`session`,
    `session_id`, `nonce`, `signature`) preserved; explicit credential
    fields masked regardless of length.
  - `app/slaif_gateway/services/request_capture.py` — flock-protected
    manifest store: finite count/TTL windows with verified-key UUID
    filter, positive per-claim reservation plus actual per-capture and
    global budget re-checks under one lock at publication, no-follow /
    owned / size-bounded control and artifact reads, atomic publication,
    only-recognized-name cleanup, bounded non-blocking locking, safe
    local rejection/provenance context channels.
  - `app/slaif_gateway/api/request_capture.py` — outermost pure-ASGI tee
    observer: app called exactly once, forwarded messages byte-identical
    (object-identity forwarded), exact original exception preserved and
    re-raised after safe finalize; incomplete bodies (not consumed /
    body limit / client disconnect / buffer failure) store **zero** body
    bytes with precise `incomplete_reason` and observed/buffered/stored
    counts; complete bodies (including malformed JSON) fully retained
    except explicit auth substitutions; method and local rejection
    metadata masked with the same known-secret pairs (fail-safe, never
    returns unmasked originals on mask failure).
  - `app/slaif_gateway/cli/request_capture.py` — `arm`/`status`/`stop`/
    `cleanup`/`inspect` with bounded no-follow/owned/size-capped reads,
    base64-retaining `--decode` with lossy-view labeling, and a fixed
    generic error boundary (unexpected exceptions never echoed).
- **Observation-only hooks** (best-effort, no public response change):
  `api/errors.py` records bounded local rejection facts including the
  public error code/param/message/status merged onto more specific
  structured facts (taxonomy reason with indexes/counts/limits, or
  bounded JSON parser/schema facts with decoder position and the safe
  decoder message, never `.input`/raw body/exception objects);
  `api/dependencies.py` records normal-auth verified-key provenance;
  `services/responses_gateway.py` records the selected client-module
  id + version + fixture_sha256 (unknown when none selected).
- **Wiring/config**: `config.py` `REQUEST_CAPTURE_*` settings; `main.py`
  installs the observer as the outermost middleware only when the
  facility is enabled and valid (thin, <80-line guard); `cli/main.py`
  registers the `request-capture` subtyper.

## Verification (this objective; focused; all SYNTHETIC data)

- **Focused JUnit, worktree run** (`/tmp/slaif-181c-strategic-venv`,
  `PYTHONPATH=app`): one invocation of the 4 new/changed suites plus the
  narrowed existing suites (`test_documentation_inventory`,
  `test_request_policy_errors`, `test_rate_limit_api_errors`,
  `test_request_id_middleware`, `test_config`,
  `test_main_app_structure`, `test_codex_0162_client_tools`,
  `test_responses_codex_client_tools`, `test_responses_request_policy`,
  `test_codex_profile_data`, `test_v1_auth_dependency`) and
  `tests/integration/test_request_capture_store.py`:
  **tests=532 failures=0 errors=0 skipped=0** (519 unit/doc cases + 13
  REAL multiprocess store integration cases). Separate E2E invocation of
  `tests/e2e/test_request_capture.py`: **tests=3 failures=0 errors=0
  skipped=0** (owned labelled loopback tmpfs PostgreSQL 16 per run,
  exact-ID cleanup). 535 focused cases total, 0 failures/errors/skips.
- **Real multiprocess store** (no DB): barrier-synchronized spawned
  workers report per-worker claim outcomes over a queue — exactly-one
  winner for a count-1 window; finite count sums exactly; expiry/stop
  never re-arm across restarts; 0700/0600 modes; symlinked root/manifest
  refused; zero-reservation, unclaimed, duplicate, and over-budget writes
  refused; cleanup preserves unrelated files.
- **E2E evidence and its honest limits** (see
  `docs/verification/incoming-request-capture.md`):
  - Chat regression runs the gateway in a test-process thread with a
    respx-mocked OpenAI upstream: it proves default-OFF/no-arm
    passthrough parity, finite-window capture of chat/stream/full-body
    retention, exact exhaustion, malformed-JSON 422 capture with precise
    parser facts, and exactly 5 usage-ledger rows for the 5 accepted
    requests (a count — per-row finalized state/token totals are asserted
    only in the Responses regression). It is **SDK/mocked-upstream
    coverage, not a fresh-process proof**.
  - Responses regression spawns a **FRESH gateway process** (real
    uvicorn) against a **real loopback mock Local-Coding HTTP backend**
    with the owned PG: bad-HMAC verified-key non-consumption, complete
    malformed-JSON capture (`read_only_capture_probe` provenance, since
    malformed JSON is rejected before normal auth), precise
    `tool_name_not_allowed` taxonomy facts with the public error
    code/param/message, actual module id/version/digest, successful
    admission with `(3 requests, 15 tokens)` and three `finalized`
    5-token ledger rows, identical provider payload hashes across
    unarmed/captured/injected-publish-failure, and canary-free gateway
    logs.
  - **Neither regression is actual Codex CLI or actual model
    qualification**, and none of it claims real traffic was captured or
    inspected. All request data is synthetic.
- **Historical/independent evidence (strategic side, same source;
  source-bound probe receipts in the strategic review-artifacts directory —
  retained and re-run against the current source between review rounds,
  not immutable artifacts):** masker corpus 15/15; ASGI observer 11/11 (incl. 10 MiB exact artifact,
  surrogate diagnostic masking, partial-secret incomplete path); CLI
  subprocess 11/11; store 7/7 + boundary 4/4; taxonomy parity 2605 and
  policy parity 1848 (old acceptance surface preserved); fresh
  HTTP/owned-PG/live mock backend proof PASS (public error facts, decoder
  reason, module identity, exact provider payload hashes, three
  finalized rows, bad-HMAC non-consumption, clean logs). These are
  external evidence for this source; they are not part of this
  repository and do not replace the permanent in-repo regressions.
- **Pending:** final GitHub CI at the PR head. Local focused runs above
  are not a substitute for the full matrix; no release, production,
  security, or compliance claim follows from this objective.

## Docs impact statement

- New: `docs/runbooks/incoming-request-capture.md` (exact operator
  procedure: external overlay template, dedicated `0700` host directory,
  restart matrix, loader-based CLI invocations, access-log safety,
  arm/inspect/cleanup, synthetic-vs-real distinction) and
  `docs/verification/incoming-request-capture.md` (bounded verification
  record, 2026-10-18).
- Updated: `docs/configuration.md` (Operator Request Capture settings
  table and guarantees), `docs/observability.md` (default-OFF capture as
  the single bounded exception to the no-request-content rule; retention
  vs expiry; permission boundary), `docs/security-model.md` (capture
  privacy boundary), `docs/cli-reference.md` (five commands + complete
  command inventory entries), `docs/upgrade-runbook.md` (binary-only,
  default-OFF upgrade/rollback; manifest-persistent windows), `AGENTS.md`
  (narrow opt-in exception in Observability), `.env.example` (curated
  block), and the runbooks/verification README indexes.

## Current / historical / synthetic-vs-real distinction

- **Current:** the JUnit numbers above are from this worktree at the
  implementation head; they describe exactly the focused suites named.
- **Historical:** the strategic independent probe receipts are dated,
  source-bound records against successive drafts of this same source
  during review (re-run against the current source between rounds); they
  are cited as evidence, not as permanent CI, and are not immutable
  artifacts.
- **Synthetic vs real:** every captured byte in tests and probes is
  synthetic; no actual Codex CLI run, end-user production traffic, real
  model, real provider, or production database was involved, while real
  Python SDK HTTP requests were made against the local gateway with
  mocked upstreams. The operator runbook's reproduction step is an
  operator action, not a performed test.
