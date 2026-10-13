# OAP Work Order — 182-c

PR mode: AMEND_EXISTING_PR

## Objective/reason and verified state

Close three precise proof defects and DB-network documentation on existing
Objective182/PR320. No new product scope or supporting infrastructure. Retain
all original182-a A1–A4/AP1–AP5 and182-b evidence. Read the strategic
OBJECTIVE-182-B-STRATEGIC-REVIEW.md, original orders, repository governance/
coding protocol and relevant accounting/catalog/schema contracts.

Reconciled2026-10-13: main60214c54226a9b488666e8a849fe9f326faf8218 (accepted181).
Unique182PR320 OPEN branch oap/182-atomic-catalog-apply/base main. Current
SELF73578577c04760ef0a5027ecb37c2e242b049781, firstparent implementation
16489a85d100b8918eb9c965aa85c0c2422ed640; only182-breport differs; all10SELF
checks SUCCESS; noauto-merge. Prior182-b exact order SHA
1b7e5f487fac657e9d4db6d3c3291a30738edc490fe5f6d8ee3ae1768c0b9bb6,
report SHA133e803ab8325f197148dbec5ba7a44e9b3626d4a5c5df7a34cc5615ef92cc1b.
Sole responsehelper61492 exactOK/exit0 consumed/CLOSED; never poll/resignal it.
Independent finalarchive: real ownedPG16.15 23integrationPASS/0skip, six unit
files171PASS/0skip; ownedcontainerremoved. No runtimechange in182-b.
Unrelated319/protection/release unchanged; no release/prod authority.

Roots /home/janezp/codex-supervision/slaif-api-gateway (strategy) and
/home/janezp/codex-work/slaif-api-gateway (coder). Verify actualFIFOs at strategy
control.fifo/response.fifo. Coding2075296/%9/pane1703557/tmux7:0; strategy%8.
Sole codingcontrolwaiter2714812 observed; reverify before signal.
Preserve CODEX-SESSIONS.md/codex.sh/.codex/localcatalogs/worktrees/copiedvenv/
savedhumanedit. Do not manipulate Git to activate; coder owns Git. Current
worktree otherwise clean. message.txt stays neutral/objective-independent.

## C1 Make the existing reader test deterministic

In test_default_isolation_paired_capture_price_and_fx_across_actual_apply,
the lock_held event currently signals arrival but does not pause the writer.
Add a second test-local release event: actual writer holds its transaction and
catalog locks while reader captures complete OLD price+FX; reader releases it,
writer commits, fresh reader sees complete NEW values AND rowIDs. Assert actual
READ COMMITTED. Keep paired-oneSQL/no extra estimateSQL and history boundary
evidence. Bound event/task waits and clean up/release on exceptions; no sleeps
as synchronization, no production hooks/locks/isolation/instrumentation change.

## C2 Qualify retry beyond actual finite expiry

In test_aged_retry_returns_original_outcome_and_refuses_new_stale_work, advance
the test clock past the ACTUAL reviewed finite future valid_until (seed currently
now+30d, test advances only3d). Assert frozen now is later than that end and source
freshness limit. Same authenticated bundle returns original actor/T/counts,
new unapplied stale bundle still refuses, no extra rows/audit or resealing.
Do not renew source timestamps, relax freshness or change production clocks.

## C3 Prove actual provider-completed recording into recovery

In test_provider_completed_recovery_after_refresh_uses_real_old_capture_facts,
reuse real capture -> real estimate -> reservation, but persist provider completion
through existing AccountingService.record_provider_completed_before_finalization.
Use the existing finalization-failure state transition to make it eligible for
provider-completed recovery. Avoid manually synthesizing the usage row/metadata;
the purpose is to qualify the production writer's capture-to-ledger propagation.
After actual price+FX apply, assert recovery uses original persisted native/EUR
costs and price/FX IDs, correct quota counters, safe metadata/no content and ZERO
new pricing/FX queries. Reuse existing failure/recovery helpers; no accounting
redesign or new state machine. Repair runtime only if this concrete case fails
and only at previously permitted capture propagation seams.

## C4 Honest documentation/report

Correct docs/catalog-refresh.md Limits: status and export-baseline use PostgreSQL,
review --db-url may read baseline; verify is offline. Clearly distinguish DB
network from source/provider/research traffic. No broad doc rewrite.
New report explicitly corrects182-b section3.1: real bootstrap is reviewexit10
with new_model_exposure ACK, two providers/routes/USDprice rows plusoneFX;
retained third row/finiteend belong to seeded refresh, not bootstrap. Report actual
three proofs rather than inheriting overstated claim. Priorreports IMMUTABLE.

## Exact allowed paths / non-goals

- tests/integration/test_catalog_refresh_apply_postgres.py (C2 only)
- tests/integration/test_catalog_refresh_accounting_postgres.py (C1/C3 only)
- docs/catalog-refresh.md (C4 only)
- oap/orders/182-c-deterministic-accounting-evidence.md (unchangedstrategicbytes)
- oap/active (exact182-c,5bytes,no LF)
- oap/reports/182-c-deterministic-accounting-evidence.md (new immutable)

Only demonstrated C3 propagation failure permits minimal services/accounting.py
or services/reservation_reconciliation.py change under182-a's original conditional
scope; report failure/need before widening. No other paths/dependencies/schema/
transport/research/sandbox/platform/endpointcapability/monetary-policy changes.
No real source GET/provider/inference/email/Codex/production/import/release/tag/
deploy/protectedsecret access. Original authentication/secret/privacy/tool/hold/
fence/quotas/pairedcapture invariants unchanged. Need anotherpath? Identify exact
concrete necessity first. Do not rerun or extend unrelated test matrices.

## Setup, verification, report and stopping boundary

Reuse Python3.12.15 /tmp/slaif-181c-strategic-venv and existing explicitly owned
label+IDverified182-a DockerPG16.15 with a NEW disposable test database, or new
uniquelabelled loopbackephemeral/tmpfs postgres:16 at unix:///var/run/docker.sock.
Derived TEST_DATABASE_URL only; never DATABASE_URL/shared5432/real.env/unrelatedDB.
TCP readiness, synthetic credentials; never print passwords/fullURLs/private data.
Remove only verified owned resources. No system install needed.

Run three changed cases and the two focused integration files to catch their shared
fixture interactions (23 tests); zero skips. C1 repeat focused case only if needed
to demonstrate deterministic cleanup/scheduling. Ruff/diff/documentation check;
normal required finalheadCI. Units/browser/migrations inherited unchanged; no new
full local matrix. Runtime fix, if justified, demands its changed-boundary tests.

Commit/push exactstrategic order+active on samebranch/PR320, never newPR/merge/
auto-merge. After accurate evidence, atomicallypublish unique report with literal
implementationSHA and Report publication commit: SELF; onlyreport differs in
finalSELF and firstparent is implementation. Verify remotePRheadSELF then send
exact2byte responseOK/no LF ONCE and enter one controlwaiter verified%9.
Strategy independentlyaccepts/merges/times182 before any183 activation;184 final
workflow still required. No fullgoal-complete claim at this intermediate boundary.
