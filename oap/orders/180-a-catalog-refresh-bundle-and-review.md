# OAP Work Order — 180-a

PR mode: `CREATE_NEW_PR`

## Objective and business outcome

Implement the first bounded slice of the human-authorized administrator catalog
refresh workflow: a typed canonical proposal bundle, safe baseline comparison,
deterministic readiness/warnings/completeness, and ONE sealed self-contained
REVIEW.html. A busy administrator reads that file, not a pile of manifests.
This objective must deliver executable offline review tooling and a real
read-only baseline export, not a design-only PR or hardcoded mock report.

The full human mandate remains one refresh -> one trustworthy report -> one
explicit audited apply command. Later objectives implement deterministic live
sources/ECB and isolated Codex research (181), atomic audited supersession and
accounting protections (182), and final shell UX/E2E/docs (183). Those are not
silently deferred out of the thread goal. Do not implement their mutations or
research in this objective. Make intermediate capabilities honest: no refresh
or apply command may claim to work before its implementation exists.

## Verified starting state and required reading

Strategic reconciliation 2026-09-22:
- Repository ulfe-lmi/slaif-api-gateway.
- Remote main `b1e6ef0a49d7e5ab6376f6344290f58ff844e671`.
- Zero open PRs; Objective 179 is terminal, PR #316 merged
  2026-09-20T20:01:18Z. Unique matching 179-a order/report verified.
- Shared active before activation `179-a`; tracked tree clean; shared checkout
  remains 179 report head `18a988dd68a1325e9df736bc8878a835d6978ed4`.
  Coding agent owns Git reconciliation/branching; strategy has not switched it.
- All current main check runs successful (nine stable contexts; an additional
  successful repeated Analyze Python run is present). Main ruleset protects
  deletion/non-fast-forward, not required CI/reviews. Strategic gates apply.
- Only release v0.1.0-rc.1; no tag/release action authorized. New work supersedes
  the prior stop-for-tag recommendation but does not waive human release gates.

Read repository AGENTS.md and coding OAP protocol, this complete order, current
product-scope/accounting/security/database-schema/catalog/import/CLI contracts
relevant to the change. Compact strategic architecture is the current broad
architecture companion; full architecture only for unresolved details.

Inspected existing reuse points:
- `services/provider_catalog_proposal.py`: official fetching/parsing, include/
  exclude model filters, ordinary Chat/package selection, generated route/
  pricing TSV validation and current confidence labels. Reuse its contracts;
  do not expose old confidence scores as readiness authority.
- `services/route_import.py`, `pricing_import.py`, `fx_import.py`: parse,
  validate, classify and build execution plans. All existing execution plans
  are create-only. FX has a service-level import but CLI only add/list/latest.
- `cli/common.py`: transaction-bound CLI DB session. Use read-only consistent
  snapshot export without application/API startup, not a settings dump.
- Pricing/FX active lookup uses validity windows; normal finalization uses a
  captured estimate. Do not alter these paths here; 182 owns history protection.

## One objective, one PR

Create branch `oap/180-catalog-refresh-bundle-review` from exact verified main.
Suggested title: `feat: add sealed catalog refresh bundles and one-page review`.
One new PR. Commit strategic order/active bytes unchanged. Continuations amend
this PR only. Never merge or enable auto-merge. Reconcile any unexpected remote
change before implementation; report genuine conflict instead of inventing state.

## Allowed paths

- `app/slaif_gateway/schemas/catalog_refresh.py` (new typed contract)
- `app/slaif_gateway/services/catalog_refresh/` (new bounded package: bundle,
  baseline, policy, validation, rendering and sealing only; no network/research/
  apply/database-mutation implementation)
- `app/slaif_gateway/cli/catalog_refresh.py` (new offline review, verify and
  read-only export-baseline entry points; names may be refined consistently)
- `app/slaif_gateway/cli/main.py` (register that group; only necessary isolated
  offline invocation wiring, no broad settings/logging behavior rewrite)
- `admin/catalog-refresh/README.md` (new, actual current entry points and clear
  eventual wrapper contract; no fake refresh/apply scripts)
- `docs/catalog-refresh.md` (new current feature contract, evidence/policy/
  bundle/baseline/seal semantics and staged research/apply boundaries)
- `docs/README.md` (task navigation link only)
- `docs/cli-reference.md` (new actual commands and purpose)
- `tests/unit/test_catalog_refresh_bundle.py` (new)
- `tests/unit/test_catalog_refresh_policy.py` (new)
- `tests/unit/test_catalog_refresh_report.py` (new)
- `tests/unit/test_catalog_refresh_seal.py` (new)
- `tests/unit/test_cli_catalog_refresh.py` (new)
- `tests/integration/test_catalog_refresh_baseline.py` (new)
- `tests/fixtures/catalog_refresh/` (new public/synthetic non-secret fixtures
  only; no real local baseline, generated credentials, raw private artifacts)
- `oap/orders/180-a-catalog-refresh-bundle-and-review.md` (unchanged)
- `oap/active` (unchanged strategic bytes `180-a`)
- `oap/reports/180-a-catalog-refresh-bundle-and-review.md` (new immutable)

No other paths. In particular no migrations/model/schema tables, production
dependencies, workflows, Docker/Compose/NGINX, accounting/provider-forwarding/
key/security semantics, existing import mutation behavior, old OAP/verification
records, or root AGENTS changes. Prefer Python stdlib plus existing dependencies.
If exact reuse needs a small adjacent refactor outside the list, return the
specific need for strategic continuation rather than duplicate the algorithm.

## Canonical data and baseline contract

1. One versioned typed `catalog-refresh.json` is canonical proposal semantics.
   Require bounded schemas with unknown fields rejected, unique identities,
   finite exact decimal strings, known units/currencies, aware UTC dates,
   safe bounded URLs/strings, and no float arithmetic for money/FX. Do not
   allow caller-supplied READY, confidence, counters or validation results to
   bypass recomputation. Reject duplicate JSON keys and non-finite values.
2. Preserve run ID/generated time, SLAIF revision/schema, prompt/extractor/
   tool version identities (Codex NOT_RUN allowed here), policy/profile,
   provider/model selection, source manifest and field-level provenance,
   baseline identity/mode, candidate facts, change plan, warnings/exclusions,
   source inventory/reconciliation and validator results. Use N/A/NOT_RUN
   explicitly; don't fabricate evidence for unavailable research or SQL checks.
3. Every proposed field retains provider/model/field/value/unit/currency,
   authoritative URL, retrieval/publication times where relevant, extractor
   identity/method, deterministic versus semantic extraction, and supporting
   sources. Distinguish authoritative source content from model-authored
   explanation. Citation alone is not proof. Source/evidence content is data,
   never runnable instructions, HTML, shell or an authority grant.
4. Bootstrap requires an explicitly empty baseline, marked FIRST INSTALL — NO
   LOCAL BASELINE; no invented before/after values. Refresh requires a valid
   consistent snapshot from the target DB or an explicit exported baseline.
   Connection failure must never become empty bootstrap. Baseline age/mode and
   whether SQL was actually checked must be visible in the report.
5. Implement read-only consistent PostgreSQL baseline export for provider
   configuration metadata, routes, pricing and FX (including relevant history
   and validity windows). Export allowlisted metadata, not ORM dumps/settings:
   exclude provider secrets, connection strings, keys, token digests, users,
   sessions, request content, freeform sensitive notes and unrelated data.
   Provider secret ENV VARIABLE NAMES may be retained as names if required,
   never their values. Apply explicit redaction/shape rules to free metadata.
   Use consistent transaction isolation/read-only semantics; paginate correctly
   and never silently truncate. Include target identity sufficient for later
   apply preconditions without credentials. No writes/audit mutation from export.
6. Compare selected scoped identities including meaningful old/new values,
   currencies, dimensions, model mapping, capability, validity and visibility.
   Do not count source timestamps as price changes. Aggregate unchanged rows;
   model disappearance is REVIEW with retain-local/no-delete semantics. Outage,
   truncated retrieval or missing mandatory selection is not disappearance.
7. The profile contract for future sources must be explicit: standard v1 is
   ordinary text Chat Completions with explicit supported streaming and local
   models visibility; no hosted, multimodal, special-tier, Responses/Codex or
   unknown capabilities. Model include filters can select one model; never
   impose the old ten-model bootstrap requirement. Preserve existing provider
   destinations/aliases/authority; reject unreviewed capability widening in
   import plans. Do not invent model price/limits from related models.

## Deterministic readiness, completeness and validators

8. Overall state exactly READY, READY_WITH_WARNINGS, BLOCKED. Severity exactly
   BLOCKER, REVIEW, INFO; structural evidence VERIFIED, REVIEW, BLOCKED.
   No probability/confidence percentage or LLM judgment may set state.
9. Recompute all counts from inventory and row dispositions. Every considered
   source identity accounted for once; selected/out-of-scope counts explicit;
   considered = ready + excluded + blocked/incomplete. Ready = new + changed +
   unchanged. Track prior-baseline missing/deprecated models separately without
   pretending they are fetched records. Duplicate/conflicting IDs, unexplained
   gaps, retrieval caps/truncation and incomplete source inventories block the
   affected required plan. Show filtered reason counts and individual details.
10. Versioned configurable thresholds with deterministic tests: price movement
    >25%, any zero transition, FX movement >3% => REVIEW (zero not percentage
    division); missing required input/output/dimension, unknown/ambiguous unit,
    currency inconsistency, authoritative contradiction => BLOCKER for selected
    imports. Unsupported rows may be excluded with aggregated REVIEW while a
    complete permitted selected plan remains ready; explicitly selected required
    model missing cannot be hidden as exclusion. Legitimate zero values require
    explicit policy/provenance, never substitution for unknown.
11. Freshness: source retrieval >24h REVIEW, >72h BLOCKED for required source;
    FX publication date >3 calendar days REVIEW, >7 BLOCKED. Future/inconsistent
    times block; calendar/date calculation explicit UTC. These are versioned
    operator policy defaults, not finance/availability promises. Required
    source failure conflicts block; Codex failure does not block if all required
    facts already have sufficient deterministic sources. FX not required when
    every selected price is EUR: show N/A rather than missing/error.
12. Reuse actual route/pricing/FX parse/validation/classification/execution-plan
    functions, don't duplicate validation rules. Validate deterministic TSV/JSON
    artifacts by reading the exact generated bytes through those parsers;
    ensure paired route and pricing identity/model/endpoint/currency, required
    dimensions and supported capabilities. FX service supports CSV/JSON, so use
    a supported format rather than inventing TSV support.
13. Existing create-only execution remains unchanged. For this objective,
    supersession/update operations may be represented and displayed as changes
    but their apply plan is BLOCKED/NOT_SUPPORTED until 182 implements it.
    Distinguish schema-valid from execution-plan-valid. Do not relabel a blocked
    existing import classification as pass. Bootstrap create-only fixtures
    and no-change refresh may pass the implemented gates; no apply entry point
    exists yet. Show offline-versus-live validation scope precisely. Empty
    unchanged plan should be a truthful NO CHANGES result, not invalid import.

## One primary HTML report

14. Produce `REVIEW.html`: static standalone UTF-8 with inline CSS, native
    details/summary, accessible semantic tables, readable at ordinary laptop
    width, print styling. No external JS/CSS/fonts/images, no JS required, no
    automatic network fetches. Escape all data; allowlist safe evidence-link
    schemes and URLs; no javascript/data URIs, injected HTML, event attributes,
    CSS/markup or form actions from source data. A restrictive CSP is useful
    defense-in-depth but does not replace escaping/URL validation.
15. First screen: overall state and why; bootstrap/refresh/target baseline;
    provider/profile scope; counts and ranked aggregated warning summary;
    source retrieval/schema/completeness/pairing/change/unsupported/FX/import
    gate checklist; small per-provider new/changed/disappeared/unchanged summary;
    current/proposed FX and date; run/version/digest identity compactly.
    Main content is WHAT CHANGED, not a full catalog. Price table old/new input,
    output/other billed dimensions, unit/currency and percent; route table
    current/proposed/reason; FX table current/proposed/delta/source/date.
16. All details within this one file: new/changed/disappeared/deprecated models,
    excluded reason counts and rows, unchanged rows collapsed, field provenance
    with exact sources/methods, every warning, full validator outputs and exact
    proposed import rows. Do not require opening a manifest/TSV for a decision.
    Detailed evidence files remain behind the report for machines/audit only.
17. CLI prints only compact state, exact report file URI/path, changed/warning/
    blocker counts and scoped stage information. Normal output must never say
    "review these ten files". Offline bad input should yield a safe BLOCKED
    report when possible, with nonzero exit; non-parseable errors must not leak
    input secrets or raw source text. Define exit codes in docs/help.

## Sealing and reproducibility

18. Renderer and artifacts deterministic from normalized bundle inputs,
    including explicitly supplied run time/ID. Stable order/Decimal encoding;
    report not current-clock-dependent on re-render. Avoid circular hashes:
    semantic bundle + derived artifacts -> manifest -> authenticated receipt;
    no file claims a digest including its own digest/signature bytes.
19. Implement local HMAC-SHA256 sealing/verification using a runner-owned key
    outside the bundle/research directory, mode 0600, atomically created and
    never overwritten silently. No provider/session/HMAC-runtime key reuse.
    Support explicit owner-controlled key/state path for tests/operators;
    document local trust scope and rotation/portability, not protection from
    the admin controlling that key. Future researcher must never receive it.
20. Seal covers exact canonical bundle, evidence inventory/digests, generated
    proposal bytes, validation results, report, provider/profile/policy/baseline
    identities. Verify all files and recompute semantic/renderer correspondence;
    no trusting a caller's READY inside JSON. Manipulating proposals+report+
    ordinary checksums together must fail without external sealing authority.
21. Safe filesystem rules: immutable publication to new run directory, refuse
    existing completed output; atomic write/rename; strict relative manifest
    paths, regular files, no symlinks/traversal/absolute escape, size/depth caps,
    duplicate files/JSON keys rejected. Never execute shell from proposals or
    render unsafe URLs. Verification works on bytes safely read/copied once,
    not path checks followed by unchecked later reads. No key material in
    reports, bundles, logs or exceptions. No re-sign-on-verify bypass.

## Acceptance and evidence

- AP-1: Typed bundle and actual CLI render/verify/export-baseline work on
  independent inputs; deterministic output; no hardcoded fixture-only report.
- AP-2: All states/severities/count identities and meaningful delta cases pass
  positive/negative tests, including first-install, unchanged, conflicting,
  zero/missing/unusual, stale/future, failure/truncation and filtered models.
- AP-3: Actual route/pricing/FX validators consume produced bytes; schema and
  execution validity separate; unsupported updates blocked honestly; no direct
  mutation or new unsupported gateway capabilities.
- AP-4: Report first screen meets 30–60 second review design; every detail
  accessible inside one artifact; source strings safely escaped; browser file
  opens without server/network/JS; printed layout usable.
- AP-5: Seal/identity proves report/proposal/evidence/validation correspondence;
  tamper/recomputed-unkeyed-manifest/wrong-key/missing-file/path/symlink/size/
  changing-byte tests fail closed. External authority key not exposed.
- AP-6: PostgreSQL baseline export is complete, consistent and read-only;
  no secrets/personal/request content; outage never bootstrap; stale and wrong
  baseline rejected by review inputs as appropriate. Export and offline replay
  give the same semantic comparison.
- AP-7: Relevant unit/integration/browser verification, docs links/checker,
  changed-file Ruff, diff --check and ordinary final-head CI pass. No skipped
  or pending test called a pass.
- AP-8: Exact path scope, no runtime forwarding/accounting/import-mutation/
  dependency/deployment change, old records unchanged, no provider/production
  call or secret read, task-owned resource cleanup verified after all tests.

Run focused new unit files and targeted existing import/catalog/CLI/documentation
tests relevant to touched boundaries; run PostgreSQL integration for read-only
baseline consistency and redaction. Use Playwright or existing browser tooling
to open representative READY, READY_WITH_WARNINGS, BLOCKED, first-install and
large-unchanged reports from file URLs, deny/log network requests, verify
collapsible content/escaping and inspect screenshots of top screens. Browser
test driver can be disposable; retain non-secret fixtures/screenshots for
strategic review with exact paths. Do not substitute string-presence tests for
actual rendered/behavioral evidence. No new full local suite/HPC qualification.

## Setup and hard boundaries

Use existing VM development tools, local .venv and task-owned test-only
PostgreSQL/containers/browser assets as needed. No shared .env reading or
production/staging data/credentials; no real source retrieval/Codex invocation
in 180 (181 owns that), no real provider inference/email, no GitHub settings or
tag/release. Preserve unrelated .local-provider-catalog/worktrees and devices.
Clean up ONLY task-owned resources after testing; verify actual final state,
including containers, networks and volumes. No global prune. Screenshots and
fixtures contain public/synthetic data only.

Stop/return PARTIAL or BLOCKED for a scope/contract conflict, missing safe
reuse interface requiring out-of-scope refactor, schema/dependency change or
production authority need. Ordinary in-scope test fixes remain yours. Do not
weaken validators/readiness or skip hard gates to manufacture a green report.

## Documentation and immutable report

New docs must distinguish working 180 offline review/export/verify from planned
live research, shell wrappers and audited apply; complete final workflow remains
the roadmap. Keep public front door user-first, link one new task page; don't
put OAP implementation ledger in README. Enumerate actual CLI commands so
documentation inventory checks pass. Explain deterministic vs semantic evidence,
policy thresholds, baseline/SQL scope, seals, print/offline report and limits.

Report exact start/implementation SHA, one PR/base/branch, all changed paths,
AP-1..AP-8 outcomes, exact commands/results, validator reuse, browser/screenshots,
PostgreSQL read-only/consistency evidence, tamper/privacy negatives, CLI UX,
resource cleanup, dependencies/setup, CI states and explicit remaining later
objectives. State any narrower interim unsupported plan truth without reducing
the full final goal. No vague "all safe" or future-state claims.

Push all claimed non-report GitHub state before drafting. Atomically publish
one immutable report with literal implementation SHA and `Report publication
commit: SELF`. Final report-only commit first parent equals implementation SHA,
changes only that report, and is pushed PR head at signal time. No mutation
after publication; do not rewrite old orders/reports. Inspect report-head checks
and state pending honestly. Send exactly two-byte OK on verified response FIFO.
Leave PR OPEN; only strategy independently accepts and merges.
