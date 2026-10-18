# Upgrade, rollback, and forward recovery

> **Status:** Current lifecycle principles
> **Procedure:** Use the [RC-beta upgrade checklist](runbooks/rc-beta-upgrade.md)
> for executable steps

## Before changing a deployment

1. Pin the candidate tag or full commit and review its release notes and
   migration diff.
2. Snapshot PostgreSQL and preserve every secret version needed to validate
   existing gateway keys or decrypt pending one-time delivery.
3. Run `alembic history` and `alembic heads`; confirm the candidate has one
   expected head.
4. Restore the backup into an explicitly disposable target and run
   `scripts/verify_restore.py`.
5. Rehearse the upgrade with the same Compose profiles and operator settings as
   the target deployment.

## Recovery decision

Application rollback is safe only when no incompatible migration or semantic
data transformation has occurred. If migration downgrade is explicitly
supported, test it against a disposable copy before relying on it. Otherwise:

- restore the pre-upgrade database and matching application together; or
- fix forward with a reviewed corrective migration.

Never pair an older application with a newer schema merely because the process
starts, and never automate a destructive downgrade without verified backups.

Record recovery point objective (RPO) as the age of the latest successfully
restored backup and recovery time objective (RTO) as measured restore plus
verification time. Those measurements are local operational evidence; the
project offers no RPO, RTO, or availability SLA.

## Codex client-module migration (pinned 0.149-v4 keys)

The bounded `client_module` compatibility migration moves one pinned key from
the frozen historical tuple to an explicit finite target. It changes key
metadata only; it is not a schema migration and does not alter quotas, key
policy, routes, or pricing. The generic build, drain, restart, and recovery
steps in the [RC-beta upgrade checklist](runbooks/rc-beta-upgrade.md) apply
unchanged; this section adds the Codex-specific sequence.

Exact identities:

| Tuple | Module | Version | Fixture SHA-256 |
| --- | --- | --- | --- |
| `0149-v4` (frozen source and only rollback target) | `codex-0.149-responses-v1` | `4` | `ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec` |
| `0149-v5` | `codex-0.149-responses-v1` | `5` | `ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec` |
| `0162-v1` | `codex-0.162-responses-v1` | `1` | `724ec7358a95e8820f02f7dd2d2b1b4ad1276d4065af2ecd329cc2ca52b5892e` |

The only legal transitions are `0149-v4 → 0149-v5`, `0149-v4 → 0162-v1`,
`0149-v5 → 0149-v4`, and `0162-v1 → 0149-v4`. Any other current module
identity, repeated or cross-target move fails closed.

Target selection: a Codex 0.162.1 client with the wider 197-tool operator
profile needs `--target 0162-v1`. `0149-v5` is the minimal fix for the old
client: it adds the bounded declaration-item ID vocabulary but retains the
closed 0.149 namespace profile; it is not a path to the wider profile.

Migration sequence:

1. Build and deploy the candidate image/tag using the standard checklist;
   quiesce (drain) in-flight gateway traffic before restart so no request
   observes a half-upgraded registry. Verify the deployed binary first
   (`slaif-gateway version`) before touching any key. The new registry makes
   old `v4` `client_module` pins stale: inventory the affected pinned keys
   before the window, perform key migration inside a maintenance window, and
   never run mixed binaries against migrated keys. If a rollback to the old
   image is needed, first run `codex rollback-key-module --apply` with the
   new binary so every key is back on the frozen 0.149-v4 tuple that the old
   binary still accepts; only then downgrade the image.
2. Confirm the deployment prerequisites for the target profile. A key holding
   all four Codex grants requires the resolved route to set all four Codex
   route flags, including `codex_encrypted_reasoning_replay=true`, plus a
   valid top-level `codex_limits` object; Codex pricing must be complete
   (`cached_input_price_per_1m`, `reasoning_price_per_1m`, and
   `pricing_metadata.codex_accounting` with the long-context threshold,
   multipliers, and exactly one cache-write dimension). These are existing
   route/pricing prerequisites documented in
   [`responses-compatibility.md`](responses-compatibility.md); the migration
   never grants route capabilities or alters quotas.
3. Dry run first for every key:
   `slaif-gateway codex upgrade-key-module <key-uuid> --target 0162-v1
   --reason "..." --json` (or `0149-v5`). The dry run performs no write.
4. Apply with `--apply`. Each apply writes the `client_module` metadata and
   one audit record in one atomic PostgreSQL transaction; audit failure rolls
   back the metadata write.
5. Verify: re-run the same command as a dry run — an already-at-target key
   reports no change (no-op), and a key on the wrong tuple reports the
   specific identity-mismatch code. Re-run with `--apply` only after the
   no-op is confirmed.
6. Roll back any time within the supported lifecycle:
   `slaif-gateway codex rollback-key-module <key-uuid> --from-target 0162-v1
   --reason "..." --json`, then `--apply` after the dry run. The rollback
   restores the exact frozen 0.149-v4 tuple.

Unsupported selector values are rejected with a fixed safe error and never
echoed; unexpected failures render a fixed generic safe error and never echo
exception details. No key is ever modified outside one atomic
metadata-plus-audit transaction. The migration never changes key permissions,
pricing, quotas, route flags, or limits; those remain operator decisions
under their existing gates.

Evidence labeling: unit tests are DB/network independent; E2E evidence uses
the real Gateway, an owned disposable PostgreSQL instance, and a mock
loopback backend (the synthetic 197-tool declaration is labeled
not-a-capture); independent official-CLI probes are external manual evidence,
not CI. No production deployment, backend-version, or plugin claim follows
from the migration steps.
