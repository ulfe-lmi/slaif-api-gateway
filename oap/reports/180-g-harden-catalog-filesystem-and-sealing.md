# OAP Immutable Report — 180-g: harden catalog filesystem and sealing

PR mode: AMEND_EXISTING_PR on PR #317 (branch
`oap/180-catalog-refresh-bundle-review`, base `main`).

## Identity

- Starting SHA (committed PR head when this order started):
  `4267ae1f6c5bfa907d05c53a320575a1a45c3fd1`
- Activation commit (order file + `oap/active` pointer; strategic bytes
  unchanged since): `f9ce74320b2c066f1921784de114910c85851263`
- Implementation head SHA:
  `07a75f96437e8059d8c8f92d9015e9eb23893641`
- Report publication commit: SELF
- PR #317 remains OPEN. Never merged, auto-merge not enabled, no tag, no
  release. The only published release remains `v0.1.0-rc.1`. No
  production-certification claim follows. Objective 180 is NOT complete.

## Changed paths (implementation head vs starting SHA)

Protocol commit `f9ce74320b2c066f1921784de114910c85851263` (activation only):

- `oap/orders/180-g-harden-catalog-filesystem-and-sealing.md` (new order,
  unchanged since activation)
- `oap/active` (exact strategic bytes `180-g`)

Implementation commit
`07a75f96437e8059d8c8f92d9015e9eb23893641` (all within the order's exact
allowed paths; no other path touched):

- `app/slaif_gateway/services/catalog_refresh/filesystem.py` (NEW) — shared
  bounded descriptor/publication primitives: anchored component walks with
  held directory descriptors and no-follow opens; lifecycle binding handles
  (`AnchoredDir`) with hop-by-hop name-to-inode re-assertion;
  mutation-namespace permission enforcement; bounded regular-file reads with
  pre-read size/EOF/post-read identity proof; strict JSON with constant safe
  errors; exact-0600 key loader and race-safe key publication;
  `renameat2(RENAME_NOREPLACE)` NEW-ONLY directory/file publication
  (Linux-only, fail closed, no check-then-replace fallback); identity-checked
  failure cleanup.
- `app/slaif_gateway/services/catalog_refresh/sealing.py` — `seal_run` now
  reads the manifest and reconciles the exact declared file set, counts,
  per-file caps (bundle 8 MiB at its file read), and the aggregate 128 MiB
  bound (including manifest/receipt overhead) BEFORE any content read;
  captures each content file exactly once through the held run descriptor
  (bundle reread eliminated); reconciles per-file size + digest against the
  captured bytes before signing; `verify_run` holds a single anchor for all
  reads, enforces declared bounds before reading, enforces the exact
  first-install marker byte-equality gate, and re-exports the shared
  constants/key loader. All legacy check keys preserved.
- `app/slaif_gateway/services/catalog_refresh/errors.py` —
  `safe_schema_error_text`: bounded Pydantic error rendering that drops
  string location parts (keeps integer indices) and replaces
  value-bearing custom messages with fixed text; constant message bounds
  (300 chars per message, 4000 total).
- `app/slaif_gateway/services/catalog_refresh/bundle.py` — strict parse
  (duplicate-key and non-finite hooks with constant messages); JSON/schema
  errors rendered via the safe renderer; no schema, renderer, or projection
  semantics change.
- `app/slaif_gateway/services/catalog_refresh/baseline.py` — same strict
  parse and safe error handling; NO SQL/export/projection semantics change.
- `app/slaif_gateway/cli/catalog_refresh.py` — review/verify/export routed
  through the shared boundary: check-phase anchored handles with no
  creation, key-containment proof by `(dev, ino)` chain (lexical
  `is_relative_to` only as fallback when both chains exist),
  lifecycle-binding gates before key load and every publication,
  `ensure_seal_key` anchored to the held key-parent descriptor,
  `mkdir_private_child` staging, seal-before-publish, `publish_new_only_*`
  publication, identity-checked cleanup; `export-baseline` output published
  with the same NEW-ONLY primitive and all failure modes mapped to safe
  typed CLI errors (exit 65).
- `tests/unit/test_catalog_refresh_filesystem.py` (NEW) — 38 adversarial
  tests exercising the actual open/publish/read/mutate seams with explicit
  barriers (delegating wrappers at `_open_anchored`, `_open_component`,
  `anchored_read_fd`, `_renameat2_noreplace`, `os_read`), synthetic fake
  keys only, and pytest `tmp_path` resources.
- `docs/catalog-refresh.md` — new "Filesystem trust contract" subsection
  (descriptor anchoring, lifecycle binding, namespace enforcement, bounds
  before allocation, strict JSON, exact key contract, atomic NEW-ONLY
  publication, capture-once, honest platform/threat limits); exit-code
  table rows made precise; platform limit row.
- `docs/cli-reference.md` — catalog-refresh filesystem safety paragraph and
  link to the trust-contract section.
- `admin/catalog-refresh/README.md` — operator notes for the sealed
  filesystem boundary (key file contract, directory ownership, atomic
  new-only output, Linux assumption).

`app/slaif_gateway/services/catalog_refresh/__init__.py` required no export
change (all consumers import from the concrete modules); the existing
test files passed unmodified.

## Before: independently verified reproducible failures (4267ae1)

Strategic artifact
`review-artifacts/180-f-draft/filesystem-precontinuation-probes.json`
(sealing.py SHA256
`b8c7f9d3179a12b13b961c6987947b8ceaba896cde899b87c59e0cb53b04fc43`,
cli/catalog_refresh.py SHA256
`a0a6d94e4850d5b4d3b2b91700a65f8d8cb92726adc695c6210336a3bcad12d6`):

1. `parent_swap_reads_outside: true` — the parent replaced with a
   symlink immediately before `os.open` redirected the read to the outside
   target; ancestors of `run_dir` were not protected by a descriptor walk.
2. `verify_accepts_public_key_file: true` and
   `verify_accepts_symlink_key: true` — a mode-0644 key and a symlinked
   key were accepted by the verify path.
3. `publication_replaced_concurrent_directory: true` — the exists-check +
   `os.replace` pattern overwrote an empty directory created concurrently.
4. `fifo_read: hung before regular-file check; isolated child killed
   after 4s` — a FIFO leaf blocked `os.open` before any regular-file
   check.
5. Bundle/baseline bytes were read before parser caps and aggregate
   run bounds were checked only after accumulation (oversize allocation
   before refusal).

## G1 — Descriptor-anchored paths and bounded regular-file reads (closed)

- Every catalog-refresh input, key, run-content, manifest/receipt, and
  output path now passes through the shared boundary: components are
  walked one hop at a time through held directory descriptors with
  no-follow opens (`O_NOFOLLOW|O_NONBLOCK` leaves), and nothing is
  reopened by full path after a check. Symlinked leaf, intermediate
  parent, AND ancestor are refused; traversal/absolute/empty/dot/alias
  names and depth (4) escapes are refused before any open.
- Leaves are fstat-checked (regular type + size) on the opened
  descriptor BEFORE any read; the bounded reader reads exactly the
  snapshot size, probes for EOF (growing file), and re-proves
  identity + size after the read (short/growing/same-size-mutation
  reads are refused). Special files (FIFO/socket/device) fail promptly
  at open with safe typed errors.
- Bundle (8 MiB) and baseline (32 MiB) bounds are enforced before
  content is read or allocated; sealed runs enforce per-file 32 MiB,
  manifest 1 MiB, receipt 8 KiB, aggregate 128 MiB including
  manifest/receipt overhead, 64 files, depth 4, and the declared
  manifest set/count/size is reconciled before any content is read.
- Strict JSON (duplicate keys, non-finite constants, malformed input,
  deep nesting) for bundle, baseline, manifest, receipt, and the
  first-install marker; first-install verification now requires the
  EXACT canonical empty marker bytes, not any object carrying the
  expected `schema_version`. Errors render as constant, bounded text —
  never echoing input bytes or private field values.

Tests (new file, all passing): symlinked ancestor/parent/leaf refusal;
name traversal and shape refusal; FIFO leaf prompt refusal (<2s in-unit,
and a hard 15s subprocess timeout for the CLI — exit 65, no hang);
sparse-oversize refusal before any read (interposed `os_read` seam);
short-read and growing-file refusal; deep-JSON refusal; duplicate-key
and schema-error canary non-echo at loader, CLI-output, and minimal
blocked-run artifact level.

## G2 — One secure key loader and anchored key publication (closed)

- Review and verify share one loader: type/owner/mode/length/hex are
  validated on the OPENED descriptor — mode EXACT `0600` (`0400` and
  `0700` both fail), owner uid match, exactly 64 lowercase ASCII hex
  bytes, complete-file EOF proof (a valid prefix of a longer key is
  refused), no symlink parents or leaf. A key that grows while read is
  refused. No key bytes or raw inputs appear in any error, log, or
  report (safe constant messages).
- Verify never creates, repairs, chmods, rotates, or re-signs; a
  missing key is left missing. Key containment outside the run tree is
  proven by `(dev, ino)` chain identity of the held descriptors
  (lexical containment only as a documented fallback), so a post-check
  race cannot place the key inside the published run.
- Initial creation is anchored: private 0700 parent, `O_EXCL` 0600 temp,
  fsync, atomic `renameat2(RENAME_NOREPLACE)` publication; the loser
  unlinks its own temp and re-loads the complete winner through the same
  held descriptor. Invalid existing keys are never replaced.

Before/after for the strategic cross-phase reproducer
(`key-containment-reopen.json` at CLI
`a34c5da6cc9dd9deba5e49f98df57299d3e4ed5c7cf300cc98d4771229521ed7`,
filesystem `8f1776677794977362d6e8d272572832c435522c57b6e8aa74aa5eae726bb807`,
sealing `f6c3b87e2129e8328e0d6ff3a93bf4844c22cda12c20969a38aab4934a6c8127`;
recheck `key-containment-reopen-recheck.json` at CLI
`3929c966c4094ce5ec8497a8ea0c0c086cef486d10b9f3c30a3aa9a02fb6a795`,
sealing `a03fe898eeb5ca2b64a671e24cd1c4999ecd53c2aaab92d4036595a6ce037529`):
the real-`ensure_seal_key`-then-directory-swap reproducer previously exited
0 READY with `seal.key` inside the actual run-root tree; the current
implementation exits 65 ("checked path binding changed; refusing to
publish"), publishes nothing, and the original run root stays empty
(`lifecycle-correction.json`: PASS — swap → 65 with zero reports and no
READY; ordinary review READY + verify 0; 0777 output-parent refusal with
mode preserved). Re-produced in this round at the actual seams by
`test_cross_phase_directory_swap_voids_run` (swap after key load) and
`test_swap_between_check_and_key_gate_voids_run` (swap between the
check phase and the key gate): both exit 65, no run under the swapped
name, original run root untouched, no READY.

Key tests: exact mode/owner/hex/complete-file on the opened FD (0400,
0700, 0644, symlinked, non-hex, short, whitespace/case variants all
refused); growth during read; winner/loser at the `_renameat2_noreplace`
seam (one complete private winner, loser reuses it); verify on a missing
key leaves it missing.

## G3 — Atomic publication without clobber under races (closed)

- Normal sealed runs and minimal BLOCKED runs are staged in a private
  0700 directory, completed and fsynced, sealed, then published with one
  atomic `renameat2(RENAME_NOREPLACE)` directory operation through the
  held parent descriptor (Linux kernel 3.13+, glibc 2.28+; the wrapper
  fails closed when unavailable — there is no check-then-replace
  fallback and no `os.replace` on final names).
- `publish_new_only_directory` re-asserts the staging
  name-to-`(dev, ino)` identity through the held parent at the syscall
  seam (closes the `publication-cleanup-window.json` window: a foreign
  directory swapped onto the staging name immediately before rename is
  NOT published — `test_publish_refuses_replaced_staging`); the
  containing directory is fsynced after publication.
- Pre-existing targets of every type — empty directory, non-empty
  directory, regular file, symlink, and concurrently created
  destinations — remain byte- and inode-identical and the command exits
  65 ("run directory already exists; refusing to overwrite"). Concurrent
  same-run publishers are barriered at the actual rename seam: exactly
  one wins, the other gets a safe conflict (`test_concurrent_publishers_single_winner`).
- `export-baseline` output is published with the same NEW-ONLY file
  primitive; pre-existing file/empty directory/symlink targets are left
  untouched (exit 65, "refusing to overwrite existing output"). Note:
  the initial wiring of this path raised the conflict `CliError`
  outside the CLI's error-mapping block (surfacing as an unhandled
  exception, exit 1); it is now mapped to exit 65 with the same safe
  message, covered by `test_export_baseline_atomic_new_only`.
- Failure cleanup is identity-checked: `cleanup_staged_directory`
  re-asserts the staging identity before `rmdir` (a replaced staging
  directory is silently refused, never removed —
  `test_cleanup_refuses_replaced_staging`) and refusal never masks the
  original error.
- Mutation-namespace enforcement: the run root and key parent must be
  operator-owned and not group/other-writable, fstat-verified on the
  held descriptor; unsafe supplied parents fail closed (exit 65, "must
  not be writable by group or other") and are NEVER chmod'ed or repaired
  (mode preserved). This closes the 0777-mutation-parent acceptance from
  `publication-cleanup-window.json` without assuming peer-writable
  parents are private.

Tests: pre-existing run-target types (exit 65 + byte/inode identity);
sequential double publish (second → conflict); concurrent publishers
(barriered, single winner); replaced-staging refusal at both the rename
and cleanup seams; 0777 run root and 0777 key parent refusal with mode
preserved and nothing created.

## G4 — Authenticate and replay the exact captured bytes (closed)

- `seal_run` captures each run content file exactly ONCE through the
  held run descriptor, reconciles the manifest's declared set/size/hash
  against those captured bytes BEFORE signing, and uses the same bytes
  for canonical bundle identity, semantic validation, run identity, and
  the report. The old bundle reread is eliminated;
  `test_seal_capture_once_per_file` proves per-file count == 1 for all
  content files, manifest == 1, receipt read-back == 0.
- Declared bounds are enforced against the manifest before any content
  read: 65 declared entries → "bounds"; aggregate 133 MiB (6 x 21 MiB +
  7 MiB bundle) → "bounds"; 9 MiB declared bundle (> 8 MiB cap) →
  "bounds" — all without allocating the claimed bytes
  (`test_manifest_declared_bounds_checked_before_reading`).
- First-install byte-equality gate: even a forger HOLDING the key who
  recomputes every digest, the manifest, and the HMAC still fails
  verification at `first_install` because the marker document no longer
  byte-equals the canonical empty marker
  (`test_first_install_forged_marker_fails`).
- Verification is read-only, authenticates the exact captured bytes with
  the external key, recomputes deterministic correspondence, and never
  trusts ordinary digests alone. All legacy wrong-key, coordinated-tamper,
  malformed, and replay negatives (tampering each of the 7 content
  files, manifest, receipt; wrong key; missing key) remain green in the
  unmodified `test_catalog_refresh_seal.py`. A valid sealed BLOCKED run
  verifies authentic with state BLOCKED; that is not permission to
  apply it.

## Strategic review rounds (same order; all findings addressed)

1. Draft review (`workorders/180-g-draft-review-feedback.md`): no
   `os.openat` in CPython → native `os.open/mkdir/unlink/rmdir(...,
   dir_fd=)` with only `renameat2` via ctypes; descriptor ownership
   (double-close of borrowed FDs); EOF/growth/post-read identity and
   EXACT-0600 (0400/0700 fail); complete-file key proof; held
   parent/staging/inode lineage across create/write/seal/publish/cleanup
   (no unanchored pre-walk mkdir); pre-sign manifest reconciliation with
   incremental remaining budget and the 8 MiB bundle cap at its file
   read; JSON duplicate-key canary echo. Artifacts:
   `initial-primitives.json` (filesystem
   `8abb7cbcc4db2ace42421e9eae8460f8bc808d86145b61ae284d99ceca82d89f`),
   `initial-json-error-canaries.json`. All fixed.
2. Integration race review
   (`workorders/180-g-integration-race-feedback.md`): the discarded-handle
   key-containment reopen (cross-phase swap → READY with the key inside
   the run tree) and the pre-rename/pre-rmdir source-identity windows
   (0777 mutation parent accepted). Fixed with lifecycle `AnchoredDir`
   handles, hop-by-hop `assert_name_binding` gates at key load and every
   publication, mutation-namespace enforcement, and identity re-checks
   at the actual syscall seams. Artifacts:
   `key-containment-reopen.json`, `key-containment-reopen-recheck.json`,
   `publication-cleanup-window.json`, `lifecycle-correction.json`
   (PASS). All re-verified in this round's barriered tests.
3. Cleanup/privacy review
   (`workorders/180-g-cleanup-privacy-feedback.md`), artifact
   `fd-and-extra-field-probes.json` (filesystem
   `629d00c873ccf1539b47ccabd534ae078def24f482ae37e01270f662b875502d`,
   bundle `9253426fcb4a91b0c9bd530996e92528c229c2d0dd156703e1933ec630175f4d`,
   baseline `62b0d74e6f530eebe4028f8705a3bc7375792161f9677c11a8fd7237f086dd77`):
   (a) `open_anchored_directory` leaked its retained parent FD
   (12 cycles → +12 fds) — the caller now owns only the returned fd,
   every other owned descriptor is closed exactly once (leak == 0);
   (b) `AnchoredDir.close` double-closed overlapping tuples and could
   kill a concurrently reused unrelated FD — closes are deduplicated and
   identity-checked (fstat must match the opened object; ownership is
   consumed, EBADF/mismatch leaves the number alone); rejection paths in
   key creation and publication clean up their own fds;
   (c) Pydantic error locations echoed unknown extra-field canaries —
   `safe_schema_error_text` drops string location parts, keeps integer
   indices, and replaces value-bearing messages with fixed bounded text;
   used by both loaders and asserted at the CLI/report/blocked-run
   artifact level. All three re-verified by probes
   (`fd-and-extra-field-correction.json`, `lifecycle-correction.json`).

## Acceptance results (AP-G1 .. AP-G7)

- AP-G1 (parent/ancestor/leaf swaps at actual open barriers): PASS —
  swap at the `_open_anchored` seam after the walk holds the real
  directory: verification authenticates the ORIGINAL held bytes or
  safely rejects; it never reads the outside bytes
  (`test_verify_after_parent_swap_uses_held_bytes`); symlinked-ancestor
  run dir → safe rejection `run_dir: missing`
  (`test_ancestor_symlink_run_dir_safe_rejects`); cross-phase directory
  swaps void the run at every gate (G2/G3 tests above).
- AP-G2 (insecure/symlink/swapped keys rejected; verify never creates;
  one complete private winner): PASS — exact-mode/owner/hex/complete-file
  enforcement on the opened FD; winner/loser at the rename seam; missing
  key left missing (G2 tests above).
- AP-G3 (prompt special-file refusal under hard timeout; bounds before
  accumulation; safe malformed/deep JSON): PASS — FIFO under a 15s
  subprocess hard timeout exits 65 without blocking; sparse-oversize
  refused before any read; aggregate/count/per-file caps enforced
  against the declaration before reads; strict JSON safe
  (G1/G4 tests above).
- AP-G4 (concurrent destination creation never overwritten for READY,
  BLOCKED, or exported-baseline output; seam-level concurrent
  publishers; interrupted/failing writes and cleanup): PASS —
  barriered concurrent publishers at the rename seam; pre-existing
  targets of all types untouched; identity-checked cleanup refuses a
  replaced staging directory (G3 tests above).
- AP-G5 (signer/verifier consume the same captured bytes;
  replacement/tamper at read/hash/recompute barriers cannot
  authenticate a different proposal; positive replay preserved): PASS —
  capture-once counting at the real read seam; declared-bounds
  before-read; forged-marker-with-key failure; unmodified seal suite's
  tamper/wrong-key/replay negatives green (G4 tests above).
- AP-G6 (valid READY/READY_WITH_WARNINGS/sealed BLOCKED/unsealed error
  paths with honest exit/status; semantics unchanged): PASS — ordinary
  fixture review exits 0 READY and verifies (digests/hmac/correspondence
  ok); F1–F4 behaviors and all prior source/privacy negative cases
  remain passing (253 pre-existing focused tests, unmodified).
- AP-G7 (focused tests, changed-Python lint, documentation checker,
  internal links, git diff --check, CI green): PASS locally (below) and
  by the PR #317 final-head checks (CI section).

## Local verification and actual collection counts

All commands run from the repository root in the current venv; actual
process exit codes captured (not pipeline status):

- Pre-fix focused run of the broken initial draft (seal + CLI +
  bundle/baseline files, before the strategic corrections landed):
  **29 failed, 3 passed, 24 errors** in 14.36s, **EXIT=1** (log kept at
  `/tmp/obj180g-before-seal-cli.log`). After each strategic correction
  round the 8-file suite returned to green.
- Focused 9-file unit suite (the 8-file catalog-refresh set
  `test_catalog_refresh_baseline`, `test_catalog_refresh_bundle`,
  `test_catalog_refresh_policy`, `test_catalog_refresh_report`,
  `test_catalog_refresh_seal`, `test_catalog_refresh_source_evidence`,
  `test_cli_catalog_refresh`, `test_documentation_contract_drift`, plus
  the new `test_catalog_refresh_filesystem`): **291 passed** in 33.79s,
  **EXIT=0** (253 pre-existing + 38 new).
- OAP governance suite (`tests/unit/test_oap_governance.py`):
  **8 passed**, **EXIT=0**.
- `ruff check` on all 7 changed/new Python files: **All checks
  passed**.
- `python3 scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK
  files=91`, **EXIT=0**.
- `git diff --check 4267ae1f6c5bfa907d05c53a320575a1a45c3fd1
  07a75f96437e8059d8c8f92d9015e9eb23893641`: clean.
- No database, Redis, provider, Docker, or full local/HPC matrix was run
  this round (the order explicitly scopes out all of them; no disposable
  PostgreSQL was started). The post-#220 128-worker HPC qualification
  remains **NOT RUN**. Skips are not passes.

## CI (PR #317 final head)

At implementation head
`07a75f96437e8059d8c8f92d9015e9eb23893641`, all ten final-head checks are
`completed`/`success` (verified via the commit check-runs API):
Analyze (javascript-typescript), Analyze (python), Analyze Python, CodeQL,
Docker Compose smoke, Documentation hygiene, OpenAI-compatible E2E tests,
Playwright browser smoke, PostgreSQL integration tests, and Unit, lint,
and migration head. The new adversarial suite is CI-safe (no database,
Redis, provider, Docker, or network dependency; the FIFO subprocess test
uses the repository's own interpreter against a `tmp_path` FIFO under a
hard 15s timeout). The report-only SELF commit adds one markdown file
under `oap/reports/` and its report-head checks are verified green
before the protocol OK is sent (see Status).

## Privacy and no-mutation proof

- No shared 5432 instance, its configuration or logs, the privileged
  `postgres` identity, protected credentials, or any live collector was
  accessed in this round; no disposable PostgreSQL was started (verified
  before cleanup: no task-owned process or 5433 listener exists; the
  only PostgreSQL/Redis processes present are the pre-existing shared
  ones, untouched).
- All tests use pytest `tmp_path` resources and synthetic fake keys;
  canaries prove privacy at every failure surface: an unknown
  `SYNTHETIC_PRIVATE_FIELD_CANARY_180G` field and a duplicate-key canary
  never appear in loader errors, CLI output, or minimal blocked-run
  artifacts; no key bytes or raw inputs appear in any safe error.
- No application metadata mutation, no `.env` reads, no secret exposure,
  no production import, no real upstream calls, no email.
- `oap/orders/180-g-*.md` and `oap/active` bytes are unchanged since the
  activation commit (protocol bytes only); no other `oap/` path touched.
- No repository path outside the order's exact allowed list was
  modified in the implementation commit.

## Resource identity and cleanup

- No task-owned PostgreSQL or Redis resources were created this round
  (none needed by the order); nothing was left behind.
- Task artifacts in `/tmp` (`obj180g*` logs/probes) are removed as part
  of this round's cleanup after the report commit.
- No global prune/reset/cleanup performed; unrelated worktrees,
  `.local-provider-catalog/`, the root `AGENTS.md`, and the permanent
  `message.txt` are untouched.

## Corrections to the 180-f report (this report only; the 180-f
report is immutable and unchanged)

1. The 180-f report's blanket "no shared-5432 access attempted" claim
   conflicts with its own skip explanation. Precisely: the PRE-EXISTING
   `test_backup_restore_postgres` test spawned a `pg_dump` subprocess
   that dialed the shared default socket `5432` (it received the full
   URL as a database name; the connection was instantly rejected with
   `FATAL: database "..." does not exist`). No data was accessed, no
   mutation occurred, and no privileged identity was used. AGENT-MADE
   diagnostic access to the shared cluster, its configuration, or logs:
   none. This distinction is recorded here; the 180-f text is not
   amended.
2. The 180-f "synthetic confirmed imports" were TEST imports into
   task-owned disposable PostgreSQL databases (created, used, and
   dropped by the test flow), not production or staging imports.
   Precise language used here: test imports into task-owned disposable
   databases.

## Still REQUIRED for a later same-PR correction (not implemented here)

- First-screen/expanded/print layout of `REVIEW.html` (renderer version
  stays 180.4; this round changed no layout/rendering bytes) remains a
  REQUIRED later same-PR correction per the order.
- Objective 180 as a whole is NOT complete: live source retrieval,
  isolated Codex research, atomic historical price/FX supersession, and
  the final one-report workflow wrappers remain later numeric
  objectives; the administrator workflow is incomplete. Do not reduce
  the product to offline review; 181 is NOT pre-activated.
- No perfect-security or security-certified claim follows; the
  documented threat scope is local HMAC integrity against unprivileged
  local peers on Linux, not protection from a key-controlling
  administrator, root, or same-uid full-authority code.

## Status

Objective 180 remains OPEN and NOT complete. PR #317 is OPEN at the
report commit; all required final-head checks recorded above. The
coding agent never merges; awaiting the next strategic order (a same-PR
suffix may follow without resolving the numeric objective first).
