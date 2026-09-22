# OAP Work Order — 180-e

PR mode: AMEND_EXISTING_PR

## Objective and reason

Make the offline catalog review faithfully represent existing SLAIF metadata
and the effective eligibility of proposed routes. Correct the baseline export,
financial comparison and SQL evidence defects identified on PR #317. Preserve
the successful 180-d source-binding work; do not rewrite the subsystem.

The full human mandate remains one refresh command -> one trustworthy HTML
report -> one explicit audited apply command. This round is a bounded correction
to Objective 180's offline foundation, not completion of that workflow. Live
research, atomic supersession and final administrator wrappers remain subsequent
numeric objectives only after this PR is accepted and merged.

## Verified starting state and report reconciliation

Verified on 2026-09-22 directly from GitHub:

- Repository: ulfe-lmi/slaif-api-gateway; main:
  b1e6ef0a49d7e5ab6376f6344290f58ff844e671.
- Sole open PR: #317, branch oap/180-catalog-refresh-bundle-review, base main.
- Starting PR/report head: 6a177bf10f2a93ec1f8267cb930c7a3842754b9c.
- Report-only commit changes solely
  oap/reports/180-d-close-source-evidence-bypasses.md; first parent and reported
  implementation: e3d2c7d3e37aa083781723bae194a1dd80f30b94.
- All ten checks SUCCESS on the current report head; PR MERGEABLE but not
  strategically accepted. Main protection prevents deletion/non-fast-forward;
  passing CI alone does not authorize merge. Only published release v0.1.0-rc.1.
- Active before this order: 180-d. Worktree clean. The verified FIFO helper's
  response wake was received. On recovery its process handle 82132 had already
  expired; strategy did not fabricate a second terminal receipt or start an
  extra FIFO reader. Report, GitHub and coding-agent control-wait state agree.
- Independent verification of e3d2c7d: 183 focused unit tests pass with stable
  source/test/fixture digests. Original source-bypass reproducers now block,
  positive fixture remains READY; expanded HTML exposes actual observed price,
  unit and locator offline with JavaScript disabled and no network requests.
- The 180-d report correctly carries unresolved baseline/filesystem/layout
  acceptance work. The additional metadata failures below remain reproducible.
  No old order/report may be edited.

## Exact allowed paths

- app/slaif_gateway/schemas/catalog_refresh.py
- app/slaif_gateway/services/catalog_refresh/baseline.py
- app/slaif_gateway/services/catalog_refresh/bundle.py
- app/slaif_gateway/services/catalog_refresh/validation.py
- app/slaif_gateway/services/catalog_refresh/source_evidence.py (effective
  capability/deprecation observation and comparison only)
- app/slaif_gateway/services/catalog_refresh/policy.py (financial/freshness
  normalization and exact thresholds only)
- app/slaif_gateway/services/catalog_refresh/rendering.py (metadata comparison
  and truthful baseline/SQL evidence wording only; layout overhaul excluded)
- app/slaif_gateway/services/catalog_refresh/sealing.py (only deterministic
  replay integration needed for changed baseline/validation schema; filesystem
  hardening is explicitly a subsequent continuation)
- app/slaif_gateway/cli/catalog_refresh.py (only actual baseline capture-context
  propagation and safe metadata errors; filesystem hardening excluded)
- tests/unit/test_catalog_refresh_bundle.py
- tests/unit/test_catalog_refresh_policy.py
- tests/unit/test_catalog_refresh_source_evidence.py
- tests/unit/test_catalog_refresh_report.py
- tests/unit/test_catalog_refresh_seal.py
- tests/unit/test_cli_catalog_refresh.py
- tests/unit/test_catalog_refresh_baseline.py (new if useful for pure projection)
- tests/integration/test_catalog_refresh_baseline.py
- tests/fixtures/catalog_refresh/ (synthetic baseline/source fixtures and
  corresponding deterministic report snapshots only)
- docs/catalog-refresh.md
- docs/cli-reference.md (catalog-refresh baseline/input semantics only)
- admin/catalog-refresh/README.md
- oap/orders/180-e-preserve-catalog-metadata-and-baseline-truth.md (unchanged)
- oap/active (unchanged strategic bytes 180-e)
- oap/reports/180-e-preserve-catalog-metadata-and-baseline-truth.md (new report)

No other paths. Existing runtime capability/pricing parsers are read/reuse-only:
do not change application behavior to accommodate a new export. No migrations,
DB models, provider execution, accounting runtime, existing import executor,
dependencies, deployment, workflows or historical records. No live retrieval,
Codex research, provider inference, production metadata mutation, imports/apply,
tag/release or merge. Coding agent never merges or enables auto-merge.

## E1 — Baselines accept actual runtime contracts without leaking free-form data

Current BaselineRouteRow.capabilities is dict[str,bool]. Actual ordinary routes
created by ensure_default_chat_completion_capabilities({}, supports_streaming=True)
contain nested chat_completions capability booleans; _strict_capabilities rejects
them. Responses/Codex routes also contain typed nested maps and integer bounds.
A baseline exporter that works only with artificial flat text/streaming fixtures
is not acceptable for a normal installation.

Inspect implemented runtime contracts and database-schema sections for these
fields. Reuse pure validators/constants where practical. Project recognized
semantically relevant fields with bounded, typed allowlists, preserving nested
structure and effective meaning. Existing non-selected route families must not
break an otherwise valid standard-profile refresh or acquire new permissions.
An unrepresentable relevant value must be explicitly retained as a safe opaque
comparison identity with affected changes blocked, or produce an explicit safe
failure; never silently discard it and call the row unchanged. Do not put
arbitrary free-form metadata into the public bundle/report to solve fidelity.

Current boolean/key-length validation accepts arbitrary private-text keys and
its malformed-value error echoes those keys. Test synthetic private canaries in
keys and values through DB export, baseline-file load, CLI error and HTML/seal.
No raw free-form notes, provider secrets or unrelated metadata may survive in
public artifacts/errors. Approved model IDs/config identities are not a promise
of universal PII detection. State precisely what the allowlist excludes. Safe
opaque fingerprints are identities, not anonymization of guessable secrets.
Unknown free-form annotations cannot silently affect executable meaning.

Preserve legitimate legacy FX source labels (e.g. manual and ECB) as safe typed
labels or an honest normalized label; source is not always a URL. Real URLs must
remain safely sanitized without credentials/query/fragment or unsafe error echo.
A legacy local label is not authoritative current FX retrieval evidence.

## E2 — Preserve pricing meaning and correct financial normalization

BaselinePricingRow/export currently drops pricing_metadata entirely, although
runtime consumes audio_output_price_per_1m, codex_accounting cache-write and
long-context fields, and external_tool_pricing. Inspect all currently consumed
financial dimensions rather than assuming this example list is exhaustive.
Retain typed allowlisted financial values and their comparison identity, reusing
existing parsing contracts where possible. Keep free-form notes out. Unsupported
metadata for the selected profile must prevent misleading safe-update/no-change
claims; existing historical or unselected rows must remain preserved. Do not
implement supersession or silently overwrite anything in this round.

Prove that two baselines differing in an effective monetary metadata field do
not produce the same semantic identity/unchanged claim. Demonstrate ordinary
text metadata, Codex cache-write/long-context, audio pricing and selected hosted
fee preservation or explicitly blocked affected proposals. This does not enable
those families in the standard text profile.

parse_decimal_text("1E+1000000", field="price") currently raises Decimal Overflow
via abs(value) before bounding it. Safely bound untrusted digits/exponents before
arithmetic/formatting, reject invalid/out-of-range values with code-only errors,
and preserve numerically equivalent valid trailing-zero spellings. Validate
baseline monetary fields as well as proposed facts. No float conversion.

Reconcile financial comparisons with runtime's native-currency -> EUR lookup:
only active enabled unambiguous direct local rows are current runtime FX. A
derived inverse may be shown as a proposal derivation, never described as an
existing runtime row. Test expired/future/disabled rows and overlapping active
prices/FX; no historical fallback. Compare equal Decimal spellings as equal.
Check reciprocal quantization in proposal direction (not unstable round-trip
inversion) against Numeric(18,9), with a defined rounding/tolerance contract.
Do not weaken authoritative quote/date binding. Verify exact documented policy
threshold boundaries (price >25%, FX >3%, source >24h review/>72h block, FX
publication >3 days review/>7 days block); preserve explicit configurable policy.

## E3 — Effective proposal eligibility cannot bypass observed source facts

Two committed full-path reproducers using bundle-first-install.json:

1. Change raw OpenRouter data[0].deprecation.is_deprecated to true, regenerate
   evidence bytes/digest, leave ModelFacts.deprecated false. Result is READY,
   zero findings and one executable pricing row. Parser observed true is ignored.
2. Change source architecture input/output modalities to audio-only; set
   ModelFacts.capabilities.text=false but keep RouteFacts.capabilities.text=true.
   Result again READY with one executable pricing row. Validation checks only
   truthy ModelFacts text, not actual emitted route permission.

Use actual effective proposed route capabilities, including defaults and merge
precedence, when deciding required evidence. Model and route facts cannot erase
a source contradiction or authorize unsupported behavior. Bind the relevant
field to actual provider/upstream evidence and declared references as in 180-d.
An audio-only observation cannot yield an executable ordinary-text route. Keep
valid aliases, valid text and supported explicit streaming positive paths.

Provider-observed deprecation must be surfaced and handled conservatively even
if a proposal boolean defaults false. Distinguish absent source information from
explicit false; do not invent false evidence for every provider. Exclude newly
deprecated candidates by the conservative profile or block conflicting facts
with a clear reason, retain current local rows, never auto-delete/disable them.
Counts/dispositions and the single report must reconcile. Missing required
support remains blocked; no inferred hosted/multimodal/Responses/Codex grants.

## E4 — Prove a real consistent read-only snapshot

The present concurrency test keeps a writer uncommitted during both reads and
commits only before a fresh export. READ COMMITTED also passes; this does not
prove the claimed REPEATABLE READ consistency.

Use a disposable PostgreSQL database and explicit test barriers to commit a
writer between exporter queries/pages/count reads, then show the export remains
one coherent old snapshot and a subsequent export sees the new committed state.
Include pagination and cross-table changes affecting route/pricing identity;
counts cannot be from one version and rows another. Prove the test would expose
a READ COMMITTED implementation (a test-local negative control is appropriate),
without changing product isolation to satisfy the test. Assert no writes/audit
mutations by export and safe DB-failure handling; outage must not become empty
first-install state. Retain exact target host/port/database identity without
credentials. Do not assert a hardcoded port as a product requirement.

## E5 — Truthful current versus captured SQL evidence

validate_bundle currently derives sql_executed_during_review solely from the
caller-supplied bundle.baseline.mode; its first-install else branch falsely says
SQL ran historically. A supplied document boolean/hash cannot attest an actual
current connection or historical execution.

Derive current-run capture evidence from the actual CLI/export execution path,
not caller labels. Distinguish: explicit first install with no DB read; supplied
baseline document with declared capture metadata but no current SQL; actual
read-only SQL export performed by this review command; offline seal verification
replaying the recorded review, not rerunning SQL. Bind any trusted invocation
receipt to the sealed run using deterministic replay without fabricating new
execution during verify. A malicious input mode/boolean cannot claim live SQL.

Render this distinction in the same HTML and canonical validation results. Test
all four paths and falsified labels, including generated HTML assertions. Keep
report/bundle/validation correspondence and exact-byte seal guarantees intact.

## Acceptance and verification

E1–E5 must each have actual before/after evidence and nearby positive cases.
Run focused catalog-refresh unit/CLI/report/seal/source tests; disposable PG
baseline tests with real nested runtime-generated capabilities, financial
metadata and committed-writer barriers; related existing pure import/pricing/
capability tests for regressions; changed-Python lint, documentation checker,
internal links and git diff --check. Ordinary CI gates must pass on final head.
Do not run complete local/HPC suites unless reproducing a matrix failure. Tests
must assert the user contract, not codify the current defect. Review relevant
current bot findings in touched files; do not broaden scope for unrelated lint.

Use only task-owned local PostgreSQL resources, verify database/data directory
identity before destructive cleanup, record exact host/port/database and cleanup.
Shared PostgreSQL/production/protected credentials and unrelated worktrees or
.local-provider-catalog are untouched. No network-dependent source calls needed.
No hidden setup steps or secrets/content in report/logs.

## Remaining Objective 180 work and publication

Filesystem descriptor-walk/parent replacement safety, symlinked verify key,
bounded input/aggregate reads, special files, no-clobber run publication and
opened-file permission/identity checks remain REQUIRED for a later same-PR
continuation. First-screen checklist and expanded/print table layout also remain
REQUIRED, not waived or deferred out of the mandate. Do not claim Objective 180
complete. No next numeric activation before PR #317 is fully accepted/resolved.

Preserve root AGENTS.md and permanent message.txt. Commit this order and active
pointer unchanged. Push implementation before drafting a report. Report exact
starting SHA, implementation head, changed paths, E1–E5 results, negative and
positive evidence, DB transaction/barrier proof, safe projections and limitations,
SQL evidence distinction, cleanup and truthful final-head CI. List unresolved
carried work explicitly. The unique immutable report must be a final report-only
SELF commit with first parent equal to the reported implementation head, pushed
as the PR head before sending exactly two bytes OK on the verified response FIFO.
Coding agent never merges or enables auto-merge. Await the next strategic order.
