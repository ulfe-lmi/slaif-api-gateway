# Objective 198-a — faithful standard-key cloning (`keys clone`) verification

Dated evidence for the faithful standard-key cloning objective (198-a),
which replaces operator Python cloning with a shared, auditable,
retry-safe plan/execute operation and executable CLI. This is a focused
objective record, not a full-matrix qualification, and not a release or
production-certification decision.

## Scope

Bounded CLI/service functionality built on existing services (no schema
migration, no DDL, no new dependencies, no API/template/CSS changes, no
runtime forwarding/accounting/Redis changes):

- New `app/slaif_gateway/schemas/key_clone.py`: strict version-1 NON-secret
  clone-plan document (128 KiB envelope bound; unknown/duplicate JSON
  fields, bad types, non-UTF-8, and oversized files rejected with fixed
  safe errors that never echo file bodies, paths, or values; optional
  non-authoritative `preview` block).
- New `app/slaif_gateway/services/key_clone_service.py`: plan build
  (read-only, no audit) and execute (source `FOR UPDATE` lock, eligibility
  revalidation, receipt-first deduplication, strict canonical re-derivation
  and fingerprint comparison, creation + one-time secret + optional pending
  delivery + bounded safe receipt + clone audit in one caller-owned
  transaction).
- `app/slaif_gateway/db/repositories/keys.py`: narrowly typed receipt
  lookup (JSONB containment namespaced by `(source, operation)`, scoped to
  the target owner) and receipt persistence on the NEW target key's
  metadata (`metadata_json`, no DDL).
- `app/slaif_gateway/cli/keys.py`: `keys clone` with `--dry-run PATH` /
  `--execute PATH` (exactly one), explicit validity mode options, fresh
  `--confirm-external-tool-fenced`, and EXACTLY ONE explicit one-time key
  channel for execute (`--show-plaintext`, `--secret-output-file`, or
  `--email-delivery pending/send-now/enqueue`).
- `tests/unit/test_documentation_contract_drift.py`: one justified exact
  allowlist entry for the clone service's read-only consumption of
  `external_tool_policy_contract` (fenced-policy detection only; no runtime
  authority).

Canonical policy semantics are reused unchanged from the 196 export/parser/
create-builder: providers (explicit `null` = unrestricted vs `[]` = deny
all), exact Responses/module identity/grants, nullable lifetime quotas,
nullable rate overrides/window, lazy policy, supported Chat live-burn, and
external policy. Non-default or malformed raw
`responses_streaming_live_burn` source policies are refused (creation
always writes the default), and policy values carrying RECOGNIZED secret
shapes (gateway key text, bearer token, provider key, sensitive
assignment — the existing redaction patterns) are refused with a fixed
safe unsupported-source explanation instead of being emitted or silently
altered (known-shape protection, not universal content sanitization).

## Layers and exact commands

Environment: `/tmp/slaif192-coding-venv` (Python 3.12, editable project).
`PYTHONPATH=app` for all runs. No ambient `DATABASE_URL`; the integration
layer runs against its own owned PostgreSQL 16 container only.

### New unit suites (pure layer, no DB)

```text
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_key_clone_service.py \
  tests/unit/test_cli_keys_clone.py -p no:cacheprovider \
  --junitxml=/tmp/slaif198/unit-clone.xml -q
# 40 passed (19 + 21; 0 failed, 0 errors, 0 skipped), exit 0
```

- 19 service cases (fakes, no DB): strict non-secret plan document with
  source fingerprint and preview; ineligible sources (calibration purpose,
  discovery mode, suspended/revoked, fenced, not-yet-valid, expired)
  refused without mutation/audit; missing target owner/cohort; default
  allowed vs non-default/malformed Responses-streaming live-burn refused;
  recognized secret shapes in kept policy strings refused; fingerprint
  stable under usage drift but moved by configuration change; validity
  modes (copy-source-expiry / duration-from-now / absolute) with
  invalid/expired windows rejected at plan and execute time; tampered plan
  documents (unknown/duplicate fields, bad types, bad fingerprint/UUID)
  rejected; execute happy path (independent target, receipt, pending
  delivery, one clone audit with safe values only); stale plan refused
  before any write; exact repeat returns `already-applied` (no new
  key/secret/audit, no plaintext); completed operation stays identifiable
  after the source is edited; same-operation changed plan refused; fresh
  fenced confirmation required; missing source = not found; source
  became ineligible = refused; canonical semantics (providers absent /
  explicit `null` / `[]`, nullable rate members, unlimited quotas stay
  `None`).
- 21 actual-Typer CLI cases (DB helpers faked): exactly-one mode flag;
  dry-run required flags and per-mode consistency; plan file written 0600
  and never overwritten; JSON output byte-equivalent to the file and
  re-parseable by the same strict schema; dry-run text output safe
  (no policy detail, no secret); service errors surfaced as fixed safe
  codes; execute requires `--reason` and exactly one channel (zero/two
  refused before DB); `--show-plaintext` JSON includes the plaintext
  exactly once; `--secret-output-file` writes 0600 with no plaintext in
  output and refuses an existing file BEFORE any DB call;
  `--email-delivery pending/send-now/enqueue` suppress plaintext and
  report safe delivery/task metadata; send-now failure exits nonzero with
  safe IDs; already-applied repeats never emit plaintext or re-run the
  operation; missing/tampered plan files rejected without DB contact;
  post-commit output failure exits nonzero with safe created-key/secret/
  delivery IDs + recovery guidance and never re-clones;
  `--confirm-external-tool-fenced`/`--actor-admin-id` pass-through.

### New owned-PostgreSQL-16 suite

```text
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/integration/test_cli_key_clone_postgres.py -p no:cacheprovider \
  --junitxml=/tmp/slaif198/integration-clone.xml
# 5 passed, 0 failed, 0 errors, 0 skipped, exit 0
```

Ownership discipline (mirrors the 184/185/197 fixtures): a NEW
`postgres:16` container labeled `slaif198a.owner`, bound to 127.0.0.1
only, tmpfs-backed, identity re-inspected AFTER creation and BEFORE
readiness/migration, and removed by exact container ID in `finally`
(verified absent after the run; no ambient/unverified `DATABASE_URL`, no
shared or foreign DB, no apt/HPC/production).

- Student-style source (explicit `null` provider policy = unrestricted,
  unlimited cost, configured token limit, nullable request limit):
  dry-run wrote a 0600 plan and mutated NOTHING (full source column
  snapshot + table counts identical, no audit); execute with
  `--email-delivery pending` created the target with EXACT canonical
  configuration equality (`keys policy export` documents identical),
  independent material (different `token_hash`, `hmac_key_version = 1`,
  IDs), zero usage, no copied replay/ledger rows, `copy-source-expiry`
  window (from execution, to the source's fresh `valid_until`), a bounded
  safe `clone_receipt` on the target (safe UUIDs/fingerprint only — no key
  material), exactly one `gateway_key_cloned` audit with safe values, and
  the source completely unchanged with its planted finalized usage +
  `codex_replay_references` evidence intact.
- Beta-style source (deny-all `[]` providers, cost/token/request limits,
  configured rate members): exact canonical equality including `[]` and
  the rate block; exact repeat returned `already-applied` with no new
  key/secret/plaintext; a same-operation tampered plan was refused with
  `key_clone_plan_mismatch`; unknown-field and >128 KiB plan files were
  rejected before any DB write; source unchanged.
- Forced LATE clone-audit failure (real service path, monkeypatched only
  at the final `gateway_key_cloned` action): the hook observed the new
  target key + receipt + one-time secret already visible in the SAME
  transaction before raising; the CLI exited nonzero and a fresh session
  confirmed the caller transaction rolled back ALL new rows (counts and
  every source column identical; zero persisted receipts for the
  operation).
- TWO separate processes (separate OS processes, separate DB sessions)
  concurrently executing the SAME plan file: statuses were exactly
  `{created, already-applied}` with one shared target; exactly one
  one-time secret, one receipt, and one clone audit for the operation;
  only the created process wrote a secret file; neither output contained
  plaintext. `current_setting('transaction_isolation')` = `read
  committed`, the supported deduplication boundary (a pre-established
  REPEATABLE READ snapshot is documented as unsupported).
- Simulated post-commit mail failure (`--email-delivery send-now` pointed
  at a refused local port 127.0.0.1:1): the commit succeeded, the mail
  failed AFTER commit, the CLI exited nonzero with safe IDs and
  `email_delivery_status = failed` (no plaintext); the exact retry then
  returned `already-applied` with no second key, no plaintext, and no
  auto-resend.

### Gates (focused)

```text
# New + touched unit governance:
PYTHONPATH=app .../python -m pytest \
  tests/unit/test_oap_governance.py \
  tests/unit/test_documentation_inventory.py -p no:cacheprovider -q
# 22 passed (9 + 13), exit 0

PYTHONPATH=app .../python -m pytest \
  tests/unit/test_documentation_contract_drift.py -p no:cacheprovider -q
# 15 passed, exit 0 (after the one justified 198-a allowlist entry)

/tmp/slaif192-coding-venv/bin/python -m ruff check \
  app/slaif_gateway/cli/keys.py \
  app/slaif_gateway/schemas/key_clone.py \
  app/slaif_gateway/services/key_clone_service.py \
  app/slaif_gateway/db/repositories/keys.py \
  tests/unit/test_key_clone_service.py \
  tests/unit/test_cli_keys_clone.py \
  tests/integration/test_cli_key_clone_postgres.py \
  tests/unit/test_documentation_contract_drift.py
# All checks passed (E4/E7/E9/F, line-length 100)

git diff --check            # clean
/tmp/slaif192-coding-venv/bin/python scripts/check_documentation.py
# DOCUMENTATION_CHECK=OK files=125
```

Passed suites were not repeated for display/count formatting; no full
local matrix was run. Normal final-report-head CI (broad gate) remains
required and was PENDING at the time of this record; root independently
owns final-head CI.

## Privacy, atomicity, and concurrency statements

- The plan file, ordinary stdout, JSON, audit rows, and logs never
  contain a complete key, token hash, provider environment name or base
  URL, raw metadata, usage, or replay rows. The one-time plaintext
  exists only in the in-process result and the operator's explicitly
  chosen channel; repeats (`already-applied`) never recover or re-send it.
- Key + one-time secret + pending delivery + receipt + audits commit
  atomically in one caller-owned transaction; late failures roll back all
  new rows (proven in PG). No SMTP, output-file write, or enqueue happens
  before commit. There is no exactly-once SMTP promise; recovery is the
  existing explicit `email send-pending-key` for still-unconsumed
  material, otherwise rotation.
- Deduplication is bounded and honest: it is proven under the PostgreSQL
  default READ COMMITTED isolation (source `FOR UPDATE` lock + per-statement
  snapshot), not by pretending row locks guarantee arbitrary-isolation
  dedup. No schema, uniqueness constraint, or new receipt registry was
  introduced.

## Documentation impact

Required by AGENTS.md §5.1. This objective changed the documented CLI and
schema contracts:

- `docs/cli-reference.md`: new `keys clone` section with actual
  plan → review → execute → repeat/failure-recovery commands, eligibility,
  canonical-equality, fingerprint, validity, fenced-confirmation,
  retry-safety, transaction, isolation-boundary, and no-plaintext-recovery
  semantics; command inventory updated.
- `docs/cli-field-administration.md`: the 198 row moved from
  "Proposed for later objectives" to a new "Implemented in objective 198"
  row (199-205 remain proposed; the full brief and the eleven DoD are NOT
  declared complete — the objective-205 installed-executable-only
  transcript remains mandatory).
- `docs/database-schema.md`: bounded `clone_receipt` JSON contract on
  `gateway_keys.metadata` (JSON only; no DDL change) plus the supported
  READ COMMITTED deduplication boundary.
- `docs/verification/README.md`: this record indexed.

## Limitations

- Synthetic data only: fictional owners/cohorts, fake provider
  configuration, canned routes; no real provider/model contact, no real
  SMTP delivery (send-now targeted a refused local port), no Redis, no
  upstream smoke.
- The objective-205 installed-executable transcript is still outstanding;
  this record does not declare the full brief or the eleven DoD complete.
- No release, RC, production, security, or compliance claim follows from
  this record.
