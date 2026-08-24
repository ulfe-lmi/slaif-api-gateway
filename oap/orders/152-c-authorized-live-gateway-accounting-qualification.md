# OAP Work Order — 152-c

PR mode: `AMEND_EXISTING_PR`
PR: `#287`
Branch: `oap/152-real-provider-accounting-qualification`
Base: `main @ 8f2813bf745b90221da33a7cfaf40726c5b1b480`
Current remote head: `e56d31d233c565e74340a66a1263901566d320a7`
Title remains: `obj152: qualify real-provider accounting evidence`

## Objective and human authorization

Run exactly one authorized eight-request real-provider qualification through a
fresh disposable production-Compose Gateway and directly correlated
PostgreSQL. This is the live evidence round for the already implemented OpenAI
and OpenRouter Chat Completions and Responses paths. Do not change feature code
to make it pass.

The human explicitly authorized:

- use of the OpenAI credential supplied by
  `/home/ubuntu/codex-work/slaif-openai-key.sh`;
- use of the historical OpenRouter credential supplied through the ignored
  primary-checkout `.env`;
- exactly eight sequential generation requests: Chat non-stream, Chat stream,
  Responses non-stream, and Responses stream for each provider;
- no hosted/local tools, files, media, external authority, or retries;
- at most 32 output tokens per request, at least 15 seconds between request
  starts, and a `0.05 EUR` post-response SLAIF-accounting ceiling.

The user also authorized and received one separate direct OpenAI preflight. It
performed one authenticated model-list request and one minimal billable
Responses request against `gpt-5.6-luna`; the response completed HTTP 200 with
11 input, 5 output, 16 total tokens. This proves only that the credential/model
worked. It is not Gateway evidence and must not be counted among the eight live
Gateway requests. A public unauthenticated OpenRouter model-list check also
confirmed `nvidia/nemotron-3-super-120b-a12b:free` is currently listed; it is
not a generation request or qualification evidence.

## Verified starting state

- Remote `main` remains
  `8f2813bf745b90221da33a7cfaf40726c5b1b480`.
- PR #287 is open and mergeable with no auto-merge. Remote head
  `e56d31d233c565e74340a66a1263901566d320a7` is a valid 152-b report-only
  commit whose sole parent is hardened verifier implementation
  `2cbc563ddfc87977324de68aac55a9c1154792fb`. All ten checks succeeded; 49
  verifier tests and an independent rerun passed.
- The OpenAI script is a regular owner-only mode-0600 file. The ignored `.env`
  is owner-owned but mode 0644 and cannot itself be used as a protected secret
  input. Extract only `OPENROUTER_API_KEY` into the disposable owner-only
  runtime, without output, and delete it during cleanup.
- No prior 152 request has touched Gateway/PostgreSQL. Preserve the historical
  NOT-RUN reports.

## Candidate freeze and one-shot rule

- Sync the exact 152-c order/selector and commit them on PR #287 before any
  live setup. With a clean worktree, freeze that exact commit as the live
  candidate. Do not amend/rebase it after authorization-file creation.
- Create the protected authorization JSON outside the repository with that
  exact 40-character candidate, `max_requests=8`, providers exactly OpenAI and
  OpenRouter, `max_total_cost_eur=0.05`, and expiry no more than two hours in
  the future.
- Setup/model-list/health/readiness/CLI/SQL operations do not count as the
  eight generation requests, but provider discovery calls are prohibited.
  Configure routes/pricing locally without `providers setup-models` or any
  other command that probes upstream `/models`.
- Once the verifier's live invocation starts, it is the sole qualification
  attempt. Do not rerun it after any transport, HTTP, stream, provider, SQL,
  accounting, privacy, or cost failure. Publish that exact failure and clean
  up. A pre-verifier local setup defect may be repaired only if it made zero
  provider HTTP requests and the candidate remains unchanged.

## Disposable production-Compose boundary

### 1. Exact safe runtime and credentials

- Create a unique mode-0700 runtime outside every repository and a unique
  project matching `slaif-152-<digits>-<six lowercase hex>`.
- Load the OpenAI shell script only in a `set +x` subprocess with source output
  redirected. Accept its OpenAI key variable without printing it. Source the
  ignored primary `.env` similarly and extract only `OPENROUTER_API_KEY`.
- Write only the extracted key bytes into separate owner-only mode-0600 runtime
  files. Never copy/source the `.env` into Compose, and never print values,
  lengths, prefixes, hashes, paths paired with values, or shell state.
- Generate all other production secret files and TLS material in that runtime.
  Require OpenAI, OpenRouter, Gateway, HMAC, admin-session, and one-time-secret
  values to be non-empty and pairwise distinct in memory without output.
- Use a fresh database named
  `slaif_real_provider_qualification_<lowercase alphanumeric suffix>` and a
  generated password. Store the loopback verifier URL separately from the
  in-Compose async URL, both mode 0600.

### 2. Real production topology with bounded qualification override

- Use the candidate's actual `Dockerfile`, `docker-compose.production.yml`,
  NGINX configuration, migrations, production secret loader, API entrypoint,
  PostgreSQL, Redis, and named volume. No provider double or host application
  process may substitute.
- A runtime-only Compose override may change only unique loopback host ports,
  PostgreSQL database name/healthcheck, and publish PostgreSQL on a unique
  `127.0.0.1` port for the verifier. It must not be committed.
- Keep API diagnostic and PostgreSQL ports loopback-only; only the unique NGINX
  HTTPS port is the verifier's Gateway target. Keep provider egress through the
  real API container.
- Build with no pull, run migrations, and require exact API `/readyz` 200 facts
  for database/schema/Redis/provider secrets after local provider configuration.
  NGINX `/healthz` must be 200 under the generated CA.

### 3. Local operator configuration without provider discovery

- Create one disposable superadmin and owner through the documented CLI.
- Add enabled provider metadata through CLI only:
  - `openai`, env name `OPENAI_UPSTREAM_API_KEY`, base URL
    `https://api.openai.com/v1`, kind `openai_compatible`;
  - `openrouter`, env name `OPENROUTER_API_KEY`, base URL
    `https://openrouter.ai/api/v1`, kind `openai_compatible`.
- Set both provider rows to `max_retries=0` and a bounded timeout, then read them
  back. Any provider retry configuration fails the qualification.
- Without upstream discovery, insert only the reviewed disposable exact routes
  and active local pricing rows in PostgreSQL, then read them back:
  - requested `openai/gpt-5.6-luna` → OpenAI upstream `gpt-5.6-luna`;
  - requested
    `openrouter/nvidia/nemotron-3-super-120b-a12b:free` → OpenRouter upstream
    `nvidia/nemotron-3-super-120b-a12b:free`;
  - one Chat and one Responses route per provider, exact match, streaming=true,
    enabled, with the canonical `chat_and_responses_text_v1` capability objects,
    all hosted/tool/media/storage capabilities false;
  - one active EUR pricing row per endpoint/model. OpenAI may use conservative
    explicit local input/output prices; OpenRouter's reviewed free-model rows
    may be zero. Label all as local qualification assumptions, not invoices.
- Create exactly one fresh standard Gateway key through CLI, limited to the two
  public models, Chat and Responses endpoints, request total 8, cost total
  0.05 EUR, sufficient token/rate limits, validity one day, and no external
  tools. Deliver it once to an owner-only file outside the repository and retain
  only its safe UUID for the verifier.
- Before live invocation, query PostgreSQL and mechanically prove the selected
  key has zero used/reserved counters and zero reservation/ledger rows; verify
  exactly two providers, four routes, and four active pricing rows.

## Exact live verifier invocation

- Run `scripts/verify_real_provider_qualification.py` once from the clean
  candidate with all inherited provider/database/upstream-test variables unset.
- Supply only: `--execute-live`, generated HTTPS `/v1` URL, protected Gateway
  key file, safe Gateway key UUID, protected loopback PostgreSQL URL file,
  protected authorization file, the two exact public model IDs above, generated
  CA file, minimum gap 15 seconds, and bounded polling values.
- Capture only the verifier's sanitized stdout/stderr. Do not enable HTTP,
  SQLAlchemy, asyncpg, Compose, shell, or curl debug tracing.
- Require one result=ok object with attempted=8, correlated-completed=8,
  real-provider proof true, eight ordered flows, exact model/provider/endpoint/
  stream facts, positive matching response/stored usage, finalized reservation
  and ledger facts, zero pending/reserved state, bounded cost labels, total
  SLAIF-accounted cost within authorization, and no raw request IDs/content.
- Independently query the disposable PostgreSQL database after the run using
  the selected key UUID. Require exactly eight finalized reservations, eight
  matching finalized successful ledger rows, endpoint/provider/streaming split
  2 each per provider/endpoint/stream shape as expected, no pending rows, zero
  reserved counters, request-used total 8, positive total tokens, and total
  actual cost <=0.05 EUR. Compare bounded aggregates to verifier output; do not
  print IDs, JSON metadata, content, or credentials.
- Scan API/NGINX logs and the selected key/reservation/ledger/audit metadata for
  the fixed verifier prompt/response markers and all credential values in
  memory. None may occur outside provider transport/response; emit only boolean
  absence facts and scanned row/log counts.

## Cleanup and immutable evidence

- In every path, run Compose down with volumes/remove-orphans while runtime
  files still exist. Then delete only the exact runtime directory.
- Independently require zero containers by exact Compose project label, zero
  exact project networks/volumes, no runtime path, no protected temp files, and
  no process using the project/ports. If cleanup fails, the result fails.
- After a successful one-shot run, update only
  `docs/real-provider-qualification.md` with sanitized aggregate evidence and
  explicit limitations. Commit that documentation as the post-run evidence
  implementation commit; preserve the exact live candidate separately.
- Publish exactly one immutable
  `oap/reports/152-c-authorized-live-gateway-accounting-qualification.md` as the
  sole path in the final report-only commit. Record exact candidate/evidence
  commits, bounded flow/token/cost-source/accounting aggregates, setup facts,
  direct-preflight separation, cleanup, and limitations. Never record keys,
  IDs, URLs with credentials, content, raw events/rows, or provider bodies.

## Exact allowed repository paths

```text
docs/real-provider-qualification.md
oap/orders/152-c-authorized-live-gateway-accounting-qualification.md
oap/reports/152-c-authorized-live-gateway-accounting-qualification.md
oap/active
```

Runtime-only files outside repositories are allowed and must be deleted. If the
live run reveals a verifier/application defect, stop and report it; do not
change code or rerun under this order.

## Anti-false-positive acceptance

- Direct provider preflights, public model lists, setup SQL, health checks,
  provider-double tests, and historical Objective 140 evidence cannot count
  among the eight Gateway flows.
- The Gateway base URL is the disposable NGINX HTTPS endpoint and every flow
  has an internal Gateway diagnostic ID correlated to this PostgreSQL database.
- Provider config retries are exactly zero. Eight Gateway requests cannot hide
  more than eight provider generation attempts behind retries.
- The fresh key's complete total row sets—not filtered seen IDs—equal exactly
  eight after the run. No pre-existing/concurrent rows pass.
- Streaming Chat requires `[DONE]` and terminal usage; streaming Responses
  requires one `response.completed` with usage. Connection close does not pass.
- Real authenticated success plus deterministic adapter tests compose the
  credential-replacement evidence. Do not claim provider header attestation.
- SLAIF-calculated/provider-reported cost labels are reported honestly; neither
  the 0.05 bound nor local pricing is provider-invoice truth or exact pre-call
  no-overrun enforcement.
- Exactly one live verifier invocation occurs. Any live failure remains a
  failure; no retry/rerun or selective provider rerun passes.
- Every final report-head check succeeds, but CI cannot replace the live run,
  SQL correlation, privacy scan, or cleanup.

## Boundaries and non-goals

- No feature code, migration, Compose, NGINX, adapter, policy, accounting,
  dashboard, CLI, or verifier change.
- No deployment/release, persistent environment, production/shared database,
  hosted tools, media, Codex, facial/module, provider generalization, or SDK.
- No enterprise, formal penetration test, certification, compliance, HA,
  invoice-grade billing, support, or SLA claim.

## Publication and response duties

- Amend only PR #287; never merge or enable auto-merge.
- Verify live candidate, evidence commit, report SELF topology, PR/check state,
  exact request count, sanitized report, and cleanup.
- Then write exact `OK` to the response FIFO and resume control.
