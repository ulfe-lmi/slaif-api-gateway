# 205-a installed CLI field-workflow fixture

Fictional, owned, disposable fixture for the 205-a installed CLI
field-administration workflow qualification
(`tests/integration/test_cli_field_installed_workflow.py`). It exists only to
run operator business actions through the ACTUAL installed `slaif-gateway`
console and to assert durable PostgreSQL state. It is not a shared test
framework and creates no general catalog/fixture machinery.

## Owned resources

- PostgreSQL 16 container, unique per run: name `slaif205a-<RUN_TOKEN>` with
  labels `slaif205a.run=<RUN_TOKEN>`, `slaif205a.owner=uid<uid>`,
  `slaif205a.purpose=field-workflow-qualification`, `slaif205a.order=205-a`.
  Loopback-only published port (`127.0.0.1`), tmpfs data directory. Exact
  ownership, label, loopback binding, and tmpfs are inspected BEFORE
  migrations; only the exact owned container ID is removed in teardown after
  re-checking its label. Ambient `DATABASE_URL`/`TEST_DATABASE_URL` are unset.
- Owned artifact directory under the pytest temp tree (`/tmp/slaif205` on the
  qualification machine): wheel, owned Python 3.12 venv, pristine pinned
  source archive, and per-run operator directory (CLI cwd, 0600 password and
  secret-output files, seed script, safe transcripts).
- Loopback synthetic SMTP sink (`SmtpSink`) bound to `127.0.0.1` for the
  one-time key-delivery channel; no real SMTP.

## Source / wheel / installed identity

- Source: accepted objective-204 merge commit
  `5e59a023154bfebc998ef4e0a7089a3151fda0e2` (`SOURCE_SHA`), pinned and
  fetched shallow-safely (`git fetch --depth 1 origin <SHA>` when absent).
- Wheel: built with `python -m build` from that exact source into the owned
  venv, OR reused from an already payload-verified wheel of the same source.
  The ACTUAL selected wheel SHA256 is recorded in the run identity (no manual
  ZIP hash is required for a verified reuse). On qualification runs so far the
  selected wheel is
  `5c5bbdb405c7b84f4434a3cfc28f6c15cae2c4947f61d32540149e61b3f6ec55`.
- Installed payload: the installed `slaif_gateway` file set is compared
  exactly against the SELECTED wheel payload (file names + sha256); the
  console lives in the owned venv and `slaif_gateway.__file__` is asserted to
  resolve inside that venv's site-packages.
- Every CLI invocation is a subprocess of the venv console from the owned
  operator directory outside the checkout, with a scrubbed environment
  (`PYTHONPATH` unset, inherited credentials removed).
- Fixture seed: `SEED_SCRIPT` (written into the operator directory) seeds
  clearly labeled PRE-EXISTING fictional owners, models (M1-M4), routes,
  provider, keys, cohorts, and audit history using the installed package's
  own service layer as setup (separate from the operator transcript under
  test). It prints a `SEED_MANIFEST <json>` line consumed by the fixture.
  All generated credentials (PG password, HMAC secret, encryption key, key
  secrets) are random, kept in memory or 0600 files, and substituted/masked in
  every retained projection; the run identity records only booleans/hashes.

## IO substitutions

- SMTP: loopback sink (active in the fixture).
- Provider upstream: the test module contains DRAFT, NOT YET WIRED
  `ProviderMock` (loopback stdlib HTTP upstream) and `GatewayServer`
  (uvicorn of the installed `slaif_gateway.main:app`) classes for the later
  outcomes (DoD5-11); the current seed still uses a fictional provider
  `base_url` (`https://openai-fixture.example.invalid/v1`) and no gateway
  process is started. No real OpenAI/OpenRouter backend, no real client, no
  Redis, no real mail anywhere in this fixture.

## Current state (205-a handoff)

Implemented and executed through the installed console: DoD0 (installed
identity), DoD1 (lookup/bounded paging, full-bearer refusal), DoD2 (effective
policy + route explanation), DoD3 (institution/owner/cohort record
operations), DoD4 (exact student/beta + two chat clones), DoD6 (rates, bounded
lazy configuration, exact-37 cohort batch). DoD5 (discovery grant through the
live gateway), DoD7-8 (provider/route completion configurations and route
edit), DoD9 (one-time delivery lifecycle), DoD10 (gateway-recorded failure
diagnostics), and DoD11 (replay maintenance) are NOT yet implemented here and
remain mandatory for the final 205 PR.

A confirmed NEW CLI product defect (credential-shaped numeric input echoed in
`set-lazy-throttling` usage stderr, exit 2) is recorded in the strategic
receipt `205-installed-lazy-numeric-canary-probe.json` and is out of the
205-a no-product-edit scope; it is deferred to the same-PR 205-b
continuation. The ordinary usage-error law itself (native Typer BadParameter
-> exit 2, stderr, no JSON, even with `--json`) is documented 197 behavior
and is asserted, not treated as a defect.

## Reproducible invocation

```bash
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app NO_COLOR=1 \
  <venv-python> -m pytest \
  tests/integration/test_cli_field_installed_workflow.py \
  -p no:cacheprovider -q --junitxml=<artifact-dir>/205a-<slice>.xml
```

JUnit XML is authoritative for counts (repository addopts suppress the
console summary). Overlapping slice runs are never summed as unique cases.
