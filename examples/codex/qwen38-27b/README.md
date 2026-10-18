# Qwen 3.8 27B Codex profiles

Credential-free examples for Codex CLI **0.162.1** through an explicitly
configured SLAIF `local-coding-v1` Responses route. These are operator
examples, not registrations in the gateway's qualified-profile registry.

| Profile | Purpose | Local permissions | Reasoning |
| --- | --- | --- | --- |
| `qwen38-minimal` | Basic text smoke test; connectors disabled | Read only | `none` |
| `qwen38-coding` | Coding with built-in function tools and custom `apply_patch` | Workspace write, approval on request | `xhigh` |

Both profiles declare local tools; read-only mode does not remove declarations
or bypass gateway policy. Neither enables apps, plugins, hosted web search, or
remote compaction. The catalog's `use_responses_lite=true` is required by this
gateway client module: Codex puts its tools in an initial `additional_tools`
item, which the gateway validates and translates for the backend.

## Install on the Codex client machine

Copy these three files into your Codex home (normally `~/.codex`):

- [qwen38-minimal.config.toml](qwen38-minimal.config.toml)
- [qwen38-coding.config.toml](qwen38-coding.config.toml)
- [qwen38-models.json](qwen38-models.json)

In both TOML files, replace the gateway URL with your public HTTPS origin plus
`/v1`, including a nondefault port if needed. Replace the catalog placeholder
with the absolute path on the **client** machine. Do not assume TOML expands
`$HOME`. If your public route uses another model alias, change `model` in both
profiles and `slug` in the catalog together.

Supply a **gateway-issued** key at runtime, using the standard environment
variable. Keep provider credentials on the gateway. No `auth.json` edit or
embedded bearer token is needed:

```bash
read -rsp 'Gateway key: ' OPENAI_API_KEY
echo
export OPENAI_API_KEY
codex --profile qwen38-minimal
```

Or start the coding profile from a disposable workspace:

```bash
codex --profile qwen38-coding
```

Start a fresh process after editing a profile or catalog. User-level named
profile files are used here; do not put provider credentials or configuration
in a project `.codex/config.toml`, and do not add legacy `[profiles.*]` tables.

## Gateway prerequisites and limits

Complete the [Qwen deployment and troubleshooting runbook](../../../docs/runbooks/codex-qwen38.md)
first. Selecting a model is not sufficient to grant Codex capabilities.

The example context is an intentionally conservative **131,072 tokens**, with
local compaction at 100,000. These are example client ceilings, not a claim
about the physical model or hardware. Keep them within the backend's verified
capacity and the gateway route's `codex_limits`. For a separately verified
245,760-token deployment, an operator may instead use 245,760 for context and
208,125 for local compaction, updating both TOML files and all three catalog
context/compaction values consistently. Do not infer a larger capacity from a
successful short prompt.

The example is text-only. Add image input only after enabling and verifying
the corresponding gateway route and backend capability. Reasoning levels are
client hints and must match the configured backend. Custom grammar `apply_patch`
requires the new profile engine and an explicitly migrated gateway key.

Examples contain no real keys, people, organizations, deployment host names,
hardware names, local project paths, trust entries, or terminal preferences.

## Smoke tests

With the minimal profile, request an exact short marker without using tools.
With the coding profile, ask it to create a small file using `apply_patch`,
read it with `exec_command`, and report its content. Run that test only in a
disposable workspace. A successful text response does not prove tool-call
streaming, replay, plugins, images, or long-context capacity.

See the [verification record](../../../docs/verification/codex-qwen38-live-smoke.md)
for the exact tests actually executed and their limits.
