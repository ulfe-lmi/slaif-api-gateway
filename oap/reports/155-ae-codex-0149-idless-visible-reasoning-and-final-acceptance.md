# Objective 155-ae — Codex 0.149 ID-less visible reasoning and final acceptance

Date: 2026-09-02

RESULT=FAILED

This is the single immutable 155-ae diagnostic report. It records bounded
evidence only and does not establish product or release acceptance.

## Topology

- Repository: `ulfe-lmi/slaif-api-gateway`, PR #291,
  `oap/155-local-coding-signed-server-module`.
- Prior immutable report: `22a15fd65c24f655448d1547bdb275634483c8e9`.
- Activation head: `1420934e6d7df67f930bdc3cd6a8e1ffa32b6701`.
- Diagnostic implementation head: `956ec1e08b5f951f482ae12d0bbd265219bcadef`.
- This report is a report-only `SELF` commit whose first parent is the
  diagnostic implementation head above.
- No merge, release, cutover, 155-af activation, or product correction was
  performed.

## Implementation and source authority

The implementation is limited to the 155-ae allowed client-policy, verifier,
test, fixture, governance, and compatibility-document paths. No Local Coding
or Qwen file was changed. The peeled `rust-v0.149.0` tag resolved to
`758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`; the three ordered upstream source
paths and bounded field facts were independently checked.

The new canonical synthetic source-contract fixture is
`tests/fixtures/codex/0.149.0/responses-reasoning-dialect-v1.json` with digest
`d24178dc3467dfaf276b015dcf8298fcc1ddc35bc6c6dcd615f101c3e1cd76df`.
The 0.149 client retains module metadata version `3` for compatibility with
existing persisted policy rows; the new visible-reasoning policy revision is
explicitly `4` and is enabled only by the selected 0.149 policy spec and the
exact Local pair. No ID generation was added.

The visible mode accepts absent/null/present reasoning IDs, exact bounded
`summary_text`, `reasoning_text`, and `text` parts, and preserves valid UTF-8
including newline and tab characters. ID-less encrypted reasoning and all
legacy/default/0.147 paths remain strict.

## Tests and checks

- Affected client, policy, replay, streaming, payload, quota, verifier, and
  governance unit suites passed.
- Full Ruff, compilation, diff, source, fixture, and scope checks passed.
- PostgreSQL integration was first found failing because the module revision
  broke an existing literal version-3 metadata test; compatibility was
  restored without editing that out-of-scope test.
- All ten required PR checks passed on final diagnostic head
  `956ec1e08b5f951f482ae12d0bbd265219bcadef`.
- Normal fake two-turn qualification passed with two turns, one function
  lifecycle, one message lifecycle, and two accounting rows.
- Fake provider-failure and deliberate validator-rejection matrices both
  failed closed with bounded evidence and zero pending accounting.

## Single protected diagnostic

Exactly one protected task-local Codex 0.149.0 process ran. No retry and no
second protected process ran.

Safe boundary facts:

- Gateway emitted two requests/responses: first 2xx SSE, second 4xx JSON.
- Local received one request and returned one normal 2xx SSE response.
- Qwen received one inference request, returned one normal 2xx SSE response,
  and closed normally; compiler-call count was zero.
- The first request had bounded top-level tool classes custom=1, function=5,
  tool_search=1, web_search=1, with tool-choice class `automatic_none`.
- The second request was classified as
  `top_level_function_pair_without_additional_tools` and contained the
  adjacent function-call/function-call-output continuation in its bounded
  input-type projection.
- The second Gateway failure was only classified as code `other`, parameter
  root `input`, and parameter leaf `other`; no raw error text/body/value was
  retained.
- The state-bearing reasoning projection was type `reasoning`, content class
  nonempty array, encrypted-content class null, summary class empty array,
  exact allowed-key-set true, unexpected semantic fields false, and ID class
  absent.
- The one Local-bound signed projection passed service Bearer equality, exact
  required-header cardinality, canonical/raw-body participation, independent
  HMAC verification, route/method/path/query, timestamp/nonce shape, and no
  extra internal headers. Local tool-policy state was `transformed` and the
  Qwen/Local boundary states were successful for the one admitted turn.

The verifier returned fixed code `qualification_accounting_incomplete`.
Accounting actually showed one finalized reservation, one finalized ledger
row, zero pending state, and one terminal row. That is coherent for the one
request admitted before the second Gateway pre-admission rejection, but the
verifier's terminal-sequence predicate did not accept the one-turn
finalized/finalized case. Consequently the required two-turn acceptance was
not established, and no Local/Qwen ownership conclusion is claimed for the
second-turn Gateway failure. The qualification rejection artifact was absent;
there was no hook-free final run.

## Cleanup and privacy

The mode-0600 owner-only runtime reference was removed. The exact 155-ae task
roots, installed Codex files, summaries, processes, listeners, containers, and
named task database were absent after cleanup. The Local checkout remained
Git-clean with no task `.venv` or bytecode state.

No credential, endpoint, prompt, request/response body, raw header, canonical
bytes, timestamp, nonce, signature, ID, tool value, reasoning text, exception
text, or private artifact was persisted or included here. No protected retry,
hook-free final acceptance, merge, or product change is claimed.
