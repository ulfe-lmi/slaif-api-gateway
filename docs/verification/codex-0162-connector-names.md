# 2026-10-18 Codex 0.162 version-2 connector tool names

Objective 190-a bounded verification record.

## Scope

Bounded connector-only change for the registered
`codex-0.162-responses-v1` module: version `1` → `2` adds a
namespace-scoped tool-name rule — strict built-in namespaces
(`functions`, `multi_agent_v1`) keep `^[a-z][a-z0-9_.-]{0,63}$`, while
dynamic `mcp__codex_apps__*` connector namespaces additionally accept the
bounded leading-underscore form
`^(?:[a-z][a-z0-9_.-]{0,63}|_[a-z][a-z0-9_.-]{0,62})$` (64 characters
total). Exact names are preserved unmodified to the provider and in
replay; the shared downstream function-name intersection (hyphen
permitted, dot not) is unchanged. The audited key-module migration gains
the frozen `0162-v1` historical selector and the
`0162-v1 <-> 0162-v2` hop, completing the six legal edges.

## Identities

- v1 (historical, byte-immutable):
  `724ec7358a95e8820f02f7dd2d2b1b4ad1276d4065af2ecd329cc2ca52b5892e`
- v2 (current): `b7b257ed9338969a4482fd19434adb6b4a6d96c10037d69899298e643d303f85`
- 0.149-v4 frozen source:
  `ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec`

## Proven (this objective)

- Unit (DB/network independent): classifier vocabulary/boundary cases,
  full-pipeline dot/hyphen intersection, stale-v1 rejection, fixture
  immutability, frozen migration identity facts and the closed six-edge
  set, and CLI selector wiring (exact source/target/action/apply per
  selector).
- Real owned PostgreSQL (disposable, exact-ID-labelled, removed by the
  fixture): 19 upgrade/rollback cases including the v2 hop, repeat
  no-op, cross-target and drift fail-closed, stored-identity, whole-row
  preservation, audit-failure atomic rollback, concurrent duplicate
  apply, and corrupt v1 digest rejection.
- Real Gateway E2E (owned PG, mock loopback backend): pinned 0162-v2
  key, streaming declared `_read_page`/`read_page` connector namespace
  under the generic 0.162 stream grammar, owned replay carrying the
  streamed call plus its output, exact names on both provider legs,
  valid final HMAC, two finalized 5-token ledger rows, key counters
  (2, 10); invalid connector and builtin leading-underscore names
  rejected before admission with zero backend calls and zero
  accounting.
- The new E2E exercises the existing generic 0.162 stream grammar
  (output-item added, function-call arguments delta, output-item done,
  completed); `function_call_arguments.done` remains outside the 0.162
  admitted grammar (a different 0.149 strict branch), and no broader
  stream-grammar qualification is claimed.
- Independent root-side proofs (strategic review artifacts, not CI):
  33-case registered-module v2 representative policy probe; 7-lifecycle
  upgrade PostgreSQL proof; real Gateway/auth/PG/signed-Local stream and
  replay proof; 183-case focused unit plus 5 Gateway E2E green run with
  sealed source bindings.

## Not proven / pending

- The full operator-supplied 197 name/type artifact has not been
  provided; the v2 rule is validated against the representative supplied
  name (`_read_page`) and synthetic bounded vectors. The exact 197-name
  criterion is PENDING; no fabricated capture exists.
- Final-head CI on the PR is pending at publication time.
- No production deployment, real model, private plugin, or
  backend-version claim follows. Diagnostics work is out of scope.
- The existing unsuppressed SQLAlchemy unary-distinct and Alembic
  `path_separator` warnings were observed in runs but are preexisting
  and unrelated to this change.

## Evidence boundary

Unit tests are DB/network independent. E2E uses the real Gateway with an
owned disposable PostgreSQL and a synthetic mock backend (labeled
not-a-capture). The independent probes for this objective are manual
external evidence recorded under strategic review artifacts, not CI. No
actual official-CLI run with the new connector names occurred for this
objective; the official-CLI proofs on record are dated Objective 189
historical evidence (the 12-builtin lowering), and they do not qualify
the new connector names.

## 190-b continuation (2026-10-18) — file-backed compatibility profile DATA

This dated continuation records what Objective 190-b (PR #328, same branch
and PR as this record) changed on top of the 190-a evidence above. The
190-a facts above remain historical and are not rewritten.

- The pending real 197-name criterion is resolved: the full
  operator-supplied 197 name/type diagnostic capture now ships as the
  supplemental SYNTHETIC-wrapped regression fixture
  `tests/fixtures/codex/0.162.1/connector-tool-names-197-v1.json`
  (SHA-256 `a32bbf25de4e0be15690feaf3a86a4f453aac2d281b9b67d2cd21daa1bd1c8c4`)
  with its bounded provenance sidecar, and the registered module plus the
  shared request policy accepts all 197 names through it. It is evidence,
  never a runtime name inventory or selected policy identity.
- The 0162 module is now a data-revision module: the effective module
  version is the validated profile DATA revision (packaged default
  revision `3`, canonical DATA digest
  `aa3de5376819022191e11935ee311acd4b59bf590324daaa0e3ebc448daf90bd`),
  and the shipped DATA
  (`slaif_gateway/modules/clients/profiles/codex_0162.json`) defines the
  namespace literals/prefixes, bounded grammar traits, and ceilings,
  including the DATA-defined leading-underscore connector rule. The
  historical v1/v2 fixtures remain byte-immutable frozen migration
  selectors only; they are not live decoders and stale/legacy pins fail
  closed until an explicit audited `migrate-key-profile`.
- A validated operator profile file
  (`CODEX_COMPATIBILITY_PROFILE_FILE`, data revision >= 3) loads with the
  same installed engine and no rebuild; a future data revision (e.g. 4)
  changes the effective version/digest with no source change.
- The dedicated file-backed verification record is
  [`codex-file-compatibility-profiles.md`](codex-file-compatibility-profiles.md)
  (dated 2026-10-18): focused unit, owned-PostgreSQL, fresh-process
  real-HTTP Gateway, wheel, and CLI error-boundary evidence.
