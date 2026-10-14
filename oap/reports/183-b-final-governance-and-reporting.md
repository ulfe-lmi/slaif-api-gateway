# OAP Execution Report — Objective 183-b: Final Governance and Reporting

Report status: IMMUTABLE (finalized at the exact final implementation head
`d0cd4e2319a4f95660d84431aeaf71101d19fa66`; published atomically as the
immutable report; the report-only SELF commit with message
`Report publication commit: SELF` is its publication commit, first parent
= this implementation head, only this report path differs).

This is the final report of Objective 183 on PR #321. It supersedes none of
the immutable 183-a report bytes (they remain authoritative for 183-a), but
it explicitly corrects two inaccurate statements in that report's sections
9/10 (section 3 below) and closes the remaining evidence gap of the
activated 183-b order (captured official docs-page layout through the
actual CLI pipeline).

## 1. PR identity and merge state

- PR: #321 `feat: research unresolved catalog facts with isolated Codex`
  (the unique 183 PR; 183-b mode `AMEND_EXISTING_PR`).
- Branch: `oap/183-isolated-source-research`.
- Base: `main` at `50acd24459b9feb4277044f724a06f04720f2491` (unchanged at
  publication time).
- Commit chain on the branch:
  - `635a063` — 183-a activation.
  - `00992b4` — 183-a implementation.
  - `e59e11b` — 183-a docs correction.
  - `4b410505cc6dcb990bb3443c887357d6415849b5` — 183-a implementation head.
  - `e61e39fe09c28a836f3fb37a4cf27a285d87abcd` — 183-a report-only SELF.
  - `61e201d35ceeb4d6c9968c2a0fb80e1e723a2e93` — 183-b activation:
    strategic-authored order `oap/orders/183-b-final-governance-and-reporting.md`
    (SHA256 `01507aba…2f4f`, bytes unchanged since) + exact `oap/active`
    = `183-b` (5 bytes, no LF). First parent = `e61e39f`.
  - `d0cd4e2319a4f95660d84431aeaf71101d19fa66` — **183-b implementation
    head** (this report's final implementation head): captured docs-page
    fixture + unit/integration/browser evidence. First parent = `61e201d`.
- Merge performed: NO. Auto-merge: not requested/enabled. Coding agent
  never merges. The unrelated Dependabot PR #319 is untouched.
- Protected ruleset, branch protection and release/tag state unchanged.

## 2. B1 — transcript preserved; active governance failure closed

- The 183-a order (`f60c26347e801eaefe5a5776d506a31cee54262d9b95e3c36fda07b73b935fb0`),
  the 183-a report (`4dcce244c75ac3d69e342322aefbd17df93a99cc2f44cdae9f20285d9e8a11d9`),
  the governance tests, the OAP protocols and `message.txt` were NOT edited
  by 183-b (verified byte-identical at B start and at B end).
- Mechanism: `test_initial_round_declares_new_pr_and_one_objective_one_pr`
  enforces the literal `PR mode:` header only while the active order is an
  initial (`-a`) round. With `oap/active` = `183-b`, the check evaluates the
  corrected 183-b order header and passes; the immutable 183-a header is
  preserved, not rewritten.
- Focused local run (this session, worktree at the implementation head
  bytes): `tests/unit/test_catalog_refresh_research.py`
  `39/39 passed` + `tests/unit/test_oap_governance.py` `8/8 passed`
  (47 passed total, 0 failed).
- Authoritative CI confirmation at the final implementation head
  `d0cd4e2`: `Unit, lint, and migration head` **pass** —
  `4646 passed, 1 skipped, 0 failed` in 117.37s (run `38494382343`,
  job `115626703064`). The 183-a head had failed this check
  `4641 passed / 1 failed / 1 skipped` solely on the immutable-header
  formatting; that failure is now closed by the active continuation, with
  the four new 183-b unit tests counted in the 4646.
- One objective / one PR preserved: 183-b amends PR #321; no second PR,
  branch replacement, merge, auto-merge or history rewrite.

## 3. B2 — corrected disclosure of the earlier host-probe deviation
   (supersedes 183-a report §9/§10 statements)

The immutable 183-a report contained statements that are contradicted by
the earlier coding-session disclosure recorded in the strategic state
(`STATE.md`, "Credential deviation and truthful reporting"). This section
explicitly supersedes them:

**Superseded 183-a §9 statement** — "Every model interaction in this
objective is the qualification MOCK transport … **Zero live model
calls.**" — **not accurate as written.** The corrected account:

- An earlier HOST-side execution probe of the Codex CLI, run before the
  strategic boundary correction, inherited the host
  `HOME`/`CODEX_HOME` environment (including the issuer authentication
  material). Per the earlier coding-session disclosure recorded in the
  strategic state, that probe **made two authenticated requests to the
  real issuer endpoint; both were rejected HTTP 400 for unsupported
  model; no successful inference result was reported.** This activity was
  outside the original order authority.
- This account is attributed as **reported** (earlier coding-session
  disclosure, recorded in the strategic `STATE.md`). No safe primary
  record independently verifying the two requests and their rejection
  status survives; where safe primary records do not establish a fact,
  this report does not upgrade it to independently verified evidence.
- Rejected requests are not converted into safety claims: this report
  does **not** claim "no network contact", "no credential use", or "no
  processing / no charge" for those two requests.
- The absence of a protected auth-file mutation or of a host session
  directory (the 183-a §9/§10 observations) **cannot prove** absence of
  authentication or request execution. Pattern scans of diffs and scratch
  artifacts (183-a §9) are pattern scans: not exact protected-value
  comparisons, and not proof that every scratch artifact lacked
  credential-bearing data.

**Superseded 183-a §10 statement** — "The host-side calls were
help/version/availability-level probes; no live model invocation was
made …" and "No credential-bearing file or log was created by the coding
agent" — **not accurate as written**, for the reasons above. The rest of
183-a §10 (unresolved single `Authorization` field in the owned mock
relay log; all later executions isolated with an explicitly configured
synthetic task config) remains accurate.

**The unclassified `Authorization` field — uncertainty retained.**
Safe root metadata survives in
`review-artifacts/183-preflight/host-probe-safe-inventory.json`
(`mock-log.txt` SHA256 `51f3b94ea074928e97df864da8ab8b466636cb19886ac0100a9b513cfbff6cbb`,
`authorization_field_present: true`, `jwt_like_token_present: false`) and
`mock-auth-field-classification.json` (`authorization_fields_found: 1`,
`all_auth_fields_use_explicit_synthetic_prefix: false`). The trace file
itself was removed with the `/tmp/slaif183a` scratch after the 183-a
publication, so **no safe primary comparison of that field against the
configured synthetic token survives**. The field's origin (synthetic vs
real) therefore remains **unclassified**, and this report retains that
uncertainty explicitly instead of inventing a clean result.

**What 183-b itself performed:** no fresh host model execution, no real
issuer request, no protected auth-file read, no credential rotation, and
no credential value printed. All 183-b actual executions used the
enforced isolated worker with the qualification mock model transport.
Product artifacts and qualified synthetic executions are described in
sections 4–5 separately from the earlier unauthorized diagnostic history
above.

## 4. B3 — captured official docs-page layout through the actual CLI pipeline

### 4.1 The fixture and its provenance

- `tests/fixtures/catalog_refresh/research-openai-page-variant.md`
  (SHA256 `1167433c22fc055af0dbd2480afeff869107cf53969dbb9b7fe76478070b3f0c`,
  3271 bytes): a **documented exact two-line synthetic derivative** of a
  **prior official capture** of the OpenAI gpt-3.5-turbo documentation
  page (original SHA256
  `b4c0d8628e5a72d9ac94fd4a6fc26ce236ce3bda51a48d3bff042a9b8301f4e7`,
  `https://developers.openai.com/api/docs/models/gpt-3.5-turbo.md`).
- Provenance record (safe primary):
  `review-artifacts/183-preflight/source-page-provenance-verified.json`
  — original capture from the **181-h** catalog-refresh collect run
  `collect-20261012-211145-052117ddc02d`, retrieved
  `2026-10-12T21:11:46.135021Z`; the strategic side then applied the
  exact two-line transformation with network denied.
- The transformation re-lays only the two limit lines from the
  deterministic list-item layout (`- 16,385 context window`,
  `- 4,096 max output`) into the prose layout
  (`Context window (tokens): 16,385`,
  `Maximum output (tokens): 4,096`). Every price, modality, endpoint and
  feature fact is preserved byte-for-byte otherwise.
- `tests/fixtures/catalog_refresh/research-openai-page-variant-provenance.json`
  records the original capture run/timestamp, both digests, the
  transformation, `network: "denied"`, and the
  `preflight_parser_baseline` `50acd24…` — explicitly annotated as the
  main at 183-a preflight/parser verification time, **not** the base of
  the original capture (which predates it).
- **Scope, stated plainly:** this is a layout-derivative qualification on
  **captured bytes with a mock transport**. It is **not** a live/current
  official-format qualification and **not** a model-accuracy
  qualification. No live source/model call and no fabricated retrieval
  history: the collect under test serves the fixture bytes through the
  in-process fixture fetcher.

### 4.2 Unit evidence (new focused tests)

`tests/unit/test_catalog_refresh_research.py` — 4 new tests (file total
39, all passing):

1. `test_docs_page_captured_variant_plans_single_task` — deterministic
   parse of the pinned fixture succeeds (prices/modalities/endpoints
   resolved) but leaves **both** limits unresolved in the prose layout;
   the parent page scan resolves both uniquely, so the page is exactly
   one `TASK_DOCS_PAGE` task
   (`openai|gpt-3.5-turbo|docs_page`,
   `requested_fields = (model:context_length, model:max_output_tokens)`,
   `remaining = ()`).
2. `test_full_docs_page_pipeline_mock_research_seals_limit_facts` —
   first-install OpenAI collect + mock research: `SUCCEEDED` (mock
   declaration), exactly **2** sealed grounded facts, model
   `context_length = 16385`, `max_output_tokens = 4096`, semantic
   provenance for the researched limits; real `validate_bundle`
   re-grounding: `READY_WITH_WARNINGS` with warnings exactly
   `{new_model_exposure, research_semantic_method}`, review
   `facts_sealed: 2 / facts_regrounded: 2`.
3. `test_docs_page_without_readable_limits_is_never_researched` — page
   with the limit lines removed: `NOT_RUN`, 0 facts, model absent from
   the bundle, inventory `(incomplete, missing_limits)`; research is
   never invoked for unlocatable facts.
4. `test_docs_page_fabricated_quote_is_rejected_not_grounded` — a
   fabricated quote (`999,999`) from the "model" is refused by the
   parent grounding: `SUCCEEDED` exit 0 at the transport but
   `facts_rejected == 2`, zero grounded facts,
   `(incomplete, missing_limits)` inventory.

Deterministic precedence, full-context conflict checks, official
classification and the exact inventory are preserved unchanged (existing
tests green).

### 4.3 Actual-CLI integration evidence (new focused test)

`tests/integration/test_catalog_refresh_research_codex.py` — new
`test_rp1_real_cli_docs_page_pipeline_bundle_seal_verify_plan`:

- **REAL** installed Codex CLI 0.162.1
  (SHA256 `628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1`)
  inside the **real** enforced outer boundary (owned Docker 29.1.3,
  pinned Python runtime image
  `python@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f`,
  `--pull=never`, isolated network), with the **qualification mock**
  model transport: the canned tool turn makes the real CLI perform the
  useful local read of the mounted evidence
  (`cat /workspace/inputs/evidence`), then the canned structured result
  carrying the exact captured-page quotes.
- Driven through the ACTUAL product pipeline:
  `collect_bundle(providers=("openai",), first_install, fixture fetch)`
  → research phase (real CLI) → `validate/plan` → HTML render →
  `_finalize_review_pipeline` staged **sealed** publish →
  `sealing.verify_run` valid; exit `READY_WITH_WARNINGS` (10); proposal
  artifacts and `REVIEW.html` carry the researched model.
- No physical network, no live model, no real credentials; source bytes
  are the pinned captured fixture.
- Local execution at the final implementation head: **passed in 12.3s**
  (fresh actual-CLI sealed run `collect-20261014-011229-f32287968aeb`;
  that run's `REVIEW.html` SHA256
  `fefddf546ce781613a732815033c53b55102009ea78736f3f7cb7ad069e9f84f`).

### 4.4 Browser evidence (bounded new case, assertions intact)

`tests/browser/test_catalog_refresh_report.py` — one bounded new case
`research-docs-page` (13 cases total; all existing viewport, font,
request and trust assertions unchanged):

- Local JS-disabled Chromium run of the full suite at the implementation
  head worktree: **passed** (all 13 cases), including the new case
  (visible: `research 2/2 re-grounded`,
  `Research evidence (semantic fallback)`, `Mock model (declaration)`,
  `live-collection scope`; full digests visible when expanded).
- Final-head measurement of the **exact sealed artifact** from the
  actual-CLI run above (JS-disabled Chromium, file:// only, zero
  external requests in every load):
  - 1440x900 first screen: worst bottom **863.3 px** (36.7 px margin
    under the 900 px gate) across all first-screen selectors
    (`.state` 127.5, `#scope-baseline`/`#checks` 443.4, `#per-provider`
    649.1, `#fx-line` 716.6, `#plan-line` 741.6, `#findings-line`
    815.2, `#changes > h2` 837.3, first changed content 863.3).
  - Document width exact at 1440 / 1280 / 375, **collapsed AND fully
    expanded** (14 details opened), no page-wide overflow.
  - Font floors met (body 15, dl.kv 15, table 14, .state 18, h1 24,
    h2 17, .chip 14).
  - `gpt-3.5-turbo`, `16,385` and `4,096` visible in the expanded
    report; full 64-hex digests visible.
  - Evidence: `review-artifacts/183-b-review/finalhead-docpage-browser-results.json`
    + `finalhead-docpage-1440.png` (strategic root).

### 4.5 No product-code changes

No demonstrated integration defect appeared: the five allowed product
paths (`research.py`, `research_grounding.py`, `source_evidence.py`,
`collection.py`, `validation.py`) are **untouched** by 183-b. All B3
evidence rides on the 183-a implementation.

## 5. B4 — final checks, evidence and docs

### 5.1 CI at the final implementation head (authoritative)

Head `d0cd4e2319a4f95660d84431aeaf71101d19fa66`, PR #321 — **all ten
required check-runs SUCCESS**:

| Check | Result |
|---|---|
| Unit, lint, and migration head | pass (4646 passed, 1 skipped, 0 failed) |
| PostgreSQL integration tests | pass |
| OpenAI-compatible E2E tests | pass |
| Playwright browser smoke | pass |
| Docker Compose smoke | pass |
| Documentation hygiene | pass |
| CodeQL (aggregate) | pass |
| Analyze Python (code scanning) | pass |
| Analyze (python) | pass |
| Analyze (javascript-typescript) | pass |

Primary run `38494382343`; CodeQL runs `38494378478` / `38494382247`.
The known Code Quality inline comments (unused globals / lambda /
empty-close-catch style annotations) remain cosmetic annotations, not
proved security failures; no supporting infrastructure was expanded to
clear them.

### 5.2 Inherited evidence (named, not relabelled)

The following 183-a evidence was produced at the 183-a implementation
head `4b410505cc6dcb990bb3443c887357d6415849b5` (run `38494382343`
except where noted). 183-b changes **no product code, schema, migration,
accounting, transport or workflow file**, so the measured runtime paths
are unchanged; this evidence is **inherited**, not re-executed on B and
not relabelled as such:

- The ten check-runs at `4b41050` (nine SUCCESS; unit FAIL
  4641/1/1 solely the immutable governance-header literal) — closed by
  B as recorded in 5.1.
- RP1 useful-fallback proof with the real CLI on the synthetic
  OpenRouter `syn-1` row (readable `128K` limit) through
  bundle → validate/plan → render → staged sealed publish → verify.
- RP2 malicious real-CLI local-tool denials (host repo read/write,
  environment secrets, host-loopback service reach, read-only input
  tamper, Docker socket, instruction inheritance) with the phase still
  completing honestly; the call_id-matched `function_call_output`
  public-read control.
- Finite task timeout (`child_timeout`, exit 137, no partial data),
  malformed-parent-parser refusal (measured exit 0 with schema-invalid
  bytes refused by the parent strict parser), and exact owned-resource
  cleanup by invocation-created IDs/labels.
- Measured-vs-declared research identity, FX binding, and the
  first-screen repairs of 183-a (blocked-state banner, collection row).

### 5.3 Focused verification in this session (exact)

- `ruff check` on all four changed test paths: clean.
- `pytest tests/unit/test_catalog_refresh_research.py
  tests/unit/test_oap_governance.py` → 47 passed (39 + 8).
- `pytest tests/integration/…::test_rp1_real_cli_docs_page_pipeline_bundle_seal_verify_plan`
  → passed 12.3s (twice: once pre-commit, once at the final head with the
  retained sealed run cited in 4.3).
- `pytest tests/browser/test_catalog_refresh_report.py` (13 cases,
  JS-disabled Chromium) → passed.
- Final-head sealed-artifact browser probe (exact gates of the suite) →
  passed (4.4).
- No full local matrix; no repeated green suites solely for counts
  (collect-only used for counts); no fresh PostgreSQL/provider matrix —
  DB, inference and transport are unchanged by 183-b.
- Docs: `docs/catalog-refresh.md` and `admin/catalog-refresh/README.md`
  reviewed; the research-fallback/qualification wording is already
  accurate for the implemented behavior (183-b adds test evidence only),
  so **no doc changes were needed or made**.

## 6. Measured / mock / inherited scopes

| Scope | Classification |
|---|---|
| 183-b unit docs-page tests (4) | measured, mock execution stand-in, fixture source bytes |
| 183-b actual-CLI docs-page pipeline (integration) | measured real CLI + real outer boundary; MOCK model transport; captured fixture source bytes |
| 183-b browser suite + final-head artifact probe | measured rendering/geometry, JS-disabled, zero external requests |
| 183-b CI ten check-runs at `d0cd4e2` | measured (GitHub) |
| RP1/RP2 actual-CLI evidence, timeout/malformed/cleanup proofs | measured at `4b41050` (183-a); INHERITED by B (runtime paths unchanged) |
| Docs-page fixture bytes | prior official capture (181-h run) + strategic synthetic two-line transformation, network denied — NOT a live-format qualification |
| Earlier host-probe history (section 3) | reported deviation, outside order authority; not part of any qualification |

## 7. Limitations and residuals (no overclaim)

1. The 183-b docs-page evidence is a **captured-layout** qualification:
   it proves the deterministic parser's prose-layout gap is closed by the
   useful grounded fallback through the actual pipeline. It makes **no**
   live/current official-format claim and **no** semantic-accuracy claim
   for the mock transport.
2. The earlier host-probe deviation (section 3) remains partially
   unresolved by nature of the retained records: two reported
   authenticated requests (rejected 400, reported) and one unclassified
   `Authorization` field in a destroyed trace. No further safe
   verification is possible without reading protected auth material,
   which no order authorizes.
3. Installed-package (wheel) template/schema path resolution remains a
   184 item; a missing template/schema refuses UNAVAILABLE (identity is
   never invented).
4. Objective 184 (one-command wrapper + installed refresh/review/atomic-
   apply qualification) remains REQUIRED; nothing here claims the full
   thirty-requirement administrator workflow is complete.
5. Worker-only sandbox override (explicitly permitted by the 183 order
   after full outer-boundary validation) remains the confinement
   mechanism; no host `--yolo`/exec or privilege relaxation was used.
6. The 183-a report stays immutable with its original (now superseded
   where noted) statements; this B report is the corrected record.

## 8. Files changed by 183-b (implementation head)

1. `tests/fixtures/catalog_refresh/research-openai-page-variant.md` (new)
2. `tests/fixtures/catalog_refresh/research-openai-page-variant-provenance.json` (new)
3. `tests/unit/test_catalog_refresh_research.py` (4 focused tests + helpers)
4. `tests/integration/test_catalog_refresh_research_codex.py` (1 actual-CLI pipeline test)
5. `tests/browser/test_catalog_refresh_report.py` (1 bounded new case)
6. `oap/orders/183-b-final-governance-and-reporting.md` + `oap/active` (activation commit, strategic bytes unchanged)
7. `oap/reports/183-b-final-governance-and-reporting.md` (this report; SELF-only)

All within the order's exact allowed paths. No other files changed.

## 9. Identity values

- Codex CLI 0.162.1 binary SHA256
  `628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1`.
- Researcher runtime image
  `python@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f`
  (`--pull=never`); Docker 29.1.3 via `unix:///var/run/docker.sock`.
- Local verification venv `/tmp/slaif-181c-strategic-venv` (Python
  3.12.15); browser runtime scoped `LD_LIBRARY_PATH`
  `/tmp/slaif-browser-runtime-8h8e0e6z/extract/usr/lib/x86_64-linux-gnu`
  (owned temp extraction, no system install).
- Final implementation head `d0cd4e2319a4f95660d84431aeaf71101d19fa66`;
  183-b order SHA256 `01507aba…2f4f`; 183-a order
  `f60c26347e801eaefe5a5776d506a31cee54262d9b95e3c36fda07b73b935fb0`;
  183-a report `4dcce244c75ac3d69e342322aefbd17df93a99cc2f44cdae9f20285d9e8a11d9`.

## 10. Final statement

183-b closes Objective 183's governance failure (B1), corrects the
contradicted 183-a credential/probe statements without reading secrets
(B2), and closes the source-derived useful-fallback evidence gap with a
captured official docs-page layout driven through the actual CLI
pipeline, the real product seal/verify/plan path, and the unchanged
browser gate set (B3), with all ten final-head CI checks SUCCESS (B4).
The coding agent performed no merge; strategic review/merge authority
remains with the strategic model. Objective 184 remains required.
