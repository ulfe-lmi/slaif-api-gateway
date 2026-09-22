# OAP Work Order — 180-g

PR mode: AMEND_EXISTING_PR

## Objective and business reason

Make the offline catalog review's filesystem and sealing boundary match its
published guarantees. A trustworthy one-report workflow must read bounded,
authenticated bytes from the intended files, protect its external seal key,
and publish complete new runs without overwriting another run under races.
Close the concrete current-head defects below on the SAME PR #317.

The full human mandate remains one refresh command -> one REVIEW.html -> one
explicitly confirmed, audited apply command. This round is a bounded correction
to the offline foundation, not completion of Objective 180 or that workflow.
Live retrieval, isolated Codex research, atomic historical price/FX supersession
and final wrappers remain later numeric objectives after 180 is accepted and
resolved. First-screen/expanded/print layout remains a REQUIRED later same-PR
correction. Do not reduce the product to offline review or pre-activate 181.

## Verified state and reconciliation

Independently verified from GitHub, immutable transcript and FIFO on 2026-09-22:

- Repository: ulfe-lmi/slaif-api-gateway. Main:
  b1e6ef0a49d7e5ab6376f6344290f58ff844e671.
- Unique open PR #317, base main, branch
  oap/180-catalog-refresh-bundle-review, MERGEABLE/CLEAN.
- Starting PR/report head: 4267ae1f6c5bfa907d05c53a320575a1a45c3fd1.
- Report publication changes only
  oap/reports/180-f-close-catalog-roundtrip-and-comparison-gaps.md;
  first parent / implementation head:
  244d1019df348c4e20192ab28187a105cc6f67fb.
- All ten report-head checks PASS. Strategy independently accepted 253 focused
  unit tests with exact implementation identities and 21 PostgreSQL tests on
  244d101, with its own database dropped and cleanup verified.
- F1–F4 bounded fixes accepted: exact read-only parser consumer allowlist,
  conservative nested capability/create/export/no-op round trip, declared-source
  FX numeric/context comparison, exact configurable thresholds. Preserve them.
- Sole helper37141 returned RESPONSE_OK_EXACT and exit0; it is CLOSED. No
  duplicate reader or resend. Prior active180-f and clean shared worktree.
- Main ruleset23580289 protects deletion/non-fast-forward. Only published
  release v0.1.0-rc.1. No new tag/release/production authority.

The prior report explicitly carries this filesystem work. Preserve all prior
orders/reports unchanged. Its blanket no-shared5432-attempt claim conflicts with
its own skip explanation describing pg_dump's default-socket attempt. No
successful shared access/mutation is established. Correct this distinction in
the NEW report, not history. Synthetic confirmed imports in F were test imports;
use precise language rather than a blanket "no real import" claim. Awaiting a
new strategic order does not require PR resolution before a same-PR suffix.

## Exact allowed paths

- app/slaif_gateway/services/catalog_refresh/sealing.py
- app/slaif_gateway/services/catalog_refresh/filesystem.py (new shared bounded
  descriptor/publication primitives, if useful; no generic repository rewrite)
- app/slaif_gateway/services/catalog_refresh/errors.py (safe typed I/O failures)
- app/slaif_gateway/services/catalog_refresh/__init__.py (necessary exports only)
- app/slaif_gateway/services/catalog_refresh/bundle.py (bounded/strict parse and
  safe error handling only; preserve schema, renderer and projection semantics)
- app/slaif_gateway/services/catalog_refresh/baseline.py (bounded/strict parse and
  safe error handling only; NO SQL/export/projection semantics change)
- app/slaif_gateway/cli/catalog_refresh.py
- tests/unit/test_catalog_refresh_seal.py
- tests/unit/test_catalog_refresh_filesystem.py (new if useful)
- tests/unit/test_cli_catalog_refresh.py
- tests/unit/test_catalog_refresh_bundle.py (input/error regressions only)
- tests/unit/test_catalog_refresh_baseline.py (input/error regressions only)
- tests/fixtures/catalog_refresh/filesystem/ (new synthetic small fixtures only;
  prefer generated tmp_path fixtures; no keys, giant files or screenshots)
- docs/catalog-refresh.md (filesystem/trust/error/limits contract only)
- docs/cli-reference.md (affected catalog-refresh commands only)
- admin/catalog-refresh/README.md (affected filesystem/operator instructions only)
- oap/orders/180-g-harden-catalog-filesystem-and-sealing.md (unchanged)
- oap/active (exact unchanged strategic bytes180-g)
- oap/reports/180-g-harden-catalog-filesystem-and-sealing.md (new immutable report)

No other paths. Runtime APIs/providers/accounting/quota, imports, migrations,
dependencies, deployment, workflows, architecture allowlists, production scripts,
source parser/capability/financial policy, report layout and historical records
are outside scope. No live collectors, researcher, refresh/apply wrappers or
pricing supersession here. Reuse existing semantics; do not weaken tests to fit.

## Current-head reproducible failures

Strategic artifact (read-only, outside repository):
/home/ubuntu/codex-supervision/slaif-api-gateway/review-artifacts/180-f-draft/filesystem-precontinuation-probes.json

On head4267ae1 with sealing.py SHA256
b8c7f9d3179a12b13b961c6987947b8ceaba896cde899b87c59e0cb53b04fc43
and cli/catalog_refresh.py SHA256
a0a6d94e4850d5b4d3b2b91700a65f8d8cb92726adc695c6210336a3bcad12d6:

1. _safe_read checks parent paths lexically, then opens the full path with
   O_NOFOLLOW (leaf only). Swap the parent for a symlink immediately before
   os.open: it reads bytes from the outside target. Ancestors of run_dir are
   also not protected by a descriptor walk.
2. CLI _read_existing_seal_key accepts a symlink key and a mode0644 fake key.
   The service reader checks mode before opening rather than on the opened FD.
3. A FIFO leaf blocks os.open before the later regular-file fstat check;
   an isolated reproducer child had to be killed after four seconds.
4. _publish_blocked_run's exists check + os.replace overwrites an empty directory
   created concurrently at the destination. Normal review uses the same pattern.
5. CLI bundle/baseline read_bytes happens before parser caps. verify_run checks
   aggregate bytes/file count after reading/accumulating entries. seal_run reads
   the bundle once for file hash and again for semantic/identity values.

Static symlink tests are not sufficient to close these race findings.

## G1 — Descriptor-anchored paths and bounded regular-file reads

Create/reuse a small shared filesystem boundary for ALL catalog-refresh input,
key, run-content, manifest/receipt and output paths. Walk path components using
held directory descriptors and no-follow opens (including ancestors), and open
leaves relative to the verified parent descriptor. Reject symlink, traversal,
absolute manifest names, empty/dot/alias components and unrecognized run paths.
Never rely on resolve/lstat/islink followed by a full-path open as the security
boundary. A parent replaced with a symlink must not redirect a later operation.

Open leaves without blocking on FIFOs (e.g. O_NONBLOCK with O_NOFOLLOW), verify
regular type/size on the opened descriptor BEFORE reading, then use a bounded
reader. Refuse sockets/devices/directories and unsupported filesystem conditions
with safe typed errors. Avoid reading device content. Reject short/growing or
changed reads, or otherwise prove that all validation/authentication consumes a
single immutable captured byte snapshot; do not reopen by path after checking.
Handle same-size mutation and replacement at the relevant seams explicitly.

Enforce bundle8MiB and baseline32MiB input bounds BEFORE allocating their content.
Enforce small documented manifest/receipt limits, the exact expected content-file
set, per-file bounds and aggregate128MiB bound before/incrementally during reads,
including manifest/receipt overhead. Check declared sizes/counts/shapes before
iterating content. Unknown extra entries, duplicate names, path aliases and
receipt/manifest set disagreements fail closed. No multi-gigabyte read just to
find it exceeds a cap. Preserve legitimate large bounded baseline support.

Strict JSON handling must reject duplicate keys/nonfinite/malformed/deep inputs
without unhandled RecursionError, tracebacks or echoed private input. Cover
bundle, baseline, receipt, manifest and the explicit first-install marker.
First-install verification must match the intended canonical empty marker,
not merely accept any JSON object carrying one expected schema_version value.
Do not change accepted business data or baseline SQL semantics.

## G2 — One secure key loader and anchored key publication

Review and verify must use the same secure EXISTING-key loader; verify never
creates, repairs, chmods, rotates or re-signs anything. Validate actual opened
FD type, current runner ownership and exact private0600 mode, length64 lowercase
ASCII hex, bounded read, and no symlink parents/leaves. Reject permissive,
malformed, whitespace/case variants and key path swaps. No key bytes/raw inputs
in errors, logs, reports or artifacts. Keep the key outside the run tree and
out of all bundles/research authority; a lexical containment check alone must
not permit a race to place the key in the published run.

Preserve race-safe initialization: complete a private0600 temporary key, fsync,
atomically publish without replacing an existing name, validate and reuse the
complete winner for concurrent initializers, or fail safely. Invalid existing
keys are never silently replaced. Anchor creation, link, fsync and cleanup to
verified descriptors. Test winner/loser and permission/path replacement races,
not only sequential reuse. Verification of a missing key must leave it missing.

Threat scope remains local HMAC integrity, not protection from an administrator
who controls the key or arbitrary privileged interference. Document supported
platform/permission assumptions honestly; do not claim generic OS support.

## G3 — Atomic publication without clobber under races

Publish normal sealed runs and minimal BLOCKED runs from private staging using
an actual atomic NO-REPLACE directory operation. A separate exists check plus
os.replace is not acceptable. Existing empty/nonempty directories, files,
symlinks and concurrently created destinations must remain byte/inode-identical.
Only one of concurrent same-run publishers wins. Baseline export promises
new-only output and must also enforce that atomically at the actual write.

Use descriptor-anchored writes, staging and cleanup, complete/fsync every file,
seal before publication, then fsync the containing directory. Ensure temporary
resources are private and failure cleanup cannot follow a replaced path or
remove another process's files. No partial final run or READY output on failure.
Safe errors should distinguish unsupported publication primitive from success.

A narrow Linux renameat2(RENAME_NOREPLACE) wrapper via stdlib/ctypes is acceptable
if needed; fail closed when unavailable, never fall back to check-then-replace.
No new dependency, broad platform abstraction or runtime/deployment change.
Document actual Linux requirements. Existing private staging content writes may
use replacement only where ownership/anchoring proves no unrelated target can
be clobbered; final published names always require atomic new-only behavior.

## G4 — Authenticate and replay the exact captured bytes

Capture each run content file once through held descriptors. Use those SAME bytes
for manifest/receipt hashes, canonical bundle identity, run identity, semantic
validation, generated import artifacts and HTML correspondence. Eliminate
seal_run's bundle reread. Strictly reconcile manifest claims with captured files
before signing. Never sign inconsistent manifest/content or partial output.

Verification stays read-only, authenticates exact bytes with the external key,
recomputes deterministic correspondence, and never trusts ordinary digests alone.
Retain wrong-key, coordinated-tamper, malformed and replay negatives. If exposing
an internal verified snapshot to future apply, it must contain the authenticated
immutable bytes/typed identity, not a later instruction to reread paths. Do not
implement apply or claim filesystem permissions make reviewed files immutable.
Mutation after review is detected by verification; future apply must consume the
verified snapshot. No circular report/receipt self-hash scheme.

A valid sealed BLOCKED proposal may still verify as authentic with stateBLOCKED;
that is NOT permission to apply it. An unsealed minimal error report remains
clearly unsealed and cannot verify. Preserve SQL provenance: verify executes no
SQL; document-mode review does not claim current live SQL; actual live export
stays a read-only consistent snapshot. No seal or test may widen capabilities,
change prices, bypass a validator or mutate PostgreSQL.

## Acceptance and focused verification

AP-G1: the current parent-swap reproducer cannot read outside the original held
path; cover ancestor and nested-parent/leaf swaps at actual open barriers. Safe
rejection or reading the original descriptor-anchored object is acceptable.
AP-G2: CLI and service reject insecure/symlink/swapped keys, never create keys in
verify, and concurrent initialization uses one complete valid private winner.
AP-G3: FIFO/special files fail promptly under a hard subprocess timeout; oversize
sparse/growing inputs are refused before excessive reads, aggregate/count caps
are enforced before accumulation, and strict malformed/deep JSON is safe.
AP-G4: concurrent destination creation cannot be overwritten for READY, BLOCKED
or exported-baseline output. Test actual syscall seam/concurrent publishers,
interrupted/failing writes and cleanup. Pre-existing targets stay untouched.
AP-G5: signer/verifier consume the same captured bytes; replacement/tamper at
read/hash/recompute barriers cannot authenticate a different proposal. All exact
file-set/size/hash/identity/renderer and HMAC checks preserve positive replay.
AP-G6: ordinary valid READY/READY_WITH_WARNINGS/sealed BLOCKED and unsealed error
paths work with honest exit/status; report and proposals unchanged in semantics;
F1–F4 and prior source/privacy negative cases remain passing.
AP-G7: focused tests, changed-Python lint, documentation checker, internal links,
git diff --check and all ordinary final-head CI checks green. Accurate docs and
actual positive/adversarial evidence, not merely mocked predicates.

Use pytest tmp_path/private mktemp resources and synthetic fake keys only.
Exercise filesystem races through explicit barriers, avoiding timing-only sleeps.
Include key/secret canaries in failure cases to prove absence from output and
reports. Use short child timeouts for potentially blocking special files. Do not
create large committed fixtures or read real devices/secrets. Testing can mock
an export result to test atomic output; its SQL implementation is unchanged.
Run focused catalog-refresh tests and governance/contract checks. No database,
Redis, provider, Codex, Docker or full local/HPC matrix is needed for this round.
Ordinary broad GitHub CI remains required. Do not run an unrelated full local
PostgreSQL suite. If a new concrete failure truly requires such evidence, report
it to strategy rather than broadening resources unilaterally.

## Setup, privacy, accounting and publication boundaries

No protected credentials, production imports, live inference, outbound research,
shared5432 instance/configuration/logs, privileged postgres identity or unrelated
services. No application metadata mutation. No .env reads or secret exposure.
Use current venv and stdlib; no dependencies or system setup needed. Preserve
unrelated worktrees, .local-provider-catalog, rootAGENTS.md and permanent
message.txt. Never global prune/reset/cleanup. Clean only identified task-owned
resources. Capture real command exit codes, not tail/grep pipeline status;
skipped/pending/missing checks are not passes.

Report exact starting/implementation SHAs, exact changed paths, G1–G4 and AP
results, before/after race reproducers, descriptor/limits/key/no-replace/snapshot
contract, positive and negative tests with actual counts/exit codes, docs/links,
CI, privacy/no-mutation proof, resource cleanup and precise remaining work.
State platform limits and whether any checks were not run. Correct prior report
caveats only in this new report. Layout remains required; whole180 and whole
administrator workflow remain incomplete. No perfect/security-certified claims.

Commit strategic order/active bytes unchanged on the existing PR branch. Push
implementation before drafting the report. Publish exactly one immutable final
report-only SELF commit whose first parent equals the literal stated
implementation head. Verify it is remote PR317 head before sending exact two
bytesOK on the verified response FIFO. Coding agent never merges or enables
auto-merge. No tags/releases. Await the next strategic order; a same-PR suffix
may follow without resolving the numeric objective first.
