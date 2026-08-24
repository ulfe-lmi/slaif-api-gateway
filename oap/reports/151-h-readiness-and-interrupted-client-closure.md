# OAP objective 151-h report

## Result

`FAIL`

This report records the one fresh complete no-keep qualification attempt
required by objective 151-h. The run stopped in the `compose` phase while
executing the qualification-only public `/readyz` denial probe. The probe
invocation was rejected by the installed Compose CLI because `docker compose
run` does not support the supplied `--network` option. No whole-matrix rerun
was performed.

The exact disposable Compose project from the final JSON was
`slaif-151-29395-ad93ea`.

## Run and repository state

- Date: 2026-08-24
- Active order: `151-h`
- Activated order SHA: `e8953143af644e25c6fc168452ede9d2eeede64a1362382fd62a5034cdbb59f7`
- Implementation commit: `3ca2df52b1eb342e1369eedb42c21df0e07db74c`
- Implementation parent: `033ef4c3402338f7224533d400cd4d2ae5578b3b`
- Qualification command: `env -u APP_ENV -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY ENABLE_EMAIL_DELIVERY=false .venv/bin/python scripts/production-qualification/run.py`
- Captured log: `/tmp/slaif-151-h-qualification.log`
- Report publication commit: SELF

The final JSON project token was mechanically validated against
`^slaif-151-[0-9]+-[0-9a-f]{6}$`. Before publication, extraction of every
`slaif-151-[0-9]+-[0-9a-f]+` token from this report produced exactly the single
final token above. No historical or truncated project token is present.

## Phase result

| Phase | Seconds | Status |
|---|---:|---|
| prepare | 0.15 | OK |
| tls | 0.42 | OK |
| compose | 33.35 | FAIL |

Failure: the `public-readyz-denial` qualification command exited with status 1
and the bounded CLI diagnostic was `unknown flag: --network`. The run did not
reach operator configuration, traffic, Redis outage/recovery, concurrency,
active termination, persistence, restore, dashboard, metrics, quota, or
privacy phases.

## Evidence captured before failure

The initial loopback API readiness probe succeeded with four consecutive exact
observations:

- HTTP status: `200`
- state: `ok`
- database: `ok`
- schema: `ok`
- Redis: `ok`
- provider secrets acceptable: `true`
- consecutive successes: `4`

No public-denial result was accepted because the probe command failed before an
HTTP observation. No API termination or client-thread evidence was claimed.

## Cleanup and safety

Automatic cleanup reported success. An independent post-run audit of the exact
final project found:

```text
containers=0
networks=0
volumes=0
runtime_exists=false
```

The run used disposable generated state and stopped before operator traffic.
It made no real OpenAI/OpenRouter calls, sent no real email, used no production
or staging database, printed no secrets, and modified no production state. No
implementation changes were made after the frozen commit for this run.

This is a failed disposable qualification attempt, not a production
certification, release decision, security certification, compliance claim,
provider-invoice qualification, or SLA claim. The public-denial probe command
needs a deliberate bounded repair and a new single qualification attempt in a
later continuation.
