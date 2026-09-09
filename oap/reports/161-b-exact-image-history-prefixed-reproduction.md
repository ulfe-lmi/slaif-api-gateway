# OAP Coding-Agent Report — 161-b

## Status

RESULT=FAILED

Implementation head SHA: be4e94c57fb7743fb944c9cf8b3a6fc5f48cd14d
Report publication commit: SELF

161-b corrected the repository-owned image fixture and command-shape
verifier, but its one authorized real-Codex reproduction failed before the
first Gateway request. The exact safe failure was retained and no production
assistant-history behavior was changed.

## Topology

- Repository: `ulfe-lmi/slaif-api-gateway`
- Existing PR: #298
- Branch: `oap/161-codex-assistant-output-history`
- Base: `main` at `910ddaa23763883c07f5d2065662eb1157deb9f1`
- 161-a immutable report head: `3f9312a3ef00159574607998711cea6146e7734f`
- 161-a implementation parent: `9e9de4fe3bd1e12747021b4a98ab04aa474ea655`
- 161-b activation head: `f28f05c5998103530c010ff98a3ece55ecec44d6`
- Final non-report implementation head: `be4e94c57fb7743fb944c9cf8b3a6fc5f48cd14d`
- PR remained open and unmerged; no auto-merge was enabled.

The implementation changed only the allowed verifier and unit-test paths. The
161-b order and `oap/active` were committed unchanged in the activation head.
No application, dependency, fixture, Local, Qwen, schema, CI, or
documentation path changed.

## Correction implemented and tested

The verifier replaced the prior one-pixel fixture with two deterministic,
valid RGB PNGs generated without a dependency:

| Fixture | Shape | Bytes | SHA-256 equality class |
| --- | --- | ---: | --- |
| Full scene | 4x2 RGB | 80 | `98219eff9b1ebec112240aef4928d7cf7e50ecb333176d4c8db946769dd564cb` expected |
| Right crop | 2x2 RGB | 76 | `5a989a94885576fef961a926fcfb1430e9030e9d3aabdef408502b2b1f713c10` expected |

PNG chunk CRCs, dimensions, RGB color mode, byte lengths, distinctness, and
mode-0600 fixture files beneath the task root are validated in memory. The
initial command binds the full fixture after `--cd` and before
`--output-last-message`; the resume command uses `exec resume --last` and
binds only the distinct crop fixture. Both commands set request and stream
retries to zero. The private Codex home is required to contain exactly one
eligible session before `--last` resume; no session ID is retained.

Pure coverage passed 10/10 and includes exact command order/binding, missing,
malformed, same-fixture, stale-fixture, multiple-image, misplaced-option,
observer-overflow, and raw-value-retention negatives. The observer compares
actual image data URLs transiently by bounded length and fixed SHA equality
classes, then discards the bytes.

## One authorized reproduction

The mandatory preflight passed:

- verifier unit tests: 10 passed;
- active OAP governance tests: passed;
- Python compilation: passed;
- Ruff check: passed;
- Ruff format check: passed;
- `git diff --check` and allowed-path proof: passed.

Exactly one zero-retry task-local Codex 0.149.0 reproduction was then run.
It failed before the first Gateway request with only this fixed output:

`codex_first_turn_turn_failed_gateway_zero_status_none_error_other_param_other_local_zero`

The bounded facts therefore are:

- Gateway request count: zero;
- Gateway status/error/parameter: none/other/other;
- fake Local signed request count: zero;
- actual full-image wire class: not observed;
- actual crop-image wire class: not observed;
- assistant-history rejection code/parameter: not observed in this run;
- retry count: zero;
- protected, Local PR #7, Qwen, and real-provider traffic: none.

Because the process failed before Gateway admission, the required actual
`200,200,400` progression, prior assistant `output_text` history, and crop
image on the rejected request were not claimed. The verifier stopped at this
first bounded class and did not retry.

## Checks and cleanup

All ten normal required checks were successful on implementation head
`be4e94c`:

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

The failed reproduction's disposable PostgreSQL database, fake Local server,
Codex home, workspace, image files, process, listener, and task root were
removed by bounded cleanup paths. No raw request, prompt, image, assistant
text, data URL, ID, call ID, header, credential, endpoint, database URL, or
arbitrary error was retained or printed.

## Lifecycle labels

PREFX-REPRODUCTION-ACCEPTED = NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO

No production or documentation claim is made. A later continuation must first
diagnose the fixed `codex_first_turn_turn_failed` harness boundary; it must
not retry the consumed reproduction in this round or implement assistant
history acceptance without new evidence.
