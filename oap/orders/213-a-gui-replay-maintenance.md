# OAP Work Order — 213-a

PR mode: CREATE_NEW_PR

## Objective and current-state preflight

Deliver G09 from docs/MISSING_GUI_FUNCTIONALITY.md: authenticated, usable GUI
inspection and reviewed monotonic extension of retained Codex replay-reference
expiry using the CLI's existing services. The human approved the entire GUI
parity/field-guidance plan207–219 and ordinary strategic continuation/merge.
G09 completes one bounded capability; G11–G15/G17–G18 and final219 remain open.

Verified at 2026-11-01T13:06:29.062709+00:00: main abc080140cb324da29bbc01b93bb57a8abeac1e1, tree dc66f3df2556dd12905d705d6207119d1b1d3881.
Unique preceding PR 368 merged at 2026-11-01T12:54:09Z; final SELF 5347b5697c28e7f9c79b69e2c5166db7e5ffc85a.
All required final-PR gates passed, actualmain3workflows/all9checks successful,
merge tree equals accepted SELF, terminal timing recorded before activation.
Current oap/active 212-a, exact immutable order/report hashes
212-a order21889bytes SHA2560a3ce9c1a6fe74203bd6ac980f0efd992125c19b809920ac15cb16d0584714d2; report16667bytes SHA2566f90bc39b587d8f6fb468cfbbbc5654eed916e0db401f49654f2ed5e3724fa92. Open PRs only Dependabot PR319; no open212/213PR, releases only prerelease v0.1.0-rc.1; no release/tag/deploy authority, branch rules
active23580289: deletion/non-fast-forward protection, no bypass actors; required strategic final-head review/check gates unchanged. Sharedworktree protected/unrelated changes tracked worktree clean; protected untracked CODEX-SESSIONS.md/codex.sh/uv.lock hashes unchanged; preserve ignored .env/.codex/catalogs and linked worktrees; do not inspect protected file contents.
Fresh waiter/FIFO identities canonical coding waiter PID2833253 bash ./wait-control-and-wake.sh, PPID1/cwd strategic/TMUX_PANE=%9, sole instance; control.fifo trueFIFO inode4501469 and response.fifo trueFIFO inode4501470. Root mainCI66589 and response94719/finalPRCI65432/merge22890 CLOSED forever; never repoll or resignal212-a; sole next root response handle is
created by the canonical activation helper only after publication.

Create ONE PR from that verified remote main on oap/213-gui-replay-maintenance.
Coding agent owns Git execution; strategic owns order/active bytes. Preserve
unrelated changes, ignored operator config, protected files, linked worktrees
and catalogs. No reset/clean/stash/forcepush. No helper agents/nested model,
profile or effort changes. Existing right tmux pane only.

Read repository governance and directly relevant live contracts, especially
security-model.md, admin-usability.md, the replay-maintenance CLI/operator
contract and schemas/services below. Do not reread full architecture/archive
or inventories without an unresolved concrete question.

## Verified shared seams to reuse (refresh if212 changes them)

- services/codex_replay_maintenance.py CodexReplayMaintenanceService,
  inspect_replay_references, preview_replay_extend, apply_replay_extend.
- schemas/codex_replay_maintenance.py ReplayScope, ReplayExtendPlan,
  parse_replay_scope, parse_utc_datetime, validate_utc_bounds,
  render_replay_extend_plan, parse_replay_extend_plan_document and strict
  aggregate32KiB bound. cli/codex_replay.py establishes CLI behavior/projection.
- db/repositories/codex_replay.py and AuditRepository, caller-owned transaction.
  Settings availability lookup only; never return/log HMAC secrets.
- Existing admin auth/action/page/non-refresh read helpers and the purpose-,
  actor-, session-, expiry-bound HMAC review pattern in admin_review_intent.py.
- Existing Operations shell, key/cohort detail, local SLAIF assets, shared
  formatting, ordinal/sortable tables, field guidance and form recovery.

Core ceilings are1000 selected keys,50000 inspected references,100 displayed
route/model groups with explicit groups-truncated metadata, and total TTL
1..31536000 seconds. Exceeding key/reference ceiling REFUSES; never truncate
scope to the current page or latest100. Public aggregate state fingerprints
in the strict plan are permitted integrity facts, distinct from prohibited
raw reference UUIDs, provider item/call IDs, HMAC digests or key material.

Core already locks scope keys then references, rechecks membership after
BOTH blocking locks, and classifies with fresh time AFTER locks. Reuse it;
do not reimplement lock/eligibility/fingerprint/accounting law in controllers.
Original created_at + total lifetime is the target, max with stored expiry;
never now + lifetime, never shorten, recreate, or transfer reference ownership.
The real already-applied path has no duplicate writes/audit. Reuse accepted
objective200/CLI evidence where unchanged; no new20k-row scale repetition.

HMAC maintenance eligibility means the stored HMAC VERSION has a configured
secret available through the existing Settings lookup. It does not verify a
raw item ID/digest or prove the secret value matches historical material;
runtime replay authentication remains authoritative. Show availability and
exclusion counts, never secret values or promises that an extension restores
unusable material. Do not add a new digest/decryption verifier or key-recovery
surface to the GUI. Negative cases use unavailable/wrong VERSION and existing
same-key/ledger constraints, with accepted runtime-HMAC proof reused.

Explain a practical stable review scope: ongoing traffic can add references
between preview and apply and legitimately make an unbounded time window stale.
An explicit created-until cutoff or smaller selected scope can stabilize the
review; never silently add a cutoff, omit new rows, or relax the Core stale
check. This is field guidance, not a traffic-pause or maintenance-job platform.

## Required operator workflow

1. Add Replay maintenance within Operations, with clear scope choices: one
   existing key, one cohort, or explicitly every active key. Prefer existing
   Keys/Cohorts searchable lists -> selected detail -> bound Replay link; the
   global page links to these selectors and offers the explicit all-active
   scope. This matches212's known-record navigation and avoids a NEW typed
   UUID/live-search transport entirely. Selected scope is visible throughout.
   No hidden implicit all-active default. Key/cohort paths parse canonical
   UUIDs and check actual record existence, including older records. No new
   bare ID field without shared latest100/search picker. If a new picker is
   concretely necessary, report the specific absent usability seam before
   changing record-choice transport; do not add generic lookup infrastructure.

2. Scope inspection calls the shared read-only method and safely shows totals,
   active/expired states, UTC creation/expiry ranges, per-key aggregate rows,
   bounded route/model groups, exclusions with useful labels and configured
   TTL. State that eligibility is maintenance metadata, not client/backend
   readiness or replay authorization. Never expose raw stored JSON/content,
   ciphertext/reasoning, tool payloads/arguments/results, raw row identifiers,
   provider item/call IDs, raw HMAC digests or secret values/versions' values.
   Requested-model text and all dynamic labels use established known-secret
   shape/incoming-alias protection; no raw exception/plan dump in error/log.

3. Guided creation-time bounds are inclusive from/exclusive until in explicit
   UTC. Use exact service parsers; blanks mean no bound. TTL blank uses the
   configured default; explicit integer means TOTAL lifetime from ORIGINAL
   creation, units seconds, range1..31536000. Explain this beside the control
   with an example, not a tooltip. Expired inclusion defaults OFF and requires
   explicit selection. It cannot restore expired references outside selected
   lifetime, missing HMAC, inactive/invalid key, unfinalized ledger or other
   ineligible state. Show eligible/excluded counts and before/after ranges.

4. A deliberate preview invokes preview_replay_extend in the caller-owned
   transaction and has NO domain/audit write. Parse/render the returned plan
   through the existing strict schema. Require a useful bounded safe audit
   reason with field help using existing GUI convention and preserve the Core
   nonblank/credential protection. Bind the COMPLETE strict plan, safe reason,
   signed-in actor/session and15minute expiry using one distinct review purpose
   and existing HMAC/session secret. Include explicit small envelope/token
   caps covering32KiB plan+wrapper+base64 expansion; validate before allocation/
   signing. No file custody/jobs/tables/new secrets. The token is data, not
   authority; no token/reason in URLs or logs. Known incoming authentication
   aliases in any displayed/signed fact refuse safely before exposure.

5. Review displays exact scope, selected TTL/default, include-expired choice,
   eligible/excluded counts and expiry ranges before a separate confirmation
   and Apply. Apply requires current authenticated session, existing CSRF,
   correct actor/session/purpose/expiry/integrity and URL/scope agreement. Posted
   plan/count/TTL/reason/actor overrides confer no authority. Reparse strict
   plan; recheck current-request secret aliases before Core/persistence. Call
   apply_replay_extend in ONE caller transaction; shared service determines
   stale scope/state/eligibility, HMAC availability and accepted repeat.

6. Success and repeat truthfully show persisted aggregate outcome and safe audit
   facts, with reload links. Repeat never adds lifetime or creates duplicate
   audit. Stale state requests a fresh preview. On unconfirmed commit outcome,
   tell the operator to inspect state/audit; do not promise rollback. Actual
   late failure rolls back expiry changes and audit together. Do not unlock
   cost holds, edit policy/defaultTTL, grant replay access or rebind ownership.

7. Page/auth paths preserve existing behavior. Non-page reads/attachments/
   lookups, if any, authenticate without CSRF rotation and no-store. Prefer
   private POST for entered time/scope/reason data; no secret-bearing dynamic
   query URL. Validation failure is fixed/noecho with usable fresh-form/back
   recovery. NoJS operator flow works. All touched/new fields have unique
   actual-control IDs and associated meaning/default/units/scope/bounds help.

## UX, bounded paths and non-goals

Preserve cream/teal/lime SLAIF styling/local assets, navigation hierarchy,
keyboard focus, readable narrow layout, progressive disclosure. Every new
aggregate table starts with row ordinal; shared hyperlink sorting/neutral
arrows/raw typed sort keys; formatted comma/zero quantities; labelled focusable
scroll wrappers. Preserve numeric identity strings and precise timestamps.
No front-end framework, theme/flatmenu redesign or table-specific sorting.

Allowed app paths:
- NEW api/admin_replay_maintenance.py focused router and main.py composition.
- api/admin_review_intent.py one replay purpose/strict bounded plan+reason
  wrapper reusing existing primitives; all old purposes remain unchanged.
- NEW web/templates/replay_maintenance/index.html, inspection.html,
  review.html (combine if simpler); existing operations/index.html one card,
  keys/detail.html and cohorts/detail.html only useful bound-scope links.
- api/admin.py only a demonstrated shared context/read seam, backwards
  compatible defaults; no old-handler rewrites.
- Shared replay schemas/service/repository/runtime modules, CLI, models,
  settings and accounting implementation are READ-ONLY reuse. Report a concrete
  missing seam before expanding; do not repair hypothetical issues.
Tests: NEW unit/test_admin_replay_maintenance_213.py,
integration/test_admin_replay_maintenance_213_postgres.py,
browser/test_admin_replay_maintenance_213.py under tests/. Existing structural/
form/table/OAP consumer guards only directly required registrations and new
assertions, not weakened invariants. Living docs/MISSING_GUI_FUNCTIONALITY.md,
admin-usability.md, verification/gui-cli-parity.md and relevant existing replay
operator/security docs plus README index, no duplicate map/evidence catalogs.
One immutable213 report and exact activated order/active.

No schema, permission, adapter, request acceptance, accounting/replay-law change;
no raw replay inventory or content recovery, expiry shortening, key migration,
reference generation/ownership transfer, production calls, real client/provider/
mail, deploy/release/tag, packages, helper agents, generic jobs/storage platform.

## Proportionate evidence and setup

Reuse /tmp/slaif192-coding-venv, installed Chromium and existing ownedPG fixtures.
Verify exact owner/full containerID/loopback/tmpfs before use; clean only owned
resources. No environment/DSN dumps, blanketkill/prune, ambientDB mutation.
Synthetic receipts/screenshots /tmp/slaif213; no credentials/private content.

Focused unit/ASGI: scope parsing/existence/time/TTL/default/expired controls,
exact service invocation and read-only preview, strict plan envelope/types/
unknowns/duplicates/caps; invalid auth/CSRF/confirmation, wrong actor/session/
purpose/key/cohort, expired/tampered counts/TTL/reason/plan. Fixed noecho errors,
incoming alias canaries across every output/sign/apply boundary. Cover genuine
intended validator with valid auth/CSRF; generic400 alone is insufficient.

Authenticated HTTP + actualPG: inspection and preview no domain/audit write;
eligible/excluded synthetic retained references, original-age monotonic expiry,
explicit expired inclusion, same-key/finalized-ledger/HMAC eligibility, one safe
session-derived actor/reason audit, exact reload/repeat no duplicate write/audit,
stale scope and changed eligibility refusal, late failure atomic rollback.
Independent before/after database oracle compares ALL non-expiry/key/material/
ledger/quota/reservation/replay-ownership fields. Reuse unchanged accepted
concurrency/large-scope Core proof; no duplicate huge fixture or whole suites.

Actual Chromium: existing key/cohort and Operations navigation, select explicit
scope, inspect/preview/confirm/apply/reload/repeat with real shared service/PG;
independent DB oracle, existing displayed-page token remains usable after any
background read; keyboard/noJS recovery and desktop/narrow screenshots. No
mocked backend success presented as actual persistence. Root visually reviews
synthetic screenshots. No real Codex/backend qualification claimed.

Run smallest directly affected existing review/CLI/structure/consumer guards,
9 OAP governance tests on exact order+active, scoped Ruff/docschecker/diffcheck.
Routine test-fixture/doc corrections stay A/samePR; suffix only for demonstrated
blocking defect. No reruns unchanged suites; list distinct/overlap precisely.

## Delivery and handoff

Docs explain navigation, TTL original-age/default/expired/eligibility/ceilings,
read-only inspection vs reviewed maintenance, stale/repeat/audit/rollback,
retention/privacy, no schema upgrade and no production/client proof. Update
G09 only; preserve remaining G11–G15/G17–G18 and219 open. Reuse one living proof
record. Report actual exact commands/results/artifact hashes and limitations;
pending/skipped/failed checks are not passes. No terminal snapshots as law.

Create exactly one213 PR from verified main; commit/push unchanged strategic
order/active with implementation. Coding agent never merges or enablesauto.
Concise accurate PRbody/docs, literalIMPL, Documentation updated: <files>.
Construct report draft away from finalpath, publish absent
 oap/reports/213-a-gui-replay-maintenance.md using temp inreports, flush/fsync,
os.replace anddirfsync. Never revise final report. Report-onlySELF firstparent
literalIMPL, onlyreportdiff; verify remotePRheadSELF and immutablebytes/topology.
Then send ONE exacttwo-byte responseOK and installONE canonical coding control
waiter in%9. Strategic sole root response helper handles wake. Final exacthead
checks/reviews/material/visual gate -> guardedmerge -> verify actualmain
3workflows/all9checks/tree -> authoritative timing before214. WholeGUIgoal
remainsACTIVE through219; no release/deploy.
