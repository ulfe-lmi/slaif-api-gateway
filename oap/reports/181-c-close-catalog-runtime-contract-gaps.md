# OAP Execution Report — 181-c: Close catalog runtime contract gaps

## Identity

- Objective: 181 — authoritative catalog collection (SAME PR 318, branch `oap/181-authoritative-catalog-collection`)
- Round: **181-c** (AMEND), selected by `oap/active` = `181-c`
- Order: `oap/orders/181-c-close-catalog-runtime-contract-gaps.md` (committed unchanged this round, activation commit `ab8a37a`; file sha256 `f97d78fd5e49cee9ef00c1a3f1fcb41376f2347f3ae80f7834ac26ada57c4e5c`)
- Starting HEAD (181-b immutable report head, pre-round): `bcbc9c349cd463e1eb31927436a1a0f786e0d119`
- Round-start activation commit: `ab8a37a9aa20b536dad5c433a4a42a2c1f1c81c5` (order + `oap/active` strategic bytes, 2 files, +219/−1)
- Implementation head: `502369d71265dacfcdca993e81721e60d8f3e8f3` (8 files, +769/−176)
- Report commit: SELF (first parent = implementation head `502369d71265dacfcdca993e81721e60d8f3e8f3`; verified with `git rev-parse HEAD^` before the OK signal)
- Canonical `main`: `6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf`
- PR 318 head before this round: `bcbc9c349cd463e1eb31927436a1a0f786e0d119` (181-b immutable report head)
- PR 318 head after this round: the SELF report commit (verified via `git ls-remote origin oap/181-authoritative-catalog-collection` and `gh pr view 318 --json headRefOid`, both equal to the report head, before the two-byte OK)
- Strategic evidence at the exact current head (read-only): `review-artifacts/181-b-review/` — `identity.json` sha256 `7f25af0416f0c08e1481d7e081abc4b72dde368c6ad4d25b76bdcc8eb12938b4`, `results.json` sha256 `d877f804163bd254f01fa71a220616ca1e5888a7d75c355837d314c8ea1ede66`, `runtime_semantics_probe.py` sha256 `9bb455fea7b2b2f8ad0b8d4f4b84f157d12b2dda773fcbf4b6434943aa0b237f`, `runtime-semantics-results.json` sha256 `6635df6244fb8b1724a513380fd659730bb1242ab1f22a721f89bffc4192f6ea`, `hosted_probe.py` sha256 `73a70b828add4a14139e3ef95949da4e0c9c971007860bd2edb035c22258d2b6`, `hosted-results.json` sha256 `7dd6e2e076998a9da53cbb53b9560e3c93a3a2ff493a14bcf3465b572f6ad968`

## Summary

181-c closes the three independently reproduced semantic gaps at the exact
181-b head, making standard-v1 catalog eligibility agree with the CURRENT
ordinary Chat admission/accounting and route-policy contracts:

- **C1**: a value fitting a pricing column is no longer treated as proof the
  gateway can safely bill that shape. Positive separately billed reasoning
  charges and positive per-request fees are EXCLUDED from ready standard-v1
  rows by the shared deterministic source eligibility decision, enforced
  identically by the collector and the supplied-bundle validator. A
  published zero reasoning price is carried as an explicit no-charge; zero
  per-request fees are documented no-charges.
- **C2**: the blanket "accepted unreachable" hosted-charge assertion is
  gone. Positive hosted-operation charges are excluded with the exact
  machine reason; model variants (`:online`-style identities) are never
  declared safe by analogy.
- **C3**: baseline wildcard routes retain local authority over the upstreams
  they govern under the resolver's ACTUAL destination semantics (fixed
  `upstream_model` equality, or passthrough pattern == upstream identity —
  never public string similarity). The collector retains all governing rows
  and invents no parallel exact route; the validator BLOCKs a re-inserted
  parallel route for a governed upstream.

No runtime accounting, provider policy, or route-resolution behavior
changed; no apply/refresh command was added; no new dependency, schema, or
deployment change. Transport/capture-identity closure remains REQUIRED in a
later same-PR round (prospectively 181-d); 182/183/184 mandates are
unchanged. This round is a bounded continuation — 181 is NOT closed.

## Changed paths (implementation commit `502369d` only)

- `app/slaif_gateway/services/catalog_refresh/source_evidence.py`
- `app/slaif_gateway/services/catalog_refresh/collection.py`
- `app/slaif_gateway/services/catalog_refresh/validation.py`
- `app/slaif_gateway/services/catalog_refresh/rendering.py` (semantic wording only)
- `tests/unit/test_catalog_refresh_collection.py`
- `tests/unit/test_catalog_refresh_source_evidence.py`
- `docs/catalog-refresh.md`
- `admin/catalog-refresh/README.md`

(8 files, +769/−176. `oap/orders/181-c-...md` and `oap/active` were committed
byte-identical to the strategic bytes in the activation commit `ab8a37a`.
`docs/cli-reference.md` required NO change — its catalog-refresh section
delegates semantics to `docs/catalog-refresh.md` and states no carried-dim or
unreachability claims (verified by inspection). No fixture files were added
(all new test worlds are bounded synthetic rows constructed in-test).
`oap/reports/181-b-...md` untouched.)

## C1 — Decision: eligibility follows executable billing, not TSV capacity

The shared deterministic source eligibility decision
(`standard_v1_billing_decision` → `_router_billing_decision`) now excludes
from ready standard-v1 rows:

| Observation (all authoritative rows of a model) | Decision |
|---|---|
| Positive `internal_reasoning` charge (per 1M) | EXCLUDED — `reasoning_charges_unrepresentable`: ordinary Chat admission reserves at the output price and finalization bills reasoning tokens at the reasoning price, so the reservation does not cover a separately billed reasoning charge; no qualified reasoning billing contract is authorized |
| Positive `request` fee (per request) | EXCLUDED — `request_charges_unrepresentable`: ordinary Chat admission and finalization do not bill an additive per-request fee (the request column serves native-module/fixed-request contracts); no qualified per-request billing contract is authorized |
| Published ZERO `internal_reasoning` | CARRIED — `("reasoning", "0", "per_1m_tokens")`: an explicit no-charge, never a missing fact; a missing reasoning price makes finalization bill reasoning tokens at the output price (`reasoning_price_fallback_to_output`), which would change actual local billing |
| Published ZERO `request` | documented no-charge, not carried — ordinary Chat bills no per-request fee at all, so carrying nothing changes no local billing |
| Published ZERO `web_search` | documented no-charge, not carried — the standard chat contract has no web-search billing dimension and a zero publishes no provider-side cost |
| All prior 181-b exclusions (long-context standard prices even $0, contextual overrides, positive cache-write charges, unknown billing keys, source `-1` sentinels) | UNCHANGED |

Enforcement is shared and independent: the collector applies the decision
BEFORE proposal (default discovery retains flat siblings and records one
explained inventory entry per excluded row; an explicitly selected excluded
model BLOCKs with `missing_required_selection`), and the validator
RECOMPUTES the decision from the parsed official evidence for every bundle —
a supplied or tampered bundle that proposes an excluded model is BLOCKed
(`proposed_row_billing_ineligible` with the exact policy reason) even with
correct provenance and TSV shape, and a bundle that drops or alters the
carried zero no-charge is BLOCKed
(`proposed_row_billing_dim_missing` / `proposed_row_billing_dim_mismatch`).
Original source observations and provenance are preserved (the published
per-request fee still publishes a `pricing:request` observation in the
report; it is no longer proposal-representable). No fee/FX/limit inference
was introduced.

Runtime boundary (read-only probes, explicit SYNTHETIC pricing/FX objects,
repositories poison — no DB, no inference, no ledger mutation), now pinned
in `tests/unit/test_catalog_refresh_source_evidence.py::test_runtime_boundary_ordinary_chat_billing_semantics`
(1000 output tokens, input 0.54 / output 2.16 / cached 0.054 USD per 1M):

| Probe | `PricingService.estimate_chat_completion_cost` | local final components (`_component_slaif_costs`) |
|---|---|---|
| request fee 0.1 published | `0.00216` — the fee is OMITTED from the ordinary Chat total | (fee not additive by contract) |
| reasoning 9 per 1M published | `0.00216` — reserved at the OUTPUT price | `output_reasoning = 0.009` — final EXCEEDS the reservation |
| reasoning ZERO published | `0.00216` | `output_reasoning = 0` — the zero keeps finalization at zero, which is why it is carried |

These measurements establish WHY the eligibility is conservative without
modifying the runtime.

## C2 — Decision: no blanket unreachable-hosted assertion

A positive hosted-operation charge (the published `web_search` per-call
price) now EXCLUDES the row with `hosted_operation_charges_unrepresentable`:
hosted operations are denied in the standard-v1 profile and no reviewed
per-model executable contract proves the charge cannot be incurred. The
`BillingDecision.accepted_unreachable` mechanism and the
"accepted unreachable" route-warning/report wording are removed entirely —
unknown requires review/exclusion, never a confident no-hosted-capability
claim. Model variants or intrinsic hosted/search behavior are never declared
safe by analogy with optional tools: a `synth/alpha:online`-style identity
with a positive hosted charge is excluded on the price, identically to an
ordinary flat identity (identity is not laundering); copied source
snapshots and caller-supplied inventory/warnings cannot launder an excluded
model into READY (the validator recomputes eligibility from the parsed
official evidence). No tool permission is granted, no runtime policy
changed, no provider inference. All reasons stay in the single report.

## C3 — Decision: fixed-upstream wildcard routes retain local authority

Coverage is now the resolver's ACTUAL destination rule
(`resolved_model = route.upstream_model or requested_model`), implemented as
one shared pure predicate (`se.wildcard_route_governs_upstream`) used by
BOTH the collector and the validator:

- a prefix/glob row with an explicit `upstream_model` is a FIXED destination
  — it governs exactly that upstream, whatever the public pattern is;
- a prefix/glob row with an empty `upstream_model` passes the public name
  through — it governs the upstreams whose identity matches the public
  pattern (`startswith` for prefix, `fnmatchcase` for glob).

Public-pattern string similarity against an unrelated fixed destination is
NOT coverage (no broadening of public-prefix rules to every unconfigured
model).

Collector: `_baseline_identity_for` retains every governed upstream
(`excluded_subset` / `baseline_contract_not_flat`) with a retention detail
that records ALL governing rows (`prefix 'public/' -> 'synth/alpha'`,
`+N more` bounded) — alternatives are never reduced to one row — and
proposes NO parallel exact route. A retained wildcard is not a source
disappearance: the public pattern name keeps its 181-b local-pattern
`NOT_FETCHED` disposition and no `model_disappeared` finding fires.
Supplied-bundle validation: any proposed chat route for a governed upstream
is a re-inserted parallel route that bypasses local authority and is BLOCKed
with `wildcard_route_authority_bypassed` (live collection and offline
replay alike); the inventory re-verification of
`baseline_contract_not_flat` claims uses the same predicate. Exact-alias
authority (181-b) is unchanged and stays green. Existing-row changes remain
create-only BLOCKED until 183; no route/import mutation was added.

## Measured commands and results (this machine, this round)

At implementation head `502369d71265dacfcdca993e81721e60d8f3e8f3`, in the
existing `.venv`, on this machine:

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest tests/unit/test_catalog_refresh_{source_evidence,bundle,policy,report,seal,collection,sources}.py tests/unit/test_cli_catalog_refresh.py tests/unit/test_provider_catalog_proposal.py` | **318 passed in 30.73s**, exit 0 (9 suites; 181-b baseline was 308 — +10 new tests, 0 removed, all 181-b positive source/alias/seal paths retained) |
| `.venv/bin/python -m ruff check app tests` | `All checks passed!`, exit 0 |
| `.venv/bin/python scripts/check_documentation.py` | `DOCUMENTATION_CHECK=OK files=91`, exit 0 |
| `git diff --check bcbc9c349cd463e1eb31927436a1a0f786e0d119` | clean (no whitespace findings introduced this round), exit 0 |

Positive proofs (focused tests, mocked HTTP AND DNS across all CLI tests as
before; fixture time/freshness deterministic across a UTC date boundary as
before): request/reasoning/web_search reproducers now refuse ready rows with
the exact machine reasons and explicit selection BLOCKs; zero-reasoning
carries as `("reasoning","0","per_1m_tokens")` with drop/alter tampering
blocked; zero request/web_search stay READY with core dims only; flat
siblings and one-model bootstrap still work; fixed-upstream prefix/glob
retention through collector → validator → artifact plan (governed upstream
absent from `routes-proposal.tsv` and `pricing-proposal.tsv`); multiple
governing alternatives all recorded; passthrough prefix/glob retained;
fixed prefix to another upstream NOT covered (normal exact proposal
proceeds); supplied parallel route for a governed upstream BLOCKs
(`wildcard_route_authority_bypassed`); exact-alias and multiple-alias
regressions green; CLI exit pins 0/10/20 and baseline identity evidence
preserved. No live smoke was run this round: the order authorizes mocks
sufficiently for this correction, and a smoke would not close transport
assurance in any case (see Remaining findings).

## Negative / privacy / no-mutation / no-runtime-diff evidence

- `git diff bcbc9c3..502369d --name-only` = exactly the eight implementation
  paths listed above; NO changes to `services/pricing.py`,
  `services/accounting.py`, `services/hosted_tool_policy.py`,
  `services/route_resolution.py`, DB/schema/migrations, import executors,
  dependencies (`pyproject.toml`/lock untouched), Docker/Compose/NGINX/
  workflows, production scripts, final wrappers, root `AGENTS.md`/
  `message.txt`, historical evidence, or `.local-provider-catalog`.
- Read-only runtime references only: `PricingService.estimate_chat_completion_cost`,
  `_component_slaif_costs`, `classify_chat_completion_capabilities` semantics
  and the resolver's `upstream_model or requested_model` rule were READ to
  derive the conservative policy; focused tests invoke the pure pricing/
  accounting functions with explicit synthetic objects (repositories
  poison) — no DB, no inference, no ledger mutation.
- No shared 5432 access, no `.env`/credentials reads, no production URL use,
  no live DB mutation, no real inference, no Codex invocation, no email,
  no tag/release, no merge, no auto-merge, no new PR. `oap/active` remains
  exactly the strategic bytes `181-c` (5 bytes, no trailing newline).
- Cleanup: this round's scratch lived outside the repo (`/tmp/obj181c/`,
  `/tmp/ci_poll_181c.sh`, `/tmp/patch_181c_*.py`) and is removed after
  publication except the CI poll log and this report's evidence.

## Documentation impact statement

`docs/catalog-refresh.md`: reason table (three new executable-billing
reasons replace the now-unreachable `conflicting_billing_observation` row;
`baseline_contract_not_flat` documents the destination-semantics coverage),
proposal scope (executable-billing rule, zero semantics, hosted-charge
exclusion replacing the accepted-unreachable claim), refresh preservation
(governance rule and `wildcard_route_authority_bypassed`).
`admin/catalog-refresh/README.md`: collection summary updated to the exact
policy. `docs/cli-reference.md`: unchanged (verified no stale claims).
Report renderer wording updated (semantic wording only) to the exact policy.

## Corrections to 181-b claims (181-b remains immutable)

- 181-b carried positive `reasoning` (per 1M) and `request` (per request)
  charges as flat-contract dimensions. That was a TSV-capacity claim, not an
  executable-billing one: the actual ordinary Chat estimate omits the
  request fee and reserves reasoning at the output price (measured above).
  Corrected in 181-c by exclusion with exact machine reasons (C1).
- 181-b asserted published `web_search` charges were "accepted unreachable
  (denied hosted operation in the standard-v1 profile)". No reviewed
  per-model executable contract supports that blanket assertion (the actual
  `classify_chat_completion_capabilities` found no denial for the probed
  identities, and the `:online` suffix is documented by the provider as
  enabling web search). Corrected in 181-c by exclusion (C2).
- 181-b's wildcard coverage compared the public pattern against the upstream
  ID by string similarity only, so a prefix/glob row with a FIXED
  `upstream_model` governing the upstream was missed and a parallel exact
  route was invented. Corrected in 181-c by the shared destination-semantics
  predicate, retention of all governing rows, and the supplied-bundle
  parallel-route blocker (C3).
- 181-b's `conflicting_billing_observation` reason became unreachable once
  positive ancillary charges exclude the row first; it is removed rather
  than kept as dead policy.

## Remaining findings (deferred — UNCLOSED, no closure claimed)

- Transport/capture assurance (request budget, two-phase budget, bounded
  decoder allocation, proxy handling, redirect edge) remains UNCLOSED per
  the 181 strategic assessment; this round's mock-only correction does not
  close it. Actual-collection-versus-replay and exact tooling identity
  closure remain REQUIRED in a later same-PR round (prospectively 181-d).
- Full 182 (Codex research boundary), 183 (atomic apply/accounting), and
  184 (final wrappers E2E) mandates are unchanged and remain REQUIRED.
- 181 is NOT closed: this round is a bounded semantic continuation on the
  same PR; passing these tests does not claim all of B1–B4 closed beyond
  what is stated, and no RC2/release/production claim follows.

## Objective 181 status

PR 318 open; 181-a and 181-b reports immutable; 181-c implemented and
reported. Next: strategic review of this report and the PR head;
transport/capture closure (prospectively 181-d) before any 182 activation.

## CI (implementation head only)

CI results at implementation head `502369d71265dacfcdca993e81721e60d8f3e8f3`:

All 10 check-runs at the implementation head succeeded (queried via
`gh api repos/ulfe-lmi/slaif-api-gateway/commits/502369d71265dacfcdca993e81721e60d8f3e8f3/check-runs`;
polling finished 2026-09-23T01:20:36+02:00):

| Check | Conclusion |
|---|---|
| Analyze (javascript-typescript) | success |
| Analyze (python) | success |
| Analyze Python | success |
| CodeQL | success |
| Docker Compose smoke | success |
| Documentation hygiene | success |
| OpenAI-compatible E2E tests | success |
| Playwright browser smoke | success |
| PostgreSQL integration tests | success |
| Unit, lint, and migration head | success |

(PR 318 state at publication: OPEN, CLEAN/MERGEABLE; no change-request
reviews.)
