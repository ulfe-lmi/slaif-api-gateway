# Qwen 3.8 27B Codex configuration

One credential-free profile, consisting of two files, for **Codex CLI 0.162.1**:

- [qwen38.config.toml](qwen38.config.toml)
- [qwen38-models.json](qwen38-models.json)

The gateway registers this as `qwen38-27b-codex-0.162-v1`. The existing
`openai-gpt-5.6-sol-codex-0.147-v1` profile remains registered. The older
Qwen 0.148 text and vision definitions remain unregistered candidates.
Registration covers the bounded text/tool protocol; full live qualification,
images, long-context capacity, and compaction are not claimed.

## Download or install

For a ready route, open **Administration → Routes → your Qwen Responses
route**, then choose **Download Codex config** and **Download model catalog**.
The generated configuration includes the deployment's public gateway URL and
its provider section; no base-fragment merge is needed. A route must declare
this exact registered profile and pass provider, capability, limit and pricing
readiness checks before these downloads appear. See the
[operator runbook](../../../docs/runbooks/codex-qwen38.md).

Save both files together in your Codex home (normally `~/.codex`). The catalog
path is relative to that home, as verified with CLI 0.162.1. When using the
repository example instead of downloading, replace `https://gateway.example.org/v1`
with your public HTTPS gateway URL, including its port if needed.

Supply a gateway-issued key at runtime. No embedded bearer token or `auth.json`
edit is needed:

```bash
read -rsp 'Gateway key: ' OPENAI_API_KEY
echo
export OPENAI_API_KEY
codex --profile qwen38
```

Start a new process after configuration edits. Keep these user-level files out
of project configuration; no private trust paths or terminal settings are
included. Provider credentials remain on the gateway.

## Behavior and limits

The profile enables workspace writes with approval on request and defaults to
`xhigh` reasoning. It disables apps, plugins, hosted web search and remote
compaction. Its catalog uses `use_responses_lite=true`, declaring built-in
local tools in an initial `additional_tools` item. Disabling apps does not
remove built-in tools or bypass gateway permissions.

Context is conservatively set to 131,072 tokens, with local compaction at
100,000. These values must fit the actual backend and route limits; a short
smoke test does not prove long-context capacity. This profile is text-only.
No hardware, institution, private host, user path or credential is included.

In a disposable workspace, first request an exact marker without tools. Then
ask it to create a small file using `apply_patch`, read it using `exec_command`,
and return its content. The [verification record](../../../docs/verification/codex-qwen38-live-smoke.md)
records actual gateway tests separately from synthetic tests and qualification.

For an explicitly configured larger backend, use the route's generated downloads
for the separate [240K/256K profiles](../../../docs/runbooks/codex-qwen38.md#explicit-larger-context-profiles).
The repository example above remains the original conservative 131072-token
profile; do not overwrite a downloaded larger-context file with it.
