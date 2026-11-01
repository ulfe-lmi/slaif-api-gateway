# OAP Work Order — 212-a

PR mode: CREATE_NEW_PR
Base: main at 4d90d016b82568b1f5be0f4ff10750661ae0e618
Branch: oap/212-gui-codex-compatibility
Title: Add reviewed Codex compatibility management to the admin GUI

## Objective and verified activation state

Deliver G10 in docs/MISSING_GUI_FUNCTIONALITY.md: an administrator can inspect
registered Codex qualification and compatibility data, identify an existing
key's exact binding, download a validated credential-free preset, and perform
the existing CLI's exact module upgrade/rollback or data-profile migration
through dry run -> owned review -> confirmed atomic apply -> reload/repeat.
Preserve existing key creation, qualification badges, route readiness and
credential-free profile/catalog downloads.

At 2026-11-01T10:18:57.924254+00:00, canonical remote main is 4d90d016b82568b1f5be0f4ff10750661ae0e618, tree
6a4186d6325ccc905156688162707784c0b1c113. Predecessor211 PR367 (roundsA+B)
merged2026-11-01T09:59:37Z after all10finalSELF checksSUCCESS, accepted material/
security/privacy/accounting/visual/docs review and all3COMMENTEDthreadsresolved.
Root verified actualmain2026-11-01T10:16:42.209686Z: CI41295474490,
CodeQuality41295474331, CodeQL41295474518 all completedSUCCESS and all9 named
checksSUCCESS; lastPGjob completed2026-11-01T10:16:11Z. Main tree equals accepted
211SELF10dbda5f5b4f8937c3cd539451a62349a9870a14. Terminal verification and
activation/creation/merge/duration timing are ALREADY recorded in the strategic
ledger BEFORE this activation. G08/G16 are FINAL VERIFIED COMPLETE, not the
whole GUI goal. A initialbrowserfail/PGcancelled and B test-only nav repair
remain honestly recorded in their immutable reports. No211repair remains.

Only unrelated Dependabot319 is open. No212order/report/PR exists. Ruleset
23580289 is active deletion/non-fast-forward with no bypass; sole release is
prereleasev0.1.0-rc.1. Local checkout remains211SELF10dbda5f with the identical
main tree and only the protected3untracked files; root did not alter codingGit.
One canonical coding waiter2753117 (strategiccwd,TMUX_PANE=%9) is ready;
codingCLI3308462 is alive in RIGHTpane%9 at the human early-beta profile.
No rootresponseFIFO reader is live. Mainwatch27775, finalPRwatch8764 and merge
97760 are CLOSEDexit0; Bresponse27453/Aresponse98556 CLOSEDexactOK; oldACIwatch
46179 CLOSEDexit1. Neverrepoll/resignal completed211 rounds or older210handles.
OriginalFIFO types/inodes and all protected/immutable hashes were verified.
This activation is212-a on the new named branch, one newPR; no published
release, deploy or production operation is authorized.

The human approved the entire GUI207–219 plan and ordinary OAP progression.
Only212 executes here; G09/G11–G15/G17/G18 and final219 remain required. Use
ONLY the existing coding agent in RIGHT tmux pane%9 at its human-owned model,
profile and effort. No helper agents/nested sessions, model changes, merge,
auto-merge, release/tag/deploy, production mutation, real provider or real mail.
Root owns strategic review and delegated merge after all final-head gates.

Repository /home/janezp/codex-work/slaif-api-gateway; strategic root
/home/janezp/codex-supervision/slaif-api-gateway. The original control/response
FIFOs must remain true FIFOs (inodes4501469/4501470). This complete order and
exact active212-a are already present in the shared worktree before the ONE
controlOK. The canonical detached coding waiter consumed that control; execute
this order, do not read control again until report/response handoff is complete.
Coding owns Git execution and commits these activation bytes unchanged. Root
does not reset/clean/stash/switch/stage coding Git. Do not rewrite objective-
neutral message.txt. Preserve ignored.env/.codex/catalogs/worktrees and these
unrelated untracked files, without reading their contents or committing them:
CODEX-SESSIONS.md SHA2565ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda;
codex.sh SHA25666eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247;
uv.lock SHA256d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6.

## Reading, shared seams and authority

Read repository AGENTS.md/OAP-COMMUNICATION-coding-agent.md, this order,
strategic ARCHITECTURE-for-agents.md, workorders/README.md,
GUI-PARITY-ROUND-PLAN.md and212 proposal. Read current G10/section6 exceptions,
admin-usability, Codex compatibility/profile/module migration operator docs,
security/accounting/replay contracts relevant to migration and the single
living verification/gui-cli-parity.md. No full architecture/archive/generated
inventories without a concrete unresolved question. Derive live GitHub state.
Read docs/client-compatibility-presets.md and module-architecture.md for the
current schema-1 fallback/schema-2 preset distinction. Use the existing loaders
for BOTH validated formats and all current shipped presets; do not hardcode
revision numbers, derive CLI provenance from the decoder-generation module ID,
or mislabel a shipped preset as an adopted/qualified runtime snapshot.

Existing seams to REUSE, not replace:
- cli/codex.py presets/export-preset/inspect/profile/show-profile/
  inspect-profile-file/upgrade-key-module/rollback-key-module/migrate-key-profile.
  Controllers call shared functions, never CLI subprocesses.
- services/codex_qualification.py CodexQualificationService and safe renderers;
  services/codex_profile_registry.py qualification profiles; registered client
  modules via modules.clients; modules/codex_profile_data.py list_codex_presets,
  read_codex_preset and strict bounded loaders. Compatibility data is distinct
  from qualification profiles and upstream LLM instruction/tool profiles.
- services/codex_module_upgrade.py mutate_codex_client_module and
  migrate_codex_0162_key_profile, exact legal edges/frozen tuples, locked key
  reads, caller transaction and AuditRepository. These are compatibility-only
  metadata operations, not general policy edits.
- api/admin_review_intent.py existing HMAC-SHA256/actor/session/purpose/expiry
  pattern. Reuse primitives; add one narrowly scoped review purpose and strict
  finite validation, not a generic workflow platform or persistent job store.
- api/admin.py session/action/read helpers, record-choice components and shared
  numeric/table/theme/help patterns. Operations navigation already exists.
- app.state.codex_0162_profile is the validated API startup display snapshot;
  the actual module migration consumer resolves active through get_client_module.
  Never confuse another process's file inspection with API adoption.

## Required behavior

1. Add a coherent Compatibility entry beneath Operations, plus useful links
   from key detail and existing route qualification detail. Do not widen the
   flat navigation. Show the shared global qualification/readiness projection
   with named profile, module/data identity and reasons. This is configuration
   inspection, not live-client/provider proof. Preserve existing views/downloads.
   Offer the existing credential-free base/profile/catalog artifact controls
   from ready global qualification rows too, reusing their canonical handlers,
   registered-profile/readiness gates and gateway-base-URL validation. Do not
   synthesize artifacts for unready results or introduce recovered key material.

2. List validated shipped compatibility presets with bounded safe facts and
   inspect/export the same document read_codex_preset returns. Use only exact
   registered preset names, no arbitrary server paths. Omit CLI-only filesystem
   paths from browser output. Exports are authenticated private no-store,
   bounded by the existing65536-byte profile limit, credential-free JSON with
   safe filenames. Registered/loaded never means every newer Codex is supported.
   Inspect current API startup data identity/provenance and current key binding
   as exact module ID/version/fixture digest, distinct from qualification and
   upstream selectors. Missing/invalid/unavailable state is explicit and safe.
   No browser hot reload/editor/upload, implicit bootstrap or active-file write.
   Any configured-file inspection must use the existing strict loader and label
   file facts separately from the running snapshot. No browser-selected paths.
   Keep canonical preset bytes/identity trustworthy: do not redact a document
   silently and claim it still has the original digest. If known-secret
   substitution would be necessary for an export, refuse it with a fixed safe
   message rather than serving a modified compatibility artifact.

3. Provide guided single-key module upgrade, rollback and data-profile migration
   using the SAME core functions and legal CLI operations. Select known keys
   using the shared latest100/search/manual-ID component, finite registered
   operation/target selects, explicit expected source and bounded field help.
   Only approved frozen module edges are legal: preserve intermediate hops;
   do not synthesize direct cross-family/version moves. Data migration supports
   active and the frozen0162-v1/v2 rollback targets as the CLI does, with exact
   source version/digest and same-revision/different-digest refusal. Do not
   replace the target or repin through generic G01 configuration edits.

4. Review invokes the shared operation with apply=False in the caller
   transaction; it takes the existing key row lock briefly but performs no
   domain/audit writes. Display exact source/target tuples and the typed dry-run
   or already-at-target outcome before offering apply. Reasons follow the core
   migration law:8–200 printable ASCII characters, with nonwhitespace content.
   This is NOT the general512-character Unicode GUI reason bound. Refuse/mask
   credential-shaped or known incoming authentication values without echoing or
   persisting them. Actor always derives from the authenticated session.

5. Bind reviewed operation, key UUID, exact source, selector, resolved target
   tuple, safe reason, actor and session to an expiring integrity-checked review.
   Reuse existing15-minute intent TTL and session secret; use a purpose distinct
   from clone/batch/route, strict keys/types/duplicate rejection and a small
   explicit bounded token/payload cap sufficient for one finite migration
   (8KiB is ample). No replay database, file custody or new deployment secret.
   Apply accepts current valid session/CSRF, deliberate confirmation and the
   authentic owned review; posted actor/source/target/reason overrides confer
   no authority. No token or untrusted reason in URLs/logs/public errors.

6. Recheck the target against the APPLY worker's actual client-module registry
   before mutation. An active selector is symbolic: bind ID/version/digest at
   review and reject if the apply worker resolves a different tuple, even if
   app.state display facts appear unchanged. If necessary add the smallest
   backwards-compatible optional expected-target guard to the shared migration
   function at its actual target resolution; preserve all existing CLI defaults.
   Do not duplicate mutation SQL/metadata writes in controllers or silently
   accept a newly active tuple. Missing validated active profile fails safely.

7. The shared locked operation and audit commit together or roll back. Update
   ONLY responses_policy.client_module. Preserve key material/UUID, owner,
   model/provider/endpoint/local/hosted-tool restrictions, expiry, limits,
   counters, reservations, usage, key state, and replay ownership. Preserve
   current==target BEFORE source-mismatch behavior after validating legal
   operation/source syntax: a repeat is already_at_target with NO new write or
   audit, including when another authorized action reached the same target.
   Do not add a whole-key fingerprint gate that blocks this accepted outcome.
   Actual non-target source drift still fails under the existing key lock.

8. Explain traffic quiescence/fresh-client-session guidance and rollback limits
   from the existing CLI contract. Updating a key pin does not reload files,
   qualify a backend, grant tool permissions, transfer replay ownership, rewrite
   old replay material or guarantee replay across different compatibility data.
   Do not add a traffic-pause/control platform. Success/repeat/error reloads must
   truthfully show persisted binding, audit outcome and recovery action; an
   authentication redirect is not a successful mutation. Treat lost commit ACK
   as unconfirmed, not a guaranteed rollback. Keep errors fixed and secret-safe.

9. All inspection/download/lookup/status reads authenticate with existing
   non-mutating session checks and no-store; they do not rotate the displayed
   page's CSRF. Preserve full-page/mutation security. Prove download -> same-page
   review/apply and repeated refresh works. No new unauthenticated diagnostics,
   plaintext key recovery or key-inclusive configuration installer.

   Concrete privacy constraint: the legacy shared key picker sends typed q in
   GET URLs. Do not put a pasted bearer/session credential into a URL for a NEW
   compatibility key selector. Prefer existing key-detail entry for known UUIDs;
   if the global page uses live shared search, add only one explicit fixed
   compatibility-key private POST kind, reusing services/admin_record_choices.py
   load_choices and the qualified211 body-only/non-rotating-CSRF pattern. Bound
   q/selected before use, refuse known authentication aliases without echo, and
   retain latest100/search/older selection semantics. Keep old kinds' GET
   behavior and211diagnostic behavior unchanged. No runtime-configurable lookup
   endpoint or generic transport framework. Verify actual browser URLs with a
   synthetic pasted credential, and successful lookup -> same-page submission.

## UX, paths and non-goals

Preserve SLAIF theme/local assets and existing GUI behavior. Guided controls
with meaningful associated help/unique actual-control IDs cover key, operation,
expected source, target, digest, reason and confirmation; explain units, legal
hops, blank/default and dry-run/apply implications. Put migrations in clear
progressive disclosure, use readable current/target comparison, keyboard and
no-JS validation recovery. Tables are ordinal-first, hyperlink-sortable with
neutral markers/raw typed sort keys, separate request/token measures where
present, exact zero/comma/M-token formats and labelled focusable scroll wrappers.

Allowed app paths under app/slaif_gateway/:
- NEW api/admin_compatibility.py focused router; api/admin_review_intent.py
  narrowly scoped new purpose/finite review validation, existing purposes intact.
- main.py composition only; api/admin.py only directly necessary safe links/
  context, preserving old handlers; web/templates/keys/detail.html and
  routes/detail.html only compatibility navigation, not lifecycle redesign.
- NEW web/templates/compatibility/index.html, preset.html, key.html,
  migration_review.html (one small shared fragment only if useful); existing
  operations/index.html compatibility card. Reuse shared assets/components.
  web/static/js/record-choices.js ONLY the narrowly necessary fixed private
  compatibility-key POST branch described above, with old kinds intact;
  services/admin_record_choices.py is reused read-only without new lookup law.
  No new JS controller, CSS theme or generic form framework.
- services/codex_module_upgrade.py ONLY a necessary additive exact-target
  guard/read-only legal-target facts seam; existing CLI signatures/default law
  preserved. Existing qualification/registry/profile modules are reused without
  adapter/profile-data/loader changes. Raise a concrete absent seam before
  expanding scope. No arbitrary module/preset paths or new tool taxonomy.

Tests: NEW tests/unit/test_admin_compatibility_212.py,
tests/integration/test_admin_compatibility_212_postgres.py,
tests/browser/test_admin_compatibility_212.py; directly relevant review-intent
cases in existing tests/unit/test_admin_key_clone_208.py and
tests/unit/test_admin_provider_route_configuration_210.py (there is no separate
test_admin_review_intent.py); existing tests/unit/test_cli_codex.py and
tests/integration/test_codex_module_upgrade_postgres.py only directly affected
guard/CLI-default regressions, reusing unchanged component cases. Existing
structure/design/usability/documentation
consumer guards for exact registrations, preserving substantive assertions.
Docs: SAME MISSING_GUI_FUNCTIONALITY.md G10/status, admin-usability.md,
verification/gui-cli-parity.md + README index; existing Codex compatibility/
migration/operator docs and deployment/security notes only directly useful
navigation/upgrade/rollback facts. No duplicate inventories/evidence documents.
docs/client-compatibility-presets.md only a useful GUI/operator counterpart
pointer, not a change to its dialect/engine/activation contract.
This exact order/active and ONE immutable212 report.

No schema/models/migrations, permissions, acceptance/adapter/tool/data-profile
changes, accounting/replay mutation, settings writer, general filesystem
browser, capture UI, plaintext secret recovery, new queue/job framework,
database migration executor, new dependencies or production calls.

## Proportionate evidence and setup

Use existing /tmp/slaif192-coding-venv, Chromium and qualified owned-PG fixtures,
synthetic records and /tmp/slaif212 receipts/screenshots. No packages/helper
agents/new qualification infrastructure or complete local matrix. Reuse accepted
module/profile/qualification/209–211 component proof where unchanged. Confirm
exact owner label/full container ID/loopback/tmpfs BEFORE use; clean only owned
resources. No ambient DATABASE_URL mutation, blanket pkill or docker prune.

Focused unit/ASGI: exact registered safe projections/exports, no filesystem
path/credential/raw fixture leakage, global qualification reasons and current
binding, safe unavailable state; shared dry-run selection and strict reason
law; wrong auth/CSRF/confirmation, wrong source/digest, invalid edge, unavailable
active profile, expired/tampered/cross-actor/cross-session/wrong-purpose review,
and apply-worker registry drift. Establish valid auth/CSRF before each intended
validator; generic400 is not sufficient. Existing review purposes still pass.

Actual PostgreSQL through authenticated HTTP: module upgrade + supported
rollback and data-profile migration/rollback using shared operations; review
has no domain/audit writes, apply one actual session actor/reason/tuple audit;
reload exact binding; exact repeat no new write/audit even after another
authorized action achieved target; non-target drift and wrong active tuple
refuse; late failure rolls back policy and audit. Compare all unrelated key/
policy/material/quota/usage/reservation/replay-ownership fields, using synthetic
sentinels. Reuse prior Core preservation/concurrency proof, do not repeat whole
producer/Codex/provider suites. No real backend/client qualification claimed.

Actual Chromium: navigate Operations/Compatibility and existing key/route
entry, inspect qualification/preset/current identity, download credential-free
preset -> same-page reviewed migration -> confirm -> reload persisted result
and exact repeat. Independent DB oracle for update/audit/preservation; keyboard,
validation/no-JS recovery, desktop/narrow rendered styles and old entry points.
Capture synthetic-only screenshots in /tmp for root visual review. No proxy-
based mocked success: browser mutations must reach real shared operations/PG.

Run smallest affected legacy migration/review/CLI/default/consumer/structure/
inventory guards,9 OAP governance tests on exact order+active, scoped Ruff,
documentation checker and git diff --check. Routine fixtures/docs/oracle fixes
remain in this order/PR; another suffix only for a demonstrated blocking defect.
Do not rerun unchanged tests merely because comments/imports/formatting changed.
Report distinct cases and overlapping rechecks precisely, never add counts.

## Publication, operator instructions and handoff

Update the single living map with G10 only; retain G09/G11–G15/G17–G18 and
final219 as open. Document Operations/key/route navigation, approved legal hops,
source/target identity,8–200 ASCII reason, quiescence/replay limitations,
dry-run/review/apply/repeat and rollback; API snapshot vs operator file update/
restart/adoption, no automatic key migration and no schema upgrade. No deploy
performed, no general new-Codex/provider compatibility claim. Distinguish
synthetic/mock/real PG/Chromium evidence from installed219/real-client evidence.

Create exactly ONE212 PR from verifiedmain on the named branch; commit/push
unchanged strategic activation with implementation. No force-push/merge/auto-
merge. Write accurate concise PR title/body and docs before final report.
Include exact report line Documentation updated: <files>. Report literal final
IMPL and actual per-head checks; pending/failed/skipped never passed. Keep
preliminary fixture history brief, not a second inventory.

Construct complete report draft away from final path. Publish absent
oap/reports/212-a-gui-codex-compatibility.md via temporary file in reports,
flush/fsync, same-filesystem os.replace and directory fsync. Never append to
or revise final report. Report-only SELF firstparent must equal literalIMPL,
with only that report diff. Verify remotePRhead=SELF, exact order/active/report
bytes and topology before ONE two-byte responseOK (no newline). THEN install
exactly ONE detached strategic wait-control-and-wake.sh with TMUX_PANE=%9 and
verify its real script/PID. No ad hoc reader/duplicate waiter/extra response.
Root independently reviews material/visual/security/accounting/docs, all final-
head gates, merges with exact-head guard, verifies actualmain workflows/tree
and records terminal timing BEFORE213. Full GUI goal remains ACTIVE through219.
