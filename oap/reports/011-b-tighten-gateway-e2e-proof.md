# OAP Coding-Agent Report — 011-b

## Work order

- Identifier: `011-b`
- Work-order file:
  `oap/orders/011-b-tighten-gateway-e2e-proof.md`
- Work-order SHA-256:
  `eaf529d1e8cd927c89a2ee738b6e692401fc9191913008d99a6cb29a2c38517e`
- Active-pointer SHA-256:
  `c050b517a63f73852c333f8a5f2ae49a3ecb5ae52712f7e401b23b18db0b67e6`
- Numeric objective: `011`
- PR mode: `AMEND_EXISTING_PR`

## Status

COMPLETE

## Executive summary

Objective 011-b tightens the unified local Codex gateway verifier so every
reported proof now follows from exact evidence rather than a weaker proxy. The
verifier reconciles every successful key and ledger at PostgreSQL's exact
nine-decimal money scale; requires an exact successful local-exec sentinel and
the exact final structured Codex marker; proves unique interruption and
provider-error body sentinels do not persist; accepts only a canonical
numeric-loopback disposable PostgreSQL URL; and uses one shared helper that
creates and verifies 0700 private directories and 0600 credential-free profile
files for every Codex child.

The same five actual-Codex scenarios passed with exact `/usr/bin/codex` 0.147.0,
bundled `gpt-5.6-sol`, the real local SLAIF app, a fresh disposable PostgreSQL
database, private no-persistence Redis, and a numeric-loopback scripted OpenAI
Responses mock. The human-only real-OpenAI pilot runbook now includes one
copyable bounded command, but that pilot remains PREPARED, NOT EXECUTED.

The exact support state remains:

```text
local_gateway_e2e_qualified=true
bounded_real_openai_pilot_prepared=true
real_provider_e2e=false
```

No real provider, production/staging gateway, hosted tool, MCP/connector, or
non-loopback endpoint was called. This is not full Codex compatibility,
real-provider qualification, production readiness, pilot completion, release
readiness, provider-invoice truth, or evidence for another Codex/model/profile.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- Remote `main` at report drafting:
  `7f35b1107037a9e351fc1128715eccbca1181693`
- Starting remote PR head / immutable 011-a report:
  `fbf1d71d04ac5160a362faa5a74ca33a7bf4a1b5`
- Implementation head SHA:
  `d43d62ea66fecc3efa0fec81675cc786ab8e3671`
- Implementation-head first parent:
  `fbf1d71d04ac5160a362faa5a74ca33a7bf4a1b5`
- Implementation-head commit message:
  `OAP 011-b: tighten Codex gateway E2E proof`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA verified after push)
- Report commit first parent: same as Implementation head SHA
- PR number: `236`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/236`
- PR title: `[OAP 011] Prove Codex gateway E2E and pilot readiness`
- PR state at report drafting: `OPEN`, non-draft, GitHub `MERGEABLE` / `CLEAN`
- Base branch: `main`
- Head branch: `oap/011-codex-cli-e2e-openai-pilot-readiness`
- Objective-011 PR count: exactly one, PR #236
- Created a new PR this turn: NO
- Amended existing PR #236: YES
- Auto-merge enabled: NO (`autoMergeRequest=null`)
- Merge performed: NO

## Implementation

The verifier now:

- parses only `postgresql+asyncpg://` URLs with a safe simple user, optional
  password, exact `127.0.0.1`, explicit numeric TCP port, one safe disposable
  database path, and no query, fragment, control, whitespace, socket, host, or
  option override;
- loads key used/reserved EUR cost and each ledger's HTTP status, EUR/native
  actual cost, native currency, component-token facts, and complete native
  component-cost mapping;
- compares `Decimal` values exactly at scale `0.000000001`, with no floats,
  tolerance, or positivity-only reduction;
- generates one high-entropy exec sentinel per run, emits it only after the
  fixed `pwd` succeeds, and accepts local exec only when the next request has
  exactly one linked `custom_tool_call_output` for the exact call ID whose
  recursively validated output contains that sentinel;
- accepts final text only from the exact structured `item.completed`
  `agent_message.text` marker plus `turn.completed`;
- gives interruption and structured provider-error bodies separate per-run
  sentinels and includes both in the typed database-wide no-persistence scan;
- prepares every Codex root/home/workspace through one shared helper, creates
  directories at 0700, writes each credential-free profile file once, sets it
  to 0600 once, and verifies modes immediately before child execution; and
- resolves cleanup roots against resolved `tempfile.gettempdir()`, requiring
  both the unique generated prefix and the exact resolved parent.

The pilot runbook's single command uses `/usr/bin/codex`, profile `slaif`,
ephemeral mode, approval `never`, zero request/stream retries, workspace-write
sandbox, the chosen disposable workspace, the fixed harmless prompt, bounded
output, update checking off, and the pinned low-effort/low-verbosity profile.
It places no secret in argv/history and does not enable search, network, hosted
tools, or MCP. A successful authorized pilot must have exit zero, exact marker
content, final `PILOT_OK`, a completed turn, and at most four provider calls.

## Exact accounting proof

All monetary comparisons used exact `Decimal` values at the database column's
nine-decimal scale. Native currency was `EUR`, so the native and EUR totals are
identical for this fixed verifier pricing.

### Key and ledger totals

| Scenario/key | Successful ledgers | Per-ledger actual EUR/native | Exact key `cost_used_eur` | Exact key `cost_reserved_eur` |
| --- | ---: | --- | ---: | ---: |
| Tool/replay | 3 | `0.000003000` each | `0.000009000` | `0.000000000` |
| Context above threshold | 1 | `1.050030000` | included below | `0.000000000` |
| Context threshold edge | 1 | `0.234504000` | included below | `0.000000000` |
| Context below threshold | 1 | `0.000011750` | included below | `0.000000000` |
| Context/compact key total | 3 | rows above | `1.284545750` | `0.000000000` |
| Request-quota admitted call | 1 | `0.000003000` | `0.000003000` | `0.000000000` |

Every successful ledger was exactly `finalized`, HTTP 200,
`success=true`, with the stated `actual_cost_eur`, matching
`actual_cost_native`, and `native_currency=EUR`.

### Complete successful component expectations

All values below are native EUR. Each mapping also contained
`output_audio=0.000000000`; standalone/output audio was not used.

| Ledger | Uncached input | Cached input | Cache write | Non-reasoning output | Reasoning output | Exact total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Each tool/replay row | `0.000001000` | `0.000000000` | `0.000000000` | `0.000002000` | `0.000000000` | `0.000003000` |
| Context above | `0.600000000` | `0.200000000` | `0.250000000` | `0.000018000` | `0.000012000` | `1.050030000` |
| Context edge | `0.122000000` | `0.050000000` | `0.062500000` | `0.000002000` | `0.000002000` | `0.234504000` |
| Context below | `0.000004000` | `0.000002500` | `0.000001250` | `0.000002000` | `0.000002000` | `0.000011750` |
| Quota admitted row | `0.000001000` | `0.000000000` | `0.000000000` | `0.000002000` | `0.000000000` | `0.000003000` |

The exact component-token expectations were complete for the safe persisted
representation: tool/quota rows used one uncached input and one
non-reasoning-output token; context rows used input/cached/cache-write counts
`600000/200000/100000`, `272000/100000/50000`, and `10/5/1`, with
non-reasoning/reasoning output counts `6/4`, `1/1`, and `1/1`. Cache-write
counts were exactly derived from input/cached/uncached facts because the
repository redactor intentionally omits that raw field. Output-audio tokens
were unsupported and zero.

### Exact failure contract

| Failure | Reservation/ledger | Error type | HTTP status | Actual EUR/native | Currency | Key used/reserved cost |
| --- | --- | --- | --- | ---: | --- | ---: |
| Interrupted stream | `released` / `failed`, `success=false` | `provider_request_error` | `NULL` | `0.000000000` | `EUR` | `0.000000000` / `0.000000000` |
| Structured provider 429 | `released` / `failed`, `success=false` | `provider_http_error` | `429` | `0.000000000` | `EUR` | `0.000000000` / `0.000000000` |

Failure ledgers contained no successful component metadata, no replay
reference was created, and no missing usage was converted into zero-cost
success.

## Exec, final-text, failure-body, and persistence evidence

- The fixed exec source emitted its unique per-run sentinel only when the
  `pwd` result had exit code zero.
- The immediately following request contained exactly one linked
  `custom_tool_call_output` with the exact expected call ID and recursively
  validated output text containing that sentinel.
- The final marker appeared in the exact bounded structured Codex
  `item.completed` agent-message text and the turn completed.
- The edit marker file still exactly matched its per-run expected content.
- The incomplete stream carried its own unique response-body sentinel without
  token-bearing usage; the structured 429 carried a different sentinel in
  content that the gateway's raw-content sanitizer discards while retaining
  the fixed safe diagnostic type/code/message.
- Both failure sentinels, the exec input/output sentinel, final marker, edit
  marker, prompts, reasoning/compaction material, keys, and dummy upstream auth
  joined the typed scan of every known text/string/JSON database column.
- None persisted, appeared in verifier output, or entered this report.
- Replay storage remained HMAC-only with safe ownership/routing/expiry
  metadata; raw payloads, outputs, encrypted reasoning, and compaction values
  were not stored.

## Final exact manual verifier

Pinned evidence:

```text
/usr/bin/codex --version: codex-cli 0.147.0
model: gpt-5.6-sol
fixture SHA-256: 436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432
profile: API-key Responses profile v1 / profile-v2 file layout
```

The final dedicated database was
`slaif_gateway_oap011b_test_20260818c`. It was absent before creation, created
through the repository-approved narrow PostgreSQL sudo operation with owner
`slaif`, migrated and used only by the verifier, and dropped afterward by that
exact literal name. The canonical private `TEST_DATABASE_URL` used
`postgresql+asyncpg`, numeric `127.0.0.1`, and an explicit TCP port. Its dummy
local password/DSN was not printed. `DATABASE_URL` was unset and never used for
creation, migration authority, reset, truncate, or drop.

Exact safety environment:

```text
unset DATABASE_URL TEST_DATABASE_URL RUN_UPSTREAM_TESTS OPENAI_API_KEY OPENAI_UPSTREAM_API_KEY OPENROUTER_API_KEY SLAIF_OAP011_UPSTREAM_KEY
export ENABLE_EMAIL_DELIVERY=false
TEST_DATABASE_URL=<private canonical numeric-loopback disposable asyncpg URL>
.venv/bin/python scripts/verify_codex_gateway_e2e.py
```

Final safe output:

```text
RESULT=OK
CLI_VERSION_MATCHED=true
FIXTURE_DIGEST_MATCHED=true
SCENARIO_COUNT=5
TEXT_COMPLETION_SEEN=true
LOCAL_EXEC_SEEN=true
LOCAL_EDIT_SEEN=true
WORKSPACE_MARKER_MATCHED=true
MULTI_ROUND_REPLAY_SEEN=true
ENCRYPTED_REASONING_REPLAY_SEEN=true
CACHE_READ_USAGE_SEEN=true
CACHE_WRITE_USAGE_SEEN=true
LONG_CONTEXT_TIERS_SEEN=true
V1_COMPACT_SEEN=true
POST_COMPACT_CONTINUATION_SEEN=true
QUOTA_REJECTION_SEEN=true
QUOTA_REJECTED_BEFORE_UPSTREAM=true
STREAM_INTERRUPTION_SEEN=true
PROVIDER_ERROR_SEEN=true
ACCOUNTING_MATCHED=true
OUTSTANDING_RESERVATIONS=0
PROVIDER_AUTH_REPLACED=true
OUTBOUND_HEADERS_SANITIZED=true
LOOPBACK_ONLY=true
RAW_PAYLOADS_PERSISTED=false
REDIS_PRIVATE_EPHEMERAL=true
WORKSPACES_REMOVED=true
REAL_PROVIDER_CALLED=false
ELAPSED_MS=11278
```

Final cleanup proved:

```text
OAP011B_DATABASES_REMAINING=0
MATCHING_CODEX_ROOTS=0
MATCHING_REDIS_ROOTS=0
MATCHING_PROCESSES=0
```

All three exact 011-b disposable database names were confirmed absent.

## Failed bounded attempts and repairs

Every runtime attempt remained local, used no real credential, and contacted
no real provider or non-loopback endpoint.

1. The first ordinary TCP `createdb` attempt under the dummy local role was
   refused because that role cannot create databases; it created nothing. The
   database was then created with the approved narrow
   `sudo -n -u postgres /usr/bin/createdb -O slaif` operation.
2. Attempt A used fresh empty database
   `slaif_gateway_oap011b_test_20260818a` and returned only the fixed safe
   `context_fact_failed` result. A bounded boolean-only diagnosis proved all
   exact EUR/native totals, currencies, tier facts, component-cost mappings,
   and failure contracts matched. It also proved that the privacy redactor
   intentionally omits raw `input_cache_write_tokens` and
   `output_audio_tokens`. The verifier was corrected to require the exact
   persisted safe subset and derive cache-write counts. Database A, temporary
   roots, and processes were removed; all cleanup counts were zero.
3. Attempt B used fresh empty database
   `slaif_gateway_oap011b_test_20260818b` and returned only the fixed safe
   `isolation_fact_failed` result. A fixed prefix-only diagnosis reported exec,
   final, interruption, and HMAC scans safe, but the provider-error-body scan
   false. The unique sentinel had been placed in the ordinary diagnostic
   message, which SLAIF correctly persists in sanitized form. The fixture was
   corrected to put it in raw error `content`, which the current sanitizer
   drops, while keeping a fixed safe diagnostic message/type/code. Database B,
   temporary roots, and processes were removed; all cleanup counts were zero.
4. Final attempt C used the new fresh empty database named above and passed
   with the exact output shown. Database C, temporary roots, private Redis, and
   child processes were removed.
5. `gh pr edit` could not update the body because GitHub's Projects-classic
   GraphQL field is deprecated. The same in-scope body update succeeded through
   GitHub's pull-request REST endpoint; no repository or PR topology changed.

No failed attempt printed a sentinel, key, DSN, raw payload, component blob, or
subprocess output.

## Verification

Focused pytest command:

```text
.venv/bin/python -m pytest -q tests/unit/test_codex_gateway_e2e_verifier.py tests/unit/test_oap_governance.py tests/unit/test_documentation_contract_drift.py tests/unit/test_rc2_feature_scope_docs.py tests/unit/test_supercomputer_sharded_script.py
```

Result: PASS, 74/74 tests. Collection comprised 38 verifier tests, 8 OAP
governance tests, 9 documentation-contract tests, 4 RC2 feature-scope tests,
and 15 supercomputer-script tests.

Additional focused checks:

```text
.venv/bin/python -m ruff check scripts/verify_codex_gateway_e2e.py tests/unit/test_codex_gateway_e2e_verifier.py
.venv/bin/python -m ruff format --check scripts/verify_codex_gateway_e2e.py tests/unit/test_codex_gateway_e2e_verifier.py
.venv/bin/python -m py_compile scripts/verify_codex_gateway_e2e.py tests/unit/test_codex_gateway_e2e_verifier.py
sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
git diff --check
```

Results: Ruff passed; both files were already formatted; compilation passed;
the fixture digest matched; exact allowed paths and commit topology passed.
`git diff --check` reported only the unchanged strategic order's pre-existing
extra blank line at EOF when staged; the order's bytes and digest remained
unchanged.

The verifier remains absent from `pyproject.toml`, GitHub workflows,
application startup, packaging, Docker, and the supercomputer harness. No
package was installed. Redis 7.0.15 and the existing repository environment
were used; only the approved narrow disposable-PostgreSQL create/drop commands
required sudo.

Implementation-head GitHub checks at
`d43d62ea66fecc3efa0fec81675cc786ab8e3671`:

| Required check | Result |
| --- | --- |
| Analyze (javascript-typescript) | PASS |
| Analyze (python) | PASS |
| Analyze Python | PASS |
| CodeQL | PASS |
| Docker Compose smoke | PASS |
| Documentation hygiene | PASS |
| OpenAI-compatible E2E tests | PASS |
| Playwright browser smoke | PASS |
| PostgreSQL integration tests | PASS |
| Unit, lint, and migration head | PASS |

Fresh report-head checks are verified from GitHub after immutable report
publication; their external results cannot be written retroactively into this
SELF report.

## Acceptance criteria

1. PASS — every successful ledger/key reconciled exact nine-decimal Decimal
   component/native/EUR costs; reserved money was zero; failures matched the
   exact zero/null contract.
2. PASS — local exec required exact linked successful sentinel output, final
   text required the exact structured marker, edit required its file, and none
   persisted or printed.
3. PASS — unique failure-body sentinels did not persist; exact safe error
   types, statuses, and one-call paths remained.
4. PASS — database validation rejected query, fragment, whitespace/control,
   alternate-scheme, implicit-port, socket, host, and option override forms and
   accepted only the canonical numeric-loopback disposable target.
5. PASS — one shared helper verified 0700 directories, 0600 credential-free
   files, and portable guarded cleanup for every scenario.
6. PASS — the runbook contains one exact bounded command and remains
   PREPARED, NOT EXECUTED, requiring separate human authorization.
7. PASS — focused tests, final verifier, privacy/accounting/cleanup evidence,
   docs, and all implementation-head GitHub checks passed. Required fresh
   report-head checks are verified externally after publication. Broad local
   suites and real providers were not run as ordered.
8. PASS — only PR #236 was amended; no merge or auto-merge occurred; the final
   report commit is SELF and report-only.

## Changes and exact paths

Implementation commit `d43d62ea66fecc3efa0fec81675cc786ab8e3671`
changed exactly:

```text
AGENTS.md
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/configuration.md
docs/openai-compatibility.md
docs/runbooks/codex-openai-pilot.md
docs/security-model.md
docs/testing-parallelism.md
oap/active
oap/orders/011-b-tighten-gateway-e2e-proof.md
scripts/verify_codex_gateway_e2e.py
tests/unit/test_codex_gateway_e2e_verifier.py
```

The strategic order and active pointer were committed unchanged from the
activated inputs. Every earlier order/report remained byte-for-byte unchanged.
The report publication commit adds only:

```text
oap/reports/011-b-tighten-gateway-e2e-proof.md
```

Documentation updated: AGENTS.md, docs/codex-compatibility.md,
docs/compatibility-matrix.md, docs/configuration.md,
docs/openai-compatibility.md, docs/runbooks/codex-openai-pilot.md,
docs/security-model.md, and docs/testing-parallelism.md.

## Scope, omissions, and safety

- Scope deviation: NONE.
- Unexpected unrelated tracked modification: NONE.
- `.local-provider-catalog/` was not modified, staged, or committed.
- Full local unit, integration/PostgreSQL, OpenAI-client E2E,
  Playwright/browser, Docker/Compose, HPC, old manual Codex verifiers, and
  upstream-optional suites: NOT RUN, exactly as the work order required; broad
  routine coverage was delegated to GitHub CI.
- Real OpenAI/OpenRouter provider call: NOT RUN.
- Human bounded real-OpenAI pilot: PREPARED, NOT EXECUTED.
- Production/staging gateway or database access: NONE.
- Credentials searched for or printed: NONE.
- Real email: NONE (`ENABLE_EMAIL_DELIVERY=false`).
- `DATABASE_URL` destructive setup: NONE.
- Temporary DB deletion was limited to three validated literal generated test
  names; all were disposable and no recovery was required.
- New PR: NO. Existing PR #236 only.
- Merge: NO.
- Auto-merge: NO.
- Report publication commit changes only this immutable report: YES.

## Coding-agent conclusion

Objective 011-b's execution turn is complete. The tightened local verifier and
focused tests passed; implementation-head CI passed all ten checks; the real
provider pilot remains deliberately unexecuted; and the coding agent did not
merge or enable auto-merge. Strategic acceptance and any merge decision remain
with the strategic model/human maintainer.
