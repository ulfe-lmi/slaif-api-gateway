# OAP Objective 199-c — final report: explicit note clearing and module/transport parity

Work order: `oap/orders/199-c-provider-clear-and-module-parity.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `199-c` (5 bytes, no trailing newline); order sha256
`0bedb600ce7aea086da355530dbaa8d622c148a2e7c0a25037ef8e944db345af`,
verified before and after committing).
Branch: `oap/199-provider-route-configuration`; base: `main`
`df7fb43cc9898cc784cf83cd10ddad9e946fc2af`.
PR mode: AMEND_EXISTING_PR — the same unique PR #355 created by 199-a,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/355, base `main`,
title "Configure provider timeouts and update routes through reviewed CLI
plans". The coding agent never merges; no auto-merge; root reviews
independently and guard-merges.

Implementation head SHA: 581d52f4be4758b6e5d830da5a7feacdee3b872a
Report publication commit: SELF

## Predecessor state (immutable)

199-a is complete on this branch: implementation head
`af792c9a00ff519f20cd20c39fbdf709fb76221c` and its report commit
`3170b6611b0e7765f071eedec8e859bc867d505c` (order sha256
`18f50b2dcfda225a7d358db1a167a66a576c0f8c6b5d3e93623ed19c9525fee6`).
199-b is complete on this branch: implementation head
`16d3a2d7e492f646d315f9e15858373a2b234ac8` (order sha256
`d1846162e5a85496ae49aa45511a3eb0c787f805d4fc057ede8c0fb64672dcb6`) and
its report commit `e0c0e3c9fb8a4c8eea2936dd326758cc47b0c8da` (report
sha256 `6e0fa48050742067d01207d205eae65ace2011b19074bfb3e4930195b7bd7c2f`).
Neither was amended by this round; the 199-c implementation commit's
first parent is the 199-b report commit. Objectives 200-205 remain
INERT; no other 199 suffix was activated.

## Implementation commit (this round)

1. `581d52f4be4758b6e5d830da5a7feacdee3b872a` — "Finish provider note
   clearing and module/transport parity (199-c)": the strategic order
   (bytes verified unchanged, sha256 above) + exact `oap/active` =
   `199-c` + the bounded implementation, tests, docs, and verification
   addendum listed below.

No schema migration, no DDL, no new dependency, no workflow/config/
template/CSS change, no UI change, and no runtime
auth/admission/accounting/forwarding/Redis behavior was modified. The
shared service/repository gained ONLY the opt-in `clear_notes` intent
(all other behavior and defaults preserved); ModelRouteService
CRUD/normalizer, the routing repository, the three extracted pure
validators, the registry/modules/profiles/adapter layer,
AuditRepository, and the CLI `routes` command are unchanged. Objectives
200-205 were not started.

## Allowed diff (implementation commit, 14 files)

Product (allowed paths only):

- `app/slaif_gateway/services/provider_route_configuration.py` — C3:
  `validate_merged_route_candidate` now receives the COMPLETE canonical
  streaming state (`supports_streaming` is a required keyword at all
  three call sites: preview, execute, creation) and reuses the EXISTING
  pure `resolve_server_module` (registry) plus the profile/binding
  parsers: every candidate must resolve to a supported server module for
  the provider's actual kind/slug/capabilities, failing safe with a
  fixed no-echo error on unknown/unresolvable modules. The completion
  contract (chat completions endpoint, `max_retries=0` zero-retry rule,
  profile availability in the SAME configured profile directory,
  public/upstream model identity) now applies to an EXPLICIT
  `completion_service` selector AND the implicit legacy profile binding
  (bindings.json `facial_scoring` -> `facial-scoring-v1`), and reviewed
  configurations that advertise streaming (route flag or
  `chat_completions.chat_streaming`) are refused, never silently
  stripped (the completion adapter refuses stream values other than
  `false`). Compatible/local/vLLM/upstream/video contracts keep their
  own endpoint rules (no global completion endpoint imposition). No
  adapter construction, credentials, or network. C1: the 199 typed
  clear delegates `notes=None` + `clear_notes=True` through the shared
  service (no direct pre-clear, no second audit, no nested commit).
- `app/slaif_gateway/services/provider_config_service.py` (C1 ONLY):
  `update_provider_config` gained opt-in `clear_notes: bool = False`
  with a pre-mutation contradiction refusal (notes + clear_notes) and
  delegation of the explicit intent; every other caller keeps the
  pre-existing default (`notes=None` means preserve).
- `app/slaif_gateway/db/repositories/provider_configs.py` (C1 ONLY):
  `update_provider_metadata` gained opt-in `clear_notes: bool = False`;
  `True` stores NULL within that same operation, the default keeps the
  historical None-means-preserve law for every other caller.
- `app/slaif_gateway/cli/providers.py` — C2: the SAME existing
  known-shape guards as `update` now apply to `providers add`
  `--display-name` / `--base-url` / `--notes` / `--reason` BEFORE any
  database access (fixed no-echo errors; optional creation reason and
  the HTTP confirmation law preserved; no credential-value option, no
  env-value lookup, no new sanitizer).

Tests (allowed paths only):

- `tests/unit/test_provider_route_configuration.py` — 118 -> 135
  pure-layer tests: C3 positives (explicit supported selector; implicit
  legacy binding; operator-directory implicit resolution) and negatives
  (unknown module without selector/binding; implicit wrong public
  model / upstream model / endpoint / retries; explicit AND implicit
  streaming flag and `chat_streaming` capability refusals;
  operator-directory missing profile); creation-candidate unknown
  module / valid legacy binding / streaming refusals; C1 clear-intent
  delegation (`notes=None` + `clear_notes=True`) and default
  None-preservation. Single import style completed (from-imports with
  dotted monkeypatch targets; the `prc` alias removed). Synthetic
  fixtures corrected to valid supported declarations: unregistered
  module/no-selector fakes became genuinely compatible providers or
  explicit/profile-mapped declarations; completion fixtures advertise
  no streaming (truthful chat flags).
- `tests/unit/test_cli_provider_route_configuration.py` — 31 -> 35
  actual-Typer tests: `providers add` canary refusals (notes/reason/
  display name/base URL) with the creation service NOT called and no
  canary echo, plus ordinary text/env-reference acceptance; the review
  fixture destination provider became a genuinely compatible provider
  for the pure module resolution.
- `tests/unit/test_provider_config_service.py` — 8 -> 10: the fake
  repository mirrors the real clear-intent law (no more
  set-every-non-None-None behavior), and the two narrow regressions
  prove explicit clear stores NULL with ONE audit (real old -> real
  new null) and default callers keep None-preservation.
- `tests/integration/test_cli_provider_route_configuration_postgres.py`
  — 24 -> 31 owned-PostgreSQL-16 tests (same owned-container
  discipline). RESTORED substantive clear oracle: `--clear-notes`
  stores NULL with one audit carrying real old text -> real new null
  while every sibling field survives; omitted notes preserve and
  ordinary replacement works; zero retries and env-reference names
  survive (existing proofs). NEW 199-c proofs: a forced LATE provider
  audit failure rolls back BOTH the clear and the sibling change with
  no orphan audit (updated row visible in the SAME transaction before
  the failure; retry succeeds and audits real old -> null); a known
  credential shape in `providers add --notes` is refused with zero
  rows/audits and no canary in output while ordinary text and safe
  env-variable NAMES store literally; an unregistered module-kind
  provider cannot back a NEW route (refused before write/audit); the
  implicit legacy binding creates a valid no-selector route with
  truthful no-streaming declarations while a wrong requested model and
  advertised streaming are refused with zero writes/audits; an
  explicit-selector route update advertising streaming is refused
  before any plan file; and the implicit binding resolves through the
  SAME configured `COMPLETION_SERVICE_PROFILE_DIR` operator directory
  (0600 file present: accepted; absent: refused with the fixed safe
  error). Fixture corrections within the module (no weakened
  accounting/privacy/concurrency checks): the completion fixtures
  advertise no streaming (`ZAP_CAPS` chat block `chat_streaming:
  false`; `routes add --no-streaming` for both completion routes), the
  provider-switch fixtures are genuinely compatible providers (the
  test asserts nothing about kind), and the two module-provider full-
  replacement documents keep the completion selector so the provider
  still resolves.

Docs (allowed paths only):

- `docs/cli-reference.md` — the 199 section corrected for 199-c:
  `--clear-notes` now describes the EXPLICIT working clear semantics
  (real old -> null in one audited operation; pre-existing callers keep
  the None-means-preserve default) replacing the 199-b no-op caveat;
  `providers add` gains the known-shape creation guards (known-shape
  protection, not universal sanitization); the candidate-validation
  statement covers complete pure server-module resolution, implicit
  legacy binding, and the no-advertised-streaming limit.
- `docs/cli-field-administration.md` — the 199 rows corrected to the
  199-c semantics (explicit clear, creation guards, module resolution
  + implicit binding + streaming limits in the execute revalidation).
- `docs/completion-services.md` — configuration-time validation
  statement extended: supported server-module resolution (unknown
  modules refused), implicit legacy binding with the SAME validation as
  an explicit selector, and the streaming non-support (refused, never
  silently stripped); configuration validation is not
  credential/model readiness.
- `docs/verification/2026-10-28-cli-provider-route-configuration.md`
  — APPENDED "199-c ADDENDUM" (the 199-a text and the 199-b addendum
  are unchanged); the addendum CORRECTS the two historical claims
  without editing the old text: (1) the 199-b no-op caveat — the
  stored column was NOT cleared, because the repository skipped
  `None`; root's own earlier inference that the None forward therefore
  cleared was incorrect; 199-c completes the operation with the
  explicit intent; (2) the 199-b too-broad creation claim — root's
  actual `_add_provider` + real create service probe accepted and
  stored a recognized synthetic `sk-proj-` canary in `providers add
  --notes` (redacted on safe output, but unguarded at storage/input);
  199-c covers the creation surface.

OAP: exact `oap/active` = `199-c` (5 bytes, no newline) and the
strategic order, both byte-verified unchanged at the implementation
head.

## Actual focused verification (this execution)

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python`
(Python 3.12) with `env -u DATABASE_URL -u TEST_DATABASE_URL`; no
ambient `DATABASE_URL` / foreign PG (the integration layer's owned
container is the only database); JUnit receipts under `/tmp/slaif199/`
(disposable). The genuine 199-b receipts (`b-unit-pure1.xml` 118,
`b-unit-cli1.xml` 31, `b-affected1.xml` 298, `pg-b.xml` 24,
`b-gov-inv-drift.xml` 37) were NOT rerun for formatting; the changed
code justifies the affected regressions below.

- Affected/touched suites, one run, after all 199-c changes: **330
  passed, 0 failed / 0 errors / 0 skipped**, exit 0
  (`c-affected.xml`): `test_chat_completion_route_capabilities` (29),
  `test_responses_route_capabilities` (57),
  `test_media_input_estimation` (36), `test_provider_config_service`
  (10 = 8 + 2 new), `test_model_route_service` (4), `test_cli_providers`
  (7), `test_cli_routes` (8), `test_provider_route_configuration` (135
  = 118 + 17 new), `test_cli_provider_route_configuration` (35 = 31 + 4
  new), `test_oap_governance` (9).
- Owned-PostgreSQL-16 integration module (owned disposable container,
  label-owner `slaif199a.*.owner`, loopback-only, tmpfs, alembic head;
  container removed on teardown, zero leftover containers): **31
  passed, 0 failed / 0 errors / 0 skipped**, exit 0 (`c-pg.xml`) — the
  24 199-b proofs plus the seven new 199-c proofs listed above.
- Governance/inventory/drift, one run (after the docs append): 37
  passed, 0 failed / 0 errors / 0 skipped, exit 0 (`c-gov.xml`):
  `test_oap_governance` (9), `test_documentation_inventory` (13),
  `test_documentation_contract_drift` (15) — the unchanged
  consumer-allowlist guard included.
- Gates: `ruff check app/ tests/` clean;
  `python3 scripts/check_documentation.py` -> `OK files=126`;
  `git diff --check` clean.

## Security and privacy statements

- Secret protection is KNOWN-SHAPE protection: recognized credential
  patterns are refused on new input (now including provider creation
  free-form fields) and redacted on safe reads; it is NOT universal
  content sanitization. `api_key_env_var` NAMES and structured fields
  are never masked; no credential VALUE is ever accepted, resolved, or
  printed. No canary appears in any new error, output, or log path.
- The clear operation is REAL on the 199 surface: NULL stored, ONE
  audit with real old -> real new values, full rollback on a late audit
  failure. The shared service/repository change is the opt-in typed
  intent only; every pre-existing caller (including the admin form
  path) keeps the None-means-preserve default.
- Configuration validation reuses the EXISTING pure module resolution,
  profile/binding parsers, and loaders: it is configuration validation,
  not credential, model, SMTP, or performance qualification. No real
  provider, client, SMTP, Redis, or network contact was made by this
  execution's evidence.

## Honest state and limitations

- Final-head CI is root-gated and its state is **PENDING** at this
  publication; the final new SELF must have all checks green before
  root merges. No CI result is claimed here.
- No full verification matrix, browser, or Docker Compose coverage was
  run for 199-c; the genuine 199-b passes stand as 199-b evidence and
  are not re-claimed.
- The 200-205 rows and the 205 full executable-only transcript remain
  outstanding. No 205/all-11-DoD or real-backend qualification claim.
- Plan files and JUnit receipts under `/tmp/slaif199/` are disposable
  execution state, not durable evidence.
