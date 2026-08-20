# OAP Work Order — 014-b

## Objective

Amend PR #239 to close the material fence-identity, exclusivity, and
authoritative-resolution gaps found in independent strategic review of
014-a. Preserve the working PostgreSQL fence foundation, but do not merge a
service that can treat changed provider/route facts as an exact retry, accept a
duck-typed admission decision or malformed stored policy, coexist with an
already-reserved ordinary request, or clear a fence merely because counters are
non-negative.

Provider-hosted forwarding remains disabled. This continuation changes the
same unreleased 0015 migration and the same objective-014 PR; it does not create
a new migration number or PR.

## Authoritative current state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Remote `main` remains
  `72ac24d9820fef34bcf23021345c12ec8a57db34` (merged PR #238).
- Existing objective PR: #239,
  <https://github.com/ulfe-lmi/slaif-api-gateway/pull/239>.
- Required existing branch:
  `oap/014-external-tool-exclusive-fence-reservation`.
- Current remote report head:
  `f9168909bf14342d3a2f661bff92a112d5a9401f`.
- Its first parent/014-a implementation head is
  `9ca9d62e8c3765cf2bf1610decc5cb511303fd04`.
- The 014-a report topology is valid, the PR is clean/mergeable, auto-merge is
  null, and all ten checks on the report head are successful.
- Exactly one objective-014 PR exists. Continue PR #239; never create another.
- Strategic review confirmed the core key-row lock, fence blocking, stale-skip,
  and focused concurrency foundation, but found the exact gaps below.
- GitHub code-quality review also reports unused `_DEFAULT_FENCE_TTL` and the
  unused `remote` import/workaround.

Reconcile these named facts once before editing. If they have materially
changed, report the exact conflict; do not invent a replacement PR.

## Execution discipline — start implementing

Do not enter another reconnaissance loop. The relevant symbols and first edits
are named below.

1. Read this continuation and the directly affected current files once.
2. Immediately start slice 1 by editing migration 0015, `db/models.py`, and
   their focused migration tests.
3. Continue through the four implementation/test slices below.
4. Read another file only when a concrete missing symbol or failing focused
   test requires it.

Do not repeat general preflight, environment discovery, migration-style
discovery, repository-wide searches, or broad test discovery. Do not run a
full local suite. Work in small edit → focused-test slices.

## Slice 1 — bind exact route facts and close database shapes

Because migration 0015 is unmerged/unreleased, amend it directly; do not add
0016.

Add nullable strict-mode/default fields on `quota_reservations`:

```text
external_tool_provider text null
external_tool_route_id uuid null FK model_routes.id ON DELETE RESTRICT
```

For an `external_tool_fenced` row both are required. For a
`strict_bounded` row both are null. Extend model/migration checks so:

- both external fact JSON values are arrays in every valid mode;
- strict mode has empty arrays and null external provider/route;
- fenced mode has a non-empty capability array, an array destination value,
  a non-empty bounded provider string, and a non-null route UUID;
- the fence reservation pointer is unique when non-null as well as RESTRICT,
  so one reservation cannot be the durable pointer for two keys;
- downgrade removes only objective-014 objects in dependency-safe order;
- existing rows still backfill strict with empty arrays/null route facts.

Update `QuotaReservation`, repository creation, the authoritative schema doc,
and exact-head/migration tests together. Service validation remains responsible
for canonical capability/destination values, but PostgreSQL must enforce the
JSON/container/mode/linkage shape.

## Slice 2 — exact acquisition facts and fail-closed policy

In `ExternalToolFenceAcquireInput` and `ExternalToolFenceService`:

- require the actual objective-012 `ExternalToolAdmissionDecision` type; remove
  `Any`/duck-typed acceptance and convert tests to the real DTO;
- require the exact positive fenced decision contract, including positive
  effective call cap and canonical allowed reason/obligation facts;
- validate endpoint, requested model, provider, and route UUID as bounded safe
  facts before locking/mutation;
- parse the stored key policy through `parse_key_external_tool_policy` with the
  canonical operator ceilings; missing, malformed, noncanonical, wrong-version,
  duplicate, over-ceiling, non-acknowledged, or non-fenced policy fails closed;
- validate canonical request capabilities/destinations without silently
  accepting malformed/duplicate/over-ceiling facts;
- persist provider and route UUID on the fenced reservation;
- exact retry must compare key, request ID, endpoint, requested model, provider,
  route UUID, capabilities, destinations, fenced mode, and linked fence facts;
- changing provider alone or route UUID alone must produce the fixed conflict
  and must not change counters, reservation, fence, or audit state.

Do not add request bodies, raw tool values, URLs, credentials, provider
responses, prompts, results, or arbitrary metadata.

## Slice 3 — make the fence actually exclusive and resolution authoritative

Architecture section 12.2 promises that external-tool mode prevents concurrent
use of the key. A previously admitted ordinary pending reservation cannot
coexist with a new external fence.

Under the already-held key row lock, acquisition must fail closed before any
new mutation if an ordinary/unlinked pending reservation or non-zero reserved
request/cost/token counter already exists. Use a fixed safe busy/invariant
error. The row-lock ordering must produce these outcomes:

- external fence wins first: a pre-authenticated ordinary quota transaction
  that began before fence commit blocks, then rejects after seeing the fence;
- ordinary reservation wins first: external acquisition blocks, then rejects
  after seeing the committed pending reservation/reserved counters;
- neither order allows both reservations/provider exposures to coexist.

The successful full-balance case therefore starts with zero reserved counters
and reserves exactly `limit - used` for cost/tokens plus one request. Stale or
drifted pre-existing reservation state remains blocked for operator
reconciliation; it is never guessed away.

Before `resolve()` clears `active`, require all of the following under the same
key/reservation lock order:

- fence request and reservation pointer match;
- reservation belongs to the same key, has the same request ID, is
  `external_tool_fenced`, and carries valid bound provider/route facts;
- exactly one linked terminal ledger exists and belongs to the same key;
- ledger endpoint/provider/requested-model facts agree with the reservation;
- finalized reservation has finalized successful ledger; released reservation
  has failed unsuccessful ledger;
- key reserved cost, token, and request counters are each exactly zero after
  terminal accounting—not merely non-negative.

Any mismatch keeps the fence active and returns a fixed safe invariant/conflict
error without mutation or audit. Exact re-resolution after a valid clear stays
idempotent. `held` remains blocking and 014 still does not create it.

## Slice 4 — tests, cleanup, and honest docs

Add focused unit and real-PostgreSQL negatives for every repaired gap:

- provider-only and route-ID-only retry changes conflict;
- wrong object type cannot stand in for `ExternalToolAdmissionDecision`;
- malformed/partial/duplicate/over-ceiling stored key policy fails closed;
- invalid/badly bounded route facts fail before mutation;
- strict/fenced provider/route and both-JSON-array DB constraints plus unique
  fence pointer and downgrade/backfill;
- existing pending ordinary reservation/counters block acquisition;
- deterministic independent-session race with fence lock first and ordinary
  reservation attempting before fence commit;
- deterministic inverse race with ordinary lock/reservation first and external
  acquisition attempting before ordinary commit;
- mismatched reservation key/request/mode and ledger key/provider/endpoint/model
  never clear the fence;
- positive unreconciled reserved counters never clear the fence;
- exact zero-counter terminal evidence clears once and re-resolution is a no-op;
- no provider, Redis, content, or credential side effect.

Remove the unused `_DEFAULT_FENCE_TTL` and resolve the unused `remote` import/
relationship workaround without weakening relationship correctness. Address
both GitHub code-quality comments.

Update only affected schema/accounting/security/forwarding/product docs. Keep
the status honest: this is still fence/reservation foundation; objectives 015
and 016 own holds and provider execution.

## Allowed paths

This continuation may modify only:

```text
app/slaif_gateway/db/models.py
app/slaif_gateway/db/repositories/quota.py
app/slaif_gateway/schemas/external_tool_fence.py
app/slaif_gateway/services/external_tool_fence.py
docs/accounting.md
docs/database-schema.md
docs/product-scope.md
docs/provider-forwarding-contract.md
docs/security-model.md
migrations/versions/0015_external_tool_exclusive_fence.py
oap/active
oap/orders/014-b-close-fence-identity-exclusivity-resolution-gaps.md
tests/integration/test_external_tool_fence_concurrency_postgres.py
tests/integration/test_external_tool_fence_postgres.py
tests/unit/test_alembic_external_tool_fence.py
tests/unit/test_external_tool_fence.py
```

The final report-only commit adds only:

```text
oap/reports/014-b-close-fence-identity-exclusivity-resolution-gaps.md
```

Do not edit the immutable 014-a order/report, provider adapters, request
handlers, policy-contract implementation, dependencies, CI, README, prior OAP
history, or any path outside this list. If a concrete failing symbol requires
one additional path, stop and report the exact narrow blocker rather than
broadening scope yourself.

## Verification and test economy

Run in slices, not as one broad discovery pass:

1. focused migration/model unit test;
2. focused fence-service unit test;
3. the two dedicated PostgreSQL fence files against one explicit safe
   disposable `TEST_DATABASE_URL`, with no skips;
4. scoped Ruff/format/compile, Alembic one-head, diff/path/privacy checks.

You may include only an adjacent test already named above when a concrete
failure requires it. Do not run the full local unit, integration, E2E, browser,
Docker, HPC, manual-Codex, or provider suites. GitHub CI supplies routine broad
coverage. Never call a real provider or send real email. Clean up only the
disposable objective database you create.

## Acceptance criteria

1. Exact retry is bound to durable provider and route identity as well as all
   original request/policy/fence facts; changed facts fail without mutation.
2. Only the real positive Objective-012 decision and an exact canonical stored
   fenced key policy can acquire.
3. PostgreSQL enforces strict/fenced route-fact and JSON-array shapes and unique
   reservation-pointer lifecycle with safe backfill/downgrade.
4. An external fence and an already-admitted ordinary reservation cannot
   coexist regardless of which transaction takes the key lock first.
5. Resolution proves exact reservation/ledger ownership and fact agreement and
   requires all key reserved counters to be zero before clearing.
6. Every negative keeps state unchanged; expiry and `held` remain blocked;
   Redis is irrelevant and no prohibited content is stored/exposed.
7. Both GitHub code-quality findings are closed; focused tests and every final
   report-head GitHub check pass.
8. Runtime external forwarding remains denied; no provider call occurs.
9. PR #239 remains the sole objective-014 PR; no merge/auto-merge occurs; the
   immutable continuation report satisfies `SELF` topology.

## GitHub and immutable report contract

Commit the unchanged continuation order and `oap/active=014-b` with the repair,
push to the existing branch, and amend PR #239 only. Inspect CI and repair only
in-scope failures. Never merge or enable auto-merge.

Atomically publish exactly one report at
`oap/reports/014-b-close-fence-identity-exclusivity-resolution-gaps.md` with:

- literal implementation SHA and `Report publication commit: SELF`;
- exact schema/provider/route/policy/decision/resolution changes;
- both deterministic lock-order race outcomes and worker/session facts;
- exact unit/PostgreSQL commands, counts, skips, cleanup, and broad suites not
  run;
- state-unchanged negative evidence, privacy/Redis/no-provider evidence;
- GitHub checks, bot-comment disposition, docs impact, scope, and no merge/
  auto-merge confirmation.

The final report commit must parent the implementation head and change only the
new report. Verify it is the remote PR head, then signal exact `OK` through
`response.fifo` and return to the control FIFO wait.
