# OAP Work Order — 008-a

## Objective

Implement bounded multi-turn Codex client-managed replay for prior local-tool
calls/outputs and provider-encrypted reasoning, with HMAC-only per-key/provider/
route ownership metadata, exact linkage/order validation, no plaintext content
storage, and no conflation with `previous_response_id` provider state.

## GitHub state

- Numeric objective `008`, round `008-a`.
- PR mode: `CREATE_NEW_PR`.
- Repository/base: `ulfe-lmi/slaif-api-gateway` / `main`.
- Starting main: `064be428a58d9d1c0581d36d16a37853bb7d5952`.
- Objective 007/PR #232 merged.
- Branch: `oap/008-codex-multiturn-reasoning-replay`.
- Title: `[OAP 008] Bind Codex encrypted replay to gateway keys`.
- Expected unrelated open PR: Dependabot #224 only.

Create one PR; continuations amend it.

## Architecture decision: safe replay references

Codex `store=false` sessions replay provider output items client-side. Content
can remain stateless, but the proposal's cross-key denial cannot be enforced by
shape validation alone. Implement durable **safe reference metadata only**:

- HMAC digest of provider item/call IDs, never plaintext IDs;
- HMAC key version;
- owning gateway key;
- provider/model-route compatibility metadata;
- safe item kind and approved namespace/tool name where required;
- source usage-ledger/request linkage and created/expiry timestamps;
- no prompt, completion, reasoning, encrypted content, arguments, results,
  messages, schemas, grammar, metadata values, raw bodies, or provider events.

References are reusable for full-history replay until expiry because Codex may
send prior items on multiple later turns. They are not invoice data and do not
create provider state.

Record references only after a successful provider completion with final usage
and successful PostgreSQL accounting finalization. If reference persistence
fails, do not emit normal `response.completed`; return a safe failure while
preserving charged/finalized usage truth. Unknown/missing/expired/cross-key/
provider-route mismatches fail before Redis, pricing, quota, or provider calls.

`previous_response_id`, stored Responses, and Conversations remain separate
owned provider-state contracts. A Codex client-managed replay request must not
combine with `previous_response_id` or `conversation` in this objective.

## Governing/start requirements

Read complete AGENTS/OAP law, database schema contract, 004–007 Codex contracts,
accounting/security/forwarding docs, models/migrations/repositories, HMAC key
version helpers, stream validator/replay policy, and pinned Codex ResponseItem
source. Verify GitHub/main, PR #232 merge, no objective-008 PR, clean worktree,
single Alembic head, and fixture SHA.

The strategic model atomically published this order and `oap/active=008-a`;
commit exact bytes and branch from `origin/main`. Preserve unrelated state and
all credentials.

## Allowed paths

Implementation may change only:

```text
AGENTS.md
app/slaif_gateway/db/models.py
app/slaif_gateway/db/repositories/codex_replay.py
app/slaif_gateway/services/key_template_service.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/responses_request_policy.py
app/slaif_gateway/services/responses_route_capabilities.py
app/slaif_gateway/services/codex_replay_service.py
docs/accounting.md
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/database-schema.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
migrations/versions/0013_codex_replay_references.py
oap/active
oap/orders/008-a-codex-multiturn-reasoning-replay.md
scripts/verify_codex_reasoning_replay.py
tests/integration/test_codex_replay_references_postgres.py
tests/unit/test_alembic_codex_replay_references.py
tests/unit/test_codex_replay_service.py
tests/unit/test_key_template_service.py
tests/unit/test_responses_codex_multiturn_replay.py
tests/unit/test_responses_codex_streaming_tools.py
tests/unit/test_responses_request_policy.py
tests/unit/test_responses_route_capabilities.py
```

Final report-only commit adds only
`oap/reports/008-a-codex-multiturn-reasoning-replay.md`.

Do not edit fixture/capture/007 harness, provider adapters/event allowlist unless
a verified pinned shape requires strategic continuation, dependencies, CI,
deployment, README, pricing/catalog, or prior history.

Update `docs/database-schema.md` first/in same PR; implementation/migration must
match it exactly. One new Alembic head only.

## Capability gate

Add `codex_encrypted_reasoning_replay`, default false, to safe explicit key
template and route capability vocabularies. Never default/calibration enable.

Encrypted reasoning replay requires this plus
`codex_request_envelope`. Tool-call/output replay also requires
`codex_client_tools`; streaming generation retains
`codex_streaming_tool_events`. Require exact independent key and route grants.

No capability implies another. Key/shape/ownership denial occurs before route/
Redis/pricing/quota/provider; route denial before Redis/pricing/quota/provider.

## Schema and repository

Define a conservative `codex_replay_references` table (exact naming may follow
repository conventions) with UUID PK and:

- `gateway_key_id` FK, restrictive deletion preserving audit/accounting truth;
- source `usage_ledger_id` FK or equivalent safe request linkage;
- provider and model-route/provider-model compatibility identifiers safe for
  routing checks;
- `item_kind` constrained to `reasoning`, `function_call`, `custom_tool_call`;
- `item_id_hmac` and/or `call_id_hmac` fixed-length digests as required;
- `hmac_key_version`;
- optional approved safe namespace/tool name (no user-defined value);
- `created_at`, `expires_at`, and active status if needed;
- unique constraints preventing duplicate ownership rows and indexes for
  key+digest lookups/expiry.

No raw provider IDs. Do not reuse token hashes as foreign identifiers. Use the
existing versioned HMAC secret infrastructure and constant-time comparisons/
indexed digest equality as appropriate. Refuse when required HMAC version is
unavailable. Use a documented fixed conservative expiry for this MVP unless an
existing safe setting is already appropriate; do not add config merely for
convenience.

Repository/service operations:

- atomically upsert/fetch exact safe refs;
- validate key/provider/route/kind/name/expiry;
- batch lookup without N+1 where practical;
- no content parameters or content logging;
- no mutation during preview/policy failure;
- safe duplicate/retry idempotency.

## Stream reference capture

Extend request-scoped Codex stream validation to derive safe in-memory reference
candidates only from fully validated `response.output_item.done` items:

- reasoning item ID;
- function/custom item ID and call ID plus exact approved tool identity.

Never retain argument/input/summary/encrypted content after the frame is
forwarded. Candidate structures expose IDs only to the immediate HMAC/persist
step and must not be logged/serialized.

After `response.completed` usage is present and accounting finalizes, persist
HMAC-only refs in the same safe completion sequence before emitting the held
completed event. Persistence failure is a safe post-provider accounting/state
failure, not a zero-cost release or successful completion.

## Encrypted reasoning request/replay policy

Accept only the pinned provider reasoning replay item under the capability:

- exact `type="reasoning"`;
- required bounded safe `id`;
- required non-empty opaque `encrypted_content`, conservatively size-capped;
- optional bounded `summary` array of exact summary-text item shape required by
  pinned Codex; no raw chain-of-thought/content field;
- optional pinned safe status only if source proves required;
- no unknown/provider-authority fields.

Do not decrypt, parse, inspect, store, hash, log, meter as identity, audit,
export, or expose encrypted/summary text. Forward only through canonical rebuilt
input after item-ID ownership/provider/route validation. Count encrypted and
summary bytes conservatively as provider input.

Explicitly reject plaintext reasoning content/raw chain-of-thought, unencrypted
reasoning replay, arbitrary item types, malformed IDs, oversized blobs, and
reasoning without an owned active reference.

## Tool call/output replay hardening

Apply durable ownership validation to the function/custom call replay and
outputs introduced in 007:

- every replayed call/item ID must resolve to an active same-key compatible ref;
- namespace/name/type must match the stored safe ref and current declared
  taxonomy;
- output must follow its matching call in canonical order;
- reject orphan, duplicate, reordered, cross-key, expired, provider/route/model
  mismatch, or call/output type mismatch;
- never persist call arguments/inputs/results.

Existing non-Codex local function/custom output behavior remains separate and
must not accidentally require Codex refs.

## Multi-turn linkage/order

For Codex-gated replay, enforce one deterministic input-state machine:

- messages/reasoning/call/output order accepted only as pinned;
- unique item IDs and call IDs across the request;
- output follows exactly one matching replayed call;
- reasoning refs may repeat across later full-history requests but duplicate
  copies inside one request deny;
- `previous_response_id` and `conversation` cannot combine with client replay;
- all ownership checks finish before rate/quota/provider side effects.

## Accounting/privacy

Each model request retains independent PostgreSQL reservation/finalization.
Encrypted reasoning, summaries, arguments, results, IDs, and replay bodies are
never in ledger metadata/logs/metrics/audit/errors. Safe evidence may include
counts, kinds, approved names, aggregate bytes/tokens, reference lookup outcome
category, and expiry—not HMAC digests or raw IDs.

Provider final usage/cost remains authoritative. Unknown completion usage or
reference-persistence ambiguity fails closed and never becomes zero-cost
success. HMAC reference rows are control metadata, not content or billing truth.

## Actual harmless replay mock

Create `scripts/verify_codex_reasoning_replay.py`, manual-only and never pytest/
CI/application/HPC. Reuse exact isolation/dummy-loopback rules.

Use fixed provider streams to cause at least three in-memory Codex requests:

1. first harmless `functions.exec` custom call using only
   `text("SAFE_REPLAY_ONE")`;
2. second response includes a synthetic encrypted reasoning item plus another
   harmless `functions.exec` call using only `text("SAFE_REPLAY_TWO")`;
3. third request proves Codex replays the reasoning item and exact linked tool
   calls/outputs, then receives a fixed final assistant completion.

No shell/filesystem/network/nested tool. Print only safe counts/booleans/types;
never raw IDs, encrypted content, summaries, arguments, results, prompts,
headers/bodies, or logs. If pinned client cannot produce this safely, report a
blocker rather than broaden.

This composes client-shape evidence; focused gateway/provider/PostgreSQL tests
prove the actual enforcement. Objective 011 remains full CLI-through-gateway.

## Tests

Create unit/integration/migration tests covering:

1. schema/model/migration exact columns, constraints, indexes, one head,
   upgrade/downgrade and no plaintext columns;
2. HMAC version/digest behavior, idempotent insert, expiry, batch lookup,
   same-key/provider/route/name matching and cross-key negatives;
3. all key/route capability matrices and pre-side-effect ordering;
4. exact reasoning item positive/invalid/plaintext/unknown/size cases;
5. function/custom replay+output ownership/order/duplicate/orphan/mismatch cases;
6. persistence only after provider usage + successful finalization, completed
   event held until success, persistence failure safe and charged;
7. missing usage/error/disconnect never writes usable refs;
8. separate non-Codex and `previous_response_id`/conversation behavior intact;
9. input estimation includes content bytes but evidence has safe counts only;
10. logs/errors/ledger/metrics/audit/DB contain no raw ID/digest/encrypted/
    summary/argument/result canaries;
11. harmless three-request Codex mock and pure harness no-side-effect tests;
12. immutable fixture/previous harnesses unchanged.

No real provider/tool service or production data.

## Documentation

Update database schema first, then AGENTS and Codex/Responses/forwarding/
accounting/security/compatibility contracts with HMAC-only refs, TTL/lifecycle,
cross-key semantics, encrypted replay, client-state versus provider-state,
failure/ordering/privacy, harmless mock, and remaining cache/compaction/full-E2E
gaps. README remains unchanged until qualified CLI path.

## Non-goals/test economy

No plaintext reasoning/ID storage, gateway execution, hosted/MCP/background/
WebSocket, provider conversation expansion, arbitrary state, full production
claim, dependencies/CI, real provider, or broad local suite.

Run only focused unit files for new replay/service/policy/stream/template/
migration plus one PostgreSQL integration file, exact harmless mock, Ruff,
Alembic heads, diff, fixture SHA, and OAP/docs tests. The coding agent must list
literal commands in its report. Do not run full unit/integration/E2E/browser/
Docker/HPC. Use a disposable `TEST_DATABASE_URL`; never `DATABASE_URL`. GitHub
CI supplies broad evidence.

## Acceptance/PR/report gate

Success requires same-key durable HMAC refs, cross-key/expired/provider-route
denial, exact encrypted reasoning/tool replay, completion/persistence/accounting
ordering, zero content leakage, harmless three-request client evidence, focused
tests, one PR, allowed paths, and all final checks.

Commit unchanged order/pointer, create one non-draft PR on required branch/title,
inspect real checks, never merge/auto-merge. Publish one immutable report at
`oap/reports/008-a-codex-multiturn-reasoning-replay.md` with literal
implementation SHA/SELF, exact schema/HMAC/replay/mock/test/privacy/accounting
evidence, broad suites not run, and docs impact. Final commit only report with
implementation parent; verify/signal exact `OK`.

If safe cross-key binding or post-finalization reference persistence cannot be
proved, report a blocker rather than weaken/expand. Do not merge.
