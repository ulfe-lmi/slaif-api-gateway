# OAP Work Order — 180-b

PR mode: `AMEND_EXISTING_PR`

## Objective and reason

Correct the offline review trust/accounting/privacy defects found by independent
strategic review of 180-a. Keep one PR for Objective 180. The full goal remains
one refresh, one trustworthy review artifact, and one explicit audited apply;
181–183 remain subsequent work, not a substitute for truthful 180 readiness.

The 180-a report is immutable. Its PASS claims are not accepted where they
contradict the probes below. Do not edit that report; publish corrections and
new evidence in 180-b. This is correction of the existing offline subsystem,
not permission to add live research, supersession, or mutation here.

## Verified live state

Verified 2026-09-22 after exact response OK from the sole helper session 48664:
- Repository `ulfe-lmi/slaif-api-gateway`; main remains
  `b1e6ef0a49d7e5ab6376f6344290f58ff844e671`.
- Unique open PR #317, base main, branch `oap/180-catalog-refresh-bundle-review`.
- Final 180-a PR/report head `7afa476943b9b254d47fbabe2007a7e2b4c862e4`;
  first parent `75af092743f1f4c7ce0832b2bd5b704ff1438715`. GitHub confirms
  that publication commit changes only the 180-a report.
- Implementation `c24f079082ca555374e6fb2343b6d775113dc7d6` followed by
  75af092 test-port fix. All ten implementation-head checks passed; fresh
  report-head checks were pending at initial review. Query current state.
- Active before this activation `180-a`; tracked tree clean; strategic order
  hash remains 540a263c640b9c8fc1856105750270d3ccf90f2eeb11483d5d011ed7d0a6ddd0.
- Independent draft tests: 94 unit tests passed; 7 PostgreSQL tests passed
  against an independently created/dropped safe test DB. These selections do
  NOT cover all the failures reproduced below. Existing bot comments on c24f079
  also identify dead assignments/unused locals; inspect and address relevant
  ones while touching the affected code, without weakening checks.

Read this order, 180-a, current repository/OAP contracts and the relevant code.
Continue the SAME PR from 7afa476; no new branch/PR/objective. Coding agent
never merges or enables auto-merge. Commit this strategic order/active unchanged.

## Allowed paths

- `app/slaif_gateway/schemas/catalog_refresh.py`
- `app/slaif_gateway/services/catalog_refresh/` (existing bounded subsystem;
  offline source evidence validation, baseline, policy, rendering, sealing only)
- `app/slaif_gateway/cli/catalog_refresh.py`
- `app/slaif_gateway/cli/main.py` (only necessary offline-group integration)
- `admin/catalog-refresh/README.md`
- `docs/catalog-refresh.md`
- `docs/cli-reference.md`
- `tests/unit/test_catalog_refresh_bundle.py`
- `tests/unit/test_catalog_refresh_policy.py`
- `tests/unit/test_catalog_refresh_report.py`
- `tests/unit/test_catalog_refresh_seal.py`
- `tests/unit/test_cli_catalog_refresh.py`
- `tests/integration/test_catalog_refresh_baseline.py`
- `tests/fixtures/catalog_refresh/` (synthetic fixtures and current screenshots)
- `oap/orders/180-b-correct-offline-review-trust-and-accounting.md` (unchanged)
- `oap/active` (unchanged strategic bytes `180-b`)
- `oap/reports/180-b-correct-offline-review-trust-and-accounting.md` (new)

No other paths. No existing import executor, pricing/accounting/runtime API,
DB schema/migration, dependencies, workflow, Docker/Compose/NGINX or historical
record change. No live source fetch/Codex invocation/application of a plan.
Refactor this unmerged new subsystem where useful; retain useful functionality
and validator reuse, do not paper over problems with more duplicated rules.

## R1 — Overall readiness must reflect executable plans

Reproducer at 75af092: load `bundle-refresh-ready.json` and
`baseline-synthetic.json`, then validate_bundle. It returns overall READY
although route and pricing plans EACH have ready=1, blocked=2, and gate text
says apply plan blocked until 182. Overall state ignores REVIEW gate results
when no Warning object is present. This violates 180-a requirement 13.

- Derive one consistent gate/issue/state model. Any actual blocked proposed
  mutation makes overall BLOCKED; any REVIEW gate makes at least
  READY_WITH_WARNINGS. Blocker/warning counts include gate failures, not only
  the separate warning list. Never show BLOCKED with zero blocking issues.
- Separate genuinely unchanged rows (no-op, excluded from mutation plan) from
  actual changed rows requiring currently unsupported update/supersession.
  A true no-change refresh can be READY/NO CHANGES with zero mutations; do not
  call duplicates updates or send them into create-only executors. Real
  unsupported changes remain BLOCKED until 182 implements them.
- Produce artifacts for permitted intended operations; excluded/unsupported
  rows must not leak into ready import artifacts. Preserve full catalog facts
  and excluded rows in the canonical bundle/report, not in executable deltas.
- Pair pricing with routes by effective provider + UPSTREAM model + endpoint;
  public aliases need not equal upstream IDs. Test aliases and provider/model
  collisions, not only fixtures where all names happen to match.
- Maintain non-degenerate positive cases: valid bootstrap/create-only and true
  no-change refresh must work. Marking everything blocked is not a solution.

## R2 — Correct FX direction and baseline price semantics

Exact independent probe: take first-install fixture, set selected prices and
dimensions to USD, add EUR->USD=1.08. Current output is READY and emits only
that pair. Replace it with USD->EUR=0.925925926: current output is BLOCKED with
fx_missing_required_pair. Runtime PricingService.convert_to_eur instead calls
find_latest_rate(base_currency=native_currency, quote_currency=EUR).

- Canonical import-ready FX must match runtime: native currency -> EUR. Keep
  original EUR-based source quotations distinct from normalized import facts.
  If conversion is supplied, calculate and record its reciprocal deterministically
  with Decimal and explicit precision; never silently relabel a direction.
  Live ECB fetching remains 181, but offline fixtures/validator/output must be
  correct now. Verify emitted FX with real existing import validators and a
  disposable PricingService.convert_to_eur lookup demonstrating expected EUR
  cost, including reciprocal/double-inversion negatives.
- A missing required conversion, currency mismatch, ambiguous/unknown unit,
  contradictory rate, missing indispensable provenance/date or expired required
  rate cannot become READY. All-EUR selected prices correctly report FX N/A.
- Baseline current-price/rate selection must mirror active lookup: exclude
  disabled pricing, respect valid_from <= as-of < valid_until, and do not
  fall back to expired/future rows when no active row exists. Show history
  separately. Detect ambiguous overlapping active rows rather than inventing a
  before value. Compare currencies before calculating deltas; divide-by-zero
  transitions are explicit, not percentages.
- Align documented threshold boundaries and tests (180-a says age >24h REVIEW,
  >72h BLOCK; FX >3 calendar days REVIEW, >7 BLOCK). Explain reference time for
  deterministic offline rendering and distinguish it from fresh execution-time
  validation; future apply will recheck freshness using its current clock.
- Ensure monetary inputs/normalization are bounded and representable for the
  actual import/database contract; reject hostile huge exponent/precision values
  before expensive formatting/arithmetic. Do not test with unbounded allocations.

## R3 — Source provenance must support the claimed facts

Independent probe at c24f079/75af092: replace EVERY source URL in the valid
first-install fixture with https://example.invalid/fabricated-pricing. The
result remains READY with zero warnings. Renderer calls every link
"authoritative source". Current contradiction loop compares context_length
from aggregated model records, not independent source-specific pricing facts;
different input/output/cached price observations cannot be checked by it.

- Remove caller-supplied authoritative/deterministic labels as authority.
  Derive provenance classification from provider/method/domain rules and actual
  supporting evidence. Enforce exact official hosts/allowed methods; reject
  lookalike hosts, credentials/unsafe URLs and mismatched provider/source kinds.
  A safe URL syntax is not an authoritative source. Operator-supplied/manual
  or singly semantic observations must be labeled REVIEW as appropriate, never
  automatically VERIFIED. Unsourced/ambiguous required values block.
- Preserve per-source, per-field observations with values, units, currencies,
  model/endpoint identity and their supporting snapshot/locator. Required
  pricing dimensions and limits must be traceable to those observations;
  do not invent values from related models or source labels.
- Compare independently represented observations for each billed dimension,
  currency/unit and required capability/context fact. Disagreement in required
  authoritative facts is BLOCKED, not selected by LLM confidence. Two references
  to the same evidence are not independent corroboration.
- Bind underlying supplied evidence bytes/digests to the run where they are
  claimed to be verified; a declared content_sha256 without accessible matching
  evidence cannot prove that verification occurred. Reuse existing deterministic
  parsers where applicable on offline snapshots; no live fetch or new research
  in this round. Explicitly distinguish supplied/cached evidence from a live
  retrieval this process did not perform. 181 will supply real collection.
- Source inventories, selection and dispositions must reconcile independently
  with evidence, not merely define considered as the sum of output counters and
  assert the same equation. Test a dropped candidate, truncated source,
  duplicated ID, missing mandatory selected model and scoped selection. Every
  excluded row needs a deterministic reason; disappearance is retain-local.
- Keep typed interfaces suitable for OpenAI, OpenRouter and independent FX
  sources. FX provenance must not borrow an unrelated model's OpenRouter source
  reference just to satisfy the schema. No source can broaden runtime support.

## R4 — Baseline privacy and truthful SQL/integrity claims

Independent pure probes: `_redact_notes` preserves the entire synthetic string
"Synthetic private customer conversation content: sample only." and
`_redact_free_metadata({'unrelated_context': same_string})` retains it. Regex
secret redaction is not an allowlist for unrelated request/personal content.

- Remove free-form notes/unrelated metadata from default export/report. Use
  field-specific allowlists for semantically necessary capability/pricing facts;
  preserve financial meaning and provenance without leaking unrelated content.
  Do not silently truncate financially material metadata to satisfy bounds:
  fail with a safe explicit issue or retain a safe opaque comparison fingerprint
  where justified. Never overwrite underlying DB rows.
- Validate/handle secret-bearing provider/source URL components safely. Do not
  export credentials, query tokens, freeform secret values or unrelated data;
  keep required provider environment-variable NAMES only. Avoid claiming
  universal PII detection for arbitrary text; exclude unnecessary free text.
- An unkeyed SHA256 is integrity checking, NOT "self-authenticating" and NOT
  proof of a live/current baseline. Correct docs/report wording. Verify target
  and relevant baseline content identity, and label exported-file baseline
  provenance separately from SQL actually executed in the current review.
  Neither bundle.sql_checked nor a baseline JSON boolean may manufacture a live
  database-validation claim. Display historical capture versus current checks.
- Add real PostgreSQL tests with ordinary private-content canaries (not just
  sk-/api_key patterns), consistent concurrent snapshot/pagination, unchanged
  table/audit state and outage behavior. Compare exported target against parsed
  configured URL, not a hardcoded database suffix or port. Preserve test DB
  safety guards and use disposable state.

## R5 — Correct filesystem sealing and publication safety

Independent probes against the published implementation:
- `_safe_file` accepts an internal symlink because resolve() happens before
  is_symlink(). Required no-symlink semantics are not implemented.
- Simulate another initializer creating a valid key between exists-check and
  `_atomic_write`: ensure_seal_key overwrites that key. 180-a's report claim
  "O_EXCL create, never overwritten" is false; mkstemp exclusivity for the
  temporary file is not exclusivity for publishing the final key.

Required corrections:
- Race-safe final-key creation: one key wins, other concurrent initializers
  reuse that verified existing key or fail safely; never replace it silently.
  Validate key files, permissions and relevant parent/path trust; reject leaf,
  parent and dangling symlinks. No runtime/provider secret reuse or key output.
- Safe bounded descriptor-based reads/copies: no lexical check then unchecked
  read_bytes race; reject symlink components, traversal/absolute/duplicate paths,
  special files and untrusted run roots. Enforce per-file/total/count/depth caps
  before unbounded reads/allocation and account for growth/replacement. Keep
  writer and verifier limits consistent (e.g. baseline export limit cannot
  exceed accepted sealed-baseline size without a clear pre-publication block).
- Strict typed receipt/manifest parsing, duplicate JSON keys/paths rejected,
  malformed shapes fail closed without tracebacks/raw input leaks. Constant-time
  HMAC check and exact semantic/artifact/validation/HTML correspondence remain.
- Build the complete run in private staging, then atomically publish the
  finished directory/receipt without clobbering an existing run. Failure must
  not leave a publicly complete-looking unsealed review at the final path.
  Verify must never write, initialize a key, or re-sign mutated input.
- Adversarial tests: internal/external/parent/dangling symlinks, concurrent key
  initialization, changed bytes between checks/reads, duplicate/malformed
  manifests, bounded-size failures, coordinated unkeyed digest rewrite, wrong
  key, partial publication failure and existing-output refusal. No global prune.

## R6 — One-glance report and accurate details

Independent 1440x900 file-browser inspection of first-install report found the
per-provider summary below the fold behind a ten-row metadata block and raw
12-column counter table. Required source-retrieval checklist rows are missing.
FX table caption says current vs proposed but only proposed values appear.

- First screen must prioritize state/why, blocker and REVIEW counts, selected
  scope/baseline, compact OpenAI/OpenRouter change/completeness summaries, FX
  current/proposed/date and aggregated important warnings. Keep compact run
  identity visible; put expanded technical identifiers in a details section.
- Include source, schema, complete pricing, pairing, unsupported filtering,
  unusual change, FX and actual execution-plan gates with truthful scope.
  Blocked plans must be visually impossible to mistake for READY.
- Display old/new price dimensions with unit/currency and signed percentage
  where meaningful; route current/proposed/reason; FX current/proposed/delta/
  source/publication date. Unchanged rows collapsed. Show filtered counts with
  reason aggregation and all exact rows/evidence/validation on demand in the
  same HTML, with no extra-file homework.
- Use product language: remove internal objective-number guidance from normal
  report/CLI output. Say offline review, live retrieval unavailable, or apply
  unavailable in this version as appropriate; do not make operators learn OAP.
- Maintain offline self-contained escaped HTML, no JS/remote assets/network,
  accessible details and printable layout. Visually inspect actual first-screen
  screenshots at laptop dimensions for bootstrap, no-change, changes with
  warnings, blocked plan, and a large mostly-unchanged catalog.

## Verification, scope and acceptance

Original AP-1..AP-8 still govern completion of Objective 180. R1–R6 must be
closed with actual behavioral evidence, not merely new explanatory text.
The full final workflow remains 181–183; do not implement it early to avoid
truthful BLOCKED state for unavailable operations.

Run the focused new unit/integration files and relevant existing import/CLI/
documentation tests. Add independent input mutations covering the exact probes
above and meaningful alternate-provider/public-alias/FX cases. Preserve good
positive paths; do not bless a broken result by changing expected outcomes.
No complete local suite/HPC run. Ordinary CI final-head gates still apply.

Use fresh task-owned PostgreSQL DBs and safe test fixtures; do not reuse real
local catalogs or production credentials. Verify table/audit no-write behavior
for export and demonstrate runtime FX lookup ONLY with synthetic disposable
rows, not a new apply feature. Browser tests must inspect actual DOM/layout and
no-network operation, not just string presence. Run changed-Python Ruff, docs
checker, cumulative diff --check and allowed-path/history review. Inspect bot
review findings in touched code and remove misleading dead branches.

The strategic `.env` concern in provisional notes was DISPROVEN: the actual
poison-.env probe succeeds and Settings has no env_file configuration. Do NOT
invent a fix for implicit dotenv access or accuse the report of that behavior.
Still preserve the existing no-shared-.env/no-protected-credential boundary.

No live sources, Codex research, provider inference, real email or production
system action; no dependencies/deployment/accounting-runtime/schema change.
If a true out-of-scope interface change is required, report its exact need
rather than duplicate code or weaken requirements. Preserve all unrelated
worktrees/provider catalogs. Clean and verify actual task-owned containers,
DBs, networks, volumes and credential files after all tests; retain safe
evidence/screenshots only. No blanket absence claim without final enumeration.

## Report and publication

Report exact starting and implementation SHA, same PR identity, changed paths,
per-R and original AP results, test commands/counts, new negative probes,
source observation/corroboration examples, FX conversion proof, no-op versus
blocked plans, PostgreSQL/privacy/consistent-export evidence, real browser
screenshots/first-screen metrics, race/tamper proof, cleanup and CI state.
Explicitly correct the inaccurate 180-a O_EXCL/no-symlink/self-authentication/
readiness claims in this NEW report; never rewrite the old report.

All claimed implementation GitHub state must be pushed before report drafting.
Atomically publish one immutable 180-b report with literal implementation SHA
and `Report publication commit: SELF`. Final report-only commit first parent
equals that SHA and changes only the report; verify it is pushed PR head.
Inspect final-head checks without changing the immutable report; pending is
not passed. Signal exactly two bytes OK to response FIFO. Leave PR #317 open;
coding agent never merges/auto-merges. No subsequent objective is activated
until strategy resolves this one.
