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

## Codex client-module migration (pinned Codex keys)

The bounded `client_module` compatibility migration moves one pinned key
from a frozen historical tuple to an explicit finite target. It changes
key metadata only; it is not a schema migration and does not alter
quotas, key policy, routes, or pricing. The generic build, drain,
restart, and recovery steps in the [RC-beta upgrade checklist](runbooks/rc-beta-upgrade.md)
apply unchanged; this section adds the Codex-specific sequence.

Exact identities:

| Tuple | Module | Version | Fixture SHA-256 |
| --- | --- | --- | --- |
| `0149-v4` (frozen source; rollback target for 0149-v5 and 0162-v1) | `codex-0.149-responses-v1` | `4` | `ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec` |
| `0149-v5` | `codex-0.149-responses-v1` | `5` | `ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec` |
| `0162-v1` (historical; frozen selector and rollback target for 0162-v2) | `codex-0.162-responses-v1` | `1` | `724ec7358a95e8820f02f7dd2d2b1b4ad1276d4065af2ecd329cc2ca52b5892e` |
| `0162-v2` | `codex-0.162-responses-v1` | `2` | `b7b257ed9338969a4482fd19434adb6b4a6d96c10037d69899298e643d303f85` |

Only the six listed transitions are supported: `0149-v4 → 0149-v5`,
`0149-v4 → 0162-v1`, `0149-v5 → 0149-v4`, `0162-v1 → 0149-v4`,
`0162-v1 → 0162-v2`, and `0162-v2 → 0162-v1`. An exact repeat of an
already-at-target key (dry run or `--apply`) is a successful no-op that
performs no additional audit mutation, while drifted or unexpected module
identities and cross-target moves fail closed.

Target selection: keys already on the exact 0162-v1 tuple take
`--target 0162-v2` directly for the version-2 connector-name profile
(bounded leading-underscore connector tool names with exact
preservation). Legacy 0.149-v4 keys need the explicit two-hop sequence
`0149-v4 → 0162-v1 → 0162-v2`, performed while quiesced. `0149-v5` is the
minimal fix for the old client: it adds the bounded declaration-item ID
vocabulary but retains the closed 0.149 namespace profile; it is not a
path to the wider profile. The full
operator-supplied 197 name/type diagnostic capture now ships as the
supplemental SYNTHETIC-wrapped regression fixture
(`tests/fixtures/codex/0.162.1/connector-tool-names-197-v1.json`); the
connector-name rule is validated against all 197 supplied names in that
fixture as well as the representative supplied name.

Migration sequence:

1. Build and deploy the candidate image/tag using the standard
   checklist; quiesce (drain) in-flight gateway traffic before restart
   so no request observes a half-upgraded registry. Verify the deployed
   binary first (`slaif-gateway version`) before touching any key. The
   new registry makes old `v4` `client_module` pins stale, and the v2
   hop additionally makes `0162-v1` pins stale: inventory the affected
   pinned keys before the window, perform key migration inside a
   maintenance window, and never run mixed binaries against migrated
   keys. The rollback destination depends on the selected old image.
   When downgrading to this PR's base (`86ae51c`, the PR #327 merge),
   that registry accepts `0162-v1` and `0149-v5` and rejects `0149-v4`:
   run only `0162-v2 → 0162-v1` with the new binary, leave existing
   `0149-v5` keys in place, and then start the base image. Moving keys to
   `0149-v4` in that lifecycle would break the rollback. The `0149-v4`
   destination applies only to an older pre-189 binary whose registry
   still accepts v4, and is a separate explicit lifecycle: first run
   `codex rollback-key-module --apply` with the new binary so every key
   is back on the frozen `0149-v4` tuple the old binary accepts; only
   then downgrade to that old image.
2. Confirm the deployment prerequisites for the target profile. A key
   holding all four Codex grants requires the resolved route to set all
   four Codex route flags, including
   `codex_encrypted_reasoning_replay=true`, plus a valid top-level
   `codex_limits` object; Codex pricing must be complete
   (`cached_input_price_per_1m`, `reasoning_price_per_1m`, and
   `pricing_metadata.codex_accounting` with the long-context threshold,
   multipliers, and exactly one cache-write dimension). These are
   existing route/pricing prerequisites documented in
   [`responses-compatibility.md`](responses-compatibility.md); the
   migration never grants route capabilities or alters quotas.
3. Dry run first for every key; the dry run performs no write:
   `slaif-gateway codex upgrade-key-module <key-uuid> --target 0149-v5
   --reason "add optional id vocabulary" --json`;
   `slaif-gateway codex upgrade-key-module <key-uuid> --target 0162-v1
   --reason "migrate key to codex module 0162" --json`;
   `slaif-gateway codex upgrade-key-module <key-uuid> --target 0162-v2
   --reason "upgrade key to codex module 0162 v2" --json` (`0162-v2`
   only from a key on the exact 0162-v1 tuple).
4. Apply with `--apply`. Each apply writes the `client_module` metadata
   and one audit record in one atomic PostgreSQL transaction; audit
   failure rolls back the metadata write.
5. Verify: re-run the same command as a dry run — an already-at-target
   key reports no change (no-op), and a key on the wrong tuple reports
   the specific identity-mismatch code. Re-run with `--apply` only
   after the no-op is confirmed.
6. Roll back any time within the supported lifecycle, dry run first and
   `--apply` after:
   `slaif-gateway codex rollback-key-module <key-uuid> --from-target
   0162-v2 --reason "revert key to codex module 0162 v1" --json`
   (restores the exact historical 0162-v1 tuple); `--from-target 0162-v1`
   or `--from-target 0149-v5` restore the frozen 0149-v4 tuple. Choose
   the destination the target old image's registry accepts, as in step
   1.

Unsupported selector values are rejected with a fixed safe error and
never echoed; unexpected failures render a fixed generic safe error and
never echo exception details. No key is ever modified outside one
atomic metadata-plus-audit transaction. The migration never changes key
permissions, pricing, quotas, route flags, or limits; those remain
operator decisions under their existing gates.

Evidence labeling: unit tests are DB/network independent; E2E evidence
uses the real Gateway, an owned disposable PostgreSQL instance, and a
mock loopback backend (the synthetic 197-tool declaration is labeled
not-a-capture); independent official-CLI probes are external manual
evidence, not CI. No production deployment, backend-version, or plugin
claim follows from the migration steps.

## Operator request capture (binary-only, default OFF)

The operator request-capture facility (Objective 191) is **binary-only**: it
adds no database migration, no schema change, and no environment requirement.

- **Upgrade.** Deploying a build that includes the facility changes nothing
  by default: `REQUEST_CAPTURE_ENABLED=false` means no capture middleware
  behavior difference beyond a no-op observer gate, no new files are created,
  and no configuration is required. If you adopt it, follow
  [runbooks/incoming-request-capture.md](runbooks/incoming-request-capture.md)
  (dedicated `0700` writable mount shared by all API workers, restart all
  workers, arm a finite window).
- **Rollback.** Rolling back to a binary without the facility is safe: no
  database state references the capture root, and the retained files remain
  private (`0700`/`0600`) and inert under the old binary. Note that armed
  windows live in the **shared filesystem manifest**, not in worker memory;
  only the enable/dir/revision *settings* are per-process startup snapshots.
  Before downgrading, `request-capture stop` (and `cleanup` if the artifacts
  are no longer needed) is recommended; if you do not, an unexpired and
  unexhausted window in the manifest can resume collection as soon as a build
  with the facility is enabled again.
- **Restart matrix.** `REQUEST_CAPTURE_ENABLED`, `REQUEST_CAPTURE_DIR`, and
  the revision-provenance settings take effect only after all API workers
  restart; `arm`/`status`/`stop`/`cleanup`/`inspect` need no restart.

## Codex 0.162 file-backed profile DATA (data-only upgrade)

The one Gateway upgrade that installs the data-revision 0162 engine is a
normal binary upgrade; after it, future compatibility-policy updates are
DATA file operations with the same installed engine:

1. **Mount the profile directory read-only.** Point
   `CODEX_COMPATIBILITY_PROFILE_FILE` at a file inside a trusted directory
   bind-mounted read-only into the API, worker, and scheduler containers.
   Atomic host-side file replacement (write temp file, rename over) stays
   visible to running hosts; only process bootstrap consumes it.
2. **Validate the candidate offline first:**
   `slaif-gateway codex inspect-profile-file <candidate> --json` (bounded
   regular UTF-8 JSON, revision >= 3, finite vocabulary, ceilings within the
   installed hard caps). A profile describes namespace literals/prefixes,
   grammar traits, and ceilings only; it cannot grant permissions,
   endpoints, providers, hosted authority, or executable behavior.
3. **Record provenance** (source, digest via `inspect-profile-file`,
   revision) in the deployment record before rollout.
4. **Restart/drain every process** (all API workers and any CLI usage
   against the same configuration). There is no hot reload; all workers
   and the CLI must use one profile snapshot — never serve traffic with
   mixed profile revisions. A missing or invalid configured file refuses
   startup; there is no silent fallback.
5. **Verify:** `slaif-gateway codex show-profile` (this CLI process
   snapshot) matches the candidate facts, and the running HTTP process
   reports the same active identity for its pinned keys.
6. **Migrate pinned keys explicitly**, dry run first:
   `slaif-gateway codex migrate-key-profile <key-uuid> --from-version
   <rev> --from-digest <hex> --reason "..." --json`, then `--apply`
   (target `active` by default). Legacy/stale pins are denied by the
   registry until their explicit migration; a same-revision/
   different-digest source fails closed.

**Data-only rollback** uses the previous trusted file (or the packaged
default by clearing the setting) with the new engine: validate,
restart/drain, verify, then migrate any key that must return to the
previous pin. **Binary rollback** down to an old image requires first
restoring the literal old tuple with the new engine —
`migrate-key-profile --target 0162-v1` (or `0162-v2`) — because the old
image's registry does not know data-revision pins; rolling back to
`86ae51c` requires `0162-v1` and leaves `0149-v5` keys unchanged.

Do not claim that all future Codex protocol semantics fit in profile
DATA: new execution, stream, or item behavior outside the engine
validators may still require a code change.
