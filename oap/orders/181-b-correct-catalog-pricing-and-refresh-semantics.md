# OAP Work Order — 181-b

## Correct catalog pricing eligibility and refresh preservation

## Objective, reason, and PR mode

Continue Objective181 on the SAME PR318. A trustworthy short administrator
review requires complete eligible pricing and faithful comparison with local
policy. Green CI is insufficient when the collector omits billable dimensions
or proposes a new enabled route in place of a disabled local alias.

This round closes the semantic collection/refresh findings below. It does not
close Objective181 by itself: trusted transport and actual-capture/replay identity
still require a later same-PR continuation. Do not merge, enable auto-merge, open
a new PR, or activate182. The full human mandate remains one refresh command ->
one self-contained report -> one explicit audited apply, with182 Codex isolation,
183 atomic pricing/FX supersession/accounting,184 final wrappers and qualification
still REQUIRED. These later boundaries are not implemented in this round.

## Verified starting state and required reading

Strategic reconciliation on2026-09-22:
- Canonical GitHub main6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf.
- Unique open PR318, branch oap/181-authoritative-catalog-collection, base main.
- PR/report head32d3e91113046425cb71ce1a048e4bc1a0b54cca, first parent
  d0a6fc90c91a3d4074ec522152decac7eeaa7e17. Publication commit changes only
  oap/reports/181-a-authoritative-catalog-collection.md.
- Active181-a; its immutable order SHA256
  e0ce0b322b86c84e66250740c5b6be295296e5eadbc8e9cd17064809fa752f98.
- Sole response helper85027 completed exactRESPONSE_OK_EXACT/exit0; closed.
- All ten current report-head checks SUCCESS, PR MERGEABLE/CLEAN, no change-request
  review. Shared worktree clean. CI does not resolve the findings below.
- Main deletion/non-fast-forward protection23580289 active; only published release
  v0.1.0-rc.1. No release/tag/production authority.

Read this complete order, repository AGENTS/coding protocol,181-a order/report,
current catalog-refresh and provider-catalog proposal/import contracts, relevant
route/pricing/accounting contracts and compact architecture. Strategic evidence:
/home/ubuntu/codex-supervision/slaif-api-gateway/review-artifacts/181-a-review/probe.py
/home/ubuntu/codex-supervision/slaif-api-gateway/review-artifacts/181-a-review/results.json
/home/ubuntu/codex-supervision/slaif-api-gateway/workorders/OBJECTIVE-181-PROVISIONAL-REVIEW.md
/home/ubuntu/codex-supervision/slaif-api-gateway/workorders/CATALOG-REFRESH-IMPLEMENTATION-MANDATE.md
These are diagnostic inputs, not replacement runtime truth or prewritten tests
to copy without understanding. Do not load full architecture/history absent need.

## Independently reproduced failures at the exact starting head

Synthetic official-format fixtures and HTTPX mock transport; no DB/provider
inference/live network. Strategic Python probe used the actual collector,
validator and Typer CLI, owned disposable paths, fresh ECB publication date:

1. OpenAI gpt-syn-1: short input/output0.54/2.16, long1.08/4.32, documented
   context1000000. Explicit selection produced READY, no warnings, full context,
   and only short input/output/cached_input dimensions. No enforced short-context
   restriction justifies flattening.
2. OpenRouter synth/alpha independently with positive input_cache_write,
   internal_reasoning, request, or a supported-shaped overrides array with
   min_prompt_tokens200000 and higher prompt/completion prices: each produced
   READY with only core dimensions. Capturing an observation is not enforcing it.
3. Actual collect --refresh --baseline-file against a valid canonical digest
   returned20/BLOCKED baseline_target_mismatch: collector declares
   127.0.0.1:5433/slaif-collect-test, finalizer compares slaif-collect-test.
4. Baseline public-alias -> synth/alpha, disabled/invisible/nonstreaming,
   priority77, explicit streaming denial: collector proposed NEW enabled/visible/
   streaming synth/alpha at100, reported the alias disappeared. This is not
   preserving local policy or matching upstream disappearance.

Also reproduced but DEFERRED within181 to the next semantic-independent round:
- offline review of an intact collected bundle, with network forbidden, claims
  live_collection and 'live collection performed by this invocation'; presence
  of caller-supplied CollectionIdentity is not measured execution evidence;
- mixed public+loopback DNS accepted; arbitrary non-registry path/query on an
  approved host accepted. Static transport budget/connection-binding/decompression
  concerns and package-version-only code identity remain open.

No claim is made that every extra source field is billable in every profile;
that decision must follow explicit source and current runtime contracts.
The prior report says OpenRouter EUR; actual code/source is USD. Correct the
new report/docs, NEVER relabel correct USD code to match that historical typo.
An exit-code defect is not yet independently established; test actual0/10/20
outcomes instead of assuming the report's RWW/exit0 statement is correct.

## Exact allowed paths for this round

- app/slaif_gateway/services/catalog_refresh/collection.py
- app/slaif_gateway/services/catalog_refresh/source_evidence.py
- app/slaif_gateway/services/catalog_refresh/validation.py
- app/slaif_gateway/services/catalog_refresh/bundle.py (only necessary route/
  pricing identity projection; preserve existing artifact and import boundaries)
- app/slaif_gateway/schemas/catalog_refresh.py (only necessary typed eligibility,
  inventory and baseline/route identity observations; deliberate compatibility)
- app/slaif_gateway/cli/catalog_refresh.py (baseline identity/semantic pipeline
  and accurate exit/stage reporting only)
- app/slaif_gateway/services/catalog_refresh/rendering.py (accurate eligibility/
  inventory/retained-alias details only; no layout redesign)
- tests/unit/test_catalog_refresh_collection.py
- tests/unit/test_catalog_refresh_source_evidence.py
- tests/unit/test_catalog_refresh_bundle.py
- tests/unit/test_catalog_refresh_policy.py
- tests/unit/test_catalog_refresh_report.py
- tests/unit/test_cli_catalog_refresh.py
- tests/fixtures/catalog_refresh/collection/ (bounded synthetic current-format
  source fixtures only; no credentials, private baseline or whole web corpus)
- docs/catalog-refresh.md
- docs/cli-reference.md (catalog-refresh section only)
- admin/catalog-refresh/README.md
- oap/orders/181-b-correct-catalog-pricing-and-refresh-semantics.md (unchanged)
- oap/active (exact strategic bytes181-b)
- oap/reports/181-b-correct-catalog-pricing-and-refresh-semantics.md (new only)

No other paths. No runtime pricing/accounting/forwarding/import execution,
DB models/migrations, dependencies, Docker/Compose/NGINX/workflows, production
scripts, provider/owner/key mutation, Codex execution, shell wrappers, rootAGENTS,
message.txt, historical reports/orders or .local-provider-catalog changes.
Transport/capture fixes stay for the next same-PR round; do not quietly broaden.

## B1 — Shared, independently enforced pricing eligibility

Derive a deterministic eligibility decision from ALL relevant authoritative
observations and billing contexts before proposing a row. Reuse that semantic
policy in validator recomputation: a supplied/tampered canonical bundle must not
bypass eligibility merely by removing extra dimensions from the proposal.

- Preserve Standard/Batch/Flex/Fast, text/other modality and short/long contexts.
  Models with unsupported contextual prices must be explicitly excluded; if the
  administrator explicitly requires such a model, BLOCK. Do not choose a cheaper
  band and expose the whole model context, silently clamp observed limits, assume
  unenforced request constraints, or add runtime support in this round.
- Recognize positive extra charges, unknown billed keys/units and published
  contextual overrides. Parse supported JSON/stringified JSON structures strictly;
  no regex-only acceptance of arbitrary override text as harmless zero blocks.
  Missing, negative sentinel, malformed, nonfinite, conflicting and ambiguous
  values remain fail-closed. Legitimate zero stays zero, not missing.
- Current standard-v1 remains flat core text Chat. Do not silently drop request,
  cache-write or distinct reasoning charges that can be exercised. Conservatively
  exclude unrepresentable billing. An out-of-scope dimension may be ignored ONLY
  under an explicit tested policy that current profile/runtime denial makes it
  unreachable (e.g. a denied hosted operation), with the exclusion evidence shown.
  A schema column existing somewhere does not prove end-to-end accounting support.
- Keep flat, complete siblings usable in default discovery; aggregate exclusion
  reasons into the one report and reconcile counts. Unsupported row exclusions
  must not claim the whole provider has failed. Empty usable bootstrap BLOCKs.
- Do not infer FX, prices, units or permissions. Native USD and existing exact
  Decimal ECB reciprocal/date/freshness contracts remain unchanged.

## B2 — Real refresh identity and route-policy preservation

Correct the baseline target representation consistently without weakening the
content-digest/target checks. The target's host/port/database identity is already
inside the hashed baseline: preserve that binding and reject substituted baseline
content. Test the actual CLI path, not only collect_bundle -> validate_bundle.

Match authoritative provider/upstream/endpoint facts to existing LOCAL route
identities. Preserve public aliases, match type, priority, enabled/visibility,
streaming and every approved denial. Multiple aliases/priorities must never be
silently reduced by setdefault to one row. Do not invent a new upstream-named
route because an alias exists. Keep provider destinations unchanged.

If current proposal representation cannot faithfully represent a baseline route
(prefix/compound capabilities/multiple alternatives), retain the local row with
an explicit deterministic reason, and do not propose a parallel route that
bypasses it. Do not manufacture permission by treating 'not representable' as
'not present'. Block an explicit requested modification that cannot be safely
represented. New genuinely unconfigured model exposure must remain visible in
the report under the existing conditional allow-all-key warning contract.

An alias remaining mapped to a present upstream is not a disappeared upstream
model. Source disappearance is retain-local/REVIEW, never deletion; a source
retrieval/parse failure is not disappearance. Existing row changes stay BLOCKED
until183; no apply/supersession is added here.

## B3 — Complete inventory and honest semantics

Audit inventory construction, including the retrieved OpenAI models index.
Current collection primarily iterates standard pricing rows; the index parser
can produce zero models from actual linked-index format. Every in-scope observed
model ID in official source snapshots must receive exactly one explained
source disposition, including index-only/no-price IDs. Distinguish source model
counts from local route/alias counts. Do not call pricing rows the entire official
model catalog or silently ignore an index that was fetched as model evidence.

Use bounded deterministic current-format identity/link extraction; no arbitrary
URL fetching or new transport authority. Retain unresolved facts for182 research,
without pretending Codex ran or guessing missing information. Source failure and
no parseable inventory must be visible, not silently treated as a complete empty
source. Recompute supplied inventory claims against parsed observations.

Update current docs to explain exact flat eligibility, preservation and command
stages. Correct broad claims from181-a in the NEW report, leaving181-a immutable.
Clearly distinguish implemented collection refresh from missing atomic apply.
Do not claim transport/capture-identity closure in this round.

## Acceptance and focused verification

AP-B1: all strategic monetary reproducers refuse a ready selected row; supported
flat siblings still produce usable proposals; explicit unsupported selections
BLOCK. Add bypass negatives through normal supplied-bundle validation, not only
collector unit tests. Show malformed/unknown/zero/equal-vs-distinct context cases
and the exact policy reason for any intentionally accepted extra dimension.

AP-B2: real collect CLI --refresh --baseline-file -> validator -> sealed report
-> verify succeeds for a fresh unchanged representable baseline; actual changed
pricing is correctly BLOCKED by existing create-only semantics. Wrong digest/
target substitution rejects. Alias, two aliases, priority alternatives, disabled,
hidden, streaming-denied, prefix and unrepresentable contracts retain authority;
no accidental additional upstream-named enabled route. No live database needed.

AP-B3: index-only/pricing-only/explicitly filtered/source-outage/current-alias/
true-disappearance scenarios reconcile without silent row loss or false removal.
All details remain in ONE report; no extra administrator homework.

AP-B4: pin actual CLI exit statuses READY0 / READY_WITH_WARNINGS10 / BLOCKED20,
including semantic-blocked collect stage wording. Eliminate calendar/DNS-sensitive
unit evidence: tests use coherent injected/frozen clocks and fully mocked DNS/
HTTP, and meaningful freshness-boundary tests; no live DNS in unit CLI tests.
A test passing once after unexplained flakiness is not its diagnosis.

Run the focused changed catalog/source/CLI/route-projection regression suites,
Ruff, documentation checker and internal links, git diff --check, and ordinary
CI. No full local DB/Redis/Docker/HPC matrix or new browser matrix is required
for unchanged layout/runtime. If renderer semantics change, a targeted report
assertion suffices here; full changed-collection browser proof remains181 closure.

Live unauthenticated official source GET smoke remains authorized as in181-a,
bounded to selected provider source/model pages and ECB. Prefer mocks while
transport is pending; any live smoke must explicitly disclaim unclosed transport
assurance. No real inference, Codex invocation, provider credentials, production
DB or email. Do not claim final181 public qualification before later fixes.

## Setup, report, publication and synchronization

Use existing .venv/httpx/stdlib and owned temporary directories outside repo.
No package/system changes, .env or saved-auth/protected reads, shared5432 access,
privileged postgres identity, inherited production URL use or unrelated cleanup.
No new DB mutation authority. PostgreSQL remains runtime/accounting truth; no
usage repricing/history modification; source strings are data, never commands.
Keep private test inputs/seal key out of Git/logs and clean owned resources.

Commit this exact strategic order and active bytes unchanged; amend PR318.
Publish implementation first, then exactly one immutable report-only SELF commit
whose first parent is the literal implementation head. Report exact starting/
implementation SHA, changed paths, eligibility/preservation decisions, measured
commands/results/exit codes, negative/privacy/accounting/no-runtime-diff evidence,
documentation-impact statement, remaining transport/capture findings, and CI.
Correct earlier overclaims explicitly without editing historical evidence. Do not
mark all181 APs closed or the full human goal complete on this narrower round.

Verify report-only topology and remote PR head before exact two-byte responseOK.
Never merge or enable auto-merge. Await strategic continuation. Explicitly target
verified coding pane%3 when launching the subsequent control waiter; do not use
strategic pane%2. Permanent startup authority remains objective-neutral.
