# OAP Work Order — 180-d

PR mode: AMEND_EXISTING_PR

## Objective and reason

Close the independently reproduced source-evidence bypasses remaining after
180-c. Preserve the useful parser integration and its positive paths. Make
targeted corrections; do not rewrite the whole subsystem or reimplement the
existing provider-catalog parsers.

The human still requires the complete administrator workflow: refresh -> one
trustworthy REVIEW.html -> explicit audited apply. This round corrects the
offline evidence foundation on the same PR. It does not complete Objective180,
authorize imports, or advance to live research/supersession/end-to-end work.

Read this exact order, current applicable governance/contracts, and relevant
code/tests. The prior report conclusions requiring correction are reproduced
below; do not load unrelated historical reports or full architecture/catalogs
without a concrete unresolved question. Use targeted reads and focused tests.

## Verified state and immutable report reconciliation

Verified 2026-09-22 after sole helper51394 completed with exact
RESPONSE_OK_EXACT and exit0:

- Repository ulfe-lmi/slaif-api-gateway; remote main
  b1e6ef0a49d7e5ab6376f6344290f58ff844e671.
- Unique open PR317, branch oap/180-catalog-refresh-bundle-review, base main.
- Current PR/report head f728c7468ed352d3ca3ad1945bcd95a968552782.
- GitHub confirms report-only publication, first parent
  7e470132447ea9475eee37fd9da447171eade42c, matching the report's implementation SHA.
- Implementation7e47013 changed21 allowed paths, parent activation
  0636f62f3475ae06b0e350964928cec5b20ad731. Worktree clean at review.
- All10 checks passed at implementation7e47013. Report-head checks were still
  running at reconciliation; query current state. Pending is not passed.
- Strategy independently ran all167 focused unit cases successfully, with
  source/test/fixture SHA256 stable across the run. Green tests did not cover
  the failures below. Nine PG and60 related tests are reported by the agent.
- Active before this order180-c. Main ruleset prevents deletion/non-fast-forward;
  it does not replace strategic acceptance. Only release remains v0.1.0-rc.1.

The 180-c report correctly carries earlier baseline/filesystem blockers, but
its C1-C4 "met" claims overstate current behavior. In particular, actual HTML
does not contain the claimed observed model prices/units/locators; wrong source
and upstream identities are not always blocked; embedded snapshot JSON still
accepts duplicate keys; semantic labels can bypass absent evidence. Do not
rewrite any old report/order. Correct these claims in the new report.

## Exact allowed paths

- app/slaif_gateway/schemas/catalog_refresh.py
- app/slaif_gateway/services/catalog_refresh/source_evidence.py
- app/slaif_gateway/services/catalog_refresh/validation.py
- app/slaif_gateway/services/catalog_refresh/rendering.py (evidence and
  selection/reconciliation presentation only, not a wholesale layout rewrite)
- app/slaif_gateway/services/catalog_refresh/bundle.py (only necessary canonical
  source/selection contract integration)
- docs/catalog-refresh.md
- docs/cli-reference.md (only changed source/selection input semantics)
- admin/catalog-refresh/README.md (only changed source/selection input semantics)
- tests/unit/test_catalog_refresh_source_evidence.py
- tests/unit/test_catalog_refresh_bundle.py
- tests/unit/test_catalog_refresh_policy.py
- tests/unit/test_catalog_refresh_report.py
- tests/unit/test_catalog_refresh_seal.py (evidence fixture/serialization checks)
- tests/unit/test_cli_catalog_refresh.py
- tests/integration/test_catalog_refresh_baseline.py (source fixture adaptation only)
- tests/fixtures/catalog_refresh/ (synthetic evidence and affected screenshots)
- oap/orders/180-d-close-source-evidence-bypasses.md (unchanged strategic bytes)
- oap/active (unchanged strategic bytes180-d)
- oap/reports/180-d-close-source-evidence-bypasses.md (new immutable report)

No other paths. No baseline exporter redesign, filesystem implementation,
runtime API/provider/accounting, existing import executor, DB migration/schema,
dependency, deployment, workflow or historical-record changes in this round.
No live retrieval/Codex invocation/import/apply. Coding agent never merges or
enables auto-merge. Continue the same branch/PR from f728c74.

## D1 — Bind every field to its actual upstream and claimed sources

Exact committed-code reproducer: load current bundle-first-install.json;
change ONLY routes[0].upstream_model to synthetic/unobserved-upstream; leave
all model/pricing facts and snapshots untouched. Full validate_bundle returns
READY with zero issues and emits a pricing row for the unobserved upstream at
the original model's EUR0.25 input/EUR1 output prices.

Another reproducer: change ONLY pricing[0].provenance.sources to the existing
ECB source key in that bundle, leaving model/route references unchanged. Result
is again READY. The union of fact_sources and global observation search silently
supplies a different source than the pricing fact claims.

- Provider facts must bind to effective provider + actual upstream model +
  applicable endpoint/pricing context. A public alias is local routing policy;
  it is not an alternative provider model whose price can be borrowed.
- Keep the valid alias case: public B -> observed upstream A may use A's prices
  when the evidence explicitly supports A. Public A -> unobserved/different B
  may not use A's prices. Test collisions where both names exist in the catalog.
- Validate EACH financial/capability/limit field against its own declared
  supporting references and locators. Referenced-but-wrong field/model/provider
  evidence blocks; do not silently repair it using unrelated sources elsewhere
  in the bundle. Existing reference-existence validation alone is insufficient.
- Detect applicable authoritative conflicts even when a proposal omits one
  conflicting source from its field references. Do not allow selective citation
  to hide conflicting supplied observations for the same required fact/context.
- Prove positive OpenRouter and OpenAI paths through the complete validator/CLI.
  Resolve the current openai_models_docs parser-registry vs SOURCE_KINDS mismatch
  coherently. Do not use an operator-input mirror to stand in for a functioning
  OpenAI source path or infer endpoint support from a related model.

## D2 — A semantic label is not evidence; FX must be authoritative

Exact reproducer1: in the valid first-install fixture replace OpenRouter
snapshot bytes by {}, update their digest, and set that SourceRecord.extraction
to semantic. Full result is READY_WITH_WARNINGS with executable rows, whereas
the same bytes labelled deterministic correctly block.

Exact reproducer2: remove ECB source, retain the numeric FX fact, and point its
provenance to openrouter|EUR-USD|docs_page with extraction=semantic and evidence
bytes "fx notes with no numeric rate" plus their correct digest. Full result is
READY_WITH_WARNINGS, fx_backed=[], executable route/pricing rows. The guessed
FX rate is used to justify USD-observed prices as EUR proposals.

- Empty/unrelated/missing required-value evidence must BLOCK regardless of the
  extraction label, optional/required caller flag, or presence of another
  semantic source. A model-wide semantic boolean cannot waive per-field proof.
- FX used for either import or source-price currency normalization must first
  bind to a parsed authoritative quote and publication date. No semantic/manual
  escape hatch for guessed FX. This is the human's explicit deterministic-FX
  requirement; ordinary manual metadata CLI operations do not authorize a
  bypass in this refresh workflow.
- Compute currency comparisons only from validated FX bindings, not from a
  candidate rate merely labelled verified before its later check. Recheck both
  direct and reciprocal direction, date, currency, finite positive rate and
  complete supporting source. Missing dates/quotes cannot be warning-only.
- Genuine semantic extraction may require REVIEW in the later research workflow,
  but must retain actual official supporting text/locator, value/unit/currency
  and identity. If this offline contract cannot represent such evidence, BLOCK
  that candidate honestly until the bounded researcher provides it. Do not
  fabricate semantic observations by copying proposal values or treating a
  string label as proof. Keep valid structured-source positive paths.

## D3 — Strict snapshot parsing, canonical conflict checks and real locators

Exact committed reproducer: insert a second prompt key in the embedded
OpenRouter pricing JSON, with conflicting value0.00000999 followed by the
original prompt value; regenerate digest. Full result remains READY, zero
issues, executable rows. Outer bundle JSON duplicate-key checks do not examine
base64-decoded snapshot JSON.

Exact second reproducer: insert null before the valid model in raw data[].
Full result stays READY; emitted locator data[0].pricing.prompt now points to
null because the reused helper filters rows before enumeration.

- Reject duplicate JSON object keys and non-finite constants in EACH decoded
  snapshot, not merely the outer bundle. Safely reject malformed/deep/oversized
  inputs with code-only errors; no traceback or raw-secret echo.
- Validate raw structure and preserve original row indices before invoking
  reused pure helpers. Invalid rows/IDs must be rejected or represented with
  explicit disposition/reason/count; never disappear through filtering. OpenAI
  set/dict helpers must not erase duplicates before checking them either.
- Conflicting rows/observations within ONE snapshot must block. Do not skip
  conflicts because only one digest is involved. Identical duplicate rows may
  only be deduplicated under an explicit safe policy with reconciled counts and
  a truthful finding; do not claim BLOCKED if actual policy merely warns.
- Compare exact normalized value AND unit/currency/context. Equal decimal
  spellings agree; recognized unit conversion is explicit; missing/unknown or
  contradictory source units cannot be assigned USD/per-million by assertion.
- Distinct content hashes from repeated retrievals/aliases of the same official
  URL are not two independent corroborating sources. Deduplicate provenance
  identity appropriately without suppressing conflicting observations.
- Bound raw decimal digits/exponents before calling existing formatting/math
  helpers; hostile exponents must not trigger huge allocation or uncaught
  Decimal errors. Preserve ordinary per-token precision needed for correct
  per-million conversion. XML remains offline and entity/network safe.

## D4 — Explicit selection and complete per-ID reconciliation

Committed probe: add another fully populated eligible text model to the raw
OpenRouter snapshot and regenerate its digest, leaving model_include empty and
proposals unchanged. Result READY/zero issues; inventory records2 evidence
models,1 selected,1 unproposed. The counter notices the omission but gives no
per-ID disposition/reason while the UI says all models of selected providers.

Do not force every provider model into an import. Preserve explicit subsets
and conservative profiles. Make the selection contract unambiguous: an explicit
subset/profile exclusion differs from an unexplained missing eligible proposal.
Every parsed raw identifier must reconcile into selected/proposed, excluded
with an actual reason, incomplete/blocked, duplicate/malformed, or retained
historical local state. Unexplained omissions under an all-eligible selection
block. Explicitly excluded models need no low-value warning per row, but their
names/reasons and aggregate counts must be available in the report.

Do not define desired scope solely by whichever proposal rows happen to exist.
Never auto-create routes or delete disappeared local rows to make counters pass.
Retain all original scope and no-op/executable-plan guarantees.

## D5 — Put the actual observations inside the one report

Current source_evidence contains only scope/note/backed_facts/fx_backed/inventory.
A pricing backed_fact contains proposed value, source IDs and an independence
count; it omits the observed value, unit/currency and locator. Actual generated
HTML does not contain data[0].pricing.prompt or the observed USD/token value for
the EUR0.25 proposal. The 180-c C4 claim that these are in the HTML is false.

Serialize the actual derived observations and their binding/normalization into
the canonical validation result and render them in expandable evidence details:
observed value/unit/currency, provider/upstream/endpoint context, exact locator,
source URL/digest/parser/time, normalized value and transformation, proposed
value, agreement/conflict status. Include supporting semantic excerpts only
where genuinely validated and permitted. Keep details escaped, bounded, offline,
deterministic and printable. No extra-file/base64 homework for the administrator.
Recompute these same fields during seal verification; no second semantic truth.

Keep the normal view compact. Full first-screen layout remediation remains a
later same-PR round; this change must not bury the primary state/counts further.

## Acceptance, verification and report duties

For each exact reproducer above add a meaningful end-to-end regression and a
nearby positive case. Tests must validate the intended contract, not codify a
bypass (the present semantic-FX and unproposed-candidate READY assertions need
correction). Include public alias/collision, wrong per-field source, semantic
empty body, no-rate FX, duplicate inner JSON keys, conflicting duplicate model,
raw-row locator, explicit subset vs missing eligible proposal, unit/currency
and decimal equivalence, and actual HTML observed-value/locator assertions.

Run focused source/bundle/policy/report/seal/CLI tests, related import/catalog
checks, changed-Python Ruff, documentation checker/links and diff --check. Use
the existing disposable PG integration selection only if its source fixtures
change. No full local suite/HPC; no live sources, provider calls, Codex research,
protected credentials, imports or production actions. Ordinary final-head CI
still applies; passing tests do not waive independently demonstrated failures.
Visually inspect actual expandable evidence in a local browser with no network.
Address relevant bot findings in the touched code without weakening checks.

Carry all earlier baseline privacy/nested-capability/financial-metadata,
filesystem/decimal/snapshot-isolation and first-screen blockers explicitly;
do not fix them outside this scope or claim Objective180 complete. No next
numeric objective until this PR is fully accepted and resolved.

Preserve unrelated worktrees, catalogs, AGENTS.md and permanent message.txt.
Clean and enumerate task-owned resources/keys; never global prune. Commit this
order/active unchanged. Push implementation before drafting the report. Report
exact starting and implementation SHA, changed paths, per-D evidence and test
results, before/after reproduction outcomes, real observation/HTML examples,
limits, cleanup and truthful CI state. Correct the inaccurate 180-c claims in
the NEW report; old reports/orders remain immutable.

Publish one immutable report with literal implementation SHA and
Report publication commit: SELF. Final report-only commit first parent equals
that SHA, changes only the report, and is verified pushed PR head. Signal exact
two-byte OK on response FIFO. Leave PR317 open; strategy owns further
continuations and merge. No tag/release authority is granted.
