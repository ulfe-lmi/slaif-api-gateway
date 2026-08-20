# External-tool accounting hold reconciliation

This runbook covers the bounded external-tool accounting foundation. It does
not enable provider forwarding or execute any provider-hosted tool request.

When a provider outcome has missing usage, missing or ambiguous final cost, an
interruption/disconnect, or an error whose charge is unknown, the gateway keeps
the exclusive key fence in `held`, keeps the complete `external_tool_fenced`
reservation pending, and writes exactly one content-free usage ledger. Missing
or ambiguous cost is never interpreted as a zero-cost success. Hold expiry is
inspection age only and never releases the reservation.

Operators may inspect candidates with:

```bash
slaif-gateway quota list-external-tool-holds --limit 100 --json
```

Reconciliation is dry-run by default. Dry-run validates the proposed action and
evidence and does not require an actor UUID or reason. Only an authenticated
operator action with an admin UUID, bounded reason, and `--execute` can either provide explicit
actual cost/tokens and a boolean provider outcome, or release with
`--confirm-no-charge`. The supplied actual amount is reconciliation evidence,
not a provider-invoice equivalence guarantee. A charged provider failure is
finalized and charged normally. An actual overrun is charged, and subsequent
quota admission fails normally when the used balance is over its limit.

```bash
slaif-gateway quota reconcile-external-tool-hold \
  --reservation-id UUID \
  --action finalize-actual \
  --execute \
  --actor-admin-id ADMIN_UUID \
  --reason 'bounded operator reason' \
  --actual-cost-eur 0.0042 \
  --actual-total-tokens 123 \
  --failure \
  --json
```

For a confirmed no-charge outcome:

```bash
slaif-gateway quota reconcile-external-tool-hold \
  --reservation-id UUID \
  --action release-no-charge \
  --execute \
  --actor-admin-id ADMIN_UUID \
  --reason 'provider confirmed no charge' \
  --confirm-no-charge \
  --json
```

Both actions are PostgreSQL-authoritative, audited, exact-once, and safe to
retry with the identical bounded facts. Changed repeats, missing evidence,
negative/non-finite values, mismatched ledger/reservation/fence facts, and
multiple linked ledgers fail closed and leave the hold in place. Scheduled
reconciliation inspects and alerts on holds only; it never auto-executes them.
Redis is not used for hold truth, and no raw provider/tool content, URLs,
credentials, prompts, responses, arguments, results, or diagnostics are
stored.

The `finalize-actual` and `release-no-charge` evidence flags are mutually
exclusive and strict: release rejects supplied actual cost, token, or success
facts, while finalize requires all three explicit facts and rejects
`--confirm-no-charge`. The bounded operator reason is retained as the audit
event note. Only the exact held-fence, pending-reservation, single-ledger
shape is eligible; malformed, missing, or multiply linked ledgers are reported
for inspection and are never repaired or retried automatically.
