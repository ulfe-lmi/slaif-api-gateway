# OAP Work Order — 184-a

## Objective and reason

Complete the accepted administrator catalog-refresh mandate: documented install
→ one read-only refresh command → one offline REVIEW.html → separate explicit
audited atomic apply. Close installation/operator/E2E gaps using the services
accepted in180–183. All thirty human requirements remain required; use
`/home/janezp/codex-supervision/slaif-api-gateway/workorders/CATALOG-REFRESH-IMPLEMENTATION-MANDATE.md`.
This order supersedes inert184 planning only when published under oap/orders
and selected by oap/active. Do not expand supporting infrastructure without a
demonstrated integration defect.

## Verified state and publication identity

PR mode: `CREATE_NEW_PR`

- Canonical repository: ulfe-lmi/slaif-api-gateway; base: `main`.
- New branch: `oap/184-installed-admin-workflow`.
- Proposed title: `feat: qualify the installed administrator catalog refresh workflow`.
- Predecessor183 PR321 MERGED2026-10-14T01:27:11Z. Remote main
  c9c7630da1d7abf87029e130f486b4075e73d9b5; tree
  c781dd7964bcc8d451f63f952abf2d4c95462402 equals accepted SELF
  a6ab0c50c94d26938e45fde167969d2dbc8b5060. Expected merge parents verified.
- All ten final183 SELF checks SUCCESS; no blocking review/auto-merge. All nine actual main
  push check-runs completed SUCCESS, verified before184 activation.
- Prior live selector183-b/report6222484a6ce16ff212f6854708ca8ca17311ae11a1b33bc5929b8e7899f0f372;
  exact response26159 closed. No unresolved183 PR. Only unrelatedDependabot319
  remains open; no184 PR exists at order preparation.
- Active protect-main ruleset23580289, no bypass; release remainsv0.1.0-rc.1.
- Preserve untracked CODEX-SESSIONS.md/codex.sh, all prior immutable transcripts,
  .codex/, .local-provider-catalog/, unrelated worktrees/files/containers.
- `184-a` creates exactly one new PR for numeric184. Continuations amend it;
  coding agent never merges or enables auto-merge.

## Read before work

Repository AGENTS.md/applicable hierarchy and OAP-COMMUNICATION-coding-agent.md;
compact strategic OAP/ARCHITECTURE-for-agents.md; mandate and inert184 plan;
current docs/catalog-refresh.md, admin/catalog-refresh/README.md,
docs/cli-reference.md, docs/security-model.md, docs/database-schema.md,
docs/accounting.md and relevant constitution contracts. Consult accepted183
and182 audits for inherited evidence and limitations. Do not load full root
architecture/archived catalogs merely for context. Reconcile remote main,
open PRs, checks, release/rules, active and local state before Git execution.

## Exact permitted implementation paths

- pyproject.toml
- app/slaif_gateway/cli/catalog_refresh.py
- app/slaif_gateway/cli/catalog_refresh_admin.py (new thin entry point if needed)
- app/slaif_gateway/services/catalog_refresh/research.py (asset loading only)
- app/slaif_gateway/resources/catalog_refresh/__init__.py (new)
- app/slaif_gateway/resources/catalog_refresh/research-instructions.md (new canonical packaged asset)
- app/slaif_gateway/resources/catalog_refresh/research-output.schema.json (new canonical packaged asset)
- admin/catalog-refresh/research-instructions.md and research-output.schema.json
  (only relocate/remove duplicates or keep deliberate compatibility copy with drift verification)
- admin/catalog-refresh/README.md
- admin/catalog-refresh/refresh.sh (optional thin source-checkout wrapper)
- tests/unit/test_cli_catalog_refresh.py
- tests/unit/test_catalog_refresh_admin.py (new)
- tests/unit/test_catalog_refresh_research.py (asset assertions only)
- tests/integration/test_catalog_refresh_installed_workflow.py (new)
- tests/integration/test_catalog_refresh_research_codex.py (reuse/helpers and installed case only)
- tests/browser/test_catalog_refresh_report.py (installed report/print cases only)
- tests/fixtures/catalog_refresh/installed-workflow/ (controlled fixture inputs/provenance only)
- docs/catalog-refresh.md, docs/cli-reference.md, docs/security-model.md,
  docs/compatibility-matrix.md, README.md (preserve top brand block)
- docs/verification/catalog-refresh-installed-workflow.md (new thirty-row closure/evidence index)
- oap/orders/184-a-installed-administrator-workflow.md and oap/active
  (commit unchanged strategic bytes); one new matching immutable report.

No financial/runtime/accounting/schema/migration/transport/grounding/isolation
redesign. If an actual installed integration defect requires an unlisted path,
show concrete evidence and request strategic scope adjustment BEFORE editing.
Do not weaken tests or add production test-hook configuration to achieve fixtures.

## Requirements

R1. Provide one documented, installed administrator refresh entry point as a
thin composition of the existing collect/review pipeline and standard Linux
timeout watchdog. Prefer an installed Python entry point with argument-list
subprocess invocation, reusing existing CLI options/presets, over a bespoke
runner. Source wrapper optional. Bootstrap/refresh choice explicit; default
bothproviders/all-eligible/standard-v1; optional provider and single/list model
selection; opt-in existing research options. Validate positive finite timeout,
300s default/5s KILL grace, preserve exact child exits and option boundaries.
Watchdog ONLY read-only collect, never apply/review/export/verify/status. No
automatic apply, retry, browser server or Gateway startup. Print compact
readiness/run/report identity, not a file-review checklist. Existing raw commands
remain available with their current semantics. Unsupported preset refuses.

R2. Fix demonstrated installed-asset gap: research.py currently uses parents[4]
for admin/catalog-refresh assets absent from wheel package-data. Use existing
packaged-resource conventions; one authoritative template/schema and measured
hashes, task-local renamed AGENTS.md, strict output parser retained. Verify
wheel contents and resource resolution outside source checkout with no dev
PYTHONPATH/editable install dependency. Missing optional research prerequisites
refuse honestly, without host fallback or inferred identity. Do not create
another research mechanism or Gateway client compatibility profile.

R3. Execute documented fresh-checkout/build/wheel installation in owned temporary
environment. Invoke real installed entry point from outside checkout, clean
cwd/environment and no host .env/research profile/auth/history. Use the documented
source-checkout migration/setup path for owned PostgreSQL; do not claim migrations
ship in wheel unless actually implemented/qualified. No running Gateway required.
Controlled source/model fixtures must be injected only by owned test harness at
existing seams (not public unsafe source URLs or a new runtime fixture option).
Clearly record where test harness supplies fixtures and where actual installed
commands execute. Never substitute CliRunner-only/dev imports for installed proof.

R4. Real owned synthetic PostgreSQL bootstrap BOTH OpenAI/OpenRouter+ECB:
refresh command produces one sealed HTML, verify succeeds, explicit apply with
actor/reason/confirm/exposure ACK commits catalog+audit/application atomically;
status and retry return same outcome. Refresh against live coherent baseline:
changed native prices AND FX, single report before/after, required warning ACK,
explicit apply, old windows closed/new rows at oneT, history/IDs retained and
route authority preserved. Prove with queries/identities, not just exit codes.
Reuse accepted182 accounting/capture/recovery/concurrency evidence with exact
inherited binding; execute representative real installed apply workflow now.
No full fresh financial matrix if core unchanged.

R5. Qualify default all-eligible and explicit one-model selection, complete
inventory/exclusions/disappearance semantics; no fixed ten-model cap/silent
truncation. Selected missing/unsupported facts, source failure and truncated
inventory remain blocked; DB export failure never becomes bootstrap or deletion.
Use actual entry point for representative negatives; inherit exact unchanged
parser/policy negative tests where appropriate.

R6. Useful real Codex fallback through installed refresh entry point, using
accepted183 captured official page derivative, qualified CLI0.162.1 and real
existing outer Docker boundary with controlled model transport. Observe public
file local-tool result, grounded limit facts, semantic disclosure, exact canonical
plan/HTML/seal/verify. Packaged assets actually load. Reuse183 malicious-local-tool,
timeouts/malformed/cleanup boundary proofs; do not repeat entire matrix without
change. No live inference/host model execution/protected auth use authorized.

R7. Installed negative workflow proves non-success/no SQL mutation for blocked,
unsealed, tampered, stale, wrongkey/wrongbaseline and missingconfirm/actor/reason/
unacknowledgedwarnings. Verify baseline/catalog/audit/application state around
refusal, with focused representatives plus inherited unchanged trust tests.
Actual watchdog cancellation of owned stalled fixture collection leaves no
actionable partial run/no overwriting earlier run, no automatic retry. Missing
research prerequisites and unsupportedpreset honestly refuse.

R8. Exact installed SUCCESS and BLOCKED HTML artifacts, offline Chromium with
JavaScript disabled,1440x900/1280x800/375x812 initial and expanded, zero external
requests, existing font/hash/no-overflow/firstscreen gates unchanged. Native
prices/local EUR, ECB date/direction, changes/exclusions/provenance/research state
visible. Execute promised print behavior; all decision details available in one
document, not hidden behind JS or omitted from print. No UI framework/redesign.

R9. Update install/bootstrap/refresh/review/apply/status/retry/troubleshooting
docs and exact supported versions/limitations. Review30–60sec is an operator
design target, not a measured usability claim. Provide all THIRTY individually
numbered requirement rows with actual commands/artifacts/tests and new versus
inherited qualification; gaps remain explicit, never declared complete by a
green unit suite. No current live source-format/model accuracy claim from mocks.
Concrete existing documentation drift must be reconciled in these allowed
files: docs/catalog-refresh.md still says no apply exists in collection Limits,
readiness and report prose despite the implemented Apply section; security-model
still says uid65534 unconditionally despite invoking-nonroot UID/GID behavior.
Correct those statements to inspected current behavior, without changing runtime
or broadening supported scope.

## Setup authority, security and non-goals

Routine owned local venv/tool installation and synthetic disposable resources
authorized. Reuse /tmp/slaif-181c-strategic-venv (Python3.12.15) for development;
installed proof needs separate owned environment. Qualified Codex binary
/home/janezp/.codex/packages/standalone/releases/0.162.1-x86_64-unknown-linux-musl/bin/codex,
SHA628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1.
Docker29.1.3 unix:///var/run/docker.sock; existing pinned research image
python@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f,
--pull=never. Browser scoped libraries already in
/tmp/slaif-browser-runtime-8h8e0e6z/extract/usr/lib/x86_64-linux-gnu.
Use new owned loopback/tmpfs PostgreSQL16.15 with explicit TEST_DATABASE_URL;
only that synthetic URL supplied to installed CLI. Never DATABASE_URL/.env
production/shared5432. Cleanup exact created IDs+ownership labels; no broad
prefix deletion/kill. Preserve unrelated runtime resources.

Fixed official HTTPS destinations, certificate/SNI verification, vetted numeric
connection binding/safe redirects, secret isolation and trustworthy reports
remain unchanged. Human-approved cooperative collection timing and processed
returned-body budgets remain the only relaxed transport guarantees. This does
not relax PostgreSQL monetary accounting. No new service/daemon/catalog store,
dashboard, general sandbox/transport platform, release/tag/deploy, production
application/credentials, live source GET or real model request authorized.
No host researcher invocation inheriting HOME/CODEX_HOME/auth, even as a probe.
Use already verified version/hash or strictly isolated synthetic execution.

## Verification, acceptance and report duties

Before product edits map minimal R1/R2 implementation and test harness to current
seams. Implement directly; do not spend cycles constructing new supporting
frameworks. Run focused changed CLI/resource tests, actual installed workflow
on owned PostgreSQL, useful isolated installed research case and exact offline
browser/print artifacts. Ruff/diff/docs/build checks and all required final-head
GitHub checks must pass. Do not run full local suite except reproducing an
actual matrix failure; skipped/missing/not-run evidence is never PASS.

Publish unique184 PR from acceptedmain, unchanged activation bytes and scoped
implementation/docs/evidence. Report exact install/build commands, package
identity, cwd/env controls, fixture versus live/mock scope, SQL observed outcome,
watchdog failure, inherited accounting/isolation binding, all30 rows and any
limitations/deviations. Include required documentation-impact statement. Store
only safe synthetic evidence; no protected values or content-bearing host logs.
The183 corrected historical disclosure stays immutable; do not repeat false
zero-live claims for the whole project history.

Exactly one immutable report: oap/reports/184-a-installed-administrator-workflow.md;
literal `Implementation head SHA: <40-hex>` and `Report publication commit: SELF`.
Publish report-only commit with first parent matching implementation head, push,
verify unique remotePR head, then exact responseOK once and attach sole control
waiter. Coding agent never merges or enables auto-merge. Strategy independently
audits all30 requirements, report topology, diff/docs/security/accounting and all
finalSELF checks before guarded merge. Completion is workflow implementation
qualification, never a production/release/certification/invoice-equivalence claim.
