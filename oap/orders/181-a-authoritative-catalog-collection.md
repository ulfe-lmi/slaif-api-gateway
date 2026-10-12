# OAP Work Order — 181-a

PR mode: `CREATE_NEW_PR`

## Objective and business outcome

Implement real administrator-triggered collection of authoritative OpenRouter,
OpenAI and ECB facts into the existing canonical catalog bundle and ONE sealed
REVIEW.html. Reuse the accepted180 validators, baseline comparison, warning policy,
report and seal. The operator must not hand-author prices/FX or review a stack of
files to prepare a supported one-model or standard-profile proposal.

This objective owns trusted deterministic collection and current-format source
adapters. Codex execution/isolation is a separate next objective182; atomic audited
apply/supersession/accounting is183; final shell wrappers and clean-install/refresh/
apply qualification are184. This refines the original proposed181–183 grouping,
not the human goal. All original requirements remain mandatory. No fake Codex run,
no automatic import, no release, and no claim the whole workflow is complete.

## Verified state and required reading

Verified from GitHub on2026-09-22:

- Repository ulfe-lmi/slaif-api-gateway. Remote main
  6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf, merge ofPR317 at17:12:05Z.
- Zero open PRs. Objective180 is terminal; rounds180-a through180-i accepted as
  the offline foundation. Final implementationb45ef6a8528fe1ed4c98119f5b6aa174ee6ad11a;
  reportb43b60a0958442bf04465c18d620ab77a3852f0d report-only, parentb45ef6a.
- Independent299unit tests and standalone8-case browser passed; browser left
  worktree unchanged. All10 final-PR checks green; all9 post-merge main checks green.
- Shared active before activation180-i; shared checkout remains the180report head,
  clean. Coding agent owns Git fetch/branch reconciliation. Strategy has not reset,
  switched, cleaned or stashed it.
- Ruleset23580289 protects deletion/non-fast-forward. Sole published release
  v0.1.0-rc.1. No tag/release/production authority.

Read the repository constitution/coding protocol, this complete order, current
catalog-refresh/provider-catalog/import/pricing/FX/CLI/security contracts, and
compact architecture. Strategic assessment and updated full requirement ledger:
/home/ubuntu/codex-supervision/slaif-api-gateway/workorders/OBJECTIVE-181-ASSESSMENT.md
/home/ubuntu/codex-supervision/slaif-api-gateway/workorders/CATALOG-REFRESH-IMPLEMENTATION-MANDATE.md
Do not read the full architecture/history without a concrete unresolved need.

Create branch oap/181-authoritative-catalog-collection from exact remote main above.
Suggested PR title: feat: collect authoritative provider catalogs and ECB FX.
One numeric objective maps to one PR. Never merge or enable auto-merge.

## Independently observed source reality (not assumptions)

Strategic public, unauthenticated GET probes at2026-09-22T17:24Z are under
/home/ubuntu/codex-supervision/slaif-api-gateway/review-artifacts/181-assessment/:

- https://openrouter.ai/api/v1/models returned200,730233bytes,444models,6missing
  max_completion_tokens. Five router IDs (auto-beta,fusion,pareto-code,bodybuilder,
  auto) have prompt/completion values -1. The CURRENT180parser rejects the entire
  snapshot as invalid_price. Never turn those values into zero or guessed prices.
- https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml returned200,
 1547bytes; existing pure parser produces29quotes. EUR is the implicit base.
- Official OpenAI pricing/models HTML endpoints return200 but current parsers
  extract0rows. Their official .md versions return200 text/markdown:
  https://developers.openai.com/api/docs/pricing.md (23063bytes)
  https://developers.openai.com/api/docs/models.md (12163bytes).
- Pricing Markdown has distinct Standard/Batch/Flex/Fast sections. The Standard
  table has Short context input/cached input/cache writes/output and corresponding
  Long context columns. Existing parser misses these headers and finds other
  price families instead. Do NOT flatten tiers, use a cheaper section, or mix
  audio/realtime/fine-tuning prices into ordinary Chat prices.
- Models Markdown is an index of per-model official links, not a limits table.
  Fetch appropriate model pages for endpoint/modality/limit/alias evidence.

Probe JSONs record exact sizes/hashes; public .snapshot files are available for
inspection, not application input to be blindly promoted. Re-fetch bounded live
sources for this round's smoke. Website schemas may change; live reality wins.

## Exact allowed paths

- app/slaif_gateway/services/catalog_refresh/collection.py (new orchestrator)
- app/slaif_gateway/services/catalog_refresh/sources.py (new trusted bounded HTTP
  acquisition and source-adapter assembly; no model execution)
- app/slaif_gateway/services/catalog_refresh/source_evidence.py (current official
  source formats, contextual billing/endpoint observations and explicit unsupported
  record reasons; preserve strict parsing, locators and fact binding)
- app/slaif_gateway/services/catalog_refresh/bundle.py (collection normalization /
  canonical identity integration; existing import artifact formats preserved)
- app/slaif_gateway/services/catalog_refresh/validation.py (collection-versus-replay
  evidence, eligibility/reconciliation and source issues only; no relaxed monetary,
  capability, readiness or baseline safety guarantees)
- app/slaif_gateway/services/catalog_refresh/rendering.py (actual collection status,
  provenance/completeness/exclusions and stage wording only; preserve180.6 layout)
- app/slaif_gateway/services/catalog_refresh/errors.py (safe collection errors)
- app/slaif_gateway/services/catalog_refresh/sealing.py (only necessary canonical
  collection metadata/replay integration; preserve authenticated-byte/I/O boundary)
- app/slaif_gateway/services/catalog_refresh/__init__.py (necessary exports only)
- app/slaif_gateway/schemas/catalog_refresh.py (typed collection identity,
  source outcomes/inventory and required new observations; deliberate versioning)
- app/slaif_gateway/cli/catalog_refresh.py (new collect entry point and reuse of
  existing review/export/verify; no import/application entry point)
- app/slaif_gateway/services/provider_catalog_proposal.py (ONLY narrow pure helper
  reuse/extraction/current-format corrections if necessary; preserve legacy CLI
  behavior and all existing mutation boundaries; no wholesale rewrite)
- tests/unit/test_catalog_refresh_collection.py (new)
- tests/unit/test_catalog_refresh_sources.py (new)
- tests/unit/test_catalog_refresh_source_evidence.py
- tests/unit/test_catalog_refresh_bundle.py
- tests/unit/test_catalog_refresh_policy.py (collection eligibility regressions)
- tests/unit/test_catalog_refresh_report.py
- tests/unit/test_catalog_refresh_seal.py (collection replay/identity regressions)
- tests/unit/test_cli_catalog_refresh.py
- tests/unit/test_provider_catalog_proposal.py (only if its pure helpers change)
- tests/browser/test_catalog_refresh_report.py (actual collection scope labels only)
- tests/fixtures/catalog_refresh/collection/ (new bounded synthetic/public-format
  fixtures; no credentials, local baseline or whole copied documentation pages)
- tests/fixtures/catalog_refresh/bundle-first-install.json
- tests/fixtures/catalog_refresh/bundle-refresh-ready.json
- tests/fixtures/catalog_refresh/bundle-blocked.json
- tests/fixtures/catalog_refresh/bundle-truncated.json
- tests/fixtures/catalog_refresh/report-layout/two-provider-long-ids.bundle.json
  (existing fixtures: only necessary explicit version/collection-scope fields)
- docs/catalog-refresh.md
- docs/cli-reference.md (catalog collection commands only)
- admin/catalog-refresh/README.md
- docs/README.md (task navigation only if needed)
- oap/orders/181-a-authoritative-catalog-collection.md (unchanged)
- oap/active (exact unchanged strategic bytes181-a)
- oap/reports/181-a-authoritative-catalog-collection.md (new immutable report)

No other paths. No request forwarding, accounting/quota, DB schema/migrations,
import executors, provider configuration/key/ownership mutation, production
scripts, dependencies, Docker/Compose/NGINX, workflows, rootAGENTS/message.txt or
historical-record changes. No Codex/subagent/model invocation in this objective;
182 owns that boundary. No new dashboard or final refresh/apply shell wrappers.
If an adjacent contract change is necessary, return its exact need to strategy.

## C1 — One actual collection command and one report

Add a real CLI entry point, recommended:

  slaif-gateway catalog-refresh collect --bootstrap --profile standard-v1
  slaif-gateway catalog-refresh collect --refresh --baseline-file FILE

Support explicit provider selection (OpenAI/OpenRouter; default both), optional
model include selection (including ONE model), and existing run-root/seal-key
controls. A small alias such as standard -> standard-v1 is fine; do not invent
all-supported capabilities. Define provider/model filter semantics unambiguously.
No ten-model minimum or 40-question setup. --bootstrap is explicitly no baseline;
--refresh requires the existing read-only DB snapshot or explicit exported file.
No DB outage may become bootstrap. Gateway API/server need not be running.

The command gathers sources, builds the typed bundle, invokes the existing actual
route/pricing/FX validators and review/seal pipeline, and prints the established
compact state/report URI/counts. Nothing is imported. A failure produces one safe
BLOCKED report where possible, with nonzero exit and a clear cause; do not require
opening several machine files. Keep provider/pricing metadata prerequisites
honest: existing providers add permits provider-only setup; don't force the old
fixed ten-price bootstrap. Actual apply/provider mutation remains later work.

Default scratch and output must be private, outside the repository; no generated
AGENTS file in this phase, no repo worktree changes merely to collect data. An
explicit operator archive path must satisfy the existing ownership/no-symlink/
no-clobber rules. The seal key stays outside the run tree. Reuse existing safe I/O.

## C2 — Trusted deterministic acquisition and authoritative source selection

Use a bounded HTTP client with fixed official provider/publisher source registries.
Prefer official structured OpenRouter models API and official OpenAI Markdown/
structured page data over human-oriented HTML where available. OpenAI's model API
is identity-only and requires credentials; public-doc collection must work without
that API or any provider key. No authenticated model discovery is required here.
No .env or saved Codex auth read. Provider keys are never sent to public documents.

Validate every requested and redirected URL: HTTPS, approved exact hosts/source
families, no credentials/unsafe ports, no local/private/link-local destinations,
no arbitrary URLs from model/source text. Bound redirects, timeout, retries,
concurrency, request count, decoded-body bytes and total collection size. Reject
unexpected compression or decode it with a real bounded path; content-length
alone is not protection. Respect429/Retry-After within finite limits. Do not
silently turn partial/truncated data into a complete catalog or re-use legacy
follow_redirects=True/unbounded fetching without an enforcement boundary.

Record exact requested/final URL, retrieved UTC time, response outcome, content
method/type/bytes/hash, parser version and source publication date when ACTUALLY
provided. Retrieval time is not publication time; model creation time is not
price publication time. Cache replay must retain original retrieval provenance,
not be stamped as fresh. Public pages/source instructions are data, never shell,
HTML authority or executable configuration. Safe failures omit raw response bodies
and secret-bearing exception text. Deduplicate shared snapshots by URL/bytes;
never repeat a full444-model payload once for every model in the bundle.

## C3 — Contextual normalization, conservative eligibility, complete inventory

Reuse existing pure table/price/model/currency helpers and180registered snapshot
parsers/fact binding. Do not duplicate import validators or resurrect legacy
confidence scores as readiness. Every proposed monetary/capability/model field
must bind to exact observed source bytes, actual upstream model, unit/currency,
source context and locator. Wrong-model pages, navigation/sidebar mentions, related
model names or aliases not explicitly established must not back a fact.

OpenAI: preserve Standard-vs-Batch/Flex/Fast, text-vs-audio/realtime/embedding,
short-vs-long-context and cache-write distinctions. Supported flat ordinary-Chat
prices may be proposed. If a billed shape/tier cannot be represented by CURRENT
SLAIF pricing and runtime policy, exclude it with an explicit reason (or BLOCK
an explicitly required model), not a flattened/maximum/guessed price. No new
pricing/accounting functionality to accommodate new provider tiers. Establish
ordinary Chat support from the applicable official model/API contract; text
modality alone is not proof that a Responses-only/Realtime model supports Chat.

OpenRouter: preserve raw indices/identities and strict JSON validation. Recognized
non-representable values such as the observed -1 router prices must retain their
identity and explicit exclusion/incomplete reason; never become0 or a guessed
related-model price. They must not silently disappear or unnecessarily poison
complete supported siblings in a default discovery package. Explicitly selecting
an unsupported/unpriced model must BLOCK. Malformed structure, duplicate IDs/keys,
nonfinite values, contradictory units/currencies and truncation remain fail-closed.
Unsupported extra billed dimensions that can be exercised by the selected profile
must not be ignored. Explain the evidence for excluding vs accepting such rows.

Use one reviewed standard-v1 scope, ordinary text Chat plus explicit local streaming
policy; no new hosted tools, multimodal, Responses, Codex or function authority by
analogy. Preserve existing provider destinations, route aliases, priority,
visibility, enablement and approved denials on refresh. Upstream availability is
not permission to broaden existing local policy. New routes use exact identities
and conservative existing mappings. New visibility to keys permitting all models
must be surfaced conditionally in the report, not hidden as a price-only update.

Reconcile EVERY observed source model exactly once: supported/proposed, explicit
subset exclusion, unsupported/incomplete/deprecated, retained local, or a required
unresolved gap. Separate source inventory from local baseline rows. Recompute
exclusions from source facts/profile, not caller- or model-declared counters that
could hide valid rows. Model disappearance is REVIEW/retain-local, never deletion;
source outage is a retrieval failure, not disappearance. No READY for an empty
usable bootstrap. Group reasons compactly; all available details stay in the one
report. When data is insufficient, say unknown and do not invent it; Codex fallback
is not implemented or simulated in181.

## C4 — ECB FX, native prices and exact arithmetic

Fetch the official ECB reference XML and reuse the pure parser. Parse Decimal
quotes/date deterministically. ECB quotes units of currency per1EUR; derive the
required native-currency -> EUR rate using exact Decimal and the existing bounded
rounding/tolerance contract. Retain original quote, direction, derivation, date,
URL/hash and locator. No search-result/LLM rate, float arithmetic or stale-date
substitution. Existing strict >3/>7-calendar-day FX and >24/>72-hour source
thresholds stay unchanged.

Keep actual provider prices in their published native currency; do not relabel USD
as EUR. Any permitted normalization must retain the exact FX evidence and clearly
say it is derived. Source publication date and local row validity are different.
Use only FX pairs actually needed by the selected supported proposal; a missing
required currency/quote blocks. If conversion was used, show it in the SAME report;
N/A is only truthful when none was required. No independent FX homework or import.
Do not overwrite/close/create live pricing or FX rows; supersession is183.

## C5 — Canonical bundle, actual capture identity and honest replay

The existing typed JSON remains the sole semantic proposal bundle. Extend it
narrowly for measured acquisition outcomes/inventory and explicit exclusions;
version changes deliberately. ResearchIdentity must remain honest NOT_RUN/N/A for
Codex in this objective. A new collection must record the actual tool/code revision,
source digests and current retrieval outcome, not a bundle author's SUCCESS label.

Separate what this invocation ACTUALLY fetched from supplied/replayed declarations,
just as baseline SQL capture already does. Offline review of a supplied bundle
must not claim live retrieval occurred in that invocation. Sealed verification
replays the ORIGINAL captured bytes/metadata and performs no fetching. Never let
a caller-supplied successful-collection flag override a failed transport/parse or
promote an unbound value to VERIFIED. Source conflict, missing selected mandatory
facts, unsupported billing, stale data and invalid import plans remain deterministic
gates. Existing-row updates stay BLOCKED until183, even if research discovers them.

All new identity/evidence/proposals/validation/report bytes must be covered by the
existing seal. Preserve capture-once/no-clobber/key isolation; no manifest escape,
verify-time network request or re-sign-on-verify. Document legacy version/replay
behavior; never rewrite or re-seal archived runs. Update report stage wording to
reflect working live collection and absent Codex/apply, preserving the readable
180.6 layout and one-artifact experience. No presentation redesign here.

## Acceptance and required verification

- AP1: actual collect CLI -> canonical bundle -> existing validators -> sealed
  REVIEW.html -> verify, for bootstrap and supplied-baseline refresh; one-model
  selection works; no API-server dependency or application metadata mutation.
- AP2: current public OpenRouter/OpenAI/ECB shapes supported conservatively;
  flat supported positives work, router -1/tiered/unsupported/ambiguous negatives
  are explicitly accounted; no ten-row preparation or silent row loss.
- AP3: transport bounds/redirect/host/private-address/compression/timeout/429 and
  malformed-source controls tested; actual captured metadata distinct from replay.
- AP4: exact price units/currency/FX direction/date/freshness and locators tested;
  wrong model/alias/tier/field/source conflicts cannot produce a ready selected row.
- AP5: report states/counts/reasons accurate, readable, all evidence inline,
  live-source status honest, Codex NOT_RUN, no apply claim, seal/tamper replay green.
- AP6: mocked-source E2E and bounded real unauthenticated public-source smoke on
  the literal final implementation; docs/lint/links/diff and ordinary CI green;
  exact-path/no-runtime-accounting/dependency/deployment diff proof.

Focused unit tests use HTTPX mock transports/synthetic source fixtures; exercise
actual production collector/normalizer functions, not prewritten ValidationReport
objects. Include supported siblings alongside unsupported price rows, explicitly
required missing models, before/after baseline changes, true provider outage,
partial bodies, conflicting authoritative pages, malformed JSON/XML, markup/
command injection, unknown units and legitimate zero. Retain all prior180negative
protections. Do not weaken selected-row failure assertions to make a live source
pass; document any narrower per-row classification precisely with new negatives.

A bounded live smoke is AUTHORIZED for unauthenticated GETs to the official
OpenRouter models/docs, OpenAI pricing/model docs, and ECB reference endpoints
and approved same-publisher links needed for selected-model metadata. No inference,
authenticated discovery, email, Codex call or production access. Record exact
URLs/times/status/bytes/digests, reconciled counts, one supported model per selected
provider where published facts permit, actual report/verify result, and filtered
scope. A website outage or unsupported model is a finding, never fabricated PASS.
Use public-format/synthetic fixtures in Git; no whole copied documentation corpus.

Run focused catalog/source/import regression tests and a targeted browser check
for actual collection labels (temp outputs only). Baseline SQL and import executors
are unchanged; no new DB/Redis/Docker/local full/HPC matrix needed. Normal broad CI
remains required. Actual subprocess exit codes, no skipped/pending-as-pass claims.

## Setup, publication and full-goal continuity

Use existing .venv/httpx/stdlib and owned temporary directories. No dependency or
system changes, .env/protected credential reads, shared5432/config/log access,
privileged postgres identity, global cleanup, or unrelated worktree changes.
Source scratch outside repo, safe errors, no secrets in artifacts. Preserve
.local-provider-catalog, rootAGENTS.md and permanentmessage.txt.

Commit this strategic order and active pointer unchanged. Create exactly one PR,
push all implementation before drafting the immutable report. Report exact start/
implementation SHA, changed paths, actual command/positive/negative/source smoke/
validator/report/seal outcomes, semantic changes to source classification,
collection-vs-replay proof, resource cleanup, CI and limitations. State clearly
that182Codex,183auditedapply and184finalwrappers/E2E remain REQUIRED; do not claim
full goal completion or erase them to fit this objective.

Publish exactly one final report-only SELF commit, first parent equal to the
literal implementation head, and verify it is the remote PR head before sending
exact two-byteOK on the verified response FIFO. Coding agent never merges or
enables auto-merge. Report only already-existing implementation CI; strategy checks
SELF-head CI after publication. No tag/release. Await next strategic order.

After report/response, explicitly target the verified coding pane%3 when starting
the next control waiter. Never start another control reader during this round.
