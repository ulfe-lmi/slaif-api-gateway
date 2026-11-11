# OAP Coding-Agent Report — 220-e

## Work order and result

- Identifier `220-e`; root-authored order `oap/orders/220-e-demo-account-final-unit-fixture.md` SHA256 `4538e91d126f93164f3972eb51a2e873edb8911caa2bafb9b7d35303459dba04`; `oap/active` exact `220-e`.
- Scoped unit-oracle repair COMPLETE; numeric objective 220 and PR #377 remain OPEN pending final-head CI and strategic review.
- Existing PR #377, base `main`, branch `oap/220-demo-account-control`, prior head 220-d report-only SELF `ec6c447c20daddfc99765627d4e84cd9d29ec124`. Pushed implementation head `15e6638b7861d016cfb1a639aae82faed9c2223b`. Report publication commit: SELF. Coding agent did not merge or enable auto-merge.

## Change and boundary

Only `tests/unit/test_admin_numeric_display_206.py` changed. In `test_usage_detail_actual_zero_cost_in_preference_to_estimate`, the page-wide `assert "7.75" not in page` (which falsely matched timestamp fractional seconds on the hosted run) is replaced by a cost-field-specific assertion `re.findall(r"<dt>Cost EUR</dt><dd>([^<]*)</dd>", page) == ["0"]`: exactly one cost field, value exactly zero, so a present actual zero still wins over estimated 7.75. The test pins `created_at`/`completed_at` to the deterministic timestamp `2026-11-11 22:51:17.751590+00:00` and asserts its fragment renders, so the old substring oracle is provably the collision source. Token-readout assertions and the separate estimate-only (`7.75`) and no-cost (`n/a`) tests are unchanged. The implementation commit also contains the unchanged root order and exact active pointer. No production code, formatter, pricing/FX, quota/accounting, schema, auth, CLI, provider/client, GUI, or docs change; prior OAP orders/reports remain immutable.

## Verification and limitations

- Exact failed test: `pytest tests/unit/test_admin_numeric_display_206.py::test_usage_detail_actual_zero_cost_in_preference_to_estimate` — 1 passed, direct exit 0.
- Full affected module: `pytest tests/unit/test_admin_numeric_display_206.py` — 60 passed, direct exit 0, including the estimate-only and n/a cases.
- Scoped Ruff on the changed file and `git diff --check`: pass. Changed paths are exactly the one test file plus the root order and active pointer. Mocked ASGI page test; no PostgreSQL, provider, Codex or browser rerun was required locally.
- Context: hosted unit check on the 220-d SELF `ec6c447c` was the sole failing check (1 failed / 7318 passed / 1 skipped); all other nine checks and all three workflows succeeded there. This order repairs that single brittle oracle; it is not evidence of, nor a fix to, any accounting or formatting defect.
- The full local integration suite and other local matrices were NOT rerun. Hosted final-head CI on this report SELF is the complete gate: all ten checks and three workflows must be SUCCESS before root merge; pending, missing or failed checks are not passes.
- No production data or credentials, provider/mail calls, deployment, release or schema change. Protected untracked `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock` were hash-verified without reading, staging or changing them.

## Publication and strategic follow-up

This report is published once at `oap/reports/220-e-demo-account-final-unit-fixture.md` via same-directory temp, file fsync, atomic replace and directory fsync. Its report-only SELF commit has sole parent `15e6638b7861d016cfb1a639aae82faed9c2223b` and changes ONLY this report. After verifying remote PR head, order/active/report bytes, prior immutable artifacts and protected hashes, send exactly one two-byte response `OK` to the canonical response FIFO and rearm one canonical control waiter on tmux `%9`. Strategic root verifies all TEN final-head checks and THREE workflow identities, reviews material scope, guarded-merges PR #377 only if green, then verifies actual-main nine checks/three workflows, records timing, and only then activates 221-a. No release/tag/deploy.
