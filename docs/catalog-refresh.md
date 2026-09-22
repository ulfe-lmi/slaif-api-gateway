# Catalog Refresh (Offline Review)

> **Status:** Working offline slice of the catalog refresh workflow
> **Audience:** Administrators and maintainers who refresh provider catalogs
> **Boundary:** Offline review, export, and verify only. Live source retrieval
> is unavailable in this version and no refresh or apply command exists in
> this version.

SLAIF catalog refresh is a staged workflow whose end goal is: one refresh,
one trustworthy one-page report, and one explicit audited apply command.
This page documents the **working offline slice** and clearly separates it
from later slices that do not exist yet.

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

- **Live sources and research:** deterministic live provider source
  retrieval (including ECB FX) and isolated Codex-assisted research.
  Nothing in this slice fetches from the network.
- **Audited supersession and apply:** atomic, audited update/supersession of
  existing rows with accounting protections. Until it exists, every
  execution plan is create-only and any represented existing-row change is
  displayed as **BLOCKED** (no apply operation in this version), never
  executed.
- **Shell UX, E2E, and docs completion.**

No refresh or apply command exists. Any tool or script that claims to
"apply" a catalog refresh is out of contract.

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
  URL, retrieval/publication times, extractor identity and method,
  deterministic-versus-semantic extraction, and supporting sources. Trust is
  **derived, never declared**: no caller-supplied "authoritative" label
  exists in the schema; classification (OFFICIAL / REVIEW / BLOCKED) comes
  from (provider, source kind) → official-host rules plus evidence binding;
- source inventory with truncation and required/optional marking, plus
  optional inline evidence bytes bound to the declared content digest
  (without supplied matching evidence a digest is unprovable offline and the
  source classifies as REVIEW, not VERIFIED);
- baseline identity and mode.

The bundle is strict: unknown fields are rejected, identities are unique,
money and FX are exact decimal strings bounded to the database
`Numeric(18,9)` contract (floats, huge exponents, and values beyond nine
decimal places are rejected before any arithmetic), datetimes are
timezone-aware, URLs are bounded and credential-free, and duplicate JSON
keys and non-finite values fail. A bundle can never carry a caller-supplied
READY state, confidence percentage, counter, or validator result: all of
those are recomputed deterministically from the facts. Source and evidence
content is data, never instructions, HTML, or an authority grant.

### Source evidence binding (offline replay)

Supplied source evidence is **parsed, never believed**. A matching content
digest of arbitrary bytes — even `{}` or an unrelated page — is not content
trust: it only proves the bytes match the declared digest.

**Registered parsers.** OFFICIAL classification additionally requires a
reviewed deterministic parser registered for the exact
(provider, source kind) combination, and a successful parse of the
digest-verified bytes:

| Provider | Source kind | Parser | Derives |
|---|---|---|---|
| `openrouter` | `openrouter_models_api` | `openrouter_models_api/v1` | per-model pricing (per-token USD, normalized exactly to per-million), context length, max output, text modality, deprecation |
| `openai` | `openai_models_api` | `openai_models_api/v1` | model identity only (no pricing facts) |
| `openai` | `openai_pricing_docs` | `openai_pricing_docs/v1` | per-model pricing tables with row/field locators |
| `openai` | `openai_models_docs` | `openai_models_docs/v1` | per-model context/output limits |
| `ecb` | `ecb_reference_xml` | `ecb_reference_xml/v1` | EUR-based reference-rate quotes (date, quote currency, rate) |

A "deterministic" extraction label without a registered parser demotes the
source to REVIEW; a registered parser whose parse fails on digest-verified
required source bytes blocks the affected plan
(`source_evidence_parse_failed`).

**Bounded parsing.** Snapshots are bounded (4 MiB decoded, item/row,
model-count, and FX-quote caps; 1 MiB for ECB XML), XML DOCTYPE and external
entities are rejected, and format failures carry a safe code only (they
never echo content).

**Typed observations.** Only typed, locatable observations derived from
successfully parsed snapshot bytes may bind a proposed fact — never copies
of proposed values stamped onto their provenance sources. An observation
carries its source key, row/field locator, canonical value, unit, currency,
and parser identity.

**Canonical comparison.** Money compares in EUR after exact Decimal
conversion with import-contract quantization: `1 == 1.0`, and a USD
observation agrees with a EUR proposal exactly when the bundle's own
verified native-to-EUR FX rate makes them equal. A currency with no
verified rate is never converted with an invented rate: the fact reports
unbound and blocks. Alias, priority, visibility, streaming, and match type
are operator policy, never provider facts, and are never backed by
evidence.

**Independence and corroboration.** Repeated references to one snapshot —
duplicate URLs, aliases to identical bytes, several source records sharing
one digest — count as **one** independent source; corroboration requires
distinct content digests. Contradictions are counted only across distinct
snapshots (one snapshot never contradicts itself).

**FX evidence binding.** An FX fact verifies only against a verified quote
from the ECB publisher (its own source identity: provider `ecb`, kind
`ecb_reference_xml`, EUR-based reference-rate snapshot on an official ECB
host): the supplied quote must equal the fact's rate — or its exact Decimal
reciprocal for EUR-to-native quotations — within 1e-8, and the fact's
publication date must equal the quote's date. An undated or
date-mismatched ECB-backed fact blocks; operator/semantic FX input without
a verified quote is REVIEW-only, never verified.

**Inventory reconciliation.** The per-provider evidence inventory is
derived independently from complete parsed snapshots and reconciled to the
selection: models present in evidence, models selected, and unproposed
candidates (counted, never silently dropped). A selected model absent from
every complete referenced snapshot blocks
(`source_evidence_model_missing`); a duplicate model ID inside one snapshot
is REVIEW.

**Exact offline scope.** Evidence assessment is an **offline replay of
supplied snapshots**: snapshot origin and retrieval claims (`retrieved_at`,
`published_at`) are caller-supplied labels assessed against freshness
policy; they are not authenticated retrievals. This version performs no
network I/O.

**Versioning note.** The catalog refresh subsystem is not yet merged into
`main`: `schema_version` stays `1` within the subsystem, and
`renderer_version` is bumped per reviewed report/evidence-contract change
(`180.1` adds the source-evidence binding contract and its report
sections).

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
- free-form notes and unrelated metadata are **not exported at all**: the
  export is a field-specific allowlist (route/pricing/FX financial facts,
  validity windows, capability booleans). There is no redaction regex and no
  shape-bounded free text — ordinary private content in database notes or
  metadata cannot survive into the document;
- the `content_sha256` field is an **integrity check**, not
  "self-authenticating": it covers the canonical target identity plus rows
  (never the export timestamp), and `load`/`review` recompute and reject
  mismatches. It detects later modification; it is not authentication and
  not proof that the baseline is current. `sql_checked` records that SQL was
  executed **when the document was exported** (a historical capture fact);
  a review that consumes the document from a file states that separately. A
  stale or tampered baseline file is a data error, not a valid baseline.

Connection failure never becomes an empty bootstrap. The report always shows
baseline mode, baseline age, target identity (without credentials), whether
SQL was executed at the historical document export, and whether SQL was
executed during the current review.

## Deterministic readiness

Overall state is exactly one of `READY`, `READY_WITH_WARNINGS`, `BLOCKED`.
Warning severity is exactly `BLOCKER`, `REVIEW`, or `INFO`. Structural
evidence is `VERIFIED`, `REVIEW`, or `BLOCKED`. No probability, confidence
score, or model judgment may set state.

**State model.** A genuinely unchanged row is a no-op: it is excluded from
the mutation plan and the executable artifacts and carries no gate impact, so
a true no-change refresh is `READY` (NO CHANGES) with zero mutations. An
actually **changed** existing row requires an update/supersession that no
create-only executor can run, so it is an excluded mutation that makes the
overall state `BLOCKED` (its apply operation does not exist in this
version). `READY_WITH_WARNINGS` requires at least one REVIEW finding and no
blockers. Gate failures are first-class findings: every `BLOCKED`/`REVIEW`
gate appears in the warning list and counts, so `BLOCKED` is never shown
with zero blocking issues. Executable import artifacts contain only permitted
create rows; excluded, updated, and duplicate rows never leak into them
while full facts remain in the bundle and report.

Versioned operator policy defaults (deterministic, configurable per bundle
policy block, tested at their exact boundaries; the offline reference time is
the bundle `generated_at` — a future live apply re-checks freshness against
its own clock):

| Rule | Boundary (exact) |
|---|---|
| Price movement review | relative change > 25% (exact 25% is not a review) |
| Zero transition | any zero ↔ non-zero crossing is REVIEW, never a percentage (no division by zero) |
| FX movement review | normalized-pair relative change > 3% (exact 3% is not a review) |
| Source retrieval age | age < 24 h fresh; 24 h ≤ age ≤ 72 h REVIEW; age > 72 h BLOCKED |
| FX publication age | age < 3 calendar days fresh; 3 ≤ age ≤ 7 days REVIEW; age > 7 days BLOCKED |
| Future/inconsistent timestamps | BLOCKED |

FX direction: the canonical import-ready pair is **native currency → EUR**,
the exact pair the runtime `PricingService.convert_to_eur` lookup uses
(`find_latest_rate(base_currency=native, quote_currency=EUR)`). A supplied
`EUR → native` quotation is reciprocated deterministically with `Decimal`
and explicit 9-decimal precision, recorded as **derived** (with its source
pair) and never silently relabeled; direct and reciprocal facts for the same
pair must agree within 1e-8 or the run blocks. Baseline current prices and
rates mirror the active lookup: disabled rows excluded, strict
`valid_from ≤ t < valid_until`, no fallback to expired/future rows, and
ambiguous overlapping active rows are reported instead of inventing a
before-value. Currencies are compared before any delta; zero-crossings are
explicit states, not percentages.

Blocking conditions include: any actually-blocked proposed mutation
(update/supersession excluded from a create-only plan), missing required
pricing dimensions, unknown/ambiguous units, currency inconsistency for a
selected model, contradiction between independently represented source
observations, explicitly selected required model missing, truncated required
source, blocked FX pairs, off-host/unsupported source provenance, supplied
evidence contradicting its declared digest, failed deterministic parsing of
digest-verified required evidence, proposed financial facts that do not
match any parsed official snapshot observation (or have no supporting
observation), a selected model absent from every complete parsed snapshot,
unbound FX rates, and FX facts not bound to a verified reference quote. Model disappearance
(a complete, non-truncated source omits a baseline model) is a REVIEW
finding with retain-local, no-delete semantics — an outage or truncated
retrieval is never counted as disappearance.

All counts are recomputed from the inventory and row dispositions:
considered = ready + changed + excluded + blocked/incomplete + disappeared +
deprecated + not-fetched; **ready = new + unchanged** (changed rows are not
ready); prior-baseline missing or deprecated models are tracked separately.
A no-change refresh is a truthful NO CHANGES result, not an invalid
import.

## The one-page report (`REVIEW.html`)

`REVIEW.html` is static, standalone UTF-8 with inline CSS and native
`<details>`/`<summary>`: no external JS/CSS/fonts/images, no JavaScript, no
network fetches, print-friendly, and safe on an ordinary laptop width. All
data is escaped; evidence links are allowlisted; a restrictive CSP is added
as defense-in-depth.

The first screen prioritizes the decision: overall state and why; blocker
and REVIEW finding counts; selected scope (providers, model filter) and
baseline (mode, target, SQL-evidence note); a compact per-provider
change/completeness summary; the **create-only execution plan** (visually
blocked when any plan is excluded/blocked); FX current/proposed/delta/date;
aggregated important findings, including a compact source-evidence line
(how many proposed facts are bound to parsed observations, review-only
facts, and the evidence inventory); the full gate checklist (sources,
schema, pricing completeness, pairing, unsupported rows, unusual changes,
completeness, and the routes/pricing/FX execution-plan gates); and the
recomputed counts. A compact run identity line stays visible; expanded
technical identifiers (revisions, artifact digests) live in a details
section. The main content is **what changed**: price tables with old/new
values, units, currencies, and signed percentages; route tables with current
→ proposed values and the reason (no apply operation exists in this
version); FX tables with current/proposed/delta/source/publication date,
including derived-reciprocal markers. Everything else — new/changed/
disappeared models, excluded rows and reason counts, collapsed unchanged
rows, field provenance with derived (never declared) source classification,
the expanded source-evidence section (per-source parse status with the
registry parser and content digest prefix, the exact parsed observations
that bound each proposed fact with independent-source counts, FX facts
bound to verified reference quotes, and the reconciled evidence
inventory), every warning, full validator outputs, and the exact proposed
import rows — is inside the same file, on demand. The detailed evidence files
(`validation.json`, TSV/JSON artifacts, manifest, receipt) exist for
machines and audit; a human decision never requires opening them.

## Sealing and reproducibility

Every review run is sealed with a local HMAC-SHA256 receipt over the exact
canonical bundle, evidence inventory and digests, generated proposal bytes,
validation results, report, and provider/profile/policy/baseline
identities. The seal key is runner-owned:

- lives **outside** the run directory (enforced by the CLI);
- is created race-safe (the winner completes a private temp file and
  publishes it with an atomic link, so the final path only ever holds a
  complete key; concurrent initializers reuse the verified key or fail)
  with mode `0600` and is never silently overwritten;
- must never be a provider, session, or other runtime key;
- `verify` requires an existing key and never creates one; it never writes
  and never re-signs mutated input.

The seal proves local integrity and correspondence between the report and
its inputs. It is a local trust scope: an administrator who controls the key
can re-seal, and future researchers must never receive the key. Rotate the
key when trust boundaries change; old runs verify only against the key that
sealed them.

Tampering fails closed: altering any content file, the manifest, or the
receipt — including coordinated tampering that recomputes all ordinary
digests from local knowledge — fails verification without the sealing
authority. Publication is immutable: a run is built in a **private staging
directory** and published with one atomic directory rename (new-only,
refuses existing output), so a failure leaves nothing complete-looking at
the final path; manifest paths are strict relative regular files with no
symlink components (leaf, parent, or dangling), traversal, or
size/depth escapes, and every read is bounded through an `O_NOFOLLOW`
descriptor with an `fstat`-fixed size.

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
  research; live source retrieval is unavailable in this version.
- Apply is unavailable: represented existing-row changes are displayed,
  their execution plans are blocked, and no refresh or apply entry point
  exists in this version.
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
