# AGENTIC_CLIENT_INTEGRATION.md

## Versioned agentic-client dialect integration contract for SLAIF API Gateway

> **Status:** Proposed permanent architecture, security, evidence, and onboarding contract  
> **Audience:** Maintainers, strategic OAP models, coding agents, security reviewers, and contributors  
> **Recommended repository placement:** repository root as `AGENTIC_CLIENT_INTEGRATION.md`, with links from `AGENTS.md`, `docs/module-architecture.md`, `docs/responses-compatibility.md`, and `docs/compatibility-matrix.md`  
> **Worked reference case:** Codex CLI 0.149.0 through SLAIF Gateway to `local-coding-v1`  
> **Future candidates:** OpenCode, Antigravity, Claude Code, Gemini CLI, Aider, and other agentic clients, but **no compatibility with any of them is asserted by this document**

---

## 0. Purpose, authority, and evidence baseline

This document defines how SLAIF API Gateway may add support for an agentic client whose traffic is nominally OpenAI-compatible, partially OpenAI-compatible, or translated through an OpenAI-compatible boundary.

Agentic clients are not ordinary SDK callers. They often maintain multi-turn state, select model-specific request envelopes, emit and replay reasoning or compaction records, declare locally executed tools, expose provider-like tool names without requesting provider authority, mutate item identifiers between turns, depend on exact streaming event lifecycles, and derive session identity from metadata that is not obvious from field names. A gateway can pass a simple one-turn text request while still being incompatible, unsafe, incorrectly accounted, or non-replay-safe for the real client.

The contract therefore treats each supported agentic client profile as a **versioned protocol dialect**, not as a brand name and not as a broad relaxation of the OpenAI API.

### 0.1 Normative language

The words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** are normative.

- **MUST / MUST NOT**: mandatory for an integration to be accepted.
- **SHOULD / SHOULD NOT**: expected unless a reviewed, documented exception exists.
- **MAY**: optional and non-authorizing.
- **Observed**: supported by a pinned capture, source inspection, or executed test.
- **Inferred**: a reasoned conclusion that still requires explicit verification.
- **Qualified**: passed the stated bounded tests for one exact profile and topology.
- **Supported**: available under the documented key, route, capability, and pairing gates.
- **Production-ready**: a separate release/deployment judgment; protocol qualification alone never establishes it.

### 0.2 Canonical evidence used to derive this contract

This document is based on the following repository state and immutable evidence:

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- The canonical `main` branch remained at `7ffce834915b74809109e8b579d8541cdcfa9df7` while Objective 155 was developed. That commit merged the versioned client-module foundation from PR #290.
- Objective 155 was technically accepted on PR #291.
- Accepted Objective-155 implementation head:  
  `acea2af4ca0f4586fc159c91607e1848f53f1107`
- Accepted Objective-155 report head:  
  `45eeeb538e95ab3ae1d4d6e78ffb654e0e496fa2`
- Frozen cleaned production candidate from which final verifier-only conformance work proceeded:  
  `e503f9647cb1ef9d2fef5cebe159c84e5a9c1ed4`
- Pinned Local Coding authority used in final qualification:  
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`
- The final accepted run used exact task-local `@openai/codex@0.149.0`, made two Gateway-to-Local requests, made two Local-to-Qwen inference requests, completed one function lifecycle and one assistant-message lifecycle, finalized two accounting rows, and left zero pending state.
- PR #291 remained open and unmerged after technical acceptance. It is an evidence-rich historical branch, not automatically an acceptable merge vehicle.

Some earlier documents on the branch describe Codex 0.149 as unqualified, pairless, or default-denied. Those statements accurately describe the historical point at which they were written. The final Objective-155 acceptance report supersedes only those status statements; it does not erase the historical reports or retroactively rewrite their evidence.

### 0.3 What this document does not authorize

This document does **not**:

- register OpenCode, Antigravity, or any other future client;
- assert that any future client uses the same protocol as Codex;
- grant a client access to a model, provider, endpoint, hosted tool, local tool, network, repository, or secret;
- permit dynamic plugin loading or third-party executable code inside the Gateway;
- permit automatic protocol inference from a `User-Agent`, model name, request shape, or brand;
- permit raw prompt, reasoning, tool, identifier, credential, or stream capture in durable artifacts;
- replace endpoint, route, key, capability, pricing, quota, accounting, audit, privacy, or deployment review;
- make PR #291 merge-ready;
- make a qualified client profile production-certified.

---

# Part I — Core doctrine

## 1. The fifteen non-negotiable rules

Every future agentic-client integration MUST obey all of these rules.

### Rule 1 — Integrate an exact profile, not a product name

Support MUST be keyed to an exact, reproducible client profile. “Codex,” “OpenCode,” or “Antigravity” is not a sufficient compatibility identity.

A profile normally includes:

```text
client product
+ exact distribution/package
+ exact version
+ exact executable provenance
+ exact source tag/commit when available
+ model or bundled model-catalog selection
+ relevant client configuration/profile
+ wire protocol and endpoint
+ enabled feature flags
+ client-side tool mode
+ exact server-module pairing
```

If any component can change the wire contract, it is part of the profile.

### Rule 2 — A client dialect is not the public OpenAI contract

An observed client-specific request MUST NOT be used to relax `openai-default`.

A client-specific difference belongs in a versioned client module or in an explicitly reviewed client/server pair. The generic OpenAI-compatible path remains strict.

### Rule 3 — Client modules classify; they do not authorize

A client module MAY normalize syntax and return bounded facts. It MUST NOT authenticate, route, select providers, access PostgreSQL or Redis, reserve quota, price requests, grant tools, perform HTTP, or persist state.

A client module’s “capability intent” means only:

> “This request structurally appears to ask for capability X.”

It never means:

> “Capability X is authorized.”

### Rule 4 — Server modules translate transport; they do not own policy

A server module MAY implement an exact downstream transport contract. It MUST NOT authenticate the public Gateway key, choose a route, broaden endpoint support, mutate key policy, reserve or finalize quota directly, or receive the caller’s public Gateway bearer.

### Rule 5 — Compatibility pairs are finite and non-authorizing

A client/server pairing MUST be an explicit literal registry entry. The pair proves only that the two dialects are allowed to meet after all other gates pass.

A pair MUST NOT imply:

- endpoint permission;
- model permission;
- provider permission;
- hosted-tool permission;
- local-tool permission;
- state/replay permission;
- pricing or accounting mode;
- quota;
- release readiness.

### Rule 6 — Unknown and unproven shapes fail closed

Unknown top-level fields, item types, tool types, authority-bearing fields, state combinations, stream events, metadata identities, or replay forms MUST fail closed before the first avoidable side effect.

“Looks similar” is not evidence.

### Rule 7 — Absence, null, empty, and non-empty are different protocol states

The integration MUST distinguish:

- field absent;
- field present with `null`;
- empty string;
- empty array/object;
- non-empty value;
- malformed type.

A presence test MUST NOT be substituted for a semantic-value test.

### Rule 8 — Never fabricate state identity

The Gateway MUST NOT invent a provider or client item ID merely because a downstream validator expects one.

Missing identity MAY be accepted only if the exact client dialect permits it and another authenticated ownership anchor exists. Otherwise the request fails closed.

### Rule 9 — Preserve legitimate state; do not “clean it up”

Reasoning, compaction, function-call, custom-tool, message, and output history may carry client state. The Gateway MUST NOT strip, summarize, reorder, canonicalize away, or reinterpret such state unless an exact reviewed transformation is part of the client dialect.

### Rule 10 — Tool declaration is not execution authority

A tool declaration in a client request MUST be classified as one of:

- client-local declaration;
- adapter-managed candidate;
- provider-hosted authority;
- unsupported/unknown authority.

Names such as `web_search`, `tool_search`, `shell`, `mcp`, or `computer` MUST NOT automatically activate provider or Gateway execution.

### Rule 11 — Replay ownership must survive client serialization behavior

If a client legitimately removes one identifier between turns, replay acceptance MUST still be cryptographically bound to same-key, same-kind, same-route/provider/model, unexpired prior output. A fallback MUST NOT become a downgrade path.

### Rule 12 — Streams are state machines, not bags of event names

SSE support requires exact event names, payload shapes, ordering, cardinality, cross-event identity relations, terminal usage, and normal-close semantics.

An allowlist alone is insufficient.

### Rule 13 — Producer and consumer grammars must be tested together

It is not enough for the Gateway to produce a value that passes its own test. Generated headers, identities, route names, request bytes, and signatures MUST be exercised against the actual pinned consumer implementation or an exact source-derived conformance harness.

### Rule 14 — Reports are claims; machine evidence is proof

A report MUST point to executed, collected test nodes and immutable GitHub state. A prose table that names a test is not proof that the required case exists.

Required obligations MUST be represented by a machine-checked manifest whose final state is `missing=[]`.

### Rule 15 — Acceptance ends feature discovery

After a profile passes a hook-free real multi-turn qualification, its behavior is frozen. The next step is decomposition, review, and clean integration—not another compatibility feature on the evidence branch.

---

## 2. Why ordinary “OpenAI-compatible” testing is insufficient

A one-turn request can conceal every difficult property of an agentic client.

A client may:

- send a different second-turn item set than its first-turn request;
- replay provider output as client-managed history;
- omit IDs that a generic SDK type marks required;
- preserve `call_id` while dropping an item `id`;
- send visible reasoning with no item ID;
- include `encrypted_content: null`, which is not equivalent to encrypted replay;
- declare search-like tools that it intends to execute locally;
- change tools or `tool_choice` after a response;
- use a model catalog to select a different internal protocol;
- expose several metadata IDs, only one of which is stable across resume;
- expect a detailed reasoning/function/message SSE lifecycle;
- terminate successfully despite an evidence recorder not knowing all event names;
- account as two independent model requests even though the user perceives one agent turn.

Therefore the minimum meaningful client test is not “text in, text out.” It is:

```text
exact client process
  -> first model request
  -> streamed reasoning/tool lifecycle
  -> client executes or simulates one approved local tool
  -> natural second request with prior state and tool output
  -> final assistant-message lifecycle
  -> terminal accounting for each admitted model request
```

Single-turn support MAY be documented separately, but it MUST NOT be called agentic-client compatibility.

---

# Part II — Architecture and trust boundaries

## 3. Required architecture

The permanent architecture is:

```text
untrusted client
    |
    v
versioned client module
    |
    | CanonicalClientRequest:
    | - fresh canonical body
    | - bounded capability intents
    | - bounded adapter-managed candidates
    | - stream profile
    | - immutable public profile facts
    | - transient untrusted identity hints
    v
Gateway core
    |
    | public authentication
    | endpoint/model/provider policy
    | route resolution
    | exact client/server pair check
    | capability gates
    | request bounds
    | replay ownership
    | rate limit, pricing, quota, accounting
    | privacy and audit
    v
versioned server module / provider adapter
    |
    | exact downstream request bytes
    | server-side credential substitution
    | versioned signed identity where required
    | bounded response/stream translation
    v
downstream service or provider
```

### 3.1 Unequal trust interfaces

The interfaces are deliberately unequal.

| Component | May interpret client syntax | May grant authority | May access durable state | May perform provider HTTP | May own accounting |
|---|---:|---:|---:|---:|---:|
| Client module | yes | no | no | no | no |
| Gateway core | yes, through generic policy | yes | yes | orchestrates | yes |
| Server module | downstream syntax only | no | no direct policy ownership | yes | no |
| Evidence verifier | observes bounded facts | no | disposable test state only | test/protected scope only | verifies only |

This separation is security architecture, not code organization preference.

### 3.2 Static registration

Client and server modules MUST be registered in literal source-controlled registries. Unknown IDs and unsupported pairs fail closed.

The production architecture MUST NOT use:

- dynamic `importlib` loading;
- Python entry points;
- arbitrary dotted class paths;
- admin-uploaded modules;
- package discovery;
- a plugin marketplace;
- runtime-evaluated code;
- client-selected module classes.

A future client module is a reviewed part of the Gateway release.

### 3.3 Server-side selection only

Client-module selection MUST come from complete server-side key/policy metadata, including the expected module ID, module version, and fixture digest.

The client MUST NOT select its own privileged module by sending:

- a header;
- a query parameter;
- `User-Agent`;
- a model name;
- a metadata key;
- a request field that resembles a known dialect.

A mismatch between configured module metadata and compiled module facts fails closed.

### 3.4 No scattered concrete-version conditionals

Client-specific behavior SHOULD be declared in a client policy specification with default-false facts. Core code SHOULD consume those facts.

Avoid:

```python
if codex_version == "0.149.0":
    ...
```

throughout generic policy, routing, and accounting code.

Prefer:

```text
client policy fact:
    reasoning_visible_id_optional = true
    allow_idless_tool_call_replay = true
```

and keep those facts enabled only for the exact reviewed client profile and pair.

Concrete version constants remain appropriate inside the version-owned client module and fixture/provenance checks.

---

## 4. Responsibility allocation

### 4.1 Client-module responsibilities

A client module MAY:

- reject unsupported endpoints for that client profile;
- deep-copy the request into a fresh mapping;
- validate the exact known top-level field vocabulary;
- validate client-specific metadata shape;
- validate exact tool declaration shapes;
- classify adapter-managed candidates;
- emit bounded capability intents;
- select a version-owned stream profile;
- return immutable public profile facts;
- extract transient, untrusted identity hints;
- declare version-owned request-policy differences.

A client module MUST:

- be deterministic for the same request and compiled profile;
- have no network or database side effects;
- retain no request state;
- echo no rejected value in errors;
- keep unknown authority-bearing shapes fail-closed;
- return only facts the core understands.

### 4.2 Gateway-core responsibilities

The core owns:

- public Gateway-key authentication;
- endpoint, model, provider, and route permission;
- client-module selection from server-side policy;
- client/server pairing;
- route capability intersection;
- hosted/external-tool admission;
- local/client tool policy;
- request bounds;
- replay ownership and route compatibility;
- rate limiting;
- pricing;
- PostgreSQL reservation and ledger lifecycle;
- Redis operational controls;
- accounting finalization and reconciliation;
- audit;
- privacy and retention;
- safe public errors.

No module may bypass these.

### 4.3 Server-module responsibilities

A server module MAY:

- enforce an exact route contract;
- support a deliberately narrow operation set;
- reject all other operations before HTTP;
- serialize final downstream bytes deterministically;
- substitute only server-side credentials;
- construct downstream signed identity;
- perform exact HTTP/SSE transport;
- parse bounded usage and provider errors;
- return standard Gateway provider response types.

A server module MUST NOT inherit a broader provider adapter merely for convenience if that inheritance silently exposes unsupported endpoints.

The Local Coding lesson is explicit: a Responses-only service should directly implement the provider interface and reject every non-Responses operation before network activity.

### 4.4 Verifier responsibilities

A verifier is not a production module.

It MAY:

- provision disposable dependencies;
- install exact client binaries;
- run fake loopback services;
- invoke one authorized protected test;
- retain bounded structural facts;
- compare candidate and baseline behavior;
- inspect PostgreSQL terminal state;
- emit a fixed safe result.

It MUST NOT:

- grant product authority;
- alter production semantics to improve evidence;
- retain raw protected data;
- make repeated protected requests until a pass;
- report unexecuted tests as evidence;
- leave production-only diagnostic hooks behind.

---

# Part III — Exact profile identity and provenance

## 5. Compatibility identity

### 5.1 Required profile tuple

A future client dossier MUST define a profile identity equivalent to:

```text
AgenticClientProfile = {
  product_name,
  distribution_name,
  exact_distribution_version,
  executable_version_output,
  distribution_integrity,
  source_tag,
  source_commit,
  model_catalog_identity,
  selected_model_identity,
  client_configuration_profile,
  enabled_feature_flags,
  wire_protocol,
  endpoint_set,
  transport_mode,
  tool_mode,
  state_mode,
  server_module_id,
  fixture_digests
}
```

Not every field must become a database column. Every behavior-affecting field must nevertheless be pinned in source, fixture metadata, or the qualification dossier.

### 5.2 Binary version alone is insufficient

A client binary can change behavior based on:

- bundled model metadata;
- replacement model catalog;
- selected model;
- provider profile;
- wire API selection;
- feature flags;
- compaction mode;
- tool mode;
- approval/sandbox configuration;
- update channel;
- plugin/MCP configuration;
- environment variables.

Two runs of the same executable version with different catalogs or profiles may be different protocol profiles.

### 5.3 Exact executable proof

Before a capture or protected run, the verifier MUST prove:

- requested package/distribution name;
- exact package/distribution version;
- exact executable path under the task-owned root or isolated environment;
- resolved executable target;
- exact `--version` output class;
- the verified executable is the executable actually invoked;
- host-default executable version is recorded only as a class and is not substituted;
- client auto-update and remote profile refresh are disabled or otherwise bounded;
- source tag/commit is pinned when source is available.

The Codex history proved why this matters: the host executable was 0.149.1 while the intended profile was 0.149.0. Until task-local provenance was proven, every observed protocol difference was suspect.

### 5.4 Source authority

When source is available, exact source inspection MUST be tied to the release actually executed.

Do not inspect current `main` and assume it describes an older release.

Source-derived facts should be converted into small structural fixtures or tests. Examples include:

- optional versus required item IDs;
- request preparation that clears non-prefixed IDs;
- mandatory `call_id`;
- exact event types;
- metadata keys;
- model-catalog effects.

When source is not available, the profile MUST be narrower and black-box evidence stronger. Absence of source is not permission to infer unobserved behavior.

### 5.5 Versioning rules

Create a new module ID or version when any of the following changes the accepted wire contract:

- client version;
- source contract;
- fixture digest;
- model catalog or selected model protocol;
- request field vocabulary;
- metadata/session semantics;
- tool declaration taxonomy;
- reasoning/history shape;
- stream lifecycle;
- identifier preservation;
- compaction/state mode;
- required downstream pairing.

A patch release MAY reuse a module only if a source/capture differential proves the relevant protocol profile is unchanged and the fixture identity remains intentionally valid.

A convenient naming pattern is:

```text
<client>-<version-series>-<wire-family>-v<dialect-generation>
```

Examples are illustrative only:

```text
opencode-<exact-version>-responses-v1
antigravity-<exact-version>-responses-v1
```

The names do not create support.

---

# Part IV — Reconnaissance and structural capture

## 6. Decide whether a dedicated client module is necessary

Do not create a module merely because the caller is an agent.

First run the ordinary `openai-default` compatibility matrix.

A dedicated module is warranted only if the exact client requires a bounded difference such as:

- extra request-envelope fields;
- distinct metadata rules;
- non-standard reasoning/history;
- custom tool declarations;
- client-managed replay;
- version-specific stream events;
- different endpoint behavior;
- a server-module-specific transport contract.

If the exact client works through `openai-default` without relaxation, keep it there and document the tested profile.

## 7. Capture environment

A structural capture MUST use:

- a private task-owned temporary root;
- a private client home/config directory;
- an empty or synthetic workspace;
- synthetic credentials;
- a numeric-loopback fake endpoint where possible;
- no production provider key;
- no user auth store;
- no real model call during initial capture;
- updates and remote discovery disabled;
- plugins, MCP, search, and optional tools disabled initially;
- no inherited user history, rules, memory, or config;
- bounded process timeout;
- cleanup verification.

Additional features are enabled one at a time in later capture variants.

### 7.1 Prefer real loopback transport over test-framework illusion

An in-process ASGI test transport can behave differently from real streaming HTTP. Objective 155 encountered a `StreamConsumed` artifact in an ASGI-only attempt and accepted the later real loopback result instead.

Use real loopback TCP for:

- chunking;
- SSE framing;
- disconnect behavior;
- normal close;
- proxy/relay boundaries;
- exact body/header observation.

In-process tests remain useful for pure policy and unit behavior.

## 8. Structural fixture contents

A committed capture fixture SHOULD contain only public provenance and structural facts.

Recommended schema:

```json
{
  "profile": {
    "client_module_id": "...",
    "client_module_version": "...",
    "distribution": "...",
    "distribution_version": "...",
    "source_tag": "...",
    "source_commit": "...",
    "model_catalog_class": "...",
    "wire_api": "responses"
  },
  "request": {
    "top_level_fields": [
      {"name": "input", "type": "array"}
    ],
    "input_items": [
      {
        "type_class": "reasoning",
        "field_types": [
          {"name": "id", "state": "absent"}
        ]
      }
    ],
    "tool_declarations": {
      "counts_by_type": {},
      "shape_fields_by_type": {}
    },
    "metadata": {
      "key_names": [],
      "value_type_classes": {}
    }
  },
  "response": {
    "content_type_class": "sse",
    "event_type_sequence_or_runs": [],
    "event_counts": {},
    "terminal_predicates": {}
  },
  "privacy": {
    "raw_content_retained": false,
    "provider_call_performed": false
  }
}
```

A fixture MUST NOT contain:

- prompts;
- completions;
- reasoning text;
- tool descriptions if they may contain user data;
- tool arguments or results;
- raw item IDs;
- raw call IDs;
- client installation/session IDs;
- credentials;
- authorization headers;
- protected endpoints;
- raw request or response bodies;
- home/workspace paths;
- arbitrary exception text.

Public package hashes, public source commits, and fixture digests are allowed.

## 9. Capture variants

At minimum, capture these variants separately:

1. ordinary single-turn text;
2. streaming text;
3. local function tool;
4. custom/freeform local tool if used;
5. natural two-turn tool continuation;
6. same session resumed;
7. separate session under same installation;
8. same session under another Gateway key where relevant;
9. reasoning/history replay;
10. compaction/history reduction if used;
11. image/file input if in scope;
12. provider error;
13. client disconnect;
14. missing usage or malformed terminal event;
15. plugin/search/MCP declarations, initially expected to fail closed.

Do not combine all feature toggles in the first capture. A combined shape is hard to attribute.

## 10. Session and identity discovery experiment

Never infer session identity from field names.

Run at least:

```text
A1 = new session A, first request
A2 = explicit resume of session A
B1 = separate session B under same installation
C1 = optional same session/profile under another Gateway key
```

For each candidate metadata field, retain only predicates:

- present;
- type class;
- canonical format;
- A1 equals A2;
- A differs from B;
- installation-stable across A/B;
- changes per turn;
- suitable as a namespace;
- rejected as authority.

A field is eligible as a transient session hint only if its stability and isolation match the required semantics.

The Codex 0.149 evidence established that `session_id` and `thread_id` were equal canonical UUID aliases, stable across explicit resume, and different for another session. Installation identity, root-turn, turn, cache, and item IDs were not used as session identity.

### 10.1 Identity hint is not identity authority

Even a correctly identified client session field remains untrusted.

Gateway identity SHOULD bind it beneath server-side facts such as:

- authenticated owner;
- authenticated Gateway key;
- server-side repository scope;
- resolved route;
- dedicated derivation secret.

The raw client identifier MUST NOT become the Local principal or repository identity.

---

# Part V — Request, state, and tool semantics

## 11. Preserve the absent/null/value distinction

Every dialect parser and test fixture MUST model field state explicitly.

Use classes such as:

```text
absent
null
empty_string
nonempty_string
empty_array
nonempty_array
empty_object
nonempty_object
wrong_type
```

Do not write logic equivalent to:

```python
if "encrypted_content" in item:
    encrypted_replay = True
```

when `null` has a different meaning.

Objective 155 found exactly this defect: `encrypted_content: null` was initially misclassified as encrypted-reasoning replay even though the visible-reasoning path legitimately carried a null field.

## 12. Reasoning and history

### 12.1 Do not equate missing ID with empty state

An item may lack an `id` while still carrying non-empty visible reasoning content.

The Gateway MUST inspect the exact dialect contract:

- Is `id` absent, null, or present?
- Is `content` absent, null, empty, or non-empty?
- Is `summary` absent, empty, or non-empty?
- Is `encrypted_content` absent, null, or non-null?
- What key set is allowed?
- What content-part types are allowed?
- What byte and part-count bounds apply?

### 12.2 No fabricated reasoning ID

If the exact dialect permits ID-less visible reasoning:

- preserve the item’s lack of ID;
- preserve allowed content semantically unchanged;
- apply explicit part and byte bounds;
- reject unknown fields/types;
- keep encrypted ID-less variants denied unless separately proven;
- scope the behavior to the exact client profile and pairing.

Never generate a UUID, hash-derived ID, positional ID, or synthetic provider ID.

### 12.3 Do not strip state as a “placeholder”

An apparently empty or metadata-only reasoning item may be semantically significant to the client.

Removal is allowed only when all of these are proven:

- the exact client treats it as semantically empty;
- the exact downstream ignores or rejects it;
- removal preserves subsequent continuation behavior;
- no state or correlation is lost;
- the transformation is version-owned and tested.

Objective 155 rejected the proposed “empty placeholder canonicalization” after the real item proved to have non-empty content.

### 12.4 Visible and encrypted reasoning are separate capabilities

A null encrypted field is not encrypted replay.

Non-null encrypted reasoning SHOULD remain behind an independent, default-off capability and normally requires a valid provider item identity. ID-less encrypted reasoning remains denied unless separately sourced, modeled, and qualified.

Visible reasoning support MUST NOT implicitly grant encrypted reasoning support.

## 13. Provider-managed state versus client-managed replay

The integration MUST distinguish:

- provider-managed state, such as a provider response or conversation identifier;
- client-managed history replay, where prior items are sent again;
- Gateway-owned replay-control metadata.

Client-managed replay SHOULD NOT be combined with provider-managed state in the same request unless an exact contract explicitly defines the interaction. The current Codex path rejects that combination.

## 14. Tool taxonomy and authority

### 14.1 Required tool classes

Every observed tool-like shape MUST be classified:

| Class | Meaning | Default |
|---|---|---|
| Local function/custom tool | Client executes it; model requests it | bounded, explicitly allowed |
| Adapter-managed candidate | Downstream adapter may remove/translate it | non-authorizing |
| Provider-hosted tool | Provider executes it | denied unless independently authorized |
| Gateway-hosted tool | Gateway executes it | denied unless independently implemented |
| MCP/connector/computer/shell authority | External execution/control | denied |
| Unknown | Unreviewed | denied |

### 14.2 Search-shaped declarations

Names such as `web_search` and `tool_search` are ambiguous across clients.

A client may advertise them because:

- the client itself can search;
- an adapter removes unsupported declarations;
- the provider is expected to search;
- a discovery subsystem is present;
- the tool is unavailable but still serialized.

Therefore:

- declaration presence MUST NOT activate hosted search;
- `tool_choice` must be validated after any allowed declaration transformation;
- a choice referencing a removed tool must fail closed;
- adapter-managed candidate fields and values must be bounded;
- URLs, credentials, headers, tokens, MCP/server definitions, or nested authority shapes must be denied.

### 14.3 Tool declarations are model input for accounting

Descriptions, schemas, grammar, and other forwarded declaration bytes contribute to model input and MUST be bounded and estimated.

The Gateway does not charge for client-local tool execution unless a separately implemented service does so. It still accounts for every model request around the tool execution.

## 15. Tool-call and tool-output continuation

### 15.1 Item identity and call identity are different

A function/custom-tool call can have:

- an item `id`;
- a mandatory invocation `call_id`;
- a matching output tied by `call_id`.

The exact client may preserve or remove the item ID before sending the next request.

### 15.2 Natural-client reproduction comes before relaxation

Before accepting an ID-less tool call, run the actual pinned client against a fake provider that returns:

- a valid non-client-prefixed item ID;
- a valid call ID;
- a bounded approved tool call.

Then prove whether the client:

- preserves, rewrites, or removes the item ID;
- preserves the call ID;
- emits the matching adjacent output;
- generates a replacement ID.

Objective 155 proved that exact Codex 0.149 request preparation removed a non-prefixed item ID and generated no replacement.

### 15.3 Secure ID-less replay fallback

An ID-less fallback is allowed only if:

- the exact client policy enables it;
- item kind is function/custom tool call;
- `call_id` is present and valid;
- a same-key, same-kind, active, unexpired HMAC record exists;
- exactly one record matches;
- HMAC key version is available and matches;
- tool namespace/name match;
- route/provider/model compatibility matches;
- the matching output is adjacent and has the same call ID;
- no raw ID or digest is logged or exposed.

### 15.4 No downgrade when an ID is present

If the client supplies an item ID:

- use the item-ID ownership path;
- also require the associated call identity to agree;
- if the supplied item ID is wrong, do not fall back to the call-ID-only path.

This prevents an attacker from presenting a forged item ID together with a known call ID.

### 15.5 Rotation and ambiguity

Replay tests MUST cover:

- old HMAC version while old material remains configured;
- new active HMAC version;
- present-ID and ID-less call paths under both;
- missing old material;
- invalid stored version;
- duplicate/ambiguous cross-version matches;
- cross-key, route, provider, model, and tool mismatch;
- expiry;
- privacy of raw IDs and HMACs.

---

# Part VI — Streaming and terminal semantics

## 16. Event vocabulary is profile-specific

The verifier and production validator need an exact reviewed vocabulary for the active profile.

A Codex-style reasoning/function/message stream may include:

```text
response.created
response.in_progress
response.output_item.added
response.reasoning_part.added
response.reasoning_text.delta
response.reasoning_text.done
response.reasoning_part.done
response.output_item.done
response.function_call_arguments.delta
response.function_call_arguments.done
response.content_part.added
response.output_text.delta
response.output_text.done
response.content_part.done
response.completed
```

This list is illustrative of the accepted Codex 0.149 profile. It MUST NOT be copied into another client profile without evidence.

### 16.1 No wildcard admission

Do not accept:

```text
response.reasoning.*
```

or another prefix family.

Every event name and branch must be explicit.

### 16.2 Event-name recognition is not lifecycle validation

A known event can still be invalid because of:

- wrong order;
- duplicate lifecycle transition;
- missing parent item;
- wrong output/content index;
- mismatched item or response relation;
- delta after done;
- missing done;
- wrong item type;
- invalid status;
- excessive bytes or parts;
- inconsistent final output;
- invalid usage;
- error event;
- abnormal close.

The validator MUST maintain bounded state.

## 17. Terminal completion predicate

A successful streamed model request SHOULD require all applicable facts:

- 2xx status;
- SSE content type;
- exactly one `response.created`;
- exactly one `response.completed`;
- created response status is in progress;
- completed response status is completed;
- consistent response identity relation;
- expected model relation;
- valid terminal output shape;
- valid final usage;
- no duplicate terminal events;
- no unknown event;
- no provider failure/error event;
- no handler error;
- no upstream truncation;
- no downstream early close;
- normal transport close;
- official client observes completion where part of the test.

A stream that transports bytes and closes is not necessarily a valid completion.

## 18. Production validator and evidence recorder

The production validator and external verifier have different roles:

- production decides whether traffic is safe and valid;
- verifier decides whether the test can support a claim.

The verifier MUST cover every event accepted by the exact active production profile. It SHOULD remain independent enough to catch accidental production broadening.

A useful invariant is:

```text
verifier active-profile vocabulary
    == source-reviewed event names reachable in production active-profile branches
```

but verifier lifecycle tests remain separate.

Objective 155 showed both failure modes:

1. a verifier narrower than production classified valid reasoning events as `other`;
2. reports claimed complete verifier coverage even when the actual parameterized test contained only two cases.

Both are prevented by source-derived vocabularies and machine-collected obligation manifests.

## 19. Safe stream evidence

A safe stream recorder MAY retain:

- event names from a closed set;
- ordered run-length counts;
- total counts;
- bounded generated-byte counts by event class;
- boolean lifecycle predicates;
- status/content-type classes;
- ordinal structure presence;
- terminal output class;
- normal-close/error/truncation predicates.

It MUST NOT retain:

- `data:` payloads;
- text deltas;
- reasoning text;
- function arguments;
- tool output;
- item/response/call IDs;
- raw usage objects beyond approved numeric aggregates;
- arbitrary unknown event names.

Unknown names should become `other` plus `unknown_events=true`; they must not be copied verbatim into evidence.

## 20. Evidence must survive failure

Construct and sanitize the boundary snapshot **before** assertions that may terminate the run.

A protected test MUST NOT end with only:

```text
gateway_sse_invalid
```

when the process already holds safe facts about Gateway, Local, Qwen, and accounting.

The exception path must carry the sanitized snapshot out of temporary cleanup. This is verifier-owned behavior; it does not require a production writer.

---

# Part VII — Downstream identity and exact-byte signing

## 21. Separate identity layers

Do not conflate:

1. public Gateway-key authentication;
2. Gateway owner/key policy identity;
3. client session namespace;
4. server-side repository scope;
5. downstream service Bearer;
6. downstream signed principal/session/repository/route;
7. provider model request identity.

Each has a distinct trust source.

## 22. HMAC pseudonymization

When deriving downstream opaque identity:

- use a dedicated derivation secret;
- use domain-separated messages for principal, session, and repository;
- bind session beneath authenticated owner/key plus corroborated client session;
- bind repository beneath server-side repository scope;
- use a deterministic representation;
- preserve full digest entropy;
- validate the downstream consumer grammar;
- describe the result as pseudonymization, not anonymity.

### 22.1 Unconditional encoding prefix

If base64url output may begin with a character disallowed by the consumer, prefix **all** encodings with a fixed version/alphabet-safe character.

Do not conditionally prefix only bad values. Conditional prefixing can collide with naturally prefixed encodings.

Objective 155 found that unprefixed base64url HMAC output could begin with `-` or `_`, while Local required an alphanumeric first character. With three independently derived fields, this created intermittent-looking signed-identity failures. The corrected representation uses an unconditional `h` prefix and the full unpadded digest encoding.

## 23. Producer-side consumer grammar

The Gateway MUST validate every generated field against the exact downstream contract before signing or network activity.

For `local-coding-v1`, the accepted signed-field grammar is:

```text
^[A-Za-z0-9][A-Za-z0-9_-]{0,255}$
```

A route contract may have a broader static-mode grammar. Signed mode must use the signed consumer grammar.

Tests MUST include fixed values that failed before the correction.

## 24. Exact-byte signing

The signed body and transmitted body MUST be the same bytes.

Required pattern:

1. build the final downstream body;
2. deterministically serialize once;
3. hash/sign those exact bytes;
4. send those exact bytes with `content=...`;
5. disable implicit redirects;
6. avoid a second JSON serialization layer.

Canonical signing input SHOULD bind:

- protocol/version domain;
- method;
- path;
- raw query hash;
- exact body hash;
- principal;
- session;
- repository;
- route;
- timestamp;
- nonce.

## 25. Secret-role separation

The following MUST be distinct:

- public Gateway key material;
- downstream service Bearer;
- downstream signing secret;
- identity derivation secret;
- Gateway token-HMAC secret;
- admin/session/one-time secrets;
- upstream provider credentials.

Construction should fail safely if configured roles collide. Errors must never include values.

## 26. Replay mode and deployment claims

If the downstream verifier uses process-local nonce TTL/LRU replay state:

- the qualified deployment is single worker/process;
- restart-persistent replay protection is not claimed;
- multi-worker exclusion is not claimed;
- secret rotation requires coordinated drain/disable/update/restart/re-enable;
- overlapping key acceptance requires a new versioned contract.

A protocol qualification must state these limits.

---

# Part VIII — Accounting, quota, and failure ownership

## 27. One admitted model request, one accounting lifecycle

An agent-visible turn may cause multiple model requests.

For each public request that passes admission:

```text
one reservation
-> one terminal reservation state
-> one terminal ledger outcome
```

Internal Local compiler/governance calls are not separate public Gateway requests unless explicitly modeled as such.

## 28. Pre-admission rejection

A request rejected before reservation MUST NOT be required to create a dummy ledger row.

The correct evidence may be:

```text
one earlier request finalized
second request rejected before admission
zero pending
```

A verifier that blindly expects two ledger rows for two attempted client requests is wrong.

## 29. Streaming finalization

For a successful stream:

- provider final usage is authoritative when available;
- missing usage is not zero-cost success;
- completion may be withheld until accounting finalization succeeds;
- replay references derived from provider output should be persisted only after the corresponding ledger is finalized;
- persistence failure must not leave an apparently normal success if future replay would be unauthenticated;
- zero pending state is mandatory after success or failure.

## 30. Error ownership ladder

Classify failures at the narrowest established boundary:

```text
client launch/provenance
client request construction
Gateway client normalization
Gateway request policy
Gateway pair/route/capability
Gateway replay ownership
Gateway pricing/quota/admission
Gateway server adapter
downstream service authentication
downstream signed identity
downstream JSON/route/media policy
downstream tool policy
downstream constitution/observation
downstream upstream call
Qwen/provider
Local response stream
Gateway production stream validation
official client consumption
verifier expectation
test infrastructure
```

Do not say “Gateway failure” merely because the client-facing stream contains an error emitted by the Gateway. Preserve the originating safe downstream code/stage when possible.

## 31. Layer-specific closed error vocabularies

Gateway and Local errors MUST have separate closed classifiers.

Reusing a Gateway allowlist to classify Local errors can turn a precise Local failure into `other`. `other` means only that the evidence vocabulary did not classify the value; it is not a root-cause diagnosis.

A safe error projection MAY retain:

- exact code from a source-reviewed closed set;
- root parameter class;
- leaf field class from a closed set;
- rejection stage;
- status class;
- boundary ordinal.

It MUST NOT retain arbitrary messages or values.

---

# Part IX — Verification ladder

## 32. Phase 0 — Repository archaeology and change ownership

Before implementation:

- inspect current `main`;
- inspect open integration PRs;
- identify existing client/server module contracts;
- identify generic versus client-owned behavior;
- inspect current tests and docs;
- identify stale status prose;
- select exact immutable dependency heads;
- define allowed files;
- define non-goals;
- define which repository owns each potential defect.

Deliverable: a reviewed integration dossier, not code.

## 33. Phase 1 — Exact provenance and source contract

Required evidence:

- package/distribution identity;
- exact version;
- executable proof;
- source tag/commit where available;
- model/catalog/profile identity;
- no auto-update drift;
- source-derived request/item/event facts;
- fixture hashes.

No protected model call is required.

## 34. Phase 2 — Structural capture

Required captures:

- first request;
- natural second request;
- resume/separate-session relationships;
- tool declarations and choice;
- reasoning/history;
- stream event vocabulary and order;
- final usage;
- error path.

Only structural, privacy-safe fixtures may be committed.

## 35. Phase 3 — Pure module and policy tests

Test:

- exact known fields;
- unknown fields;
- malformed types;
- absent/null/value distinctions;
- tool taxonomy;
- authority-bearing negatives;
- identity-hint extraction;
- module metadata/digest mismatch;
- default module unchanged;
- other client versions unchanged;
- unsupported pair failure;
- no side effects/import authority.

## 36. Phase 4 — Consumer conformance

Run the producer against the actual pinned consumer implementation where feasible.

Test:

- request bytes;
- header grammar/cardinality;
- signature;
- route;
- body tamper;
- signature tamper;
- replay;
- secret separation;
- endpoint containment;
- error codes;
- tool transformation.

A copied reimplementation of the consumer validator is not a substitute.

## 37. Phase 5 — Actual client with fake downstream

Use the actual exact client binary and fake downstream.

Minimum cases:

- one-turn text;
- natural two-turn function roundtrip;
- custom tool roundtrip if supported;
- provider failure;
- validator rejection;
- resumed session;
- separate session;
- malformed/unknown state;
- normal and interrupted stream.

This phase proves actual serialization behavior such as ID removal.

## 38. Phase 6 — PostgreSQL and replay/accounting integration

Execute, do not merely collect or skip:

- same-key replay persistence;
- expiry;
- route/provider/model binding;
- HMAC rotation;
- ambiguity;
- accounting finalization;
- failure release;
- zero pending;
- no side effects on pre-admission denial;
- privacy of durable metadata.

Use a uniquely named disposable database and verify cleanup.

## 39. Phase 7 — Candidate-versus-baseline differential

For old-client or environment-sensitive tests:

- use the exact same client binary;
- use the same isolated environment;
- use the same timeout;
- run candidate and baseline;
- classify whether failure occurs before candidate-specific behavior.

Allowed conclusions:

| Candidate | Baseline | Conclusion |
|---|---|---|
| pass | pass/fail | candidate gate passes |
| fail | pass | regression; stop |
| same fail before candidate behavior | same fail | baseline/harness defect; possible explicit non-regression waiver |
| different fail | fail | unresolved; stop |

A waiver is not a compatibility pass. It only says the candidate did not introduce that pre-existing failure.

## 40. Phase 8 — Pre-protected machine manifest

Before protected traffic, produce:

```json
{
  "required": [...],
  "collected": [...],
  "executed": [...],
  "missing": []
}
```

The manifest should include exact test node IDs and required external checks.

Rules:

- missing, skipped, xfailed, cancelled, pending, or environment-failed required nodes are not passes;
- prose cannot override the manifest;
- the manifest must be generated from actual collection/execution;
- all required GitHub checks must be green on the exact candidate head.

## 41. Phase 9 — One protected multi-turn qualification

Run exactly one zero-retry process after all gates pass.

Required topology:

```text
exact task-local client
-> candidate Gateway
-> exact pinned downstream service
-> protected model/provider
```

Required evidence:

- exact client provenance;
- request count at every hop;
- status/content-type classes;
- signed identity predicates;
- Qwen/provider invocation and success classes;
- exact stream lifecycle;
- function then message chronology;
- client exit result;
- terminal accounting per admitted request;
- zero pending;
- privacy, route, replay, and authority invariants.

If it fails, publish bounded evidence and stop. Do not repair and rerun under the same authorization.

## 42. Phase 10 — Hook-free final state

Any temporary production diagnostic hook must be removed before acceptance.

The final accepted run MUST execute against:

- final candidate code;
- no production qualification writer;
- no special production behavior toggle;
- no diagnostic route;
- no retry;
- exact pinned dependencies.

Verifier-owned test instrumentation outside `app/` may remain if it is a durable, reviewed regression asset.

---

# Part X — Safe diagnostics

## 43. Boundary snapshot schema

A reusable diagnostic should produce one sanitized snapshot with these sections.

### 43.1 Gateway boundary

- request count class;
- response count;
- status classes;
- content-type classes;
- SSE structure count;
- per-ordinal lifecycle predicates;
- safe error code/parameter class;
- handler/truncation/close state;
- accounting terminal state.

### 43.2 Downstream service boundary

- forwarded request count;
- response count/status/content type;
- fixed service-auth/signed-identity/tool-policy/upstream code;
- rejection stage;
- tool transformation state;
- per-ordinal stream predicates;
- signed identity booleans only.

### 43.3 Model/provider boundary

- inference count;
- success count;
- compiler/internal count if relevant;
- response status/content type;
- terminal stream predicates;
- handler/truncation/path rejection.

### 43.4 Accounting

- reservation finalized/released/pending counts;
- ledger finalized/failed/estimated/pending counts;
- query success;
- zero-pending predicate.

### 43.5 Client

- exact provenance class;
- process exit success;
- first/second request observed;
- function output count;
- no raw process output.

## 44. Diagnostic output privacy classes

### 44.1 Safe to retain

- public commit SHAs;
- public source tags;
- public package/version names;
- public artifact digests;
- closed event names;
- closed error codes;
- field names;
- type/presence classes;
- counts;
- booleans;
- status/content-type classes;
- fixed stage names;
- test node IDs;
- synthetic fixture values.

### 44.2 Ephemeral only

- raw request/response bodies;
- raw SSE;
- prompts/completions;
- reasoning;
- tool arguments/results;
- item/call/session/response IDs;
- signed identity values;
- nonces/signatures;
- protected endpoint;
- credentials;
- private filesystem paths;
- HMAC replay digests;
- arbitrary exception text.

### 44.3 Product-persisted control metadata

The product MAY persist versioned HMAC digests for replay control together with safe ownership/routing/expiry metadata. Those digests are private control metadata:

- not billing truth;
- not logs;
- not metrics labels;
- not audit text;
- not exports;
- not OAP evidence.

Do not write “no digest is persisted” when HMAC digests are deliberately stored. Say “no raw identifier is persisted or exposed.”

## 45. Cleanup verification

Cleanup is part of evidence.

Verify absence of:

- task roots;
- task client installation;
- temporary credentials/runtime references;
- disposable database/container;
- listeners/processes;
- generated bytecode/caches;
- task-created dependency environment in a pinned read-only checkout;
- protected service changes.

Do not trust a prior cleanup report blindly. Objective 155 found eleven leftover task roots after a report claimed cleanup. The historical report correctly remained immutable; the later audit recorded and repaired the discrepancy.

---

# Part XI — OAP governance for protocol integrations

## 46. Work-order structure

Each protocol-integration work order SHOULD state:

- exact repository/PR/base/head;
- exact dependency heads;
- exact client profile;
- exact allowed paths;
- exact non-goals;
- source hypothesis;
- mandatory pre-fix reproduction;
- authorized product change, if any;
- required negative/security tests;
- protected-run count;
- stop law;
- cleanup requirements;
- immutable report path;
- no-merge/no-auto-continuation rule.

## 47. Evidence before correction

A proposed compatibility fix MUST follow:

```text
observe bounded failure
-> classify exact boundary
-> reproduce with pure or actual-client fake test
-> inspect exact source
-> authorize one narrow correction
-> run regressions
-> perform one protected qualification
```

Do not jump from an unclassified `other` to product behavior.

Objective 155 avoided one serious speculative change by reverting standalone function-output/replay modifications when the exact failing Gateway branch had not been proven.

## 48. Stop is a valid result

An OAP round may end:

- PASSED;
- FAILED;
- BLOCKED;
- PARTIAL;
- deliberately stopped before implementation.

A strategic review that invalidates an assumption should stop the coding agent before product mutation. Objective 155-d did exactly this and preserved a truthful activation/report transcript.

## 49. Immutable reports

Each report is an immutable factual handoff.

Required discipline:

- report-only final commit;
- first parent is the literal implementation head;
- only the report path changes;
- record `Report publication commit: SELF`;
- never amend a published report;
- correct later-discovered inaccuracies in a later report;
- preserve failed and partial reports as history.

A report’s immutability does not make its claims true. Strategic review must inspect code, test collection, CI, and GitHub state.

## 50. Machine-check report claims

Every repeated checklist SHOULD have a generated obligation manifest.

For each requirement, record:

```text
obligation ID
-> concrete test node(s)
-> collected?
-> executed?
-> passed?
-> source/fixture pin?
```

The final report should be generated from or checked against this manifest.

Objective 155-aj demonstrated why: its report claimed all seven outcome classes while the actual parameterized test contained only two cases. Objective 155-ak repaired this with 80 required nodes, 80 executed nodes, and `missing=[]`.

## 51. Protected-run discipline

A protected run is expensive evidence, not a debugging loop.

Rules:

- do not run it before fake/database/CI gates;
- authorize an exact maximum count;
- zero automatic retries;
- no prompt steering around failure;
- no alternate route after failure;
- no product correction plus second run in the same authorization unless explicitly planned;
- preserve safe evidence before cleanup;
- stop after the first new unclassified boundary.

## 52. OAP suffix explosion and PR growth

A long suffix chain signals that the objective has become discovery work.

When a PR grows beyond reasonable review:

- freeze accepted behavior;
- do not add the next client;
- preserve the branch as evidence;
- decompose net product changes onto clean branches from current `main`;
- use mechanical equivalence checks;
- resume dependent repository acceptance against a clean head.

Objective 155 ended at 235 commits and 121 changed files. This is valuable history but poor review ergonomics.

---

# Part XII — Objective 155: worked lessons

## 53. Historical overview

Objective 154 introduced the static, versioned client-module foundation and left Codex 0.149 structurally captured but default-denied. Objective 155 then integrated that exact client profile with `local-coding-v1` and a protected Qwen service.

The sequence was not a straight implementation. It was a protocol-discovery program in which each exact failure exposed another hidden assumption.

The following timeline summarizes only milestones supported by inspected immutable reports and accepted source. It does not rewrite omitted rounds.

## 54. Foundation: 155-a and 155-b

### 54.1 155-a — exact Local Coding server module

Implemented:

- static `local-coding-v1` server module;
- exact route contract;
- deterministic JSON bytes;
- exact-byte signing and forwarding;
- separate service Bearer;
- signed identity;
- core-owned accounting;
- fake-Qwen conformance.

Lesson:

> A special downstream service deserves its own narrow server module. Do not disguise it as a generic OpenAI adapter.

### 54.2 155-b — endpoint and secret containment

Refined:

- direct `ProviderAdapter` inheritance;
- Responses create/stream only;
- all other operations rejected before HTTP;
- service/signing/derivation secret-role checks;
- stronger core identity boundary;
- real loopback conformance after an in-process streaming artifact.

Lessons:

- inheritance can accidentally grant unsupported endpoints;
- secret-role separation is testable configuration law;
- real loopback is required for transport evidence.

## 55. Identity discovery: 155-d and 155-e

### 55.1 155-d — deliberate stop

Skeptical review invalidated the planned session-identity assumptions, and work stopped before product implementation.

Lesson:

> A stopped round is better than encoding an identity guess.

### 55.2 155-e — relationship-based session capture

The exact client capture compared resumed and separate sessions. It established:

- `session_id` and `thread_id` as equal canonical aliases;
- stability across explicit resume;
- isolation across another session;
- installation identity was not a session;
- turn/root/cache/item IDs were not session identity.

Lesson:

> Discover identity through controlled relationships, not semantic field names.

## 56. Real-composition harness: 155-f through the stream-diagnostic rounds

155-f constructed a full-stack verifier and reached an environment-isolation failure: the pinned dependency created a repository-local `.venv`.

Subsequent stream-diagnostic rounds developed:

- task-isolated environments;
- bounded relays;
- safe status/event summaries;
- disconnect/truncation handling;
- fake provider and fake validator paths;
- protected-run stop laws;
- cleanup checks.

Lessons:

- environment side effects are part of test correctness;
- a verifier can become a major subsystem and must itself be tested;
- fake and protected topologies must be structurally comparable;
- no raw protected payload is needed to localize most failures.

## 57. Stream semantics: 155-l and 155-r

### 57.1 155-l — safe but incomplete vocabulary

The direct protected stream completed, but a narrow evidence vocabulary classified many event names as `other`, producing `ambiguous_stream_evidence`.

Lesson:

> Privacy-safe evidence that is too coarse can be operationally useless.

### 57.2 155-r — legitimate reasoning and message lifecycles

A bounded rejection shape showed a legitimate reasoning output item. Source comparison and tests led to exact ordered reasoning and assistant-message validators. A protected request then completed.

However, the external structural recorder still classified some valid production events as `other`.

Lessons:

- production and verifier vocabularies must be synchronized for the active profile;
- event names alone are insufficient; lifecycle ordering remains required;
- “production passed, verifier uncertain” must be reported explicitly.

## 58. Two-turn diagnostics: 155-t through 155-z

### 58.1 155-t — no surviving safe artifact

The fake two-turn path passed, but the protected attempt ended with `qualification_evidence_incomplete` because no safe per-boundary artifact survived.

Lesson:

> Build the safe snapshot before the assertion and before cleanup.

### 58.2 155-y — revert an unproven fix

A speculative standalone function-output/call-digest/session replay change was implemented during exploration but the exact failure code was not proven. The change was reverted; only diagnostics remained.

Lesson:

> Revert a plausible fix when ownership is unproven.

### 58.3 155-z — second-turn shape localized

The protected second request contained:

- three message items;
- one reasoning item;
- one function call;
- one function-call output;
- function/custom plus search-like declarations.

It still failed with a Gateway error classified as `other`. The accounting verifier then incorrectly expected a two-turn accounting sequence even though only one request had been admitted.

Lessons:

- request-attempt count is not admitted-request count;
- layer-specific error vocabularies are mandatory;
- exact item shape matters more than a coarse “second turn failed.”

## 59. Reasoning and provenance: 155-aa through 155-ad

### 59.1 155-aa — generic API type used too early

The rejected item was identified as ID-less reasoning with content/summary/encrypted fields. The analysis compared it to a generic OpenAI SDK type that required an ID and declined support.

Later exact Codex 0.149 source showed that the client dialect allowed an optional reasoning ID.

Lesson:

> Generic SDK types do not override exact client-version source.

### 59.2 155-ab — empty-placeholder hypothesis not proven

The intended predicate was not reached because the first turn failed. No canonicalization was implemented.

Lesson:

> Do not implement a transformation when the predicate-bearing request was not observed.

### 59.3 155-ac — exact executable provenance

The verifier proved task-local `@openai/codex@0.149.0` was actually invoked and host 0.149.1 was not.

Lesson:

> Version provenance is a prerequisite, not report decoration.

### 59.4 155-ad — state-bearing ID-less reasoning

A successful first turn revealed that the ID-less reasoning item had non-empty content, empty summary, null encrypted content, and no unexpected fields.

This killed the “empty placeholder” idea.

Lesson:

> Missing provider identity does not mean missing semantic state.

## 60. Dialect corrections: 155-ae through 155-ag

### 60.1 155-ae — visible reasoning support

The exact 0.149 client dialect gained bounded ID-less visible reasoning support, scoped to the exact pairing. No ID was fabricated.

### 60.2 155-af — null is not encrypted replay

The early encrypted-replay detector treated field presence as intent. `encrypted_content: null` was corrected to stay on the visible path.

Lesson:

> Presence, null, and non-null are distinct authority classes.

### 60.3 155-ag — item ID removal and call-ID replay

Actual Codex behavior proved that a non-prefixed tool-call item ID could be removed while `call_id` remained. The Gateway implemented same-key call-ID-HMAC fallback, exact-match and route/tool binding, and no downgrade from a wrong present item ID.

Lessons:

- serialize with the actual client, not a handwritten approximation;
- a fallback can preserve security if it uses an existing authenticated anchor;
- absent-ID support must be declarative and exact-profile-scoped.

## 61. Boundary and identity corrections: 155-ah and 155-ai

### 61.1 155-ah — first Local request rejected

A verifier-only diagnostic showed `signed_identity_field_invalid` before Qwen.

Source comparison found:

- Local required alphanumeric-leading identity fields;
- Gateway used unprefixed base64url HMAC output;
- base64url could begin with `-` or `_`;
- the route grammar also differed.

Lesson:

> Test generated values against the actual consumer grammar, including edge-distribution cases.

### 61.2 155-ai — full real product path succeeded

The producer changed to an unconditional safe prefix over the full HMAC digest and validated signed route/identity grammar.

The protected run then achieved:

- two Gateway requests;
- two Local requests;
- two successful Qwen inference calls;
- valid signatures and grammar;
- successful Codex exit;
- two finalized accounting rows;
- zero pending.

The only failure was external verifier event vocabulary: valid reasoning events were collapsed to `other`.

Lesson:

> Separate a product-path success from an evidence-layer failure.

## 62. Conformance cleanup: 155-aj and 155-ak

### 62.1 155-aj — production hook cleanup, non-conformant report

The production qualification hook was removed deletion-only, which was good.

But the report claimed:

- complete event vocabulary;
- all seven outcome cases;
- complete rotation coverage;
- a larger Local matrix;

while source/test collection did not support all claims. No final protected run occurred.

Lessons:

- deleting temporary production hooks is mandatory;
- a green CI set does not validate report prose;
- manually written obligation tables can overclaim.

### 62.2 155-ak — machine-checked final acceptance

155-ak:

- kept the `app/` tree byte-identical to the cleaned candidate;
- repaired only verifier/tests;
- added exact reasoning event names;
- executed all snapshot and outcome cases;
- completed HMAC rotation tests;
- ran a 19-row actual-Local matrix;
- classified an old 0.148 test through candidate/baseline differential;
- produced `missing=[]` over 80 required nodes;
- ran one hook-free zero-retry real two-turn qualification;
- finalized two accounting rows;
- cleaned task state.

Lesson:

> Final acceptance should be an evidence-conformance exercise, not another feature round.

---

# Part XIII — Future client onboarding procedure

## 63. Gate A — integration dossier

Before code, create:

```text
docs/agentic-clients/<profile-id>.md
```

The dossier MUST answer:

### Identity and provenance

- What exact product and distribution?
- What exact version?
- Is source available?
- What tag/commit corresponds to the executable?
- What package hash or integrity metadata is pinned?
- What model catalog/profile is active?
- Can it auto-update or refresh model metadata?
- What executable is actually invoked?

### Wire behavior

- Chat Completions, Responses, Anthropic, custom, or mixed?
- HTTP or WebSocket?
- Streaming or non-streaming?
- Which endpoints?
- Which top-level fields?
- Which item types?
- Which request fields vary by model or feature?
- What does the natural second turn contain?

### State

- Provider-managed or client-managed?
- What reasoning/compaction/history is replayed?
- Which IDs are optional?
- Does the client remove or rewrite IDs?
- What is the replay anchor?
- Can provider-managed and client-managed state coexist?

### Tools and authority

- Which tools are local to the client?
- Which appear provider-hosted?
- Which are adapter-managed?
- What `tool_choice` forms occur?
- Are MCP, shell, computer, search, connectors, or plugins present?
- Can they be disabled for baseline capture?

### Session identity

- Which metadata changes per request?
- Which stays stable across resume?
- Which separates sessions?
- Which is installation-wide?
- Is any candidate canonical and bounded?
- How is it bound beneath Gateway owner/key/repository truth?

### Streaming

- Exact event names?
- Exact item/part lifecycle?
- Ordering/cardinality?
- Final output/usage shape?
- Error events?
- Normal close?
- Client behavior on unknown/missing events?

### Accounting and privacy

- How many model requests per natural agent turn?
- Is final usage present on every request?
- Are tool declaration/history bytes counted?
- What may be retained?
- What must remain ephemeral?
- What durable replay metadata is needed?

## 64. Gate B — profile decision

Choose one:

1. **Ordinary default client**  
   No dialect difference. Test and document only.

2. **New versioned client module, existing server module**  
   Client request/history differs, downstream transport remains supported.

3. **Existing client module, new server module**  
   Client is ordinary; downstream service has a distinct exact contract.

4. **New client module and new server module**  
   Both sides differ.

5. **Unsupported protocol**  
   The client does not fit current endpoint/transport/state architecture.

Do not force a custom or Anthropic/WebSocket protocol into Responses merely to reuse code.

## 65. Gate C — required source files

A typical new client profile may require:

```text
app/slaif_gateway/modules/clients/<client_profile>.py
app/slaif_gateway/modules/clients/registry.py
app/slaif_gateway/modules/contracts.py
tests/fixtures/<client>/<version>/...
tests/unit/test_<client>_module.py
tests/unit/test_<client>_request_policy.py
tests/unit/test_<client>_streaming.py
tests/integration/test_<client>_replay_postgres.py
docs/agentic-clients/<profile-id>.md
docs/responses-compatibility.md
docs/compatibility-matrix.md
```

A new downstream contract may additionally require:

```text
app/slaif_gateway/modules/servers/<server>/
tests/fixtures/<server>/
tests/unit/test_<server>_module.py
tests/integration/test_<server>_postgres.py
```

Do not copy Objective-155’s entire verifier into each client. Extract reusable bounded harness components after review.

## 66. Gate D — default-false policy facts

Every dialect difference SHOULD be a named default-false fact.

Potential categories:

```text
request envelope fields
metadata vocabulary
session alias requirements
reasoning ID optionality
visible reasoning content types
encrypted reasoning
function/custom item-ID optionality
call-ID replay fallback
compaction state
tool declaration shapes
stream event profile
output ID behavior
```

A future integration SHOULD add only the facts it actually needs.

## 67. Gate E — negative matrix

Before any real model call, prove:

- unknown field denied;
- unknown item denied;
- unknown tool denied;
- explicit hosted authority denied;
- MCP/connector/shell/computer denied unless separately implemented;
- malformed metadata denied;
- session ambiguity denied;
- wrong module version/digest denied;
- unsupported pair denied;
- missing key/route capability denied;
- cross-key replay denied;
- cross-route/provider/model replay denied;
- expired replay denied;
- wrong present ID cannot downgrade;
- malformed/oversized state denied;
- provider-managed plus client-managed state denied where unsupported;
- no raw value in errors/logs/evidence;
- no pre-admission accounting side effect.

## 68. Gate F — natural multi-turn acceptance

A future client is not agentically qualified until the actual client naturally performs:

```text
turn 1:
  model reasoning
  approved local tool call
client:
  executes/simulates tool
turn 2:
  replay/history
  tool output
  final assistant response
```

Handcrafting the second request is insufficient for final compatibility evidence, though it is useful for unit tests.

## 69. OpenCode-specific instruction

No OpenCode protocol claim is made here.

For an OpenCode integration:

- select an exact release and distribution;
- determine whether its provider layer uses Responses, Chat Completions, Anthropic messages, or another API for the chosen model;
- capture the actual provider request;
- identify whether tools execute locally;
- identify session and continuation state;
- inspect source at the exact release when available;
- create a separate module only for proven differences;
- do not inherit Codex reasoning, metadata, ID, or tool rules.

An OpenCode profile that happens to speak ordinary OpenAI-compatible Chat Completions may need no special client module. Another profile or provider plugin may require a different one.

## 70. Antigravity-specific instruction

No Antigravity protocol claim is made here.

For an Antigravity integration:

- establish whether a reproducibly pinnable client exists;
- establish whether source is available;
- pin exact executable and model/provider configuration;
- disable updates, extensions, connectors, and external tools for the baseline;
- use black-box structural capture if source is unavailable;
- narrow support to observed shapes;
- require stronger differential and multi-turn evidence;
- do not infer Codex-compatible state or SSE behavior.

If the client cannot be pinned or its protocol changes remotely without a stable profile identity, it MUST remain unsupported for security/accounting-critical use.

## 71. Closed-source or remotely mutable clients

When source is unavailable or behavior is remotely controlled:

- retain executable/package signature and version;
- retain configuration and remote-profile identity where observable;
- use repeated deterministic structural captures;
- use candidate-versus-prior-profile differentials;
- support a narrower feature set;
- shorten requalification interval;
- default-deny on drift;
- avoid provider-state/replay features that cannot be authenticated;
- document the uncertainty.

A vendor brand/version string alone is not enough.

---

# Part XIV — Definition of done

## 72. Technical qualification checklist

An integration is technically qualified only when all applicable items are true.

### Profile

- [ ] exact distribution and version pinned;
- [ ] actual invoked executable proven;
- [ ] exact source tag/commit inspected where available;
- [ ] model/catalog/config profile pinned;
- [ ] fixture digests bound to module metadata;
- [ ] update/drift behavior controlled.

### Architecture

- [ ] client module is pure and non-authoritative;
- [ ] server module is transport-limited;
- [ ] static registries only;
- [ ] exact client/server pair;
- [ ] default client unchanged;
- [ ] other client versions unchanged;
- [ ] core retains all authority.

### Request and state

- [ ] exact fields/types/bounds;
- [ ] absent/null/value cases;
- [ ] reasoning/history semantics;
- [ ] no fabricated ID;
- [ ] provider/client state combination rule;
- [ ] tool-call/output chronology;
- [ ] replay ownership and no downgrade.

### Tools

- [ ] local versus hosted versus candidate taxonomy;
- [ ] exact declaration schemas;
- [ ] post-transformation `tool_choice`;
- [ ] hosted/MCP/shell/computer denial;
- [ ] declaration-byte accounting.

### Identity

- [ ] session relationship capture;
- [ ] owner/key/repository/route binding;
- [ ] consumer grammar;
- [ ] exact-byte signing;
- [ ] secret-role separation;
- [ ] replay mode/deployment limitation;
- [ ] actual consumer matrix.

### Streaming

- [ ] exact active event vocabulary;
- [ ] reasoning lifecycle;
- [ ] function/custom lifecycle;
- [ ] message lifecycle;
- [ ] terminal output/usage;
- [ ] unknown/error/truncation/disconnect negatives;
- [ ] verifier/production vocabulary relationship.

### Accounting

- [ ] per-admitted-request lifecycle;
- [ ] pre-admission no dummy row;
- [ ] provider failure;
- [ ] validator failure;
- [ ] missing usage;
- [ ] replay persistence after finalization;
- [ ] zero pending.

### Evidence

- [ ] fake actual-client two-turn;
- [ ] PostgreSQL tests executed;
- [ ] baseline differential where needed;
- [ ] machine manifest `missing=[]`;
- [ ] all required GitHub checks;
- [ ] exactly one hook-free protected run;
- [ ] immutable report;
- [ ] cleanup verified.

## 73. Status vocabulary

Use precise status:

| Status | Meaning |
|---|---|
| Structurally captured | Request/stream shapes observed safely |
| Module implemented | Code exists; no E2E implication |
| Fake-conformant | Actual client works against fake topology |
| Cross-contract conformant | Producer passes actual pinned consumer |
| Protocol-qualified | Exact protected multi-turn path passed |
| Deployment-qualified | Deployment topology/operations separately passed |
| Release-ready | Maintainer-approved release criteria passed |
| Production-certified | Only after explicit security/operational certification; never inferred |

---

# Part XV — Post-acceptance decomposition and long-term maintenance

## 74. Evidence branch versus merge vehicle

A long discovery branch may contain:

- product code;
- permanent tests;
- permanent fixtures;
- permanent docs;
- one-off verifier code;
- dozens of immutable orders/reports;
- temporary diagnostic history.

Technical acceptance does not make the whole branch reviewable.

For Objective 155, PR #291 is the immutable evidence branch. A clean integration should be reconstructed from current `main` in small PRs.

## 75. Recommended decomposition classes

### 75.1 Permanent production

Examples:

- client-module facts;
- static registry entries;
- exact server module;
- request-policy deltas;
- replay service/repository;
- stream validator;
- identity/signing;
- core orchestration;
- configuration.

### 75.2 Permanent contract tests and fixtures

Examples:

- exact source/capture fixtures;
- pure client module tests;
- consumer grammar tests;
- replay/HMAC rotation tests;
- stream lifecycle tests;
- PostgreSQL accounting/replay tests;
- fake actual-client two-turn test.

### 75.3 Permanent documentation

Examples:

- this contract;
- client profile dossier;
- compatibility matrix;
- request/stream/replay/accounting contracts;
- deployment limitations.

### 75.4 Reusable verifier tooling

Keep only components that are:

- generic enough for another profile;
- bounded and privacy-safe;
- testable without protected resources;
- not hard-coded to one historical objective/head/path;
- useful for regression or release qualification.

### 75.5 Historical-only material

Keep on the evidence branch or archive:

- objective-specific topology constants;
- obsolete protected-runtime paths;
- report-specific discrepancy logic;
- temporary rejection artifacts;
- one-off source probes;
- hard-coded Objective-155 suffix gates;
- old failed-run orchestration.

## 76. Mechanical equivalence during decomposition

A decomposition MUST prove:

- intended `app/` behavior matches the accepted implementation;
- no temporary production hooks return;
- fixtures preserve exact hashes or intentionally version;
- test coverage maps to accepted obligations;
- default and older clients remain unchanged;
- final clean head passes fake, database, CI, and one appropriately authorized real qualification;
- Local Coding resumes its acceptance against the exact clean Gateway head.

Do not merge PR #291 merely to preserve history. Git history remains available on the open/closed evidence branch.

## 77. Requalification triggers

Requalify when:

- client version changes;
- model catalog changes;
- client config/profile changes;
- downstream server version changes;
- stream vocabulary changes;
- reasoning or ID behavior changes;
- tool taxonomy changes;
- replay schema or HMAC rotation changes;
- identity/signing contract changes;
- deployment worker/replay topology changes;
- provider usage/accounting changes.

A fixture digest mismatch should fail closed until review.

---

# Part XVI — Anti-pattern catalogue

## 78. Protocol anti-patterns

### “It is OpenAI-compatible”

Why wrong: brand-level compatibility says nothing about agentic state, tools, or streams.

Correct response: capture the exact multi-turn profile.

### “The SDK type requires an ID, so the client is wrong”

Why wrong: the actual client version may use a narrower or extended dialect.

Correct response: inspect exact client source and actual serialization.

### “Missing ID means placeholder”

Why wrong: item may contain state.

Correct response: classify every field state and preserve legitimate content.

### “Add an ID so validation passes”

Why wrong: fabricates provider/client identity.

Correct response: preserve absence or fail; use another authenticated anchor only if proven.

### “Field exists, therefore capability requested”

Why wrong: null may mean no state.

Correct response: classify absent/null/non-null.

### “Call ID fallback can rescue any bad item ID”

Why wrong: creates downgrade attack.

Correct response: fallback only when item ID is absent and exact policy authorizes it.

### “Tool named web_search means provider search”

Why wrong: may be client-local or adapter-managed.

Correct response: classify authority independently.

### “Known event name means valid stream”

Why wrong: ordering and correlations matter.

Correct response: bounded state machine.

### “Production validator passed, so verifier can ignore unknown names”

Why wrong: verifier then cannot support the acceptance claim.

Correct response: exact source-reviewed active-profile vocabulary.

## 79. Testing anti-patterns

### One-turn-only qualification

Fails to test replay and tool continuation.

### Handwritten second request only

Fails to prove actual client serialization.

### Fake success as final evidence

Useful but not a protected topology result.

### Retry until green

Conceals intermittent protocol/identity defects.

### Host-default executable

Makes version claims unreliable.

### In-process-only stream tests

Can hide real HTTP framing/close behavior.

### Collected-but-skipped PostgreSQL test

Not evidence.

### Report table without test-node manifest

Can claim nonexistent cases.

### Protected assertion before snapshot serialization

Destroys the most valuable failure evidence.

### Environment failure called product failure

Use candidate/baseline differential.

## 80. Security anti-patterns

- raw IDs in logs;
- HMAC digest in reports;
- caller-selected client module;
- dynamic module loading;
- inherited broad provider adapter;
- shared service/signing/derivation secret;
- client metadata used as principal authority;
- route name not checked against signed consumer grammar;
- process-local replay described as multi-worker safe;
- provider-managed and client-managed state mixed without a contract;
- diagnostic production hook left after acceptance.

## 81. Process anti-patterns

- amending an immutable report;
- declaring failed evidence successful retroactively;
- continuing feature discovery after acceptance;
- allowing a giant evidence PR to become the merge vehicle;
- treating ten green CI checks as proof of a report’s prose;
- creating a new client before decomposing shared architecture;
- cleaning unrelated worktrees/artifacts;
- letting the coding agent choose the next objective or merge.

---

# Part XVII — Templates

## 82. Agentic client profile dossier template

```markdown
# <CLIENT PROFILE ID>

## Status

- Product:
- Distribution:
- Exact version:
- Executable version output:
- Source tag:
- Source commit:
- Package integrity:
- Model/catalog:
- Client config/profile:
- Wire API:
- Endpoint set:
- Server module:
- Fixture digests:
- Qualification status:

## Scope

Supported:
- ...

Explicitly unsupported:
- ...

## Provenance procedure

- ...

## Request envelope

| Field | State/type | Bound | Authority meaning |
|---|---|---:|---|

## Input items

| Item type | Fields | ID semantics | State semantics |
|---|---|---|---|

## Session identity experiment

| Candidate | A1=A2 | A!=B | Installation-wide | Selected |
|---|---:|---:|---:|---:|

## Tool taxonomy

| Client shape | Class | Transformation | Required gates |
|---|---|---|---|

## Replay ownership

- Item identity:
- Call identity:
- Persistence:
- TTL:
- Rotation:
- No-downgrade rule:

## SSE state machines

### Reasoning
- ...

### Function/custom tool
- ...

### Assistant message
- ...

### Terminal
- ...

## Accounting

- Requests per natural tool round:
- Usage source:
- Failure handling:
- Zero-pending rule:

## Privacy

Ephemeral:
- ...

Persisted safe metadata:
- ...

Forbidden:
- ...

## Test and obligation manifest

- ...

## Protected qualification

- Exact topology:
- Maximum runs:
- Acceptance predicates:
- Cleanup:
```

## 83. Strategic work-order template

```markdown
# Objective NNN-x — <exact profile task>

PR mode:
Repository:
PR:
Branch:
Base:
Starting head:
Dependency heads:
Client profile:
Protected run allowance:

## Fixed hypothesis

...

## Mandatory reproduction before product change

...

## Authorized change

...

## Explicit non-goals

...

## Allowed paths

...

## Required pure tests

...

## Required actual-client fake tests

...

## Required PostgreSQL tests

...

## Required privacy/security negatives

...

## Machine obligation manifest

`missing=[]` required before protected traffic.

## Protected run

Exactly <N> zero-retry process(es).

## Stop law

On the first new unclassified boundary:
- publish bounded evidence;
- make no second correction;
- do not retry.

## Cleanup

...

## Immutable report

Report path:
Report-only commit:
No amendment:
No merge:
No automatic next objective:
```

## 84. Failure-triage template

```text
1. Is exact client provenance proven?
   no -> provenance-owned; stop

2. Did Gateway receive the request?
   no -> client/transport-owned

3. Did client normalization pass?
   no -> client-dialect module

4. Did pair/route/capability pass?
   no -> Gateway configuration/policy

5. Did replay ownership pass?
   no -> replay contract

6. Was reservation created?
   no -> pre-admission failure; no ledger row required

7. Did downstream service receive exact bytes?
   no -> server adapter/Gateway

8. Did service auth/signed identity pass?
   no -> service boundary; compare producer/consumer

9. Did model/provider receive request?
   no -> downstream policy/constitution

10. Did model/provider complete valid stream?
    no -> model/provider

11. Did downstream return valid stream?
    no -> downstream stream translation

12. Did Gateway production validator accept?
    no -> production stream contract

13. Did official client complete?
    no -> client consumption

14. Did only verifier reject?
    yes -> verifier expectation/evidence layer

15. Is failure identical on baseline before candidate behavior?
    yes -> baseline/harness defect, possible explicit non-regression waiver
```

## 85. Module-version decision table

| Change | Same module allowed? | Required action |
|---|---:|---|
| Documentation typo only | yes | docs/test hygiene |
| New public fixture digest for unchanged semantics | usually no silent reuse | version metadata deliberately |
| Client patch, wire proven identical | possibly | differential + source proof |
| New request field | no | new module version/profile |
| New metadata/session semantics | no | new module version/profile |
| Changed ID/replay behavior | no | new module version/profile |
| New stream event/lifecycle | no | new module version/profile |
| New model catalog selecting another protocol | no | distinct profile |
| New server pairing | no | explicit pair review |
| New hosted tool authority | never via module alone | core policy/accounting objective |

---

# Part XVIII — Suggested AGENTS.md insertion

The following concise section should be added to `AGENTS.md` when this contract is adopted.

```markdown
### Agentic client integrations

`AGENTIC_CLIENT_INTEGRATION.md` is authoritative for adding or changing support
for Codex, OpenCode, Antigravity, Claude Code, Gemini CLI, Aider, or any other
agentic client.

A product/brand or “OpenAI-compatible” claim is never a compatibility key.
Support must be pinned to one exact executable/distribution version, source
contract where available, model/catalog/config profile, structural fixtures,
client-module version, and explicit client/server pairing.

Client modules are pure, static, non-authoritative dialect decoders. They must
not authenticate, route, grant tools, access PostgreSQL/Redis, perform HTTP, or
own quota/accounting. Server modules are exact downstream transports and must
not own public authentication or policy. The Gateway core retains all
authority.

Client-specific reasoning, metadata, tool, identifier, replay, and SSE behavior
must remain version-owned and default-false. Do not globally relax the ordinary
OpenAI contract. Do not fabricate item IDs, treat null as non-null state, infer
hosted authority from tool names, or accept ID-less replay without a
cryptographically authenticated same-key fallback and no-downgrade proof.

Every agentic profile requires exact-client structural capture, natural
two-turn fake conformance, producer-against-actual-consumer tests, executed
PostgreSQL replay/accounting tests, a machine-checked `missing=[]` obligation
manifest, and an explicitly authorized hook-free protected multi-turn run.
Reports are immutable claims, not proof; strategic review must inspect actual
test collection/execution and GitHub state.

Temporary production diagnostic hooks must be removed before acceptance.
After acceptance, freeze behavior and decompose/review the evidence branch
before adding another client.
```

---

# Part XIX — Source and evidence map

This section makes the derivation auditable. It is not a substitute for reading the source.

## 86. Canonical architecture and code

- **S01** — `ulfe-lmi/slaif-api-gateway@7ffce834915b74809109e8b579d8541cdcfa9df7`  
  Main baseline merging versioned client modules.

- **S02** — `ulfe-lmi/slaif-api-gateway@acea2af4ca0f4586fc159c91607e1848f53f1107:app/slaif_gateway/modules/contracts.py`  
  Declarative `ResponsesClientPolicySpec`, `CanonicalClientRequest`, server descriptors, pair type.

- **S03** — `...:app/slaif_gateway/modules/clients/base.py`  
  Pure trust-limited client-module protocol.

- **S04** — `...:app/slaif_gateway/modules/clients/registry.py`  
  Literal client registry and server-side `{id, version, fixture_sha256}` selection.

- **S05** — `...:app/slaif_gateway/modules/clients/codex_0149.py`  
  Exact Codex 0.149 profile, source pins, field/tool allowlists, default-denied authority shapes, dialect policy facts.

- **S06** — `...:app/slaif_gateway/modules/clients/openai_default.py`  
  Ordinary default client behavior and no special dialect grants.

- **S07** — `...:app/slaif_gateway/modules/servers/registry.py`  
  Literal server registry and finite client/server compatibility pairs.

- **S08** — `...:app/slaif_gateway/modules/servers/local_coding/contract.py`  
  Exact Local route contract and signed-route grammar.

- **S09** — `...:app/slaif_gateway/modules/servers/local_coding/identity.py`  
  HMAC pseudonymization, unconditional safe prefix, grammar validation, canonical signing bytes.

- **S10** — `...:app/slaif_gateway/modules/servers/local_coding/adapter.py`  
  Responses-only exact-byte transport and endpoint/secret containment.

- **S11** — `...:app/slaif_gateway/services/codex_replay_service.py`  
  Same-key HMAC replay ownership, item/call lookup, no-downgrade behavior, route compatibility, post-accounting persistence.

- **S12** — `...:app/slaif_gateway/providers/streaming.py`  
  Exact stream event sets and bounded reasoning/function/message lifecycle validators.

- **S13** — `...:app/slaif_gateway/services/responses_request_policy.py`  
  Core request policy, independent capabilities, input validation, state/tool gates, token bounds.

## 87. Permanent documentation

- **S14** — `docs/module-architecture.md` on accepted Objective-155 branch.  
  Static client/server architecture and unequal trust interfaces.

- **S15** — `docs/responses-compatibility.md` on accepted branch.  
  Bounded Responses behavior, exact Codex/Local pair, reasoning and ID-less replay semantics.

- **S16** — `docs/codex-compatibility.md`.  
  Exact-version/profile/fixture methodology and capture privacy.

- **S17** — `AGENTS.md`.  
  Repository authority hierarchy, security/accounting law, OAP/GitHub truth.

- **S18** — `OAP-COMMUNICATION-coding-agent.md`.  
  Immutable order/report and FIFO execution protocol.

## 88. Objective-155 milestone reports

- **E01** — `oap/reports/155-a-local-coding-signed-server-module.md`
- **E02** — `oap/reports/155-b-endpoint-secret-and-core-identity-containment.md`
- **E03** — `oap/reports/155-d-stable-codex-session-identity-closure.md`
- **E04** — `oap/reports/155-e-codex-thread-namespace-and-key-bound-session.md`
- **E05** — `oap/reports/155-f-real-codex-local-coding-qwen-acceptance.md`
- **E06** — `oap/reports/155-l-total-safe-stream-normalization-and-single-diagnostic.md`
- **E07** — `oap/reports/155-r-retained-event-qualification-and-final-stream.md`
- **E08** — `oap/reports/155-t-codex-envelope-activation-and-function-roundtrip.md`
- **E09** — `oap/reports/155-y-second-turn-continuation-admission-and-final-closure.md`
- **E10** — `oap/reports/155-z-exact-second-request-error-and-decisive-closure.md`
- **E11** — `oap/reports/155-aa-input-item-branch-and-hook-free-acceptance.md`
- **E12** — `oap/reports/155-ab-proven-empty-reasoning-canonicalization-and-acceptance.md`
- **E13** — `oap/reports/155-ac-pinned-provenance-first-turn-stabilization-and-predicate.md`
- **E14** — `oap/reports/155-ad-local-error-stage-and-tool-choice-diagnostic.md`
- **E15** — `oap/reports/155-ae-codex-0149-idless-visible-reasoning-and-final-acceptance.md`
- **E16** — `oap/reports/155-af-null-encrypted-replay-detector-and-final-acceptance.md`
- **E17** — `oap/reports/155-ag-codex-0149-idless-tool-call-replay-and-final-acceptance.md`
- **E18** — `oap/reports/155-ah-local-turn2-boundary-diagnostic-and-evidence-closure.md`
- **E19** — `oap/reports/155-ai-signed-identity-grammar-interoperability-and-acceptance.md`
- **E20** — `oap/reports/155-aj-final-hook-free-objective-155-acceptance.md`
- **E21** — `oap/reports/155-ak-conformance-repair-and-final-acceptance.md`

## 89. Current accepted evidence

- **Accepted implementation:** `acea2af4ca0f4586fc159c91607e1848f53f1107`
- **Accepted report:** `45eeeb538e95ab3ae1d4d6e78ffb654e0e496fa2`
- **Cleaned production semantic base:** `e503f9647cb1ef9d2fef5cebe159c84e5a9c1ed4`
- **Local Coding authority:** `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`
- **Exact Codex source contract used by the module:** tag `rust-v0.149.0`, commit `758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`

---

# Part XX — Final maintainer rule

The most important lesson from Objective 155 is not a Codex-specific field rule.

It is this:

> Agentic compatibility is an evidence-backed relationship among an exact client serializer, a versioned non-authoritative dialect module, the Gateway core’s independent authority and accounting gates, an exact downstream server contract, and a multi-turn stream/replay lifecycle.

Future integrations MUST preserve that relationship.

Do not copy Codex behavior into OpenCode or Antigravity. Copy the **method**:

```text
pin
capture
classify
separate authority
model state explicitly
reproduce naturally
bind replay cryptographically
test producer against consumer
validate streams as lifecycles
account each admitted request
retain only bounded evidence
run once hook-free
freeze
decompose
review
```

That is the reusable product of Objective 155.
