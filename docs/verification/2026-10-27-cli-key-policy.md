# Objective 196-a — typed CLI key-policy configuration verification

Dated evidence for the typed key-policy configuration objective (196-a).
This is a focused objective record, not a full-matrix qualification, and not
a release or production-certification decision.

## Scope

Typed CLI key-policy administration: a bounded version-1 policy file
(`--policy-file`) and explicit provider flags on `keys create` /
`keys policy update`, a safe `keys policy export`, strict Responses/Codex
authoring validation, safe partial updates (omission preserves), an
explicit one-time key channel requirement for the new typed create
surfaces (with the documented legacy flag-free exception preserved),
provider parity in the existing bulk-import execution path, and safe
bounded file I/O and error vocabulary. No schema migration, no new
dependencies, no API/template/CSS changes, no runtime forwarding/accounting
changes.
Final authoring strictness: a closed chat streaming live-burn member
vocabulary enforced BEFORE runtime projection on policy-file create,
configuration update, and RAW stored export (unknown members fail with a
fixed safe message, never echoed); the rendered export is re-parsed by the
same strict version-1 schema before return; and the bulk import rejects an
explicit empty provider list combined with `allow_all_providers`
(contradictory deny-all vs all; a blank/omitted column remains the
unrestricted default).

## Layers and exact commands

Environment: `/tmp/slaif192-coding-venv` (Python 3.12, editable project,
Playwright available). `PYTHONPATH=app` for all runs.

### New unit suites (pure layer, no DB)

```text
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_key_policy_configuration.py \
  tests/unit/test_cli_key_policy_files.py -p no:cacheprovider
# 80 passed (0 skipped)
```

- 52 validator/schema/service-law cases: finite capability vocabulary,
  reserved-authority fail-closed, Codex prerequisite closure, local tool
  pairing, exact/stale/malformed pins, migration-law classification
  (resolved vs stored/stale vs unbound), per-member rate patch with strict
  vocabulary (unknown rejected, alias canonicalized, alias conflict
  rejected), fenced quota invariants, write-phase failure handling at the
  fake repository seam (a first-write failure leaves no partial state or
  audit in the fake; this is NOT a database-rollback proof - the actual
  late-failure transaction rollback is proven in the PG section below),
  export explicit-null round-trips, and the secret-safe audit projection
  (unknown stored fields counted, never copied; canary asserted absent).
  The final-authoring strictness cases prove: an unknown
  `chat_streaming_live_burn_policy` member is rejected on file create and
  configuration update (no write, no audit, member name never echoed), a
  complete known-member block is accepted, a RAW stored unknown live-burn
  member fails the export explicitly, and a stored negative rate window
  fails the export through the final schema-consumability re-parse.
- 28 actual-CLI cases: option-source tracking on the real installed Typer
  app (explicit/omitted/negative/repeatable), file/flag conflict law,
  provider mutual exclusion, no-op rejection, bounded file read (I/O traced
  to at most 65537 bytes), safe error vocabulary (no path/body echo), and
  the configured Codex profile bootstrap BEFORE pin authoring proven in
  FRESH subprocesses (packaged-registry one-shot must not be reconfigured
  inside the test process): a valid configured revision-9 profile is bound
  in the same `keys create` that authors its pin, and an invalid configured
  profile file fails closed with a fixed safe message. The six newest
  cases pin the explicit one-time key channel law for typed surfaces:
  a policy-file or provider-flag create WITHOUT `--show-plaintext`,
  `--secret-output-file`, or an explicit `--email-delivery` mode is
  rejected BEFORE any creation call (no key, no canary in output), while
  `--show-plaintext`, the 0600 secret-output file, and the queued
  email-delivery channel each succeed with the documented output
  behavior, and legacy flag-free creation still prints the one-time
  plaintext key once (the preserved, documented exception). The seventh
  newest case rejects a policy file whose chat streaming live-burn block
  carries an unknown member, before any creation call, with the fixed
  safe message (member name never echoed).

### Affected existing unit suites (no oracle weakening)

```text
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_cli_keys_create.py tests/unit/test_cli_keys_limits.py \
  tests/unit/test_cli_keys_status.py tests/unit/test_cli_keys_rotation.py \
  tests/unit/test_cli_keys_email_delivery.py tests/unit/test_cli_keys_safety.py \
  tests/unit/test_cli_keys_secret_output.py tests/unit/test_key_service_policy_update.py \
  tests/unit/test_key_service_create.py tests/unit/test_key_policy_validation.py \
  tests/unit/test_key_import_service.py -p no:cacheprovider
# 146 passed (0 skipped)
```

Two oracles were updated exactly where the mandated behavior changed:
`test_cli_keys_status.py` now asserts the typed configuration payload (with
ABSENT-preservation of omitted members) and `test_key_import_service.py`
now asserts the provider policy is a supported import column (send-now
rejection unchanged) plus a permanent negative case: an explicit empty
provider list combined with `allow_all_providers=true` is an invalid row
(contradictory deny-all vs all), while a blank/omitted column with
`allow_all_providers=true` remains valid and unrestricted.

### Real owned PostgreSQL 16 integration

```text
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/integration/test_cli_key_policy_configuration_postgres.py \
  -p no:cacheprovider
# 8 passed (0 skipped)
```

Fresh owned, labeled, loopback-bound, tmpfs-backed PostgreSQL 16 container
(created and removed by the imported `owned_pg_url` fixture; ownership
inspected before readiness/migration; cleanup removes only the exact
created ID). Proven through the real Typer entry path with a real database:

- file-only create (providers + rate + quotas + models/endpoints);
- safe export (explicit nulls, exact money decimal, no fresh confirmation);
- provider-only update preserving models/endpoints/rates/quota/usage/
  validity/key material (one audit record per update);
- distinct persisted `null` (unrestricted, key absent) vs `[]` (deny-all)
  provider states for CLI-created and bulk-imported keys;
- the STORED provider policy reaching the REAL consumers: both CLI-created
  keys (unrestricted and deny-all) are authenticated with the real
  `GatewayAuthService` using the one-time material read only from the
  test-owned `--secret-output-file` files (never printed or committed),
  and the real `ModelCatalogService` then admits the route for the
  unrestricted key and filters every route for the deny-all key - no
  provider HTTP, no inference; the configured gateway key prefix is
  deliberately custom in this module, so prefix parsing and auth
  expectations derive from configured Settings, not the production
  default;
- forced LATE audit failures proving the caller-owned transaction: the
  terminal `add_audit_log` call is forced to fail AFTER the repository
  write phase flushed (create: after key + one-time-secret writes;
  update: after the metadata write). The forced hook records every
  invocation, the test asserts the named terminal audit was actually
  reached, and an in-hook observation in the SAME open transaction -
  before the raise - records that the write phase was visible and
  correct at the moment of failure (create: exactly one new
  `GatewayKey` row plus one `OneTimeSecret` with the typed provider
  policy; update: the changed deny-all provider list with the key
  material hash intact). A fresh session then proves the ENTIRE create
  left no `GatewayKey`/`OneTimeSecret`/`EmailDelivery`/audit rows and no
  secret output file, and the update left the key row byte-for-byte
  unchanged (config, key material, counters, reservations, usage, expiry,
  metadata) with zero `update_key_configuration` audits. The transaction
  manager is never patched and no state is manually restored;
- bound-key repin rejected atomically with migration guidance (stored block
  unchanged, zero configuration audits, no extra keys);
- bulk-import provider parity through real execution (omitted / allow-list /
  deny-all / allow-all persisted distinctly; external-tool metadata columns
  still rejected row-wise).

No ambient `DATABASE_URL` was used for destructive setup; no real provider
inference, no real email.

### Static and governance gates

```text
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m ruff check <changed python>
# All checks passed
git diff --check
# clean
scripts/check_documentation.py
# passed
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_oap_governance.py tests/unit/test_documentation_inventory.py \
  -p no:cacheprovider
# 22 passed (9 OAP governance + 13 documentation inventory, 0 skipped)
```

## Boundaries and limitations

- Focused evidence only; the normal final-head CI supplies the broad matrix.
- No browser rerun (no GUI change). No HPC/128-worker run.
- The external-profile bootstrap proof is fresh-subprocess evidence with
  mocked persistence; the PG integration covers the packaged-profile path.
- No real Codex/provider qualification, no real SMTP, no production DB.
- Objective 196 does not declare the full CLI field brief complete; see
  `docs/cli-field-administration.md` for implemented vs proposed (197-205).

## 196-b addendum — bounded CI regression reconciliation (tests/docs only)

This addendum records the 196-b continuation on the same PR
(#352 `oap/196-typed-key-policy`). It resolves the two demonstrated
PostgreSQL-integration CI failures with **test/doc changes only**: no
`app/` runtime change, no new infrastructure, and the 196-a report and
order remain immutable. The 196-a sections above (including their failure
history) are preserved unchanged.

### The two stale oracles (exact source)

1. `tests/integration/test_admin_bulk_key_import_execute_postgres.py::test_admin_bulk_key_import_execute_postgres` —
   the final provider-policy POST asserted `400` plus `"allowed_providers"`
   in the page, i.e. it assumed the bulk-import path did not carry provider
   policy. 196-a R5 deliberately made the shared import path carry
   `allowed_providers` (absent/blank column = unrestricted default;
   explicit empty list = deny-all; list = allow-list), so that blanket
   rejection oracle was obsolete. The sample row still had NO
   endpoint/model policy, so it still 400s — now at the service guard with
   the stable message `Bulk key import execution failed safely. No keys
   were created.` and unchanged state.
2. `tests/integration/test_lazy_throttling_postgres_redis.py::test_http_chat_waits_for_capacity_then_admits_once`
   — a coarse global pool sampler (3 samples × 0.15 s) observed one
   checked-out app connection during a **legitimate short DB revalidation
   that happens BETWEEN released wait sleeps**. Phase distinction: the
   asserted invariant (no connection held by the waiting request) holds at
   the blocked **sleep boundaries**; each retry's revalidation is a
   deliberate short session outside the blocked phase. The old sampler
   confuses revalidation with blocked waiting; it is a test-phase error.
   The 196-a `app/` changes touched authoring/policy code, not the runtime
   auth/admission/lazy/Redis paths. The archived `d8` isolated baseline
   runs PASSED but were not sleep-phase instrumented; only the current
   code was phase-instrumented, so isolated baseline outcomes alone never
   proved flake or a runtime regression.

### Repairs (test-only)

- Admin file: the obsolete negative is replaced by a valid authenticated
  admin **preview → execute** proof: a complete row (owner/cohort/
  validity/cost/token/request/model/endpoint/rate/`allowed_providers=
  openai`/delivery `none`) previews non-mutating with the policy rendered
  (`Providers: openai`) and executes to a new key whose persisted
  `metadata_json` carries `allowed_providers=["openai"]` while the rest of
  the row is preserved; an explicit empty JSON provider list previews as
  `Providers: deny-all` and persists `allowed_providers=[]` (distinct from
  the omitted unrestricted default, asserted on the first legacy key); the
  minimal provider-only row is retained as a negative asserting its TRUE
  stable remaining guard (execution-stage safe failure, unchanged state,
  no new queued payloads) instead of obsolete unsupported-column text.
  All prior missing-confirmation/reason/CSRF, strict-only external-tool,
  secret-nonce/token_hash leakage, all-or-nothing, one-time
  plaintext/channel and enqueue assertions are unchanged; count baselines
  were extended explicitly for the two new successful imports.
- Lazy file: only `test_http_chat_waits_for_capacity_then_admits_once` was
  changed. It now observes the phase it asserts, through the
  `wait_for_rate_limit_admission` helper's EXISTING injectable `sleep`
  seam (a test-local wrapper around the chat gateway's callsite supplies
  the observing sleep; the lazy service, revalidation, real DB session
  lifetime, Redis code, and all final outcome assertions are untouched).
  It records `app.state.db_engine.pool.checkedout()` at **entry AND exit**
  of each bounded wait-loop sleep, waits deterministically (thread-safe
  event, bounded) for **FOUR consecutive sleeps** (eight boundaries) while
  request 1 still holds the slot — so repeated real revalidation happened —
  and only then releases the holder. An observer exception propagates
  through the request path and fails the final outcome assertions; the
  bounded wait failure is a test assertion, not a thread-only warning.
  The module-level `_assert_no_checked_out_pool_connections` helper is
  unchanged for all other nodes.

### Focused verification (actual commands, exits, JUnit counts)

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python`
(Python 3.12); owned services only (unique-labeled, loopback-bound,
tmpfs-backed PostgreSQL 16 and no-persistence Redis 7, identity inspected
before readiness, exact-ID cleanup); no ambient `DATABASE_URL`, no shared
test DB, no Testcontainers fallback, no foreign PG version.

- Admin target node (owned PG through a TEMP outside-repo launcher that
  reuses the existing `owned_pg_url` fixture via `__wrapped__()` and sets
  the explicitly owned `TEST_DATABASE_URL` before collection):
  `pytest tests/integration/test_admin_bulk_key_import_execute_postgres.py::test_admin_bulk_key_import_execute_postgres`
  → **1 passed, 0 failed, 0 errors, 0 skipped**, actual exit 0
  (JUnit `/tmp/slaif196b/admin-provider-policy.xml`).
- Lazy target node (real uvicorn HTTP + owned PG + owned Redis): root-
  independently executed against the exact working-tree source
  (`fa180549d94a79d3b8ec45e9d1fbb95615b1b84184c319208c41e53a7f1b7dc4`) →
  **1 passed, 0 skipped**, actual exit 0
  (JUnit `/tmp/slaif196-root/196b-permanent-lazy-independent.xml`).
  Cited as root-provided independently inspected evidence.
- Focused negative control (TEMP outside-repo full-source copy replacing
  ONLY `_observing_sleep` so the app connection is held across the sleep):
  **FAILED exactly as intended**, actual exit 1, at the new assertion
  `the waiting request must hold no app DB connection at any observed sleep
  boundary: [1, 1, 1, 1, 1, 1, 1, 1]` — not a timeout or setup failure
  (JUnit `/tmp/slaif196-root/196b-permanent-lazy-negative.xml`).
  Cited as root-provided independently inspected evidence; never a product
  passing test.
- The two 196-a export strictness regression nodes (unchanged):
  `tests/unit/test_key_policy_configuration.py::test_export_stored_unknown_live_burn_member_fails_explicitly`
  and `::test_export_stored_negative_rate_window_fails_explicitly` →
  **2 passed, 0 skipped**, actual exit 0 (JUnit
  `/tmp/slaif196b/export-strictness.xml`).
- Static gates on the changed Python: `ruff check` on both changed test
  files → all checks passed; `git diff --check` → clean.
- Governance/doc: `tests/unit/test_oap_governance.py` (9 cases) plus the
  documentation inventory → see commit-level result recorded in the 196-b
  OAP report.

Qualification layer: the lazy node is real uvicorn HTTP against a real
app with owned PostgreSQL/Redis and real accounting rows. The admin node
is in-process ASGI through FastAPI TestClient against the real app with
the owned PostgreSQL (no network HTTP, no Redis in that node) and real DB
rows. Neither uses real provider inference, real SMTP, or a real external
client. The 196-a unit evidence above remains fakes/pure-layer as
recorded; nothing here upgrades it.

### CI state and limits (honest, at publication)

- First implementation head `7762b08` (CI run 40609965209): ONLY the
  `PostgreSQL integration tests` job failed (381 passed / 9 skipped /
  2 failed — exactly the two nodes above); the other nine checks passed.
- 196-a report-only head `34850df`: final CI finished **9/10 success**,
  the same two PG failures only.
- At 196-b publication the fix-head CI is **PENDING, not a pass**; the
  final normal matrix is supplied by final-head CI and the coding agent
  never merges. All final-head merge gates (strategic review + all checks
  successful) remain required.
- No runtime was changed; this is a test/doc reconciliation, not a
  completed runtime repair. Objective 196 does not declare the full CLI
  field brief complete (197-205 remain the standing mandate), and the
  separate 196-c bounded continuation for the out-of-scope stored
  Responses known-field audit finding is root-activated after this handoff.
