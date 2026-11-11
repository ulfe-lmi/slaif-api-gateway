# 219-b immutable report — GUI completion repair (SAME PR #376)

## Identity and activation

- Objective: 219, identifier `219-b` (CONTINUE_EXISTING_PR); the SAME
  single PR #376, branch `oap/219-gui-completion-gate`; OPEN at
  publication, never merged, no auto-merge, coding agent did not merge.
- Order: `oap/orders/219-b-gui-completion-repair.md` (22,369 bytes,
  SHA-256 `5774037e581d881f4e7a0bd1c6ae0df2764d5e5d85ebf80ce082033fc8d87fc9`),
  root-authored, committed byte-unchanged with the active pointer update in
  `5192444f0902e996090ee37313d5c7b198963f45`; bytes immutable.
- Active pointer: `oap/active` = exactly the five bytes `219-b`
  (no trailing newline; SHA-256
  `fa22c476136bc8412c53abfd0b80045f3c2b602e56993d50b0f4b97218be73f5`).
- Base/remote main: `663c673494d4c0daeb4d5b1269b428ee13277448`
  (merged PR #375 / predecessor objective 218: terminal); unchanged by
  this turn.
- The ONE exact control `OK` for 219-b was already consumed and validated
  by the canonical waiter before this execution turn began. No
  `control.fifo` read, wait, or signal occurred in this turn; no response
  was sent for 219-a or 218. After this report commit is the verified
  remote head, exactly ONE exact two-byte `OK` is sent to
  `response.fifo` (root's terminal 32087 solely owns that reader) and ONE
  canonical control waiter is re-armed to tmux pane %9.
- The prior 219-a order (29,183 bytes, SHA-256
  `78cf72bed89e783fe068c002928cf08eac70ecbba12d09530c52dd4364d5d4e7`) and
  the immutable 219-a report (12,802 bytes, SHA-256
  `27d279601d15769d016970f6acba035b70cd20963c61b87c076bbdd40ef1eeba`) are
  preserved byte-unchanged, including the 219-a report's mistakes;
  corrections live in the CURRENT docs/PR and in this report.
- Protected untracked local files preserved BY HASH ONLY (never staged,
  never modified): `CODEX-SESSIONS.md`
  (`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`),
  `codex.sh` (`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`),
  `uv.lock` (`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`).

## Publication topology

Implementation head SHA: 865be40f3e55032f3b0e92b15634fa687e2d0693
Report publication commit: SELF

- Final product head: `34cbf03078a47ebee5a52faf5bd00a1188ec1216`
  (tree `ca720571bc7ddd26e5fc7bda345b3f44ddc30b7b`); byte-equality proof:
  `git diff 34cbf030 e86e6604 -- app/` is empty (the implementation head is
  docs-only on top of the final product head, identified separately as the
  order requires).
- Twelve append-only commits over base main `663c6734` (no amend, no
  force-push, no reset/clean/stash):
  - `07396b0d` — 219-a: Strategic activation (order + active,
    byte-unchanged, root-authored);
  - `45893daa` — 219-a: whole-GUI field guidance, calibration JSON
    download, visual consolidation (219-a product);
  - `00737d17` — 219-a: whole-GUI completion gate (test/fixture/doc
    corrections only);
  - `66be0959` — 219-a: publish immutable report (report-only SELF);
  - `5192444f` — 219-b: order + active pointer + GUI completion repair
    (calibration JSON export boundary, guidance/interaction completion,
    installed workflow outcomes);
  - `5aa58fe3` — 219-b: seed live-burn telemetry as canonical decimal
    text;
  - `2ee9cf06` — 219-b: CI-focused repairs (create document-mode toggle,
    batch picker help oracles, keyboard submit wait, calibration-404
    header law, export audit scope projection);
  - `b327e359` — 219-b: legacy-scenario fixture corrections and 219-b
    documentation (docs/fixture-only; product source 2ee9cf06);
  - `8179b877` — 219-b: gui-cli-parity verification record (doc-only);
  - `34cbf030` — 219-b: rendered all-field guidance completion (policy-
    selector and live-burn control descriptions, rendered/native whole-
    control sweeps, account docs correction) — the FINAL product head;
  - `e86e6604` — 219-b: gui-cli-parity record update (doc-only: rendered
    all-field correction, final installed gate at product head 34cbf030,
    intermediate receipt re-labeled);
  - `865be40f` (implementation head) — 219-b: gui-cli-parity record
    correction (doc-only: post-fix unit batch receipt is 461/461 per the
    JUnit receipt).
- This report-only SELF commit has SOLE parent the literal
  implementation head `865be40f3e55032f3b0e92b15634fa687e2d0693` and its diff
  contains ONLY this report file.
- PR #376: https://github.com/ulfe-lmi/slaif-api-gateway/pull/376 (base
  `main`, head `oap/219-gui-completion-gate`; title/body rewritten around
  the complete PRODUCT change — it is not a test-only diff).
- Root owns final-head CI, review, material/visual gates, guarded merge,
  actual-main verification, and the full original-scope audit; nothing in
  this report claims any of those complete.

## What this delivers (complete 219-b scope, finishing the original 219
scope on this PR)

- **Calibration JSON export boundary**: the trusted-calibration download
  refuses the WHOLE artifact (fixed safe 400, no echo of the refused
  value, unchanged CLI-compatible machine projection) when any nested
  canonical string is a known incoming authentication alias or recognized
  complete credential material; refuses oversize output at the finite
  1 MiB local ceiling (explicit refusal advising narrower scope, never
  truncation, no Core aggregation/accounting change); success AND refusal
  responses — including the malformed-key early 404 — are private
  no-store/no-cache and `X-Content-Type-Options: nosniff`. Same
  trusted-key/time/multiplier validation, exact Decimal/UUID/datetime
  serialization, raw units, non-rotating read-only attachment session
  context, and same-page confirmed template creation are unchanged.
- **Rendered all-field guidance completion**: root's isolated real-
  Jinja/CSS/JS audit of the ACTUAL rendered pages found 11 visible entry
  controls without a resolving description in each rendered state (create
  guided 57 controls; standard AND trusted detail 75 each): the two
  unnamed older-provider/model search inputs, the six
  `{create,detail}-policy-{providers,endpoints,models}-{available,
  selected}` dual selects, and the dynamic
  `{create,detail}-chat-streaming-live-burn-enabled` / cost-margin /
  token-margin fields. The shared `keys/_policy_selector.html` partial
  now associates every control with the EXISTING caption help via stable
  prefixed IDs (no new copy, no new component, no visual churn), and the
  dynamic live-burn controls in BOTH the create and detail templates
  reference their EXISTING hint help. Field names, values, modes, layout,
  and Core semantics are unchanged. Audit hardening in the existing
  modules: the source-structure inventory no longer skips unnamed or
  Jinja-named controls and filters hidden/readonly/submit (matching the
  rendered definition); a new rendered whole-field audit requires EVERY
  visible editable/choice control on the real rendered create page
  (guided AND document policy-source states) and on both standard and
  trusted detail pages to resolve its description to a defined non-empty
  element; the 219 browser module runs the same whole-control sweep in
  the real DOM with computed-CSS visibility (details disclosures opened)
  on create (both states) and both detail pages.
- **Remaining specified guidance/interaction items**: enhanced picker
  menu-search help on the shared record-choice macro (main + menu-search
  associations, unique help definition); explain-model via the shared
  searchable known-model picker plus manual unknown-model entry; key-
  create document-mode disclosure corrected (document group shown in
  document mode, guided bodies hidden, toggle no longer inverted);
  compatibility readiness fixed useful setup direction (invalid
  `PUBLIC_BASE_URL` included, canonical verified-HTTPS/numeric-loopback
  gates preserved, no exception echo); media-estimation per-typed-part
  help; concise plain account guidance RETAINED (the 218 account
  templates are unchanged by 219; their purpose/consequence guidance is
  revalidated, and the current guides' false "prose shortened" assertion
  is corrected); batch membership disclosure, 105+/1000-key scope law,
  and the static field-name/form-action preservation unchanged.
- **Export audit scope projection**: a key-scoped usage JSON export's
  audit row records the exact scoped record UUID as top-level
  `scope_gateway_uuid` (the already parsed/validated
  `filters.gateway_key_id`); the shared sanitizer's removal of the nested
  `filters.gateway_key_id` is intentional and unchanged (key-named fields
  are sensitive and never exempted) — no global sanitization,
  AuditRepository, schema, accounting, or permission change. The
  installed oracle asserts the stored safe UUID plus the existing
  actor/count/filter facts and documents the intentional removal; a
  focused 214 test covers the projection, unscoped absence, and the
  continued cookie-UUID alias refusal with no-write law.
- **Demonstrated CI consumer repairs (no weakening)**: the 209 batch
  form-page oracle (each actual control association + unique help
  definition, search help retained), the two 207 create consumers
  (document-mode toggle product fix, visible-editor/canonical-policy
  persistence assertions preserved), the 219 keyboard external-tool
  submit wait (waits on the actual target POST 303 and the resulting
  navigation/flash; keyboard Enter and persisted audit outcome preserved),
  and the lazy-throttling consumer re-qualification.
- **Installed workflow's missing outcomes and oracles (original 219
  scope finished on this PR)**: G01 exact canonical unrestricted state
  (None and [] deliberately distinct); G06 real partial capability leaf
  change with untouched deep siblings on the SAME route; G07 real
  provider preparation plus explicit activation (persisted values/audits,
  preparation/activation separation); G10 real upgrade/rollback, exact
  active snapshot identity, credential-free profile/config/catalog
  artifacts with valid public URL, honest G10 non-rotation probe (valid
  plain-route origin form token captured before the artifact GETs and
  accepted afterward with no intervening render — a non-rotation probe,
  NOT a Codex-route configuration parity claim); G11 grouped usage,
  live-burn report, and safe JSON export with distinct
  `prompt_tokens`/`completion_tokens` export columns (the UsageLedger
  fixture seeds both the `input/output_tokens` pair AND the distinct
  columns; no fallback/remapping, exact export oracle and Core
  semantics); G13 complete filter paging/sort/ordinal; G18 real
  pricing-disable with honest unavailable-FX wording. Representative
  legacy outcomes run to persisted/audit state in the final installed
  workflow: standard-key create, suspend/activate, rotation with one-
  time destination and REAL old-material invalidation (old bearer 200
  before on local /v1/models, 403 permission_error after; replacement
  bearer 200; no provider call), validity/hard-quota edits without usage
  reset, lazy-waiting/external-tool configuration, provider
  discovery/import with explicit insecure-HTTP confirmation and enable
  acknowledgement (default `provider/upstream` public-model naming,
  asserted as the actual prefixed public name), template issue from the
  calibration-created revision, GUI audit inspection and the existing
  safe CSV/JSON exports, login/logout (raw-client 303 bounce + re-login),
  credential-free download then usable still-displayed form. G14 fence
  family remains read-only (authoritative state inspected, unknown cost
  never forgiven). Exact actor/session/replay ownership and audit
  oracles preserved; negative matrix description matches actual evidence
  with accepted unchanged component proofs explicitly reused.
- **Fixture/tooling corrections (test-only)**: pre-operation exactly-
  one-new-ID baselines (snapshot before each create/rotate/template-
  issue, bind the exact result), legacy positive usage on the
  independent still-priced seeded nano model (the G18-disabled
  gpt-4.1-mini rule state is kept, not re-enabled), clean generic
  unfenced valid-policy key(s) for the tampered-intent prerequisite
  (the frozen Codex-metadata key and fence keys keep their laws;
  oracles bound to the actual selected keys), the `_wheel_name`
  distribution-name stem correction (PEP 503) so the default artifact
  candidate can match while the mandatory source/wheel/installed payload
  byte checks gate every reuse.

## Evidence (owned local fixtures, honest labels)

All substantive runs below saved the direct pytest exit and JUnit before
display. Local evidence used owned labeled loopback PostgreSQL 16 (tmpfs)
and Redis 7, strictly synthetic provider (loopback mock) and SMTP (local
sink), the existing qualified `/tmp/slaif216-qualification-venv`
(Python 3.12), and unique owner-label/full-container-ID/loopback/tmpfs
identities with exact cleanup; no ambient databases, no real provider
inference, no real mail, no secrets in retained outputs.

### FINAL installed whole-GUI workflow (the 219 gate, 219-b)

Run exactly once after final product stabilization, on the actually
updated final payload:

```bash
env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL \
  RUN_GUI_PARITY_INSTALLED_WORKFLOW=1 \
  /tmp/slaif216-qualification-venv/bin/python -m pytest \
  tests/integration/test_gui_parity_installed_workflow.py \
  -q -p no:cacheprovider --junit-xml=/tmp/slaif219/junit-installed-workflow-219b-final2.xml
```

- Result: 19/19 tests passed, 0 skipped, 0 failed, 0 errors,
  PYTEST_EXIT=0, suite 69.832 s, start 2026-11-11 15:05:08 UTC. Log
  SHA256 `9dc7f8010a6aa459985ecad8ba07ac94c1ee0ca0b1f0230c3ae464bc5019cd64`,
  JUnit SHA256
  `a5dcb7bb8de0ad0b9eadd28f2bf119d8ea5fb354e0b36fa7fd877985c35a6cef`.
- Source identity at the run: commit
  `34cbf03078a47ebee5a52faf5bd00a1188ec1216`, tree
  `ca720571bc7ddd26e5fc7bda345b3f44ddc30b7b` — the FINAL product head,
  which existed BEFORE the run; no product file changed after it.
- Wheel: `slaif_api_gateway-0.1.0-py3-none-any.whl` (version 0.1.0,
  2,325,829 bytes), REBUILT by the run from the pristine final head
  (product bytes changed since the intermediate wheel — a justified
  build, not a receipt-only rerun), SHA256
  `8a364a97ee70610c3ccfa569246b01bbe93ce50588141d63b1f8cda42e6e8e06`;
  the workflow's own source/wheel/installed payload byte checks verified
  it before use.
- Installed origins: API and worker import from
  `/tmp/slaif219/installed-workflow/venv/lib/python3.12/site-packages/`
  (`slaif_gateway/__init__.py`, `slaif_gateway/workers/celery_app.py`),
  outside the checkout, PYTHONPATH unset; all packaged templates/assets
  match the selected installed payload (asserted by the workflow).
  Honest test-environment extra: `packaging` 26.3 installed in the owned
  venv for the real Celery worker's kombu Redis transport soft-import
  (not part of the wheel's hard dependency closure).
- Coverage: every G01-G18 row, the calibration row, the legacy
  lifecycle outcomes, and the negative matrix ran to persisted/audit
  outcomes in the final installed code.

### Intermediate installed receipt (superseded for product scope)

Before the rendered all-field correction, the same workflow passed once
at product head `2ee9cf068d69ae730d4e7d05441ef4bb59029d31`: 19/19, 0
skipped/failed/errors, PYTEST_EXIT=0, suite 42.998 s, start
2026-11-11 14:19:33 UTC, run HEAD
`b327e359d04ea96a64e78bd83dc394074be4a051` (docs/fixture-only on top of
the product head; `git diff 2ee9cf06 b327e359 -- app/` empty). Wheel
`slaif_api_gateway-0.1.0-py3-none-any.whl` SHA256
`a0657a78feee5bb13bc6ab3b313fc9228d70508c55249177e86f73c4ee3e7356` was
REUSED (built earlier from the pristine product head during focused
debugging; the corrected distribution-name candidate hit, gated by the
payload byte checks). Log SHA256
`458276376847b45c351023eac171146fa5ccb0d31fc1357849e76a8da976d19e`,
JUnit SHA256
`8d226ad7e54c38649aa030ec5c9c7fe5f620776718ced355abf4ee1893abfcf2`.
This is valid PARTIAL evidence for THAT code: the rendered whole-field
description requirement was not yet covered by its tests.

### Focused installed debug selections (product head 2ee9cf06)

- batch 00/01/02/06/09/10: 6/6, PYTEST_EXIT=0, 2026-11-11 13:49 UTC,
  JUnit SHA256 `3cc01e2c01ae0b9b148c6aefecfc5f5e070854281459db0d56c7fd481aa6e17c`.
- batch 01/06/10/15/15b/16/17: 7/7, PYTEST_EXIT=0, 2026-11-11 14:16
  UTC, JUnit SHA256
  `9a75f7ff2e58ec31d94d2f557965b41565625230eeaf0c5d21485eeb08ea2d52`.
  Intermediate debug iterations (fixture/oracle corrections, all
  test-only) are recorded in the debug logs and are not repeated here.

### Unit, docs, and lint

- Focused unit batch (219, 209, 214, 207, create-templates,
  actions-templates, 212): 265/265 passed, 0 failed, 0 skipped,
  PYTEST_EXIT=0, 89.421 s, 2026-11-11 14:24 UTC; log SHA256
  `99f2b4a7cdafe75ac1d99d5261cff264a675b3ac6d76447f6ea8a0c164143d39`,
  JUnit SHA256
  `2bb3bae919fe09e7e70cdc5a8f54fb8875727dfacdc1427909c9e6b63e5fab6d`.
- Focused unit batch after the rendered all-field correction (219, 209,
  214, 207, create-templates, actions-templates, 212, table-rows,
  inventory, keys-routes, key-create-routes): 461/461 passed, 0 failed,
  0 skipped, PYTEST_EXIT=0, 112.598 s, 2026-11-11 15:00 UTC; log SHA256
  `60e261e73aaab08d190ed462883327434911d5ffa65bd306ecd42c25c01e1042`,
  JUnit SHA256
  `c057162d7dc35c246ef6b6869cea6a721197692c4a747f64644d3f3dd3534ac5`.
  The actions-templates disabled-live-burn oracle was adapted to the
  actual DOM (the dynamic margin inputs now carry their stable ids and
  the linked live-burn help), preserving the value/inputmode/disabled
  guarantees.
- Docs checks (asof, contract-drift, inventory, logo, product-scope,
  rc2-feature-scope) after each documentation touch: 59/59,
  PYTEST_EXIT=0 (2026-11-11 ~14:2x and ~15:0x UTC); first-run log
  SHA256 `e754593284eb8180e22256cd3be83cd88327e73883ac09527dc40b5f5e77bb73`.
- Scoped Ruff over ALL PR-changed Python files (14 at 2ee9cf06, 15 at
  the final head, including the extended inventory module): RUFF_EXIT=0
  in both runs ("All checks passed!"; both log files byte-identical,
  SHA256 `a6f0dbc8994bde1c14490ce37df741b06dc0b7012b391cfc3d1044eea877577f`).

### Real-Chromium browser (owned full-app services)

- DIRECT-EXIT receipts at the rendered-correction head
  (219 create whole-field sweep in both policy-source states; 219
  trusted AND standard detail whole-field sweeps with details
  disclosures opened; 207 `test_create_form_help_and_provider_tri_state`;
  207 `test_create_document_mode_persists_canonical_policy`): 4/4
  passed, 0 failed, 0 skipped, PYTEST_EXIT=0, 22.129 s,
  2026-11-11 15:03 UTC; log SHA256
  `42cca89486381255232af0426b555460d1b5a8fc344022b07a7c2ac360ded352`,
  JUnit SHA256
  `25fd7105fd687d81b54715f342c2492d00feb5e37f200b5a03dacf477172328a`.
- Earlier local runs at 2ee9cf06 (207 x2 create consumers, 219 keyboard
  detail): observed completion with passing dots, 2026-11-11 13:46-
  13:47 UTC. Those local receipts were `pytest | tail` sessions without
  a captured pytest status: they are observed completion, NOT a direct-
  exit receipt; the final-head CI browser job provides the authoritative
  direct qualification.
- CI classification: at pushed 5aa58fe the unit job failed ONLY the 209
  form-page oracle and the browser job failed the three documented cases
  (create document-mode toggle, 209 picker help, 219 keyboard wait) —
  all repaired in 2ee9cf06 and re-qualified locally above. At 2ee9cf06
  the browser job failed during InstallChromium (apt temporary DNS
  failures, exit 100, BEFORE tests — all browser tests skipped by setup,
  an infrastructure error, not a product failure); root retried ONLY
  that failed job in run 43032572345; its actual result is root's to
  verify. No product or test change was made for the infrastructure
  error.

### Root independent scoped probes (separately qualified, not pytest)

- Calibration boundary (preauthorized fake summary + REAL ASGI route,
  no DB/network/browser): safe 200, known-cookie-alias 400 (no echo),
  oversize 400, invalid-multiplier 400, and the corrected malformed-key
  404 with private/no-store/nosniff — handler-boundary proof, not a
  deployed/backend exploit claim and not native DB proof.
- Rendered all-field re-audit (actual Jinja/CSS/JS isolated Chromium,
  fake-authorized ASGI, no DB/server/network): create-guided 57
  controls, detail-standard 75, detail-trusted 75 (details disclosures
  opened) — ZERO missing resolving descriptions and ZERO duplicate IDs
  in all three states after the correction (57/75/75 before: 11 missing
  each). This verifies the concrete 14-source-pattern correction; field
  names/values/layout/Core unchanged.
- Macro/JS picker probe (isolated Chromium, actual admin.css + record-
  choices/policy-selector JS, network blocked): BOTH main and menu-
  search of the enhanced picker have resolving help.

### Corrected 219-a provenance (immutable 219-a report retained as-is)

Root independently verified the 219-a wheel's 503 packaged files equal
final app bytes (four missing source files are empty `.gitkeep`
placeholders) and app bytes at `45893daa` equal SELF. However
`00737d17` was created 09:32:51Z, AFTER the final 219-a installed run
(09:31:18-09:32:00Z); the 219-a report's build-source assertion is
wrong — the actual source HEAD was `45893daa`. This report corrects the
provenance; the immutable 219-a report is unchanged, and the valid
wheel/component proof is retained at its exact scope.

### Reused accepted component evidence at its exact scope (not repeated)

- 219-a focused receipts (root-verified): unit 240/0/0, start
  08:59:50.469615Z, log SHA256
  `32979fcf674ef49fc5875cc88dfced4bfcdada52637a792fa91e282be72978b3`;
  browser 5/0/0, start 08:05:48.841807Z, log SHA256
  `0533bd443bbb1e35c91ffd2e3a0b5f3df30d1492c9d5fb609f184a9a92722bf3`;
  installed 17/0/0, start 09:31:18.564329Z, 41.393 s, log SHA256
  `0b5d796b31848ee99cc67bed9311a690845fb832302043b21b10ef2eb134d347`
  (their `.rc` files contain actual PYTEST_EXIT=0).
- The unchanged backend service/CLI matrices, inventories, and the
  accepted 207-218 component receipts are cited in the current guides
  (`docs/verification/gui-cli-parity.md`), not repeated here.

## Documentation updated / checked

Updated (current, living docs only; no earlier immutable report or
order touched):

- `docs/MISSING_GUI_FUNCTIONALITY.md` — section 22 (219-b delivery
  status) plus the section 6 delivery line; the false account-prose-
  shortened claim corrected (account templates unchanged by 219;
  purpose/consequence guidance retained and revalidated).
- `docs/admin-usability.md` — section 20.3 account bullet corrected;
  section 20.6 (219-b corrections) with the rendered all-field
  guidance completion.
- `docs/verification/gui-cli-parity.md` — the single current GUI
  verification record: 219-b section (what it repairs, focused
  evidence, the FINAL installed gate at product head 34cbf030 with the
  intermediate 2ee9cf06 receipt re-labeled, honest source/wheel reuse),
  account line corrected.
- `docs/configuration.md` — calibration JSON boundary paragraph
  (commit b327e359).

Checked: docs checks (asof, contract-drift, inventory, logo,
product-scope, rc2-feature-scope) 59/59, PYTEST_EXIT=0, after every
documentation touch.

## Limitations

- The fake-ASGI calibration probes are handler-boundary proof with a
  preauthorized fake summary; they are NOT native DB, deployed, or
  exploit claims. The isolated-Chromium rendered/macro probes are scoped
  native-DOM checks with network blocked and no DB/server; styled
  native full-app proof is the focused browser tests and CI.
- The G10 non-rotation probe proves the plain-route attachment session
  does not rotate the displayed form token; it does NOT claim Codex-
  route configuration parity (the guided plan validator's group
  boundary for Codex-specific keys is pre-existing and unchanged).
- The frozen Codex-metadata key (k6) is lawfully inadministrable for
  generic batch operations and keeps its sentinels; the held (k3) and
  active (k5) fence keys keep their fence laws; the tampered-intent
  negative coverage uses clean generic unfenced valid-policy keys with
  their focused prerequisites, and oracles are bound to the actual
  selected keys.
- Legacy rotation invalidation is proven by real pre/post bearer
  authentication on local /v1/models (no provider call) plus DB
  revoked/hash facts; it is not a live-provider cache-invalidation
  claim.
- The 13:46-13:47Z local browser receipts are observed completion only
  (no captured pytest status); the final-head CI browser job (root-
  retried after the apt-DNS InstallChromium infrastructure failure) is
  the authoritative direct browser qualification, still root's to
  verify.
- No claim of release, RC2, production, security, compliance, or
  universal-client compatibility; the RC2 release decision remains
  outstanding per the repository baseline. No 220+ deferral was made:
  all remaining original 219 scope was finished on this PR.
- The installed workflow's test environment includes the honest extra
  (`packaging` 26.3 for the worker's kombu Redis transport soft-
  import); the wheel's own dependency closure is unchanged.
