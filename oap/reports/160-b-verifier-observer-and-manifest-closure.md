# Objective 160-b report — verifier observer and manifest closure

RESULT=FAILED

160-b continued PR #297 only. It corrected the verifier-owned observer method
placement and replaced the label-only obligation check with a deterministic
local evaluator. The one decisive exact-Codex fake two-turn run was then run
once after pure/unit preflight and failed closed at the fixed Gateway
pre-Local boundary. Per the order, it was not retried and no protected,
provider, Qwen, or real Local Coding service was contacted.

## OAP and PR topology

- Repository: `ulfe-lmi/slaif-api-gateway`
- Base: `main` at `07ae3cce21c52654bdec1f50bc7e5da9c59082c6`
- Existing PR: #297, branch `oap/160-idless-tool-replay-clean-stack`, open
- 160-a immutable report/start head: `e6c7ea11318ad870f2c0aa792b8b360b53591cb7`
- 160-b activation commit: `b617675cd7b7edac53951328139d580ef54b7be9`
- 160-b implementation head: `82117d2efbda7f1cb9f02ba49d2c0755fbd0b2d7`
- Report publication commit: SELF
- No merge and no auto-merge

The 160-b activation commit contains only the exact `oap/active` selector and
160-b order. The cumulative implementation change after the 160-b activation
is exactly these two allowed verifier paths:

- `scripts/verify_codex_0149_local_roundtrip.py`
- `tests/unit/test_codex_0149_local_roundtrip.py`

No product, documentation, accepted test blob, fixture, Local, Qwen, schema,
migration, or Objective-155 path changed in 160-b.

## Corrections and evaluator

`_record_request_shape()` is now owned by `_GatewayObservation`, the class
whose ASGI receive wrapper invokes it. `_GatewayExceptionObservation` retains
only bounded exception-class facts and does not parse request projections. A
pure ASGI regression passes a synthetic Responses request through the observer,
records one bounded shape, and verifies the ownership split.

`evaluate_obligations()` now mechanically checks the exact app tree, six
production blobs, five permanent test blobs, five permanent fixture blobs,
required verifier/test paths, historical verifier absence, absence of
`SLAIF_155X_` under `app/`, unchanged governance/integration blobs, and the
four permanent doctrine links. Its observed result was exactly:

```text
missing=[]
```

The evaluator uses local immutable blob/tree facts and does not depend on
GitHub, reports, mutable branch names, protected resources, or external
services.

## Product and exact-blob carry-forward

The product implementation remains the accepted 160-a `G_clean`:

- `G_clean=d625af9eb3df45c163342a05e03cda2d3dd0d7c4`
- app tree: `bd536a282362cc549cc0c5518db8e743af667b63`
- `git diff --exit-code acea2af4ca0f4586fc159c91607e1848f53f1107 <G_clean> -- app/`: empty

All six production blobs, five permanent test blobs, the unchanged Responses
E2E blob, and five permanent fixture blobs were reverified unchanged from the
160-a report. No product behavior was added in 160-b.

## Decisive fake result

Pure verifier tests, Ruff, and compilation passed before the decisive run. The
decisive run used an exact task-local `@openai/codex@0.149.0` installation,
numeric loopback, the real Gateway candidate, a bounded fake Local endpoint,
and a disposable PostgreSQL database. The command emitted exactly:

```text
VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_FAILED code=gateway_pre_local_rejected
```

The verifier observer correction exposed that the real task-local Codex
request was rejected by the Gateway before Fake Local admission. Therefore
160-b does not claim two Gateway/Local turns, ID-less continuation success,
function execution, finalized two-turn accounting, or accepted replay
ownership. No protected/provider inference was attempted, and no second fake
Codex process was run after this decisive failure.

The verifier retains only bounded counters, structural classes, fixed error
codes, and booleans. It does not emit or persist prompts, bodies, IDs, call
IDs, arguments, results, headers, credentials, endpoints, paths, or arbitrary
exception text.

## Verification

- `tests/unit/test_codex_0149_local_roundtrip.py`: 8 passed after correction
- Repository unit/lint/migration CI: PASS
- PostgreSQL integration CI: PASS
- OpenAI-compatible E2E CI: PASS
- Analyze (javascript-typescript): PASS
- Analyze (python): PASS
- Analyze Python: PASS
- CodeQL: PASS
- Docker Compose smoke: PASS
- Documentation hygiene: PASS
- Playwright browser smoke: PASS
- `git diff --check`: PASS
- Allowed verifier Ruff and Python compilation: PASS

All ten required checks were green on the implementation head
`82117d2efbda7f1cb9f02ba49d2c0755fbd0b2d7` before this report-only commit.
The prior 160-a PostgreSQL replay integration, full Responses E2E, exact app
tree, security, identity, stream, accounting, privacy, and historical-
machinery evidence remains unchanged and is carried forward only as such.

## Cleanup and boundaries

The exact task-local check root `/tmp/slaif-160b-check.YU7Dn2` was removed by
validated non-trash deletion and verified absent. The final PostgreSQL query
found zero databases with the `slaif_gateway_160_` prefix. No protected
runtime reference, provider credential, or external service was created or
read. No protected/provider/Qwen/real Local Coding request was made.

The truthful outcome is a verifier/fake integration failure at Gateway
pre-Local admission, not a Local, Qwen, provider, or ownership conclusion.
This report makes no acceptance, release, production, or broad compatibility
claim. Strategic review must decide any later continuation; this PR was not
merged.
