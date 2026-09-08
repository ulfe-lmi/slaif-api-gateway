# OAP Coding-Agent Report — 161-c

## Status

RESULT=FAILED

Implementation head SHA: 1f74626f1bc9d180aef3fe85d2a67e056efe6fdc
Report publication commit: SELF

161-c added the exact Local-005-q vision catalog facts and binary provenance
gate, but the one authorized reproduction stopped at the binary digest check.
No Gateway, Local, provider, or protected request occurred, and no production
assistant-history behavior was changed.

## Topology

- Repository: `ulfe-lmi/slaif-api-gateway`
- Existing PR: #298
- Branch: `oap/161-codex-assistant-output-history`
- Base: `main` at `910ddaa23763883c07f5d2065662eb1157deb9f1`
- 161-b activation head: `f28f05c5998103530c010ff98a3ece55ecec44d6`
- 161-b immutable report head: `c3201697068780af1c56b63766347cfbe639f6c1`
- 161-c activation head: `1f5ebed154406bfebc5a71d3cbacfd5ae7cf2254`
- Final non-report implementation head: `1f74626f1bc9d180aef3fe85d2a67e056efe6fdc`
- PR remained open and unmerged; no auto-merge was enabled.

Only the allowed verifier and unit-test paths changed after activation. The
161-c order and `oap/active` were preserved unchanged. No app, dependency,
fixture, Local, Qwen, schema, CI, or documentation path changed.

## Catalog correction

The verifier now selects the configured synthetic model by exact slug rather
than list position and applies only the reviewed Local vision facts:

- `input_modalities = ["text", "image"]`;
- `supports_image_detail_original = false`;
- `context_window = 100000`;
- `max_context_window = 100000`;
- `supports_parallel_tool_calls = false`.

It preserves unrelated generated catalog fields, writes canonical JSON mode
0600 under the task root, re-reads and validates the selected facts, and fails
closed for missing/duplicate models, malformed modalities, invalid detail,
context, parallel-tool, canonicalization, size, unrelated-mutation, and raw
value cases.

The source anchor is the immutable Local commit
`64e50172ee02563e2b021554f6b0d345cc7dfdec`, path
`tests/helpers/vision_e2e_support.py`; no Local source was imported or changed
at runtime.

## Preflight and one authorized run

Preflight passed:

- 31 verifier/governance unit tests;
- Python compilation;
- Ruff check and format check;
- `git diff --check` and exact allowed-path proof.

The task-local package version check reached the exact expected
`@openai/codex@0.149.0` CLI version. The previously accepted binary digest
equality check failed closed (`codex_binary_sha_mismatch`). Only the fixed
failure code was emitted; the actual digest and installation path were not
printed or retained in evidence.

Because the provenance gate failed before launch, the following facts are
not claimed for this round:

- Gateway request/status progression;
- full-image or crop-image wire classes;
- assistant `output_text` history;
- Gateway rejection code/parameter;
- fake Local signing/request counts;
- reservations, ledger, replay, or provider calls.

No retry was made. No protected credential, Local PR #7, Qwen, provider, or
production traffic was contacted. Task-owned temporary database, process,
listener, Codex state, catalog, image fixtures, and root were removed by
bounded cleanup paths.

## Final checks

All ten normal checks passed on implementation head `1f74626`:

- Unit, lint, and migration head: SUCCESS;
- PostgreSQL integration tests: SUCCESS;
- OpenAI-compatible E2E tests: SUCCESS;
- Playwright browser smoke: SUCCESS;
- Docker Compose smoke: SUCCESS;
- Documentation hygiene: SUCCESS;
- Analyze Python: SUCCESS;
- Analyze (python): SUCCESS;
- Analyze (javascript-typescript): SUCCESS;
- CodeQL: SUCCESS.

## Lifecycle labels

PREFX-REPRODUCTION-ACCEPTED = NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO

No production or documentation claim is made. A later continuation must
resolve the fixed binary-provenance mismatch before any new reproduction;
this round authorizes no retry and no production correction.
