# OAP Work Order — 016-c

## Objective

Amend PR #241 to make OpenAI-only provider identity and official completed-
response shape mandatory before web-search accounting evidence can be
authoritative, and to remove the remaining ambiguous non-stream item/action
defaults. This is the final narrow contract review closure; no runtime scope.

Start immediately in `openai_web_search_contract.py` and its focused test.
Do not repeat repository or architecture reconnaissance.

## Verified state

- Sole Objective 016 PR: #241 on
  `oap/016-selected-hosted-tools-provider-contracts`.
- 016-b implementation:
  `a727549efcd2eea212deb6440c07d7fa4fe66602`.
- 016-b report head:
  `182601bdcb401f06f5400454d9fc7cb1dcfee222`.
- Report topology is valid; 016-a/b artifacts are immutable.
- Direct policy imports, official web-search lifecycle event fields,
  deduplication, zero-call arithmetic, and pricing requirements are repaired.
- Final report-head CI was still running when strategic review found the
  remaining issues below; do not wait on that obsolete head before editing.

## Required repairs

1. `validate_web_search_request`, non-stream parsing, and stream parsing are
   OpenAI-only. Any provider other than exact `openai` must fail with a fixed
   safe reason/exception. Never copy an arbitrary provider argument into
   `WebSearchAccountingEvidence`, repr, logs, or errors; a private-canary
   provider string must be absent from all observable safe surfaces.
2. A streaming `response.completed` terminal is official/authoritative only
   when it contains a bounded response mapping with `status="completed"` and
   a mapping-valued `usage` object. Bare, missing, failed, incomplete,
   wrong-type, or conflicting terminal response facts require a hold. Do not
   retain or expose the response body or usage object.
3. For non-stream output, use deterministic list position as the internal
   output index rather than silently assigning every item index zero. A
   repeated call ID at a different position is conflicting evidence. Indexes
   remain in-memory validation only and never enter safe evidence.
4. Validate official action structures without retaining content:
   - `search`: optional string `query`, list-of-string `queries`, and list of
     `{type:"url", url:string}` sources;
   - `open_page`: optional string URL;
   - `find_in_page`: required string URL and pattern.
   Reject wrong types, unknown action keys/types, excessive bounded counts, or
   excessive string sizes with a fixed content-free reason. Private queries,
   URLs, patterns, sources, response text, IDs, and provider canaries must be
   absent from result/repr/exception/captured logs.
5. Preserve authoritative zero-call behavior only for a complete official
   non-stream response or complete official stream with exact valid pricing
   and neutral tool choice.

## Allowed paths

```text
app/slaif_gateway/services/openai_web_search_contract.py
tests/unit/test_openai_web_search_contract.py
oap/active
oap/orders/016-c-close-provider-and-terminal-shape-gaps.md
```

Final report-only commit may add:

```text
oap/reports/016-c-close-provider-and-terminal-shape-gaps.md
```

No schema/pricing/doc/runtime/provider/database/migration/Redis/admin/CLI/
browser/deployment edit is authorized.

## Acceptance and verification

- Arbitrary provider values fail safely without reflection; only `openai`
  appears in authoritative evidence.
- Official `response.completed` response/status/usage facts are required.
- Non-stream repeated IDs at distinct indexes conflict.
- Official action variants accept bounded correct shapes and reject malformed
  or excessive content without retention.
- Existing request, policy, pricing, lifecycle, zero-call, and privacy tests
  remain green.

Run only:

```text
.venv/bin/python -m pytest \
  tests/unit/test_openai_web_search_contract.py \
  tests/unit/test_pricing.py \
  tests/unit/test_documentation_contract_drift.py::test_external_tool_contract_is_wired_only_to_policy_surfaces_not_runtime_or_migrations \
  tests/unit/test_external_tool_policy_contract.py -q -ra
.venv/bin/python -m compileall -q \
  app/slaif_gateway/services/openai_web_search_contract.py
```

Run scoped Ruff when available, `git diff --check`, exact path-scope checks,
and final GitHub CI. No broad local suite or external/provider call.

## PR/report protocol

Use existing PR #241 and branch; create no PR. Commit this order and exact
`oap/active=016-c` unchanged. Publish one immutable
`oap/reports/016-c-close-provider-and-terminal-shape-gaps.md` with literal
implementation SHA and `Report publication commit: SELF`; its report-only
commit must parent the implementation head and change only the report. Verify
remote head, signal exact `OK`, and never merge/auto-merge.
