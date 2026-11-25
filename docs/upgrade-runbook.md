# Upgrade, rollback, and forward recovery

> **Status:** Current lifecycle principles
> **Procedure:** Use the [RC-beta upgrade checklist](runbooks/rc-beta-upgrade.md)
> for executable steps

## Before changing a deployment

For `responses_input_item_count_exceeded`, follow the
[Codex input-item ceiling runbook](runbooks/codex-input-item-count.md).
The deployment's 65,536-item override is an API environment setting: recreate
HTTP API workers through a rolling replacement. It needs no rebuilt image,
schema migration, route edit or key rotation. This differs from the hot-read
PostgreSQL adapter-byte settings below.

For large Codex image histories, align both ingress and route adapter byte
ceilings using the [image-history payload runbook](runbooks/codex-image-payload-size.md).
The six local Qwen adapter ceilings can be raised from the inherited 64 MiB
to 128 MiB through existing audited route configuration. That route-only change
requires no rebuilt image, process restart, schema migration or key rotation;
the independently configured image allowance and Nginx limits still apply.

The [Codex model-switching update](codex-model-switching.md) changes replay
compatibility in the engine: verified same-key client-tool history is portable,
while opaque reasoning/compaction remains source-bound. Deploy the reviewed
image and recreate API workers; there is no schema, key-pin, registry or key
rotation step. Existing reference rows retain their source provenance. An older
binary may reject a newly accumulated mixed-route history after rollback;
preserve the database and local conversations, and use forward recovery or
visible-history reconstruction rather than deleting ownership records.

For the Qwen output-budget/terminal update, follow the
[Codex tuning guide](codex-tuning-qwen.md). The engine change accepts bounded,
usage-backed output-limit terminals and requires recreating API workers; it adds
no schema or compatibility-preset revision and requires no key rotation/pin
migration. Apply the six reviewed 64,000-default/128,000-maximum route changes
through audited partial-update plans. Coordinate the conservative client
compaction settings first, especially for the 100,000-context RTX3090 backend.
The examples do not overwrite existing user configurations or rewrite historical
qualification identities. Rollback restores prior route values through fresh
audited plans and the prior image; never roll back finalized usage.

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

## CLI field-configuration round (objectives 196-205)

The field-configuration round delivered objectives 196-204 (typed key-policy,
effective/lazy/lookup, faithful cloning, provider/route parity, replay-reference
maintenance, content-free request diagnostics, delivery inspection, batch
administration, and owner/cohort edits plus process-configuration inspection)
and objective 205. Objectives 196-204 are merged into `main`; objective 205 is
qualification evidence (the single complete executable-only installed
transcript) and adds NO product schema, NO module-identity or key-policy
migration, and NO automatic key rotation - its only product change is the
accepted 17-position safe numeric-input conversion fix (205-b).

- **Migration:** the only schema migration in this round's lineage is
  `0026` (`request_diagnostics`, from objective 201). Run `alembic upgrade
  head`; it applies `0026` when not already present. Objective 205 adds none.
- **Data preservation:** the upgrade does not alter issued key material,
  policy, quotas, usage, or replay ownership. Keys, policy/batch edits, and
  extended replay-reference expiries made before the upgrade persist and remain
  visible to the new CLI.
- **Runtime recreation:** any change to runtime environment/Settings (for
  example diagnostics recording, request-capture settings, or the replay TTL)
  requires recreating the affected containers (`api`/`worker`/`scheduler`).
  `config show` is a PROCESS-LOCAL snapshot of the calling CLI process; it does
  not observe live workers. Configure workers consistently and reload/recreate
  them rather than assuming a config snapshot reflects live processes.
- **CLI checks after upgrade (safe, read-only; use `--json` when scripting):**
  `slaif-gateway keys policy effective <KEY_ID>`, `slaif-gateway codex replay
  inspect --all-active`, `slaif-gateway config show`, `slaif-gateway
  diagnostics status`.
- **Rollback is not undo:** returning to an older binary does NOT reverse
  issued keys, policy/batch edits, or extended reference expiries - there is no
  shortening/recovery SQL backdoor. The `0026` diagnostics table is additive;
  do not casually drop it, and do not restore a pre-upgrade database while
  accounting writers are running (follow the stopped-writer/backup/restore
  procedure). Returning to a pre-`420` CLI restores its older numeric-parser
  behavior (credential-shaped numeric input is no longer refused no-echo).
  These are instructions, not production-execution or release authority.

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

### Codex 226 declaration-history profile upgrade (revision 15 -> 16)

Visible-reasoning model-switch correction: retained empty-string ciphertext
must not activate opaque replay, and a qualified backend's null/omitted
ciphertext remains visible at stream completion. See
[the classification contract](responses-compatibility.md#visible-reasoning-is-not-an-opaque-replay-reference).
Deploy a rebuilt engine and drain/restart all API and worker processes. No
schema, preset file/digest, key pin, key material, route limit or quota change
is required. The correction preserves input/output fields; existing
conversations do not need manual edits. Rolling back the engine restores the
old mixed-history stream rejection; genuine encrypted replay retains its
existing provider/route/model restrictions in both versions.

Engine correction for optional result identities: revision 16's pinned
protocol already defines optional `name` on function/custom outputs and
`namespace` on function outputs. The corrected engine validates these against
the original call binding, including after catalog updates, and translates
them consistently through preserve/native/portable transports. See
[the compatibility contract](responses-compatibility.md#optional-codex-tool-result-identities).
For deployments already on revision 16, rebuild and drain/restart every API
and worker process. Keep the existing profile file, digest, key pins, and
keys; no database migration or rotation is required. Rolling back only this
engine correction restores the old field rejection for affected histories.

The follow-up engine correction also supports Codex's named client context:
`function_call_output` with a name and absent/null `call_id`. This source-defined
item is additional context rather than a call-linked result. It is normalized
to labeled user data for every backend, under the original key/route gates;
no call ID or ownership is fabricated. See
[the exact behavior and boundaries](responses-compatibility.md#named-client-context-without-a-tool-call).
Deploying only the optional-name fix can expose the next rejection at
`input[...].call_id`; the named-context correction requires a new engine
build and drained API/worker restart. Existing revision-16 files, digests,
pins, keys, routes, quotas and schema remain unchanged.

The 226 declaration-history lifecycle is ENGINE behavior plus profile
DATA: the new preset (`codex-0.167.1`, revision `16`) requires the NEW
engine containing the lifecycle validators. Pointing the preset file at
an old engine is NOT a supported upgrade: the old engine's
single-initial-declaration law refuses the incremental history and may
return its singleton refusals.

The engine must also recognize the exact pinned incremental hint in both
standalone text representations: a string and a one-part `input_text`
array. Codex 0.167.1 uses the latter in real resumed histories. Leaving
this protocol metadata in the forwarded history can trigger an instruction
placement refusal or a prefix-only backend template error. The representation
fix changes neither the revision-16 preset digest nor key material; it
requires rebuilding and restarting the engine processes. Ordinary late
developer instructions still retain their chronology and placement checks.

Exact scoped sequence (synthetic planning example; run the literal
commands with the operator's real key UUIDs and trusted file paths):

1. Deploy the new engine (API, worker, and scheduler images) with the
   PREVIOUS profile file still active (e.g. the `codex-0.167.0`
   revision-15 file); no key change yet.
2. Validate the candidate offline:
   `slaif-gateway codex inspect-profile-file
   /operator/client-compatibility/codex-0.167.1.json --json` —
   expected: module `codex-0.162-responses-v1`, version `16`,
   canonical digest
   `cff9f7b56966eb2068fdbeb203fe04ac32890e34524200372c2d3f2a30e566ed`.
3. Save the active revision-15 file (canonical digest
   `9634f95de985d8c06fd0b09af3358ae589a14b828d4d4c357d4f98bcafec6a5d`)
   as the rollback snapshot, then point
   `CODEX_COMPATIBILITY_PROFILE_FILE` at the revision-16 file (trusted
   read-only mount, atomic host-side rename).
4. DRAIN and RESTART every process (all API workers plus any CLI usage
   against the same configuration): one active profile snapshot per
   deployment; no hot reload, no mixed-revision serving.
5. Verify `slaif-gateway codex show-profile` reports module
   `codex-0.162-responses-v1`, version `16`, digest
   `cff9f7b56966eb2068fdbeb203fe04ac32890e34524200372c2d3f2a30e566ed`.
6. Migrate each pinned key explicitly — dry run first, then `--apply`,
   repeated per key:
   `slaif-gateway codex migrate-key-profile <key-uuid> --from-version
   15 --from-digest 9634f95de985d8c06fd0b09af3358ae589a14b828d4d4c357d4f98bcafec6a5d
   --reason "226 declaration-history upgrade" --json`, then the same
   command with `--apply` (target `active` by default).
7. Verify the migrated pinned keys serve under revision 16; any
   un-migrated pin remains denied closed.

**Rollback (on the new engine, data-only):** restore the saved
revision-15 file as the active snapshot, restart/drain every process,
then migrate each key back:
`slaif-gateway codex migrate-key-profile <key-uuid> --from-version
16 --from-digest cff9f7b56966eb2068fdbeb203fe04ac32890e34524200372c2d3f2a30e566ed
--reason "226 rollback" --json`, then `--apply`, and verify revision 15
is active. Only then, if required, downgrade to the prior image. There
is NO database or usage rollback: ledger rows, replay references, and
audit entries are never reverted; and keys served under the restored
revision-15 snapshot return to the old engine's singleton law, whose
incremental-history refusals may reappear for 0.167.1-shaped clients.


## Hermes/OpenCode Chat client profile upgrade and rollback (227-a)

Chat client profiles (`hermes-0.22.5-chat-v1`, `opencode-1.19.3-chat-v1`)
differ from Codex compatibility profiles in two ways: their profile DATA
is PACKAGED in the gateway image (no operator-mounted profile file by
default), and key pins have NO migration command. Each process loads
exactly ONE identity per module id from its packaged DATA, so a key pin
resolves only when its `fixture_sha256` matches the deployed revision;
any pin/deployment digest mismatch fails that key's requests closed
before admission. The REGISTERED RUNTIME module `version` and the
`fixture_sha256` are both derived from that document's bytes (the module's
exported `VERSION` constant is a separate source literal that is not the
runtime identity), so a reviewed DATA-only revision needs only the new
document bytes and a re-pin; the module ID remains the one source
constant.

Two distinct file locations must not be conflated:

- **Profile DATA** — the baked JSON documents the binding loads at
  startup, at container path
  `/app/app/slaif_gateway/modules/clients/profiles/` (host source
  `app/slaif_gateway/modules/clients/profiles/`):
  `hermes-0.22.5-chat.json` and `opencode-1.19.3-chat.json`.
- **Policy file** — the `schema_version` 1 document you pass to `keys
  policy update --policy-file`; under `run-cli` it lives in the mounted
  working directory (`/workspace`). It carries the per-key pin and is
  unrelated to the profile DATA bytes.

**Data-only revision (NO code/package/image change required):**

A vocabulary/bounds revision that is only a new reviewed DATA document
can stay on the SAME code and image:

1. Review the new profile JSON and record its new canonical
   `fixture_sha256` and the version string it declares.
2. Bind-mount that reviewed JSON **read-only** at its exact packaged
   path, identically on API, worker, and scheduler (all must see the
   same bytes). Append to the `volumes` list of EACH of those three
   services (do not replace their existing mounts); in YAML long syntax:

   ```yaml
   volumes:
     # existing service volumes stay above these two lines
     - type: bind
       source: /path/to/hermes-0.22.5-chat.json
       target: /app/app/slaif_gateway/modules/clients/profiles/hermes-0.22.5-chat.json
       read_only: true
     - type: bind
       source: /path/to/opencode-1.19.3-chat.json
       target: /app/app/slaif_gateway/modules/clients/profiles/opencode-1.19.3-chat.json
       read_only: true
   ```

   The CLI runs in the API service, so the API container carries the
   mount the CLI uses.
3. **Recreate** the API, worker, and scheduler containers. Restart alone
   never changes bytes baked into the image; the read-only bind mount is
   what overrides them.
4. Re-pin each affected key to the NEW exact tuple through a
   `schema_version` 1 policy file (`keys policy update --policy-file`
   with `--reason`), from the `/workspace` policy file.
5. Verify with `keys policy export <key-id>`: the stored pin shows the
   new `version` and `fixture_sha256`.

A matching new image that bakes the same reviewed JSON is an
ALTERNATIVE to the bind mount, not a requirement. On a native
(non-Docker) install, replace the trusted installed JSON in place and
restart; the loader reads the file relative to the installed module.

**Full image/package upgrade (new image bakes the new DATA):**

1. Deploy the new image to API, worker, and scheduler. All workers must
   use one revision; never serve traffic with mixed revisions.
2. Re-pin each affected key to the NEW exact tuple through a
   `schema_version` 1 policy file (`keys policy update --policy-file`
   with `--reason`). Example, Hermes revision 2: `{"id":
   "hermes-0.22.5-chat-v1", "version": "2", "fixture_sha256":
   "c5e34d46270280d7e08639c01c28065380a2a80843c1114ac1f1ad2a2744d327"}`.
3. Verify with `keys policy export <key-id>`: the version-1 document
   renders the stored pin.

**Rollback (restore the previous revision):**

Rollback is a full DATA restore, not just a re-pin: the previous pin
cannot resolve until the matching previous DATA is deployed again.

1. Re-deploy the PREVIOUS trusted revision to API, worker, and
   scheduler: the previous image, OR the previous reviewed JSON at the
   packaged paths (read-only bind mount, or native replace). Then
   recreate/restart. A re-pin alone on the new DATA is NOT a rollback.
2. Re-pin each key to the previous exact tuple with the matching CLI
   (same `schema_version` 1 policy-file update as the upgrade).
3. While a key's pin digest and the deployed DATA digest mismatch, that
   key's requests fail closed. The previous revision must itself be
   reviewed and qualified; the gateway makes no automatic
   compatibility promise.

**Pin clearing is not key disablement**: clearing the pin
(`"chat_client_module": null` in a `schema_version` 1 policy file)
returns the key to `openai-default` Chat validation. It does NOT
suspend or revoke the key, and it is not a rollback; a client tuned
to a profile's widened envelope (for example Hermes `xhigh`
reasoning effort) may fail default validation until the pin is
restored. To actually disable a key, suspend it (`keys suspend
<key-uuid> --reason "..."`) or revoke it (`keys revoke <key-uuid>
--reason "..."`).

## OpenCode 1.19.3 Responses client profile upgrade and rollback (228)

The pinned OpenCode Responses profile
(`opencode-1.19.3-responses-v1`) follows the same packaged-DATA /
no-migration-command model as the 227-a Chat profiles: each process
loads exactly ONE identity per module id from its packaged DATA, and a
key pin resolves only when its `fixture_sha256` matches the deployed
revision; any pin/deployment digest mismatch fails that key's requests
closed before admission. There is NO database migration and NO
automatic key migration: an upgrade changes the deployed revision and
re-pins keys only.

Exact identity — the `responses_policy.client_module` pin object
(exact keys `id`, `version`, `fixture_sha256`; `version` is the
string `"1"`):

| Module id | Version | Fixture SHA-256 |
| --- | --- | --- |
| `opencode-1.19.3-responses-v1` | `"1"` | `592c5d1baa7aa3a805320411f3f961521ba72b30cc34cafe01cb755ddf69f0ff` |

**Upgrade (new code revision bakes the module DATA):**

1. Deploy the new image to API, worker, and scheduler (one revision;
   never mixed). This module requires an initial code upgrade — the
   profile DATA is baked into the image.
2. Pin each affected key to the exact identity above, with the four
   required capabilities, through a `schema_version` 1 policy file
   (`keys policy update --policy-file` with `--reason`). The
   `responses_policy` field is a COMPLETE replacement block (no
   partial member merge): first run `keys policy export <key-uuid>`
   and, if the key already has a `responses_policy` block, copy that
   whole block into the file and edit it, preserving every member
   you want to keep. Omitting `responses_policy` from the file
   preserves the stored block; `null` clears it (no Codex
   authority). Minimal schema-version-1 block for this module:

   ```json
   {
     "schema_version": 1,
     "responses_policy": {
       "version": 1,
       "allowed_capabilities": [
         "codex_request_envelope",
         "codex_client_tools",
         "codex_streaming_tool_events",
         "codex_encrypted_reasoning_replay"
       ],
       "allowed_local_tool_types": ["function", "custom"],
       "client_module": {
         "id": "opencode-1.19.3-responses-v1",
         "version": "1",
         "fixture_sha256": "592c5d1baa7aa3a805320411f3f961521ba72b30cc34cafe01cb755ddf69f0ff"
       }
     }
   }
   ```
3. Set `RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES=8192` in `.env`
   (shared default `4096` unchanged), then recreate/restart.
4. Verify with `keys policy export <key-id>`.

**Rollback (restore the previous revision):**

Rollback is a full revision restore, not just a re-pin: restore the
PREVIOUS image (or the previous reviewed profile DATA at the packaged
paths) to API, worker, and scheduler, recreate/restart, and only then
re-pin each key to the matching previous identity with the matching
CLI. Clearing the pin is neither a compatibility rollback nor a key
disablement: it reverts the key to default validation (a client tuned
to the profile envelope may fail default validation until the pin is
restored). To actually disable a key, use `keys suspend <key-uuid>
--reason "..."` or `keys revoke <key-uuid> --reason "..."`. Key
material and usage are preserved in all paths; the previous revision
must itself be reviewed and qualified — the gateway makes no
automatic compatibility promise. A code-only fix that keeps the
module `id`/`version`/`fixture_sha256` unchanged needs NO re-pin: the
stored pin keeps resolving against the same DATA identity. Re-pin
only on initial enablement or a DATA identity change (a new
`{id, version, fixture_sha256}`).

## Qwen executable compatibility update (packaged profile 8)

The Qwen schema-label, custom `functions.apply_patch`, sparse Local visible
reasoning stream, and empty-ciphertext continuation fixes require the new
binary. Profile DATA alone cannot add executable validators. The packaged
revision changes from 3 to 8; existing pins require the explicit
`migrate-key-profile` dry run and `--apply` flow above. Record the prior
revision/digest instead of assuming every deployment starts at revision 3.
There is no schema migration in this change.

For a rollback to an earlier data-revision binary, save its exact packaged or
operator profile file first. While still using the new binary, configure that
old file as the active snapshot, migrate the key from its new revision/digest
to that old active profile, and then downgrade the image. Do not use a frozen
`0162-v1` selector to stand for revision 3, 4, 5, or 6. Reopen traffic only after
all workers and key pins agree. See [the Qwen runbook](runbooks/codex-qwen38.md).


## Admin GUI upgrade: catalog seal verification after the 214 asset change

The 214 GUI objective changes the bytes of the bundled
`web/static/js/table-sort.js` asset (an opt-in per-table
`data-ordinal-offset` value; default 0 preserves every existing
table's behavior, and the catalog report renderer picks the asset up
at render time). Consequences for `slaif-catalog-refresh` seals:

- Previously sealed catalog runs that embedded the OLD script bytes
  will FAIL verification after the upgrade. This is a SAFE REFUSAL:
  the seal binds the exact asset bytes, and the mismatch is reported
  rather than silently accepted. It changes no catalog data and no
  verification law.
- **Finish pending catalog runs before upgrading** (let in-flight
  refresh/review runs complete and review their reports on the old
  binary), or
- **Collect and review a FRESH run after upgrading** (a new
  refresh seals the current bytes and verifies cleanly).
- **Never rewrite or regenerate an old seal** to make it match the
  new bytes: an old seal is historical evidence for the bytes it
  bound, and editing it destroys the audit property.

There is no schema migration in this change; keys, routes, pricing,
FX, and accounting are untouched.

## Admin GUI upgrade: email inspection, retry and SMTP test (215-a)

The 215-a GUI objective (G12) adds the email-delivery inspection,
explicit failed retry, and bounded SMTP test controls under the
existing `/admin` exposure. Upgrade is **recreate/restart only**:

- **No schema migration**: existing delivery rows, secrets, and audit
  records are untouched and read exactly as before; the views add
  shared projections and controls over the same tables.
- **No Nginx change**: the new routes sit under the existing `/admin`
  exposure; streaming/anti-buffering settings are unaffected.
- **No new environment variables and no new dependencies**: the SMTP
  test uses the server's existing configured SMTP transport.
- Existing pending/failed deliveries keep their state; the explicit
  retry is a NEW distinct failed-only route and changes no legacy
  send/enqueue behavior.

Rollback to the previous image restores the prior email views; the
append-only audit rows written by 215-a actions are inert historical
evidence to older binaries.

## Admin GUI upgrade: reviewed accounting recovery (216-a)

The 216-a GUI objective (G14) adds the bounded accounting operations
area under the existing `/admin` exposure: four read-only candidate
views (expired pending reservations, external-tool holds,
provider-completed recovery rows, and read-only external-tool fences)
plus reviewed dry-run -> signed review -> confirm-and-apply recovery
actions over the existing reconciliation/hold services. Upgrade is
**recreate/restart only**:

- **No schema migration**: reservations, ledger rows, fences, and
  audit records are untouched and read exactly as before; the area
  adds fresh ordered lock-and-compare reads over the same tables.
- **No Nginx change**: the new routes sit under the existing `/admin`
  exposure; streaming/anti-buffering settings are unaffected.
- **No new environment variables and no new dependencies**.
- **CLI unchanged**: every `reconcile-*` command keeps identical
  behavior; the console is an additional reviewed path, not a
  replacement.
- One operator note: confirm-and-apply requires the EXISTING
  `superadmin` role. If your deployment has no superadmin yet, create
  one explicitly with `slaif-gateway admin create --superadmin`
  (see [`runbooks/admin-access.md`](runbooks/admin-access.md));
  nothing is elevated automatically.

Rollback to the previous image removes the accounting operations
views; the reconciliation/audit rows written by 216-a actions are
inert historical evidence to older binaries.
