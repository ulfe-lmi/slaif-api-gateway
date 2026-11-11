# OAP Work Order — 220-e

PR mode: AMEND_EXISTING_PR (objective 220; unique PR #377)

## Objective and exact observed failure

Finish objective 220's final-head CI by repairing ONE false-positive unit
assertion in an existing admin numeric-display test. This is a test-only
continuation on PR #377, not a change to gateway accounting or formatting.
The human-approved fake-admin feature still requires later objectives
221–224 for fresh-at-login PostgreSQL AND file-backed snapshots, masking,
read-only/no-op GUI, disposal and installed proof. This order introduces none
of those public/demo behaviors and authorizes no live data or deployment.

Verified 2026-11-11 ~23:08 UTC: remote `main`
`51677702cbc44673f2e60f924f6a1400eb2fa673`; PR #377 OPEN, base `main`,
branch `oap/220-demo-account-control`, exact remote head
`ec6c447c20daddfc99765627d4e84cd9d29ec124`. That is immutable 220-d
report-only SELF with sole parent implementation
`703cdd38ae792f0ffa4630fc54f8e1cf226b0f05`, only changed file
`oap/reports/220-d-demo-prefix-migration-fixture.md` SHA256
`e35b5f46d45a671434fc7ce1011fe3747e5e420de0e0348accc218b5ae0d4d60`.
220-d order SHA256
`045ae6e67c7bcd0408c89ac42e6f25728fd6826dcdf321080ad260c2b23d9480`;
`oap/active` exact `220-d`. Preserve all 220-a/b/c/d orders, reports and
commits byte-for-byte. Unrelated open PRs #378 (provider catalog), #374
(Codex namespace) and #319 (Dependabot) remain untouched.
No release/tag/deploy authority; only prerelease v0.1.0-rc.1 published.

On exact SELF `ec6c447c`, all THREE workflows completed: CI FAILURE,
CodeQL SUCCESS, CodeQL - Code Quality SUCCESS. Exactly nine of ten PR checks
SUCCESS; the sole failed check is `Unit, lint, and migration head`. The
PostgreSQL integration, Playwright browser, E2E, Docker, documentation and
all CodeQL checks PASS. Hosted unit result: 1 failed, 7318 passed, 1 skipped,
14 warnings. The only failing test is
`tests/unit/test_admin_numeric_display_206.py::
test_usage_detail_actual_zero_cost_in_preference_to_estimate` at line449.
Its rendered HTML correctly contains `Cost EUR</dt><dd>0</dd>`; a page-wide
`assert "7.75" not in page` then falsely matches the fractional seconds
of a timestamp (`...22:51:17.751590...`). The estimate is NOT displayed as
the cost. Root inspected the exact hosted traceback and test source. This
is a brittle test oracle, not evidence of a cost/accounting defect.

Use the SAME existing coding CLI in right tmux pane `%9` (PID3308462,
profile `early-beta`, Qwen3.8-27B A100 Q8 medium); no helper/subagent,
nested Codex, new model/profile or worktree. Canonical control waiter
PID2295174 at strategic cwd `/home/janezp/codex-supervision/slaif-api-gateway`,
`TMUX_PANE=%9`, reads actual `control.fifo` inode4501469;
`response.fifo` inode4501470. Root publishes this full order and exact
active pointer into shared REPO_ROOT before ONE control OK. Permanent
`message.txt` stays objective-neutral and untouched.

Protected untracked `CODEX-SESSIONS.md` SHA256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
`codex.sh` SHA256
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
`uv.lock` SHA256
`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`:
preserve by HASH ONLY; never read/stage/change. Preserve ignored `.env`/
`.codex`, unowned containers/processes/worktrees and provider catalogs.

## Bounded repair and verification

Allowed implementation path: ONLY `tests/unit/test_admin_numeric_display_206.py`,
plus unchanged root-authored
`oap/orders/220-e-demo-account-final-unit-fixture.md`, exact `oap/active`
(`220-e`) and one matching immutable report. Replace the page-wide numeric
substring denial with a cost-field-specific assertion that proves the
rendered `Cost EUR` value is exactly zero (and, if useful, that only one
such cost field appears). Preserve the test's meaning: a present actual
zero wins over estimated 7.75; the separate estimate-only test must still
show 7.75 and absent-cost test must still show n/a. Make the collision
deterministic within the existing test by using a safe fixed timestamp whose
microseconds contain `751590` (or equivalent `7.75` sequence), then show
the cost-field assertion passes while the old page-wide assertion would
have failed. No production code, formatter, pricing/FX, quota/accounting,
schema, auth, CLI, provider/client or GUI behavior change. No unrelated
test cleanup or docs change for a test-only oracle correction.

Run the exact failed test and the affected unit module with direct pytest
exit (no full local suite); check the estimate-only and n/a cases, scoped
Ruff, `git diff --check`, exact changed paths, prior artifact hashes and
protected hashes. A mocked ASGI page test is sufficient; no PostgreSQL,
provider, Codex or browser rerun is required locally. Report that the
hosted final-head CI is the full gate, not the local focused test. If a
distinct blocker emerges, report to root rather than broadening scope.

## OAP delivery and final gate

Commit/push ONLY the scoped test repair plus root-authored 220-e order and
active pointer UNCHANGED on the existing branch/PR #377. Keep report concise
and factual; do not duplicate prior evidence inventories. Prepare
`oap/reports/220-e-demo-account-final-unit-fixture.md` away from its final
path, publish once with same-directory temp, file fsync, atomic replace and
directory fsync. Report literal implementation head SHA and `Report
publication commit: SELF`. The report-only SELF has implementation head as
SOLE parent and ONLY this report diff. Verify remote PR/head, order/active/
report bytes, prior immutable reports and protected-file hashes before ONE
exact two-byte response `OK` to canonical response FIFO, then rearm ONE
control waiter on tmux `%9`. Coding agent never merges or enables auto-merge.
Root independently verifies all TEN final-head checks and all THREE workflow
identities SUCCESS, reviews material scope/limitations, then guarded merges
PR377 if green. After merge, root verifies actual-main NINE checks/THREE
workflows, records timing and only then activates 221-a. No release/tag/deploy.
