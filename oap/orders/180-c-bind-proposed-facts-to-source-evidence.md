# OAP Work Order — 180-c

PR mode: AMEND_EXISTING_PR

## Objective and reason

Make the offline catalog review prove that proposed values are supported by
the supplied source contents. Correct the remaining R3 trust failure on the
same Objective-180 PR. A matching hash of arbitrary bytes and an official URL
are not evidence of a model's price, units, limits or capabilities.

This is a deliberately focused continuation. Do not repeat the entire 180-b
rewrite. Preserve its useful improvements and close the source-evidence
requirements below with independent behavioral tests. This round does not
declare all of Objective 180 complete; remaining issues are explicitly retained
below for further same-PR continuations. The full human mandate remains the
complete refresh -> one REVIEW.html -> explicit audited apply workflow, including
subsequent live research, transactional supersession, and end-to-end onboarding.

## Verified GitHub and OAP state

Verified 2026-09-22 after sole response helper 37804 completed with exact
RESPONSE_OK_EXACT and exit 0:

- Repository: ulfe-lmi/slaif-api-gateway.
- Remote main: b1e6ef0a49d7e5ab6376f6344290f58ff844e671.
- Unique open PR: #317, branch oap/180-catalog-refresh-bundle-review, base main.
- Current PR/report head: 80b8242dc5a4092a0d52aa34da6167e9a860ec3c.
- GitHub verifies that 80b8242 is report-only, first parent
  4c70c29369077782105f5c5c64f3b8935ead2718, exactly the implementation SHA
  named by the immutable 180-b report.
- Implementation 1f20b19a2b0146e4ebb218d9440ecddedf34f37b changed 27 allowed
  paths; 4c70c29 added only a test. Application trees are identical between them.
- All ten checks passed at 4c70c29. Report-head checks were still running at
  this activation review; query current state. Pending is never passed.
- PR remains OPEN and mergeable. Main protection has deletion/non-fast-forward
  rules, no configured required-check substitute for strategic acceptance.
- Only published release remains v0.1.0-rc.1. No tag/release authority here.
- Active before this order: 180-b. Working tree clean at review.
- The 180-a and 180-b orders/reports are immutable. Do not edit them.

Read this order, the prior two orders/reports, applicable repository/OAP
contracts, and the relevant current code. Commit the strategic order and active
pointer unchanged. Continue this same branch/PR; do not create another PR,
merge, enable auto-merge, or activate any later objective.

## Independent failure and report reconciliation

Reproduced at committed 1f20b19 (identical application tree at 4c70c29): load
the current bundle-first-install.json in memory; for every source set
evidence_b64 to base64 of the two bytes {}, and content_sha256 to SHA256 of those
same bytes. Call load_bundle and validate_bundle with no baseline and the
bundle's policy. Result: READY, zero warnings, one executable route row and one
executable pricing row. The evidence contains no model, price or capability.

The 180-b report's own source example contains only reference and snapshot
labels, no billed values. Its claim that independent per-field observations
are compared is not established by _fact_observations: it copies one selected
fact's values to each named source and then compares those copies. Existing
schema checks for a referenced source's existence are useful but do not bind
a field's value to source contents. Extraction='deterministic' and arbitrary
extractor strings remain caller supplied; removing the authoritative boolean
did not remove this trust shortcut.

Do not repair only the exact {} input. Fix the evidence-to-fact contract.
Do not mark every candidate blocked or downgrade every valid structured source
to a warning to evade positive-path acceptance. Do not simply add explanatory
prose while leaving unsupported values import-ready.

## Exact allowed paths

- app/slaif_gateway/schemas/catalog_refresh.py
- app/slaif_gateway/services/catalog_refresh/source_evidence.py (new, pure
  bounded snapshot parsing, observations, normalization and reconciliation)
- app/slaif_gateway/services/catalog_refresh/bundle.py
- app/slaif_gateway/services/catalog_refresh/validation.py
- app/slaif_gateway/services/catalog_refresh/rendering.py (source evidence,
  source counts/details and truthful source-status wording only)
- app/slaif_gateway/services/catalog_refresh/sealing.py (only source/schema
  correspondence integration if necessary; filesystem remediation is later)
- app/slaif_gateway/cli/catalog_refresh.py (only source/schema integration and
  safe source-validation errors; no new commands or filesystem redesign)
- docs/catalog-refresh.md
- docs/cli-reference.md (only affected offline source-input contract)
- admin/catalog-refresh/README.md (only affected offline source-input contract)
- tests/unit/test_catalog_refresh_source_evidence.py (new)
- tests/unit/test_catalog_refresh_bundle.py
- tests/unit/test_catalog_refresh_policy.py
- tests/unit/test_catalog_refresh_report.py
- tests/unit/test_catalog_refresh_seal.py (schema/evidence fixture adaptation)
- tests/unit/test_cli_catalog_refresh.py
- tests/integration/test_catalog_refresh_baseline.py (source fixture adaptation
  only; do not redesign baseline export in this round)
- tests/fixtures/catalog_refresh/ (synthetic snapshots, bundles and affected
  browser evidence; no credentials or real customer data)
- oap/orders/180-c-bind-proposed-facts-to-source-evidence.md (unchanged)
- oap/active (unchanged strategic bytes 180-c)
- oap/reports/180-c-bind-proposed-facts-to-source-evidence.md (new immutable report)

No other paths. In particular no runtime pricing/accounting/forwarding,
existing import executor, DB migration/schema, dependency, deployment,
workflow or historical-record changes. No edits to the existing provider
catalog subsystem: reuse its pure helpers through a bounded adapter here.
If an interface genuinely prevents reuse, report its exact need instead of
duplicating a parser or silently broadening scope.

## C1 — Typed observations and supporting snapshots

Use one canonical typed bundle contract, not parallel competing fact stores.
It may evolve deliberately while this subsystem is still unmerged; document
the version/compatibility decision and reject incompatible inputs clearly.

Each proposed financial/capability/limit fact needs resolvable support: source
identity, publisher, retrieval/publication time where relevant, supporting
snapshot bytes and digest, field/row locator, observed value, unit, currency,
provider/model/endpoint identity, extraction method and reviewed parser version.
An observation must not be manufactured by copying the proposal value to every
source listed in its provenance. Source-level and field-level identities must
agree; dangling, wrong-model/provider/endpoint/field references block.

Represent independent observations so two authoritative sources can actually
disagree about input/output/cached/reasoning/request price, currency, unit,
context/output limit or capability. Compare canonical semantics, not raw string
spellings (1 and 1.0 agree; different units need an explicit supported conversion).
Do not count duplicate URLs, aliases to identical bytes, or repeated references
as independent corroboration. Unknown required values and unresolved required
source conflicts block; no model-family inference or price invention.

Local route choices such as alias, priority and visibility are operator policy,
not facts claimed to come from provider pricing pages. Clearly separate these
from provider-observed capabilities, prices and limits. They may not broaden
the current gateway capability contract or grant hosted-tool authority.

## C2 — Real deterministic parsing, semantic extraction honestly classified

Inspect and reuse existing pure helpers in services/provider_catalog_proposal.py,
including _openrouter_models_from_payload, _openrouter_pricing_candidate,
_convert_openrouter_price, _parse_openai_pricing_docs and
_parse_openai_models_docs where applicable. Do not invoke the live proposal
generator or its fetchers in this round. Do not copy its confidence-score
heuristics into the new report.

- OpenRouter: parse synthetic cached snapshots in the actual official models
  API shape, derive per-token USD values/recognized dimensions and supported
  metadata deterministically, then normalize with exact Decimal arithmetic to
  the existing SLAIF import contract. A fixture-specific envelope containing
  only labels is not an API parser or a positive evidence fixture.
- OpenAI: parse supported cached official pricing/model tables with existing
  pure parsers. Models API identity alone cannot prove a price or context limit.
  Unknown table/unit formats must not be silently accepted. Semantic extraction
  may retain exact supporting page/locator observations and REVIEW status;
  a caller's label or an LLM explanation cannot promote it to deterministic
  verification. Missing or ambiguous required values block.
- FX: give ECB its own publisher/source identity, not a fictitious OpenAI or
  OpenRouter model source. Where needed to prove required USD->EUR facts, a
  small stdlib-only parser for supplied ECB reference-rate XML is authorized
  here (pure offline parsing only). Preserve the original EUR-based quote and
  publication date; derive native->EUR explicitly and bind the normalized fact
  to that quote. Live ECB retrieval remains later work and must reuse this.

Registry/policy decides supported publisher/method/parser/official host and
path combinations. Arbitrary caller extractor strings, https lookalikes,
provider/source-kind mismatches and unsupported units cannot establish trust.
Required evidence from an unapproved source blocks. Explicit operator/manual
input may be REVIEW only where the documented policy deliberately permits it;
it must never masquerade as an authoritative verified source.

Verify actual bytes and their parsed meaning against proposed facts before
declaring source validation passed. Empty, unrelated or contradictory bytes
with a correct self-supplied digest must fail the relevant acceptance gate.
Bound sizes/depth/rows before expensive decoding or parsing; reject malformed
JSON/XML safely; XML must not fetch external entities or resolve network URLs.

Offline replay can prove extraction consistency against supplied snapshots; it
does not authenticate a live retrieval that never occurred. State that exact
scope. Keep snapshot origin/retrieval claims distinct from deterministic
extraction verification. The future trusted collector will establish actual
retrieval; do not fabricate its attestation now or treat a supplied boolean as
one. Keep meaningful valid bootstrap/no-change fixtures and source-gate positive
paths without overclaiming origin authenticity.

## C3 — Inventory and executable proposals must reconcile

Derive source inventory independently from the parsed snapshot, then reconcile
selection, supported scope, ready rows, incomplete rows and excluded rows.
Do not define considered as the sum of output counters and verify that tautology.
No silent row disappearance. A dropped candidate, source truncation, duplicate
source model ID, selected model absent from a complete snapshot, or a proposal
for a model absent from its evidence must be detected. Retain-local behavior
for disappeared models remains; there is no automatic deletion.

Preserve provider+upstream+endpoint pairing, alias behavior, complete pricing,
no-op separation and honest blocking of unavailable updates. Invalid or filtered
rows cannot enter executable artifacts even if another row is valid. Support
ordinary text Chat Completions only under the current standard profile; a
provider's broader catalog does not enable unsupported gateway behavior.

## C4 — One report, evidence available inline, meaningful tests

Render compact truthful source-status and reconciliation summaries in REVIEW.html.
Expanded evidence in the same artifact must show the exact observations,
supporting locators/URLs, parsed values, units/currency and conflicts. No separate
file homework. Keep HTML escaping, no JS/network, and deterministic rendering.
Do not rework the entire first-screen layout in this round; carry that issue.

Required independent-input cases include:

1. Empty {}, unrelated valid JSON/HTML, correct hash/wrong contents, changed
   proposed price with unchanged snapshot, wrong source locator/model/provider,
   unknown parser, and missing evidence: none may yield a false verified-ready
   plan. Include full CLI/report/seal recomputation, not helper-only tests.
2. Two genuinely distinct official-format snapshots with conflicting input,
   output, cached, unit/currency and context observations; repeated references
   to one snapshot; equal numerical values with different decimal spellings.
3. Real-shaped OpenRouter per-token USD -> per-million normalization; OpenAI
   table extraction or honestly classified semantic input; ECB quote/date ->
   USD/EUR normalization when non-EUR prices are selected. No live requests.
4. Independent raw inventory vs selected/output counts, missing/dropped/duplicate
   rows, partial failures and unsupported-capability exclusion.
5. Valid bootstrap/create-only and true no-change refresh, public aliases and
   same model IDs across providers; no degenerate all-blocked implementation.
6. No network fetch, DB mutation, provider call or import invocation from the
   parser/research path; arbitrary snapshot text cannot become code, shell or
   unsafe report markup. Safe errors do not echo secrets or unrelated content.

Run the focused source/bundle/policy/report/seal/CLI tests and affected existing
catalog/import tests, changed-Python Ruff, docs checker/link checks, diff --check,
and ordinary CI. Use a disposable test DB only if adapting the existing
integration fixture requires it; never use shared 5432 or a real catalog.
No full local suite/HPC. Visually inspect the changed evidence details in a
browser with network disabled. Reuse maintained helpers, not tests mirroring
implementation labels. Address relevant unused-code bot findings in touched
source paths without weakening checks or redesigning unrelated code.

## Carried blockers — not waived, not silently fixed in this focused round

These still prevent Objective-180 acceptance and will be reviewed/remediated
in subsequent same-PR continuations; do not mark all original APs passed:

- Baseline capability keys can carry arbitrary private text, including in
  errors. Dropping all pricing_metadata can lose financial comparison meaning.
- Extreme exponent raises decimal.Overflow; financial normalization and exact
  policy boundary semantics need completion. Missing indispensable FX dates
  and baseline inverse-vs-runtime-current interpretation need reconciliation.
- Filesystem parent replacement bypasses lexical symlink checks. CLI verify
  accepts a symlinked key; CLI input reads are unbounded. os.replace publication
  can clobber a concurrently created empty output directory. Special-file and
  aggregate-size handling, descriptor identity/permissions need full review.
- The concurrent snapshot test does not commit between reader pages/queries;
  its current result also holds under READ COMMITTED and is insufficient proof.
- Report first-screen gate checklist remains below the fold. First-install
  historical-SQL wording was false; any correction must be verified along with
  per-provider/FX summaries and truthful current-vs-captured evidence.

The 180-b CLOSED/PASS claims on these boundaries are not accepted by strategy.
Keep all prior reports untouched. This source-focused continuation must not
declare Objective 180 complete, authorize imports, or advance to 181.

## Boundaries, cleanup and publication

Only synthetic/public cached data; no live source retrieval, Codex research,
provider inference, real email, production action or protected credentials.
No runtime import/accounting/deployment/dependency change. Preserve unrelated
worktrees, .local-provider-catalog, root AGENTS.md and message.txt. Clean actual
task-owned DBs/files/keys/containers if created; never global prune.

Publish all implementation to the same PR before drafting the new report. State
exact starting/implementation SHA, exact changed paths, C1-C4 evidence, test
commands/results, real snapshot/observation examples, positive and adversarial
outcomes, report/browser checks and cleanup. Correct the 180-b source-trust
claims explicitly in this new report. List carried blockers as unresolved,
not deferred out of the human mandate or represented as passes.

Publish exactly one immutable 180-c report with literal implementation SHA and
Report publication commit: SELF. Its final report-only commit first parent must
equal that SHA; verify pushed PR head and exact report-only diff. Query final
checks honestly. Signal exactly two bytes OK on the response FIFO and leave
PR317 OPEN. Strategy owns the next continuation and eventual merge decision.
