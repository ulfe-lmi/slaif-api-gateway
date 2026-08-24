# OAP Objective 154-b Report — Codex ownership and capture truth closure

Report publication commit: SELF

## Immutable execution identity

- Objective: `154-b`
- Active selector SHA-256: `562a827c67dad2741908d286d26ebebb56d85e9eb0823372f99f3a7e464681b6`
- Work-order SHA-256: `223f6a5c050df9a70597e5220e30d78700455dfd467452ebffb7beee9f1ba382`
- Base: `main @ 4b04d6519c11c684b2eac70dc1757c515d2ea4ab`
- Activation commit: `525619e4a17c557319021ae67b25671a2bb117c0`
- Implementation commit: `3dc8a2b2aca1af4d8010b46021092c1520512960`
- Branch: `oap/154-versioned-codex-client-modules`
- PR: #290, `obj154: move Codex protocols into versioned client modules`

The 154-b activation commit contains the exact selector and order bytes. This
report is the sole later report-only commit for the amendment.

## Ownership closure

Generic Responses policy no longer imports the Codex-named support module or a
large private Codex constant surface. Ordinary message/content/image/file
shapes, generic function/custom tools, hosted-tool taxonomy, conversation
metadata, and text-format primitives now live in neutral pure
`modules/clients/responses_support.py`.

`ResponsesClientPolicySpec` is a public neutral contract. The exact
`codex-0.147-responses-v1` module owns and constructs its immutable policy spec,
including envelope/item/replay/compaction shapes, metadata vocabulary,
taxonomies, limits, authority exceptions, and fixture facts. Gateway
orchestration passes the selected module spec into `ResponsesRequestPolicy`;
core retains authorization, route selection, HMAC ownership, persistence,
quota, pricing, accounting, Redis, and provider behavior.

The existing complete legacy Codex key path still derives the qualified 0.147
module from server-side policy facts. Ordinary OpenAI traffic remains on the
default client module. Architecture tests now assert that generic policy has
no direct Codex private imports, 0.147/0.148 IDs, or exact client taxonomy
tuples, and that generic primitives are not owned by Codex support.

## Exact 0.149 capture truth

The exact official npm source package `@openai/codex@0.149.0` was previously
verified as raw `codex-cli 0.149.0`; its retained structural fixture was
updated and now has SHA-256
`0a0b62bc7fec7b4da2c504f7db67d260ebe3e2d9fe6be64548c82207a787061d`.
The disposable binary, private CODEX_HOME, npm cache, workspace, and logs
were removed.

The retained capture observes `web_search` with the exact field shape
`{type, external_web_access}`. It observes no `tool_search` declaration. The
0.149 module and fixture findings now accept only that observed
`web_search` candidate; `tool_search` is rejected as unobserved. A fixture
self-consistency test derives candidate types and shapes from the capture
section and requires exact equality with the module constants and findings.
The 0.149 module remains pairless/default-denied and cannot reach hosted-tool
fencing, accounting, quota, Redis, or provider work.

## Exact 0.147 E2E preservation evidence

The prior hard-coded `/usr/bin/codex` verifier failure was diagnosed as the
binary-path preflight boundary. The verifier now accepts an optional
`SLAIF_CODEX_BINARY` only when it is absolute, owner-owned, regular,
non-group/world-writable, non-symlink, and exact-version validated. Default
behavior remains `/usr/bin/codex`; unsafe paths produce fixed safe output.

The exact official npm source package `@openai/codex@0.147.0` was obtained in
a private disposable directory. It verified as raw `codex-cli 0.147.0`; the
tarball SHA-512 was
`1102c45de7001b6a6dc48ed4a41328d9347f81ae79f7afdcfceb1817fd0ba140e1e4900d67b2281aa97304459bb84550efa25e3c86ed4d6fe2842929d5aed9df`.

The existing isolated local Gateway verifier was rerun with that explicit
absolute binary, a disposable PostgreSQL database, private ephemeral Redis,
numeric-loopback scripted upstream, and no provider credential. It returned:

```text
RESULT=OK
CLI_VERSION_MATCHED=true
FIXTURE_DIGEST_MATCHED=true
SCENARIO_COUNT=5
TEXT_COMPLETION_SEEN=true
LOCAL_EXEC_SEEN=true
LOCAL_EDIT_SEEN=true
WORKSPACE_MARKER_MATCHED=true
MULTI_ROUND_REPLAY_SEEN=true
ENCRYPTED_REASONING_REPLAY_SEEN=true
CACHE_READ_USAGE_SEEN=true
CACHE_WRITE_USAGE_SEEN=true
LONG_CONTEXT_TIERS_SEEN=true
V1_COMPACT_SEEN=true
POST_COMPACT_CONTINUATION_SEEN=true
QUOTA_REJECTION_SEEN=true
QUOTA_REJECTED_BEFORE_UPSTREAM=true
STREAM_INTERRUPTION_SEEN=true
PROVIDER_ERROR_SEEN=true
ACCOUNTING_MATCHED=true
OUTSTANDING_RESERVATIONS=0
PROVIDER_AUTH_REPLACED=true
OUTBOUND_HEADERS_SANITIZED=true
LOOPBACK_ONLY=true
RAW_PAYLOADS_PERSISTED=false
REDIS_PRIVATE_EPHEMERAL=true
WORKSPACES_REMOVED=true
REAL_PROVIDER_CALLED=false
```

All 0.147 temporary runtime artifacts and the disposable PostgreSQL/Redis
state were cleaned after the run.

## Verification

| Area | Result |
| --- | --- |
| Focused unit, architecture, module, profile, policy, stream/replay/compaction, verifier, and docs suites | `782 passed in 9.98s` |
| PostgreSQL: 0.149 no-side-effect denial plus 0.147 accounting/replay | `3 passed`; isolated disposable database; reservation/ledger denial counts unchanged |
| Exact 0.147 local Gateway E2E | `RESULT=OK`; five scenarios; no real provider |
| Documentation checker | `DOCUMENTATION_CHECK=OK files=79` |
| Documentation contract tests | passed |
| Alembic head | `0024_quota_reservation_accounting_facts (head)` |
| Ruff focused E4/E7/E9/F check and `git diff --check` | pass |
| Final GitHub checks on implementation head | all ten successful: Unit/lint/migration, PostgreSQL integration, OpenAI-compatible E2E, Playwright, Docker Compose, Documentation hygiene, CodeQL, Analyze Python, Analyze python, Analyze javascript-typescript |

No real upstream, Local Coding, Qwen, OpenCode, production Compose, email,
release, certification, compliance, or broad local suite was run.

## GitHub and publication audit

Before report publication, PR #290 remained open, non-draft, mergeable, clean,
and without auto-merge. The implementation head was `3dc8a2b` and the
report-only commit must use it as its first parent and change only this report
path. The coding agent does not merge or enable auto-merge.
