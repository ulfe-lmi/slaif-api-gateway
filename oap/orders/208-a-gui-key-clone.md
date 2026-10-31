# OAP Work Order — 208-a

PR mode: CREATE_NEW_PR
Base: main at 09cbfb4795e279ef04e7a54f933afbeeaa7022b6
Branch: oap/208-gui-key-clone
Title: Add reviewed key cloning to the admin GUI

## Objective and human mandate

Deliver G04 of docs/MISSING_GUI_FUNCTIONALITY.md: an administrator can clone
an eligible standard key through select -> review -> confirm -> inspect
result/recover outcome, using the already-qualified clone service. Preserve
the working GUI and make every new/touched choice understandable. This is
one stage of the approved full GUI parity and all-fields-guidance round;
G05–G18 and final whole-GUI consolidation remain later objectives209–219.

Use ONLY the existing coding agent in right tmux pane%9, with its current
model/profile/effort. No helper/subagents or nested coding sessions. One208
objective, exactly one NEW PR against main. The coding agent never merges or
enables auto-merge. Routine in-scope fixture/docs/CI corrections belong in
this order/PR, without another repair round merely for those corrections.

## Verified state and activation gate

PR363/objective207 MERGED2026-10-31T19:45:51Z. Its final SELF is
6a32f3b8332259ede3df849a924671724e85c9ea, parent IMPL
59b2561db6eb3ce214da715bb8dadff41402bc3f. All10 final-head checks passed;
the automated test-helper comment was independently reviewed/resolved and
no unresolved review thread remained. Remote main09cbfb above has parents
67604ad6970ff8486e0a9905fdb87ffd37060bd2 and that accepted SELF; its tree
5518e59a220d6558dcbfd0a7276526144642d6ee equals the accepted SELF tree.

Activation gate PASSED 2026-10-31T20:01:33.638106+00:00: actual main09cbfb above has all9
expected checks SUCCESS and all3 workflows SUCCESS: CI41235731057,
CodeQL41235731053, Code Quality: Push on main41235731208. The final main
job completed 2026-10-31T19:59:44Z. Objective207 is terminal and fully verified;
208 is the next authorized objective. Root recorded closure in the timing
ledger before publishing this order.

No208 PR/order/report exists at drafting; root rechecks uniqueness and main
before activation. Only unrelated DependabotPR319 remains open; leave it
alone. Ruleset23580289 is active, no bypass actors. Release remains
v0.1.0-rc.1; no release/tag/deploy or production authority is delegated.
The shared checkout is on the207 branch/SELF; root does not manipulate Git.
The coding agent owns its safe fetch/branch execution and must preserve the
already-present exact strategic order/active bytes when changing branches.

Root verifies the sole coding waiter (last observed1929338,PPID1,cwd
strategic root,TMUX_PANE=%9), fixed true FIFOs4501469/4501470 and shared
order/active before ONE controlOK. Fixed root paths are the actual
/home/janezp/codex-work/slaif-api-gateway and
/home/janezp/codex-supervision/slaif-api-gateway. Never substitute FIFOs.
Read this entire selected208-a after that signal, not another proposal.

Protected untracked CODEX-SESSIONS.md SHA256
5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda
and codex.sh SHA256
66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247
remain unchanged/uncommitted. Preserve ignored secrets/catalogs/worktrees
and every earlier order/report. No reset/clean/stash. Keep permanent
objective-neutral message.txt unchanged.

## Read and reuse the existing implementation

Read repository AGENTS.md, coding OAP protocol, this order, G04 and section6
exceptions of MISSING_GUI_FUNCTIONALITY.md, admin-usability/visual-design,
relevant security-model, database-schema clone-receipt contract,
cli-field-administration/reference clone contract, and
docs/verification/2026-10-28-cli-key-cloning.md plus the final sections of
docs/verification/2026-10-29-cli-field-installed-workflow.md. Older component
records retain historical pending states; do not reopen the completed CLI
round or reinterpret those as current GitHub blockers. Reuse accepted core/CLI
proof; do not rerun the unchanged CLI matrices or recopy their inventory.

Concrete seams (recheck current source):
- app/slaif_gateway/services/key_clone_service.py: KeyCloneService.build_plan/execute_plan,
  KeyCloneResult, source eligibility/freshness/locking, receipt deduplication.
- app/slaif_gateway/schemas/key_clone.py: strict version1 plan, MAX_CLONE_PLAN_FILE_BYTES128KiB,
  source-expiry / exact-duration-seconds / absolute validity modes and bounds.
- app/slaif_gateway/services/key_policy_configuration.py: canonical create/export fidelity;
  app/slaif_gateway/db/repositories/keys.py: existing receipt lookup, not direct metadata writes.
- app/slaif_gateway/cli/keys.py clone runtime: caller-owned transaction; execute passes delivery
  creation separately; existing send/enqueue operations occur after commit.
- app/slaif_gateway/api/admin.py: current session/action/non-rotating read contexts, bounded
  reasons/known-secret display protection, record pickers, service scopes,
  key detail and existing one-time creation/email result patterns.
- Existing tests/unit/test_key_clone_service.py, tests/unit/test_cli_keys_clone.py
  and tests/integration/test_cli_key_clone_postgres.py cover unchanged core semantics.

## Required GUI workflow and invariants

1. Add an accessible Clone entry from key detail and a guided form. Show the
   source's non-secret public identity and supported/unsupported state; the
   core determines eligibility, including standard kind, status/validity,
   fence, and supported source policies. Refuse unsupported sources honestly,
   never silently reset their policy or weaken eligibility.
   Select existing owner and optional cohort with the shared latest100 plus
   older-search picker. Explain UUID versus public ID and optional no-cohort.
   Offer the three canonical validity modes, preserving exact positive
   seconds/service bounds (friendly unit choices allowed), and clear UTC
   absolute dates. Preview execution-relative times honestly.

2. Review a readable canonical policy/target/validity/delivery summary, with
   raw non-secret JSON optional. Preserve provider null/list/[], quotas and
   inheritance, supported Responses/module/profile, lazy/streaming/hosted-tool
   policy and every core restriction. Call build_plan, not a GUI policy engine.
   Preview is non-mutating/no policy audit. Require explicit apply confirmation
   and a bounded nonblank audit reason, with server-derived actor and CSRF.
   Fenced hosted-tool overrun acceptance remains a separate fresh explicit
   confirmation whenever the canonical plan requires it.

3. Protect reviewed intent, not merely its appearance. Bind the complete
   strict plan (including its operation UUID), source/target, delivery choice,
   current admin/session and bounded expiry with integrity; check before
   apply. Reuse suitable existing review mechanics or a minimal purpose-bound
   adapter using existing administrator-secret/standard HMAC helpers. No new
   persistence, secret deployment setting, workflow platform, or crypto design.
   A hidden JSON/fingerprint is not authority. Keep gateway-key/replay/provider
   secrets out of this mechanism. Bound encoded and decoded sizes based on
   the128KiB core plan plus bounded wrapper/encoding overhead, not a smaller
   arbitrary GUI policy cap. Tampering, wrong actor/session/source, expired
   reviews and malformed input fail with safe errors before mutation. Reparse
   through the strict canonical schema and execute the SAME reviewed plan;
   never regenerate a different operation UUID on apply/retry. Core locking,
   fresh-source checks and equality/receipt law remain authoritative.

4. Bind delivery before confirmation. The core plan itself does NOT contain
   GUI delivery mode; execute_plan receives create_email_delivery separately.
   A mutable apply field must not turn a reviewed mail operation into plaintext
   display or vice versa. Reuse explicit existing one-time display/pending/
   send-now/enqueue modes and their readiness/sendability rules. Commit the
   clone, one-time secret, pending delivery, receipt and audit through the
   existing caller-owned transaction; dispatch only after commit.
   A post-commit mail/broker failure means CREATED WITH DELIVERY FAILURE,
   with stable target/operation/delivery IDs and safe recovery. Never report
   that a second new clone is needed because dispatch failed.
   KeyCloneResult has an in-process plaintext_key member: never serialize/log
   the dataclass wholesale. Only the selected first successful one-time channel
   may show that new secret, privately/no-store. No secrets in URLs, hidden
   review state, errors, audit, logs, local storage, screenshots or assertions.
   Already-applied outcomes must not decrypt/recover/redisplay plaintext.

5. Provide authenticated result/receipt recovery by canonical source+operation
   identity or existing target/delivery views, including after review expiry
   or a lost response. Expiry blocks starting a new clone from that review;
   it must not force an automatic new UUID/clone merely to inspect an outcome.
   Read recovery never creates a clone or assumes an unknown outcome committed
   or rolled back. Ambiguous/malformed receipts fail safely. Delivery retry
   uses existing authorization/one-time sendability, never blindly resends a
   consumed/ambiguous secret. Clearly distinguish created, already-applied,
   not-found/unknown, refused, and delivery-failed. Preserve normal key actions.

6. New target has independent key material/identity, zero usage/reservations,
   independent replay ownership; source/unrelated rows stay unchanged. Preserve
   PostgreSQL accounting truth, holds/fences, strict local versus hosted tool
   authority, bound-module law and no-content-storage defaults. No inference,
   provider transport, CLI semantics, client/module/profile identity change.

## Bounded paths and user experience

Use app/slaif_gateway/api/admin.py for the relevant entry/runtime/rendering or
a focused new
app/slaif_gateway/api/admin_key_clone.py router with a minimal
app/slaif_gateway/main.py include. A small focused
app/slaif_gateway/api/admin_review_intent.py helper is allowed if necessary;
no general admin platform or monolith rewrite. Reuse existing session/reason/redaction/record-choice helpers.
KeyCloneService may gain a narrowly allowlisted READ-ONLY receipt projection
if essential; do not change execute/fingerprint/deduplication/eligibility law.
No schema/model/migration, direct production SQL/metadata writes or CLI shell.
Templates: app/slaif_gateway/web/templates/keys/detail.html and focused
app/slaif_gateway/web/templates/keys/clone*.html. Minimal changes in
app/slaif_gateway/web/static/css/admin.css, a focused
app/slaif_gateway/web/static/js/key-clone.js and
app/slaif_gateway/web/assets.py registration only if necessary; no global
component rewrite. Keep SLAIF palette/local fonts/cards, responsive
layout, native finite choices/shared record picker, meaningful adjacent help
and aria-describedby for every touched/new field. Explain purpose/units/blank/
scope/defaults/validity/delivery consequences; explain that a clone starts
with unused configured limits rather than transferring the source remaining
balance. Do not rely on placeholders.
Maintain no-JS submit/review/apply and keyboard access. Any data table follows
existing ordinal/hyperlink-sort/raw-sort/separate-request-token law. Readouts
use shared comma/M-token formatting; editable quantities stay exact.

Tests: tests/unit/test_admin_key_clone_208.py,
tests/integration/test_admin_key_clone_208_postgres.py,
tests/browser/test_admin_key_clone_208.py and minimal affected existing oracles. Reuse existing owned PG/browser fixtures,
not another framework. Docs: update docs/MISSING_GUI_FUNCTIONALITY.md G04 delivery status,
docs/admin-usability.md, the
single docs/verification/gui-cli-parity.md and existing navigation/index as
needed. Add a focused docs/security-model.md subsection for the new clone
review/actor/session/integrity/expiry, one-time delivery and recovery boundary;
no wholesale security-contract rewrite. Preserve dated analysis and previous evidence. Other G-items remain
open. Ordinary API/assets rebuild/restart; no schema/key-policy mass migration.

## Proportionate verification and setup authority

Focused native tests must prove plan fidelity, integrity/actor/session/source/
delivery binding, bounds/expiry, stale source, confirmations/reasons, wrong
session/CSRF, unsupported source and recognized-secret protection. Assert the
intended validator/service gate, not just any400 or login303. Keep ordinary
values/errors useful. Use synthetic values; failures must print fixed messages
or booleans, not generated keys or signed session material.

Real owned PostgreSQL GUI-to-service evidence: faithful canonical clone and
source/unrelated snapshots, target existence/validity, original operation
repeat => one target/already-applied with no plaintext redisplay/duplicate
audit, stale/tampered review refusal before writes, and committed clone with
post-commit dispatch failure/recovery. Reuse unchanged core concurrency,
rollback and same-key ownership proofs from the accepted CLI record rather
than rerunning its full matrix. Inspect actual persisted result/redirect target.

Actual Chromium: source detail -> guided choices -> review -> confirm -> safe
result -> inspect new target/faithful policy, repeated submission, recovery
and preserved ordinary key actions. Include keyboard/narrow/no-JS behavior
and focused safe screenshots of NEW controls; never capture the one-time
plaintext result page. Mock SMTP/broker IO; no real provider/mail/production.

Use /tmp/slaif192-coding-venv and the existing labeled loopback/tmpfs PG fixture
from tests/integration/test_lazy_throttling_postgres_redis.py; TEST_DATABASE_URL
only, never default DATABASE_URL or secrets. Temporary wrappers may reuse that
fixture; do not add repo infrastructure, dump Docker environment or prune.
Clean only exact created containers and record their identity/cleanup.
JUnit/screenshots under /tmp/slaif208, not committed. Run focused affected
tests plus9 governance cases, Ruff/diff/documentation checks. Repair routine
in-scope failures here; no full local suites or repeated unchanged evidence.

## Publication and report duties

Commit/push this exact strategic-authored208-a order and active pointer with
implementation. Create ONE208 PR against actual main, then verify/update its
head/description BEFORE final report publication. Preserve old orders/reports.
Inspect CI; pending/missing/skipped checks are not passes. No merge/auto-merge.

Construct the complete208-a report outside its final path. For final filesystem
publication, write a unique temporary file INSIDE oap/reports, flush+fsync it,
then os.replace/rename it to the absent final208-a filename and fsync that
directory. Do NOT cp/cat/append directly into the final report name. Fail if a
final report already exists; never rewrite it. This is the existing atomic
publication rule, not permission to build a new helper framework.

Commit only that new complete report in final SELF; literal IMPL SHA must be
SELF's first parent and only the report may differ. Verify pushed remote PR
head==SELF and report bytes/topology before ONE exact two-byte responseOK.
Then attach exactly ONE verified detached control waiter in pane%9. Report
commands/counts/artifacts, mocked versus real/installed scope, privacy/state/
accounting limits, setup/cleanup and upgrade instructions honestly. Root alone
reviews final-head checks, accepts, merges and verifies actual main before209.
