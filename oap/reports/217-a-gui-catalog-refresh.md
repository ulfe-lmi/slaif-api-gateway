# 217-a immutable report — G15 GUI catalog workspace + human-approved FX conversion

## Identity and activation

- Objective: 217, identifier `217-a` (CREATE_PR); ONE PR #373, branch
  `oap/217-gui-catalog-refresh`; DRAFT, never merged, no auto-merge.
- Order: `oap/orders/217-a-gui-catalog-refresh.md` (25,359 bytes,
  SHA-256 `9444fe37f59fd45c25f7a72881764c7d8946f47f7b825a66dc1d69a4f9f7ed36`),
  committed byte-unchanged (root-authored, bytes immutable).
- Active pointer: `oap/active` = exactly the five bytes `217-a`
  (no trailing newline), unchanged.
- Base/remote main: `3b7a5e39189c5406641f4143d0b8ed1c3992e968`.
- The original control signal was consumed ONCE; no further control
  reads or waiters were started by this turn.

## Publication topology

Implementation head SHA: 6bf8641021816c02c6c5c4a98122d642090fbbdd
Report publication commit: SELF

- Six append-only implementation commits over base main (no amend, no
  force-push):
  - `978e50cb` — G15 GUI catalog workspace (proposals + sealed catalog
    refresh) with custody, guards, and unit qualification;
  - `8a0a7f07` — current-head CI qualification (closed-leaf custody job
    ids, hermetic no-source CLI fixture, proxy-reload + copy-ready
    deploy guide);
  - `6b1aa16e` — copy-ready deploy procedure corrections (root one-off
    ownership, offline `ensure_seal_key`, checked private backup,
    optional shipped nginx profile vs external proxy);
  - `679544a0` — gzip size-bound text correction + `--build` the new
    checkout code in the apply step;
  - `23b9b432` — REAL FX conversion for non-USD provider-catalog
    proposals (human-approved after the bounded estimate): shared pure
    capture/converter seam, CLI/worker/GUI composition, focused unit +
    native + browser qualification, docs, visual hint correction;
  - `6bf86410` — doc precision for the FX conversion (per-batch write
    order; runtime native→EUR accounting distinction).
- This report-only SELF commit has SOLE parent the literal
  implementation head `6bf86410…` and its diff contains ONLY this
  report file.
- PR #373: https://github.com/ulfe-lmi/slaif-api-gateway/pull/373
  (DRAFT/OPEN at publication; description updated to the resolved FX
  decision).

## What this delivers (G15, bounded)

- Admin GUI "Catalog workspace" (`/admin/operations/catalog/`) over the
  EXISTING Core catalog services, default-off, feature-local:
  - **Proposals**: queued `generate_provider_catalog_proposal` job
    (closed endpoint-scope vocabulary, closed package presets,
    OpenAI-only `api`/`assisted` behind the existing deployment-secret +
    risk-ack gates, finite caps); generated route/pricing TSVs bridge to
    the EXISTING import preview; UNSEALED proposal artifacts (no
    cryptographic "verified" claim); closed preset + closed-file
    package downloads; enforced 32 MiB output ceiling with before-write
    admission; exact job-id result/refresh binding (explicit
    unknown/foreign id refused, never substituted).
  - **Collect**: bootstrap vs refresh, closed providers, the NEW closed
    `catalog_upstream` record choice (official upstream IDs; the
    collector selects literal upstream IDs), live read-only DB or
    uploaded baseline (8 MiB bundle / 32 MiB baseline), publishes one
    sealed run via the same Core pipeline as the CLI.
  - **Run review / verify / apply / status**: authenticated canonical
    plan rendering (honest configured-vs-SQL-observed target semantics,
    prices with explicit currency + per-1M/per-request units, bounded
    apply-plan projection); apply is the reviewed explicit
    confirmation (bounded reason, server-derived actor, fresh existing
    superadmin gate, session-bound HMAC intent, Core one-transaction
    `apply_reviewed_run`); status renders authoritative `apply_status`
    records (committed repeat = `already_committed`; unconfirmed only
    for unknown/unconfirmed outcomes).
  - **Review supplied bundle / Export baseline**: queued jobs;
    NEW-ONLY publication with byte/inode identity.
  - **Operator custody**: opened-never-created 0700 root + existing
    0600 seal key (refused inside repo/source/PGDATA); finite active
    (1) / retained (20) / bytes (1 GiB floor 64 MiB) / time (300 s)
    bounds with before-growth reservations under concurrency; exact
    custody-byte accounting (metadata/temp/lock + nested packages);
    truthfully terminal queued-cancel recovery; complete-entry
    identity-checked terminal cleanup; IDs-only broker payloads;
    secret-persistence canaries (known-incoming-secret/credential-shape
    refusal before custody persistence).
- **Output currency / FX conversion (human-approved extension)**:
  non-USD proposal output converts every price with ONE active,
  configured direct USD→target FX rate captured once before generation
  (single DB transaction closed before network/generation), applied per
  candidate batch before its artifacts are written, with the source USD
  amounts + applied FX pair/rate UUID/validity/capture time preserved
  and the official source unit never relabeled. USD is the identity
  conversion and stays offline-capable (no database). Missing or
  not-currently-active direct pairs (or an unconfigured database)
  refuse safely before generation (`proposal_fx_unavailable` /
  `proposal_fx_rate_missing` GUI; fixed safe CLI errors); no relabeling,
  no inferred inverse, no cross-currency graph, no automatic FX fetch.
  Intentional correctness fix: pre-217-a non-USD `--currency` relabeled
  native USD amounts; default USD output is unchanged. Runtime
  pricing/accounting (native→EUR at request time) is unchanged.
- Deploy/ops docs: copy-ready new-install/upgrade procedure (volume
  ownership, offline seal-key creation without printing/replacing it,
  the three GUI env settings, `--build` restart, setup-ready
  verification, checked private backup of the SAME seal key + runs),
  optional shipped nginx profile vs external proxy wording, disabled/
  feature-off route truth, and the OpenAI `max_models` cap disclosure
  (now honored for OpenAI too, after include/exclude filtering).

## Evidence index (honest scopes; reused receipts as accepted by root)

Labeled seams everywhere: collect/proposal OFFICIAL-source BYTES are
synthetic at the labeled transport seam only; broker, worker process,
PostgreSQL, auth/CSRF, custody, sealing, and publication are real. No
upstream network, no ambient PG/Redis, no mocked broker, no real
provider or mail calls.

- **Unit, proposal FX pure seams** (`tests/unit/test_provider_catalog_proposal.py`):
  24 PASS / 0 fail / 0 error / 0 skip, 1.297 s — root-run receipt
  `/tmp/slaif217/junit-root-fx-proposal-unit.xml` (SHA-256
  `950e2db1816fb36061242fa21aff97dffbcab32b0b641b41047364d54cb1b9cf`):
  capture/convert/apply identity, Numeric(18,9) ROUND_HALF_UP contract,
  underflow/overflow/contract refusals, double-apply refusal,
  converted root+package/report/manifest/label agreement, USD no-fx,
  non-USD-without-capture and mismatched-capture refusals, OpenAI-
  assisted helpers receive native USD with final converted output.
- **Unit, CLI** (`tests/unit/test_cli_provider_catalog.py` + assisted
  non-USD case): 13 PASS / 0 / 0 / 0, 5.767 s — root-run receipt
  `/tmp/slaif217/junit-root-fx-cli-assisted.xml` (SHA-256
  `15a4dd9e7973666190595dbbbc3aebcbab31be57c85a1c1add57c7e208c8d273`):
  USD no-DB, missing-rate refusal with exact single direct-pair lookup
  + engine disposal, capture-once with configured row, credential-
  shaped `--currency` refused before settings/DB with no echo,
  configuration-fault canary wrapped into the fixed safe error.
- **Unit, worker capture** (`tests/unit/test_admin_catalog_refresh_217.py`):
  3 new FX cases PASS (`/tmp/slaif217/junit-217a-worker-fx.xml`,
  3/0/0/0, 2.373 s, actual EXIT=0): missing rate → failed
  `proposal_fx_rate_missing` with no output, one direct-pair lookup and
  engine disposed; configured row → ready with truthful
  `FX USD→EUR rate=…` progress and exact capture facts; unconfigured
  database → `proposal_fx_unavailable` with no engine built. Full
  module re-run (74 tests, actual EXIT=0) passed.
- **Native owned-PG real-HTTP/worker module**
  (`tests/integration/test_admin_catalog_refresh_217_postgres.py`):
  18 PASS / 0 fail, actual EXIT=0, 23.286 s — root-tracked
  independently re-verified receipt
  `/tmp/slaif217/junit-root-int-binding.xml` (SHA-256
  `0a855d3340736912ebe3b18147be94d94ecf4f951bdbb74c14499be7a8fdf4d8`).
  Plus ONE new non-USD queued proposal case: 1 PASS / 0 / 0 / 0,
  12.565 s, actual EXIT=0, `/tmp/slaif217/junit-217a-int-fx-case.xml`
  (SHA-256
  `a98f48156505663a0fbaac215c4279a98e51af0191e8c677a569c28e856a3eb8`):
  real owned-PG seeded exact USD→EUR row (UUID asserted), real owned
  Redis + application worker capture, exact-Decimal converted TSV
  (zero/None semantics), source-USD metadata + normalized-JSON FX fact,
  semantic import-preview counts with EUR rows. The two EARLIER
  full-module attempts of that case FAILED on fixture issues (stale
  seeded `valid_from`; equivalent-decimal spelling) and remain labeled
  failed — they are NOT a 19-case pass; only the corrected single case
  was re-run.
- **Browser** (`tests/browser/test_admin_catalog_refresh_217.py`, real
  Chromium over real app + owned PG + owned Redis + real worker):
  7 PASS / 0 fail (accepted module receipt). Plus ONE new non-USD
  rendered-form case: 1 PASS / 0 / 0 / 0, 12.711 s, actual EXIT=0,
  `/tmp/slaif217/junit-217a-browser-fx.xml`: currency select → generate
  → ready progress with the exact seeded rate → converted TSV download
  containing the exact seeded FX row id → EUR pricing import preview →
  desktop + 420 px captures.
- **Unit boundary reuse (accepted, unchanged code)**: 125-case CI-fix
  unit receipt `/tmp/slaif217/junit-217a-ci-fixes.xml` (47.556 s,
  SHA-256
  `01888c9130773d644d8456973129840e4c2f3865cffd4c2a6e5e592f95aa77bb`),
  41-CLI, 122-unit-GUI, 24-proposal-writers receipts.
- **Static**: Ruff clean over the full changed file set; documentation
  contract-drift/inventory/asof + admin usability inventory modules
  pass (actual EXIT=0).
- **GitHub CI (root-owned)**: on head `679544a0` all 10 checks SUCCESS
  (root individually adjudicated the CodeQL path-injection findings as
  false positives for that head). Final implementation head `6bf86410`
  CI is running/owned by root and is NOT asserted green here.
- **Visual (frozen)**: `/tmp/slaif217/217a-{index,run,collect,review-
  run,proposals,proposals-fx-narrow,apply-committed}-*.png`; the
  balanced proposals layout (short currency hint + full-width FX help)
  was inspected and accepted by root; no further visual churn.

## Limitations and non-claims

- The 219 installed whole-GUI gate remains OPEN: no installed-
  workflow, release, production, security, or compliance claim follows.
- No live-provider/upstream smoke; source bytes in queued/native/
  browser proofs are synthetic at the labeled seams only.
- Assisted proposal remains gated on the EXISTING
  `OPENAI_ADMIN_DISCOVERY_API_KEY` deployment secret + explicit risk
  acknowledgement; `max_web_calls` stays a REQUESTED prompt budget,
  not proven hard provider call/cost enforcement.
- The FX conversion freezes ONE captured configured rate until the
  proposal is re-run; it changes no runtime quota/accounting behavior
  and creates/inferes no rate pairs (runtime native→EUR remains
  separately configured; EUR is identity).
- PR #373 stays DRAFT; the strategic model/human owns final CI
  observation, review, and merge. No auto-merge.
- Untracked local files `CODEX-SESSIONS.md`, `codex.sh`, and `uv.lock`
  are hash-only protected context and were never staged or modified.
