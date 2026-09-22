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
slaif-gateway secrets generate hmac|admin-session|one-time
slaif-gateway secrets validate-env
```

Codex commands apply only to explicitly registered qualification profiles.
Configuration validation reports bounded names/status, never secret values.

## Catalog refresh (offline review)

Bounded offline catalog refresh: one typed proposal bundle, one safe
baseline, one sealed one-page report. Offline review, verify, and read-only
export only — live source retrieval is unavailable in this version and there
is no refresh or apply command in this version. Full semantics, policy
thresholds, sealing, and exit codes live in
[Catalog refresh (offline review)](catalog-refresh.md).

```bash
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
```

Review exit codes: 0 READY, 10 READY_WITH_WARNINGS, 20 BLOCKED, 65 data
error, 2 usage error. Verify: 0 valid, 30 invalid, 65 data error.
Export-baseline: 0 written, 65 data error (never overwrites output, never
bootstraps empty).

Filesystem inputs and outputs are handled by a descriptor-anchored,
symlink-free boundary: symlinked bundle/baseline/run/key paths, FIFOs and
other special files, oversized or growing inputs, and run roots or key
parents writable by group or other are refused with exit 65 and a safe
error that does not echo input content. Runs are published atomically
new-only and never overwritten; `export-baseline` writes only to a
new output path. Full contract:
[Catalog refresh (offline review)](catalog-refresh.md#filesystem-trust-contract).

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

The bundle's `sources` entries are replayed offline, never fetched. Only
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
slaif-gateway catalog-refresh review
slaif-gateway catalog-refresh verify
slaif-gateway catalog-refresh export-baseline
slaif-gateway codex inspect
slaif-gateway codex profile
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
