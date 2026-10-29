# Feedback from field use: where CLI functionality is lacking

**Date:** 2026-10-27
**Audience:** the gateway's main coder and maintainers
**Baseline inspected:** canonical `main` at `ca274200f1c34b74ea70217c105637bcf722565b`
(merged PR #349).
**Status:** implementation brief; commands marked **proposed** do not exist yet.
This report changes no application behavior or production configuration.

**Implementation status (2026-10-29, appended note — historical body below
unchanged):** every objective named in this brief (objectives 196-204) is
implemented and merged into `main`. Objective 205 — the single complete
executable-only installed transcript and its qualification evidence, covering
all eleven section-12 outcomes plus installation identity and configuration —
is delivered by PR 361. Current per-field CLI status:
`docs/cli-field-administration.md`. Final full-scope coverage table, the actual
final artifact, and honest limitations:
`docs/verification/2026-10-29-cli-field-installed-workflow.md`.

## 1. The operational problem

During live administration, an operator repeatedly needed short Python programs
inside the application container to create equivalent keys, configure waiting,
change route capabilities, and prepare providers. Those programs opened database
sessions and called services or repositories directly. One maintenance operation
used a raw SQL update to extend existing replay-reference expiries.

An administrator should instead be able to perform these operations with the
installed `slaif-gateway` executable, without importing Python modules, knowing
the database schema, editing key metadata, or writing SQL. The CLI may use the
normal database connection internally; eliminating that normal connection is
not the objective. The objective is eliminating operator-authored bypass code.

Not every bypass demonstrated a missing feature. We also used scripts for
operations that the supplied CLI already supports. Fix the actual gaps and
make the supported path discoverable; do not reimplement working commands.

This report is bounded to the tasks encountered. It does not request universal
provider support, unrestricted Responses/Codex compatibility, new authentication
mechanisms, automatic key rotation, or a general database-editing CLI.

## 2. Evidence and limits of the field audit

The conversation audit reconstructed 48 configuration interventions, counting a
bulk operation once and separating account creation, key creation, and delivery.
Read-only investigations, repeated confirmations, software-only bug fixes and
ordinary version deployments were excluded. The reconstruction classified:

| Classification | Interventions | Meaning |
|---|---:|---|
| Fully supported by supplied CLI | 20 | A supported command or a loop of supported commands could perform the complete operation. |
| Incomplete CLI; custom service/database scripting used or needed for exact parity | 16 | Some essential policy or update operation was not exposed. This is not a claim that handwritten SQL was required. |
| Raw SQL maintenance | 1 | Existing replay-expiry extension had no supplied administrative command. |
| File/runtime/source configuration | 11 | Client profiles, proxy settings, secret mounts, compatibility data, capture bootstrap, or packaged defaults. These are not missing CRUD commands. |

These are reconstructed operation counts, not counts of CLI invocations or
verified historical command executions. Earlier exchanges do not retain their
complete execution traces. The capability findings below were checked against
the baseline source, not assumed to have existed at every earlier date.

Representative cases and the required improvement:

| Field task | What prevented normal CLI administration | Required outcome |
|---|---|---|
| Issue student/beta keys with exactly the policy of an existing key | Key creation does not expose the full provider, Responses/Codex, and lazy-wait policy; no faithful clone operation | Typed policy creation and a secret-safe clone command |
| Issue two chat keys equivalent to a newer existing key | Copying only models/endpoints would omit provider restrictions and policy metadata | Reproduce configuration exactly without copying secrets or usage |
| Configure one request per window, waiting, maximum wait and concurrency | Rate-limit CLI exists; lazy-throttling CLI does not | Expose the waiting service and show its effective behavior |
| Change limits across a cohort or a reviewed set of 37 keys | Individual rate-limit commands exist; applying exact mixed policies needs scripting and careful membership handling | Reviewable, bounded batch operation using the same services |
| Enable catalog listing for a model-restricted key | Endpoint update already exists | Document the existing command and make discovery permission visible |
| Raise route context/output headroom; configure image/video estimates | No general update command for existing route capabilities | Audited partial updates and validated configuration-file support |
| Prepare the two custom completion services | Provider add omits timeout/retry controls; route add omits explicit capabilities, although route import can create them | Complete provider flags and route creation/update parity |
| Extend retained replay references after changing the global lifetime | Configuration changes only newly persisted expiries | A dry-run-first replay maintenance command |
| Diagnose authentication, authorization, context and stream failures | Pre-admission failures lack enough correlated, content-free diagnostics; raw log searches and response-size inference were used | Effective-policy inspection and request-ID diagnostics |

The earlier abandoned template request is a separate product limitation:
`key_template_revisions` requires finite request/token totals, unlike ordinary
keys. Do not silently substitute large finite values for unlimited quotas. An
exact key-clone command solves the immediate field task without expanding the
template schema. Unlimited-quota templates require their own reviewed change.

## 3. Existing functionality to reuse

The following are available already; improve help/examples rather than creating
parallel implementations:

- `owners create/list/show`, `institutions create/list/show`, and
  `cohorts create/list/show` cover the new owner/institution/cohort cases.
- `keys create`, lifecycle commands, `keys set-limits`, and
  `keys set-rate-limits` cover ordinary creation, expiry, total quotas and
  per-key operational limits. Existing clear flags must retain their semantics.
- `keys policy update` can change allowed models/endpoints. Adding
  `/v1/models` to the vision key did not require a database script.
- `email send-pending-key`, key creation's `--email-delivery` option, and the
  existing delivery service cover delivery of new encrypted one-time secrets.
  Do not implement plaintext-key recovery or resending consumed secrets.
- `providers enable/disable` and `routes enable/disable` cover activation.
- `codex inspect`, profile/preset commands and supported key-module/profile
  migrations cover their existing reviewed compatibility boundaries.
- `request-capture arm/status/stop/cleanup/inspect` already exists. Initial
  enablement and storage/revision settings are process configuration. Capturing
  content is not the default solution to missing operational diagnostics.
- `admin reset-password --password-stdin` already covers password changes.
- Usage reporting already supports key, owner, cohort, provider and model
  filters. Extend it or share its services instead of creating competing totals.

Examples in operator documentation must use actual CLI group names and flags,
include `--json` where scripting is intended, and show the existing deployment
wrapper as optional rather than assuming a particular local container layout.

## 4. P0: complete key policy management and exact cloning

### 4.1 Expose all reviewed policy dimensions

Extend key creation and policy management with typed options or versioned policy
files for:

- Provider allow-lists, independently of endpoint and model allow-lists.
- The existing bounded `responses_policy`, including reviewed Codex capability
  and client-module/profile information.
- Lazy throttling, through the dedicated operation in section 5.
- All existing streaming live-burn and external-tool policy fields that are
  supported by the service layer. Reuse existing commands where present.

**Proposed interface:** extend `keys create` and `keys policy update` with
`--allowed-provider`, explicit provider-all/provider-none operations, and a
`--policy-file` option backed by a versioned, strict schema. A policy export
command must emit the same safe schema. Do not accept arbitrary metadata JSON.

Define these semantics before implementation:

1. An omitted update field preserves its current value.
2. An explicit empty allow-list denies that dimension; it must not become
   unrestricted. Distinguish unrestricted providers (`None`) from no providers
   (`[]`), as the current service does.
3. Clearing a key rate override means inherit the deployment default. It does
   not mean unlimited if that deployment has a default limit.
4. Lifetime quotas and operational limits are different. A null lifetime quota
   means unlimited; preserve the current service validators and clear flags.
5. File data and flags must have a documented conflict rule; reject ambiguous
   combinations instead of silently choosing one.
6. Unknown capabilities, incomplete Codex prerequisites, arbitrary module names,
   and unsupported hosted/external authority fail closed. Importing a policy
   file is not permission to expand the supported protocol boundary.

`CreateGatewayKeyInput` and `UpdateGatewayKeyPolicyInput` already contain several
missing CLI fields. The latter requires `update_allowed_providers=True` when the
provider policy is intentionally changed. Use these schemas and `KeyService`;
do not update `metadata` from the CLI layer.

The bulk-key import service also currently rejects provider-policy fields.
Resolve that inconsistency if the supported CLI import path is used; merely
adding a flag while leaving execution rejection in place is not completion.

### 4.2 Add a faithful key-clone operation

**Proposed:** `keys clone --source-key-id UUID --owner-id UUID --cohort-id UUID`
with explicit validity controls, `--dry-run`, `--execute`, `--reason`,
`--actor-admin-id`, `--json`, and the existing secret-output/delivery options.

Implement a shared service operation and a canonical, typed configuration
snapshot so the CLI does not independently enumerate raw metadata keys.

Copy configuration, including model/provider/endpoint restrictions, the standard
key purpose/capability mode, supported Responses/Codex policy, nullable lifetime quotas,
configured rate overrides, lazy throttling and streaming policies. Preserve
**inherited** settings as inherited, rather than replacing them with today's
effective numeric values. Reject unsupported source policy rather than dropping
it. Fenced external-tool policy retains its current confirmations and finite
quota requirements.

Never copy key material, public key ID, usage/reservations, last-used state,
replay ownership records, one-time secrets, email delivery state, or external-tool
holds. Generate an independent new key and delivery secret. Do not manufacture
membership in a template revision merely because the source has provenance.
Record source-key provenance separately in the audit record. Scope the first
clone operation to standard keys. Reject trusted-calibration source keys unless
a separately reviewed path retains every current confirmation, short-validity
and finite-quota prerequisite; copying a mode is not permission to bypass them.

Require the target owner and cohort to exist. Do not create duplicate owners or
cohorts as a cloning side effect. Reject inactive/fenced source situations that
cannot be safely copied. Validate validity explicitly: distinguish copying the
source's expiry from issuing a duration starting now, and reject expired results.

The plan must show a canonical configuration diff, identity/validity changes,
and an expected-source fingerprint. Revalidate on execution to catch concurrent
source edits. Commit key creation and audit together; enqueue email only after
commit. A delivery failure must not cause an unnoticed second key on retry.

**Acceptance:** reproduce both field cases—student/beta equivalence and two chat
keys in an existing cohort—using only executable CLI commands. Prove exact
policy equality, distinct secrets/IDs, zero initial usage, independent replay
ownership and unchanged source keys. Test null overrides, deny-all lists,
invalid capabilities, conflicting options, stale plans and rollback on failure.

## 5. P0: lazy-throttling commands

**Proposed:** `keys set-lazy-throttling KEY_ID --mode wait --max-wait-seconds N
--max-waiting-requests N`, plus explicit reject/reset behavior and safe JSON
inspection. Add the same typed policy to creation/clone files.

Use `KeyService.update_gateway_key_lazy_throttling` with
`UpdateGatewayKeyLazyThrottlingInput`. Preserve the service's audit reason,
strict validation, installation ceilings and safe fallback. Do not reproduce
waiting or Redis admission logic in the CLI.

Show waiting and rate policy together: request count/window, estimated tokens
per window, concurrency, wait mode, maximum wait and queue bound. Warn clearly
when the key inherits a lower deployment rate than the operator intended, but
do not silently raise or disable limits.

**Acceptance:** configure the field's one-request-per-10-second window,
concurrency one and bounded wait through commands only, when permitted by the
installation ceilings. Reject an excessive wait with a useful error. Changing
waiting must not change rates, quotas, credentials or expiry. Test disabling,
clearing, malformed policies and preserved unrelated metadata.

## 6. P0: route and provider configuration parity

### 6.1 Update existing routes

`routes import` accepts capability data for creation, but
`execute_route_import_plan` is explicitly create-only. A preview classification
of `update` is not an implemented update operation. Do not tell operators to
replace an existing route by deleting it and creating another: its identity is
referenced by replay/accounting data.

**Proposed:** `routes update ROUTE_ID` with typed editable fields and
`--capabilities-file FILE`, reason/actor, dry-run/execute, expected-version or
fingerprint, and JSON output. Also expose a small typed partial-update surface
for common route-owned limits, such as Codex context/output and media budgets.
The exact spelling may follow existing CLI conventions; the behavior is required.

Merge explicitly supplied fields into a loaded route configuration and call
`ModelRouteService.update_model_route`. Full capability-file replacement must
be clearly distinct from a typed partial update. Validate the complete result
with existing capability/module/pricing contracts. Never shallow-merge nested
objects and accidentally discard sibling capabilities.

Cover fields encountered in the field: `codex_limits` context, default output
and maximum output; `media_input_estimation` image/video budgets; Chat input,
streaming and tool capability flags; configured completion-service profile
selection; endpoint, provider and upstream model mapping.

The preview must distinguish model physical context, client advertised context,
gateway admission ceiling and output reservation. Editing a gateway ceiling
must not rewrite client profiles, key grants or other routes implicitly.

**Acceptance:** change only the selected V100 route ceiling to 400,000 while
preserving route ID, output values and every other capability; update the
multi-route headroom and media settings via commands; prove rollback and stale
plan rejection. Route/model/provider mismatches remain denied.

### 6.2 Finish provider creation and update

Add `--timeout-seconds` and `--max-retries` to provider creation and implement
`providers update` using `ProviderConfigService.update_provider_config`.
Expose reviewed mutable fields, including display name, origin, kind, credential
**environment-variable reference**, timeout/retries and notes. Omitted fields
preserve existing values. Preserve the current HTTP confirmation, URL checks,
secret-name validation and audit policy.

Do not accept or print an upstream credential value in command arguments.
Creating a provider with a credential reference must not silently enable it or
prove its backend credential is valid. Keep explicit disabled preparation,
readiness/authentication checks and activation separate.

Service-specific endpoint/model/credential identities belong in provider and
profile data. No `if provider == <actual service name>` branches in CLI or shared
adapter code. Existing route import and pricing commands can be composed with
these commands; a special command for either field service is unnecessary.

**Acceptance:** prepare each of the two configured completion services with its
own origin, profile, timeout, zero retries and pricing using CLI commands only;
leave it disabled until explicitly enabled. Test that editing one provider
preserves unrelated providers and never returns a secret value.

## 7. P0: replay-reference inspection and expiry maintenance

Changing `CODEX_REPLAY_REFERENCE_TTL_SECONDS` affects newly persisted records;
it does not repair old expiry timestamps. The field operation extended 20,451
retained references for 26 active keys, including 91 expired references needed
by a resumed conversation. That should not require an operator-authored UPDATE.

**Proposed:**

- `codex replay inspect` with key/cohort and time filters, counts of active and
  expired records, creation/expiry ranges, route/model grouping and safe reasons
  records cannot be reused. Do not expose raw IDs, HMAC digests or content.
- `codex replay extend` with exactly one explicit scope (`--key-id`,
  `--cohort-id`, or `--all-active`), `--ttl-seconds`, dry-run/execute,
  reason/actor and JSON. Restoring expired records needs explicit
  `--include-expired`; it must not happen as an undocumented side effect.

Create a reviewed maintenance service and repository method. Eligibility must
retain active/valid key checks, a successful finalized ledger for the same
key/source request, supported reference kinds and available HMAC secret versions.
Preserve original IDs/digests, key ownership, route/model and ledger linkage.
Do not reconstruct missing/deleted references from client input or move them
between keys.

Compute the target expiry as **original creation time + selected lifetime**,
not execution time + lifetime. Respect the installation's supported maximum.
Extend eligible rows monotonically; do not shorten existing expiry or refresh
creation times. Repeated execution should be idempotent. Report exclusions,
including revoked/expired keys, unavailable HMAC versions, missing/failing ledger
linkage and records outside the requested lifetime.

A dry run must resolve the exact bounded target set, record its fingerprint and
show affected-key/reference counts. Revalidate or lock appropriately at apply;
do not silently expand membership. Audit the old/new policy, scope and counts
without logging digests. Provide a controlled recovery/export of prior expiry
metadata if needed; never export conversation content or provider identifiers.

**Acceptance:** PostgreSQL tests cover expiry boundaries, reactivation of
explicitly selected expired records, one-year cap, original-age calculation,
same-key/route isolation, ledger/HMAC exclusions, stable batch scope, audit,
rollback and idempotency. This is maintenance, not an authorization bypass.

## 8. P1: effective policy, lookup and error diagnostics

### 8.1 Make inheritance and actual routability visible

Extend existing `keys show`/policy inspection with an effective-policy view.
Show configured overrides beside effective values and their source. A null
per-key rate limit must display as **inherited**, with the effective deployment
limit, rather than being presented as unlimited.

Include provider/model/endpoint allow-lists, lifetime quotas, operational
window/rates/concurrency, lazy waiting, expiry, Responses/Codex policy and profile
revision. Show the intersection with enabled routes. In the field a key allowed
three model names but only one had an enabled Chat Completions route.

Add a content-free permission explanation for a selected key + model + endpoint:
which grant/route/capability prevents access, without issuing inference. Explain
that `/v1/models` is catalog discovery and must be explicitly permitted when
needed; listing must remain filtered to the key's allowed models/providers.

Support safe key lookup by UUID/public identifier and owner email, and bounded,
complete pagination/filtering by owner/cohort/status. Never require entering a
full secret just to find a key. Existing show/list/export output must remain
backward compatible or be explicitly versioned.

### 8.2 Diagnose a rejected request by request ID

**Proposed:** `diagnostics request show --request-id ID --json`, backed by a
shared, bounded operational diagnostic service. Resolve both client-facing
request IDs and gateway diagnostic IDs where recorded. Return a clear not-found
or unavailable result, not a fabricated attribution.

The field repeatedly encountered validation failures before a usage-ledger row
existed. A useful diagnostic therefore cannot rely solely on that ledger. Add
content-free failure facts at the validation/admission/stream boundaries:

authentication vs endpoint/model/capability denial; public error code/parameter;
HTTP status vs stream outcome; resolved key UUID **only after successful
authentication**; resolved route/model when available; input estimate, output
allowance and relevant ceilings; and replay missing/expired counts where safely
known. Do not report an unmatched request as belonging to an owner merely from
an IP address, model or nearby timestamp. Do not infer error codes from HTTP
response byte lengths.

Use a documented bounded retention/storage policy and existing structured
observability primitives where possible. If durable diagnostics need schema,
update `docs/database-schema.md` and provide migrations. No raw Bearer tokens,
keys, provider secrets, request/response bodies, tool arguments/results, image
URLs, reasoning, replay IDs or HMAC digests in events or CLI output. Do not
automatically arm full request capture to compensate for missing metadata.

For a stream rejected after HTTP 200, report failure rather than success based
on HTTP status alone. When exact historical facts were never retained, state
that limit. Known unsupported/expired references remain fail-closed.

**Acceptance:** CLI-only investigations of endpoint denial, unsupported function
tools, context-window rejection, expired replay and unsupported stream events;
include pre-admission failures, unattributable authentication failures and
missing historical evidence. Assert secret/content redaction in every path.

### 8.3 Inspect email delivery without a database query

The send commands exist, but a durable delivery lookup is not exposed as a
complete administrative CLI workflow. Add **proposed** `email list` / `email
show` filtered by delivery UUID, key UUID, owner and bounded time range. Return
recipient and status, timestamps, safe failure code, and whether the one-time
secret is pending, consumed or expired. Never return the secret or rendered
message body. Support JSON and pagination; do not mistake enqueue success for
SMTP acceptance or SMTP acceptance for confirmed arrival in a recipient inbox.

Reuse `EmailDeliveryService` sendability checks for retries. A `sent`, consumed
or ambiguous attempt must not be blindly requeued. Preserve the existing
send-pending command as the action, with a reason and explicit safe retry only
when the service permits it. Tests must cover queued, sent, failed, expired and
ambiguous cases, including an operator asking whether a batch was actually sent.

## 9. P1: batch administration and record edits

Individual rate-limit changes and a shell loop are already possible. A batch
command is an operational improvement, not evidence that raw SQL is necessary
for simple cohort rate updates.

Add a plan/apply facility for reviewed key-policy/rate changes across a cohort
or explicit key list. Resolve exact UUIDs during preview; report the count,
status filters and configuration diff. Default to active keys, require a
separate explicit choice for revoked/inactive records, and reject unexpected
membership/configuration changes at apply. Never imply that editing existing
keys creates a cohort-level default for future keys.

Use existing per-key services within a defined transaction/audit strategy.
Email is post-commit, and partial delivery must not cause key duplication.
Test rollback of a failed configuration batch. Bound batch sizes and provide
complete pagination; never operate on an unnoticed default first page of keys.

For general CLI/dashboard parity, expose owner/cohort edits supported by
`OwnerService.update_owner` and `CohortService.update_cohort`, notably moving an
existing owner to an institution. This is a follow-up: the field's new-owner
creation cases already had CLI coverage. Do not invent a cohort-institution
relationship; the current schema does not provide one.

## 10. Runtime files and secrets: supported boundaries

Not every external change should become a database command. Nginx limits,
Docker secret mounts, backend credential files, client installation/profiles and
process environment belong to deployment tooling/documentation. Compatibility
profiles remain validated data files, not arbitrary CLI-imported Python code.

Provide safe, allow-listed configuration inspection with effective value,
source and restart requirements for relevant non-secret settings, including
replay lifetime and media/body ceilings. A credential check may report
configured/missing/unreadable and backend authentication outcome; it must not
print the value. Reuse `codex` profile/preset and request-capture commands.

Document portable file/Compose examples instead of baking this host's paths,
container names, VPN addresses or credential values into application commands.
Do not offer `config set-anything`, arbitrary SQL, generic ORM editing or a
metadata-write escape hatch as the solution to the gaps above.

## 11. Implementation order and common requirements

Implement in reviewable increments:

1. Typed key-policy parity, lazy throttling and effective-policy output.
2. Shared key cloning with the existing delivery workflow.
3. Provider timeout/retry/update and route update/capability parity.
4. Audited replay inspection and expiry maintenance.
5. Request diagnostics, batch plans and remaining owner/cohort edit surfaces.

Across all increments:

- Put business rules in shared services. CLI and dashboard call those services;
  CLI code parses input and formats safe output, not raw database mutations.
- Use existing Pydantic/dataclass schemas and registries where applicable.
  Extend them deliberately where absent; reject unknown file fields.
- Mutations require an audit reason and support the existing actor identity.
  Configuration changes and their audit must commit consistently.
- Provide stable JSON, useful nonzero exit codes, bounded selection and clear
  counts. Validate completely before side effects. Preserve untouched fields.
- Reuse the existing encrypted one-time secret and email machinery. Default
  output excludes plaintext; use existing explicit secure output mechanisms.
- Do not introduce tests that require real inference, real credentials or real
  email. Unit-test parsing and schemas, mock service/SMTP boundaries, and run
  PostgreSQL integration tests in isolated test databases for persisted changes.
- Update CLI help and operator documentation in each increment. Clearly label
  what is implemented versus proposed; preserve compatibility promises.

Code entry points for the implementer:

| Area | Existing code to extend/reuse |
|---|---|
| Key CLI and shared schemas | [`cli/keys.py`](app/slaif_gateway/cli/keys.py), [`schemas/keys.py`](app/slaif_gateway/schemas/keys.py), [`services/key_service.py`](app/slaif_gateway/services/key_service.py) |
| Provider/route CLI and services | [`cli/providers.py`](app/slaif_gateway/cli/providers.py), [`cli/routes.py`](app/slaif_gateway/cli/routes.py), [`services/provider_config_service.py`](app/slaif_gateway/services/provider_config_service.py), [`services/model_route_service.py`](app/slaif_gateway/services/model_route_service.py) |
| Create-only route import | [`services/route_import.py`](app/slaif_gateway/services/route_import.py) |
| Key import restrictions | [`services/key_import.py`](app/slaif_gateway/services/key_import.py) |
| Replay and database contracts | [`services/codex_replay_service.py`](app/slaif_gateway/services/codex_replay_service.py), [`db/repositories/codex_replay.py`](app/slaif_gateway/db/repositories/codex_replay.py), [`docs/database-schema.md`](docs/database-schema.md) |
| Delivery and safe CLI sessions | [`cli/email.py`](app/slaif_gateway/cli/email.py), [`services/email_delivery_service.py`](app/slaif_gateway/services/email_delivery_service.py), [`cli/common.py`](app/slaif_gateway/cli/common.py) |
| Diagnostic boundaries | [`api/errors.py`](app/slaif_gateway/api/errors.py), [`api/middleware.py`](app/slaif_gateway/api/middleware.py), [`services/responses_gateway.py`](app/slaif_gateway/services/responses_gateway.py) |

## 12. Definition of done for the encountered tasks

A documented operator transcript using only `slaif-gateway` commands and
ordinary deployment-file management must demonstrate:

1. Find an existing owner/cohort/key without SQL or secret disclosure.
2. Explain configured versus inherited limits and enabled endpoint/model pairs.
3. Create the field's owner/institution/cohort records without duplicates.
4. Clone an exact student/beta/chat policy to another owner and existing cohort,
   retaining unlimited quotas and inherited limits where configured.
5. Grant model listing while preserving the inference restrictions.
6. Set request windows, concurrency and bounded lazy waiting; apply reviewed
   cohort changes without silently touching revoked or newly added keys.
7. Prepare, inspect and explicitly activate configured completion providers and
   routes, with custom timeouts/retries/capabilities/pricing and no named-service
   branches in shared code.
8. Change a selected context ceiling/media budget without replacing the route,
   rotating keys or modifying client context/output allowances unexpectedly.
9. Email the new keys once through the existing one-time-secret workflow and
   inspect sent/failed/ambiguous status without retrieving consumed secrets.
10. Explain a recorded request failure by ID without guessing or capturing
    request content by default.
11. Preview and explicitly extend eligible retained replay references to the
    configured lifetime with the original age, ownership and audit preserved.

Until this transcript and its tests are possible, the CLI is not complete for
these observed administration tasks. A feature is not covered merely because
its service exists, the dashboard can do it, or an administrator can import a
repository class into a Python shell.
