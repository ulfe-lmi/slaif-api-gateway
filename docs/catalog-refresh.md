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
source to REVIEW; a required source whose digest-verified bytes fail
deterministic parsing blocks the affected plan
(`source_evidence_parse_failed`) **regardless of the extraction label** — a
semantic label is not evidence and not a waiver, and an optional failing
source is REVIEW-classified.

**Strict snapshot parsing.** Each decoded snapshot is parsed strictly at
every nesting level, not merely the outer bundle: duplicate JSON object keys
and non-finite constants (`NaN`, `Infinity`) are rejected with code-only
errors (`duplicate_key`, `non_finite_constant`); raw row structure is
validated with original row indices preserved *before* any reused pure
helper runs, so a malformed row or invalid model id is a format error
(`malformed_row`, `invalid_model_id`) that never disappears through
filtering; and raw decimal price cells are bounded in digits and exponent
before any conversion helper is called, so hostile exponents are rejected
code-only (`invalid_price`) instead of triggering huge allocations or
uncaught decimal errors. OpenAI model rows are iterated on the raw payload,
so duplicate model ids are preserved for the conflict checks below rather
than erased by a set/dict helper. XML stays offline, with DOCTYPE and
external entities rejected.

**Bounded parsing.** Snapshots are bounded (4 MiB decoded, item/row,
model-count, and FX-quote caps; 1 MiB for ECB XML), XML DOCTYPE and external
entities are rejected, and format failures carry a safe code only (they
never echo content).

**Typed observations.** Only typed, locatable observations derived from
successfully parsed snapshot bytes may bind a proposed fact — never copies
of proposed values stamped onto their provenance sources. An observation
carries its source key, row/field locator, canonical value, unit, currency,
and parser identity.

**Per-field declared-source binding.** Provider facts bind to the effective
provider **and the route's actual upstream model** (plus the applicable
endpoint/pricing context): a public alias is local routing policy, not an
alternative provider model whose price can be borrowed. The valid alias
case remains — public `B` → observed upstream `A` uses `A`'s evidence when
the evidence explicitly supports `A` — while public `A` → unobserved or
different `B` may not use `A`'s prices, and a proposal may not carry the
price of another catalog name that happens to exist in the same snapshot.
Each financial/capability/limit field is validated against the sources its
own fact declares: referenced-but-wrong field/model/provider evidence
blocks (`source_evidence_reference_mismatch`, `source_evidence_unsupported`,
`source_evidence_value_mismatch`), and a match that exists only in an
undeclared source is never silently adopted. Authoritative conflicts are
detected across **all** official observations for the provider/upstream/
field context, so a proposal cannot hide a conflicting supplied
observation by omitting the conflicting source from its field references
(`source_observations_contradict`). A selected model absent from the
complete parsed snapshots of its declared sources blocks
(`source_evidence_model_missing`). Only OFFICIAL-classified observations
can verify a fact; operator input and semantic provenance never do, and an
operator-input mirror of a model ID in a second provider is not provider
evidence.

**Effective proposal eligibility.** Eligibility for a capability is
decided from the single derived contract the emitted import path would
actually store, not from the flat declared keys alone. One deterministic
mapping takes the proposal's flat standard capability keys to the actual
runtime `chat_completions` shape, and the same derived intent drives the
emitted import bytes, the evidence requirements, the before/after
comparison, and the rendered rows — nothing else grants or compares
capability meaning. For a **new** standard route the derived block is the
documented standard scope (text plus the declared streaming intent) plus
any other standard key the proposal explicitly declares; the create never
turns on permissions the proposal did not request, and undeclared runtime
defaults stay runtime-denied. For an **existing** row the reviewed
baseline block is the base and only the explicitly declared intent is
overlaid: omitted approved fields — including explicit denials — are
preserved, so a partial proposal is an honest no-op and an explicitly
requested capability change is shown as a change (create-only behavior
preserved). An explicit `text: false` therefore narrows the executable
surface and binds to the provider's observed facts like any other field:
an audio-only observation agrees with the declared denial (no invented
mismatch) yet still cannot yield an executable ordinary text route, and a
route that would be created without text is blocked as not a usable
standard text candidate rather than silently enabled
(`text_disabled_route`). A proposal that declares a streaming capability
contradicting its own `supports_streaming` column is rejected explicitly
(`streaming_intent_conflict`), never resolved by a silent precedence.
Generated route and pricing rows carry the recognized runtime metadata
shape only — no stray flat storage keys, and no proposal-internal state
(dimension blobs, source timestamps) in row metadata — so rows created
from a confirmed import survive the next baseline export and refresh as an
honest unchanged/no-op result.
Provider-observed deprecation is surfaced conservatively even when the
proposal boolean defaults false: the affected proposal is blocked with a
retain-local disposition (the local row is retained; no auto-delete or
auto-disable). Absent source information is never invented into false
evidence: a snapshot without a deprecation or modality fact emits no
observation for that field.

**Canonical comparison.** Money compares in EUR after exact Decimal
conversion with import-contract quantization: `1 == 1.0` (equal decimal
spellings agree), a recognized unit/currency conversion is explicit, and a
USD observation agrees with a EUR proposal exactly when the bundle's own
verified native-to-EUR FX rate makes them equal. A value whose unit or
currency is missing or unknown, or whose currency has no verified rate,
**cannot be assigned a currency by assertion**: it is its own distinct
marker in comparisons, never silently treated as USD or per-million, and
the affected fact reports unbound and blocks. Alias, priority, visibility,
streaming, and match type are operator policy, never provider facts, and
are never backed by evidence.

**Independence and corroboration.** Independence counts **distinct
official source URLs**: repeated retrievals or aliases of the same official
URL are one independent source, not corroboration — even when the content
hashes of the repeated retrievals differ. Contradiction checks group
observations by (URL, digest): references to identical bytes never
contradict themselves, while distinct content at distinct (URL, digest)
snapshots that disagree on the same field blocks. A single snapshot
contradicting *itself* (conflicting rows for one model id within the same
bytes) also blocks — "only one digest is involved" is not an escape.

**FX evidence binding (authoritative, no semantic escape).** FX used for
import or for source-price currency normalization must first bind to a
parsed authoritative quote **before any normalization happens** — a
candidate rate merely labelled verified is not verified. Every FX fact
must pass, all at once, against the ECB publisher's own source identity
(provider `ecb`, kind `ecb_reference_xml`, EUR-based reference-rate
snapshot on an official ECB host):

- at least one official quote exists for the pair (otherwise the fact
  blocks: `fx_evidence_unbound`, or `source_evidence_unapproved` when only
  unapproved sources carry quotes);
- the fact's rate is a finite positive decimal (`fx_rate_not_finite_positive`);
- the quote equals the fact's rate — or its exact Decimal reciprocal for
  EUR-to-native quotations — within 1e-8, compared **in the fact pair's
  direction** (a reciprocal quote is normalized to the proposed pair's
  direction; the fact is never inverted back)
  (`source_evidence_value_mismatch`);
- the official quotes are compared **as exact Decimal values in the fact
  pair's direction, grouped by publication date and direction**:
  equivalent spellings of the same quote (`1.08` vs `1.080`) never
  fabricate a conflict, genuinely different same-context quotes block
  (`source_observations_contradict`), and same-date quotes supplied in the
  reciprocal direction must agree within the bounded 1e-8 reciprocal
  tolerance in the proposed pair's direction — never by an unstable
  invert-back equality;
- the supporting quote is selected **from the fact's own declared,
  approved, parsed sources**: a rate match at an undeclared source is not
  backing, and an earlier uncited match never shadows a correctly cited
  later quote (`source_evidence_reference_mismatch`) - while the
  same-context contradiction check above still covers ALL authoritative
  evidence for the pair;
- the fact carries a publication date equal to the quote's date
  (`fx_evidence_date_mismatch`).

There is **no semantic/manual escape hatch**: an FX fact pointed at a
docs-page or operator input with no verified quote blocks, its rate is
never used to normalize any price, and affected non-EUR price facts report
`fx_evidence_unbound` instead of converting with a guessed rate. Currency
comparisons in the whole run use only the validated bindings built from
the quotes themselves (direct or exact reciprocal, 9-dp precision).

**Selection reconciliation (every identifier reconciled).** The
per-provider evidence inventory is derived independently from the complete
official parsed snapshots, and every parsed raw identifier must reconcile
into an explicit disposition: selected/proposed; retained local (historical
baseline state, no delete semantics); explicitly excluded by an
explicit-subset selection (named in the report with aggregate counts, no
low-value per-row warning); unsupported-excluded (text modality not
observed); or an **unexplained omission**. An unexplained omission of an
eligible model under an all-eligible selection (empty `model_include`)
**blocks** (`selection_unexplained_omission`); explicit subsets and
conservative profiles are preserved and are not forced to all-eligible.
Desired scope is never defined solely by whichever proposal rows happen to
exist, and no routes are auto-created or local rows deleted to make
counters pass. Within one snapshot, conflicting rows for one model id
block (`source_observations_contradict`), while identical duplicate rows
are deduplicated under an explicit policy with a truthful REVIEW finding
and reconciled counts (`source_duplicate_rows_deduplicated`) — never a
silent disappearance and never a false "blocked" claim. A selected model
absent from every complete referenced snapshot blocks
(`source_evidence_model_missing`).

**Actual observations inside the one report.** The canonical validation
result serializes the actual derived observations that bind each proposed
fact — observed value, unit, currency, exact row/field locator, provider/
upstream/endpoint context, source URL, content digest, parser identity and
retrieval time, and the exact normalized value with its transformation —
plus the bound FX quotes (quote value, locator, URL, digest, parser,
date, and derivation). The report renders them in expandable evidence
details, escaped, bounded, deterministic and printable: no extra files, no
base64 homework for the administrator, and the normal view stays compact.
Seal verification recomputes these same fields from the same deterministic
pipeline; there is no second semantic truth.

**Exact offline scope.** Evidence assessment is an **offline replay of
supplied snapshots**: snapshot origin and retrieval claims (`retrieved_at`,
`published_at`) are caller-supplied labels assessed against freshness
policy; they are not authenticated retrievals. This version performs no
network I/O.

**Versioning note.** The catalog refresh subsystem is not yet merged into
`main`: `schema_version` stays `1` within the subsystem, and
`renderer_version` is bumped per reviewed report/evidence-contract change
(`180.1` adds the source-evidence binding contract and its report
sections; `180.2` closes the remaining source-evidence bypasses: per-field
declared-source and upstream-model binding, authoritative FX quote binding
with no semantic escape, strict per-snapshot parsing with real locators,
per-ID selection reconciliation with an unexplained-omission block,
and the actual rendered observations in the one report; `180.3` adds
baseline metadata preservation — nested capability projection with opaque
unrepresented fingerprints, allowlisted monetary metadata mirroring the
runtime contracts, and value-based `Numeric(18,9)` spelling rules, the
consistent-snapshot proof under a committing writer, and the truthful
capture-path SQL evidence; `180.4` closes the proposal round-trip and
comparison gaps — the single derived capability contract (conservative
create scope for new rows; declared-intent-only overlay over the reviewed
baseline for existing rows, preserving omitted approved fields including
explicit denials), metadata-free generated pricing rows, explicit
streaming-intent and text-disabled route findings, numeric FX quote
comparison with (date, direction) context and bounded reciprocal
tolerance, and the exact documented age/movement thresholds (inclusive
24-hour source freshness, calendar-day FX publication age, and exact
25%/3% movement boundaries compared before display rounding)).

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
silent truncation. The whole document is one coherent snapshot: the count
reads and the paginated rows cannot come from different versions, and a
writer that commits while the export is paging must not mix into it
(proven by a test-only barrier at the exporter's real query/page seam —
with a committed writer mid-export the document stays exactly the
pre-commit state, the next export sees exactly the post-commit state, and
the same exporter forced to READ COMMITTED trips the cross-check as a
negative control). The export performs no writes: no audit entries or row
mutations. It exports metadata, not ORM dumps or settings:

- provider **secret environment variable names may be retained (names only)**;
  values, connection strings, keys, token digests, users, sessions, request
  content, and unrelated data are never exported;
- free-form notes and unrelated metadata are **not exported at all**: the
  export is a field-specific allowlist. Capability booleans keep their
  recognized nested runtime structure (the `chat_completions` contract
  block and the other recognized endpoint-family blocks) verbatim; a key or
  value outside the recognized contract is never silently discarded — it
  flags the row `unrepresented` and carries only a safe opaque
  deterministic fingerprint (an identity, not anonymized content), and the
  affected changes are blocked;
- pricing rows retain the **allowlisted monetary metadata the runtime
  consumes**: audio output pricing, Codex long-context together with
  **exactly one** cache-write field (price or multiplier, mirroring the
  runtime contract), and the selected hosted fee with its pinned source.
  Unsupported monetary metadata flags the row `unrepresented` instead of
  enabling a misleading safe-update/no-change claim; historical or
  unselected rows remain preserved;
- money is bounded to the database `Numeric(18,9)` contract **by value, not
  by spelling**: exact decimal strings only (floats rejected), trailing-zero
  spellings of an in-range value are accepted and preserved verbatim
  (`1.0000000000` is value-equal to `1`), and hostile exponents fail with
  code-only errors before any arithmetic;
- FX sources are either a safely sanitized URL (no credentials, query, or
  fragment) or a bounded safe label (`manual`, `ecb`, ...); a legacy local
  label is honest metadata, never authoritative current FX retrieval
  evidence;
- the `content_sha256` field is an **integrity check**, not
  "self-authenticating": it covers the canonical target identity plus rows
  (never the export timestamp), and `load`/`review` recompute and reject
  mismatches. It detects later modification; it is not authentication and
  not proof that the baseline is current. `sql_checked` records that SQL was
  executed **when the document was exported** (a historical capture fact);
  a review that consumes the document from a file states that separately. A
  stale or tampered baseline file is a data error, not a valid baseline.

Connection failure never becomes an empty bootstrap.

**SQL evidence is a property of the execution path, never of a label.**
The report states the actual capture path of this execution:
`first_install` (an explicit first install read no database and no baseline
document exists), `document` (a supplied baseline document carries declared
capture metadata from its own export time — SQL ran historically, not
during this review), or `live_export` (this review command performed the
read-only export, so SQL ran during the review). The capture must agree
with the bundle's declared baseline mode; a supplied boolean or mode label
cannot claim live SQL. `verify` is an offline seal replay: it recomputes
from the sealed bytes, executes no SQL, and says so. The report always
shows baseline mode, baseline age, target identity (without credentials),
and this capture-path note.

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
| Price movement review | exact relative change > 25% (exact 25% is not a review; the ratio is compared before any display rounding) |
| Zero transition | any zero ↔ non-zero crossing is REVIEW, never a percentage (no division by zero) |
| FX movement review | exact normalized-pair relative change > 3% (exact 3% is not a review; compared before display rounding) |
| Source retrieval age | age ≤ 24 h fresh; 24 h < age ≤ 72 h REVIEW; age > 72 h BLOCKED |
| FX publication age | calendar age ≤ 3 days fresh; 3 < age ≤ 7 days REVIEW; calendar age > 7 days BLOCKED (UTC date basis: whole days between the publication date and the reference date; the time-of-day never changes the state) |
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
baseline (mode, target, and the capture path of this execution
with its truthful SQL-evidence note); a compact per-provider
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
that bound each proposed fact — observed value, unit, currency, exact
locator, URL/digest/parser/time, normalized value and transformation —
with declared backing sources and distinct-URL independence counts, FX
facts bound to verified reference quotes with quote locator/URL/digest/
parser/date, and the reconciled evidence inventory with per-provider
selection dispositions and bounded ID lists), every warning, full validator outputs, and the exact proposed
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
