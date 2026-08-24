# OAP objective 151-f report

## Result

`FAIL`

This report records the one fresh complete no-keep qualification run required
by objective 151-f. The run was executed after implementation freeze at
`27f63601f6425eee5d6df9223b5f7f00cfac16b4`, whose first parent is the accepted
151-e report commit `958f892d767baa579ef3fa67d90fb39e82e330d3`. The run did not
establish production-appliance qualification closure because
`api-termination-and-cli-reconciliation` failed. No whole-matrix rerun was
performed after that failure.

The exact disposable Compose project from the final JSON was
`slaif-151-4088816-f5eea6`.

## Run and repository state

- Date: 2026-08-24
- Active order: `151-f`
- Activated order SHA: `2b2b2ed3d6d7926bc725297511520c9418f562707c8756fa9ce61dff02c882aa`
- Implementation commit: `27f63601f6425eee5d6df9223b5f7f00cfac16b4`
- Qualification command: `env -u APP_ENV -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY ENABLE_EMAIL_DELIVERY=false .venv/bin/python scripts/production-qualification/run.py`
- Captured log: `/tmp/slaif-151-f-qualification.log`
- Report publication commit: SELF

The final JSON project token was mechanically validated against
`^slaif-151-[0-9]+-[0-9a-f]{6}$`. Before publication, extraction of every
`slaif-151-[0-9]+-[0-9a-f]+` token from this report produced exactly the single
final token above; no historical or truncated project token is present.

## Phase result

| Phase | Seconds | Status |
|---|---:|---|
| prepare | 0.15 | OK |
| tls | 0.33 | OK |
| compose | 40.02 | OK |
| operator-configuration | 27.37 | OK |
| async-worker-and-scheduler-liveness | 6.13 | OK |
| chat-and-responses | 2.65 | OK |
| provider-failures-and-disconnects | 2.94 | OK |
| redis-and-timeout-controls | 9.08 | OK |
| redis-concurrency | 9.12 | OK |
| api-termination-and-cli-reconciliation | 10.73 | FAIL |

Failure: the API-termination phase reported that its deliberately interrupted
stream did not have a persisted reservation before API termination. The
failure is retained as qualification evidence; it is not reclassified as a
pass and no request identifier is reproduced here.

## Deterministic Redis-concurrency evidence

The new concurrency phase itself passed its bounded assertions:

- active slot: `true`
- active stream: `true`
- original thread alive during overlap: `true`
- original reservation pending during overlap: `true`
- overlap status: `429`
- overlap error code: `concurrency_rate_limit_exceeded`
- overlap provider-forward delta: `0`
- overlap accounting unchanged: `true`
- bounded Redis-recovery 503 retries: `0`
- released slot: `true`
- following request status: `200`

The final JSON contains only bounded concurrency evidence. It does not expose
response bodies, gateway request identifiers, gateway keys, provider keys, or
provider URLs.

## Cleanup and safety

The run's cleanup object reported success for containers, networks, volumes,
and runtime state, with no remaining labeled networks or volumes. An
independent post-run audit of the exact final project found:

```text
containers=0
networks=0
volumes=0
runtime_exists=false
```

The run used disposable PostgreSQL and Redis state, the isolated qualification
provider double, generated credentials and canaries, and disabled email
delivery. It did not use a production or staging database, make real
OpenAI/OpenRouter calls, send real email, print secrets, or modify production
state. No code was changed after the implementation freeze for this run.

## Qualification boundary

This failed disposable qualification result is not a production
certification, release decision, security certification, compliance claim,
provider-invoice qualification, or SLA claim. The implementation and focused
tests for deterministic concurrency remain on the objective PR for strategic
review; the API-termination reservation-timing failure requires a later
deliberate repair and fresh qualification before closure can be considered.
