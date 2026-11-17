# Qwen Codex tuning templates

These Codex **0.167.1** client templates cover the original V100/llama.cpp,
A100/vLLM, and RTX3090/vLLM routes. They select the model explicitly and use
`OPENAI_API_KEY`; no credential belongs in these files.

Read the [Codex tuning guide](../../../docs/codex-tuning-qwen.md) before installing.
It explains context headroom, the 64,000 default/128,000 maximum gateway output
budgets, backend limitations, adapter choices, key gates, and failure handling.
The RTX3090 example has a 100,000-token backend context, so a full 128,000-token
response is impossible there; the maximum is a policy ceiling.

From the repository root:

```bash
export OPENAI_BASE_URL="https://your-gateway.example/v1"
python3 examples/codex/qwen38-tuning/install.py
# Supply your gateway-issued key using your normal secret-management method.
export OPENAI_API_KEY="sk-slaif-..."
codex --profile qwen-v100
# Or: codex --profile qwen-a100
# Or: codex --profile qwen-rtx3090
```

The installer writes an absolute catalog path and refuses to replace existing
files. It does not edit global configuration, contact a model, provision a route
or key, or grant permissions. The six-model [output budget manifest](output-budgets.json)
is an operator change specification, not a complete capabilities import.
Existing route context ceilings and all other route/key policy must be preserved.
Legacy 0.162 qualification fixtures remain frozen in the adjacent examples.
