# OAP objective 151-i report

## Result

`OK`

The single fresh complete no-keep qualification run passed all 16 phases. It
proved the inspected non-allowlisted public HTTPS `/readyz` denial, all exact
loopback readiness lifecycle checkpoints, post-kill client termination and
provider-count stability, and the previously accepted accounting, concurrency,
reconciliation, persistence, restore, dashboard, metrics, quota, and privacy
boundaries.

The exact disposable Compose project from the final JSON was
`slaif-151-42631-713c6c`.

## Run and repository state

- Date: 2026-08-24
- Active order: `151-i`
- Activated order SHA: `06ddbc200c42a70dec58695892f1c84f05ee71e26f0412f95895908d971669dd`
- Active selector SHA: `485580f79ebb02a021ee05f117b391a9eb8c760f5c77b7def0862f7df943171f`
- Implementation commit: `e7673d6c17cf2d13b82144224897f5cdf96de94e`
- Implementation parent: `638760f59da1830154b46415a2708074b437dfaa`
- Qualification command: `env -u APP_ENV -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY ENABLE_EMAIL_DELIVERY=false .venv/bin/python scripts/production-qualification/run.py`
- Captured log: `/tmp/slaif-151-i-qualification.log`
- Report publication commit: SELF

The final JSON project token was mechanically validated against
`^slaif-151-[0-9]+-[0-9a-f]{6}$`. Before publication, extraction of every
`slaif-151-[0-9]+-[0-9a-f]+` token from this report produced exactly the single
final token above. No historical or truncated project token is present.

## Phase result

| Phase | Seconds | Status |
|---|---:|---|
| prepare | 0.15 | OK |
| tls | 0.19 | OK |
| compose | 33.69 | OK |
| operator-configuration | 26.65 | OK |
| async-worker-and-scheduler-liveness | 5.94 | OK |
| chat-and-responses | 2.11 | OK |
| provider-failures-and-disconnects | 2.28 | OK |
| redis-and-timeout-controls | 12.29 | OK |
| redis-concurrency | 9.08 | OK |
| api-termination-and-cli-reconciliation | 20.80 | OK |
| persistence | 47.32 | OK |
| backup-restore | 11.66 | OK |
| privacy-input-boundaries | 0.60 | OK |
| quota-and-key-controls | 8.07 | OK |
| admin-dashboard-session | 0.29 | OK |
| privacy | 36.66 | OK |

## Readiness evidence

The bounded `readiness` object recorded exact results for every named event:

- initial startup: HTTP `200`, `ok`, database/schema/Redis `ok`, four
  consecutive successes;
- Redis outage: HTTP `503`, `not_ready`, Redis `error`;
- Redis recovery: HTTP `200`, exact ready facts, four consecutive successes;
- API restart: HTTP `200`, exact ready facts, four consecutive successes;
- API recreation: HTTP `200`, exact ready facts, four consecutive successes;
- PostgreSQL/API recreation: HTTP `200`, exact ready facts, four consecutive
  successes;
- public HTTPS `/readyz` denial: `true`.

The public result came from the provider-double container after both exact
Compose containers were connected to a disposable `198.18.0.0/15` bridge.
The probe destination was the inspected NGINX IPv4 address, and only HTTP 403
or 404 was accepted. The report contains no container IDs, network names, IP
addresses, URLs, headers, certificates, bodies, or command output.

## Interrupted client and accounting evidence

The bounded `api_termination` object recorded:

- active status: `200`
- active provider-forward delta: `1`
- active Redis slots: `1`
- pending-before-kill correlation: `true`
- client thread terminated after API kill: `true`
- provider count stable after kill and restart: `true`
- API restart readiness: `true`
- terminal reservation status: `expired`
- terminal accounting status: `failed`
- reserved counters cleared: `true`
- reconciliation audit present: `true`

The existing documented CLI reconciliation path remained the mechanism used
after the actual API container kill. No request ID or response content is
included in bounded evidence.

## Preserved qualification evidence

- Deterministic Chat overlap: HTTP `429`, exact code
  `concurrency_rate_limit_exceeded`, zero overlap provider-forward delta,
  unchanged accounting, released Redis slot, and following HTTP `200`.
- Dashboard: exact `/admin` landing, HTTP `200`, redirect followed, Secure
  cookie, three scanned bodies.
- Positive Prometheus samples: all four exercised metric families present.
- Backup/restore counts matched: `gateway_keys=2` and `usage_ledger=15` in
  both source and restored databases.
- Automatic cleanup reported no labeled containers, networks, volumes, or
  runtime directory.

An independent post-run audit of the exact final project found:

```text
containers=0
networks=0
volumes=0
runtime_exists=false
```

## Safety and boundary

The run used disposable PostgreSQL and Redis state, the isolated qualification
provider double, generated credentials and canaries, and disabled email
delivery. It made no real OpenAI/OpenRouter calls, sent no real email, used no
production or staging database, printed no secrets, and modified no production
state. Docker command compatibility preflight, Ruff, and focused unit tests
passed before the run.

This is disposable qualification evidence, not a production certification,
release decision, security certification, compliance claim, provider-invoice
qualification, or SLA claim. PR #286 remains subject to strategic review; the
coding agent does not merge or enable auto-merge.
