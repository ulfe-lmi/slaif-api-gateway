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
