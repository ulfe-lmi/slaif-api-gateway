# OAP Work Order — 210-a

PR mode: CREATE_NEW_PR
Base: main at 32478e0aa16c5a51ac7657f6b5863a107f2d9dcd
Branch: oap/210-gui-provider-route
Title: Add reviewed route changes and provider preparation to the admin GUI

## Objective, authority and current state

Deliver G06–G07 in docs/MISSING_GUI_FUNCTIONALITY.md: an administrator can
prepare guided partial route changes or an explicit complete-capabilities
replacement, review the exact canonical before/after and destination, and
apply that same plan through the existing shared services. Add faithful
provider notes clearing and visible preparation/activation semantics, while
preserving working full record editors, discovery/setup, imports and toggles.
The human approved the entire GUI207–219 round and useful hints in existing
and new forms. This order covers210 only; later G08–G18 and final installed
whole-GUI219 remain required, not implicitly complete.

Use ONLY the existing coding agent in right tmux pane%9, retaining its
human-owned model/profile/effort. No helper agents, nested coding sessions,
model changes, merge/auto-merge, release/tag/deploy, production mutations or
real provider/mail calls. Root owns strategic review and delegated merge.

At 2026-11-01T02:28:13.451782+00:00, canonical remote main is 32478e0aa16c5a51ac7657f6b5863a107f2d9dcd.
Preceding209 merged PR365 at2026-11-01T02:08:52Z into this main. Root verified at2026-11-01T02:27:17.580483Z that actualmain CI41263970567, CodeQuality41263970637 and CodeQL41263970622 all completedSUCCESS; all9main checksSUCCESS, lastPGjob completed2026-11-01T02:26:11Z. All10finalPRchecks passed on acceptedSELF; no unresolved review threads, material/visual/security/ privacy/accounting/docs accepted. Timing was recorded before this activation. Root mainwatch72233, PRwatch37586 and guardedmerge77717 are CLOSEDexit0; response84086/62671 are CLOSEDexactOK forever. Never repoll/resignal them. No210branch/PR/order/report exists. Only Dependabot319 is open. Ruleset23580289 is active (deletion/non-fast-forward, no bypass actors); sole published prerelease remainsv0.1.0-rc.1. Local209SELF has the identical accepted main tree, with only the two protected untracked files; root does not switch coding Git. The ONE detached coding control waiter2212338 (bash,PPID1,strategic cwd,pane%9) and original FIFO types/inodes were verified immediately before publication.
The unique209 PR365 is merged; A/B orders and reports were independently
verified immutable, including finalSELF54113f4eba62a5b20d259fb1d3baf13971a14c7f
whose tree de7d5dd0863841385226631fb1f08de0360cd45d equals the209 merge tree.
Root accepted the G05 implementation, native PG/browser/visual/privacy/
transaction proof and final-head gates, and recorded authoritative timing.
No210 PR/order/report is active. Only unrelated open PRs listed in the final
activation preflight remain. Refresh GitHub, not old mutable snapshots.

Actual roots: /home/janezp/codex-work/slaif-api-gateway (repository),
/home/janezp/codex-supervision/slaif-api-gateway (strategic). Fixed control.fifo
and response.fifo there are true FIFOs, inodes4501469 and4501470. Root has
published this COMPLETE order plus exact active210-a in the shared worktree
before one controlOK. The coding agent commits those bytes unchanged and
owns Git execution; root does not reset/clean/stash/switch/stage coding state.
Final209 CI watches/response terminals are closed; never repoll or resignal
them. Reuse the ONE verified detached control waiter identified at activation;
no second waiter/reader, and keep permanent objective-neutral message.txt.

Protected untracked CODEX-SESSIONS.md SHA256
5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda and codex.sh
SHA25666eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247
remain unchanged/uncommitted. Preserve ignored .env/.codex, catalogs,
worktrees and unrelated state. No environment/credential dumps or blanket
cleanup. No authority to alter runtime/accounting/client/server adapters.

## Required reading and accepted seams

Read current repository AGENTS.md and OAP-COMMUNICATION-coding-agent.md,
this order, compact strategic ARCHITECTURE-for-agents.md, workorders/README.md
and GUI-PARITY-ROUND-PLAN.md/210 proposal, and relevant current contracts:
docs/MISSING_GUI_FUNCTIONALITY.md G06/G07, docs/cli-field-administration.md
objective199, docs/admin-usability.md, docs/security-model.md and the SAME
docs/verification/gui-cli-parity.md. No full architecture/archive/catalog
inventory without a concrete unresolved detail.

Reuse, rather than copy the business rules:
- schemas/provider_route_configuration.py: strict64KiB version1 capabilities
  file, CapabilityPatch, strict128KiB route plan and canonical render/parse;
- services/provider_route_configuration.py: partial_update_provider_config,
  preview_route_update_for_route, execute_route_update_plan,
  validate_route_creation_candidate, real route/provider fingerprints and
  installation ceilings/profile directory;
- ProviderConfigService.update_provider_config(clear_notes=...), provider
  repository get_provider_config_for_update, existing ModelRouteService;
- existing admin auth/CSRF/server-derived actor/service/session helpers;
  admin_review_intent.py's small purpose/session/actor-bound signed-state
  pattern, preserving all208 clone/209 batch APIs and semantics;
- shared record choices and their optional help_id, common number/raw/M-token
  formatters, shared hyperlink sorting/ordinal/table-wrap, packaged theme.

Existing API/frontend seams: GET/POST /admin/providers/new and
/admin/providers/{provider_config_id}/edit; GET/POST /admin/routes/new and
/admin/routes/{route_id}/edit; detail pages, discovery/import and explicit
enable/disable already work. Keep them. The new reviewed route flow belongs
in a focused router with discoverable detail/edit entry, not more business
orchestration in admin.py and not a second full editor styling system.

## Required behavior and boundaries

1. **Preserve existing full editing and expose the new reviewed action.**
   Keep provider slug/status edits, route full editing, record detail/list,
   discovery/setup (including explicit LAN HTTP acknowledgement), public
   alias mapping, imports and explicit activation controls working. The
   reviewed partial route flow is additional and clearly labelled. Avoid
   dynamic /routes/{route_id} collisions; a longer target-bound path is safe.
   Do not replace a full editor with a narrower partial helper or silently
   change inference/permission rules to make a form succeed.

2. **Guided route edits use the actual closed schema.** Support the shared
   preview's optional requested_model, match_type, endpoint, provider,
   upstream_model, priority, visible_in_models, supports_streaming, notes
   and clear_notes. Omission preserves; false and zero remain explicit where
   valid; no invented null-clear on fields whose Core does not support it.
   Route enabled status is deliberately preserved by this shared preview;
   keep existing enable/disable/full-editor controls separate. Use known
   record pickers with correct identifier kinds and finite selects, safe
   current/older choices and no-JS entry. Provider kind=provider references
   the existing provider slug, including disabled records for preparation;
   do not substitute policy_provider's enabled-only catalog or credential
   values. Target route is an exact UUID, not a model alias.

3. **Practical partial capabilities plus distinct complete replacement.**
   Expose the actual CapabilityPatch leaves: codex_limits
   (`context_window_tokens`, `default_max_output_tokens`, `max_output_tokens`),
   media_input_estimation (`image_tokens`, `video_tokens`, `video_frames`), current closed
   Chat/Responses boolean leaves, and completion_service selector. Omitted
   leaves preserve deep siblings; booleans have unchanged/true/false intent;
   numeric capability leaves are positive integers (priority and provider
   retries separately permit0). Keep unrelated transport/adapter/hosted-tool
   groups unchanged on partial updates; do not invent dotted patches.

   Choose one capability input source: unchanged/guided partial, or an
   explicit advanced COMPLETE version1 document. Complete replacement uses
   parse_capabilities_file on bounded bytes with schema_version1 plus
   capabilities, at most64KiB; label this wrapper distinctly from the
   working legacy raw capability-object editor. No simultaneous full and
   partial sources. Use the same complete-candidate validator and shared
   normalizer so preview equals stored state (including Core defaults).
   Unknown/duplicate fields, invalid groups/types/relationships/ceilings
   fail safely. Browser upload, if offered, means bounded bytes, not a path.

   The completion selector is exactly {"version":1,"profile":"installed-profile-id"}
   in the current contract. Reuse the loader and configured operator-owned
   directory; offer known installed IDs and safe current selection through
   existing picker/native finite choices. No file/path input, dynamic code,
   new profile editor, revision/digest selector fields or hot-reload promise.
   Profiles are process-cached; operator file deployment/API recreation
   stays an operator task. This is distinct from212 Codex pin migrations.

4. **Review exact target/canonical state before execution.**
   Call preview_route_update_for_route with the actual installation's
   external-tool ceilings and completion profile directory, not unqualified
   defaults. It resolves the PROPOSED destination provider and seals route
   UUID, full route state/enabled fingerprint, destination provider UUID and
   context (kind/base URL/credential ENV-var NAME/timeout/retries). Display
   meaningful readable differences and destination plus exact non-secret
   JSON detail; not just a raw JSON blob or a configured-profile name claim.
   Preview is read-only, zero policy writes/audits/provider calls.

   IMPORTANT: render_route_update_plan currently only serializes; a service
   comment is not proof of strict reparse. Explicitly strict-reparse and
   enforce128KiB canonical plan bytes BEFORE ANY rendering/HMAC construction,
   and again at apply. The whole-plan known-shape guard covers retained
   current values and preview data too. Redacting visible text is insufficient
   if a hidden base64 token still contains unsafe raw values. Refuse
   unadministerable legacy state safely; do not alter fingerprints/canonical
   reviewed data to force acceptance. Reuse existing schemas, not a new
   generic sanitizer. The review envelope fits existing admin limits after
   base64 overhead: no209 batch proxy allowance or file/job custody needed.

5. **Bounded owned review and atomic apply.**
   Reuse the small HMAC pattern with a distinct route-configuration purpose,
   entire-plan integrity, current admin+session, exact route target and
   bounded15minute lifetime. Preserve clone/batch token APIs. Wrong purpose,
   actor/session/route URL, expiry, tamper, malformed/non-ASCII digest,
   oversize or strict-plan refusal fails with fixed safe errors before any
   mutation. A valid signature is reviewed data, never current authority.

   Require fresh valid admin session, CSRF, explicit confirmation and a
   nonblank bounded safe audit reason; server derives actor, never a form
   admin UUID. Execute the SAME plan with execute_route_update_plan in ONE
   caller-owned transaction, using installation ceilings/profile directory.
   Deterministic route then proposed-provider locks and fresh revalidation
   remain Core-owned. Actual route/provider-context drift refuses all writes/
   audits; display/enabled-only provider edits are intentionally outside that
   context digest and must not be mislabelled readiness or stale failures.
   Changing route enabled does stale its full fingerprint. A repeated
   effective route update is stale, unlike clone/batch repeats; a fresh
   zero-diff plan is no-write/no-audit. No invented operation receipt or
   current/historical completion authority. Preserve unrelated rows, keys,
   pricing, usage, holds/fences, replay ownership and module bindings.

6. **Provider notes and preparation parity.**
   Expose unambiguous preserve/replace/clear notes intent; blank replacement
   is not an implicit clear. Reuse existing clear_notes in the shared service
   and the CLI's locked partial helper, or lock before the existing full
   editor's audited prior-state capture. One caller transaction and ONE audit
   must show REAL prior notes -> null on clear. Never pre-clear directly or
   issue a second synthetic audit. Preserve enabled and omitted fields on a
   partial action; keep the existing full editor's slug/activation controls.
   No schema/service-law change is presumed necessary.

   New-provider preparation starts disabled unless explicitly activated;
   existing edit status must remain its actual stored value. Route creation
   distinguishes automatic/basic default(enabled), complete-capabilities
   preparation(default disabled), explicit disabled preparation and explicit
   activation. Use an unambiguous finite creation intent or equivalent;
   a default prechecked legacy checkbox cannot prove deliberate activation
   of a new prepared document. Do not disable all basic-route creation to
   avoid the distinction. Preserve working legacy POST/edit/toggle behavior
   where unaffected, and document these intended preparation defaults.
   Enabled never proves provider authentication, health or compatibility.

7. **Secret protection, recovery and field help.**
   The inspected provider renderer passes form values directly and legacy
   route errors retain raw JSON: while touching these surfaces, use the
   established known-shape projection so credential inputs are not echoed
   in field values/errors/logs/audit. Keep ENV-variable NAMES literal; never
   resolve/display provider key values. Refused advanced document bytes are
   cleared before redisplay (unknown JSON password values cannot be masked
   by a generic shape detector). Preserve safe selections, edit modes and
   useful field recovery, with no hidden replayed confirmation.

   Add meaningful adjacent, associated help for EVERY touched/new editable
   or choice control: purpose, raw units, omission/clear/replace/default,
   bounds, scope, and consequences. Distinguish physical model/context,
   route settings, installation ceilings and client context; configuration
   validation is not admission/pricing/provider-health or live-model proof.
   Use valid one-control labels, unique help IDs and aria-describedby on
   actual inputs. Reuse optional record_choice help_id without changing old
   callers, keeping search/dropdown integrated and chips expanding down.
   Client JS only manages progressive active/inactive state, never a second
   policy engine or unit conversion; after record-choice adoption and on
   rc-change rederive managed hidden state so stale values cannot resubmit.
   Provide keyboard and no-JS successful paths; hide/disclose inactive
   groups coherently, do not make an ordinary form a wall of JSON/warnings.

   Keep packaged SLAIF theme/fonts/branding, responsive grouping, exact zero,
   comma/M-token display and raw machine units for edits/downloads. New
   tables use ordinal first, shared hyperlink sorting/neutral markers/raw
   typed keys, separated request/token measures where present, standard
   empty rows, and labelled keyboard-focusable table-wrap. No new CSS theme,
   picker/dependency system or flat top-menu expansion. Non-page lookups/
   attachments must not rotate a displayed form's CSRF.

## Exact allowed implementation paths and non-goals

Shortened api/, web/ and services/ paths in this section mean paths under
app/slaif_gateway/. All existing test basenames below mean tests/unit/ unless
their full integration/browser path is explicitly listed.

New focused api/admin_provider_route_configuration.py (and
api/admin_route_configuration_review.py only if a small companion is genuinely
needed), small route-purpose
extension of api/admin_review_intent.py, main.py composition only. api/admin.py
ONLY bounded provider/route creation intent, notes/locking/argument propagation,
safe touched-form projection and required context helpers/entry composition;
no broad extraction or new orchestration in the monolith.

New web/templates/routes/configuration_form.html,
web/templates/routes/configuration_review.html and
web/templates/routes/configuration_result.html; existing
web/templates/routes/detail.html, web/templates/routes/edit.html,
web/templates/routes/create.html, web/templates/providers/create.html,
web/templates/providers/edit.html and web/templates/providers/detail.html;
web/templates/routes/list.html and web/templates/providers/list.html for entry links
only if needed. Optional web/templates/routes/_configuration_fields.html and
web/templates/providers/_notes_controls.html to avoid duplicated field
semantics. Small progressive enhancement in
web/static/js/catalog-configuration.js if needed, web/assets.py registration,
isolated web/static/css/admin.css additions only if
existing components cannot express the layout. _record_choice.html only
backwards-compatible help documentation/necessary touched-form integration.
services/admin_record_choices.py and api/admin_record_choices.py only for a
bounded installed completion-profile choice kind if needed, keeping existing
auth, bounds, current/older lookup and no-CSRF-rotation behavior; no arbitrary
directory/path browser or unrelated choice changes.

New tests/unit/test_admin_provider_route_configuration_210.py,
tests/integration/test_admin_provider_route_configuration_210_postgres.py and
tests/browser/test_admin_provider_route_configuration_210.py. Existing
test_admin_provider_config_actions_routes.py, test_admin_route_actions_routes.py,
test_admin_record_choices.py and directly affected cases in
tests/integration/test_admin_provider_config_actions_postgres.py,
tests/integration/test_admin_route_actions_postgres.py,
tests/integration/test_admin_record_choices_postgres.py,
tests/browser/test_admin_usability.py and tests/browser/test_admin_slaif_design.py
ONLY for directly affected behavior. Existing test_admin_usability_inventory.py,
test_admin_slaif_design.py, test_documentation_contract_drift.py and
test_main_app_structure.py only for actual new surfaces/composition or legitimate
exact consumer/count registrations, preserving substantive assertions.

Docs (all under docs/): SAME MISSING_GUI_FUNCTIONALITY.md G06/G07/status,
admin-usability.md, verification/gui-cli-parity.md and verification/README.md
index; cli-field-administration.md counterpart pointer;
security-model.md/deployment.md only necessary new review/
restart notes. This order/exact active pointer and one new final report.

No DB models/schema/migrations, client/server adapter changes, inference,
pricing/accounting/replay/permission-law changes, CLI semantics, worker/job
platform, file custody, capture UI, dependency/test framework or profile editor.
No new source/module pin or key migration. If a demonstrated shared-law defect
requires an additional exact path, show evidence to root before changing it;
do not invent a need for architecture redesign. Routine fixture/doc/oracle
corrections stay in this order/PR, not another suffix without a blocking defect.

## Proportionate verification and setup

Use /tmp/slaif192-coding-venv and /tmp/slaif210; existing native Chromium and
qualified owned-PG fixtures. No new packages/harness needed. Run tests in a
managed foreground terminal; no dead background shell/unused outer PG. Verify
owned label/exactID/loopback/tmpfs before readiness/migration, clean ONLY those
owned IDs, and report cleanup. Use unique/get-or-create seeds so relevant
GUI modules coexist in normal collection order. No real provider/mail calls.

Reuse accepted tests/unit/test_provider_route_configuration.py,
tests/integration/test_cli_provider_route_configuration_postgres.py and
docs/verification/2026-10-28-cli-provider-route-configuration.md for unchanged
Core merge/fingerprint/lock/profile laws. Add focused GUI parsing/security/
transaction proof, not another full CLI/provider matrix. Verify:
- guided scalar/partial/deep sibling preservation; explicit false and valid0;
  notes preserve/replace/clear; distinct full replacement and incompatible
  input-source refusal; strict document/plan bounds and pre-render reparse;
- actual auth/CSRF/actor/target/purpose/confirmation/reason denials, expiry/
  tamper/stale route/context; validators demonstrably reached after valid
  auth/CSRF for policy refusals, not generic400s credited as validator proof;
- real PG through authenticated GUI: read-only preview, exact reviewed final
  canonical state, one actor/reason audit, unrelated fields/records preserved,
  true stale context and route refusal, zero-diff no audit, late failure
  rolling back GUI caller transaction; provider clear real old->null oneaudit,
  disabled preparation/explicit activation/zero retries and legacy editing;
- real Chromium: discoverable route entry, keyboard guided edit→readable
  review→confirm/apply→reload plus independent DB oracle; provider notes clear
  and creation intent; full replacement path, no-JS success, meaningful field
  help and real desktop/narrow screenshots with synthetic data under /tmp.
  Lookups/downloads→same-page submission, no stale inactive fields;
- Boolean canaries prove no recognized input/retained secrets in rendered
  pages, signed hidden data, logs/audits; fixed safe errors and blank refused
  advanced bytes. Distinguish synthetic/fake persistence, nativePG/browser
  and installed proof; no live inference or final219 claim.

Run the SMALLEST affected existing guard/form modules before publication,
including main composition and consumer/table/wrapper inventories. 209 showed
their finite counts/allowlist need legitimate exact additions; preserve the
guards, do not discover these only after an immutable handoff. Run9 OAP
governance cases on the byte-exact order, Ruff on changed Python, documentation
checker and git diff --check. Full modules once include their subset cases;
do not rerun unchanged suites or complete local matrices. Normal final-head
GitHub CI supplies required broad regressions; pending/skipped is never pass.

## Documentation and immutable publication

Update only G06/G07 delivered; preserve earlier chronology and later work.
Consolidate operator navigation, clear/default semantics, unchanged legacy
actions, real evidence and limitations in the existing living documents.
Upgrade is normal API/assets rebuild+recreate/restart, no schema/key migration
or new proxy allowance; operator profile file changes retain process/restart
scope. Keep product hints practical and put implementation-only details in
appropriate docs. Do not claim backend readiness, universal compatibility,
certification, release or the whole GUI goal complete.

Create exactly ONE210 PR from accepted current main on the named branch.
Commit/push unchanged order and active with implementation; verify remote
IMPL and PR identity and update PR description BEFORE final report. If the
installed gh pr edit fails Projects(classic), use REST PATCH with a JSON file
and --input, preserving actual newlines and avoiding duplicate addenda. Coding
agent never merges/enables auto-merge or rewrites history.

Construct COMPLETE report away from final target. For absent
oap/reports/210-a-gui-provider-route.md, use a temporary file INSIDE reports,
flush/fsync, os.replace/rename on same filesystem, fsync directory. Never
construct/copy/append directly into final name or rewrite finalized reports.
Record actual current CI status per exact head; do not copy an old report's
"no run exists" claim or call a failed job pending. A superseded cancelled
workflow and its completed failed job have distinct outcomes. Final-head
checks remain root's gate, not a report-time pass assumption.
Report literal final IMPL SHA; report-only SELF firstparent exactly IMPL and
ONLY report differs. Multiple ordinary implementation commits are fine;
no force push. Verify remotePRhead=SELF and exact topology/bytes before ONE
two-byte responseOK (no newline), then install ONE detached control waiter
for the same pane%9 and wait. Root reviews immutable claims/material/visual/
security/privacy/accounting, all final-head checks/reviews, guarded merge and
actual main verification/timing before211. Entire GUI goal stays active.
