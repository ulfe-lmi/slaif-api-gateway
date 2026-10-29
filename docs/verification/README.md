# Verification Evidence

This directory indexes durable verification records for specific repository
commits and execution environments. A record describes what one bounded run
actually proved; it is not permanent certification of later commits, production
fitness, security, compliance, provider behavior, or scale.

## Current evidence (newest first)

For current readers, these are the newest qualification and identity records
on record. They are dated, commit-specific evidence, not certifications.

- [`2026-10-29 Objective 205-a installed CLI field administration workflows verification (PARTIAL handoff)`](2026-10-29-cli-field-installed-workflow.md)
  (recorded 2026-10-29) - actual installed `slaif-gateway` console from a
  payload-verified wheel of accepted source `5e59a02` in an owned venv, on
  an owned labeled PostgreSQL 16 container with a loopback SMTP sink:
  outcomes 1-4 and 6 executed and green in the final byte-matched module
  run (6/6 PASS, 0 skip). Same-PR 205-b continuation (recorded in the same
  file): the confirmed numeric-echo CLI product gap fixed in source
  `420fb8f` (shared no-echo conversion at 17 positions; 110 new + 136
  existing unit PASS, 0 skip), first six outcomes re-qualified 6/6 PASS on
  the fresh wheel `042eb23a` in a fresh owned venv (root-verified 432-file
  identity + 17-position installed canary). Same-PR 205-c continuation
  (recorded in the same file, product still frozen at `420fb8f`): outcome
  5 (real filtered `GET /v1/models` through the installed owned gateway
  with provider/allow-list/disable controls), outcome 7 (two configured
  completion services + routes prepared disabled, inspected, separately
  activated), and outcome 8 (stable-ID context/media route updates via
  reviewed plans, stale-plan refusal, multi-route) executed and green in
  the final combined run (3/3 PASS, 0 skip), plus the safe persisted
  0600/0700 operator transcript/identity export (66 labeled records,
  canary-clean); outcomes 9-11, config-show, the complete all-eleven
  transcript, and the final fresh all-eleven run remain mandatory in
  later same-PR suffixes.
  Same-PR 205-d continuation (recorded in the same file, product still
  frozen at `420fb8f`): outcome 9 (one-time delivery lifecycle against the
  owned loopback SMTP sink: pending channel, real send-now with full
  MIME-decoded key observation, exact repeat refusal, definite 550 refusal
  + safe explicit retry, and labeled sending/ambiguous/expired fixture
  states inspected before any unsafe probe) and outcome 11 (reviewed
  replay-reference expiry maintenance: schema-valid planted rows,
  configured-default-TTL dry-run, mixed-mode refusal, monotonic apply,
  already-applied repeat, explicit `--include-expired` second plan,
  column-level preservation) executed and green, plus the installed
  `config show` finite process-configuration evidence (exact 45-field
  allowlist, configured vs default provenance, invalid-Settings
  no-echo/no-traceback) in the final D combined run (3/3 PASS, 0 skip,
  37-record labeled transcript); outcome 10, the complete all-eleven
  transcript, and the final fresh all-eleven run remained mandatory in
  later same-PR suffixes.
  Same-PR 205-e continuation (recorded in the same file, product still
  frozen at `420fb8f`): outcome 10 (gateway-recorded failure diagnostics)
  executed and green through the ACTUAL installed gateway observer +
  installed `diagnostics` commands: pre-auth 401 without key attribution,
  endpoint denial with resolved key but no route facts, unsupported
  function-tool capability, Codex context-window rejection with actual
  decision numbers/ceilings, a genuine service-persisted replay reference
  authorizing then denying after ONLY its expiry moved, and an unsupported
  provider stream event after wire 200 with failed-then-released
  accounting; plus CLI status/not-found/ambiguous/typed-unavailable
  outcomes, capture OFF with an empty owned capture dir, and
  content-free store/transcript canaries (focused run 1/1 PASS, 0 skip,
  15-record labeled transcript). Same-PR 205-f continuation (recorded in
  the same file, product still frozen at `420fb8f`): the SINGLE FINAL
  COMPLETION run — one fresh complete installed workflow of ALL 13 cases
  (installation identity + all 11 outcomes + configuration) executed
  13/13 PASS, 0 skip, on a fresh source-verified wheel `4e4c76fb` in a
  fresh owned venv (root-verified 432-file identity), with DoD5 then
  DoD10 actually exercising the prior-gateway stop/replace path, the
  complete 206-record indexed operator transcript (0 unlabeled, 33
  expected negative exits, 0700/0600, canary-clean), the single
  full-scope brief coverage table, and consolidated operator/upgrade
  documentation; the earlier "remains mandatory in the final same-PR
  phase" carry-forward is SUPERSEDED by that final section. Strategic
  merge and actual-main verification remain pending.

- [`2026-10-29 Objective 204 CLI record edits and process configuration inspection verification`](2026-10-29-cli-record-edits-and-config.md)
  (recorded 2026-10-29) - owned-PostgreSQL-16 actual-CLI +
  actual-service evidence (8: owner move preservation with exact audit,
  clears/conflicts/refusals, late-audit rollback, cohort partials and
  FINAL merged window, causal lock-wait for both record types with
  cleared PG statistics snapshots) and focused unit layers (74 new:
  42 schema + 21 service/CLI + 11 config inspection incl. cold
  subprocess entrypoint; 61 unchanged consumers; 69
  governance/documentation passes) for
  `slaif-gateway owners update` / `cohorts update` partial edits through
  the shared record services (locked row first, delegated
  complete-update law, exact owner_updated/cohort_updated audits,
  late-fault rollback) and `slaif-gateway config show` (finite 45-name
  allowlist, honest current-process snapshot, fixed safe
  configuration_unavailable boundary, no credential values), plus the
  two fixed task-import deferrals; synthetic data only, no
  schema/settings change, no provider/client/SMTP/205-wheel claim;
  final-head CI gated by root.
- [`2026-10-29 Objective 203-a reviewed key-configuration batches verification`](2026-10-29-cli-key-batches.md)
  (recorded 2026-10-29) - owned-PostgreSQL-16 actual-CLI +
  actual-service evidence (13) and focused unit layers (50: 38
  service/schema + 12 actual-Typer CLI, plus 137 unchanged consumers,
  56 governance/protocol, 44 documentation passes) for the two-step
  `slaif-gateway keys batch plan` / `apply` surface: READ ONLY exact
  37-key cohort preview (zero writes/audits, empty `excluded_by_status`
  per contract), atomic one-transaction apply with exact per-key audits
  and same-scope preservation, >100-eligible no-truncation vs cap+1
  overflow, stale membership/config/status/lock-join whole-batch
  refusals (causal holder/waiter observed with cleared PG statistics
  snapshot), late-audit full rollback (fresh-session proof), usage-only
  movement non-staleness across preview->first-write->repeat,
  `Numeric(18, 9)` money target proof, fresh fenced confirmation (saved
  confirmation is never authority), edited-artifact fingerprint refusal
  (first-apply and repeat states), and no-echo known-shape canaries in
  policy content/pathname/reason/retained config (guard fires before
  route/model validation can reflect values); synthetic data only, no
  schema/settings change (head 0026/33 tables), no
  provider/client/request-accounting/SMTP/205-wheel claim; final-head
  CI gated by root.
- [`2026-10-29 Objective 202-a email delivery inspection and safe explicit retries verification`](2026-10-29-cli-email-inspection.md)
  (recorded 2026-10-29) - focused affected unit batch (145 PASS: 18 new
  inspection + 3 new page-parse cases in the existing CLI suite + 2 new
  pre-decryption binding cases in the existing sender suite, plus 79
  unchanged consumers) and owned-PostgreSQL-16 actual-CLI +
  actual-service evidence (12) for the read-only
  `slaif-gateway email list/show` inspection surface and the explicit
  `--retry-failed`/enqueue-intent semantics: exact AND-combined SQL
  filters before deterministic paging of a 110-row tied-timestamp batch
  (owner email exact, never substring), no-echo page parsing, allowlisted
  metadata with safe historical audit error codes, zero-side-effect
  read-only proofs, exact delivery/secret binding and same-secret
  prior-attempt guards refused before decryption (real crypto hooks),
  causally correlated lock-wait concurrency with t0 < expiry < t1
  fresh-clock boundary, intent audit committed before dispatch with the
  existing three-UUID broker payload and safe
  `one_time_reference_id` reference; fake SMTP/Celery only, no real
  mail/broker, no schema change (head stays 0026/33 tables); root
  independent owned-PG baseline/fixed rechecks and CLI/dispatch/parser
  probes credited separately; not the 205 installed-wheel transcript;
  final-head CI gated by root. The same record carries the bounded
  202-b prepared-recipient correction (149 unit + 13 owned-PG layers):
  attempts prepared by this code record the exact prepared `to` in the
  existing sending commit (fresh-session DURING-attempt proof for
  success/SMTP-failure/finalization-failure), untouched older rows may
  retain creation-time metadata with no backfill, and the
  code-quality `await o_task` thread is recorded as a false positive.
- [`2026-10-29 Objective 201-a content-free request-failure diagnostics verification`](2026-10-29-cli-request-diagnostics.md)
  (recorded 2026-10-29) - focused unit (61 new: 25 service + 24
  middleware + 8 actual-Typer CLI + 4 alembic), owned-PostgreSQL-16
  service (11) and real-app API (11) evidence for the default-OFF,
  content-free `request_diagnostics` table and
  `slaif-gateway diagnostics status/request show/cleanup` surface:
  finite vocabularies, known-secret client-ID masking (fail-closed),
  true concurrent cap with idempotent repeat no-op, 8 KiB/64-char
  bounds, write-timeout boundary with byte-identical public responses,
  deterministic replay-reference authorize-then-expire chronology, and
  row/CLI/log canaries; plus 727 unchanged consumer/head-literal/
  governance passes and root independent actual-PG probes (schema,
  repeat-at-capacity, param bound, disabled-history/CLI); synthetic
  data only, no real client/provider/model/SMTP claim; final-head CI
  gated by root.
- [`2026-10-28 Objective 200-a Codex replay reference inspection and reviewed expiry extension verification`](2026-10-28-cli-replay-maintenance.md)
  (recorded 2026-10-28) - focused unit (42 new: 30 service/plan + 12
  actual-Typer CLI) and owned-PostgreSQL-16 (14) evidence for the
  read-only `codex replay inspect` summary and the two-step reviewed
  `codex replay extend` plan workflow: strict non-secret 0600 plan with
  three public optimistic fingerprints, monotonic expiry-only extension
  at original `created_at` + selected TTL, deterministic key/row lock
  order with post-lock scope revalidation and re-derived counts,
  already-applied no-op law, forced late-audit rollback, real-PG
  concurrent cohort-move invalidation, and the 20,451-reference/26-key
  single reviewed operation; synthetic data only, no real
  client/provider/model/SMTP claim; final-head CI gated by root.
- [`2026-10-28 Objective 199-a provider/route configuration parity CLI verification`](2026-10-28-cli-provider-route-configuration.md)
  (recorded 2026-10-28) - focused unit (90 new pure + 25 actual-Typer
  CLI) and owned-PostgreSQL-16 (19) evidence for the audited,
  lock-protected `providers update` partial updates,
  `routes add --capabilities-file` preparation, and the two-step reviewed
  `routes update --dry-run/--execute` plan workflow: strict bounded files,
  partial-vs-replacement capability semantics, configuration fingerprint
  staleness with zero-write refusals, no-op plan law, forced late-audit
  rollback, concurrency invalidation, and known-shape secret refusal;
  synthetic data only, no real provider/model/SMTP claim; final-head CI
  gated by root.
- [`2026-10-28 Objective 198-a faithful standard-key cloning verification`](2026-10-28-cli-key-cloning.md)
  (recorded 2026-10-28) — focused unit (40 new: 19 service + 21
  actual-Typer CLI) and owned-PostgreSQL-16 (5) evidence for the
  auditable, retry-safe `keys clone` plan/execute operation: strict
  non-secret plan document with source fingerprint, eligibility
  revalidation, receipt-first deduplication, canonical
  re-derivation/equality, recognized secret-shape refusal, one-time key
  channel with bounded pending delivery, clone audit, and atomic
  single-caller-transaction commit under READ COMMITTED proven with two
  separate OS processes; synthetic data only, no real
  provider/model/email claim; final-head CI gated by root.
- [`2026-10-28 Objective 197-a effective key policy, safe lookup, bounded lazy throttling CLI verification`](2026-10-28-cli-effective-key-policy.md)
  (recorded 2026-10-28) — focused unit (65 new + 135
  affected groups) and owned-PostgreSQL-16 (9) evidence for the
  dedicated audited `set-lazy-throttling` setter, the
  configuration-only `policy effective` view, safe
  UUID/public-key-ID/email lookup with bounded complete paging, and
  configuration-only `policy explain-route` with key-state blockers
  first, the existing resolver law, base-request capability checks,
  and the disclosed 1000-candidate bound; real `GatewayAuthService`
  parity proven in PG; synthetic data only, no real
  provider/model/email claim; final-head CI gated by root.
- [`2026-10-25 Objective 195-a admin multi-value list filters verification`](2026-10-25-admin-list-multiselection.md)
- [`2026-10-25 Objective 195-a admin multi-value list filters verification`](2026-10-25-admin-list-multiselection.md)
  (recorded 2026-10-25) — focused unit (147 affected + 96
  choices/195-new), owned-PostgreSQL-16 (13, incl. the R5 selected
  audit-hydration scope/limit regressions and the root-probe recheck
  2/2), and real authenticated Chromium evidence for the
  OR-within/AND-across multi filters, bounded 400s, SQL-before-LIMIT
  pagination, chip UI, label-only async refresh, and CSV multi
  exports; synthetic data only, no real provider/model/email claim;
  final-head CI gated by root.
- [`2026-10-25 Objective 193-a admin-visual-consolidation verification`](2026-10-25-admin-visual-consolidation.md)
  (recorded 2026-10-25) — focused unit (401 passed) and native-Chromium
  owned-PostgreSQL evidence for the shared visual foundations,
  hyperlink table-sort headers, integrated record-choice control
  appearance, and deterministic local asset-revision URLs; synthetic
  data only, no real provider/model/email claim.
- [`2026-10-25 Objective 194-a admin numbered tables and metric columns verification`](2026-10-25-admin-numbered-tables-and-metric-columns.md)
  (recorded 2026-10-25) — focused unit (131 passed, mocked ASGI /
  pure renderer) and native-Chromium owned-PostgreSQL evidence for
  the structural row ordinals, split usage/quota metric columns,
  Rows selector, Source-row provenance, and the report ordinal
  column; synthetic data only, no real provider/model/email claim.
  The same-day 194-b record below resolves the pending
  renderer-identity (194.1) same-PR follow-up.
- [`2026-10-25 Objective 194-b catalog renderer identity upgrade verification`](2026-10-25-catalog-renderer-upgrade.md)
  (recorded 2026-10-25) — bounded metadata repair binding the
  current report renderer to `194.1`: supported-versions constants
  only (no schema/field/policy/accounting change), authenticated
  `183.1` refusal proven before database contact in apply and
  apply-status (digests/HMAC ok, fixed distinguishable reason,
  sealed bytes untouched), fresh-run CLI review→verify binding
  `194.1`, focused catalog-refresh unit groups, and one real owned
  PostgreSQL 16 atomic-apply node; no full-matrix rerun, no
  release/production claim. (194-d same-PR continuation later
  corrected the upgrade instructions' output-root collision and this
  record's Layer-2 evidence wording — see the 194-d OAP report.)
- [`2026-10-25 Objective 192-a admin-usability verification`](2026-10-25-admin-usability.md)
  (recorded 2026-10-25) — focused JUnit, owned-PostgreSQL, real
  authenticated admin HTTP, and native-Chromium evidence for the
  sortable-table and known-record/known-option picker surfaces;
  synthetic data only, no real provider/model/email claim.
- [`Incoming request capture bounded verification`](incoming-request-capture.md)
  (recorded 2026-10-18) — objective 191: unit/multiprocess-store/
  fresh-HTTP-owned-PG-mock-backend results for the default-OFF operator
  request-capture facility; synthetic request data only, no real
  client/model/provider claim.
- [`2026-09-20 post-documentation release-identity record (candidate 71092fef)`](2026-09-20-post-documentation-release-identity-71092fef.md)
  — `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY` for exact `main`
  `71092fefee74649bad71dbb5b7a7106115e9f545` (PR #315 merge): identity
  derivation that binds the Objective-173 integrated qualification to the
  documentation-complete candidate through empty
  runtime/deployment/dependency-surface diffs from both prior anchors
  (the Objective-177 `db0bd3ae` identity record and the 173 integrated
  record); not a second full clean-room run, and not a release decision.
- [`2026-09-20 release-candidate identity record (candidate db0bd3ae)`](2026-09-20-release-identity-db0bd3ae.md)
  — `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY` for exact `main`
  `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (PR #313 merge): identity
  derivation from the Objective-173 qualification through an empty
  runtime/deployment/dependency-surface diff; not a second full clean-room
  run, and not a release decision.
- [`2026-09-17 current-main integrated requalification (candidate 2b61312e)`](2026-09-17-current-main-integrated-requalification-2b61312e.md)
  — `RESULT=QUALIFIED-RC-POSTURE` for `main`
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (PR #309 merge): mocked-upstream
  production-appliance double with two labeled environment-only non-passes;
  not a real-provider run, release decision, or production certification.

## Records

- [`2026-10-18 Codex 0.162 file-backed compatibility profile DATA`](codex-file-compatibility-profiles.md) —
  Objective 190-b: shipped default profile DATA (revision 3, canonical
  digest `aa3de537...daf90bd`), bounded parser/immutable loader,
  data-revision module identity with frozen v1/v2 migration selectors,
  operator file override with no-silent-fallback bootstrap, audited
  `migrate-key-profile`, real 197-name regression fixture, fresh-process
  real-HTTP Gateway and owned-PostgreSQL evidence, and wheel packaging
  proof.
- [`2026-10-18 Codex 0.162 version-2 connector tool names`](codex-0162-connector-names.md) —
  Objective 190-a: registered `codex-0.162-responses-v1` v2 profile
  (namespace-scoped leading-underscore connector tool names, exact
  preservation), frozen 0162-v1 historical selector with the
  0162-v1 ↔ 0162-v2 audited migration hop (six legal edges), unit,
  real-PostgreSQL migration, and real-Gateway stream/replay E2E
  evidence; the full operator-supplied 197-name artifact remains
  pending.
- [`2026-10-18 Codex 0.162.1 additional-tools profile and Local-pair lowering`](codex-0162-local-tools.md) —
  Objective 189-a: registered `codex-0.162-responses-v1` v1 profile
  (finite 16/256/256/20,000/262,144/4,096 taxonomy), approved initial-prefix
  provider lowering for the exact Local pair, prompt-cache-key omission,
  and documented route/pricing prerequisites; unit, mocked, real-PostgreSQL
  E2E, and independent official-CLI evidence.
- [`2026-10-18 Codex 0.149-v5 additional-tools ID and audited module migration`](codex-additional-tools-id.md) —
  Objective 189-a: bounded optional declaration item ID on 0.149 (v4 → v5)
  with unknown-field rejection and existing gates preserved, and the
  audited four-edge key-module upgrade/rollback (frozen 0.149-v4 tuple,
  dry-run default, no schema change).

- [`2026-10-17 SLAIF visual design`](slaif-visual-design.md) —
  Objective 188-a: packaged admin theme, shared shell, named table
  regions, and branded error surfaces; twelve unit design tests plus
  four native-browser cases (owned PostgreSQL, no provider
  invocation) and inherited 187/185 browser regressions.
- [`2026-08-17 current-main baseline`](2026-08-17-current-main-baseline.md) —
  one 24-worker full current-machine matrix, classified `RESULT=FAIL` because
  one of 2,534 tests failed. The separate post-PR-220 128-worker HPC
  qualification remains not run.
- [`2026-08-24 production-appliance qualification`](2026-08-24-production-appliance-qualification.md)
  — disposable production Compose, NGINX/TLS, PostgreSQL, Redis, worker/
  scheduler, provider-double, accounting, failure, privacy, persistence,
  backup/restore, and cleanup evidence for the named candidate. It is not a real-
  provider run, release decision, security certification, or production approval.
- [`2026-08-24 documentation architecture and truth audit`](2026-08-24-documentation-audit.md)
  — repository-wide cross-document and documentation-versus-code baseline for
  the documentation-modernization PR.
- [`2026-08-24 RC-beta readiness record`](../beta-readiness.md)
  — dated readiness record for `main`
  `8f2813bf745b90221da33a7cfaf40726c5b1b480` (reviewed 2026-08-24).
  Historical/dated evidence for the named commit only; not a current-state
  claim.
- [`2026-09-17 OpenAI SDK 3.9.0 official-client compatibility qualification`](2026-09-17-openai-sdk3-qualification.md)
  - 54-test official OpenAI-client E2E matrix qualified under
  `openai==3.9.0` (`OUTCOME=A`): wire-identity capture evidence, one
  root-cause family (SDK 3.x `httpx2` transport escapes respx observation),
  harness adaptation only, no gateway change. Evidence boundary: base
  `main` `1fccaa746df6cd44f1ddf8c2ec5cf6ea9f18b1cb` and the Objective 166 PR
  head. Mocked-upstream qualification only; not a real-provider run, release
  decision, security certification, or production approval.
- [`2026-09-17 current-main integrated qualification`](2026-09-17-current-main-integrated-qualification.md)
  - fresh RC-posture qualification of `main`
  `9bb81cb960b6d3ba5373425cbe50cdcc670b93dc` (PR #303 merge): clean-room
  P1 freeze, production-appliance harness run 1 `RESULT=FAIL` (privacy
  metrics scrape) with run 2 reproduction `RESULT=OK`, full local unit/
  integration/E2E matrix, and 9/9 CI checks SUCCESS. Verdict
  `RESULT=NOT-QUALIFIED` on the non-deterministic per-worker
  metrics-exposure finding. Dated evidence for the named candidate commit
  only; mocked-upstream qualification, not a real-provider run, release
  decision, security certification, or production approval.
- [`2026-09-17 current-main integrated requalification`](2026-09-17-current-main-integrated-requalification.md)
  - fresh RC-posture integrated requalification of `main`
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7` (PR #305 merge; repeat of the
  abandoned Objective 169): two consecutive no-keep production-appliance
  harness runs `RESULT=OK` 16/16, full local unit/integration/E2E matrix
  (modulo the two labeled environment-only non-passes), and 9/9 required
  CI checks SUCCESS on the PR head. Verdict
  `RESULT=QUALIFIED-RC-POSTURE`. Dated evidence for the named candidate
  commit only; mocked-upstream qualification, not a real-provider run,
  release decision, security certification, or production approval.
- [`2026-09-17 OpenAI Python SDK 3.14.1 official-client compatibility requalification`](2026-09-17-openai-sdk-3141-requalification.md)
  - deliberate requalification of the declared official-client
  compatibility contract under the current stable SDK
  `openai==3.14.1` from the qualified baseline `openai==3.9.0`
  (`OUTCOME=A`): Phase B soundness 54/0/0, Phase C 54/0/0 on a
  single-variable dependency delta, ripple check green modulo the two
  labeled environment-only non-passes, and 9/9 CI checks SUCCESS on the
  PR head. Dated evidence for the named base commit and candidate SDK
  version only; mocked-upstream qualification, not a real-provider run,
  release decision, security certification, or production approval.
- [`2026-09-17 current-main integrated requalification (candidate 2b61312e)`](2026-09-17-current-main-integrated-requalification-2b61312e.md)
  - fresh RC-posture integrated requalification of `main`
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (PR #309 merge; repeats the
  strict 170 acceptance set plus the new P0 runtime-tree identity proof):
  the exact 12-path candidate-to-candidate delta is dev-pin/documentation/
  OAP-record paths only and the runtime-surface diff is empty; two
  consecutive no-keep production-appliance harness runs `RESULT=OK` 16/16,
  full local unit/integration/E2E matrix (modulo the two labeled
  environment-only non-passes), and 9/9 required CI checks SUCCESS on the
  PR head. Verdict `RESULT=QUALIFIED-RC-POSTURE`. Dated evidence for the
  named candidate commit only; mocked-upstream qualification, not a
  real-provider run, release decision, security certification, or
  production approval.
- [`2026-09-20 release-candidate identity record (candidate db0bd3ae)`](2026-09-20-release-identity-db0bd3ae.md)
  - verification-only identity derivation binding the Objective-173
  full integrated qualification
  (`2b61312e0eb569aa7c6f953f52e35b44e84b91c1`,
  `RESULT=QUALIFIED-RC-POSTURE`) to exact `main`
  `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (PR #313 merge): empty
  runtime/deployment/dependency-surface diff, every intervening path
  classified CI-only / release-metadata-SBOM / documentation-OAP,
  fresh 9/9 stable checks plus CodeQL suite rollup `success`, RC2 scope
  closure 27/0/21/3/0, and SBOM correspondence
  `SBOM_CHECK=OK components=60`. Verdict
  `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`. Dated evidence for the
  named candidate commit only; identity derivation, not a second full
  clean-room qualification, and not a release decision.

- [`2026-10-15 objective 185-a lazy (waiting) throttling verification`](lazy-throttling.md)
  - focused objective record for per-key lazy throttling (PR #323): 14
  real owned-PostgreSQL/owned-Redis integration cases, 24 helper/route unit
  cases, and 3 actual-browser cases with exact new-versus-inherited test
  mapping. Mocked-upstream provider evidence only; not a release decision,
  production approval, or broad-matrix claim.
- [`2026-10-16 objective 187-a operator branding verification`](operator-branding.md)
  - focused objective record for optional operator branding (PR #187):
  62 new/affected unit cases (reader FD I/O, PNG framing, render,
  config, compose contract, docs gates), 3 actual-browser cases against
  a real owned PostgreSQL, and 4 owned-container cases with the read-only
  branding mount; test-only container bootstrap, no provider/model/email
  access; final-head CI, strategic review, and guarded merge pending.

- [`2026-10-27 objective 196-a typed CLI key-policy verification`](2026-10-27-cli-key-policy.md)
  - focused objective record for typed CLI key-policy configuration:
  68 new unit cases (strict authoring validator, version-1 schema safe
  errors, partial-update laws, fresh-subprocess configured-profile
  bootstrap proof), 145 affected existing unit cases (two oracles updated
  exactly where mandated), and 5 real owned-PostgreSQL integration cases
  (file-only create/export, preserving provider updates, distinct
  null-vs-empty provider persistence, atomic bound-key repin rejection,
  bulk-import provider parity); no schema migration, no provider/model/
  email access, not a release decision.

- [Qwen Codex live smoke and regression evidence](codex-qwen38-live-smoke.md)
