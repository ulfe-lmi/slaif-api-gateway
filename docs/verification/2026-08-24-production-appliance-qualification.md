# Objective 151 production-appliance qualification

Date: 2026-08-24 (Europe/Ljubljana)

Implementation head SHA: `91ebb9248911e7ee733274506a56d14199c319bc`
Report publication commit: `SELF`
Pull request: [#286](https://github.com/ulfe-lmi/slaif-api-gateway/pull/286)

This report records one successful disposable qualification of the production
Compose appliance and its composed Nginx boundary. It is RC-beta evidence only;
it is not a production certification, penetration test, compliance assessment,
SLA, or provider-invoice reconciliation claim.

## Run evidence

Command:

```text
.venv/bin/python scripts/production-qualification/run.py --keep
```

The runner used the permitted `sudo -n docker` fallback because the shell user
did not have direct Docker socket access. It created and later removed the
unique project `slaif-151-3132428-e31b28` and its named PostgreSQL volume.

| Phase | Result | Seconds |
| --- | --- | ---: |
| prepare | OK | 0.15 |
| TLS generation | OK | 0.41 |
| Compose config/build/start and health | OK | 29.87 |
| CLI operator/provider/route/pricing/key setup | OK | 23.46 |
| Chat and Responses normal/streaming | OK | 1.46 |
| Provider failures and disconnects | OK | 1.22 |
| Redis and timeout controls | OK | 3.57 |
| API/Nginx and PostgreSQL persistence | OK | 40.89 |
| PostgreSQL backup/restore | OK | 4.76 |
| Quota and key controls | OK | 7.34 |
| Privacy canary scan | OK | 7.62 |

All phases were mandatory and exited zero. No phase was skipped.

Migration head observed through a loader-backed Compose run:

```text
0023_module_provider_foundation (head)
```

Qualification image IDs:

```text
api sha256:4910e573d0c808d62aa834ad7c8aaadceae20f1aaa30c2c6e795e3e46d77078a
worker sha256:967bdaef873f7bea9a71c00744ea6d118f451b215d748e2d3e8f1b01ee4cc392
scheduler sha256:42b7e2c783961085db328af0c34bb2d883035cb845aa0d7bc9e35542ba4530ea
provider-double sha256:324ea7fcaebe92e7d7c441f82995ec2704c5196b3f5043b56f49cbdc08a540c1
nginx sha256:db35bfc6b2951e7f8a72db5db120288c127ffaeeb4a6d4b95a26fead017d5913
postgres sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685
redis sha256:7aec734b2bb298a1d769fd8729f13b8514a41bf90fcdd1f38ec52267fbaa8ee6
```

## Topology and scenarios

- PostgreSQL 16 and Redis 7 had no published host ports. PostgreSQL used the
  named `postgres_data` volume; Redis used protected mode plus a generated
  password and authenticated URL.
- API was attached to private `internal` and provider `egress` networks.
  Nginx was the only client boundary and served the generated short-lived TLS
  certificate. Streaming proxy buffering and cache were disabled.
- The async profile started the exact Celery worker and Beat application
  objects. Email delivery and scheduled reconciliation remained disabled.
- The CLI created an admin, owner, generic socket provider, model routes,
  explicit pricing, and gateway key. No dashboard shortcut or direct database
  metadata replacement was used for setup.
- Chat Completions and Responses succeeded through normal JSON and SSE paths.
  Provider authentication was observed by the separate socket double; the
  gateway response did not contain the generated completion canary.
- Provider HTTP error, malformed JSON, malformed SSE, incomplete SSE,
  timeout, client-abort, and Responses disconnect paths were exercised. Failed
  streaming paths did not emit a successful terminal marker or finalized
  success accounting.
- Redis stop/restart was exercised. Requests failed closed while Redis was
  stopped, did not reach the provider, and succeeded after authenticated Redis
  readiness returned.
- PostgreSQL-backed request, token, and cost quota crossings were rejected
  before provider forwarding. A key validity expiry and CLI revocation were
  both denied before provider forwarding.
- API and Nginx recreation plus PostgreSQL recreation preserved the usage
  ledger and gateway-key identity through the named volume. A custom-format
  PostgreSQL dump was restored into a separate disposable database and
  verified by row count.
- Logs and durable audit, usage, reservation, and key metadata were scanned for
  all generated request, completion, authorization, and secret canaries. No
  canary or secret was found. Generated runtime files were removed after the
  run and were not committed.

## Safety boundary

The run used no real OpenAI/OpenRouter credentials, no real upstream calls, no
real email, and no production or staging database. The provider was an
isolated local socket-level HTTP double on the Compose egress network. The
qualification does not establish production readiness, security certification,
regulatory compliance, high-availability behavior, or exact upstream billing.
