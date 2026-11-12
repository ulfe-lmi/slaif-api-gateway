# OAP 223-a — Demo file-backed snapshot (worker-only) — final report

Order: `oap/orders/223-a-demo-file-snapshot.md`
SHA256: `4202690f1576b2194136414a6e2fed0e275fce86bdb496ad8bb11831d2574369`
`oap/active`: exact `223-a` (5 bytes)
Repository: `ulfe-lmi/slaif-api-gateway` · Branch: `oap/223-demo-file-snapshot` · PR #382 (base `main` `2209e100`)
Activation bytes commit: `2844ca5ddedd68997e7c5e2fadb89a07300248b3`
Implementation head (sole parent of this report's SELF): `f36771e32388012c74ac02b7da726d57d35ba7fb`
(all test/check evidence below was executed 2026-11-12 (18:50–19:10Z) against
`05eb7307d1ebf001c5b09a6f643332d0b7fd27d9`; the head is that commit plus a
docs-only accuracy commit, so the evidence applies unchanged)

## 1. What this stage implements (worker-only; no public route, no web grant)

A worker-only file snapshot stage that, for one per-copy demo job, captures a
positively allowlisted set of file-backed operator sources, converts each to a
typed READ-ONLY DEMO DISPLAY copy, and persists only flat sanitized leaves —
while the 221 DB dump and 222 DB sanitize remain the database half of the same
per-login copy. The 224 web stage will later read only the verified per-copy
files; this stage grants it nothing.

Implementation (two commits: `05eb7307` code+tests+docs, then `f36771e3`
docs-only accuracy fixes — torn-write/manifest wording and the
two-snapshot-times limitation):

- `app/slaif_gateway/services/demo_snapshot_files.py` (new, ~4.4k lines):
  - 9 finite safe codes: `FILES_SOURCE_MISSING`, `FILES_SOURCE_UNSAFE`,
    `FILES_SOURCE_UNSUPPORTED`, `FILES_SOURCE_TOO_LARGE`,
    `FILES_SOURCE_CHANGED`, `FILES_BUDGET_EXCEEDED`, `FILES_WRITE_FAILED`,
    `FILES_VERIFY_FAILED`, `FILES_CLEANUP_FAILED`.
  - Bounded `_Capture`: aggregate RAW bytes admitted BEFORE any artifact is
    parsed, per-kind typed sanitizer, aggregate DISPLAY bytes admitted before
    the leaf is retained; each raw body is sanitized and discarded per file
    and only the bounded sanitized leaf is retained (one focused refcount
    test proves non-retention for its specific neutral-path case — the
    bound is the budget law, not that single test).
  - 16 display kinds, each with a closed typed sanitizer and an independent
    per-kind display-policy spec that the verifier re-proves from stored bytes.
  - Reads only through held anchored descriptors (no-follow; identity
    re-checks; run-entry `(dev,ino)` compared against the opened handle;
    `runs/` parent identity compared through held fds); no source file is
    created or modified. One documented exception (stated exactly as in
    the docs): branding slot selection reuses the existing validated
    `web.branding.resolve_slot` resolver, which performs its own anchored
    no-follow open of the configured slot path; candidate presence is
    inspected through the HELD dirfd before resolution, and the worker
    re-asserts the held branding directory name binding before trusting
    the resolved bytes.
  - Display tree: FLAT 0600 leaves `f{NNNN}-{sha12}` (4-digit index, 4096-leaf
    cap, boundary-tested) under one owned 0700 `files/` directory; the
    private 0600 `files/files_manifest.json` is written LAST (interrupted
    write => job not verified, exact-owned cleanup, artifacts retained).
  - Independent read-only verifier: re-reads every leaf through the anchored
    boundary, rechecks files-dir identity, exact leaf set (no foreign entry,
    no missing leaf), digest/bytes/0600/inode, then the per-kind display
    policy; trusted configured caps (never manifest counts) plus absolute
    finite ceilings; deadline re-checked before every read and before
    promotion; malformed stored shapes fail `FILES_VERIFY_FAILED` (no raw
    tracebacks escape the verifier).
  - `run_files_job`: custody fence, idempotent skip of already-verified
    state, prior PENDING/FAILED cleanup, per-copy absolute deadline, final
    gate before promotion, `FilesJobResult` with an aggregate
    `failure_code` (first failed copy's ACTUAL final code; cleanup failure
    overrides with `FILES_CLEANUP_FAILED`).
  - Cleanup order: dump unlink -> target DB drop FIRST -> exact-owned flat
    files cleanup only after confirmed DB removal (anchored
    `cleanup_staged_directory` on recorded identity + manifest-listed names,
    then proven absence); any inconsistency retains artifacts for the
    operator and reports `FILES_CLEANUP_FAILED`.
- `app/slaif_gateway/services/demo_snapshot.py`: new job state
  `DB_AND_FILES_VERIFIED_UNPUBLISHED`; manifest fields
  `files_state/files_failure_code/files_verified_at/files_bytes/files_count`;
  anchored `_clean_job_files` used by the 221/222 cleanup path.
- `app/slaif_gateway/config.py`: 3 feature-local settings, validated only on
  the enabled worker path so a disabled gateway is unaffected:
  `DEMO_SNAPSHOT_FILES_MAX_FILE_BYTES` (default 32 MiB, 1–128 MiB),
  `DEMO_SNAPSHOT_FILES_MAX_TOTAL_BYTES` (default 128 MiB, 64–4096 MiB),
  `DEMO_SNAPSHOT_FILES_MAX_ELAPSED_SECONDS` (default 300 s, 10–3600 s).
- `app/slaif_gateway/cli/demo_snapshot_worker.py`: `files` command; the
  aggregate safe `code` is emitted in the payload only when a failure code
  exists; no raw paths/secrets in any CLI/log output.
- Docs: `docs/demo-admin.md` (stage 223 operator section: implemented and
  tested but the demo is NOT usable yet; source->projection table; branding
  resolver boundary described precisely; DB-first cleanup order;
  `ssl=False` private-network transport limit; identity-mask privacy limit;
  the 223-b prerequisite; two-snapshot-times limitation: the 221 DB
  dump and the later 223 file capture are not transactionally simultaneous
  and both times are recorded/inspectable), `docs/cli-reference.md` (`files` command +
  aggregate first-failed-code semantics), `docs/configuration.md` (3 settings
  + feature-local note).

## 2. Exact route/source -> safe projection inventory

All configured sources are covered; a missing/unknown/unreadable configured
source fails the login job closed (finite code). Unconfigured optional sources
are recorded as `not_configured` and skipped.

| Display kind (leaf) | Source (allowlisted) | Safe projection |
|---|---|---|
| `refresh_bundle` | sealed run `catalog-refresh.json` (and uploads `bundle-*`) | typed bundle projection; all UUIDs/IDs remapped per copy; `run_id` -> `demo-run-<24hex>`; free text/notes neutralized; capability keys from the closed catalog vocabulary |
| `baseline_document` | sealed run `catalog-baseline.json` (and uploads `baseline*`) | full `BaselineDocument` projection with per-copy ID remap; first-install sealed runs publish the canonical empty marker instead -> fixed neutral display `{first_install: true}` (note discarded) |
| `route_tsv` | sealed run `routes-proposal.tsv` | closed columns; capability cell validated by the derived RUNTIME capability projection law (same law as `BaselineRouteRow`); `notes` -> neutral |
| `pricing_tsv` | sealed run `pricing-proposal.tsv` | safe numeric prices/currency/times; `source_url`, `notes` -> neutral; `pricing_metadata` validated-then-fixed `{}`; empty producer cells accepted |
| `fx_json` | sealed run `fx-proposal.json` | closed fx fields only; `source` URL, `provenance`, `warnings` dropped |
| `validation_json` | sealed run `validation.json` | finite projection: states/gates/counts; free text neutralized; code->count maps reduced to totals; source rows: provider ∈ route providers ∪ {`ecb`} (producer's own `SourceRecord` law), `source_kind` ∈ closed `SOURCE_KINDS`; `currency_old` nullable (NEW comparisons); `excluded_mutations` plain int; `apply_plan` accepted and DROPPED (apply authority never displayed) |
| `review_html` | sealed run `REVIEW.html` | fixed neutral packaged HTML (raw active report never copied) |
| `provider_catalog_normalized` | proposals `provider-catalog-normalized.json` | closed fields; display names/descriptions/URLs/metadata dropped; comparison rows -> count; capabilities from closed catalog vocabulary |
| `source_manifest` | proposals `source-manifest.json` | `source_type` -> fixed `known`; URLs/warnings dropped; `content_hash` 64-hex retained; `output_files` checked against the exact closed artifact set; extractor version pinned to the product's current one |
| `warnings_json` | proposals `warnings.json` | closed row fields (code/provider/model_id/endpoint) with finite laws; unknown row fields dropped |
| `package_manifest` | proposals `packages/<preset>/*` (fixed product preset vocabulary only) | finite projection; warning/excluded CODE KEYS -> totals; filesystem paths and recommendation dropped |
| `markdown` | catalog Markdown reports | fixed neutral packaged Markdown |
| `upstream_llm_profiles` | operator profiles JSON file | per-copy fictional `demo-llm-profile-NN` ids; finite protocol fields + recomputed `sha256` retained; operator ids never displayed |
| `completion_choices` | operator profile directory (validated stems only) | validated fictional stems only; profile BODIES are never read |
| `branding` | operator branding slot files (logo/favicon/hero/style.css candidates via the product slot-resolution law) | packaged neutral SLAIF substitutes; selected file recorded only as name/type in the private manifest; symlink/dual/invalid candidates fail closed |
| `job_record` | catalog `jobs/<32hex>.json` records | 32-hex job id remapped with the 222 per-copy mapping; run id -> `demo-run-*`; artifact name -> per-copy remap; `progress`/`error_code` neutralized/dropped; raw params never displayed |

Additionally: packaged invariant data (Codex presets, packaged Codex startup
profile, packaged upstream-LLM defaults) are referenced by pinned per-copy
digests only (never copied); the operator `PUBLIC_BASE_URL` is recorded as a
PRESENCE MARKER only (its value never enters any artifact; the stage-224
profile download must use the demo base URL, not the live gateway URL).

For every catalog-derived leaf the private 0600 files manifest carries
`source_ref == logical_name` equal to the per-copy remapped demo id,
structurally enforced: `_read_catalog_file` requires a remapped
`logical_name` and never persists the original source name/job/artifact id.
Non-catalog leaves use FIXED non-identifying reference labels instead
(`branding:logo`, `profiles:upstream-llm.json`,
`profiles:completion-choices.json`). No original catalog run/job/artifact id
appears in the manifest, any leaf, logical name, CLI, or log.

One exact worker-private exception, disclosed: `capture_completion_profiles`
retains the fictional-id → original operator profile STEM map in the
manifest's private `source_records` block (worker-only custody: the 0600
job-private manifest; the stage-224 web path reads only verified display
leaves and never the manifest). Every other original-to-demo mapping exists
only as keyed per-copy functions of the job seed.

## 3. Canary proof

Literal secret/identity/path canaries (`CANARY223a` and variants) were planted
in top-level and nested free-text/identity/path/JSON positions for EVERY one of
the 16 kinds (per-kind positive tests assert their absence from the sanitized
bytes while safe choices/prices/counts survive at exact positions), plus:
sealed-run review-report canary -> neutral HTML/Markdown; branding SVG/CSS
canary -> neutral substitute; completion-profile id canary -> fictional id with
bodies never read; catalog source canaries (source_type, URL, provenance,
warning keys, recommendation, progress, params, display names, env-var names,
model descriptions) -> dropped/neutralized; unknown-key/unknown-type canaries
fail closed (`FILES_SOURCE_UNSUPPORTED`) and, when stored, fail verification
(`FILES_VERIFY_FAILED`). The sealed-run test also asserts the original run id
is absent from every display leaf AND from the private manifest bytes, and the
upload test asserts the original job id + artifact name are absent from the
private manifest bytes.

Deliberate original HMAC/apply rejection (owned real evidence): a positive
first-install sealed run was produced with the real `catalog-refresh review`
CLI (exit 10, READY_WITH_WARNINGS, fully sealed). After 223 capture, a forged
directory containing the sanitized display files fails
`load_verified_capture` with the ORIGINAL seal key
(`CatalogRefreshSealError`) — the display copy carries no HMAC/seal/apply
authority — while the untouched source run still authenticates with the same
key. No catalog refresh, provider discovery, mail, or outbound network
activity occurs in the worker; the focused integration uses only owned
loopback PostgreSQL.

## 4. Counts and limits

- Display kinds: 16. Safe codes: 9.
- Per-file display/raw cap default 32 MiB (1–128 MiB); total cap default
  128 MiB (64–4096 MiB); elapsed default 300 s (10–3600 s); leaf count cap
  4096; verifier absolute ceilings 128 MiB/file and 4 GiB total; TSV row cap
  10^6; job record 1 MiB.
- Captured sealed-run content set: the 7 `CONTENT_FILES` (bundle, baseline,
  routes/pricing TSV, fx, validation, REVIEW.html) per run; uploads
  `bundle|baseline|baseline-export-<32hex>`; proposal artifacts (fixed names);
  package files under the fixed preset vocabulary; admin job records.
- Sealed-run test leaf count: 7 (one first-install run); PG-handoff leaf
  count: 6 (5 branding substitutes + completion choices) with catalog
  unconfigured (root-mandated test economy; sealed catalog shapes are covered
  by the focused unit evidence above).

## 5. Test method and exact results

Method: host Python 3.12 via the repository `.venv`; unit tests are
mock/file-tree only (no DB, no network). The focused integration is a REAL
owned PostgreSQL 16 chain (221 dump -> 222 sanitize -> 223 files) against two
owned loopback PG16.15 containers (source `127.0.0.1:54351/slaif_gateway_test`,
target `127.0.0.1:54352/postgres` system-only) with PG16.15 client binaries
extracted from the worker image on `PATH` (host `pg_dump` is 18.6; the
17/18->16 restore mismatch is a known harness gap, documented, not a product
change). This is host-Python driving owned loopback PG16 — NOT an in-container
pytest run, and no real company/browser/client/provider data or verified
remote TLS is involved anywhere.

Results (all executed at the implementation head, direct pytest exit captured
before any tailing):

- `tests/unit/test_demo_snapshot_files.py`: **64/64 passed**, exit 0.
- `tests/unit/test_demo_snapshot.py`: **33/33 passed**, exit 0.
- `tests/unit/test_demo_snapshot_sanitize.py`: **58/58 passed**, exit 0.
- `tests/integration/test_demo_snapshot_files_postgres.py`: **1/1 passed**
  (3.30 s), exit 0. Proves: 221 RAW_UNVERIFIED -> 222 SANITIZED -> 223
  `DB_AND_FILES_VERIFIED_UNPUBLISHED` handoff; worker custody ownership; all
  display leaves are exact neutral substitutes with no absence-token leakage
  in any leaf/logical name/source_ref/result; source fingerprint invariant;
  target holds system databases + exactly one recorded copy DB; web role
  denied (42501) on the raw copy and at final state; exact run-owned teardown
  verified (source rows removed by recorded IDs, copy DB/roles dropped).
- Scoped Ruff on all 6 touched files: clean (exit 0).
- `git diff --check`: clean.

No full local matrix was run (order: no rerunning unchanged matrices without
reason; final-head hosted CI is root's broad gate).

## 6. Product defects found by this round's tests (fixed in the same commit)

For transparency, the focused/real-producer tests exposed and the
implementation fixed:

1. `_is_iso_timestamp` called `_dt.datetime.fromisoformat` (module vs class):
   raw `AttributeError` escaped the job-record sanitizer -> finite code path.
2. Sealed first-install runs publish the canonical empty marker document, not
   a `BaselineDocument` -> bounded exact two-field placeholder branch (note
   discarded, fixed neutral display; verifier accepts the exact marker).
3. Producer TSV dialect: `csv.DictWriter` output (CRLF rows, quoted JSON cells
   with doubled quotes) vs naive `split` -> shared `csv.reader`-based parser
   (tab delimiter, exact header/row width, bounded rows, no newline-bearing
   cells) used by BOTH sanitizers and the verifier.
4. Route TSV `capabilities` cell carries the derived RUNTIME capability
   projection (nested `chat_completions` block), not flat catalog keys ->
   validated by the schema's own `validate_route_capability_projection` law;
   verifier re-proves the display form; flat `CAPABILITY_KEYS` retained only
   for RefreshBundle and normalized proposal facts.
5. NEW price comparisons carry `currency_old: null` -> nullable bounded
   currency validation (sanitizer + verifier); `currency_new` stays required
   (producer law).
6. `import_gate.excluded_mutations` is a plain non-negative int in the
   producer (not a code->count map) -> typed int in sanitizer + verifier.
7. `validation.sources` provider is a SOURCE-provenance label (e.g. `ecb`),
   not a route provider -> finite producer law (route providers ∪ {`ecb`}) +
   closed `SOURCE_KINDS`; route-provider taxonomy not widened elsewhere.
8. Verifier escape: tampered leaf with non-string model id raised raw
   `TypeError` -> type guards + defense-in-depth catch converting any
   validator exception to `FILES_VERIFY_FAILED` (tampered leaf stays
   unpublished with a finite code).
9. Uploads path referenced non-existent `catfs.MAX_BUNDLE_BYTES` (raw
   `AttributeError`) -> the bundle module's own 8 MiB `MAX_BUNDLE_BYTES` law
   (same as the sealing law).
10. Private-manifest identity leak: `source_ref` carried ORIGINAL run/job/
    artifact ids -> all catalog-derived `source_ref`s now equal the per-copy
    remapped display identity (non-catalog leaves keep their fixed
    non-identifying labels); `_read_catalog_file` structurally requires it
    (fail closed if absent); sealed-run and upload tests assert original ids
    are absent from the manifest bytes.

## 7. Scope and honest limitations

- Stage 223 (files) is implemented and tested; the DEMO REMAINS UNUSABLE.
  Two prerequisites block stage 224: (a) same-PR 223-b — the 222 DB sanitizer
  currently REFUSES real nested `model_routes.capabilities` (live route
  config/CLI supports nested `codex_limits`, `media_input_estimation`,
  chat/responses and `completion_service {version, profile}` blocks), so a
  real configured source would fail DB sanitization; a typed privacy-safe
  mapping (shared with file-profile choices) is required; (b) stage 224
  itself (web read of the verified per-copy copies).
- Process configuration panel: `/admin/operations/process-configuration` is
  runtime API-process Settings, NOT a file-backed source. The 223 worker does
  NOT capture its finite 45-setting projection (only the `PUBLIC_BASE_URL`
  presence marker is recorded). The panel is therefore not snapshot-ready by
  223; the stage-224 login handler must take the existing safe
  `inspect_process_configuration(settings, process_scope="api")` projection at
  login and bind it to the per-login view, explicitly labeled as
  API-process capture time. No worker-to-API IPC is introduced.
- Two snapshot times: the 221 `pg_dump` database snapshot and the later
  223 per-source file capture are NOT transactionally simultaneous; both
  windows are recorded and inspectable in the private custody state, and
  the combined copy must not be claimed as a single-instant snapshot.
- Identity-masking privacy limit: per-copy fictionalization breaks identity
  but usage PATTERNS remain recognizable (documented operator limitation).
- Target DB transport is `ssl=False`: target PostgreSQL traffic must remain on
  a trusted private loopback/Compose network; this stage does not support
  verified remote DB TLS.
- Test method is host-Python + extracted PG16.15 client binaries against owned
  loopback PG16 containers (not in-container pytest); sealed-run and
  upload-manifest evidence are focused unit-level real-producer runs.
- A full valid `run_review`/RefreshBundle generation through the PG handoff is
  intentionally deferred to stage 225 installed acceptance (the PG handoff
  uses unconfigured optional catalog sources + fixed branding/completion
  fixtures; sealed catalog artifact shapes are proven in focused unit tests).
- No browser/real-company/client/provider tests; no release, deployment, or
  production data.

## 8. Publication verification

- PR #382: implementation head `f36771e32388012c74ac02b7da726d57d35ba7fb` (docs-only accuracy commit over `05eb7307`) pushed before publication; this report's SELF becomes the new PR head. Remote `git ls-remote` and `gh pr view` verification of the pushed head was completed before the single response OK.
- Order SHA256: `4202690f1576b2194136414a6e2fed0e275fce86bdb496ad8bb11831d2574369`; `oap/active` exact `223-a` (5 bytes).
- Protected untracked files unchanged (hash-only, never read): `CODEX-SESSIONS.md` `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`, `codex.sh` `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`, `uv.lock` `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
- Report-only SELF: sole parent = implementation head `f36771e32388012c74ac02b7da726d57d35ba7fb`; diff contains only this new report.
- Final-head hosted CI (all checks, CodeQL, Code Quality) is PENDING and is
  root's gate; root reviews, merges guarded only if green, and only then
  activates 224 (after 223-b on this same PR).
