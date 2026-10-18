# Codex 0.162 file-backed compatibility profile DATA — verification record

**Date:** 2026-10-18
**Objective:** 190-b (PR #328, branch `oap/190-codex-connector-tool-names`)
**Result:** `RESULT=QUALIFIED-FOCUSED` for the file-backed Codex 0.162
compatibility profile DATA slice described below. This is dated,
commit-specific, focused evidence — not a release decision, production
certification, real-provider qualification, or a broader Codex
compatibility claim.

## Scope and identities

Objective 190-b makes the 0.162 additional-tools compatibility policy
shipped DATA instead of source constants:

- Module ID (unchanged): `codex-0.162-responses-v1`.
- Packaged default DATA:
  `slaif_gateway/modules/clients/profiles/codex_0162.json`, revision `3`,
  raw file SHA-256 `5fb98ba442280c8d085fb86bfc6bc2ecaf66563bfc8709b917c927c22afb7102`,
  canonical profile DATA digest (bound as `fixture_sha256`)
  `aa3de5376819022191e11935ee311acd4b59bf590324daaa0e3ebc448daf90bd`.
- Frozen legacy migration selectors (historical, byte-immutable, not live
  decoders): v1 `("1", "724ec7358a95e8820f02f7dd2d2b1b4ad1276d4065af2ecd329cc2ca52b5892e")`,
  v2 `("2", "b7b257ed9338969a4482fd19434adb6b4a6d96c10037d69899298e643d303f85")`.
- Real 197-name/type diagnostic regression fixture (supplemental
  SYNTHETIC-wrapped evidence, not a runtime inventory or selected policy
  identity):
  `tests/fixtures/codex/0.162.1/connector-tool-names-197-v1.json`,
  SHA-256 `a32bbf25de4e0be15690feaf3a86a4f453aac2d281b9b67d2cd21daa1bd1c8c4`,
  with the approved bounded provenance sidecar
  `connector-tool-names-197-v1.provenance.json`.
- Operator override: `CODEX_COMPATIBILITY_PROFILE_FILE` (data revision >= 3,
  bounded regular UTF-8 JSON, read once at process bootstrap, no silent
  fallback; no hot reload).

Only the loaded DATA profile (revision >= 3) is a valid 0162 runtime pin;
legacy/stale pins fail closed until an explicit audited key-profile
migration. The executable decoder module and server pairing remain
statically registered; the DATA vocabulary is finite, validated, and
non-authorizing.

## Proven (this objective)

### Parser/loader (unit, DB/network independent)

`tests/unit/test_codex_profile_data.py` (16 cases): bounded decimal
revision >= 3 (10/20/100 accepted; 1/2/0, leading zeros, and non-ASCII
rejected), strict-int `schema_version` (rejects `True`, `1.0`), leading-
underscore ceiling derived from the data `max_characters - 1` (no baked
engine constant), single non-blocking open + `fstat` regular/size +
bounded read to EOF under MAX+1 with growth/truncation/oversize rejection
(monkeypatched `os.read` fixtures), embedded-NUL path mapped to a safe
error, duplicate `builtin_names` rejection, finite mixed-case grammar
traits (file-only `FooBar`/`___FutureTool` acceptance proven), immutable
FIFO/fail-fast loader behavior, and safe-error content independence.

### Real 197-name regression (unit)

`tests/unit/test_codex_0162_real_tool_names.py` (8 cases): the full human-
supplied 197-name/type capture passes the registered module plus the
shared request policy through the full chain with exact order, names, and
types preserved; built-ins stay strict; unknown authority/fields,
builtin leading underscores, duplicates, and caps remain denied. The
synthetic 197 fixture and the real-name fixture remain separate evidence.

### Focused unit pass (this run, JUnit-derived)

| Unit file | Tests |
| --- | --- |
| `tests/unit/test_cli_codex.py` | 27 |
| `tests/unit/test_codex_0162_client_tools.py` | 54 |
| `tests/unit/test_codex_0162_real_tool_names.py` | 8 |
| `tests/unit/test_codex_additional_tools_id.py` | 26 |
| `tests/unit/test_codex_client_modules.py` | 41 |
| `tests/unit/test_codex_profile_data.py` | 16 |
| `tests/unit/test_codex_profile_registry.py` | 17 |
| `tests/unit/test_config.py` | 54 |
| `tests/unit/test_module_architecture.py` | 39 |
| `tests/unit/test_responses_codex_client_tools.py` | 116 |
| `tests/unit/test_upstream_payload_reconstruction.py` | 82 |
| **Total** | **480 (0 failed)** |

### Real owned PostgreSQL (disposable, labelled, loopback, tmpfs)

`tests/integration/test_codex_module_upgrade_postgres.py`: 30 cases
(19 existing migration edges + 11 new profile-migration cases) —
profile dry-run performs no write/audit; apply to the active data profile
preserves the whole row (canary metadata, restrictions, dates, status,
quotas, counters) and audits old/new tuples; repeat target is a no-op
with no extra audit; rollback to the frozen `0162-v1` legacy tuple
restores the exact historical identity; same-revision/different-digest
and malformed version/digest/target and drifted legacy digests fail
closed with zero writes; audit failure rolls the metadata back atomically;
concurrent duplicate apply yields exactly one mutation and one no-op with
one audit record.

### Fresh-process real HTTP Gateway (owned PG, mock loopback backend)

`tests/e2e/test_codex_profile_data.py` (2 cases): a real uvicorn
subprocess boots the genuine `slaif_gateway.main:app` with an external
revision-4 profile file (same installed engine, no rebuild): the DATA-
only revision-4 rule (two bounded leading underscores) accepts the
synthetic `__future_tool` connector name end to end with a valid final
HMAC over the signed Local Coding identity, the synthetic service bearer,
and prompt-cache/metadata omission; a key still pinned to the stale
revision-3 tuple is denied before side effects (no backend call, zero
accounting); `slaif-gateway codex show-profile` in a matching CLI
process reports the same active identity as the HTTP snapshot; overwriting
the profile file after the process loaded it cannot mutate the in-flight
policy; a configured profile file that is invalid refuses startup with no
silent fallback.

`tests/e2e/test_codex_0162_local_tools.py` (5 cases, adapted to the
data-revision identity): the packaged-default (revision 3) module identity
drives the existing full-gateway 197-tool lowering, streaming plus owned
replay with final HMAC and finalized accounting, the fourth-route-grant
negative, and the stale-module negatives.

### Packaging

`slaif_api_gateway-0.1.0-py3-none-any.whl` built from this working tree
ships `slaif_gateway/modules/clients/profiles/codex_0162.json` byte-for-
byte (raw SHA-256 `5fb98ba442280c8d085fb86bfc6bc2ecaf66563bfc8709b917c927c22afb7102`),
and a clean extracted-install process (no repository path on
`PYTHONPATH`) loads revision `3` / canonical digest
`aa3de5376819022191e11935ee311acd4b59bf590324daaa0e3ebc448daf90bd` with
module constants derived from the same DATA.

### CLI error boundary (root probed, agent fixed)

An independent ACTUAL-CLI subprocess probe found the new read commands
leaking unexpected-exception detail via tracebacks; the fix wraps every
unexpected exception in the fixed generic `command_failed` safe handler
while preserving the expected fixed `CodexProfileDataError` codes and
messages, and `tests/unit/test_cli_codex.py` carries canary-leak
regression cases for `inspect-profile-file`, `show-profile`, and
`migrate-key-profile`.

### Independent root-side proofs (strategic review artifacts, not CI)

- Independent parser probe: 39 cases PASS, canonical default identity
  `aa3de5376819022191e11935ee311acd4b59bf590324daaa0e3ebc448daf90bd`,
  including revisions 10/20/100, configured underscore counts 3/7/15,
  builtin file override/default strictness, duplicates/nonfinite/bad
  types/caps, immutable snapshot, FIFO fail-fast; evidence
  `190-b-review/independent-profile-parser.json`.
- Fresh-process file3/file4 policy proof (same source/code):
  `__future_tool` rejected at revision 3, accepted at revision 4, stale
  revision-3 pin denied against the revision-4 active profile, normalized
  request/profile facts match the active file, loaded snapshot unchanged
  after a file edit; evidence
  `190-b-review/independent-file-profile-policy.json`.
- CLI error-boundary probe; evidence
  `190-b-review/cli-error-boundary-probe.json`.

## Not proven / boundary

- No real provider, real model, private plugin, or official-CLI run
  occurred for this objective; the mock Local Coding backend is synthetic
  (labeled not-a-capture), and the 197-name fixture is supplemental
  regression evidence, not a runtime allowlist or selected policy
  identity.
- No broader Codex protocol, stream-grammar (the 0162 generic grammar
  still excludes `arguments.done`), endpoint, or provider claim follows.
- Data files describe namespace names, prefixes, grammar traits, and
  ceilings only; they cannot grant permissions, endpoints, providers,
  hosted authority, or executable behavior. New execution/stream/item
  semantics outside the engine validators may still require code.
- The existing unsuppressed SQLAlchemy unary-distinct and Alembic
  `path_separator` warnings were observed in runs; they are preexisting
  and unrelated to this change.

## Evidence boundary

Unit tests are DB/network independent. PG and E2E evidence use the real
Gateway with an owned disposable PostgreSQL (exact labelled loopback
tmpfs container, removed by the fixture) and synthetic mock backends; the
E2E profile-data test additionally uses a genuine fresh uvicorn process.
No production deployment, backend-version, or release claim follows.
