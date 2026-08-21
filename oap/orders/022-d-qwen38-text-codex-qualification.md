# OAP Work Order — 022-d

PR mode: `CONTINUE_EXISTING_PR`

## Objective and reason

Harden the successful Objective 022 hermetic candidate and replace the fake
live path on PR #248. The 022-c phase genuinely ran Codex 0.148 through SLAIF
and a loopback provider, but strategic review found an unsafe authority-scan
bypass, under-specified fixture/accounting evidence, a stale mocked-qualification
flag, and a direct-to-vLLM “live” request that bypasses Codex/SLAIF.

Implement immediately in focused slices. Do not repeat the now-proven database,
version, or broad repository discovery. Run the existing hermetic phase after
the corrections.

## Verified continuation state

- `main` remains `4ad592e190f6bfa1a8878814519569b6ce7e59a2`.
- PR #248 is the unique Objective 022 PR. Remote/report head is
  `e3e7b2b8a2ee084159ae7df22ee972ff9046aca9`; first parent implementation is
  `b8d7a607eee1641d3fe832abae2256e09fc63ebc`; report commit changes only
  `oap/reports/022-c-qwen38-text-codex-qualification.md`.
- Actual hermetic evidence passed: installed Codex 0.148.0, private PostgreSQL
  16, private Redis, real SLAIF, numeric-loopback generic provider, two
  requests, executed workspace marker, final marker, zero pending reservations,
  and privacy scan.
- Candidate remains outside the production registry and live variables remain
  absent. No LAN call is authorized in this round.
- One review thread remains unresolved for dual import style in the verifier.
- `oap/active` is `022-d`. Amend PR #248 only; never merge or auto-merge.

## Allowed paths

Use only the smallest needed subset of the existing Objective 022 paths,
especially:

```text
app/slaif_gateway/services/codex_profile_registry.py
app/slaif_gateway/services/responses_request_policy.py
app/slaif_gateway/services/responses_gateway.py
scripts/verify_qwen38_text_codex.py
scripts/verify_codex_gateway_e2e.py
tests/fixtures/codex/0.148.0/qwen3.8-27b-text-api-key-responses.json
tests/unit/test_qwen38_text_codex_candidate.py
tests/unit/test_responses_request_policy.py
tests/unit/test_responses_codex_client_tools.py
docs/codex-compatibility.md
docs/configuration.md
oap/orders/022-d-qwen38-text-codex-qualification.md
oap/reports/022-d-qwen38-text-codex-qualification.md
```

No migration, admin/RBAC, vision, external/hosted-tool, or unrelated provider
path.

## Required corrections

### 1. Remove the Codex 0.148 authority bypass

- Delete the behavior where `codex_client_tool_taxonomy=codex_0_148` causes
  `_contains_recursive_codex_authority_marker()` to be skipped. The exact
  namespace/tool names already identify the finite 0.148 taxonomy; do not add a
  gateway-key metadata escape hatch whose effect is to weaken validation.
- From one bounded hermetic capture, identify only the normalized **key paths**
  in exact Codex 0.148 schemas that trigger the existing scanner. Commit no
  descriptions/schema content. Add the minimum explicit allowed-key paths per
  exact namespace/tool, analogous to the existing request-user-input `header`
  exception, and apply the recursive scanner to every tool in both taxonomies.
- Even under the 0.148 taxonomy, injected `server_url`, connector, auth,
  authorization, headers outside an exact reviewed local field, secret,
  approval, hosted/MCP/search/computer/image-generation type, or nested variant
  must fail with the existing fixed authority error. Add table-driven negatives
  across every 0.148 namespace/tool and at nested schema/description positions.
- Keep the exact taxonomy, schema complexity/byte limits, route+key Codex gates,
  and local tool distinction. Do not enable provider-hosted authority.

### 2. Make candidate/catalog privacy claims honest

- The Codex 0.148 parser required bounded model display/description/reasoning
  labels. Validate those nested strings with the same URL/secret/control/length
  checks; do not allow arbitrary instruction/message objects. Keep
  `base_instructions` empty-only and availability/upgrade/model-messages
  null-only for this safe schema.
- Require coherent catalog claims: search false, parallel false, text-only,
  no freeform patch, no remote compaction/reasoning replay. Add drift negatives.
- Since the actual hermetic phase passed, set the unregistered candidate's
  `mocked_qualification=true`; keep `live_qualification=false` and keep it out of
  `CODEX_PROFILE_REGISTRY`/route/CLI/admin selection.

### 3. Replace summary fixture and partial accounting checks

- Generate the fixture from observed safe request facts and the exact scripted
  SSE/tool sequence used in the successful run. Record, through the finite
  sanitizer, the two request phases, actual ordered event type sequence,
  function-call/tool-output continuation structure, stable placeholder ID/call
  relationships, taxonomy ID, route/key gate booleans, catalog facts, and
  credential-boundary booleans. Fixed counts alone are insufficient.
- Derive all counts from observed mock facts/actions. Re-run the phase and pin
  the candidate fixture SHA to the generated file.
- Verify exact known final usage for both requests: key tokens/requests/cost,
  two finalized reservations/ledgers, successes/statuses, zero reserved totals,
  ledger/key agreement, and zero pending. Use local-zero complete Codex pricing
  metadata or exact nonzero component math; do not seed empty pricing metadata.
- Before Codex starts, run qualification inspection against the injected
  registry and prove exactly one ready candidate Responses route. Make the key
  local-tool allowlist equal the candidate's exact `local_tools` tuple.
- Preserve executed file/tool/final markers, loopback-only peers, auth
  substitution, upstream model rewrite, and durable canary scan.

### 4. Replace direct backend “live” call with the real product path

- Remove the direct `httpx.post(<LAN>/responses)` implementation. The live
  runner must reuse the bounded disposable PostgreSQL/Redis/SLAIF/Codex
  orchestration, configuring the provider row with the validated LAN base URL
  and a dedicated server-side env-var containing the supplied key. Codex talks
  only to SLAIF; SLAIF rewrites the public model to `qwen3.8-27b`.
- The real model must cause the ordinary local file-marker tool turn and final
  marker under the same finite route/key limits. Require final supported usage,
  exact accounting/reservation/privacy checks, no redirects/retries, and safe
  failure. `REAL_PROVIDER_CALLED=true` is emitted only after an observed
  backend-bound SLAIF call plus successful accounting.
- With variables absent, run hermetic only and report live absent. With present
  variables, run hermetic then live in that order. Add a **real local plumbing
  test** that exercises the live-runner branch against a separately configured
  numeric-loopback target; this is plumbing evidence, not Qwen qualification.
- Emit exactly one unambiguous `LIVE_QUALIFIED` line. While the candidate is
  unregistered in this PR, a live evidence pass may report
  `LIVE_EVIDENCE_PASSED=true` but must not simultaneously emit false and true or
  claim production registration. Actual human-LAN evidence will authorize the
  final promotion continuation.

### 5. Cleanup and review

- Remove the process-wide child `HOME` override; use isolated `CODEX_HOME` and
  task-specific variables without altering the inherited home variable.
- Fix the dual-import review finding and resolve the thread only after the code
  is obsolete. Check for new threads.

## Non-goals

No actual LAN call while variables are absent, profile registration, vision,
Chat translation, hosted/MCP/search authority, parallel calls, freeform patch,
encrypted reasoning, remote compaction, schema migration, release claim, or
full local suite.

## Acceptance and verification

1. No 0.148 branch skips recursive authority scanning; exact legitimate schemas
   pass and injected authority/hosted shapes fail under the same taxonomy.
2. Candidate is mocked-conformant/unregistered/live-false with coherent safe
   catalog facts.
3. Re-run hermetic phase passes and produces a meaningful observed fixture plus
   exact PostgreSQL key/ledger/reservation/cost/token evidence.
4. Local plumbing exercise proves the live runner uses Codex→SLAIF→configured
   target, not direct HTTP; present/absent orchestration and output are
   unambiguous and non-reflecting.
5. Run focused policy/candidate/verifier tests, hermetic phase, one live-runner
   loopback plumbing phase, scoped Ruff/compileall, `git diff --check`, and
   routine GitHub CI. No full local suite.

## Publication

Commit implementation, then publish one immutable
`oap/reports/022-d-qwen38-text-codex-qualification.md` report-only final commit
with literal implementation head and `Report publication commit: SELF` on PR
#248. Report authority-path/negative evidence, exact hermetic and plumbing
commands/results, fixture SHA, accounting facts, candidate state, live-variable
absence, review threads, focused tests, and final-head checks. Verify remote
head, signal exact response-FIFO `OK`, and return to one control wait. Never
merge.
