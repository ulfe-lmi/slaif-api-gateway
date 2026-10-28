# CLI key-configuration field administration

This page is the authoritative list of which gateway-key configuration
fields the CLI administers today and which remain proposed. It is updated
per objective; it NEVER declares the full historical brief complete.

Status legend:

- **Implemented** — administered through the installed CLI today, with the
  documented semantics and tests.
- **Proposed (later objective)** — planned in the CLI feature round; not
  implemented. The named objective owns the scope.
- **Not a CLI surface** — intentionally administered elsewhere (named).

## Implemented in objective 196 (typed key-policy configuration)

| Field / group | CLI surface | Notes |
| --- | --- | --- |
| Model allow-list (`allowed_models`) | `create` / `policy update` flags and policy file | Omission preserves on update; invalid empty configurations remain rejected. |
| Endpoint allow-list (`allowed_endpoints`) | `create` / `policy update` flags and policy file | Same preservation law. |
| Allow-all models/endpoints flags | `create` / `policy update` flags and policy file | Explicit `--no-*` forms are explicit settings. |
| Provider restriction (`allowed_providers`) | `create` / `policy update`: `--allowed-provider`, `--provider-all`, `--provider-none` (mutually exclusive) and policy file | Per-operation semantics: omitted on CREATE = unrestricted default (flag absent); omitted on UPDATE = preserve the current value; explicit `--provider-all`/file `null` = explicitly UNRESTRICTED; `--provider-none`/file `[]` = deny ALL providers. Explicit unrestricted vs deny-all are distinct and persisted distinctly; nothing is truthiness-collapsed. |
| Lifetime quotas (cost EUR, tokens, requests) | `create` flags, `set-limits`, and policy file | `null` = unlimited; omitted on update = preserve. |
| Rate-limit overrides (per member) | `create` flags, `set-rate-limits`, and policy file per-member patch | Explicit `null` resets one member (inherit); unknown members are rejected; the historical `concurrent_requests` spelling canonicalizes to `max_concurrent_requests`. |
| Responses/Codex policy block | `create` / `policy update` policy file | Complete replacement block only; strict finite authoring validation (capabilities, prerequisites, local tool pairing, exact client-module pin). |
| Client-module pin identity | policy file `responses_policy.client_module` | Exact registered identity; stale pins fail with migration guidance; the configured Codex profile is bootstrapped before pin authoring; the migration law guards existing bindings. |
| Lazy throttling policy | policy file (`lazy_throttling_policy`) | `null` removes the stored policy; complete blocks only. The CLI does not otherwise read/change/reset it outside the typed file path. |
| Chat streaming live-burn policy | `set-chat-streaming-live-burn` and policy file (complete blocks) | `null` in a file is rejected; disabling uses the existing command. |
| External tool policy | `external-tools show|update` and policy file (complete blocks) | `null` removes the fenced policy; fenced blocks require the fresh `--confirm-external-tool-fenced` acknowledgement (file field or explicit flag). |
| Safe policy export | `keys policy export` | Version-1 document; explicit `null` for absent groups; never emits fresh confirmations; fails explicitly on stored policy it cannot administer. |

## Proposed for later objectives (NOT implemented)

| Field / capability | Proposed objective |
| --- | --- |
| Dedicated lazy/effective policy commands and effective-policy lookup | 197 |
| Source-key clone: plan/fingerprint against a live source key with expected live UUID (initial binding of a new independent key) | 198 |
| Provider/route administration parity in the CLI | 199 |
| Replay-reference inspection and expiry maintenance (NOT ownership administration or ownership transfer) | 200 |
| Diagnostics and effective-state inspection commands | 201 |
| Delivery inspection (pending/queued email state) | 202 |
| Batch key operations beyond the existing bulk import | 203 |
| Owner/cohort edits plus non-secret key-configuration inspection (NOT generic key editing) | 204 |
| Full executable-only transcript and qualification evidence | 205 |

## Intentionally not CLI surfaces

- Issued key material recovery/resend: one-time plaintext only, existing
  explicit safe options; lost keys rotate.
- Arbitrary metadata editing: the CLI and admin surfaces administer the
  reviewed field set only; no generic patch language.
- Usage/reservation/hold state: accounting is service-owned; CLI resets go
  through the dedicated commands with their confirmations.
