# External client compatibility preset engine — 2026-10-20

The human requested one redesign of the executable engine so compatibility
vocabulary ships as external presets, replacing repeated field-specific source
exceptions. The implementation is on draft PR #336, runtime-source commit
`1a4c4b4c9441484eb8f08784a6af6573d55489ce`, based on main
`81f722eddc38a87503080057e3d829ff01e0783d`. No merge or release occurred.

## Executed checks

| Check | Result |
| --- | --- |
| Complete unit suite, 4 workers | 5,189 passed, 1 skipped; 153.22 seconds |
| PostgreSQL migration, replay, context accounting and finalization | 37 passed; 19.98 seconds |
| Ruff, application/tests/new evidence verifier | Passed |
| Whitespace diff validation | Passed |
| Alembic heads | One head, `0025_catalog_refresh_applications` |
| Wheel resource inspection | Both presets, manifest, legacy data, schema and interpreter included |
| Post-documentation focused check | 99 passed |
| GitHub runtime-source commit CI and CodeQL | Both successful |
| Collected preset/replay/accounting obligations | 115 required, 115 executed passing, `missing=[]` |
| Direct interactive Codex 0.163.0 synthetic loopback | Three main requests across two user turns passed |
| Authorized protected Qwen 3.8 27B interactive smoke | Three requests finalized successfully across two user turns |

The unit skip is the existing optional Codex 0.148 CLI check: that executable
was unavailable. The final suite emitted 12 warnings; PostgreSQL emitted five
existing Alembic/SQLAlchemy deprecation warnings. An earlier unit attempt
reported seven failures: two new CLI commands were missing from the reference,
and six checks lacked Git, matching file ownership, or writable bytecode cache
in the test container. The reference was fixed and the complete suite reran
successfully with the corrected environment. That earlier failure is not
reported as a pass.

Unit invocation inside the isolated Python 3.12 test container:

```bash
python -m pytest -p no:cacheprovider -n 4 tests/unit \
  --junitxml=/evidence/unit-corrected.xml
```

The source and its Git metadata were mounted read-only at their real absolute
paths. Tests ran as UID 1000 with Git installed, `APP_ENV=test`, a temporary
`PYTHONPYCACHEPREFIX` and Hypothesis directory, and no production credentials.
The container was bounded to four CPUs and 4 GiB.

PostgreSQL invocation inside a separate test container:

```bash
python -m pytest -p no:cacheprovider \
  tests/integration/test_compatibility_presets_postgres.py \
  tests/integration/test_codex_module_upgrade_postgres.py \
  tests/integration/test_codex_replay_references_postgres.py \
  tests/integration/test_codex_context_accounting_postgres.py \
  tests/integration/test_accounting_finalization_postgres.py \
  --junitxml=/evidence/database-final.xml
```

The runner created a uniquely labelled disposable PostgreSQL 16 container on
localhost with tmpfs storage and a generated test database. Existing owned
database fixtures created their own isolated containers. All were removed.
Only `TEST_DATABASE_URL` pointed at the disposable database; no destructive
setup used production `DATABASE_URL`. Tests made no real provider or email calls.

The machine manifest was generated from pytest's collected node IDs before
execution. This offline checker compared the executed JUnit cases and pinned
interactive structural receipt:

```bash
python scripts/verify_compatibility_preset_evidence.py \
  --manifest tests/fixtures/codex/presets/obligations.json \
  --loopback tests/fixtures/codex/presets/codex-0.163.0-loopback.json \
  --junit /evidence/unit-corrected.xml \
  --junit /evidence/database-final.xml
```

It returned 115/115 and `missing=[]`. A deliberately incomplete JUnit input
returned nonzero and reported missing obligations. The checker never launches
Codex, subprocesses, a provider, or a database.

## Exact-client evidence and limits

The direct interactive executable was Codex 0.163.0, SHA-256
`399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215`.
The preset records official tag `rust-v0.163.0`, source commit
`83086188ae0614bd882818ff1aa23f3194962012`. Its schema-2 revision is 11,
canonical digest
`b0012de33a3beade9cf1b16c1cb92865146570e52980f7da0f6015efce4f22d9`.

The synthetic HTTP server used the actual client module and request policy.
Its SSE producer was separately exercised against the actual strict stream
validator in three parameterized unit cases. A human-style interactive session
naturally produced commentary, one local tool call/result, a final answer,
and another user turn replaying both completed assistant messages and empty
annotations. Only structural counts and synthetic markers were retained.
No GPU or real key was used in that loopback test.

Codex also made two background title requests using structured streaming.
They retained the existing explicit `responses_structured_streaming_not_supported`
rejection at `text.format`. The main conversation completed. These presets do
not implement that semantic feature or establish full Codex compatibility.
Codex 0.162.1 has a separate shipped preset and loader/migration tests; its
interactive executable was not requalified in this change. Browser, complete
E2E/HPC matrices, long-context/compaction and other upstream providers were
not rerun. No release, security or production-certification claim follows.

## Authorized deployment and protected smoke

The deployed runtime overlay image is
`sha256:4f5863769d86564675e521d6ad8413424220455208ef9aca1b9379fb876ab713`.
All six changed Python modules were byte-compared with the reviewed commit.
The operator-owned active file is outside the source and image:

```text
/home/ubuntu/.local/state/slaif-api-gateway/client-compatibility/active.json
```

Its directory is mounted read-only at `/run/slaif/client-compatibility` in API
and maintenance services. `CODEX_COMPATIBILITY_PROFILE_FILE` selects
`/run/slaif/client-compatibility/active.json`. These files contain no credentials;
the serving account has read access and only the operator can write them.

The first dry run found that the secret loader drops root privileges, making
the initial mode-0600 export unreadable to the service account. Read/traversal
permissions on the nonsecret preset were corrected before any traffic or key
state was changed. The subsequent dry run passed.

Ingress and API were drained. A database dump and previous configuration were
saved privately under operator backup directory
`preset-engine-20261020T124049Z`. The previous revision-9 file was saved for
rollback. With zero unsettled reservations, all three active Codex keys were
migrated from revision 9 to 11 through the audited service in one transaction.
Whole-key and non-client-policy digests matched before/after migration.
No credentials, expiry, quotas, usage counters, rate limits or other settings
changed. API readiness and public HTTPS health returned success.

The real protected smoke then used the existing `qwen-students` profile and
credential, explicitly selecting its configured `qwen3.8-27b` model. It ran a
single local printf command, produced `PRESET_A100_FIRST_OK`, and answered the
next user turn with `PRESET_A100_SECOND_OK`. All three HTTP-200 usage ledger
entries and their reservations were finalized in PostgreSQL. No diagnostic
hook or request capture was enabled. The public structural receipt is
`tests/fixtures/codex/presets/codex-0.163.0-protected-smoke.json`.

The existing key still has one request per ten-second window, wait mode,
120-second maximum wait, concurrency one, and its pre-existing waiting queue
bound of two. Its credential was preserved. The user's profile still defaults
to Qwen, workspace-write and on-request approval. `--yolo` was supplied only
to this isolated smoke invocation; it is not a profile default.
