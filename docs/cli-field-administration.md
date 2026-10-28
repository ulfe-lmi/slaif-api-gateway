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
| Lazy throttling policy | policy file (`lazy_throttling_policy`) and `set-lazy-throttling` (objective 197) | `null` removes the stored policy; complete blocks only. Objective 197 adds the dedicated audited setter; the typed file path is unchanged. |
| Chat streaming live-burn policy | `set-chat-streaming-live-burn` and policy file (complete blocks) | `null` in a file is rejected; disabling uses the existing command. Strict authoring accepts only the closed member set (`version`, `enabled`, `cost_margin_eur`, `token_margin`) on file create, configuration update, and RAW stored export. |
| External tool policy | `external-tools show|update` and policy file (complete blocks) | `null` removes the fenced policy; fenced blocks require the fresh `--confirm-external-tool-fenced` acknowledgement (file field or explicit flag). |
| Safe policy export | `keys policy export` | Version-1 document; explicit `null` for absent groups; never emits fresh confirmations; fails explicitly on stored policy it cannot administer; the rendered document is re-parsed by the same strict schema, so round-trips apply on compatible targets only. |

## Implemented in objective 197 (effective key policy, safe lookup, bounded lazy throttling)

| Field / group | CLI surface | Notes |
| --- | --- | --- |
| Lazy throttling policy (dedicated setter) | `keys set-lazy-throttling` | `--mode wait` requires both positive bounds within the installation ceilings; `--mode reject` removes the stored override (default immediate rejection) and is REFUSED - before any mutation - when waiting bounds are supplied, because the shared KeyService canonicalizes reject to "no stored override"; plain reject and `--clear` are distinct verbs with the same stored outcome and accept no waiting bounds. Shared KeyService validator/write/audit path (one audit row); changes only lazy metadata, `updated_at`, and the audit. |
| Effective policy inspection | `keys policy effective` | Configuration-only (no authentication, no state change): configured/effective/source per rate member, per-selected-window count semantics, inherited-rate-vs-unlimited-quota warning, lifetime quotas (null = unlimited), stored lazy state, model/endpoint/provider allow-lists, Responses/Codex profile identity, Redis configuration. |
| Safe lookup and bounded paging | `keys list` / `keys show` | Exact public key ID and exact owner email lookup; full bearer-shaped input AND credential-shaped references (internal whitespace, `.` secret separator, case-insensitive `Bearer` prefix, any accepted key prefix) refused with a fixed no-echo error BEFORE any database query; cohort/status filters before the limit; `--limit` (max 200) + `--offset` with additive `paging` metadata using a bounded one-row lookahead, so `has_more` is true only when an extra real row exists and `next_offset` is null at the true end; stable `created_at` + UUID tiebreaker. `show`/`list` display safe projections only (canonical or fixed-invalid Responses policy, explicit `allowed_providers_state`, finite `calibration_metadata` members, known-shape redaction of free-form read values). |
| Configuration-only route explanation | `keys policy explain-route` | Key-state blockers first; allow-list vs enabled-route intersection; existing resolver law and 1000-candidate bound (disclosed); base-request capability checks; discovery separately authorized; provider config references never projected. |

## Implemented in objective 198 (faithful standard-key cloning)

| Field / group | CLI surface | Notes |
| --- | --- | --- |
| Source-key clone: canonical plan/fingerprint + execution | `keys clone --dry-run` / `--execute` | Two-step reviewed plan file (strict version-1, 128 KiB bound, 0600, never overwritten; a SUCCESSFUL dry-run always yields an executable plan - the built document is re-validated with the same strict schema before the file is written, so out-of-bounds builds fail with no file/audit/mutation; execute read bounded at 128 KiB + 1 with oversized files refused before any database access; mixed-mode flags refused in both directions). Standard purpose/mode, active, in-window, unfenced sources only; target owner + existing cohort required. Canonical 196 export equality; configured totals copied, never usage/balance/replay/holds/template membership. On first execution the source is locked, execution time sampled AFTER the lock, and the reviewed policy/`source_public_key_id`/fenced-confirmation - plus, for copy-source-expiry, the reviewed source expiry (normalized comparison, never substituted) - revalidated against the fresh source (mismatches refused before any write). Stable operation UUID + bounded safe metadata receipt on the NEW target, namespaced by (source, operation) INDEPENDENT of target selection, deduplicates exact repeats (`already-applied`); changed plan (public ID/expiry/policy/target/validity/confirmation), un-backed/legacy receipts, and ambiguity (lookup bounded to two matches) refused; only the inert preview block may vary; an actual post-completion source edit keeps the original repeat deduplicating. Non-default/malformed raw Responses-streaming live-burn and recognized secret shapes in kept policy strings refused explicitly. Validity: copy-source-expiry / bounded duration-from-EXECUTION-now / absolute (naive normalized to UTC). Fresh `--confirm-external-tool-fenced` required for fenced sources. Execute requires exactly one explicit one-time key channel; post-commit channel failure reports safe recovery without rollback; plaintext unrecoverable; pending delivery via `email send-pending-key`; READ COMMITTED isolation ENFORCED (any other level refused before writes). |

## Proposed for later objectives (NOT implemented)

| Field / capability | Proposed objective |
| --- | --- |
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
