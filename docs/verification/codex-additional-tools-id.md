# 2026-10-18 Codex 0.149-v5 additional-tools ID and audited module migration

Objective 189-a: accept an optional bounded identifier on the Codex 0.149
`additional_tools` declaration item (module version 4 → 5) and provide the
bounded audited key-module upgrade/rollback path (0.149-v4 → 0.149-v5 /
0.162-v1 and the two reverse edges).

## Source facts

- Client module: `codex-0.149-responses-v1`, module version `4` → `5`.
  Module ID, structural capture fixture, and fixture digest are unchanged:
  `ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec`
  (`tests/fixtures/codex/0.149.0/responses-session-relationship-v3.json`).
- Source contract: tag `rust-v0.149.0`, commit
  `758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`.
- Upstream `ResponseItemId` is a serde-transparent STRING. The bounded
  character set, the 128-character ceiling, and the no-secret-content rule
  are the Gateway subset, applied through the existing bounded item-ID
  convention (`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`, ASCII) before
  canonicalization.
- The initial captured/constructed 0.149 declaration uses `None`. This record
  does not claim the entire 0.149 wire profile can never carry an ID: serde
  `default`/`skip_none` preserves a `Some(id)` value, and the upstream
  `models.rs` tests set `AdditionalTools.id` to `at_test`.
- ID fixture: `tests/fixtures/codex/0.149.0/additional-tools-id-v1.json`,
  SHA-256 `1a39db9dcc573dba2d0a10f33b4c333f27c774da2f72a4d09982d584238c00d1`.

## Behavior

- The declaration item's accepted field set is exactly
  `{type, id, role, tools}`; `id` is optional and nullable.
- A present non-null ID must pass the existing bounded item-ID validator
  before canonicalization and then canonicalizes unchanged; omitted or null
  IDs retain the prior canonical shape. Unknown fields remain rejected.
- The 0.149 taxonomy stays closed: the ID gate does not admit new tools,
  namespaces, or authority. Full positive acceptance of the wider operator
  profile is proved on the registered 0.162 module (see
  [`codex-0162-local-tools.md`](codex-0162-local-tools.md)).

## Audited module migration

- Legal transitions are exactly: `0149-v4 → 0149-v5`, `0149-v4 → 0162-v1`,
  `0149-v5 → 0149-v4`, `0162-v1 → 0149-v4`.
- The historical source tuple is frozen as the literal digest
  `ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec` (not
  imported from the current module) so later registry changes cannot silently
  retarget the historical selector.
- Targets: `0149-v5` = `codex-0.149-responses-v1` v5 (same fixture digest);
  `0162-v1` = `codex-0.162-responses-v1` v1, fixture
  `724ec7358a95e8820f02f7dd2d2b1b4ad1276d4065af2ecd329cc2ca52b5892e`.
- `slaif-gateway codex upgrade-key-module` / `codex rollback-key-module`:
  dry-run by default; `--apply` writes the `client_module` metadata and one
  audit record in one atomic transaction. Exact-target-first no-op ordering:
  an already-at-target key reports no change; a mismatched source fails
  closed with the specific code. Unsupported selectors are rejected with a
  fixed safe error and never echoed; unexpected failures render a fixed
  generic `command_failed` error and never echo exception details.
- No schema change: this objective ships no Alembic migration.

## Evidence and classification

- Unit (DB/network independent): `tests/unit/test_codex_additional_tools_id.py`
  (omitted/null/valid/invalid ID states, unknown-field and taxonomy
  invariants, upgrade-service transition matrix, digest/selector rules).
- Real PostgreSQL: `tests/integration/test_codex_module_upgrade_postgres.py`
  (repeat apply/rollback no-op, source mismatch, all four edges, audit-failure
  rollback, full `gateway_keys` row preservation except the `client_module`
  JSON path and normal `updated_at`, stale-session row-lock refresh preserving
  unrelated policy/usage, concurrent duplicate apply yielding one mutation
  and one no-op).
- CLI: `tests/unit/test_cli_codex.py` (no-configured-DB safe error, expected
  typed error code preserved, unsupported selector not echoed, injected
  unexpected `RuntimeError`/`ValueError` canary never echoed, nonzero exit,
  safe structured output).
- Deployment sequence (build, quiesce/drain, restart, fixed-binary-first
  verify, dry-run/apply/verify/repeat/rollback, and the existing
  route/pricing prerequisites) is documented in
  [`../upgrade-runbook.md`](../upgrade-runbook.md).
- Historical live deployment baseline (recorded before this change) still
  id-rejects against the deployed pre-upgrade registry; no deployment,
  release, or production claim follows from this record.
