# OAP 022-b execution report

Implementation head SHA: `165f36dc5b12c5130255c17c1e565953f9628ce0`
Report publication commit: SELF

## Scope and outcome

This continuation amends PR #248 and replaces the 022-a live-verifier stub
with a bounded orchestration path. The path validates the exact private LAN
target, verifies Codex 0.148.0, creates isolated gateway/provider state,
generates private candidate artifacts/catalog files, runs Codex through the
real gateway to a numeric-loopback OpenAI-compatible provider, and checks
provider credential substitution, PostgreSQL accounting, pending
reservations, and durable privacy canaries when its disposable database
dependency is available.

The local environment had no `TEST_DATABASE_URL`, so the actual phase gate
stopped safely before creating a database, Redis process, gateway, or network
target call. Exact invocation result:

```text
RESULT=LIVE_TARGET_ABSENT
LIVE_TARGET_PRESENT=false
REAL_PROVIDER_CALLED=false
HERMETIC_PHASE=blocked
```

The live variables were checked without printing values and remain absent:

- `SLAIF_QWEN38_TEXT_BASE_URL`: absent
- `SLAIF_QWEN38_TEXT_API_KEY`: absent

No LAN call, provider call, production registration, migration, email, or
release action occurred. The candidate remains mocked-conformant/unregistered
and `live_qualification=false`. The actual hermetic phase gate remains the
explicit continuation blocker; this report does not claim that it passed.

## Candidate contract

- Profile: `qwen3.8-27b-text-codex-0.148-v1`
- Codex CLI: `0.148.0`
- Public model: `qwen3.8-27b-text`
- Upstream model: `qwen3.8-27b`
- Provider kind: `openai_compatible`
- Wire API: Responses `/v1/responses` only
- Context: `150000`
- Default/max output: `8192` / `24576`
- Client-local compaction threshold: `125000`
- Input modality: text only
- Gates: request envelope, client tools, streaming tool events
- Excluded: image, search, parallel tools, remote compaction, encrypted
  reasoning replay, hosted/MCP authority, apps/plugins, and freeform patching
- Global registry/CLI/admin/route availability: false
- Live qualification: false

The registry candidate uses a replacement catalog with bounded credential-free
metadata. Its fixture digest is pinned to:

```text
952c6f39532d9b1543cfeb537eabaea4259f6e13b045cf250064897be88342bc
```

The fixture is now a deterministic structural projection with request/tool/
stream/final ordering, catalog, route, and credential-boundary facts. The
Objective-021 sanitizer rejects arbitrary metadata, raw content, URLs, paths,
headers, credentials, prompts, responses, tool arguments/results, and
reasoning. Its integrity and canary tests pass. Because the phase gate was
dependency-blocked, no claim is made that these facts came from a completed
Codex-to-gateway capture in this round.

## Focused verification

Exact commands and results:

```text
.venv/bin/python -m pytest -q tests/unit/test_qwen38_text_codex_candidate.py tests/unit/test_codex_profile_registry.py tests/unit/test_codex_qualification.py
88 collected, 88 passed

.venv/bin/ruff check app/slaif_gateway/services/codex_profile_registry.py scripts/verify_qwen38_text_codex.py tests/unit/test_qwen38_text_codex_candidate.py
All checks passed!

.venv/bin/python -m compileall -q app/slaif_gateway/services/codex_profile_registry.py scripts/verify_qwen38_text_codex.py
git diff --check
passed

PYTHONPATH=app .venv/bin/python scripts/verify_qwen38_text_codex.py
RESULT=LIVE_TARGET_ABSENT
LIVE_TARGET_PRESENT=false
REAL_PROVIDER_CALLED=false
HERMETIC_PHASE=blocked
```

The unit tests include absent/partial/unsafe target boundaries, no-reflection
credential validation, present-target orchestration seam invocation, fixture
sanitization/integrity/canary checks, candidate limits, unregistered state, and
runtime registry restoration. No real PostgreSQL or Redis setup was performed:
the required disposable `TEST_DATABASE_URL` was absent. No broad local suite
was run. GitHub CI supplied routine broad checks.

## GitHub checks and safety

At publication, PR #248 required checks were green: Analyze
(javascript-typescript), Analyze (python), Analyze Python, CodeQL, Docker
Compose smoke, Documentation hygiene, OpenAI-compatible E2E tests, Playwright
browser smoke, PostgreSQL integration tests, and Unit, lint, and migration
head.

The verifier accepts no CLI target/key arguments, rejects control/whitespace,
percent-encoded, backslash, credential-bearing, query, fragment, public, and
invalid-port URLs, and emits fixed status lines without reflecting inputs. No
secrets, prompts, responses, tool data, URLs, paths, or credentials were
printed or committed. PostgreSQL remains authoritative; no accounting claim
is made for the blocked phase. Documentation now labels the candidate
mocked-conformant, unregistered, and live-target-absent.

## PR state

- PR: [#248](https://github.com/ulfe-lmi/slaif-api-gateway/pull/248)
- Branch: `oap/022-qwen38-text-codex-qualification`
- Base: `main`
- No merge performed.
- Auto-merge not enabled.

The publication commit must be the only commit change after the implementation
head and must contain only this report file. The PR remains open for the next
authorized continuation that can supply the safe disposable database phase
dependency and complete the actual hermetic capture.
