# Objective 159-a report — Codex 0.149 visible reasoning dialect

RESULT=PASSED

Repository: `ulfe-lmi/slaif-api-gateway`
Base: `main` at `f1128c2d3cd8f81f2986a1bb5c0f5904c3372c4c`
Branch: `oap/159-codex-0149-visible-reasoning-dialect`
PR: #296
Activation commit: `49dccd7`
Implementation head: `3d782a6`
Report publication commit: SELF
Merge: not performed; auto-merge: disabled.

## Topology and scope

The activation selector is `159-a`, and the activated order is unchanged.
The implementation commit changes only the order-authorized paths:

- `app/slaif_gateway/modules/contracts.py`
- `app/slaif_gateway/modules/clients/codex_0149.py`
- `app/slaif_gateway/services/responses_request_policy.py`
- `scripts/capture_codex_protocol.py`
- `tests/fixtures/codex/0.149.0/responses-reasoning-dialect-v1.json`
- `tests/unit/test_codex_client_modules.py`
- `tests/unit/test_responses_codex_multiturn_replay.py`
- `docs/accounting.md`
- `docs/compatibility-matrix.md`
- `docs/module-architecture.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`

No Gateway stream wiring, Local/Qwen, replay repository/service, schema,
migration, E2E, doctrine, PR #291, or other non-allowed path changed. The
report-only commit has `3d782a6` as its first parent and changes only this
report path.

Exact required implementation/test blobs:

```text
app/slaif_gateway/modules/contracts.py                         3accb526ee519d1b78cf85bc22274e8de155afff
app/slaif_gateway/modules/clients/codex_0149.py                 bee1f18c0e61726b1046fa965e5a3edf42b8a085
scripts/capture_codex_protocol.py                              4aa54548065f457b2afa1cc939c02254cc72ae58
tests/fixtures/codex/0.149.0/responses-reasoning-dialect-v1.json 5b90402eb3fd1a968fd5ab54774bcaf0575f3c9c
tests/unit/test_codex_client_modules.py                        4f0a8ab5bbe9a00521ffa2718c17be8e7e498923
tests/unit/test_responses_codex_multiturn_replay.py            d5395e0f263a35e4d3b8b44a61608a320f53a13b
```

## Source-derived contract

The official `openai/codex` tag `rust-v0.149.0` dereferences to commit
`758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`. Source inspection of the pinned
`models.rs`, `common.rs`, and `client.rs` confirms that `ResponseItem::Reasoning`
has optional `id`, `summary`, optional visible `content`, and nullable
`encrypted_content`; the Responses request carries a vector of response items;
and request preparation only removes unprefixed IDs, never creates a reasoning
ID. `ReasoningItemContent` is limited to the source-defined `reasoning_text`
and `text` string variants. The canonical fixture is source-derived, sorted,
privacy-safe, and pinned to the same tag/commit.

## Implementation and tests

`ResponsesClientPolicySpec` now carries version-owned visible-reasoning facts:
optional nullable ID, exact summary/content fields and types, 64-part and
8,192-byte per-part limits, 65,536 aggregate visible bytes, and explicit denial
of ID-less encrypted reasoning. Only the Codex 0.149 module sets these facts.

The policy distinguishes absent, null, empty, and non-null encrypted content.
Absent/null encrypted content selects the visible path; a non-null value keeps
the existing independent encrypted-replay capability and ID requirements.
Visible IDs are preserved when present, absent/null state is preserved without
fabrication, valid summary/content text is preserved semantically including
newline/tab content, and visible bytes are included in ordinary transient input
estimation. Visible reasoning creates no replay candidate or ownership.

The complete changed unit files passed. Their source-level test inventories are
18 test functions in `test_codex_client_modules.py` and 29 test functions in
`test_responses_codex_multiturn_replay.py`; parameterized cases were executed
by pytest. Coverage includes source/fixture pinning, valid ID/absent ID/null ID,
newline/tab and both content types, envelope gating, default/OpenAI and
Codex-0.147 strict behavior, malformed/extra/unsupported fields and types,
invalid Unicode, mixed encrypted state, per-part/aggregate/summary bounds,
privacy, accounting estimation, and no replay-candidate creation.

Additional affected request-policy, Codex envelope/client-tool, compaction,
streaming, Local-module, and quota regression suites passed. The capture CLI
fixture validator passed for the existing pinned structural fixture, and the
source-derived reasoning fixture passed its canonical/provenance assertions.
No real client, provider, Local Coding, Qwen, protected endpoint, or credential
was contacted.

Observed local checks:

```text
pytest -q tests/unit/test_codex_client_modules.py tests/unit/test_responses_codex_multiturn_replay.py       PASS
pytest -q tests/unit/test_responses_request_policy.py tests/unit/test_responses_codex_envelope.py \
  tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_codex_streaming_tools.py \
  tests/unit/test_local_coding_server_module.py                                                                PASS
python -m ruff check app tests scripts/capture_codex_protocol.py                                               PASS
python -m compileall -q app tests scripts/capture_codex_protocol.py                                            PASS
git diff --check                                                                                               PASS
capture_codex_protocol.py validate-0149 structural fixture                                                    PASS
```

## Mechanical containment audit

The request-policy diff contains only visible reasoning validation, visible
byte-estimation handling, and null encrypted-replay detection. It contains no
new optional tool-call IDs, call-ID fallback, second-turn chronology, replay
lookup/storage, ID-less function/custom admission, or Objective-155 diagnostic
behavior. No product file outside the three allowed production paths changed.

## Final-head checks

The implementation head passed all ten required checks before report
publication, and the report-only head is required to rerun them:

```text
Unit, lint, and migration head   pass
Analyze (javascript-typescript)  pass
Analyze Python                   pass
Analyze (python)                 pass
PostgreSQL integration tests     pass
OpenAI-compatible E2E tests      pass
Playwright browser smoke         pass
Docker Compose smoke             pass
Documentation hygiene            pass
CodeQL                           pass
```

## Cleanup, documentation, and limitations

The task-owned root `/tmp/slaif-159a-check.jN83oX` was removed and verified
absent. No disposable database, credential, protected runtime reference, or
provider artifact was created. Repository status was clean after the
implementation commit.

Documentation records the exact Rust-derived visible-reasoning dialect,
optional-ID/no-fabrication rule, null-encrypted distinction, bounds, strict
default/0.147 behavior, transient retention boundary, and ordinary accounting.
The documentation-impact statement is limited to these five authorized
permanent documents; no root doctrine was altered.

This result is source-derived and pure/mock regression evidence only. It does
not claim ID-less tool-call replay, second-turn request admission, protected
Gateway-to-Local-to-Qwen qualification, deployment, release, or production
readiness.
