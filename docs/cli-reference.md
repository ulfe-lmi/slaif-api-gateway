# CLI reference

> **Status:** Current command index
> **Audience:** Gateway operators and maintainers
> **Authority:** Typer command registration in `app/slaif_gateway/cli/`

The `slaif-gateway` CLI manages local Gateway metadata and operator workflows.
Most commands require a migrated PostgreSQL database. Provider, route, pricing,
FX, and usage commands do not imply live provider discovery unless their
description explicitly says so.

Use `slaif-gateway <group> <command> --help` for the complete option contract.
Never put plaintext credentials, keys, passwords, or content into audit reasons
or command-line arguments.

## Bootstrap and database

```text
slaif-gateway version
slaif-gateway db check-config
slaif-gateway db show-url
slaif-gateway db current
slaif-gateway db upgrade
slaif-gateway admin create
slaif-gateway admin reset-password
slaif-gateway admin list
```

`admin create` and `admin reset-password` support password input without placing
the password in shell history. Database URL output is redacted/safe by contract;
review command help before using it in shared terminals.

## Organization records

```text
slaif-gateway institutions create|list|show
slaif-gateway cohorts create|list|show
slaif-gateway owners create|list|show
```

These commands manage the current owner/institution/cohort records. They do not
create provider routes or keys implicitly.

## Gateway keys and templates

```text
slaif-gateway keys create|create-from-template|list|show
slaif-gateway keys suspend|activate|revoke|extend|rotate
slaif-gateway keys set-limits|set-rate-limits|set-chat-streaming-live-burn
slaif-gateway keys reset-usage
slaif-gateway keys policy show|update
slaif-gateway keys external-tools show|update
slaif-gateway templates create-from-calibration
slaif-gateway calibration summarize
```

Plaintext key output is one-time only. Prefer `--secret-output-file` for an
owner-only file or explicitly confirmed plaintext output. Lost keys are rotated,
not recovered. Reserved-counter repair has additional confirmation requirements.

The lazy (waiting) throttling policy is not a CLI flag. It is managed through
the admin dashboard key create/detail forms (the same KeyService and audit
path) and is stored in the key's validated metadata; the CLI key commands do
not read, change, or reset it.

## Providers, routes, pricing, and FX

```text
slaif-gateway providers add|list|show|enable|disable
slaif-gateway providers discover-models|setup-models
slaif-gateway routes add|list|show|enable|disable|import
slaif-gateway pricing add|list|show|disable-model|import
slaif-gateway fx add|list|latest
slaif-gateway bootstrap openai-completions-catalog
slaif-gateway provider-catalog propose
slaif-gateway openai-assisted pricing-proposal|route-proposal
```

`providers discover-models` and confirmed `providers setup-models` can call a
configured upstream `/models` endpoint. Imports and proposal previews are local
metadata workflows unless their dedicated documentation states otherwise.
Pricing and FX rows are operator-reviewed local accounting inputs, not provider
invoice attestations.

## Usage, email, and reconciliation

```text
slaif-gateway usage summarize|export|live-burn-summary
slaif-gateway email test|send-pending-key
slaif-gateway quota list-expired-reservations
slaif-gateway quota list-provider-completed-recovery
slaif-gateway quota list-external-tool-fences|list-external-tool-holds
slaif-gateway quota reconcile-expired-reservations|reconcile-reservation
slaif-gateway quota reconcile-provider-completed|reconcile-external-tool-hold
```

Reconciliation commands default to inspection or dry-run where documented.
Execute modes require explicit confirmation and an audit reason. They use
PostgreSQL evidence and do not call providers to reconstruct an outcome.

## Codex and diagnostics

```text
slaif-gateway codex inspect|profile
slaif-gateway codex upgrade-key-module
slaif-gateway codex rollback-key-module
slaif-gateway codex inspect-profile-file
slaif-gateway codex show-profile
slaif-gateway codex migrate-key-profile
slaif-gateway secrets generate hmac|admin-session|one-time
slaif-gateway secrets validate-env
```

Codex commands apply only to explicitly registered qualification profiles.
Configuration validation reports bounded names/status, never secret values.

`codex upgrade-key-module <key-uuid> --target {0149-v5,0162-v1,0162-v2}
--reason ... [--actor-admin-id <uuid>] [--apply] [--json]` and `codex
rollback-key-module <key-uuid> --from-target {0149-v5,0162-v1,0162-v2}
--reason ... [--actor-admin-id <uuid>] [--apply] [--json]` are the bounded
audited client-module migration pair for pinned Codex keys. Only the six
legal edges (0.149-v4 → 0149-v5, 0149-v4 → 0162-v1, 0162-v1 → 0162-v2, and
the three reverse edges) are accepted; a 0.149-v4 key reaches 0162-v2 only
through the explicit two-hop sequence while quiesced. Any other current
module identity or unsupported selector fails closed with a fixed safe
error. The default is a dry run;
`--apply` writes the `client_module` compatibility metadata and one audit
record in one atomic PostgreSQL transaction. The commands change no schema,
no quota, no key policy, and no route or pricing data. Unexpected failures
render a fixed generic safe error and never echo exception details.

`codex inspect-profile-file <path> [--json]` validates a candidate Codex
0.162 compatibility profile DATA file completely offline (bounded regular
UTF-8 JSON, data revision >= 3, finite validated vocabulary, hard ceilings)
and prints safe facts or a fixed safe rejection with a code; it never
touches the database, network, or the active process profile, so it works
even when a configured active profile file is invalid. `codex
show-profile [--json]` shows the active profile snapshot of this CLI
process bound at bootstrap; a running HTTP server keeps its own bootstrap
snapshot until restart, so the output describes this CLI process only.
`codex migrate-key-profile <key-uuid> --from-version <rev> --from-digest
<hex> --reason ... --target {active,0162-v1,0162-v2}
[--actor-admin-id <uuid>] [--apply] [--json]` moves one exact key between
the active bootstrap profile snapshot and the frozen 0162-v1/0162-v2
legacy tuples: the explicit source must equal the key's current pin (legacy
1/2 sources require the frozen literal digests), the default is a dry run,
`--apply` writes the metadata and one audit record in one row-locked
transaction, a repeated exact target is a no-op with no extra audit, and
same-revision/different-digest drift or a missing configured active profile
fails closed with a safe error.

## Catalog refresh (collect, review, verify, apply)

Bounded catalog refresh: bounded live official-source collection, one typed
proposal bundle, one safe baseline, one sealed one-page report, and the one
explicit atomic `apply` of a reviewed run. The one-command administrator
wrapper `slaif-catalog-refresh` (bootstrap/refresh, built-in read-only
watchdog, exact child exit codes) plus the lower-level `collect`, `review`,
`verify`, read-only `export-baseline`, mutating `apply`, and read-only
`status` commands — Codex research is opt-in (`--research`) and NOT_RUN by
default. Full semantics, the source registry, policy thresholds, sealing,
apply ordering, and exit codes live in
[Catalog refresh (collect, review, and
verify)](catalog-refresh.md).

```bash
# ONE refresh, ONE report: the supported administrator entry point.
# Validates the mode before spawning, runs the read-only collect under the
# standard watchdog (300 s default + 5 s KILL grace; --timeout/--kill-grace
# must be positive), preserves the child exit code, never applies.
slaif-catalog-refresh --mode bootstrap \
  [--providers openai,openrouter] [--models a,b] \
  [--run-root P] [--seal-key P] [--json] \
  [--timeout 300] [--kill-grace 5]

# Refresh against the existing catalog (live read-only baseline export;
# bootstrap is never combined with --baseline-file or --db-url)
slaif-catalog-refresh --mode refresh --db-url postgresql+asyncpg://user@host:5432/dbname \
  [--providers openai,openrouter] [--models a,b] \
  [--run-root P] [--seal-key P] [--json]

# Refresh with the opt-in isolated Codex research fallback
slaif-catalog-refresh --mode refresh --db-url "$DATABASE_URL" \
  --research --research-cli-bin /path/to/codex \
  --research-endpoint https://inference.example.test/v1 \
  --research-model gpt-example --research-auth-env SLAIF_RESEARCH_UPSTREAM_KEY \
  [--research-timeout 120]

# Lower-level entry point: collect the official catalogs now (first install,
# both providers, all eligible models)
slaif-gateway catalog-refresh collect --bootstrap

# Refresh collection against an exported baseline with an explicit selection
slaif-gateway catalog-refresh collect --refresh \
  --providers openrouter --models synth/alpha,synth/beta \
  --baseline-file /path/to/baseline.json

# Refresh collection with the isolated Codex semantic research fallback
# enabled (deterministic parsing stays first; only eligible unresolved
# facts are research candidates; the researcher's only model contact is
# the operator-configured HTTPS endpoint through a task-owned relay)
slaif-gateway catalog-refresh collect --refresh \
  --baseline-file /path/to/baseline.json \
  --research \
  --research-cli-bin /path/to/codex \
  --research-endpoint https://inference.example.test/v1 \
  --research-model gpt-example \
  --research-auth-env SLAIF_RESEARCH_UPSTREAM_KEY \
  [--research-timeout 120]

# Review a proposal bundle against an exported baseline (sealed run output)
slaif-gateway catalog-refresh review /path/to/catalog-refresh.json \
  --baseline-file /path/to/baseline.json

# Review against a live read-only database snapshot
slaif-gateway catalog-refresh review /path/to/catalog-refresh.json \
  --db-url postgresql+asyncpg://user@host:5432/dbname

# First install: explicitly empty baseline
slaif-gateway catalog-refresh review /path/to/catalog-refresh.json --first-install

# Verify a sealed run directory against the runner-owned key
slaif-gateway catalog-refresh verify --run-dir /path/to/run --seal-key ~/.local/state/slaif/catalog-refresh/seal.key

# Export a read-only consistent baseline document
slaif-gateway catalog-refresh export-baseline --out /path/to/baseline.json --db-url postgresql+asyncpg://user@host:5432/dbname

# Apply the reviewed plan of one sealed READY/READY_WITH_WARNINGS run
# atomically (explicit operator confirmation; one effective instant; one
# durable application record). Never wrap this in the collect watchdog.
slaif-gateway catalog-refresh apply --run-dir /path/to/run \
  --db-url postgresql+asyncpg://user@host:5432/dbname \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key \
  --confirm --actor "ops:alice" --reason "apply reviewed openrouter refresh" \
  [--admin-id UUID] [--ack-warnings new_model_exposure] [--json]

# Read-only committed-outcome visibility (lock-free; never mutates or
# blocks writers)
slaif-gateway catalog-refresh status --run-dir /path/to/run \
  --db-url postgresql+asyncpg://user@host:5432/dbname \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key [--json]
```

Collect exit codes: 0 READY, 10 READY_WITH_WARNINGS, 20 BLOCKED (a blocked
run is always published, labeled by the path actually reached:
`collection not started` when the baseline failed before any retrieval,
`collection attempted and failed before completion` when the retrieval
attempt failed, or the `live collection` wording after a completed
collection, including semantically blocked collects), 65 data error where
no blocked run is published (e.g. an unreadable or invalid
`--baseline-file`), 2 usage error.
Under the documented watchdog prefix a timed-out collect exits non-success
(124 on the TERM timeout, 137 after the KILL grace for a TERM-ignoring
process) and publishes no run: the collect writes nothing during the fetch
phase, publication is one atomic rename at finalization only, so an
interrupted run never reports a fresh READY and never overwrites an older
review. Direct raw collect without the watchdog may exceed the 120-second
cooperative collection target during blocked DNS or a continuous slow
stream (documented limit; no hard total bound is claimed). Review exit codes: 0 READY, 10
READY_WITH_WARNINGS, 20 BLOCKED, 65 data error, 2 usage error. Verify: 0 valid, 30 invalid (including a missing,
non-directory, or symlinked run directory with an otherwise valid key),
65 data error (missing or unsafe seal key; verify never creates keys).
Export-baseline: 0 written, 65 data error (never overwrites output, never
bootstraps empty). Apply: 0 committed (or `already_committed` for a
same-bundle retry, which returns the prior record and never overwrites),
10 unacknowledged apply-time findings (pass each code to `--ack-warnings`),
20 plan not applicable (`apply_state_not_applicable`,
`apply_freshness_blocked`, `apply_no_plan`, `apply_plan_unsupported`,
`apply_plan_mismatch`), 30 seal/authentication failure (no database contact
made), 65 blocked execution or data error (`apply_target_mismatch`,
`apply_bootstrap_not_empty`, `apply_baseline_stale`, `apply_admin_unknown`,
`apply_duplicate_record`, `apply_supersession_guard_failed`, `apply_database_error`,
missing `--confirm`, or blank `--actor`/`--reason`). Status: 0 (committed or
not — the fact is reported), 30 seal/authentication failure, 65 data error.

Filesystem inputs and outputs are handled by a descriptor-anchored,
symlink-free boundary: symlinked bundle/baseline/key paths, FIFOs and
other special files, oversized or growing inputs, and — for the writing commands — run
roots or key parents (`review`) and the output parent (`export-baseline`)
writable by group or other are refused with exit 65
and a safe error that does not echo input content; a symlinked run
directory makes `verify` invalid (exit 30). Runs are published atomically
new-only and never overwritten; `export-baseline` writes only to a
new output path. Full contract:
[Catalog refresh (collect, review, and verify)](catalog-refresh.md#filesystem-trust-contract).

The three review baseline inputs are distinct execution paths with
distinct SQL evidence: `--db-url` performs the live read-only export
itself (SQL executed during this review), `--baseline-file` consumes a
supplied document (SQL was executed historically at that document's export
time, not during this review), and `--first-install` is the explicit empty
baseline (no database read). A label or boolean in the bundle cannot claim
a capture path. `export-baseline` writes one coherent `REPEATABLE READ`
snapshot of the four allowlisted tables, retaining the recognized nested
capability contracts and the allowlisted monetary metadata; it never
writes to the database.

### Offline source input contract

For `review`, the bundle's `sources` entries are replayed offline, never
fetched (a bundle produced by `collect` additionally carries the measured
collection identity, which `review` re-verifies; see
[catalog-refresh.md](catalog-refresh.md#collection-versus-replay-validation-re-verification)). The
report scope is runner-selected: a `review` of a previously collected
bundle is `supplied_collection`, never `live_collection` — the retrieval
claims stay the supplied record's. Only
the registered (provider, source kind) pairs are parsed deterministically:
`openrouter/openrouter_models_api` (official OpenRouter `/models` shape,
per-token USD pricing), `openai/openai_models_api` (identity only),
`openai/openai_pricing_docs`, `openai/openai_models_docs` (bounded docs
tables), and `ecb/ecb_reference_xml` (EUR-based ECB reference-rate XML:
provider `ecb`, model part a currency pair such as `EUR-USD`, official ECB
host, DOCTYPE and external entities rejected). `evidence_b64` must match
the declared `content_sha256` and parse successfully to support required
facts; a matching digest of arbitrary or empty bytes is not content trust
and fails the gate, regardless of any extraction label. Each decoded
snapshot is parsed strictly (duplicate JSON keys, non-finite constants,
malformed rows, and unbounded price cells are code-only errors), and every
proposed field is validated against the sources its own fact declares for
the route's actual upstream model — an unobserved upstream, a wrong
per-field source, or a conflicting supplied observation blocks. An FX fact
binds to an official `ecb/ecb_reference_xml` quote before any currency
normalization (finite positive rate or exact reciprocal within 1e-8, quote
source declared in the fact's provenance, publication date equal to the
quote date); an unbound FX rate is never guessed or used. Selection is
reconciled per model: an unexplained eligible-model omission under an
all-eligible selection blocks; explicit subset exclusions are named in the
report. Full contract:
[Catalog refresh (offline review)](catalog-refresh.md#source-evidence-binding-offline-replay).

## Related documentation

- [Configuration](configuration.md)
- [QUICKSTART](../QUICKSTART.md)
- [First-time operator guide](first-time-operator-guide.md)
- [Provider catalog proposals](provider-catalog-proposals.md)
- [Pricing catalog](pricing-catalog.md)
- [Key templates](key-templates.md)
- [Operator runbooks](runbooks/README.md)

## Complete command inventory

This inventory is checked against Typer registration so new commands cannot be
added without a documentation decision.

```text
slaif-gateway version
slaif-gateway admin create
slaif-gateway admin reset-password
slaif-gateway admin list
slaif-gateway bootstrap openai-completions-catalog
slaif-gateway calibration summarize
slaif-gateway catalog-refresh collect
slaif-gateway catalog-refresh review
slaif-gateway catalog-refresh verify
slaif-gateway catalog-refresh export-baseline
slaif-gateway codex inspect
slaif-gateway codex profile
slaif-gateway codex upgrade-key-module
slaif-gateway codex rollback-key-module
slaif-gateway codex inspect-profile-file
slaif-gateway codex show-profile
slaif-gateway codex migrate-key-profile
slaif-gateway cohorts create
slaif-gateway cohorts list
slaif-gateway cohorts show
slaif-gateway db check-config
slaif-gateway db show-url
slaif-gateway db upgrade
slaif-gateway db current
slaif-gateway email test
slaif-gateway email send-pending-key
slaif-gateway fx add
slaif-gateway fx list
slaif-gateway fx latest
slaif-gateway institutions create
slaif-gateway institutions list
slaif-gateway institutions show
slaif-gateway keys create
slaif-gateway keys create-from-template
slaif-gateway keys list
slaif-gateway keys show
slaif-gateway keys suspend
slaif-gateway keys activate
slaif-gateway keys revoke
slaif-gateway keys extend
slaif-gateway keys set-limits
slaif-gateway keys set-rate-limits
slaif-gateway keys set-chat-streaming-live-burn
slaif-gateway keys reset-usage
slaif-gateway keys rotate
slaif-gateway keys policy show
slaif-gateway keys policy update
slaif-gateway keys external-tools show
slaif-gateway keys external-tools update
slaif-gateway openai-assisted pricing-proposal
slaif-gateway openai-assisted route-proposal
slaif-gateway owners create
slaif-gateway owners list
slaif-gateway owners show
slaif-gateway pricing add
slaif-gateway pricing list
slaif-gateway pricing show
slaif-gateway pricing disable-model
slaif-gateway pricing import
slaif-gateway provider-catalog propose
slaif-gateway providers add
slaif-gateway providers list
slaif-gateway providers show
slaif-gateway providers discover-models
slaif-gateway providers setup-models
slaif-gateway providers enable
slaif-gateway providers disable
slaif-gateway quota list-external-tool-fences
slaif-gateway quota list-expired-reservations
slaif-gateway quota list-external-tool-holds
slaif-gateway quota reconcile-external-tool-hold
slaif-gateway quota list-provider-completed-recovery
slaif-gateway quota reconcile-expired-reservations
slaif-gateway quota reconcile-reservation
slaif-gateway quota reconcile-provider-completed
slaif-gateway routes add
slaif-gateway routes list
slaif-gateway routes show
slaif-gateway routes enable
slaif-gateway routes disable
slaif-gateway routes import
slaif-gateway secrets generate hmac
slaif-gateway secrets generate admin-session
slaif-gateway secrets generate one-time
slaif-gateway secrets validate-env
slaif-gateway templates create-from-calibration
slaif-gateway usage summarize
slaif-gateway usage export
slaif-gateway usage live-burn-summary
```
