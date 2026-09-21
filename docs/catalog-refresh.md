# Catalog Refresh (Offline Review)

> **Status:** Working offline slice (objective 180 of the catalog refresh thread)
> **Audience:** Administrators and maintainers who refresh provider catalogs
> **Boundary:** Offline review, export, and verify only. No live retrieval and no apply command exist yet.

SLAIF catalog refresh is a staged workflow whose end goal is: one refresh,
one trustworthy one-page report, and one explicit audited apply command.
This page documents the **working offline slice** and clearly separates it
from the planned later slices.

## What exists now (offline)

The implemented entry points are three CLI commands under
[CLI reference](cli-reference.md#catalog-refresh-offline-review):

```bash
slaif-gateway catalog-refresh review <bundle> [--baseline-file FILE | --db-url URL | --first-install]
slaif-gateway catalog-refresh verify --run-dir DIR --seal-key FILE
slaif-gateway catalog-refresh export-baseline --out FILE [--db-url URL]
```

- `review` validates one typed proposal bundle against a baseline,
  recomputes every count, warning, and gate, and publishes **one sealed run
  directory** whose primary artifact is a single self-contained
  `REVIEW.html`. The CLI prints only a compact state summary with the exact
  report path; the report, not the command output, is the review surface.
- `verify` re-checks a sealed run directory (all content bytes, manifest
  digests, and the runner-owned HMAC receipt) and fails closed on any
  mismatch.
- `export-baseline` writes a read-only, consistent, allowlisted PostgreSQL
  baseline document. It never writes to the database and never produces an
  empty bootstrap from a failed connection.

The bounded proposal tooling in
[Provider catalog proposals](provider-catalog-proposals.md) remains the
existing proposal surface; catalog refresh consumes the same route/pricing/FX
parse, validate, classify, and execution-plan functions and does not duplicate
their rules.

## What is planned later (not implemented, do not claim)

- **Live sources and research (objective 181):** deterministic live provider
  source retrieval (including ECB FX) and isolated Codex-assisted research.
  Nothing in this slice fetches from the network.
- **Audited supersession and apply (objective 182):** atomic, audited
  update/supersession of existing rows with accounting protections. Until
  then, every execution plan is create-only and any represented
  existing-row change is displayed as **NOT_SUPPORTED** for apply, never
  executed.
- **Shell UX, E2E, and docs completion (objective 183).**

No refresh or apply command exists. Any tool or script that claims to
"apply" a catalog refresh before objective 182 is out of contract.

## The proposal bundle (`catalog-refresh.json`)

One versioned, typed JSON document carries the proposal **facts and
provenance only**:

- run ID, generation time, schema/renderer/policy revision identities;
- research identities (status `NOT_RUN` is required for this offline slice);
- the standard v1 profile (ordinary text Chat Completions, explicit streaming,
  local-model visibility, no hosted/multimodal/Responses/Codex capabilities);
- provider and model selection (an include filter may select a single model;
  there is no ten-model bootstrap requirement);
- per-field provenance: provider, model, field, value, unit, currency,
  authoritative URL, retrieval/publication times, extractor identity and
  method, deterministic-versus-semantic extraction, and supporting sources;
- source inventory with truncation and required/optional marking;
- baseline identity and mode.

The bundle is strict: unknown fields are rejected, identities are unique,
money and FX are exact decimal strings (floats are rejected), datetimes are
timezone-aware, URLs are bounded and credential-free, and duplicate JSON keys
and non-finite values fail. A bundle can never carry a caller-supplied
READY state, confidence percentage, counter, or validator result: all of
those are recomputed deterministically from the facts. Source and evidence
content is data, never instructions, HTML, or an authority grant.

## Baselines

Three baseline modes are supported:

- **First install:** an explicitly empty baseline marked FIRST INSTALL — NO
  LOCAL BASELINE. No invented before/after values.
- **Exported file:** an explicit previously exported baseline document.
- **Database snapshot:** a live read-only export via `--db-url`.

A read-only export covers exactly four allowlisted tables —
`provider_configs`, `model_routes`, `pricing_rules`, and `fx_rates` —
including validity windows, inside one `REPEATABLE READ` read-only
transaction with keyset pagination and a count cross-check that refuses
silent truncation. It exports metadata, not ORM dumps or settings:

- provider **secret environment variable names may be retained (names only)**;
  values, connection strings, keys, token digests, users, sessions, request
  content, and unrelated data are never exported;
- free-form notes and metadata are redacted and shape-bounded before export;
- the document is self-authenticating: `content_sha256` covers the canonical
  target identity plus rows (never the export timestamp), and `load`/`review`
  recompute and reject mismatches. A stale or tampered baseline file is a
  data error, not a valid baseline.

Connection failure never becomes an empty bootstrap. The report always shows
baseline mode, baseline age, target identity (without credentials), and
whether SQL was actually checked.

## Deterministic readiness

Overall state is exactly one of `READY`, `READY_WITH_WARNINGS`, `BLOCKED`.
Warning severity is exactly `BLOCKER`, `REVIEW`, or `INFO`. Structural
evidence is `VERIFIED`, `REVIEW`, or `BLOCKED`. No probability, confidence
score, or model judgment may set state.

Versioned operator policy defaults (deterministic, configurable per bundle
policy block, tested at their boundaries):

| Rule | Threshold |
|---|---|
| Price movement review | > 25% (exact 25% is not a review) |
| Zero transition | any zero ↔ non-zero crossing is REVIEW, never a percentage |
| FX movement review | > 3% |
| Source retrieval age | > 24 h REVIEW, > 72 h BLOCKED for required sources |
| FX publication age | > 3 calendar days REVIEW, > 7 days BLOCKED |
| Future/inconsistent timestamps | BLOCKED |

Blocking conditions include: missing required pricing dimensions,
unknown/ambiguous units, currency inconsistency for a selected model,
authoritative contradiction, explicitly selected required model missing,
truncated required source, and blocked FX pairs. Model disappearance
(a complete, non-truncated source omits a baseline model) is a REVIEW
finding with retain-local, no-delete semantics — an outage or truncated
retrieval is never counted as disappearance.

All counts are recomputed from the inventory and row dispositions:
considered = ready + excluded + blocked/incomplete; ready = new + changed +
unchanged; prior-baseline missing or deprecated models are tracked
separately. A no-change refresh is a truthful NO CHANGES result, not an
invalid import.

## The one-page report (`REVIEW.html`)

`REVIEW.html` is static, standalone UTF-8 with inline CSS and native
`<details>`/`<summary>`: no external JS/CSS/fonts/images, no JavaScript, no
network fetches, print-friendly, and safe on an ordinary laptop width. All
data is escaped; evidence links are allowlisted; a restrictive CSP is added
as defense-in-depth.

The first screen answers: overall state and why; bootstrap/refresh mode and
target baseline; provider/profile scope; recomputed counts; the ranked
warning summary; and the gate checklist (retrieval, schema, completeness,
pairing, change, unsupported, FX, import gates). The main content is
**what changed**: price tables with old/new values, units, currencies, and
percentages; route tables with current/proposed/reason; FX tables with
current/proposed/delta/source/date. Everything else — new/changed/disappeared
models, excluded rows and reason counts, collapsed unchanged rows, field
provenance, every warning, full validator outputs, and the exact proposed
import rows — is inside the same file. The detailed evidence files
(`validation.json`, TSV/JSON artifacts, manifest, receipt) exist for
machines and audit; a human decision never requires opening them.

## Sealing and reproducibility

Every review run is sealed with a local HMAC-SHA256 receipt over the exact
canonical bundle, evidence inventory and digests, generated proposal bytes,
validation results, report, and provider/profile/policy/baseline
identities. The seal key is runner-owned:

- lives **outside** the run directory (enforced by the CLI);
- is created atomically with mode `0600` and never silently overwritten;
- must never be a provider, session, or other runtime key;
- `verify` requires an existing key and never creates one.

The seal proves local integrity and correspondence between the report and
its inputs. It is a local trust scope: an administrator who controls the key
can re-seal, and future researchers must never receive the key. Rotate the
key when trust boundaries change; old runs verify only against the key that
sealed them.

Tampering fails closed: altering any content file, the manifest, or the
receipt — including coordinated tampering that recomputes all ordinary
digests from local knowledge — fails verification without the sealing
authority. Publication is immutable: a run directory is new-only, atomic,
and refuses to overwrite completed output; manifest paths are strict
relative regular files with no symlinks, traversal, or size/depth escapes.

## Exit codes

| Command | Code | Meaning |
|---|---|---|
| `review` | 0 | READY |
| `review` | 10 | READY_WITH_WARNINGS |
| `review` | 20 | BLOCKED (safe blocked run published when possible) |
| `review` | 65 | data error (unreadable/unparseable input, bad baseline, seal key problem) |
| `review` | 2 | usage error (contradictory options) |
| `verify` | 0 | run verified |
| `verify` | 30 | run failed verification |
| `verify` | 65 | data error (missing key or run directory is a data/usage error; verify never creates keys) |
| `export-baseline` | 0 | baseline written |
| `export-baseline` | 65 | data error (never overwrites output; never bootstraps empty) |

## Limits

- Offline only: this slice makes no network calls and performs no Codex
  research.
- Apply is NOT_SUPPORTED: represented existing-row changes are displayed,
  their execution plans are blocked, and no apply entry point exists.
- The seal is a local integrity tool, not a substitute for GitHub/audit
  authority or protection against a key-holding administrator.
- Baseline export reads four metadata tables; it is not a database backup
  (see [Backup and restore](backup-restore.md)).
- Pricing/FX validity-window lookup and normal finalization behavior are
  unchanged; history protection belongs to the later apply slice.

## Related documentation

- [CLI reference](cli-reference.md#catalog-refresh-offline-review)
- [Provider catalog proposals](provider-catalog-proposals.md)
- [Pricing catalog and bounded overrun](pricing-catalog.md)
- [Database schema](database-schema.md)
