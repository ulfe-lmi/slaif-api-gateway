# OAP Objective 197-a — final report: effective key policy, safe lookup, bounded lazy throttling in CLI

Work order: `oap/orders/197-a-effective-key-policy-and-waiting.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `197-a` (5 bytes, no trailing newline); order sha256
`ee0540b8254088909b66b9e4d35c785e0a85ceda95784b8221f531b560a6b75d`,
verified before and after committing).
Branch: `oap/197-effective-key-policy-and-waiting`; base: `main`
`6f6bc6fa7dc2aa9bb21ee2b0bc04f913e5d8c25c` (verified origin/main at
branch creation; unchanged at publication).
PR mode: CREATE_NEW_PR — unique PR #353,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/353, base `main`,
title "Explain effective key policy and expose bounded lazy throttling
in CLI". The coding agent never merges; no auto-merge is enabled; root
reviews independently and guard-merges.

Implementation head SHA: 22b247dfa79c9fcb3fac8b528cfa3e86b54aea79
Report publication commit: SELF

## Predecessor state (unchanged)

Objective 196 is TERMINAL: unique PR #352 merged 2026-10-28 as
`6f6bc6fa7dc2aa9bb21ee2b0bc04f913e5d8c25c`; all final-head checks and
merged-main checks succeeded as verified by root; the 196-a/196-b/196-c
orders and immutable reports are untouched. The only other open PR at
publication is the unrelated Dependabot PR #319 (preserved). Objectives
198-205 remain INERT; no later stage was started.

## Implementation commit (this round)

1. `22b247dfa79c9fcb3fac8b528cfa3e86b54aea79` — "Explain effective key
   policy and expose bounded lazy throttling in CLI": the strategic
   order (bytes verified unchanged, sha256 above) + exact
   `oap/active` = `197-a` + the bounded implementation, tests, docs,
   and verification record listed below.

No other product path, dependency, workflow, config, schema, migration,
model, or template was changed; no runtime auth/admission/accounting/
Redis/forwarding behavior was modified; no 198-205 feature was started.

## Allowed diff (implementation commit, 15 files)

Product (allowed paths only):

- `app/slaif_gateway/services/key_policy_inspection.py` (NEW) — read-only
  configuration-only inspection: `build_inspection_key` (safe
  AuthenticatedGatewayKey DTO mirroring GatewayAuthService derivation,
  NO authentication), `build_key_policy_inspection` (configured /
  effective / source per rate member with per-selected-window count
  semantics, inherited-rate-vs-unlimited-quota warning, lifetime quotas
  (null = unlimited), stored lazy state/source, allow-lists with
  explicit provider states, strict-196-validated Responses/Codex
  profile, Redis configuration view, key status_note), and
  `explain_model_route_access` (key-state blockers first, stable
  endpoint alias canonicalization, discovery separately authorized,
  payload-dependent endpoints not-evaluated, allow-list vs enabled-route
  intersection applying enabled provider + provider restriction + the
  public `matches_model_route` law, existing RouteResolutionService
  typed blockers, base-request capability enforcement via the current
  pure enforcers on an empty payload, safe resolution subset, and the
  1000-route candidate bound preserved and disclosed).
- `app/slaif_gateway/cli/keys.py` — new commands `keys
  set-lazy-throttling` (wait/reject/clear; both positive bounds within
  operator ceilings for wait; reject bounds validated-but-inactive;
  reason required; existing shared input/service in a caller-owned
  transaction), `keys policy effective`, and `keys policy explain-
  route`; `keys list` gains exact `--owner-email`, `--offset`, a
  200-row limit bound, and additive `paging` metadata; `keys show`
  accepts UUID or exact public key ID with bearer-shaped input refused
  (fixed safe error, no echo); additive `lazy_throttling_policy` in the
  management result dict; a read-only inspection runtime that
  bootstraps the configured Codex profile like 196.
- `app/slaif_gateway/services/endpoint_policy.py` — additive only:
  `_ALIAS_TO_CANONICAL_ENDPOINT` (derived from the existing alias
  table) + `canonical_endpoint_id(value)`.
- `app/slaif_gateway/db/repositories/keys.py` — `list_gateway_keys`
  ordering gains the stable `id.desc()` UUID tiebreaker after
  `created_at.desc()` (only caller: the CLI).

Tests (allowed paths only):

- `tests/unit/test_key_policy_inspection.py` (NEW, 42 cases) —
  effective projection, safe allow-list/provider markers, strict
  Responses profile (unknown/stale-0162-v1 pins = unavailable marker,
  no copied values), explain-route key-state blockers first,
  intersection law, typed resolver blockers, base-request capability
  enforcement (nested `{"chat_completions": {"chat_text": false}}`),
  safe resolution subset, bound disclosure. Includes the six permanent
  regressions from the strategic WIP review (below).
- `tests/unit/test_cli_keys_effective_policy.py` (NEW, 23 cases) —
  actual installed Typer app with faked runtimes: flag conflicts,
  ceiling pre-check, JSON shapes, paging metadata, owner-email mutual
  exclusion, public-key-ID lookup, bearer refusal (no echo).
- `tests/integration/test_cli_key_effective_policy_postgres.py` (NEW,
  9 cases) — real owned PostgreSQL 16 + real CLI entry path (see
  verification record).
- `tests/unit/test_cli_keys_status.py` / `tests/unit/test_cli.py` —
  narrow oracle updates for the affected behavior only (show reference
  resolution; additive list paging metadata).

Docs (allowed paths only):

- `docs/cli-reference.md` — command block, the implemented
  set-lazy-throttling / policy effective / policy explain-route
  semantics (replacing the deferred-setter paragraph), safe lookup and
  bounded paging, and the complete command inventory (kept in sync with
  Typer registration).
- `docs/cli-field-administration.md` — new "Implemented in objective
  197" table; the 197 row removed from "Proposed" (198-205 stay); the
  196 lazy row updated (dedicated CLI command now exists; file path
  unchanged).
- `docs/verification/2026-10-28-cli-effective-key-policy.md` (NEW) +
  `docs/verification/README.md` index entry.

OAP: unchanged strategic order + exact `oap/active` bytes (committed),
plus this report. No root strategic plan/audit/timing files in the PR.

## Actual focused verification (this execution)

Environment: `/tmp/slaif192-coding-venv` (Python 3.12); `PYTHONPATH=app`;
no ambient `DATABASE_URL` (the integration layer's owned container is
the only database).

- New unit suites: 65 passed (42 + 23), 0 skipped, exit 0.
- Focused affected unit groups (10 files, incl. the 65 new + the two
  updated oracles + status/limits/rate-limit/endpoint-policy/route-
  resolution/cli/create suites): 135 passed, 0 skipped, exit 0
  (JUnit `/tmp/slaif197/unit-focused.xml`).
- Owned-PostgreSQL-16 integration module (real CLI entry path):
  9 passed, 0 skipped, exit 0 (final JUnit
  `/tmp/slaif197/integration-4.xml`; ~17s). Fresh qualified owned
  fixture: unique `slaif197a-*` owner label, postgres:16, 127.0.0.1
  loopback, tmpfs data directory, identity re-inspected BEFORE
  readiness/migration, cleanup removes only the exact created container
  ID (verified no leftover container after the run). The cases cover:
  wait set/inspect/clear with only lazy metadata + one audit changed;
  over-ceiling wait failing (exit 2, fixed message) with NO change and
  NO extra audit; forced LATE audit failure with the in-transaction
  hook assertion and caller-transaction rollback (no partial audit);
  effective-policy parity against the REAL GatewayAuthService via a
  test-owned 0600 one-time secret file; tied-timestamp pagination
  (2+2+1, no duplicates/lost rows); public-key-ID lookup + bearer
  refusal + unknown-email safe errors; cohort/status filters before the
  limit; explain blockers (resolved with safe subset, model-route-
  disabled, model-not-allowed-for-key, route-capability-not-supported
  with `chat_capability_not_supported`, discovery separately
  authorized) with no provider configuration references in output;
  provider deny-all `[]`, suspended/expired/fence-active key-state
  blockers first; read-only before/after full-state snapshots with
  canary/HMAC/full-bearer/provider-secret absence asserted in every
  output.
- Gates: Ruff on all changed Python — OK; `git diff --check` — OK;
  `scripts/check_documentation.py` — OK (124 files);
  `tests/unit/test_oap_governance.py` +
  `tests/unit/test_documentation_inventory.py` — 22 passed, exit 0.

CI: the normal FINAL-head CI on the report head is the broad gate and
was still PENDING at publication; no full local unit/browser/HPC matrix
rerun was performed (skipped/pending items are not passes). Root
independently monitors final-head CI and may activate a same-PR
continuation for bounded test-scope fixes if any scoped failure
appears.

## Security / privacy / accounting statements

- No authentication is performed or implied by any new surface; blocked
  key states cannot look like authentication success (status note and
  key-state blocker asserted in PG).
- No secrets, canaries, provider configuration references (base URLs,
  API-key env vars), raw metadata, or Settings/ORM dumps reach any 197
  stdout/JSON/error (asserted in the unit and PG layers); full
  bearer-shaped input is refused and never echoed.
- No quota/accounting/Redis/forwarding behavior changed; waiting never
  relaxes hard quota, auth, security, or pricing; the setter changes
  only lazy metadata, updated_at, and one audit row (proven).
- No real provider/model/client/SMTP contact; synthetic data only.

## Strategic WIP review (honest provenance)

An independent root-side review of the first WIP inspection service
(`/tmp/slaif197-strategic-first-review.txt`) found six demonstrated
defects before final handoff; all six were repaired within the allowed
paths with permanent unit regressions: (1) unknown/stale-0162-v1
Responses module pins were labeled `bound` with private canary values
copied — now the strict shared 196 validator/registry with fixed safe
`invalid`/`unavailable` markers; (2) malformed provider allow-list
members were echoed via `str(dict)` — now a fixed `invalid` marker with
legitimate None-vs-[] preserved; (3) expired/fenced keys were explainable
as `resolved` — now the known key-state blocker is reported first (no
authentication faked); (4) base-request capabilities were not enforced
— now the current pure runtime enforcers run on an empty payload (Chat
text / Responses mandatory text); (5) the allow-list intersection ignored
the enabled-provider/provider-restriction law — now the same public
matching law as the resolver (rank not shadowed, runtime resolver
untouched); (6) a valid stored `reject` reported source `default` — now
`key` for ANY valid stored mode, `default` only for absent/invalid.
Root receipt: `/home/janezp/codex-supervision/slaif-api-gateway/review-
artifacts/cli-feature-round/197-inspection-capability-and-status-review.
json`; corrected probe `/tmp/slaif197-root/corrected_probe.py`. These
probes/receipts are root-owned artifacts cited for provenance; they are
not claimed as this execution's own runs.

## Limitations

- No live Redis/HTTP lazy-runtime rerun (paths unchanged; source
  inspection + configuration parity prove the boundary).
- The resolver's `AmbiguousRouteError` is unreachable for distinct
  routes (the deterministic route-ID tiebreaker always differs); the
  integration layer records the honest `model-not-allowed-for-key`
  behavior instead of faking ambiguity.
- No full local matrix; final-head CI pending at publication.
- No release, RC, production, security, or compliance claim follows.
