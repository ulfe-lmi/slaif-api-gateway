# OAP Work Order — 220-a

PR mode: CREATE_NEW_PR

## Objective, authority and verified state

Begin the human-approved fresh-at-login fake-admin demonstration feature.
Objective 220 owns ONLY CLI-managed demo-account control and schema. The
complete authorized feature includes a fresh source snapshot after each
successful fake-admin login, wait page, identity masking while real usage
patterns remain, private disposable copy, silent no-op operational actions,
zero-active-account 404, logout/expiry cleanup and final installed/browser
proof. Later inert objectives 221–224 in strategic
workorders/DEMO-ADMIN-ROUND-PLAN.md own the remaining subsystems; do not
implement them early, create a partial public demo route, or declare this
first PR complete feature delivery. A live source snapshot/deployment/real
provider/mail call is NOT authorized by this coding order. Synthetic owned
fixtures only. The human is deciding whether file-backed admin artifacts
must be copied; that choice does not affect this identity foundation.

Verified startup 2026-11-11 19:06 UTC: predecessor219 TERMINAL on unique
PR376 (219-a/b/c), merged main
51677702cbc44673f2e60f924f6a1400eb2fa673, tree
a1f581cd8536c2b9cbc8cd1f664fca06b84b9970, parents
663c673494d4c0daeb4d5b1269b428ee13277448 and final SELF
42adf95d85fc9c44fe11fffd0f3b974e22af9a2c. All nine actual-main
checks and all three workflows SUCCESS (last workflow success
2026-11-11T18:15:13Z); timing and fullGUI audit recorded in strategic
STATE.md/EXECUTION_TIMINGS.md before this order. Existing `oap/active`
was exact `219-c`, its immutable report 5,056 bytes SHA256
709795225bc38046d69f89dfc21ad29592cf31fa4f5bec636099f2c8cf3a28bd;
prior a/b orders/reports and main history unchanged. No 220 PR exists.
Only unrelated open PR319 (Dependabot) and PR374 (Codex namespace) exist;
keep both untouched and do not incorporate their unmerged work. Main
ruleset23580289 active; basic/code-quality disabled. Only published
release remains prerelease v0.1.0-rc.1. No release/tag/deploy authority.

Use SAME existing coding CLI in right tmux pane %9 (PID3308462,
profile early-beta, Qwen3.8-27B A100 Q8 medium). No helper/subagent/
nested Codex/new model/profile/effort. Root has returned to NORMAL OAP after
its explicitly human-directed root-only219-c repair; this new 220-a is
coding-agent execution. Sole canonical control waiter PID1748414, cwd
/home/janezp/codex-supervision/slaif-api-gateway, TMUX_PANE=%9. Canonical
FIFOs are that directory's control.fifo inode4501469 and response.fifo
inode4501470, both actual FIFOs. The strategic model publishes this full
order and active `220-a` into the shared repository BEFORE one control OK.
Treat the consumed wake as execution authority; do not read control again
or send response before the report-only SELF is remote. Permanent
message.txt remains objective-neutral; do not rewrite it.

Shared checkout presently at old219 SELF with only protected untracked
CODEX-SESSIONS.md7881B SHA256
5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377feda,
codex.sh492B SHA256
66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247,
uv.lock405520B SHA256
d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6.
Preserve by HASH ONLY: never read contents/stage/modify. Preserve ignored
.env/.codex, provider catalogs, unowned worktrees/processes. Fetch current
remote main; create ONE branch `oap/220-demo-account-control` from the
exact base above while preserving the already-present root order/active.
CREATE exactly ONE new PR, suggested title "220: CLI-managed fake-admin
accounts in isolated control tables". Coding agent never merges or
sets auto-merge; root owns final-head checks/review/merge/actual-main9/3.

## Boundary and implementation

This is NOT a new real administrator role. Fake-admin usernames/passwords
live in dedicated `demo_control` PostgreSQL schema tables, separate from
`admin_users`/`admin_sessions`/gateway keys, and are writable only by a
trusted operator CLI path. Add one backward-compatible Alembic successor
of current head `0026_request_diagnostics`, with only the demo schema,
`fake_admin_accounts`, and a safe append-only account-events table.
Update SQLAlchemy model metadata consistently. No changes to existing
business-table columns, migrations, permissions, quota/accounting law,
provider/Codex/client modules, replay ownership, default content storage,
normal admin auth, or inference routes. Default live gateway has no
fake-admin login route at this stage; `/fakeadmin/login` remains 404 until
a later complete demo application is mounted. No HTTP endpoint may create,
reset, enable, disable or list fake-admin credentials.

Register `slaif-gateway demo-admin` CLI group with bounded `create`, `list`,
`enable`, `disable`, and `reset-password`. Use separate identities from
normal admins; no account can authenticate through the existing `/admin/login`
by username/password. Accept a username of 3..64 normalized ASCII letters,
digits, underscore/hyphen (start with a letter), case-insensitive unique.
Bound list size and numeric parsing; the list reveals only safe username,
UUID, enabled state, time and account generation. Passwords are only
salted hashes using the existing password primitive; never persist,
list, log, or display a plaintext/password hash. Password input is via
hidden confirmation prompt or `--password-stdin`; do not add a literal
`--password` argv option. Require nonempty bounded credentials and a
strong documented minimum appropriate to publicly reachable demo accounts;
reject credential-shaped username/reason text without echo. CLI exceptions
including DB/duplicate/invalid parameters produce fixed safe errors.
No raw DB URL/password/hash/user-provided secret in stdout, stderr, JSON,
audit or OAP artifacts. Use no real demo credentials in fixtures.

CLI account changes are one owned PostgreSQL transaction: current state,
password-hash change/activation state, monotonically increasing
`credential_generation` on reset/disable/enable, and one safe append-only
event with bounded reason and no hash/secret. Repeat disable/enable should
have defined idempotent behavior without fake success audit; a failed late
event/write must roll back the account change. This generation is the later
session invalidation fence; do not implement a session platform now.
Disabling the last active account must make the query for active demo
accounts return zero immediately; later demo login/access will use this
fact for 404. Password reset must not accidentally reenable a disabled
account. Avoid ambient production data or credentials in tests.

Document least-privilege future demo-web role: control-table SELECT only on
fake accounts; no INSERT/UPDATE/DELETE on account or event rows, and NO
business-table SELECT/DML or source-provider credentials. It may receive
narrow future session/job-table grants in later orders. This is the
mechanism that keeps a compromised fake-admin browser away from production
business state. Test the privilege boundary on an owned PostgreSQL 16 role;
operator role/bootstrap instructions must never print a live DSN. Schema
migration may grant nothing to absent roles; explicit grants come only
after roles exist. Do not make the normal admin app use this role.

## Exact files and verification

Allowed implementation paths: `migrations/versions/0027_demo_admin_accounts.py`;
`app/slaif_gateway/db/models.py` for the two demo-control models;
`app/slaif_gateway/db/repositories/fake_admin_accounts.py`;
`app/slaif_gateway/services/fake_admin_accounts.py`;
`app/slaif_gateway/cli/demo_admin.py` and
`app/slaif_gateway/cli/main.py` CLI registration. A tiny shared password
validator in the existing password utility is allowed only if direct reuse
cannot meet the documented bounds. Tests:
`tests/unit/test_demo_admin_accounts.py` and
`tests/integration/test_demo_admin_accounts_postgres.py`, plus directly
affected existing CLI/migration/OAP/contract tests. Documentation:
`docs/database-schema.md` (actual successor head/schema/rollback),
`docs/cli-reference.md`, and one new current `docs/demo-admin.md` that
labels this PR as foundation/disabled until later objectives. Root-authored
`oap/orders/220-a-demo-account-control.md`, exact `oap/active`, and one
matching immutable `oap/reports/220-a-demo-account-control.md`. If a
concrete necessary path is absent, report the reason to root before any
unsafe broadening; ordinary directly affected tests/docs may be added
within this scope. Do not create a generic demo framework or Nginx/Compose
profile at this stage.

Run focused unit CLI/password/credential-leak checks with direct pytest
exit and a real owned PostgreSQL16 integration for migration upgrade,
account lifecycle, alternate restricted role, duplicate/disable/reset,
no-write refusals, transactional late-failure rollback and safe outputs.
Use existing labeled loopback/tmpfs owned-PG fixture; no ambient
`DATABASE_URL` test setup, real production DB, provider calls, mail or
borrowed container cleanup. Check `alembic heads`, relevant documentation
contract/asof/schema tests, scoped Ruff and `git diff --check`. CI will run
the broad standard checks; no full local suite or unnecessary prior
CLI/browser/client matrices. No new GUI exists yet, so no claim of browser
feature qualification. Standard PR final-head full CI/review gates remain
root's responsibility; skipped/pending/missing checks are not passes.

## Delivery and immutable report

Docs say exactly what is implemented and how the later demo service will
use the restricted role. Document migration/rollback behavior and no
normal admin changes. Cite actual commands/exits/counts, owned-DB role
proof, negative/synthetic secret canaries and limitations. The full
fresh-snapshot/no-op UX remains a later objective, not silently complete.

Commit/push only the root-authored order/active unchanged plus the scoped
work. Prepare the complete report away from its final path; publish once
with same-directory temp, file fsync, atomic replace and directory fsync.
Report literal implementation head SHA and `Report publication commit: SELF`.
The final report-only SELF commit must have that implementation head as its
SOLE parent and ONLY the matching report diff. Verify exact remote head,
branch, PR identity, report/order/active bytes before one exact two-byte
response `OK`. Rearm exactly one canonical control waiter on tmux%9 after
handoff. Root then reviews material/CI, performs guarded merge if green,
checks actual-main9/3, records timing and only then activates221-a. No
release/tag/deploy or fake company data run.
