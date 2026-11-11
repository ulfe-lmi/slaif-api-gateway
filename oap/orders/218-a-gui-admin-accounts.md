# OAP Work Order — 218-a

PR mode: CREATE_NEW_PR

## Objective and authority

Deliver G17 in docs/MISSING_GUI_FUNCTIONALITY.md: routine administrator account
list/create/password-reset in the existing GUI. The human approved the complete
GUI parity round207–219, ergonomic SLAIF styling and meaningful field guidance.
Existing superadmin privilege is required on the SERVER for every account view
and mutation. Preserve offline first-admin/break-glass CLI. No new roles, general
RBAC, role editor, delete, activate/deactivate, MFA, tenancy or OIDC redesign.

Verified activation baseline (2026-11-10 UTC, root independent review):
- Predecessor217 is TERMINAL accepted. Unique PR373, round217-a, guarded
  ordinary merge at2026-11-10T19:57:44Z. Final report-only SELF
  919663b9e07433f5ebc192f51488e38e7530f31b has sole parent implementation
  6bf8641021816c02c6c5c4a98122d642090fbbdd and differs only by its report.
- Actual remote main/base is aacdc7b396d68a29f769117b6487e44df3e9ffcc;
  tree d82b948aeabd619e05872c1ef55b9607e4ed4266 exactly equals reviewed SELF.
  All NINE actual-main check runs and all THREE workflows succeeded:
  CI42890481529, CodeQL42890481511, CodeQuality42890482470. Last PostgreSQL
  completion20:13:24Z; root independently verified and recorded terminal
  resolution/timing in the strategic ledger before this activation.
  Final PR10/3 gates,26 resolved threads and root material review6766648129
  passed before merge. Main CI terminal24739 CLOSED exit0; never repoll it.
- Immutable217 order25359bytes SHA256
  9444fe37f59fd45c25f7a72881764c7d8946f47f7b825a66dc1d69a4f9f7ed36;
  report11736bytes SHA256
  8f42fbd1e89b03c44513fd301a7def5f864993803a19a7a762484490a01038c9;
  root verified complete local/remote exact-SELF bytes and active217-a5bytes.
  Preserve them. Root recorded the past non-atomic initial report write and
  evidence-provenance errata in review6766648129; do not rewrite that history.
- Only unrelated PR319 Dependabot and PR374 fix/codex-0167-namespace remain
  open. No218 PR exists. Preserve their work; no adapter/compatibility edits.
  Active main ruleset23580289 protects deletion/non-fast-forward; no bypass
  actors or required approval/status rules. Other rulesets disabled. Root
  nevertheless requires complete final-head checks and strategic review.
  Only release remains prerelease v0.1.0-rc.1; no new release/tag/deploy here.
- Shared worktree is still at old217 SELF branch as expected; coder owns Git
  reconciliation/new-branch execution, not root. Only protected untracked
  CODEX-SESSIONS.md, codex.sh and uv.lock exist before activation. Hash-only
  baselines: CODEX-SESSIONS.md7881bytes SHA256
  5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda;
  codex.sh492bytes SHA256
  66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247;
  uv.lock405520bytes SHA256
  d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6.
  Never read/stage/modify those contents, ignored .env/.codex/catalog state,
  unrelated worktrees or unowned processes/containers.
- SAME existing coding CLI PID3308462, right tmux pane%9, early-beta profile,
  Qwen3.8-27B A100Q8 medium. No model/profile/effort change, helper/subagent
  or nested Codex. Canonical control waiterPID274162 verified alone with
  STRATEGIC cwd and TMUX_PANE=%9. Root publishes complete shared activation
  before its one control signal. No second control reader in this turn.

Numeric218 has exactly ONE new PR, branch oap/218-gui-admin-accounts, base the
actual verified remote main at activation. Suggested title: Add privileged
administrator account management to the console. No219 activation while218
is unresolved. Coder never merges/enables auto-merge/force-pushes or amends a
pushed commit; root owns all final-head gates and guarded merge.

## Verified current source seams

Rechecked on the accepted217 main tree immediately before218 activation:
AdminService accepts AdminUsersRepository and AuditRepository. Create/reset
receive already-hashed passwords, and audits lack a caller actor. Reset changes
the password hash but does NOT revoke sessions. CLI composes the same service.
AdminSessionsRepository already has revoke_all_sessions_for_admin; no schema is
needed. AdminUsersRepository has get_admin_user_for_update from215 SMTP claims;
its existing SELECT FOR UPDATE does not request populate_existing.

GUI login authenticates and creates the session inside ONE _admin_service_scope
transaction. Authentication currently reads/verifies the password before its
last-login update acquires a write lock. A GUI-only sequential session deletion
cannot substantiate reset revocation under a concurrent login. Reuse existing
admin-row locking and fresh reads to serialize reset with password verification
and session creation. Do not invent session epochs, tables, token frameworks,
global request draining or generic account workflow engines.

## Allowed paths

Unless fully qualified, services/db/cli/api/web paths below are relative to
app/slaif_gateway/. Tests/docs paths are repository-relative.

- NEW app/slaif_gateway/api/admin_accounts.py; minimal main.py router wiring
  and operations/index.html/navigation link using the existing coherent groups.
- NEW web/templates/admin_accounts/*.html; existing shared components/CSS only
  directly needed for these forms, no replacement design system.
- services/admin_service.py, services/admin_session_service.py,
  db/repositories/admin_users.py and db/repositories/admin_sessions.py: minimal
  shared actor/reason, transaction/session revocation and fresh row-lock seams.
- cli/admin.py: compatible service composition for the intentional shared reset
  behavior correction, safe actor/reason provenance if necessary. Preserve
  bootstrap/list/create/reset commands and safe secret input/output.
- api/admin.py ONLY directly necessary existing session-scope composition or
  helper reuse; no unrelated legacy auth/RBAC/action rewrite.
- api/admin_record_choices.py, services/admin_record_choices.py ONLY a closed
  administrator-reference lookup if actually needed; no broad query surface.
- NEW tests/unit/test_admin_accounts_218.py,
  tests/integration/test_admin_accounts_218_postgres.py,
  tests/browser/test_admin_accounts_218.py; existing focused tests for
  AdminService/CLI/admin sessions/login rate limiting/password utilities and
  directly affected SMTP row-lock consumer only if its behavior changes.
- Existing tests/unit/test_admin_usability_inventory.py and
  test_admin_slaif_design.py for exact final table inventories and all guards.
- docs/MISSING_GUI_FUNCTIONALITY.md, docs/admin-usability.md,
  docs/verification/gui-cli-parity.md, docs/runbooks/admin-access.md,
  docs/security-model.md, docs/database-schema.md (behavior prose only; no DDL),
  docs/cli-reference.md, docs/configuration.md,
  docs/deployment.md, docs/compatibility-matrix.md, docs/rc2-feature-scope.md,
  README.md only current account/reset/upgrade truth. Preserve README logo.
- Root-authored order and oap/active byte-unchanged, one matching immutable report.

No model/schema/migration/dependency/accounting/replay/provider/client adapter
changes. Report any concretely necessary missing path to root within THIS order.
Routine fixtures/docs/static/qualification corrections stay in218-a and its PR.

## Functional and safety requirements

1. List existing administrator identities, names, exact stored roles, active
   state and safe timestamps using the existing service. Bounded pagination/
   lookup must expose older accounts, preserve filters and never imply a short
   page is complete. No hashes/session tokens/secrets, including attributes or
   JSON embedded in HTML. First ordinal, shared hyperlink sorting/neutral marker,
   correct typed raw sort values and accessible scroll wrapper.
2. All account views/actions authenticate and require the current persisted
   superadmin role. Hiding links is insufficient. Normal admin/operator/viewer,
   inactive/expired/revoked/missing sessions and wrong CSRF deny before effects.
   Preserve the existing dashboard-off gate and ordinary legacy GUI behavior.
3. Create a normal admin by default. Email/display name/password/confirmation
   and only admin-versus-superadmin choices, with explicit confirmation and
   bounded safe reason. Explain the privileged choice and its consequences.
   Normalize email/deduplicate through the shared service. Handle concurrent
   duplicate submission safely; no raw SQL exception or password/hash echo.
   Validate bounded input before expensive Argon2id hashing. No role/actor
   authority from browser-provided identifiers and no browser GET bootstrap.
4. Reset an exact existing target, show its server-derived identity and explain
   session revocation before confirmation. Require matching new password and
   confirmation, explicit confirmation/reason, fresh authorization and CSRF.
   Preserve exact password bytes rather than trimming or normalizing the secret.
   Never redisplay password/confirmation on success OR failure, put them in a
   URL/audit/log/task or return the hash. Only Argon2id hashes persist.
5. Shared service transaction changes the target hash, revokes all of that
   target's existing sessions and writes the actor/target/reason audit together.
   Audit failure rolls everything back. Unrelated users and sessions remain
   unchanged. Self-reset deliberately revokes the actor session and clears its
   cookie/returns to safe login with a secret-free outcome. New credentials
   subsequently authenticate; old credentials and revoked sessions do not.
6. Correctly order reset and login using existing user-row locks and fresh
   ORM values. A login based on the superseded password cannot escape session
   revocation after reset. Qualify BOTH transaction orderings with deterministic
   native-PG synchronization. No sleeps as race oracles, mocked locks or global
   serialization. Preserve rate-limit/failed-login/audit behavior. Document that
   session revocation does not recall already-running authenticated requests.
7. Reuse AdminService for GUI and CLI; do not duplicate password/account SQL in
   routes. Extend the smallest compatible actor/reason/session-repository seams.
   Preserve honest offline CLI provenance rather than fabricating a browser
   actor, and document intentional shared CLI reset-session behavior. No hidden
   CLI security bypass or second weaker reset implementation.
8. Every visible entry/choice has meaningful associated field help: identifier
   versus bearer, password semantics/bounds/non-redisplay, ordinary versus
   privileged role, reason/confirmation, target/self-reset/session effects.
   Known-account references use the existing searchable choices if editable;
   finite roles use native choices. Retain cream/teal/lime shell/local fonts,
   usable desktop/narrow/keyboard/no-JS flows and safe actionable error recovery.
   Ordinary product text explains outcomes and consequences, not OAP internals.
9. Keep first-superadmin/offline recovery available. Upgraded deployments with
   only ordinary admins get useful setup direction, never silent auto-elevation
   or browser bootstrap. Update the precise targeted privilege exceptions in the
   admin-access runbook AND the stale admin_users role-semantics prose in
   docs/database-schema.md (currently incorrectly says no role checks anywhere);
   document only the actual targeted G14/G15/G17 exceptions and reset-session
   behavior, with no DDL/schema change. Do not claim full RBAC on legacy routes.

## Focused qualification and test economy

Reuse accepted unchanged session/password/secret/CLI proofs. Require new focused
unit/ASGI tests plus real HTTP/service/owned-PG proofs for successful list/create/
reset, hashes-only persistence, exact actor/reason/target audit, duplicate races,
transaction rollback, complete target-session revocation, unrelated preservation,
self-reset logout, subsequent new-password login, old-password/session refusal,
and concurrent login/reset ordering. Demonstrate auth/CSRF passed when testing
a deeper gate; do not count an unrelated login303 or arbitrary400 as evidence.

Actual Chromium over the real app/ownedPG covers create/reset/self-reset,
ordinary-role denial, password non-redisplay, wrong/missing choices, navigation,
desktop/narrow/keyboard/no-JS and the persisted outcome. Synthetic accounts only,
no production/provider/mail calls. Store a few synthetic screenshots under
/tmp/slaif218 for root inspection; freeze accepted visuals, no cosmetic churn.

Use existing qualified owned Docker PostgreSQL16 fixture: unique owner labels,
exact full container ID verified before use/removal, loopback/tmpfs and cleanup.
Clear ambient DATABASE_URL/TEST_DATABASE_URL; never use ambient clusters, old
containers or bulk-prefix cleanup. No new installs/setup platform is required.
Refresh the existing qualified interpreter/browser tools at activation without
repeating a machine inventory. No real credentials, provider inference, SMTP,
deploy/release/tag or full-capture browsing.

Canaries must prove complete passwords/confirmation, session tokens, known
incoming auth aliases, provider secrets and password hashes never appear in
HTML/JSON bodies, errors, logs, audit or task payloads. The existing intentional
session-token Set-Cookie and CSRF form/cookie protocol remain functional; do not
misclassify that required delivery as a leak or weaken it. Test complete bodies
and captured logs rather than only selected elements. Reuse secret protection and safe error
helpers; do not merely omit assertions or suppress real warnings.

Run affected focused consumers and the TWO existing inventory/design modules
once against final templates, exact inventories retaining ordinal/sort/leaf/
empty-row/colspan/scroll guards. No lower bounds/ignore/skip/xfail/replacement
inventory. Scoped Ruff/compile/OAP/diff/docs checks. Do not rerun unchanged suites
for receipt naming or expand into all CLI/provider/Codex matrices.219 owns ONE
complete final installed whole-GUI workflow.

Concrete qualification commands (execute after implementing the named modules;
keep actual pytest exit separate from display/tail commands):

```bash
env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL \
  /tmp/slaif216-qualification-venv/bin/python -m pytest \
  tests/unit/test_admin_accounts_218.py \
  tests/unit/test_admin_session_service.py tests/unit/test_admin_login_rate_limit.py \
  tests/unit/test_cli_admin.py tests/unit/test_password_utils.py \
  tests/unit/test_admin_usability_inventory.py tests/unit/test_admin_slaif_design.py \
  tests/unit/test_oap_governance.py -q -p no:cacheprovider

env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL \
  /tmp/slaif216-qualification-venv/bin/python -m pytest \
  tests/integration/test_admin_accounts_218_postgres.py -q -p no:cacheprovider

env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL \
  /tmp/slaif216-qualification-venv/bin/python -m pytest \
  tests/browser/test_admin_accounts_218.py -m playwright -q -p no:cacheprovider
```

The existing native CLI consumer case is
`tests/integration/test_cli_admin_owner_records_postgres.py::test_admin_cli_create_reset_and_list_persist_safe_password_data`;
run it once if shared reset/composition changes (expected). If the existing
`get_admin_user_for_update` seam changes, exercise only its affected215 SMTP
claim cases (`test_claim_records_bound_identity_and_commits` and
`test_claim_refuses_duplicate_and_budget`) rather than rerunning mail/browser
matrices. Reuse the already-qualified owned PG fixture for the native case.
Run the existing documentation contract-drift/inventory/asof modules only for
the actual docs updates, scoped Ruff on changed Python, and git diff --check.
No redundant repeated inventory or tests just to change a receipt filename.

## Documentation, publication and handoff

Update G17 and the single shared GUI parity proof, operator usage and explicit
upgrade/restart/session consequences. State no schema/key-policy migration if
true; preserve key material/policy/quotas/usage/replay and existing exceptions.
No claim that all GUI guidance/final installed qualification is complete before
219. Include the repository-required exact documentation-impact statement.

Coder owns Git; preserve protected untracked CODEX-SESSIONS.md/codex.sh/uv.lock
by HASH ONLY and ignored local files. Do not reset/clean/stash unrelated state.
Use the SAME existing right-pane coding CLI/profile/model/effort unchanged.
No helper agents/subagents/nested Codex. Native compact/new only same-CLI context
maintenance, then reread active order. No fresh human permission for routine
current-order corrections or ordinary OAP continuation.

217-a publication lesson: a direct cat/write to the final report filename is
not atomic publication. Do not repeat it or claim a later Git commit retroactively
makes it atomic. Do not echo a pipeline tail status as pytest exit; use direct
pytest with immediate captured exit and the existing JUnit receipt.

Construct the complete report away from its final path, atomically fsync/publish
ONE oap/reports/218-a-gui-admin-accounts.md, final report-only SELF with sole
parent the literal implementation head. Report exact PR/base/branch/paths,
Implementation head SHA: <literal 40-hex>, Report publication commit: SELF,
commands/exits/JUnit/time/source snapshots, reused evidence and actual mock vs
native vs browser vs installed/live limits. Verify remote topology/head/bytes
and unchanged root order/active before one exact response OK. Re-arm ONE
canonical control waiter. Coder never merges/enables auto-merge.

Canonical handoff, verified before activation:
STRATEGIC_ROOT=/home/janezp/codex-supervision/slaif-api-gateway
REPO_ROOT=/home/janezp/codex-work/slaif-api-gateway
CONTROL_FIFO=/home/janezp/codex-supervision/slaif-api-gateway/control.fifo
RESPONSE_FIFO=/home/janezp/codex-supervision/slaif-api-gateway/response.fifo
Both are actual FIFOs, inodes4501469/4501470 respectively; never substitute.
Root atomically publishes this exact order under
REPO_ROOT/oap/orders/218-a-gui-admin-accounts.md and oap/active as the exact
five bytes218-a (NO LF), rereads both/unique match, records activation, then
invokes the canonical signal-wait-response-and-wake.sh once with TMUX_PANE=%8.
The existing waiter consumes that ONE exact2-byte OK and wakes your SAME CLI;
it has already consumed the signal when the OAP_CONTROL_OK_RECEIVED wake
arrives. Do not open another control reader. Read active/order and execute.
Root owns those bytes; commit/push unchanged with your implementation. Do not
amend217 commits or add another217 report. All old root terminals94638,
21178 and24739 are CLOSED forever; never repoll them or resignal217-a.
Root will record the sole new218 response-reader terminal separately in STATE.
At completion publish one immutable218 report by the required atomic procedure,
verify remote SELF topology, send ONE exact responseOK, then rearm ONE canonical
control waiter. The numeric change needs no fresh human authorization.
Root then verifies final-head checks/review/material/visual/docs gates, guarded
merges exact reviewed SELF and verifies actual main tree/9checks/3workflows and
terminal timing before219. Full approved GUI goal remains ACTIVE through219.
