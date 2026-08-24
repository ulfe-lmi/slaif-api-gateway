# OAP Work Order — 151-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/151-production-appliance-closure`
Base: `main @ ce0cf95685796477685a3aab6edacb39def6c27b`
Title: `fix: make the production gateway appliance bootable and provable`

## Objective and reason

Close the verified production-appliance defect in the declared current SME
Gateway MVP and replace synthetic deployment claims with one fail-closed,
clean-state qualification through the real production Compose, TLS/NGINX,
PostgreSQL, Redis, API, migration, and optional Celery topology.

This objective is not generic hardening. Canonical `main` currently advertises
`docker compose -f docker-compose.production.yml up -d`, but that path cannot
produce the claimed gateway: Compose requests a nonexistent Dockerfile target,
passes secret-file variable names that `Settings` never reads, does not persist
PostgreSQL, documents a database user/name that PostgreSQL does not create,
attaches the API only to an `internal: true` network that cannot reach provider
origins, uses a nonexistent Celery app module, and starts Redis without enabling
the documented production rate/concurrency control. Existing preflight and demo
scripts do not boot or falsify those boundaries and can still print success
after manual/skipped work.

## Reconciled current state

- Objective 150 is terminal: PR #285 merged to canonical `main` as
  `ce0cf95685796477685a3aab6edacb39def6c27b` at 2026-08-23T18:01:56Z.
- `oap/active` still named terminal `150-a`; this activation deliberately
  advances it to `151-a` after independent reconciliation.
- Required CI is green on `ce0cf95`, but its Docker job builds and starts only
  development `docker-compose.yml`; it does not exercise production Compose.
- The primary checkout is on `work/facial-scoring-qualification` with two local,
  unpushed commits (`0b9845f`, `e912afd`). They are not GitHub truth and are
  unrelated to this objective. Preserve that branch and its commits exactly;
  do not reset, clean, delete, merge, or silently transplant them. Create the
  objective branch from the exact remote base above while carrying only this
  activated order and active pointer into the objective PR.
- The current application, policy, accounting, operator, and endpoint code is
  substantive. Do not rewrite those services merely because their existing
  evidence is fragmented. Make only defects exposed by the composed production
  qualification continuations of objective 151.

## Required implementation

### 1. Coherent production image, configuration, and topology

1. Give the Dockerfile a real named `runtime` stage or remove all target
   references consistently. The one built artifact must contain the API, CLI,
   Alembic migrations, and Celery application used by production commands.
2. Add one explicit, allowlisted production secret-file loading mechanism used
   by API, migrations, worker, and scheduler before Python settings are loaded.
   It must support exactly the secrets needed by the declared Compose path,
   trim no arbitrary secret characters, reject missing/unreadable/empty files,
   reject ambiguous conflicting direct-value/file configuration, export only
   the corresponding existing application environment names, never print
   values, and `exec` the original command. Do not add a generic secret manager.
3. Align PostgreSQL initialization and the documented `DATABASE_URL` around one
   explicit database user and database. Add a named PostgreSQL data volume.
   Redis may remain disposable acceleration, but its loss must never become
   accounting truth.
4. Preserve the private service network while adding an explicit API egress
   network so permitted provider transport can leave the stack. PostgreSQL and
   Redis must remain unexposed. NGINX remains the only public HTTP/TLS ingress;
   a loopback-only API diagnostic port is acceptable only if documented
   precisely and never used as qualification evidence for gateway traffic.
5. Correct worker/scheduler commands to the actual
   `slaif_gateway.workers.celery_app:celery_app` object. Keep them under the
   existing opt-in `async` profile and prove both processes stay healthy long
   enough to inspect registered tasks/schedule; do not claim that optional
   email or reconciliation execution is enabled by default.
6. Enable Redis request/concurrency enforcement explicitly in production with
   production fail-closed behavior and finite documented defaults. PostgreSQL
   remains authoritative for quotas, reservations, usage, cost, holds, and
   reconciliation.
7. Keep TLS and provider credentials out of images and Git. Production startup
   must fail closed on missing or malformed required files. Operator-defined
   generic provider secret variables may require an explicit Compose override;
   document that bounded mechanism without exposing values.

### 2. Replace synthetic preflight/journey evidence

Create or repair a repository-owned production qualification harness. It may
use a dedicated qualification-only Compose override and a small controllable
OpenAI-compatible HTTP service, but the provider double must be a separate
process/container reached over a real socket. It must not replace API services,
PostgreSQL, Redis, NGINX, authentication, routing, policy, pricing, quota, or
accounting with in-process mocks.

The harness must:

- refuse non-disposable project/database targets and use a unique Compose
  project name;
- start from no inherited project containers or volumes, generate disposable
  TLS and plausible test-only secrets outside tracked files, validate Compose,
  build the production image, run migrations, and start the default and `async`
  profiles;
- fail on every required command or skipped mandatory stage; never use
  `|| true` or emit an overall success result after a failure/manual placeholder;
- create a local admin and use real supported CLI/dashboard interfaces to
  configure a provider, routes, pricing, and one bounded gateway key;
- retrieve the key plaintext once, send client requests only through HTTPS
  NGINX, inspect safe usage/audit state, expire or revoke the key, and prove a
  later request is denied before provider transport;
- query PostgreSQL directly by gateway request identity for accounting
  assertions rather than trusting response text or verifier output;
- preserve useful sanitized diagnostics and clean only its exact disposable
  Compose project in a trap.

### 3. Mandatory composed scenarios

At minimum, drive these scenarios through production NGINX against the separate
provider process:

1. Chat non-streaming success and streaming success with authoritative usage.
2. Responses non-streaming success and ordinary stateless text streaming
   success with authoritative usage.
3. Provider HTTP error, timeout, malformed non-streaming body, malformed or
   incomplete SSE, and a client-aborted Chat stream.
4. Ordinary Responses client disconnect after output, with real PostgreSQL and
   real Redis active; do not substitute the hosted-web-search hold path for
   this ordinary-stream proof.
5. Request/token/cost quota rejection, quota crossing after one admitted
   request, and concurrent-request rejection while a stream is active.
6. Stop the actual Redis container, prove production fails closed before
   provider transport and without a new reservation/ledger mutation, restart
   Redis, and prove recovery.
7. Terminate the API during an active stream, restart it, and prove the
   reservation is terminal or is discovered and repaired by the documented
   reconciliation procedure. No unexplained pending row may be ignored.
8. Recreate API and PostgreSQL containers without deleting the named database
   volume, then prove key, route, pricing, ledger, audit, and quota state remain.
9. Run the existing backup/restore verification against data created through
   the production stack.

For every accepted generation request, assert the expected reservation state,
ledger status, streaming flag, token/cost source, key reserved/used counters,
provider/route/model identity, and zero unrelated pending reservations.

### 4. Privacy and documentation truth

- Inject unique canaries for gateway key, upstream key, prompt/input,
  completion/output, image/media-like payload, malformed provider body, and
  authorization header. Inspect PostgreSQL, container logs, audit/usage exports,
  metrics output, and generated reports. None may contain prohibited content or
  secret values; only allowlisted safe metadata may remain.
- Update production deployment, operations, and verification documentation to
  describe commands that the harness actually ran, optional async behavior,
  loopback/public port boundaries, egress, persistence, backup/restore, Redis
  fail-closed behavior, and evidence limitations.
- Remove or correct any claim that `scripts/demo/run-journey.sh`, Compose syntax,
  or preflight alone proves clean deployment. Documentation correction earns no
  functional pass without the runtime evidence above.
- Do not declare production certification, compliance, penetration testing,
  enterprise readiness, an SLA, invoice-grade billing, or exact no-overrun.

## Exact allowed paths

```text
Dockerfile
docker-compose.production.yml
nginx/production.conf
deploy/production/**
scripts/preflight.sh
scripts/demo/run-journey.sh
scripts/verify_production_compose.py
scripts/production-qualification/**
tests/unit/test_production_compose*.py
tests/integration/test_production_compose*.py
tests/e2e/test_production_compose*.py
.github/workflows/ci.yml
docs/deployment-production.md
docs/deployment.md
docs/runbooks/**
docs/verification/**
oap/orders/151-a-production-appliance-and-composed-boundary-closure.md
oap/reports/151-a-production-appliance-and-composed-boundary-closure.md
oap/active
```

Use the narrowest subset. A necessary file outside this list is a strategic
continuation request, not implicit authority. Do not modify migrations,
application gateway/accounting/policy code, dependency manifests,
`ARCHITECTURE.md`, endpoint matrices, facial-scoring assets/code, or unrelated
tests in 151-a. If the required composed run exposes an application defect,
report the exact reproduction and stop; a 151-b continuation can authorize the
minimal additional path on the same PR.

## Anti-false-positive acceptance criteria

- A clean `docker compose -f docker-compose.production.yml ... build` resolves
  every target, and the migration/default/async services start with secrets
  loaded through the same mechanism documented for operators.
- Every `/v1` and `/admin` qualification request traverses HTTPS NGINX. Direct
  ASGI/TestClient/service calls and the loopback API port do not count.
- Provider behavior traverses a real network socket to a separate process.
- PostgreSQL and Redis are real services. Fake repositories, fake Redis, and
  print-only database claims do not count.
- The qualification fails if a required stage is skipped, a service exits, TLS
  or egress is bypassed, a request cannot be correlated to PostgreSQL, a pending
  reservation remains unexplained, persistence is lost, or a content/secret
  canary is found.
- Production Compose has durable PostgreSQL storage, valid Celery commands,
  explicit rate-limit enablement, and provider egress while DB/Redis remain
  private.
- The objective report contains exact commands, exit codes/results, tested
  commit, image digest, migration head, service topology, and sanitized per-
  scenario database evidence. Skips and environment blockers are failures, not
  passes.
- Exactly one PR is created for objective 151. The coding agent does not merge
  or enable auto-merge.

## Required verification

Run, at minimum:

```text
git diff --check
python -m ruff check <changed Python files and focused tests>
python -m pytest <focused production-contract unit tests> -q
python -m pytest <focused existing auth/accounting/privacy tests selected by the implementation> -q
sudo -n docker compose -f docker-compose.production.yml config --quiet
<repository production qualification harness in destructive-disposable mode>
```

The Docker run must use a validated unique disposable Compose project and may
use passwordless `sudo` as authorized by repository governance. Record exact
results; do not run real OpenAI, OpenRouter, facial-scoring, email, or any
production/staging service. Normal broad CI remains GitHub's responsibility.
All final-head required checks must pass before strategic merge consideration.

## Explicit non-goals

- Kubernetes, cloud deployment, multi-host HA, managed secret products,
  autoscaling, multi-region, or external load balancers.
- Enterprise multi-tenancy, SSO/SCIM, MFA, full RBAC, compliance, certification,
  formal penetration testing, or release/tag work.
- Additional OpenAI endpoints, hosted tools, MCP/connectors, provider adapters,
  native-module SDKs, or facial-model qualification.
- Real-provider calls, provider accuracy/SLA, invoice reconciliation, exact
  mid-request no-overrun, or synthetic performance claims.
- Broad visual polish or unrelated refactoring.

## Report and publication contract

Publish one immutable `151-a` report only after implementation commits and the
single PR exist remotely. It must identify the PR/base/branch, activation
commit, implementation head, `Report publication commit: SELF`, exact changed
paths, qualification environment, commands/results, image digest, migration
head, service health, each mandatory scenario, direct PostgreSQL correlation,
privacy scan, negative evidence, skips/blockers, documentation impact, and all
non-goals. The final report-only commit must have the reported implementation
head as first parent and change only the report file. Send exact two-byte `OK`
only after that commit is the verified remote PR head. Do not merge.
