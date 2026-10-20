# Parallel tool replay follow-up — 2026-10-20

The reported HTTP 400 at input[10] is the core adjacent-pair validator, not
throttling or a network disconnect. Two real Qwen A100 requests near 21:12 UTC
completed with finalized usage before the next history request was rejected.
Ordinary logs do not retain the rejected request body, so its exact item order
is not claimed as captured evidence.

A separate natural-client reproduction used the installed exact Codex 0.162.1
binary in exec mode, its shipped revision-10 preset, explicit qwen3.8-27b model
selection, and a synthetic local SSE endpoint. Two harmless printf calls were
returned in one response, naturally executed by Codex, and then replayed as
call-call-result-result. The existing core validator rejected that next request
with responses_codex_tool_roundtrip_invalid. The client sent
parallel_tool_calls=false: current generation preference cannot be used to
invalidate already-present parallel history. No production capture was enabled.

The fixed core validates preceding-call identity and result kind, exactly one
result per call, unique invocation/item IDs, declared taxonomy and independent
capabilities. Pending calls cannot cross new user/system/developer input,
declarations or compaction. Existing input/byte ceilings bound all maps.
Reasoning and assistant commentary retain their positions. Existing HMAC
same-key/route/expiry ownership verification still runs for every replay call.
No history is repaired, reordered, dropped or synthesized. This is a producer/
consumer state-machine correction; it introduces no new preset settings,
operator ceilings, credentials or authorization capabilities.

After restarting the synthetic endpoint with the corrected validator, the exact
same failed Codex conversation resumed, consumed both existing tool outputs and
completed successfully. A later turn also completed. A separate fresh two-call
run completed naturally. The structural receipt, including executable digest,
is tests/fixtures/codex/presets/parallel-tool-replay.json. The receipt stores no
raw invocation/item/session IDs, prompt bodies, arguments, output or secrets.
This is exact exec-mode consumer evidence, not a claim that every interactive
CLI configuration is qualified. Initial interactive fixture attempts encountered
an unrelated mcp__codex_tui declaration; those are excluded from this receipt.

Focused existing/new request-policy checks passed 255 tests. The final new
regression file passed 18 cases, covering natural parallel history, reversed
result order, mixed function/custom output, preserved context, invalid graphs
and independent gates. Relevant disposable PostgreSQL checks passed 37 tests
in 23.23 seconds. The first full unit run had 5,305 passes, one skip and
one documentation failure: the newly linked verification file had not yet been
written when the checker ran. No runtime test failed. A complete stable-tree
rerun and live-deployment results follow after execution.
Only the explicit manual Codex calls use Codex; normal pytest never invokes it.

Documentation impact: the Responses and forwarding contracts now describe
identity-based parallel pairing, and AGENTIC_CLIENT_INTEGRATION.md replaces the
incorrect adjacency requirement while retaining all ownership requirements.
No new compatibility profile, full-release/HPC qualification or merge is claimed.
