# OAP Work Order — 027-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/027-model-qualification-tool-use`
Base: main @ ccfac0b

## Objective

Record tier-3 (tool-use) qualification: both Nemotron Super and Kimi K3
successfully used Codex CLI tool calls to create a file through SLAIF.

## Evidence

| Model | Exit | Reply | File content |
|---|---|---|---|
| nvidia/nemotron-3-super-120b-a12b:free | 0 | DONE | TOOL_TEST=PASS |
| moonshotai/kimi-k3 | 0 | DONE | TOOL_TEST=PASS |

Sandbox: workspace-write. Both models used exec_command to write the file.

## Scope

Add "Codex CLI model qualification — tier-3 tool-use" section to compatibility matrix.

## Allowed paths

```
docs/compatibility-matrix.md
oap/orders/027-a-model-qualification-tool-use.md
oap/reports/027-a-model-qualification-tool-use.md
oap/active
```

## Verification

`git diff --check`; CI green.
