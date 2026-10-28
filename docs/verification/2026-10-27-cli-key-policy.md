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

## Layers and exact commands

Environment: `/tmp/slaif192-coding-venv` (Python 3.12, editable project,
Playwright available). `PYTHONPATH=app` for all runs.

### New unit suites (pure layer, no DB)

```text
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_key_policy_configuration.py \
  tests/unit/test_cli_key_policy_files.py -p no:cacheprovider
# 74 passed (0 skipped)
```

- 47 validator/schema/service-law cases: finite capability vocabulary,
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
- 27 actual-CLI cases: option-source tracking on the real installed Typer
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
  plaintext key once (the preserved, documented exception).

### Affected existing unit suites (no oracle weakening)

```text
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_cli_keys_create.py tests/unit/test_cli_keys_limits.py \
  tests/unit/test_cli_keys_status.py tests/unit/test_cli_keys_rotation.py \
  tests/unit/test_cli_keys_email_delivery.py tests/unit/test_cli_keys_safety.py \
  tests/unit/test_cli_keys_secret_output.py tests/unit/test_key_service_policy_update.py \
  tests/unit/test_key_service_create.py tests/unit/test_key_policy_validation.py \
  tests/unit/test_key_import_service.py -p no:cacheprovider
# 145 passed
```

Two oracles were updated exactly where the mandated behavior changed:
`test_cli_keys_status.py` now asserts the typed configuration payload (with
ABSENT-preservation of omitted members) and `test_key_import_service.py`
now asserts the provider policy is a supported import column (send-now
rejection unchanged).

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
