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
ordinary Chat Completions and Responses create traffic. Versioned Codex client
modules are separate static entries: `codex-0.147-responses-v1` owns the
qualified legacy profile, while `codex-0.149-responses-v1` owns only its
bounded structural request facts and is default-denied. The latter has exactly
one reviewed `local-coding-v1` server-module pair. Pair metadata is finite
compatibility data; it does not
grant an endpoint, model, route, provider, capability, pricing mode, hosted
tool, or key permission.

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

Codex 0.149 client syntax is structurally captured and registered, but has no
qualification or provider/model E2E. Its only compatible pair is the static
`codex-0.149-responses-v1` → `local-coding-v1` entry, and that pair still
requires the exact server-side key metadata and route contract. The static
`local-coding-v1` server module is now implemented for an exact
`openai_compatible` route contract with deterministic/mock-conformance only;
its adapter owns only Responses create and Responses streaming and rejects
every other ProviderAdapter operation before HTTP. OpenCode remains planned
follow-on work. The 0.149 module may return only bounded candidate facts for
the exact captured `web_search` and `tool_search` declaration shapes; those
facts reach only the exact Local Coding adapter after core pair/route gates.
They cannot enter hosted-tool policy, hosted accounting, or provider authority.

Local Coding is the only server module permitted to construct the reviewed
private service Bearer and signed-identity-v1 headers. It receives only the
core-resolved provider request and opaque derived identity facts; it cannot
authenticate public keys, select routes, reserve quota, or persist identity.
Its signed mode is explicitly single-worker/process-local replay protection.
The core identity boundary is tested with authenticated owner UUID, transient
session hint, server-side repository scope, exact resolved route contract, and
dedicated derivation secret; this is not a Codex-composed E2E qualification.

Client-module profile facts are limited to the reviewed module ID, version,
and fixture digest. Identity hints from Codex metadata are transient
untrusted input and are never stored, logged, audited, exported, hashed, or
forwarded.
