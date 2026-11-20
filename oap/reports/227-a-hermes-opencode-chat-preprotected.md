# OAP Report — 227-a (preprotected): Hermes 0.22.5 + OpenCode 1.19.3 native Chat client profiles

## Status

**NEEDS_CONTINUATION**

The implementation is reviewable, but preprotected qualification remains incomplete; three declared
gaps remain, so this is not a false READY and `preprotected.missing` is not
`[]`:

1. **governance:227-a-order-format** — `tests/unit/test_oap_governance.py`
   reports **2 failed / 8 passed** (EXIT 1) because the activated 227-a
   order's format does not match the strict validator: its title line is
   `# Objective 227-a — ...` instead of `# OAP Work Order — 227-a`, and its
   PR-mode declaration is prose (`CREATE_NEW_PR.` in the "Objective and
   reason" paragraph) instead of a standalone `PR mode: CREATE_NEW_PR` line.
   Failing tests:
   `test_active_identifier_resolves_exactly_one_matching_order`,
   `test_initial_round_declares_new_pr_and_one_objective_one_pr`. This is an
   order-format issue, not a code or test regression. During round 227-a the
   activated order, `oap/active`, and the governance tests were not edited
   and the validator was not weakened. Root decision: the canonical **227-b
   `AMEND_EXISTING_PR`** round on the same PR corrects the order format; no
   source/runtime change or unit/native rerun is required for that
   resolution.
2. **obligation-mapping** — the order's duty is one machine obligation
   manifest linked to executed test node IDs/results, source tree/fixture
   digests, and client binary/package/config identity. The published
   `docs/verification/2026-11-20-hermes-opencode-chat-obligations.json` is
   currently an **evidence index** (receipts + identity/digest facts), not
   yet the required per-obligation verified test-node-ID mapping.
3. **protected-live-test-plan** — the bounded proposed live test currently
   carries requirement placeholders only. No actual target route/model/
   backend and no numeric request/token/cost/time ceilings are declared
   here; the order forbids inventing them, and they require root review and
   protected authority.

The protected live gate remains **not_run** (see below). No profile is
called supported or mergeable on the strength of mocks.

## Identification

- Repository: `ulfe-lmi/slaif-api-gateway`
- Branch: `oap/227-hermes-opencode-chat`
- Base: `main` at `0940d8a28f3a413d2a2cc6f4962c0efcafd71e13`
- PR: **#395** (draft), title exactly
  `227: Add bounded Hermes and OpenCode Chat client profiles`
- Tested implementation head SHA:
  `5c2bacf83578f5a23b6e9700656e8bfd26dc373c`
  (tree `430aae04aaa2f4dbaf4ff529623d022ff3a09278`;
  `app/slaif_gateway` tree `0ab1e80ad89a6578b17b0bfcaa99fa5e8ccab21e`)
- Final implementation head at report time (docs-only commits after the
  tested head, no runtime/test changes):
  `5594530641adf61265ec9dcaf74865098eb0cb1c`
  (tree `24c06e9554e317fb0e601f48cb41b5baaec1e345`)
- Report publication commit: SELF (this report's sole report-only commit,
  sole parent = final implementation head, sole diff = this report)
- Activated order: `oap/orders/227-a-hermes-opencode-chat-preprotected.md`,
  SHA-256 `4d24d84bef3b7c7d2f1a4b4f70e380dc84debf95da726c8a922735dcadd0f546`
  (not edited during round a)
- `oap/active` = `227-a`, SHA-256
  `ea3d8056453a861b46ca727cf55aee5043a1df7b36cde04d49af43688ab17738`
  (not edited during round a)

## What was delivered

Two bounded, data-driven Chat client profiles on a shared neutral engine:

- `hermes-0.22.5-chat-v1` — doc version `"2"` (string), pinned
  `fixture_sha256 c5e34d46270280d7e08639c01c28065380a2a80843c1114ac1f1ad2a2744d327`
  (raw packaged file SHA-256
  `ecd9aa5d5474a140ba0b4969f539bba526d7366296d116e1a6acb956476aba58`).
  Provenance: NousResearch hermes-agent v0.22.5, source commit
  `bf0203a794a07aac3ff764972ab9087baa4e4f4e`, openai-python 2.24.0,
  Python 3.14.9 observed, `chat_completions` wire.
- `opencode-1.19.3-chat-v1` — doc version `"1"` (string), pinned
  `fixture_sha256 2bd4f2599456892bb5d5119a85c9ffe9525796c1aa934ad46b49ce34d18f0e14`
  (raw packaged file SHA-256
  `302c5469d048c7037bac76ba1f40dc2f9ce78e214b133c1e414c928181d9af07`),
  structural fixture bundle SHA-256
  `c84570f8dbbefb727ec90b17df2de802257951bda65e78b352df4742392208d3`.
  Provenance: OpenCode 1.19.3 (`anomalyco/opencode` tag `v1.19.3`, commit
  `e3c4eb242585dcd77be1a867391b7c25fd47ce52`), executable SHA-256
  `179ca421d61eefeadfa0c50e084a6e79c1623734732f0f4593f81ccfd3ab7ee9`,
  archive SHA-256
  `531cff2441129c30f0edd5878af494108ad07f5feb46d7ee29a2a5b830a5765d`,
  `@ai-sdk/openai-compatible 2.0.41` (ai 6.0.168), bun 1.3.14,
  `chat_completions` wire, observed UA
  `opencode/1.19.3 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14`.

Runtime module `version` and `fixture_sha256` derive from the packaged DATA
bytes; only the module id is a source constant. A pin resolves only when its
`fixture_sha256` matches the deployed revision; a digest mismatch fails that
key closed before admission.

Changed services versus base (root-confirmed scope): auth, Chat
orchestration/request-caps, request policy, key policy configuration, key
service, plus the new neutral engine/loader/bindings, schemas, registry,
and CLI wiring. **Unchanged versus base**: quota/accounting foundations,
Redis foundations, provider-forwarding contract/repository foundations.

Operator documentation: `docs/module-architecture.md` (Chat profile
selection), `docs/first-time-operator-guide.md` (pin/clear/inspect via
`keys policy export`, OpenCode `CHAT_MAX_TOOL_DESCRIPTION_BYTES=8192` and
`HARD_MAX_OUTPUT_TOKENS=32768` without changing global defaults),
`docs/cli-reference.md`, `docs/upgrade-runbook.md` (data-only profile-DATA
bind-mount upgrade path; full-revision restore + matching pin for rollback;
registered runtime module version is DATA-derived, not the exported
constant), dossiers `docs/agentic-clients/hermes-0.22.5-chat-v1.md` and
`opencode-1.19.3-chat-v1.md`. Secondary-owned contract docs
(`docs/security-model.md`, `docs/accounting.md`,
`docs/provider-forwarding-contract.md`) integrated from root-accepted
secondary commits.

## Evidence index (receipts; details + exact commands in the record)

1. **Unit** (tested implementation head `5c2bacf8`, Python 3.12): exact
   9-file invocation
   `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest
   tests/unit/test_agent_chat_profiles.py
   tests/unit/test_hermes_aux_reasoning_effort.py
   tests/unit/test_opencode_1193_chat.py
   tests/unit/test_agent_chat_dispatch.py
   tests/unit/test_verify_hermes_chat_capture.py
   tests/unit/test_auth_service.py
   tests/unit/test_key_policy_configuration.py
   tests/unit/test_key_service_create.py
   tests/unit/test_request_policy_service.py
   -q -o addopts= -p no:cacheprovider`
   → **557 passed**, EXIT 0. Provider upstream mocked; the
   `TestR4ChatBindingRevalidation` cases (3 denial + unchanged
   binding-quota path) use fake rate-limiter/quota seams; no native client
   or real Redis/PostgreSQL exercised. One independent overlapping
   receipt (root, at `f9dd35b6`, Python 3.12.15):
   `tests/unit/test_verify_hermes_chat_capture.py` → 16 passed, EXIT 0 —
   its 16 nodes are included in the 557; counts are not summed.
2. **PostgreSQL lifecycle** (owned disposable PG16 at
   `127.0.0.1:54398`, DB `slaif_227_agent_chat_test`,
   `TEST_DATABASE_URL` only for destructive setup; reused per-run
   receipts, chronological and overlapping — not summable): binding
   round-trip (1); projection/dry-run/export strictness + rotation pin
   preservation (4); Hermes runtime dispatch + PG accounting success (1);
   runtime success parameterized Hermes + OpenCode (2); pre-upstream
   denial battery + absent-pin default (13); stream success finalizes PG
   usage, one case per profile (2); provider-error release paths —
   `test_chat_pin_provider_http_error_releases_reservation` and
   `test_chat_pin_stream_provider_error_after_admission_releases_
   reservation`, **both Hermes-only parameters currently, no OpenCode
   parameters exist yet** (2); client disconnect 2 profile executions +
   request-quota 429 (3); disconnect hardening re-executed for the same 2
   profile parameters, superseding the older 2 executions (2, incl. the
   `e3e97918` real-TCP disconnect); model/endpoint/provider/streaming
   policy denials, 4 cases × 2 profiles (8).
   Proves: reservation → finalization with provider-reported usage,
   release on provider HTTP error, **estimated finalization** on client
   disconnect after partial output (settlement from estimated usage, not an
   error release), 429 request-quota denial, pre-upstream denials.
   Does not prove: R4 held-slot revalidation (unit fake-slot only) or real
   Redis behavior (mocked). Current gap: OpenCode parameters for the two
   HTTP 500 release tests do not exist yet.
3. **Native loopback** (task-owned 127.0.0.1 fake, isolated HOME/XDG,
   synthetic bearer; accepted cases reused — **NOT rerun**): Hermes
   `loop7` (7 POSTs), `timeout4` (11 POSTs; outer-watchdog cancellation
   CLI −15 @120s), `error3` (11 POSTs, 68 error lines), `multi1` (3 POSTs,
   2 correlated read_file call/result pairs), `entry-final-positive` (3
   POSTs / 2 calls / CLI 0 / verified cleanup / hash-only receipt);
   OpenCode structural captures in `tests/fixtures/opencode/1.19.3/chat/`.
4. **Static**: `ruff check app tests` → All checks passed, EXIT 0
   (tested implementation head; unchanged by the subsequent docs-only
   commits). `git diff --check` clean.
5. **Governance**: `tests/unit/test_agentic_client_integration_governance.py`
   + `tests/unit/test_provider_governance.py` → **5 passed**, EXIT 0,
   recorded separately. `tests/unit/test_oap_governance.py` → **2 failed,
   8 passed**, EXIT 1 — the activated-order format issue in Status item 1,
   not a code regression.

## Selected default-vs-dedicated decisions

- Keys without a `chat_client_module` pin keep the existing
  `openai-default` Chat behavior; a pin never widens policy, and absent
  pin never changes dispatch.
- Pin strictness: top-level policy document requires `schema_version: 1`;
  pin is `{id, version, fixture_sha256}` with all-string values (numeric
  `version` parses but the resolver raises
  `AgentChatModuleSelectionError`); `null` clears only the Chat binding;
  absent preserves.
- Only `keys policy export` renders the Chat pin; `policy show` /
  `policy effective` do not.
- OpenCode requires operator env `CHAT_MAX_TOOL_DESCRIPTION_BYTES=8192`
  and `HARD_MAX_OUTPUT_TOKENS=32768`; global defaults stay 4096/4096.
- Data-only profile revision = reviewed JSON read-only bind-mount at
  `/app/app/slaif_gateway/modules/clients/profiles/<name>.json` on
  api/worker/scheduler + recreate + matching pin; no new code/image
  required; rollback = full matching revision restore (DATA + matching
  code/image where the revision changed them) + recreate + exact old pin.
- `xhigh` remains selected-profile-only for the pinned profiles; ordinary
  `openai-default` Chat effort vocabulary is unchanged.

## Limitations and honesty disclosures

- The protected live gate is **not_run**: no production live inference,
  real-key binding, or deploy is recorded. This PR is a preprotected
  candidate.
- Historical secondary full-unit run (Python 3.13) FAILED one named
  OpenRouter audio test; aggregate counts and causality are unknown. No
  unrelated audio fix was made and no full matrix rerun is claimed or
  implied.
- `setupfail1` receipt cleanup is unverified/retained; manual cleanup
  only, not automated.
- The manifest is an evidence index, not yet the per-obligation
  test-node-ID mapping (Status item 2); the protected live test plan has
  no actual target or numeric ceilings (Status item 3). Both are declared
  gaps for the canonical 227-b round.
- The two HTTP 500 release tests are Hermes-only currently (no OpenCode
  parameters yet).
- The disconnected-stream round proves mocked-upstream transport close
  before teardown; real-provider disconnect behavior is not covered.

## Protected NOT_RUN gate and bounded proposed live test

`protected.status = not_run`. Proposed (plan incomplete by design — no
invented target or limits):

- Scope: one zero-retry process per profile (`hermes-0.22.5-chat-v1`,
  `opencode-1.19.3-chat-v1`) against a real authorized
  route/model/backend chosen by root review with the exact protected
  authority and valid test key.
- Ceilings to declare before any run: request-count ceiling per profile,
  token/cost ceiling, wall-clock time ceiling (all currently placeholders;
  numeric caps not declared here).
- Assertions: task-owned process cleanup; PG reservation/finalization
  accounting with zero stranded reservations; OpenAI-shaped errors on
  denial; no plaintext key/credential in logs or persisted state.

## Source ownership / cherry-picks

- Primary implemented the neutral engine, loader, Hermes track, shared PG
  qualification, operator docs, and this record/manifest; primary is the
  sole push/PR/OAP/FIFO publisher.
- Secondary worked in its own isolated worktree; its owned OpenCode
  module/profile/fixtures/tests/dossier commits and two root-accepted
  docs-only commits (`14b4a170983dfac35b34b3d9bd89585ec3d74fd859` chain
  for the Hermes dossier integration point; `2e50035738af24a0cf4b0dcd9f05e5adf7c9fca0`
  for `security-model.md` / `accounting.md` / `provider-forwarding-
  contract.md`) were cherry-picked by primary into this branch after root
  review. No secondary push or PR exists.
- Coding agents never merge or enable auto-merge; root owns review/merge.

## Continuation

Root activates the canonical **227-b `AMEND_EXISTING_PR`** on PR #395 to:
(a) correct the activated order's format (resolving the two governance
failures), (b) complete the per-obligation verified test-node-ID mapping in
the manifest, and (c) declare the concrete protected live test plan (target
route/model/backend + numeric ceilings) subject to root review and
protected authority. No new objective number is opened; 228 remains
sequenced after 227 is terminal.
