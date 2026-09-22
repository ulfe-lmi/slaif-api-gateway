# OAP Work Order — 181-c

## Objective and business reason

Continue Objective181 on SAME PR318. Make standard-v1 catalog eligibility agree
with the CURRENT ordinary Chat admission/accounting and route-policy contracts.
A value fitting a pricing TSV column does not mean the Gateway can safely bill
that shape. Correct the remaining three semantic gaps; do not change runtime
accounting or provider policy to make a proposal pass.

This is a bounded continuation, not a new PR or full181 closure. Transport,
actual-collection-versus-replay and exact tooling identity remain REQUIRED in a
later same-PR round (prospectively181-d). No182 activation while181 is unresolved.
The full182Codex/183atomicapply-accounting/184wrappers-E2E mandate is unchanged.

## Verified current state and authority

On2026-09-22T22:41Z (2026-09-23 local):
- GitHub main6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf, unchanged.
- Unique open PR318, branch oap/181-authoritative-catalog-collection, base main.
- PR/report headbcbc9c349cd463e1eb31927436a1a0f786e0d119; first parent
  109461ab428ec7efaf32b7a2625f13d559f2b856 is the implementation.
- Report-only head changes solely181-b report; implementation changes12allowed
  paths; worktree clean and file bytes independently matched Git objects.
- Active181-b; exact orderSHA256
  39c467d4abf2fc1fc1794170b7c33749ba11db41e279d255b343217cb629ee8f.
- Solehelper4075 returned RESPONSE_OK_EXACT/exit0 and is CLOSED.
- All10final-headCIchecksSUCCESS; PR CLEAN/MERGEABLE, no change-request review.
- Independent308focused tests pass; documentation checkerOK91files. Implementation
  diffcheckclean. The immutable181-breport has a trailing blank line atEOF; retain
  it as historical evidence, do not edit it for cosmetic diff-check cleanup.
- Main ruleset23580289 prohibits deletion/non-fast-forward; only releasev0.1.0-rc.1.
  No release/tag/production authority.

Read this complete order, repository constitution/coding protocol,181-b order and
report, current catalog-refresh contracts, relevant pricing/accounting/route/
hosted-tool code and compact architecture. Earlier fixes are preserved, reports
are immutable, GitHub is software truth. Required strategic evidence:
/home/ubuntu/codex-supervision/slaif-api-gateway/review-artifacts/181-b-review/
  identity.json, results.json, runtime_semantics_probe.py,
  runtime-semantics-results.json, hosted_probe.py, hosted-results.json.
Full requirement ledger:
/home/ubuntu/codex-supervision/slaif-api-gateway/workorders/CATALOG-REFRESH-IMPLEMENTATION-MANDATE.md
Do not read whole historical architecture without concrete need.

## Independent findings at the exact current head

Accepted progress: valid baseline-file collect now exits0; the disabled exact
alias preserves name/priority/visibility/streaming denial; long-context,
cache-write and override reproducers now BLOCK; index-only IDs are accounted.
READY_WITH_WARNINGS exit10 is correct;181-a's exit0 claim was a pipe measurement
mistake, not a reason to rewrite working exit semantics.

Unclosed findings:
1. Request fee: actual collect+validate marks READY with request0.1USD and
   output2.16USD/1M. Feed those exact proposed dimensions to the actual
   PricingService ordinary OpenRouter Chat estimate,1000output/0input:
   estimate0.00216 and local final components0.00216, omitting the0.1fee.
   The request column is used by other endpoint/native-module contracts, not
   additive ordinary Chat billing. Repositories were None (no DB); pricing and
   FX were explicit synthetic objects; no inference or actual ledger mutation.
2. Reasoning: READY with reasoning9USD/1M and output2.16USD/1M. Same actual Chat
   admission estimate reserves0.00216, while1000reasoning tokens yield local final
   components0.009. Carrying the column does not fix admission coverage.
3. Prefix route: baseline requested_model public/, match_type prefix,
   upstream_model synth/alpha, disabled/hidden/nonstreaming,priority77. Collector
   emits READY with a NEW enabled/visible/streaming exact synth/alpha at100.
   The production resolver uses upstream_model as fixed destination; comparing
   the public prefix only against upstream spelling misses this existing route.
4. Claimed unreachable hosted charges: synthetic synth/alpha:online with
   web_search0.01 produces READY and 'accepted unreachable' text; actual
   classify_chat_completion_capabilities returns no denial. Official OpenRouter
   documentation says the :online model suffix itself enables web search (though
   deprecated); omission of a tools field does not establish unreachability:
   https://openrouter.ai/docs/guides/routing/model-variants/online
   https://openrouter.ai/docs/guides/features/server-tools/web-search
   No provider call was made. This is a catalog-policy gap; no runtime hosted-tool
   fix is authorized here. Not every positive optional web-search price necessarily
   means a hosted operation will run, but the blanket assertion is unsupported.

A supplemental OpenAI unknown-surcharge-column probe already BLOCKed with
source_evidence_parse_failed; do not claim or fix a nonexistent acceptance bug.
Transport/capture concerns remain as explicitly deferred; do not claim closure.

## C1 — Conservative eligibility follows executable billing, not TSV capacity

Keep standard-v1 the reviewed flat core text Chat profile. For this round,
exclude positive per-request fees and positive separately published reasoning
charges from ready standard-v1 rows. They require an additional qualified billing
contract; none is authorized here. Do not increase core prices, rename a fee,
assume hosted-overrun authority, infer equal-price semantics, change runtime
reservation/finalization, or call a representable column proof of accounting.

The shared deterministic source eligibility decision must enforce this in BOTH
collector and supplied-bundle validator. Default discovery retains flat siblings
and explains excluded rows; an explicitly selected excluded model BLOCKs. Keep
original source observations/provenance; never overwrite them with invented prices.

Handle zero and missing distinctly. Preserve legitimate zero core prices and
cached prices; do not invent a positive fee. Document how a zero ancillary field
is interpreted under the source contract; a zero must not be silently treated as
missing if doing so changes actual local billing. If semantics are unknown,
retain explicit ambiguity and exclude rather than invent an interpretation.
Existing positive-request/reasoning 'carry' tests must become regressions for
refusal under standard-v1, not weakened assertions that the TSV has a column.
Other/native/legacy import and accounting behavior remains untouched.

## C2 — No blanket unreachable-hosted assertion

For this bounded profile, conservatively exclude positive hosted-operation
charges unless an already reviewed, executable per-model contract proves those
charges cannot be incurred. There is no such general contract merely because
profile text says hosted tools denied. Do not introduce new opt-in authority or
runtime model-name special cases in this round. The simplest authorized fix is
explicit exclusion of these rows with a concise aggregated reason.

Model variants or intrinsic hosted/search behavior must not be declared safe by
analogy with optional tools. Reuse existing pure classification where adequate;
otherwise retain an explicit unsupported/ambiguous disposition. Unknown requires
review/exclusion, not a confident no-hosted-capability claim. Supply exact source
and executable evidence for any exceptional row class you propose to retain; if
that requires a new runtime contract, STOP that subcase and exclude it.

Tests must cover :online/intrinsic-hosted-style identities and ordinary flat
siblings; copied source snapshots and caller-supplied inventory/warnings cannot
launder an excluded model into READY. All reasons stay in the single report.

## C3 — Fixed upstream wildcard routes retain local authority

Use both dimensions of the current routing contract: public match pattern and
resolved upstream destination. A prefix/glob with an explicit upstream_model
already controls that upstream even when public prefix and upstream ID differ.
Retain such unrepresentable local rows with explicit reasons and do not invent a
parallel exact route. Cover prefix and glob, disabled/hidden/denied cases,
multiple alternatives, and exact aliases. Preserve provider destination, priority,
visibility and denials. Do not reduce alternatives to one row.

Enforce this independently in supplied-bundle validation as well as generation:
reinserted parallel routes must BLOCK. A wildcard retained locally is not a
source disappearance. Do not broaden unrelated public-prefix rules to every
unconfigured model; base the relation on actual fixed/passthrough routing
semantics, not just string similarity. Existing-row changes remain create-only
BLOCKED until183; no route/import mutation is added.

## Exact allowed paths

- app/slaif_gateway/services/catalog_refresh/source_evidence.py
- app/slaif_gateway/services/catalog_refresh/collection.py
- app/slaif_gateway/services/catalog_refresh/validation.py
- app/slaif_gateway/services/catalog_refresh/rendering.py (semantic wording only)
- tests/unit/test_catalog_refresh_collection.py
- tests/unit/test_catalog_refresh_source_evidence.py
- tests/unit/test_catalog_refresh_policy.py
- tests/unit/test_catalog_refresh_report.py
- tests/unit/test_cli_catalog_refresh.py
- tests/fixtures/catalog_refresh/collection/ (bounded synthetic fixtures only)
- docs/catalog-refresh.md
- docs/cli-reference.md (catalog-refresh section only)
- admin/catalog-refresh/README.md
- oap/orders/181-c-close-catalog-runtime-contract-gaps.md (unchanged)
- oap/active (exact strategic bytes181-c)
- oap/reports/181-c-close-catalog-runtime-contract-gaps.md (new immutable report)

No other paths. Especially NO services/pricing.py, accounting.py, hosted_tool_policy.py,
route_resolution.py, DB/schema/migrations, import executors, dependencies,
Docker/Compose/NGINX/workflows, production scripts, Codex execution, final wrappers,
rootAGENTS/message.txt, historical evidence or .local-provider-catalog changes.
Read-only calls to existing runtime pure/service functions in focused tests are
explicitly allowed and required to demonstrate why the eligibility is conservative.

## Acceptance and verification

AP-C1: request/reasoning synthetic rows no longer produce ready standard-v1
proposals; flat complete sibling and one-model bootstrap still work. Shared
validator rejects injected candidates even with correct provenance/TSV shape.
Actual existing pricing/admission/component probes establish the unsupported
boundary without modifying it. Core zero, missing, unknown and conflicts retain
honest distinct outcomes. No fee/FX/limit inference.

AP-C2: hosted-charge/implicit-variant reproducers refuse ready rows, with accurate
aggregate report reasons and no unsupported 'unreachable' assertion. No tool
permission is granted, no runtime policy changed, no provider inference.

AP-C3: fixed-upstream prefix/glob retain authority through actual collector ->
validator -> artifact plan; supplied parallel bypass rejects. Exact-alias and
multiple-route regressions remain green; no false model-disappeared event.

AP-C4: focused catalog/source/policy/CLI/seal/proposal regressions, docs checker/
links, Ruff, git diff --check against this round's starting report, ordinary CI.
Tests use mocked HTTP AND DNS across ALL CLI tests, not only the new helper;
fixture time/freshness is deterministic across a UTC date boundary. No full local
DB/Redis/Docker/HPC/browser matrix is needed for semantic-only wording; no layout
redesign. Preserve the passing CLI0/10/20 and baseline identity evidence.

## Setup, boundaries, report and publication

Use existing .venv and owned scratch outside repo. No package/system changes,
.env/protected/saved-auth reads, inherited production URL, shared5432 or any live
DB mutation. Existing runtime probes use explicit synthetic pricing/FX and no DB.
PostgreSQL remains quota/accounting truth; no repricing historical usage, no apply,
no provider/owner/key mutation, no secrets/content in artifacts. No real inference,
Codex, email, production access, tag or release. Public authoritative read-only
GETs remain authorized as in181-a if needed for a source contract; mocks suffice
for this correction. Transport assurance is not closed by such a smoke.

Update current docs/report claims precisely.181-b stays immutable; explain its
remaining TSV-versus-runtime and wildcard gaps in the new report. Do not claim
allB1–B4 or181 closed merely because tests pass. Record exact start/implementation
SHA, exact paths, actual commands/exit codes, positive/negative/runtime-boundary
proofs, no-runtime/dependency/deployment diff, cleanup, documentation-impact
statement, CI and remaining transport/capture/full182–184 obligations.

Commit strategic order/active bytes unchanged on the existing branch/PR318.
Publish implementation then exactly one immutable report-only SELF commit whose
first parent equals the literal implementation head. Verify it is remote PR head
before exact two-byte responseOK. Never merge/auto-merge or open another PR.
After report/response, launch the control waiter targeting verified coding pane%3,
never strategic pane%2. Await next strategic order; permanent startup is unchanged.
