# 2026-10-18 Codex 0.162.1 additional-tools profile and Local-pair lowering

Objective 189-a: register the structurally captured Codex CLI 0.162.1
`additional_tools` profile (`codex-0.162-responses-v1` v1, one exact
`local-coding-v1` pair) and implement the approved bounded initial-prefix
provider lowering for that pair only.

## Source facts

- Source contract: tag `rust-v0.162.1`, commit
  `092d3acd6bec3e3a14bdc7e7a2810ab628ab759d`.
- Official isolated capture: archive SHA-256
  `a676f5722aae0d86cbe3764332f08eab1fdd89dc0a300b3ad4ffbf48611fa3e3`,
  binary SHA-256
  `628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1`.
- Profile fixture: `tests/fixtures/codex/0.162.1/additional-tools-profile-v1.json`,
  SHA-256 `724ec7358a95e8820f02f7dd2d2b1b4ad1276d4065af2ecd329cc2ca52b5892e`,
  honesty label `codex_0162_additional_tools_profile_v1`.
- The capture observed 7 `functions` tools and 5 `multi_agent_v1` tools.
  That is a sample of a larger built-in vocabulary (the operator profile
  reports 11 functions; the synthetic 197-tool / 11-namespace case is
  11 + 5 + 181 across the supplied namespace counts and is labeled
  not-a-capture). No exact built-in tool list or count is pinned, and no
  claim is made about current backend versions, installed private plugins,
  or full newer-Codex qualification.

## Profile contract (version-owned, finite)

- Strict built-in namespaces `functions` and `multi_agent_v1`; dynamic
  namespaces match `^mcp__codex_apps__[a-z][a-z0-9_.-]{0,63}$`.
- Ceilings: 16 namespaces, 256 tools total, 256 tools per namespace,
  20,000 bytes per tool description, 262,144 total description bytes,
  4,096 schema properties per tool; tool names match
  `^[a-z][a-z0-9_.-]{0,63}$`, function-only, unique per namespace; existing
  schema/depth/byte/recursive-authority checks apply.
- Unknown fields, namespaces, tool types, duplicates, missing relevant
  grants, hosted types, and malformed items fail closed. Profile facts
  (ID/version/digest/source) are coherent and version-owned.

## Bounded provider lowering (0.162 × Local pair only)

- Only the validated `input[0]` `additional_tools` prefix is eligible. Its
  namespace declarations are lowered into the existing top-level `tools`
  array (one `{"type": "namespace"}` entry per declared namespace, declared
  order, exact preservation), then the item and its protocol ID are removed
  while the remaining input is preserved in order.
- No prefix → unchanged body. Later position, repeated item, mixed top-level
  `tools`, wrong role, or malformed shape fail closed with a safe error
  before any provider body is built.
- Policy/admission run first and estimation consumes the canonical policy
  result, so declaration bytes remain in the conservative estimate; lowering
  is pure body construction before final serialization and HMAC signing, and
  the same lowering plus revalidation applies to the refreshed body after a
  lazy quota wait. The signature always covers the final forwarded bytes.
- Privacy: the exact Local pair omits `prompt_cache_key` and client metadata
  for 0.162 requests (the 0.162 client derives its prompt-cache key from
  session metadata), exactly as for 0.149; the signed opaque identity and
  service Bearer substitution are unchanged. No other profile or server pair
  is altered.

## Deployment prerequisites (existing gates, unchanged)

- All-four key grants require all-four route flags (including
  `codex_encrypted_reasoning_replay=true`) plus a valid route
  `codex_limits` object; missing route capability fails closed before
  backend work.
- Codex pricing must be complete (`cached_input_price_per_1m`,
  `reasoning_price_per_1m`, `pricing_metadata.codex_accounting` with positive
  long-context threshold, positive input/output multipliers, and exactly one
  cache-write dimension); partial/unknown metadata fails closed with
  `invalid_pricing_data` before backend work.
- The migration and profile registration never grant route capabilities or
  alter quotas; test-owned route/pricing data is additive fixture data only.

## Evidence and classification

- Unit (DB/network independent): `tests/unit/test_codex_0162_client_tools.py`
  (real registered module; exact 197 synthetic counts; omitted/null/valid ID
  states; invalid ID classes; unknown field/namespace/type/duplicate and
  missing-grant negatives; coherent version-owned profile facts; canonical
  fixture hash; pair registration and 0149/0147 pair integrity; 256/257
  tool and 16/17 namespace boundaries; description/schema/byte ceilings with
  global limits intact).
- Provider-body lowering (mocked): `tests/unit/test_upstream_payload_reconstruction.py`
  (exact provider body, no-prefix unchanged, later-position safe failure,
  helper fail-closed matrix, input preservation, flag ownership,
  policy-result byte identity after build).
- Real Gateway, real PostgreSQL (owned instance), mock loopback backend:
  `tests/e2e/test_codex_0162_local_tools.py` (synthetic 197 profile full
  gateway pass with signature verification over exact final provider bytes,
  input preservation, prompt-cache/client-metadata absence, two finalized
  ledger rows of 5 tokens with aggregate key total 10; all-four key grants
  without the fourth route grant → safe 400 before backend, no accounting;
  0.149-v5 key rejects the 197 profile before accounting).
- Independent external proofs (not part of CI): 21-case registered-module
  profile/policy probe; official 0.162.1 CLI → mock capture; official
  0.162.1 CLI → real Gateway/auth/owned PG/admission/signed Local → real
  loopback HTTP mock backend run (exit 0, one backend request, HMAC over
  final bytes verified, key requests/tokens/ledger finalized); independent
  legacy 0.149 Local streaming E2E rerun; CLI unexpected-error probe;
  missing-route-grant and missing-pricing negatives.
- Pending: final-head CI checks on the published commit. The post-PR-220
  128-worker qualification remains NOT RUN. No production deployment claim
  follows from this record.
