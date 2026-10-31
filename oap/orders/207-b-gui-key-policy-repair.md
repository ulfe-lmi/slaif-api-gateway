# OAP Work Order — 207-b

PR mode: AMEND_EXISTING_PR
PR: 363 — https://github.com/ulfe-lmi/slaif-api-gateway/pull/363
Base: main at 67604ad6970ff8486e0a9905fdb87ffd37060bd2
Branch: oap/207-gui-key-policy
Title: Complete GUI key policy and rate administration

## Objective and authority

Finish G01–G03 of the approved GUI parity round. Repair the demonstrated
privacy and same-page download defects, bound reasons on the touched key
mutations, qualify advanced document creation and the actual new controls.
This is a continuation on the SAME unique PR363, not a new feature round or
permission to start208. Preserve all working GUI functionality and styling.
Human approved full GUI parity and explanatory help on new AND existing
fields; the remaining stages are inert proposals in the strategic GUI plan.

Use only the existing coding agent in right tmux pane %9. No helpers,
subagents, nested coding sessions, or model/profile/effort changes. Strategic
model alone accepts and merges, after final-head checks and review gates.
Routine in-scope fixture, documentation and CI corrections belong in this
order and PR; do not request a new repair round for those corrections.

## Verified live state and immutable history

At reconciliation PR363 is OPEN, non-draft, mergeable, no auto-merge,
no submitted reviews or unresolved review threads. Head/207-a SELF is
f0f5d13899cf9bd13def5f152b5aa415902c647f, first parent/IMPL
27a5f0a00d629bed32f9f0733d175e6a48034390; GitHub report-only diff and
local/remote report bytes independently verified. Report SHA256:
318f825ffb73fe826839037297bb4cc8c33d3fb6bc7200b8692da4b5abcad412.
PR created2026-10-31T18:22:35Z. Main remains67604ad above. The only other
open PR319 is unrelated Dependabot. Active main ruleset23580289 remains
enforced; latest release remainsv0.1.0-rc.1. No release/deploy authority.
GitHub head checks are partly successful, partly running; NOT all green.
Reconcile fresh before execution/publication; pending is never a pass.

207-a exact response was received by the canonical helper (root wake),
its terminal86236 is now closed/absent. It must not be signalled/replayed.
The sole new coding waiter is1894120, PPID1, cwd strategic root,
TMUX_PANE=%9, bash wait-control-and-wake.sh; recheck before activation.
True control/response FIFOs have inodes4501469/4501470 at the fixed
/home/janezp/codex-supervision/slaif-api-gateway paths. No substitution.

207-a order SHA256 MUST remain
a3e959226d2429ccc7f2d4d62603bf2e779304ae9d444394eb42959c52b5bbd0.
Its activated header/PR-mode syntax was a strategic authoring mistake,
causing2 governance format failures, correctly recorded without waiver.
The original bytes were restored before IMPL after an unauthorized edit;
that incident is history, not authority to edit activated inputs. NEVER
rewrite A/order/report, edit governance tests, or represent historical A as
all-green. This correctly formatted B becomes the active order; commit
its exact strategic-authored bytes and exact oap/active=207-b unchanged.

Protected untracked CODEX-SESSIONS.md SHA256
5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda
and codex.sh SHA256
66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247
remain unchanged/uncommitted. Preserve ignored credentials/catalogs,
auxiliary worktrees and all unrelated state. No reset/clean/stash.
Keep objective-neutral message.txt unchanged.

## Read and reuse

Read repository AGENTS.md, coding OAP protocol, this entire order,
docs/MISSING_GUI_FUNCTIONALITY.md G01–G03, current admin-usability and
gui-cli-parity verification record, relevant visual/security/session/policy
contracts. Reuse the strict version1 key configuration parser and core
KeyService operations, existing redaction utility, real session validation,
existing207 tests/owned PostgreSQL/browser fixtures. Do not reimplement
CLI/core policy, switch persistence, introduce a parallel API, or wrap CLI.

## Demonstrated defects and requirements

1. Protect new/touched key-form error output and retained values.
   Root used real ASGI/Jinja with synthetic input and mocked persistence,
   connection guards and zero DB attempts. Three cases currently return400
   with a COMPLETE credential-shaped canary in HTML: (a) otherwise valid
   version1 JSON allowed_models containing a canary, reaching real shared
   validate_gateway_key_policy against no routes: domain safe_message embeds
   rejected model; (b) malformed JSON plus a canary in reason; (c) a canary
   in a numeric rate input. Existing tests only unknown-field canaries do
   not prove these paths. Mask/reject known credential shapes using the
   existing redaction rules, including configured accepted key prefixes;
   sanitize safe-message display and retained form values at focused seams
   covering advanced create/update, touched guided key policy/create and
   rate edits. Do not retain rejected raw JSON. Keep useful ordinary field
   values/errors and HTML escaping. Known secrets must not reach HTML,
   flash, diagnostic logs, audit notes or allowlisted exports. Do not add a
   global DOM/Jinja redactor, content capture, broad DLP, new logger or
   silently corrupt canonical policy documents. Existing legitimate
   one-time plaintext creation result remains intentional and functional.

2. Configuration download must authenticate WITHOUT rotating form CSRF.
   download_admin_key_configuration currently calls _admin_page_context,
   which refreshes stored CSRF while the attachment leaves the displayed
   page unchanged. Root real-HMAC synthetic-session ASGI probe: detail200,
   attachment200, same-page old-token ratePOST400InvalidCSRF; fresh-token
   control303. Browser test currently avoids the defect by downloading
   BEFORE page.goto(detail). Fix the read-only attachment authentication
   using existing real session validation/non-rotating context, with the
   same active/expired/revoked checks and appropriate login-cookie behavior.
   Do not weaken mutation CSRF, authorization, global page-render/session
   design or cookie protections. Browser must load detail, download, then
   edit successfully using THAT SAME still-displayed form/token, no reload,
   page.goto, hidden-token replacement or injected fresh token workaround.
   Prove actual private attachment/headers/body and persisted mutation plus
   redirect destination; login303 is not a successful edit.

3. Bound reasons on these new/touched mutations.
   Root valid fresh-token ratePOST with513-character reason reaches service
   and303. _clean_admin_reason only strips; MAX_KEY_CONFIGURATION_REASON_LENGTH
   is512 but unused. Apply server-side nonblank/maximum512-character bounds
   to new rate/config edits and touched create/policy paths; field maxlength
   and meaningful visible hints must agree. Refuse oversize with fixed safe
   message before mutation/audit and preserve ordinary accepted reasons.
   Keep correction local to GUI seams; do not alter every legacy operation,
   CLI/service contracts or schema merely to introduce this bound. Confirm
   exactly512 valid,513 invalid and Unicode character behavior. Credential
   protection applies equally to refused reasons.

4. Qualify real document-mode key creation and actual-control visuals.
   Existing browser toggles policy_source then returns to guided; unit fake
   creation is insufficient for actual document-mode JS/form wiring. Add a
   native-browser document-mode create using synthetic policy, assert actual
   persisted canonical settings/export and unchanged provider tri-state,
   then navigate away from the intentional one-time secret result before
   taking any screenshot. Preserve strict unknown/duplicate/size/type and
   module binding migration guards; reuse unchanged component proof.
   Existing screenshots called create-form/effective-policy capture the
   legacy form bottom/top identity instead of new controls. Use the current
   browser fixture with focused element/scroll screenshots showing source
   and provider controls, effective-policy readout, rate and explain areas,
   and relevant narrow layout. No new harness, design system, screenshot
   inventory, or unrelated cosmetic redesign. Keep existing SLAIF theme,
   fonts, consistent field appearance, visible field help/aria-describedby,
   no-JS fallback, keyboard behavior and no overflow. No screenshots of
   plaintext keys, login/session values or other sensitive content.

5. Preserve accepted207 functionality and architecture.
   Preserve null/unrestricted vs []/deny-all vs selected providers, stored
   disabled provider preservation, no-mode empty fail-closed, strict64KiB
   canonical JSON and exact Decimals, absence/null/[] semantics, bound-module
   guard, positive rate controls/no-op/set/clear and nested window preservation
   (metadata.rate_limit_policy.window_seconds; A fixed that actual bug),
   read-only configuration-only explain and effective reports, one-time
   creation result, legacy lazy throttling/lifecycle actions. No request
   acceptance, tool/route permission, accounting, quota, replay or credential
   authority changes. PostgreSQL stays authoritative. No provider/SMTP calls.

## Bounded paths and non-goals

Product: app/slaif_gateway/api/admin.py relevant207 key handlers/rendering
and focused existing session helper only; existing shared redaction helper
may be used, not redesigned. web/templates/keys/{create,detail,_policy_selector}.html
for local reason constraints/help and needed field wiring. Existing207 CSS/JS
only for demonstrated local visual/wiring defects; no broad styling rewrite.
Tests: existing tests/unit/test_admin_key_policy_207.py,
tests/integration/test_admin_key_policy_207_postgres.py,
tests/browser/test_admin_key_policy_207.py and minimal directly affected
existing oracles if genuinely necessary. Do not create another infrastructure
or evidence suite. Docs: docs/MISSING_GUI_FUNCTIONALITY.md delivery status,
docs/admin-usability.md, docs/verification/gui-cli-parity.md and existing index
entries. Add current B status/proof, preserve accurate historical A evidence.
OAP: unchanged this order, active pointer, new207-b report only.
No schema/model/migration, core policy/service/CLI rewrite, transport/adapters,
provider/module taxonomy updates, capture UI, other G04–G18 functionality,
new dependencies/framework, production, release/tag/deploy or merge.

## Acceptance and focused verification

Reproduce corrected three privacy cases using recognized synthetic canaries
and ordinary-value controls. Cover authentication and wrong/expired/revoked
session, wrong/missingCSRF, blank/512/513 reasons, no mutation on failure,
safe logs/audit/HTML/export, unchanged ordinary rendering, and exact POST
success destination+persistence. Prove download/session behavior with real
CSRF service, not a mock always accepting all tokens. Browser same-page
download/edit and document-mode creation are required. Reuse current fixture
and accepted core/module/accounting evidence; row snapshots establish no
usage/reservation/key-material/validity/ownership changes from policy edits.
Never print canary values in command output/reports or include live secrets.

Run affected207 unit tests and9 governance tests; focused affected existing
unit cases only if changed. Run existing207 real-owned-PG and browser suite
with the new regressions because these changed form/auth/privacy boundaries
warrant it. A evidence already accepted as component proof:49 new unit,
168 combined,282 affected (overlapping, never sum),7 real-owned-PG,
6 actual Chromium. A browser chronology did NOT qualify same-page download.
Do not rerun unchanged CLI/provider/Codex/full matrices locally. Ruff/diffcheck
and documentation hygiene required; routine full CI supplies broad gates.
Use existing labeled loopback tmpfs PostgreSQL16 fixture, synthetic data,
TEST_DATABASE_URL only. Never default DATABASE_URL/secrets or Docker inspect
environment. Verify cleanup of exact created containers only, no prune.
JUnit/screenshots stay under /tmp/slaif207, not repository. Count failures,
skips, mocked/native/real layers honestly; do not sum overlapping runs.

Update one living verification file, operator usage/upgrade instructions and
status map. Correct earlier claims that reasons were bounded and all canaries
were covered: historical report stays immutable, B explains the actual gap and
resolution. No schema migration; code/assets rebuild/restart required, no key
mass-update. G04–G18 and final all-fields hints still pending later objectives.

## Publication and handoff

On same PR363 push implementation with exact B order and active bytes;
preserve all previous orders/reports. Amend concise PR description for final
behavior and precise evidence, not just format repair. Inspect current checks,
repair routine in-scope failures without another strategic order. Before
report verify unique PR/head/branch/state and clean authorized changes.
Then atomically publish exactly one new oap/reports/207-b-*.md, literal IMPL
SHA and Report publication commit: SELF; report-only final commit, first
parent IMPL. Verify remote PR head is SELF and report-only diff before exact
two-byte responseOK. Do NOT publish SELF before updating/verifying the PR.
Pending final-head CI is reported as pending for strategic verification.
Never edit activated order/active, old reports, governance gates or fabricate
completion. After response attach exactly one detached waiter in %9; no
new numeric objective or merge. Root independently reviews and gates merge.
