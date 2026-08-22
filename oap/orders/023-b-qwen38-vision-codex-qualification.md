# OAP Work Order — 023-b

PR mode: CONTINUE_EXISTING_PR
PR: #249
Branch: oap/023-qwen38-vision-codex-qualification
Base: main @ 7cb16960f4413ebfa1e63c8a9c079598963c1526

## Objective and reason

Strip the SLAIF-internal `additional_tools` input item before constructing the
outbound Responses payload for openai_compatible providers. This item is a
gateway envelope extension that is not part of the OpenAI Responses API
schema, and the authorized LAN vLLM target rejects it with 400. Removing it
from the upstream body enables live vision qualification without any wire-API
translation or profile invariant relaxation.

## Root-cause evidence (independently verified 2026-08-22)

- Direct Codex → image-cap proxy(:18021) → vLLM(:18020) /v1/responses with
  one inline image: 200 OK, correct answer.
- SLAIF gateway → vLLM /v1/responses with the same request: 400.
- Captured SLAIF upstream body (23175 bytes) has input[0] with
  type="additional_tools", role="developer", tools=[2 namespaces].
- Replaying the same body without input[0] returns 200 OK with SSE.
- The item is constructed by
  responses_request_policy._validate_codex_additional_tools_item and included
  in canonical_input; normalize_responses_upstream_request copies it verbatim
  into the upstream payload.

## Exact requirements

1. In app/slaif_gateway/services/upstream_request_contracts.py, inside
   normalize_responses_upstream_request, when body["input"] is a list, filter
   out items where item.get("type") == "additional_tools" before the
   tuple(deepcopy(...)) construction. Keep the string-input path unchanged.
   Do not alter any other endpoint normalizer in this round.
2. Do not change responses_request_policy.py validation. The gateway must
   still validate and accept the envelope internally; it just must not
   forward additional_tools upstream.
3. Update or add focused unit tests proving:
   - normalize_responses_upstream_request strips additional_tools from a
     list input.
   - The remaining items are deep-copied unchanged.
   - A string input passes through unchanged.
   - Existing Codex envelope/client-tools tests still pass.
4. Re-run the live vision verifier with the authorized env vars and confirm
   RESULT=OK, REAL_PROVIDER_CALLED=true, LIVE_QUALIFIED=true.

## Non-goals

No wire-API change. No profile invariant change. No new translation layer.
No changes to text profiles, pricing, quota, migrations, or docs.

## Allowed paths

app/slaif_gateway/services/upstream_request_contracts.py
tests/unit/test_upstream_request_contracts.py   # or the existing test file for this module
scripts/verify_qwen38_vision_codex.py           # only if a diagnostic needs removal
oap/active
oap/orders/023-b-qwen38-vision-codex-qualification.md
oap/reports/023-b-qwen38-vision-codex-qualification.md

## Verification commands

PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_upstream_request_contracts.py
PYTHONPATH=.:app .venv/bin/pytest -q \
  tests/unit/test_qwen38_vision_codex_candidate.py \
  tests/unit/test_qwen38_text_codex_candidate.py \
  tests/unit/test_codex_profile_registry.py

SLAIF_QWEN38_VISION_BASE_URL=http://10.8.132.76:18020/v1 \
SLAIF_QWEN38_VISION_API_KEY=673a4621463edb31bfb3893cefd13e2fc84352298cc48951d9c0838481097815 \
PYTHONPATH=.:app .venv/bin/python scripts/verify_qwen38_vision_codex.py

git diff --check; scoped Ruff on changed paths.

## Acceptance

Focused suites pass; live verifier exits 0 with REAL_PROVIDER_CALLED=true and
LIVE_QUALIFIED=true; all final-head PR #249 checks green; threads resolved;
report-only SELF commit pushed; exact OK on response.fifo. Never merge.

## Boundaries

Same LAN target/key as 023-a. Non-production only. No content persistence.
