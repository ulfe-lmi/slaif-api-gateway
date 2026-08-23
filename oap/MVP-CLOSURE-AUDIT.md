# SLAIF API Gateway MVP Closure Audit

Audited main SHA: `1d357c497c56358c3c5e72e955ea4915d7221563`
Audit date: 2026-08-23
Open non-Dependabot PRs: none (2 Dependabot dependency bumps only)

---

## 1. RC2-Required Matrix Status

All 27 `RC2_REQUIRED_IMPLEMENTED` rows have implementation code and deterministic
test coverage on main. No `RC2_REQUIRED_MISSING` rows remain per
`docs/rc2-feature-scope.md`.

## 2. Evidence Classification

| Capability | Classification | Basis |
|---|---|---|
| Chat Completions non-streaming | `IMPLEMENTED_AND_MOCK_E2E_PROVEN` | Unit + integration + mocked official-client E2E |
| Chat Completions streaming | `IMPLEMENTED_AND_MOCK_E2E_PROVEN` | Same |
| Chat streaming live-burn | `IMPLEMENTED_WITH_INTEGRATION_TESTS` | Unit + integration; no real-provider stream test |
| Chat image/file/audio input | `IMPLEMENTED_AND_MOCK_E2E_PROVEN` | Unit + mocked E2E |
| Responses text output | `IMPLEMENTED_AND_MOCK_E2E_PROVEN` | Unit + integration + mocked E2E |
| Responses Codex envelope/tools/replay | `IMPLEMENTED_AND_REAL_E2E_PROVEN` | Qwen/vLLM real-provider qualification (022-f/023-b) |
| External-tool fenced web_search | `IMPLEMENTED_AND_MOCK_E2E_PROVEN` | Unit/integration/mocked; explicitly no real-provider claim |
| GET /v1/models | `IMPLEMENTED_AND_REAL_E2E_PROVEN` | Exercised in Qwen live run and ad-hoc gateway tests |
| Embeddings | `IMPLEMENTED_WITH_INTEGRATION_TESTS` | Unit + integration; mocked official client |
| Realtime client_secrets | `IMPLEMENTED_WITH_INTEGRATION_TESTS` | Bounded slice; no live session proof |
| Audio endpoints (speech/transcriptions) | `IMPLEMENTED_WITH_INTEGRATION_TESTS` | Unit + integration; no real-provider audio call |

## 3. Real-vs-Mock Evidence Distinction

### Real-provider evidence that exists

| Provider | Protocol | Evidence source | Scope |
|---|---|---|---|
| Qwen via vLLM (generic openai_compatible) | Responses (Codex profile) | OAP 022-f / 023-b immutable reports | Codex CLI → SLAIF → vLLM: hello, file-marker turn, vision image ID; accounting proved |
| OpenRouter (ad-hoc, not in OAP reports) | Chat + Responses | Session smoke tests (2026-08-22) | Nemotron/Kimi/Luna/Terra/Sol HELLO through gateway with ledger entries |
| OpenAI Pro (ad-hoc) | Responses non-streaming | Session smoke tests | Luna/Terra/Sol HELLO through gateway; streaming fails due to validator gap |

### Real-provider evidence that does NOT exist

- OpenAI adapter against api.openai.com through SLAIF with accounting finalization
- OpenRouter adapter against openrouter.ai/api through SLAIF recorded in immutable OAP reports
- Streaming SSE through a real hosted provider (OpenAI/OpenRouter) end-to-end with usage finalization
- Real-provider tool-use roundtrip (non-Qwen)

## 4. Production Deployment Status: NOT BOOTABLE AS DOCUMENTED

`docker-compose.production.yml` has these confirmed gaps:

1. **Missing required secrets**: The API container receives only `database_url`.
   It does NOT receive `TOKEN_HMAC_SECRET_V1`, `ADMIN_SESSION_SECRET`, or
   `ONE_TIME_SECRET_ENCRYPTION_KEY`. In `APP_ENV=production`, config validation
   raises on all three (`config.py` `_validate_production_secret`). Therefore
   `docker compose -f docker-compose.production.yml up -d` will start the API
   container but the application will fail closed at startup.
2. **No TLS certificate mount**: `nginx/production.conf` references
   `/etc/nginx/certs/fullchain.pem` and `/etc/nginx/certs/privkey.pem` but the
   compose file provides no volume mount for those paths. Nginx will fail to
   start.
3. **No provider credentials provisioned**: Neither `OPENROUTER_API_KEY` nor
   `OPENAI_UPSTREAM_API_KEY` reaches the API container. Provider calls will
   fail with `missing_provider_api_key`.
4. **No migration job**: Alembic migrations are not run by any service in the
   production profile. A fresh database will lack tables.
5. **No health check on API service** in the production profile.

These findings mean the documented deployment command does not produce a
functioning gateway. This is confirmed by code inspection of
`config.py` validation logic and `docker-compose.production.yml`; it has not
been tested empirically because the failure is deterministic from code reading.

## 5. Worker/Scheduler Packaging Discrepancy

The development Compose deploys `worker` (Celery) and `scheduler` (Celery Beat).
The production profile deploys neither.

Reconciliation is claimed as `Implemented` in the compatibility matrix with the
note "Celery/Celery Beat can be explicitly enabled". Email delivery uses Celery.
Neither is stated as RC2-required. However:

- Without worker/scheduler, reconciliation must be triggered manually via CLI.
- Email key delivery is unavailable.
- The product contract does not require scheduled reconciliation as Current;
  it says it "can be explicitly enabled."

Classification: **documentation/packaging inconsistency**, not an MVP blocker.
Resolution: either add optional worker/scheduler to production profile with
clear opt-in, or state explicitly in deployment docs that they are not included
and reconciliation is manual-only in this profile.

## 6. Operator Journey Status

The clean-clone demo (134-a) used the development Compose profile, not the
production profile. The journey was demonstrated with mocked providers plus one
real OpenRouter call. The journey itself (admin bootstrap → provider → route →
pricing → key → request → accounting → revoke) is implemented and exercised.

## 7. Accounting/Failure Path Status

Extensive unit and PostgreSQL integration coverage exists for reservation,
finalization, missing usage, stale reservations, concurrent budget, fence hold,
reconciliation, and live-burn interruption. These are deterministic mock-based
tests. No real-provider failure-path scenarios have been exercised.

## 8. Privacy/Security Negative Test Status

Content-minimization negative tests exist at unit/integration level. Security
negative tests cover auth, policy fail-closed, CSRF, SSRF, headers. These are
deterministic and adequate for their claims. The audit correctly identifies
that retention/anonymization scheduling lacks independent enforcement.

## 9. Detected Stubs / Documentation-Only Claims

None found beyond the known limitations already documented. The codebase does
not contain placeholder implementations masquerading as complete features.

## 10. Documentation/Code Contradictions

1. `docs/deployment-production.md` implies `docker compose up -d` produces a
   working deployment. Code inspection proves it cannot boot due to missing
   secrets and TLS mounts.
2. Compatibility matrix says reconciliation "can be explicitly enabled" via
   Celery but production profile omits Celery entirely without stating this.

## 11. Remaining Work Dependency Graph

```
139-a: Fix production Compose (secrets, TLS mount, migration, provider keys, health)
    ↓
140-a: Clean-host production boot proof + real-client vertical (OpenAI/OpenRouter)
    ↓
141-a: Worker/scheduler packaging decision + documentation truth pass
    ↓
MVP closure gate re-audit
```

## 12. Explicitly Deferred / Non-Goal List (NOT MVP blockers)

Per normative documents, the following remain outside MVP closure:

- Full OpenAI API parity
- `/v1/files`, image-generation, batch, vector stores
- Every Responses hosted-tool family beyond fenced web_search
- MCP/connectors, code interpreter, computer use
- Background Responses, cancel/list
- Full Realtime WebSocket/SIP surface
- Native Anthropic API
- Multi-organization tenancy, tenant isolation, SSO/SCIM, MFA
- Enterprise RBAC, enterprise SLA/support
- Formal penetration testing, SOC/ISO certification
- Regulatory/compliance certification
- Invoice-grade billing
- Internet-scale performance claims
- Automated retention/anonymization enforcement (risk-accepted)

## 13. Separate Completion Estimates

| Area | Estimate | Basis |
|---|---|---|
| Feature implementation | 0% remaining | All 27 RC2 rows implemented |
| Integration evidence | ~95% complete | Extensive deterministic coverage exists |
| Real-provider evidence | ~40% complete | Qwen proven; OpenAI/OpenRouter streaming/failure paths not |
| Deployment reproducibility | ~30% complete | Dev profile works; production profile cannot boot |
| SLAIF demonstrator readiness | ~70% complete | Journey works on dev; not on production profile |
| Broader production readiness | Deferred | Explicitly out of MVP scope |
