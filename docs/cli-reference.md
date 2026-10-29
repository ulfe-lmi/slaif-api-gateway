# CLI reference

> **Status:** Current command index
> **Audience:** Gateway operators and maintainers
> **Authority:** Typer command registration in `app/slaif_gateway/cli/`

The `slaif-gateway` CLI manages local Gateway metadata and operator workflows.
Most commands require a migrated PostgreSQL database. Provider, route, pricing,
FX, and usage commands do not imply live provider discovery unless their
description explicitly says so.

Use `slaif-gateway <group> <command> --help` for the complete option contract.
Never put plaintext credentials, keys, passwords, or content into audit reasons
or command-line arguments.

## Bootstrap and database

```text
slaif-gateway version
slaif-gateway db check-config
slaif-gateway db show-url
slaif-gateway db current
slaif-gateway db upgrade
slaif-gateway admin create
slaif-gateway admin reset-password
slaif-gateway admin list
```

`admin create` and `admin reset-password` support password input without placing
the password in shell history. Database URL output is redacted/safe by contract;
review command help before using it in shared terminals.

## Organization records

```text
slaif-gateway institutions create|list|show
slaif-gateway cohorts create|list|show
slaif-gateway owners create|list|show
```

These commands manage the current owner/institution/cohort records. They do not
create provider routes or keys implicitly.

## Gateway keys and templates

```text
slaif-gateway keys create|create-from-template|clone|list|show
slaif-gateway keys suspend|activate|revoke|extend|rotate
slaif-gateway keys set-limits|set-rate-limits|set-lazy-throttling|set-chat-streaming-live-burn
slaif-gateway keys reset-usage
slaif-gateway keys policy show|update|export|effective|explain-route
slaif-gateway keys external-tools show|update
slaif-gateway templates create-from-calibration
slaif-gateway calibration summarize
```

Plaintext key output is one-time only. Prefer `--secret-output-file` for an
owner-only file or explicitly confirmed plaintext output. Lost keys are rotated,
not recovered. Reserved-counter repair has additional confirmation requirements.

Since objective 197 the lazy (waiting) throttling policy has a dedicated
audited CLI setter, `keys set-lazy-throttling`, which reuses the same
shared KeyService validator, write path, and audit row as the 196
`--policy-file` authoring surface and `keys policy export`; the admin
dashboard key create/detail forms remain an applicable path as well.

### Bounded lazy (waiting) throttling (`keys set-lazy-throttling`)

```bash
# One request per 10 seconds plus concurrency 1, then a bounded wait
slaif-gateway keys set-rate-limits <gateway-key-id> \
  --requests-per-minute 1 --window-seconds 10 --concurrent-requests 1 \
  --reason "one request per ten seconds"
slaif-gateway keys set-lazy-throttling <gateway-key-id> \
  --mode wait --max-wait-seconds 30 --max-waiting-requests 2 \
  --reason "bounded wait for batch runs" --json

# Canonical reject (immediate 429) and reset (clear the stored policy)
slaif-gateway keys set-lazy-throttling <gateway-key-id> --mode reject \
  --reason "fail fast"
slaif-gateway keys set-lazy-throttling <gateway-key-id> --clear \
  --reason "stop waiting"
```

Semantics:

- `--mode wait` requires BOTH positive whole `--max-wait-seconds` and
  `--max-waiting-requests` within the installation ceilings
  (`LAZY_THROTTLING_MAX_WAIT_SECONDS`, `LAZY_THROTTLING_MAX_WAITING_PER_KEY`);
  bool/float/negative values and out-of-ceiling bounds fail BEFORE any
  write (no change, no audit row).
- `--mode reject` removes the stored override (default immediate
  rejection). The shared KeyService canonicalizes a reject policy to "no
  stored override", so supplying waiting bounds alongside reject would be
  silently discarded; the CLI refuses them with a fixed error BEFORE any
  mutation (no change, no audit row). Use `--mode wait` for waiting bounds.
- `--clear` removes the stored policy; plain reject and clear are distinct
  verbs with the SAME stored outcome (no stored override / immediate
  rejection); neither accepts waiting bounds, and they cannot be combined.
- Safe default display: `keys show` / `keys list` project safe metadata only.
  Stored Responses policies render through the strict shared validator
  (canonical members only, or a fixed `{"state": "invalid"}` marker for
  unknown/malformed/stale blocks); the stored provider restriction renders
  as an explicit `allowed_providers_state` (`unrestricted` / `allow-list` /
  `deny-all` / `invalid`) while the legacy `allowed_providers` /
  `allow_all_providers` members keep their shape; `calibration_metadata`
  keeps only its finite known members (`creation_channel`, `created_from`,
  `operator_review_required`). Free-form read values (`revoked_reason`) and
  surviving strings pass the existing known-shape redaction, so KNOWN
  authentication/provider secret shapes cannot reach CLI output; this is
  known-shape protection, not universal content sanitization.
- The shared service validator is re-applied in the caller-owned
  transaction, so installations with ceilings LOWER than the schema
  defaults keep reject/clear usable without silently enlarging the active
  wait bounds.
- Changing the policy touches ONLY the key's lazy metadata, `updated_at`,
  and one audit row: no rates, quotas, identity, secret, validity, status,
  counters, reservations, or other keys.
- Waiting never relaxes hard quota, auth, security, or pricing; it is
  operational waiting behavior only, applicable to the Chat Completions
  and Responses endpoints.

### Effective policy inspection (`keys policy effective`)

```bash
slaif-gateway keys policy effective <gateway-key-id> --json
```

Configuration-only view of the key's configured plus effective policy:

- Per rate member (`requests_per_window`, `tokens_per_window`,
  `concurrency`, `window_seconds`): `configured`, `effective`, and
  `source` (`key` / `deployment` / `none`). A NULL per-key rate is
  INHERITED (the deployment value), never unlimited. The historical
  requests-per-minute / tokens-per-minute fields are counts PER SELECTED
  WINDOW: with a 10-second window, `1` means one per 10 seconds, not one
  per minute. The report renders `count_semantics: "counts per selected
  window"` and never scales or renames the values.
- Lifetime quotas: a `null` quota is UNLIMITED (`remaining` is `null`);
  configured quotas render configured/used/reserved/remaining.
- A warning is emitted when an inherited deployment rate still applies
  despite an unlimited lifetime quota; the CLI never guesses operator
  intent or silently raises limits.
- Stored lazy policy: `stored_state` (`absent`, `reject-configured`,
  `wait-configured`, `invalid-stored`) plus the effective mode/bounds and
  source. Any VALID stored mode is KEY-configured; only absent/invalid
  fall back to the deployment default source. A stored wait beyond an
  operator ceiling classifies as `invalid-stored` (default reject),
  without dumping the raw stored value.
- Allow-lists: models/endpoints plus the provider restriction as an
  explicit state (`unrestricted` / `allow-list` / `deny-all` / `invalid`);
  malformed stored members surface as the fixed `invalid` marker, never
  copied values.
- Responses/Codex profile: policy state, client-module identity (public
  registration identity only; a pin never grants capabilities), validated
  capabilities and local tool types. Unknown, malformed, or stale pins are
  a fixed safe `unavailable` marker.
- Redis: `enabled` / `fail_closed` / `has_limits` as CONFIGURATION, not
  live health or capacity proof. No `REDIS_URL`, provider secrets, or
  Settings/ORM/metadata dumps.
- The key block includes `status_note` for suspended/revoked/expired/
  not-yet-valid/fenced keys so an inspected key in a blocked state cannot
  look like authentication success. The command performs NO
  authentication (no HMAC, status, fence, or time checks) and never
  changes any state.

### Configuration-only route explanation (`keys policy explain-route`)

```bash
slaif-gateway keys policy explain-route <gateway-key-id> \
  --model <model> [--endpoint /v1/chat/completions] --json
```

Explains which configuration grants or blocks model access WITHOUT
inference, authentication, admission, quota reservation, waiting, provider
contact, or capture:

- Key-state blockers are reported FIRST (`key-suspended`, `key-revoked`,
  `key-expired`, `key-not-yet-valid`,
  `key-external-tool-fence-active`): an inspected key in a blocked state
  never looks like a usable key (`key_state.usable_for_requests` is
  false, no resolution is reported).
- Endpoint aliases canonicalize to stable endpoint IDs; an unknown
  endpoint fails with a fixed safe message. `/v1/models` is
  separately-authorized discovery (`verdict:
  discovery-separately-authorized`), never an auto-grant of model access.
  Endpoints whose access depends on payload or resource state report
  not-evaluated reasons instead of pretending model-route absence is their
  full runtime verdict.
- `allowlist_intersection` shows the key's allowed models versus
  CANDIDATE enabled routes (enabled route + enabled provider + provider
  allow-list) using the same public matching law as the runtime resolver;
  a candidate match is not final routability, which is reported in
  `verdict`/`resolution`.
- The verdict reuses the existing RouteResolutionService law:
  `model-not-allowed-for-key`, `model-route-disabled`, `model-not-found`,
  `provider-not-allowed-for-key`, `provider-disabled`, `ambiguous-route`,
  `unsupported-route-match-type`, or `resolved` with a safe resolution
  subset (provider, resolved model, route id/match type/pattern/priority,
  streaming support). No provider base URLs, API-key env vars, or raw
  capability/metadata dumps.
- `capability_checks` runs the current pure runtime enforcers with an
  EMPTY payload: only the base required capability (Chat text / Responses
  mandatory text) is checked (`base_request_supported`,
  `capability_error_code`); request body, tools, media, streaming shape,
  pricing, quota, Redis, and provider health remain explicitly
  not-evaluated.
- The runtime 1000-route candidate bound is preserved and disclosed in
  `bounds` (`route_candidate_bound`, `routes_examined`,
  `possible_unexamined_routes`).

### Safe lookup and bounded paging (`keys list` / `keys show`)

- `keys show <uuid-or-public-key-id>`: UUID lookup remains usable and the
  exact public key ID is also accepted. Full bearer-shaped input is
  refused with a fixed safe error and never echoed; there is no identity
  lookup from token hash/HMAC/plaintext. Credential-SHAPED references are
  likewise refused BEFORE any database query: any internal whitespace,
  a secret separator (`.`), a case-insensitive `Bearer` header prefix, or
  any configured accepted key prefix (including `GATEWAY_KEY_PREFIX`)
  cannot be a safe UUID/public ID and fails with the same fixed no-echo
  error.
- `keys list --owner-email <exact email>` uses exact owner lookup (never
  substring matching); unknown email fails with a fixed safe error.
  `--owner-id` and `--owner-email` are mutually exclusive.
- `--cohort-id` and `--status` filters apply in SQL BEFORE the limit.
- Bounded complete pagination: `--limit` (default 50, maximum 200) and
  `--offset`; JSON adds `paging` metadata (`limit`, `offset`, `returned`,
  `has_more`, `next_offset`). The list fetch uses a bounded lookahead of
  ONE extra row (`limit + 1`), so `has_more` is true ONLY when an extra
  real row exists and `next_offset` is `null` at the true end of the
  result set - a full final page reports `has_more: false` instead of
  claiming unknown state. Only the requested `limit` rows are returned;
  the internal lookahead for the maximum page of 200 is bounded (201) and
  never unbounded. The default `{"keys": [...]}` shape is unchanged
  (additive metadata only).
- Stable ordering: `created_at` DESC with a UUID tiebreaker, so rows with
  equal timestamps paginate without duplicates or lost rows.

### Cloning standard keys (`keys clone`)

Since objective 198, `keys clone` is a two-step plan/execute operation that
replaces operator Python cloning: a reviewed NON-secret plan file is written
first, then executed exactly. Help examples are actual commands.

```text
# 1) Plan: strict non-secret plan file (new 0600 file, never overwritten).
#    Mutates nothing and writes no audit row.
slaif-gateway keys clone --dry-run /tmp/clone-plan.json \
  --source-key-id <source-key-uuid> \
  --target-owner-id <target-owner-uuid> \
  --target-cohort-id <existing-cohort-uuid> \
  --validity-mode copy-source-expiry
# or:  --validity-mode duration-from-now --validity-duration-seconds 86400
# or:  --validity-mode absolute --valid-from <ISO> --valid-until <ISO>

# 2) Review the file (canonical configured policy, source fingerprint,
#    stable operation UUID, confirmation requirements), then execute with
#    EXACTLY ONE explicit one-time key channel:
slaif-gateway keys clone --execute /tmp/clone-plan.json \
  --reason "clone for <owner>" \
  --secret-output-file /tmp/new-key.secret
# or:  --show-plaintext
# or:  --email-delivery pending
# or:  --email-delivery send-now
# or:  --email-delivery enqueue

# 3) Retry the SAME executed plan after a post-commit output/mail failure:
slaif-gateway keys clone --execute /tmp/clone-plan.json \
  --reason "retry after output failure" --email-delivery pending
```

- Eligibility: standard purpose AND standard capability mode; the source
  must be `active`, currently within its validity window, and not fenced.
  The target owner and (if given) cohort must already exist; nothing is
  auto-created. Calibration sources, inactive/revoked/suspended sources,
  not-yet-valid or expired sources, and missing targets are refused without
  mutation.
- Canonical configured policy: the plan stores the 196 strict version-1
  export of the source. The target's configured policy equals the source's
  by construction (that equality IS the clone); configured totals are
  copied, never the source's usage, remaining balance, replay rows, holds,
  or template membership. The target starts as an independent active key
  with its own material, HMAC state, and zero usage.
- Unsupported source policies fail explicitly: a non-default or malformed
  raw `responses_streaming_live_burn` policy is refused (creation always
  writes the default), and a policy value carrying a RECOGNIZED secret
  shape (gateway key text, bearer token, provider key, sensitive
  assignment) is refused with a fixed safe unsupported-source explanation
  instead of being emitted or silently altered. This is known-shape
  protection, not universal content sanitization.
- Validity: exactly one mode - `copy-source-expiry` (from execution time to
  the source's fresh `valid_until`), `duration-from-now` (positive whole
  seconds from EXECUTION time, never from dry-run time, bounded by a
  documented maximum of 1,000 years), or `absolute` (naive timestamps are
  normalized to UTC so a mixed aware/naive window is compared
  predictably and rejected instead of crashing). Invalid or
  already-expired result windows are rejected at plan and at execute
  time.
- Fingerprint: SHA-256 over the source public key ID, status, validity,
  purpose/mode, and the canonical policy document. Traffic usage,
  reservations, `last_used_at`, and usage-only `updated_at` drift do NOT
  move the fingerprint; a configuration/validity/status change makes a
  stale plan refuse before any write.
- Reviewed plan revalidation: on FIRST execution, AFTER the source-row
  lock, the service re-derives the source fingerprint and the FRESH
  canonical configured policy and rechecks them against the plan's
  reviewed `policy` document, `source_public_key_id`, and
  `requires_fenced_confirmation`; for COPY-SOURCE-EXPIRY plans the
  reviewed `validity.source_valid_until` is additionally compared
  (normalized ISO datetime) against the fresh locked source's actual
  expiry. Any mismatch is refused with a fixed safe error before any
  write: a stale source is a stale plan, and a reviewed
  policy/identity/validity/confirmation the (unchanged) source does not
  back is refused, never silently ignored (another expiry is never
  substituted while claiming the exact reviewed plan executed). The
  editable plan file is never authority to widen or narrow the source
  policy.
- Execution time: the clock is sampled AFTER the source-row lock is
  acquired, so a source that expires while the lock is acquired is
  refused at execute time.
- Mixed-mode refusal: `--execute` refuses the dry-run-only flags
  (`--source-key-id`, `--target-owner-id`, `--target-cohort-id`,
  `--validity-*`) and `--dry-run` refuses the execute-only channel/
  confirmation flags (`--show-plaintext`, `--secret-output-file`,
  `--email-delivery` other than `none`,
  `--confirm-external-tool-fenced`). On execute, the reviewed plan file
  is the sole source of source/target/validity values.
- Fenced external policy: the plan records the fresh confirmation
  requirement; execution requires `--confirm-external-tool-fenced` on the
  execute command. Source confirmation flags are never copied into
  execution authority.
- Plan file: strict version-1 JSON. Unknown or duplicate fields, bad types,
  non-UTF-8, and files over the documented 128 KiB bound are rejected with
  fixed safe errors that never echo file bodies or values. The execute
  read is itself bounded (at most 128 KiB + 1 byte is read), so an
  oversized file is refused BEFORE any database access, and a missing or
  unreadable file produces a fixed error without the path. The plan never
  contains key material, hashes, provider environment names or base URLs,
  raw metadata, or usage.
- Consumable dry-run: a SUCCESSFUL dry-run always yields an executable
  plan. Before the file is written, the built document is re-validated
  with the SAME strict version-1 schema and bounds that execute re-parses
  (no second duration rule): an out-of-bounds build (for example a
  duration-from-now over the documented 1,000-year maximum) fails with a
  fixed safe error - no plan file, no audit, no mutation. Normal short
  durations, naive-as-UTC valid absolute windows, and copy-source-expiry
  remain usable.
- Retry safety (no schema): the stable `operation_uuid` plus a narrowly
  typed receipt on the NEW target key's metadata deduplicates. The
  receipt lookup is namespaced by `(source, operation)` ONLY and is
  INDEPENDENT of the (mutable) target selection: a retry that changes the
  target owner or cohort still finds the completed operation. Repeats
  compare the FULL business identity (source public key ID, source
  fingerprint, canonical policy fingerprint, target owner, target cohort,
  all four validity parameters including the reviewed copy-source-expiry
  source expiry, and the fenced-confirmation requirement): an exact
  repeat returns `already-applied` with safe IDs - never a new key,
  secret, send, or plaintext; a same-operation changed plan (public ID,
  reviewed expiry, policy, target, validity, or confirmation) is refused;
  a receipt a completed operation no longer backs (including legacy
  objective-198-a/b receipts lacking any identity member) is refused
  rather than adopted; and MORE THAN ONE match (the lookup is bounded to
  two) is refused as ambiguous rather than silently choosing one. Only
  the explicitly inert preview block may vary. A completed operation
  stays identifiable even if the source is later edited or becomes
  ineligible: an ACTUAL source edit changes the source fingerprint (a
  fresh plan would be stale) but the ORIGINAL exact repeat still dedups
  to the same target.
- Transaction: key creation, one-time secret, optional pending delivery,
  receipt, and audits commit atomically in one caller-owned transaction; a
  late audit/receipt/delivery-preparation failure rolls back ALL new rows.
  Nothing (no SMTP, no output file, no enqueue) happens before commit.
- Enforced isolation boundary: PostgreSQL READ COMMITTED is REQUIRED, not
  only supported. Before any write, the execution reads
  `current_setting('transaction_isolation')` (after the source-row lock);
  a pre-established REPEATABLE READ snapshot - or any other level - is
  refused with a fixed safe error and the operation commits nothing. The
  existing source-row `FOR UPDATE` lock serializes same-source executions
  and the receipt query after the lock sees the prior commit.
- Post-commit output recovery: the commit happens BEFORE any output
  channel (secret file, send-now SMTP, Celery enqueue). If a selected
  channel fails AFTER commit, the clone is NOT rolled back; the CLI
  reports safe recovery information (target key, one-time secret, and
  delivery IDs plus fixed guidance) and exits nonzero. The one-time
  plaintext cannot be recovered: use `slaif-gateway email
  send-pending-key --one-time-secret-id <uuid>` for a still-unconsumed
  pending delivery, otherwise rotate. Re-executing an EXACTLY repeated
  plan never clobbers an existing output file: the repeat reaches
  receipt deduplication before any file channel.
- No plaintext recovery: the one-time plaintext is unrecoverable after
  first output, and repeats never recover or re-send it. A still-unconsumed
  pending delivery is sent with `slaif-gateway email send-pending-key
  --one-time-secret-id <uuid>`; otherwise rotate the key. There is no
  exactly-once SMTP promise.

### Typed key-policy configuration (`--policy-file`)

`keys create` and `keys policy update` accept a bounded versioned policy
file (`--policy-file`, at most 64 KiB, strict JSON). The file is the ONLY
source of policy configuration when provided: combining it with any
explicit policy flag is rejected. Identity, validity, reason/actor,
secret-output, and delivery flags may accompany the file, and the explicit
`--confirm-external-tool-fenced` control may supply the acknowledgement when
the file omits its own `confirm_external_tool_fenced` field (the file's own
field wins when present). `keys policy export` renders the stored key policy
as the same version-1 document, so an export can be reviewed and consumed by
create or update on a COMPATIBLE target: a target whose stored
client-module binding conflicts with the exported identity is rejected
atomically by the migration law. The rendered document always satisfies
the version-1 file contract (it is re-parsed by the same strict schema);
stored policy it cannot administer fails the export explicitly.

Schema version 1 fields (unknown fields, duplicate keys, and NaN/Infinity
are rejected; all errors are fixed safe messages that never echo file
bodies or operator-supplied values):

| Field | Semantics |
| --- | --- |
| `schema_version` | Exactly `1` (integer). |
| `allowed_models` / `allowed_endpoints` | List of values; explicit `null` is the empty list. Omitted on update: preserve. |
| `allow_all_models` / `allow_all_endpoints` | Boolean. Omitted on update: preserve. |
| `allowed_providers` | `null` = UNRESTRICTED; `[]` = deny ALL providers; list = allow-list. Omitted on update: preserve. Never truthiness-collapsed. |
| `responses_policy` | `null` clears the block; an object is a COMPLETE replacement block (strictly validated; no partial member merge). Omitted on update: preserve. |
| `rate_limit_policy` | `null` clears every per-key override (inherit the deployment); an object carries nullable members `requests_per_minute`, `tokens_per_minute`, `max_concurrent_requests` (positive integers or `null`; `null` inherits that member). An omitted member keeps the current override (per-member patch); the historical `concurrent_requests` spelling canonicalizes to `max_concurrent_requests`, and unknown members are rejected, never silently ignored. |
| `lazy_throttling_policy` | `null` removes the stored policy; an object is a complete block. Omitted on update: preserve. |
| `cost_limit_eur` / `token_limit_total` / `request_limit_total` | `null` = UNLIMITED for that quota. Omitted on update: preserve. |
| `chat_streaming_live_burn_policy` | Complete block only (`null` is not accepted - use `keys set-chat-streaming-live-burn` to disable). The closed member set is `version`, `enabled`, `cost_margin_eur`, `token_margin`; unknown members are rejected on file create, configuration update, and RAW stored export (fixed safe message; member names never echoed). Omitted on update: preserve. |
| `external_tool_policy` | `null` removes the fenced policy (strict bounded default); an object is a complete block. Omitted on update: preserve. |
| `confirm_external_tool_fenced` | Boolean operation acknowledgement for fenced blocks. It is an operation control, not inherited configuration: exports never emit it and an exported document never carries it into a later operation. A fresh acknowledgement (file field or explicit flag) is required whenever a fenced `external_tool_policy` block is SUPPLIED by the operation - including supplying the unchanged full-export block. Merely omitting the block while updating unrelated fields (providers, rates, quotas) does not create a new confirmation requirement. The existing finite-quota and external-tool fence guards still apply on every path. |

Create defaults differ from update preservation: on create, omitted policy
fields take the documented service defaults (unrestricted providers, no
Responses authority, deployment-inherited rates); on update, omitted fields
preserve the loaded current values. `keys policy update` with no requested
change is rejected - it never silently resets policy.

Provider flags without a file remain mutually exclusive: use exactly one of
`--allowed-provider` (repeatable), `--provider-all`, or `--provider-none`.

Default secret output on typed surfaces: with `--policy-file` or any
explicit provider flag, `keys create` requires an explicit one-time key
choice BEFORE creation - `--show-plaintext`, `--secret-output-file PATH`
(a new 0600 file), or `--email-delivery pending/send-now/enqueue`. The
pre-existing legacy flag-free `keys create` intentionally keeps its
documented default of printing the one-time plaintext key once, so the
typed surfaces are secret-guarded while that legacy exception remains
usable; do not read this as every CLI default being secret-free. The
existing `--json` guard is unchanged: JSON output never includes the
plaintext key unless `--show-plaintext` or `--secret-output-file` is
explicit.

Responses/Codex authoring (strict, fail-closed):

- Finite capability vocabulary (current runtime-known capabilities minus the
  reserved generic authority shapes `background`/`storage`/`multimodal`,
  which fail closed as positive authored grants); unknown fields and values,
  duplicates, bool/float versions, and unknown capability names are
  rejected.
- Codex prerequisite closure is enforced: `codex_client_tools` requires
  `codex_request_envelope`; `codex_streaming_tool_events` requires client
  tools; `codex_encrypted_reasoning_replay` requires the envelope;
  `codex_compaction` requires streaming tool events plus encrypted
  reasoning replay.
- Local tool types pair with reviewed capabilities: `function` requires
  `function_tools` or the Codex client-tools grant; `custom` requires
  `custom_tools` or the client-tools grant; the client-tools grant requires
  the full local tool type set.
- `client_module` is an exact registered identity
  (`id`/`version`/`fixture_sha256`); stale pins fail with a migration
  hint. A pin never grants authority by itself: an explicit block
  retaining the same pin with no or empty capabilities is a valid
  deauthorization state.
- The configured `CODEX_COMPATIBILITY_PROFILE_FILE` (when set) is
  bootstrapped in the same CLI process BEFORE pin authoring, so a fresh
  `keys create`/`keys policy update` validates pins against the configured
  profile, not the packaged default. An invalid configured profile file
  fails closed with a fixed safe message.

Client-module migration law: a key whose stored Responses block carries a
client-module binding - a currently resolvable identity (explicit registered
pin or the implicit historical five-gate shape) OR a stale/unregistered/
malformed stored pin - may only retain that exact binding through a
configuration update. Re-pinning (including straight to the current
registered identity), replacing, or clearing a bound policy is refused with
migration guidance; only a genuinely unbound key may be initially bound.
Use the reviewed client-module migration workflow for identity changes.

Examples (fictional identities):

```bash
# Deny all providers for one key, preserving everything else
slaif-gateway keys policy update <gateway-key-id> --provider-none --reason "provider audit"

# Full typed create from a reviewed policy file
slaif-gateway keys create --owner-id <owner-uuid> --valid-days 30 \
  --policy-file ./key-policy.json --reason "onboarding" \
  --secret-output-file ./new-key.secret

# Export, review, and apply only a provider change
slaif-gateway keys policy export <gateway-key-id>
slaif-gateway keys policy update <gateway-key-id> --provider-all --reason "lift provider restriction"
```

`docs/cli-field-administration.md` lists which key-configuration fields the
CLI currently administers and which remain proposed for later objectives.

## Providers, routes, pricing, and FX

```text
slaif-gateway providers add|list|show|update|enable|disable
slaif-gateway providers discover-models|setup-models
slaif-gateway routes add|list|show|update|enable|disable|import
slaif-gateway pricing add|list|show|disable-model|import
slaif-gateway fx add|list|latest
slaif-gateway bootstrap openai-completions-catalog
slaif-gateway provider-catalog propose
slaif-gateway openai-assisted pricing-proposal|route-proposal
```

`providers discover-models` and confirmed `providers setup-models` can call a
configured upstream `/models` endpoint. Imports and proposal previews are local
metadata workflows unless their dedicated documentation states otherwise.
Pricing and FX rows are operator-reviewed local accounting inputs, not provider
invoice attestations.

### Provider and route configuration parity (`providers update`, `routes update`, objective 199)

Since objective 199, the CLI administers the remaining provider and route
configuration fields that previously required operator Python. Every change
is audited, row-locked, and secret-safe: no command accepts, resolves, or
prints a provider credential VALUE - only environment-variable NAMES - and
recognized secret shapes in new configuration/plan input are refused with
fixed no-echo errors instead of being emitted or silently altered. This is
known-shape protection, not universal content sanitization. Free-form READ
values (display name, base URL, notes) are projected with the same
known-shape redaction in `providers show|list` and route output; credential
environment-variable NAMES are never masked.

**Provider configuration**

```text
# Create metadata (stays DISABLED until explicitly enabled)
slaif-gateway providers add --provider svc-a --api-key-env-var SVC_A_API_KEY \
  --kind module --base-url https://svc-a.internal \
  --timeout-seconds 180 --max-retries 0 --reason "add module backend"

# Partial update: omitted fields preserve the fresh current values
slaif-gateway providers update svc-a --reason "raise timeout" --timeout-seconds 300
```

- `providers add` gained `--timeout-seconds` (positive whole seconds,
  default 300), `--max-retries` (non-negative, 0 valid, default 2), and
  `--actor-admin-id`. Deliberate default change: an omitted
  `--enabled/--disabled` at creation now leaves the provider DISABLED; only
  an explicit `--enabled` activates a new provider. Recognized secret
  shapes in `--display-name`, `--base-url`, `--notes`, or `--reason` are
  refused before any database access with the SAME fixed no-echo error as
  update (known-shape protection, not universal sanitization); safe
  environment-variable NAMES and ordinary text remain literal.
- `providers update PROVIDER` partially updates display name, base URL,
  kind, credential environment-variable name, timeout, retries, and notes.
  `--reason` is required and must be nonblank. Recognized secret shapes in
  `--display-name`, `--base-url`, `--notes`, or `--reason` are refused
  before any mutation with a fixed no-echo error. The row is locked FOR
  UPDATE before the complete service input is assembled, so omission means
  preserve and a stored zero retry count survives. There is no `--enabled`
  flag: use `providers enable|disable`. `--notes` and `--clear-notes` are
  mutually exclusive (refused before mutation). `--clear-notes` uses the
  EXPLICIT clear intent through the shared audited service: the REAL prior
  value is captured before mutation, the repository stores NULL within that
  same operation, and the ONE audit record carries the real old notes value
  and the real new null (no direct pre-clear, no second audit, no nested
  write). Existing shared callers keep the pre-existing default
  (`notes=None` means preserve), so the admin form and all other shared
  behavior are unchanged.

**Route creation with a strict capabilities file**

```text
slaif-gateway routes add --requested-model zap-it-1 --match-type exact \
  --provider zap-it --upstream-model zap-it-1 \
  --endpoint /v1/chat/completions --no-streaming --disabled \
  --capabilities-file /tmp/zap-it-route-caps.json
```

- `routes add` gained `--capabilities-file PATH` (a COMPLETE strict
  capabilities document, at most 64 KiB, read at cap+1 before parse),
  optional `--reason`, and `--actor-admin-id`. `--notes` carrying a
  recognized secret shape is refused before any database access.
  Deliberate default: a capabilities-file preparation stays DISABLED
  unless the operator explicitly passes `--enabled`; flag-free route
  creation keeps the historical enabled default.

**Reviewed two-step route updates**

```text
# 1) Plan: READ-ONLY. Writes a NEW 0600 plan file (never overwritten).
slaif-gateway routes update <route-uuid> --dry-run /tmp/route-plan.json \
  --codex-max-output-tokens 400000

# 2) Review the file, then apply it UNCHANGED in one transaction.
slaif-gateway routes update <route-uuid> --execute /tmp/route-plan.json \
  --reason "raise reviewed ceiling"
```

- Edit flags exist ONLY for `--dry-run`: `--codex-context-window-tokens`,
  `--codex-default-max-output-tokens`, `--codex-max-output-tokens`,
  `--media-image-tokens`, `--media-video-tokens`, `--media-video-frames`,
  repeatable `--chat-capability NAME=true|false` and
  `--responses-capability NAME=true|false`,
  `--completion-service-profile ID` / `--clear-completion-service`
  (mutually exclusive), and the route fields `--requested-model`,
  `--match-type`, `--endpoint`, `--provider`, `--upstream-model`,
  `--priority`, `--visible/--hidden`, `--streaming/--no-streaming`,
  `--notes` / `--clear-notes`. Omission means preserve, never
  false/null/default; only explicit leaves merge, all siblings are deeply
  preserved. `--capabilities-file` is a clearly documented COMPLETE
  replacement and cannot be combined with partial capability flags
  (refused); file+flag ambiguity is always rejected.
- `--execute PATH` applies the reviewed file exactly and requires a
  NONBLANK, secret-shape-guarded `--reason`; edit flags on execute (mixed
  mode) are refused. A successful dry-run always writes a plan whose built
  document first re-parses with the same strict schema under the SAME
  configured installation ceilings and profile directory (schema version
  1, every top-level field explicit; omitted edits snapshot the fresh
  current values; `capabilities_mode` is `unchanged`, `partial`, or
  `full-replacement`), then writes exclusively with mode 0600 and no
  overwrite. Execute reads are bounded at the 128 KiB plan cap + 1 byte
  before parse.
- The plan records `expected_route_id` and
  `expected_configuration_fingerprint`: the digest is SHA-256 over the
  ROUTE UUID plus the reviewed configuration fields (requested model, match
  type, endpoint, provider, upstream model, priority, visibility, streaming,
  enabled, capabilities, notes), so an unchanged expected pre-state can
  never validate against a DIFFERENT route that happens to carry identical
  configuration; only timestamps are excluded. The digest is staleness data
  only, never credential or replay authority.
- The plan also BINDS the proposed destination provider:
  `expected_provider_id` and `expected_provider_context_fingerprint`
  (SHA-256 over kind, base URL, credential environment-variable NAME,
  timeout, and retry count; display fields and the enabled flag excluded on
  purpose). The destination is the `--provider` edit when given, otherwise
  the route's current provider. Plans written before the 199-b plan schema
  (without these binding fields) fail strict parsing; rerun the dry-run.
- Execute law: the CLI route ARGUMENT is bound to the reviewed plan (a
  plan can never be applied to a different route). The route row is locked
  FOR UPDATE first, then the PROPOSED destination provider (deterministic
  lock order: route, then provider). The fresh route identity, enabled
  state, and route-bound configuration fingerprint - then the destination's
  continued existence, provider identity, and context fingerprint - are
  revalidated against the plan. Any mismatch is refused as stale with ZERO
  writes and ZERO audits, so a repeated apply of an already-applied plan is
  refused stale, never re-mutated. The merged candidate is canonicalized
  with the same pure normalizer the service uses (installation ceilings
  included) and revalidated against the FRESH provider row (kind, the
  completion zero-retry rule, the configured profile directory) before ONE
  audited `ModelRouteService.update_model_route` call in the caller
  transaction; a transaction or audit failure rolls back the whole change.
- No-op law: a plan whose complete proposed state already equals the fresh
  locked row (possible only when it changed nothing) returns the row with
  ZERO writes and ZERO audits.
- The plan preview block renders the CANONICAL current and proposed
  configurations - the exact stored shape the service will write, defaults
  included - plus the changed canonical field names; the preview is review
  data, never execution authority. The plan preview is configuration review
  only: the gateway Codex context/admission ceiling, the configured
  default/max output reservation, the physical model capacity, and the
  client-advertised context are distinct values, and unknown physical or
  client values remain unknown. No credential, model, or SMTP
  qualification is performed by a plan.
- All capabilities and plan validation (capabilities files, plan
  read/write round-trips, preview, execute) uses the ACTUAL installation
  ceilings from the current settings (for example
  `EXTERNAL_TOOL_MAX_PROVIDER_TOOL_CALLS_PER_REQUEST`) - never
  defaulted-away limits - and completion profiles resolve through the SAME
  configured profile directory the runtime uses: the bundled directory, or
  the absolute, non-symlink operator directory configured through
  `COMPLETION_SERVICE_PROFILE_DIR` (files must be regular, non-symlink,
  0600, and at most 64 KiB; when an operator directory is configured, the
  bundled directory is not visible). Every candidate (new route and
  reviewed update) must additionally resolve, through the EXISTING pure
  server-module resolution, to a supported server module for the
  provider's actual kind/slug/capabilities - an unregistered
  `module`-kind provider with no selector and no legacy binding is
  refused before any write or audit. A completion route - explicit
  `completion_service` selector OR the implicit legacy profile binding for
  the provider slug - requires a `module`-kind provider on the chat
  completions endpoint with `max_retries=0` (the completion adapter's
  zero-retry rule), the profile's public/upstream model must match the
  route's requested/upstream model, and the configuration must not
  advertise streaming (the route `supports_streaming` flag or the
  `chat_completions.chat_streaming` capability): the completion adapter
  refuses stream values other than `false`, so reviewed streaming
  declarations are refused rather than silently stripped. These are
  configuration-time checks: they validate configuration, not credential
  or model readiness, and perform no credential loading, adapter
  construction, or network call.

## Usage, email, and reconciliation

```text
slaif-gateway usage summarize|export|live-burn-summary
slaif-gateway email test|send-pending-key|list|show
slaif-gateway quota list-expired-reservations
slaif-gateway quota list-provider-completed-recovery
slaif-gateway quota list-external-tool-fences|list-external-tool-holds
slaif-gateway quota reconcile-expired-reservations|reconcile-reservation
slaif-gateway quota reconcile-provider-completed|reconcile-external-tool-hold
```

Reconciliation commands default to inspection or dry-run where documented.
Execute modes require explicit confirmation and an audit reason. They use
PostgreSQL evidence and do not call providers to reconstruct an outcome.

### Email delivery inspection and safe retries

`email list` and `email show <delivery-uuid>` are READ-ONLY inspection
commands. They never decrypt one-time secrets, render or send email,
consume material, insert audit rows, or enqueue work; an empty or missing
result is distinct from a store-unavailable or invalid-parameter error,
and invalid inputs fail nonzero without echoing supplied values.

```text
slaif-gateway email list [--delivery-id <uuid>] [--key-id <uuid>]
                         [--owner-id <uuid>] [--owner-email <exact email>]
                         [--status pending|sending|sent|failed|ambiguous|cancelled]
                         [--created-from <aware-UTC ISO>] [--created-until <aware-UTC ISO>]
                         [--limit 1..100 (default 50)] [--offset 0..1000000]
                         [--json]
slaif-gateway email show <delivery-uuid> [--json]
```

- Filters combine with SQL `AND` BEFORE deterministic
  `(created_at DESC, id DESC)` paging; at most `limit + 1` rows are
  fetched, and `--json` reports `items`, `limit`, `offset`, `has_more`,
  and `next_offset` (no unbounded all-history materialization).
- `--owner-email` is EXACT after the same strip/lower normalization as
  owner management — never substring identity. `--status` accepts only the
  six PERSISTED statuses; `queued` is not a database status and is
  rejected.
- Time bounds are explicit aware UTC instants (naive or reversed windows
  are refused). Bounds are inclusive.
- Output is allowlisted metadata only: delivery/owner/key/one-time-secret
  UUIDs, the recorded recipient, persisted status, created/sent/failed
  timestamps, the service-derived secret lifecycle/sendability, and the
  safe last-recorded failure (a finite known email error code with action,
  time, and provenance `last recorded audit error`). No subject, rendered
  or template body, raw error prose, SMTP/provider message IDs, encrypted
  payload/nonce, plaintext key, hash/HMAC, or credentials.
- The last-recorded failure is the LATEST audit row with action
  `email_key_failed` or `email_key_ambiguous`, exact
  `entity_type = email_delivery` and exact delivery UUID, ordered by
  `created_at` then `id`. Unknown/missing codes report `unavailable`; a
  `sent` row can retain a historical failure, labeled by provenance, never
  as the current attempt's error.
- `email show` reports the secret lifecycle with the existing meanings:
  `present` (pending usable material — NOT proof the email was sent),
  `consumed`, `expired`, `unavailable`, plus `can_send` and a fixed
  blocking reason when not safely sendable.
- The reported recipient is PREPARED-ATTEMPT metadata: an attempt prepared
  by this code records, in the existing sending commit, the exact
  destination prepared for that attempt (the current owner email), so
  inspection reflects the recipient prepared for THAT attempt. Untouched
  older rows and rows that were never prepared may retain creation-time
  metadata, and the actual historical destination of a pre-upgrade attempt
  is unknown and is never reconstructed or backfilled. The field never
  infers or rewrites historical destinations and proves nothing about SMTP
  acceptance or mailbox arrival.

`email send-pending-key` (the sender action) additionally accepts:

```text
--retry-failed            Explicitly retry an existing FAILED delivery
--reason <text>           Bounded nonblank audit note (UTF-8, <= 1024 bytes)
```

- A selected delivery whose persisted status is `failed` requires
  `--retry-failed` AND a nonblank `--reason` in BOTH synchronous
  (`--send-now`) and `--enqueue` modes; the checks run BEFORE any
  send/queue. `--retry-failed` itself requires `--email-delivery-id`, and
  a non-failed selected row refuses the flag.
- `--reason` values containing recognized credential patterns are refused
  without echo whenever the reason is persisted (retry in either mode,
  or enqueue intent).
- Enqueue mode records a bounded safe enqueue-REQUEST intent audit
  (action `email_key_enqueue_requested`: selected IDs, actor, reason, and
  explicit intent) via the existing audit repository BEFORE dispatch; the
  commit must succeed first, and an audit failure prevents dispatch. The
  one-time secret is attributed through the safe reference field
  `one_time_reference_id` (the secret-bearing key name is dropped by the
  global durable metadata sanitizer). The Celery task payload remains
  EXACTLY the existing three UUIDs — no reason, body, secret, boolean,
  policy, or context crosses the broker; the worker revalidates actual
  sendability at execution.
- `queued` in the CLI result means broker submission only — NOT a
  persisted delivery status and NOT a worker acknowledgement. `sent`
  means recorded SMTP acceptance/finalization — NOT confirmed inbox
  arrival. A queue failure after the committed intent is reported
  nonzero and leaves the honest intent; it never changes the delivery to
  sent/queued or mutates/consumes the secret.

## Codex and diagnostics

```text
slaif-gateway codex inspect|profile
slaif-gateway codex upgrade-key-module
slaif-gateway codex rollback-key-module
slaif-gateway codex presets
slaif-gateway codex export-preset
slaif-gateway codex inspect-profile-file
slaif-gateway codex show-profile
slaif-gateway codex migrate-key-profile
slaif-gateway codex replay inspect
slaif-gateway codex replay extend
slaif-gateway secrets generate hmac|admin-session|one-time
slaif-gateway secrets validate-env
```

Codex commands apply only to explicitly registered qualification profiles.
Configuration validation reports bounded names/status, never secret values.

`codex upgrade-key-module <key-uuid> --target {0149-v5,0162-v1,0162-v2}
--reason ... [--actor-admin-id <uuid>] [--apply] [--json]` and `codex
rollback-key-module <key-uuid> --from-target {0149-v5,0162-v1,0162-v2}
--reason ... [--actor-admin-id <uuid>] [--apply] [--json]` are the bounded
audited client-module migration pair for pinned Codex keys. Only the six
legal edges (0.149-v4 → 0149-v5, 0149-v4 → 0162-v1, 0162-v1 → 0162-v2, and
the three reverse edges) are accepted; a 0.149-v4 key reaches 0162-v2 only
through the explicit two-hop sequence while quiesced. Any other current
module identity or unsupported selector fails closed with a fixed safe
error. The default is a dry run;
`--apply` writes the `client_module` compatibility metadata and one audit
record in one atomic PostgreSQL transaction. The commands change no schema,
no quota, no key policy, and no route or pricing data. Unexpected failures
render a fixed generic safe error and never echo exception details.

`codex presets [--json]` lists validated shipped compatibility presets.
`codex export-preset <name> --output <path>` copies one to a new operator-owned
file without overwriting or activating it. See
[external preset configuration](client-compatibility-presets.md).

`codex inspect-profile-file <path> [--json]` validates a candidate Codex
0.162 compatibility profile DATA file completely offline (bounded regular
UTF-8 JSON, data revision >= 3, finite validated vocabulary, hard ceilings)
and prints safe facts or a fixed safe rejection with a code; it never
touches the database, network, or the active process profile, so it works
even when a configured active profile file is invalid. `codex
show-profile [--json]` shows the active profile snapshot of this CLI
process bound at bootstrap; a running HTTP server keeps its own bootstrap
snapshot until restart, so the output describes this CLI process only.
`codex migrate-key-profile <key-uuid> --from-version <rev> --from-digest
<hex> --reason ... --target {active,0162-v1,0162-v2}
[--actor-admin-id <uuid>] [--apply] [--json]` moves one exact key between
the active bootstrap profile snapshot and the frozen 0162-v1/0162-v2
legacy tuples: the explicit source must equal the key's current pin (legacy
1/2 sources require the frozen literal digests), the default is a dry run,
`--apply` writes the metadata and one audit record in one row-locked
transaction, a repeated exact target is a no-op with no extra audit, and
same-revision/different-digest drift or a missing configured active profile
fails closed with a safe error.

`codex replay inspect [--key-id <uuid> | --cohort-id <uuid> |
--all-active] [--created-from <utc>] [--created-until <utc>] [--json]`
is a READ-ONLY summary of retained Codex replay references for exactly
ONE explicit scope (the three scope options are mutually exclusive;
`--all-active` selects every currently active key; there is no
bearer-secret lookup and no unscoped database-wide mode). The optional
UTC creation bounds are inclusive/exclusive and validated for order.
The output is a stable safe summary - selected key/reference counts,
active/expired counts, stored creation/expiry ranges, bounded
route/public-model groupings, and fixed exclusion-reason counts - that
distinguishes expiry eligibility from actual client/model readiness.
It never outputs provider item/call IDs, HMAC digests, compaction
ciphertext or content, raw stored JSON, replay-row UUIDs, secrets, or
tool payloads, and it writes nothing (no audit, no rows, no provider
or credential contact).

`codex replay extend [--key-id <uuid> | --cohort-id <uuid> |
--all-active] [--ttl-seconds <1..31536000>] [--include-expired]
[--created-from <utc>] [--created-until <utc>] [--output <path> |
--execute <path>] [--reason <text>] [--actor-admin-id <uuid>] [--json]`
is the two-step reviewed expiry-extension operation. `--output` runs a
READ-ONLY dry run that writes a NEW strict version-1 non-secret plan
file (mode 0600, at most 32 KiB, never overwritten; the file is read
in a bounded stream of at most 32 KiB + 1 bytes, and oversize,
malformed, or over-deep JSON as well as recognized secret shapes are
refused with fixed no-echo errors). The dry-run output reports
`new_expiry_range` as the range of ACTUAL post-apply expiries of the
eligible rows, i.e. `max(existing expiry, original created_at +
selected TTL)` per row - never a shortening. `--execute <path>
--reason` applies that previously reviewed plan file ONLY: every
preview/edit flag (the scope selectors, `--ttl-seconds`,
`--include-expired`, `--created-from`/`--created-until`) is refused
with a fixed no-echo error BEFORE the plan file is read or any
database access, so a conflicting invocation can never silently apply
the plan while ignoring supplied edits. The
selected lifetime is the explicit `--ttl-seconds` or, when omitted, the
ACTUAL configured `CODEX_REPLAY_REFERENCE_TTL_SECONDS`; both are
rendered distinctly and no global setting is modified. Extension is
monotonic and expiry-only: the target is the ORIGINAL STORED
`created_at` + selected TTL (never execute-now + TTL), already-later
expiries stay unchanged, expired rows require explicit
`--include-expired`, and `created_at` is never rewritten. Execute locks
the selected keys then their reference rows, re-resolves the exact
reviewed scope membership AFTER the key locks and AGAIN after the
reference-row locks, and re-derives eligible counts AFTER all locks
(the saved plan's fingerprints and counts are public optimistic
guards, not signed authority - drift is refused stale with zero
writes). Before any write, the reviewed post-state fingerprint AND
the saved report descriptors (old/new expiry ranges, exclusion
counts) are re-verified against the fresh locked rows under the
SELECTED TTL, so a TTL-only or descriptor-only edit of an otherwise
valid plan is refused stale - including on an already-applied repeat
whose selected TTL would require a different post-state, while an
edit with no actual post-state effect keeps the honest no-op.
Execute then updates only `expires_at` of exactly the eligible
reviewed rows, and records ONE bounded audit; the execute JSON
labels its exclusion/range descriptors as reviewed-plan metadata
(`range_descriptors_source: reviewed_plan`) while the
applied/already-applied/updated fields are derived from the actual
operation. A repeated apply is recognized as already-applied
with no duplicate audit; a zero-diff apply makes no writes or audits;
a transaction or audit failure rolls back everything. Ceilings: 1,000
selected keys, 50,000 inspected references, 100 route/model groups;
oversized scopes are refused with a fixed safe narrowing instruction,
never silently truncated. There is no expiry-shortening or rollback
command; backup/restore is the normal recovery responsibility and
`inspect`/dry-run is how an operator re-previews after a failure. No
schema change, no quota or key-policy change, no runtime replay
behavior change.

```text
slaif-gateway request-capture arm|status|stop|cleanup|inspect
```

The operator request-capture facility (default OFF; see
[configuration.md](configuration.md#operator-request-capture) and
[runbooks/incoming-request-capture.md](runbooks/incoming-request-capture.md))
exposes five bounded commands. They operate on the shared local capture
manifest and never construct the HTTP app or touch the database; they fail
with a fixed safe error when the facility is not enabled in this process's
settings.

- `request-capture arm --endpoint /v1/responses [--key-uuid <uuid>]
  [--count <n>] [--ttl-seconds <s>]` arms one finite, expiring capture
  window. `--key-uuid` filters on the verified gateway key UUID; omitted
  options fall back to the configured defaults (count 1, TTL 300 s, capped by
  `REQUEST_CAPTURE_MAX_COUNT` / `REQUEST_CAPTURE_MAX_TTL_SECONDS`).
- `request-capture status` lists sessions with remaining count, state
  (active / exhausted / expired / stopped), and total reserved storage.
- `request-capture stop [--session-id cap-<hex32>]` stops one session (or
  all), ending collection without deleting artifacts.
- `request-capture cleanup [--session-id cap-<hex32>]` deletes a session's
  owned capture/record artifacts and releases its storage quota. It removes
  only recognized owned artifact names and preserves anything else.
- `request-capture inspect --request-id gw-... [--decode]` locates and prints
  one specific capture + record pair by the `X-SLAIF-Diagnostic-ID`. Reads
  are bounded (no-follow regular owned files, size-capped); `--decode`
  renders the base64 fields as text while retaining the original base64, and
  labels non-UTF-8 values as a lossy view.

Unexpected failures render a fixed generic `command_failed` error and never
echo exception details; known facility errors keep their fixed reason codes.

```text
slaif-gateway diagnostics status|request show|cleanup
```

The content-free request-failure diagnostics facility (default OFF; see
[configuration.md](configuration.md#request-failure-diagnostics-default-off))
exposes three read/operate commands over the shared typed service. Stored
fields are content-free, bounded, and secret-free by the service projection,
so the CLI echoes exactly the retained typed fields and nothing else. A
lookup ID never establishes authentication authority.

- `diagnostics status [--json]` reports recording status and the retained-
  dataset summary, distinguishing recording-disabled, store-unavailable,
  and empty retained dataset; it works whether or not recording is enabled.
  `recording_enabled` is the setting loaded by the CALLING CLI process,
  not a live inspection of the API workers (no worker heartbeat or config
  registry exists): run it in the intended deployment environment and keep
  the workers on consistent, reloaded settings; retained rows alone cannot
  prove the current recording state of any worker.
- `diagnostics request show --request-id ID [--namespace any|gateway|client]
  [--json]` resolves ONE retained record by recorded client or gateway
  request ID. Client IDs are nonunique (and can equal another request's
  gateway ID): the namespace is explicit (`any` by default; never inferred
  from a prefix), ambiguous matches are bounded at 100 candidates with an
  honest count/overflow and the gateway diagnostic IDs offered for
  disambiguation. Outcomes are typed (`found` / `ambiguous` / `not_found` /
  `unavailable`); exit 0 for the first three, exit 1 for an unavailable
  store or configuration failure.
- `diagnostics cleanup [--json]` physically prunes ONE bounded batch of
  expired records from the diagnostics table only. There is no background
  expiry daemon: idle storage needs repeated cleanup (or the bounded prune
  that runs on writes). Exit 0 on a completed operation (store-unavailable is
  reported in the payload as exit 1); 1 on configuration or unexpected
  failure.

No record editing, raw SQL, secret recovery, or audit-log retention changes
exist in this surface.

## Catalog refresh (collect, review, verify, apply)

Bounded catalog refresh: bounded live official-source collection, one typed
proposal bundle, one safe baseline, one sealed one-page report, and the one
explicit atomic `apply` of a reviewed run. The one-command administrator
wrapper `slaif-catalog-refresh` (bootstrap/refresh, built-in read-only
watchdog, exact child exit codes) plus the lower-level `collect`, `review`,
`verify`, read-only `export-baseline`, mutating `apply`, and read-only
`status` commands — Codex research is opt-in (`--research`) and NOT_RUN by
default. Full semantics, the source registry, policy thresholds, sealing,
apply ordering, and exit codes live in
[Catalog refresh (collect, review, and
verify)](catalog-refresh.md).

```bash
# ONE refresh, ONE report: the supported administrator entry point.
# Validates the mode before spawning, runs the read-only collect under the
# standard watchdog (300 s default + 5 s KILL grace; --timeout/--kill-grace
# must be positive), preserves the child exit code, never applies.
slaif-catalog-refresh --mode bootstrap \
  [--providers openai,openrouter] [--models a,b] \
  [--run-root P] [--seal-key P] [--json] \
  [--timeout 300] [--kill-grace 5]

# Refresh against the existing catalog (live read-only baseline export;
# bootstrap is never combined with --baseline-file or --db-url)
slaif-catalog-refresh --mode refresh --db-url postgresql+asyncpg://user@host:5432/dbname \
  [--providers openai,openrouter] [--models a,b] \
  [--run-root P] [--seal-key P] [--json]

# Refresh with the opt-in isolated Codex research fallback
slaif-catalog-refresh --mode refresh --db-url "$DATABASE_URL" \
  --research --research-cli-bin /path/to/codex \
  --research-endpoint https://inference.example.test/v1 \
  --research-model gpt-example --research-auth-env SLAIF_RESEARCH_UPSTREAM_KEY \
  [--research-timeout 120]

# Lower-level entry point: collect the official catalogs now (first install,
# both providers, all eligible models)
slaif-gateway catalog-refresh collect --bootstrap

# Refresh collection against an exported baseline with an explicit selection
slaif-gateway catalog-refresh collect --refresh \
  --providers openrouter --models synth/alpha,synth/beta \
  --baseline-file /path/to/baseline.json

# Refresh collection with the isolated Codex semantic research fallback
# enabled (deterministic parsing stays first; only eligible unresolved
# facts are research candidates; the researcher's only model contact is
# the operator-configured HTTPS endpoint through a task-owned relay)
slaif-gateway catalog-refresh collect --refresh \
  --baseline-file /path/to/baseline.json \
  --research \
  --research-cli-bin /path/to/codex \
  --research-endpoint https://inference.example.test/v1 \
  --research-model gpt-example \
  --research-auth-env SLAIF_RESEARCH_UPSTREAM_KEY \
  [--research-timeout 120]

# Review a proposal bundle against an exported baseline (sealed run output)
slaif-gateway catalog-refresh review /path/to/catalog-refresh.json \
  --baseline-file /path/to/baseline.json

# Review against a live read-only database snapshot
slaif-gateway catalog-refresh review /path/to/catalog-refresh.json \
  --db-url postgresql+asyncpg://user@host:5432/dbname

# First install: explicitly empty baseline
slaif-gateway catalog-refresh review /path/to/catalog-refresh.json --first-install

# Verify a sealed run directory against the runner-owned key
slaif-gateway catalog-refresh verify --run-dir /path/to/run --seal-key ~/.local/state/slaif/catalog-refresh/seal.key

# Export a read-only consistent baseline document
slaif-gateway catalog-refresh export-baseline --out /path/to/baseline.json --db-url postgresql+asyncpg://user@host:5432/dbname

# Apply the reviewed plan of one sealed READY/READY_WITH_WARNINGS run
# atomically (explicit operator confirmation; one effective instant; one
# durable application record). Never wrap this in the collect watchdog.
slaif-gateway catalog-refresh apply --run-dir /path/to/run \
  --db-url postgresql+asyncpg://user@host:5432/dbname \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key \
  --confirm --actor "ops:alice" --reason "apply reviewed openrouter refresh" \
  [--admin-id UUID] [--ack-warnings new_model_exposure] [--json]

# Read-only committed-outcome visibility (lock-free; never mutates or
# blocks writers)
slaif-gateway catalog-refresh status --run-dir /path/to/run \
  --db-url postgresql+asyncpg://user@host:5432/dbname \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key [--json]
```

Collect exit codes: 0 READY, 10 READY_WITH_WARNINGS, 20 BLOCKED (a blocked
run is always published, labeled by the path actually reached:
`collection not started` when the baseline failed before any retrieval,
`collection attempted and failed before completion` when the retrieval
attempt failed, or the `live collection` wording after a completed
collection, including semantically blocked collects), 65 data error where
no blocked run is published (e.g. an unreadable or invalid
`--baseline-file`), 2 usage error.
Under the documented watchdog prefix a timed-out collect exits non-success
(124 on the TERM timeout, 137 after the KILL grace for a TERM-ignoring
process) and publishes no run: the collect writes nothing during the fetch
phase, publication is one atomic rename at finalization only, so an
interrupted run never reports a fresh READY and never overwrites an older
review. Direct raw collect without the watchdog may exceed the 120-second
cooperative collection target during blocked DNS or a continuous slow
stream (documented limit; no hard total bound is claimed). Review exit codes: 0 READY, 10
READY_WITH_WARNINGS, 20 BLOCKED, 65 data error, 2 usage error. Verify: 0 valid, 30 invalid (including a missing,
non-directory, or symlinked run directory with an otherwise valid key),
65 data error (missing or unsafe seal key; verify never creates keys).
Export-baseline: 0 written, 65 data error (never overwrites output, never
bootstraps empty). Apply: 0 committed (or `already_committed` for a
same-bundle retry, which returns the prior record and never overwrites),
10 unacknowledged apply-time findings (pass each code to `--ack-warnings`),
20 plan not applicable (`apply_state_not_applicable`,
`apply_freshness_blocked`, `apply_no_plan`, `apply_plan_unsupported`,
`apply_plan_mismatch`), 30 seal/authentication failure (no database contact
made), 65 blocked execution or data error (`apply_target_mismatch`,
`apply_bootstrap_not_empty`, `apply_baseline_stale`, `apply_admin_unknown`,
`apply_duplicate_record`, `apply_supersession_guard_failed`, `apply_database_error`,
missing `--confirm`, or blank `--actor`/`--reason`). Status: 0 (committed or
not — the fact is reported), 30 seal/authentication failure, 65 data error.

Filesystem inputs and outputs are handled by a descriptor-anchored,
symlink-free boundary: symlinked bundle/baseline/key paths, FIFOs and
other special files, oversized or growing inputs, and — for the writing commands — run
roots or key parents (`review`) and the output parent (`export-baseline`)
writable by group or other are refused with exit 65
and a safe error that does not echo input content; a symlinked run
directory makes `verify` invalid (exit 30). Runs are published atomically
new-only and never overwritten; `export-baseline` writes only to a
new output path. Full contract:
[Catalog refresh (collect, review, and verify)](catalog-refresh.md#filesystem-trust-contract).

The three review baseline inputs are distinct execution paths with
distinct SQL evidence: `--db-url` performs the live read-only export
itself (SQL executed during this review), `--baseline-file` consumes a
supplied document (SQL was executed historically at that document's export
time, not during this review), and `--first-install` is the explicit empty
baseline (no database read). A label or boolean in the bundle cannot claim
a capture path. `export-baseline` writes one coherent `REPEATABLE READ`
snapshot of the four allowlisted tables, retaining the recognized nested
capability contracts and the allowlisted monetary metadata; it never
writes to the database.

### Offline source input contract

For `review`, the bundle's `sources` entries are replayed offline, never
fetched (a bundle produced by `collect` additionally carries the measured
collection identity, which `review` re-verifies; see
[catalog-refresh.md](catalog-refresh.md#collection-versus-replay-validation-re-verification)). The
report scope is runner-selected: a `review` of a previously collected
bundle is `supplied_collection`, never `live_collection` — the retrieval
claims stay the supplied record's. Only
the registered (provider, source kind) pairs are parsed deterministically:
`openrouter/openrouter_models_api` (official OpenRouter `/models` shape,
per-token USD pricing), `openai/openai_models_api` (identity only),
`openai/openai_pricing_docs`, `openai/openai_models_docs` (bounded docs
tables), and `ecb/ecb_reference_xml` (EUR-based ECB reference-rate XML:
provider `ecb`, model part a currency pair such as `EUR-USD`, official ECB
host, DOCTYPE and external entities rejected). `evidence_b64` must match
the declared `content_sha256` and parse successfully to support required
facts; a matching digest of arbitrary or empty bytes is not content trust
and fails the gate, regardless of any extraction label. Each decoded
snapshot is parsed strictly (duplicate JSON keys, non-finite constants,
malformed rows, and unbounded price cells are code-only errors), and every
proposed field is validated against the sources its own fact declares for
the route's actual upstream model — an unobserved upstream, a wrong
per-field source, or a conflicting supplied observation blocks. An FX fact
binds to an official `ecb/ecb_reference_xml` quote before any currency
normalization (finite positive rate or exact reciprocal within 1e-8, quote
source declared in the fact's provenance, publication date equal to the
quote date); an unbound FX rate is never guessed or used. Selection is
reconciled per model: an unexplained eligible-model omission under an
all-eligible selection blocks; explicit subset exclusions are named in the
report. Full contract:
[Catalog refresh (offline review)](catalog-refresh.md#source-evidence-binding-offline-replay).

## Related documentation

- [CLI key-configuration field administration](cli-field-administration.md)
- [Configuration](configuration.md)
- [QUICKSTART](../QUICKSTART.md)
- [First-time operator guide](first-time-operator-guide.md)
- [Provider catalog proposals](provider-catalog-proposals.md)
- [Pricing catalog](pricing-catalog.md)
- [Key templates](key-templates.md)
- [Operator runbooks](runbooks/README.md)

## Complete command inventory

This inventory is checked against Typer registration so new commands cannot be
added without a documentation decision.

```text
slaif-gateway version
slaif-gateway admin create
slaif-gateway admin reset-password
slaif-gateway admin list
slaif-gateway bootstrap openai-completions-catalog
slaif-gateway calibration summarize
slaif-gateway catalog-refresh collect
slaif-gateway catalog-refresh review
slaif-gateway catalog-refresh verify
slaif-gateway catalog-refresh export-baseline
slaif-gateway codex inspect
slaif-gateway codex profile
slaif-gateway codex upgrade-key-module
slaif-gateway codex rollback-key-module
slaif-gateway codex inspect-profile-file
slaif-gateway codex show-profile
slaif-gateway codex migrate-key-profile
slaif-gateway codex replay inspect
slaif-gateway codex replay extend
slaif-gateway cohorts create
slaif-gateway cohorts list
slaif-gateway cohorts show
slaif-gateway db check-config
slaif-gateway db show-url
slaif-gateway db upgrade
slaif-gateway db current
slaif-gateway diagnostics status
slaif-gateway diagnostics request show
slaif-gateway diagnostics cleanup
slaif-gateway email test
slaif-gateway email send-pending-key
slaif-gateway email list
slaif-gateway email show
slaif-gateway fx add
slaif-gateway fx list
slaif-gateway fx latest
slaif-gateway institutions create
slaif-gateway institutions list
slaif-gateway institutions show
slaif-gateway keys create
slaif-gateway keys create-from-template
slaif-gateway keys clone
slaif-gateway keys list
slaif-gateway keys show
slaif-gateway keys suspend
slaif-gateway keys activate
slaif-gateway keys revoke
slaif-gateway keys extend
slaif-gateway keys set-limits
slaif-gateway keys set-rate-limits
slaif-gateway keys set-lazy-throttling
slaif-gateway keys set-chat-streaming-live-burn
slaif-gateway keys reset-usage
slaif-gateway keys rotate
slaif-gateway keys policy show
slaif-gateway keys policy update
slaif-gateway keys policy export
slaif-gateway keys policy effective
slaif-gateway keys policy explain-route
slaif-gateway keys external-tools show
slaif-gateway keys external-tools update
slaif-gateway openai-assisted pricing-proposal
slaif-gateway openai-assisted route-proposal
slaif-gateway owners create
slaif-gateway owners list
slaif-gateway owners show
slaif-gateway pricing add
slaif-gateway pricing list
slaif-gateway pricing show
slaif-gateway pricing disable-model
slaif-gateway pricing import
slaif-gateway provider-catalog propose
slaif-gateway providers add
slaif-gateway providers list
slaif-gateway providers show
slaif-gateway providers update
slaif-gateway providers discover-models
slaif-gateway providers setup-models
slaif-gateway providers enable
slaif-gateway providers disable
slaif-gateway quota list-external-tool-fences
slaif-gateway quota list-expired-reservations
slaif-gateway quota list-external-tool-holds
slaif-gateway quota reconcile-external-tool-hold
slaif-gateway quota list-provider-completed-recovery
slaif-gateway quota reconcile-expired-reservations
slaif-gateway quota reconcile-reservation
slaif-gateway quota reconcile-provider-completed
slaif-gateway routes add
slaif-gateway routes list
slaif-gateway routes show
slaif-gateway routes update
slaif-gateway routes enable
slaif-gateway upstream-llm profiles
slaif-gateway routes disable
slaif-gateway routes import
slaif-gateway request-capture arm
slaif-gateway request-capture status
slaif-gateway request-capture stop
slaif-gateway request-capture cleanup
slaif-gateway request-capture inspect
slaif-gateway secrets generate hmac
slaif-gateway secrets generate admin-session
slaif-gateway secrets generate one-time
slaif-gateway secrets validate-env
slaif-gateway templates create-from-calibration
slaif-gateway usage summarize
slaif-gateway usage export
slaif-gateway usage live-burn-summary
```
