# OAP Objective 155-c Report — Codex 0.149 Local Coding preflight closure

Report publication commit: SELF

## Immutable execution identity

- Objective: `155-c`
- Active selector SHA-256: `1e02fbc1d26e4970645533da78ae5cec6ff03260c5d324a1e29807d8dce71817`
- Work-order SHA-256: `a9fcbe7667a9dd152d6ea62e06871e510bb361d82e79a9bdef1f4c65dcc8f770`
- Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
- Existing PR: #291, branch `oap/155-local-coding-signed-server-module`
- Prior PR head: `c68fa511141a0c21d420e7a94100f717e674553f`
- Final implementation head: `02670e3275ff57850aeaa9bc8aae4ed3c8e2f124`

The activated order and `oap/active` selector were committed unchanged. The
coding agent did not merge PR #291 or enable auto-merge.

## Exact 0.149 capture and production-path proof

The exact official npm Codex CLI 0.149.0 binary reported `codex-cli 0.149.0`.
It ran in a private disposable home/workspace against a loopback synthetic
Responses endpoint with no provider key or model call. The fresh raw request
was passed, in memory and before disposal, through the registered
`CODEX_0149_CLIENT_MODULE` normalizer and its version-owned
`CODEX_0149_POLICY_SPEC`. The production policy was invoked with the actual
independent envelope, client-tool, and streaming gates enabled.

The live verifier result was:

```text
VERIFY_LIVE_0149_OK status=structural_candidate production_path=passed
```

The production path returned exactly the candidate types `tool_search` and
`web_search`. Candidate declarations were preserved for the adapter-managed
path, while hosted-tool admission was disabled. Raw request values were not
returned, serialized, logged, persisted, or included in the fixture.

The checked-in v2 fixture is a separate canonical artifact:

- Path: `tests/fixtures/codex/0.149.0/responses-structural-v2.json`
- Module version: `2`
- Profile: `responses-structural-capture-v2`
- SHA-256: `baba5403949d44900d8bd3cdef3f7c65bf6abd5109b78bda0b67f3f9787118d1`
- Observed declaration counts: `function=5`, `custom=1`, `tool_search=1`, `web_search=1`
- Exact pair: `codex-0.149-responses-v1 -> local-coding-v1`
- Qualification/provider E2E: none

The historical fixture remains byte-for-byte unchanged:

- Path: `tests/fixtures/codex/0.149.0/responses-structural.json`
- SHA-256: `0a0b62bc7fec7b4da2c504f7db67d260ebe3e2d9fe6be64548c82207a787061d`

`git diff --exit-code c68fa511141a0c21d420e7a94100f717e674553f..02670e3275ff57850aeaa9bc8aae4ed3c8e2f124 -- tests/unit/test_responses_codex_envelope.py`
was clean. The final implementation diff contains no change to that path.

## Pair and authority boundary

The static registry adds exactly one new compatibility entry:
`codex-0.149-responses-v1` to `local-coding-v1`. Every other 0.149 server
pair is denied. The exact server-side module metadata, route/provider kind,
and complete Local Coding route contract remain required before transport,
quota, or provider work.

The 0.149 module validates captured top-level value classes, exact candidate
field sets, bounded candidate values, neutral choice, and nested authority
markers. Explicit candidate choices and `required` with only adapter-managed
candidates fail before policy/provider work. `required` remains valid when a
local function/custom tool is present. URLs, credentials, headers, MCP,
preview/versioned hosted names, malformed shapes, and nested search
declarations fail closed.

Candidate facts are transient and reach only the exact Local Coding adapter.
They are not executed, converted into OpenAI hosted search, used for route or
provider selection, placed in external-tool fences/holds, charged hosted-tool
fees, or persisted as content.

## Accounting and transport evidence

The PostgreSQL-backed mocked official-client E2Es passed for both non-streaming
and typed Responses SSE Local Coding requests. Both assert:

- one ordinary `strict_bounded` reservation and terminal finalized ledger;
- empty external capability and destination facts;
- null external provider and route facts;
- Gateway key external fence state `none`;
- no external-tool fee/hold facts in ledger metadata;
- provider usage finalization and zero pending reserved tokens; and
- service Bearer substitution with no Gateway bearer forwarding.

The Local Coding adapter remains Responses-create/stream only. Input-token
count, compact, stored lifecycle, Conversations, Audio, Embeddings, Realtime,
Chat, and all other operations remain rejected before unsigned transport.

Local Coding PR #7 was used only as read-only blocker evidence at immutable
005-g head `cd1a16cbddc4ff7e1ad2b2769fc1311479f0dc97`. The protected Qwen/full
005-h cross-repository acceptance was not run or modified in this objective.

## Verification ledger

| Check | Result |
| --- | --- |
| Exact disposable Codex 0.149 capture and literal version | `PASSED` |
| Raw capture through registered 0.149 normalizer and 0.149 policy/gates | `PASSED` |
| v2 fixture canonical validation, privacy scan, and digest | `PASSED`; `baba5403949d44900d8bd3cdef3f7c65bf6abd5109b78bda0b67f3f9787118d1` |
| Historical fixture byte/digest guard | `PASSED`; `0a0b62bc7fec7b4da2c504f7db67d260ebe3e2d9fe6be64548c82207a787061d` |
| Focused client, policy, architecture, Local Coding, factory, and quota tests | `PASSED` |
| PostgreSQL integration | `PASSED`; safe disposable `slaif_gateway_oap_155c_test` |
| Mocked official-client non-streaming and typed SSE E2E | `PASSED`; 2 tests |
| Ruff and `git diff --check` | `PASSED` |
| Documentation hygiene | `PASSED`; `DOCUMENTATION_CHECK=OK files=79` |
| Alembic head | `PASSED`; unchanged at `0024_quota_reservation_accounting_facts` |
| Final PR #291 checks on `02670e3` | `PASSED`; all ten required checks successful |
| Broad local suite | `NOT RUN` by order |
| Real provider/model/Qwen, production cutover, release, and certification | `NOT RUN` |

No real upstream call, real email, protected Qwen mutation, production
deployment, release, or production/security/compliance certification claim
follows.

## Safety and scope audit

- No schema, migration, dependency, Compose, deployment, external-repository,
  release, or production change was made.
- No `DATABASE_URL` destructive setup was used; the PostgreSQL evidence used a
  dedicated disposable test database owned by the current user.
- No raw capture values, credentials, prompts, outputs, IDs, paths, URLs,
  headers, or bodies were committed or printed by the successful verifier.
- The final implementation range from prior accepted head through `02670e3`
  excludes `tests/unit/test_responses_codex_envelope.py`.

The final report-only commit must have `02670e3275ff57850aeaa9bc8aae4ed3c8e2f124`
as its first parent and change only this report path.
