# OAP Work Order — 004-a

## Objective

Capture, sanitize, version, and test the exact current Codex CLI Responses-wire
protocol baseline before any gateway policy is relaxed. Produce a deterministic
golden fixture and an explicit current-gateway compatibility diff for one named
CLI/model/profile, without calling OpenAI or any real upstream provider.

This objective creates evidence and tooling only. It must end by saying whether
the captured profile is currently compatible; it must not make it compatible.

## GitHub objective state

- Numeric objective: `004`
- Execution round: `004-a`
- PR mode: `CREATE_NEW_PR`
- Repository: `ulfe-lmi/slaif-api-gateway`
- Base branch: `main`
- Starting authoritative `main`:
  `b87171e75e46d12b3edfcaa4f938882c797ee293`
- Starting state: OAP objective 003 is merged as PR #228.
- Required new branch: `oap/004-codex-protocol-capture-golden-fixtures`
- Required PR title: `[OAP 004] Capture Codex Responses protocol baseline`
- Expected unrelated open PR: Dependabot PR #224 only.

Create exactly one new PR for objective 004. Any `004-b` through `004-z`
continuation must amend that same PR and branch.

## Pinned capture target and verified sources

The strategic model verified this execution environment on 2026-08-17:

- installed binary: `/usr/bin/codex`;
- installed version output: `codex-cli 0.147.0`;
- official source release/tag: `rust-v0.147.0`, published 2026-08-07;
- selected bundled model: `gpt-5.6-sol`;
- selected model metadata includes Responses-lite mode, `shell_command`,
  freeform apply-patch, parallel tool calls, and text/image input;
- current gateway hosted/external/Codex tool policy remains fail closed.

Use these primary sources as the documented reference boundary:

- OpenAI Codex configuration reference:
  `https://developers.openai.com/codex/config-reference`
- OpenAI Codex advanced configuration / custom providers:
  `https://developers.openai.com/codex/config-advanced`
- official Codex 0.147.0 release:
  `https://github.com/openai/codex/releases/tag/rust-v0.147.0`
- exact tagged request-compression tests:
  `https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/core/tests/suite/request_compression.rs`
- exact tagged model-catalog schema:
  `https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/protocol/src/openai_models.rs`
- exact tagged loopback Responses test server:
  `https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/app-server-test-client/src/loopback_responses_server.rs`

The official documentation/source establish:

- provider selection/configuration belongs in user-level Codex config;
- custom providers declare `base_url`, an authentication source such as
  `env_key`, and `wire_api="responses"`;
- `responses` is the only supported custom-provider wire API;
- `model_catalog_json` can replace the bundled startup catalog, while
  `codex debug models --bundled` exposes the exact bundled catalog without a
  remote refresh;
- request compression is zstd for the ChatGPT-backend auth path when enabled;
  the tagged official test proves API-key auth is not compressed even when the
  feature is enabled.

The gateway profile uses API-key authentication, so this objective must observe
and assert **no request `Content-Encoding`** for the pinned custom-provider
capture. Do not add request decompression support in this objective.

## Governing instructions

Before editing, read and obey:

1. `AGENTS.md`, especially OAP, test-economy, privacy, provider, and Responses
   rules;
2. `OAP-COMMUNICATION-coding-agent.md` in full;
3. this order;
4. `docs/product-scope.md` Agent/Codex boundary;
5. `docs/responses-compatibility.md`, `docs/compatibility-matrix.md`,
   `docs/security-model.md`, `docs/accounting.md`, and
   `docs/provider-forwarding-contract.md`;
6. `app/slaif_gateway/api/openai_compat.py`;
7. `app/slaif_gateway/services/responses_request_policy.py`;
8. `app/slaif_gateway/services/responses_route_capabilities.py`;
9. the Responses streaming event allowlist in
   `app/slaif_gateway/services/responses_gateway.py`;
10. the pinned official references above;
11. existing OAP/documentation drift tests.

Fetch and verify current GitHub state, the starting main SHA, PR #228 merge,
absence of an objective-004 PR, installed exact CLI version, and clean local
state. If the CLI version no longer equals exactly 0.147.0 or another material
starting fact changed, publish a truthful blocker rather than capturing a
differently versioned client.

## Required start sequence

The strategic model has atomically published this order and
`oap/active=004-a` in the shared checkout.

1. Verify these are the only dirty paths.
2. Preserve their exact bytes; never edit the strategic order/pointer.
3. Create the required branch from current `origin/main`.
4. Preserve `.local-provider-catalog/`, `.codex/`, user Codex config/auth,
   linked worktrees, local secrets, and unrelated state.

Any additional unexplained dirty tracked path is a blocker.

## Narrow Codex-invocation governance exception

Existing HPC documentation says repository verification harnesses must never
launch Codex because Codex is the caller in that workflow. Preserve that rule
and its tests.

This objective authorizes one separate, narrowly named exception:

```text
scripts/capture_codex_protocol.py
```

That script is not an HPC/test runner and must never be called by normal pytest,
CI, application startup, packaging, Docker, migrations, or production. It may
launch the exact pinned local Codex binary only when a human/active work order
explicitly invokes its live-capture/verify command. Document this distinction
in `AGENTS.md` without weakening the existing HPC rule.

## Allowed path scope

Implementation/governance commits may change only:

```text
AGENTS.md
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/responses-compatibility.md
docs/security-model.md
scripts/capture_codex_protocol.py
tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
tests/unit/test_codex_protocol_capture.py
oap/active
oap/orders/004-a-codex-protocol-capture-golden-fixtures.md
```

The final report-publication commit may add only:

```text
oap/reports/004-a-codex-protocol-capture-golden-fixtures.md
```

Do not change application runtime, Responses policy, providers, routing,
accounting, schemas, migrations, dependencies, lock files, config settings,
CI, deployment, existing tests/fixtures, README, pricing/catalog data, or prior
OAP history.

## Required capture tool

Create `scripts/capture_codex_protocol.py` using Python standard library plus
already-installed project imports only. Do not add a dependency.

The script must have explicit, non-default live actions such as:

- `capture --write-fixture` — exact-version live capture and atomic sanitized
  fixture write;
- `verify-live` — repeat an in-memory live capture and compare it byte-for-byte
  or canonical-JSON-equivalent to the checked-in fixture without rewriting it;
- a pure fixture validation mode if useful.

Exact CLI spelling may differ, but the safety/behavior below is mandatory.

### Version and target pinning

- Call `<codex-binary> --version` first.
- Require exact normalized version `0.147.0` and exact raw family
  `codex-cli 0.147.0`.
- Require model `gpt-5.6-sol` and profile id
  `api-key-responses-baseline`.
- Refuse an unknown version/profile/model before binding a server, starting
  Codex, or writing a fixture.
- Record official source tag `rust-v0.147.0` in sanitized metadata.
- Never silently bless the locally installed “latest” version.

### Isolated Codex execution

For each live run:

- create a private temporary `CODEX_HOME` and empty temporary working directory;
- do not read the human's real `~/.codex/config.toml`, auth store, session
  history, plugins, memories, rules, or project `AGENTS.md`;
- run `codex exec` with `--ephemeral`, `--ignore-user-config`,
  `--ignore-rules`, `--skip-git-repo-check`, read-only sandbox, and approval
  policy `never`;
- disable startup update checks and any unnecessary network/search/plugin/MCP
  behavior through explicit supported config/isolation;
- use a custom provider id dedicated to capture, `wire_api="responses"`, a
  loopback `base_url`, `requires_openai_auth=false`, zero HTTP/stream retries,
  and a dedicated dummy `env_key`;
- remove real OpenAI/OpenRouter/Azure/AWS/provider/auth variables from the child
  environment; supply only a fixed non-secret canary token under the dedicated
  capture env-var name;
- use a fixed non-sensitive capture prompt canary, never a user prompt,
  repository content, or AGENTS content;
- set short bounded subprocess/server timeouts and terminate safely on timeout;
- discard temporary state after the run.

The script must not make a real provider call. The only model-provider target
is a server bound to `127.0.0.1` on an ephemeral port. `localhost` name
resolution is not sufficient; validate the resolved target is loopback.

### Loopback server and bounded raw handling

- Accept only the expected `POST .../responses` request.
- Reject any other method/path and multiple unexpected requests fail closed.
- Cap header and body bytes before parsing.
- Handle the pinned API-key profile as plain JSON and assert no
  `Content-Encoding`; unknown/compressed encodings fail safely without dumping
  body bytes.
- Keep raw headers/body only in memory for the shortest processing window.
- Never write raw request bytes, request JSON, subprocess output, Codex logs,
  prompts, instructions, client IDs, authorization values, or tool schemas to
  disk.
- Never include raw payloads in exceptions or stdout/stderr.

Return a minimal fixed SSE sequence known to Codex 0.147.0:

- `response.created` with a fixed synthetic response id; and
- `response.completed` with the same synthetic id and zero synthetic usage.

Use exact `text/event-stream`, bounded fixed JSON, and connection close. The
successful zero-output completion must prove the pinned Codex response parser
accepted the mock; no model output or tool execution is needed.

### Bundled model-catalog evidence

Run `codex debug models --bundled` under the same isolated home (no refresh),
parse it in memory, and select only `gpt-5.6-sol`.

Persist only an allowlisted safe metadata subset needed to explain client
request/tool behavior, such as:

- slug;
- visibility;
- shell type;
- apply-patch tool type;
- parallel-tool-call support;
- Responses-lite flag;
- input modality names;
- reasoning level names and safe booleans;
- context/compaction numeric bounds if present.

Never persist `base_instructions`, `model_messages`, instruction templates,
descriptions, migration copy, NUX copy, or any free text from the catalog.

### Sanitized structural fixture

Atomically write only:

```text
tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
```

Use canonical deterministic JSON: stable key ordering, fixed indentation,
newline at EOF, no timestamps/random ports/request IDs.

The fixture must contain only safe derived structure:

- schema version, pinned CLI/source/model/profile identity;
- request method and normalized `/v1/responses` path;
- sorted header names and safe header classifications/presence only;
- authorization present/redacted boolean, never value/token/fingerprint/hash;
- content type and absence of content encoding;
- sorted request top-level field names;
- recursively sanitized type/field/discriminator structure;
- input item roles/types/content-part types and field names without text;
- tool type/name taxonomy and parameter-schema shape without descriptions,
  defaults, examples, raw definitions, or arbitrary string values;
- safe selected bundled-catalog metadata;
- fixed mock SSE event names and safe field/type shapes;
- subprocess success/accepted-mock booleans without stdout/stderr;
- a current gateway compatibility diff.

Allowlist only contract-critical discriminator values (`type`, role, tool name,
schema primitive type, selected model/profile ids, event name). Replace or omit
all other strings. Do not store raw string length/hashes that could disclose or
fingerprint prompts, AGENTS content, client identifiers, descriptions, schema
text, paths, secrets, or personal data.

The fixed prompt and dummy-token canaries must be absent from the fixture.

### Current gateway compatibility diff

Derive the comparison from the captured fixture and the current code contracts,
without changing them:

- `_SUPPORTED_FIELDS` and relevant input/tool rules in
  `responses_request_policy.py`;
- supported local function/custom tool boundary;
- `_ALLOWED_RESPONSES_STREAM_EVENT_TYPES` plus the separately handled terminal
  `response.completed` event;
- documented current Responses capability and fail-closed rules.

Record observed supported and rejected:

- top-level request fields;
- input item/content types;
- tool types/namespaces;
- fixed SSE events.

Record safe reason codes, not payload excerpts. The fixture must set overall
status to `not_compatible` if any required captured request/tool/event element
is rejected. Do not soften the diff to produce compatibility. The expected
004 result is evidence, not success marketing.

## Required tests

Create `tests/unit/test_codex_protocol_capture.py`. Normal pytest must never
launch `codex` or bind a network listener. Test pure parsing, sanitization,
validation, and checked-in fixture behavior with mocks/in-memory values.

Cover at least:

1. exact version parsing and mismatch refusal before capture/write;
2. allowlisted model-catalog sanitization excludes every free-text/instruction
   field;
3. header sanitization never retains authorization/user-agent/client-id values;
4. request sanitization removes prompt/instruction/metadata values and raw tool
   descriptions/schemas while keeping required structural discriminators;
5. unknown content encoding, oversized headers/body, unexpected method/path,
   extra requests, timeout, nonzero Codex exit, malformed JSON, and malformed
   SSE fail with safe messages and no raw echo;
6. fixture schema/version/profile/model identity and deterministic canonical
   serialization;
7. prompt/token/secret/client-id/AGENTS/schema-description canaries are absent;
8. checked-in observed request path is `/v1/responses`, auth is redacted,
   content encoding is absent, and mock acceptance succeeded;
9. compatibility diff is reproducible from current gateway constants and
   remains `not_compatible` with at least one explicit captured rejection;
10. future/altered CLI version and structurally altered fixture fail validation;
11. module import and unit tests do not execute subprocesses, bind ports, read
    real Codex config/auth, or write outside test temp paths;
12. capture output path is restricted to the versioned fixture tree and live
    write requires an explicit flag.

Use fixed synthetic values only. No real keys or provider traffic.

## Documentation requirements

Create `docs/codex-compatibility.md` as the canonical versioned Codex contract.
It must document:

- captured CLI/source/model/profile identity;
- official source links and checked date;
- user-level custom-provider example using `model_provider`,
  `[model_providers.slaif]`, gateway `base_url`, `env_key`, and
  `wire_api="responses"`;
- provider/auth settings cannot be safely supplied by project-local config;
- `model_catalog_json`/bundled catalog behavior and why compatibility is pinned
  to model metadata as well as CLI version;
- API-key request-compression result (no `Content-Encoding`) and the distinct
  ChatGPT-backend zstd behavior, without promising future versions match;
- capture/sanitization/privacy invariants;
- exact fixture regeneration/verification commands;
- version-upgrade workflow: new directory/fixture/review, never overwrite old
  evidence or silently accept drift;
- the compatibility diff with safe rejected field/item/tool/event names and
  reasons;
- status: **CAPTURED, NOT YET CODEX-COMPATIBLE**;
- future objective boundaries 005–011;
- no production/provider/release claim.

The config example must use standard `OPENAI_API_KEY` as the client-side
gateway-issued key per repository contract, never a real value. Clearly say
the gateway later substitutes the upstream provider credential.

Update minimally:

- `AGENTS.md` — add the versioned compatibility invariant and the one narrow
  capture-script exception without weakening HPC rules;
- `docs/responses-compatibility.md` — link the capture and state current Codex
  gaps remain rejected;
- `docs/compatibility-matrix.md` — add a Captured/Not compatible row, not an
  Implemented Codex claim;
- `docs/security-model.md` — document raw-in-memory-only capture, fixture
  redaction, isolated dummy auth, loopback, and absence of content persistence.

README stays unchanged because Codex usage is not yet supported.

## Explicit non-goals

- No gateway acceptance/normalization of Codex fields, items, tools, or events.
- No runtime/API/provider/routing/quota/accounting/schema/migration change.
- No real OpenAI/OpenRouter/other provider request or key.
- No user/project prompt, AGENTS, source-code, tool-output, personal data, or
  client identifier capture.
- No raw request/header/body/log/fixture artifact.
- No ChatGPT login/auth reuse and no human Codex config/auth mutation.
- No hosted tool, MCP, shell, patch, or tool execution.
- No custom model catalog import into SLAIF.
- No claim that Codex works through SLAIF.
- No CI invocation of the installed Codex binary.
- No dependency or CI change.
- No production/staging/database/email/catalog action.
- No full local suite, integration, E2E, browser, Docker, or HPC run.
- No release/tag/GitHub setting change.
- No second PR, merge, or auto-merge by the coding agent.

## Human test-economy instruction

The human explicitly prohibited routine full suites. Run the two deliberate
live loopback captures and the focused tests below only. Do not run any broad
local test matrix. Normal GitHub CI supplies broad regression evidence.

## Required local capture and focused verification

The coding agent may adapt flag names to the implemented CLI, but must report
literal executed commands and results.

1. Confirm the exact installed binary/version:

```bash
/usr/bin/codex --version
```

2. Run explicit live capture/write against loopback only:

```bash
.venv/bin/python scripts/capture_codex_protocol.py capture \
  --codex-binary /usr/bin/codex \
  --expected-cli-version 0.147.0 \
  --model gpt-5.6-sol \
  --profile api-key-responses-baseline \
  --output tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json \
  --write-fixture
```

3. Repeat live capture in memory and compare without rewriting:

```bash
.venv/bin/python scripts/capture_codex_protocol.py verify-live \
  --codex-binary /usr/bin/codex \
  --expected-cli-version 0.147.0 \
  --model gpt-5.6-sol \
  --profile api-key-responses-baseline \
  --fixture tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
```

4. Run an expected version-mismatch refusal that performs no capture/write:

```bash
.venv/bin/python scripts/capture_codex_protocol.py verify-live \
  --codex-binary /usr/bin/codex \
  --expected-cli-version 0.146.0 \
  --model gpt-5.6-sol \
  --profile api-key-responses-baseline \
  --fixture tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
```

This command must fail nonzero with a safe version-mismatch message before
binding/capture. Report it as an expected negative test, not a failed objective.

5. Run focused tests only:

```bash
.venv/bin/python -m pytest tests/unit/test_codex_protocol_capture.py -q
.venv/bin/python -m pytest tests/unit/test_documentation_contract_drift.py -q
.venv/bin/python -m pytest tests/unit/test_oap_governance.py -q
.venv/bin/ruff check scripts/capture_codex_protocol.py tests/unit/test_codex_protocol_capture.py
git diff --check
```

6. Run bounded safety/status scans:

```bash
rg -n "CAPTURED, NOT YET CODEX-COMPATIBLE|0.147.0|rust-v0.147.0|wire_api|Content-Encoding|not_compatible" docs/codex-compatibility.md docs/responses-compatibility.md docs/compatibility-matrix.md tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
rg -n "SLAIF_CAPTURE_PROMPT_CANARY_DO_NOT_PERSIST|SLAIF_CAPTURE_TOKEN_CANARY_DO_NOT_PERSIST" tests/fixtures/codex docs/codex-compatibility.md
git status --short
```

The canary scan must have no matches in fixtures/docs. Do not print the raw
capture to prove absence.

## GitHub CI and merge gate

After pushing all non-report commits and creating the PR, inspect actual GitHub
checks. The expected final set is the standard ten checks. Report every
success/failure/pending/missing state accurately.

The coding agent must not merge or enable auto-merge. The strategic model will
independently inspect the fixture for forbidden content, reproduce focused
validation, verify the OAP report commit, and wait for all final-head checks.

## Acceptance criteria

1. Exact Codex CLI 0.147.0/gpt-5.6-sol/API-key Responses structural evidence
   is captured through loopback with no provider traffic.
2. The checked-in fixture is deterministic, versioned, sanitized, bounded, and
   contains no prompt/instruction/secret/client/tool-schema content.
3. API-key request compression is observed as absent and documented separately
   from ChatGPT-backend zstd behavior.
4. Bundled model metadata is allowlisted and contains no free text.
5. Live recapture matches the fixture; a version mismatch fails before capture.
6. Compatibility diff is reproducible and honestly says `not_compatible` with
   explicit safe current rejections.
7. Normal tests never execute Codex or network and all focused checks pass.
8. Docs give an accurate user-level future config and version-upgrade workflow
   without claiming current compatibility.
9. Existing provider-secret, content-minimization, fail-closed, accounting, HPC,
   and OAP contracts remain intact.
10. Exactly one PR contains only allowed paths; final report/OAP invariants pass;
    the coding agent does not merge.

## Commit, PR, and immutable report requirements

Commit the unchanged strategic order and active pointer with the implementation
commit set. Stage only explicit paths. Push the required branch and create one
non-draft PR with the exact title/base.

The PR description must state pinned version/profile, loopback-only capture,
privacy design, compression result, compatibility `not_compatible` status,
focused verification, and no runtime/provider call.

Before reporting, push all non-report commits and record the literal
implementation head SHA. Publish exactly one immutable report:

```text
oap/reports/004-a-codex-protocol-capture-golden-fixtures.md
```

Use the complete coding-agent report structure. Include:

- authoritative PR/branch/SHA and all commits;
- exact installed version and official source tag;
- literal live capture/write, live verify, expected mismatch, and focused-test
  commands/results;
- safe observed structural summary and compatibility rejected names/reasons,
  never raw content;
- exact fixture path/hash/size;
- proof only loopback/dummy auth was used;
- broad suites NOT RUN;
- implementation-head GitHub checks;
- documentation-impact line;
- no production/secrets/provider access, no extra PR, no merge;
- literal `Implementation head SHA: <40 hex>` and
  `Report publication commit: SELF`.

The final report-only commit must have that implementation head as first parent
and change only the new report. Push and verify remote head/parent/path/bytes,
then signal exact two-byte `OK` and return to the listener.

## Failure and blocker handling

Never capture a different CLI version, call a real provider, persist raw data,
weaken sanitizer tests, or change gateway policy to make the result look
compatible. Publish truthful partial/blocked/failed evidence for version drift,
unsafe output, nondeterminism, mock incompatibility, or publication failure.

Do not merge under any circumstance.
