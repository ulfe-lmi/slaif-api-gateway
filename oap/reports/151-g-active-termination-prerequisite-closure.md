# OAP objective 151-g report

## Result

`OK`

The single fresh complete no-keep qualification run passed all 16 phases after
the implementation was frozen. It proved the active Responses-stream
prerequisites immediately before API termination, completed the real API
container kill/restart and documented CLI reconciliation path, and preserved
the accepted deterministic Chat concurrency evidence.

The exact disposable Compose project from the final JSON was
`slaif-151-4166413-bbd423`.

## Run and repository state

- Date: 2026-08-24
- Active order: `151-g`
- Activated order SHA: `2e921382aca850ad9bb8509f66a9936f75c5e7c1e68c9c6c83d4f32af349df38`
- Active selector SHA: `c4e2f9d97102e5fa6954b7b9e9cf4c583d5c42a40f67d4dd51aa5d22324d04bf`
- Implementation commit: `cb404b495d14b63fcf51ef6a2099fe55cb17b2ee`
- Implementation parent: `3002cebe2c3bd63b04c38259ec566a79a962bcc1`
- Qualification command: `env -u APP_ENV -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY ENABLE_EMAIL_DELIVERY=false .venv/bin/python scripts/production-qualification/run.py`
- Captured log: `/tmp/slaif-151-g-qualification.log`
- Report publication commit: SELF

The final JSON project token was mechanically validated against
`^slaif-151-[0-9]+-[0-9a-f]{6}$`. Before publication, extraction of every
`slaif-151-[0-9]+-[0-9a-f]+` token from this report produced exactly the single
final token above. No historical or truncated project token is present.

## Phase result

| Phase | Seconds | Status |
|---|---:|---|
| prepare | 0.14 | OK |
| tls | 0.29 | OK |
| compose | 29.48 | OK |
| operator-configuration | 29.05 | OK |
| async-worker-and-scheduler-liveness | 6.45 | OK |
| chat-and-responses | 2.19 | OK |
| provider-failures-and-disconnects | 3.34 | OK |
| redis-and-timeout-controls | 9.68 | OK |
| redis-concurrency | 9.21 | OK |
| api-termination-and-cli-reconciliation | 18.89 | OK |
| persistence | 40.09 | OK |
| backup-restore | 12.30 | OK |
| privacy-input-boundaries | 0.64 | OK |
| quota-and-key-controls | 7.91 | OK |
| admin-dashboard-session | 0.32 | OK |
| privacy | 36.75 | OK |

## Active termination evidence

The bounded `api_termination` object recorded:

- active status: `200`
- active request ID present: `true`
- active client thread alive immediately before kill: `true`
- active provider-forward delta: `1`
- active Redis slots: `1`
- active pending reservation present: `true`
- pending-before-kill correlation: `true`
- restart readiness: `true`
- recovery 503 count: `0`
- terminal reservation status: `expired`
- terminal accounting status: `failed`
- reserved counters cleared: `true`
- reconciliation audit present: `true`

The phase killed the actual API container, restarted API and NGINX, waited for
the HTTPS health boundary and Redis readiness, then invoked the documented
`slaif-gateway quota reconcile-expired-reservations` CLI path. The retained
Responses endpoint, provider, resolved model, and streaming facts were checked
before and after reconciliation. The bounded object contains no request ID,
body, key, URL, prompt, completion, or provider payload.

## Deterministic concurrency evidence

The accepted 151-f Chat concurrency semantics remained green:

- active stream and slot: `true`
- overlap status: `429`
- overlap error code: `concurrency_rate_limit_exceeded`
- overlap provider-forward delta: `0`
- overlap accounting unchanged: `true`
- original reservation pending and thread alive during overlap: `true`
- Redis slot released: `true`
- following request status: `200`

## Other qualification evidence

- Dashboard followed the authenticated redirect to exact `/admin` with HTTP
  `200`, a Secure cookie, and three scanned bodies.
- Positive Prometheus samples were present for all four exercised metric
  families.
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
state. Focused Ruff and unit tests passed before the run.

This is disposable qualification evidence, not a production certification,
release decision, security certification, compliance claim, provider-invoice
qualification, or SLA claim. PR #286 remains subject to strategic review and
the final report-head checks; the coding agent does not merge or enable
auto-merge.
