# OAP Work Order — 229-d

Finish the normal model-picker summary event path and accurate email recovery guidance

Objective: 229-d
PR mode: AMEND_EXISTING_PR
PR: 403
Repository: ulfe-lmi/slaif-api-gateway
Branch: oap/229-key-creation-active-profiles
Base main: f1feec6bca0fd55f83d78c5badef2ab0b13ee304
Reviewed SELF: 321e7f20f965d75d0cb45ad6edda3698337581f5
Reviewed implementation: 9eea3146c04432144746c8194086be940520291b

## Evidence and narrow reason

Root validated the exact229-c response (terminal77396 nowclosed), immutable report-only SELF/parent, order hash4c105a70f2b5cabd020bb65786abbe88863e23f0d703e281e0c9fa0cc007ecfb and committed current pointer. PR403 remains draft/unmerged/no blocking external review; main remains f1feec6b. The actual per-field help, single-field correction, preset/readiness/rev16/17/transactions and manual-input live-summary work is ACCEPTED component evidence. Do not reimplement it, repeat inventories or run unchanged broad local suites.

One real browser blocker remains: ROOT executed the UNMODIFIED policy-selector.js and create.html inline scripts in Chromium with synthetic DOM, no DB/provider/key. Selecting modeltest in the normal available-model list and clicking its Add selected button produced submitted textarea value=modeltest but preview Models=None yet. Typing the same value into the advanced textarea correctly updated the preview. Reason: policy-selector.js syncManualFromSelected sets manual.value programmatically after Add/Remove/search selection, without a notification; the summary listens only to input/change on unrelated controls. Existing c browser test uses page.fill on the advanced textarea and therefore misses the primary user path. Fix the shared post-mutation notification / summary subscription seam without observers, polling or new framework, and without changing policy-selection acceptance or other forms' selected values. Avoid event recursion. Cover provider/model/endpoint additions and removals plus server-search selection paths that use the same mutation helper. Preserve explicit-vs-preset endpoint ownership and doc-mode behavior.

A second small but material recovery-copy correction: new summary/help says a failed or unqueued email's key "cannot be resent" universally. Existing EmailDeliveryService.send_pending_key_email consumes the secret after SMTP SUCCESS; failed safe attempts can retain an unconsumed secret and have an explicit retry-failed GUI/CLI flow. The service's actual sendability rules forbid unsafe retries of sent/sending/ambiguous/consumed/expired state. Say the operator should check the Email delivery result and use the existing retry action ONLY when permitted; if delivery is ambiguous or the secret is unavailable, follow the existing rotate/reissue guidance. No promise that every failure is retryable or that a sent key can be re-revealed. Keep no-email show-ONCE/copy-before-leaving and send-now/enqueue browser suppression accurate. Change explanatory text only; do not modify email/secret/retry law or rotate existing keys.

## Exact scope, verification and publication

Primary existing%9 owns source/Git/tests; secondary stays idle, no helpers/delegation/prompt handoffs. Allowed changes: the existing policy-selector.js notification seam, create.html summary listener/copy, focused admin summary text, existing browser tests and relevant documentation. Commit this root-authored order and active229-d unchanged. Preserve untracked trio and all earlier immutable reports/orders.

Add a committed regression using the ACTUAL normal available/selected widgets and Add/Remove buttons (not page.fill, direct dispatch or page.evaluate to mimic the mutation). Assert real submitted values AND the visible summary agree immediately after provider/model/endpoint selection/removal. Test the actual older-model/provider search selection where practical, or directly prove its common mutation seam using existing browser fixtures. Retain manual-input/client-toggle/document/no-JS and ownership behavior. Screenshot the actual summary element with the selected clients/models/providers visible, rather than a viewport showing only unrelated fields.

Check the email guidance against existing failed-retry/sendability tests and add a focused copy/helper assertion if needed. Use mocked email/providers and owned disposable fixtures only; no production, real SMTP or inference. Run the affected selector/summary/browser tests and relevant Ruff/docs/whitespace/governance checks; reuse rev16/17/13PG/readiness/security/accounting evidence. Broad final-head CI remains root's gate. No new compatibility, permissions, DATA, schema, migration, source framework or unrelated cleanup.

Update SAME consolidated verification record and operator doc wording with exact new/reused results and the previously missed primary-widget event case. This is a bounded material correction in the same PR, not another feature round. Finish routine fixtures/docs within this order; do not publish early. No additional rounds except a demonstrated blocking defect.

After completion publish ONE immutable oap/reports/229-d-key-creation-final-widget-path.md with literal Implementation head SHA, Report publication commit: SELF, exact verification/not-run results, documentation-impact and code/template restart/no schema/preset/existing-key-migration conclusions. Report-only SELF sole parent=implementation, sole diff=report; push/verify unique remote403head=SELF/noauto before exactly one responseOK. Then one existing control waiter%9. Coding agent never merges/enablesauto. Root independently reviews final checks/material gates, marks PR ready, guarded merges and verifies actualmain. Never reread/resignal closed229-a/b/c or activate230/release/deploy.
