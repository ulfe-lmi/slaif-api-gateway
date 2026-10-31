# GUI–CLI administrative parity: current coverage and missing GUI work

**Date:** 2026-10-30  
**Source baseline:** canonical `main` at `67604ad6970ff8486e0a9905fdb87ffd37060bd2` (merged PR #362).  
**Status:** analysis and implementation backlog only; no application behavior changed.  
**Delivery update (2026-10-31):** G01-G03 of the section 4 backlog are delivered by OAP objective 207-a (branch `oap/207-gui-key-policy`), and 207-b on the same branch/PR repaired the demonstrated privacy, same-page download, and reason-bound gaps in those surfaces; see [section 9](#9-delivery-status-objective-207-a). G04 (faithful standard-key cloning) is delivered by OAP objective 208-a (branch `oap/208-gui-key-clone`); see [section 10](#10-delivery-status-objective-208-a). 208-b on the same branch/PR qualified the demonstrated final-head CI failures with test-only changes plus removal of one unused tuple; no product behavior change. G05-G18 remain open.
**Authoring:** independent strategic-model inspection, without the coding agent or helper agents.

## 1. Findings and scope

The GUI already supports much of everyday administration. Its main deficit is the newer **configuration, review, inspection, and recovery workflows**, rather than a complete absence of record editing.

The highest-priority gaps are:

1. Preserve the CLI's provider-policy distinction between **unrestricted**, **restricted list**, and **deny-all**. The GUI currently collapses an empty selection to unrestricted.
2. Add editing of **existing keys' operational rate/window/concurrency overrides**. Creation-time fields and the existing lazy-throttling editor do not provide that operation.
3. Expose **effective policy and route-access explanation**, including inherited values and their sources.
4. Add **faithful cloning** and **reviewed batch changes**; existing bulk import creates new keys and is not a substitute.
5. Give route capabilities the CLI's **guided partial editing, preview, stale-plan checks, and complete-candidate validation**, while retaining the existing full JSON editor as an explicit advanced mode.
6. Expose **content-free request diagnostics, replay maintenance, usage aggregates, and controlled accounting recovery** through their existing backend contracts.
7. Complete the **Codex compatibility/pin migration** and **email inspection/retry** interfaces.

These are functional-parity findings, not a proposal for a browser terminal. First-admin bootstrap, secret generation, deployment migrations, and some host-file workflows have different authority boundaries. Their treatment is explicit in section 6; retaining those exceptions must not be described as literal coverage of every CLI command.

### Evidence and limitations

I inspected:

- The real Typer registration tree: **25 top-level groups and 118 leaf commands**, with no hidden leaf commands. Registration introspection did not invoke command handlers.
- The second installed console entry point, `slaif-catalog-refresh`.
- All registrations in [the admin router](../app/slaif_gateway/api/admin.py): **104 handlers, 51 GET and 53 POST**, plus the separate record-choice and branding infrastructure.
- Form fields, submitted parameters, handler/service calls, schemas, and relevant shared services. A route name or an existing service alone was not counted as a complete GUI workflow.
- The CLI reference, field-administration guide, security contract, and configuration/operations documentation.

The local checkout was on the final report commit `40a275c735de38b3961381833be5696a785920b7`; its tree `9860b5ea7e5ca7715bb6e6b5d2c1dee52543678c` was verified identical to the above `main` tree. This report is a source/registration audit, **not a new live-browser, PostgreSQL, SMTP, provider, or deployment qualification**. No coding agent was engaged and no operational command, capture, migration, reconciliation, or provider request was executed for this analysis.

The HTTP-handler and CLI-command counts are inventory counts, not a parity score. One GUI action can require several routes; one CLI command can expose many controls. Developer/test/backup scripts under `scripts/` are outside the installed application-command inventory.

## 2. What is already exposed in both interfaces

“Both” below means the ordinary operation exists in each interface; it does not promise identical flags, defaults, output formats, or concurrency behavior. GUI features require `ENABLE_ADMIN_DASHBOARD`, an authenticated admin session, and applicable feature/configuration prerequisites.

| Area | CLI surface | Existing GUI surface | Assessment |
| --- | --- | --- | --- |
| Owners and cohorts | `owners create/list/show/update`; `cohorts create/list/show/update` | List/detail/create/edit pages; owner institution association; cohort dates and descriptions | Ordinary record administration already present. CLI partial-patch semantics and GUI full forms should remain distinguishable. No new cohort–institution association is needed. |
| Institutions | `institutions create/list/show` | List/detail/create **and edit** pages | GUI is already broader for institution editing. |
| Key creation | `keys create` | `/admin/keys/create`: owner/cohort, validity, lifetime quotas, allow-lists, creation-time rates, lazy throttling, streaming margins, external-tool policy, trusted calibration and selected Codex presets | Substantial coverage; advanced policy expressiveness and provider tri-state are incomplete (G01). |
| Key inspection and lifecycle | `keys list/show/suspend/activate/revoke/extend/rotate` | Keys list/detail; suspend/activate/revoke; validity editor; confirmed, reasoned rotation with old-key status and delivery choice | Basic workflows present. A direct validity edit can achieve an extension; no separate “extend” button is intrinsically required. Improve lookup/paging and inspection (G03/G13). |
| Lifetime quotas and resets | `keys set-limits/reset-usage` | Hard-quota editor with explicit clear controls; confirmed usage/reserved-counter reset | Present. Lifetime null means unlimited. Usage reset is **not** accounting-hold or reservation reconciliation. |
| Basic request permissions | `keys policy show/update` | Read-only policy summaries and provider/model/endpoint selector on existing keys | Partial: ordinary allow-lists exist, but not the complete versioned policy-file surface, deny-all provider semantics, or safe export (G01). |
| Operational rates | `keys set-rate-limits` and creation flags | Request/token/window/concurrency fields **during creation**, configured summaries afterward | Partial: no existing-key rate-update handler/form (G02). |
| Lazy waiting | `keys set-lazy-throttling` | Existing-key wait/reject form with wait/queue bounds; warning when Redis limiting is disabled | Present. Do not rebuild it. Add effective/inherited context alongside it (G03). |
| Chat streaming live-burn | `keys set-chat-streaming-live-burn` | Existing-key enable/margin editor and summaries | Present; preserve negative/zero margins, disabled-state behavior, exact edit units, and audit. |
| External tools | `keys external-tools show/update` | Policy view/editor, reviewed capability/destination choices, call ceiling, overrun acknowledgement and confirmation | Present within the same bounded runtime support. A policy setting alone does not make unsupported hosted tools runnable. |
| Providers | `providers add/list/show/update/enable/disable` | Full create/edit forms, timeout, zero retries, credential **ENV-variable name**, status actions | Already present. Notes clearing and preparation defaults differ (G07). Provider status is not proof of backend authentication. |
| Generic-provider model onboarding | `providers discover-models/setup-models` | Discover/preview/execute, model selection, public aliases, presets, pricing, priority, streaming/tools and confirmations | Existing workflow, including a fresh probe on execution. Do not list discovery or alias mapping as wholly missing. |
| Routes | `routes add/list/show/update/enable/disable/import` | Create/edit/status/list/detail and import preview/execute; capabilities JSON textarea | Editing exists. CLI reviewed partial updates and associated validation are not mirrored by a full JSON form (G06). |
| Pricing | `pricing add/list/show/import/disable-model` | Create/edit/list/detail, per-row enable/disable, reviewed import | Broad coverage; GUI is richer for individual editing. CLI matching-model disable is a separate bulk convenience (G18). |
| FX | `fx add/list/latest` | List/detail/create/edit/import preview/execute | Broad coverage and GUI-only edits/imports. Explicit effective/latest-pair lookup remains a small parity/discoverability task (G18). |
| Calibration | `calibration summarize` | Trusted-calibration key preview with time range and multiplier | Existing summary/proposal workflow. A JSON preview download would cover CLI output-file convenience without running inference. |
| Templates | `templates create-from-calibration`; `keys create-from-template` | Calibration-to-template confirmation, template list/detail, issue key from the current revision | Existing lifecycle. No generic template editor is implied by the CLI; unlimited-quota templates remain a separate product limitation. |
| Usage | `usage export` | Filtered usage ledger/detail and bounded, confirmed CSV export | Partial: no grouped summary or live-burn aggregate page; JSON export and filter contracts also differ (G11). |
| Email | `email list/show/send-pending-key` | Delivery list/detail, secret lifecycle status, send-now and enqueue confirmations | Partial: newer inspection projection, explicit failed-retry intent/audit, and SMTP test are not fully mirrored (G12). |
| OpenAI-assisted proposals | `openai-assisted pricing-proposal/route-proposal` | Proposal forms, model/source/filter choices, returned TSV and import-preview bridge | Already present. These are proposals, not the sealed catalog-refresh pipeline. CLI ENV/path flags need not become arbitrary browser inputs. |
| Codex readiness and profile artifacts | `codex inspect/profile` | Route-level readiness/reason badges and credential-free base/profile/catalog downloads for ready registered profiles | Partial: route-specific features exist; global inspection, data-profile management and existing-key migrations are missing (G10/G16). |

### GUI capabilities that are not missing merely because they lack a matching CLI verb

The GUI additionally has institution editing, individual pricing editing/enable/disable, FX editing/import, bulk key-import preview/execute, template browsing, audit browsing/detail/CSV export, login/logout/session handling, and searchable record-choice controls. Some are compositions or GUI-only operations. They should be retained, not replaced with redundant CLI-shaped buttons.

Bulk key import is visible in the GUI; there is **no registered `slaif-gateway keys import` command** in this baseline. A service-level bulk-import capability is not evidence for an installed CLI verb.

## 3. Verified semantic differences that need attention first

### 3.1 Empty providers currently mean unrestricted in the GUI

[CLI policy controls](../app/slaif_gateway/cli/keys.py) expose `--provider-all`, `--provider-none`, and explicit provider lists. The versioned policy schema distinguishes `null` from `[]`.

By contrast, `_parse_admin_allowed_providers()` in [admin.py](../app/slaif_gateway/api/admin.py) (baseline line 11028) returns `None` both when the allow-all checkbox is set **and when the parsed selection is empty**. The existing-key policy POST also always supplies `update_allowed_providers=True`.

Therefore unchecking allow-all and leaving the selection empty does **not** express deny-all. A saved deny-all policy cannot be faithfully round-tripped through that empty selection. This is a confirmed code-path difference, not a conjecture based on labels.

**Required behavior:** explicit states for unrestricted, selected providers, and deny-all; explicit unchanged intent where partial updates are offered. A GET/display/POST round-trip must preserve each state, especially `[]`. Do not reinterpret an empty list through truthiness.

### 3.2 Existing-key rate controls are absent, despite creation fields

`create_admin_key()` accepts request/token rates, window seconds, and concurrency. Existing-key POSTs cover policy allow-lists, lazy throttling, streaming margins, validity, quotas and lifecycle, but **none accepts a rate/window/concurrency patch**. The detail page's configured summary is not an editor.

**Required behavior:** the GUI equivalent of `keys set-rate-limits`, with per-member clear/inherit controls and the existing audited `KeyService` operation. Waiting controls must stay separate from rates, lifetime quotas, and installation ceilings.

### 3.3 Routes can already be edited, but the review contract differs

The route form accepts a complete `capabilities` JSON object. `update_admin_route()` passes the submitted fields directly to `ModelRouteService.update_model_route()`.

The newer CLI `routes update` instead has dry-run/execute plans, typed partial capability leaves, deep preservation, route/provider fingerprints, fresh revalidation and the configuration orchestration in [provider_route_configuration.py](../app/slaif_gateway/services/provider_route_configuration.py).

**Required behavior:** use that same reviewed update path for the GUI. Add guided fields for context/output limits, media estimates, Chat/Responses capabilities and completion-service profile selection; keep complete replacement a distinct advanced action. A raw JSON textarea is partial functionality, not equivalent protection against overwriting concurrent or unrelated values.

### 3.4 Provider fields exist; clearing and defaults differ

The GUI already edits timeout, retries, origin, kind, credential reference and notes. However, its POST does not supply the service's `clear_notes=True` intent: clearing the textarea produces `None`, whose existing default means preserve. [ProviderConfigService](../app/slaif_gateway/services/provider_config_service.py) and the CLI distinguish clearing from preservation.

Also, `_default_provider_config_form()` sets `enabled="true"`, while CLI provider creation defaults to disabled. `_default_route_form()` sets enabled true; CLI route creation with `--capabilities-file` defaults to disabled unless explicitly enabled. Manual GUI disabling exists, but the preparation defaults do not match.

**Required behavior:** explicit clear notes; safe preparation/activation distinction and equivalent defaults for reviewed prepared configurations. Changing status should remain deliberate and auditable.

### 3.5 Email sending exists, but intent and read-side consistency differ

The GUI can send/enqueue a selected pending or failed delivery after confirmation. Its action handlers recheck the shared `EmailDeliveryService.get_key_email_delivery_sendability()`; this is important existing protection and must be retained.

The newer CLI additionally requires `--retry-failed` plus a bounded nonblank reason for an existing failed delivery, and records explicit enqueue/retry intent. The GUI has no separate failed-retry control; reasons are optional, and `enqueue_admin_email_delivery()` currently discards its `reason` after dispatch (`_ = reason`). Its detail projection is also built by the older `AdminActivityDashboardService._email_delivery_action_state` logic, whereas the CLI uses [EmailInspectionService](../app/slaif_gateway/services/email_inspection.py), including shared sendability/history facts and safe recorded failures.

**Required behavior:** align inspection, action labels, explicit failed-retry confirmation, reason validation and intent audit with the CLI. Do not describe this as “email sending missing,” or imply that the existing action-time guards are absent. Consumed/expired/sending/ambiguous secrets must never become blindly resendable. Enqueue intent, SMTP acceptance, and confirmed inbox delivery are different facts.

## 4. GUI implementation backlog

Priorities: **P0** = ordinary configuration correctness / essential CLI administration; **P1** = inspection, operational control and safe recovery; **P2** = broader operator workflow and convenience. These are proposed priorities, not execution orders.

“Schema” indicates whether the capability already has backing data/services; it is not permission to add tables opportunistically. **No** means no schema change is expected for the core capability. Durable job/review storage and new authorization policies must be assessed separately if an implementation needs them.

| ID / priority | Missing or partial GUI capability | Concrete GUI work and acceptance | Backend to reuse / schema expectation |
| --- | --- | --- | --- |
| **G01 / P0** | Complete typed key policy, safe import/export, provider tri-state | Add an advanced versioned policy editor/import and safe JSON export alongside guided controls. Support the reviewed Responses/Codex block, module binding, existing supported streaming/tool policy and lazy policy; reject unknown fields and unsupported authority. Make unrestricted/list/deny-all explicit; preserve omitted fields and null meanings. Round-trip CLI-exported policies on compatible targets without silently repinning a bound key. | `KeyService`, key policy/configuration schemas and [key_policy_configuration.py](../app/slaif_gateway/services/key_policy_configuration.py). **No** new policy columns. |
| **G02 / P0** | Operational rate updates for existing keys | Add request count, token count, selected window, concurrency and per-member clear/inherit controls to key detail. Test one request per 10 seconds, concurrency one, valid zero/omission rules where applicable, and reset-to-deployment behavior. Preserve expiry, material, lifetime quotas and other policies. | Existing key rate-update operation; same input schemas and audit. **No**. |
| **G03 / P0** | Effective policy and route-access explanation | Add “Configured / Effective / Source” and “Explain model access” panels. Explain key/deployment/default sources, enabled route/model/provider intersections, module/profile prerequisites and blockers, with explicit configuration-only labeling. Show inherited rates separately from unlimited lifetime quotas. The existing Redis-disabled warning and route Codex badge are useful but incomplete. | [key_policy_inspection.py](../app/slaif_gateway/services/key_policy_inspection.py) and CLI inspection adapters. **No**. |
| **G04 / P0** | Faithful standard-key cloning | Add Clone on key detail: source, existing target owner/cohort, explicit validity mode, canonical configuration comparison, preview then confirm. Generate independent material/IDs, zero usage and separate replay ownership. Preserve unlimited totals and inherited overrides. Revalidate source fingerprints; preserve idempotent operation identity and post-commit delivery recovery. Display a new secret only through an explicit approved one-time channel. | [KeyCloneService](../app/slaif_gateway/services/key_clone_service.py), strict clone plan/result schemas. **No** new key fields; a bounded browser review-state adapter is needed. |
| **G05 / P0** | Reviewed changes to existing key sets | Add batch plan/review/apply for one cohort or an explicit UUID set, matching CLI scope. Preview exact selected/excluded IDs and counts, per-key changes and reasons; default active keys; reject changed membership/configuration. Apply atomically with per-key audit. If adding “all filtered results,” resolve that scope server-side within service bounds; never mean just the current displayed page. Editing members does not create defaults for future cohort keys. | [KeyBatchService](../app/slaif_gateway/services/key_batch_service.py), strict reviewed-plan schema. **No** new policy columns; review-state adapter required. |
| **G06 / P0** | Reviewed route-capability changes | Guided partial fields plus explicit complete-JSON/file replacement mode; preserve deep siblings, IDs, pricing/keys/client settings and unrelated routes. Preview before/after and exact route/provider identity; revalidate/lock at apply and reject stale plans. Reuse the CLI's operator ceilings, configured profile directory, merged-candidate validation and file/JSON bounds. Explain gateway context/output ceilings versus physical model and client context. | Existing route configuration orchestration, `ModelRouteService`, server/client registries. **No**. This is not a new routing engine. |
| **G07 / P0** | Provider preparation and explicit clearing | Keep the existing provider editor; add explicit notes clearing and preservation intent. Align disabled preparation with CLI behavior and clearly separate activation. Preserve retry `0`, HTTP confirmation, audit and credential-reference-only handling. Offer supported server-profile inspection/help without pretending that enabled metadata proves backend auth. | `ProviderConfigService`; existing generic discovery/setup services. **No**. |
| **G08 / P1** | Content-free request diagnostics | Add status/retention/store-availability view, request-ID lookup with explicit gateway/client namespaces, ambiguity/disambiguation, not-found/unavailable states, and controlled bounded cleanup. Link suitable inference request IDs from usage/error views. Show wire HTTP status separately from stream failure and identity only where authenticated. Do not assume every admin error reference ID is a retained inference diagnostic. Never infer historical facts from nearby timestamps or automatically enable content capture. | [RequestDiagnosticsService](../app/slaif_gateway/services/request_diagnostics.py), existing `request_diagnostics` data. **No**: migration `0026` already supplies the table. |
| **G09 / P1** | Replay-reference inspection and extension | Key/cohort/active-key scope, time bounds, safe counts/ranges/exclusions, selected TTL, preview then confirm, explicit include-expired. Preserve original creation time, same-key ownership, HMAC eligibility, finalized-ledger linkage and all non-expiry fields. Monotonic extension, stale-scope refusal, idempotency and audit; no shortening, raw replay IDs/digests, content recovery or ownership transfer. | [codex_replay_maintenance.py](../app/slaif_gateway/services/codex_replay_maintenance.py). **No** new replay schema. |
| **G10 / P1** | Codex policy-data inspection and existing-key migration | Add current validated compatibility profile/version/digest and per-key module/profile binding inspection. Mirror exact supported module upgrade/rollback and profile migration with source/target identity, preview, explicit confirmation, reason and audited apply. Offer preset inspection/export and ready profile artifacts using the existing registries. Current creation checkboxes and route downloads are not existing-key migrations. | Existing functions behind [cli/codex.py](../app/slaif_gateway/cli/codex.py). **No** new binding schema. Host-file deployment/activation remains separately controlled. |
| **G11 / P1** | Grouped usage and live-burn reporting | Add summaries by provider, model, provider+model, owner, cohort, key and day, plus aggregate live-burn outcomes/margins/estimate provenance. Reuse authoritative usage services and bounds; ledger pages alone are not summaries. Offer safe JSON export alongside CSV where CLI parity requires it, and state any deliberate GUI export caps/filter differences. No content/reasoning or separate competing accounting totals. | `UsageReportService` and existing live-burn telemetry. **No**. |
| **G12 / P1** | Complete delivery inspection, explicit retry and SMTP test | Reuse the CLI inspection projection for safe status/history/failure provenance and complete bounded filters. Make failed retry a distinct action with required reason, matched target and shared sendability/history preflight; audit enqueue/retry intent. Retain existing send-now/enqueue. Add explicit safe test-email action without keys, rate/budget bounds appropriate to the deployment, and honest queued/sent/ambiguous labels. | [EmailInspectionService](../app/slaif_gateway/services/email_inspection.py), `EmailDeliveryService`, existing email test path. **No**. |
| **G13 / P1** | Complete list navigation and safe lookup | Existing list handlers accept offsets, but inspected templates have Rows selectors without visible previous/next navigation or CLI-style `has_more`/`next_offset` metadata. Add usable stable pagination, retained filters, honest “more results” indication and safe UUID/public-ID/email lookup. Preserve OR within a field / AND across fields and latest-100 picker search beyond that batch. CLI key/email pages already expose explicit paging metadata; not every CLI list is paged. | Existing dashboard/lookup services plus bounded page-result metadata where needed. **No** schema expected. Never fetch the whole database into the browser. |
| **G14 / P1 views, P2 mutations** | Quota fences, holds and reservation/finalization recovery | Add an Operations/Accounting area for all four CLI candidate lists and dry-run reconciliation of individual/bounded groups. Require authoritative stored evidence, explicit action/reason/confirmation and appropriate privilege for execution. Keep unknown cost blocked, external-tool concurrency fenced, and ledger/reservation/key balances authoritative and consistent. A usage-reset button must not be presented as equivalent recovery. | Existing `ExternalToolFenceService`, `ExternalToolAccountingHoldService`, `ReservationReconciliationService` used by [cli/quota.py](../app/slaif_gateway/cli/quota.py). **No** new accounting schema expected; authorization/workflow design is material. |
| **G15 / P2** | Official catalog proposals and full sealed refresh workflow | Add a controlled UI for supported provider-catalog packages and catalog collect/review/verify/export-baseline/apply/status. Preserve fixed official sources, safe destinations/HTTPS, secret isolation, seals, baseline/staleness checks, atomic apply and truthful status. Existing standalone `REVIEW.html` is already a visual report, but not a web-admin controller; existing import and OpenAI-assisted pages are separate workflows. Long-running work needs bounded execution/status/cancellation using existing facilities where suitable; do not add a generic job system or shell console by default. | Existing catalog proposal/refresh services. Some orchestration is CLI/file-bound: **not merely a template task**. No intrinsic catalog schema migration; server-owned artifacts/job-state integration needs design and review. |
| **G16 / P2** | Safe configuration, profile and version inspection | Add an authenticated read-only deployment/compatibility status page: package version, reviewed non-secret configuration values/source/restart scope, registered upstream profile data/selectors and Codex data identities. Reuse the 45-setting allowlist, not an environment dump. Label API-process versus CLI-process scope; do not claim observation of every worker or live proxy limit. No generic settings writer or arbitrary server path browser. | [configuration_inspection.py](../app/slaif_gateway/services/configuration_inspection.py), existing profile loaders/registries. **No** database schema expected. File and restart operations remain deployment controls. |
| **G17 / P2, privileged** | Post-bootstrap admin accounts | Add authenticated admin list/create/password-reset workflows corresponding to the three CLI commands, after deciding explicit privilege/self-reset rules and session consequences. Resolve the actor from the session, never a browser-supplied `--actor-admin-id`. First-admin creation and break-glass access still need CLI/offline support. Do not invent user/team/tenant administration just because architecture mentions it. | Existing `AdminService` and admin-user schema; security/session adapters may be needed. **No** schema intrinsically required for these three actions. |
| **G18 / P2** | Remaining small catalog-operation differences | Add reviewed matching-model pricing disable if bulk equivalence to `pricing disable-model` is required; current GUI can disable rows individually. Add a clear latest/effective FX-pair lookup using the same service as `fx latest`, rather than assuming a visible sorted list identifies the selected rate. Show exact affected scope and audit actions. | Existing pricing/FX services. **No**. |

### Suggested sequence

1. **Correct semantics and make state understandable:** G01–G03 and G07. Provider deny-all and inherited-rate behavior should be settled before adding faster cloning/batch workflows.
2. **Complete routine configuration workflows:** G04–G06. Reuse canonical configuration and reviewed-plan machinery instead of a second GUI implementation.
3. **Make investigation and reporting self-sufficient:** G08, G10–G13 and G16. Share safe projections with the CLI.
4. **Add controlled maintenance:** G09 and G14, with read-only views before mutations and the existing database/concurrency evidence retained.
5. **Broader operator integration:** G15, G17 and G18 after their filesystem, privilege and execution boundaries are explicit.

This sequence is a recommendation. It does not activate an OAP order, authorize production actions, or require coding-agent involvement in this analysis.

## 5. Acceptance criteria for GUI equivalence

For each implemented gap, test the **same operation and semantics**, not just a button or route:

| Requirement | Proof required |
| --- | --- |
| Existing functionality retained | Preserve working record forms, key lifecycle/quotas, lazy waiting, external tools, discovery, imports, calibration/templates, exports, audit and credential-free profile downloads. |
| Policy fidelity | Create/show/export/import/update round-trips for supported fields; `None` versus `[]`; zero versus absence; inherited rates versus unlimited totals; unknown/conflicting fields denied. Existing-key binding changes use the reviewed migration path. |
| Clone fidelity | Standard student/beta/chat configurations compare canonically; source unchanged; new IDs/material/zero usage/separate replay ownership; exact repeat does not duplicate keys after delivery failure. Unsupported calibration/template behavior remains refused. |
| Batch correctness | Exact reviewed scope, exclusions/counts, complete bounded selection across pages, membership/stale-plan refusal, atomic apply/rollback and expected audit. No unnoticed first-page-only operation. |
| Route/provider correctness | Partial updates preserve deep siblings and unrelated rows; complete replacement is explicit; source/provider fingerprints checked on apply; correct operator profile/ceiling validation; retry zero, explicit clear and disabled preparation retained. |
| Shared authority | GUI controllers call existing schemas/services, not shell CLI wrappers, direct metadata edits or raw SQL. Server-authorized session actor, CSRF, explicit reason/confirmation, secret-safe error handling and consistent transaction/audit semantics. |
| Diagnostics truth | Actual pre-admission and HTTP-200 stream failures resolvable by retained IDs; unauthenticated failures unattributed; ambiguity/not-found/unavailable honest; no requests/prompts/arguments/replay IDs/credentials exposed. |
| Mail safety | Pending/sent/failed/expired/sending/ambiguous and same-secret history; explicit failed retry and reason; consumed or ambiguous delivery not blindly retried; enqueue intent versus SMTP acceptance versus inbox delivery clearly separated. |
| Replay/accounting safety | Same-key/ledger/HMAC eligibility, original-age TTL and monotonicity; explicit expired restoration, no shortening/transfer. Recovery preserves holds/fences and authoritative PostgreSQL totals; no “unblock” shortcut through reset counters. |
| Browser usability | Real authenticated browser workflows, keyboard use, searchable known-record controls, stable filter-preserving paging and exact raw numeric sorting. Keep the shared numeric/M-token display with exact counts; editable values and downloaded machine formats retain exact raw units. |
| Evidence and bounds | Scoped unit/service/PostgreSQL/browser coverage appropriate to each changed boundary; reuse unchanged accepted concurrency/privacy/accounting evidence. New preview state and background work are bounded and owned. No need for real provider/SMTP credentials in the normal test suite. |

Most G01–G14 controls are backed by existing data/services. A GUI-only limitation should not automatically produce a database migration. Conversely, catalogue run custody, long-running job state or new account-security rules must not be labelled “frontend only” without examining their actual backend needs.

## 6. Explicit operator-only or policy-restricted differences

These remain real CLI–GUI differences. The recommendation is to retain or specially review them, not to hide them from the parity assessment.

| CLI capability | Current GUI | Recommended treatment |
| --- | --- | --- |
| `request-capture arm/status/stop/cleanup/inspect` | No admin control/view | **Policy-restricted.** [The current security contract](security-model.md) explicitly says operator-owned local files, no admin UI and no remote export. A browser controls page would need a deliberate contract/security decision; serving full captured bodies would widen the existing content-access boundary. Do not bundle that into ordinary parity work. Content-free diagnostics (G08) are the normal GUI investigation path. |
| `db check-config/show-url/current/upgrade` | No matching page/action | Read-only redacted configuration/migration status may be useful in G16. Keep migration execution in the controlled deployment/backup/runbook workflow; no arbitrary DB URL input or SQL console. An unavailable/misconfigured API cannot repair its own bootstrap solely through its GUI. |
| `secrets generate hmac/admin-session/one-time`; `secrets validate-env` | No secret-generation editor | Keep secret values and host-file writes in operator tooling. GUI may expose reviewed configured/missing status, not secret material or arbitrary environment access. First-install secrets, rotation, mounts and process recreation remain controlled deployment operations. |
| `admin create/reset-password` for first install/break-glass | Login requires an existing working admin/runtime | Preserve offline/bootstrap support even after G17. Browser parity for authenticated routine account administration must not remove the recovery path. |
| `bootstrap openai-completions-catalog` | Can compose record creation/imports, but no exact bootstrap action | Keep the documented first-install command or add a separately reviewed onboarding wizard using the same idempotent service. Never confuse it with collecting current upstream prices or making an inference call. |
| Host paths, output-file overwrite flags, shell completion, `--verbose`/`--log-level`, research executable/seal-key choices | Not browser form controls | Translate safe outputs into downloads/server-owned artifacts and reviewed status. Keep executable paths, credentials, secret files and environment changes operator-controlled. CLI verbosity is process-local; a GUI log-level toggle would be a different global/runtime feature. |
| Arbitrary operator-supplied server/client profile files | GUI shows selected registered readiness/artifacts | Add validated identity/selector inspection where useful (G10/G16). File deployment and activation must follow the current operator contract; no executable plugin imports or arbitrary path editor. |

A key-inclusive Codex installer/profile bundle is **not** supplied by the existing credential-free `codex profile` command or route-artifact endpoint. It is a separate feature, not evidence of an unimplemented CLI-equivalent download. If pursued under separate authorization, it can use a new key only during an approved creation/rotation secret window; it cannot recover an already-issued plaintext key.

Also outside a CLI-parity claim: unlimited-quota templates, unrestricted future Codex compatibility, arbitrary metadata/SQL editing, multi-tenant/SCIM provisioning, provider secret recovery, and declaring SMTP acceptance to be confirmed inbox delivery. They are not registered CLI capabilities in this baseline.

**Completion must be described honestly:** ordinary administrative parity can be achieved while documented operator-only exceptions remain. Literal equivalence to every installed CLI operation would require explicit decisions on those exceptions; this document does not silently authorize browser execution of them.

## 7. Complete registered CLI inventory

Every row below is drawn from the actual Typer/Click registration tree, not copied from potentially stale prose. Prefix each listed leaf with **`slaif-gateway <group>`**; nested names such as `policy effective` retain their spaces. The root `version` command is listed separately. Generated shell-completion/help options are not counted as leaf commands.

| Group | Leaf count | Registered leaf commands |
| --- | ---: | --- |
| Root | 1 | `slaif-gateway version` |
| `admin` | 3 | `create`; `list`; `reset-password` |
| `bootstrap` | 1 | `openai-completions-catalog` |
| `calibration` | 1 | `summarize` |
| `catalog-refresh` | 6 | `apply`; `collect`; `export-baseline`; `review`; `status`; `verify` |
| `codex` | 11 | `export-preset`; `inspect`; `inspect-profile-file`; `migrate-key-profile`; `presets`; `profile`; `replay extend`; `replay inspect`; `rollback-key-module`; `show-profile`; `upgrade-key-module` |
| `cohorts` | 4 | `create`; `list`; `show`; `update` |
| `config` | 1 | `show` |
| `db` | 4 | `check-config`; `current`; `show-url`; `upgrade` |
| `diagnostics` | 3 | `cleanup`; `request show`; `status` |
| `email` | 4 | `list`; `send-pending-key`; `show`; `test` |
| `fx` | 3 | `add`; `latest`; `list` |
| `institutions` | 3 | `create`; `list`; `show` |
| `keys` | 24 | `activate`; `batch apply`; `batch plan`; `clone`; `create`; `create-from-template`; `extend`; `external-tools show`; `external-tools update`; `list`; `policy effective`; `policy explain-route`; `policy export`; `policy show`; `policy update`; `reset-usage`; `revoke`; `rotate`; `set-chat-streaming-live-burn`; `set-lazy-throttling`; `set-limits`; `set-rate-limits`; `show`; `suspend` |
| `openai-assisted` | 2 | `pricing-proposal`; `route-proposal` |
| `owners` | 4 | `create`; `list`; `show`; `update` |
| `pricing` | 5 | `add`; `disable-model`; `import`; `list`; `show` |
| `provider-catalog` | 1 | `propose` |
| `providers` | 8 | `add`; `disable`; `discover-models`; `enable`; `list`; `setup-models`; `show`; `update` |
| `quota` | 8 | `list-expired-reservations`; `list-external-tool-fences`; `list-external-tool-holds`; `list-provider-completed-recovery`; `reconcile-expired-reservations`; `reconcile-external-tool-hold`; `reconcile-provider-completed`; `reconcile-reservation` |
| `request-capture` | 5 | `arm`; `cleanup`; `inspect`; `status`; `stop` |
| `routes` | 7 | `add`; `disable`; `enable`; `import`; `list`; `show`; `update` |
| `secrets` | 4 | `generate admin-session`; `generate hmac`; `generate one-time`; `validate-env` |
| `templates` | 1 | `create-from-calibration` |
| `upstream-llm` | 1 | `profiles` |
| `usage` | 3 | `export`; `live-burn-summary`; `summarize` |
| **Total** | **118** | **25 groups plus the root version command** |

### Second installed entry point

`slaif-catalog-refresh` is installed separately by [pyproject.toml](../pyproject.toml), implemented in [catalog_refresh_admin.py](../app/slaif_gateway/cli/catalog_refresh_admin.py). It wraps the read-only collect/review pipeline with explicit `--mode bootstrap|refresh` and a bounded GNU `timeout` watchdog. It does not automatically apply changes, retry indefinitely, or provide a web server. Its artifact/status behavior belongs in G15; it is not a second catalog backend to reproduce.

## 8. Source map for implementation

Use the baseline above when checking these findings; future source changes may resolve individual gaps.

| Evidence | Main sources |
| --- | --- |
| Installed commands and registration | [Entry points](../pyproject.toml); [CLI root](../app/slaif_gateway/cli/main.py); `app/slaif_gateway/cli/`; nested batch/replay commands in [key_batch.py](../app/slaif_gateway/cli/key_batch.py) and [codex_replay.py](../app/slaif_gateway/cli/codex_replay.py) |
| Actual GUI operations and submitted fields | [Admin handlers](../app/slaif_gateway/api/admin.py); [shared layout](../app/slaif_gateway/web/templates/base.html) and [key detail template](../app/slaif_gateway/web/templates/keys/detail.html); [API application/router registration](../app/slaif_gateway/main.py) |
| Existing CLI scope and operator usage | [CLI reference](cli-reference.md) and [field-administration guide](cli-field-administration.md); [Previously identified CLI gaps](../MISSING_CLI_FUNCTIONALITY.md) |
| Security and capture access boundary | [Security model](security-model.md) |
| Shared policy/route configuration and inspection | [Key configuration](../app/slaif_gateway/services/key_policy_configuration.py); [effective policy](../app/slaif_gateway/services/key_policy_inspection.py); [provider/route configuration](../app/slaif_gateway/services/provider_route_configuration.py) |
| Safe operational inspection | [Request diagnostics](../app/slaif_gateway/services/request_diagnostics.py); [email inspection](../app/slaif_gateway/services/email_inspection.py); [configuration inspection](../app/slaif_gateway/services/configuration_inspection.py); [replay maintenance](../app/slaif_gateway/services/codex_replay_maintenance.py) |

Implementation should update this file's status against actual delivered GUI behavior. Do not mark an item complete from the existence of a backend service, a disabled button, or a successful CLI test alone.


## 9. Delivery status (objective 207-a)

Added 2026-10-31 as the delivery update required at the end of section 8
(207-b repair round appended the same day). The historical findings above
are preserved as written at the baseline; this section records what 207-a
delivered, what 207-b repaired on the same PR, and what remains open.

### Delivered by 207-a (G01-G03)

- **G01 - provider tri-state and advanced versioned configuration.** Key
  creation and existing-key policy edits now express exactly one of:
  allow-all (unrestricted, stored `null`), an explicit provider allow-list
  (stored list, disabled or older stored providers preserved on save), or
  deny-all (stored `[]`, explicit checkbox). A POST with neither mode
  checked and an empty selection fails closed with a fixed error; an empty
  selection never grants unrestricted access. The guided create/detail
  controls keep working; the create page additionally offers an explicit
  policy source choice (guided fields, or one advanced version-1
  configuration document using the SAME strict parser, bounds, and
  canonical semantics as the CLI, including exact Decimal handling and
  unknown/duplicate-field denial). Existing keys get a safe JSON download
  (allowlisted projection, `attachment` with private/no-store headers) and
  a confirmation-gated, reason-required partial update whose omitted fields
  preserve state and whose rejected documents are never redisplayed.
  Trusted-calibration keys remain incompatible with deny-all, and existing
  bound client-module changes remain blocked for the reviewed migration
  path.
- **G02 - existing-key operational rate editor.** The key detail page adds
  a per-member editor (requests per window, tokens per window, concurrency,
  window seconds) with explicit leave-unchanged / set / clear-to-deployment
  actions, the shared positive-integer law (zero is not a value), refusal of
  no-op submissions, the audited `KeyService` rate-limit operation, and a
  configured/source/effective readout in the inspection section. One
  request per 10 seconds with concurrency one is a tested case. Usage,
  reservations, identities, validity, and key material are untouched by a
  rate edit.
- **G03 - effective-policy inspection and explain model access.** The key
  detail page renders the shared `build_key_policy_inspection` projection
  (provider state, endpoints, models, per-rate-member configured/effective/
  source, lazy throttling, lifetime quotas, Responses profile state, and
  the Redis-disabled caveat) and adds an authenticated, bounded, read-only
  "Explain Model Access" form that reuses the exact shared
  `explain_model_route_access` projection as the CLI
  (`resolved` / `blocked` / `not-evaluated` verdicts, blockers, bounds, and
  explicit configuration-only labeling). Inspections never write, reset
  counters, contact upstreams, or authenticate as the key.
- **Ergonomics (order requirement 5).** The touched key forms carry
  field-specific help beside each control via `aria-describedby`
  (validity, limits, provider modes, policy source, rate units,
  configuration semantics), grouped advanced sections, and the existing
  card/typography patterns; no new tables were introduced, so the section 6
  table law is unaffected.

Evidence lives in the objective 207-a report and PR (focused unit/integration
JUnit counts, owned-PostgreSQL facts, real-Chromium workflow facts, and
screenshots under `/tmp/slaif207/`), plus
[docs/verification/gui-cli-parity.md](verification/gui-cli-parity.md) and the
new section in [docs/admin-usability.md](admin-usability.md). The 207-b
repair round appends its evidence to the same verification file and
records the GUI-side reason bound and the non-rotating configuration
download.

### Repaired by 207-b (same PR, 2026-10-31)

The 207-b order (correctly formatted, same PR363) repaired three
demonstrated gaps in the 207-a surfaces without new scope:

- **Credential privacy at the new/touched seams.** Scoped by value
  kind (recognized through the existing redaction rules, including
  configured accepted key prefixes): credential-shaped MODEL
  identifiers in the policy inputs are refused with a fixed safe
  message before the shared validators; credential-shaped values in
  reasons and other retained fields are masked in the re-rendered
  form, flash errors, audit notes, and failure logs (a valid change
  with a credential-shaped reason still succeeds, stored masked).
  The explain action's shared classifier is unchanged (original
  input); only its retained display is masked. Useful ordinary
  values are preserved for correction.
- **Same-page configuration download.** The attachment authenticates
  through a non-rotating read-only session context (the same real
  session checks), so the detail page's own form token stays valid:
  the browser-qualified flow is detail page -> download -> edit
  through the SAME still-displayed form.
- **Reason bound on the new/touched mutations.** Nonblank and at most
  512 Unicode characters, enforced server-side before mutation or
  audit with a fixed safe refusal, with matching `maxlength` and
  visible help. This is a GUI-side seam bound: the schema constant
  existed but was previously unused, and the unchanged CLI is not
  claimed to enforce it.

The 207-b record (same
[gui-cli-parity.md](verification/gui-cli-parity.md) file) corrects the
earlier claims that reasons were bounded and that all canaries were
covered.

### Still open (G05-G18)

Nothing in 207-a, 207-b, or 208-a claims G05 (batch), G06
(route-capability
review), G07 (provider preparation/clearing), G08 (diagnostics), G09 (replay
inspection), G10 (Codex migration), G11 (usage reporting), G12 (email
inspection), G13 (list navigation), G14 (accounting recovery), G15 (catalog
workflows), G16 (configuration inspection page), G17 (admin accounts), or
G18 (small catalog operations) is complete. The section 3.1-3.5 findings for
those areas remain as documented at the baseline. G04 is delivered by
208-a; see section 10 below.

## 10. Delivery status (objective 208-a)

Added 2026-10-31 as the delivery update for G04 (faithful standard-key
cloning) on branch `oap/208-gui-key-clone` (its own PR). The historical
findings above are preserved as written at the baseline; this section
records what 208-a delivered and what remains open.

### Delivered by 208-a (G04)

- **Clone entry on key detail.** The existing key-detail page gains a
  bounded "Clone This Key" action panel (clone link plus a "Check a
  clone outcome" recovery link). All prior detail sections are unchanged.
- **Guided clone form.** `/admin/keys/{id}/clone` shows the source public
  identity and a read-only core eligibility probe (the core decides; an
  unsupported source is refused honestly and its policy is never reset or
  weakened), the existing latest-100 record pickers for the target owner
  (required) and cohort (optional; blank = no cohort) with plain-text
  no-JS fallbacks, and exactly three validity modes: copy the source
  expiry, a positive whole duration from execution time (seconds/
  minutes/hours/days, service-bounded), or an explicit UTC window.
  Nothing is created on this page.
- **Review before confirm.** POSTing the form calls the core
  `KeyCloneService.build_plan` (no GUI policy engine; no mutation, no
  policy audit) and renders a readable summary of the canonical policy
  (providers/models/endpoints, limits, window-aware rate counts, lazy
  throttling mode, live-burn, external-tool, Responses settings) plus the
  reviewed target, validity, one-time delivery channel, and operation
  identity. The full non-secret plan/policy JSON remains available as
  optional detail. The review page never shows key material.
- **Signed review-intent binding.** The review state is an HMAC-SHA256
  token over the strict plan plus the acting admin user, session, a short
  expiry, and the delivery mode. Apply verifies format (including a
  controlled non-ASCII/tampered-digest refusal before comparison), the
  constant-time HMAC, purpose/actor/session, expiry, and re-parses the
  embedded strict plan before any mutation; the plan's source must match
  the URL path. A mutable apply field can never change the reviewed
  delivery channel. Bounded encoded/decoded sizes are enforced at build
  and verify.
- **Apply with confirmation and reason.** Apply requires the explicit
  confirmation checkbox, a bounded nonblank audit reason (masked through
  the existing redaction seam before storage), the session-derived actor,
  and CSRF. A source whose configured policy includes fenced
  external-tool mode requires a fresh fenced checkbox at apply. The core
  `execute_plan` runs the SAME reviewed plan in the caller-owned
  transaction: locked source revalidation, dedup first, fresh
  fingerprint/policy, independent material and IDs, zero usage and
  reservations, its own replay ownership, and the committed receipt.
- **One-time delivery channel.** The channel (none / pending /
  send-now / enqueue) is bound at review and revalidated against the
  existing readiness rules. The generated key is displayed at most once
  (none/pending), in a private no-store result page; send-now/enqueue
  dispatch only AFTER commit, and a post-commit channel failure renders
  "Created With Delivery Failure" with the stable target/secret/delivery
  IDs and an explicit "a second clone is NOT needed" recovery path.
  Already-applied repeats never decrypt or redisplay the plaintext.
- **Read-only outcome recovery.** `/admin/keys/{id}/clone/receipts?
  operation=` inspects the committed receipt by source + operation
  (created / not-found / ambiguous / malformed, each a safe fixed state),
  works after the review state expired or the result page was lost, and
  never creates or assumes anything. The operation input is redacted
  before redisplay; ordinary misspelled UUIDs keep their useful fixed
  error.
- **Window-aware rate readout.** The new review readout labels copied
  rate counts by the configured window the runtime meters in (e.g. "per
  10s window"); minute and omitted windows keep the existing per-minute
  grammar. No runtime/accounting or global formatter change.

### Bounded paths (208-a)

`app/slaif_gateway/api/admin_key_clone.py` (focused router),
`app/slaif_gateway/api/admin_review_intent.py` (purpose-bound review
token), the read-only `find_clone_receipt` projection plus
`KeyCloneReceiptMalformedError` in
`app/slaif_gateway/services/key_clone_service.py`, the router include in
`app/slaif_gateway/main.py`, four `keys/clone_*.html` templates, the
detail-page action panel, `web/static/js/key-clone.js` (progressive
validity-mode enablement only - never value conversion), and the asset
registration. No schema, migration, model, CLI, worker, or runtime
accounting change; the core clone service's existing concurrency,
rollback, dedup, and replay laws are reused and re-qualified, not
re-implemented.

### Focused evidence (208-a)

- Fake-persistence ASGI/Jinja unit suite (47 cases): intent round-trip,
  expiry/actor/session/source/delivery binding, tamper and malformed
  formats (including the non-ASCII digest refusal), builder/verify size
  bounds with the full core-supported scope still building, controlled
  404 for a vanished source on form and re-render, ineligible-source
  refusals, one-time plaintext exactly once with no-store headers,
  already-applied without redisplay, post-commit delivery failure with
  stable IDs, and read-only recovery including malformed-receipt refusal.
- Owned-PostgreSQL integration suite (4 cases on the qualified
  loopback/tmpfs fixture): faithful canonical clone to an ALTERNATE
  owner + cohort (target controls proven persisted), exact 3601s window,
  zero usage/reservations, independent material, receipt identity equal
  to the reviewed operation, source/unrelated isolation, exact-repeat
  already-applied, stale (post-review source change) and tampered-token
  refusals with no-write snapshot proof, committed clone with a
  post-commit SMTP failure (synthetic) and its recovery, suspended-source
  form/review states, and the send-now precondition refusal. The 208
  seed is get-or-create on the DB-unique provider slugs so it coexists
  with the 207 module on one session database (verified together:
  14/14).
- Real Chromium on the owned fixture (3 cases): detail entry + guided
  form (record pickers driven, 3601s duration), review with the window-
  aware readout, keyboard-only apply (focus/Space/Enter), one-time result
  asserted from HTML only (the plaintext page is never screenshotted),
  persisted-target oracles, exact-repeat via the same still-valid token,
  recovery views, no-JS typed-UUID fallback through to the persisted
  target, and a narrow-viewport review capture.

### CI qualification (208-b, same PR)

208-b repaired the two demonstrated 208-a final-head CI failures (the
unit structural-guard line budget and the 207/208 provider-slug seed
collision in the shared session database) with test-only changes plus
removal of the unused `_CLONE_FORM_FIELDS` tuple; no GUI behavior, product
law, or schema change. The full chronology and focused evidence are in
the 208-b section of `docs/verification/gui-cli-parity.md`.

### Still open

G05-G18 remain open as documented in section 9. Nothing in 208-a touches
batch editing, route-capability review, provider preparation,
diagnostics, replay inspection, Codex migration, usage reporting, email
inspection, list navigation, accounting recovery, catalog workflows, the
configuration inspection page, admin accounts, or small catalog
operations.
