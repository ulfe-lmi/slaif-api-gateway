# Admin: catalog refresh (collect, review, verify, apply)

Operator entry points for the working slice of the catalog refresh
workflow: bounded live official-source collection, offline review,
verification, read-only export, and the one explicit atomic `apply` of a
reviewed run (plus read-only `status`). Codex research remains NOT_RUN.
Full semantics live in
[`docs/catalog-refresh.md`](../../docs/catalog-refresh.md).

## Current entry points

There is exactly one supported way to run this workflow: the CLI.

```bash
# 0) Collect now: bounded official-source retrieval plus review in one
#    invocation; publishes one sealed run directory (REVIEW.html).
#    The supported administrator workflow prefixes the read-only collect
#    with the standard OS watchdog: 300 s default plus a 5-second KILL
#    grace (any explicit positive finite duration may be chosen). The
#    watchdog is never used around review, verify, export-baseline, or
#    any apply:
timeout --kill-after=5 300 slaif-gateway catalog-refresh collect --bootstrap \
  --run-root /var/lib/slaif/catalog-refresh/runs \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key

# 0') Refresh collection against the current baseline (live export)
slaif-gateway catalog-refresh collect --refresh --db-url "$DATABASE_URL" \
  --run-root /var/lib/slaif/catalog-refresh/runs \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key

# 1) (offline alternative) Read-only coherent baseline export: one
#    REPEATABLE READ snapshot of the four allowlisted tables, retaining
#    the recognized capability contracts and the allowlisted monetary
#    metadata; never writes.
slaif-gateway catalog-refresh export-baseline \
  --out /var/lib/slaif/catalog-refresh/baseline.json \
  --db-url "$DATABASE_URL"

# 2) Review a typed proposal bundle against that baseline.
#    Publishes one sealed run directory; the primary artifact is REVIEW.html.
slaif-gateway catalog-refresh review /path/to/catalog-refresh.json \
  --baseline-file /var/lib/slaif/catalog-refresh/baseline.json \
  --run-root /var/lib/slaif/catalog-refresh/runs \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key

# 3) Verify a published run (e.g. after copying it for archival)
slaif-gateway catalog-refresh verify \
  --run-dir /var/lib/slaif/catalog-refresh/runs/<run-id> \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key

# 4) Apply the reviewed plan of one sealed READY/READY_WITH_WARNINGS run
#    atomically: one explicit operator confirmation, one effective instant,
#    one durable application record. Idempotent per reviewed bundle (a
#    retry returns the committed record and never re-applies). Never wrap
#    apply in the collect watchdog:
slaif-gateway catalog-refresh apply \
  --run-dir /var/lib/slaif/catalog-refresh/runs/<run-id> \
  --db-url "$DATABASE_URL" \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key \
  --confirm --actor "ops:alice" \
  --reason "apply reviewed openrouter refresh" \
  [--admin-id UUID] [--ack-warnings new_model_exposure] [--json]

# 5) Read-only committed-outcome visibility (lock-free; never mutates or
#    blocks writers)
slaif-gateway catalog-refresh status \
  --run-dir /var/lib/slaif/catalog-refresh/runs/<run-id> \
  --db-url "$DATABASE_URL" \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key [--json]
```

Exit codes: collect and review 0/10/20/65/2, verify 0/30/65 (a missing or unsafe
run directory with a valid key is 30 — including sealed runs whose
authenticated execution context is missing (sealed before the execution
context existed) or has an unsupported shape or version; a
missing or unsafe seal key is 65), export-baseline 0/65, apply 0/10/20/30/65 (0 = committed or
already committed; 10 = unacknowledged apply-time findings; 20 = plan not
applicable; 30 = seal/authentication failure; 65 = blocked execution or
data error), status 0/30/65 (see the docs page for the tables). A blocked collect run is always published and
labeled by the path actually reached: `collection not started` (baseline
failure before any retrieval), `collection attempted and failed before
completion` (failed retrieval attempt), or the `live collection` wording
(after a completed collection); `review` is always labeled `offline
review`. A
watchdog-timed-out collect exits non-success (124 on the TERM timeout,
137 after the KILL grace for a TERM-ignoring process) and publishes no
run — the finalization-only atomic publication leaves no partial
artifact, never overwrites an earlier run, and an incomplete/unsealed
run cannot be applied. Direct raw collect without the watchdog may
exceed the cooperative 120-second collection target during blocked DNS
or a continuous slow stream (documented; no hard total bound is
claimed). The review's
baseline input is part of the SQL evidence: `--db-url` is a live export
(SQL ran during this review), `--baseline-file` is a supplied document
(it DECLARES a historical SQL export at its export time; consuming the
file does not verify that execution), `--first-install` read no database,
and `verify` replays the sealed bytes without executing SQL.

Collection proposes the flat standard-v1 short-context core text prices
and, only when the source publishes it as an explicit zero, the reasoning
no-charge. The documented OpenRouter `:online` variant (its official
contract states the suffix enables real-time hosted web search for any
model) is excluded by IDENTITY, independent of positive, zero, or missing
`web_search` fees. Eligibility otherwise follows executable billing, not
TSV capacity: models
with positive separately billed reasoning charges, positive per-request
fees, positive hosted-operation charges, published long-context standard
prices (even $0), contextual override tiers, positive cache-write charges,
unknown billing keys, or source sentinels on billable dimensions are
excluded with the exact machine reason, and explicitly selecting one blocks
the run. Refresh preserves local route authority: one flat baseline row
keeps its public alias, match type, priority, enabled/visible/streaming
state, and every approved denial; multiple aliases, mixed
exact+governing-wildcard authority sets, and wildcard routes that
govern the upstream (fixed destination or passthrough pattern) or non-flat
contracts are retained locally as a whole, never reduced or bypassed, and a
baseline
alias still mapped to a present upstream is never reported as disappeared.

## Preparing source evidence (offline replay)

The `collect` command is the live alternative: it fetches the registered
official sources itself and records the measured outcomes in the bundle's
collection identity, which `review` re-verifies. For a supplied bundle,
bundle sources are replayed offline, never fetched. Only the registered
(provider, source kind) pairs are parsed: `openrouter/openrouter_models_api`
(official OpenRouter `/models` shape with per-token USD pricing),
`openai/openai_models_api` (identity only), `openai/openai_pricing_docs`,
`openai/openai_models_docs`, and `ecb/ecb_reference_xml` (EUR-based ECB
reference-rate XML; provider `ecb`, currency-pair model such as `EUR-USD`,
official ECB host). Each source's `evidence_b64` must match its declared
`content_sha256` and parse successfully to support required facts: a
matching digest of arbitrary or empty bytes is not content trust and blocks
the run regardless of any extraction label, each decoded snapshot is
parsed strictly (duplicate keys, non-finite constants, malformed rows, and
unbounded price cells are code-only errors), and repeated references to
the same official URL count as one independent source. Every proposed
field is validated against the sources its own fact declares for the
route's actual upstream model, and conflicting supplied observations block.
FX facts bind to an official `ecb/ecb_reference_xml` quote before any
currency normalization (rate or exact reciprocal within 1e-8, quote source
declared in the fact's provenance, publication date equal to the quote
date); an unbound rate is never guessed or used. Selection is reconciled
per model: unexplained eligible-model omissions under an all-eligible
selection block, while explicit subset exclusions are named in the report.
Details and the exact offline scope:
[catalog refresh documentation](../../docs/catalog-refresh.md#source-evidence-binding-offline-replay).

The seal key is runner-owned, mode `0600`, created only if missing, and must
live outside the run tree. It is a local integrity key: protect it, rotate
it on trust-boundary changes, and never hand it to research or provider
tooling.

Operator notes for the sealed filesystem boundary:

- The seal key file must be a regular file (no symlinks anywhere in its
  path), mode exactly `0600`, owned by the operator running the gateway.
- The run root and the directory containing the seal key must be
  operator-owned and not writable by group or other; the gateway refuses
  unsafe directories (exit 65) instead of fixing permissions.
- Each review publishes exactly one new run directory atomically; an
  existing run directory or file is never overwritten, and `verify`
  never creates or repairs a key.
- The boundary assumes Linux (atomic `renameat2` publication) and
  protects against unprivileged local peers — not against an
  administrator who controls the key or privileged code.

## What does not exist yet

- **No Codex-assisted research.** Isolated Codex research remains NOT_RUN in
  this version. Bundles are produced by the bounded deterministic live
  `collect` or out-of-band and reviewed here.

Do not add shell scripts or dashboard buttons that apply catalog data by
any path other than the explicit `apply` command on one sealed
READY/READY_WITH_WARNINGS run; an honest blocked label is part of the
contract.

## Eventual wrapper contract (planned for a later slice)

When the live-research and audited-apply slices land, the intended
operator surface will be a thin wrapper around the same primitives
documented here:

1. trigger a deterministic live retrieval + research pass;
2. produce one typed bundle with full provenance;
3. run the same offline `review` against a fresh `export-baseline`;
4. print the local report path so the operator opens the single
   `REVIEW.html` in an ordinary browser (the accepted one-command,
   one-static-report architecture — the wrapper must NOT require a new
   management dashboard surface);
5. require the explicit, separately audited `apply` CLI step (documented
   above), which re-authenticates the sealed run and re-validates the
   baseline identity inside the transaction before superseding rows.

The wrapper must never weaken the bundle schema, the readiness
recomputation, the sealing, or the read-only export semantics defined in
`docs/catalog-refresh.md`.
