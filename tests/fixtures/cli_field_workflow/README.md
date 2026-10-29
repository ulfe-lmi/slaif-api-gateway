# 205 installed CLI field-workflow fixture

Fictional, owned, disposable fixture for the objective-205 installed CLI
field-administration workflow qualification
(`tests/integration/test_cli_field_installed_workflow.py`), currently
executed under work orders 205-a, 205-b, and 205-c (same PR). It exists only to
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

- Source: `420fb8f6d9377f569d126d08f4c9e4146fc7250b` (`SOURCE_SHA`), the
  205-b implementation commit carrying the bounded no-echo numeric fix.
  Pinned and fetched shallow-safely (`git fetch --depth 1 origin <SHA>` when
  absent). Shallow archival was verified in owned scratch: a fresh depth-1
  clone of origin lacks the commit, the narrow fetch obtains it, and
  `git archive` yields a payload whose commit tree hash
  (`1213f89b985f514204821790d79ddb2b24710b76`) matches the local commit
  exactly.
- Wheel: built with `python -m build` from that exact source into the owned
  venv, OR reused from an already payload-verified wheel of the same source.
  The ACTUAL selected wheel SHA256 is recorded in the run identity (no manual
  ZIP hash is required for a verified reuse). On qualification runs so far the
  selected wheel is
  `042eb23ac7042d2e77c4af4dca6d80d52f0968a328b33d03c8d0f825c07dad6f`
  (205-b run); the earlier 205-a wheel
  `5c5bbdb405c7b84f4434a3cfc28f6c15cae2c4947f61d32540149e61b3f6ec55` is
  stale for this source and is rejected by the payload gate, not reused.
- Stale-venv rejection: a previously reused venv is rejected and replaced by
  a fresh owned venv whenever its installed payload differs from the SELECTED
  wheel; a matching path/version alone is never treated as usable.
- Setup subprocess hygiene: the build venv, `python -m build`, fresh-venv
  creation, and `pip install` run with a scrubbed environment (no inherited
  `PYTHONPATH`), and `pip` runs from a neutral cwd, so the source-tree
  egg-info cannot make pip treat the same-version wheel as already installed.
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

- SMTP: loopback sink (active in the fixture; unused for delivery in the
  current slice).
- Provider upstream: the seed still uses a fictional provider `base_url`
  (`https://openai-fixture.example.invalid/v1`), never contacted. Since
  205-c the existing `GatewayServer` helper is WIRED: DoD5 starts the ACTUAL
  installed `slaif_gateway.main:app` on an owned loopback port against the
  owned PG (scrubbed explicit fictional settings, capture OFF, transient log
  drain, fixed safe readiness, bounded stop, no raw subprocess output in
  assertions). No real OpenAI/OpenRouter backend, no real client, no Redis,
  no real mail anywhere in this fixture.

## Fixture setup that is NOT operator action

- `SEED_SCRIPT` (above) and the 205-c helper `_plant_dod8_history` insert
  pre-existing rows through the pytest process using the product-equivalent
  ORM (same committed `420fb8f` source bytes as the installed payload),
  following the native 199 reference pattern. They create fictional
  historical linkage (e.g. a pre-existing key + a `pending` usage-ledger row
  + a replay reference bound to a route) with constant synthetic digests
  only. The DoD8 ledger is `pending`, NOT a successful-finalized
  replay-eligibility record. These rows are never presented as operator CLI
  actions.
- `_profile_data_fingerprint` hashes the installed COMPLETION-SERVICE SERVER
  profile data (`modules/servers/completion_service/profiles/*.json`), not an
  external Codex client catalog; the client-module pin is a separate matter
  not covered by the canonical key export.

## Current state (205-c handoff)

Implemented and executed through the installed console: DoD0 (installed
identity), DoD1 (lookup/bounded paging, full-bearer refusal), DoD2 (effective
policy + route explanation), DoD3 (institution/owner/cohort record
operations), DoD4 (exact student/beta + two chat clones), DoD6 (rates, bounded
lazy configuration, exact-37 cohort batch), and — new in 205-c — DoD5
(discovery grant: real filtered `GET /v1/models` through the installed owned
gateway with provider/allow-list/disable controls), DoD7 (two configured
completion services + capabilities routes prepared disabled, inspected,
separately activated), and DoD8 (stable-ID context/media route updates via
reviewed plans, stale-plan and mixed-mode refusals, multi-route, preserved
key policy/material, route-linked history). DoD9 (one-time delivery
lifecycle), DoD10 (gateway-recorded failure diagnostics), and DoD11 (replay
maintenance) are NOT yet implemented here and remain mandatory for the final
205 PR.

The NEW CLI privacy defect confirmed under 205-a (credential-shaped numeric
input echoed completely in native usage errors, exit 2; root receipts
`205-installed-lazy-numeric-canary-probe.json` and
`205-installed-new-numeric-surface-canary-probe.json`) is FIXED in source
commit `420fb8f` by the shared no-echo conversion helper at the 17 observed
positions (root recheck `205-b-root-fixed-installed-numeric-probe.json`: all
17 fixed). The ordinary usage-error channel itself (native Typer usage
refusal, exit 2, stderr, no JSON, even with `--json`) remains documented 197
behavior and is asserted, not treated as a defect.

Transcript persistence (implemented in 205-c):
`FieldEnvironment.persist_transcript(outcome)` writes per run, outside the
checkout, into a 0700 per-run directory
`<ARTIFACT_DIR>/transcripts/<RUN_TOKEN>/` (default `/tmp/slaif205`, override
`SLAIF205_ARTIFACTS`): `transcript.json` and `identity.json`, both 0600,
never overwriting another run. Records carry the actual requirement-indexed
`run_cli` argv boundaries/output projections/exit codes (each real record
has a meaningful outcome `label`) plus safe run/installation identity. No
raw bearer/provider values, passwords, encryption keys, request/response
bodies, or raw subprocess/SQL exception dumps are persisted; generated
credentials are registered before retention and asserted absent by canary
checks; the directory survives PG/process teardown and pytest temp cleanup
by construction. A persistence failure surfaces as an evidence failure while
teardown always completes. Retention is operator-controlled (remove the run
directory after review). This is a PARTIAL transcript: it covers the NEW
C cases only; the previously executed six outcomes are not retroactively
re-transcribed, and the final fresh all-eleven run must export every
outcome.

## Reproducible invocation

```bash
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app NO_COLOR=1 \
  <venv-python> -m pytest \
  tests/integration/test_cli_field_installed_workflow.py \
  -p no:cacheprovider -q --junitxml=<artifact-dir>/205a-<slice>.xml
```

JUnit XML is authoritative for counts (repository addopts suppress the
console summary). Overlapping slice runs are never summed as unique cases.
