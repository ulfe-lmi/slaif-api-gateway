# Codex client-tool history portability — 2026-11-19

## Behavior and scope

Based on main `0940d8a28f3a413d2a2cc6f4962c0efcafd71e13`, the change makes
verified same-key function/custom-tool history portable across providers,
routes and models. The common replay check covers generation, input-token
counting and supported compact paths. Opaque reasoning/compaction remains
source-bound under the existing explicit compact-route exceptions.

Ownership lookup, expiry, item/call kind, tool identity, qualified ID-less
rules, client/server pairing, destination key/capability policy and accounting
are retained. Source provenance in existing reference rows is unchanged.
There is no schema, key-pin or compatibility-profile migration. The operator
procedure and restrictions are in [model switching](../codex-model-switching.md).

## Initial local verification

| Check | Result |
| --- | --- |
| `python -m pytest -n 8 tests/unit` | 8,316 passed, 1 skipped; 204.14 seconds pytest wall time |
| Focused PostgreSQL suites listed below | 46 passed, 0 skipped; 11.287 seconds JUnit suite time |
| `python -m pytest tests/e2e/test_codex_0162_local_tools.py` | 6 passed, 0 skipped; 16.930 seconds JUnit suite time |
| `python -m ruff check app tests` | Passed |
| `git diff --check` | Passed |
| `python -m alembic heads` | Existing single head `0028_demo_web_control` |

The unit skip is the existing optional Codex-0.148 CLI plumbing test: that CLI
version was unavailable. No real Codex client or model inference was run.
Existing pytest-asyncio, Alembic and SQLAlchemy deprecation warnings remain.

The focused PostgreSQL command ran:

```bash
python -m pytest \
  tests/integration/test_codex_tool_history_postgres.py \
  tests/integration/test_visible_reasoning_replay_postgres.py \
  tests/integration/test_codex_replay_references_postgres.py \
  tests/integration/test_codex_replay_delivery_postgres.py \
  tests/integration/test_codex_context_accounting_postgres.py
```

Integration tests used an isolated, labelled, loopback-bound, tmpfs PostgreSQL
16 container and a generated test-only URL. E2E used its existing separately
owned PostgreSQL fixture. No production database, real provider credentials,
inference or email was used. Provider HTTP was mocked. Browser and unrelated
integration/E2E suites were not rerun locally for this change.

## Regression evidence

Service tests persist references from two sources, then authorize the mixed
history on those routes, a third provider/model, and back on the original.
Both function/custom kinds and qualified ID-less forms are covered, with stored
provenance unchanged. Mixed tool plus opaque reasoning/compaction still rejects
provider, route or model mismatches.

Real-PostgreSQL gateway workflow tests replay source-owned history through
local-preserve, native-vLLM and configured upstream transports, including the
preserve-order profile and retained-summary/late-instruction shape. Actual
destination pricing, quota settlement and wire call/result linkage are checked.
Destination model/provider restrictions use the real resolver; missing key or
route capabilities remain negative cases. Cross-key, unknown, expired and
changed-tool ownership negatives remain enforced.

The official OpenAI SDK E2E test starts a real gateway and uses its auth,
route resolution, signed transport, streaming validation, PostgreSQL replay
persistence and accounting. After a streamed tool call on A, the same key
replays it on a different provider/route/upstream model B, then returns to A
with B's visible assistant reply in history. All three requests settle once.
The same-route case and existing profile/capability negatives also pass.

For the baseline proof, the exact `verify_route_compatibility` method from the
main commit above was loaded into a separate test process, without editing
checkout or production files. The new switch E2E case failed at B with
`responses_codex_replay_route_mismatch`, as expected. With the candidate method,
the full six-case E2E file passed. This isolates the route-binding regression;
it is not a live-provider or full Codex qualification claim.

## CI follow-up

CI on the initial PR head found that this verification page, added after the
local unit run, was not reachable from the documentation navigation. That
failed both documentation hygiene and its unit assertion. The model-switching
guide now links this record, and the actual documentation checker and its
13 unit cases pass.

The full integration run also exposed a separate installed-CLI test defect:
a randomly generated public key ID began with `-` and was passed as an option.
The driver now puts `--json` before `--` and the identifier after it, and the
fixture includes a deterministic leading-dash public ID. This changes only the
test invocation and synthetic seed shape, not production key generation or CLI
parsing. The standard option-separator usage is documented in the
[CLI reference](../cli-reference.md).
The focused installed-wheel lookup/paging test passed against its owned
PostgreSQL fixture, including that forced leading-dash ID (67.1 seconds).
