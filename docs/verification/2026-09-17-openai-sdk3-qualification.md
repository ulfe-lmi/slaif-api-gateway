# 2026-09-17 OpenAI Python SDK 3.9.0 Official-Client Compatibility Qualification

**Objective:** OAP 166-a (`oap/orders/166-a-openai-sdk3-compatibility-qualification.md`).
**Question:** does the current Gateway preserve its declared official OpenAI-client
compatibility contract when exercised through OpenAI Python SDK `3.9.0`?

**Result: OUTCOME=A** — the declared compatibility surface holds under
`openai==3.9.0`. The dev/test pin was deliberately updated from
`openai==2.41.0` to `openai==3.9.0`; the complete 54-test official-client E2E
matrix passes under that pin with harness adaptation only (no gateway change).

## Evidence boundary

- Base `main` SHA: `1fccaa746df6cd44f1ddf8c2ec5cf6ea9f18b1cb` (merge of PR #302 /
  Objective 165; all nine main-branch checks SUCCESS at that commit).
- PR: `oap/166-openai-sdk3-compatibility-qualification` against `main`.
- PR head: the implementation-head commit containing this record — i.e., the
  first parent of the OAP 166-a report-publication (`SELF`) commit on that
  branch. The OAP report for 166-a records the literal implementation-head SHA.
- All local matrix runs used a disposable local PostgreSQL 16 database
  `slaif_gateway_test` (dropped and recreated before each full matrix run;
  owner role `slaif`; never `DATABASE_URL`); upstream providers were mocked
  with respx; no live provider calls; `RUN_UPSTREAM_TESTS` unset.

## Environments

| Environment | Python | openai | httpx | pydantic | notes |
|---|---|---|---|---|---|
| Baseline (repo venv) | 3.12.3 | 2.41.0 | 0.28.1 | 2.13.4 | pre-existing dev environment; also respx 0.23.1, pytest 9.0.3, anyio 4.14.2, jiter 0.15.0 |
| Candidate (isolated venv, single-variable) | 3.12.3 | 3.9.0 | 0.28.1 | 2.13.5 | fresh venv with every transitive dependency constrained to the baseline freeze, then `openai==3.9.0` forced; final verification reinstalled `.[dev]` from the updated pin (no constraint), yielding identical versions |

`pip freeze` lines for the candidate environment after the final pin-driven
install: `openai==3.9.0`, `httpx==0.28.1`, `httpx2==2.13.0`,
`httpcore2==2.13.0`, `truststore==0.10.4`, `jiter==0.17.0`, `respx==0.23.1`,
`pytest==9.0.3`, `pydantic==2.13.5`.

Diff versus the baseline environment (single-variable check): the only
version changes are `openai 2.41.0 -> 3.9.0`, `jiter 0.15.0 -> 0.17.0`, and
the new packages `httpx2==2.13.0`, `httpcore2==2.13.0`, `truststore==0.10.4`
(all required by openai 3.9.0). OpenAI Python SDK 3.x ships its own HTTP
stack (`httpx2`/`httpcore2`) instead of `httpx`.

## Q1 baseline matrix (openai 2.41.0)

Command: `python -m pytest tests/e2e -q` (repo venv, disposable
`TEST_DATABASE_URL`).

Result: **54 passed, 0 failed, 0 skipped** (collected 54). Matches green CI
on the base commit.

## Q3 candidate matrix (openai 3.9.0)

Pre-adaptation result: **11 passed, 43 failed**. All 43 failures shared one
mechanism: `AssertionError: RESPX: some routes were not called!` against the
harness pass-through route `<Route <Host eq '127.0.0.1'>>`, raised at
`respx.mock(__exit__)` — after the request/response cycle had already
completed (the mocked upstream route was called, returned 200, and the SDK
received and parsed the response).

Post-adaptation result: **54 passed, 0 failed, 0 skipped**.

## Root-cause families

### F1 — SDK 3.x transport stack escapes respx observation (43 tests) — class (a)

- **Wire evidence.** A transparent local TCP capture harness (disposable,
  not committed) recorded the exact request the SDK issued to the gateway for
  one representative test per surface under both SDK versions. Comparison of
  the two captures (10 requests each): method, path, and request body were
  byte-identical except per-run random values (multipart boundary, temp
  filename); the case-insensitive header sets were identical, with value
  differences limited to `user-agent` (`OpenAI/Python 2.41.0` ->
  `OpenAI/Python 3.9.0`), `x-stainless-package-version` (`2.41.0` -> `3.9.0`),
  per-run `Host` port, per-run bearer token, and the multipart
  `Content-Type` boundary. No new header, no new field, no changed body
  shape. The gateway accepted every request (HTTP 200) and forwarded to the
  mocked upstream exactly as under 2.41.0.
- **Mechanism.** openai 3.9.0 performs the SDK-to-gateway leg over
  `httpx2`/`httpcore2`, a separate package pair that respx 0.23.1 does not
  intercept (respx patches `httpx` transports). The harness pass-through
  route `router.route(host="127.0.0.1").pass_through()` therefore records no
  calls under 3.9.0, and `respx.mock(assert_all_called=True)` fails at
  context exit purely as mock bookkeeping. Under 2.41.0 the same route is
  observed and the suite passes.
- **Classification: (a) SDK API/harness change.** The breaking change is in
  the test harness's mock-interception layer, not in the gateway's declared
  contract. The 11 tests that passed under 3.9.0 pre-adaptation are exactly
  the negative/error-path tests that already used
  `respx.mock(assert_all_called=False)`; the 43 failures are exactly the 43
  `respx.mock(..., assert_all_called=True)` blocks (verified 1:1 by AST
  audit).
- **Remedy (tests/e2e only).** In all 43 blocks,
  `assert_all_called=True` -> `assert_all_called=False`. The pass-through
  route is retained (still required for `assert_all_mocked=True` under the
  2.41.0 transport), and every test's explicit upstream-route assertions
  (`assert len(upstream_route.calls) == 1` / `len(...) == 0` / indexed
  `calls[0].request` wire assertions) are unchanged and remain the operative
  contract assertions. An AST audit confirmed that every one of the 43 tests
  references `.calls` after its respx block, so no test lost its
  upstream-was-called guarantee. This adaptation keeps the harness valid on
  both the 2.x and 3.x SDK transport stacks.
- **Tests affected:** 43 (audio 3, chat 10, embeddings 1, realtime 1,
  responses 20, streaming 6, OpenRouter chat 1, OpenRouter streaming 1).
- **Gateway fixes:** none. **Product decisions required:** none (zero (d)
  families; no new endpoint/field/header was observed).

No other failure family surfaced: no (b) wire-shape drift (wire proven
identical), no (c) declared-contract violation, no (e) gateway defect.

## 54-row compatibility matrix

| Test | Baseline 2.41.0 | Candidate 3.9.0 (pre-adaptation) | Disposition |
|---|---|---|---|
| `test_openai_python_client_audio_speech_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_audio_transcription_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_audio_translation_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_image_input_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_inline_file_input_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_audio_input_e2e[wav-cHJpdmF0ZSBhdWRpbyBwYXlsb2Fk]` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_audio_input_e2e[mp3-cHJpdmF0ZSBtcDMgYXVkaW8gcGF5bG9hZA==]` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_audio_output_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_env_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_multiple_choices_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_generic_chat_streaming_final_usage_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_streaming_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_streaming_multiple_choices_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_streaming_image_input_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_streaming_file_input_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_streaming_audio_input_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_streaming_tool_calls_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_codex_0149_signed_thread_namespace_e2e` | PASS | PASS | PASS (unchanged) |
| `test_openai_python_client_local_coding_server_module_e2e` | PASS | PASS | PASS (unchanged) |
| `test_openai_python_client_codex_0149_local_coding_streaming_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_codex_0149_zero_argument_function_streaming_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_conversations_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_conversation_update_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_embeddings_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_models_list_empty_for_no_allowed_models` | PASS | PASS | PASS (unchanged) |
| `test_openai_python_client_rejects_multi_choice_chat_without_route_capability_before_upstream` | PASS | PASS | PASS (unchanged) |
| `test_openai_python_client_rejects_hosted_tool_chat_before_upstream` | PASS | PASS | PASS (unchanged) |
| `test_openai_python_client_rejects_unknown_chat_completion_field_before_upstream` | PASS | PASS | PASS (unchanged) |
| `test_chat_completions_rejects_oversized_response_schema_before_upstream` | PASS | PASS | PASS (unchanged) |
| `test_local_coding_malformed_stream_before_output_releases_accounting` | PASS | PASS | PASS (unchanged) |
| `test_local_coding_malformed_stream_after_output_records_interruption` | PASS | PASS | PASS (unchanged) |
| `test_openai_python_client_responses_rejects_store_and_stream_without_upstream` | PASS | PASS | PASS (unchanged) |
| `test_openai_python_client_chat_completions_custom_tool_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_generic_chat_images_and_function_tool_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_openrouter_env_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_chat_completions_openrouter_streaming_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_realtime_client_secret_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_text_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_structured_text_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_function_tool_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_custom_tool_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_image_input_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_file_input_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_generic_responses_conformance_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_streaming_text_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_streaming_input_items_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_generic_responses_stream_and_remote_rejection_e2e` | PASS | PASS | PASS (unchanged) |
| `test_openai_python_client_responses_web_search_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_store_retrieve_delete_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_previous_response_id_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_input_items_list_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_input_items_structured_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_input_token_count_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |
| `test_openai_python_client_responses_compact_e2e` | PASS | FAIL (F1) | PASS after F1 harness adaptation |

Counts: 54 rows = 54 collected tests. Baseline: 54 pass / 0 fail / 0 skip.
Candidate pre-adaptation: 11 pass / 43 fail (all F1). Candidate final:
54 pass / 0 fail / 0 skip. Family F1: 43 tests, 43 harness blocks adapted,
0 gateway fixes, 0 deferred surfaces.

## Outcome

OUTCOME=A

- `pyproject.toml` dev extras pin: exactly `openai==3.9.0` (single line).
- `docs/openai-compatibility.md`: qualified-version statement added.
- Gateway application code: unchanged (`app/` diff empty).

## Local verification (final PR-head code)


- `python -m pytest tests/e2e -q` (candidate venv, pin-driven `.[dev]` install,
  `openai==3.9.0`, disposable `TEST_DATABASE_URL`, fresh DB):
  **54 passed, 0 failed, 0 skipped** (54 collected).
- `python -m pytest tests/e2e -q` (repo venv, `openai==2.41.0`, fresh DB —
  harness compatibility with the old pin): **54 passed, 0 failed, 0 skipped**.
- `python -m pytest tests/unit -q` (repo venv, final PR-head code):
  **4043 passed, 1 failed, 0 skipped** (4044 collected). The single failure
  is the known environment-only
  `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
  (VM codex CLI version versus the fixture pin `codex-cli 0.148.0`); it
  reproduces identically on the base commit
  `1fccaa746df6cd44f1ddf8c2ec5cf6ea9f18b1cb` in a read-only detached worktree
  and is unrelated to this diff.
- `python -m ruff check app tests` (ruff 0.15.16, pin unchanged):
  `All checks passed!`
- `alembic heads`: single head `0024_quota_reservation_accounting_facts`.
- `python scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK`.
- `git diff --check`: clean.

Diff proof: `tests/e2e/` diff removes no `def test_` line and adds no
skip/xfail; the only behavioral change is `assert_all_called=True` ->
`assert_all_called=False` in 43 respx blocks (43 lines changed, 43 lines
added). The `app/` diff is empty. The `pyproject.toml` diff touches exactly
one line (the `openai` pin in `[project.optional-dependencies] dev`).


## Honest limitations

- Mocked-upstream qualification only: providers were respx mocks on a
  disposable PostgreSQL; this is not a real-provider run and proves nothing
  about live OpenAI/OpenRouter wire behavior under SDK 3.9.0.
- Not a release, production certification, security review, compliance
  finding, or SLA approval of any kind.
- The `httpx2`/`httpcore2` transport of SDK 3.x is outside respx's
  interception boundary in this harness; the SDK-to-gateway leg is covered by
  the gateway's own behavior and by the explicit upstream-wire assertions,
  and by the disposable capture harness for this record. A future respx or
  httpx2-aware interception layer could restore direct observation of that
  leg; that is a harness enhancement, not a contract question.
- The known environment-only unit failure
  (`tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`,
  VM codex CLI version versus fixture pin) is unrelated to this change and is
  labeled as such in the OAP report.
