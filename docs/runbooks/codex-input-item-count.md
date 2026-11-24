# Codex conversation input-item ceiling

Use this runbook for HTTP 400 `responses_input_item_count_exceeded` with
`param: input` and message `The Responses input item array has too many items.`
The gateway checks the length of the submitted top-level `input` array before
route selection, quota reservation or provider contact. This is independent of
token/context capacity and image/request-body byte limits.

## What counts

Messages, reasoning items, tool calls, tool results and tool-declaration items
each occupy positions in the submitted array. This is not a count of user turns,
images, tools currently declared, or tokens. A tool-heavy history can reach the
item ceiling while remaining below its token and byte limits. Retrying the
same history does not reduce the count.

The setting also bounds the text-focused `/v1/responses/compact` input array.
The error code is additionally used for too many text parts inside a message;
that case has a content-path parameter and a different message, and is governed
by `RESPONSES_MAX_TEXT_CONTENT_PARTS_PER_ITEM`, not this setting.

## Packaged default and deployment override

| Setting | Packaged default | Previous deployment value | Deployment override, 2026-11-24 |
| --- | ---: | ---: | ---: |
| `RESPONSES_MAX_INPUT_ITEMS` | 128 | 1,024 | 65,536 |

Here **64K items means exactly 65,536 items**. This does not change the decimal
64,000-token output budget in the [Qwen tuning guide](../codex-tuning-qwen.md).
The deployment override is an existing positive-integer Settings value; zero
is not an unlimited mode. It applies globally to Responses input validation,
including all permitted models and keys, rather than to one route or cohort.
Packaged defaults remain unchanged.

All other limits remain independent: total/per-item text bytes, text-part
counts, image/file bytes, adapter body bytes, replay ownership, route/key
permissions, token estimates, backend context, output allowances, rate limits
and quotas. Accepting 65,536 items at this guard does not promise every such
request fits the other limits or the selected backend.

## Configure and roll the HTTP API

Preserve the deployment's existing image, secrets, environment and mounts.
Set the override on every service hosting gateway HTTP API processes:

```yaml
services:
  api:
    environment:
      RESPONSES_MAX_INPUT_ITEMS: "65536"
```

Merge this overlay with the normal deployment configuration. This is an API
process environment setting, not PostgreSQL route metadata, a client model
catalog field or a compatibility-preset value. A new CLI process seeing the
value does not prove an already-running API worker loaded it.

Recreate all HTTP API workers with the updated environment. For active traffic:

1. Preserve the current effective Compose configuration and proxy configuration
   privately, plus safe key/route configuration fingerprints for comparison.
2. Start a temporary API instance using the same reviewed image, secrets,
   network and mounts, changing only `RESPONSES_MAX_INPUT_ITEMS` and the
   temporary instance's private bind port/name.
3. Verify readiness, the runtime setting and count-boundary behavior on that
   instance before routing public requests to it.
4. Reload the reverse proxy to send new requests to the temporary instance.
   Let existing connections finish on the old API; do not kill active streams.
5. Recreate the canonical API service with the new environment and verify it.
   Restore canonical proxy routing, drain the temporary instance, then remove it.
6. Compare configuration and health after rollout. Only the intended API
   environment value should persist as a deployment change.

No source-code edit, image rebuild, schema migration, backend restart, key
rotation, key-pin migration or route-capability change is required. A dedicated
Celery worker is not an HTTP API worker and does not need recreation for this
ingress-only change. Existing in-flight requests keep their original process
settings. Newly submitted requests use the new limit after the proxy cutover.

## Verify without backend inference

Run the following inside the complete environment of each new API instance:

```python
from slaif_gateway.config import get_settings

assert get_settings().RESPONSES_MAX_INPUT_ITEMS == 65536
```

Also exercise the installed policy validator with small synthetic messages:
65,536 one-character user messages should pass the array-count check and
65,537 should produce `responses_input_item_count_exceeded`. Repeat for
ordinary create and compact input validation. These policy-only checks make
no HTTP calls and verify this guard only, not backend inference or complete
Codex compatibility. Do not retain user history or log synthetic payloads.

For an ingress check, explicitly use the gateway's URL and a model slug known
to be unavailable to the diagnostic key. Send 65,536 small message items and
expect `model_not_allowed_for_key` or `model_not_found`: this shows count
validation passed and model policy stopped forwarding. Send 65,537 and expect
HTTP 400 `responses_input_item_count_exceeded`. Do not rely on a real model
being denied accidentally. Neither request should reserve generation quota
or reach a provider. Verify both the temporary private endpoint and public
endpoint after cutover; record only counts, status and fixed error codes.

Check `/healthz` and the deployment's restricted readiness endpoint. Confirm
the API image, all route settings and all existing key configurations are
unchanged. Tests of a newly instantiated policy/CLI process supplement these
checks; they do not alone establish which workers serve public traffic.

## Retry and rollback

After cutover, retry the existing conversation. This rejection occurs before
provider execution and does not itself require discarding history or rotating
the key. A request above 65,536 items still needs client history reduction or a
separately reviewed larger ceiling; other independent limits can still reject it.

Rollback restores the previous API environment value and repeats the same
rolling replacement. Do not restore an entire old deployment configuration over
unrelated intervening changes. Returning to 1,024 will reject longer histories
again. Keep durable accounting, replay ownership and local conversations intact.

## Diagnostic evidence boundary

The reported 2026-11-24 deployment used engine
`0c0ffec2a8ff70fc3c304471a5427dd2ab8a8058` with a live 1,024-item override.
The installed validator accepted 1,024 synthetic items and rejected 1,025 with
the exact array-count message above. The recent local rejection records did
not retain error codes or item counts, so they do not establish the original
conversation's exact length or conclusively correlate a particular record.
This configuration change does not repair that separate diagnostic omission.
