# OAP Work Order — 008-b

## Objective

Resolve the verified 008-a event-path blocker by authorizing the minimal strict
encrypted-reasoning stream-validator change, then complete the HMAC-only
same-key/provider/route multi-turn reasoning and tool replay objective on the
existing PR #233.

## GitHub state

- Numeric objective `008`, round `008-b`.
- PR mode: `AMEND_EXISTING_PR`.
- Existing PR #233:
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/233`.
- Branch `oap/008-codex-multiturn-reasoning-replay`; base `main`.
- Starting remote head:
  `96cbbcd9b8a40fa8a5f30a804f50fc0bb3607035`.
- Prior transcript implementation head:
  `4575b41b42279e1baf2e4c579f27e67c39cf2e2e`.
- Prior 008-a status: `BLOCKED` before product implementation.

Amend PR #233 only. Never create another objective-008 PR.

## Blocker resolution

Pinned Codex tag `rust-v0.147.0` proves encrypted reasoning is delivered inside
`response.output_item.done.item` with `type`, `id`, `summary`, and
`encrypted_content`. Current strict validator rejects `encrypted_content`.

This continuation explicitly authorizes:

```text
app/slaif_gateway/providers/streaming.py
tests/unit/test_responses_codex_streaming_tools.py
```

for the minimal exact event shape. Accept `encrypted_content` only when:

- all Codex request/event/replay capability gates required by 008 are active;
- event is `response.output_item.done`;
- item type is exactly `reasoning`;
- required safe item ID and exact summary shape validate;
- value is a non-empty opaque string under a conservative per-item and
  per-stream cumulative byte cap;
- no plaintext `content`/raw chain-of-thought or unknown/authority field exists.

Do not parse, decrypt, log, store, hash, inspect, metric-label, audit, or echo
the encrypted value. Forward the validated frame unchanged to Codex, retain only
the item ID transiently for HMAC reference creation, and discard content.

All malformed/oversized/plaintext/ungated reasoning fields fail safely.

## Governing/start requirements

Re-read full AGENTS/OAP, immutable 008-a order/report, this order, pinned source,
007 stream validator/accounting, database/HMAC/repository conventions, and all
008-a named contracts. Verify PR #233 exact topology/head, only one objective
PR, single Alembic head, and clean tree except strategic `oap/active=008-b` and
this order. Commit strategic bytes unchanged and preserve unrelated state.

## Allowed paths

Implementation may change the complete original 008-a allowed set plus the two
newly authorized paths:

```text
AGENTS.md
app/slaif_gateway/db/models.py
app/slaif_gateway/db/repositories/codex_replay.py
app/slaif_gateway/providers/streaming.py
app/slaif_gateway/services/codex_replay_service.py
app/slaif_gateway/services/key_template_service.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/responses_request_policy.py
app/slaif_gateway/services/responses_route_capabilities.py
docs/accounting.md
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/database-schema.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
migrations/versions/0013_codex_replay_references.py
oap/active
oap/orders/008-b-authorize-encrypted-reasoning-event-and-replay.md
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
`oap/reports/008-b-authorize-encrypted-reasoning-event-and-replay.md`.

Do not edit 008-a history, fixtures/capture/007 harness, dependencies, CI,
deployment, README, provider routing, or unrelated paths.

## Required implementation

Complete every substantive 008-a requirement, with this event authorization:

1. Update `docs/database-schema.md` first/in same PR.
2. Add one migration/table/model/repository/service for HMAC-only replay refs:
   owner key, source ledger/request, provider/route compatibility, constrained
   kind, versioned item/call ID digests, approved safe tool identity, created/
   expiry, uniqueness/indexes—never plaintext/content/digest exposure.
3. Add explicit default-off `codex_encrypted_reasoning_replay` key/template and
   route capability with dependency on prior Codex gates.
4. Capture validated reasoning/function/custom output-item IDs transiently;
   persist HMAC refs only after provider final usage and successful accounting,
   before releasing held completed event. Failure is safe and charged.
5. Require active same-key/provider/route/kind/name HMAC refs before replay and
   before Redis/pricing/quota/provider; reject cross-key/expired/mismatch.
6. Accept canonical encrypted reasoning replay with bounded opaque encrypted
   content and optional exact summary; reject plaintext CoT/content.
7. Apply ownership/order/linkage to Codex function/custom call/output replay;
   keep ordinary non-Codex local-tool output behavior separate.
8. Prohibit combining client replay with `previous_response_id`/conversation.
9. Count replay bytes conservatively; safe evidence contains counts/kinds only.
10. Create/run the harmless isolated three-request reasoning replay verifier
    specified by 008-a, with no shell/filesystem/network/nested tools.
11. Update every named database/accounting/forwarding/security/Codex/Responses/
    compatibility contract honestly. README stays unchanged.

Use a documented conservative fixed TTL; no new setting solely for convenience.
Preserve one Alembic head and exact migration/model/schema agreement.

## Tests and test economy

Cover the full 008-a matrix plus:

- exact encrypted reasoning done-event positive/gate/size/plaintext/unknown
  negatives;
- frame forwarded unchanged but content absent from validator state/logs;
- cumulative encrypted byte cap;
- no usable reference on malformed event/missing usage/error/disconnect;
- reference persistence failure after accounting suppresses completed success;
- unchanged 007 ordinary/tool stream behavior.

Run only focused new/affected unit files, one migration file, one disposable
PostgreSQL integration file, the harmless reasoning replay script, scoped Ruff,
Alembic heads, documentation/OAP tests, diff, and fixture SHA. Do not run full
unit/integration/E2E/browser/Docker/HPC locally. Never use `DATABASE_URL` for
tests. GitHub CI supplies broad evidence.

The final report must list literal commands/counts, environment/DB lifecycle,
and every NOT RUN broad suite. Skips are not passes.

## Acceptance criteria

1. Pinned encrypted reasoning event validates only under exact gates and caps.
2. HMAC-only refs bind replay to same key/provider/route with cross-key denial.
3. Content/IDs/digests never persist or leak; only safe metadata persists.
4. References appear only after final usage+accounting; completion waits.
5. Encrypted reasoning and tool replay order/linkage are exact; provider state
   remains separate.
6. Harmless three-request Codex mock succeeds with no external side effect.
7. Schema/migration/model/repository and focused tests pass, fixture unchanged.
8. One PR/allowed paths only; no broad local suite or real provider/tool.
9. All final report-head GitHub checks green.
10. Coding agent never merges; report-only parent/path satisfy OAP.

## PR/report requirements

Commit unchanged 008-b order/pointer with implementation, push to existing PR,
inspect actual checks, never merge/auto-merge. Publish exactly one immutable
report at
`oap/reports/008-b-authorize-encrypted-reasoning-event-and-replay.md` with
literal implementation SHA and `Report publication commit: SELF`, exact event/
schema/HMAC/replay/accounting/privacy/mock/test evidence, broad suites not run,
and docs impact. Final commit only report with implementation parent; verify and
signal exact `OK`.

If cross-key binding, persistence ordering, or content privacy cannot be proven,
report a blocker rather than weaken. Do not merge.
