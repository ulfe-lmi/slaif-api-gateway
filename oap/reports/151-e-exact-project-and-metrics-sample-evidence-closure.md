# OAP report — 151-e exact project and metrics sample evidence closure

Report publication commit: SELF

Date: 2026-08-24 (Europe/Ljubljana)

Status: **QUALIFICATION PASS — evidence correlation closed; no production-certification claim**

Objective 151-e preserves the accepted 151-d production-appliance repairs and
closes only three evidence defects: exact project/cleanup correlation,
positive exercised Prometheus samples, and inclusion of the authenticated
dashboard landing page in privacy scanning. This report is the single
immutable 151-e report. It is disposable RC-beta qualification evidence, not
production readiness, security, compliance, SLA, provider-invoice, or real
upstream deployment certification.

## Git and OAP evidence

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR: `#286`, branch `oap/151-production-appliance-closure`, open, no auto-merge
- Base recorded by the activated order: `main @ ce0cf95685796477685a3aab6edacb39def6c27b`
- Implementation head: `87b3cfb6699d85a03d889bf5fab9fec7628bb6d3`
- Implementation head parent: `d362439e132275833f0fe4e963ac9af7497e01c6`
- Activated order: `oap/orders/151-e-exact-project-and-metrics-sample-evidence-closure.md`
- Active pointer: `oap/active` contains exactly `151-e\n`
- The report publication commit has the implementation head as its first
  parent and changes only this report path.

The implementation commit changes only the five allowlisted paths:
`scripts/production-qualification/run.py`,
`tests/unit/test_production_compose_contract.py`,
`docs/verification/2026-08-24-production-appliance-qualification.md`,
`oap/orders/151-e-exact-project-and-metrics-sample-evidence-closure.md`, and
`oap/active`.

## Fresh final no-keep qualification

Exact command, with inherited provider/database/test variables removed:

```text
env -u APP_ENV -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS \
  -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY \
  ENABLE_EMAIL_DELIVERY=false \
  .venv/bin/python scripts/production-qualification/run.py
```

The first post-change attempt was not used as final evidence: its existing
Redis-concurrency phase received HTTP 200 where the harness expected 429/503.
It cleaned up successfully. A fresh rerun then passed every phase and produced
the final JSON used below.

The exact `project` value was parsed directly from that final JSON, without
manual retyping:

```text
slaif-151-4043410-43784
```

All 16 phases passed:

| Phase | Seconds | Result |
| --- | ---: | --- |
| prepare | 0.15 | OK |
| tls | 0.65 | OK |
| compose | 29.25 | OK |
| operator-configuration | 27.06 | OK |
| async-worker-and-scheduler-liveness | 5.98 | OK |
| chat-and-responses | 2.91 | OK |
| provider-failures-and-disconnects | 2.29 | OK |
| redis-and-timeout-controls | 8.66 | OK |
| redis-concurrency | 8.42 | OK |
| api-termination-and-cli-reconciliation | 15.54 | OK |
| persistence | 39.75 | OK |
| backup-restore | 12.29 | OK |
| privacy-input-boundaries | 0.98 | OK |
| quota-and-key-controls | 7.43 | OK |
| admin-dashboard-session | 0.34 | OK |
| privacy | 36.43 | OK |

## Bounded evidence

### Prometheus samples

The real authorized exposition body was parsed after the in-container
loopback request. HELP/TYPE metadata, `_created` samples, zero values,
non-finite values, malformed lines, and unrelated families were excluded.
The final JSON emitted only these bounded booleans:

```json
{
  "gateway_cost_eur_total": true,
  "gateway_http_requests_total": true,
  "gateway_provider_requests_total": true,
  "gateway_tokens_total": true
}
```

The public Nginx `/metrics` route remained denied and the unallowlisted host
request to the API diagnostic endpoint remained HTTP 403. The qualification
override continued to allow metrics only from API-container `127.0.0.1`.
The actual exposition body was scanned with logs, dashboard bodies, provider
state, and database metadata for every generated canary and secret; no
generated value was found. No exposition body, labels, URLs, prompts, models,
or secrets were emitted as evidence.

### Dashboard and privacy

The normal HTTPS client followed the real login redirect to the exact `/admin`
landing path and received HTTP 200. The bounded final JSON recorded:

```json
{
  "final_path": "/admin",
  "final_status": 200,
  "redirect_followed": true,
  "secure_cookie": true,
  "scanned_body_count": 3
}
```

The three scanned bodies were the authenticated landing page, usage page, and
audit page. Their HTML was held only for the in-process privacy scan and was
not emitted or persisted as report evidence.

### Exact cleanup correlation

The final JSON's exact project string above was used as the input to an
independent Docker audit. It found:

```json
{
  "containers": 0,
  "networks": 0,
  "volumes": 0,
  "runtime": false
}
```

The qualification's own cleanup object independently reported all cleanup
booleans true, empty remaining network/volume lists, and no runtime directory.
The independent checks used the complete machine-parsed string and exact
`.qualification-runtime-slaif-151-4043410-43784` path; no prefix or visually
copied/truncated identifier was used.

## Restore, accounting, and privacy evidence

The final qualification restore counts matched exactly:

```text
gateway_keys=2
usage_ledger=15
```

The interrupted streamed request retained
`provider=qualification-double`, `resolved_model=qualification-model`, and
`streaming=true`; reservation counters were cleared and reconciliation audit
metadata was present. Normal, failure, expiration, quota, persistence, and
key-control phases all passed.

No real OpenAI/OpenRouter request or email was sent. The exposed inherited
provider credential was not enumerated, printed, validated, or reused; all
relevant commands explicitly unset provider variables. No production,
staging, shared, or remotely managed database was touched.

## Verification and final-head checks

- `git diff --check`: passed
- Ruff on changed Python files and focused tests: passed
- Focused production contract and positive-sample tests: 6 passed
- Fresh final no-keep qualification: 16/16 phases passed
- Exact project independent cleanup: 0 containers, 0 networks, 0 volumes,
  runtime absent
- PR #286 final report head: all required checks successful, including Unit,
  lint, and migration head; PostgreSQL integration; OpenAI-compatible E2E;
  Playwright; Docker Compose; documentation hygiene; Analyze Python;
  Analyze JavaScript/TypeScript; and CodeQL.

No merge, release, deployment, auto-merge, credential rotation, or
production-certification action was taken.
