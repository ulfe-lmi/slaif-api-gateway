# OAP Work Order — 180-f

PR mode: AMEND_EXISTING_PR

## Objective and reason

Close the independently reproduced proposal round-trip and financial comparison
gaps remaining in the offline catalog review foundation. Register the new
read-only policy-parser consumer without weakening architecture safeguards.
Make focused corrections on PR #317, preserving the useful 180-e metadata,
source binding, SQL provenance and consistent-snapshot work.

The human still requires the whole administrator workflow: one refresh command,
one trustworthy REVIEW.html, one explicitly confirmed audited apply command.
This round does not complete that workflow or Objective 180. Live collection,
isolated Codex research, atomic historical supersession and final wrappers remain
later numeric objectives after this PR is accepted and resolved. No scope
reduction or replacement with an offline-only product.

## Verified current state and immutable report reconciliation

Verified directly from GitHub and the sole FIFO helper on 2026-09-22:

- Repository ulfe-lmi/slaif-api-gateway, main
  b1e6ef0a49d7e5ab6376f6344290f58ff844e671.
- Unique open PR #317; branch oap/180-catalog-refresh-bundle-review; base main.
- Starting PR/report head c1cd097aeb36b92dacec49ce1c6600018a2a82f3.
- Report-only commit changes solely
  oap/reports/180-e-preserve-catalog-metadata-and-baseline-truth.md;
  first parent/reported implementation head
  5f6aac4738da1784828e5125aa6f1b172867cfc7.
- Implementation2ce80342f86e7244b08eff74d93aac2e2c7d402b changed25 allowed
  files. Follow-up5f6aac4 changes only tests/integration/test_catalog_refresh_baseline.py
  to fix cross-file residue and a stale-baseline test's implicit seed dependency.
- Exact RESPONSE_OK_EXACT received from sole helper59399, exit0. Active before
  this order180-e. Worktree clean. Do not reuse that completed helper.
- Final implementation AND report-head checks: nine SUCCESS, one FAILURE.
  The unit gate fails exactly
  test_documentation_contract_drift.py::test_external_tool_policy_contract_consumers_remain_allowlisted
  because schemas/catalog_refresh.py is absent from the consumer allowlist.
  The PostgreSQL gate now passes; this is not an all-green PR.
- Strategy independently ran230 focused unit cases on2ce8034 with exact stable
  hashes and20 PostgreSQL baseline cases in its own disposable database.
  The agent subsequently proved the test-isolation correction with the complete
  PostgreSQL CI sequence (243 passed,2 skipped), and GitHubPG passes on5f6aac4.
  Skips are not passes. No broad qualification claim follows.
- Main ruleset still prohibits deletion/non-fast-forward. Only published release
  remains v0.1.0-rc.1. No merge/tag/release authority transfers to the coding agent.

The 180-e report correctly preserves the known filesystem/layout work and the
CI allowlist conflict. Its broad E1/E2 closure claims are not accepted for the
reproducers below. Preserve that report and every earlier order/report unchanged;
record precise corrections only in this round's new report.

## Exact allowed paths

- app/slaif_gateway/schemas/catalog_refresh.py (only necessary proposal/runtime
  projection or comparison contract integration)
- app/slaif_gateway/services/catalog_refresh/validation.py
- app/slaif_gateway/services/catalog_refresh/baseline.py (only round-trip
  projection/comparison support; preserve privacy and existing typed metadata)
- app/slaif_gateway/services/catalog_refresh/policy.py
- app/slaif_gateway/services/catalog_refresh/source_evidence.py (only numeric
  equality/direction/context normalization if needed; no parser rewrite)
- app/slaif_gateway/services/catalog_refresh/bundle.py (only necessary canonical
  projection/version integration)
- app/slaif_gateway/services/catalog_refresh/rendering.py (accurate capability,
  comparison and threshold presentation only; no layout overhaul)
- tests/unit/test_documentation_contract_drift.py (F1 exact allowlist entry only)
- tests/unit/test_catalog_refresh_baseline.py
- tests/unit/test_catalog_refresh_bundle.py
- tests/unit/test_catalog_refresh_policy.py
- tests/unit/test_catalog_refresh_source_evidence.py
- tests/unit/test_catalog_refresh_report.py
- tests/unit/test_catalog_refresh_seal.py (derived-artifact/fixture adaptation)
- tests/unit/test_cli_catalog_refresh.py
- tests/integration/test_catalog_refresh_baseline.py
- tests/fixtures/catalog_refresh/ (synthetic affected fixtures/screenshots only)
- docs/catalog-refresh.md
- docs/cli-reference.md (changed catalog-refresh semantics only)
- admin/catalog-refresh/README.md
- oap/orders/180-f-close-catalog-roundtrip-and-comparison-gaps.md (unchanged)
- oap/active (unchanged strategic bytes180-f)
- oap/reports/180-f-close-catalog-roundtrip-and-comparison-gaps.md (new report)

No other paths. No application/provider/accounting runtime changes, import
executor changes, schema/migrations, dependencies, deployment, workflows,
production scripts or historical-record changes. Existing runtime capability,
policy and import modules are read/reuse-only. No new live collector, researcher,
apply wrapper, pricing supersession or arbitrary capability profile. Do not
change product behavior to accommodate a proposal or test.

## F1 — Register the reviewed read-only policy consumer

The new schemas/catalog_refresh.py consumer imports the authoritative
parse_route_external_tool_policy and DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
used only to validate/project existing metadata into a read-only baseline.
Strategy authorizes adding this EXACT consumer path to the existing allowlist
in test_external_tool_policy_contract_consumers_remain_allowlisted.

Keep the architecture assertions, allowlist mechanism and other consumers
unchanged. Do not duplicate the policy parser, hide an import through indirection,
make external_tools opaque merely to satisfy the gate, or add a broad directory
exception. Prove that this use grants no runtime hosted-tool authority and that
malformed/unknown metadata still fails safely without private content leakage.

## F2 — Generated routes must survive create -> export -> refresh

Committed reproducer on2ce8034 (unchanged product bytes at5f6aac4): the valid
first-install fixture is READY and emits capabilities JSON
{"streaming":true,"text":true} in routes-proposal.tsv. The existing route
importer passes those flat keys to ModelRouteService, which preserves them and
adds its nested chat_completions defaults. project_route_capabilities then marks
that exact stored result capabilities_unrepresented=True, so the next refresh
blocks on metadata the refresh mechanism itself generated.

Build one deterministic mapping from proposal/profile intent to the ACTUAL
runtime route capability shape. Use the same derived contract for evidence
requirements, before/after comparison, rendered rows and emitted import bytes.
Emit recognized nested runtime metadata, not stray flat storage keys; preserve
explicit denials and supported streaming intent. Resolve contradictory streaming
column/capability values explicitly, not with a silent precedence accident.
Do not broaden the standard profile or rely on importer defaults to grant
undeclared permissions. Unsupported/hosted/multimodal/Responses/Codex authority
remains denied. A disabled-text route is not a usable standard text candidate;
exclude/block it with a clear reason rather than silently enabling text or
claiming a successful text bootstrap. Preserve valid text, supported streaming,
public aliases and all existing source-evidence safeguards.

Partial proposal intent must not silently erase existing approved metadata.
For unchanged rows, preserve unselected fields. For actual changes, show the
change and keep existing create-only/no-supersession behavior. Never delete or
disable current rows because discovery omitted them. Unknown/private metadata
cannot become broadly allowed just to make the round trip pass.

Prove the complete local round trip in a FRESH disposable database: create the
synthetic provider state, generate and dry-run a valid proposal, explicitly
confirm existing deterministic pricing/route imports with an audit reason,
export the resulting real rows, review the same synthetic source facts again,
and show an honest unchanged/no-op result with zero executable duplicate rows,
no unrepresented-capability blocker and no permission widening. This authorizes
ONLY existing import commands in task-owned test databases using synthetic data;
it does not add or authorize a product apply workflow or any production import.
Assert actual persisted capability values; do not replace real imports with
hand-seeded lookalike rows or test only the projection helper.

## F3 — Compare FX values, not their spellings

Exact committed reproducer: use bundle-first-install.json (READY); add a second
ECB SourceRecord for the same official URL/date/quote (pair alias USD-EUR), with
snapshot rate spelled1.080 rather than1.08 and a correctly regenerated digest.
The full validator returns BLOCKED source_observations_contradict and discards
all FX backing, claiming1.08 and1.080 disagree. The code constructs
rates={str(quote.rate)}, so it compares spellings instead of numeric values.

Use exact Decimal numeric equality with the applicable currency pair, quote
publication date and unit/direction context. Preserve all provenance identities,
no invented corroboration and no suppression of genuine conflicting quotes.
Repeated retrievals/aliases of one URL remain one independent source, as in180-d.
Equivalent representations must not fabricate a financial conflict.

Test identical/equivalent quotes, genuinely different quotes, valid direct and
reciprocal quotes, rounding at representable precision, wrong date/pair/source,
and full report/seal replay. Verify reciprocal agreement in the proposed pair's
direction with an explicit bounded rounding/tolerance rule, rather than an
unstable invert-back comparison. Preserve native-currency -> EUR runtime truth,
required quote/date binding and the rule that a derived inverse is not an
existing local runtime row. No guessed rates or floats.

## F4 — Decisions use the exact documented thresholds

Current committed source_age_state(24h) and fx_age_state(3d) return REVIEW.
The 180-e order required strict >24h / >3d review thresholds, not >=; its report
instead declares the existing inclusive boundary closed. Correct the policy,
docs and tests coherently. Defaults:

- source age <=24h fresh, >24h through72h REVIEW, >72h BLOCKED;
- official FX publication date age <=3 calendar days fresh, >3 through7 days
  REVIEW, >7 days BLOCKED (use a documented consistent calendar/date basis);
- absolute price change >25% REVIEW; exact25% does not trigger;
- absolute FX change >3% REVIEW; exact3% does not trigger.

Keep policy configurable. Test below/equal/above every boundary, including date
versus time-of-day behavior. Compare exact financial ratios BEFORE rounding for
display: _pct currently quantizes to1e-6, so an above-threshold value can round
back to the threshold. Display formatting must not change acceptance decisions.
Retain zero transitions, missing dimensions, stale/future/unknown/conflicting
facts and true excessive movements as explicit deterministic findings.

## Verification, scope and publication duties

Run focused changed catalog-refresh tests, the exact architecture drift gate,
relevant pure capability/import regressions, the actual disposable-DB round trip
and baseline integration tests, changed-Python lint, documentation checker,
internal links and git diff --check. Ordinary final-head GitHub gates must pass.
Do not run full local/HPC suites unless a specific matrix failure requires it;
the earlier integration CI issue is now fixed, so default to focused verification.
Keep test fixtures self-contained and clean their own rows; do not reintroduce
cross-file padding/provider residue or assertions that rely on prior tests.

Use task-owned local databases only. Verify actual data directory, host/port and
requested database identity before setup/cleanup. No shared5432 instance, its
configuration/logs, privileged postgres identity, protected credentials or
production systems. A shorter database transaction than Python processing time
is not evidence of a different server. Preserve unrelated worktrees,
.local-provider-catalog, root AGENTS.md and permanent message.txt. Do not perform
global prune/reset/cleanup. Capture actual subprocess exit codes, not tail/grep
pipeline exit codes; do not call skipped checks passed.

Report exact starting and implementation SHAs, changed paths, F1-F4 results,
actual persisted round-trip/no-op proof, FX/threshold before-after reproducers,
negative privacy/authority cases, source/report/seal correspondence, resource
identity/cleanup and final-head CI. Correct the 180-e broad equality/threshold
closure claims in the NEW report only. Also distinguish test-only database-name
assertions from product behavior, and note that the task-owned-database-only
restriction existed in the original180-e order, not only after the reminder.
Report actual test collection counts, not guessed per-file totals.

Filesystem descriptor-walk/parent-replacement safety, symlinked verify-key,
bounded input/aggregate reads, special files, no-clobber run publication,
opened-file identity/permissions, and first-screen/expanded-print layout remain
REQUIRED for later same-PR correction. Do not implement them outside this scope
or claim Objective180 complete. No later numeric objective untilPR317 resolves.

Commit the strategic order and active pointer unchanged. Push implementation
before drafting the report. Publish exactly one immutable final report-only SELF
commit, first parent equal to its stated implementation head, as the remote PR
head before sending exactly two bytesOK on the verified response FIFO. Never
merge or enable auto-merge. Await the next strategic order.
