# Objective 156-a — agentic doctrine and Codex 0.149 client contract

RESULT=FAILED

Repository: `ulfe-lmi/slaif-api-gateway`
Base: `2823b1b8ca95aeb795b2df8bba49c2d9f2cb9ddf` (`main`)
Branch: `oap/156-agentic-doctrine-codex-0149-client-contract`
PR: #293 — https://github.com/ulfe-lmi/slaif-api-gateway/pull/293
PR state: OPEN, non-draft, no auto-merge
Activation commit: `8721289ee51396ecdffc2c83d8ee57321e1b62e4`
Implementation head: `5e37809e339a29178036a8793b223be8c3776a4a`
Report publication commit: SELF

This report is the single report-only publication for 156-a. Its first parent
must be the implementation head above and its only changed path must be this
report. No merge, auto-merge, protected request, Local Coding request, or real
provider request was made.

## Scope and changed paths

The activation commit contains only `oap/active` and the exact 156-a order.
The implementation diff from the authorized base contains:

```text
AGENTS.md
app/slaif_gateway/modules/clients/codex_0149.py
app/slaif_gateway/modules/contracts.py
app/slaif_gateway/services/responses_request_policy.py
docs/compatibility-matrix.md
docs/module-architecture.md
docs/responses-compatibility.md
scripts/capture_codex_protocol.py
tests/fixtures/codex/0.149.0/responses-session-relationship-v3.json
tests/fixtures/codex/0.149.0/responses-structural-v2.json
tests/integration/test_codex_client_modules_postgres.py
tests/unit/test_agentic_client_integration_governance.py
tests/unit/test_codex_client_modules.py
tests/unit/test_codex_protocol_capture.py
tests/unit/test_responses_request_policy.py
```

The `app/` diff inventory is exactly the three app paths listed above. No
other product, server, route, transport, accounting, schema, migration,
configuration, or Local Coding path changed.

## Exact source and fixture identity

The selected implementation/tool/fixture blobs are the required blobs from
source snapshot `4eb768254fcde0a4108bcabb35f175a74bd07a3f`:

| Path | Final blob |
| --- | --- |
| `app/slaif_gateway/modules/clients/codex_0149.py` | `c196eb2f9608248303d6d9f2126d1d7596438866` |
| `app/slaif_gateway/modules/contracts.py` | `653ec8f8770c2c5c464663d614bda126d6e5ace7` |
| `app/slaif_gateway/services/responses_request_policy.py` | `88f3ff334818aa31b06dbf12066beb224e6b5bc1` |
| `scripts/capture_codex_protocol.py` | `7bc06d39fedbe3d6d6957137c5afc0e751f38f77` |
| `tests/fixtures/codex/0.149.0/responses-structural-v2.json` | `c182dd195312368d58c80f25c915e83e8474a470` |
| `tests/fixtures/codex/0.149.0/responses-session-relationship-v3.json` | `a0073a638b82750b3752ac5b78f5df91f97d7d56` |

The inherited `AGENTIC_CLIENT_INTEGRATION.md` remained byte-for-byte
unchanged: blob `7c48c679d14aa127f0c31fc3260e4a3fb01ee25f`, SHA-256
`1b498f8d15e11ff21639aa8981cc1fcc17b2581708e5d774d11f8955e38c74c8`.

## Doctrine, governance, and documentation

`AGENTS.md` adopts the inherited doctrine in the authority hierarchy and adds
the required concise `Agentic client integrations` constitution section. The
precedence statement preserves the repository human/OAP hierarchy and makes
the detailed doctrine authoritative for this subject.

The governance test passed and verifies the doctrine link, required authority
markers, default-denied/static module constraints, and the three documentation
links without claiming full-prose immutability. All three links resolve to the
unchanged inherited doctrine:

- `docs/module-architecture.md`: present and resolves.
- `docs/responses-compatibility.md`: present and resolves.
- `docs/compatibility-matrix.md`: present and resolves.

Documentation updated: `AGENTS.md`, `docs/module-architecture.md`,
`docs/responses-compatibility.md`, and `docs/compatibility-matrix.md` to adopt
the bounded doctrine and document the default-denied Codex 0.149 structural
contract. No Local Coding, deployment, release, or production-readiness
claim is made.

## Contract and capture evidence

The final Codex client module is version `0.149.0`/module version 3 and is a
pure, static, default-denied client dialect module. It has no active server
pair in this intermediate PR and grants no provider, hosted-tool, Local, or
accounting authority. The focused no-pair runtime-selection regression
rejects selection before accounting/provider side effects.

A task-local exact `@openai/codex@0.149.0` installation was used only for the
bounded capture verifiers. Fresh structural and session captures both passed:

```text
VERIFY_LIVE_0149_OK status=structural_candidate production_path=passed
VERIFY_SESSION_0149_OK status=namespace_candidate production_path=passed
```

Both captures had `provider_calls=0` and empty stderr. No external provider,
protected endpoint, Local Coding service, or non-loopback service was used.

## Checks

Observed focused results:

- `tests/unit/test_agentic_client_integration_governance.py`,
  `tests/unit/test_codex_client_modules.py`,
  `tests/unit/test_codex_protocol_capture.py`, and
  `tests/unit/test_responses_request_policy.py`: **260 passed**, 0 failed,
  0 skipped, 0 xfail; empty stderr.
- `tests/integration/test_codex_client_modules_postgres.py`: **3 passed**,
  0 failed, 0 skipped; empty stderr.
- Ruff check on all changed Python paths: passed.
- Python compilation on all changed Python paths: passed.
- `ruff format --check` on the exact selected snapshot paths: **failed** for
  seven mandated exact blobs. No formatting rewrite was applied because that
  would violate the required source/fixture blob identities.

On implementation head `5e37809e339a29178036a8793b223be8c3776a4a`, all ten
required GitHub checks were observed successful: Unit/lint/migration head,
Analyze (javascript-typescript), Analyze Python, Analyze (python), PostgreSQL
integration tests, OpenAI-compatible E2E tests, Playwright browser smoke,
Docker Compose smoke, Documentation hygiene, and CodeQL.

The formatter failure is an unresolved acceptance gate. Accordingly this
report is FAILED and makes no implementation, compatibility, release,
deployment, or production acceptance claim. The exact mandated blobs were
preserved and the conflict was reported rather than silently rewritten.

## Safety and cleanup

No protected or real-provider traffic ran. No Local Coding/server pair was
activated. PostgreSQL evidence used only a disposable task-local test
database; it was removed. The task-local exact Codex installation, virtual
environment, capture fixtures' temporary workspace, and generated temporary
state were removed. No secrets, provider credentials, raw request values,
session identifiers, or response content were printed, persisted, or
committed. The inherited doctrine and unrelated worktrees/state were not
modified.

Limitations: this is doctrine adoption plus a default-denied Codex 0.149
client contract only. It is not Local-Coding activation, a client/server-pair
qualification, a clean-stack acceptance, a deployment qualification, a
release, certification, or production readiness result.
