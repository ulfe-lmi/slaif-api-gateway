# OAP Work Order — 016-b

## Objective

Amend PR #241 to remove the source-scan evasion, make the web-search accounting
contract match official OpenAI event shapes, accept authoritative zero-call
auto-choice outcomes, and require valid tool pricing before any accounting
evidence is authoritative. Also move the active selector off the immutable
016-a order whose missing literal `PR mode:` marker is the sole current CI
governance failure.

Stop reconnaissance. Open the named service, schema, and two test files and
edit immediately in small focused slices. Do not re-read broad architecture,
provider, migration, or gateway runtime surfaces.

## Verified state

- Base/main remains `181a23be25a9c636127a756c86bd2d9c8477c971`.
- Sole Objective 016 PR: #241,
  `oap/016-selected-hosted-tools-provider-contracts`.
- Current implementation head:
  `9ade567c208cdf49ab785a8b09d11a710f52beda`.
- Current report head:
  `6a83323a18f0814a71244e0772b72f9cd096adf8`.
- Report topology is valid and 016-a remains immutable.
- Current CI has one governance failure because 016-a says
  `Mode: CREATE_NEW_PR` rather than the exact repository-tested
  `PR mode: CREATE_NEW_PR`. Do not edit 016-a or weaken that invariant; once
  `oap/active=016-b`, the initial-round-only assertion no longer applies.
- The implementation otherwise stays contract-only; no runtime/provider call
  is enabled.

## Required repairs

1. Replace the split-string `import_module` policy import with ordinary explicit
   imports. Update the existing documentation-contract drift test so the new
   pure web-search contract is an intentional allowed consumer of
   `external_tool_policy_contract`; do not evade or delete the source scan and
   do not allow gateway/request/provider runtime consumers.
2. Match pinned OpenAI 2.41 official stream shapes:
   `response.web_search_call.in_progress`, `.searching`, and `.completed`
   require bounded `item_id`, `output_index`, and `sequence_number`;
   `response.output_item.done` takes its index/sequence from the event and its
   web-search ID/status/action from `item`. Merge both completion forms without
   conflict or double count when IDs and indexes agree. Missing, wrong-type,
   negative, excessive, conflicting, or non-monotonic facts remain
   non-authoritative.
3. Because tool choice is absent/`auto`, a completed non-stream response or
   completed stream with zero web-search calls is authoritative zero-call
   evidence, not a missing-terminal hold. A started/searching/failed/incomplete
   call remains non-authoritative.
4. No result may be authoritative without exact valid
   `ExternalToolPricing`. Missing pricing returns a safe hold-required reason;
   negative, non-finite, wrong-source, or invalid-currency directly constructed
   pricing is rejected by schema/helper validation. Valid zero-call evidence
   has exact zero fee.
5. Keep safe evidence content-free. Add private-canary official-shape fixtures
   proving queries, URLs, sources, patterns, response text, IDs, and tokens do
   not enter result/repr/errors/log capture. Keep the hosted fragment separate
   from existing validated client-tool declarations so content-bearing client
   schemas are neither retained nor silently represented as part of safe
   evidence.

## Allowed paths

```text
app/slaif_gateway/schemas/openai_web_search.py
app/slaif_gateway/schemas/pricing.py
app/slaif_gateway/services/openai_web_search_contract.py
tests/unit/test_openai_web_search_contract.py
tests/unit/test_pricing.py
tests/unit/test_documentation_contract_drift.py
oap/active
oap/orders/016-b-close-official-event-pricing-and-governance-gaps.md
```

Final report-only commit may add exactly:

```text
oap/reports/016-b-close-official-event-pricing-and-governance-gaps.md
```

No docs rewrite is needed unless a focused test proves current 016 wording
false. No runtime, adapter, request-policy, database, migration, Redis,
admin/CLI/browser, provider, or deployment edit is authorized.

## Acceptance and verification

- Direct imports are readable and the narrowly updated governance test still
  forbids every unapproved runtime consumer.
- Official required event fields are enforced and the event/item completion
  pair deduplicates exactly once.
- Completed zero-call non-stream and stream fixtures are authoritative with
  zero fee; incomplete/failed evidence requires a hold.
- Missing/invalid pricing can never yield authoritative evidence.
- No canary content appears in safe output, repr, exception, or captured logs.
- Existing request/cap/policy/pricing negatives remain green.

Run only:

```text
.venv/bin/python -m pytest \
  tests/unit/test_openai_web_search_contract.py \
  tests/unit/test_pricing.py \
  tests/unit/test_documentation_contract_drift.py::test_external_tool_contract_is_wired_only_to_policy_surfaces_not_runtime_or_migrations \
  tests/unit/test_external_tool_policy_contract.py -q -ra
.venv/bin/python -m compileall -q \
  app/slaif_gateway/schemas/openai_web_search.py \
  app/slaif_gateway/schemas/pricing.py \
  app/slaif_gateway/services/openai_web_search_contract.py
```

Run scoped Ruff when available, `git diff --check`, exact path-scope checks,
and final GitHub CI. No broad local suite or real provider.

## PR/report protocol

Use existing PR #241 and branch; create no PR. Commit this order and exact
`oap/active=016-b` unchanged with the repair. Publish one immutable
`oap/reports/016-b-close-official-event-pricing-and-governance-gaps.md` with
literal implementation SHA and `Report publication commit: SELF`. The
report-only commit must parent the implementation head and change only the
report. Verify remote head/check truth, signal exact `OK` on `response.fifo`,
and never merge or enable auto-merge.
