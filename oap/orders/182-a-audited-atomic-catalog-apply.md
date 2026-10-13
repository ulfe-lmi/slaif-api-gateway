# OAP Work Order — 182-a

PR mode: `CREATE_NEW_PR`

## Objective and business reason

Complete the deterministic administrator refresh -> one reviewed sealed HTML ->
one explicit atomic PostgreSQL apply path. Add audited create/supersession,
durable retry status, preserved price/FX history and coherent admission snapshots.
This is NEW objective182/NEW PR, not a continuation of merged318. It must solve
bootstrap AND refresh, including existing-row price/FX changes; a create-only
executor or a sequence of independent imports is not completion.

Human prioritizes this workflow and approved R1/R2 collection simplification.
Those are operational transport limits, not permission to weaken financial,
source, secret, reporting or atomicity guarantees. Reuse existing primitives;
no catalog platform, event bus, new transport machinery or general accounting
redesign. Isolated Codex research is183; final wrappers/clean-install/full E2E184.
All numbered human requirements in CATALOG-REFRESH-IMPLEMENTATION-MANDATE.md remain.

## Verified state, PR identity and setup

Reconciled2026-10-12 after181 strategic acceptance:
- Repo ulfe-lmi/slaif-api-gateway. Remote main60214c54226a9b488666e8a849fe9f326faf8218.
- PR318 MERGED2026-10-12T23:50:50Z; mergecommit above. Whole181 accepted, rounds
  181-a through181-i. Final report50a2b1b74d62d1ea6cf37670df6c61a29004e0b4,
  firstparent implementationb75c38fa48b2673c2220742439663b8674119b60; all10SELF
  checksSUCCESS. Immutable order/reports retained. Solehelper6254 exactOK/exit0
  consumed/CLOSED. Do not resignal181 or create another response reader.
- Postmerge main tree equals the accepted report tree (a2dac93c836345b716471fc4d3ce7cd3f7189f40); all10 current main checks completed/success.
- Independent182affectedtestsPASS49.266s/zeroDNS+childnetworkmarkerabsent,
  final9trustcases and11reporttestsPASS, actualboth-provider mocked CLI/live and
  same intact offline reports pass JS-disabled browser1440/1280/375 collapsed
  and expanded, decisionbottom866.3/845.3, noexternalrequests; H publicsource
  qualification reused explicitly with final-code offline public-byte bridge.
- Before activation exactactive181-i; sharedcodingcheckout remains318reporthead.
  Strategy did not reset/clean/stash/switch. Agent owns fetch/newbranch execution.
- CREATE_NEW_PR from exact remote main above; branch oap/182-atomic-catalog-apply.
  Suggested title: feat: apply reviewed catalog changes atomically with pricing history.
  Exactly one182 PR. Coding agent never merges/enables auto-merge.
- DependabotPR319 remains unrelated/untouched. Ruleset23580289 active deletion/
  nonfastforward/nobypass; merge commits allowed. Only prereleasev0.1.0-rc.1.
  No production import, inference, release/tag/deploy or protected credential scope.
- STRATEGIC_ROOT=/home/janezp/codex-supervision/slaif-api-gateway;
  REPO_ROOT=/home/janezp/codex-work/slaif-api-gateway; verified FIFOs at strategicroot.
  Panes%8strategy/%9coding, session7/window0, coding2075296/pane1703557;
  onecontrolwaiter2323607 under2075296, TMUX_PANE=%9. Reverify explicitpane identity.
- ManagedPython3.12.15/devvenv /tmp/slaif-181c-strategic-venv available. Preserve
  broken copied.venv, CODEX-SESSIONS.md, codex.sh, ignored.codex/localcatalogs,
  linked worktrees and unrelated Docker resources. No new Python dependency needed.
  Scoped optional browser test libraries:
  LD_LIBRARY_PATH=/tmp/slaif-browser-runtime-8h8e0e6z/extract/usr/lib/x86_64-linux-gnu.
- Migration head0024_quota_reservation_accounting_facts. New durable application
  record may use one0025 migration; no unrelated schema/accounting changes.

Read repository governance/protocol/compactarchitecture and current contracts:
docs/catalog-refresh.md, docs/accounting.md, docs/pricing-catalog.md,
docs/database-schema.md, docs/security-model.md, applicable CLI/import contracts.
Required read-only strategic inputs: OBJECTIVE-181-I-STRATEGIC-REVIEW.md,
OBJECTIVE-182-ATOMIC-APPLY-PREFLIGHT.md, CATALOG-REFRESH-IMPLEMENTATION-MANDATE.md,
review-artifacts/182-preflight/postgres_quote_probe.py and postgres-quote-results.json.
Old activated roadmap labels stay immutable; current mapping182apply/183Codex/184final.

## A1 authenticate one captured reviewed plan; explicit operator action

Add one catalog-refresh apply CLI, recommended --run-dir DIR --seal-key KEY
--db-url URL --confirm --reason TEXT --actor TEXT plus --ack-warnings when needed,
and read-only status/retry visibility. Match existing CLI conventions; no web API
or running Gateway requirement, no provider key read. Actor text is an operator
assertion, not verified RBAC identity; record actual PostgreSQL current_user and
existing admin ID where supplied/validated. Do not invent an authentication system.

Consume existing anchored bounded capture-once bytes and authenticate HMAC,
manifest, canonical bundle, report/validation/derived-artifact correspondence.
Do not verify one path then reopen/reparse another copy for execution: one held
capture is the authority throughout. Keep key outside run, no-clobber, immutable
archives and safe errors. Reuse/refactor a small verified-capture return boundary
in sealing/filesystem if necessary; no alternate signer or artifact platform.

Refuse wrong key, tampered/unsupported/legacy/unsealed/incomplete/BLOCKED plans,
missing explicit confirmation/reason/actor, and unacknowledged warnings. No force
bypass. Re-evaluate applicable freshness and policy at actual apply time, without
rewriting/resealing or renewing source/generated timestamps. Old verification
is original-context replay, not a fresh-source endorsement. New apply-time
findings must be visible; never silently change reviewed semantic operations.
Unknown/unsupported facts remain blocked; Codex stays NOT_RUN in this objective.

Preserve verified HTTPS/destination/redirect/secret protections; apply performs
no source HTTP, inference, research, email, provider discovery or credential load.
DB URL is operator configuration, never untrusted bundle authority; errors/audits
must not contain it, passwords, provider keys, raw source bodies or customer data.
The181 read-only collection watchdog is NEVER used to cancel apply.

## A2 canonical actionable plan and one stale-baseline-safe transaction

Reuse bundle/baseline/proposal/import validators and deterministic comparisons.
Make representable reviewed creates and existing price/FX supersessions actionable
in a canonical typed plan bound by the existing authenticated artifacts. Prefer
existing validation.json for operation identity/details; JSON remains sole semantic
proposal, existing artifact set/signing chain retained. Necessary explicit context/
renderer versioning is allowed; unsupported archives fail honestly, no migrations
of sealed files/historical-renderer fleet. Collect/review still write no SQL.

Do not merely remove existing-row BLOCKED gates: prove and expose actual executable
operations and IDs/old/new/native currency/FX/effective-time behavior in the SAME
HTML and consistent CLI/JSON plan. Preserve first-screen readability, scope,
original/current generator distinction and full expanded evidence. New route
visibility to allow-all keys must be surfaced as a warning requiring acknowledgement.

Inside ONE transaction, obtain a consistent current projection of the reviewed
catalog and compare target and retained/scoped row facts against the captured
baseline BEFORE mutations. Use minimum adequate bounded PostgreSQL serialization/
lock strategy, fixed order, bounded lock/statement waits. It must serialize with
ordinary existing catalog edits as well as other applies; an advisory lock followed
only by new apply code is insufficient if ordinary writers can race the comparison.
A short appropriate table-lock strategy is a candidate, not a platform mandate.
Reusing export_baseline on another connection does not prove a locked writer view.

Bootstrap must prove the expected empty catalog, never convert a DB outage or
unexpected populated state to bootstrap. Provider-only existing setup can use an
explicit refresh baseline without fixed ten-price preparation. Existing providers'
destinations, secret environment names, enablement, timeout/retry settings and
other authority remain unchanged. Only missing reviewed OpenAI/Router provider
metadata may be created using existing validated services; no secret values.

Preserve route aliases/priorities/enabled/visible/streaming flags and all approved
denials. Refresh does not grant new hosted/local tools, endpoints, multimodal,
Responses/Codex authority or bypass exact+wildcard governors. Unscoped, retained,
disappeared, unsupported, ambiguous/multiple and non-flat rows stay unchanged
or block an explicitly required operation. No deletions or broad provider rewrites.

## A3 supersession, audit and durable idempotent outcome

For changed representable pricing/required native->EUR FX, use one effective T
chosen for this successful transaction, close prior active validity windows and
insert new rows. Preserve old amounts/currency/rates/source metadata/row identities;
never in-place reprice old rows. Source publication date is not local effective T.
Use existing Decimal/rounding/eligibility contracts; do not broaden pricing/tier/
fee representation. Missing FX/price fails closed. Unchanged rows are not churned.

One durable PostgreSQL application record with a uniqueness boundary must bind
canonical reviewed bundle identity, authenticated receipt/plan identity, operator
assertion/actualDBactor/reason, effective T, applied row IDs/counts and safe outcome.
Use existing AuditRepository in the SAME transaction. No filesystem-only applied
marker or check-then-insert race. Same reviewed bundle retries/concurrent duplicates
must return an observable committed result and never apply/charge/audit twice.
Check authenticated known-committed status before rejecting a retry merely because
its own successful apply changed the baseline. Distinguish a new stale bundle.

Mid-apply failure rolls back provider/route/price/FX/application/audit together.
Disconnect after commit must be recoverable by read-only status/idempotent retry,
not ambiguous replay. No rollback of completed usage/cost or deletion of history.
Any schema needed is a small additive application-record table/constraint, with
upgrade/downgrade and schema docs; no generic event journal/catalog-version system.

## A4 coherent request accounting during and after refresh

Demonstrated on real isolated PostgreSQL16.15: a writer superseded price and FX
atomically between existing PricingService's two reads. READ COMMITTED captured
old price1/newFX.9 -> EUR.0027; coherent old1/.5 ->.0015, new2/.9 ->.0054.
REPEATABLE READ was a coherent control, not a mandate for global isolation.
This is independent of approved R1/R2 and not an observed production incident.

Capture price and FX for applicable admissions from ONE coherent PostgreSQL view,
using a focused combined lookup or a short coherent read transaction. Freeze its
safe immutable facts and IDs through reservation, finalization and recovery.
No transaction/lock held over upstream HTTP, no global engine isolation change.
Do not assume two reads with the same Python timestamp create one database view.

Shared FX impacts Chat/strict Responses/Codex, hosted Responses pre-admission,
audio, embeddings and Realtime admission. Use a shared minimal seam and prove the
affected entry paths consume it, without changing endpoint/tool eligibility,
token estimation, provider-usage parsing, monetary formulae, overrun/fence/hold
law or PostgreSQL quota truth. Preserve complete Codex/cache/hosted pricing metadata
on captured facts; ordinary and exempt/fixed-request behavior stays compatible.

Existing ChatCostEstimate already stores unit prices, rate and row IDs; existing
AccountingService computes completed native/EUR costs from that capture, and
provider-completed recovery stores finalized facts in the durable ledger. Reuse
these paths. Old pending requests completing after refresh and provider-completed
recovery after refresh must retain their original captured pricing/FX, never query
new rows to reprice history. Unknown final hosted cost still holds/blocks the key.

## Exact allowed paths

- app/slaif_gateway/services/catalog_refresh/apply.py (new bounded orchestrator)
- app/slaif_gateway/services/catalog_refresh/planning.py (new small canonical-plan helper if needed)
- app/slaif_gateway/services/catalog_refresh/baseline.py (same-transaction projection reuse only)
- app/slaif_gateway/services/catalog_refresh/sealing.py (one verified captured-byte interface/version support only)
- app/slaif_gateway/services/catalog_refresh/filesystem.py (only necessary captured-descriptor reuse)
- app/slaif_gateway/services/catalog_refresh/validation.py (actionable typed-plan/review gates/current apply freshness only)
- app/slaif_gateway/services/catalog_refresh/rendering.py (plan/actions/apply-stage wording only, no redesign)
- app/slaif_gateway/services/catalog_refresh/execution_identity.py (fixed newly relevant owned paths/version metadata only)
- app/slaif_gateway/schemas/catalog_refresh.py (bounded plan/result/version contracts)
- app/slaif_gateway/cli/catalog_refresh.py (apply/status plus honest existing stage/help)
- app/slaif_gateway/db/models.py (application-record table only)
- migrations/versions/0025_catalog_refresh_applications.py (one new additive migration)
- app/slaif_gateway/db/repositories/catalog_refresh.py (new application-record/transaction helpers)
- app/slaif_gateway/db/repositories/pricing.py (supersession/coherent paired lookup only)
- app/slaif_gateway/db/repositories/fx_rates.py (supersession/paired lookup integration only)
- app/slaif_gateway/services/pricing.py (shared coherent immutable admission capture)
- app/slaif_gateway/schemas/pricing.py (necessary safe immutable pair/capture contracts)
- app/slaif_gateway/services/responses_gateway.py (hosted paired-facts integration only)
- app/slaif_gateway/services/chat_completion_gateway.py
- app/slaif_gateway/services/audio_gateway.py
- app/slaif_gateway/services/embeddings_gateway.py
- app/slaif_gateway/services/realtime_gateway.py
  (these four gateway files ONLY if shared capture requires small call-site integration)
- app/slaif_gateway/services/accounting.py
- app/slaif_gateway/services/reservation_reconciliation.py
  (these two ONLY if concrete preservation/recovery proof reveals necessary capture propagation; no redesign)
- tests/unit/test_catalog_refresh_apply.py (new)
- tests/unit/test_catalog_refresh_planning.py (new if helper added)
- tests/unit/test_catalog_refresh_policy.py
- tests/unit/test_catalog_refresh_report.py
- tests/unit/test_catalog_refresh_seal.py
- tests/unit/test_catalog_refresh_execution_identity.py
- tests/unit/test_cli_catalog_refresh.py
- tests/unit/test_pricing_service.py
- tests/unit/test_accounting_service_finalize.py
- tests/unit/test_provider_completed_reconciliation_service.py
- tests/unit/test_v1_responses_quota.py
- tests/unit/test_v1_chat_completions_forwarding.py
- tests/unit/test_v1_audio_forwarding.py
- tests/unit/test_v1_embeddings_forwarding.py
- tests/unit/test_v1_realtime_forwarding.py
  (existing forwarding tests only affected capture seams)
- tests/integration/test_catalog_refresh_apply_postgres.py (new primary transactional proof)
- tests/integration/test_catalog_refresh_baseline.py
- tests/integration/test_catalog_refresh_accounting_postgres.py (new financial/concurrency proof)
- tests/integration/test_repositories_accounting_and_pricing.py
- tests/integration/test_accounting_finalization_postgres.py
- tests/integration/test_provider_completed_reconciliation_postgres.py
- tests/browser/test_catalog_refresh_report.py (plan/action/stage facts only)
- docs/catalog-refresh.md
- docs/cli-reference.md
- docs/database-schema.md
- docs/accounting.md
- docs/pricing-catalog.md
- admin/catalog-refresh/README.md
- oap/orders/182-a-audited-atomic-catalog-apply.md (unchanged strategic bytes)
- oap/active (exact182-a, five bytes/no LF)
- oap/reports/182-a-audited-atomic-catalog-apply.md (new immutable report)

No other paths, dependencies, transport/source_evidence/collection redesign,
rootgovernance/message changes, unbounded fixture corpora, dashboard, new sandbox,
Codex invocation, source GET, provider/inference/email/production access, wrapper
scripts, or broad accounting subsystem change. Existing services/repositories/import
parsers outside allowed paths may be imported/reused unchanged. If another exact
path is essential, report concrete need before widening; preserve unrelated state.

## Acceptance and proportionate evidence

AP1 Real CLI with real owned PostgreSQL: sealed reviewed bootstrap -> confirmed
atomic create of both-provider supported metadata -> read-only status/CLI retry,
no API server needed. Real refresh baseline -> reviewed existing price+FX change
-> supersession at one T with IDs/history/audit/receipt identity and unchanged
routes/denials/unselected rows. Same single HTML explains actions/limitations.
AP2 Negative trust/intent/source: wrong key, coordinated tamper, symlink/rebinding/
TOCTOU between authentication and use, missing/unsupported context, partial/
BLOCKED/stale/wrong target/baseline, missing confirmation/reason/actor, warning
without ACK, unsupported monetary/capability/exposure plans. No SQL writes before
gates, safe output/audit no secrets/raw bodies. Current freshness clock explicit.
AP3 Real PostgreSQL interleavings: two different plans race same baseline;
ordinary catalog edit races apply; identical bundle concurrent/retry; bounded
lock failure; injected failure after partial stages rolls back everything;
commit-success/client-loss status recoverable; no duplicate history/audit.
AP4 Real PostgreSQL price/FX reader paused across atomic writer: pair always old
or new, never mixed, preserved boundary T/history; old pending completion and
provider-completed recovery after refresh use old capture/old ledger costs.
Exercise all shared affected admission seams, including hosted pair/fixed request/
EUR and non-EUR, unknown-rate fail-closed; fences/holds/quotas/content privacy remain.
AP5 Focused unit/CLI/seal/plan/price/accounting tests, targeted transaction/recovery
PostgreSQL files and only changed-boundary browser. Migrate fresh owned DB upgrade
head/downgrade0024/re-upgrade. Ruff/docs/diff and normal GitHub CI on finalhead.
No skipped-as-pass or full local DB/Redis/Docker/HPC matrix. Broaden only to reproduce
an actual failing CI job or the specific changed financial/concurrency boundary.

Owned isolated PostgreSQL setup is AUTHORIZED using existing Docker postgres:16:
unique named/labeled container, loopback-only ephemeral port, synthetic credentials,
no persistent/shared volumes, TEST_DATABASE_URL derived solely from this container.
TCP readiness must ignore temporary Unix-socket init server; migrate only this DB.
Never destructive setup against DATABASE_URL, shared5432, existingcontainers,
production/env configs or unrelated projects. Capture safe versions/results and
remove only identity/label-verified owned container. No packages/system installs
required; Docker available at unix:///var/run/docker.sock. DB-only network allowed
for these focused proofs; source/model traffic mocked/denied. Never print passwords,
DB URLs/private configs or protected data. Archive scratch/keys outside repo.

## Publication and execution economy

Commit/push strategic order and active unchanged with implementation, NEWunique182PR
from verified main. No merges/auto-merge. Keep changes minimal at existing seams;
use small isolated edits and focused failures, not large speculative all-or-nothing
patchers or new supporting infrastructure. Report concise requirement -> evidence
and exact commands/counts/versions/heads/CI/remaining limits; distinguish in-process
collector tests from actual CLI, mock from live, prior from current evidence.
Do not copy speculative prose or claim skipped/missing/pending proof as PASS.

Before atomic final report-path publication, ensure evidence/claims accurate.
After publication report immutable. Final report-only SELF commit firstparent MUST
be reported exact implementation head; only namedreport differs. Push/verify remote
PRheadSELF then exacttwo-byte responseOK/no LF and onecontrolwaiter explicit%9.
Strategy owns review/merge/numericprogression; no automatic nextnumber by coder.
182 mustsolvefullA1–A4/AP1–AP5 beforemerge, then183isolatedCodex and184finalcomplete
workflow. No claim the human's whole task is complete after this intermediate PR.
