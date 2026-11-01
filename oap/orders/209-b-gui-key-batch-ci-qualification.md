# OAP Work Order — 209-b

PR mode: AMEND_EXISTING_PR
PR: 365 — Add reviewed atomic key batch changes to the admin GUI
Base: main at a4ed3ae68851ecbe0cb6862106abc287f3d6af55
Branch: oap/209-gui-key-batch
Current head: cadc9b30eca3f64b76ef38003235d25d5c96f0b0

## Objective, reason and authority

Qualify the two demonstrated blocking CI failures from the G05 key-batch
implementation, on the SAME PR365, and correct the factual qualification
record. This is a narrowly bounded continuation of209, not another feature
round or a new PR. The approved whole-GUI207–219 mandate remains active:
G06–G18, existing/new field guidance and final installed219 are still required.

Use ONLY the existing coding agent in right tmux pane%9, retaining its
human-owned model/profile/effort. No helper agents, nested coding sessions,
merge/auto-merge, history rewrite, release/tag/deploy or production/provider/
mail actions. Root retains strategic/material review, final-head gates and
delegated merge. No further human authorization is needed for this ordinary
same-PR repair.

## Verified GitHub/OAP state at activation

At 2026-11-01T01:40:07.554795+00:00, remote main is a4ed3ae68851ecbe0cb6862106abc287f3d6af55.
PR365 is the unique open209 PR, nondraft, branch oap/209-gui-key-batch to
main, current head cadc9b30eca3f64b76ef38003235d25d5c96f0b0. Only unrelated
Dependabot319 is also open. Active ruleset23580289 enforces deletion and
non-fast-forward protection with no bypass actors. No release/deployment is
authorized. Do not substitute old compact-state snapshots for live truth.

Root independently verified A IMPL2aaf11d2714ec7e24c732293f3ef7088a2b1ba7c,
parent acceptedmaina4ed3ae, tree475cd530e850ef5c0b2a7ef86b8fd841fc144a99,
27 bounded paths. All14 product/proxy file SHA256 values match the reviewed
source. A SELFcadc9b30eca3f64b76ef38003235d25d5c96f0b0, tree
967b412c2941c5af24bf1c0d0d0754fdadaa2f64, firstparent exactly A IMPL; only
oap/reports/209-a-gui-key-batch.md differs. Its local/Git/remote bytes match:
18,958 bytes, SHA2560116767a272b60e44cbd3da4a8f53d2433916b8589a5a198b3d0194c92f29747.
A order remains18,960bytes SHA256
e16fe3c2fc951136723ea7373293f94031bab8c50111d7aa0337907f5f7d6c5b.
Preserve both finalized files exactly. Never edit A to fix its statements.

The A implementation CI run41261553792, unit job124715694142, completed
FAILURE at2026-11-01T01:36:04Z. Its actual job log identifies these two
failures, independently reproduced locally on unchanged A SELF by root
terminal86469 (CLOSEDexit1, two cases/two failures):

1. tests/unit/test_documentation_contract_drift.py::
   test_external_tool_policy_contract_consumers_remain_allowlisted:
   new api/admin_key_batch.py imports the authoritative external-tool
   contract constant but is absent from the finite consumer allowlist.
2. tests/unit/test_admin_slaif_design.py::
   test_table_wrappers_are_labeled_and_focusable:
   actual24 wrappers versus historical expected23. The added batch wrapper
   already has its required role, keyboard focus and accessible label.

A SELF CI has started; pending is not pass. Its product/tests are identical
to A IMPL, so the demonstrated failures justify this repair without waiting
for that report-only run to reproduce them. Do not invent another failure.
If another material final-head failure occurs, inspect the actual evidence
and keep routine in-scope qualification within this B order before report.

Root62671 has returned exact RESPONSE_OK_EXACT and is CLOSED forever; do not
repoll or resignal A. Root verified ONE detached coding control waiter:
bash2201380, PPID1, cwd strategic root, TMUX_PANE%9. Fixed true FIFOs retain
inodes4501469(control) and4501470(response). No second waiter/reader.

Actual roots: repository /home/janezp/codex-work/slaif-api-gateway;
strategic /home/janezp/codex-supervision/slaif-api-gateway. Root publishes
this complete order and exact active209-b in the shared worktree before
sending ONE controlOK; commit the strategic-authored bytes unchanged.
Coding agent owns Git execution; root performs no reset/clean/stash/switch.
Keep permanent objective-neutral message.txt unchanged.

Protected untracked CODEX-SESSIONS.md SHA256
5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda and codex.sh
SHA25666eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247
remain unchanged/uncommitted. Preserve ignored .env/.codex, catalogs,
worktrees and unrelated state. No credential/environment dumps or cleanup.

## Read and preserve current contracts

Refresh repository AGENTS.md, OAP-COMMUNICATION-coding-agent.md, this order,
the exact two failed tests, api/admin_key_batch.py's import and
_batch_requires_fenced_confirmation, current batch/schema contracts and the
existing SAME docs/verification/gui-cli-parity.md. Use the compact strategic
ARCHITECTURE-for-agents.md; do not load full architecture/archives/catalogs
without a concrete unresolved detail. A's accepted component evidence below
remains valid for its scope and should not be rerun merely for a B heading.

## Exact required changes and allowed paths

1. tests/unit/test_documentation_contract_drift.py ONLY the demonstrated
   consumer registration: add the exact path
   app/slaif_gateway/api/admin_key_batch.py to allowed_consumers, with a
   concise explanation that it reads EXTERNAL_TOOL_FENCED to present and
   require the existing fresh apply-time acknowledgement. The reviewed input
   policy determines that UI gate; shared KeyBatchService/KeyService still
   own validation, current authorization, fences/holds and execution. This
   grants no runtime hosted-tool authority. Preserve every existing consumer,
   whole-tree scan, operator-limit assertion and rejection of unlisted
   modules. No wildcard API allowlist, skipped test or contract duplication.

2. tests/unit/test_admin_slaif_design.py ONLY update the demonstrated wrapper
   count23→24 for the new batch scroll region. Preserve the per-wrapper
   role=region/tabindex=0/nonempty aria-label assertions and all other design
   tests. The product wrapper is already correct; do not change its markup.

3. Correct and consolidate the current factual qualification record in SAME
   docs/verification/gui-cli-parity.md, its README.md index and a compact B
   status note in docs/MISSING_GUI_FUNCTIONALITY.md. Add necessary brief
   operator clarification in docs/admin-usability.md if useful. Do not create
   a second verification document or repeat inventories. Explicitly record:
   - actual A IMPL CI failure, its run/job/time, both failed cases, root's
     exact two-case reproduction and B's narrow guard qualification;
   - A's immutable statement that no CI run existed/pending implementation
     checks is superseded by actual GitHub evidence, not rewritten;
   - A's claim that core plans require at least one selected key is false.
     KeyBatchService.plan permits an empty cohort/status selection and the
     strict schema's selected_count minimum is0. The standard empty row is
     valid for that outcome; no service/parser change is needed;
   - Core membership is rechecked after the last selected-key lock under
     the existing READ COMMITTED law. Later joins are untouched; do not
     imply serializability or a new lock guarantee;
   - A's native proof remains scoped as recorded, final B-head CI pending
     until actually green, and the whole-GUI goal remains incomplete.
   Keep real field-value snapshots distinct from physical-byte equality;
   preserve the corrected80/81 unit-receipt chronology. Update the SAME
   PR365 title/body around the final G05 feature and actual final evidence.

4. This order, exact oap/active=209-b, and ONE new final report
   oap/reports/209-b-gui-key-batch-ci-qualification.md.

No other product/source/static/proxy/CLI/service/schema/accounting changes
are authorized by this tiny repair. Do not remove the authoritative constant
import to evade its review guard. No request/permission acceptance change,
secret/capture/replay surface, infrastructure, dependency or workflow change.
No modification of tests/unit/test_oap_governance.py or old orders/reports.
If a new real product defect needs another exact path, report the concrete
evidence to root before changing that boundary; do not invent a scope issue.

## Acceptance, security and proportionate verification

The two actual failed cases pass, finite import-consumer review remains
effective, and every scroll region is still labelled and keyboard-focusable.
No product bytes change from A, no policy authority widens, no authentication/
CSRF/fresh confirmation is bypassed, provider secrets remain isolated, and
PostgreSQL accounting/replay ownership are untouched. Negative/privacy/
transaction evidence from A remains accepted for unchanged product code.

Use existing /tmp/slaif192-coding-venv and /tmp/slaif209. Run the two affected
test modules (which include both failed cases) ONCE after the fixes, with
actual case/failure/error/skip counts. No need for a second subset run after
the full modules pass. Run9 OAP governance cases on the byte-exact B order,
Ruff on current PR-changed Python files (small finite set), existing
documentation checker and git diff --check. Reuse unchanged A proof:
81 focused unit,119 inventory,73 related,6 nativePG,20 coexistence
(6new209+14reused),7 nativeChromium and scoped root component probes.
Do not rerun these unchanged local suites, PostgreSQL/browser/CLI/provider/
Codex matrices or new duplicate inventories. Normal final-head CI provides
the broad required regression gate; skipped/missing/pending is never pass.

No new package/runtime/Docker setup is needed for this test/docs repair.
Use only synthetic existing fixtures, bounded safe failure summaries and
Boolean canary assertions. Never print whole CI assertion-source expansions,
secret values, raw request content or environment/DSNs. Distinguish actual
qualified app/PG/browser proof from synthetic/fake-persistence tests; there
is still no live inference, final billing or installed219 qualification.

## Publication, immutable handoff and root gates

Amend ONLY existing PR365 on oap/209-gui-key-batch. Preserve A SELF and its
parent/history. Multiple ordinary implementation commits are allowed, no
force push or history rewrite. Commit this B order/active unchanged with the
two test/doc corrections, push and verify remote IMPL/PR identity; update
the PR description before final report. Keep routine fixture/docs/claim
corrections within B until its immutable handoff, not another repair round.

Build the complete B report outside its final path. Check final target is
absent; write a temporary file INSIDE reports, flush/fsync, os.replace/rename
on the same filesystem, fsync directory. Never write/append/copy a partial
report directly to its final name or rewrite a finalized report. Report
literal final B IMPL SHA; report-only SELF firstparent equals that IMPL and
ONLY the B report differs. Verify remotePRhead=SELF and exact topology/bytes
before sending exactly ONE two-byte responseOK (no newline). Then install
exactly ONE detached control waiter for the same pane%9 and wait.

Root independently reviews B/A claims, immutable topology, exact diff,
documentation/architecture/security/privacy/accounting, reviews and every
required final-SELF check. Coding agent NEVER merges/enables auto-merge.
Only root may guarded-merge PR365 after all final gates pass; root must
verify actual remote main/all required workflows and record timing before
activating210. No release/tag/deploy or whole-GUI completion claim follows.
