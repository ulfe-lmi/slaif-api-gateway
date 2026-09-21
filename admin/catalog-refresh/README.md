# Admin: catalog refresh (offline review)

Operator entry points for the working offline slice of the catalog refresh
workflow (objective 180). Full semantics live in
[`docs/catalog-refresh.md`](../../docs/catalog-refresh.md).

## Current entry points

There is exactly one supported way to run this workflow: the CLI.

```bash
# 1) Read-only consistent baseline export from the target database
slaif-gateway catalog-refresh export-baseline \
  --out /var/lib/slaif/catalog-refresh/baseline.json \
  --db-url "$DATABASE_URL"

# 2) Review a typed proposal bundle against that baseline.
#    Publishes one sealed run directory; the primary artifact is REVIEW.html.
slaif-gateway catalog-refresh review /path/to/catalog-refresh.json \
  --baseline-file /var/lib/slaif/catalog-refresh/baseline.json \
  --run-root /var/lib/slaif/catalog-refresh/runs \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key

# 3) Verify a published run (e.g. after copying it for archival)
slaif-gateway catalog-refresh verify \
  --run-dir /var/lib/slaif/catalog-refresh/runs/<run-id> \
  --seal-key ~/.local/state/slaif/catalog-refresh/seal.key
```

Exit codes: review 0/10/20/65/2, verify 0/30/65, export-baseline 0/65
(see the docs page for the table).

The seal key is runner-owned, mode `0600`, created only if missing, and must
live outside the run tree. It is a local integrity key: protect it, rotate
it on trust-boundary changes, and never hand it to research or provider
tooling.

## What does not exist yet

- **No refresh command.** Live source retrieval (provider APIs, ECB FX) and
  Codex-assisted research are planned for objective 181 and are not
  implemented. Bundles are produced out-of-band and reviewed here.
- **No apply command.** Supersession/update of existing rows with accounting
  protections is planned for objective 182. Until then, every execution plan
  is create-only and the report marks existing-row apply as NOT_SUPPORTED.

Do not add shell scripts or dashboard buttons that claim to refresh or apply
catalog data before those objectives exist; an honest NOT_SUPPORTED label is
part of the contract.

## Eventual wrapper contract (planned, objective 183)

When the live-research and audited-apply slices land, the intended admin
surface will be a thin wrapper around the same primitives documented here:

1. trigger a deterministic live retrieval + research pass;
2. produce one typed bundle with full provenance;
3. run the same offline `review` against a fresh `export-baseline`;
4. surface the single `REVIEW.html` in the admin dashboard;
5. require an explicit, separately audited apply step that re-validates the
   baseline identity before superseding rows.

The wrapper must never weaken the bundle schema, the readiness
recomputation, the sealing, or the read-only export semantics defined in
`docs/catalog-refresh.md`.
