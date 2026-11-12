# OAP Coding-Agent Report — 222-b

## Work order and result

- Identifier `222-b`; root-authored order `oap/orders/222-b-report-accuracy.md` SHA256 `e02cd38d56c56a38f5a2312c07aff56264ebc516a8e6e9f82b67586f1f125542`; `oap/active` exact `222-b` (5 bytes, no newline).
- RESULT: COMPLETE — docs/report-only correction of the 222-a handoff's material reporting error, on the SAME objective-222 PR #381. No product behavior, schema, runtime, security, accounting, permission or GUI change; no test reruns (predecessor evidence is restated, not re-run).
- PR #381 `222: Verify masked demo database copies`, branch `oap/222-demo-db-masking`, base main `ccd058dacdb9ae9e0f55b7a2be69d4a7a38ad6b2`. At round start local == remote head `044556930d3a03d1bfc75ffda176e156622f80eb` (222-a report-only SELF, sole parent implementation head `7cb7217e3aa5d5ac64679349f3472f24ae678592`). Unrelated PRs 379/319 not touched. The published 222-a report `oap/reports/222-a-demo-database-masking.md` SHA256 `e3c09dbc13839bd5c24d8c61e4d579ec140fd2a35656b61b1785b30faf142d0b` is preserved VERBATIM — not edited, replaced, amended or deleted. Report publication commit: SELF. Coding agent did not merge or enable auto-merge.

## The corrected claims (substantiated)

222-a report line 16 said: "No raw source value, DSN, password, target database name or row content renders in CLI output, logs, manifests or this report." Line 22, case (6) said the "private manifest bytes and the CLI `sanitize --json` output (idempotent `SKIPPED`) contain no canary token and no target database name."

Verified against source and tests this round:

- `app/slaif_gateway/services/demo_snapshot.py` — `SnapshotManifest.to_json()` deliberately includes `target_db` (class docstring: retained so later stages can address the exact copy). So the private 0600 custody manifest CONTAINS the exact target database name plus private handoff/cleanup metadata. Line 16's extension of the no-render law to "manifests" is false; it is true for CLI output, ordinary logs and the report.
- `app/slaif_gateway/services/demo_snapshot_sanitize.py` — the private 0600 pre-state file (`sanitize_prestate.json`) retains source-derived entity ID lists and aggregate (md5) checksums that the independent verifier needs. It is a private custody record, not rendered output; it is not sanitized and not public-safe.
- `tests/integration/test_demo_snapshot_sanitize_postgres.py::test_cli_and_manifest_contain_no_canaries` — the ACTUAL assertions are: (a) manifest bytes contain no canary token ONLY; (b) CLI `sanitize --json` output contains no canary token AND `manifest.target_db not in output`. Line 22 case (6) conflated these into one joint claim; the no-target-database-name assertion applies to CLI output only. Distinguished precisely: private-manifest canary-negative assertion vs CLI-output no-target-name assertion.

Corrected statement: the private manifest does contain `target_db`; the CLI output does not.

## Actual test method (correcting 222-a's ambiguity)

The six synthetic owned-PG16 integration cases ran under HOST Python using PostgreSQL 16.15 client binaries (`Debian 16.15-1.pgdg13+2`) extracted from the optional worker image and placed on a temporary host PATH; this was NOT an in-container pytest run. The optional image was built separately (`docker build --target demo-snapshot-worker`, exit 0) and its binary versions (in-image `pg_dump`/`pg_restore` 16.15), packaged fixture (`demo_identities.json` loads, 31 keys) and in-image source SHA256s (`demo_snapshot_sanitize.py`, data file — equal to the worktree) were checked. That image build/content check is separate evidence from the integration run. Predecessor evidence is restated only, with no new run: unit `test_demo_snapshot_sanitize.py` 54/54 and unchanged 221 suite 33/33 (direct exit 0), owned-PG16 integration 6/6 in 14.79s (pytest exit 0 captured before any pipeline tail).

## Predecessor final-head CI (observed, not gated here)

At root review 2026-11-12T07:50Z the 222-a final-head CI on SELF `04455693` was still running (PG and browser pending). Re-observed at 2026-11-12T08:00:37Z UTC: CI run `43177466290` on `04455693` is in progress — CodeQL, Playwright browser smoke, Unit/lint/migration head, Docker Compose smoke, Documentation hygiene, OpenAI-compatible E2E and the CodeQL analyze jobs passed; the PostgreSQL integration tests job was still pending at that timestamp (it may have finished since; the state at gate time governs). No demonstrated blocking defect. Per the order, the report correction is required regardless of that CI outcome, and no product or test code was changed; the final-head hosted CI of this 222-b SELF is the strategic root's gate, and pending/missing/failed checks are not passes.

## PR body and cli-reference check (order item: correct if the false claim repeats)

- PR #381 body: verified — it contains no manifest/target-database-name wording and does not repeat the false claim; no PR description change was needed.
- `docs/cli-reference.md`: verified — its only "manifest" mention is the unrelated request-capture facility; no false claim; no change.

## Docs correction (same PR, scoped)

`docs/demo-admin.md` only:

1. Objective-222 "Private operator inspect / retry / cleanup" section now states precisely: the private custody manifest contains the exact target database name plus the private metadata the later stages and exact-copy cleanup address; the private pre-state file contains source-derived entity IDs and aggregate checksums the independent verifier needs; the custody directory must be configured OUTSIDE the repository and databases — an operator requirement, since the worker enforces the no-symlink and owner-only 0700 boundary but not repository exclusion; the custody files are operator-owned 0600 under the existing custody access and retention rules; the raw dump/copy already exists in private custody; the private files are NOT sanitized and NOT public-safe (they may retain source-derived values) and must never be moved, displayed, committed or attached. The Cleanup bullet now states the rendered-output law exactly: CLI output, ordinary logs, reports and committed artifacts omit the target database name, secrets and source identifiers, and that law does not apply to the private custody files, which intentionally retain them.
2. The pre-existing objective-221 "Custody" bullet carried the same unconditional "OUTSIDE the repository" runtime-guarantee phrasing; it is aligned to the same operator-requirement wording (same accuracy finding, same file, minimal rephrase).
3. Preserved unchanged: the retry → exact-recorded-copy cleanup → custody-files-last ordering with the orphaned-copy risk statement; the explicitly accepted usage-pattern privacy limitation; and the target private-network / `ssl=False` transport limitation.

## Verification (this round, scoped)

- Substantiation: source (`demo_snapshot.py` manifest, `demo_snapshot_sanitize.py` pre-state) and the integration test read and quoted above; every corrected claim is backed by that evidence.
- Diff scope: exactly `docs/demo-admin.md` plus the unchanged strategic-authored `oap/orders/222-b-report-accuracy.md` and `oap/active` in the implementation/docs commit; the SELF commit changes only this new report. No other file edits.
- Documentation hygiene (the CI job's checks): `git diff --check` clean; `scripts/check_documentation.py` OK (files=137); public-client env-name grep clean.
- No rerun of any unchanged unit/PG/browser matrix; no new infrastructure.
- No actual target database name, secret, source identifier, raw row or canary token appears in the new docs text or this report (`target_db` appears only as a field name).
- Protected untracked `CODEX-SESSIONS.md` / `codex.sh` / `uv.lock` never read, staged or changed; hashes re-verified immediately before the response OK.
- No production data or credentials, no provider/mail calls, no deployment, release or tag. Objectives 223–225 remain inert.

## Publication and strategic follow-up

This report is published once at `oap/reports/222-b-report-accuracy.md` via same-directory temp, file fsync, atomic replace (exactly once) and directory fsync. Its report-only SELF commit has sole parent the implementation/docs head and changes ONLY this report. After verifying the exact remote PR head, order/active/report bytes and the three protected untracked hashes, exactly one two-byte response `OK` is sent to the canonical response FIFO and exactly one canonical control waiter is rearmed on tmux `%9`. Strategic root reviews the final-head hosted CI (all checks/workflows SUCCESS), material scope, report truth and the review threads, then guarded-merges only if all gates pass. No release/tag/deploy.
