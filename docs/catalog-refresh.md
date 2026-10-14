# Catalog Refresh (Collect, Review, and Verify)

> **Status:** Working collect/review/verify/apply slice of the catalog
> refresh workflow
> **Audience:** Administrators and maintainers who refresh provider catalogs
> **Boundary:** Bounded live official-source collection (`collect`), offline
> review of supplied or collected bundles, read-only export, verify, and the
> one explicit atomic `apply` of a reviewed run (plus read-only `status`).
> Codex-assisted research is opt-in (`--research`) and NOT_RUN by default.

SLAIF catalog refresh is a staged workflow: one refresh, one trustworthy
one-page report, and one explicit audited apply command. This page documents
the working slice — bounded live collection, offline review, verification,
and the atomic apply of a reviewed run — and clearly separates it from later
slices that do not exist yet.

## What exists now

The implemented entry points are the one-command administrator wrapper
`slaif-catalog-refresh` plus six `slaif-gateway catalog-refresh` commands,
under
[CLI reference](cli-reference.md#catalog-refresh-collect-review-verify-apply):

```bash
slaif-catalog-refresh --mode bootstrap|refresh [--providers openai,openrouter] [--models a,b] \
  [--baseline-file FILE | --db-url URL] [--run-root P] [--seal-key P] [--json] \
  [--timeout S] [--kill-grace S] [--research ...]
slaif-gateway catalog-refresh collect --bootstrap|--refresh [--providers openai,openrouter] [--models a,b] \
  [--baseline-file FILE | --db-url URL] [--run-root P] [--seal-key P] [--json]
slaif-gateway catalog-refresh review <bundle> [--baseline-file FILE | --db-url URL | --first-install]
slaif-gateway catalog-refresh verify --run-dir DIR --seal-key FILE
slaif-gateway catalog-refresh export-baseline --out FILE [--db-url URL]
slaif-gateway catalog-refresh apply --run-dir DIR --db-url URL [--seal-key P] --confirm --actor NAME --reason TEXT \
  [--admin-id UUID] [--ack-warnings CODE,...] [--json]
slaif-gateway catalog-refresh status --run-dir DIR --db-url URL [--seal-key P] [--json]
```

- `collect` performs the bounded live official-source collection in this
  invocation (registered catalog/pricing/model-page/FX endpoints over HTTPS
  with bounded retries, redirects, and byte budgets), builds the proposal
  bundle, and immediately reviews it through the same pipeline as `review`,
  publishing one sealed run directory. Every retrieval outcome — including
  failures — is recorded in the bundle's collection identity and
  re-verified by validation. See
  [Live collection](#live-collection-the-collect-command).
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
- `apply` applies the reviewed plan of one sealed run atomically to
  PostgreSQL: one explicit operator confirmation, one effective instant, one
  durable application record. See
  [Apply](#apply-one-explicit-atomic-command).
- `status` reports the committed apply outcome for one sealed run by its
  canonical bundle identity. It is lock-free read-only and never mutates or
  blocks writers.

The bounded proposal tooling in
[Provider catalog proposals](provider-catalog-proposals.md) remains the
existing proposal surface; catalog refresh consumes the same route/pricing/FX
parse, validate, classify, and execution-plan functions and does not duplicate
their rules.

## One-command administrator workflow (`slaif-catalog-refresh`)

The installed administrator workflow is one read-only command that
produces one sealed report, followed by the separate explicit
[apply](#apply-one-explicit-atomic-command):

```bash
# first install (empty baseline; never combined with a baseline source)
slaif-catalog-refresh --mode bootstrap --run-root /var/lib/slaif/catalog-refresh-runs \
  --seal-key /var/lib/slaif/catalog-refresh/seal.key --json

# refresh against the existing catalog (live read-only baseline export)
slaif-catalog-refresh --mode refresh --db-url "$DATABASE_URL" \
  --run-root /var/lib/slaif/catalog-refresh-runs \
  --seal-key /var/lib/slaif/catalog-refresh/seal.key --json
```

`slaif-catalog-refresh` is a thin wrapper around the installed
`slaif-gateway catalog-refresh collect` command:

- it validates `--mode` (and the mode/baseline-source combination)
  BEFORE the child is spawned;
- it runs the read-only collect under a standard Linux `timeout(1)`
  watchdog (`--timeout`, default 300 s, plus `--kill-grace`, default 5 s,
  both required to be positive) so a stalled collection is cancelled
  without leaving a partial run behind;
- it preserves the child's exact exit code (0/10/20/65, plus 2 for
  usage refusals) and 124/137 when the watchdog cancels a stalled
  collection;
- it never applies, never retries, never opens a browser or server, and
  never starts the Gateway;
- `--research` and its options (`--research-cli-bin`,
  `--research-endpoint`, `--research-model`, `--research-auth-env`,
  `--research-timeout`) pass through to the opt-in
  [isolated Codex research fallback](#isolated-codex-research-fallback-opt-in).

The command works before the Gateway web app is started: it only reads
the configured official sources (or, in `refresh` mode, one read-only
PostgreSQL baseline export), writes one sealed run directory, and prints
the compact state summary with the exact report path. The report, not
the command output, is the review surface. The installed wheel ships the
research task assets, so the command runs identically outside the source
checkout (see
[Installed workflow qualification](verification/catalog-refresh-installed-workflow.md)).

## First install and operation (installed wheel)

The workflow is a set of installed CLI commands; it works before the
Gateway web app is started (no running Gateway is required).

Supported versions/limits for this surface:

- Python 3.12+ (the wheel is built with standard build isolation; no
  dev `PYTHONPATH` or editable install is needed or supported for
  operation);
- PostgreSQL 16+ for `refresh` (live baseline export) and `apply`
  (migrations run from the source checkout's Alembic configuration —
  the wheel does not ship `migrations/`);
- Linux `timeout(1)` on `PATH` for the one-command wrapper watchdog;
- one profile (`standard-v1`), two providers (`openai`, `openrouter`).

Executable fresh-install path (owned temporary environment):

```bash
# 1) fresh checkout of the implementation head
git clone --no-hardlinks https://github.com/ulfe-lmi/slaif-api-gateway /tmp/slaif-install
cd /tmp/slaif-install && git checkout --detach <implementation-head-sha>

# 2) build the wheel (standard build isolation) and install it into a
#    clean environment (no dev PYTHONPATH, no editable install)
python3 -m venv /tmp/slaif-install-venv
/tmp/slaif-install-venv/bin/pip wheel . --no-deps -w /tmp/slaif-dist
/tmp/slaif-install-venv/bin/pip install --no-cache-dir /tmp/slaif-dist/slaif_api_gateway-*.whl

# 3) one explicit, consistently configured database target (persisted for
#    migration, refresh, and apply below)
export DATABASE_URL="postgresql+asyncpg://user:pass@127.0.0.1:5433/slaif"

# 4) owned PostgreSQL 16+ (your deployment's normal setup), then run the
#    schema migrations from the SOURCE CHECKOUT (the wheel does not ship
#    migrations/):
cd /tmp/slaif-install
/tmp/slaif-install-venv/bin/python -m alembic upgrade head
```

Owned run-root and seal-key parent preparation (first install):

```bash
# run root: an OPERATOR-WRITABLE owned path, not group/other-writable.
# (The CLI refuses unsafe directories instead of fixing permissions; a
# system-wide path such as /var/lib/slaif/... requires a documented
# ownership setup, e.g. chown to the operating user.)
mkdir -p -m 0700 ~/.local/state/slaif/catalog-refresh/runs

# seal key parent: the DEFAULT seal-key parent (~/.local/state/slaif/
# catalog-refresh/) may be ABSENT on a first install — create it owned
# with restrictive permissions. The CLI creates the seal key file 0600
# if missing; it never repairs permissions of pre-existing directories.
mkdir -p -m 0700 ~/.local/state/slaif/catalog-refresh
```

Then the one refresh and the separate explicit apply. The wrapper
resolves its `slaif-gateway` child from PATH, so the same installed
venv must be on PATH for the wrapper invocation (activate it, or pass
`--cli-bin /tmp/slaif-install-venv/bin/slaif-gateway` explicitly):

```bash
source /tmp/slaif-install-venv/bin/activate
slaif-catalog-refresh --mode bootstrap \
  --run-root ~/.local/state/slaif/catalog-refresh/runs \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key --json
# ... review the sealed REVIEW.html ...
slaif-gateway catalog-refresh apply \
  --run-dir <run_dir> --db-url "$DATABASE_URL" \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key \
  --confirm --actor <identity> --reason <reason> \
  [--ack-warnings <code>[,<code>...]] --json
```

The installed workflow qualification (fresh-clone wheel environment,
owned PostgreSQL, exact commands and artifacts) is recorded in
[Installed workflow qualification](verification/catalog-refresh-installed-workflow.md).

## What is planned later (not implemented, do not claim)

- **Interactive shell UX** beyond the one-command wrapper (watch modes,
  TUI review, scripted multi-run orchestration) is not implemented.

The only in-contract apply path is the explicit
[apply](#apply-one-explicit-atomic-command) command on one sealed
READY/READY_WITH_WARNINGS run. Any other tool or script that claims to
"apply" a catalog refresh is out of contract.

## Live collection (the `collect` command)

`collect` is the bounded live-source slice of this version: one invocation
fetches the registered official sources, parses them with the registered
deterministic parsers, builds the standard-v1 proposal bundle, and runs the
identical review pipeline (validation, seal, one-page report) as `review`.

```bash
# First install: explicitly empty baseline, both providers, all eligible models
slaif-gateway catalog-refresh collect --bootstrap

# Refresh against an exported baseline, one provider, explicit selection
slaif-gateway catalog-refresh collect --refresh \
  --providers openrouter \
  --models synth/alpha,synth/beta \
  --baseline-file /var/lib/slaif/catalog-refresh/baseline.json

# Refresh against a live read-only database snapshot
slaif-gateway catalog-refresh collect --refresh --db-url "$DATABASE_URL"
```

Exactly one of `--bootstrap` / `--refresh` is required; `--refresh` requires
`--baseline-file` or `--db-url` (or `DATABASE_URL`). `--profile` is
`standard-v1` (the only profile in this version), `--providers` is a
non-empty subset of `openai,openrouter`, and `--models` is an optional
explicit selection (a single model is a valid selection). Exit codes:
0 READY, 10 READY_WITH_WARNINGS, 20 BLOCKED — a blocked collect run is
always published, labeled by the path actually reached (`collection not
started` before any retrieval, `collection attempted and failed before
completion` for a failed retrieval attempt, the `live collection` wording
only after a completed collection; see [Stage wording and execution
identity](#stage-wording-and-execution-identity)) — 65 data error (input
problems where no blocked run is published, e.g. an unreadable or invalid
`--baseline-file`), 2 usage error.

### The bounded official source registry

Collection fetches only these registered endpoints, over HTTPS, on the
approved host families:

| Provider | Source kind | URL (exact path family) | Body cap |
|---|---|---|---|
| `openrouter` | `openrouter_models_api` | `https://openrouter.ai/api/v1/models` | 4 MiB |
| `openai` | `openai_pricing_docs` | `https://developers.openai.com/api/docs/pricing.md` | 512 KiB |
| `openai` | `openai_models_docs` | `https://developers.openai.com/api/docs/models.md` | 512 KiB |
| `openai` | `docs_page` | `https://developers.openai.com/api/docs/models/<slug>.md` (slug = URL-quoted model ID, no raw separators in the segment) | 256 KiB |
| `ecb` | `ecb_reference_xml` | `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml` (only when a proposed non-EUR price needs FX) | 1 MiB |

Retrieval guarantees (enforced before the first byte is read, and re-applied
to **every attempted URL, including each redirect target and every cache
reuse**):

- HTTPS only, no credentials in the URL, no non-default ports, **no query,
  no fragment**, and the exact registered path family for the provider and
  source kind — a 3xx to any other host, path, or query is refused, never
  followed;
- a public-destination DNS guard runs before every request and every
  redirect hop: only **global-unicast** destinations are accepted (positive
  `is_global` classification in addition to explicit loopback/private/
  link-local/reserved/multicast/unspecified exclusions — notably RFC 6598
  shared address space, documentation ranges, and NAT64 ranges are
  refused), and a **mixed** answer set (any global-unicast address together
  with any other one) is refused as a whole, never filtered down to its
  global subset; resolver failures are safe code-only failures; the lookup
  is ordinary and in-process (trusted host/resolver, 181-h R1) and is
  followed by a cooperative checkpoint, and the ACTUAL connect re-runs the
  same vetting on its own answer set;
- manual redirects are bounded to 3, with relative locations resolved
  RFC 3986-style against the current URL and re-validated;
- a 429 with a finite `Retry-After` of at most 30 s is retried (the
  wait is bounded by the remaining collection target and checkpointed
  after the wait); an oversized or non-finite `Retry-After` is never
  waited on; 5xx and transport errors retry up to 3 total attempts;
- bodies are read as bounded returned chunks against the per-kind
  byte cap above (a mid-stream overflow fails with `body_too_large`, or —
  when it crosses the whole-invocation byte budget first — the crossing
  chunk is debited in full and the invocation is terminally exhausted); a
  crossing chunk is bounded by the delivered chunk, never by an exact
  network/TLS/header byte quota (181-h R2); `Content-Length` is never
  trusted;
- the transfer encoding is **identity only**: the client sends
  `Accept-Encoding: identity`, any other `Content-Encoding` is refused
  BEFORE any decoding or expansion, and bodies are read as raw wire bytes
  with no decoder ever constructed (so a compressed body can never expand
  before refusal);
- the whole invocation runs under ONE collection-owned acquisition
  context (see below): a finite attempt budget, a finite body-byte budget,
  a cooperative whole-invocation collection target (181-h R1), and a
  cross-phase URL outcome cache.

#### Transport and budget guarantees (181-f)

**One whole-invocation budget.** `collect_bundle` creates one
`AcquisitionContext` before acquisition starts and passes it through the
catalog phase, the model-doc phase, the ECB phase, and every redirect and
retry. No later fetch phase can reset any allowance. The attempt
budget reserves one unit per attempted iteration (conservatively, before
pre-validation); the recorded *attempts* metadata counts only requests
actually sent (initial request, each redirect hop, each 429 wait, each
5xx/transport retry) — rejected preflight/redirect validation is never
counted as a sent request. One *byte* unit is every RETURNED application
body chunk on a 2xx response — successful reads, interrupted/failed reads,
and overflow reads alike; failures never refund; a chunk returned after
the collection target has passed is still debited (181-h R2). The defaults are
128 attempts and 32 MiB of body bytes per invocation, plus the per-source
caps above. When a remaining budget can no longer cover the next spec, the
run fails closed (`collection_budget_exhausted`) instead of continuing
partially.

**Overflow is debited in full, and exhaustion is terminal.** When a
consumed chunk exceeds the remaining byte budget, the FULL chunk is
debited — the honest deficit is kept in the context (the remaining count
goes negative, never refunded) — and the invocation is marked TERMINALLY
exhausted: no later attempt, read, or fetch phase may use any leftover
credit, and the failure aborts the whole run. A target (deadline)
failure does not hide already-consumed bytes: every RETURNED chunk —
including one that arrives after the target has passed — is debited
BEFORE the failure propagates (181-h R2), and every prior charge remains
recorded.

**A cooperative 120-second collection target, standard per-operation
timeouts, and an operator watchdog (181-h R1, human-approved).** The
context carries a 120-second whole-invocation collection target. The
HTTP client uses ordinary per-operation timeouts (connect/write/pool
10 s, read 30 s — the read timeout bounds inactivity, not total elapsed
time). The target itself is enforced COOPERATIVELY at application
checkpoints — before each new request (headers may already have consumed
it), after every returned body chunk, at phase boundaries, and around
the 429 retry wait — so that once a checkpoint observes expiry, no NEW
application activity starts. This is an approved relaxation of the 181-g
in-library enforcement: it is NOT a hard total elapsed bound and there
is no mid-library cancellation. A blocking in-process DNS lookup (the
ordinary system resolver on the trusted host), a library operation, or a
continuous slow stream can exceed the target. The custom DNS child
process, kill/reap lifecycle, and deadline-wrapped stream of 181-g are
removed with their machinery-specific claims; the trusted host, its
administrator, and the OS resolver are the security boundary. The
documented elapsed-time cutoff for the read-only collect command is the
standard operator watchdog (below).

**Operator watchdog (read-only collect only).** The supported
administrator workflow runs the collect command under the standard OS
job watchdog: `timeout --kill-after=5 300 slaif-gateway catalog-refresh
collect ...` — 300 s plus a 5-second KILL grace by default; the operator
may choose any explicit positive finite duration. The watchdog covers the
READ-ONLY collect command only — never review, verify, export-baseline,
or any apply/imports/database mutation. A timed-out run exits non-success
(124 on the TERM timeout; 137 after the KILL grace for a TERM-ignoring
process); an interrupted run is NEVER a fresh READY and never overwrites
an older run: the collect writes nothing during the fetch phase,
publication is one atomic rename of a private staging directory at
finalization only, so cancellation may produce no final report at all,
and an incomplete or unsealed run cannot later be applied. No fake sealed
BLOCKED report is invented after a SIGKILL and no automatic retry occurs.
The documented qualification drove a stalled mock collect in an owned
subprocess under the installed watchdog (short injected durations, no
private service); the utility is the standard `timeout` from GNU or
uutils coreutils on Linux — no platform matrix or kernel-hard guarantee
is claimed.

**Cross-phase URL outcome cache.** One URL's success OR failure is cached
across phases within the invocation: the captured bytes (or safe failure)
are reused without new retrieval-time claims, duplicate network, or budget
expenditure. Each cached reuse revalidates the planned spec's registry
identity (provider, source kind, model, cap, required flag) and the URL
family before accepting the cached result; an identity mismatch fails
closed (`duplicate_url_planned`). Caller-supplied JSON never owns the
context.

**Vetted connection binding.** The production client's only TCP connection
path is a vetted network backend: on every new connection it resolves the
approved hostname, vets the COMPLETE answer set (every returned address
must be a GLOBAL UNICAST address — positive `is_global` classification in
addition to the explicit loopback/private/link-local/reserved/multicast/
unspecified exclusions, so addresses that are neither private nor global,
notably RFC 6598, are refused), and connects only to those vetted numeric
addresses. TLS then starts on that bound socket with the ORIGINAL hostname
as SNI and the standard verified certificate context — chain and hostname
verification are exactly the library defaults (no TLS bypass, no custom
trust store). A preflight DNS check alone would not be a fix (the
client could resolve independently and bind elsewhere); the connect-time
answer set is the one that is bound, so rebinding between lookups cannot
bypass the decision. Connection reuse reuses sockets a vetted connect
created; retries and redirect hops open new connections that pass through
the same vetting. Environment proxies and other implicit network
configuration are disabled (`trust_env=False` on client and transport);
Unix-domain sockets are forbidden by the backend.

Every retrieval outcome — success or failure — is recorded in the bundle's
**collection identity**: requested and final URL, retrieval UTC time (fetch
time, never publication time), transport status, body size and SHA-256,
attempts, redirects, and for failures a safe code only (no response
bodies, no exception text, no credentials). The recorded `final_url` is
only the LAST VALIDATED SAFE URL (or absent): a rejected redirect target —
one carrying credentials, a query or fragment, an unapproved host, or a
malformed port — never leaves the resolution loop variable and is never
persisted in provenance, metadata, or error text. The identity also
records the
tool and code revision, the profile, the providers, the selection, and the
start/finish window of the collecting invocation.

### Inventory: every observed model reconciled once

Each model the collected sources observed is reconciled exactly once.
Proposed models carry full facts; every other observed model appears in the
collection inventory exactly once with a machine reason code:

| Reason code | Meaning |
|---|---|
| `service_variant` | `:batch` service variant (the canonical chat row is proposed) |
| `deprecated_model` | source deprecation flag set |
| `negative_router_sentinel` | router `-1` pricing sentinel on a billable dimension (the charge cannot be verified; never converted to zero) |
| `missing_limits` | context length and/or max output not published |
| `non_text_modality` | text is not an input and output modality |
| `missing_core_prices` | input and/or output price not representable |
| `no_standard_short_prices` | no standard short-context input+output prices |
| `page_unavailable` / `page_parse_failed` / `page_model_mismatch` | the official model page 404'd, failed strict parsing, or declares a different Model ID |
| `page_no_chat` / `page_no_text` | the model page does not list Chat Completions support / text output |
| `page_price_conflict` | the model page's text prices conflict with the pricing table |
| `explicit_selection_excluded` | observed but not in the explicit `--models` selection |
| `long_context_prices_unrepresentable` | the standard tier publishes long-context prices (even $0 — a published contextual price); the flat short-band proposal cannot bill the model faithfully |
| `contextual_overrides_unrepresentable` | contextual override tiers (e.g. `min_prompt_tokens` blocks) publish prices the flat standard contract cannot represent |
| `cache_write_charges_unrepresentable` | a positive cache-write charge (1h or not) is not billable in the flat standard-v1 contract |
| `unknown_billing_dimension` | a published pricing key outside the recognized billable/observed set; fail-closed |
| `reasoning_charges_unrepresentable` | a positive separately billed reasoning charge; ordinary Chat admission reserves at the output price and no qualified reasoning billing contract is authorized for standard-v1 |
| `request_charges_unrepresentable` | a positive per-request fee; ordinary Chat admission and finalization do not bill an additive per-request fee (that column serves native-module contracts) |
| `hosted_operation_charges_unrepresentable` | a positive hosted-operation charge on an ordinary ID (e.g. `web_search` per call); hosted operations are denied in the profile and no reviewed per-model executable contract proves the charge cannot be incurred |
| `intrinsic_hosted_variant_unrepresentable` | the documented OpenRouter `:online` model variant - a KNOWN INTRINSIC HOSTED IDENTITY: the official model-variants contract states the suffix enables real-time web search for any model, exactly equivalent to the `web` plugin, and marks the variant deprecated in favor of the `openrouter:web_search` server tool; excluded by IDENTITY, independent of positive, zero, or missing `web_search` fees (a zero cost cannot qualify tool authority, and absent fees cannot establish absence of search); one exact documented variant identity, not a model-name classifier |
| `price_below_quantum` | a positive charge quantizes to zero at the 9-dp import contract; excluded rather than stored as a free price |
| `baseline_contract_not_flat` | the stored baseline route contract cannot be proposed flat (a non-flat exact route, a prefix/glob baseline route that governs the upstream under the resolver's destination semantics - a fixed `upstream_model` equal to the upstream, or a passthrough pattern matching the upstream identity - or a MIXED authority set: one or more exact rows together with at least one governing prefix/glob route for the same provider/upstream); the whole authority set is evaluated before any single flat row is chosen; retained locally, all alternatives recorded, never reduced |
| `baseline_multiple_routes` | multiple local route rows (aliases/priorities) for one upstream; alternatives are never reduced; retained locally |
| `baseline_currency_mismatch` | the stored baseline pricing currency differs from the published native currency |
| `index_only_no_standard_prices` | listed in the official models index but no standard short-context Chat pricing is published |

A page 404 or parse failure for an **optional** model page is an observed
incompleteness, never a disappearance and never an outage claim.

### The models index is model evidence

The fetched OpenAI models index is model evidence, not decoration. The
current linked-index format is parsed with a bounded deterministic
extraction: model-page bullets whose link is
`/api/docs/models/<id>.md` — the ID is the page path, **never the display
name** (display names include aliases that differ from API IDs); the
documented specialized-models exception that links elsewhere and declares
`Model ID: \`<id>\`` inline (exactly one such ID is accepted; zero or
more than one deterministically skip the bullet); duplicates across
sections deduplicate to the first occurrence. Non-bullet prose links are
never extracted. Index rows are identity-only (limits and prices come from
the model pages and the pricing document).

Every observed model ID — including index-only IDs with no pricing at
all — receives exactly one explained inventory disposition
(`index_only_no_standard_prices` for the index-only case). The report's
`source_model_counts` records distinct observed source identities per
provider, deliberately distinct from local route/alias rows: a source
catalog is not a route table, and pricing rows are not the entire official
model catalog.

### Collection versus replay (validation re-verification)

A bundle that carries a collection identity is **re-verified, not trusted**:

- `collection_source_unbacked` — every source record needs a successful
  retrieval record with the same URL and matching content digest;
- `collection_retrieval_failed` — every collected provider needs at least
  one successful retrieval of its catalog URL: a source outage is a
  **retrieval failure (BLOCKED), never model disappearance**, and an empty
  bootstrap is never READY;
- `collection_inventory_unsupported` — every inventory entry is re-checked
  against the parsed official evidence and the baseline; a fabricated or
  stale entry blocks the run;
- `collection_empty_bootstrap` — a live collection that fetched its sources
  but proposed no model, route, or pricing is never READY (a refresh
  against an existing baseline may legitimately propose nothing while
  retaining every baseline model);
- billing eligibility is **recomputed** with the shared standard-v1 policy
  from the parsed official evidence for every bundle — live collection and
  offline supplied-bundle replay alike: an ineligible proposal blocks
  (`proposed_row_billing_ineligible`), and a published positive charge that
  the proposal drops or alters blocks
  (`proposed_row_billing_dim_missing` / `proposed_row_billing_dim_mismatch`);
- `alias_route_replaced` — a baseline public alias still mapped to a present
  upstream is never replaced by proposed route names, and no parallel
  upstream-named route bypasses it.

The report scope is decided by the RUNNER-SELECTED context of THIS
invocation, never by the collection field's presence alone, and has three
truthful values: `live_collection` (this invocation performed the bounded
collection; the retrieval claims are its own measurement),
`supplied_collection` (the supplied bundle carries a recorded collection
identity — historical provenance of a prior collection, re-verified
offline), and `offline_replay` (no collection identity at all: supplied or
cached snapshot bytes parsed offline). `review` of a previously collected
bundle is therefore `supplied_collection`: it re-verifies the recorded
identity offline, does not fetch again, and does not claim a new
retrieval — the retrieval claims remain the supplied record's, not this
invocation's, and the review proves extraction consistency against the
supplied bytes, not provider authenticity or current data.

### Stage wording and execution identity

Every `collect`/`review` invocation is labeled by the path it ACTUALLY
reached, and the CLI summary `stage` line and the published report footer
agree (the minimal blocked report's footer carries the same stage). A
label can never claim a retrieval that was not performed:

- `live collection` — this command performed the bounded official-source
  retrieval and then reviewed the collected bundle (including semantically
  blocked collects and post-collection baseline identity mismatches);
- `collection not started` — baseline resolution failed before any
  retrieval; no live collection was performed by this command (pre-
  acquisition `collect` failures, e.g. a failed live baseline export);
- `collection attempted and failed before completion` — bounded retrieval
  was attempted but no complete collection was produced and no sealed
  collected review exists;
- `offline review` — `review` of supplied bytes: no live retrieval was
  performed by this invocation.

The stage and the report scope come from the RUNNER-SELECTED context of
this invocation. Each sealed run's `validation.json` additionally carries
a runner-owned `execution_context` inside the HMAC-protected content:

- `acquisition` — the runner-selected mode of the generating invocation
  (`live_collection` or `offline_supplied`), never inferred from the
  bundle's collection field;
- `generator` — the measured code identity of the generating invocation
  (`tool` plus `code_revision`), measured by the running code, never
  copied from the untrusted bundle declaration;
- `generator_versions` — the ACTUAL generating schema/renderer/policy/
  extractor versions, bound to the running code's own constants (the
  bundle's supplied `revision`/`research` declarations stay labeled as
  supplied historical text and are never rendered as this run's generator
  versions).

`verify` checks content digests, then the HMAC, then the context shape
and version, and only then replays the validation with the ORIGINAL
authenticated context (the sealed acquisition mode and generator; the
current verifier's identity is reported separately as `current generator`
and the sealed one as `original generator`, authenticated in the sealed
`validation.json`). Verification executes no HTTP, DNS, or SQL. A sealed
run whose context is missing (sealed before the runner-owned execution
context existed) or whose shape or version is unsupported is refused
explicitly (exit 30) — no historical
renderer fleet, no re-derivation, no re-sealing.

The generator `code_revision` is a bounded MEASURED content identity: a
deterministic SHA-256 over the content of a fixed set of fifteen owned
catalog-refresh files (including the helper that measures them), formatted
`catalog-ccid/v1:sha256:<64 hex>` — or the explicit `unavailable` marker
when measurement fails (missing, non-regular, or unreadable file, or bound
exceeded: 32 files, 512 KiB per file, 8 MiB total). It is not a
whole-environment digest, not loaded-bytecode attestation, not a security
boundary, and not a reproducibility promise: relocation or timestamp
changes do not change it; changed bytes DO change it, even under an
unchanged package version. It uses no Git inspection, no environment or
config traversal, no subprocess, and no recursive scan. The package
version is recorded separately in the tool metadata, so two installations
with the same version and different bytes remain distinguishable.

### Proposal scope and FX derivation

Eligibility follows **executable billing, not TSV capacity**: a value
fitting a pricing column is not proof the gateway can safely bill that
shape. The collector proposes **standard-v1 short-context core pricing**:
`input`, `output`, and (when published) `cached_input` per 1M tokens in the
published native currency, plus — only when the source publishes it as an
**explicit zero** — the `reasoning` no-charge dimension. Before anything is
proposed, a single deterministic shared policy decides flat billing
eligibility for each model from **all** authoritative observations of it
(every billing tier, every context band, every published pricing key); the
same policy is recomputed by validation from the parsed official evidence,
so a supplied or tampered bundle cannot bypass eligibility by dropping
dimensions:

- **Excluded, fail-closed, with the exact machine reason**: the documented
  OpenRouter **`:online` model variant** - a KNOWN INTRINSIC HOSTED
  IDENTITY (the official model-variants contract, checked 2026-10-12,
  states the suffix enables real-time web search for any model, exactly
  equivalent to the `web` plugin, and marks the variant deprecated in favor
  of the `openrouter:web_search` server tool); it is excluded by IDENTITY,
  independent of positive, zero, or missing `web_search` fees - a zero cost
  cannot qualify tool authority, and absent fees cannot establish absence
  of search - and this is one exact documented variant identity, not a
  model-name classifier. Also excluded: positive separately billed
  **reasoning charges** (ordinary Chat admission reserves at the output
  price; no qualified reasoning billing contract is authorized), positive
  **per-request fees** (ordinary Chat admission and finalization do not
  bill an additive per-request fee; that column serves native-module
  contracts), positive **hosted-operation charges** on ordinary IDs (hosted
  operations are denied in the profile and no reviewed per-model executable
  contract proves the charge cannot be incurred), published long-context
  standard prices (even $0 — a published contextual price), contextual
  override tiers, positive cache-write charges (1h or not), unknown
  published billing keys, source `-1` sentinels on any billable dimension,
  and positive charges that quantize to zero at the 9-dp import contract
  (`price_below_quantum`). Other OpenRouter variant classes have **no**
  reviewed executable ordinary-Chat contract and are not declared safe by
  analogy: unknown classes remain honestly unsupported/ambiguous and stay
  subject to the price-based gates.
- **Zero semantics (documented, tested)**: a **legitimate zero is a
  no-charge, never a missing fact**. A published zero `reasoning` price is
  **carried**, because a missing reasoning price makes finalization bill
  reasoning tokens at the output price (`reasoning_price_fallback_to_output`)
  — a change of actual local billing. A published zero per-request fee is a
  documented no-charge (ordinary Chat bills no per-request fee at all), and
  a published zero web-search charge is a no-charge (the standard chat
  contract has no web-search billing dimension and a zero publishes no
  provider-side cost); both are never carried.
- An excluded model's official model page is **never fetched** (eligibility
  is decided before page retrieval); explicitly selecting an ineligible
  model BLOCKs the run.
- OpenAI `batch`/`flex`/`fast` tiers are **service variants** of the same
  model (mirroring the OpenRouter `:batch` handling): they never block or
  flatten the standard tier; a model with only non-standard rows is
  `no_standard_short_prices`.
- A collection that fetched sources but produced no usable proposal is
  `collection_empty_bootstrap` (BLOCKED), never an empty READY bootstrap.

Provider-alias rows (`~` prefix) are proposed under their **exact observed
identity** (the prefix is part of the published model ID; no alias mapping
is asserted), and `:batch` variants are excluded as service variants.

OpenAI candidates come from the pricing document's standard short-context
rows; each eligible candidate's official model page is fetched (bounded to
64 pages per run) and must declare the matching Model ID, Chat Completions
support, text output, a context window, and text prices that **exactly
match** the pricing table (otherwise `page_price_conflict`).

FX is fetched only when a proposed price is non-EUR: the ECB EUR-base daily
reference XML is parsed and the latest quote for each needed pair is recorded
**as published** (EUR is the implicit base currency) with per-pair provenance
`ecb|EUR-<CUR>|ecb_reference_xml`. The native→EUR rate the runtime looks up is
then reciprocated deterministically by the FX gate (9-dp `HALF_UP`) and marked
as a derived reciprocal of the original pair in every comparison and FX
artifact row, so the published direction is never relabeled. An ECB retrieval
failure blocks the run as an unbound FX fact — never as a missing model.

### Refresh preservation

For `--refresh`, local route authority is keyed by the **upstream**
identity and is never overridden:

- A single flat-representable exact-route baseline row is a **local route
  identity**: the proposal preserves its public alias (`requested_model`),
  match type, `priority`, `enabled`, `visible_in_models`, and
  `supports_streaming` values, and its capability block projects onto flat
  standard keys **only when the contract is exactly one `chat_completions`
  block** — including explicit denials (a denied capability stays denied;
  nothing is granted). A genuinely unconfigured model keeps the exact
  upstream name.
- **Multiple aliases/priorities are never reduced** to one row
  (`baseline_multiple_routes`): the model is retained locally with no
  parallel route proposed.
- A **prefix/glob baseline route that GOVERNS the upstream** is retained
  (`baseline_contract_not_flat`): coverage is the resolver's actual
  destination semantics, never public string similarity — an explicit
  `upstream_model` is a fixed destination (the row governs exactly that
  upstream, whatever the public pattern is), and an empty `upstream_model`
  passes the public name through (the row governs the upstreams whose
  identity matches the public pattern). All governing rows are recorded in
  the retention reason — alternatives are never reduced — a flat exact
  proposal cannot preserve wildcard contracts, and the routing pattern
  itself is local state: retained with an explicit disposition, never a
  source disappearance, and no parallel route may re-insert a bypass of
  that authority (supplied bundles are BLOCKed with
  `wildcard_route_authority_bypassed`).
- A **MIXED exact + governing-wildcard authority set** (one or more exact
  rows and at least one governing prefix/glob route for the same
  provider/upstream) is likewise retain-only
  (`baseline_contract_not_flat`): the WHOLE local authority set is
  evaluated before any single flat row is chosen; every exact alias and
  wildcard alternative keeps local authority (denied alternatives
  preserved, priorities and destinations recorded), no flat exact route or
  pricing candidate is invented, and no parallel route may bypass the
  wildcard (supplied bundles are BLOCKed with
  `wildcard_route_authority_bypassed`).
- A **non-flat exact contract** or a **baseline pricing currency other
  than USD** retains the model locally with an explicit inventory reason
  instead of re-proposing it under a different contract.
- An alias **remaining mapped to a present upstream is not a disappeared
  model**. A supplied bundle that replaces the alias with an
  upstream-named route, or adds a parallel upstream-named route, BLOCKs
  (`alias_route_replaced`).
- The declared baseline target is the **database name plus explicit host
  and port identity fields**; the full `host:port/database` identity
  remains bound inside the hashed baseline content, so a substituted
  document is still rejected (`baseline_identity_mismatch`), and any
  database/host/port mismatch BLOCKs (`baseline_target_mismatch`).

### Limits

- Codex research is opt-in (`--research`) and stays `NOT_RUN` by default;
  when enabled, deterministic retrieval plus parsing remains first and only
  eligible unresolved facts may be transcribed by the isolated Codex
  semantic fallback (real CLI in an enforced outer boundary, parent
  re-grounding — see [Isolated Codex research fallback](#isolated-codex-research-fallback-opt-in)).
- Every refresh command is read-only: the sealed run directory is the
  terminal output of `collect`/`slaif-catalog-refresh`; changing the
  catalog requires the separate explicit [apply](#apply-one-explicit-atomic-command)
  on one sealed READY/READY_WITH_WARNINGS run.
- One profile (`standard-v1`), two providers (`openai`, `openrouter`),
  OpenAI model pages bounded to 64 per run.
- The registry is intentionally small and reviewed; adding a source kind or
  host is a contract change, not a configuration.

## Isolated Codex research fallback (opt-in)

Deterministic official-source collection and parsing are always first. Only
when an eligible required standard-v1 fact remains unresolved **from the
already-captured bytes** (for example a readable limit in a layout the
registered parser does not resolve) may the `collect` command, with explicit
`--research` operator configuration, plan a bounded research task. The
fallback is a real Codex CLI running outside the repository in a private
task workspace, inside one enforced outer boundary (Docker): nonroot,
read-only root, dropped capabilities, task-only mounts, an isolated internal
network, and an inference-only relay that refuses every non-inference
authority before serving or forwarding. The researcher receives no database,
provider, seal, or host credentials; the structured result is the CLI's own
final message, validated against a checked-in bounded output schema, and the
parent re-resolves every claimed locator/quote against the captured bytes
before any fact can enter the bundle.

Contract points:

- **Deterministic first.** Existing registered observations win whenever
  complete; research only unresolved eligible facts. With research enabled,
  a fully deterministic collect still records research `NOT_RUN`.
- **Measured identity, parent-set.** The bundle carries the producing
  run's measured research identity (status, actual CLI version and binary
  hash, template/output-schema identities, safe counts, elapsed time,
  failure code, result hash). A model or a supplied bundle can never
  certify an execution: for a supplied or offline review the identity is a
  historical declaration, and the report labels it as such.
- **Re-grounded at review time.** Every sealed research fact is re-derived
  from the sealed source bytes by the parent in every review and verify
  (one ungroundable fact BLOCKs the run); offline re-grounding verifies the
  sealed facts, not the original CLI execution. Grounded cells render as
  semantic-method evidence, never as deterministic extraction.
- **Honest failures.** A child timeout/failure, malformed result, a
  boundary refusal after earlier tasks executed, or a required cleanup
  failure records a measured `FAILED` identity that preserves the verified
  CLI identity and execution history (scope, timing, exit record) while
  discarding all research output; only a refusal before any invocation
  records `UNAVAILABLE`; the deterministic dispositions stand and no
  partial research data is used.
- **Mock versus live.** Qualification runs may wire the relay to a parent
  prepared mock model transport; such runs are flagged `mock_model` in the
  identity and are never presented as live model evidence. Live runs use
  the operator-configured endpoint (HTTPS required at the CLI).
- **No authority growth.** Research never chooses readiness, signs,
  re-fetches arbitrary URLs, touches the database, or applies; the same
  gates, seal chain, and artifact set apply to the resulting bundle.

See [Security model — catalog refresh research boundary](security-model.md#catalog-refresh-research-boundary)
for the isolation limits.

## The proposal bundle (`catalog-refresh.json`)

One versioned, typed JSON document carries the proposal **facts and
provenance only**:

- run ID, generation time, schema/renderer/policy revision identities;
- research identity (measured per producing run: `NOT_RUN`, `SUCCEEDED`, `FAILED`, or `UNAVAILABLE`; a supplied bundle's research identity is a historical declaration, and every sealed research fact is re-grounded against the sealed source bytes at review time — see [Isolated Codex research fallback](#isolated-codex-research-fallback-opt-in));
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

**Scope is bundle-determined.** A bundle **without** a collection
identity is an **offline replay of supplied snapshots**: snapshot origin and
retrieval claims (`retrieved_at`, `published_at`) are caller-supplied labels
assessed against freshness policy; they are not authenticated retrievals,
and reviewing such a bundle performs no network I/O. A bundle **with** a
collection identity records the collecting invocation's own bounded
retrievals (requested/final URL, UTC fetch time, outcome, size, digest,
attempts, redirects, safe failure code); the review re-verifies those
claims against the bundle's source records and parsed evidence instead of
fetching again (see [Live collection](#live-collection-the-collect-command)).

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
25%/3% movement boundaries compared before display rounding);
`180.5` changes presentation only — the first-screen decision dashboard
(state/reason banner with blocker/REVIEW chips, the scope-and-baseline
card, the grouped deterministic gate checklist, per-provider source-snapshot
versus baseline-comparison tables, the FX card, the create-only execution
plan, aggregated top findings, recomputed counts and the compact run
identity), the changes-first detail section, expandable inline evidence
with full digests, long-value wrapping and the documented print behaviour —
plus the corrected SQL-capture wording. No state, gate, count, monetary or
capability semantics changed;
`180.6` changes presentation and test evidence only — the first screen
becomes a concise decision overview (plain-language state reason instead
of a code list, compact scope/baseline card with plain baseline meaning
and profile, compact grouped checklist preserving the worst state per
group with the full per-gate detail in a labelled expandable section of
the same file, full-width per-provider change summary keeping the
source-snapshot and baseline-comparison populations in distinct columns
with no invented zeros, a per-pair FX line or one truthful N/A line, a
concise create-only import-plan line, the leading ranked findings line,
and "What changed" as the next visible section), main reading text at
least 14 px (decision information 15 px), no mid-word breaks of short
words at desktop widths, wide tables scrolling inside their own wrapper
on narrow viewports, and browser tests that measure the real document
width, fonts and visible expanded text while writing only to pytest-owned
temporary output — plus the corrected mutation-namespace wording. No
state, gate, count, monetary or capability semantics changed;
`181.1` adds bounded live official-source collection (the `collect`
command: the registered source registry with per-attempt host allowlist
re-validation, the public-destination DNS guard, bounded re-validated
redirects, bounded 429/5xx/transport retries, mid-stream body byte caps,
and collection budgets; the collection identity recording every measured
retrieval outcome and the observed-model inventory; the
collection-versus-replay validation gates `collection_source_unbacked`,
`collection_retrieval_failed`, and `collection_inventory_unsupported`; ECB
FX derivation for proposed non-EUR prices; refresh preservation of baseline
route attributes including explicit denials, with non-flat-contract and
currency exclusions; and the scope-aware report wording) — supplied-bundle
offline replay semantics are unchanged.)

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
  not proof that the baseline is current. `sql_checked` records that the
  document **declares** SQL was executed when it was exported (a historical
  capture fact carried by the document; consuming the file does not verify
  that execution occurred, and the review does not attest it); a review that
  consumes the document from a file states that separately. A stale or
  tampered baseline file is a data error, not a valid baseline.

Connection failure never becomes an empty bootstrap.

**SQL evidence is a property of the execution path, never of a label.**
The report states the actual capture path of this execution:
`first_install` (an explicit first install read no database and no baseline
document exists), `document` (a supplied baseline document
DECLARES a historical SQL export at its own export time; consuming the file
does not verify that the historical execution occurred, and the review does
not attest it; no SQL ran during this review), or `live_export` (this review command performed the
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

The renderer is a pure function of (bundle, report): identical inputs
reproduce identical bytes. The layout is a concise decision overview,
then changes-first detail, then expandable inline evidence.

**First screen (decision overview).** The first 1440x900 viewport shows,
without expanding details or scrolling through evidence prose:

- the state banner: overall state (READY / READY_WITH_WARNINGS / BLOCKED)
  with a concise plain-language reason — for BLOCKED, the human labels of
  the first blocking codes plus a pointer to the remaining codes in the
  findings (the exact code list is never the primary reason) — plus chips
  counting BLOCKERS, REVIEW findings and all findings;
- a two-column card grid:
  - *Scope &amp; baseline*: the selected providers plus model filter with
    considered/selected counts (a compact selection, not a list of every
    model), the selected profile/endpoint, the baseline in plain language
    ("First install — explicitly empty; no database was read", "Live
    export performed by this review (SQL ran during the review)", or
    "Supplied export of &lt;date&gt; — not checked against a live
    database"), a compact source-evidence line (how many proposed facts
    are bound to parsed snapshot observations, snapshot inventory), and a
    compact run-identity annotation (run ID, generated time,
    SLAIF/schema/renderer/policy revisions) linking to the expanded
    identity section;
  - *Deterministic checks*: the deterministic gates grouped into five
    display groups (source evidence; schema and pricing completeness;
    pairing and supported capabilities; changes and reconciliation;
    import-plan validation). Each group shows its worst-state chip and
    how many members are not a concern; the full per-gate technical
    rendering (every gate's state chip, name, and detail, any ungrouped
    gate listed individually — nothing hidden) is in the labelled
    "Full per-gate checklist" expandable section of the same artifact,
    open whenever the run is BLOCKED;
- **Providers &amp; changes**: a summary line (considered / selected /
  ready and the provider list) and a readable full-width table — the
  per-provider baseline comparison (new, changed, mutations, unchanged,
  excluded, blocked, disappeared, deprecated, not fetched) plus, when
  sources parsed, the distinct source-snapshot columns (in snapshot,
  selected in snapshot) — with a footnote stating the populations are not
  additive, an honest "no source snapshots parsed" line when no source
  parsed (no count is invented), and the recomputed counts as compact
  chips;
- the **FX line**: per pair, current (local baseline) → proposed (bundle)
  rates, signed delta, state, publication date and source, with
  derived-reciprocal markers and the direct/derived distinction — or one
  concise, truthful "not required" line when no conversion is needed;
- the **plan line**: the single first-screen actionable-plan summary —
  when the authenticated apply plan is non-empty it shows the operation
  counts plus the one atomic apply (representable existing-row updates
  execute as supersession operations in that plan; only the legacy
  create-only TSV export omits them), and without an apply plan it shows
  the historical create-only import-plan wording (executable create rows,
  "nothing to create", or a conspicuous BLOCKED line), linking to the
  "Import plan detail" expandable section (open whenever a plan is
  blocked);
- the leading **findings line**: the top finding groups ranked by severity
  with concise human labels (exact codes retained) and a link to the full
  per-item list — ranked aggregates plus a link, not pages of codes, when
  findings are numerous.

Directly after the overview, the "What changed" heading and the first
relevant change (the price-change table or the explicit no-change lines)
are visible in the normal desktop case.

Main reading text is at least 14 px at default zoom (15 px for decision
information; state and headings clearly larger), and short words and
provider names do not break mid-word at desktop widths. Long run IDs,
model filters, URLs and digests wrap; wide tables scroll horizontally
inside their own wrapper on narrow screens instead of forcing the page
wider. There is no page-wide horizontal overflow at 1440, 1280, or a
375 px viewport, collapsed or with every detail expanded; cards collapse
to one column below 900 px and natural vertical scrolling on narrow
screens is expected.

**Changes first.** Directly after the dashboard, the "What changed"
section leads the detail: price changes with old/new values, units,
currencies and signed percentages — with a note that displayed
percentages are rounded to 0.001 % while the gate decision uses the exact
stored ratio (a strictly above-threshold movement can display at the
threshold); route/model attribute changes with current → proposed values
and the reason (refresh never modifies existing route rows; representable
price/FX changes carry as supersession operations in the apply plan);
and an explicit "Unchanged: N model(s)" line pointing to the collapsed
unchanged section. Disappearance is displayed as an observation, not a
delete operation, and no decision is downgraded by presentation logic.

**Evidence on demand, all inside the same file.** Expandable native
`<details>` sections hold: all warnings and findings (open by default,
per-item detail); the full validator outputs; import-gate details
(schema-valid versus execution-plan-valid, per kind); the source inventory
and reconciliation with FULL 64-hex digests (never truncated); the source
evidence — per-source parse status with the registry parser, the exact
parsed observations that bound each proposed fact (observed value, unit,
currency, exact locator, URL, full digest, parser, retrieval time,
normalized value and transformation, declared backing sources,
distinct-URL independence), FX facts bound to verified reference quotes,
and the reconciled evidence inventory with per-provider selection
dispositions and bounded ID lists; baseline identity (historical capture
versus current checks, with the SQL capture-path note); the expanded run
identity (revisions, artifact digests); bundle notes; and the unchanged
rows. Bounded example lists are labelled with their totals, and nothing is
silently dropped to make the page small.

**Print.** The print CSS keeps state borders and textual labels
(colour is not relied on; severities are additionally underlined), wraps
long values instead of clipping them, keeps table rows from splitting
across page breaks, prints opened (expanded) sections in full, and prints
closed sections as their summary line only. The report footer documents
this behaviour. The browser test measures the real document geometry,
fonts and visible expanded text, and captures actual print PDFs of the
price-change and FX-required cases — but writes everything only under
pytest-owned temporary output; the committed screenshots and print PDFs
under `tests/fixtures/catalog_refresh/` are deliberately copied,
inspected outputs of exactly that run (never rewritten by routine tests).

The detailed evidence files (`validation.json`, TSV/JSON artifacts,
manifest, receipt) exist for machines and audit; a human decision never
requires opening them.

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
the final path.

### Filesystem trust contract

All catalog-refresh inputs — bundle, baseline, seal key, run content,
manifest, receipt, and export output — pass through one
descriptor-anchored filesystem boundary:

- **Anchored walks.** Path components are walked one hop at a time
  through held directory descriptors with no-follow opens; nothing is
  reopened by full path after a check. A symlink at any level — leaf,
  intermediate parent, or ancestor — is refused, as are traversal
  components (`..`, empty, dot), absolute names, and depth/alias
  escapes.
- **Lifecycle binding.** Review keeps the anchored handles for the run
  root and the seal-key parent across the whole operation and re-asserts
  the name-to-inode binding at every publication gate; a directory swapped
  mid-operation voids the run (exit 65) and nothing is published under the
  swapped name. Verify is read-only: it anchors the run directory once
  through the same no-follow walk (the held descriptor serves every read)
  and loads the existing key separately; it retains no key-parent
  lifecycle, publishes nothing, and never creates, repairs, or re-signs
  anything.
- **Mutation-namespace enforcement.** Every writing catalog-refresh
  command enforces the namespace on the directory it writes into:
  `review` requires the run root and the seal-key parent to be
  operator-owned directories that are not writable by group or other,
  and `export-baseline` requires the same of the output parent; each
  check is an `fstat` on the held descriptor, and unsafe directories are
  refused, never chmod'ed or repaired (exit 65). Read-only `verify`
  enforces no writability at all — a group/other-writable run directory
  or key parent still verifies with exit 0 — and its safety rests on the
  no-follow anchoring, the single captured read, and key-held
  authentication instead. The identity check
  and the later name mutation (rename/rmdir) are separate operations on
  held descriptors: no single syscall atomically compares a source inode
  against a name. The race closure therefore combines descriptor anchoring
  with these enforced mutation parents, not an atomic check-and-mutate.
- **Bounds before allocation.** The bundle (8 MiB) and baseline
  (32 MiB) bounds are enforced before any content is read or
  allocated. Sealed runs are bounded per content file (32 MiB),
  manifest and receipt (1 MiB read cap each), per run (128 MiB including
  manifest/receipt overhead — the 8 KiB receipt constant is a
  signing-overhead reservation in that aggregate budget, not the
  verifier's read cap), file count (64) and depth (4), and the
  manifest's declared set, count, and sizes are reconciled before any
  content is read. Special files (FIFO, socket, device) fail promptly
  at open, and sparse files over their declared size are refused before
  reading.
- **Strict JSON, safe errors.** Bundle, baseline, manifest, receipt,
  and the first-install marker are parsed strictly: duplicate keys,
  non-finite constants, malformed input, and excessive nesting are
  refused. Parse and schema errors render as constant, bounded text and
  never echo input bytes or private field values.
- **Exact key contract.** The seal key must be a regular,
  symlink-free file whose parent chain is symlink-free, owned by the
  invoking user, with mode exactly `0600` and exactly 64 lowercase
  ASCII hex bytes, validated on the *opened* descriptor; a key that
  grows while read is refused. Verification never creates, repairs, or
  re-signs anything and leaves a missing key missing. Key containment
  outside the run tree is proven by `(dev, ino)` chain identity, not
  lexical path comparison alone.
- **Atomic NEW-ONLY publication.** A run is staged in a private
  (0700) directory, completed and fsynced, sealed, then published with
  one atomic `renameat2(RENAME_NOREPLACE)` (Linux kernel 3.13+, glibc
  2.28+; fails closed when unavailable — never check-then-replace).
  Pre-existing targets of any type, including concurrently created
  ones, remain byte- and inode-identical and the conflict exits 65.
  `export-baseline` enforces the same new-only guarantee on its output
  file. Failure cleanup is identity-checked and refuses to remove a
  replaced staging directory.
- **Capture-once.** Each content file is read exactly once through the
  held descriptor, and those same captured bytes drive the manifest and
  receipt digests, canonical bundle identity, semantic validation, and
  the report correspondence. First-install runs must byte-equal the
  canonical empty marker, not merely carry the expected
  `schema_version`. The bounded reader re-proves identity and size on the
  opened descriptor after the read and refuses short reads and growing
  files (EOF probe); a same-size in-place mutation that races the read is
  NOT detectable at the byte level. The accepted guarantee is the single
  captured byte snapshot and the authenticated correspondence between it,
  the manifest and the receipt, within the platform and threat scope
  below.

Platform and threat scope, stated honestly: the boundary assumes Linux
with `renameat2`. It provides local integrity against unprivileged local
peers; it is not protection from an administrator who controls the seal
key, from root or same-uid code with full authority, or from hostile
kernel behavior. Filesystem permissions do not make reviewed files
immutable — later mutation is detected by verification, and any future
apply must consume the authenticated snapshot rather than reread paths.

## Apply (one explicit atomic command)

`apply` is the single in-contract execution path for a reviewed run. It is
always explicit: it requires `--confirm`, a non-blank operator `--actor`,
and a non-blank `--reason`, and it never runs as a side effect of
`collect`, `review`, `verify`, or any other command. The OS watchdog prefix
documented for `collect` is never used around `apply` (it mutates) and never
around `status`, `review`, or `verify`.

```bash
slaif-gateway catalog-refresh apply \
  --run-dir /path/to/run \
  --db-url postgresql+asyncpg://user@host:5432/dbname \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key \
  --confirm --actor "ops:alice" \
  --reason "apply reviewed openrouter refresh 2026-10-13" \
  [--admin-id UUID] [--ack-warnings new_model_exposure] [--json]

slaif-gateway catalog-refresh status \
  --run-dir /path/to/run \
  --db-url postgresql+asyncpg://user@host:5432/dbname \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key [--json]
```

### What apply checks, in order

1. **Authentication (before any database contact).** The run directory is
   re-verified byte-for-byte against the same runner-owned seal key
   (content digests, manifest, and HMAC receipt). A wrong key or any
   tampering fails with exit 30 before any connection is opened. Only
   `READY` and `READY_WITH_WARNINGS` runs are applicable; the sealed
   `validation.json` must carry an apply plan with a supported schema
   version.
2. **One transaction.** Everything else happens inside one PostgreSQL
   transaction with a bounded prelude (10-second lock waits, 60-second
   statement limit) and fixed-order catalog table locks
   (`fx_rates`, `model_routes`, `pricing_rules`,
   `provider_configs`) taken as `SHARE ROW EXCLUSIVE`: ordinary catalog
   writers (INSERT/UPDATE/DELETE) are blocked while apply holds the locks;
   plain reads are not.
3. **Target check (refresh mode).** The operator `--db-url` host, port, and
   database must match the reviewed baseline target. Bootstrap mode instead
   proves all four catalog tables are empty
   (`apply_bootstrap_not_empty` otherwise); an existing catalog is never
   "bootstrapped over".
4. **Known-committed lookup first.** The transaction looks up
   `catalog_refresh_applications` by the canonical bundle identity *before*
   any apply-time gate or mutation. A retry of an already-applied bundle —
   even after source aging, a finite validity window expiring, or a
   re-derived plan drifting — returns the prior committed record (same
   `operator_actor`, `db_actor`, `effective_at`, and counts) as
   `already_committed`; it never overwrites, re-applies, re-charges, or
   re-audits.
5. **Current execution gates (after the lookup, before any mutation).**
   The review is re-computed at apply time on the captured, authenticated
   run: a freshly `BLOCKED` plan refuses (`apply_freshness_blocked`),
   unacknowledged review findings refuse unless each code is passed to
   `--ack-warnings` (`apply_warnings_unacknowledged`), and a re-derived
   plan identity different from the sealed plan refuses
   (`apply_plan_mismatch`).
6. **Stale-baseline comparison.** The locked live projection of the four
   catalog tables is compared row-for-row against the baseline captured at
   review time (excluding the informational `updated_at`). Any drift
   refuses (`apply_baseline_stale`); nothing is mutated in any refusal
   path.
7. **One effective instant.** A single `T` (UTC, chosen once inside the
   transaction after all checks pass) is the effective time for every operation: each
   supersession closes the reviewed old window at exactly `T` and opens the
   new row at exactly `T`. Amounts, currency, metadata, and row identity
   are preserved — history is never repriced in place. Each close is
   guarded on the exact reviewed facts (row identity, currency, opening
   instant, the reviewed closing instant via NULL-safe
   `IS NOT DISTINCT FROM`, still enabled, still active at `T`); any drift
   refuses the whole transaction (`apply_supersession_guard_failed`).
8. **Execution and record.** The sealed plan operations execute in plan
   order through the same verified services the admin dashboard and CLI
   use (each row keeps its own audit trail). The transaction then writes
   exactly one `catalog_refresh_applications` record (safe fields only:
   bundle/receipt/plan identities, actor assertions, `T`, affected row IDs,
   counts) and one `catalog_refresh_applied` audit row, and commits.

Any failure anywhere rolls the entire transaction back and surfaces a safe
`code: detail` error (never a database URL, credential, or provider key).
The `--admin-id` value, when supplied, is verified to exist in the target
database inside the transaction; a blank actor or reason is refused at the
service entry as well as the CLI.

### Idempotency and concurrency

- `unique(bundle_sha256, plan_sha256)` on the application record makes
  same-bundle retries resolve the committed outcome. Two concurrent applies
  of the same bundle serialize on the catalog locks: one commits, the other
  finds the committed record (or loses a unique conflict and re-reads) and
  reports `already_committed` — never a double apply.
- `status` performs the same identity lookup without any catalog lock: it
  never blocks writers and never mutates. Exit 0 reports whether the
  bundle is committed (with the safe record); exit 30 is a seal
  authentication failure; exit 65 is a data error.

See the [application record schema](database-schema.md#524-catalog_refresh_applications)
and the [CLI reference](cli-reference.md#catalog-refresh-collect-review-verify-apply)
for the full option and exit-code surface.

## Exit codes

| Command | Code | Meaning |
|---|---|---|
| `collect` | 0 | READY |
| `collect` | 10 | READY_WITH_WARNINGS |
| `collect` | 20 | BLOCKED — a blocked run is always published, labeled by the path reached: `collection not started` (baseline failure before any retrieval), `collection attempted and failed before completion` (retrieval failure), or the `live collection` wording (semantic blockers and baseline identity mismatch, after a completed collection) |
| `collect` | 65 | data error where no blocked run is published (unreadable/invalid `--baseline-file`, unsafe directory configuration, seal key problem) |
| `collect` | 2 | usage error (contradictory options) |
| `review` | 0 | READY |
| `review` | 10 | READY_WITH_WARNINGS |
| `review` | 20 | BLOCKED (safe blocked run published when possible) |
| `review` | 65 | data error (unreadable/unparseable/oversized input, bad baseline, seal key problem, unsafe directory configuration, existing run output) |
| `review` | 2 | usage error (contradictory options) |
| `verify` | 0 | run verified |
| `verify` | 30 | run failed verification — including a missing, non-directory, or symlinked run directory with an otherwise valid key, or any seal/digest/correspondence mismatch |
| `verify` | 65 | data error (missing or unsafe seal key: a key path or parent refused by the no-follow walk, a non-regular file, a mode other than exactly 0600, foreign ownership, or wrong length/content; verify never creates keys. A key stored in a group/other-writable parent is still accepted — verify performs no mutation) |
| `export-baseline` | 0 | baseline written |
| `export-baseline` | 65 | data error (never overwrites output — new-only atomic write; never bootstraps empty) |
| `apply` | 0 | committed — or `already_committed` for a same-bundle retry (the prior record is returned, never overwritten) |
| `apply` | 10 | `apply_warnings_unacknowledged` — pass each code to `--ack-warnings` |
| `apply` | 20 | plan not applicable: `apply_state_not_applicable`, `apply_freshness_blocked`, `apply_no_plan`, `apply_plan_unsupported`, or `apply_plan_mismatch` |
| `apply` | 30 | seal/authentication failure (wrong key, tampered or unreadable run) — no database contact was made |
| `apply` | 65 | blocked execution or data error: `apply_target_mismatch`, `apply_bootstrap_not_empty`, `apply_baseline_stale`, `apply_admin_unknown`, `apply_duplicate_record`, `apply_supersession_guard_failed`, `apply_database_error`, missing `--confirm`, or blank `--actor`/`--reason` |
| `status` | 0 | status reported (committed or not — the fact is printed) |
| `status` | 30 | seal/authentication failure |
| `status` | 65 | data error (lookup or configuration failure) |
| `slaif-catalog-refresh` | 0 / 10 / 20 | the child `collect` exit code, preserved exactly (same meanings as `collect`) |
| `slaif-catalog-refresh` | 2 | a child usage refusal, preserved exactly (e.g. an unsupported `--profile` preset) |
| `slaif-catalog-refresh` | 65 | wrapper-own argument validation before spawn (invalid `--mode`, non-positive `--timeout`/`--kill-grace`, contradictory `--mode bootstrap` plus `--baseline-file`/`--db-url`, or missing `timeout`/`slaif-gateway` binaries), or the child `collect` data error |
| `slaif-catalog-refresh` | 124 / 137 | the watchdog cancelled a stalled read-only collection (TERM, then KILL after `--kill-grace`); no run is published |

## Limits

- `collect` makes bounded live official-source retrieval calls and, only when
  `--refresh` is combined with `--db-url`, performs a read-only PostgreSQL
  baseline capture of the target database. By default it performs no Codex
  research; with `--research`, the researcher's only model contact is a
  task-owned inference relay to the operator-configured endpoint, and the
  operator credential never reaches the researcher. `verify` is fully
  offline. The other commands make no source, provider, or research traffic;
  their only possible network contact is the permitted
  PostgreSQL connection to their target database: `export-baseline` and
  `status` use it, `apply` uses the reviewed target, and `review` only when
  `--db-url` reads a live baseline.
- Apply is explicit and single-target: one sealed run, one database, one
  effective instant, one durable record. It is a catalog refresh tool, not
  a migration or backup tool, and it is never wrapped in the collect
  watchdog. Supersession preserves history (windows close, rows are added)
  and never reprices rows in place.
- The seal is a local integrity tool, not a substitute for GitHub/audit
  authority or protection against a key-holding administrator.
- The sealed-run filesystem boundary assumes Linux (atomic
  `renameat2` publication) and protects against unprivileged local
  peers, not privileged or key-controlling code.
- Baseline export reads four metadata tables; it is not a database backup
  (see [Backup and restore](backup-restore.md)).
- Admission cost estimation uses the coherent single-statement
  pricing+FX capture described in
  [Accounting](accounting.md#coherent-admission-capture-pricing-and-fx);
  apply supersession closes reviewed validity windows at the one effective
  instant and preserves history.

## Related documentation

- [CLI reference](cli-reference.md#catalog-refresh-collect-review-verify-apply)
- [Provider catalog proposals](provider-catalog-proposals.md)
- [Pricing catalog and bounded overrun](pricing-catalog.md)
- [Database schema](database-schema.md)
- [Installed administrator workflow qualification](verification/catalog-refresh-installed-workflow.md)
