# Objective 197-a — effective key policy, safe lookup, bounded lazy-throttling CLI verification

Dated evidence for the effective-key-policy / safe-lookup / bounded
lazy-throttling CLI objective (197-a). This is a focused objective record,
not a full-matrix qualification, and not a release or
production-certification decision.

## Scope

Bounded CLI functionality built on existing services (no schema migration,
no new dependencies, no API/template/CSS changes, no runtime
forwarding/accounting/Redis changes):

- R1: dedicated audited `keys set-lazy-throttling` (wait/reject/clear)
  reusing the existing shared KeyService validator, write path, and audit
  row (caller-owned transaction; one audit row; only lazy metadata,
  `updated_at`, and the audit change).
- R2: configuration-only `keys policy effective` view (configured /
  effective / source per rate member, per-selected-window count
  semantics, inherited-rate-vs-unlimited-quota warning, lifetime quotas,
  stored lazy state, allow-lists, Responses/Codex profile identity, Redis
  configuration; no authentication, no state change).
- R3: safe lookup (`keys show` UUID or exact public key ID; full
  bearer-shaped input refused with a fixed safe error) and bounded
  complete paging (`keys list --owner-email` exact match, `--cohort-id` /
  `--status` before the limit, `--limit` max 200 + `--offset`, additive
  `paging` metadata, stable `created_at` + UUID tiebreaker).
- R4: configuration-only `keys policy explain-route` (key-state blockers
  first, allow-list vs enabled-route intersection, existing resolver law,
  base-request capability checks via the current pure enforcers with an
  empty payload, discovery separately authorized, 1000-route candidate
  bound preserved and disclosed).
- R5: shared safe outputs (new read-only inspection service projecting
  only known safe values; unknown/malformed/stale stored policy surfaces
  as fixed safe markers, never copied values; parity against the REAL
  `GatewayAuthService` proven in PostgreSQL).

The 196 typed configuration surfaces are reused unchanged; their evidence
(`2026-10-27-cli-key-policy.md`) is cited, not rerun.

## Layers and exact commands

Environment: `/tmp/slaif192-coding-venv` (Python 3.12, editable
project). `PYTHONPATH=app` for all runs. No ambient `DATABASE_URL`; the
integration layer runs against its own owned PostgreSQL 16 container only.

### New unit suites (pure layer, no DB)

```text
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_key_policy_inspection.py \
  tests/unit/test_cli_keys_effective_policy.py -p no:cacheprovider
# 65 passed (42 + 23; 0 skipped)
```

- 42 inspection-service cases: effective projection (inherit vs unlimited,
  per-member source, window counts, stored lazy state/source incl. valid
  reject = key-configured, over-ceiling wait = invalid-stored, Redis
  configuration view, quota unlimited/remaining), safe allow-list
  projection (None vs [] preserved, malformed provider member = fixed
  `invalid` marker with no echoed value), Responses profile (strict 196
  validator: unknown/stale-0162-v1 module pins = `unavailable` marker with
  no copied values; valid bound identity + validated grants; pin alone
  grants nothing), explain-route (key-state blockers reported first with
  no resolution for suspended/revoked/expired/fenced keys, endpoint
  canonicalization/aliases, discovery verdict, not-evaluated payload-
  dependent endpoints, allow-list intersection applying enabled provider
  + provider restriction + public matching law, typed resolver blockers,
  base-request capability enforcement incl. the nested
  `{"chat_completions": {"chat_text": false}}` block, safe resolution
  subset without provider configuration references, bound disclosure).
- 23 actual-CLI cases on the installed Typer app (faked runtimes):
  set-lazy-throttling flag conflicts (wait needs both bounds, reject/clear
  exclusive, ceiling pre-check with no write, reason required), effective
  / explain-route JSON shapes, list paging metadata (limit bound,
  has_more/next_offset), owner-email mutual exclusion, show public-key-ID
  resolution and bearer refusal (fixed message, no echo).

### Focused affected unit groups (regression)

```text
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_key_policy_inspection.py \
  tests/unit/test_cli_keys_effective_policy.py \
  tests/unit/test_cli_keys_status.py tests/unit/test_cli_keys_limits.py \
  tests/unit/test_key_rate_limit_policy_cli.py \
  tests/unit/test_rate_limit_policy.py tests/unit/test_endpoint_policy.py \
  tests/unit/test_route_resolution_service.py tests/unit/test_cli.py \
  tests/unit/test_cli_keys_create.py -p no:cacheprovider
# 135 passed (0 skipped), exit 0
```

Updated oracles (affected behavior only): `test_cli_keys_status.py`
(show now resolves UUID-or-public-key-ID references) and `test_cli.py`
(list JSON carries additive `paging` metadata).

### Owned-PostgreSQL-16 integration (real CLI entry path)

```text
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/integration/test_cli_key_effective_policy_postgres.py \
  -p no:cacheprovider
# 9 passed (0 skipped), exit 0
```

Fresh qualified owned fixture (unique `slaif197a-*` owner label,
postgres:16, 127.0.0.1 loopback bind, tmpfs data directory, identity
re-inspected BEFORE readiness/migration, cleanup removes only the exact
created container ID even on failure; verified no leftover container
after the run). `DATABASE_URL` is set to the exact owned fictional
database only; no ambient or foreign database, no real Redis, no provider
HTTP, no SMTP.

The 9 cases:

1. wait set / inspect / clear / out-of-range: one-per-10-seconds +
   concurrency 1 via the existing rate CLI, then `--mode wait 30/2`;
   effective view shows configured=effective=source key, `stored_state`
   wait-configured, source key; clear removes the stored policy; an
   over-ceiling wait fails (exit 2, fixed "operator ceiling" message)
   with NO change and NO extra audit; a subsequent `--mode reject` stores
   the canonical (cleared) policy and the effective view reports
   `stored_state: absent`. Only the waiting metadata + one audit row
   changed between snapshots (all other key columns, ledger, and
   reservation counts asserted unchanged).
2. Forced LATE audit failure: a monkeypatched `add_audit_log` hook for
   `update_key_lazy_throttling` verifies the metadata update is VISIBLE
   IN THE SAME TRANSACTION before raising; the CLI exits 1, the caller
   transaction rolls back (metadata identical to before), and no partial
   audit row persists.
3. Effective-policy parity against the REAL `GatewayAuthService`: a
   test-owned 0600 one-time secret file (CLI `--secret-output-file`),
   real Bearer authentication, then `build_rate_limit_policy` /
   `effective_lazy_throttling_policy` on the real authenticated context;
   the CLI effective view's rate/lazy/allow-list values match the real
   auth context exactly; `scope: configuration-only` and
   `status_note: null` are asserted so the view cannot read as
   authentication success.
4. Safe lookup and bounded complete paging: five keys with two TIED
   `created_at` timestamps paginate 2+2+1 via `--owner-email` +
   `--limit 2` + `--offset` with no duplicates or lost rows
   (`has_more`/`next_offset` exact, `next_offset` null at the end).
5. Exact public-key-ID lookup works; full bearer-shaped input is refused
   (fixed safe message present; the bearer string itself never echoed to
   stdout or stderr); unknown owner email fails with a fixed safe message
   (email not echoed).
6. Cohort/status filters apply BEFORE the limit (3 active in cohort A, 1
   suspended in cohort B; filtered page shapes exact).
7. Explain blockers with real route/provider fixtures: three allowed
   models with only one enabled Chat route (required example; the
   disabled-route models are repository-created because CLI create
   validation requires enabled routes for authored allow-lists);
   `resolved` (openai) with safe resolution subset and base-request
   capability supported; `model-route-disabled`; `model-not-allowed-for-
   key` for an unlisted model (the resolver's own ambiguity error is
   unreachable for distinct routes because the deterministic route-ID
   tiebreaker always differs — recorded honestly rather than faked);
   `route-capability-not-supported` with `chat_capability_not_supported`
   for a key allowed on the nested `chat_text: false` route; `/v1/models`
   = `discovery-separately-authorized` with `endpoint_allowed: false`;
   no provider base URL / env var / fake provider secret in any output.
8. Provider deny-all `[]` blocks with `provider-not-allowed-for-key` and
   empty candidate intersection; suspended / expired / fence-active keys
   report their key-state blocker first with `usable_for_requests: false`
   and no resolution (the fence row satisfies the real bound-shape check
   constraint).
9. Read-only inspection changes nothing: canary planted in the key's
   private metadata; effective / explain-route / show / list outputs all
   succeed; before/after snapshots of audit/ledger/reservation/one-time-
   secret counts and EVERY key column are identical; canary, HMAC
   secret, full bearer (prefix + full public ID), provider base URL, and
   fake provider secret are asserted absent from every output.

### Strategic WIP review fixes (honest provenance)

An independent root-side review of the first WIP inspection service
(`/tmp/slaif197-strategic-first-review.txt`; corrected probe
`/tmp/slaif197-root/corrected_probe.py`; receipt
`/home/janezp/codex-supervision/slaif-api-gateway/review-artifacts/cli-
feature-round/197-inspection-capability-and-status-review.json`) found six
demonstrated defects: (1) stale/unknown Responses module pins labeled
`bound` with copied private values — now the strict shared 196
validator/registry with fixed safe markers; (2) malformed provider
allow-list members echoed — now a fixed `invalid` marker with
None-vs-[] preserved; (3) expired/fenced keys explainable as resolved —
now the key-state blocker is reported first; (4) base-request capability
not enforced — now the current pure enforcers run on an empty payload;
(5) intersection ignoring provider enabled/restriction law — now the same
public matching law as the resolver; (6) valid stored reject reporting
source default — now key for any valid stored mode. All six have
permanent regressions in the 42-case unit suite. The root probes/receipts
are root-owned artifacts cited here, not re-run or claimed as this
execution's own runs.

### Gates

```text
/tmp/slaif192-coding-venv/bin/python -m ruff check <all changed .py>   # OK
git diff --check                                                        # OK
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python \
  scripts/check_documentation.py                                        # OK (files=123)
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_oap_governance.py tests/unit/test_documentation_inventory.py
# 22 passed (governance 9 + inventory 13), exit 0
```

## Security / privacy / accounting statements

- No authentication is performed or implied by the inspection surfaces;
  blocked key states cannot look like auth success (status note +
  key-state blocker asserted).
- No secrets, canaries, provider configuration references, raw metadata,
  or Settings/ORM dumps reach any 197 stdout/JSON/error (asserted in the
  unit and PG layers).
- No quota/accounting/Redis/forwarding behavior changed; waiting never
  relaxes hard quota, auth, security, or pricing.
- No real provider/model/client/SMTP contact; synthetic data only.

## Limitations

- No live Redis/HTTP lazy-runtime rerun (unchanged paths; source
  inspection + configuration parity prove the boundary).
- No full local unit/browser/HPC matrix rerun; the normal FINAL-head CI
  is the broad gate and was still pending at record time.
- No release, RC, production, security, or compliance claim follows.
