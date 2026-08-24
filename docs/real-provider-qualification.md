# Real-provider qualification boundary

Real-provider qualification is a guarded evidence workflow, not a normal test
suite and not a production-readiness claim. The verifier must be run only by
an explicitly authorized operator against a disposable PostgreSQL database and
an HTTPS SLAIF Gateway.

## Historical Objective 140 evidence

Objective 140 recorded six historical calls: non-streaming Chat Completions,
streaming Chat Completions, and non-streaming Responses for each of OpenAI and
OpenRouter. Those artifacts are preserved as historical records only. They
did not independently prove all currently supported flow variants, exact
Gateway request-ID correlation, streamed terminal usage, or direct
reservation/ledger cardinality. They must not be represented as current
real-provider accounting qualification.

The provider adapters' exact replacement of the client Authorization value is
supported by deterministic transport tests in
tests/unit/test_provider_headers.py,
tests/unit/test_openai_provider_streaming.py, and
tests/unit/test_openrouter_provider_streaming.py. A live provider cannot
echo or independently attest to the received Authorization header. Real
authenticated success plus PostgreSQL correlation proves that the real
adapter path executed; it does not create a provider attestation of the
header.

## Objective 152-a implementation boundary

Objective 152-a refactors
scripts/verify_real_provider_qualification.py into a fail-closed verifier
for exactly eight sequential Gateway requests:

1. OpenAI Chat Completions non-streaming;
2. OpenAI Chat Completions streaming;
3. OpenAI Responses non-streaming;
4. OpenAI Responses streaming;
5. OpenRouter Chat Completions non-streaming;
6. OpenRouter Chat Completions streaming;
7. OpenRouter Responses non-streaming; and
8. OpenRouter Responses streaming.

Each request uses an operator-selected model, a fixed bounded probe, and a
maximum generated output of 32 tokens. The verifier has no retry path and
stops after the first transport, HTTP, parse, stream, or database failure. Its
safe default gap between request starts is 15 seconds and cannot be reduced
below that bound.

Before any Gateway traffic, the verifier requires:

- an explicit --execute-live switch;
- a fresh authorization JSON file outside the repository, with mode 0600,
  the current candidate commit, exactly eight maximum requests, both
  providers, a decimal maximum total cost no greater than EUR 0.05, and a
  future expiry;
- separate mode-0600 Gateway-key and PostgreSQL-URL files outside the
  repository;
- an HTTPS Gateway URL whose path is exactly /v1, with no userinfo, query,
  fragment, or provider-direct host;
- a loopback PostgreSQL URL naming a disposable database matching
  slaif_real_provider_qualification_<lowercase-alphanumeric-suffix>;
- an exact current_database() match and current Alembic head.

The verifier rejects symlinks, unsafe permissions, repository-contained
protected files, inherited secret environment values, secret values in
argv, provider-direct targets, shared/default database names, and ambiguous
database URLs. A CA file may be supplied for disposable local TLS; TLS
verification is never disabled.

For every successful response, including streams, it requires a syntactically
valid X-SLAIF-Diagnostic-ID. It parses the actual Chat SSE [DONE] terminal
and the Responses response.completed terminal, rejects error/incomplete
events and truncated streams, and requires positive internally consistent
usage. After every terminal it selects PostgreSQL rows by that exact
diagnostic ID and requires exactly one finalized quota reservation and exactly
one finalized usage-ledger row with the matching relationship, endpoint,
provider, requested/resolved model, streaming flag, HTTP 200 status, terminal
timestamps, non-negative accounting fields, and exact response/ledger usage
when response usage exists.

After every request the verifier requires zero pending reservations and zero
reserved request/token/cost counters for the Gateway key. At the end it
requires eight distinct correlated reservation/ledger pairs, no duplicate
correlations, a total actual cost within the authorization bound, and no
prompt marker, response marker, or plaintext Gateway key in the correlated
safe metadata or key row. The emitted summary contains only bounded facts and
gateway_request_id_present=true; it never emits a request ID, secret,
prompt, completion, raw JSON, URL credential, or exception text.

The dedicated deterministic verifier tests use fake HTTP/SQL state only. They
do not qualify a provider.

## 152-a status

Objective 152-a made **no real provider call**. It implemented and tested the
guarded verifier only. Therefore current real-provider qualification remains
**NOT RUN**. A later same-number continuation requires fresh protected human
inputs and explicit bounded authorization before it may make the single
eight-flow live qualification. No release, deployment, production
certification, provider-invoice audit, benchmark, or compliance claim follows
from this implementation round.
