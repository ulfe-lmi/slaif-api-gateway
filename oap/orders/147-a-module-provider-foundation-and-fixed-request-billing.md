# OAP Work Order — 147-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/147-module-provider-foundation`
Base: `main @ ddf6688b93cda905e0bc38673f6138afb2385a28`
Title: `feat: add module-provider foundation and fixed request billing`

## Objective and business reason

Add the smallest explicit gateway foundation for a statically registered native
downstream module. This enables the separately planned facial-scoring adapter
without treating a non-OpenAI service as an OpenAI-compatible provider and
without moving authentication, policy, quota, accounting, audit, or key
revocation into an adapter.

The immediate product reason is the human-authorized facial-manipulation-scoring
extension, whose eventual public operation is Chat Completions only, data-URL
images only, and fixed pricing of `0 EUR` per request. This objective must stop
before any facial adapter or downstream facial-service call.

## Reconciled current state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Remote `main`: `ddf6688b93cda905e0bc38673f6138afb2385a28`, including merged PR
  #281, which published `oap/MVP-CLOSURE-AUDIT.md`.
- Predecessor objective `141-a`: PR #280 is merged and has a matching immutable
  order/report; `oap/active` currently points to terminal `141-a`.
- No facial adapter, `app/slaif_gateway/modules/` package, or module-provider
  migration exists on current `main`.
- Current provider kind model/check constraint and
  `ProviderConfigService`/admin validation accept only `openai_compatible`.
- Current `PricingService.estimate_chat_completion_cost()` ignores
  `PricingLookupResult.request_price`; request pricing is currently used by
  selected non-chat operations.
- Current `QuotaService.reserve_for_chat_completion()` derives reserved tokens
  from the Chat policy estimate, so a fixed-request module needs an explicit
  zero-token reservation path.
- Current `AccountingService` has normal and custom finalization paths, but the
  normal Chat finalization computes token cost and does not yet express a
  fixed-request billing mode.
- Current migration head is `0022_provider_governance`; the next migration in
  this order is exactly `0023_module_provider_foundation.py`.
- Current GitHub branch protection API reports `main` as not protected. The
  only published release remains `v0.1.0-rc.1`. Open Dependabot PRs #224 and
  #250 are unrelated and must not be reused.
- Both candidate facial-service addresses currently answer `/healthz` and
  `/readyz`; their `/openapi.json` SHA-256 is
  `8e77d16fb308d354bac8e84bfa7ba90c8cf77b8df644d59e391d7b68aa023832`.
  No authorized score request was made and no credential is available to this
  objective. These observations do not authorize a production endpoint or a
  live call.

## Requirements

1. Add provider kind `module` to the SQLAlchemy model/check constraint and the
   exact next Alembic migration. Preserve existing rows and
   `openai_compatible` behavior; unsupported kinds must fail closed.
2. Update the provider configuration service, CLI/admin request validation,
   and provider screens so `module` can be configured without weakening slug,
   environment-variable, URL, or audit validation. Module base URLs remain
   operator configuration; no endpoint is hardcoded. Private/insecure HTTP is
   accepted only through the existing explicit confirmation/reason/audit
   boundary, with URL userinfo, query, fragment, and unsafe redirects denied.
3. Add `app/slaif_gateway/modules/` with a minimal abstract module adapter
   contract built on the existing `ProviderAdapter` boundary. Add only static
   registry/dispatch plumbing in this objective. Unknown module identifiers,
   arbitrary import paths, user-supplied classes, and dynamic plugin loading
   must fail closed. Do not register or implement facial scoring here.
4. Add fixed-request pricing for Chat Completions module routes. When the
   resolved provider kind is `module`, require a non-null non-negative
   `request_price`, use its configured currency and existing EUR conversion,
   ignore token component prices for billing, and expose the configured
   request amount as the estimate. A `0 EUR` rule must produce exact zero EUR.
5. Make Chat quota reservation use zero reserved tokens for the fixed-request
   module billing mode while retaining one reserved request and all existing
   key status, request-limit, concurrency, rate-limit, expiry, and external-tool
   fence controls. Existing non-module routes must retain their current token
   reservation behavior.
6. Make successful normal Chat accounting finalize fixed-request module calls
   with zero provider usage tokens and the fixed request cost, including exact
   `0 EUR`, while retaining PostgreSQL counter/ledger/reservation atomicity.
   Downstream failure or timeout must release the reservation and record the
   existing safe failed-attempt evidence. The adapter must not own accounting.
7. Ensure provider credentials are still loaded only from the configured
   environment variable. Never forward client `Authorization` as a provider
   credential and never log/store raw credentials, image content, request
   bodies, or response bodies in the foundation.
8. Document module-provider boundaries and fixed-request/zero-price accounting:
   zero price does not mean unlimited requests; token usage is zero for the
   module billing mode; streaming/Responses/facial-specific behavior is not
   enabled by this objective.

## Explicit non-goals

- No facial-scoring adapter, `facial_scoring` registration, multipart request,
  data-URL decoding, image validation, or downstream HTTP call.
- No Responses API, legacy `/v1/completions`, streaming implementation,
  remote-image fetching, client-supplied multipart, or image persistence.
- No generic dynamic plugin system, arbitrary imports, model catalog seed,
  production provider row, endpoint rollout, or API key.
- No change to `ARCHITECTURE.md`, release/tag state, MVP declaration, or
  unrelated built-in/OpenAI-compatible provider behavior.
- No production database or deployment changes and no live provider call.

## Allowed paths

Only these paths may change. New test files are allowed only at the named
locations; no broad formatting or unrelated cleanup is permitted.

```text
app/slaif_gateway/db/models.py
app/slaif_gateway/modules/__init__.py
app/slaif_gateway/modules/base.py
app/slaif_gateway/providers/factory.py
app/slaif_gateway/schemas/pricing.py
app/slaif_gateway/services/accounting.py
app/slaif_gateway/services/chat_completion_gateway.py
app/slaif_gateway/services/chat_completion_route_capabilities.py
app/slaif_gateway/services/pricing.py
app/slaif_gateway/services/provider_config_service.py
app/slaif_gateway/services/quota_service.py
app/slaif_gateway/api/admin.py
app/slaif_gateway/cli/providers.py
app/slaif_gateway/web/templates/providers/create.html
app/slaif_gateway/web/templates/providers/edit.html
app/slaif_gateway/web/templates/providers/detail.html
migrations/versions/0023_module_provider_foundation.py
docs/accounting.md
docs/openai-compatibility.md
docs/provider-forwarding-contract.md
tests/unit/test_alembic_provider_pricing.py
tests/unit/test_accounting_service_finalize.py
tests/unit/test_chat_completion_route_capabilities.py
tests/unit/test_cli_providers.py
tests/unit/test_module_provider.py
tests/unit/test_pricing_service.py
tests/unit/test_provider_config_service.py
tests/unit/test_provider_factory.py
tests/unit/test_quota_service.py
tests/integration/test_accounting_finalization_postgres.py
tests/integration/test_admin_provider_config_actions_postgres.py
tests/integration/test_quota_accounting_invariants_postgres.py
tests/integration/test_module_provider_foundation_postgres.py
oap/orders/147-a-module-provider-foundation-and-fixed-request-billing.md
oap/reports/147-a-module-provider-foundation-and-fixed-request-billing.md
oap/active
```

## Observable acceptance criteria

- A clean migration from current head `0022_provider_governance` accepts
  `ProviderConfig.kind = module`; existing and invalid-kind checks are proven.
- Provider CLI/admin validation can create/update `module` configuration and
  still rejects invalid slugs, credential-like values, invalid environment
  names, unsafe URLs, and unconfirmed insecure HTTP.
- Static module dispatch has no dynamic import path and an unregistered module
  cannot produce a provider request.
- A fixed-request Chat pricing row with `currency = EUR` and `request_price =
  0` produces an exact zero-cost, zero-token estimate; non-module token pricing
  tests remain unchanged.
- Module-mode quota reservation records `reserved_requests = 1`,
  `reserved_tokens = 0`, and zero reserved EUR while request limits,
  revocation, concurrency, rate limiting, and external-tool fencing still
  apply. Existing routes continue reserving their policy-estimated tokens.
- A representative successful fixed-request `ProviderResponse` finalizes
  through the normal Chat accounting owner with zero prompt/completion/total
  tokens and exact fixed cost; failure/release behavior remains safe.
- No client Authorization header is used as the module credential, and focused
  inspection finds no raw secret/content in logs, ledger metadata, fixtures, or
  reports.
- Documentation states the implemented foundation versus the planned facial
  adapter and its unsupported endpoints/streaming boundary.

## Required verification

Run focused checks on the final implementation head:

```text
python -m pytest \
  tests/unit/test_module_provider.py \
  tests/unit/test_provider_factory.py \
  tests/unit/test_provider_config_service.py \
  tests/unit/test_pricing_service.py \
  tests/unit/test_quota_service.py \
  tests/unit/test_accounting_service_finalize.py \
  tests/unit/test_chat_completion_route_capabilities.py \
  tests/unit/test_alembic_provider_pricing.py \
  tests/unit/test_cli_providers.py
python -m pytest \
  tests/integration/test_module_provider_foundation_postgres.py \
  tests/integration/test_accounting_finalization_postgres.py \
  tests/integration/test_quota_accounting_invariants_postgres.py \
  tests/integration/test_admin_provider_config_actions_postgres.py
python -m ruff check app tests
alembic heads
git diff --check
```

Also inspect the final diff for dynamic imports, credential/header leakage,
content persistence, accidental external calls, nonzero token reservation for
module routes, bypassed policy/quota/accounting, URL validation regressions,
and changes outside the allowed paths. CI is required evidence; skipped,
pending, missing, cancelled, or environment-blocked checks are not passes.

## Security, privacy, accounting, and provider boundaries

- No real facial-service call, API key, production endpoint, or production
  database is permitted. A fake in-process adapter/response is sufficient for
  foundation tests.
- The module contract receives an already authenticated/policy-checked request
  envelope and remains forbidden from authenticating clients, reserving or
  finalizing quota, writing audit records, or storing content.
- PostgreSQL remains the only quota/accounting authority. Zero monetary cost
  removes the money hold but does not remove one-request reservation, rate,
  concurrency, revocation, expiry, or failed-attempt controls.
- Provider base URLs are configuration and must pass the current URL security
  checks. No redirects, userinfo, query, or fragment may smuggle credentials
  or alter the selected target.
- Reports and test evidence must describe the absence of an authorized live
  score call and must not include credentials, images, data URLs, or raw native
  payloads.

## Documentation and operator setup

Documentation impact is required: update the three named docs in the same PR,
or record a precise reason in the final report for any file not needing a
change. Describe the future operator values without committing data:
provider kind `module`, environment variable naming by configuration, fixed
request pricing semantics, and the fact that facial-specific setup belongs to
`148-a`.

No operator setup, production row, secret, endpoint activation, or live smoke
is authorized by this order.

## Report and publication contract

The coding agent must create exactly one PR for `147-a`, never merge or enable
auto-merge, and push all implementation commits before report publication. The
final report must be the only file changed by its publication commit and must
record:

- implementation-head SHA and literal `Report publication commit: SELF`;
- PR number, base, branch, commits, final-head checks, and review state;
- exact changed paths and scope/non-goal confirmation;
- focused command results, migration evidence, and any not-run/blocked checks;
- negative/security/privacy/accounting evidence and secret/content inspection;
- documentation impact and honest limitations, including no facial adapter or
  live provider qualification;
- report parent/tree and final remote PR-head verification.

The report and this order are immutable orchestration evidence. Do not edit the
order after activation; use `147-b` through `147-z` on the same PR if a
strategic or human finding requires bounded amendment.
