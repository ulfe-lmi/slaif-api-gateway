# Static client and server module architecture

> **Status:** Current internal architecture contract
> **Audience:** Maintainers and contributors

SLAIF keeps protocol decoding and upstream translation in statically registered
modules while the Gateway core remains the sole authority for authentication,
effective policy, routing, quota, accounting, Redis controls, pricing, audit,
privacy, and failure behavior.

See [the detailed normative agentic-client integration contract](../AGENTIC_CLIENT_INTEGRATION.md)
for the versioned client/server boundaries and qualification rules.

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
ordinary Chat Completions and Responses create traffic. Versioned Codex client
modules are separate static entries: `codex-0.147-responses-v1` owns the
qualified legacy profile, while `codex-0.149-responses-v1` owns only its
bounded structural request facts and is default-denied except for the one
reviewed `codex-0.149-responses-v1` → `local-coding-v1` pair. Pair metadata is
finite compatibility data; it does not grant an endpoint, model, route,
provider, capability, pricing mode, hosted tool, or key permission.

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

Codex 0.149 client syntax is structurally captured and registered with exactly
one static Local Coding server pair. The pair is non-authorizing: endpoint,
model, route, provider, capability, pricing, quota, accounting, identity, and
tool decisions remain Gateway-core facts. The Local Coding server module is a
Responses-create/Responses-SSE transport only; it uses a separate service
Bearer and, in signed mode, derived opaque HMAC identity fields. Its
process-local TTL/LRU replay boundary requires the reviewed single-worker
deployment contract. The observed `tool_search` and `web_search` declarations
remain bounded adapter-managed candidates and never grant hosted authority.
The exact Codex 0.149 Local pair additionally owns the bounded visible-
reasoning request dialect and the strict reasoning/function/message stream
profile. Visible reasoning may omit or explicitly null its item ID without
fabrication; encrypted reasoning remains independently ID-bound and gated.
ID-less tool replay and second-turn request behavior are not part of this
client-module contract.

Client-module profile facts are limited to the reviewed module ID, version,
and fixture digest. Identity hints from Codex metadata are transient
untrusted input and are never stored, logged, audited, exported, hashed, or
forwarded.
