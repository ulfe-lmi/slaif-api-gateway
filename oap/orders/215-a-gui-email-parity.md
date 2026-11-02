# OAP Work Order — 215-a

PR mode: CREATE_NEW_PR

## Objective and current-state preflight

Deliver G12 from docs/MISSING_GUI_FUNCTIONALITY.md: shared safe email
inspection, explicit existing-delivery failed retry, attributable enqueue
intent, and a bounded SMTP test. Preserve working creation/rotation delivery,
the richer GUI list filters and the 214 pagination/formatting/accessibility.
The approved whole-GUI goal continues through216–219 after this objective.

Verified 2026-11-01T20:47:45.558612+00:00: preceding214 PR370 merged2026-11-01T20:27:27Z, accepted
SELF310442eb4af8adedaf5552ddee2bbead4d9b402e, actual main279f71a89fa6d41f34587ca300f1c6aaed815731 treebaad88bcc91e471ceb8beb50648a2a8f9cc7825b with all3workflows/all9checks
successful (CI41346942146,CodeQL41346942100,Quality41346942228; lastmainjob20:44:27Z,rootverified20:44:59.604437Z); actualmaintreeequalsacceptedSELF; final-head review/material/CI gates and terminal timing recorded BEFORE this activation.

ClosedROOT59505mainCI/85174finalBPRCI/25257merge/33490response/18503oldCI/9574oldresponsemustNEVER be repolled or214-a/bresignaled. Rootcanonicalhelpercreates sole215response reader AFTER sharedactivation.


Preactivation active214-b; exact prior order/report214-b order7159bytes SHAd6d9fd85dcbf008f1e060995b1e01ea7f676473a112249ef1845ad306dd6fbc0;report7227bytes SHA9548416c16fd13e21c61d70409dea963ac3c340a4ec43ab97cff260ad1447858; old214-aorder/reportunchanged andremoteverified in214review. Fresh open
PRsonlyunrelatedDependabot319; no215local/remotebranch or215PR, rules/protectionactive23580289(deletion/nonff,no bypass),disabled19441572/15649613; finalCI/material/review gates mandatory, releasesonlyv0.1.0-rc.1published2026-05-01T21:33:27Z; nonewrelease/tag/deploy, preserved local
statetrackedclean ataccepted214-bSELF310442eb; onlyprotecteduntrackedCODEX-SESSIONS.md7881bytesSHA5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda/codex.sh492bytesSHA66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247/uv.lock405520bytesSHAd3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6; ignored.env/.codex/catalogs/worktreespreserved, sole canonical coding waiter/FIFO types/inodesonecanonicalbashwait-control-and-wake.shPID3131927,cwd/home/janezp/codex-supervision/slaif-api-gateway,TMUX_PANE=%9; truecontrolinode4501469/response4501470; SAMECLI3308462unchangedhumanprofile/model/effort,newnativeconversation20:35:34 inCURRENTworktree,neutralstartupread/onewaiterverified/no helper.

Create ONE PR from that verified main on oap/215-gui-email-parity.
PR title: Complete safe email inspection, retry and SMTP test controls.
Coding agent owns Git; strategic owns immutable order/active bytes. Existing
right tmux CLI only; no helper agents/nested Codex/model/profile/effort change.
No reset/clean/stash/forcepush or unrelated worktree/catalog/config changes.
Read current governance, security/email/CLI/usability contracts and the inert
proposal /home/janezp/codex-supervision/slaif-api-gateway/workorders/215-a-gui-email-parity-PROPOSAL.md
plus GUI-PARITY-ROUND-PLAN.md beside it. Refresh actual214 bridges, not another
whole-codebase inventory. No production/real-recipient/provider calls, release,
tag, deployment or schema changes are authorized.

## Shared inspection and preserved list semantics

Reuse services/email_inspection.py EmailInspectionService and its strict
schemas/email_inspection.py projections. Existing list_deliveries uses exact
single-value AND filters and limit1..100; show_delivery resolves the exact
UUID, calls the injected EmailDeliveryService sendability provider, and reads
ONLY the latest exact-delivery error audit with finite known codes. Unknown,
missing or unsafe recorded code is unavailable, never inferred from prose or
an older event. Inspection never decrypts/renders/consumes/enqueues/sends or
writes an audit. Show store-unavailable separately from missing delivery.

The legacy GUI list has repeatable OR-within/AND-across filters, owner-email
substring scope, one-time-reference filtering and valid custom1..200 limits.
Retain those semantics, selected chips, latest100+older search, deterministic
ordering, real cap+1 has_more, no-JS links and page ordinals after sorting.
Do NOT replace its scope with CLI exact-email/single-value/100-row behavior.
Use the smallest explicit shared admin-query/projection bridge in the email
inspection service with the EXISTING GUI repository query and already-loaded
relationships; keep CLI defaults/output unchanged. Preserve the public GUI
page-size ceiling200 and its SQL lookahead of201; the CLI list validator
ceiling100 must not reject or silently trim this separate admin bridge. Preserve current key/owner
labels and detail links. Avoid an N+1 inspection/history query per list row,
racing companion queries or fetching all history into the controller.

Complete missing CLI inspection filters additively, not by changing legacy
owner-email semantics: the existing GUI lacks exact delivery UUID, owner UUID
and exact normalized owner email. Add these as explicit optional bounded
filters (e.g. delivery_id, owner_id, owner_email_exact). Keep existing
owner_email as case-insensitive SUBSTRING, repeated values OR-within and
AND-across. Exact-email filter uses the SAME shared normalization/equality as
CLI; dates remain inclusive aware UTC and end-before-start refuses safely.
All accepted filters must reach the SQL BEFORE limit/offset, carry through
Previous/Next, retain submitted values/chips and reset offset when changed.
Use existing owner/owner_email choice kinds; add ONE focused email_delivery
kind to the EXISTING record-choice service/API allowlists if needed for the
new delivery filter: latest100 + older UUID search/selected hydration, minimal
ID/status/time label, no subject/body/secret/provider prose. This is reuse of
the existing picker, not a second lookup system or raw UUID entry. Keep the
common list ergonomic; the extra exact filters may use existing advanced
filter disclosure patterns with their meanings and active state clear.

Detail retains existing metadata/secret lifecycle and adds the shared safe
latest-recorded-failure provenance: finite code, action and recorded time,
with a useful unavailable explanation. Reuse the existing sendability provider
for action eligibility; do not invent another secret lifecycle classifier.
Current eligibility is a preflight, not proof of SMTP readiness/delivery.
Preserve the prepared-recipient contract in the current ambiguous-email
runbook: the stored delivery recipient is recorded attempt metadata; older
history is not reconstructed. If current owner address is shown, label it
separately from the recorded recipient. Core prepares the destination from
the refreshed current owner at execution time, including deferred workers.
An enqueue review does NOT freeze a future SMTP destination or prove inbox
arrival; explain this briefly beside the action. Do not change Core to trust
posted recipient/owner overrides, freeze old metadata as delivery authority,
or add recipient/body data to the existing three-UUID task payload.
Retain pending/sent/failed/sending/expired/consumed/ambiguous distinctions and
same-secret history protection, including confirmed/ambiguous SMTP acceptance.
No plaintext key, encrypted payload/nonce, email body, full auth token or raw
SMTP exception/provider response in HTML, logs, audit, downloads or tasks.

## Exact selected-delivery actions and audited dispatch

Keep normal pending send-now/enqueue, and expose explicit retry-failed intent
for an EXISTING failed delivery, matching the CLI --retry-failed contract.
A failed attempt is eligible only when the shared current Core preflight says
so; consumed/expired/sending/sent/ambiguous same-secret history is never made
resendable by a checkbox. Explain existing rotate/recovery paths without
recovering old material. Do not auto-create a new delivery when a selected
UUID is missing or a different secret/key/recipient binding is supplied.

Preserve the existing one-page confirmation/action flow for ordinary pending
sends, including its optional reason (blank remains None). Failed retries
require a distinct explicit retry intent plus a nonblank reason. Resolve
exact delivery/key/one-time-reference binding and current eligibility on the
server before send/enqueue; the browser supplies no authority through posted
actor, owner, key, recipient or reference overrides. A failed-only flag on a
now-pending row or a normal-send intent on a now-failed row refuses. Keep the
worker's independent atomic claim/consume/history law. Do not add a general
cryptographic review workflow to ordinary delivery actions merely to match
the CLI. If a separate failed-retry review is useful, reuse existing bounded
actor/session/action-purpose/expiry primitives and refuse stale/forged/cross-
target reviews; it is not a new receipt platform. The SMTP test below DOES
need its explicit expiring one-use intent because it has no existing sender
claim/consume lifecycle. Current normal admin auth and CSRF remain mandatory.

The CLI retry reason is at most1024 UTF-8 BYTES, not212's8–200ASCII rule or a
silently different GUI512-character rule. Reuse/extract its existing nonblank,
known-secret and byte-bound validation into the minimal shared application
seam as necessary. Give accurate Unicode-byte help and fixed safe rejection;
retain valid original reasons consistently with the reviewed/audited value.
Normal pending behavior/CLI defaults remain unchanged; do not globally apply
the failed-only required/nonblank/1024-byte CLI rule to pending CLI actions.
Any finite GUI bound for an optional provided reason must be documented and
keep blank/omitted pending reasons accepted. Include a multibyte
boundary case, not only ASCII character count.

Concrete missing seam: cli/email.py _record_enqueue_request_audit commits
email_key_enqueue_requested BEFORE dispatch, with the parsed UUID under safe
one_time_reference_id (the global sanitizer intentionally omits secret-bearing
field names). Legacy GUI discards reason. Extract this small operation into a
shared service function/method; web code must not import CLI. Preserve the
CLI helper's stable public/testing surface by delegating with unchanged
ordering, metadata and defaults. Server actor/reason/explicit retry intent
must reach the GUI intent audit. Do not weaken the global metadata sanitizer.

Celery receives EXACTLY the existing three safe UUID arguments, never reason,
body, credentials, policy or plaintext key material. Preserve deferred task
import (workers validate Settings at import); no new worker engine/queue.
Persist requested intent before broker dispatch. Broker failure/lost ack must
not become queued/sent success or a rollback promise; say requested and
unconfirmed and point to checking existing delivery/audit state before retry.
Distinguish requested enqueue, worker attempt, SMTP acceptance and inbox
receipt. Repeated POSTs must follow existing safe claim/history/idempotency
behavior rather than resend consumed or ambiguous material.

## Bounded SMTP test through the existing primitive

Use EmailService.send_email, as composed by CLI _send_test_email, with the
SERVER-configured SMTP host/port/TLS/auth/from. Never accept browser server
addresses, passwords or transport overrides. No new SMTP transport or public
email API. Respect ENABLE_EMAIL_DELIVERY and configuration readiness before
attempting a send. Preserve ordinary delivery/key email behavior.

Provide a confirmed deliberate test form with one validated recipient and
useful field help. Default subject/body are a harmless gateway SMTP test,
containing no gateway key. Offer optional subject and plain-text body for the existing CLI test
convenience, with safe defaults. Subject: at most255 UTF-8 bytes, no CR/LF/NUL;
body: at most4096 UTF-8 bytes. One validated email recipient, no CR/LF, address
lists or transport overrides. Reject known credentials before signing/sending;
use existing validation/secret checks. These explicit GUI resource bounds do
not change the CLI defaults. Do not add HTML composition or attachments. Do not store raw message subject/body in
audit, diagnostics or logs. Document any deliberate bounded GUI/CLI difference.
The result reports accepted-by-configured-SMTP or a fixed safe unavailable/
failed/unconfirmed outcome, never verified inbox arrival. Raw-ish
provider_status/message_id from the primitive is not a browser trust source.

Prevent accidental double send of the SAME reviewed test intent. Use a small
expiring actor/session-bound intent and EXISTING PostgreSQL session/user locks
and audit facts (or an already-proven equivalent) to record a one-use attempt
BEFORE the external SMTP call; no new table, generic receipt/outbox/job system
or Redis dependency solely for this form. A lost result after a claimed
attempt is unconfirmed, not permission to send again. Bound resource use with
a documented per-actor test-attempt budget of3attempts per60seconds; explain cooldown in the form and count attempted/unconfirmed sends
honestly. Keep the duplicate guard atomic across the deployed API workers.
SMTP failure must not mutate gateway policy, key material or accounting.
Bound each GUI test attempt by an outer30second deadline (respect a shorter
configured SMTP timeout); SMTP_TIMEOUT_SECONDS currently accepts any positive
number, so the per-actor budget alone is insufficient to bound a hung test.
Use a small async orchestration deadline around the existing primitive, not
a new transport/settings platform. A timeout after dispatch can mean SMTP
accepted: report UNCONFIRMED, keep the one-use claim/budget consumed, and do
not automatically retry. CLI and ordinary key-delivery timeouts stay unchanged.
Qualify this with a controlled timeout seam (no30second real-network wait).

## Exact bounded paths and ergonomics

All app paths relative to app/slaif_gateway/:
- NEW api/admin_email_operations.py focused router if simpler than growing
  legacy handlers; main.py composition only.
- api/admin.py ONLY email list/detail/send/enqueue bridges, useful navigation
  and preservation of existing key-issuance/rotation delivery paths.
- api/admin_review_intent.py one bounded SMTP intent purpose (and a failed-retry purpose ONLY if
  a separate review is demonstrably useful), existing primitives, strict
  closed facts, derived size limits, actor/session
  and expiry binding; old purposes unchanged. SMTP test review expiry15minutes;
  one-use claim is authoritative across API workers before attempting SMTP.
- services/email_inspection.py, schemas/email_inspection.py,
  services/admin_activity_dashboard.py and the verified existing
  schemas/admin_activity.py: minimal shared GUI projection/query bridge.
- services/email_delivery_service.py, services/email_service.py only concrete
  compatible admin-operation bridges; NEW services/email_admin_operations.py
  if the shared enqueue audit/one-use SMTP orchestration needs one narrow home.
  Preserve sender claim/decrypt/consume/ambiguity/finalization law.
- cli/email.py ONLY delegation to the extracted shared validator/audit operation
  with unchanged CLI behavior; no command redesign or global CLI refactor.
- db/repositories/email.py and audit.py for required bounded shared read/intent
  query seams; admin_users.py/admin_sessions.py ONLY a directly necessary
  existing-row lock/claim seam for SMTP test budget/idempotency, preserving
  normal authentication/session behavior. No models/migrations/schema changes.
- services/admin_record_choices.py and api/admin_record_choices.py ONLY the
  directly necessary closed email_delivery choice kind using bounded minimal-
  column SQL; existing choice privacy/nonrotating-session behavior unchanged.
- web/templates/email_deliveries/list.html/detail.html, directly necessary
  existing email action partials, NEW web/templates/email_operations/ bounded
  inspection/retry/test/review/outcome/error templates, operations/index.html
  one useful entry. Existing _record_choice.html optional control_id/help_id
  reuse; do not redesign it, the theme, navigation or sorter.

Use existing SLAIF shell/local assets, ordinal/link-sorted tables/raw typed
keys, comma/M-token formatters, focusable scroll regions, known-record pickers
latest100+older search or suitable finite selects. Every new/touched visible
entry/choice field has a unique ACTUAL control ID and associated field-specific
help (units, blank/default/inherit, scope, consequences, examples). No generic
walls of HMAC/transaction/authority prose in operator flows. Progressive
inspection/actions, clear disabled reasons and direct safe no-JS recovery.
Private non-page reads/status/downloads do not rotate an already displayed
form's CSRF; actual page/mutation session checks remain. Secret-valued input
is refused/withheld before render/sign/audit/dispatch; ordinary values remain
faithful. An error's login303 is not a successful action: verify destination
and persisted outcome. No current-purpose or caller authority through an ID.

## Proportionate verification and setup

Reuse /tmp/slaif192-coding-venv, installed Chromium and qualified fresh-owned
PG/Redis/Mailpit or local mock SMTP fixtures. Exact full resource ID/owner,
loopback binding and disposal verification before use/cleanup; no ambient DB,
real recipient, real SMTP account, provider or Codex call. No new packages,
helper agents, infrastructure, baseline inventory or unrelated/full local
suite. Reuse accepted CLI/sender/worker components where unchanged; use one
current focused receipt per necessary suite and report overlaps precisely.

Unit/ASGI: real strict projectors/validators/intents and controlled fake broker/
SMTP at seams; preserve rich list filters/paging, qualify new exact delivery/
owner/email filters versus unchanged substring email with genuine SQL results
and repeated-filter page links, and inspect only safe latest exact failure. Valid auth/CSRF must reach the intended retry/target/reason/
confirmation validator. Wrong/missing/stale binding, actor/session/purpose,
expired/tampered review, Unicode byte limit and known secret/current opaque
auth alias negatives. Safe fixed recovery and no raw exception/provider prose.

Actual authenticated HTTP + ownedPG: pending/failed/sending/sent and secret
pending/expired/consumed/ambiguous/history states; shared current preflight,
exact existing target, explicit failed intent, actor/reason audit and requested
intent durable BEFORE broker stub, broker failure unconfirmed, worker minimal
3UUID payload, repeat no duplicate secret delivery. Native valid reason and
state changes, independent full target/history/audit snapshots and nonzero
key/ledger/quota/policy preservation; no fake persistence called native.

SMTP test: actual owned local SMTP acceptance and attempt count, same reviewed
intent duplicate/concurrent submit produces at most one attempted message,
budget/cooldown/disabled/config-failure behavior. Controlled broker/transport
fault injection is labelled; no actual inbox or production delivery claim.
Chromium uses actual app/PG for list/detail/retry/enqueue and synthetic local
SMTP test, truthful reload/outcome, existing issuance/rotation regressions,
unchanged-form/background-read token, keyboard/no-JS recovery and desktop/
narrow synthetic captures under /tmp/slaif215. Root visually reviews them.
Do not build another installed whole-GUI matrix;219 is that explicit gate.

Run directly affected legacy email/CLI/session/structure consumers, OAP9 on
exact order/active, scoped Ruff/docs/diff checks. Routine fixture/documentation
corrections remainA/samePR; continuation only for a demonstrated blocking
defect. No repeated unchanged suites or extra evidence catalogs.

## Documentation, publication and handoff

Update docs/MISSING_GUI_FUNCTIONALITY.md G12 only, admin-usability.md, relevant
email/CLI/security/upgrade instructions, verification/gui-cli-parity.md and its
README index. Explain eligibility/retry/queued-vs-accepted-vs-inbox/unknown ack,
one-use SMTP budget, UTF-8 reason bounds, read-only provenance, process/restart
scope, local-test limitations and upgrade with NO schema migration. G14/G15/G17
and final219 stay open; do not call all GUI complete.

Commit/push unchanged strategic order and active pointer with implementation
in ONE215PR, never merge or enable auto-merge. Construct complete report draft
away from its final name; atomically temp-file+flush/fsync+os.replace+dirfsync
to absent oap/reports/215-a-gui-email-parity.md. Final reports never revised.
Report-only SELF sole first parent literalIMPL, only report diff; independently
verify remote PR head/bytes/topology. Then ONE exact responseOK and ONE canonical
coding control waiter in the existing right pane. Root final-head CI/review/
material/visual gates, guarded merge, actualmain3workflows/all9checks/tree and
authoritative terminal timing BEFORE216 activation. WholeGUIgoal ACTIVE until
all agreed scope and final219 installed qualification are actually fulfilled.
