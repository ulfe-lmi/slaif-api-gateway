# Codex 0.147.0 bounded OpenAI pilot

> **Status:** Separately authorized pilot procedure; historical pinned client/profile
> **Not:** General Codex or real-provider qualification

Status: **PREPARED, NOT EXECUTED**. Objective 011 did not call OpenAI or any
other real provider. `real_provider_e2e=false` remains authoritative.

This runbook is for one later human-authorized, non-production pilot of exactly
Codex CLI 0.147.0, model `gpt-5.6-sol`, and SLAIF's API-key Responses profile
v1. It is not approval for production, a general Codex compatibility claim, or
authorization for a different CLI/model/profile.

## Hard authorization gate

Stop unless all of these are true:

1. A human maintainer has separately and explicitly authorized a real OpenAI
   call for this exact pilot and recorded the approver, UTC time, target,
   maximum provider calls, token ceiling, and EUR ceiling.
2. The human has selected a non-production local or staging SLAIF gateway and
   confirmed its public and upstream targets. Production is prohibited.
3. The installed binary is `/usr/bin/codex`, `codex --version` reports exactly
   `codex-cli 0.147.0`, and the chosen model is exactly `gpt-5.6-sol`.
4. The server-side OpenAI secret is supplied to the gateway only as
   `OPENAI_UPSTREAM_API_KEY` through the target's approved secret-injection
   mechanism. The gateway process has no `OPENAI_API_KEY`; that name belongs
   exclusively to the client gateway key.
5. The operator has a written abort owner and can immediately revoke the pilot
   key and disable the two Codex routes.

Do not continue on implied, historical, or blanket authorization. Never paste
either key into a command, argument, shell history, ticket, log, chat,
screenshot, or evidence file. Do not enable CI or scheduled execution for this
procedure.

## Prepare the exact route and key boundary

On the chosen gateway, require one enabled OpenAI provider and one reciprocal
exact route pair for `/v1/responses` and `/v1/responses/compact`. Both routes
must select `gpt-5.6-sol`, carry the exact qualification declaration, five
Codex gates, strict 1,050,000/32,768/128,000 limits, reciprocal UUIDs, and
complete active pricing for ordinary, cached, cache-write, output, reasoning,
and long-context accounting. The provider base URL must be the human-reviewed
OpenAI endpoint.

Run the credential-free readiness checks:

```bash
slaif-gateway codex inspect
slaif-gateway codex profile --base-url https://NON_PRODUCTION_GATEWAY.example/v1
```

`codex inspect` must report exactly one ready profile. Review the two profile
documents without combining them: merge the provider fragment into a fresh
temporary `$CODEX_HOME/config.toml`, and place the complete named profile in
`$CODEX_HOME/slaif.config.toml`. The files contain no credential.

Create one new standard gateway key through the reviewed admin Codex
protocol-pilot option. Require all of the following before confirming:

- provider `openai` only;
- model `gpt-5.6-sol` only;
- endpoints `/v1/models`, `/v1/responses`, and `/v1/responses/compact` only;
- exactly the five Codex gates and local `function`/`custom` tool types;
- allow-all models/endpoints disabled;
- trusted calibration disabled;
- hosted tools, web/file search, MCP/connectors, provider authorization,
  background execution, provider-managed state, and external network/tool
  authority disabled;
- short validity and deliberately low positive finite limits: at most four
  total requests, an operator-approved token ceiling no greater than 100,000,
  and an operator-approved EUR ceiling no greater than EUR 1.00;
- rate limits and one concurrent request configured explicitly.

Record only the public key ID, internal key UUID, route UUIDs, qualification
result, safe provider name, limits, and timestamps. Do not record plaintext.
Confirm zero outstanding reservations for the new key and calculate the worst-
case provider cost from the active pricing row. Stop if that amount exceeds the
written authorization.

## Preflight the isolated client

Create a disposable empty workspace and private temporary `CODEX_HOME`. Use
dead external proxies with a proxy exception only for the selected
non-production gateway. Do not copy user auth, history, rules, memories,
plugins, MCP configuration, or a repository `.codex` directory into it.

For example, create the two private directories, set both to mode `0700`, and
install the two reviewed credential-free profile documents there before
continuing:

```bash
PILOT_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/slaif-codex-pilot.XXXXXX")"
export PILOT_WORKSPACE="$PILOT_ROOT/workspace"
export CODEX_HOME="$PILOT_ROOT/codex-home"
mkdir -m 0700 "$PILOT_WORKSPACE" "$CODEX_HOME"
```

The two profile files must already have been written by the reviewed
credential-free `slaif-gateway codex profile` workflow before the invocation;
do not paste either key into them. After writing them once, run:

```bash
chmod 0600 "$CODEX_HOME/config.toml" "$CODEX_HOME/slaif.config.toml"
```

Set the dead proxy variables and a `NO_PROXY` exception for only the exact
reviewed non-production gateway host.

Supply the freshly issued gateway key without putting it in shell history or
argv:

```bash
read -rsp 'Paste the one-time SLAIF pilot gateway key: ' OPENAI_API_KEY
printf '\n'
export OPENAI_API_KEY
```

The operator must verify variable presence without printing its value. Never
set `OPENAI_UPSTREAM_API_KEY` in the Codex environment. Query `/v1/models`
through the standard OpenAI-compatible client and require exactly the intended
model to be visible. Recheck the key's unused request/token/EUR counters and
zero outstanding reservations.

## Execute one bounded call

The authorization covers one Codex process and no more than four admitted
provider Responses requests. Use `--profile slaif`, `--ephemeral`, approval
policy `never`, retries disabled, the workspace-write sandbox, and the private
empty workspace. Do not override model or provider on the command line.

Use this fixed harmless prompt only:

```text
In this disposable workspace only, run pwd, create pilot-marker.txt containing
SLAIF_CODEX_BOUNDED_PILOT, read that file, then reply with PILOT_OK. Do not use
network access, Git, package managers, credentials, or any path outside this
workspace.
```

After the private profile, dead proxies, exact gateway-only proxy exception,
and `OPENAI_API_KEY` environment variable are prepared, the complete copyable
Codex invocation is:

```bash
/usr/bin/codex \
  --ask-for-approval never \
  --profile slaif \
  exec \
  --ephemeral \
  --ignore-rules \
  --json \
  --skip-git-repo-check \
  --sandbox workspace-write \
  --cd "$PILOT_WORKSPACE" \
  -c check_for_update_on_startup=false \
  -c 'model_reasoning_effort="low"' \
  -c 'model_verbosity="low"' \
  -c model_providers.slaif.request_max_retries=0 \
  -c model_providers.slaif.stream_max_retries=0 \
  -c model_providers.slaif.stream_idle_timeout_ms=5000 \
  'In this disposable workspace only, run pwd, create pilot-marker.txt containing SLAIF_CODEX_BOUNDED_PILOT, read that file, then reply with PILOT_OK. Do not use network access, Git, package managers, credentials, or any path outside this workspace.'
PILOT_EXIT=$?
```

This command reads the client key only from `OPENAI_API_KEY`; neither client nor
provider secret appears in argv or shell history. It does not enable search,
network tools, hosted tools, MCP, or provider-side authorization. Require
`PILOT_EXIT=0`, `pilot-marker.txt` to contain exactly
`SLAIF_CODEX_BOUNDED_PILOT`, one final structured agent message exactly
`PILOT_OK`, and a completed turn. Observe those facts live without retaining
full Codex output. The gateway's safe counters must still prove that no more
than four provider calls were admitted.

Observe only the process exit status and expected marker/result. Do not capture
raw HTTP, prompts, responses, tool arguments/results, reasoning, ciphertext,
gateway keys, provider keys, or full Codex output. Abort immediately if Codex
requests hosted tools, MCP/connectors, external network authority, an
unexpected path/model/provider, more than the authorized call count, or a
quota/cost above the written ceiling.

## Postflight evidence and mandatory cleanup

Using safe admin/CLI views, verify and record:

- exact CLI/model/profile and non-production target;
- public key ID and route UUIDs, never plaintext key material;
- admitted provider-request count within the ceiling;
- safe provider request IDs, timestamps, status, and endpoint paths;
- finalized request/token/EUR counters matching active pricing;
- cached/cache-write/reasoning component counts when OpenAI returns them;
- finalized quota reservations and zero outstanding reservations;
- HMAC-only replay/reference metadata with no prompt, completion, tool payload,
  reasoning/ciphertext, or raw body persistence;
- server-side auth substitution and absence of client/admin/internal headers at
  the upstream boundary, using safe boolean evidence only.

Regardless of success, revoke the pilot key immediately, unset
`OPENAI_API_KEY`, remove the private `CODEX_HOME` and disposable workspace, and
remove the key from any approved temporary client secret store. Do not remove
the server's OpenAI secret unless the target's secret owner authorizes that
separate operation.

Run the normal stale-reservation inspection. If any reservation is pending,
stop further use and follow
[stale reservation reconciliation](stale-reservation-reconciliation.md). Do
not reset counters or retry the pilot to hide a failure.

## Abort and rollback criteria

Revoke the pilot key and disable both Codex routes if any of these occurs:

- target, CLI, model, profile, provider, endpoint, or qualification drift;
- missing/ambiguous pricing, unexpected cost, quota overrun, or a pending
  reservation;
- client gateway auth reaches OpenAI, the server secret reaches Codex, or a
  sensitive/internal header crosses the boundary;
- raw content/ciphertext persistence, unexpected logs, or non-approved capture;
- hosted/MCP/background/provider-state/external tool behavior;
- provider interruption, accounting/replay persistence failure, or unexpected
  retry/call count.

Preserve safe identifiers and timestamps for diagnosis, leave
`real_provider_e2e=false`, and open a narrow follow-up. Route re-enablement and
a second real call require fresh human authorization.

## Evidence gate for a future status change

A later strategic order may consider `real_provider_e2e=true` only after an
authorized pilot has all postflight evidence above, the key is revoked, the
workspace/profile are removed, reservations are zero, costs reconcile, no
content leaked or persisted, and the human maintainer explicitly accepts the
result. This runbook and the local objective-011 verifier are preparation, not
that acceptance.
