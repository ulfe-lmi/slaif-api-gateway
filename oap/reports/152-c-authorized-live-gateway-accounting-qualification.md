# OAP report — 152-c authorized live Gateway accounting qualification

## Identity and result

- Objective: 152-c
- Active selector: 152-c
- Active selector SHA-256: 6a331ab44ce4ac26f04897f8a7f9fd49ac90ca185dfea55948011d723db19f56
- Work-order SHA-256: 257660604d75d3ff27e8798988b6086fba6f9570fc6de22452b4a5a18a30b68d
- Existing PR: #287, amend-only, no merge, no auto-merge
- Branch: oap/152-real-provider-accounting-qualification
- Frozen live candidate: ea8b98fb104f44c1138a025ad5c23c7c30690a52
- Post-run documentation evidence commit: none; the order requires no documentation change after a failed live round
- Report publication commit: SELF
- Result: FAIL; bounded live qualification stopped after the first flow
- REAL_PROVIDER_CALLED: false; verifier real-provider proof: false

This report records the one authorized live attempt. It does not qualify the
provider set, Gateway accounting, production readiness, or any release.

## Authorization and setup

The protected authorization document was bound to the frozen candidate, exactly
eight maximum requests, providers OpenAI and OpenRouter, a EUR 0.05 maximum
total cost, and a future expiry. The live verifier command used the HTTPS
loopback Nginx `/v1` target, protected Gateway-key and PostgreSQL-URL files,
the generated CA, the two reviewed public model IDs, a 15-second minimum gap,
and bounded PostgreSQL polling. Inherited provider, database, and upstream-test
environment variables were unset.

The disposable production topology used the candidate Dockerfile,
`docker-compose.production.yml`, production secret loader, Nginx configuration,
API image, migrations, PostgreSQL, Redis, and generated TLS. Local setup added
exactly two enabled providers, four exact streaming routes, and four active EUR
pricing rows without provider discovery or any `/models` request. Provider
metadata read back as `max_retries=0` and `timeout_seconds=90` for both
providers. The fresh standard Gateway key had zero reservation and ledger
history, zero used/reserved counters, bounded model/endpoint allowlists, and
strict standard capability policy.

Before provider traffic, disposable setup repaired a raced Nginx port choice,
supplied the production Nginx private-key filename, and used a loopback-only
runtime PostgreSQL relay because Docker did not expose a port for the
PostgreSQL service attached only to the production `internal: true` network.
These repairs did not change repository files, the candidate, the API image,
the provider path, or the database volume contents.

## Live result

Two guarded pre-live verifier invocations stopped before any Gateway or
provider request because the protected database URL was initially missing and
then because Docker had not exposed the internal-only PostgreSQL port. After
the permitted runtime-only repairs, the authorized live verifier invocation
was executed exactly once. It attempted one ordered flow: OpenAI Chat
Completions, non-streaming. The Gateway
response passed the verifier's terminal HTTP/shape/usage stage and the direct
SQL state showed one finalized successful HTTP-200 reservation/ledger pair.
The verifier then stopped with:

```text
error_code=correlation_metadata_invalid
attempted_requests=1
correlated_completed_count=0
real_provider_call_proven=false
```

No second live verifier invocation, provider retry, selective provider rerun,
code repair, or additional Gateway generation request was made. The remaining
seven flows were not attempted.

Direct bounded SQL evidence for the one observed row was:

- finalized reservations: 1; finalized successful ledger rows: 1;
- provider/endpoint/stream split: OpenAI, `/v1/chat/completions`, non-streaming, 1;
- response/stored accounting total tokens: 36/36;
- SLAIF actual cost: EUR 0.000005800;
- SLAIF estimated cost: EUR 0.000012900;
- recorded cost source/confidence labels: `slaif_calculated` / `slaif_calculated`;
- selected-key used counters: 1 request and 36 tokens, with zero reserved request/token/cost counters.

The SQL metadata contained the bounded cost-label fields, but the verifier
failed at its correlation-metadata validation boundary. This report does not
infer a code fix from that observation. The direct SQL row is not upgraded to
real-provider proof: the verifier's required proof remained false.

The historical direct OpenAI preflight and public unauthenticated OpenRouter
model-list check were not repeated and are not counted here. No provider
discovery call, hosted tool, file, media, external authority, real email, or
provider retry was used by this round.

## Privacy and cleanup

- Prompt-marker hits in captured API/Nginx logs and selected ledger text: 0.
- Response-marker hits in captured API/Nginx logs and selected ledger text: 0.
- Credential-value hits across captured logs and selected ledger text: 0.
- No key, prompt, completion, raw JSON, request ID, URL credential, provider body, or protected authorization content was printed or committed.
- Compose teardown used `down --volumes --remove-orphans` while runtime files existed.
- Final cleanup verification: 0 project containers, 0 project networks, 0 project volumes, 0 runtime processes, 0 qualification ports busy.
- The exact disposable runtime and setup scratch files were removed.

## Boundaries

This is a failed, partial live attempt, not a qualification. It does not prove
real-provider execution, all eight flow variants, complete accounting
cardinality, provider authorization-header attestation, invoice-grade cost,
hard pre-call cost containment, deployment safety, production certification,
security certification, compliance, HA, SLA, or release readiness. Historical
Objective 140, 152-a, and 152-b evidence remains separate and does not turn
this failed round green.

No feature code, migration, adapter, policy, accounting service, verifier,
Compose file, Nginx file, or contract document was changed in this cycle.
