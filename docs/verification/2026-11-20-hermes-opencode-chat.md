# Hermes 0.22.5 + OpenCode 1.19.3 native Chat client profiles (objective 227-a) — 2026-11-20

Two bounded, data-driven Chat client profiles for agentic CLI clients:
``hermes-0.22.5-chat-v1`` (Hermes 0.22.5) and ``opencode-1.19.3-chat-v1``
(OpenCode 1.19.3). Both speak the standard ``/v1/chat/completions`` wire.
The shared neutral engine (``app/slaif_gateway/modules/clients/
agent_chat.py``) plus a pure profile-DATA loader (``modules/
agent_chat_profile_data.py``) are new; each client is a thin binding that
attaches one packaged, reviewed ``schema_version`` 1 profile document to
that engine. Keys without a pin keep the default ``openai-default`` Chat
behavior; a pinned key is validated against its profile's declared
vocabulary, reasoning-effort envelope, and bounds. Quota, accounting,
Redis, and the provider-forwarding foundations are **unchanged** relative
to the base.

This is a PREPROTECTED candidate, not a final live-qualification claim.
The protected live gate is **``not_run``** (see the adjacent
obligation-manifest JSON). No real private client body, credential, or
upstream inference was used; captured cases are task-local native
loopback against a task-owned fake and are reused, not rerun.

## Changed versus base ``0940d8a2``

Changed app services (18 files, +2137/−33):

- New: ``modules/agent_chat_profile_data.py`` (pure DATA loader),
  ``modules/clients/agent_chat.py`` (neutral engine + finite registry),
  ``modules/clients/hermes_0225_chat.py`` and
  ``modules/clients/opencode_1193_chat.py`` (thin bindings),
  ``modules/clients/profiles/hermes-0.22.5-chat.json`` and
  ``profiles/opencode-1.19.3-chat.json`` (packaged DATA).
- Chat orchestration / dispatch: ``services/
  chat_completion_gateway.py`` (dispatch, selected-profile transport-pair
  guard, R4 held-slot revalidation).
- Request caps: ``services/chat_completion_request_caps.py``.
- Request policy: ``services/request_policy.py``.
- Key policy configuration: ``services/key_policy_configuration.py``.
- Key service: ``services/key_service.py`` (chat pin
  create/update/projection/audit and rotation-time pin
  preservation wiring).
- Auth: ``services/auth_service.py`` and ``schemas/auth.py``
  (``AuthenticatedGatewayKey.chat_client_module`` projection).
- Schema: ``schemas/keys.py`` (``chat_client_module: dict[str, str] |
  None``), ``schemas/key_configuration.py`` (strict pin
  parse/canonicalize; ``null`` clears only the Chat binding).
- CLI: ``cli/keys.py`` (bootstrap + policy-file field), ``main.py``.
- Server registry: ``modules/servers/registry.py``.

**Unchanged versus base** (root review confirmed): quota/accounting,
Redis, and the provider-forwarding contract/repository foundations.

## Source provenance (immutable observations)

- **Hermes** ``hermes-0.22.5-chat-v1`` — NousResearch hermes-agent
  v0.22.5, source commit
  ``bf0203a794a07aac3ff764972ab9087baa4e4f4e``, OpenAI Python SDK 2.24.0,
  Python 3.14.9 observed, ``chat_completions`` wire. ``tests/fixtures/
  hermes/0.22.5/provenance.json`` records these immutable facts and the
  separately pinned runtime-candidate DATA revision.
- **OpenCode** ``opencode-1.19.3-chat-v1`` — OpenCode 1.19.3
  (``anomalyco/opencode`` tag ``v1.19.3``, direct commit
  ``e3c4eb242585dcd77be1a867391b7c25fd47ce52``),
  ``@ai-sdk/openai-compatible 2.0.41`` (ai 6.0.168), bun 1.3.14,
  ``chat_completions`` wire. ``tests/fixtures/opencode/1.19.3/chat/
  provenance.json`` records the pinned executable + archive digests and
  the structural-fixture digest rule.

## Pinned identities (from the checked-in provenance documents)

| profile | id | doc version | fixture ``fixture_sha256`` |
| --- | --- | --- | --- |
| Hermes | ``hermes-0.22.5-chat-v1`` | ``"2"`` (string) | ``c5e34d46270280d7e08639c01c28065380a2a80843c1114ac1f1ad2a2744d327`` |
| OpenCode | ``opencode-1.19.3-chat-v1`` | ``"1"`` (string) | ``2bd4f2599456892bb5d5119a85c9ffe9525796c1aa934ad46b49ce34d18f0e14`` |

The REGISTERED RUNTIME module ``version`` and ``fixture_sha256`` are both
derived from the packaged DATA bytes; only the module id is a source
constant. A pin resolves only when its ``fixture_sha256`` matches the
deployed revision; a digest mismatch fails that key closed before
admission. The OpenCode ``observed_user_agent`` is
``opencode/1.19.3 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14``.

## Evidence

### Unit coverage — 557 passed, EXIT 0

Exact command, on the tested implementation head
``5c2bacf83578f5a23b6e9700656e8bfd26dc373c`` (full tree
``430aae04aaa2f4dbaf4ff529623d022ff3a09278``;
``app/slaif_gateway`` tree ``0ab1e80ad89a6578b17b0bfcaa99fa5e8ccab21e``),
Python 3.12:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/unit/test_agent_chat_profiles.py \
  tests/unit/test_hermes_aux_reasoning_effort.py \
  tests/unit/test_opencode_1193_chat.py \
  tests/unit/test_agent_chat_dispatch.py \
  tests/unit/test_verify_hermes_chat_capture.py \
  tests/unit/test_auth_service.py \
  tests/unit/test_key_policy_configuration.py \
  tests/unit/test_key_service_create.py \
  tests/unit/test_request_policy_service.py \
  -q -o addopts= -p no:cacheprovider
```

Result: **557 passed** (9.97s), EXIT 0. Only the ``pytest_asyncio``
``asyncio_default_fixture_loop_scope`` unset deprecation notice.

Coverage label: these are **unit** tests — the provider upstream is
mocked and the Chat engine runs against in-memory/fixture seams; they
prove profile resolution, reasoning-effort envelope, dispatch, pin
parse/canonicalize, auth projection, and key-service wiring. The
provider-seam fakes are specific to the ``TestR4ChatBindingRevalidation``
cases in ``test_agent_chat_dispatch.py`` (fake rate-limiter/quota
seams driving the R4 held-slot revalidation path: 3 denial cases plus
the unchanged binding-quota path), not to all 557 nodes. Unit coverage
does **not** prove a real PostgreSQL lifecycle, real Redis behavior, or
any native-client behavior; the PG rounds below cover the PG/HTTP
lifecycle, and the accepted native loopback cases (reused, not rerun)
cover actual client processes.

**Independent overlapping evidence (reused, not rerun):** root
integration check at ``f9dd35b6``, primary Python 3.12.15:
``PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/unit/
test_verify_hermes_chat_capture.py -q -o addopts= -p no:cacheprovider``
→ **16 passed** (0.35s), EXIT 0, only the ``pytest_asyncio``
deprecation notice. Those 16 nodes are **included in** the 557 above
(the file is one of the nine), so this check is independent,
overlapping evidence from an earlier commit, not excluded coverage;
the two counts must not be summed.

### PostgreSQL lifecycle (real disposable PG16) — reused, not rerun

Owned disposable PostgreSQL 16 (``127.0.0.1:54398``, database
``slaif_227_agent_chat_test``, data dir
``/tmp/slaif-227a-pg16-1795160166/data``; ``TEST_DATABASE_URL`` used only
for destructive setup). The file
``tests/integration/test_agent_chat_profiles_postgres.py`` was built up
across the commit stack below; **each run's counts are chronological
and overlap** — a later run re-executed tests already covered by an
earlier run — so the numbers below are per-run receipts, not a
partition, and must not be summed into an inflated total:

- **b63c4ec7** (1 passed): first binding case
  ``test_chat_pin_binding_round_trip_on_persisted_state``.
- **2475bb71** (4 passed): projection/dry-run no-write, stale/forged/
  malformed export denial + repair, rotation pin preservation, plus a
  rerun of the first binding case.
- **9fe29e23** (1 passed): Hermes Chat runtime dispatch + PG
  accounting success.
- **a5edb7ab** (2 passed): runtime success parameterized Hermes +
  OpenCode — the Hermes parameter re-ran the preceding Hermes runtime
  success case; the second parameter was the new OpenCode runtime
  success.
- **fd086c95** (13 passed): pre-upstream denial battery
  (stale/unknown/malformed pin, tampered/revoked key, native provider
  pair denial) + absent-pin default behavior, re-running already-green
  pin-denial cases where the file had grown.
- **c9434f6f** (2 passed): streamed Chat success finalizes PG usage —
  one ``test_chat_pin_stream_success_finalizes_pg_usage`` case executed
  separately per profile (Hermes, OpenCode).
- **7821f944** (2 passed): provider-error release paths —
  ``test_chat_pin_provider_http_error_releases_reservation`` (HTTP 500
  non-stream) and ``test_chat_pin_stream_provider_error_after_admission_
  releases_reservation`` (HTTP 500 stream). **Both HTTP 500 release
  tests are currently Hermes-only**; no OpenCode parameters exist for
  them yet.
- **e645b381** (3 passed): client disconnect (2 — one
  ``test_chat_pin_client_disconnect_proves_actual_cancellation``
  execution per profile: Hermes, OpenCode) + request-quota 429 (1).
- **e3e97918** (2 passed): disconnect hardening — the strengthened
  ``test_chat_pin_client_disconnect_proves_actual_cancellation``
  (real-TCP disconnect, mocked upstream transport close proven before
  teardown) re-executed for the same 2 profile parameters, **superseding
  the 2 older disconnect executions** from the ``e645b381`` batch.
- **e6e166c2** (8 passed): model/endpoint/provider/streaming-disabled
  route policy denials (4 cases, each executed under two profile
  parameters: Hermes and OpenCode).

What the PG rounds prove: the **PG/HTTP** accounting lifecycle —
reservation → finalization with provider-reported usage, reservation
release on provider HTTP error, **estimated finalization** on client
disconnect after partial output (the disconnect path settles the
reservation from estimated usage; it is not an error release), 429
request-quota denial, and pre-upstream denial of bad pins/keys/routes.
Current coverage gaps: the two HTTP 500 release tests are Hermes-only
(no OpenCode parameters yet); the disconnect round only proves transport
close for the mocked upstream, and real-provider behavior is not
covered. What the PG rounds do **not** prove at all: R4 held-slot
revalidation (exercised only by the unit fake-slot seam tests above)
and real Redis behavior (rate-limit seams are mocked/faked in all of
these tests).

### Native loopback (preprotected, reused — NOT rerun)

Accepted native client loopback cases against a task-owned 127.0.0.1
fake, isolated task-owned HOME/XDG, synthetic bearer, bounded timeouts:

- **Hermes** ``loop7`` (7 POSTs: title req 1, summary req 5, continuation
  6); ``timeout4`` (11 POSTs; OUTER-watchdog cancellation CLI −15 @120s,
  not self-exit); ``error3`` (11 POSTs; 68 error lines); ``multi1`` (3
  POSTs, 2 correlated read_file call/result pairs,
  reasoning+reasoning_content replay); ``entry-final-positive`` (3
  POSTs / 2 calls / CLI 0 / verified cleanup / hash-only receipt).
- **OpenCode** structural captures in
  ``tests/fixtures/opencode/1.19.3/chat/`` (title/aux, session
  identity, text stream, reasoning, tool loop, multi-call, compaction).

No native/client rerun was performed for this documentation assembly;
these accepted cases are reused as-is.

### Static checks

- ``ruff check app tests`` → **All checks passed!**, EXIT 0.
- ``git diff --check`` → clean.
- OAP/agentic governance: ``test_agentic_client_integration_governance.py``
  + ``test_provider_governance.py`` → **5 passed**, EXIT 0 (recorded
  separately from the 227-a-order governance finding below).

### Governance (canonical 227-b continuation)

**Historical 227-a finding (preserved, not rewritten):** while the
round-227-a order was active, ``tests/unit/test_oap_governance.py`` →
**2 failed, 8 passed**, EXIT 1. Both failures were against the
**immutable root-authored 227-a order's format**, not a code or test
regression:

- ``test_active_identifier_resolves_exactly_one_matching_order``
- ``test_initial_round_declares_new_pr_and_one_objective_one_pr``

The gate requires a standalone ``PR mode: CREATE_NEW_PR`` line; the
227-a order declared the PR mode in prose and its title line was not
the ``# OAP Work Order — 227-a`` form the validator expects. **During
round 227-a the activated order, the ``oap/active`` pointer, and the
governance tests were not edited, and the validator was not
weakened.** The 227-a report (immutable) therefore honestly recorded
``NEEDS_CONTINUATION`` with this as one of three declared gaps.

**Canonical 227-b continuation (current active state):** root published
the canonical order
``oap/orders/227-b-preprotected-governance-and-evidence-closure.md``
(first line ``# OAP Work Order — 227-b``, standalone line
``PR mode: AMEND_EXISTING_PR``, SHA-256
``8e6dc2da39ff9a199d5872f68ee3c72dfb68463f8cf807739d7eb2374e36ad90``)
and set ``oap/active`` to ``227-b`` (SHA-256
``bd7995dfb437b1b1e083eac24a5bc9de8a768f42256dcddaa542072f99a9e29e``),
committed and pushed unchanged as ``a9539700`` (sole parent
``b87ad897``, the 227-a report SELF). This legitimately replaces the
active selector; the archived 227-a order and report were not touched.

**New focused run against the NEW active state** (justified by the
state change; the only test rerun in this round):

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/unit/test_oap_governance.py -q -o addopts= -p no:cacheprovider
```

Result: **10 passed**, EXIT 0 (0.33s; only the ``pytest_asyncio``
``asyncio_default_fixture_loop_scope`` deprecation notice). No skips,
xfails, or special exceptions; the two historical 227-a format
failures are gone because the active order now carries the canonical
title and PR-mode declaration lines.

**Other governance files (reused, recorded separately):**
``test_agentic_client_integration_governance.py`` +
``test_provider_governance.py`` → **5 passed**, EXIT 0.

## Honesty disclosures

- **Historical secondary full-unit run (Python 3.13)** FAILED on one
  named OpenRouter audio test; aggregate counts and causality are
  unknown. No unrelated audio fix was made and no full matrix rerun is
  claimed or implied.
- ``setupfail1`` receipt cleanup is unverified/retained; manual cleanup
  only, not automated.
- The protected live gate is **``not_run``**: no production live
  inference, key mutation, or deploy is recorded. The 227-a report
  (immutable) was **NEEDS_CONTINUATION** because of the three gaps it
  declared (order-format governance, obligation mapping, concrete
  protected plan); the canonical 227-b round resolves (a) by the new
  active order and its 10/10 governance run, and (c) by the full
  **PROPOSED** protected live test plan in this record. The plan is
  proposed/unconfirmed — human target authority and protected
  execution remain pending, and ``protected.status`` stays
  ``not_run``. Gap (b), the per-obligation ``obligation_mapping`` in the
  adjacent obligation-manifest JSON, is owned by the secondary
  component: its reviewed mapping commit is in handoff and is **not yet
  integrated** into this branch; this record must not claim it
  completed before that handoff lands.

- **Base ancestry note (factual, no rebase/merge performed):** remote
  ``main`` advanced past this branch's base ``0940d8a2`` to
  ``4500e16fa0b5f177aa25313c6a72321307b52efc`` (merge of PR #394,
  docs only: five Codex image-limit doc files, disjoint from
  ``app``/``tests``) while this branch was under review. The base
  ``0940d8a2`` remains an ancestor of remote ``main``; no rebase or
  merge is required or performed by 227-b.
- **227-a report source-ownership SHA typo (corrected here; the
  immutable report was not edited):** the 227-a report records the
  secondary Hermes dossier commit as
  ``14b4a170983dfac35b34b3d9bd89585ec3d74fd859``; the correct literal
  is ``14b4a170983dfac35b34b9bd89585ec3d74fd859`` (integrated on the
  primary branch as ``d5e798bf``). The accepted secondary
  contract-doc source commit
  ``2e50035738af24a0cf4b0dcd9f05e5adf7c9fca0`` was integrated as
  ``d776b92a``. Source ownership and history are preserved; no
  secondary push or PR was made.
- Quota/accounting/Redis foundations are **unchanged** versus base
  ``0940d8a2``; the changed services are auth, Chat
  orchestration/request-caps/request-policy, key policy, and key service.

## Proposed protected live test plan (PROPOSED / UNCONFIRMED)

The plan below is a **proposal** drafted in this record (mirrored into the
adjacent obligation-manifest JSON by the owning component); it is **not** an
executed, deployed, or approved fact. Root will present the concrete reviewed
candidate and plan for explicit human target authority and protected
execution authorization. ``protected.status`` stays **``not_run``** until
then. No 227-b activity authorizes a deployment, production key binding,
provider request, real-client launch, live gateway setup, or any read of
saved real client credentials/configs.

### Proposed topology (planned, not existing resources)

- Exact candidate code in a **task-local loopback gateway** with an isolated
  task DB and task-owned keys, configured as a generic openai-compatible
  provider pointing at the reported FULL LAN chain
  ``http://10.8.132.55:18021/v1`` -> its existing controlled backend.
- Proposed wire model ``qwen38-27b`` per the supplied historical status
  reports. This is a proposal from pinned historical reports, **not** current
  remote health, route-capability, credential, or deployed-version evidence.
- Planned local provider/route labels ``qualification-227-lan-chain`` /
  ``qualification-227-chat`` are **planned labels only**, not existing
  resources. Never bypass the chain (port 18020 / direct model), never
  remove required signing, and never pretend the Responses-only
  ``LocalCodingAdapter`` serves Chat. If the approved chain requires
  unsupported identity/transport behavior, stop and report it; no fallback
  bypass.

### Proposed numeric ceilings (configured admission/accounting bounds)

- ONE native process launch per profile; NO outer retry/rerun after
  failure.
- Original strict proposal: at most **6 ADMITTED** Chat/model requests
  per profile including auxiliary traffic, guarded by a finite
  task-key request quota. **UNSATISFIED as a guarantee** — see the
  retry-semantics section below: source proof shows native retries
  cannot be promised off, and the PG 500-release assertions prove a
  finite ``request_limit_total`` does **not** cap total admitted
  attempts across failures. The strict ceiling is therefore recorded
  as **UNSATISFIED / protected human-decision pending**, not as a
  bound the gateway enforces.
- Total input+output token quota **1,000,000** per profile.
- Configured gateway cost quota **EUR 1.00** per profile / **EUR 2.00**
  aggregate under approved pricing.
- Outer wall clock **600 s** per profile / **1200 s** aggregate.

These are proposed configured admission/accounting bounds, not an invoice
and not an exact external no-overrun guarantee. Rejected attempts are
distinct from admitted requests. The "6 SETTLED/charged requests per
key" ceiling appears **only** in the unapproved relaxed alternative
below, never as the strict proposal's enforced bound.

### Retry semantics — strict guarantees are UNSATISFIED (source-proven)

The original strict reading (zero automatic retries; at most 6 total
admissions per profile) is **not** currently provable and is documented here
as a **protected human-decision prerequisite, not as passed**:

- **Hermes 0.22.5** (pinned source commit
  ``bf0203a794a07aac3ff764972ab9087baa4e4f4e``; local review copy
  ``/tmp/slaif-227-hm/src``):
  - ``agent/agent_init.py:1444`` — ``api_max_retries`` default 3, clamped
    ``max(..., 1)``; config ``agent.api_max_retries=1`` gives a single
    attempt. ``agent/agent_init.py:1451`` — ``auto_recovery_cycles``
    default 5; ``=0`` disables the post-exhaustion recovery ladder.
  - ``agent/agent_runtime_helpers.py:2076`` — primary OpenAI SDK clients
    ``setdefault("max_retries", 0)`` (SDK retries off for the primary path).
  - ``agent/auxiliary_client.py:200`` and ``:4752`` — auxiliary sync/async
    clients ``setdefault("max_retries", 0)``; the sync auxiliary path adds
    ``_transient_retry_count()`` (``auxiliary.transient_retries`` default 2,
    clamped [0, 6]) → ``transient_retries=0`` yields zero sync-aux retries.
  - **Caveat — no universal zero-retry claim:** ``_async_call_llm_impl``
    (``auxiliary_client.py:8337``) hardcodes ONE same-provider retry on
    transient transport error for the async auxiliary path. Title
    generation (``title_generator.py``, sync ``call_llm`` task
    ``"title_generation"``) and compression (``context_compressor.py:3831``,
    sync ``call_llm`` task ``"compression"``) are sync tasks;
    ``{"compression","vision","title_generation"}`` ∈
    ``_TIMEOUT_NO_RETRY_TASKS`` (``auxiliary_client.py:3540``) means TIMEOUT
    errors skip the same-provider retry, but **fast blips still retry** on
    those tasks.
- **OpenCode 1.19.3** (pinned ``anomalyco/opencode`` tag ``v1.19.3``,
  commit ``e3c4eb242585dcd77be1a867391b7c25fd47ce52``,
  ``packages/opencode/src``):
  - ``session/llm.ts:323`` — SDK ``maxRetries = input.retries ?? 0``.
  - **However** ``processor.ts:674`` applies unconditional
    ``Effect.retry(SessionRetry.policy)``; ``retry.ts:31``
    ``RETRY_MAX_RETRIES = 5`` and ``retry.ts:189-193`` make the policy a
    **hard cap with no override parameter**. Therefore OpenCode's native
    HTTP retries **cannot be promised off** by configuration alone.
- **Admission ceiling:** the existing PG 500-release assertions record
  ``requests_used_total == 0`` after failed attempts, proving
  ``request_limit_total = 6`` does **not** cap total *admitted attempts*
  across failures. A strict "≤ 6 total admissions including retries"
  guarantee is therefore **UNSATISFIED** unless independently proven.

**Proposed relaxed alternative (ROOT/HUMAN decision only; not the same as
the strict plan):** ONE process, no harness rerun, **stock native retries
explicitly allowed**; the ceiling becomes **6 SETTLED/charged (admitted and
finalized) requests per key**, with admitted attempts allowed to exceed 6
while rejections are not charged; the 1,000,000-token / EUR 1.00-per-profile
/ EUR 2.00-total and 600 s / 1200 s ceilings are unchanged. This is a
**relaxed guarantee** requiring explicit human risk approval; it must not be
executed, and no client patch, accounting change, proxy, or budget framework
is introduced by 227-b. Root will seek an explicit human risk decision after
the reviewable B candidate exists.

### Preserved qualified baseline and planned assertions

- Pinned baseline preserved: Hermes native main ``xhigh`` / auxiliary
  ``none`` with its captured toolsets; OpenCode pure/denied-web 9 tools,
  Chat-compatible SDK, and its captured auxiliary
  ``max_tokens=32000`` request envelope. Proposed task-gateway settings
  ``CHAT_MAX_TOOL_DESCRIPTION_BYTES=8192`` and
  ``HARD_MAX_OUTPUT_TOKENS=32768`` (deployment-scoped operator settings; the
  source defaults ``4096``/``4096`` remain untouched) accept the native
  envelope without widening defaults in source; normal input policy remains
  authoritative. Efforts, title/compaction, tools, wire-model alias, and
  legitimate history are not altered to obtain a pass; any deliberate QA
  variant must be explicit and separately scoped.
- Planned positive: task-owned unpredictable file read and exact result
  through actual client/tool/history continuation per profile, auxiliary
  behavior preserved, isolated task HOME/XDG/workspace, existing approved
  workflow/native assets, no new harness framework.
- Planned assertions: exact client/source/package/config and candidate
  identity; request/call/result correlation; successful final
  provider-reported usage and one terminal PG settlement per admitted
  request; no stranded reservations/holds after cleanup; credentials never
  exposed in logs/artifacts/persisted metadata; owned native
  runtime/process cleanup. If final usage is missing, the actual
  estimated/failed outcome is recorded; a client exit or transport close
  does not prove GPU inference cancellation. Provider-specific
  pricing/billing limitations remain explicit.

### Required CI gate before any protected traffic

- Per ``AGENTIC_CLIENT_INTEGRATION.md`` §40, all **required external CI
  checks must be represented, scoped to the exact candidate head, and
  green** before protected traffic; pending, skipped, or missing checks are
  not passes. Root owns the final exact-head CI gate after this report.
- Per §51, the **zero automatic retry** requirement is a protected
  prerequisite. Given the source facts above, it is recorded as
  **UNSATISFIED / human-decision pending**, never waived or labeled pass.

## Operator references

- Chat profile selection: ``docs/module-architecture.md``.
- First-time operator setup (pin/clear/inspect, OpenCode env):
  ``docs/first-time-operator-guide.md``.
- Data-only vs image upgrade + full-revision rollback:
  ``docs/upgrade-runbook.md`` (Hermes/OpenCode section).
- CLI policy-file field reference: ``docs/cli-reference.md``.
- Provider-forwarding / accounting / security contract additions
  (secondary-owned): ``docs/provider-forwarding-contract.md``,
  ``docs/accounting.md``, ``docs/security-model.md``.
