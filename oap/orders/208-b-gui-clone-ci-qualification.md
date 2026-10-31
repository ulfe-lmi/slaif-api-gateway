# OAP Work Order — 208-b

PR mode: AMEND_EXISTING_PR
Base: main at 09cbfb4795e279ef04e7a54f933afbeeaa7022b6
Branch: oap/208-gui-key-clone
Title: Add reviewed key cloning to the admin GUI

## Objective and reason

Finish the existing208/G04 PR364 by fixing its demonstrated final-head CI
blocker. This is the SAME objective and PR, not another feature or a new PR.
The approved full GUI round207–219 remains in force; G05–G18 and final
whole-GUI field guidance/installed qualification are still later work.
Use ONLY the existing coding agent in right tmux pane%9, unchanged current
model/profile/effort. No helpers/subagents, nested coding sessions, merge,
auto-merge, release, tag, deployment or production mutation.

## Verified state and immutable inputs

208-a exact responseOK was received and its canonical root terminal85987 is
CLOSED. Root verified PR364 OPEN, unique208 branch above, and remote head
4335ecb014ecbdfbdf52b22ea0ea18456d9b1a15 (A SELF). SELF's first parent is
65ac0fd5543840383637d48fa71110cb9e3886a9 (A IMPL); only the new A report
differs. Product commit f8d9af4e4d44e7167612824dd99ff17efcbefaad plus that
documentation-index commit are the accepted implementation set.

A order SHA256 ca86edff0f72dc1d1dec56d13e7c6f964afc9f8740e29a3b6fbdf735ba96f297;
A report SHA256 346f2dfec2a2abb3c7a04dd88ddcc51e8f9e9da60d79d0eb4c8f85b010479894.
Preserve every activated order/report unchanged. Do not rewrite history to
combine legitimate implementation commits. Root owns this order and the
active pointer; commit/push their exact bytes unchanged.

Live recheck before activation 2026-10-31T21:39:39.854656+00:00: remote main remains the base
above; PR364 is OPEN/MERGEABLE at A SELF, the sole208 PR. All10
final-A checks are present:8SUCCESS, the identified Unit failure, and
PostgreSQL integration IN_PROGRESS on run41243331544. Browser, E2E,
Compose, docs and analyses passed. Local B work may start now, but the
no-push-until-parent-run-terminal condition below preserves that final
pending job. Release remains v0.1.0-rc.1; ruleset23580289 active with
no bypass actors; only unrelated DependabotPR319 is also open.

The demonstrated failure is tests/unit/test_main_app_structure.py::
test_main_app_only_wires_app_and_routes: assert87<84. CI unit job124661804858
on run41243331544 reports1FAILED,6687PASS,1SKIPPED. That skip is not a pass.
The new router's legitimate import/include/comment lines exceed the brittle
source-line budget; independent source review confirms main still only
composes the app. The failure log is /tmp/slaif208/ci-final-unit.log.

Automated comments: PRRT_kwDOSLm-qM6yUwAr identifies unused _CLONE_FORM_FIELDS
in api/admin_key_clone.py. PRRT_kwDOSLm-qM6yUwAk (BaseException in browser _db)
was independently reviewed and RESOLVED by root: its body AST is identical
to accepted207's worker bridge; it retains and re-raises the original error
on the caller thread and disposes the engine. Do not alter that intentional
exception transport merely to silence a comment.

The sole detached coding waiter was verified PID1989692, exact argv
bash wait-control-and-wake.sh, PPID1, cwd strategic root, TMUX_PANE=%9.
Root rechecks it and fixed true FIFOs4501469/4501470 before ONE controlOK.
Actual roots are /home/janezp/codex-work/slaif-api-gateway and
/home/janezp/codex-supervision/slaif-api-gateway; never substitute FIFOs.
Protected untracked CODEX-SESSIONS.md SHA256
5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda and codex.sh
SHA25666eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247
remain unchanged/uncommitted. Preserve ignored secrets/catalogs/worktrees,
permanent objective-neutral message.txt and unrelated changes. No reset,
clean, stash, work-order edits, force push or unauthorized Git manipulation.

## Bounded repair and acceptance

1. In tests/unit/test_main_app_structure.py, replace the brittle total-line
   count with small, meaningful structural checks for the existing main-as-
   composition contract. Keep the health/route/authentication and existing
   no-business-orchestration assertions. The guard must permit ordinary
   router imports/includes without a ceiling increase each time, and still
   reject business/service/repository orchestration or inline API handlers
   in main. Standard-library AST inspection is sufficient; no new test
   framework, production refactor, exhaustive call allowlist or dependency.
   Do not simply delete the guard, raise an arbitrary ceiling or compress
   source whitespace to game it. No change to inference/auth/accounting law.

2. Remove only the genuinely unused _CLONE_FORM_FIELDS tuple from
   app/slaif_gateway/api/admin_key_clone.py. Its form parameters and actual
   validations remain unchanged. Do not remove delivery-mode, schema or
   permission allowlists. No other GUI behavior or review/delivery/recovery
   redesign, no new features, new module/profile acceptance or schema.

3. Check actual remaining A CI results for any further demonstrated failure
   before pushing the B implementation or publishing its report. Start the
   bounded local repair while that last A job runs, but DO NOT push until
   run41243331544 is terminal: a push would cancel the remaining A job and
   hide useful failure evidence. Root is watching that exact run in70081;
   ordinary bounded read-only GitHub polling is enough, no duplicate watcher
   framework. Routine tightly related fixture/oracle corrections
   belong here on PR364. If a materially different defect is discovered,
   report its exact evidence before expanding production scope. Never alter
   A's immutable report to turn its failed CI into a pass.

## Exact scope and proportionate verification

Allowed paths: tests/unit/test_main_app_structure.py;
app/slaif_gateway/api/admin_key_clone.py (dead tuple only);
docs/verification/gui-cli-parity.md (concise208-b qualification/CI chronology);
docs/MISSING_GUI_FUNCTIONALITY.md and docs/verification/README.md only for
necessary current status/link corrections; this exact B order, active=B,
and one new final B report. main.py needs no business/formatting change.
No schema/model/migration, core clone execution, token helper, templates,
JS/assets, CLI, backend/client adapters, provider IO or worker changes.

Run the focused main-structure tests plus9 OAP governance cases, native Ruff
and diff/documentation checks on the resulting bounded changes. No local
full unit/integration/browser/CLI matrix. The A focused evidence is accepted
and unchanged:47unitPASS (unit-208a-4.xml),4realPGPASS,14coexistPASS
(10accepted207+4new208, not18distinct),3realChromiumPASS including actual
keyboard and no-JS apply; all no-skip. Reuse it, including source/target
isolation, exact3601s, operation repeat/recovery, actor/session/CSRF/tamper,
known-secret masking and synthetic post-commit delivery failure. Do not
rerun these unchanged workflows just for the suffix or index wording.

Use /tmp/slaif192-coding-venv and /tmp/slaif208 for focused local outputs.
This repair needs no new DB, container, provider/mail, package setup or
framework. Keep secrets/tokens/key material out of logs, assertions, docs
and reports; no environment/credential dumps. No secret/content storage or
authority expansion; PostgreSQL accounting, replay ownership, existing
review integrity/expiry/actor/delivery and one-time-channel law are unchanged.

Update the SAME living verification record with actual A CI failure and B
repair/results, accepted reused component evidence, and honest final-head
pending status. Keep operator/upgrade instructions: ordinary API/assets
rebuild/restart, no schema or existing-key migration; no production action
is authorized. Do not create another inventory or verification record.

## Publication and report duties

Commit/push exact strategic B order and active pointer with the repair to
the SAME branch/PR364. Keep the title/description about the resulting clone
feature and incorporate the bounded CI qualification; no new PR. Verify the
remote non-report implementation head and update PR364 BEFORE the report.
Inspect final-code CI and fix routine in-scope failures before completing
the report; pending/skipped/missing checks are not passes. Root alone owns
final-head review and merge. Multiple implementation commits are permitted.

Build the complete B report outside its final path. Publish to the absent
new final B filename through a temporary file INSIDE oap/reports, flush and
fsync it, os.replace/rename on that filesystem, then fsync the directory.
Never cp/cat/append directly to the final name or alter any finalized report.
Commit only the complete new B report in SELF; literal final IMPL SHA must
be SELF's first parent and only that report may differ. Verify pushed remote
PR364 head==SELF and report bytes/topology, then ONE exact two-byte responseOK
and exactly ONE verified detached control waiter in pane%9. State commands,
counts, reused versus newly run evidence, limitations and cleanup honestly.
No merge/auto-merge; root accepts, merges, verifies actual main and records
timing before any209 activation.
