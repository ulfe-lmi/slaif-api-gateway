# OAP Work Order — 209-a

PR mode: CREATE_NEW_PR
Base: main at a4ed3ae68851ecbe0cb6862106abc287f3d6af55
Branch: oap/209-gui-key-batch
Title: Add reviewed atomic key batch changes to the admin GUI

## Objective and authority

Deliver G05 in docs/MISSING_GUI_FUNCTIONALITY.md: an administrator can
select existing keys by one cohort or an explicit bounded UUID set, prepare
supported configuration changes, inspect exact before/after changes and
scope, then atomically apply the same reviewed plan. Bulk import creates
new keys and remains a separate working flow. The human approved the whole
GUI parity round207–219 and helpful/ergonomic old and new forms; this order
delivers only209/G05. G06–G18 and final whole-GUI219 remain mandatory later.

Use ONLY the existing coding agent in right tmux pane%9, retaining the
human-owned model/profile/effort. No helpers/subagents, nested coding
sessions, model changes, agent merge/auto-merge, release/tag/deploy, real
provider/mail calls or production mutations. Root owns strategic review,
ordinary continuation orders, final gates and delegated merge.

## Verified live state at activation

At 2026-10-31T22:31:46.263974+00:00, canonical remote main is a4ed3ae68851ecbe0cb6862106abc287f3d6af55,
merged208 PR364 at2026-10-31T22:13:29Z. Root accepted G04 implementation,
immutable A/B reports, SELF99ca0f909deb14465a70429131efb9b13ec18c0e topology,
security/privacy/accounting/PG/browser/visual/docs and both B fixture/guard
repairs. All10 finalPRchecks SUCCESS,0unresolved reviewthreads. Actualmain
CI41247207844, CodeQuality41247207839 and CodeQL41247207912 allSUCCESS;
all9actualmainchecksSUCCESS, lastcompleted2026-10-31T22:30:36Z. Merge tree
matches acceptedSELF exactly. Resolution and finalverification timestamps
are recorded in the strategic timing ledger before this activation.

No209 PR/branch/order/report exists; only unrelated DependabotPR319 is open.
Release remains v0.1.0-rc.1; active ruleset23580289 has no bypass actors.
Local tracked worktree clean at208SELF with only the two protected untracked
files below; main has the identical accepted tree. Active precedinground208-b
is terminal. Do not infer mutable GitHub truth from historical snapshots.
Sole detached coding control waiter2011297 (bash wait-control-and-wake.sh,
PPID1, strategic cwd, pane%9) and original FIFO types/inodes were verified.
Root's90370 actualmainwatch and28498 finalPRwatch are CLOSEDexit0;
63770 Bresponse is CLOSEDexactOK. Never repoll/resignal those completed rounds.
This209 order creates ONE new PR on the named branch from this acceptedmain.

Actual repository /home/janezp/codex-work/slaif-api-gateway; strategic root
/home/janezp/codex-supervision/slaif-api-gateway. Fixed control.fifo and
response.fifo there are verified true FIFOs with original inodes4501469 and
4501470. Before signaling, root verifies the sole existing detached coding
waiter and publishes this complete order plus exact oap/active=209-a in the
shared worktree. No remote-only activation. Commit the strategic-authored
bytes unchanged; do not edit this order or any finalized order/report.

Protected untracked CODEX-SESSIONS.md SHA256
5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda and codex.sh
SHA25666eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247
must remain unchanged/uncommitted. Preserve ignored .env, .codex,
.local-provider-catalog, worktrees, unrelated state and permanent
objective-neutral message.txt. No reset/clean/stash/force push or unrelated
Git manipulation. Coding agent owns branch creation and Git execution.

## Read and reuse the existing implementation

Read the compact strategic ARCHITECTURE-for-agents.md, repository AGENTS.md,
OAP-COMMUNICATION-coding-agent.md, docs/MISSING_GUI_FUNCTIONALITY.md G05 and
the common strategic workorders/GUI-PARITY-ROUND-PLAN.md. Refresh relevant
docs/security-model.md, docs/accounting.md, docs/cli-field-administration.md,
docs/cli-reference.md batch contract, docs/admin-usability.md and the SAME
docs/verification/gui-cli-parity.md. No need to reread unrelated archived
inventories/full architecture or generated catalogs.

Concrete accepted seams:
- schemas/key_batch.py: strict version1 parse/render, KEY_BATCH_MAX_KEYS=1000,
  KEY_BATCH_PLAN_MAX_BYTES=8MiB, bounded512-byte reason, fixed safe errors;
- services/key_batch_service.py: plan/apply, selection/membership, before/post
  fingerprints, exact shared KeyService policy projection and audit law;
- schemas/key_configuration.py and services/key_policy_configuration.py:
  strict versioned partial configuration and existing preparation law;
- cli/key_batch.py: caller-owned transaction wiring and existing contracts;
- api/admin.py, api/admin_key_clone.py and api/admin_review_intent.py: existing
  auth/CSRF/server-derived actor, safe error projection, focused router
  composition, purpose/session/actor-bound expiring HMAC review-state example;
- services/admin_record_choices.py, api/admin_record_choices.py and shared
  web/templates/_record_choice.html + existing record-choices.js;
- web/templates/keys/list.html/detail.html, shared number formatters and
  sortable-table CSS/JS. main.py remains composition only.

The core batch has NO operation UUID or execution receipt. Never copy clone
receipt/recovery behavior into batch or invent historical commit authority.
No schema change or new persistence is needed. Reuse accepted component
evidence in tests/unit/test_key_batch.py,
tests/integration/test_cli_key_batch_postgres.py and
docs/verification/2026-10-29-cli-key-batches.md / final installed CLI record.

## Required behavior and acceptance

1. Add a discoverable, clearly separate “Change existing keys” entry on the
   key list and a focused server-rendered batch form/review/result flow.
   Target source is exactly one cohort OR an explicit UUID set. Default
   status is active; finite active/suspended/revoked choices with clear
   persisted-status versus expiry meaning. Cohort edits affect current
   eligible members, never defaults for future keys, never only the visible
   page. No new “all filtered” mode is necessary for this parity objective.
   Account for route registration order: current admin_router includes
   GET/keys/{gateway_key_id}. A new literal GET/keys/batch registered later
   would be swallowed by that dynamic route. Register safe literal routing
   precedence or choose an unambiguous longer path; prove the real app's
   navigation reaches the new form and existing key details still work.

2. Existing-record fields use shared searchable latest100/older-search
   controls. Cohort kind=cohort; key UUID kind=key (NOT key_public_id or a
   bearer input). Explicit keys support chips plus bounded newline/comma
   UUID entry for full1000 scope and a working no-JS fallback. Shared lookup
   selected-parameter limit100 must not silently truncate a1000-key batch:
   keep batch transport independent of that display/lookup bound, hydrate
   labels/search in existing bounded requests or use honest safe UUID
   labels. Reject malformed, duplicate, overflow, unknown IDs predictably,
   with no credential-shaped input reflected into responses/logs/URLs.

3. Provide practical guided edits for the usual quota/rate/provider/model/
   endpoint/lazy/streaming fields, reusing existing controls and strict
   service/schema semantics; provide an advanced partial version1 document
   for the full supported configuration surface. Choose one input source,
   avoid a page of active contradictory controls. Guidance explains omit=
   unchanged, clear/null, zero, deny-all and inherited values accurately.
   Provider null=unrestricted, []=deny-all; quota null=unlimited, zero=zero;
   per-member rate omitted=preserve, null=inherit, whole block null=clear
   all overrides. Complete policy blocks are replacements where the core
   says so. Do not derive policy from truthiness or silently merge blocks.
   No arbitrary metadata, ownership/identity/expiry edits, module repins,
   unsupported batch operation or relaxed service validation.
   In particular, the existing single-key _compose_admin_rate_limit_policy
   returns that ONE key's full override state and removes cleared members;
   it is not a batch patch builder. For batch guided actions send omitted
   members for unchanged, explicit null for clear, positive integer for set
   through the canonical configuration parser, independently per target.

4. Plan calls KeyBatchService.plan in one caller-owned transaction, no
   writes/audit/key material/dispatch/admission. Review exact selected UUIDs,
   selected/changed/unchanged counts, finite status scope, per-key readable
   before/after differences and retained values where material; offer exact
   nonsecret JSON disclosure/download if useful without substituting it for
   readable review. Explicit UUID scope reports actual excluded IDs/statuses.
   Cohort scope filters at the DB and does not enumerate excluded members:
   label that honestly rather than claiming zero other cohort members.

5. Preserve full supported1000 combined selected/excluded IDs and8MiB plan
   bound, all-or-nothing. Do not lower GUI caps, truncate firstpage, silently
   drop submitted keys or apply non-atomic chunks. Size canonical plan bytes
   AND review envelope/base64/form encoding overhead. A128KiB clone token
   cap is unsuitable; multipart defaults may cap text at1MiB. Use suitable
   existing-stack bounded transport (for example urlencoded) and explicit
   parser limits/content-type; check production Nginx128m route behavior.
   Prove valid core-sized review transport near8MiB works and above-bound
   refusal is controlled. Don’t introduce file custody/DB/Redis/job systems
   or a generic workflow framework solely to carry review data. Any actual
   operator host-resource refusal must be explicit, not labelled parity.

6. Browser review state is purpose209/batch-bound, entire-plan integrity
   checked, actor+current session bound, bounded15minute expiry, no secrets
   and no authority of its own. Reuse the small HMAC review pattern without
   changing clone token semantics or creating a second crypto design.
   Parse strict plan again before apply. Reject crosspurpose, wrongactor/
   session, expired, malformed, nonASCII digest, tampered or oversize state
   with fixed safe errors before any mutation; never echo the token. Do not
   use global current-plan state that collides across tabs/admins/workers.

7. Apply requires fresh valid admin auth, CSRF, explicit reviewed-scope
   confirmation, nonblank reason bounded512 UTF8bytes and fresh separate
   external-tool-fenced confirmation when needed. Server derives actor.
   A saved confirmation is never permission or current consent. Use ONE
   caller-owned PGtransaction around KeyBatchService.apply and commit only
   after whole success. Do not catch failures inside a transaction and
   accidentally commit earlier keys/audits. Don’t bypass fences/holds,
   route/provider restrictions, module law or accounting through the GUI.

8. Preserve deterministic locks and core state/membership revalidation,
   including the post-last-selected-key-lock membership check and honest
   READ COMMITTED boundary (later joins untouched, no serializability claim).
   Usage-only movement does not stale the plan or reset usage. Preserve key
   material/HMAC, ownership/identity, expiry, usage/reservations/replay and
   unrelated settings. No provider/secret/decrypt/email/broker work.

9. Render applied / already-at-target / no-change honestly, safe exact IDs
   and counts. Already-at-target proves current reviewed state equality,
   NOT a historical commit receipt; no additional writes/audits. Lostresponse
   or expired review is resolved with a fresh read/plan, not a new invented
   historical receipt. Validation/stale failures keep useful NON-secret
   selections/help and allow fresh review without replaying hidden consent.

10. Preserve SLAIF shell, local fonts/theme, ergonomic stacked groups,
    integrated search/dropdown, chips expanding DOWN, keyboard support and
    no-JS server flow. Adjacent specific hints and unique aria-describedby
    explain every new editable/choice field, raw units/defaults/scope and
    actual consequences, not generic tooltip/placeholder text. New tables
    start with ordinals; sortable headers are existing hyperlinks with
    neutral markers and typed raw sort keys; request/token columns separate.
    Exact zero/comma counts/M-token readouts, raw units for edits/downloads.
    Usable bounded review paging/disclosures must not hide membership or
    imply apply only affects a displayed page. No broad style redesign.

11. Non-page lookups/downloads/status reads must not rotate current form
    CSRF. Existing key create, bulk import, single-key changes/exports,
    clone/recovery, key list filtering/sorting remain working. Test real
    download/lookup → same-page submit where added. No unrelated refactor.

## Exact allowed paths and boundaries

New focused app/slaif_gateway/api/admin_key_batch.py and, if necessary,
api/admin_key_batch_review.py (or a small explicit purpose-aware extension
of admin_review_intent.py preserving208 APIs/tests). main.py import/include
only. api/admin.py only narrowly needed shared form/parser/read-only helper
reuse; avoid enlarging its monolith with batch orchestration.
web/templates/keys/batch_*.html; keys/list.html and detail.html for bounded
entry/navigation only; small shared keys form partial if it prevents copied
field semantics. web/static/js/key-batch.js if needed and web/assets.py asset
registration; reuse local styling or a small isolated component CSS adjustment
inside existing theme rather than replacing styling or introducing dependencies.

New tests/unit/test_admin_key_batch_209.py,
tests/integration/test_admin_key_batch_209_postgres.py,
tests/browser/test_admin_key_batch_209.py, and focused shared-intent tests if
the shared helper changes. Existing207/208 tests/fixtures only for directly
affected integration assertions or routine unique-provider seed coexistence
fixes; record each exact path. No new testing framework or duplicated harness.
Use existing qualified owned-PG/native-browser fixtures and exact-ID cleanup.

docs/MISSING_GUI_FUNCTIONALITY.md G05/currentstatus only,
docs/admin-usability.md, SAME docs/verification/gui-cli-parity.md and its
README index; docs/security-model.md only necessary new browser-review law;
docs/cli-field-administration.md only a useful GUI counterpart pointer.
This order/exact active pointer and one new final report.

No DBmodels/schema/migrations, client/server adapters, inference/routing/
permissions/accounting/replay laws, CLI semantics, workers, capture UI,
catalog infrastructure or session model changes. Core batch/schema changes
are not presumed necessary: report a demonstrated product-law defect for
strategic review before changing it. Routine fixture/docs/oracle corrections
stay within current order and PR, not another suffix without a blocking defect.

## Proportionate verification

Use /tmp/slaif192-coding-venv and new /tmp/slaif209 output directory. No new
package/tool/model setup is needed. Focused controller/review/template tests
prove exact parsing/omit-null semantics, all security failures, complete
max1000 scope and near8MiB review transport/bounds, unknownfield rejection,
safe canaries and correct numeric display. Wrong/missing CSRF tests must
distinguish auth/CSRF denial from reaching actual policy validation.

Real owned-PG through authenticated GUI routes must demonstrate a mixed
synthetic cohort spanning more than100 keys, exact selectedset/no firstpage
truncation, explicit mixed-status exclusions and unchanged controls, correct
persisted changes/per-key actor+reason audit, preserved usage/material/
reservations/unrelated data, no-write preview, repeat no-new-audit equality,
stale membership/config/status refusal and a failed apply leaving all keys/
audits unchanged. Reuse unchanged accepted batch rowlock concurrency,
late-audit rollback and fenced-policy proof; add only the new GUI transaction
and fresh-confirmation bridge evidence rather than rerunning all CLI cases.

Actual native Chromium: keyboard cohort/key selection, plan→readable review→
apply→reload with independent persisted assertion, multi-selection/validation
recovery, no-JS successful server fallback. Real desktop+narrow screenshots
with synthetic data under /tmp/slaif209 for root visual review, no secrets.
Verify the smallest affected legacy list/bulk-import/single-key/clone flow
or reuse unchanged proof where no boundary changed. Check new PGfixtures
coexist in CI collection order with207/208 using get-or-create seeds; no
global state reset or forced testcollection order.

Run9 OAPgovernance cases, focused new/affected tests, Ruff, documentation
hygiene and git diff --check. Do NOT run local full unit/integration/browser/
CLI/provider/Codex suites. Broad normal finalheadCI supplies regression gates;
skipped/missing/pending/blocked cases are not passes. Protect credentials in
all responses/logs/audits/screenshots/reports; use Boolean canary assertions
before printing failures. No environment/credential dumps or blanket cleanup.
Record synthetic versus mocked versus realPG/realbrowser evidence precisely.

## Documentation, upgrade and immutable handoff

Update the single living coverage map only G05 delivered with honest limits;
preserve dated analysis and future G06–G18/219. Add compact operator steps to
admin-usability and evidence to SAME gui-cli-parity record/index; ordinary
API/assets rebuild+restart, no schema/key migration. No production deployment
or final entireGUI completion claim. PRdescription leads with resulting
batch workflow plus actual verification/security/size/transaction limits.

Create exactly one209 PR from accepted currentmain on named branch. Commit
and push this order and active bytes unchanged with implementation; inspect
remote nonreport implementation SHA and update PR before final report. Fix
routine in-scope failures/docs/fixtures in this order/PR. No merge/automerge.

Build complete report outside its final path. For absent new final report
oap/reports/209-a-gui-key-batch.md, create temporary file INSIDE reports,
flush+fsync, os.replace/rename on same filesystem and fsync directory.
Never construct/cp/append directly to finalfilename or rewrite a report.
Report literal final implementation SHA as IMPL; final report-only SELF
commit's FIRSTparent must equal that IMPL and only report differs. Multiple
implementation commits allowed; no history rewrite to force one. Verify
pushed remotePRhead==SELF and topology/bytes before exactly ONE two-byte
responseOK, then exactly ONE verified detached control waiter for pane%9.
Root reviews immutable claims, all finalheadchecks/reviews, guarded merge
and actualmain verification/timing before any210. EntireGUIgoal stays active.
