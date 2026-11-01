# OAP Work Order — 211-a

PR mode: CREATE_NEW_PR
Base: main at f71f5799ee4f14ff5774f0e96775f1fd5f02d38e
Branch: oap/211-gui-diagnostics-config
Title: Add content-free diagnostics and safe process inspection to the admin GUI

## Objective, authority and verified activation state

Deliver G08 and G16 in docs/MISSING_GUI_FUNCTIONALITY.md. An authenticated
administrator can find a retained inference failure, distinguish a failed
stream from its wire status, inspect safe API-process settings and registered
profile identities, and explicitly prune expired diagnostics. Preserve working
administration, inference, accounting, replay ownership and privacy.

The human approved the entire GUI207–219 plan, ergonomic SLAIF presentation,
and meaningful field-specific help in old/new forms. This order covers211
only:212–219 and every remaining G item still require delivery. Use ONLY the
existing coding agent in right tmux pane%9 at its human-owned profile/model/
effort. No helper agents, nested coding sessions, model changes, release/tag/
deploy, production mutations, real provider or real email calls. Root retains
strategic review and delegated merge. Ordinary sequencing is already delegated.

At 2026-11-01T06:43:08.970581+00:00, canonical remote main is f71f5799ee4f14ff5774f0e96775f1fd5f02d38e.
Predecessor210 PR366 merged at2026-11-01T06:23:56Z after all10 finalSELF
checksSUCCESS and independent material/visual/security/privacy/accounting/docs
review; all12 review threads resolved and no CHANGES_REQUESTED or auto-merge.
Root verified actualmain at2026-11-01T06:42:25.165199+00:00: CI41280672009,
CodeQuality41280671829 and CodeQL41280671937 all completedSUCCESS, all9 checks
SUCCESS, lastPGjob completed2026-11-01T06:41:37Z. The main tree
 d7368dc79f841fb1bcc9479898195af000e4669a equals accepted210 SELF
83dbc224a4f779234bcfd912b7eb5e84e5793fa8. Authoritative merge/verification
timing was recorded BEFORE this activation. G06/G07 are terminal accepted;
full GUI work remains open. Closed handles30574/23223/84166/26084 and response
91725 must NEVER be repolled/resignalled. No211 PR/order/report exists.
Only unrelated Dependabot319 is open. Ruleset23580289 is active (deletion/
non-fast-forward, no bypass); sole release remains prereleasev0.1.0-rc.1.
Local checkout is210SELF with the identical main tree and only the two
protected untracked files; root has not changed Git state. One canonical
coding wait-control-and-wake.sh PID2558056, TMUX_PANE=%9, is ready; no root
response-FIFO reader remains from210. Its earlier ad hoc waiter was already
replaced without any extra FIFO signal. Original FIFO types/inodes and all
protected/immutable hashes were verified immediately before publication.

Actual paths: repository /home/janezp/codex-work/slaif-api-gateway;
strategic /home/janezp/codex-supervision/slaif-api-gateway. Control and response
FIFOs there must remain true FIFOs with inodes4501469 and4501470. Root publishes
this complete immutable order and exact active211-a in the shared worktree
BEFORE one controlOK. Coding agent owns Git execution and commits these bytes
unchanged. Root does not reset/clean/stash/switch/stage coding Git. Do not
rewrite objective-neutral message.txt. The detached canonical coding waiter
has ALREADY consumed control when its wake message arrives: execute the shared
active order, do not open another reader. Reverify live GitHub, not snapshots.

Preserve untracked CODEX-SESSIONS.md SHA256
5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda and codex.sh
SHA25666eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247,
ignored .env/.codex, local catalogs/worktrees and unrelated state. No contents,
credential/environment dumps, blanket process/container cleanup or unowned
resources. No database schema or inference acceptance changes are authorized.

## Reading and actual existing seams

Read repository AGENTS.md, OAP-COMMUNICATION-coding-agent.md, this order,
strategic compact ARCHITECTURE-for-agents.md, workorders/README.md and
GUI-PARITY-ROUND-PLAN.md/211 proposal. Consult relevant docs/contracts:
MISSING_GUI_FUNCTIONALITY.md G08/G16 and section6 exceptions,
security-model.md content-free diagnostics/configuration/admin-session
boundaries, configuration.md, upstream-llm-adapter.md, admin-usability.md,
verification/gui-cli-parity.md and accepted201/204 CLI diagnostics/config proof.
No full architecture/archive/generated inventories without a concrete question.

Current implementation seams verified while preparing this order:
- services/request_diagnostics.py RequestDiagnosticsService.resolve/status/
  cleanup; schemas/request_diagnostics.py frozen typed records/outcomes;
  db/repositories/request_diagnostics.py exact retained COUNT, fetch101,
  DIAGNOSTIC_LOOKUP_BOUND100, delete_expired one batch at most1000.
- resolve accepts namespace any/gateway/client; safe ID grammar1..128 chars;
  unsafe IDs yield typed not_found. This alone does NOT protect input
  redisplay/URLs. Lookup is read-only and works with recording disabled.
- status distinguishes recording_enabled from store_available and retained
  count/time bounds. Expiry is retention-relative; no background expiry daemon.
- cleanup currently owns its own session+commit and maps store errors to a
  typed unavailable result. A later separate audit cannot roll back its prune.
- RequestDiagnosticRecord has gateway/client IDs, authenticated gateway-key
  UUID when genuinely observed, route UUID/pattern, revision, typed error/
  reason/positions/counts/limits and wire+stream facts. It has NO historical
  client-module identity fields; show unavailable rather than infer current
  key bindings or create new storage. Unknown observed facts stay unavailable.
- services/configuration_inspection.py inspect_process_configuration currently
  projects EXACT45 names, sources from Settings.model_fields_set and restart
  scope, but hardcodes CLI-process wording. Preserve the CLI default contract;
  add a small explicit finite API-scope seam for browser use.
- create_app already binds app.state.settings, upstream_llm_profiles and
  codex_0162_profile to validated startup snapshots. Inspect THOSE snapshots;
  do not reload arbitrary paths or pretend new on-disk files are live.
- modules/servers/upstream_llm/profiles.py LLMProfile has finite data fields
  profile_id, revision, instruction_placement, tool_encoding plus computed
  canonical sha256. Exact route selector is version1/profile/revision/sha256.
- __version__ is the existing CLI package version source. Existing operator
  revision Settings are REQUEST_CAPTURE_DEPLOYED_REVISION and its provenance;
  reading that safe declaration must NOT instantiate/arm capture. Unknown or
  unsafe provenance/revision is unavailable. Do not run Git at request time.
- main.py composes focused GUI routers; api/admin.py supplies authenticated
  page/action contexts, server-derived actor, no-store helpers, redaction,
  existing safe picker, table sorting and number formatting. One-way helper
  reuse; no reverse import or new monolith business orchestration.

## Required diagnostics behavior

1. Add a coherent Operations landing area linking Diagnostics and Process
   configuration/profile inspection, reachable from the existing dashboard
   Usage and operations group. Keep the top navigation ergonomic; do not add
   one flat top-menu link per operation. Reuse shared shell/components and
   leave room for later operations, without advertising unimplemented actions.

2. Add a read-only status and ID lookup workflow using the SAME service and
   typed results as the CLI. Form labels explain gateway diagnostic ID
   (X-SLAIF-Diagnostic-ID), client/request ID (X-Request-ID), namespace any/
   gateway/client, retention and ambiguity. Namespace is a native finite select.
   Recent retained diagnostic IDs use the shared bounded searchable
   picker, with manual entry for gateway/client response IDs absent from the
   current choices. A narrow diagnostic_request_id choice kind is allowed:
   minimal safe ID/namespace/time fields, current retention cutoff, at most100
   latest choices plus bounded search/current-older hydration through the same
   law. Choices follow the selected any/gateway/client namespace: do not offer
   only gateway IDs when the operator selected client lookup. Deduplicate
   choices by submitted value; actual lookup ambiguity is still resolved by
   the existing service, never silently choosing a record.
   The existing request_id kind mixes raw UsageLedger and AuditLog IDs and
   does not provide this projection; do not inject it unfiltered into this
   new page or pretend its choices are retained inference diagnostics.
   Request IDs are identifiers, not authority or guaranteed successful matches.

   Use POST for arbitrary typed lookup input so a pasted credential is not
   placed into a query URL/access log by the form. Authenticate and validate
   CSRF even for this form; no domain writes/audits for ordinary lookup. Keep
   unsafe/credential-shaped values out of HTML/errors/logs/redirects/hidden
   fields and clear them on refusal; safe input recovery remains useful.
   Reuse existing known-shape projection and finite service ID checks; no
   universal DLP or expanded lookup vocabulary. Any GET convenience entry
   accepts ONLY safe projected identifiers, never raw untrusted secret fields.

   Concrete preflight privacy finding: record-choices.js currently sends
   EVERY typed search in GET query parameters. Merely making the final lookup
   form POST is insufficient; the picker would already leak a pasted key into
   the access-log URL. For this ONE diagnostic_request_id kind, add a small
   explicit opt-in POST lookup to the fixed focused-router endpoint (for
   example /admin/operations/diagnostics/choices): q, selected IDs and finite namespace in the
   bounded body, current form CSRF in the body, fresh session with touch=False,
   no CSRF refresh, safe no-store JSON without unsafe q echoes. A short
   kind-specific branch in existing record-choices.js is sufficient; all old
   kinds retain their exact GET transport. No arbitrary lookup URL, generic
   transport framework, JS credential detector, second combobox or global API
   rewrite. Recent choices and selected hydration use the same new bounded
   diagnostics read, not unfiltered audit/usage IDs. A namespace change refreshes
   this kind's choices using the same finite field; preserve the typed ID for
   deliberate cross-namespace disambiguation rather than silently replacing it. The new kind need not be
   registered on the old GET record-choices endpoint. Bound input lengths and
   selected count server-side before use; do not echo parsed body/error detail.

3. Found view presents recorded correlation, timestamps, endpoint template,
   observed wire HTTP status SEPARATELY from stream_outcome, recorded reason/
   error/param, position/count/limit facts, token estimates/allowances, route
   and deployment provenance, authenticated key UUID only when recorded.
   Missing fields say unavailable; absent identity is not a guessed key.
   A stream_failure with HTTP200 is visibly a failure, not a success badge.
   Historical module identity says not recorded/unavailable. Optional current
   key/route detail links are contextual only and never historical assertions.
   Do not derive a rejection explanation by guessing from the current policy.

   Ambiguous view shows exact match_count, first at most100 typed candidates,
   overflow explicitly, namespaces/times/gateway diagnostic IDs, and safe
   disambiguation actions which resolve the chosen ID in GATEWAY namespace.
   Never silently show a first match, truncate the count or fetch all records.
   Not-found/expired versus unavailable-store are distinct useful outcomes;
   not-found does not prove no request was sent or that recording was enabled.

4. Status shows recording state, retention seconds/human duration, maximum
   records, write timeout, store availability, retained count/oldest/newest
   when available. Disabled recording still permits retained reads/cleanup.
   Explain bounded best-effort metadata, retention and physical cleanup, not
   full request storage. No switch to enable diagnostics or request capture.

5. Expose explicit expired-diagnostics cleanup with current authentication,
   valid CSRF, deliberate confirmation and nonblank bounded safe audit reason
   (reuse current512-character GUI reason bound). One action prunes at most
   the existing1000 expired rows, leaving retained diagnostics, usage, audits,
   replay, key state and capture files untouched. Show actual deleted count,
   batch limit and whether another invocation may be needed; no invented total
   remaining count without evidence and no automatic unbounded drain loop.

   Add the smallest explicit backwards-compatible shared service seam for
   this audited operation: delete and its one actor/reason/count/cutoff audit
   commit in ONE transaction, or both roll back. Preserve existing CLI
   cleanup() signature/default typed output and recording behavior. Do not
   duplicate SQL in the controller, monkeypatch commit, perform a direct
   controller delete, or claim an audit failure undoes an earlier commit.
   Derive actor from the session, never a posted UUID. On cleanup/audit/store
   failure report safe unavailable/failed status with no deletion success;
   do not echo exception details. A successful zero-delete explicit action may
   be audited once with actual count0; document that convention consistently.

6. From usage detail, offer diagnostic lookup for suitable local request IDs
   with explicitly correct namespace. The stored usage.request_id is the
   middleware request_id/client namespace; it is NOT the separate generated
   gw-UUID diagnostic ID. Use client lookup or any with truthful ambiguity;
   no upstream request ID presented as a gateway diagnostic ID. Do not turn
   every admin error reference into an inference lookup. Safe projected POST
   form is suitable where it prevents putting untrusted client IDs into URLs.

## Safe configuration and profile inspection

7. Show EXACT45 existing allowlisted Settings with value, configured/default
   source, practical units/meaning and process restart/recreate scope. Add a
   small explicit API-process scope option to the shared inspector; existing
   CLI output/default tests must stay compatible. Do not inspect __dict__,
   model_dump of Settings, arbitrary environment variables or .env files.
   Null/no configured limit/zero meanings follow each actual Settings contract,
   not a generic unlimited claim. Separate request budgets, output/context
   ceilings and operational waiting/rate limits. These values are not per-key
   effective policy and not the limits of every worker or the reverse proxy.

8. Display running package version using existing trusted package identity;
   available operator-declared deployed revision/provenance with safe bounded
   projection and explicit unavailable state; never synthesize a deployment
   SHA from mutable checkout Git. Do not expose server paths, credential env
   values, secret contents, connection strings, HMACs or password/session data.
   No DB/Redis/provider connectivity claim follows from configuration values.

9. Display validated registered UPSTREAM_LLM startup snapshot profiles as
   readable finite data and their exact version/profile/revision/sha256 route
   selector; registry unavailable/empty must be explicit and safe. Display
   safe identity ONLY of the active Codex compatibility DATA snapshot
   (module/revision/canonical digest and declared exact client provenance where
   available), clearly distinct from upstream selectors and qualification
   presets. Do not expose captured prompts/tool schemas/profile raw fixtures,
   browser path/file choices, hot reload, profile editor or compatibility
   migration here.212 owns Codex preset/binding management and migrations.
   Registered means loaded data, not real-client/provider compatibility proof.

10. All read-only pages/downloads/lookups use established session checks and
    no-store behavior. Non-page lookups/attachments MUST NOT rotate a currently
    displayed form's CSRF. If a JSON export is useful, keep it to these same
    exact finite safe projections, typed raw units, never a Settings dump.
    No need to add an export solely to create infrastructure.

## UX, preservation, allowed paths and non-goals

Retain SLAIF theme/fonts/branding, responsive cards/disclosures and clear
purpose-first wording. Every visible entry/choice control, including lookup,
namespace, cleanup confirmation/reason, needs adjacent meaningful associated
help and unique IDs/aria-describedby on actual controls. Use shared searchable
picker or native finite select; keyboard and no-JS usable through success and
validation recovery. Ordinary lookup stays simple; destructive cleanup sits
in a clearly labelled disclosure/action area. All new tables use ordinal first,
shared hyperlink sorting with neutral markers/raw typed sort keys, separate
request/token measures when present, exact zero/comma/M-token displays and
labelled keyboard-focusable scroll wrapper with correct empty rows. Editable
fields/export retain raw counts. No new design system, generic JS controller,
DOM-wide hint generator or global picker rewrite. No unrelated legacy cleanup.

Allowed app paths under app/slaif_gateway/:
- NEW api/admin_operations.py for the focused operations/diagnostics/inspection
  router; optional small companion api/admin_process_inspection.py only if
  materially useful, not an additional layer by default.
- main.py composition only; api/admin.py ONLY the directly necessary safe usage
  link context if a template cannot safely compose it from an explicit helper.
- services/request_diagnostics.py audited cleanup seam, safe result handling
  and narrowly bounded recent/search/hydrated namespace-aware ID read if needed;
  db/repositories/request_diagnostics.py matching minimal retained-ID query
  and any genuinely necessary small shared cleanup seam, no storage law.
  schemas/request_diagnostics.py ONLY a small immutable ID-choice projection
  if needed for that read; existing stored-record/outcome schemas unchanged.
  No persisted module identity or new diagnostic facts.
  db/repositories/audit.py unchanged unless an exact demonstrated constraint
  needs root review first; existing add_audit_log already supplies the seam.
- services/configuration_inspection.py explicit finite process-scope option and
  safe GUI-friendly unit/meaning metadata if useful; preserve45 allowlist and
  all default CLI fields/text. No config.py changes/new settings necessary.
- NEW web/templates/operations/index.html, diagnostics.html,
  diagnostic_detail.html and process_configuration.html; one small shared
  fragment within operations/ if genuinely reduces duplication. Existing
  web/templates/dashboard.html Usage/operations entry; usage/detail.html
  scoped link/form only; base.html ONLY coherent Operations entry/group if
  justified, preserving responsive/keyboard navigation and old links.
  Existing _record_choice.html optional backwards-compatible integration only
  if needed. web/static/css/admin.css isolated small layout additions only if
  established components cannot express it; no new asset is presumed needed.
- No upstream/client/profile loader changes are presumed necessary:
  app.state validated snapshots already exist. If truly absent data access
  needs an exact new path, show the current-state reason to root first.

Tests:
- NEW tests/unit/test_admin_operations_211.py,
  tests/integration/test_admin_operations_211_postgres.py,
  tests/browser/test_admin_operations_211.py.
- tests/unit/test_request_diagnostics.py and
  tests/integration/test_request_diagnostics_postgres.py ONLY affected shared
  cleanup regressions; tests/unit/test_cli_diagnostics.py ONLY affected
  compatibility coverage if needed, not a CLI behavior redesign.
- tests/unit/test_admin_record_choices.py ONLY directly affected shared
  default-transport regressions if needed; new private diagnostic search,
  retention, safe hydration and CSRF evidence belongs in the211 modules.
- tests/unit/test_cli_configuration_inspection.py explicit process-scope and
  unchanged CLI default coverage; tests/unit/test_main_app_structure.py,
  test_admin_slaif_design.py, test_admin_usability_inventory.py and
  test_documentation_contract_drift.py for exact new registrations/counts/
  consumer links, retaining substantive guards. Directly affected existing
  tests/browser/test_admin_dashboard_smoke.py or
  tests/unit/test_admin_activity_routes.py or
  tests/unit/test_admin_activity_templates_safety.py only if required by the
  scoped usage entry change.

Docs (existing files under docs/): SAME MISSING_GUI_FUNCTIONALITY.md G08/G16
and delivery status, admin-usability.md, verification/gui-cli-parity.md and
verification/README.md; security-model.md narrow audited cleanup/API-scope
notes and deployment.md/configuration.md only upgrade/restart clarification;
upstream-llm-adapter.md or cli-field-administration.md only a useful GUI
counterpart pointer. This exact order/active and one report. No duplicate
inventories/evidence documents or prose snapshots of every setting.

No DB schema/models/migrations, permissions/roles, API request acceptance,
client/server adapters/profile DATA, capture access/activation, provider calls,
accounting/quota/replay changes, worker/broker platform, filesystem custody,
settings editor, SQL console, browser terminal, schema executor or generic
pagination/retention framework. No exposing diagnostic full request content
under the guise of equivalence. All remaining objectives remain mandatory.

## Proportionate acceptance evidence and setup

Use /tmp/slaif192-coding-venv, existing Chromium and qualified owned PG
fixtures, /tmp/slaif211 receipts/screenshots (synthetic only). No new packages/
verification infrastructure or complete local matrix. Managed foreground test
terminals, qualified exact owner-label/loopback/tmpfs IDs and exact owned cleanup
only; no unused outer PG, abandoned background shell or blanket pkill/prune.
Reuse accepted201 producer/classifier/auth-provenance/retention/eviction tests
unchanged; prove the new GUI consumer and the changed cleanup boundary.

Focused unit/ASGI must cover typed found/ambiguity/overflow/not-found/store
unavailable/disabled state; wire200 stream failure; unavailable historical
module identity; no attribution on unauthenticated retained failures; safe
input/output canaries (including client-ID-shaped credential aliases), fixed
errors/no raw exception/log values; auth/CSRF/confirmation/reason denials;
allowlist45/source/default/API-scope/units/profile startup identity versus file
content changed later, version/revision unavailable; no environment dump.
A generic400 does not prove the intended validator was reached: establish
valid session+CSRF and assert intended safe rejection outcomes.

Actual PostgreSQL through authenticated HTTP must prove retained pre-admission
and HTTP200-stream records rendered correctly; collision/client ambiguity and
namespace disambiguation, expiry, recording-disabled reads; expired cleanup
bounded1000 with retained/unrelated rows preserved; one real actor/reason/count
audit and atomic rollback on a late audit/commit failure; failure is not a
success redirect. Reuse synthetic producer insertion/shared producer service
where appropriate and label that fact; do not claim a real provider/Codex
request. No need to regenerate unchanged complete producer conformance.

Actual Chromium must navigate dashboard→Operations→Diagnostics, safely look
up/disambiguate a retained failure and verify independently persisted cleanup
outcome; intercept actual browser requests to prove a synthetic credential
pasted into the picker never reaches ANY URL, error response or logs (POST
body refusal only), and existing kinds still use their normal GET lookup;
inspect API settings/profiles, keyboard/no-JS validation recovery and
real narrow/desktop styling. Capture actual rendered styles (no tokens or
secrets) for root visual review. Show existing usage/admin workflows still
work; include lookup/download if present→same-page form to protect CSRF.

Run smallest directly affected legacy/config/diagnostics/UI/consumer/structure/
inventory guards,9 OAP governance tests on exact order+active, scoped Ruff,
documentation checker and git diff --check. Inspect finite table/wrapper/
consumer registrations BEFORE publication; retain guards instead of relaxing
them to hide missing surfaces. Reuse component proof and avoid repeated
unchanged tests. Routine fixture/oracle/documentation corrections stay in this
order/PR; another suffix only for demonstrated blocking defects.

## Publication, operator instructions and handoff

Update the single living proof/coverage map: delivered G08/G16 only; G09–G15
and G17–G18 remain open, with final219 still required. Preserve earlier history. Explain where to find diagnostics/configuration; exact
namespace/retention/recording and cleanup semantics; unavailable historical
fields and process scope; strict local-only capture exception; ordinary API/
assets upgrade+recreate/restart, no schema or key migration, profile/operator
environment changes require recreating affected containers, no deploy done.
State synthetic vs actual PG/Chromium vs installed qualification; final219
installed whole-GUI test and remaining stages are NOT complete here.

Create exactly ONE211 PR on the named branch from accepted remote main.
Commit/push unchanged activation files with implementation. No force push,
merge or auto-merge. Update coherent PR title/body and same living docs BEFORE
final immutable report; no copied stale fixture/chronology/CI claims. Include
exact required report line Documentation updated: <files>. Report final literal
IMPL and actual per-head checks (pending/failed/skipped never passed).

Construct complete report draft away from final path. For absent
oap/reports/211-a-gui-diagnostics-config.md, publish from a temporary file in
reports with flush/fsync, same-filesystem os.replace and directory fsync.
Never assemble/append directly into final name or revise a finalized report.
Commit report-only SELF with firstparent exactly literalIMPL; only reportdiff.
Verify remotePRhead=SELF and exact order/report/topology bytes before sending
ONE two-byte responseOK, no newline. THEN install exactly ONE detached
/home/janezp/codex-supervision/slaif-api-gateway/wait-control-and-wake.sh,
with TMUX_PANE=%9, and verify its script/PID. No ad hoc read-r waiter, duplicate
reader or extra response. Root's canonical signal-wait-response-and-wake.sh
handles the other FIFO side and wake. No coding terminal needs polling after
canonical detached control wake. Wait without starting another objective.

Root independently checks immutable claims/material/visual/security/privacy/
accounting/docs and all final-head gates, merges with exact-head guard, verifies
actual main workflows/tree and records timings before212. Entire GUI goal
remains active through219, no release/tag/deploy/production authority.
