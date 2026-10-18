# OAP Objective 190-a — final report: Codex 0.162 version-2 connector tool names

Work order: `oap/orders/190-a-codex-connector-tool-names.md` (committed
unchanged in the activation commit `77d676b`).
Branch: `oap/190-codex-connector-tool-names` from `main`
`86ae51c929b85ace6ef257239e4e900e7488754f`.
PR mode: CREATE_NEW_PR — exactly one Objective-190 PR, base `main`; the
coding agent never merges.

Implementation head SHA: e375e81684e996385a921b79785af1c49bf33e5d
Report publication commit: SELF

## What changed

Bounded connector-only compatibility fix for the registered
`codex-0.162-responses-v1` module, version `1` → `2`:

- `app/slaif_gateway/modules/clients/codex_0162.py`: namespace-scoped
  name classifier. Strict built-in namespaces (`functions`,
  `multi_agent_v1`) keep `^[a-z][a-z0-9_.-]{0,63}$`; dynamic
  `mcp__codex_apps__*` connector namespaces additionally accept the
  bounded leading-underscore form
  `^(?:[a-z][a-z0-9_.-]{0,63}|_[a-z][a-z0-9_.-]{0,62})$` (64 characters
  total including the underscore). Same character vocabulary, same
  cap; empty, all-underscore, doubled-underscore, uppercase/number-first
  after the underscore, and non-vocabulary names are rejected. Accepted
  names are preserved exactly (no strip/rename/normalize). No downstream
  shared validator was widened; the shared function-name intersection
  (hyphen permitted, dot not) is unchanged.
- `tests/fixtures/codex/0.162.1/additional-tools-profile-v2.json` NEW
  version-owned fixture (digest
  `b7b257ed9338969a4482fd19434adb6b4a6d96c10037d69899298e643d303f85`,
  provenance and pending-197 honesty recorded inside it). The v1
  fixture (digest `724ec7358a95e8820f02f7dd2d2b1b4ad1276d4065af2ecd329cc2ca52b5892e`)
  is byte-for-byte immutable and remains the historical `0162-v1`
  selector.
- `app/slaif_gateway/services/codex_module_upgrade.py` +
  `app/slaif_gateway/cli/codex.py`: selector `0162-v2` on the existing
  bounded audited tool; exact historical 0162-v1 tuple frozen as a
  literal; only the `0162-v1 -> 0162-v2` and `0162-v2 -> 0162-v1` edges
  added (six legal edges total); `--target 0162-v2` expects exact
  0162-v1, `--from-target 0162-v2` returns exact 0162-v1; original four
  0.149-v4 edges and all dry-run/apply/reason/row-lock/atomic-audit/
  idempotence/drift-denial/safe-error behavior preserved.
- Docs narrowly updated: `docs/codex-compatibility.md`,
  `docs/responses-compatibility.md`, `docs/module-architecture.md`,
  `docs/compatibility-matrix.md`, `docs/cli-reference.md`,
  `docs/upgrade-runbook.md` (image-dependent rollback guidance,
  six-edge lifecycle, v2 dry-run/apply/rollback examples),
  `AGENTIC_CLIENT_INTEGRATION.md`; NEW
  `docs/verification/codex-0162-connector-names.md` plus
  `docs/verification/README.md` navigation entry. Objective-189 dated
  records and old fixtures are preserved. `docs/provider-forwarding-contract.md`
  required no wording change (the lowering paragraph is
  profile-version neutral and remains accurate).

## Tests run (this objective; focused, no repeated green matrices)

- Unit (DB/network independent), focused selection: 183/183 PASS
  (0162 module 52, 0149 ID 26, payload reconstruction 82, CLI 14 +
  8 new selector-wiring cases, 1 new service identity-facts case),
  verified again by an independent 183-case focused run with sealed
  source bindings.
- Real owned PostgreSQL (`owned_pg_url` fixture, disposable,
  exact-ID-labelled, loopback/tmpfs, removed by the fixture):
  19/19 PASS in `tests/integration/test_codex_module_upgrade_postgres.py`
  (15 baseline + 5 v2-edge cases: dry-run/apply/repeat/rollback with
  stored-identity assertions, cross-target and drift fail-closed,
  audit-failure atomic rollback, concurrent duplicate apply, corrupt
  v1 digest rejection).
- Real Gateway E2E (`tests/e2e/test_codex_0162_local_tools.py`):
  5/5 PASS (3 existing 197/zero-admission cases + 2 new: pinned 0162-v2
  key streaming declared `_read_page`/`read_page` connector namespace
  under the existing generic 0.162 stream grammar plus owned replay
  carrying the streamed call and its output — exact names on both
  provider legs, valid final HMAC, credential/identity isolation, two
  finalized 5-token ledger rows, key counters (2, 10); invalid
  connector and builtin leading-underscore names rejected before
  admission with zero backend calls and zero accounting).
- `ruff check` on all changed Python: clean. `git diff --check`:
  clean. Docs checker independently reported OK (100 files).
- Warnings observed (preexisting, unrelated, unsuppressed): SQLAlchemy
  unary-`distinct` and Alembic `path_separator`. No test skipped.

## Independent external evidence (root-side, not CI)

- 33-case representative policy probe against the actual registered
  v2 module (connector positives/denials, exact name preservation,
  replay candidates, ambiguity denial).
- 7-lifecycle upgrade PostgreSQL proof (stored identity, full-row
  preservation, drift, concurrent, audit rollback).
- Real Gateway/auth/owned-PG/signed-Local-to-mock-backend stream +
  owned-replay proof (exact names on both legs, final HMAC valid,
  2×5 finalized ledger, key 2 requests/10 tokens).
- 183-case focused unit + 5 Gateway E2E green run with source hashes
  sealed in `review-artifacts/190-a-review/independent-final-source-binding.json`.

## Historical evidence carried forward (not reruns)

Objective 189 (PR #327, merged as `86ae51c`) records remain valid
historical evidence: the 0.149-v5 ID gate, the 0.162-v1 profile and
Local-pair lowering, the official-CLI 12-builtin lowering proof, the
route/pricing prerequisite proofs, and the legacy local streaming
E2E. The 189 official-CLI proofs exercise the 12-builtin lowering
only and do NOT qualify the new connector names; no official-CLI run
with connector names occurred for this objective.

## Explicitly pending (criterion NOT met)

- V2 / real 197 names/types artifact: PENDING. Only namespace counts
  (11/5/40/3/89/1/11/6/5/1/25) and the single actual `_read_page`
  example are on file; the human-supplied full names/types summary has
  not arrived. The v2 rule is validated against that representative
  name plus synthetic bounded vectors. No fabricated capture exists and
  no 197-name criterion is claimed. Root has been notified; the
  supplemental `connector-tool-names-197-v1.json` fixture will be added
  only when the data arrives.
- Final-head CI on the PR: pending at publication; not a pass.

## Safety confirmations

No production DB/SSH/deploy/release/tag/email/provider/model calls; no
diagnostic changes; no schema, dependency, workflow, UI, default-0147/
0149 widening, or namespace expansion; no real model, private plugin,
backend-version, or fixed-deployment claims; untracked local files
(`CODEX-SESSIONS.md`, `codex.sh`) preserved and uncommitted; no
merge/auto-merge performed.
