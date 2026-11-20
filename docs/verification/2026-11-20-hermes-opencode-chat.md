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

Exact command, on the current implementation HEAD, Python 3.12:

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
  ``test_chat_pin_provider_http_error_releases_reservation`` and
  ``test_chat_pin_stream_provider_error_after_admission_releases_
  reservation``, **Hermes-only** parameters (the OpenCode stream-error
  release parameter was added later and is not part of this 2-case
  batch).
- **e645b381** (3 passed): client disconnect (1) + request-quota 429
  (1) + stream provider-error release (1).
- **e3e97918** (2 passed): disconnect hardening — the strengthened
  ``test_chat_pin_client_disconnect_proves_actual_cancellation``
  (real-TCP disconnect, mocked upstream transport close proven before
  teardown) **supersedes** the earlier disconnect case from the
  ``e645b381`` batch, plus one additional disconnect assertion case.
- **e6e166c2** (8 passed): model/endpoint/provider/streaming-disabled
  route policy denials (4 cases, each executed under two profile
  parameters: Hermes and OpenCode).

What the PG rounds prove: the **PG/HTTP** accounting lifecycle —
reservation → finalization with provider-reported usage, reservation
release on provider error, **estimated finalization** on client
disconnect after partial output (the disconnect path settles the
reservation from estimated usage; it is not an error release), 429
request-quota denial, and pre-upstream denial of bad pins/keys/routes.
What they do **not** prove: R4 held-slot revalidation (that path is
exercised only by the unit fake-slot seam tests above) and real Redis
behavior (rate-limit seams are mocked/faked in all of these tests).

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

### Governance finding (2 failed / 8 passed) — NOT a code regression

``tests/unit/test_oap_governance.py`` → **2 failed, 8 passed**, EXIT 1.
Both failures are against the **immutable root-authored 227-a order's
format**, not a code or test regression:

- ``test_active_identifier_resolves_exactly_one_matching_order``
- ``test_initial_round_declares_new_pr_and_one_objective_one_pr``

The gate ``_NEW_PR_DECLARATION_RE`` requires a standalone line
``PR mode: CREATE_NEW_PR``. The 227-a order declares the PR mode in
prose (``CREATE_NEW_PR.`` at the start of the "Objective and reason"
paragraph) and its title line is not the
``# OAP Work Order — 227-a`` form the validator expects. **During
round 227-a the activated order, the ``oap/active`` pointer, and the
governance tests were not edited, and the validator was not weakened.**
Root decision: the canonical 227-b ``AMEND_EXISTING_PR`` round on the
same PR will correct the activated order's format. No
source/runtime change or unit/native rerun is required for that
resolution.

## Honesty disclosures

- **Historical secondary full-unit run (Python 3.13)** FAILED on one
  named OpenRouter audio test; aggregate counts and causality are
  unknown. No unrelated audio fix was made and no full matrix rerun is
  claimed or implied.
- ``setupfail1`` receipt cleanup is unverified/retained; manual cleanup
  only, not automated.
- The protected live gate is **``not_run``**: no production live
  inference, key mutation, or deploy is recorded. The report is
  **NEEDS_CONTINUATION** (see the adjacent obligation-manifest JSON)
  because the two governance assertions above remain failed against the
  immutable 227-a order; ``preprotected.missing`` includes governance and
  is deliberately **not** ``[]`` and not a false READY.
- Quota/accounting/Redis foundations are **unchanged** versus base
  ``0940d8a2``; the changed services are auth, Chat
  orchestration/request-caps/request-policy, key policy, and key service.

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
