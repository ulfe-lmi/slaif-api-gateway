# OAP Objective 190-b — final report: file-backed Codex 0.162 compatibility profile DATA

Work order: `oap/orders/190-b-file-backed-codex-profile.md` (committed
unchanged in this implementation commit; `oap/active` = `190-b`).
Branch: `oap/190-codex-connector-tool-names`.
PR mode: AMEND_EXISTING_PR — PR #328, base `main`
`86ae51c929b85ace6ef257239e4e900e7488754f`; predecessor SELF
`1549384cbdabdbfadf94de349358017bb8f623cb`, predecessor implementation
`e375e81684e996385a921b79785af1c49bf33e5d`. The coding agent never
merges; root reviews independently.

Implementation head SHA: 3d5a694c74999249a892f62935dc40d3439fa524
Report publication commit: SELF

## What changed

The 0.162 additional-tools compatibility policy is now shipped DATA with a
bounded parser and immutable snapshot loader. Future profile updates are
DATA FILE operations with the same installed engine (no source change, no
rebuild), while the executable decoder module and the exact Local server
pairing remain statically registered:

- `app/slaif_gateway/modules/clients/profiles/codex_0162.json` NEW
  packaged default profile DATA: revision `3`, raw file SHA-256
  `5fb98ba442280c8d085fb86bfc6bc2ecaf66563bfc8709b917c927c22afb7102`,
  canonical DATA digest (bound as `fixture_sha256`)
  `aa3de5376819022191e11935ee311acd4b59bf590324daaa0e3ebc448daf90bd`.
  No tool-name inventory: namespace literals/prefixes, bounded grammar
  traits, cardinality/schema/description/declaration ceilings, and
  provenance only. The leading-underscore connector bound is a DATA value
  (one leading underscore by default); the engine ceiling is derived from
  `max_characters - 1`, never a baked constant.
- `app/slaif_gateway/modules/codex_profile_data.py` NEW standalone
  bounded parser/loader: deeply immutable snapshot; bounded decimal
  revision >= 3 (10/20/100 accepted; 1/2/0, leading zeros, non-ASCII
  rejected); strict-int `schema_version`; finite validated grammar traits
  (no arbitrary regex/code/import paths); duplicate-key, nonfinite,
  unknown-field, above-cap, and unsafe-grammar rejection; single
  non-blocking open + `fstat` regular/size + bounded read to EOF under
  MAX+1 with growth/truncation/oversize rejection; safe errors never
  echo profile content, paths, or exception detail.
- `app/slaif_gateway/modules/clients/codex_0162.py` + `registry.py`:
  data-revision module. Module ID unchanged
  (`codex-0.162-responses-v1`); effective module version is the validated
  data revision and `fixture_sha256` binds the canonical DATA digest.
  Packaged-default facts (version/digest/builtins/prefix/limits) derive
  from the loaded default DATA and are never rewritten at bootstrap.
  One-shot registry bind: idempotent for repeated same-config
  initialization, rejects any different profile after binding; no
  facade, no hot reload, no in-flight mutation. The frozen v1
  (`724ec7358a95e8820f02f7dd2d2b1b4ad1276d4065af2ecd329cc2ca52b5892e`)
  and v2 (`b7b257ed9338969a4482fd19434adb6b4a6d96c10037d69899298e643d303f85`)
  tuples are historical migration/rollback identities only — not live
  decoders; only a loaded DATA profile (revision >= 3) is a valid
  runtime pin, and stale/legacy pins fail closed.
- `config.py` + `main.py`: operator-only
  `CODEX_COMPATIBILITY_PROFILE_FILE`; the HTTP app factory validates it
  exactly once at bootstrap (missing/invalid refuses startup, no silent
  fallback); the shared bootstrap helper lives in the client factory
  (not the app module) so offline CLI commands never import or
  construct the HTTP application.
- `cli/codex.py` + `services/codex_module_upgrade.py`: `inspect-profile-file`
  (pure offline validate + safe facts), `show-profile` (this CLI
  process's active snapshot), and `migrate-key-profile` (explicit
  `--from-version`/`--from-digest` source, target `active`/`0162-v1`/
  `0162-v2`, dry-run default, row-locked single-transaction
  metadata+audit, repeat-target no-op, same-revision/different-digest
  and drifted-legacy rejection). Original selector/edge upgrades
  untouched. Every unexpected CLI exception is rendered by the fixed
  generic safe handler (canary-leak regression cases added); expected
  `CodexProfileDataError` codes/messages are preserved.
- `pyproject.toml`: ONLY package-data inclusion of
  `modules/clients/profiles/*.json`. `.env.example`: ONLY the documented
  operator override.
- Real 197-name regression: human diagnostic capture copied byte-for-byte
  to `tests/fixtures/codex/0.162.1/connector-tool-names-197-v1.json`
  (SHA-256
  `a32bbf25de4e0be15690feaf3a86a4f453aac2d281b9b67d2cd21daa1bd1c8c4`)
  plus the approved bounded provenance sidecar; wrappers labeled
  SYNTHETIC. Counts 11/5/40/3/89/1/11/6/5/1/25, all `function`, 181
  single-underscore connector names, longest 42. Supplemental evidence
  only — never a runtime inventory or selected policy identity.
- Docs: `AGENTIC_CLIENT_INTEGRATION.md` (data-vs-executable contract
  distinction, data-revision versioning rules),
  `docs/module-architecture.md`, `docs/codex-compatibility.md`,
  `docs/responses-compatibility.md`, `docs/compatibility-matrix.md`,
  `docs/cli-reference.md`, `docs/configuration.md`,
  `docs/upgrade-runbook.md` (D5 data-only upgrade/rollback workflow);
  `docs/verification/codex-0162-connector-names.md` updated with the
  dated 190-b continuation; NEW
  `docs/verification/codex-file-compatibility-profiles.md` and
  `docs/verification/README.md` entry; stale pending-real-197 claims
  removed from current docs while dated 190-a/189 historical records and
  previous immutable reports/orders were never edited.

## V4 correction of the previous 190-a report subcounts (never rewritten)

The 190-a report remains immutable; its subcount arithmetic is corrected
here only:

- Unit: the 190-a focused selection total of 183 is arithmetically
  correct, but the per-file attribution was mislabeled. The authoritative
  per-file counts of that unit selection were 53
  (`test_codex_0162_client_tools.py`), 26
  (`test_codex_additional_tools_id.py`), 22
  (`test_cli_codex.py`), and 82
  (`test_upstream_payload_reconstruction.py`): 53+26+22+82 = 183.
- PostgreSQL: the 190-a run of 19 cases was 14 pre-existing
  `test_codex_module_upgrade_postgres.py` cases plus 5 new v2-edge cases
  (14+5 = 19), not "15 baseline + 5".

All NEW totals below are derived from the JUnit XML of this objective's
runs.

## Tests run (this objective; focused, no repeated green matrices)

Current runs (JUnit-derived):

- Unit (DB/network independent), one focused pass, 480/480 PASS (0
  failed): `test_cli_codex.py` 27, `test_codex_0162_client_tools.py` 54,
  `test_codex_0162_real_tool_names.py` 8,
  `test_codex_additional_tools_id.py` 26,
  `test_codex_client_modules.py` 41, `test_codex_profile_data.py` 16,
  `test_codex_profile_registry.py` 17, `test_config.py` 54,
  `test_module_architecture.py` 39,
  `test_responses_codex_client_tools.py` 116,
  `test_upstream_payload_reconstruction.py` 82.
- Real owned PostgreSQL (`owned_pg_url` fixture: disposable,
  exact-ID-labelled, loopback-bound, tmpfs-backed, removed by the
  fixture; no ambient production URL): 30/30 PASS in
  `tests/integration/test_codex_module_upgrade_postgres.py` — the 19
  190-a migration cases plus 11 new profile-migration cases: dry-run
  no-write/no-audit, apply-to-active whole-row preservation with
  old/new tuple audit, repeat no-op, rollback to the frozen 0162-v1
  legacy tuple, same-revision/different-digest + malformed
  version/digest/target + drifted-legacy-digest fail-closed, audit
  failure atomic rollback, concurrent duplicate apply = one mutation +
  one no-op + one audit.
- Real HTTP Gateway E2E, fresh process (owned PG, synthetic mock
  Local Coding backend labeled not-a-capture): 2/2 PASS in
  `tests/e2e/test_codex_profile_data.py` — a genuine uvicorn subprocess
  boots `slaif_gateway.main:app` with an external revision-4 DATA file
  (same installed engine): the DATA-only revision-4 rule accepts the
  synthetic `__future_tool` connector name end to end (valid final HMAC,
  synthetic service bearer, prompt-cache/metadata omission); a key
  pinned to the stale revision-3 tuple is denied before side effects
  (no backend call, zero accounting); CLI `show-profile` matches the
  HTTP snapshot; a post-load file edit cannot mutate in-flight policy;
  an invalid configured file refuses startup.
- Real Gateway E2E (existing, adapted to the data-revision identity):
  5/5 PASS in `tests/e2e/test_codex_0162_local_tools.py` — full-gateway
  197-tool lowering with final HMAC and finalized accounting, streaming
  plus owned replay, the fourth-route-grant negative, and the stale-
  module negatives.
- Packaging: `slaif_api_gateway-0.1.0-py3-none-any.whl` built from this
  tree ships `slaif_gateway/modules/clients/profiles/codex_0162.json`
  byte-for-byte (raw SHA-256
  `5fb98ba442280c8d085fb86bfc6bc2ecaf66563bfc8709b917c927c22afb7102`),
  and a clean extracted-install process (no repository path on
  `PYTHONPATH`) loads revision `3` / canonical digest
  `aa3de5376819022191e11935ee311acd4b59bf590324daaa0e3ebc448daf90bd`
  with module constants derived from the same DATA.
- `ruff format`/`ruff check` on all changed Python: clean.
  `git diff --check`: clean. `scripts/check_documentation.py`:
  `DOCUMENTATION_CHECK=OK files=101`.

Carried-forward evidence (historical, not reruns): the 190-a/189 dated
records, fixtures, and root-side proofs (33-case v2 policy probe,
7-lifecycle upgrade PG proof, 190-a stream/replay proof) remain valid as
recorded.

Evidence classes distinguished: synthetic schemas (all test wrappers),
actual human-supplied 197 names (fixture only, never runtime), mocked
backend (Local Coding loopback double), real owned PostgreSQL, fresh
real HTTP process, and historical official-CLI (189 only).

## Independent external evidence (root-side, not CI)

- Independent parser probe: 39 cases PASS including revisions 10/20/100,
  configured underscore counts 3/7/15, builtin file override/default
  strictness, duplicates/nonfinite/bad types/caps, immutable snapshot,
  FIFO fail-fast; canonical default identity
  `aa3de5376819022191e11935ee311acd4b59bf590324daaa0e3ebc448daf90bd`;
  evidence `review-artifacts/190-b-review/independent-profile-parser.json`.
- Fresh-process file3/file4 policy proof on the same source/code:
  `__future_tool` rejected at revision 3, accepted at revision 4,
  stale revision-3 pin denied against the revision-4 active profile,
  normalized request/profile facts match the active file, loaded
  snapshot unchanged after a file edit; evidence
  `review-artifacts/190-b-review/independent-file-profile-policy.json`.
- ACTUAL CLI subprocess error-boundary probe (found two read-command
  tracebacks leaking an unexpected-exception canary; never printed raw):
  fixed to the fixed generic safe handler with regression cases;
  evidence `review-artifacts/190-b-review/cli-error-boundary-probe.json`.

## Explicitly pending

- Final-head CI on PR #328: pending at publication; not a pass.

## Safety confirmations

No production DB/SSH/deploy/release/tag/email/provider/model calls; no
diagnostics; no schema, dependency, workflow, UI, or default-0147/0149
changes; no broadened stream grammar (0162 still excludes
`arguments.done`); no new server pairs, executable plugins, passthrough,
hot reload, remote fetch, or signing infrastructure; untracked local
files (`CODEX-SESSIONS.md`, `codex.sh`, and the
`.codex/.local-provider-catalog` tree where present) preserved and
uncommitted; no
merge/auto-merge performed; exact two-byte `OK` response sent once after
this report's publication, attached to the sole control waiter.
