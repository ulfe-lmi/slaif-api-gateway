# Static client and server module architecture

> **Status:** Current internal architecture contract
> **Audience:** Maintainers and contributors

SLAIF keeps protocol decoding and upstream translation in statically registered
modules while the Gateway core remains the sole authority for authentication,
effective policy, routing, quota, accounting, Redis controls, pricing, audit,
privacy, and failure behavior.

```text
client → client module → Gateway core → server module → upstream
```

## Unequal trust interfaces

Client modules receive only an endpoint and the validated-at-ingress mapping
needed to normalize an untrusted client dialect. They return fresh canonical
request facts, bounded capability intents, and explicitly untrusted identity
hints. They cannot authenticate, query PostgreSQL, use Redis, select a route or
provider, reserve quota, price, audit, perform HTTP, or grant authority.

Server modules receive only core-resolved provider/route facts and a canonical
provider request after policy and admission. They return the existing safe
provider response, stream, usage, and failure types. They cannot authenticate a
public key, mutate policy, reserve or finalize quota directly, or receive the
public Gateway bearer.

The initial default client module is the immutable `openai-default` module for
ordinary Chat Completions and Responses create traffic. The initial server
registry contains the built-in OpenAI, OpenRouter, generic OpenAI-compatible,
and `facial_scoring` descriptors. Pair metadata is finite compatibility data;
it does not grant an endpoint, model, route, provider, capability, pricing mode,
hosted tool, or key permission.

## Static registration

Module IDs, versions, descriptors, factories, and client/server pairings are
literal source-code allowlists under `app/slaif_gateway/modules/`. Unknown IDs,
duplicate registrations, unsupported endpoints, and absent pairings fail closed
before provider construction and before a new side effect. The architecture
does not use `importlib`, entry points, arbitrary dotted paths, reflection-based
loading, package discovery, admin-supplied classes, a plugin marketplace, or a
third-party module SDK.

The old `slaif_gateway.modules.facial_scoring` import path is a thin
compatibility re-export. Its single implementation is now under
`modules/servers/facial_scoring/`. Provider construction delegates to the
server registry; there is no parallel production factory.

## Change ownership

Client syntax and dialect changes should normally remain client-module changes.
Upstream protocol, header, body, and response translation changes should
normally remain server-module or shared transport changes. Any new authority,
admission, quota, pricing, accounting, audit, retention, or privacy semantics
require Gateway-core review even when a module is involved.

The current facial-scoring module remains the bounded post-MVP,
non-streaming Chat image adapter. Its fixture packaging, hashes, dimensions,
manifest provenance, zero-EUR request pricing, authentication, accounting,
privacy, retry, and error behavior are unchanged.

Codex 0.149 compatibility, Local Coding, and OpenCode modules are planned
follow-on work, not implemented by this architecture objective. Objective 154
owns later Codex client extraction.
