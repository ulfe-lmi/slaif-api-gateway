# Objective 160-a report — ID-less tool replay and clean-stack closure

RESULT=FAILED

Objective 160-a was executed on the new Objective-160 PR only. The required
exact Codex 0.149.0 local fake two-turn verifier was run with a task-local npm
installation, numeric loopback, a disposable PostgreSQL database, the real
Gateway candidate, and a bounded fake Local endpoint. It failed closed before
the fake Local endpoint at the Gateway pre-Local boundary. No protected,
provider, Qwen, or real Local Coding service was contacted.

## OAP and Git topology

- Repository: `ulfe-lmi/slaif-api-gateway`
- Base: `main` at `07ae3cce21c52654bdec1f50bc7e5da9c59082c6`
- Branch: `oap/160-idless-tool-replay-clean-stack`
- PR: #297, open, no merge and no auto-merge
- Activation commit: `956224754b8a103dcb0ceb30a2382af0c0b4f746`
- Implementation head (`G_clean`): `d625af9eb3df45c163342a05e03cda2d3dd0d7c4`
- Implementation parent: `956224754b8a103dcb0ceb30a2382af0c0b4f746`
- Report publication commit: SELF
- Remote PR head was verified equal to `G_clean` before publication.

The activation order and `oap/active` were committed unchanged in the
activation commit. The implementation commit contains no report.

## Exact reconstructed production blobs

All six required production files match their Objective-155 accepted blobs:

| File | Required blob | Result |
| --- | --- | --- |
| `app/slaif_gateway/db/repositories/codex_replay.py` | `2e5ddd592c3a3f39ffef789c442dba884444919c` | MATCH |
| `app/slaif_gateway/modules/clients/codex_0149.py` | `9f773ea74f9aeb7e6ed651f34fc85466fbbd7a4d` | MATCH |
| `app/slaif_gateway/modules/contracts.py` | `b24a19901445483d18c6799b55e89fb73d1fa73f` | MATCH |
| `app/slaif_gateway/services/codex_replay_service.py` | `c0813d120c67474785bb1ddad971dd2cd4dcdec6` | MATCH |
| `app/slaif_gateway/services/responses_gateway.py` | `c280af6354904ebcb831f75023373b1fecfdb700` | MATCH |
| `app/slaif_gateway/services/responses_request_policy.py` | `e2197a3184ee028f95e0a72dbe8857954cad45bd` | MATCH |

The resulting `app/` tree is
`bd536a282362cc549cc0c5518db8e743af667b63`, and the mechanical diff from
`acea2af4ca0f4586fc159c91607e1848f53f1107` over `app/` is empty.

## Permanent tests and fixtures

The five reconstructed permanent test blobs match the order exactly:

| File | Required blob | Result |
| --- | --- | --- |
| `tests/integration/test_codex_replay_references_postgres.py` | `7810a949e00b7c89c290ba79ac246fa145d5c651` | MATCH |
| `tests/unit/test_codex_client_modules.py` | `ba14d1e8a9953cdc885918c1fa867cf23deba630` | MATCH |
| `tests/unit/test_codex_replay_service.py` | `29a9b11195670f933d83ffef4f23673e92801893` | MATCH |
| `tests/unit/test_responses_codex_multiturn_replay.py` | `f91038cf946aeb097b6de91886bcd21490115e47` | MATCH |
| `tests/unit/test_responses_codex_streaming_tools.py` | `f872fa53820687a3a6612c8131d4fddb73521757` | MATCH |

`tests/e2e/test_openai_python_client_responses.py` remains the accepted blob
`aa95589294f48f883b1c174a5a3a43428d9c44f0`.

The five required fixture results were also exact matches:

- reasoning dialect: `5b90402eb3fd1a968fd5ab54774bcaf0575f3c9c`
- session relationship: `a0073a638b82750b3752ac5b78f5df91f97d7d56`
- structural v2: `c182dd195312368d58c80f25c915e83e8474a470`
- Local tool filter: `cdd33cb5c52377f80282803f53005074df091fc8`
- signed identity v1: `e1e4c43e10318ff3170859876dc4d8f6f7d5bdb9`

## Implementation and verification evidence

The implementation restores optional function/custom tool item IDs only for
the exact Codex 0.149 Local pair, preserves mandatory call-ID HMAC ownership,
keeps no-downgrade behavior, and adds the permanent replay/request coverage.
The documentation updates describe the same-key/route/provider/model binding,
rotation, accounting, privacy, and default-deny boundaries.

Focused unit files passed: 236 tests across the five reconstructed unit files
and the compact-verifier unit file. The PostgreSQL replay-reference integration
test passed against a disposable database with no skip. The full
`tests/e2e/test_openai_python_client_responses.py` passed with 23 tests against
a disposable database. Ruff, compilation, and `git diff --check` passed.

The compact verifier is:

- `scripts/verify_codex_0149_local_roundtrip.py`
- `tests/unit/test_codex_0149_local_roundtrip.py`

Its emitted result was exactly:

```text
VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_FAILED code=gateway_pre_local_rejected
```

The failure means the real task-local Codex process issued a bounded request
that the unchanged production Gateway rejected before Fake Local admission.
The verifier retained no request/response bodies, prompts, IDs, call IDs,
arguments, credentials, endpoints, or arbitrary exception text. Because the
required two-turn fake did not pass, this report does not claim two-turn
success, finalized two-turn accounting, or acceptance of the compact fake
roundtrip.

## Obligation and absence checks

The permanent verifier manifest has no missing entries and covers the exact
blobs, replay/no-downgrade/rotation, identity, stream, accounting, privacy,
fake two-turn, and historical-machinery absence obligations. The historical
Objective-155 full-stack verifier and its verifier-only unit file are absent.
No schema or migration was changed. Local Coding, Qwen, protected credentials,
and protected/provider endpoints were not modified or contacted.

## CI checks on implementation head

All ten required checks passed on `G_clean` before report publication:

- Analyze (javascript-typescript): PASS
- Analyze (python): PASS
- Analyze Python: PASS
- CodeQL: PASS
- Docker Compose smoke: PASS
- Documentation hygiene: PASS
- OpenAI-compatible E2E tests: PASS
- Playwright browser smoke: PASS
- PostgreSQL integration tests: PASS
- Unit, lint, and migration head: PASS

## Cleanup and limitations

The task-owned verifier root `/tmp/slaif-160a-check.p2SwGr` and the task-owned
package-inspection root `/tmp/slaif-160-source.CmPYIn` were removed with exact
validated non-trash deletion. The temporary PostgreSQL databases created for
the verifier and integration/E2E checks were dropped; the final count of
databases with the `slaif_gateway_160_` prefix was zero. No protected runtime
reference or provider credential was created or read.

The truthful result is failed at the compact fake’s Gateway pre-Local
admission, not a provider or Local/Qwen result. A later continuation would
need to diagnose that local fake request/profile mismatch before any protected
or real-provider qualification. This report makes no release, production,
compatibility, or acceptance claim and does not merge the PR.
