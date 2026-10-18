# 2026-10-18 Incoming Request Capture Bounded Verification

> **Scope:** Objective 191 — operator-controlled full incoming-request
> capture (default OFF). This record describes what the bounded runs on this
> worktree actually proved. No actual Codex CLI run, end-user production
> traffic, model, or provider call was performed; real Python SDK HTTP
> requests were made against the local gateway (owned loopback) with the
> provider upstream mocked. All captured request data is **synthetic**, and
> nothing here is a claim that any real traffic was captured or inspected.

## Environments

- Worktree: `slaif-api-gateway` (objective 191 branch, base `5564bef2`),
  interpreter `/tmp/slaif-181c-strategic-venv/bin/python` (Python 3.12),
  `PYTHONPATH=app`.
- PostgreSQL: owned, labelled, loopback-bound, tmpfs-backed `postgres:16`
  container per run (`owned_pg_url` fixture), explicit exact-ID cleanup.
- Provider backend: real loopback mock Local-Coding HTTP server for the
  fresh-process Responses regression; respx-mocked OpenAI upstream for the
  thread-gateway Chat regression. No real provider calls.

## What ran, and what it proved

### 1. Unit: redaction, observer, CLI, and facility construction
`pytest tests/unit/test_request_capture.py
tests/unit/test_cli_request_capture.py
tests/unit/test_capture_redaction.py` (plus the narrowed existing suites
`test_documentation_inventory`, `test_request_policy_errors`,
`test_rate_limit_api_errors`, `test_request_id_middleware`, `test_config`,
`test_main_app_structure`, `test_codex_0162_client_tools`,
`test_responses_codex_client_tools`, `test_responses_request_policy`,
`test_codex_profile_data`, `test_v1_auth_dependency` and
`tests/integration/test_request_capture_store.py`) in one invocation:

- **JUnit: tests=532 failures=0 errors=0 skipped=0** (~19.9 s) —
  519 unit/doc cases **plus 13 REAL multiprocess store integration cases**
  (Section 2), not 532 pure unit cases.

Covered invariants: complete-body retention byte-exact except explicit auth
substitutions; known secrets masked in method/path/query/headers/body and in
local rejection metadata (including a surrogate-unsafe diagnostic value);
raw `raw_path` preservation; incomplete captures (not consumed / body limit /
client disconnect / zero budget) storing **zero** body bytes with precise
`incomplete_reason` and observed/buffered/stored counts; exact original
exception preservation with safe finalize; write-failure passthrough with
claim consumed; claim exhaustion after the finite count; normal-auth vs
read-only-probe provenance; module id/version/digest in the record;
default-OFF passthrough; CLI lifecycle (arm defaults/explicit, status, stop,
cleanup, inspect with bounded decode) and the fixed generic error boundary
(unexpected exceptions never echoed; known store/CLI reasons preserved).

### 2. Integration: REAL multiprocess store (no database)
`pytest tests/integration/test_request_capture_store.py` (the 13 cases inside
the JUnit run above): real OS child processes (spawn context) behind a
shared barrier reporting per-worker claim outcomes over a queue —

- exactly-one-winner race for a count-1 window (one `won`, one `skipped`,
  both exit code 0, manifest `claimed=1`, then exhausted);
- finite count 5 across three workers sums exactly 5;
- expiry and stop never re-arm across store restarts on the same root;
- `0700` directory / `0600` file permissions;
- symlinked root and symlinked manifest refused;
- zero-reservation claim rejected; unclaimed/duplicate writes rejected;
- per-capture envelope and global total budget enforced;
- cleanup preserves unrelated files and releases quota.

### 3. E2E: real HTTP + owned PG + mock backend
`pytest tests/e2e/test_request_capture.py` (separate invocation, JUnit
tests=3 failures=0 errors=0 skipped=0, ~14.3 s):

- **Chat (in-process thread gateway, respx-mocked upstream):** unarmed
  baseline changes nothing (identical upstream bytes, no artifacts); a
  count-3 window captures chat/stream/chat full bodies (canary prompt
  present, gateway key absent); the window exhausts exactly; a count-1
  window captures a malformed-JSON 422 with exact original bytes, bounded
  `json_invalid` parser facts (loc with body offset + decoder message) and
  the public `validation_error` facts; the 5 accepted requests produce
  exactly 5 usage-ledger rows (a count — this Chat regression does not
  assert per-row finalized state or token totals; that exact
  finalized/token claim is made only in the Responses regression below);
  the disabled facility is fully passthrough.
- **Responses (FRESH gateway process, real loopback mock Local-Coding
  backend):** verified-key UUID filtering with bad-HMAC non-consumption;
  complete malformed-JSON capture (provenance `read_only_capture_probe`,
  since malformed JSON is rejected before normal auth); precise taxonomy
  `tool_name_not_allowed` rejection with `tool_index`/`namespace_index` and
  the public error code/param/message; actual selected-module
  id/version/`fixture_sha256` in the record; successful admission with
  exact body preservation; controlled publication failure leaving the app
  result unchanged and the claim consumed; identical provider payload
  hashes across unarmed/captured/failed-publish requests; PostgreSQL
  counters `(3 requests, 15 tokens)` and three `finalized` 5-token ledger
  rows; no canaries in the gateway log.
- **Evidence honesty:** the Chat regression is SDK/mocked-upstream
  coverage, not a fresh-process proof; neither regression is actual Codex
  CLI or actual model qualification.

### 4. Focused totals

535 focused cases total (532 in the first JUnit invocation + 3 E2E),
0 failures, 0 errors, 0 skips.

### 5. Strategic independent probes (external, source-bound)
The strategic reviewer ran independent probes against this worktree's
source (source-bound independent evidence — retained probe receipts that
are re-run against the current source between review rounds, not immutable
artifacts): masker corpus 15/15; ASGI observer 11/11 (including 10 MiB
exact-body artifact, surrogate diagnostic masking, partial-secret
incomplete path); CLI subprocess 11/11; store 7/7 + boundary 4/4; taxonomy
parity 2605 and policy parity 1848 (old acceptance surface preserved);
fresh HTTP/owned-PG/live mock backend proof PASS including public error
facts, decoder reason, module identity, exact provider payload hashes,
three finalized 5-token rows, bad-HMAC window non-consumption, and clean
logs. Probe receipts live in the strategic review-artifacts directory
(e.g. `independent-live-http-probe.json`,
`redaction-layer-acceptance.json`); they are external evidence for the same
source, not part of this repository.

## What this record does NOT establish

- No production deployment was performed and no production traffic was
  captured or inspected.
- No real OpenAI/OpenRouter/Codex CLI/model qualification of any kind.
- Final GitHub CI at the PR head is pending at the time of this record; the
  numbers above are local bounded runs on the worktree source.
- No claim about reverse-proxy or external operator log behavior.
