# OAP Work Order — 023-a

PR mode: `CREATE_NEW_PR`
Branch: oap/023-qwen38-vision-codex-qualification
Base: main @ 7cb16960f4413ebfa1e63c8a9c079598963c1526

## Objective and reason

Add Qwen3.8-27B vision Codex qualification profile and prove the complete
operator-defined backend boundary for multimodal input through Codex CLI
0.148.0 → SLAIF → LAN vLLM.

## Human-authorized live target (explicit approval received)

The human has authorized this exact debug/development LAN target:

- Primary endpoint: http://10.8.132.76:18020/v1
  Raw access to Qwen3.8 27B vision-enabled on an RTX 3090.
- Secondary endpoint (informational): http://127.0.0.1:18021/v1
  Special proxy forwarding to the same Qwen backend but stripping all images
  except one per request. Not used for primary qualification; may be referenced
  as documentation of the infrastructure topology.
- API key (non-secret, LAN dev credential): 673a4621463edb31bfb3893cefd13e2fc84352298cc48951d9c0838481097815

Environment contract for the live phase:

```
SLAIF_QWEN38_VISION_BASE_URL=http://10.8.132.76:18020/v1
SLAIF_QWEN38_VISION_API_KEY=673a4621463edb31bfb3893cefd13e2fc84352298cc48951d9c0838481097815
```

### Hard constraints on the live phase

- The Qwen3.8 27B vision server runs on a single RTX 3090 with a hard limit
  of ONE image per request. Do NOT send multi-image live requests.
- Do NOT run concurrent or parallel live requests against this endpoint.
  All live verification MUST be strictly sequential.
- Use a single synthetic image per request. Keep image size small (e.g.,
  ≤512x512 PNG) to minimize GPU load.
- If the server is unresponsive or returns rate-limit errors, back off and
  retry once after ≥30 seconds; do not hammer the endpoint.

## Verified continuation state

- main = 7cb16960f4413ebfa1e63c8a9c079598963c1526; no 023 branch or PR exists.
- PR #248 (objective 022) merged; all rounds terminal.
- Registry supports image modality with image-input gate;
  _validate_catalog_artifact() accepts input_modalities arrays including "image".
- Text verifier scripts/verify_qwen38_text_codex.py provides hermetic + live
  pattern with SLAIF_QWEN38_TEXT_{BASE_URL,API_KEY} env contract.
- responses_request_policy already validates inline data URLs and rejects
  remote http(s) image URLs.

## Scope

1. Define QWEN38_VISION_CODEX_CANDIDATE profile in codex_profile_registry.py:
   - public_model="qwen3.8-27b-vision", upstream_model="qwen3.8-27b"
   - cli_version="0.148.0", wire_api="responses", provider_kind="openai_compatible"
   - context_window_tokens=100_000, auto_compaction_token_threshold=75_000
   - max_output_tokens=24_576, default_max_output_tokens=8_192
   - input_modalities=("text","image"), supports_image_input=True
   - local_tools=("function",), streaming_tool_events=True
   - required_route_gates=("codex_request_envelope","codex_client_tools",
     "codex_streaming_tool_events")
   - model_catalog_artifact: deterministic JSON with input_modalities
     ["text","image"]; supports_search_tool=false,
     supports_parallel_tool_calls=false, supports_reasoning_summaries=false,
     supports_image_detail_original=false; no patch authority claim.
   - model_catalog_target="qwen3.8-27b-vision.json"; catalog_source="replacement"
   - fixture_sha256: SHA-256 of sanitized vision fixture artifact
   - evidence_date: date of successful live run (set only after live proof)
   - mocked_qualification=True initially; live_qualification=False initially.
     Set live_qualification=True ONLY after successful live phase proof.

2. Generate sanitized vision fixture at
   tests/fixtures/codex/0.148.0/qwen3.8-27b-vision-api-key-responses.json:
   - Inline data URL images only; deny remote http(s) image URLs.
   - Single image per live request (3090 constraint).
   - Structural projection only via sanitize_codex_fixture(); no prompt/output/
     content persistence. Must pass digest validation.

3. Implement scripts/verify_qwen38_vision_codex.py mirroring 022 pattern:
   - Hermetic phase: private PostgreSQL, mocked backend, synthetic inline-image
     request through full Responses pipeline; verify accounting ledger entries,
     zero pending reservations, privacy (no prompt/image content persisted),
     route gates, envelope normalization, streaming tool events.
   - Live phase (only when both env vars present): strictly sequential,
     single-image synthetic Codex exec → SLAIF → vLLM round-trip; verify
     real_provider_called=true, accounting reconciliation, zero pending holds;
     capture sanitized structural summary.
   - Exit 0 on success; print structured RESULT=key=value lines.
   - Enforce sequential-only live execution in code (no thread pool).

4. Add tests/unit/test_qwen38_vision_codex_candidate.py covering:
   - Profile validates against validate_codex_profile_registry().
   - Catalog artifact passes _validate_catalog_artifact().
   - Remote image URLs rejected by responses_request_policy.
   - Inline data URL single-image accepted through hermetic pipeline.
   - Multi-image live request explicitly rejected or never constructed.
   - Hermetic verifier returns expected structured output.
   - Live verifier safely reports LIVE_TARGET_ABSENT when env missing.
   - Candidate not selectable until live_qualification=True.
   - Text-profile regression still passes.

## Allowed paths

app/slaif_gateway/services/codex_profile_registry.py
scripts/verify_qwen38_vision_codex.py
tests/fixtures/codex/0.148.0/qwen3.8-27b-vision-api-key-responses.json
tests/unit/test_qwen38_vision_codex_candidate.py
oap/active
oap/orders/023-a-qwen38-vision-codex-qualification.md
oap/reports/023-a-qwen38-vision-codex-qualification.md

No docs change unless a new configuration surface is exposed.

## Non-goals

No production runtime behavior change beyond registering the candidate profile
after live proof. No new provider adapter, migration, release, or broad suite.
Do not weaken _validate_catalog_artifact or responses_request_policy.
Do not add profile-specific image-count override beyond the existing global cap.
Do not run concurrent live requests against the 3090.

## Observable acceptance

- Candidate profile validates and renders without error.
- Sanitized fixture passes structural sanitizer with valid SHA-256 digest.
- Remote image URL rejection test passes.
- Inline data URL single-image path proves accounting/privacy invariants.
- Text regression suite unchanged/passing.
- Live marker returned; REAL_PROVIDER_CALLED=true; LIVE_QUALIFIED=true;
  accounting reconciled; zero pending reservations.
- When env absent: LIVE_TARGET_ABSENT reported safely; no network call attempted.

## Verification commands

PYTHONPATH=.:app .venv/bin/pytest -q \
  tests/unit/test_qwen38_vision_codex_candidate.py \
  tests/unit/test_qwen38_text_codex_candidate.py \
  tests/unit/test_codex_profile_registry.py \
  tests/unit/test_codex_qualification.py

SLAIF_QWEN38_VISION_BASE_URL=http://10.8.132.76:18020/v1 \
SLAIF_QWEN38_VISION_API_KEY=673a4621463edb31bfb3893cefd13e2fc84352298cc48951d9c0838481097815 \
PYTHONPATH=.:app .venv/bin/python scripts/verify_qwen38_vision_codex.py

git diff --check

Scoped Ruff if imports changed.

## Negative/security/privacy/accounting evidence

- Prove remote image URL rejected with responses_input_image_url_invalid.
- Prove no prompt/image content persisted in DB after hermetic run.
- Prove accounting ledgers finalized; reservations zero pending.
- Prove provider key never appears in logs/fixtures/responses.
- Prove candidate not selectable until live_qualification=True.
- Prove live phase enforces sequential execution (no concurrency).

## Publication rules

Commit implementation, then publish one immutable report-only commit with
literal implementation head and "Report publication commit: SELF" on PR.
Report all test results, check table, review-thread state, and live/hermetic
outcome. Signal exact response-FIFO OK. Never merge.

## Boundaries

Non-production LAN only. No production credentials. No content persistence.
PostgreSQL remains quota/accounting truth. Local/hosted tools distinct.
Single RTX 3090 capacity limit respected: one image per live request,
strictly sequential.
