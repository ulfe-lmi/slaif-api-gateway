# OAP Report — 223-b (Route Capability Snapshot)

Same-PR continuation of objective 223 on PR #382. This report is
immutable once published; it records what 223-b implemented, how it was
focused-verified, and the honest limitations. It does not merge anything.

## 1. Identity and verified state

- Active work order: `oap/orders/223-b-route-capability-snapshot.md`,
  SHA256 `759f34a450dd84e306fa3aa4fced63773e821ffcbec87c31ec8869d4e274c796`;
  `oap/active` exact `223-b`.
- Vehicle: unique PR #382 `223: Verify demo file-backed snapshot`,
  branch `oap/223-demo-file-snapshot`, base `main`
  `2209e100552397407d9641fc2eeba1029710c1a3`. No new PR, no merge, no
  auto-merge, no helper/subagent, no model/profile change.
- 223-a report `oap/reports/223-a-demo-file-snapshot.md` and all earlier
  orders/reports remain in this PR, byte-for-byte unchanged.
- The three protected untracked files (`CODEX-SESSIONS.md`, `codex.sh`,
  `uv.lock`) are preserved by hash only and were never read/staged/modified.

Problem closed: the merged 222 database sanitizer treated
`model_routes.capabilities` as a top-level boolean map (action `JJ`).
Real installed route configuration writes nested typed capability blocks
and may reference an operator completion-profile ID, so a real route with
such a block failed 222 DB sanitization before 223 files could complete.

## 2. Diff scope (implementation head `b53fa881`)

Seven files changed on the existing branch:

- `app/slaif_gateway/services/demo_snapshot_sanitize.py` — new route
  capability action `RC`; shared per-copy `demo_profile_id`; RC transform
  and independent verifier; `RC` reserved for `model_routes.capabilities`
  and removed from the `JJ` validator set; verifier conflict recheck.
- `app/slaif_gateway/services/demo_snapshot_files.py` — 223 completion
  choices reuse the shared `demo_profile_id`; combined DB/files
  completion-link gate (verified stored leaf + bounded read-only DB query
  + post-query deadline); `run_files_job` fence-leak fix (base config
  validated before fence acquisition).
- `tests/unit/test_demo_snapshot_sanitize.py` — 8 RC unit cases (empty doc,
  representative nested doc, per-copy profile/compaction/destination
  remap, unknown/invalid fail-closed, tampered stored doc, policy wiring).
- `tests/unit/test_demo_snapshot_files.py` — completion-link law and
  runner cases (mismatch before publication, missing-choices refusal,
  config-validation fence-leak regression).
- `tests/integration/test_demo_snapshot_sanitize_postgres.py` — 222 owned
  PG seed route now carries a nested capability document using the
  installed child grammar (boolean flags + `codex_limits` + compaction
  reference + completion selector; a direct-SQL fixture, not a
  full-route-validated installed candidate).
- `tests/integration/test_demo_snapshot_files_postgres.py` — 223 owned PG
  seed now holds an ordinary openrouter nested route plus a synthetic
  module-provider completion-service route and its `provider_configs`
  row; the main handoff test asserts the copied completion profile links
  to the captured choices leaf and the compaction list is remapped;
  empty-`except` hygiene corrected in the web-denial helper.
- `docs/demo-admin.md` — replaced the 223-b follow-up limitation with the
  exact implemented route-capability support and the documented
  transport-group limit.

## 3. What was implemented

### 3.1 Route-specific typed transformation (action `RC`)

`_transform_route_capabilities` reuses the installed per-group parsers
(the same child laws as ordinary route admission), so the demo law cannot
drift from the product. For a stored capabilities document it:

- Preserves the reviewed non-identifying groups as typed values: the five
  boolean blocks (`chat_completions`, `responses`, `audio_endpoints`,
  `embeddings`, `realtime`), `codex_limits` (ordered positive integers),
  `media_input_estimation`, and `vllm_chat_video`.
- Remaps `codex_compaction_compatible_route_ids` entry-for-entry with the
  SAME per-copy UUID law as every other route id (list order/meaning kept).
- Rewrites `completion_service.profile` to the shared per-copy fictional
  id (see 3.2).
- Remaps the `external_tools.approved_destination_ids` opaque names per
  copy (the `connector|remote_mcp` kind is preserved so the product's
  kind/capability match law stays valid; the operator-chosen opaque part
  is a keyed per-copy digest).
- Fails closed (`CODE_SANITIZE_FAILED`) on the three preserved transport
  groups (`local_coding`, `local_coding_vllm`, `upstream_llm`), on unknown
  groups/flags, on wrong types, on oversized documents (>11 groups or
  >64 KiB), and on recognized secret shapes. The ordinary empty `{}`
  route remains supported.

### 3.2 Shared per-copy completion-profile id

`demo_profile_id(seed, profile_id)` is the single canonical derivation
`demo-profile-<first 24 hex of HMAC-SHA256(seed, "completion-profile|" + id)>`.
Both the 222 route transform and the 223 completion-choices projection use
it under the same job seed, so a copied route references exactly the
fictional choice captured from the same configured profile directory.

### 3.3 Independent 222 verifier re-proof

`_verify_route_capabilities` re-proves the STORED transformed document
using the installed per-group parsers plus the fictional laws: the
completion profile matches the `demo-profile-` shape, and every compaction
route id exists in the copied `model_routes` set (UUID↔str normalized on
both sides). It returns `False` (the copy is refused, never promoted) for
transport-group or unknown-group injection, a non-bool flag, a raw/tampered
profile id, a non-JSON value, or a document carrying BOTH the completion
selector and `vllm_chat_video` (the installed conflict the transformer
refuses).

### 3.4 Combined DB/files completion-link gate (223, before publication)

`run_files_job` runs `_completion_link_gate` after `verify_files` and
before the promotion write. It derives the choice id set from the
VERIFIED stored `profiles/completion-choices.json` leaf (read through the
anchored custody boundary; absent leaf = unconfigured source), performs a
READ-ONLY fetch of the copied `completion_service` profile ids — the
connection uses a fixed finite driver connect timeout, while the session
`statement_timeout` and the fetch itself are bounded by the REMAINING copy
deadline (via `statement_timeout_ms` + `asyncio.wait_for`) — and re-checks
the deadline AFTER the query. The gate fails the copy
(`FILES_VERIFY_FAILED` / `FILES_BUDGET_EXCEEDED`) if any copied completion
profile does not link to a captured choice. The gate is read-only and
finite; it is exercised on
real PostgreSQL in the owned handoff test.

### 3.5 Small correctness fixes

- `run_files_job` now validates the 221 base configuration BEFORE taking
  the custody fence, so a config-validation failure cannot leak the fence.
- The 223 PG web-denial helper no longer swallows its `finally` cleanup in
  an empty `except` (the prior Code Quality inline item).

## 4. Focused verification (method and results)

All runs used the repository `.venv` on the host. No live provider, mail,
browser, or production resource was contacted; no code was modified during
the verification pass.

### 4.1 Unit (host Python; no database)

- `tests/unit/test_demo_snapshot.py` (221 custody/handoff): 33 passed.
- `tests/unit/test_demo_snapshot_sanitize.py` (222 + RC): 66 passed.
- `tests/unit/test_demo_snapshot_files.py` (223 + link gate + fence):
  68 passed.

The RC unit cases prove: empty `{}` is representable; a representative
nested document preserves its booleans/limits and remaps compaction ids,
destinations and the completion profile; per-copy ids differ across seeds
and the original profile id is absent from the transformed output;
unknown groups/flags, wrong types, transport groups and secret-shaped
payloads fail closed; and the independent verifier rejects a tampered
stored document (raw profile restored, transport injection, non-bool flag,
and the completion+video conflict).

### 4.2 Owned PostgreSQL 16 (real owned-PG integration)

Two real `postgres:16` (16.15) loopback containers were used as source and
target, with PostgreSQL 16.15 client binaries placed on `PATH`
(`/tmp/pg16/bin`) so the `pg_dump`/`pg_restore` versions match the owned
servers (a newer host client hits the known 17/18→16 restore harness
mismatch). Source: `slaif222d-src-pg` `127.0.0.1:54351/slaif_gateway_test`.
Target: `slaif222d-tgt-pg` `127.0.0.1:54352/postgres`. Only synthetic
run-tagged canary rows are seeded; cleanup is exact and run-owned (recorded
row IDs, recorded target database, run-tagged roles).

- `tests/integration/test_demo_snapshot_sanitize_postgres.py`: 6 passed
  (`test_full_chain_promotes_sanitized_copy`,
  `test_second_fresh_copy_cannot_reuse_first_mapping`,
  `test_unknown_schema_refused_before_promotion`,
  `test_partial_failure_rolls_back_byte_identical`,
  `test_verifier_refuses_public_connect`,
  `test_cli_and_manifest_contain_no_canaries`). This runs the 222 sanitizer
  (the RC transform + verifier over a real nested capabilities document
  validated by the installed child parsers — child-grammar evidence; the
  seeded route is a direct-SQL fixture carrying a completion selector, not
  a fully route-validated installed candidate) and the
  fail-closed/partial-failure/verifier/CLI paths on real PG.
- `tests/integration/test_demo_snapshot_files_postgres.py`: 1 passed
  (`test_files_chain_handoff_and_privacy`). This runs the full
  221→222→223 chain on real PG and asserts: promotion to
  `DB_AND_FILES_VERIFIED_UNPUBLISHED` (the combined completion-link gate
  passed); the copied completion-service route's stored
  `completion_service.profile` equals
  `demo_profile_id(job_seed, "alpha-profile-223")` and that id is present
  in the captured choices leaf (the DB↔leaf link); the ordinary nested
  route's `codex_compaction_compatible_route_ids` is remapped to its copied
  id; the seeded source row fingerprint is unchanged across the whole
  chain (read-only capture of the seeded DB rows — this proves no source
  DML, not source-file byte invariance, which is a separate 223-a proof);
  the web role is denied (`42501`) before and after the file stage; and
  the original completion-profile stem is absent from every display leaf
  and from the stored completion-profile value (the provider slug is, by
  design, a preserved finite code in the copied DB).

Method distinction: the 4.2 evidence is REAL owned-PostgreSQL (synthetic
data only), separate from the 4.1 mocked/host unit evidence. This is a
host-Python pytest run against owned PG16.15 servers with matching PG16.15
client binaries on PATH — NOT an in-container pytest run, and NOT a real
client/provider/browser run.

Scoped `ruff check` over all six touched code/test files: clean.
`git diff --check`: clean.

## 5. Limitations (honest)

- Preserved transport groups fail closed. A route using `local_coding`,
  `local_coding_vllm` or `upstream_llm` carries configuration secrets or
  operator transport-profile references that cannot be safely projected in
  this stage; such a route FAILS 222 DB sanitization closed. This is the
  documented, bounded limit, not a silent passthrough.
- Capability grammar vs full route law. The 222/223 worker validates the
  capability-DOCUMENT grammar (the installed child parsers) but does NOT
  run the full route-level `validate_merged_route_candidate` law, which
  additionally requires the provider's actual kind to resolve to a
  supported server module and a LOADABLE completion profile whose
  public/upstream models match the route. The owned-PG completion-service
  route is therefore a synthetic module-provider fixture (`kind='module'`,
  `max_retries=0`, no streaming) that proves the fictionalization and the
  DB↔leaf link; it is NOT asserted to be a fully route-validated installed
  candidate.
- No remote TLS / private-network transport. The demo worker connects to
  the target PostgreSQL with `ssl=False`; target DB traffic must remain on
  a trusted private loopback/Compose network. No verified remote TLS is
  claimed.
- Two separate capture times. The 221 DB dump snapshot and the later 223
  per-source file capture are NOT transactionally simultaneous; their times
  are recorded and must be inspected, not treated as one instant.
- Identity-masked usage-pattern limit. Masking is not irreversible
  anonymity: usage quantities, timestamps, costs, quota shapes and
  route/model/provider choices are preserved by design in the display copy.
- No real client/provider/browser. No OpenAI/OpenRouter call, no email, no
  demo browser was run. The demonstration as a whole remains INACCESSIBLE
  until objective 224 (browser binding/login); 224 is still required.

## 6. Negative / privacy / accounting evidence

- Negative: transport-group, unknown-group/flag, wrong-type, oversized and
  secret-shaped documents fail closed in the RC transform; the independent
  verifier rejects a tampered stored document (raw profile restored,
  transport injection, non-bool flag, and the completion+video conflict) so
  a stored copy cannot be promoted on a falsified success flag.
- Privacy: the original completion-profile stem is absent from every
  display leaf AND from the stored completion-profile value in the copied
  DB; per-copy fictional ids differ across copies; the seeded source row
  fingerprint is unchanged across the whole 221→222→223 chain (this proves
  the seeded DB rows were not modified — no source DML — not that source
  file bytes are invariant; the catalog-custody source-file byte proof is a
  separate 223-a result); the demo web role is denied (`42501`) on the raw
  and sanitized copies. PUBLIC CLI/log output is finite safe output (no
  target database name, DSN, password, or private custody reference); the
  VERIFIED display leaves contain typed SANITIZED data — the neutral
  substitutes and, for catalog-backed families, the preserved
  model/provider/route choices — and omit raw credentials, the target
  database name, and private custody references. The PRIVATE 0600 custody
  manifest intentionally retains worker-only custody references (the
  target database name and the original→demo profile-stem map) that the
  demo web role cannot read.
- Accounting: 223-b changed no quota/accounting, provider routing,
  authentication/session, admin GUI, migrations/schema, image/Compose, or
  224 browser work. It is a privacy and installed-functionality repair to
  the demo DB/files masking path only.

## 7. Topology

- Implementation head: `b53fa881f2da9cc6dccffb9719dc8c0e8e2a6e1e`
  (sole parent: `fc8844ad887f0bb12b99e1951710a7f058b9109d`, the 223-b
  activation-byte commit, whose sole parent is the 223-a report-only SELF
  `0e497fbe7e6970044397bd075ebf3e2d5c7f0d40`).
- This report is published as a report-only SELF commit whose sole parent
  is the implementation head `b53fa881` and whose sole diff is this file
  `oap/reports/223-b-route-capability-snapshot.md`.
