# OAP Work Order — 182-b

PR mode: AMEND_EXISTING_PR

## Objective and reason

Complete the missing acceptance evidence for the existing administrator
refresh -> one authenticated REVIEW.html -> confirmed audited atomic PostgreSQL
apply. Prove actual price AND FX changes and old-request accounting, concurrency
and recovery. This amends Objective182's sole PR320. It does not expand product
scope: all A1–A4/AP1–AP5 from immutable182-a remain required. Reuse implemented
services and test helpers. Repair runtime only when a focused proof demonstrates
a concrete defect. Do not build supporting infrastructure to satisfy test prose.

Read strategic OBJECTIVE-182-A-STRATEGIC-REVIEW.md and the original182-a order,
repository governance/coding protocol and current catalog/accounting/pricing/
schema/security/CLI contracts. CATALOG-REFRESH-IMPLEMENTATION-MANDATE.md retains
all human requirements. Objective183 is isolated Codex;184 final workflow.

## Verified state and exact publication identity

Reconciled 2026-10-13T17:08 UTC (reverify before execution):
- Main60214c54226a9b488666e8a849fe9f326faf8218; accepted181 PR318 terminal.
- Unique182 PR320 OPEN, base main, branch oap/182-atomic-catalog-apply.
  Current SELF a2a198a586a0187afd3f7725ab057eb3245f29a0, first parent
  implementation7f5965801cc1a97729abf2c630c9de770b84d880. SELF only changes
  oap/reports/182-a-audited-atomic-catalog-apply.md. All10 SELF checks SUCCESS.
- Prior order SHA448372eb53cd589108fcaf12dd18388d7826e2abc491fe47ab8e21b8eb9612c3;
  prior report SHAabe6e09f56f36d29c30fac0214a94a780b05461f50f6170ac78fbdbc474527ca.
  Both IMMUTABLE; never revise their claims or bytes.
- Sole182-a response helper89941 consumed exactOK/exit0 and CLOSED. No reread,
  resignal or duplicate reader for182-a. New182-b will receive its own sole helper.
- Unrelated319 remains open/untouched. Ruleset23580289 active, no bypass,
  deletion/nonFF prohibited; merge commits allowed. No auto-merge/release authority.
- Shared checkout clean except preserved untracked CODEX-SESSIONS.md/codex.sh.
  Do not reset/clean/stash/switch Git for activation. Coding agent owns Git.
- Actual tested Qwen coding agent2075296 in tmuxsession7/window0/pane%9,
  panePID1703557; strategy%8. Sole control waiter2684420 under coding agent
  observed; reverify. Use existing source codex.sh; codex --yolo --profile
  qwen-neumann session. No collaboration-agent substitution.
- Exact roots /home/janezp/codex-supervision/slaif-api-gateway and
  /home/janezp/codex-work/slaif-api-gateway. Verify exact control.fifo and
  response.fifo are FIFOs in strategic root. message.txt remains neutral.
- Migration head0025_catalog_refresh_applications. No additional migration planned.

## B1 Real CLI both-provider bootstrap and price+FX refresh

In a fresh owned migrated PostgreSQL database, use the actual CLI review (or
mocked actual collect) -> same sealed HTML -> apply --confirm/actor/reason/ACK
-> status/retry. Build minimal current, internally consistent captured official
source fixtures for BOTH OpenAI/OpenRouter with supported native USD prices and
required deterministic ECB-derived USD->EUR FX. No real GET/provider key.
Do not just edit currency fields while source evidence still says another value.

Assert exact sealed plan identities/operations and actual committed provider,
route, pricing, FX, application and audit rows. Bootstrap must create required
FX, with one T, correct direction/Decimal values, IDs and receipt binding.
Refresh the real exported baseline with changed representable prices AND FX.
Assert supersede_pricing AND supersede_fx, same T for all closes/opens, original
values/currency/source metadata/IDs preserved, exact old/new boundary and
durable affected IDs/counts. Include a reviewed finite future old validity end.
Retained/unselected rows and existing provider/route flags/aliases/denials stay
unchanged; reuse existing fixtures to keep this bounded. Warnings require ACK.
The same REVIEW.html must state this actionable plan; preserve browser layout.

Inject failure after actual FX mutation (and any price mutation before it),
before application/audit completion. Assert ALL affected old windows/amounts
and row sets, plus provider/route/application/audit, roll back together. Merely
rolling back a EUR-only bootstrap is not FX rollback evidence.

## B2 Default-isolation admission and historical accounting

Use actual PricingRulesRepository/PricingService on real PostgreSQL at default
READ COMMITTED. A deterministic paused reader spans the ACTUAL reviewed apply
which supersedes both native USD price and USD->EUR FX. Assert value AND row-ID
pairs always match complete old or complete new facts. Prove one paired SQL
capture and zero extra price/FX SQL during supplied-capture estimation; establish
the interleaving with explicit events/hooks at existing test seams, no timing
lottery or production instrumentation. REPEATABLE READ may remain a control,
but cannot be the qualifying test. No global isolation change or lock held over
HTTP. Keep freshness/effective timestamps explicit so historical-at reads are
distinguished from fresh current admissions.

Build the actual admission estimate using the pricing service and retain that
same captured estimate and IDs through reservation -> refresh -> finalization.
Do not reconstruct an estimate by hand after refresh. Verify actual native/EUR
ledger costs, pricing/FX provenance and quota counters use old facts, while new
admissions use new facts. Exercise existing provider-completed recording and
recovery with these real old estimate-derived persisted facts after refresh;
recovery must never query new pricing to reprice history. Preserve privacy and
existing reconciliation/hold/fence law.

Cover the five changed families through a compact focused capture/estimate
matrix using the real shared pricing seam: Chat, strict Responses/Codex pricing,
Audio, Embeddings, Realtime, and hosted Responses pre-fence facts/reuse. Existing
endpoint unit fixtures are reusable for call-site integration; do not rebuild a
full HTTP endpoint matrix locally. Include EUR identity, USD FX, missing-rate
fail-closed, fixed-request and relevant hosted/Codex/cache metadata. Do not grant
new capabilities to the standard-v1 catalog. Existing real-PG hosted fence/hold
tests and CI remain regression evidence, not proof of new live tool authority.

## B3 Actual executor concurrency and recoverable outcomes

Keep the existing different-plan race and helper lock matrix. Add focused real
executor cases:
- Identical authenticated bundle concurrent apply: one committed, other
  already_committed, identical prior record/T, one history change/application/
  catalog_refresh_applied audit. Distinct actor assertions cannot overwrite it.
- Ordinary catalog edit and actual apply interleave around comparison/mutation:
  ordinary writer either commits before locked comparison causing stale refusal,
  or waits until apply commit. Show committed facts cannot be silently lost.
- Hold a conflicting catalog lock and invoke actual apply: production bounded
  lock failure returns safe CLI/service refusal, no partial writes/records/audit,
  transaction cleanup complete. Shorten only a test-local timeout seam if needed;
  do not change production settings just for runtime economy.
- Inject loss of the client result AFTER the database commit, using an existing
  transaction/CLI-return test seam. First caller observes the simulated loss;
  a separate authenticated status and retry recover the same committed outcome
  without duplicate writes/audits. Successful apply followed status alone is
  not a loss injection.
- After successful apply, advance a test clock past source freshness and a
  reviewed finite validity end. Authenticated retry still returns original
  actor/T/counts; new unapplied stale work remains refused. No archived timestamps
  are refreshed/resealed and no freshness policy is relaxed.

## B4 Documentation and honest report

Correct current catalog-refresh docs' mismatched execution codes to actual
implementation (apply_baseline_stale, apply_admin_unknown,
apply_supersession_guard_failed), and clarify chosen T is after checks, not
necessarily at transaction start. Distinguish permitted DB network from absent
source/provider/research network. Keep claims limited to proved behavior.
Do not retrofit182-a report. New report must explicitly distinguish inherited
greenCI/62 independent unit passes from new actual182-b proofs, with exact
commands/counts/default isolation/interleavings and all remaining limits.

## Exact allowed paths and non-goals

Primary edits:
- tests/integration/test_catalog_refresh_apply_postgres.py
- tests/integration/test_catalog_refresh_accounting_postgres.py
- tests/unit/test_pricing_service.py
- tests/unit/test_catalog_refresh_apply.py
- tests/unit/test_v1_responses_quota.py
- tests/unit/test_v1_chat_completions_forwarding.py
- tests/unit/test_v1_audio_forwarding.py
- tests/unit/test_v1_embeddings_forwarding.py
- tests/unit/test_v1_realtime_forwarding.py
- docs/catalog-refresh.md
- docs/accounting.md
- docs/pricing-catalog.md
- docs/cli-reference.md
- oap/orders/182-b-price-fx-workflow-evidence.md (unchanged strategic bytes)
- oap/active (exact182-b,5bytes,no LF)
- oap/reports/182-b-price-fx-workflow-evidence.md (new immutable report)

Only if a focused case demonstrates a runtime defect: existing182-a authorized
apply/planning/validation/baseline/sealing/filesystem/CLI catalog-refresh paths,
db/repositories/catalog_refresh.py, pricing.py, fx_rates.py,
services/pricing.py, schemas/pricing.py, and the five already modified gateway
services. accounting.py/reservation_reconciliation.py only for demonstrated
capture propagation need as182-a originally permits. Report exact failure and
minimal repair before claiming completion. No new table/migration/dependency.
If another exact test/fixture path is necessary, identify concrete need before
editing; prefer inline small fixtures and existing helpers. Prior approved fixture
repairs stand as history; they do not license unrelated edits in this round.

No transport/source registry/research redesign, renderer redesign, new sandbox,
dashboard/wrapper, broad accounting framework, production/import/inference/email,
real source GET, Codex invocation, protected secrets, release/tag/deploy or altered
root governance/message. No global isolation or monetary/eligibility change.
Preserve authenticated handle/capture reuse and all existing negative gates.

## Setup, verification, publication and stopping boundary

Reuse Python3.12.15 /tmp/slaif-181c-strategic-venv and existing Docker postgres:16
at unix:///var/run/docker.sock. Existing explicitly owned182-a synthetic container
may be reused after ID/label verification, with a NEW disposable database for
this evidence to avoid prior-suite state. Otherwise create unique labelled
loopback-ephemeral/tmpfs synthetic instance. Never DATABASE_URL, shared5432,
real .env, existing unrelated DB/containers. Use only derived TEST_DATABASE_URL;
TCP readiness; no printed passwords/full URLs/private data. Remove only verified
owned resources. Preserve broken copied.venv, untracked files, .codex, local
catalogs, worktrees and archived human edit. No system packages required.

Run just these changed unit/PG boundaries plus relevant existing finalization/
recovery/hosted regression cases when needed. Record zero skips as PASS condition.
Ruff, git diff --check, documentation check; normal GitHub CI all required checks
on implementation and SELF. No full local matrix. No new browser run unless
rendered behavior changes; inherited final-head browser plus new CI suffices.
Original migration fresh/downgrade0024/re-upgrade evidence is inherited unless
schema changes (not planned).

Commit/push unchanged strategic order/active on same branch/PR320; never new PR,
merge or auto-merge. Fix in-scope failures, then atomically publish unique immutable
report with literal implementation SHA and Report publication commit: SELF.
Only that report differs in final SELF; first parent matches implementation.
Push and verify remote PRheadSELF, send exactly2byte responseOK/no LF once, then
one blocking control waiter in verified%9. Strategy reviews/merges/progresses.
If a boundary cannot be proved, report NOT PROVEN rather than full completion.
182 remains unresolved until all original acceptance gates are satisfied.
