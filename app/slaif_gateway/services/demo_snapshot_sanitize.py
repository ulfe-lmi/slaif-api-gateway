"""Worker-only sanitizer and independent verifier for 221 raw copies.

Objective 222, stage a: sanitize and verify the private PostgreSQL raw
copy created by objective 221 BEFORE any web role can read it.

Design law (mirrors the 221 custody law):
- worker-only: no HTTP route, admin template or web role can invoke it;
  the demo web role is NEVER granted anything in this objective;
- a copy stays RAW_UNVERIFIED (or failed) until a committed sanitizer
  transaction AND an independent read-only verifier both pass; only then
  the private manifest advances to DB_SANITIZED_UNPUBLISHED, which still
  means file-backed verification (223) and browser binding (224) are
  absent;
- fail closed: an unknown table/column/type/extension/constraint, a
  transaction error, a verifier failure, a credential error or a timeout
  never promotes the copy;
- deterministic per-copy mappings seeded by the private job id: the same
  old value always maps to the same new value within one copy (foreign
  keys, request ids and denormalized snapshots stay consistent), and a
  different copy gets a different mapping (identity authority is never
  reusable across copies);
- real usage quantities, quotas, costs, currencies, activity times,
  statuses and route/model/provider choices are preserved; identifying
  values, credentials, provider authority, free text, URLs and arbitrary
  JSONB are masked. Preserved usage patterns remain recognizable; this is
  an explicit, human-accepted limitation, not a claim of anonymity;
- the sanitized copy is not usable for gateway authentication or
  forwarding: key token hashes, session hashes, admin credentials, MFA
  secrets and one-time secrets are all invalidated by construction;
- the live source database is never written to: the sanitizer connects
  only to the target service's copy database.
- network boundary: target copy traffic runs on a trusted private
  network (loopback or private segment). The worker connects with
  ``ssl=False``; that is an explicit stage boundary, NOT a claim of
  verified remote TLS.

The field policy (``TABLE_POLICY``) covers EVERY table and column of the
full migrated public schema at the 222 checkpoint (33 public business
tables + ``alembic_version``). The live restored catalog is inventoried
at runtime and must equal the policy exactly; anything else fails closed
before a single byte of the copy is modified.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac as _hmac
import json
import re
import os
import stat
import time
import uuid as _uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from pathlib import Path

import asyncpg

from slaif_gateway.services import demo_snapshot as ds

# 224-r: the recognized clone-receipt vocabulary (objective 208). The
# sanitizer reuses the product's own receipt key and validity-mode
# constants so the demo law can never drift from the supported clone
# flow's receipt shape.
from slaif_gateway.schemas.key_clone import (
    CLONE_RECEIPT_METADATA_KEY as _KR_RECEIPT_KEY,
    VALIDITY_ABSOLUTE as _KR_VALIDITY_ABSOLUTE,
    VALIDITY_COPY_SOURCE_EXPIRY as _KR_VALIDITY_COPY_SOURCE,
    VALIDITY_DURATION_FROM_NOW as _KR_VALIDITY_DURATION,
)

# Installed runtime route capability grammar (objective 223-b). The RC
# transform reuses the product's own strict child parsers so the demo
# law can never drift from ordinary route admission.
from slaif_gateway.modules.servers.completion_service.profiles import (
    PROFILE_KEY as _RC_PROFILE_KEY,
    profile_id_from_capabilities as _rc_profile_id_from_capabilities,
)
from slaif_gateway.modules.servers.vllm_chat_video import (
    parse_video_frames as _rc_parse_video_frames,
)
from slaif_gateway.schemas.provider_route_configuration import (
    KNOWN_CAPABILITY_GROUPS as _RC_KNOWN_GROUPS,
    PRESERVED_CONTRACT_GROUPS as _RC_TRANSPORT_GROUPS,
)
from slaif_gateway.services.audio_route_capabilities import (
    AUDIO_ENDPOINT_CAPABILITIES_KEY as _RC_AUDIO_KEY,
    KNOWN_AUDIO_ENDPOINT_CAPABILITIES as _RC_AUDIO_FLAGS,
)
from slaif_gateway.services.chat_completion_route_capabilities import (
    CHAT_COMPLETIONS_CAPABILITIES_KEY as _RC_CHAT_KEY,
    validate_chat_completion_capability_block as _rc_validate_chat_block,
)
from slaif_gateway.services.embeddings_route_capabilities import (
    EMBEDDINGS_CAPABILITIES_KEY as _RC_EMBED_KEY,
    EMBEDDINGS_CAPABILITY_DIMENSIONS as _RC_EMBED_DIM,
    EMBEDDINGS_CAPABILITY_ENABLED as _RC_EMBED_ON,
)
from slaif_gateway.services.external_tool_policy_contract import (
    DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS as _RC_TOOL_CEILINGS,
    parse_route_external_tool_policy as _rc_parse_tool_policy,
)
from slaif_gateway.services.media_input_estimation import (
    validate_media_input_estimation_block as _rc_validate_media,
)
from slaif_gateway.services.provider_route_configuration import (
    contains_known_secret_shape as _contains_secret_shape,
)
from slaif_gateway.services.realtime_route_capabilities import (
    REALTIME_CAPABILITIES_KEY as _RC_REALTIME_KEY,
    REALTIME_CAPABILITY_AUDIO as _RC_RT_AUDIO,
    REALTIME_CAPABILITY_DIRECT_PROVIDER_EXPOSURE_ACCEPTED as _RC_RT_DPEA,
    REALTIME_CAPABILITY_TRANSCRIPTION as _RC_RT_TRANSCRIPTION,
    REALTIME_CAPABILITY_WEBRTC_CLIENT_SECRETS as _RC_RT_WEBRTC,
)
from slaif_gateway.services.responses_route_capabilities import (
    CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY as _RC_COMPACTION_KEY,
    CODEX_LIMITS_KEY as _RC_CODEX_LIMITS_KEY,
    RESPONSES_CAPABILITIES_KEY as _RC_RESPONSES_KEY,
    parse_codex_compaction_compatible_route_ids as _rc_parse_compaction,
    parse_codex_route_limits as _rc_parse_codex_limits,
    validate_responses_capability_block as _rc_validate_responses_block,
)

# ---------------------------------------------------------------------------
# Safe finite vocabulary
# ---------------------------------------------------------------------------

SANITIZE_STATE_PROMOTED = "PROMOTED"
SANITIZE_STATE_SKIPPED = "SKIPPED"
SANITIZE_STATE_FAILED = "FAILED"

_PRESTATE_NAME = "sanitize_prestate.json"

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.ASCII
)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

# Constraint action codes from pg_constraint (confdeltype/confupdtype).
_FK_ACTIONS = {
    "a": "NO ACTION",
    "r": "RESTRICT",
    "c": "CASCADE",
    "n": "SET NULL",
    "d": "SET DEFAULT",
}
# confmatchtype: s = NONE (default, omitted), f = FULL, p = PARTIAL.
_FK_MATCH = {"f": "MATCH FULL", "p": "MATCH PARTIAL"}

# ---------------------------------------------------------------------------
# Fixed fictional identity data (shipped, reviewed; .invalid reserved names)
# ---------------------------------------------------------------------------


def load_demo_identities() -> dict[str, object]:
    ref = resources.files("slaif_gateway.data").joinpath("demo_identities.json")
    payload = json.loads(ref.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ds.DemoSnapshotError(
            ds.CODE_SANITIZE_FAILED,
            "Demo identity data file is missing or has an unknown version.",
        )
    return payload


# ---------------------------------------------------------------------------
# Deterministic per-copy remappings (seeded by the private job id)
# ---------------------------------------------------------------------------


def _hmac_hex(seed: bytes, salt: bytes, value: bytes) -> bytes:
    return _hmac.new(seed, salt + b"|" + value, hashlib.sha256).digest()


def remap_uuid(seed: bytes, old: _uuid.UUID) -> _uuid.UUID:
    """Per-copy UUID bijection: deterministic, injective in practice,
    link-preserving (same old value -> same new value in every table).

    The first 16 bytes of the keyed HMAC-SHA256 form the new 128-bit
    UUID; the remaining digest bytes are discarded (they carry no
    independent authority beyond the keyed prefix).
    """
    return _uuid.UUID(bytes=_hmac_hex(seed, b"uuid", old.bytes)[:16])


def remap_str_id(seed: bytes, old: str) -> str:
    """Per-copy string-identifier remap (request ids, hashes, provider ids).

    The output is capped at 64 characters (``demo`` + 60 HMAC hex = 240
    keyed bits): the reviewed checkpoint stores some S columns in
    ``varchar(64)`` (codex_replay_references.*_hmac), so the remap must
    never exceed the narrowest reviewed length.
    """
    return "demo" + _hmac_hex(seed, b"s", old.encode("utf-8")).hex()[:60]


def remap_hex64(seed: bytes, salt: bytes, old: str) -> str:
    """Per-copy remap for CHECK-constrained bare 64-hex columns.

    Emits the full 256-bit keyed HMAC digest as 64 lowercase hex
    characters with NO prefix: the reviewed checkpoint constrains
    codex_replay_references.item_id_hmac (NOT NULL) and call_id_hmac
    (nullable) to ``^[0-9a-f]{64}$`` exactly, so any prefix would
    violate the CHECK. ``salt`` (the column name) keeps the two
    per-column digests of the same raw value distinct; the keyed digest
    preserves practical uniqueness and linkability within one copy.
    """
    return _hmac_hex(seed, salt, old.encode("utf-8")).hex()


def _h_column_digest(seed: bytes, column: str, values: list[str]) -> str:
    """Keyed multiset digest over the given values, taken AS-IS.

    Neither side remaps internally: prestate first maps each raw value
    through remap_hex64 to the EXPECTED stored values and passes those;
    the verifier passes the STORED values directly. Both sides therefore
    digest the same post-rewrite value space, and equality proves the
    stored multiset is exactly the expected per-copy remap multiset (an
    un-remapped raw value or any other change breaks equality). Limit:
    this is a per-column multiset proof only — it does NOT prove a
    specific HMAC stayed on its original row. A swap of two remapped
    values between rows with different (gateway_key_id, item_kind)
    tuples preserves the multiset; the composite UNIQUE constraints
    prevent duplicate tuples but prove no placement. Both swapped
    values are still per-copy keyed digests of raw values, so the swap
    exposes no source value.
    """
    h = hashlib.sha256(seed + b"|h|" + column.encode("utf-8"))
    for value in sorted(values):
        h.update(value.encode("ascii"))
        h.update(b"|")
    return h.hexdigest()


def _u_column_digest(seed: bytes, table: str, column: str, values: list[str]) -> str:
    """Keyed multiset digest over the given UUID values, taken AS-IS.

    Same construction as ``_h_column_digest``; the key additionally
    includes the TABLE because U column names such as ``id`` repeat across
    tables and must never share key space. Neither side remaps internally:
    prestate first maps each raw UUID through remap_uuid to the EXPECTED
    stored values and passes those; the verifier passes the STORED values
    directly. Both sides therefore digest the same post-rewrite value
    space, and equality proves the stored multiset is exactly the expected
    per-copy remap multiset (an un-remapped raw value or any other
    substitution breaks equality). Repeated raw FK values (for example two
    gateway keys of the same owner) must appear the same number of times
    under the SAME per-copy remapped value. Limit (shared with the H law):
    this is a per-column multiset proof, not a row-placement proof.
    """
    h = hashlib.sha256(
        seed + b"|u|" + table.encode("utf-8") + b"|" + column.encode("utf-8")
    )
    for value in sorted(values):
        h.update(value.encode("ascii"))
        h.update(b"|")
    return h.hexdigest()


def _s_column_digest(seed: bytes, table: str, column: str, values: list[str]) -> str:
    """Keyed multiset digest over the given string values, taken AS-IS.

    224-s mirror of ``_u_column_digest`` for the S (string-ID) columns:
    the key additionally includes the TABLE because S column names such
    as ``name`` or ``request_id`` repeat across tables and must never
    share key space. Neither side remaps internally: prestate first maps
    each raw value through remap_str_id to the EXPECTED stored values
    and passes those; the verifier passes the STORED values directly.
    Both sides therefore digest the same post-rewrite value space, and
    equality proves the stored multiset is exactly the expected per-copy
    remap multiset (an un-remapped raw value or any other change breaks
    equality). Repeated raw values (for example the same operator_actor
    and db_actor across two catalog applies) must appear the same number
    of times under the SAME per-copy remapped value. Limit (shared with
    the H/U laws): this is a per-column multiset proof, not a
    row-placement proof.
    """
    h = hashlib.sha256(
        seed + b"|s|" + table.encode("utf-8") + b"|" + column.encode("utf-8")
    )
    for value in sorted(values):
        h.update(value.encode("ascii"))
        h.update(b"|")
    return h.hexdigest()


def _declared_unique_single_columns(
    constraints: list[tuple[str, str, str, str, str]],
) -> dict[str, frozenset[str]]:
    """Tables -> columns on which the reviewed schema declares a
    SINGLE-column PRIMARY KEY or UNIQUE constraint.

    Derived from the constraint definitions that ``_check_catalog`` has
    already pinned to the reviewed digest, so this states what the REVIEWED
    schema declares, not what the stored rows happen to satisfy. Only
    single-column declarations are returned: a composite UNIQUE proves no
    per-column distinctness. (U columns are uuid-typed; the catalog
    signature check already proves the type, and the recreated constraints
    prove enforcement at commit - this is the verifier's declared-law
    re-proof.)
    """
    out: dict[str, set[str]] = {}
    for _schema, table, _conname, contype, definition in constraints:
        if contype not in ("p", "u"):
            continue
        start = definition.rfind("(")
        end = definition.rfind(")")
        if start == -1 or end <= start:
            continue
        cols = [c.strip().strip('"') for c in definition[start + 1 : end].split(",")]
        if len(cols) != 1 or not cols[0]:
            continue
        out.setdefault(table, set()).add(cols[0])
    return {table: frozenset(cols) for table, cols in out.items()}


# FTN (fixed tool name) row condition: the reviewed
# ck_codex_replay_references_..._kind_shape CHECK requires tool_name NULL
# for reasoning/compaction rows and NOT NULL for function_call /
# custom_tool_call rows, so one fixed safe value cannot serve both.
_FTN_DATA_KEY = "fictional_tool_name"
_FTN_KIND_COLUMN = "item_kind"
_FTN_NULL_KINDS = frozenset({"reasoning", "compaction"})
_FTN_FIXED_KINDS = frozenset({"function_call", "custom_tool_call"})
# FN (fixed tool namespace) shares the FTN row condition: the same
# reviewed kind_shape CHECK requires tool_namespace NULL for
# reasoning/compaction rows and NOT NULL for function_call /
# custom_tool_call rows.
_FN_DATA_KEY = "fictional_tool_namespace"


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@dataclass(frozen=True, slots=True)
class _IdentityMaps:
    """Per-copy entity mappings keyed by OLD entity id (deterministic)."""

    seed: bytes
    owner_name: dict[str, str]
    owner_surname: dict[str, str]
    owner_email: dict[str, str]
    institution_name: dict[str, str]
    cohort_name: dict[str, str]
    org_name: dict[str, str]
    org_slug: dict[str, str]
    team_name: dict[str, str]
    team_slug: dict[str, str]
    project_name: dict[str, str]
    project_slug: dict[str, str]
    budget_name: dict[str, str]
    template_name: dict[str, str]
    admin_name: dict[str, str]
    admin_email: dict[str, str]


def _suffix(i: int, n: int) -> str:
    """Stable overflow suffix: injective beyond the fixed list length."""
    if i < n:
        return ""
    return f" {i // n + 1}"


def _rotation(seed: bytes, salt: bytes, n: int) -> int:
    """Keyed per-copy list offset: a fresh copy assigns the fictional
    values in a different (but still deterministic and injective) order,
    so no second copy reuses the first copy's identity surface."""
    if n <= 1:
        return 0
    return int.from_bytes(_hmac_hex(seed, salt, b"rot")[:4], "big") % n




def build_identity_maps(
    seed: bytes,
    data: dict[str, object],
    *,
    owner_ids: Sequence[str],
    institution_ids: Sequence[str],
    cohort_ids: Sequence[str],
    org_ids: Sequence[str],
    team_ids: Sequence[str],
    project_ids: Sequence[str],
    budget_ids: Sequence[str],
    template_ids: Sequence[str],
    admin_ids: Sequence[str],
) -> _IdentityMaps:
    """Assign fixed-list fictional values in deterministic old-id order.

    More entities than list entries are handled by a stable overflow
    suffix, so assignments stay injective (and unique-constrained columns
    such as ``owners.email`` and ``cohorts.name`` can never collide).
    """
    firsts: list[str] = data["first_names"]  # type: ignore[index]
    lasts: list[str] = data["last_names"]  # type: ignore[index]
    domains: list[str] = data["email_domains"]  # type: ignore[index]
    insts: list[str] = data["institutions"]  # type: ignore[index]
    cohorts: list[str] = data["cohorts"]  # type: ignore[index]
    orgs: list[str] = data["organizations"]  # type: ignore[index]
    teams: list[str] = data["teams"]  # type: ignore[index]
    projects: list[str] = data["projects"]  # type: ignore[index]
    budgets: list[str] = data["budget_names"]  # type: ignore[index]
    templates: list[str] = data["template_names"]  # type: ignore[index]
    admins: list[str] = data["admin_display_names"]  # type: ignore[index]

    def assign(
        ids: Sequence[str], names: list[str], salt: bytes
    ) -> dict[str, str]:
        offset = _rotation(seed, salt, len(names))
        out: dict[str, str] = {}
        for i, old in enumerate(sorted(ids)):
            out[old] = names[(i + offset) % len(names)] + _suffix(i, len(names))
        return out

    owner_name: dict[str, str] = {}
    owner_surname: dict[str, str] = {}
    owner_email: dict[str, str] = {}
    firsts_off = _rotation(seed, b"owner-first", len(firsts))
    lasts_off = _rotation(seed, b"owner-last", len(lasts))
    domains_off = _rotation(seed, b"owner-domain", len(domains))
    combos = len(firsts) * len(lasts)
    for i, old in enumerate(sorted(owner_ids)):
        first = firsts[(i + firsts_off) % len(firsts)]
        last = lasts[(i // len(firsts) + lasts_off) % len(lasts)]
        k = i // combos
        suffix = f" {k + 1}" if k else ""
        owner_name[old] = first
        owner_surname[old] = last + suffix
        owner_email[old] = (
            f"{first.lower()}.{last.lower()}{'' if not suffix else '-' + str(k + 1)}"
            f"@{domains[(i + domains_off) % len(domains)]}"
        )

    admin_off = _rotation(seed, b"admin-email", len(domains))
    return _IdentityMaps(
        seed=seed,
        owner_name=owner_name,
        owner_surname=owner_surname,
        owner_email=owner_email,
        institution_name=assign(institution_ids, insts, b"inst"),
        cohort_name=assign(cohort_ids, cohorts, b"cohort"),
        org_name=assign(org_ids, orgs, b"org"),
        org_slug={old: f"demo-org-{i + 1}" for i, old in enumerate(sorted(org_ids))},
        team_name=assign(team_ids, teams, b"team"),
        team_slug={old: f"demo-team-{i + 1}" for i, old in enumerate(sorted(team_ids))},
        project_name=assign(project_ids, projects, b"project"),
        project_slug={old: f"demo-project-{i + 1}" for i, old in enumerate(sorted(project_ids))},
        budget_name=assign(budget_ids, budgets, b"budget"),
        template_name=assign(template_ids, templates, b"template"),
        admin_name=assign(admin_ids, admins, b"admin-name"),
        admin_email={
            old: f"admin-{i + 1}@{domains[(i + admin_off) % len(domains)]}"
            for i, old in enumerate(sorted(admin_ids))
        },
    )

# ---------------------------------------------------------------------------
# Reviewed field policy: EVERY public table, EVERY column (222 checkpoint,
# migration head 0027). Actions:
#   P    preserve (descriptive value: quantities, times, statuses, choices)
#   U    per-copy UUID remap (global bijection; preserves FK links)
#   S    per-copy string-identifier remap (request ids, hashes, provider ids)
#   H    per-copy bare 64-hex remap, no prefix (columns CHECK-constrained
#        to ^[0-9a-f]{64}$; the column name is the per-column salt)
#   FTN  fixed fictional client tool name; NULL only for the item kinds
#        whose reviewed kind_shape CHECK requires NULL
#   FN   fixed fictional client tool namespace (same row condition as FTN)
#   N    set NULL (free text that may leak; column must be nullable)
#   F:<k>  fixed fictional value from demo_identities.json key <k>
#   FC:<k> fixed credential-invalidation dummy from the data file
#   J0   arbitrary/credential-bearing JSONB -> {}
#   JA   arbitrary JSONB array -> []
#   JJ   typed-safe JSONB (reviewed: product enums/counts only) -> preserved
#   JU   JSONB arrays of UUIDs -> every UUID element remapped, shape kept
#   KR   gateway_keys.metadata clone receipt: ordinary metadata -> {};
#        a recognized, well-formed 208 clone receipt -> a typed
#        allowlisted projection (UUIDs/public-id/fingerprints remapped
#        per copy; display status + bounded nonsecret validity preserved);
#        malformed/unknown/secret-bearing receipts fail closed
#   IP   fixed fictional IP (deterministic per row)
#   UA   fixed fictional user agent
#   E_*  entity-bound fictional value (per-copy entity map; NULL-safe)
# ---------------------------------------------------------------------------

P = "P"
U = "U"
S = "S"
H = "H"
FTN = "FTN"
FN = "FN"
N = "N"
J0 = "J0"
JA = "JA"
JJ = "JJ"
# RC   route capabilities: typed per-group transform of the INSTALLED
#      model_routes.capabilities grammar (booleans/numbers/enums
#      preserved; completion_service.profile fictionalized per copy;
#      compaction route UUIDs remapped to the copied route ids).
#      Transport groups (local_coding/local_coding_vllm/upstream_llm)
#      fail closed (documented limit).
RC = "RC"
JU = "JU"
KR = "KR"
IP = "IP"
UA = "UA"
F = "F:"
FC = "FC:"
E_OWNER_NAME = "E_OWNER_NAME"
E_OWNER_SURNAME = "E_OWNER_SURNAME"
E_OWNER_EMAIL = "E_OWNER_EMAIL"
E_OWNER_SNAP_NAME = "E_OWNER_SNAP_NAME"
E_OWNER_SNAP_SURNAME = "E_OWNER_SNAP_SURNAME"
E_OWNER_SNAP_EMAIL = "E_OWNER_SNAP_EMAIL"
E_INST_NAME = "E_INST_NAME"
E_INST_SNAP_NAME = "E_INST_SNAP_NAME"
E_COHORT_NAME = "E_COHORT_NAME"
E_COHORT_SNAP_NAME = "E_COHORT_SNAP_NAME"
E_ORG_NAME = "E_ORG_NAME"
E_ORG_SLUG = "E_ORG_SLUG"
E_TEAM_NAME = "E_TEAM_NAME"
E_TEAM_SLUG = "E_TEAM_SLUG"
E_PROJ_NAME = "E_PROJ_NAME"
E_PROJ_SLUG = "E_PROJ_SLUG"
E_BUDGET_NAME = "E_BUDGET_NAME"
E_TPL_NAME = "E_TPL_NAME"
E_ADMIN_NAME = "E_ADMIN_NAME"
E_ADMIN_EMAIL = "E_ADMIN_EMAIL"

TABLE_POLICY: dict[str, dict[str, str]] = {
    "alembic_version": {
        "version_num": P,
    },
    "owners": {
        "id": U,
        "name": E_OWNER_NAME,
        "surname": E_OWNER_SURNAME,
        "email": E_OWNER_EMAIL,
        "institution_id": U,
        "external_id": S,
        "notes": N,
        "is_active": P,
        "anonymized_at": P,
        "created_at": P,
        "updated_at": P,
    },
    "institutions": {
        "id": U,
        "name": E_INST_NAME,
        "country": P,
        "notes": N,
        "created_at": P,
        "updated_at": P,
        "organization_id": U,
    },
    "cohorts": {
        "id": U,
        "name": E_COHORT_NAME,
        "description": N,
        "starts_at": P,
        "ends_at": P,
        "created_at": P,
        "updated_at": P,
        "project_id": U,
    },
    "organizations": {
        "id": U,
        "name": E_ORG_NAME,
        "slug": E_ORG_SLUG,
        "notes": N,
        "created_at": P,
        "updated_at": P,
    },
    "teams": {
        "id": U,
        "organization_id": U,
        "name": E_TEAM_NAME,
        "slug": E_TEAM_SLUG,
        "notes": N,
        "created_at": P,
        "updated_at": P,
    },
    "projects": {
        "id": U,
        "team_id": U,
        "name": E_PROJ_NAME,
        "slug": E_PROJ_SLUG,
        "description": N,
        "starts_at": P,
        "ends_at": P,
        "created_at": P,
        "updated_at": P,
    },
    "team_members": {
        "team_id": U,
        "owner_id": U,
        "role": P,
        "created_at": P,
    },
    "oidc_identities": {
        "id": U,
        "owner_id": U,
        "issuer_url": F + "issuer_url",
        "subject": S,
        "email": E_OWNER_EMAIL,
        "created_at": P,
    },
    "admin_users": {
        "id": U,
        "email": E_ADMIN_EMAIL,
        "display_name": E_ADMIN_NAME,
        "password_hash": FC + "dummy_password_hash",
        "role": P,
        "is_active": P,
        "last_login_at": P,
        "created_at": P,
        "updated_at": P,
        "mfa_secret": N,
    },
    "admin_sessions": {
        "id": U,
        "admin_user_id": U,
        "session_token_hash": S,
        "csrf_token_hash": S,
        "ip_address": IP,
        "user_agent": UA,
        "expires_at": P,
        "revoked_at": P,
        "created_at": P,
        "last_seen_at": P,
    },
    "gateway_keys": {
        "id": U,
        "public_key_id": S,
        # Configurable operator prefix may carry an organization slug and
        # renders verbatim in admin key pages: fixed fictional demo prefix.
        "key_prefix": F + "demo_key_prefix",
        "key_hint": FC + "dummy_key_hint",
        "token_hash": S,
        "hash_algorithm": P,
        "hmac_key_version": P,
        "owner_id": U,
        "cohort_id": U,
        "status": P,
        "valid_from": P,
        "valid_until": P,
        "cost_limit_eur": P,
        "token_limit_total": P,
        "request_limit_total": P,
        "cost_used_eur": P,
        "tokens_used_total": P,
        "requests_used_total": P,
        "cost_reserved_eur": P,
        "tokens_reserved_total": P,
        "requests_reserved_total": P,
        "rate_limit_requests_per_minute": P,
        "rate_limit_tokens_per_minute": P,
        "max_concurrent_requests": P,
        "allow_all_models": P,
        "allowed_models": JJ,
        "allow_all_endpoints": P,
        "allowed_endpoints": JJ,
        "metadata": KR,
        "last_used_at": P,
        "last_quota_reset_at": P,
        "quota_reset_count": P,
        "created_by_admin_user_id": U,
        "created_at": P,
        "updated_at": P,
        "revoked_at": P,
        "revoked_reason": N,
        "key_purpose": P,
        "capability_policy_mode": P,
        "calibration_metadata": J0,
        "template_id": U,
        "template_revision_id": U,
        "external_tool_fence_state": P,
        "external_tool_fence_reservation_id": U,
        "external_tool_fence_request_id": S,
        "external_tool_fence_acquired_at": P,
        "external_tool_fence_expires_at": P,
        "service_owner_id": U,
        "service_name": N,
        "rotated_at": P,
        "max_validity_days": P,
    },
    "quota_reservations": {
        "id": U,
        "gateway_key_id": U,
        "request_id": S,
        "endpoint": P,
        "requested_model": P,
        "reserved_cost_eur": P,
        "reserved_tokens": P,
        "reserved_requests": P,
        "status": P,
        "created_at": P,
        "expires_at": P,
        "finalized_at": P,
        "released_at": P,
        "quota_mode": P,
        "external_tool_capabilities": JJ,
        "external_tool_destination_ids": JU,
        "external_tool_provider": P,
        "external_tool_route_id": U,
        "provider": P,
        "resolved_model": P,
        "streaming": P,
    },
    "usage_ledger": {
        "id": U,
        "request_id": S,
        "client_request_id": S,
        "idempotency_key": S,
        "quota_reservation_id": U,
        "gateway_key_id": U,
        "owner_id": U,
        "institution_id": U,
        "cohort_id": U,
        "owner_email_snapshot": E_OWNER_SNAP_EMAIL,
        "owner_name_snapshot": E_OWNER_SNAP_NAME,
        "owner_surname_snapshot": E_OWNER_SNAP_SURNAME,
        "institution_name_snapshot": E_INST_SNAP_NAME,
        "cohort_name_snapshot": E_COHORT_SNAP_NAME,
        "endpoint": P,
        "http_method": P,
        "provider": P,
        "requested_model": P,
        "resolved_model": P,
        "upstream_request_id": S,
        "streaming": P,
        "success": P,
        "accounting_status": P,
        "http_status": P,
        "error_type": N,
        "error_message": N,
        "prompt_tokens": P,
        "completion_tokens": P,
        "input_tokens": P,
        "output_tokens": P,
        "cached_tokens": P,
        "reasoning_tokens": P,
        "total_tokens": P,
        "estimated_cost_eur": P,
        "actual_cost_eur": P,
        "actual_cost_native": P,
        "native_currency": P,
        "usage_raw": J0,
        "response_metadata": J0,
        "started_at": P,
        "finished_at": P,
        "latency_ms": P,
        "created_at": P,
    },
    "usage_profiles": {
        "id": U,
        "usage_ledger_id": U,
        "gateway_key_id": U,
        "owner_id": U,
        "institution_id": U,
        "cohort_id": U,
        "endpoint_path": P,
        "provider": P,
        "requested_model": P,
        "resolved_upstream_model": P,
        "provider_host": F + "provider_host",
        "provider_endpoint_path": P,
        "input_tokens": P,
        "output_tokens": P,
        "total_tokens": P,
        "reasoning_tokens": P,
        "cached_tokens": P,
        "tool_call_counts": J0,
        "function_tool_names": JA,
        "provider_reported_cost": P,
        "slaif_calculated_cost": P,
        "cost_currency": P,
        "cost_source": P,
        "gateway_request_id": S,
        "profile_metadata": J0,
        "created_at": P,
    },
    "response_references": {
        "id": U,
        "provider_response_id": S,
        "gateway_key_id": U,
        "owner_id": U,
        "institution_id": U,
        "cohort_id": U,
        "provider": P,
        "requested_model": P,
        "upstream_model": P,
        "endpoint": P,
        "route_id": U,
        "status": P,
        "provider_request_id": S,
        "expires_at": P,
        "deleted_at": P,
        "metadata": J0,
        "created_at": P,
        "updated_at": P,
    },
    "conversation_references": {
        "id": U,
        "provider_conversation_id": S,
        "gateway_key_id": U,
        "owner_id": U,
        "institution_id": U,
        "cohort_id": U,
        "provider": P,
        "endpoint": P,
        "route_id": U,
        "status": P,
        "provider_request_id": S,
        "deleted_at": P,
        "metadata": J0,
        "created_at": P,
        "updated_at": P,
    },
    "codex_replay_references": {
        "id": U,
        "gateway_key_id": U,
        "usage_ledger_id": U,
        "source_request_id": S,
        "provider": P,
        "route_id": U,
        "upstream_model": P,
        "item_kind": P,
        # CHECK-constrained to bare 64-hex (see remap_hex64): the generic
        # prefixed S remap would violate the reviewed constraint.
        "item_id_hmac": H,
        "call_id_hmac": H,
        "hmac_key_version": P,
        # Client/organization-specific copied free text potentially
        # visible through demo data access: fixed fictional namespace
        # (see FN).
        "tool_namespace": FN,
        # Free-text client tool name: one fixed fictional value, NULL only
        # where the kind_shape CHECK requires NULL (see FTN).
        "tool_name": FTN,
        "created_at": P,
        "expires_at": P,
    },
    "provider_configs": {
        "id": U,
        "provider": P,
        "display_name": F + "provider_display_name",
        "kind": P,
        "base_url": F + "provider_base_url",
        "api_key_env_var": F + "api_key_env_var",
        "enabled": P,
        "timeout_seconds": P,
        "max_retries": P,
        "notes": N,
        "created_at": P,
        "updated_at": P,
        "governance_region": N,
        "retention_policy": N,
        "training_use": P,
        "zdr_claimed": P,
        "tool_destinations": J0,
        "evidence_date": P,
        "reviewer": F + "reviewer_name",
    },
    "model_routes": {
        "id": U,
        "requested_model": P,
        "match_type": P,
        "endpoint": P,
        "provider": P,
        "upstream_model": P,
        "priority": P,
        "enabled": P,
        "visible_in_models": P,
        "supports_streaming": P,
        "capabilities": RC,
        "notes": N,
        "created_at": P,
        "updated_at": P,
    },
    "pricing_rules": {
        "id": U,
        "provider": P,
        "upstream_model": P,
        "endpoint": P,
        "currency": P,
        "input_price_per_1m": P,
        "cached_input_price_per_1m": P,
        "output_price_per_1m": P,
        "reasoning_price_per_1m": P,
        "request_price": P,
        "pricing_metadata": J0,
        "valid_from": P,
        "valid_until": P,
        "enabled": P,
        "source_url": F + "pricing_source_url",
        "notes": N,
        "created_at": P,
        "updated_at": P,
    },
    "fx_rates": {
        "id": U,
        "base_currency": P,
        "quote_currency": P,
        "rate": P,
        "valid_from": P,
        "valid_until": P,
        "source": F + "fx_source",
        "created_at": P,
    },
    "one_time_secrets": {
        "id": U,
        "purpose": P,
        "owner_id": U,
        "gateway_key_id": U,
        "encrypted_payload": FC + "dummy_encrypted_payload",
        "nonce": FC + "dummy_nonce",
        "encryption_key_version": P,
        "expires_at": P,
        "consumed_at": P,
        "status": P,
        "created_at": P,
    },
    "email_deliveries": {
        "id": U,
        "owner_id": U,
        "gateway_key_id": U,
        "one_time_secret_id": U,
        "recipient_email": E_OWNER_EMAIL,
        "subject": F + "generic_subject",
        "template_name": P,
        "status": P,
        "provider_message_id": S,
        "error_message": N,
        "created_at": P,
        "sent_at": P,
        "failed_at": P,
    },
    "audit_log": {
        "id": U,
        "admin_user_id": U,
        "action": P,
        "entity_type": P,
        "entity_id": U,
        "old_values": J0,
        "new_values": J0,
        "ip_address": IP,
        "user_agent": UA,
        "request_id": S,
        "note": N,
        "created_at": P,
    },
    "background_jobs": {
        "id": U,
        "celery_task_id": S,
        "job_type": F + "job_type_value",
        "status": P,
        "created_by_admin_user_id": U,
        "payload_summary": J0,
        "result_summary": J0,
        "error_message": N,
        "created_at": P,
        "started_at": P,
        "finished_at": P,
    },
    "budget_periods": {
        "id": U,
        "organization_id": U,
        "team_id": U,
        "project_id": U,
        "owner_id": U,
        "service_account_id": U,
        "name": E_BUDGET_NAME,
        "period_type": P,
        "period_start": P,
        "period_end": P,
        "cost_limit_eur": P,
        "token_limit_total": P,
        "request_limit_total": P,
        "cost_used_eur": P,
        "tokens_used_total": P,
        "requests_used_total": P,
        "cost_reserved_eur": P,
        "tokens_reserved_total": P,
        "requests_reserved_total": P,
        "carryover_policy": P,
        "created_at": P,
        "updated_at": P,
    },
    "policy_bundles": {
        "id": U,
        "organization_id": U,
        "team_id": U,
        "project_id": U,
        "name": S,
        "created_at": P,
    },
    "policy_bundle_revisions": {
        "id": U,
        "bundle_id": U,
        "revision": P,
        "policy_json": J0,
        "created_at": P,
    },
    "approved_catalog_entries": {
        "id": U,
        "revision_id": U,
        "entry_kind": P,
        "provider": P,
        "name": S,
        "metadata_json": J0,
        "created_at": P,
    },
    "catalog_refresh_applications": {
        "id": U,
        "run_id": S,
        "bundle_sha256": S,
        "receipt_hmac_sha256": S,
        "plan_sha256": S,
        "mode": P,
        "operator_actor": S,
        "db_actor": S,
        "admin_user_id": U,
        # NOT NULL column: a NULL would abort the transaction; the fixed
        # fictional note removes the operator reason safely.
        "reason": F + "generic_note",
        "effective_at": P,
        "applied_provider_ids": JU,
        "applied_route_ids": JU,
        "applied_pricing_created_ids": JU,
        "applied_pricing_superseded_old_ids": JU,
        "applied_pricing_superseded_new_ids": JU,
        "applied_fx_created_ids": JU,
        "applied_fx_superseded_old_ids": JU,
        "applied_fx_superseded_new_ids": JU,
        "created_providers": P,
        "created_routes": P,
        "created_pricing": P,
        "created_fx": P,
        "superseded_pricing": P,
        "superseded_fx": P,
        "outcome": P,
        "created_at": P,
    },
    "request_diagnostics": {
        "id": U,
        "gateway_request_id": S,
        "client_request_id": S,
        "client_id_unavailable_reason": P,
        "method": P,
        "endpoint_template": P,
        "occurred_at": P,
        "http_status": P,
        "stream_outcome": P,
        "source": P,
        "reason_code": P,
        "error_code": P,
        "error_param": N,
        "positions": N,
        "counts": N,
        "limits": N,
        "gateway_key_id": U,
        "route_id": U,
        "route_pattern": P,
        "deployment_revision": F + "deployment_revision",
        "estimated_input_tokens": P,
        "output_allowance_tokens": P,
        "context_window_tokens": P,
        "replay_error_code": P,
        "recorded_at": P,
    },
    "key_templates": {
        "id": U,
        "name": E_TPL_NAME,
        "description": N,
        "status": P,
        "created_by_admin_id": U,
        "created_at": P,
        "updated_at": P,
        "archived_at": P,
        "archived_by_admin_id": U,
        "notes": N,
        "current_revision_id": U,
    },
    "key_template_revisions": {
        "id": U,
        "template_id": U,
        "revision_number": P,
        "created_by_admin_id": U,
        "created_at": P,
        "source_type": P,
        "source_calibration_gateway_key_id": U,
        "source_time_window_start": P,
        "source_time_window_end": P,
        "source_multiplier": P,
        "allowed_endpoints": JJ,
        "allowed_models": JJ,
        "allowed_providers": JJ,
        "allowed_hosted_capabilities": JJ,
        "hosted_capabilities_requiring_review": JJ,
        "request_limit_total": P,
        "token_limit_total": P,
        "input_token_limit_total": P,
        "output_token_limit_total": P,
        "reasoning_token_limit_total": P,
        "cost_limit_eur": P,
        "max_input_tokens_per_request": P,
        "max_output_tokens_per_request": P,
        "max_total_tokens_per_request": P,
        "max_single_request_cost_eur": P,
        "rate_limit_policy": JJ,
        "validity_days_default": P,
        "email_delivery_mode_default": P,
        "template_snapshot": J0,
        "created_audit_log_id": U,
    },
}

# The restored copy may contain exactly these extensions (plpgsql is the
# server default; citext and pgcrypto travel in the 221 archive) and these
# public custom types (the table composite types are implied by the tables).
_EXPECTED_EXTENSIONS = frozenset({"plpgsql", "citext", "pgcrypto"})
_EXPECTED_EXTRA_PUBLIC_TYPES = frozenset({"citext", "_citext"})

# ---------------------------------------------------------------------------
# Reviewed 222 checkpoint catalog signature (migration head
# 0027_demo_admin_accounts). The sanitizer verifies a RESTORED copy, so
# this signature is pinned from the owned PG16 16.15 scratch restore of
# the 222 checkpoint (217 public constraints, 34 tables, 507 columns),
# not from live-source formatting.
#
# Documented source-vs-restored differences: pg_dump/pg_restore rewrites
# exactly two varchar ANY-array CHECK expressions
# (request_diagnostics_client_id_unavailable_reason_allowed and
# request_diagnostics_stream_outcome_allowed) into an element-wise cast
# form; the constraint meaning and every other definition are unchanged.
# The reviewed digest below therefore contains the restored form.
# ---------------------------------------------------------------------------

#: (full SQL type via format_type(atttypid, atttypmod), nullable) for
#: every public column at the 222 checkpoint.
_COLUMN_SIGNATURE: dict[str, tuple[str, bool]] = {
    "admin_sessions.id": ("uuid", False),
    "admin_sessions.admin_user_id": ("uuid", False),
    "admin_sessions.session_token_hash": ("text", False),
    "admin_sessions.csrf_token_hash": ("text", False),
    "admin_sessions.ip_address": ("inet", True),
    "admin_sessions.user_agent": ("text", True),
    "admin_sessions.expires_at": ("timestamp with time zone", False),
    "admin_sessions.revoked_at": ("timestamp with time zone", True),
    "admin_sessions.created_at": ("timestamp with time zone", False),
    "admin_sessions.last_seen_at": ("timestamp with time zone", True),
    "admin_users.id": ("uuid", False),
    "admin_users.email": ("citext", False),
    "admin_users.display_name": ("text", False),
    "admin_users.password_hash": ("text", False),
    "admin_users.role": ("text", False),
    "admin_users.is_active": ("boolean", False),
    "admin_users.last_login_at": ("timestamp with time zone", True),
    "admin_users.created_at": ("timestamp with time zone", False),
    "admin_users.updated_at": ("timestamp with time zone", False),
    "admin_users.mfa_secret": ("text", True),
    "alembic_version.version_num": ("character varying(255)", False),
    "approved_catalog_entries.id": ("uuid", False),
    "approved_catalog_entries.revision_id": ("uuid", False),
    "approved_catalog_entries.entry_kind": ("text", False),
    "approved_catalog_entries.provider": ("text", False),
    "approved_catalog_entries.name": ("text", False),
    "approved_catalog_entries.metadata_json": ("jsonb", False),
    "approved_catalog_entries.created_at": ("timestamp with time zone", False),
    "audit_log.id": ("uuid", False),
    "audit_log.admin_user_id": ("uuid", True),
    "audit_log.action": ("text", False),
    "audit_log.entity_type": ("text", False),
    "audit_log.entity_id": ("uuid", True),
    "audit_log.old_values": ("jsonb", True),
    "audit_log.new_values": ("jsonb", True),
    "audit_log.ip_address": ("inet", True),
    "audit_log.user_agent": ("text", True),
    "audit_log.request_id": ("text", True),
    "audit_log.note": ("text", True),
    "audit_log.created_at": ("timestamp with time zone", False),
    "background_jobs.id": ("uuid", False),
    "background_jobs.celery_task_id": ("text", True),
    "background_jobs.job_type": ("text", False),
    "background_jobs.status": ("text", False),
    "background_jobs.created_by_admin_user_id": ("uuid", True),
    "background_jobs.payload_summary": ("jsonb", False),
    "background_jobs.result_summary": ("jsonb", False),
    "background_jobs.error_message": ("text", True),
    "background_jobs.created_at": ("timestamp with time zone", False),
    "background_jobs.started_at": ("timestamp with time zone", True),
    "background_jobs.finished_at": ("timestamp with time zone", True),
    "budget_periods.id": ("uuid", False),
    "budget_periods.organization_id": ("uuid", True),
    "budget_periods.team_id": ("uuid", True),
    "budget_periods.project_id": ("uuid", True),
    "budget_periods.owner_id": ("uuid", True),
    "budget_periods.service_account_id": ("uuid", True),
    "budget_periods.name": ("text", False),
    "budget_periods.period_type": ("text", False),
    "budget_periods.period_start": ("timestamp with time zone", False),
    "budget_periods.period_end": ("timestamp with time zone", False),
    "budget_periods.cost_limit_eur": ("numeric(18,9)", True),
    "budget_periods.token_limit_total": ("bigint", True),
    "budget_periods.request_limit_total": ("bigint", True),
    "budget_periods.cost_used_eur": ("numeric(18,9)", False),
    "budget_periods.tokens_used_total": ("bigint", False),
    "budget_periods.requests_used_total": ("bigint", False),
    "budget_periods.cost_reserved_eur": ("numeric(18,9)", False),
    "budget_periods.tokens_reserved_total": ("bigint", False),
    "budget_periods.requests_reserved_total": ("bigint", False),
    "budget_periods.carryover_policy": ("text", False),
    "budget_periods.created_at": ("timestamp with time zone", False),
    "budget_periods.updated_at": ("timestamp with time zone", False),
    "catalog_refresh_applications.id": ("uuid", False),
    "catalog_refresh_applications.run_id": ("text", False),
    "catalog_refresh_applications.bundle_sha256": ("text", False),
    "catalog_refresh_applications.receipt_hmac_sha256": ("text", False),
    "catalog_refresh_applications.plan_sha256": ("text", False),
    "catalog_refresh_applications.mode": ("text", False),
    "catalog_refresh_applications.operator_actor": ("text", False),
    "catalog_refresh_applications.db_actor": ("text", False),
    "catalog_refresh_applications.admin_user_id": ("uuid", True),
    "catalog_refresh_applications.reason": ("text", False),
    "catalog_refresh_applications.effective_at": ("timestamp with time zone", False),
    "catalog_refresh_applications.applied_provider_ids": ("jsonb", False),
    "catalog_refresh_applications.applied_route_ids": ("jsonb", False),
    "catalog_refresh_applications.applied_pricing_created_ids": ("jsonb", False),
    "catalog_refresh_applications.applied_pricing_superseded_old_ids": ("jsonb", False),
    "catalog_refresh_applications.applied_pricing_superseded_new_ids": ("jsonb", False),
    "catalog_refresh_applications.applied_fx_created_ids": ("jsonb", False),
    "catalog_refresh_applications.applied_fx_superseded_old_ids": ("jsonb", False),
    "catalog_refresh_applications.applied_fx_superseded_new_ids": ("jsonb", False),
    "catalog_refresh_applications.created_providers": ("integer", False),
    "catalog_refresh_applications.created_routes": ("integer", False),
    "catalog_refresh_applications.created_pricing": ("integer", False),
    "catalog_refresh_applications.created_fx": ("integer", False),
    "catalog_refresh_applications.superseded_pricing": ("integer", False),
    "catalog_refresh_applications.superseded_fx": ("integer", False),
    "catalog_refresh_applications.outcome": ("text", False),
    "catalog_refresh_applications.created_at": ("timestamp with time zone", False),
    "codex_replay_references.id": ("uuid", False),
    "codex_replay_references.gateway_key_id": ("uuid", False),
    "codex_replay_references.usage_ledger_id": ("uuid", False),
    "codex_replay_references.source_request_id": ("text", False),
    "codex_replay_references.provider": ("text", False),
    "codex_replay_references.route_id": ("uuid", False),
    "codex_replay_references.upstream_model": ("text", False),
    "codex_replay_references.item_kind": ("text", False),
    "codex_replay_references.item_id_hmac": ("character varying(64)", False),
    "codex_replay_references.call_id_hmac": ("character varying(64)", True),
    "codex_replay_references.hmac_key_version": ("integer", False),
    "codex_replay_references.tool_namespace": ("text", True),
    "codex_replay_references.tool_name": ("text", True),
    "codex_replay_references.created_at": ("timestamp with time zone", False),
    "codex_replay_references.expires_at": ("timestamp with time zone", False),
    "cohorts.id": ("uuid", False),
    "cohorts.name": ("text", False),
    "cohorts.description": ("text", True),
    "cohorts.starts_at": ("timestamp with time zone", True),
    "cohorts.ends_at": ("timestamp with time zone", True),
    "cohorts.created_at": ("timestamp with time zone", False),
    "cohorts.updated_at": ("timestamp with time zone", False),
    "cohorts.project_id": ("uuid", True),
    "conversation_references.id": ("uuid", False),
    "conversation_references.provider_conversation_id": ("text", False),
    "conversation_references.gateway_key_id": ("uuid", False),
    "conversation_references.owner_id": ("uuid", True),
    "conversation_references.institution_id": ("uuid", True),
    "conversation_references.cohort_id": ("uuid", True),
    "conversation_references.provider": ("text", False),
    "conversation_references.endpoint": ("text", False),
    "conversation_references.route_id": ("uuid", True),
    "conversation_references.status": ("text", False),
    "conversation_references.provider_request_id": ("text", True),
    "conversation_references.deleted_at": ("timestamp with time zone", True),
    "conversation_references.metadata": ("jsonb", False),
    "conversation_references.created_at": ("timestamp with time zone", False),
    "conversation_references.updated_at": ("timestamp with time zone", False),
    "email_deliveries.id": ("uuid", False),
    "email_deliveries.owner_id": ("uuid", True),
    "email_deliveries.gateway_key_id": ("uuid", True),
    "email_deliveries.one_time_secret_id": ("uuid", True),
    "email_deliveries.recipient_email": ("citext", False),
    "email_deliveries.subject": ("text", False),
    "email_deliveries.template_name": ("text", False),
    "email_deliveries.status": ("text", False),
    "email_deliveries.provider_message_id": ("text", True),
    "email_deliveries.error_message": ("text", True),
    "email_deliveries.created_at": ("timestamp with time zone", False),
    "email_deliveries.sent_at": ("timestamp with time zone", True),
    "email_deliveries.failed_at": ("timestamp with time zone", True),
    "fx_rates.id": ("uuid", False),
    "fx_rates.base_currency": ("text", False),
    "fx_rates.quote_currency": ("text", False),
    "fx_rates.rate": ("numeric(18,9)", False),
    "fx_rates.valid_from": ("timestamp with time zone", False),
    "fx_rates.valid_until": ("timestamp with time zone", True),
    "fx_rates.source": ("text", True),
    "fx_rates.created_at": ("timestamp with time zone", False),
    "gateway_keys.id": ("uuid", False),
    "gateway_keys.public_key_id": ("text", False),
    "gateway_keys.key_prefix": ("text", False),
    "gateway_keys.key_hint": ("text", True),
    "gateway_keys.token_hash": ("text", False),
    "gateway_keys.hash_algorithm": ("text", False),
    "gateway_keys.hmac_key_version": ("integer", False),
    "gateway_keys.owner_id": ("uuid", False),
    "gateway_keys.cohort_id": ("uuid", True),
    "gateway_keys.status": ("text", False),
    "gateway_keys.valid_from": ("timestamp with time zone", False),
    "gateway_keys.valid_until": ("timestamp with time zone", False),
    "gateway_keys.cost_limit_eur": ("numeric(18,9)", True),
    "gateway_keys.token_limit_total": ("bigint", True),
    "gateway_keys.request_limit_total": ("bigint", True),
    "gateway_keys.cost_used_eur": ("numeric(18,9)", False),
    "gateway_keys.tokens_used_total": ("bigint", False),
    "gateway_keys.requests_used_total": ("bigint", False),
    "gateway_keys.cost_reserved_eur": ("numeric(18,9)", False),
    "gateway_keys.tokens_reserved_total": ("bigint", False),
    "gateway_keys.requests_reserved_total": ("bigint", False),
    "gateway_keys.rate_limit_requests_per_minute": ("integer", True),
    "gateway_keys.rate_limit_tokens_per_minute": ("bigint", True),
    "gateway_keys.max_concurrent_requests": ("integer", True),
    "gateway_keys.allow_all_models": ("boolean", False),
    "gateway_keys.allowed_models": ("jsonb", False),
    "gateway_keys.allow_all_endpoints": ("boolean", False),
    "gateway_keys.allowed_endpoints": ("jsonb", False),
    "gateway_keys.metadata": ("jsonb", False),
    "gateway_keys.last_used_at": ("timestamp with time zone", True),
    "gateway_keys.last_quota_reset_at": ("timestamp with time zone", True),
    "gateway_keys.quota_reset_count": ("integer", False),
    "gateway_keys.created_by_admin_user_id": ("uuid", True),
    "gateway_keys.created_at": ("timestamp with time zone", False),
    "gateway_keys.updated_at": ("timestamp with time zone", False),
    "gateway_keys.revoked_at": ("timestamp with time zone", True),
    "gateway_keys.revoked_reason": ("text", True),
    "gateway_keys.key_purpose": ("text", False),
    "gateway_keys.capability_policy_mode": ("text", False),
    "gateway_keys.calibration_metadata": ("jsonb", False),
    "gateway_keys.template_id": ("uuid", True),
    "gateway_keys.template_revision_id": ("uuid", True),
    "gateway_keys.external_tool_fence_state": ("text", False),
    "gateway_keys.external_tool_fence_reservation_id": ("uuid", True),
    "gateway_keys.external_tool_fence_request_id": ("text", True),
    "gateway_keys.external_tool_fence_acquired_at": ("timestamp with time zone", True),
    "gateway_keys.external_tool_fence_expires_at": ("timestamp with time zone", True),
    "gateway_keys.service_owner_id": ("uuid", True),
    "gateway_keys.service_name": ("text", True),
    "gateway_keys.rotated_at": ("timestamp with time zone", True),
    "gateway_keys.max_validity_days": ("integer", True),
    "institutions.id": ("uuid", False),
    "institutions.name": ("text", False),
    "institutions.country": ("text", True),
    "institutions.notes": ("text", True),
    "institutions.created_at": ("timestamp with time zone", False),
    "institutions.updated_at": ("timestamp with time zone", False),
    "institutions.organization_id": ("uuid", True),
    "key_template_revisions.id": ("uuid", False),
    "key_template_revisions.template_id": ("uuid", False),
    "key_template_revisions.revision_number": ("integer", False),
    "key_template_revisions.created_by_admin_id": ("uuid", True),
    "key_template_revisions.created_at": ("timestamp with time zone", False),
    "key_template_revisions.source_type": ("text", False),
    "key_template_revisions.source_calibration_gateway_key_id": ("uuid", True),
    "key_template_revisions.source_time_window_start": ("timestamp with time zone", True),
    "key_template_revisions.source_time_window_end": ("timestamp with time zone", True),
    "key_template_revisions.source_multiplier": ("numeric(18,9)", True),
    "key_template_revisions.allowed_endpoints": ("jsonb", False),
    "key_template_revisions.allowed_models": ("jsonb", False),
    "key_template_revisions.allowed_providers": ("jsonb", False),
    "key_template_revisions.allowed_hosted_capabilities": ("jsonb", False),
    "key_template_revisions.hosted_capabilities_requiring_review": ("jsonb", False),
    "key_template_revisions.request_limit_total": ("bigint", False),
    "key_template_revisions.token_limit_total": ("bigint", False),
    "key_template_revisions.input_token_limit_total": ("bigint", True),
    "key_template_revisions.output_token_limit_total": ("bigint", True),
    "key_template_revisions.reasoning_token_limit_total": ("bigint", True),
    "key_template_revisions.cost_limit_eur": ("numeric(18,9)", True),
    "key_template_revisions.max_input_tokens_per_request": ("bigint", True),
    "key_template_revisions.max_output_tokens_per_request": ("bigint", True),
    "key_template_revisions.max_total_tokens_per_request": ("bigint", True),
    "key_template_revisions.max_single_request_cost_eur": ("numeric(18,9)", True),
    "key_template_revisions.rate_limit_policy": ("jsonb", False),
    "key_template_revisions.validity_days_default": ("integer", True),
    "key_template_revisions.email_delivery_mode_default": ("text", True),
    "key_template_revisions.template_snapshot": ("jsonb", False),
    "key_template_revisions.created_audit_log_id": ("uuid", True),
    "key_templates.id": ("uuid", False),
    "key_templates.name": ("text", False),
    "key_templates.description": ("text", True),
    "key_templates.status": ("text", False),
    "key_templates.created_by_admin_id": ("uuid", True),
    "key_templates.created_at": ("timestamp with time zone", False),
    "key_templates.updated_at": ("timestamp with time zone", False),
    "key_templates.archived_at": ("timestamp with time zone", True),
    "key_templates.archived_by_admin_id": ("uuid", True),
    "key_templates.notes": ("text", True),
    "key_templates.current_revision_id": ("uuid", True),
    "model_routes.id": ("uuid", False),
    "model_routes.requested_model": ("text", False),
    "model_routes.match_type": ("text", False),
    "model_routes.endpoint": ("text", False),
    "model_routes.provider": ("text", False),
    "model_routes.upstream_model": ("text", False),
    "model_routes.priority": ("integer", False),
    "model_routes.enabled": ("boolean", False),
    "model_routes.visible_in_models": ("boolean", False),
    "model_routes.supports_streaming": ("boolean", False),
    "model_routes.capabilities": ("jsonb", False),
    "model_routes.notes": ("text", True),
    "model_routes.created_at": ("timestamp with time zone", False),
    "model_routes.updated_at": ("timestamp with time zone", False),
    "oidc_identities.id": ("uuid", False),
    "oidc_identities.owner_id": ("uuid", False),
    "oidc_identities.issuer_url": ("text", False),
    "oidc_identities.subject": ("text", False),
    "oidc_identities.email": ("text", False),
    "oidc_identities.created_at": ("timestamp with time zone", False),
    "one_time_secrets.id": ("uuid", False),
    "one_time_secrets.purpose": ("text", False),
    "one_time_secrets.owner_id": ("uuid", True),
    "one_time_secrets.gateway_key_id": ("uuid", True),
    "one_time_secrets.encrypted_payload": ("text", False),
    "one_time_secrets.nonce": ("text", False),
    "one_time_secrets.encryption_key_version": ("integer", False),
    "one_time_secrets.expires_at": ("timestamp with time zone", False),
    "one_time_secrets.consumed_at": ("timestamp with time zone", True),
    "one_time_secrets.status": ("text", False),
    "one_time_secrets.created_at": ("timestamp with time zone", False),
    "organizations.id": ("uuid", False),
    "organizations.name": ("text", False),
    "organizations.slug": ("text", False),
    "organizations.notes": ("text", True),
    "organizations.created_at": ("timestamp with time zone", False),
    "organizations.updated_at": ("timestamp with time zone", False),
    "owners.id": ("uuid", False),
    "owners.name": ("text", False),
    "owners.surname": ("text", False),
    "owners.email": ("citext", False),
    "owners.institution_id": ("uuid", True),
    "owners.external_id": ("text", True),
    "owners.notes": ("text", True),
    "owners.is_active": ("boolean", False),
    "owners.anonymized_at": ("timestamp with time zone", True),
    "owners.created_at": ("timestamp with time zone", False),
    "owners.updated_at": ("timestamp with time zone", False),
    "policy_bundle_revisions.id": ("uuid", False),
    "policy_bundle_revisions.bundle_id": ("uuid", False),
    "policy_bundle_revisions.revision": ("integer", False),
    "policy_bundle_revisions.policy_json": ("jsonb", False),
    "policy_bundle_revisions.created_at": ("timestamp with time zone", False),
    "policy_bundles.id": ("uuid", False),
    "policy_bundles.organization_id": ("uuid", False),
    "policy_bundles.team_id": ("uuid", True),
    "policy_bundles.project_id": ("uuid", True),
    "policy_bundles.name": ("text", False),
    "policy_bundles.created_at": ("timestamp with time zone", False),
    "pricing_rules.id": ("uuid", False),
    "pricing_rules.provider": ("text", False),
    "pricing_rules.upstream_model": ("text", False),
    "pricing_rules.endpoint": ("text", False),
    "pricing_rules.currency": ("text", False),
    "pricing_rules.input_price_per_1m": ("numeric(18,9)", True),
    "pricing_rules.cached_input_price_per_1m": ("numeric(18,9)", True),
    "pricing_rules.output_price_per_1m": ("numeric(18,9)", True),
    "pricing_rules.reasoning_price_per_1m": ("numeric(18,9)", True),
    "pricing_rules.request_price": ("numeric(18,9)", True),
    "pricing_rules.pricing_metadata": ("jsonb", False),
    "pricing_rules.valid_from": ("timestamp with time zone", False),
    "pricing_rules.valid_until": ("timestamp with time zone", True),
    "pricing_rules.enabled": ("boolean", False),
    "pricing_rules.source_url": ("text", True),
    "pricing_rules.notes": ("text", True),
    "pricing_rules.created_at": ("timestamp with time zone", False),
    "pricing_rules.updated_at": ("timestamp with time zone", False),
    "projects.id": ("uuid", False),
    "projects.team_id": ("uuid", False),
    "projects.name": ("text", False),
    "projects.slug": ("text", False),
    "projects.description": ("text", True),
    "projects.starts_at": ("timestamp with time zone", True),
    "projects.ends_at": ("timestamp with time zone", True),
    "projects.created_at": ("timestamp with time zone", False),
    "projects.updated_at": ("timestamp with time zone", False),
    "provider_configs.id": ("uuid", False),
    "provider_configs.provider": ("text", False),
    "provider_configs.display_name": ("text", False),
    "provider_configs.kind": ("text", False),
    "provider_configs.base_url": ("text", False),
    "provider_configs.api_key_env_var": ("text", False),
    "provider_configs.enabled": ("boolean", False),
    "provider_configs.timeout_seconds": ("integer", False),
    "provider_configs.max_retries": ("integer", False),
    "provider_configs.notes": ("text", True),
    "provider_configs.created_at": ("timestamp with time zone", False),
    "provider_configs.updated_at": ("timestamp with time zone", False),
    "provider_configs.governance_region": ("text", True),
    "provider_configs.retention_policy": ("text", True),
    "provider_configs.training_use": ("boolean", False),
    "provider_configs.zdr_claimed": ("boolean", False),
    "provider_configs.tool_destinations": ("jsonb", False),
    "provider_configs.evidence_date": ("timestamp with time zone", True),
    "provider_configs.reviewer": ("text", True),
    "quota_reservations.id": ("uuid", False),
    "quota_reservations.gateway_key_id": ("uuid", False),
    "quota_reservations.request_id": ("text", False),
    "quota_reservations.endpoint": ("text", False),
    "quota_reservations.requested_model": ("text", True),
    "quota_reservations.reserved_cost_eur": ("numeric(18,9)", False),
    "quota_reservations.reserved_tokens": ("bigint", False),
    "quota_reservations.reserved_requests": ("bigint", False),
    "quota_reservations.status": ("text", False),
    "quota_reservations.created_at": ("timestamp with time zone", False),
    "quota_reservations.expires_at": ("timestamp with time zone", False),
    "quota_reservations.finalized_at": ("timestamp with time zone", True),
    "quota_reservations.released_at": ("timestamp with time zone", True),
    "quota_reservations.quota_mode": ("text", False),
    "quota_reservations.external_tool_capabilities": ("jsonb", False),
    "quota_reservations.external_tool_destination_ids": ("jsonb", False),
    "quota_reservations.external_tool_provider": ("text", True),
    "quota_reservations.external_tool_route_id": ("uuid", True),
    "quota_reservations.provider": ("text", True),
    "quota_reservations.resolved_model": ("text", True),
    "quota_reservations.streaming": ("boolean", True),
    "request_diagnostics.id": ("uuid", False),
    "request_diagnostics.gateway_request_id": ("character varying(128)", False),
    "request_diagnostics.client_request_id": ("character varying(128)", True),
    "request_diagnostics.client_id_unavailable_reason": ("character varying(32)", True),
    "request_diagnostics.method": ("character varying(16)", False),
    "request_diagnostics.endpoint_template": ("character varying(256)", True),
    "request_diagnostics.occurred_at": ("timestamp with time zone", False),
    "request_diagnostics.http_status": ("integer", True),
    "request_diagnostics.stream_outcome": ("character varying(32)", False),
    "request_diagnostics.source": ("character varying(64)", True),
    "request_diagnostics.reason_code": ("character varying(64)", True),
    "request_diagnostics.error_code": ("character varying(64)", True),
    "request_diagnostics.error_param": ("character varying(64)", True),
    "request_diagnostics.positions": ("jsonb", True),
    "request_diagnostics.counts": ("jsonb", True),
    "request_diagnostics.limits": ("jsonb", True),
    "request_diagnostics.gateway_key_id": ("uuid", True),
    "request_diagnostics.route_id": ("uuid", True),
    "request_diagnostics.route_pattern": ("character varying(128)", True),
    "request_diagnostics.deployment_revision": ("character varying(128)", True),
    "request_diagnostics.estimated_input_tokens": ("bigint", True),
    "request_diagnostics.output_allowance_tokens": ("bigint", True),
    "request_diagnostics.context_window_tokens": ("bigint", True),
    "request_diagnostics.replay_error_code": ("character varying(64)", True),
    "request_diagnostics.recorded_at": ("timestamp with time zone", False),
    "response_references.id": ("uuid", False),
    "response_references.provider_response_id": ("text", False),
    "response_references.gateway_key_id": ("uuid", False),
    "response_references.owner_id": ("uuid", True),
    "response_references.institution_id": ("uuid", True),
    "response_references.cohort_id": ("uuid", True),
    "response_references.provider": ("text", False),
    "response_references.requested_model": ("text", True),
    "response_references.upstream_model": ("text", True),
    "response_references.endpoint": ("text", False),
    "response_references.route_id": ("uuid", True),
    "response_references.status": ("text", False),
    "response_references.provider_request_id": ("text", True),
    "response_references.expires_at": ("timestamp with time zone", True),
    "response_references.deleted_at": ("timestamp with time zone", True),
    "response_references.metadata": ("jsonb", False),
    "response_references.created_at": ("timestamp with time zone", False),
    "response_references.updated_at": ("timestamp with time zone", False),
    "team_members.team_id": ("uuid", False),
    "team_members.owner_id": ("uuid", False),
    "team_members.role": ("text", False),
    "team_members.created_at": ("timestamp with time zone", False),
    "teams.id": ("uuid", False),
    "teams.organization_id": ("uuid", False),
    "teams.name": ("text", False),
    "teams.slug": ("text", False),
    "teams.notes": ("text", True),
    "teams.created_at": ("timestamp with time zone", False),
    "teams.updated_at": ("timestamp with time zone", False),
    "usage_ledger.id": ("uuid", False),
    "usage_ledger.request_id": ("text", False),
    "usage_ledger.client_request_id": ("text", True),
    "usage_ledger.idempotency_key": ("text", True),
    "usage_ledger.quota_reservation_id": ("uuid", True),
    "usage_ledger.gateway_key_id": ("uuid", False),
    "usage_ledger.owner_id": ("uuid", True),
    "usage_ledger.institution_id": ("uuid", True),
    "usage_ledger.cohort_id": ("uuid", True),
    "usage_ledger.owner_email_snapshot": ("citext", True),
    "usage_ledger.owner_name_snapshot": ("text", True),
    "usage_ledger.owner_surname_snapshot": ("text", True),
    "usage_ledger.institution_name_snapshot": ("text", True),
    "usage_ledger.cohort_name_snapshot": ("text", True),
    "usage_ledger.endpoint": ("text", False),
    "usage_ledger.http_method": ("text", False),
    "usage_ledger.provider": ("text", False),
    "usage_ledger.requested_model": ("text", True),
    "usage_ledger.resolved_model": ("text", True),
    "usage_ledger.upstream_request_id": ("text", True),
    "usage_ledger.streaming": ("boolean", False),
    "usage_ledger.success": ("boolean", True),
    "usage_ledger.accounting_status": ("text", False),
    "usage_ledger.http_status": ("integer", True),
    "usage_ledger.error_type": ("text", True),
    "usage_ledger.error_message": ("text", True),
    "usage_ledger.prompt_tokens": ("bigint", False),
    "usage_ledger.completion_tokens": ("bigint", False),
    "usage_ledger.input_tokens": ("bigint", False),
    "usage_ledger.output_tokens": ("bigint", False),
    "usage_ledger.cached_tokens": ("bigint", False),
    "usage_ledger.reasoning_tokens": ("bigint", False),
    "usage_ledger.total_tokens": ("bigint", False),
    "usage_ledger.estimated_cost_eur": ("numeric(18,9)", True),
    "usage_ledger.actual_cost_eur": ("numeric(18,9)", True),
    "usage_ledger.actual_cost_native": ("numeric(18,9)", True),
    "usage_ledger.native_currency": ("text", True),
    "usage_ledger.usage_raw": ("jsonb", False),
    "usage_ledger.response_metadata": ("jsonb", False),
    "usage_ledger.started_at": ("timestamp with time zone", False),
    "usage_ledger.finished_at": ("timestamp with time zone", True),
    "usage_ledger.latency_ms": ("integer", True),
    "usage_ledger.created_at": ("timestamp with time zone", False),
    "usage_profiles.id": ("uuid", False),
    "usage_profiles.usage_ledger_id": ("uuid", False),
    "usage_profiles.gateway_key_id": ("uuid", False),
    "usage_profiles.owner_id": ("uuid", True),
    "usage_profiles.institution_id": ("uuid", True),
    "usage_profiles.cohort_id": ("uuid", True),
    "usage_profiles.endpoint_path": ("text", False),
    "usage_profiles.provider": ("text", False),
    "usage_profiles.requested_model": ("text", True),
    "usage_profiles.resolved_upstream_model": ("text", True),
    "usage_profiles.provider_host": ("text", True),
    "usage_profiles.provider_endpoint_path": ("text", True),
    "usage_profiles.input_tokens": ("bigint", False),
    "usage_profiles.output_tokens": ("bigint", False),
    "usage_profiles.total_tokens": ("bigint", False),
    "usage_profiles.reasoning_tokens": ("bigint", True),
    "usage_profiles.cached_tokens": ("bigint", True),
    "usage_profiles.tool_call_counts": ("jsonb", False),
    "usage_profiles.function_tool_names": ("jsonb", False),
    "usage_profiles.provider_reported_cost": ("numeric(18,9)", True),
    "usage_profiles.slaif_calculated_cost": ("numeric(18,9)", True),
    "usage_profiles.cost_currency": ("text", True),
    "usage_profiles.cost_source": ("text", False),
    "usage_profiles.gateway_request_id": ("text", True),
    "usage_profiles.profile_metadata": ("jsonb", False),
    "usage_profiles.created_at": ("timestamp with time zone", False),
}

#: (conname, table, cols, ref_table, ref_cols, confdeltype, confupdtype,
#: confmatchtype, condeferrable, condeferred, convalidated) for every
#: public foreign key at the 222 checkpoint. Every reviewed FK is
#: non-deferrable, non-deferred and validated ("false","false","true").
_REVIEWED_FOREIGN_KEYS: tuple[tuple[str, str, str, str, str, str, str, str, str, str, str], ...] = (
    ("fk_admin_sessions_admin_user_id_admin_users", "admin_sessions", "admin_user_id", "admin_users", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_approved_catalog_entries_revision_id_policy_bundle_revisions", "approved_catalog_entries", "revision_id", "policy_bundle_revisions", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_audit_log_admin_user_id_admin_users", "audit_log", "admin_user_id", "admin_users", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_background_jobs_created_by_admin_user_id_admin_users", "background_jobs", "created_by_admin_user_id", "admin_users", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_budget_periods_organization_id_organizations", "budget_periods", "organization_id", "organizations", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_budget_periods_owner_id_owners", "budget_periods", "owner_id", "owners", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_budget_periods_project_id_projects", "budget_periods", "project_id", "projects", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_budget_periods_service_account_id_owners", "budget_periods", "service_account_id", "owners", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_budget_periods_team_id_teams", "budget_periods", "team_id", "teams", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_codex_replay_references_gateway_key_id_gateway_keys", "codex_replay_references", "gateway_key_id", "gateway_keys", "id", "r", "a", "s", "false", "false", "true"),
    ("fk_codex_replay_references_route_id_model_routes", "codex_replay_references", "route_id", "model_routes", "id", "r", "a", "s", "false", "false", "true"),
    ("fk_codex_replay_references_usage_ledger_id_usage_ledger", "codex_replay_references", "usage_ledger_id", "usage_ledger", "id", "r", "a", "s", "false", "false", "true"),
    ("fk_cohorts_project_id_projects", "cohorts", "project_id", "projects", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_conversation_references_cohort_id_cohorts", "conversation_references", "cohort_id", "cohorts", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_conversation_references_gateway_key_id_gateway_keys", "conversation_references", "gateway_key_id", "gateway_keys", "id", "r", "a", "s", "false", "false", "true"),
    ("fk_conversation_references_institution_id_institutions", "conversation_references", "institution_id", "institutions", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_conversation_references_owner_id_owners", "conversation_references", "owner_id", "owners", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_conversation_references_route_id_model_routes", "conversation_references", "route_id", "model_routes", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_email_deliveries_gateway_key_id_gateway_keys", "email_deliveries", "gateway_key_id", "gateway_keys", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_email_deliveries_one_time_secret_id_one_time_secrets", "email_deliveries", "one_time_secret_id", "one_time_secrets", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_email_deliveries_owner_id_owners", "email_deliveries", "owner_id", "owners", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_gateway_keys_cohort_id_cohorts", "gateway_keys", "cohort_id", "cohorts", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_gateway_keys_created_by_admin_user_id_admin_users", "gateway_keys", "created_by_admin_user_id", "admin_users", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_gateway_keys_external_tool_fence_reservation_id_quot_9236", "gateway_keys", "external_tool_fence_reservation_id", "quota_reservations", "id", "r", "a", "s", "false", "false", "true"),
    ("fk_gateway_keys_owner_id_owners", "gateway_keys", "owner_id", "owners", "id", "r", "a", "s", "false", "false", "true"),
    ("fk_gateway_keys_service_owner_id_owners", "gateway_keys", "service_owner_id", "owners", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_gateway_keys_template_id_key_templates", "gateway_keys", "template_id", "key_templates", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_gateway_keys_template_revision_id_key_template_revisions", "gateway_keys", "template_revision_id", "key_template_revisions", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_institutions_organization_id_organizations", "institutions", "organization_id", "organizations", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_key_template_revisions_created_audit_log_id_audit_log", "key_template_revisions", "created_audit_log_id", "audit_log", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_key_template_revisions_created_by_admin_id_admin_users", "key_template_revisions", "created_by_admin_id", "admin_users", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_key_template_revisions_source_calibration_gateway_ke_3696", "key_template_revisions", "source_calibration_gateway_key_id", "gateway_keys", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_key_template_revisions_template_id_key_templates", "key_template_revisions", "template_id", "key_templates", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_key_templates_archived_by_admin_id_admin_users", "key_templates", "archived_by_admin_id", "admin_users", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_key_templates_created_by_admin_id_admin_users", "key_templates", "created_by_admin_id", "admin_users", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_oidc_identities_owner_id_owners", "oidc_identities", "owner_id", "owners", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_one_time_secrets_gateway_key_id_gateway_keys", "one_time_secrets", "gateway_key_id", "gateway_keys", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_one_time_secrets_owner_id_owners", "one_time_secrets", "owner_id", "owners", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_owners_institution_id_institutions", "owners", "institution_id", "institutions", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_policy_bundle_revisions_bundle_id_policy_bundles", "policy_bundle_revisions", "bundle_id", "policy_bundles", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_policy_bundles_organization_id_organizations", "policy_bundles", "organization_id", "organizations", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_policy_bundles_project_id_projects", "policy_bundles", "project_id", "projects", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_policy_bundles_team_id_teams", "policy_bundles", "team_id", "teams", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_projects_team_id_teams", "projects", "team_id", "teams", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_quota_reservations_external_tool_route_id_model_routes", "quota_reservations", "external_tool_route_id", "model_routes", "id", "r", "a", "s", "false", "false", "true"),
    ("fk_quota_reservations_gateway_key_id_gateway_keys", "quota_reservations", "gateway_key_id", "gateway_keys", "id", "r", "a", "s", "false", "false", "true"),
    ("fk_response_references_cohort_id_cohorts", "response_references", "cohort_id", "cohorts", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_response_references_gateway_key_id_gateway_keys", "response_references", "gateway_key_id", "gateway_keys", "id", "r", "a", "s", "false", "false", "true"),
    ("fk_response_references_institution_id_institutions", "response_references", "institution_id", "institutions", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_response_references_owner_id_owners", "response_references", "owner_id", "owners", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_response_references_route_id_model_routes", "response_references", "route_id", "model_routes", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_team_members_owner_id_owners", "team_members", "owner_id", "owners", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_team_members_team_id_teams", "team_members", "team_id", "teams", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_teams_organization_id_organizations", "teams", "organization_id", "organizations", "id", "c", "a", "s", "false", "false", "true"),
    ("fk_usage_ledger_cohort_id_cohorts", "usage_ledger", "cohort_id", "cohorts", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_usage_ledger_gateway_key_id_gateway_keys", "usage_ledger", "gateway_key_id", "gateway_keys", "id", "r", "a", "s", "false", "false", "true"),
    ("fk_usage_ledger_institution_id_institutions", "usage_ledger", "institution_id", "institutions", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_usage_ledger_owner_id_owners", "usage_ledger", "owner_id", "owners", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_usage_ledger_quota_reservation_id_quota_reservations", "usage_ledger", "quota_reservation_id", "quota_reservations", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_usage_profiles_cohort_id_cohorts", "usage_profiles", "cohort_id", "cohorts", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_usage_profiles_gateway_key_id_gateway_keys", "usage_profiles", "gateway_key_id", "gateway_keys", "id", "r", "a", "s", "false", "false", "true"),
    ("fk_usage_profiles_institution_id_institutions", "usage_profiles", "institution_id", "institutions", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_usage_profiles_owner_id_owners", "usage_profiles", "owner_id", "owners", "id", "n", "a", "s", "false", "false", "true"),
    ("fk_usage_profiles_usage_ledger_id_usage_ledger", "usage_profiles", "usage_ledger_id", "usage_ledger", "id", "r", "a", "s", "false", "false", "true"),
)

#: SHA-256 over the canonical JSON records
#: [schema, table, conname, contype, pg_get_constraintdef] (sorted) of
#: ALL public constraints (PK, UNIQUE, CHECK, FK) at the 222 checkpoint,
#: as restored. The owning schema/table is part of the record so a
#: changed placement cannot preserve the digest.
_REVIEWED_CONSTRAINT_DIGEST = "f5e216ef8d8a248d234a21acc5f8449cfd57d627b58f9ec8c47a3b44b90b946f"
_REVIEWED_CONSTRAINT_TOTAL = 217
#: Per-contype counts at the 222 checkpoint (c=CHECK, f=FK, p=PK, u=UNIQUE).
_REVIEWED_CONSTRAINT_COUNTS: dict[str, int] = {"c": 96, "f": 64, "p": 34, "u": 23}

# ---------------------------------------------------------------------------
# Bounded execution limits (fixed, reviewed; not operator-configurable)
# ---------------------------------------------------------------------------

_MAX_ROWS_PER_TABLE = 100_000
_MAX_TOTAL_ROWS = 500_000
_EXECUTE_CHUNK = 500
_STATEMENT_TIMEOUT_MS = 30_000
_COMMAND_TIMEOUT_S = 30.0


def _q(name: str) -> str:
    """Quote a catalog-provided identifier (already policy-validated)."""
    if not ds._IDENT_RE.fullmatch(name):
        raise ds.DemoSnapshotError(
            ds.CODE_SANITIZE_FAILED,
            "Demo copy catalog identifier is outside the reviewed policy.",
        )
    return f'"{name}"'


def _ensure_before_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise ds.DemoSnapshotError(
            ds.CODE_SANITIZE_FAILED,
            "Demo sanitization exceeded its bounded time budget.",
        )


# ---------------------------------------------------------------------------
# Entity fictional-value bindings (table, column) -> (map attr, ref column)
# ---------------------------------------------------------------------------

_E_BINDINGS: dict[tuple[str, str], tuple[str, str]] = {
    ("owners", "name"): ("owner_name", "id"),
    ("owners", "surname"): ("owner_surname", "id"),
    ("owners", "email"): ("owner_email", "id"),
    ("institutions", "name"): ("institution_name", "id"),
    ("cohorts", "name"): ("cohort_name", "id"),
    ("organizations", "name"): ("org_name", "id"),
    ("organizations", "slug"): ("org_slug", "id"),
    ("teams", "name"): ("team_name", "id"),
    ("teams", "slug"): ("team_slug", "id"),
    ("projects", "name"): ("project_name", "id"),
    ("projects", "slug"): ("project_slug", "id"),
    ("budget_periods", "name"): ("budget_name", "id"),
    ("key_templates", "name"): ("template_name", "id"),
    ("admin_users", "display_name"): ("admin_name", "id"),
    ("admin_users", "email"): ("admin_email", "id"),
    ("oidc_identities", "email"): ("owner_email", "owner_id"),
    ("email_deliveries", "recipient_email"): ("owner_email", "owner_id"),
    ("usage_ledger", "owner_name_snapshot"): ("owner_name", "owner_id"),
    ("usage_ledger", "owner_surname_snapshot"): ("owner_surname", "owner_id"),
    ("usage_ledger", "owner_email_snapshot"): ("owner_email", "owner_id"),
    ("usage_ledger", "institution_name_snapshot"): ("institution_name", "institution_id"),
    ("usage_ledger", "cohort_name_snapshot"): ("cohort_name", "cohort_id"),
}

_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,256}$", re.ASCII)
_ENDPOINT_PATH_RE = re.compile(r"^/[A-Za-z0-9/._{}-]{1,256}$", re.ASCII)
_PROVIDER_ID_RE = re.compile(r"^[a-z0-9_-]{1,64}$", re.ASCII)
_DOTTED_CODE_RE = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)*$", re.ASCII)
_FLAG_KEY_RE = re.compile(r"^[a-z0-9_]{1,64}$", re.ASCII)


def _jj_string_list(value: object, pattern: re.Pattern[str], *, nonempty: bool = False) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, str) or not pattern.fullmatch(item):
            return False
        if nonempty and not item.strip():
            return False
    return True


def _jj_bool_flags(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    for key, item in value.items():
        if not isinstance(key, str) or not _FLAG_KEY_RE.fullmatch(key):
            return False
        if not isinstance(item, bool):
            return False
    return True


def _jj_rate_limits(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    for key, item in value.items():
        if not isinstance(key, str) or not _FLAG_KEY_RE.fullmatch(key):
            return False
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            return False
    return True


#: Narrow typed validators for the ONLY jsonb columns preserved as typed
#: (JJ). Every preserved value must pass at sanitization time AND again in
#: the independent verifier; an unregistered JJ column is a module defect.
_JJ_VALIDATORS: dict[tuple[str, str], "callable[[object], bool]"] = {
    ("gateway_keys", "allowed_models"): lambda v: _jj_string_list(v, _MODEL_NAME_RE, nonempty=True),
    ("gateway_keys", "allowed_endpoints"): lambda v: _jj_string_list(v, _ENDPOINT_PATH_RE, nonempty=True),
    ("quota_reservations", "external_tool_capabilities"): lambda v: _jj_string_list(v, _DOTTED_CODE_RE, nonempty=True),
    ("key_template_revisions", "allowed_endpoints"): lambda v: _jj_string_list(v, _ENDPOINT_PATH_RE, nonempty=True),
    ("key_template_revisions", "allowed_models"): lambda v: _jj_string_list(v, _MODEL_NAME_RE, nonempty=True),
    ("key_template_revisions", "allowed_providers"): lambda v: _jj_string_list(v, _PROVIDER_ID_RE, nonempty=True),
    ("key_template_revisions", "allowed_hosted_capabilities"): lambda v: _jj_string_list(v, _DOTTED_CODE_RE, nonempty=True),
    ("key_template_revisions", "hosted_capabilities_requiring_review"): lambda v: _jj_string_list(v, _DOTTED_CODE_RE, nonempty=True),
    ("key_template_revisions", "rate_limit_policy"): _jj_rate_limits,
}


def _jj_is_valid(table: str, column: str, raw: object) -> bool:
    validator = _JJ_VALIDATORS.get((table, column))
    if validator is None:
        return False
    if raw is None:
        return False
    if not isinstance(raw, (str, bytes)):
        return False
    try:
        parsed = json.loads(raw)
    except ValueError:
        return False
    return validator(parsed)


# ---------------------------------------------------------------------------
# RC: installed route capability transform (objective 223-b)
#
# The 222 sanitizer previously preserved model_routes.capabilities as a
# generic top-level boolean map (JJ). The INSTALLED runtime grammar
# (schemas.provider_route_configuration.validate_capabilities_document)
# writes nested typed blocks and may reference an operator completion
# profile and compaction-compatible route UUIDs. RC reuses the product's
# own strict child parsers group by group:
#   - boolean flag groups, codex limits, media estimation, external tool
#     policy and the native video contract are preserved (non-identifying
#     booleans/numbers/finite codes only);
#   - completion_service.profile is rewritten to the shared per-copy
#     fictional id (demo_profile_id) so a copied route links to exactly
#     its 223 completion-choice leaf;
#   - codex_compaction_compatible_route_ids are remapped with the SAME
#     per-copy UUID law as every other route id (list order kept);
#   - the preserved transport groups (local_coding, local_coding_vllm,
#     upstream_llm) fail closed: they carry configuration secrets or
#     operator transport-profile references that cannot be safely
#     projected in this stage (documented limit);
#   - unknown groups, unknown flags, wrong types, oversized documents and
#     recognized secret shapes fail closed, exactly like the installed
#     configuration law.
# ---------------------------------------------------------------------------

_RC_MAX_BYTES = 64 * 1024  # same envelope as the capabilities file contract
_RC_MAX_GROUPS = len(_RC_KNOWN_GROUPS)

_RC_EMBED_FLAGS = frozenset({_RC_EMBED_ON, _RC_EMBED_DIM})
_RC_REALTIME_FLAGS = frozenset(
    {_RC_RT_AUDIO, _RC_RT_WEBRTC, _RC_RT_TRANSCRIPTION, _RC_RT_DPEA}
)

_DEMO_PROFILE_ID_RE = re.compile(r"^demo-profile-[0-9a-f]{24}$")


def demo_profile_id(seed: bytes, profile_id: str) -> str:
    """Per-copy fictional completion-profile id (SHARED 222/223 law).

    This is the single canonical derivation used by BOTH the 222 route
    capability transform (completion_service.profile) and the 223
    completion-choices display projection, so a copied route references
    exactly the fictional choice captured from the same configured
    profile directory under the same job seed.
    """
    digest = _hmac.new(
        seed,
        b"completion-profile|" + profile_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"demo-profile-{digest[:24]}"


_RC_DEST_OPAQUE_RE = re.compile(r"^demo[0-9a-f]{44}$")


def _rc_destination_id(seed: bytes, destination_id: str) -> str:
    """Per-copy remap of one reviewed external-tool destination id.

    The KIND prefix (connector|remote_mcp) is preserved so the product's
    capability/destination kind-match law stays valid in the copy; the
    operator-chosen opaque name is replaced with a keyed per-copy digest
    (4 + 44 = 48 characters, the closed grammar's bound).
    """
    kind, _opaque = destination_id.split(":", 1)
    digest = _hmac.new(
        seed,
        b"route-destination|" + destination_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{kind}:demo{digest[:44]}"


def _rc_reject() -> ds.DemoSnapshotError:
    return ds.DemoSnapshotError(
        ds.CODE_SANITIZE_FAILED,
        "Demo copy route capability document failed its reviewed shape check.",
    )


def _rc_contains_secret_shape(value: object) -> bool:
    """Recursive known-secret-shape check (reuse of the redaction contract)."""
    if isinstance(value, str):
        return _contains_secret_shape(value)
    if isinstance(value, dict):
        return any(_rc_contains_secret_shape(item) for item in value.values())
    if isinstance(value, list):
        return any(_rc_contains_secret_shape(item) for item in value)
    return False


def _rc_bool_group(raw: object, known: frozenset[str]) -> dict[str, bool]:
    """Mirror of the installed bool-block law: non-empty, known flags only."""
    if not isinstance(raw, dict) or not raw:
        raise _rc_reject()
    if not set(raw) <= known or any(not isinstance(v, bool) for v in raw.values()):
        raise _rc_reject()
    return dict(raw)


def _rc_parse_document(value: object) -> dict[str, object]:
    """Parse one stored capabilities value (asyncpg jsonb text or object)."""
    if isinstance(value, (str, bytes)):
        try:
            parsed = json.loads(value)
        except ValueError:
            raise _rc_reject()
    else:
        parsed = value
    if not isinstance(parsed, dict):
        raise _rc_reject()
    return parsed


def _transform_route_capabilities(value: object, seed: bytes) -> str:
    """Sanitize one installed capabilities document (RC action).

    Returns the transformed document as deterministic JSON text (the same
    binding form the JJ action uses for jsonb columns).
    """
    value = _rc_parse_document(value)
    if len(value) > _RC_MAX_GROUPS:
        raise _rc_reject()
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        raise _rc_reject() from None
    if len(encoded) > _RC_MAX_BYTES or _rc_contains_secret_shape(value):
        raise _rc_reject()
    # Installed conflict law: the completion-service selector conflicts
    # with the native video contract (validate_capabilities_document).
    if _RC_PROFILE_KEY in value and "vllm_chat_video" in value:
        raise _rc_reject()
    out: dict[str, object] = {}
    for group, raw in value.items():
        if group in _RC_TRANSPORT_GROUPS:
            # Documented limit: preserved transport blocks are not
            # projected into the demo copy.
            raise _rc_reject()
        if group == _RC_CHAT_KEY:
            try:
                out[group] = _rc_validate_chat_block(raw)
            except Exception:
                raise _rc_reject() from None
        elif group == _RC_RESPONSES_KEY:
            try:
                out[group] = _rc_validate_responses_block(raw)
            except Exception:
                raise _rc_reject() from None
        elif group == _RC_CODEX_LIMITS_KEY:
            try:
                _rc_parse_codex_limits({_RC_CODEX_LIMITS_KEY: raw})
            except Exception:
                raise _rc_reject() from None
            out[group] = dict(raw)  # type: ignore[arg-type]
        elif group == _RC_COMPACTION_KEY:
            try:
                _rc_parse_compaction({_RC_COMPACTION_KEY: raw})
            except Exception:
                raise _rc_reject() from None
            out[group] = [str(remap_uuid(seed, _uuid.UUID(x))) for x in raw]  # type: ignore[union-attr]
        elif group == "media_input_estimation":
            try:
                _rc_validate_media(raw)
            except Exception:
                raise _rc_reject() from None
            out[group] = dict(raw)  # type: ignore[arg-type]
        elif group == _RC_PROFILE_KEY:
            try:
                profile_id = _rc_profile_id_from_capabilities(
                    {_RC_PROFILE_KEY: raw}
                )
            except Exception:
                raise _rc_reject() from None
            if profile_id is None:
                raise _rc_reject()
            out[group] = {
                "version": 1,
                "profile": demo_profile_id(seed, profile_id),
            }
        elif group == "external_tools":
            parsed = _rc_parse_tool_policy(raw, ceilings=_RC_TOOL_CEILINGS)
            if not parsed.valid or parsed.policy is None:
                raise _rc_reject()
            doc_et = dict(raw)  # type: ignore[arg-type]
            destinations = doc_et.get("approved_destination_ids")
            if isinstance(destinations, list):
                # The opaque destination names are operator identifiers:
                # remap them per copy (kind preserved), never passthrough.
                doc_et["approved_destination_ids"] = [
                    _rc_destination_id(seed, d) for d in destinations
                ]
            out[group] = doc_et
        elif group == "vllm_chat_video":
            try:
                _rc_parse_video_frames(value)
            except Exception:
                raise _rc_reject() from None
            out[group] = dict(raw)  # type: ignore[arg-type]
        elif group == _RC_AUDIO_KEY:
            out[group] = _rc_bool_group(raw, _RC_AUDIO_FLAGS)
        elif group == _RC_EMBED_KEY:
            out[group] = _rc_bool_group(raw, _RC_EMBED_FLAGS)
        elif group == _RC_REALTIME_KEY:
            out[group] = _rc_bool_group(raw, _RC_REALTIME_FLAGS)
        else:
            raise _rc_reject()
    return json.dumps(out, sort_keys=True)


def _verify_route_capabilities(
    value: object, route_ids: frozenset[str]
) -> bool:
    """Independent re-proof of a STORED transformed capabilities document.

    Reuses the installed per-group parsers; the identity fields must
    follow the FICTIONAL laws: completion_service.profile matches the
    shared demo-profile id shape, and every compaction route id exists in
    the copied model_routes set (remapped to copied route ids).
    """
    if isinstance(value, (str, bytes)):
        try:
            value = json.loads(value)
        except ValueError:
            return False
    if not isinstance(value, dict) or len(value) > _RC_MAX_GROUPS:
        return False
    # Installed conflict law (mirrors the transformer): the completion
    # selector conflicts with the native video contract. A tampered stored
    # document carrying both must fail even though each group alone would
    # pass its per-group re-proof.
    if _RC_PROFILE_KEY in value and "vllm_chat_video" in value:
        return False
    for group, raw in value.items():
        try:
            if group in _RC_TRANSPORT_GROUPS:
                return False
            if group == _RC_CHAT_KEY:
                _rc_validate_chat_block(raw)
            elif group == _RC_RESPONSES_KEY:
                _rc_validate_responses_block(raw)
            elif group == _RC_CODEX_LIMITS_KEY:
                _rc_parse_codex_limits({_RC_CODEX_LIMITS_KEY: raw})
            elif group == _RC_COMPACTION_KEY:
                # parse returns uuid.UUID objects; route_ids are str —
                # normalize both sides before the membership proof.
                parsed = _rc_parse_compaction({_RC_COMPACTION_KEY: raw})
                if not all(str(u) in route_ids for u in parsed):
                    return False
            elif group == "media_input_estimation":
                _rc_validate_media(raw)
            elif group == _RC_PROFILE_KEY:
                profile_id = _rc_profile_id_from_capabilities(
                    {_RC_PROFILE_KEY: raw}
                )
                if (
                    profile_id is None
                    or not _DEMO_PROFILE_ID_RE.fullmatch(profile_id)
                ):
                    return False
            elif group == "external_tools":
                parsed = _rc_parse_tool_policy(raw, ceilings=_RC_TOOL_CEILINGS)
                if not parsed.valid or parsed.policy is None:
                    return False
                # Fictional-law re-proof: every stored destination opaque
                # name must follow the per-copy remap shape (a raw
                # operator name would not match).
                destinations = (
                    raw.get("approved_destination_ids")
                    if isinstance(raw, dict)
                    else None
                )
                if not isinstance(destinations, list):
                    return False
                for d in destinations:
                    if not isinstance(d, str) or ":" not in d:
                        return False
                    _kind, opaque = d.split(":", 1)
                    if not _RC_DEST_OPAQUE_RE.fullmatch(opaque):
                        return False
            elif group == "vllm_chat_video":
                _rc_parse_video_frames(value)
            elif group == _RC_AUDIO_KEY:
                _rc_bool_group(raw, _RC_AUDIO_FLAGS)
            elif group == _RC_EMBED_KEY:
                _rc_bool_group(raw, _RC_EMBED_FLAGS)
            elif group == _RC_REALTIME_KEY:
                _rc_bool_group(raw, _RC_REALTIME_FLAGS)
            else:
                return False
        except Exception:
            return False
    return True


_E_ACTIONS = frozenset({
    E_OWNER_NAME, E_OWNER_SURNAME, E_OWNER_EMAIL,
    E_OWNER_SNAP_NAME, E_OWNER_SNAP_SURNAME, E_OWNER_SNAP_EMAIL,
    E_INST_NAME, E_INST_SNAP_NAME,
    E_COHORT_NAME, E_COHORT_SNAP_NAME,
    E_ORG_NAME, E_ORG_SLUG, E_TEAM_NAME, E_TEAM_SLUG,
    E_PROJ_NAME, E_PROJ_SLUG, E_BUDGET_NAME, E_TPL_NAME,
    E_ADMIN_NAME, E_ADMIN_EMAIL,
})

# Entity kind -> (entity table, denormalized reference columns). The map is
# built over the UNION so denormalized snapshots always resolve, and the
# injective assignment keeps uniqueness-constrained columns collision-free.
_ENTITY_TABLE = {
    "owner_ids": "owners",
    "institution_ids": "institutions",
    "cohort_ids": "cohorts",
    "org_ids": "organizations",
    "team_ids": "teams",
    "project_ids": "projects",
    "budget_ids": "budget_periods",
    "template_ids": "key_templates",
    "admin_ids": "admin_users",
}

_ENTITY_REFERENCES: dict[str, list[tuple[str, str]]] = {
    "owner_ids": [
        ("usage_ledger", "owner_id"),
        ("email_deliveries", "owner_id"),
        ("one_time_secrets", "owner_id"),
        ("gateway_keys", "owner_id"),
        ("gateway_keys", "service_owner_id"),
        ("oidc_identities", "owner_id"),
        ("response_references", "owner_id"),
        ("conversation_references", "owner_id"),
        ("usage_profiles", "owner_id"),
        ("budget_periods", "owner_id"),
        ("team_members", "owner_id"),
    ],
    "institution_ids": [
        ("owners", "institution_id"),
        ("usage_ledger", "institution_id"),
        ("response_references", "institution_id"),
        ("conversation_references", "institution_id"),
        ("usage_profiles", "institution_id"),
    ],
    "cohort_ids": [
        ("gateway_keys", "cohort_id"),
        ("usage_ledger", "cohort_id"),
        ("response_references", "cohort_id"),
        ("conversation_references", "cohort_id"),
        ("usage_profiles", "cohort_id"),
    ],
    "org_ids": [
        ("institutions", "organization_id"),
        ("teams", "organization_id"),
        ("budget_periods", "organization_id"),
        ("policy_bundles", "organization_id"),
    ],
    "team_ids": [
        ("projects", "team_id"),
        ("team_members", "team_id"),
        ("budget_periods", "team_id"),
        ("policy_bundles", "team_id"),
    ],
    "project_ids": [
        ("cohorts", "project_id"),
        ("budget_periods", "project_id"),
        ("policy_bundles", "project_id"),
    ],
    "budget_ids": [],
    "template_ids": [
        ("gateway_keys", "template_id"),
    ],
    "admin_ids": [
        ("admin_sessions", "admin_user_id"),
        ("audit_log", "admin_user_id"),
        ("background_jobs", "created_by_admin_user_id"),
        ("gateway_keys", "created_by_admin_user_id"),
        ("key_templates", "created_by_admin_id"),
        ("key_templates", "archived_by_admin_id"),
        ("key_template_revisions", "created_by_admin_id"),
        ("catalog_refresh_applications", "admin_user_id"),
    ],
}


def _validate_policy_invariants() -> None:
    """Static, import-time consistency proof for the reviewed policy.

    Every E_* policy entry must have an explicit binding whose reference
    column exists in the same table's policy; every E_* constant must be
    used only where bound, and the reviewed column signature must cover
    exactly the policy's (table, column) pairs. A mismatch is an internal
    defect, not a recoverable runtime condition.
    """
    signature_pairs = {
        (name.split(".", 1)[0], name.split(".", 1)[1])
        for name in _COLUMN_SIGNATURE
    }
    policy_pairs = {
        (table, column)
        for table, columns in TABLE_POLICY.items()
        for column in columns
    }
    if signature_pairs != policy_pairs:
        raise RuntimeError("column signature does not match the table policy")
    for table, columns in TABLE_POLICY.items():
        for column, action in columns.items():
            if action == JJ and (table, column) not in _JJ_VALIDATORS:
                raise RuntimeError(f"no typed JJ validator for {table}.{column}")
            if action == RC and (table, column) != ("model_routes", "capabilities"):
                raise RuntimeError("RC is reserved for model_routes.capabilities")
    for table, columns in TABLE_POLICY.items():
        for column, action in columns.items():
            if action in _E_ACTIONS:
                binding = _E_BINDINGS.get((table, column))
                if binding is None:
                    raise RuntimeError(f"missing E binding for {table}.{column}")
                if binding[1] not in columns:
                    raise RuntimeError(f"dangling E ref for {table}.{column}")
            elif (table, column) in _E_BINDINGS:
                raise RuntimeError(f"unbound E binding for {table}.{column}")


_validate_policy_invariants()


def _require_data_keys(data: dict[str, object]) -> None:
    needed: set[str] = {
        action.split(":", 1)[1]
        for columns in TABLE_POLICY.values()
        for action in columns.values()
        if action.startswith("F:") or action.startswith("FC:")
    }
    needed.update({
        "first_names", "last_names", "email_domains", "institutions",
        "cohorts", "organizations", "teams", "projects", "budget_names",
        "template_names", "admin_display_names", "fictional_ips",
        "user_agents", _FTN_DATA_KEY,
        _FN_DATA_KEY,
    })
    if any(not data.get(key) for key in needed):
        raise ds.DemoSnapshotError(
            ds.CODE_SANITIZE_FAILED,
            "Demo identity data is incomplete for the reviewed policy.",
        )


# ---------------------------------------------------------------------------
# Runtime catalog inventory (the restored copy, never the source)
# ---------------------------------------------------------------------------


async def _inventory_catalog(conn: asyncpg.Connection) -> dict[str, object]:
    rows = await conn.fetch(
        "SELECT c.relname AS table_name, a.attname AS column_name, "
        "format_type(a.atttypid, a.atttypmod) AS sql_type, "
        "NOT a.attnotnull AS nullable "
        "FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid = c.oid "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' "
        "AND a.attnum > 0 AND NOT a.attisdropped "
        "ORDER BY c.relname, a.attnum"
    )
    tables: dict[str, dict[str, tuple[str, bool]]] = {}
    for row in rows:
        tables.setdefault(row["table_name"], {})[row["column_name"]] = (
            row["sql_type"],
            bool(row["nullable"]),
        )
    extensions = {
        row["extname"] for row in await conn.fetch("SELECT extname FROM pg_extension")
    }
    public_types = {
        row["typname"]
        for row in await conn.fetch(
            "SELECT t.typname FROM pg_type t "
            "JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = 'public'"
        )
    }
    constraint_rows = await conn.fetch(
        "SELECT n.nspname AS schema_name, tc.relname AS table_name, "
        "c.conname AS conname, c.contype::text AS contype, "
        "pg_get_constraintdef(c.oid) AS definition "
        "FROM pg_constraint c "
        "JOIN pg_class tc ON tc.oid = c.conrelid "
        "JOIN pg_namespace n ON n.oid = tc.relnamespace "
        "WHERE n.nspname = 'public' "
        "ORDER BY n.nspname, tc.relname, c.conname, c.contype::text"
    )
    return {
        "tables": tables,
        "extensions": frozenset(extensions),
        "public_types": frozenset(public_types),
        "constraints": [
            (
                row["schema_name"],
                row["table_name"],
                row["conname"],
                row["contype"],
                row["definition"],
            )
            for row in constraint_rows
        ],
        "foreign_keys": await _fk_inventory(conn),
    }


async def _fk_inventory(conn: asyncpg.Connection) -> list[dict[str, str]]:
    rows = await conn.fetch(
        "SELECT c.conname AS conname, "
        "tc.relname AS table_name, "
        "string_agg(ta.attname, ',' ORDER BY u.ord) AS cols, "
        "rc.relname AS ref_table, "
        "string_agg(ra.attname, ',' ORDER BY x.ord) AS ref_cols, "
        "c.confdeltype::text AS confdeltype, "
        "c.confupdtype::text AS confupdtype, "
        "c.confmatchtype::text AS confmatchtype, "
        "c.condeferrable::text AS condeferrable, "
        "c.condeferred::text AS condeferred, "
        "c.convalidated::text AS convalidated "
        "FROM pg_constraint c "
        "JOIN pg_class tc ON tc.oid = c.conrelid "
        "JOIN pg_namespace n ON n.oid = tc.relnamespace "
        "JOIN pg_class rc ON rc.oid = c.confrelid "
        "CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS u(attnum, ord) "
        "JOIN pg_attribute ta ON ta.attrelid = c.conrelid AND ta.attnum = u.attnum "
        "CROSS JOIN LATERAL unnest(c.confkey) WITH ORDINALITY AS x(attnum, ord) "
        "JOIN pg_attribute ra ON ra.attrelid = c.confrelid AND ra.attnum = x.attnum "
        "WHERE c.contype = 'f' AND n.nspname = 'public' "
        "GROUP BY c.oid, c.conname, tc.relname, rc.relname, "
        "c.confdeltype, c.confupdtype, c.confmatchtype, "
        "c.condeferrable, c.condeferred, c.convalidated "
        "ORDER BY tc.relname, c.conname"
    )
    return [dict(row) for row in rows]


async def _pk_map(conn: asyncpg.Connection) -> dict[str, list[str]]:
    rows = await conn.fetch(
        "SELECT tc.relname AS table_name, c.conname AS conname, "
        "string_agg(ta.attname, ',' ORDER BY u.ord) AS cols "
        "FROM pg_constraint c "
        "JOIN pg_class tc ON tc.oid = c.conrelid "
        "JOIN pg_namespace n ON n.oid = tc.relnamespace "
        "CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS u(attnum, ord) "
        "JOIN pg_attribute ta ON ta.attrelid = c.conrelid AND ta.attnum = u.attnum "
        "WHERE c.contype = 'p' AND n.nspname = 'public' "
        "GROUP BY c.oid, tc.relname, c.conname "
        "ORDER BY tc.relname, c.conname"
    )
    out: dict[str, list[str]] = {}
    for row in rows:
        if row["table_name"] in out:
            raise ds.DemoSnapshotError(
                ds.CODE_SANITIZE_SCHEMA_UNKNOWN,
                "Demo copy table declares more than one primary key.",
            )
        out[row["table_name"]] = str(row["cols"]).split(",")
    return out


def _fk_key(fk: dict[str, str]) -> tuple[str, ...]:
    return (
        fk["conname"],
        fk["table_name"],
        fk["cols"],
        fk["ref_table"],
        fk["ref_cols"],
        fk["confdeltype"],
        fk["confupdtype"],
        fk["confmatchtype"],
        fk["condeferrable"],
        fk["condeferred"],
        fk["convalidated"],
    )


def _constraint_digest(
    constraints: list[tuple[str, str, str, str, str]],
) -> str:
    records = sorted(json.dumps(record, ensure_ascii=True) for record in constraints)
    return hashlib.sha256("\n".join(records).encode("utf-8")).hexdigest()


def _check_catalog(inventory: dict[str, object]) -> None:
    """Fail closed on ANY catalog deviation from the reviewed policy.

    Covers table set, per-table column set, exact column SQL type and
    nullability, extensions, public types, the COMPLETE public
    constraint set (PK/UNIQUE/CHECK/FK via reviewed digest and
    per-contype counts) and the exact foreign-key definition set used
    for the transactional drop/recreate.
    """
    schema_unknown = ds.CODE_SANITIZE_SCHEMA_UNKNOWN
    policy_tables = set(TABLE_POLICY)
    inventory_tables = set(inventory["tables"])  # type: ignore[arg-type]
    if inventory_tables != policy_tables:
        raise ds.DemoSnapshotError(
            schema_unknown,
            "Demo copy catalog tables differ from the reviewed policy.",
        )
    for table in sorted(policy_tables):
        columns = inventory["tables"][table]  # type: ignore[index]
        if set(columns) != set(TABLE_POLICY[table]):
            raise ds.DemoSnapshotError(
                schema_unknown,
                "Demo copy catalog columns differ from the reviewed policy.",
            )
        for column, (sql_type, nullable) in columns.items():
            expected = _COLUMN_SIGNATURE.get(f"{table}.{column}")
            if expected is None or expected != (sql_type, nullable):
                raise ds.DemoSnapshotError(
                    schema_unknown,
                    "Demo copy column type or nullability differs from the reviewed policy.",
                )
    if inventory["extensions"] != _EXPECTED_EXTENSIONS:
        raise ds.DemoSnapshotError(
            schema_unknown,
            "Demo copy extension set differs from the reviewed policy.",
        )
    expected_types: set[str] = set()
    for table in policy_tables:
        expected_types.add(table)
        expected_types.add(f"_{table}")
    expected_types |= _EXPECTED_EXTRA_PUBLIC_TYPES
    if inventory["public_types"] != expected_types:
        raise ds.DemoSnapshotError(
            schema_unknown,
            "Demo copy public type set differs from the reviewed policy.",
        )

    constraints = list(inventory["constraints"])  # type: ignore[arg-type]
    if len(constraints) != _REVIEWED_CONSTRAINT_TOTAL:
        raise ds.DemoSnapshotError(
            schema_unknown,
            "Demo copy constraint count differs from the reviewed policy.",
        )
    counts: dict[str, int] = {}
    for record in constraints:
        contype = record[3]
        counts[contype] = counts.get(contype, 0) + 1
    if counts != _REVIEWED_CONSTRAINT_COUNTS:
        raise ds.DemoSnapshotError(
            schema_unknown,
            "Demo copy constraint kinds differ from the reviewed policy.",
        )
    if _constraint_digest(constraints) != _REVIEWED_CONSTRAINT_DIGEST:
        raise ds.DemoSnapshotError(
            schema_unknown,
            "Demo copy constraint definitions differ from the reviewed policy.",
        )

    foreign_keys = list(inventory["foreign_keys"])  # type: ignore[arg-type]
    for fk in foreign_keys:
        if (
            fk["condeferrable"] != "false"
            or fk["condeferred"] != "false"
            or fk["convalidated"] != "true"
        ):
            raise ds.DemoSnapshotError(
                schema_unknown,
                "Demo copy foreign key is deferrable or unvalidated.",
            )
    if frozenset(_fk_key(fk) for fk in foreign_keys) != frozenset(_REVIEWED_FOREIGN_KEYS):
        raise ds.DemoSnapshotError(
            schema_unknown,
            "Demo copy foreign key definitions differ from the reviewed policy.",
        )


def _fk_recreate_sql(fk: dict[str, str]) -> str:
    cols = ", ".join(_q(c) for c in str(fk["cols"]).split(","))
    ref_cols = ", ".join(_q(c) for c in str(fk["ref_cols"]).split(","))
    sql = (
        f"ALTER TABLE public.{_q(fk['table_name'])} "
        f"ADD CONSTRAINT {_q(fk['conname'])} "
        f"FOREIGN KEY ({cols}) REFERENCES public.{_q(fk['ref_table'])} ({ref_cols})"
    )
    if fk["confmatchtype"] in _FK_MATCH:
        sql += f" {_FK_MATCH[fk['confmatchtype']]}"
    if fk["confdeltype"] != "a":
        sql += f" ON DELETE {_FK_ACTIONS[fk['confdeltype']]}"
    if fk["confupdtype"] != "a":
        sql += f" ON UPDATE {_FK_ACTIONS[fk['confupdtype']]}"
    return sql


# ---------------------------------------------------------------------------
# Pre-state capture (private 0600 artifact, before any modification)
# ---------------------------------------------------------------------------


async def _column_md5(
    conn: asyncpg.Connection, table: str, columns: list[str]
) -> str:
    if not columns:
        return ""
    expr = " || '|' || ".join(
        f"COALESCE({_q(c)}::text, E'\\N')" for c in columns
    )
    row = await conn.fetchrow(
        f"SELECT md5(coalesce(string_agg(r, '|' ORDER BY r), '')) AS h "
        f"FROM (SELECT ({expr}) AS r FROM public.{_q(table)}) z"
    )
    return str(row["h"])


async def _masked_nonnull_rows(
    conn: asyncpg.Connection, table: str, columns: list[str]
) -> int:
    if not columns:
        return 0
    conds = " OR ".join(f"{_q(c)} IS NOT NULL" for c in columns)
    return int(
        await conn.fetchval(
            f"SELECT count(*) FROM public.{_q(table)} WHERE {conds}"
        )
    )


async def _table_stats(
    conn: asyncpg.Connection,
    tables: dict[str, dict[str, tuple[str, bool]]],
    counts: dict[str, int],
    deadline: float,
) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for table in sorted(tables):
        _ensure_before_deadline(deadline)
        columns = list(tables[table])
        policy = TABLE_POLICY[table]
        preserved = [c for c in columns if policy[c] == P]
        masked = [c for c in columns if policy[c] != P]
        out[table] = {
            "count": counts[table],
            "preserved_md5": await _column_md5(conn, table, preserved),
            "masked_md5": await _column_md5(conn, table, masked),
            "masked_nonnull_rows": await _masked_nonnull_rows(conn, table, masked),
        }
    return out


async def _entity_id_lists(conn: asyncpg.Connection) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key, table in _ENTITY_TABLE.items():
        ids = {
            str(row["id"])
            for row in await conn.fetch(f"SELECT id FROM public.{_q(table)}")
        }
        for ref_table, ref_column in _ENTITY_REFERENCES[key]:
            rows = await conn.fetch(
                f"SELECT DISTINCT {_q(ref_column)} AS v FROM public.{_q(ref_table)} "
                f"WHERE {_q(ref_column)} IS NOT NULL"
            )
            ids.update(str(row["v"]) for row in rows)
        out[key] = sorted(ids)
    return out


async def _capture_prestate(
    conn: asyncpg.Connection,
    inventory: dict[str, object],
    seed: bytes,
    deadline: float,
) -> dict[str, object]:
    """Capture the private pre-state with bounded, ordered work.

    The row budgets are enforced by cheap COUNT(*) queries BEFORE any
    aggregate scan or identity materialization, so a large restored copy
    is refused without consuming unbounded time or memory. The same
    absolute deadline that bounds the transaction also bounds this phase.
    """
    tables = inventory["tables"]  # type: ignore[assignment]
    _ensure_before_deadline(deadline)
    pk = await _pk_map(conn)
    for table in tables:
        if not pk.get(table):
            raise ds.DemoSnapshotError(
                ds.CODE_SANITIZE_SCHEMA_UNKNOWN,
                "Demo copy table is missing its primary key.",
            )
    counts: dict[str, int] = {}
    total = 0
    for table in sorted(tables):
        _ensure_before_deadline(deadline)
        n = int(await conn.fetchval(f"SELECT count(*) FROM public.{_q(table)}"))
        if n > _MAX_ROWS_PER_TABLE:
            raise ds.DemoSnapshotError(
                ds.CODE_SANITIZE_FAILED,
                "Demo copy table exceeded the bounded row budget.",
            )
        counts[table] = n
        total += n
        if total > _MAX_TOTAL_ROWS:
            raise ds.DemoSnapshotError(
                ds.CODE_SANITIZE_FAILED,
                "Demo copy exceeded the bounded total row budget.",
            )
    stats = await _table_stats(conn, tables, counts, deadline)  # type: ignore[arg-type]
    _ensure_before_deadline(deadline)
    entity_ids = await _entity_id_lists(conn)
    _ensure_before_deadline(deadline)
    # Expected post-rewrite multiset digest for every H column (bounded:
    # H columns are the two reviewed codex_replay HMAC fields, each under
    # the per-table row cap already enforced above). The digest is keyed
    # by the per-copy seed, so it is not a raw value and is safe in the
    # private pre-state artifact.
    h_expected: dict[str, dict[str, str]] = {}
    for table in sorted(tables):
        _ensure_before_deadline(deadline)
        for column, action in TABLE_POLICY[table].items():
            if action != H:
                continue
            rows = await conn.fetch(
                f"SELECT {_q(column)} AS v FROM public.{_q(table)} "
                f"WHERE {_q(column)} IS NOT NULL"
            )
            raw = [str(r["v"]) for r in rows]
            # Raw values -> expected stored values, THEN digest as-is.
            expected = [
                remap_hex64(seed, column.encode("utf-8"), value) for value in raw
            ]
            h_expected.setdefault(table, {})[column] = _h_column_digest(
                seed, column, expected
            )
    # 224-r expected per-column remap multiset digest for EVERY U column
    # (bounded: each column is under the per-table row cap already enforced
    # above). Raw UUIDs -> expected stored values, THEN digest as-is: the
    # verifier recomputes the digest over the STORED values and requires
    # equality. This is the per-copy mapping law that a blanket
    # distinctness check cannot express: repeated raw FK values (two keys
    # of one owner) must appear under the same per-copy remapped value.
    u_expected: dict[str, dict[str, str]] = {}
    for table in sorted(tables):
        _ensure_before_deadline(deadline)
        for column, action in TABLE_POLICY[table].items():
            if action != U:
                continue
            rows = await conn.fetch(
                f"SELECT {_q(column)} AS v FROM public.{_q(table)} "
                f"WHERE {_q(column)} IS NOT NULL"
            )
            expected = [
                str(remap_uuid(seed, _uuid.UUID(str(r["v"])))) for r in rows
            ]
            u_expected.setdefault(table, {})[column] = _u_column_digest(
                seed, table, column, expected
            )
    # 224-s expected per-column remap multiset digest for EVERY S column
    # (bounded: each column is under the per-table row cap already
    # enforced above). Raw strings -> expected stored values via the
    # existing remap_str_id, THEN digest as-is: the verifier recomputes
    # the digest over the STORED values and requires equality. This is
    # the per-copy value law a blanket distinctness check cannot
    # express: repeated raw values (e.g. the same operator_actor /
    # db_actor across two catalog applies) must appear under the SAME
    # per-copy remapped value, while a raw (un-remapped) pass-through, a
    # dropped duplicate or a substitution breaks equality.
    s_expected: dict[str, dict[str, str]] = {}
    for table in sorted(tables):
        _ensure_before_deadline(deadline)
        for column, action in TABLE_POLICY[table].items():
            if action != S:
                continue
            rows = await conn.fetch(
                f"SELECT {_q(column)} AS v FROM public.{_q(table)} "
                f"WHERE {_q(column)} IS NOT NULL"
            )
            expected = [remap_str_id(seed, str(r["v"])) for r in rows]
            s_expected.setdefault(table, {})[column] = _s_column_digest(
                seed, table, column, expected
            )
    # 224-r expected per-row clone-receipt projection (bounded: only the
    # gateway_keys rows whose raw metadata is non-empty are scanned, each
    # under the per-table row cap already enforced above). For a row with a
    # recognized well-formed receipt the keyed digest of the EXPECTED
    # post-rewrite metadata (projected from the RAW source receipt) is kept
    # under the row's REMAPPED id; rows without a receipt are expected to be
    # cleared to {} and are simply absent here. A malformed source receipt
    # raises and fails the copy closed BEFORE any pre-state is written.
    kr_expected: dict[str, str] = {}
    receipt_rows = await conn.fetch(
        "SELECT id, metadata FROM public.gateway_keys "
        "WHERE metadata IS NOT NULL AND metadata <> '{}'::jsonb"
    )
    for row in receipt_rows:
        _ensure_before_deadline(deadline)
        raw_id = row["id"]
        if not isinstance(raw_id, _uuid.UUID):
            raise _kr_malformed("row_id")
        expected = _expected_kr_metadata(row["metadata"], seed)
        if expected:
            new_id = str(remap_uuid(seed, raw_id))
            kr_expected[new_id] = _kr_digest(
                seed, new_id, _canonical_json(expected)
            )
    return {
        "tables": tables,
        "pk": pk,
        "stats": stats,
        "foreign_keys": inventory["foreign_keys"],
        "entity_ids": entity_ids,
        "h_expected": h_expected,
        "u_expected": u_expected,
        "s_expected": s_expected,
        "kr_expected": kr_expected,
    }


# ---------------------------------------------------------------------------
# Per-table sanitizer planning
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _TablePlan:
    table: str
    pk: tuple[str, ...]
    set_cols: tuple[str, ...]
    fetch_cols: tuple[str, ...]


def _build_plan(
    table: str, pk_cols: list[str], columns: dict[str, tuple[str, bool]]
) -> _TablePlan:
    policy = TABLE_POLICY[table]
    if not pk_cols:
        raise ds.DemoSnapshotError(
            ds.CODE_SANITIZE_SCHEMA_UNKNOWN,
            "Demo copy table is missing its primary key.",
        )
    set_cols = [c for c in columns if policy[c] != P]
    fetch: list[str] = []
    for c in (*pk_cols, *set_cols):
        if c not in fetch:
            fetch.append(c)
    for c in set_cols:
        action = policy[c]
        if action in _E_ACTIONS:
            ref = _E_BINDINGS[(table, c)][1]
            if ref not in fetch:
                fetch.append(ref)
        elif action in (FTN, FN) and _FTN_KIND_COLUMN in columns:
            if _FTN_KIND_COLUMN not in fetch:
                fetch.append(_FTN_KIND_COLUMN)
    return _TablePlan(table, tuple(pk_cols), tuple(set_cols), tuple(fetch))


# ---------------------------------------------------------------------------
# Deterministic per-value conversion (the only code that touches data)
# ---------------------------------------------------------------------------


def _unsupported_shape() -> ds.DemoSnapshotError:
    return ds.DemoSnapshotError(
        ds.CODE_SANITIZE_FAILED,
        "Demo sanitization encountered an unsupported value shape.",
    )


def _orphan_recipient_email(
    out_id: _uuid.UUID, data: dict[str, object]
) -> str:
    """Deterministic fictional recipient for an ownerless delivery row.

    ``email_deliveries.recipient_email`` is NOT NULL while its bound
    ``owner_id`` is nullable, so a legitimate row without an owner cannot
    be nulled. Derive a stable per-copy reserved-domain address from the
    delivery's REMAPPED (output) row id, which is already per-copy: the
    sanitizer passes ``remap_uuid(seed, old_id)`` and the verifier passes
    the stored (already remapped) id, so both sides derive the SAME value
    without a second remap. Linked rows keep the shared fictional owner
    email, and two copies never share an orphan address.
    """
    domains = data["email_domains"]
    assert isinstance(domains, list)
    return f"demo-{out_id.hex[:24]}@{domains[out_id.int % len(domains)]}"


def _remap_uuid_array(value: object, seed: bytes) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (str, bytes)):
        raise _unsupported_shape()
    try:
        parsed = json.loads(value)
    except ValueError:
        raise _unsupported_shape() from None
    if not isinstance(parsed, list):
        raise _unsupported_shape()
    out: list[str] = []
    for item in parsed:
        if not isinstance(item, str) or not _UUID_RE.fullmatch(item):
            raise _unsupported_shape()
        out.append(str(remap_uuid(seed, _uuid.UUID(item))))
    return json.dumps(out)


def _ju_is_safe(value: object) -> bool:
    """Shape proof for stored JU values: JSON array of UUID strings."""
    if not isinstance(value, (str, bytes)):
        return False
    try:
        parsed = json.loads(value)
    except ValueError:
        return False
    return isinstance(parsed, list) and all(
        isinstance(item, str) and _UUID_RE.fullmatch(item) for item in parsed
    )


# ---------------------------------------------------------------------------
# 224-r clone-receipt projection (gateway_keys.metadata -> KR action)
#
# The supported clone flow (objective 208) persists a bounded safe receipt
# under the ``clone_receipt`` member of the NEW target key's metadata:
# safe UUIDs, the source public identity, source/policy fingerprints and
# bounded nonsecret validity fields only. The demo sanitizer must carry
# that receipt into the private copy so the historical receipt view stays
# usable, while remapping every identifying value per copy and discarding
# anything else. The projection is CLOSED: it accepts exactly the 17
# reviewed members with their exact types and rejects (fails the copy
# closed) any malformed shape, unknown/secret-bearing member, or a new
# receipt version. No arbitrary JSON passthrough is ever performed.
# ---------------------------------------------------------------------------

_KR_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
    re.ASCII,
)
# Required non-optional UUID members (all remapped per copy).
_KR_UUID_FIELDS = (
    "source_gateway_key_id",
    "operation_uuid",
    "target_gateway_key_id",
    "target_owner_id",
    "one_time_secret_id",
)
# Nullable UUID members (remapped when present).
_KR_OPTIONAL_UUID_FIELDS = ("email_delivery_id", "target_cohort_id")
# Fingerprint members -> per-copy synthetic 64-hex (column-salted, so the
# two receipts of the same raw value stay distinct and never a source digest).
_KR_HEX64_FIELDS = {
    "source_fingerprint": b"kr_source_fingerprint",
    "policy_fingerprint": b"kr_policy_fingerprint",
}
# Stable business-public identifier (per-copy string remap, like public_key_id).
_KR_STR_FIELDS = ("source_public_key_id",)
# Bounded validity timestamp / window members, mirrored PER FIELD from
# the actual producer's acceptance set: the supported clone flow writes
# ``source_valid_until`` with ``datetime.isoformat()`` (always a full
# aware timestamp), while absolute-mode ``validity_from``/
# ``validity_until`` are the operator's plan text preserved verbatim
# (the plan schema ``_iso_string`` accepts any
# ``datetime.fromisoformat``-parseable string, including a bare ISO
# date, and ``attach_clone_receipt`` persists the plan string).
# Free text, blank, padded and wrong-typed non-null values fail the
# copy closed - never silently rewritten.
_KR_OPTIONAL_STR_FIELDS = ("source_valid_until", "validity_from", "validity_until")
# Only the absolute-mode plan-text members: the CLI/service clone flow
# may persist a bare ISO date verbatim (the GUI form normalizes to a
# full timestamp via ``_parse_admin_datetime`` + ``isoformat()``).
_KR_BARE_DATE_FIELDS = frozenset({"validity_from", "validity_until"})
_KR_BOOL_FIELDS = ("requires_fenced_confirmation",)
_KR_INT_FIELDS = ("validity_duration_seconds",)
_KR_ENUM_FIELD = "validity_mode"
_KR_STATUS_FIELD = "status"
_KR_VALIDITY_MODES = frozenset(
    {_KR_VALIDITY_COPY_SOURCE, _KR_VALIDITY_DURATION, _KR_VALIDITY_ABSOLUTE}
)
_KR_STATUS_VALUE = "created"
# The COMPLETE closed field set: exactly these 17 members, no more, no less.
_KR_ALL_FIELDS = frozenset(
    _KR_UUID_FIELDS
    + _KR_OPTIONAL_UUID_FIELDS
    + tuple(_KR_HEX64_FIELDS)
    + _KR_STR_FIELDS
    + _KR_OPTIONAL_STR_FIELDS
    + _KR_BOOL_FIELDS
    + _KR_INT_FIELDS
    + (_KR_ENUM_FIELD, _KR_STATUS_FIELD)
)
_KR_STR_MAX_LEN = 256


# Bare date-only strings (dashed and compact ISO-8601 basic forms).
_KR_BARE_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_KR_BARE_DATE_COMPACT_RE = re.compile(r"\d{8}")


def _kr_is_receipt_timestamp(value: object, *, allow_bare_date: bool) -> bool:
    """Bounded predicate for one optional validity timestamp member.

    Mirrors the actual producer's acceptance set for that member:
    non-blank, unpadded and ``datetime.fromisoformat``-parseable. The
    flow writes ``source_valid_until`` with ``datetime.isoformat()`` on
    a UTC-normalized datetime (never a bare date), while absolute-mode
    ``validity_from``/``validity_until`` are the operator's plan text
    preserved verbatim - which may be a bare ISO date (interpreted as
    midnight UTC by the product's own ``_aware_fromiso``) as well as
    offset/Z, naive, space-separated, minute-precision or compact
    spellings. Accepted values are preserved verbatim and are NOT
    asserted to be timezone-aware or normalized.
    """
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    if not allow_bare_date and (
        _KR_BARE_DATE_RE.fullmatch(value) or _KR_BARE_DATE_COMPACT_RE.fullmatch(value)
    ):
        return False
    return True


def _kr_validity_member(value: object, name: str) -> str | None:
    """Project one optional validity timestamp member (fail closed).

    ``None`` stays ``None``. A non-null member must be in that
    member's producer acceptance set (see
    ``_kr_is_receipt_timestamp``): a well-formed ISO-8601 value, with a
    bare date allowed only for the absolute-mode plan-text members.
    Malformed values fail the copy closed - the error carries only the
    member name, never the raw value - because a malformed recognized
    receipt is not projectable.
    """
    if value is None:
        return None
    if not _kr_is_receipt_timestamp(
        value, allow_bare_date=name in _KR_BARE_DATE_FIELDS
    ):
        raise _kr_malformed(name)
    return value


def _kr_malformed(param: str) -> ds.DemoSnapshotError:
    return ds.DemoSnapshotError(
        ds.CODE_SANITIZE_FAILED,
        f"Demo copy clone receipt is malformed (member: {param}).",
    )


def _canonical_json(obj: object) -> str:
    """Canonical serialization used for the keyed receipt digest."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _kr_digest(seed: bytes, row_id: str, canonical: str) -> str:
    """Collision-resistant keyed digest of one row's expected receipt.

    Keyed by the per-copy seed and the REMAPPED row id so a second copy can
    never reuse a first copy's expectation, and a single mutated projected
    field changes the digest. Only the digest (never the receipt) is kept in
    the private pre-state.
    """
    return hashlib.sha256(
        seed + b"|kr|" + row_id.encode("ascii") + b"|" + canonical.encode("ascii")
    ).hexdigest()


def _project_clone_receipt(receipt: object, seed: bytes) -> dict[str, object]:
    """Strict, closed projection of one recognized 208 clone receipt.

    Accepts EXACTLY the 17 reviewed members with their exact finite types.
    Every identifying value is remapped per copy (UUIDs via the global
    per-copy bijection, the public key id via the string remap, the two
    fingerprints via the column-salted 64-hex remap); display status and
    the bounded nonsecret validity members are preserved verbatim ONLY
    when they are in that member's producer acceptance set: well-formed
    ISO-8601 values, with a bare ISO date allowed only for the
    absolute-mode ``validity_from``/``validity_until`` plan text (never
    for ``source_valid_until``), and never free text. Any deviation - a
    missing/unknown member, an unexpected type, a wrong status or
    validity mode, or a malformed non-null validity value - fails closed
    (raises) so a partial or tampered receipt is never projected into
    the copy.
    """
    if not isinstance(receipt, dict):
        raise _kr_malformed("clone_receipt")
    if set(receipt) != _KR_ALL_FIELDS:
        raise _kr_malformed("member-set")

    def _remap_uuid_field(name: str) -> str:
        value = receipt[name]
        if not isinstance(value, str) or not _KR_UUID_RE.fullmatch(value):
            raise _kr_malformed(name)
        return str(remap_uuid(seed, _uuid.UUID(value)))

    def _opt_uuid_field(name: str) -> str | None:
        value = receipt[name]
        if value is None:
            return None
        if not isinstance(value, str) or not _KR_UUID_RE.fullmatch(value):
            raise _kr_malformed(name)
        return str(remap_uuid(seed, _uuid.UUID(value)))

    out: dict[str, object] = {}
    for name in _KR_UUID_FIELDS:
        out[name] = _remap_uuid_field(name)
    for name in _KR_OPTIONAL_UUID_FIELDS:
        out[name] = _opt_uuid_field(name)
    for name, salt in _KR_HEX64_FIELDS.items():
        value = receipt[name]
        if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
            raise _kr_malformed(name)
        out[name] = remap_hex64(seed, salt, value)
    for name in _KR_STR_FIELDS:
        value = receipt[name]
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > _KR_STR_MAX_LEN
        ):
            raise _kr_malformed(name)
        out[name] = remap_str_id(seed, value)
    for name in _KR_OPTIONAL_STR_FIELDS:
        out[name] = _kr_validity_member(receipt[name], name)
    for name in _KR_BOOL_FIELDS:
        value = receipt[name]
        if not isinstance(value, bool):
            raise _kr_malformed(name)
        out[name] = value
    for name in _KR_INT_FIELDS:
        value = receipt[name]
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise _kr_malformed(name)
        out[name] = value
    mode = receipt[_KR_ENUM_FIELD]
    if mode not in _KR_VALIDITY_MODES:
        raise _kr_malformed(_KR_ENUM_FIELD)
    out[_KR_ENUM_FIELD] = mode
    if receipt[_KR_STATUS_FIELD] != _KR_STATUS_VALUE:
        raise _kr_malformed(_KR_STATUS_FIELD)
    out[_KR_STATUS_FIELD] = _KR_STATUS_VALUE
    return out


def _kr_metadata_object(raw: object) -> dict[str, object] | None:
    """Parse a stored/raw JSONB metadata value.

    Returns the metadata object, or ``None`` when the value is valid JSON
    that is NOT an object (an array or scalar can never carry a namespaced
    receipt). Invalid JSON or an unsupported input shape fails closed
    (raises).
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (str, bytes)):
        try:
            parsed = json.loads(raw)
        except ValueError:
            raise _kr_malformed("clone_receipt") from None
        return parsed if isinstance(parsed, dict) else None
    raise _kr_malformed("clone_receipt")


def _expected_kr_metadata(raw: object, seed: bytes) -> dict[str, object]:
    """Expected POST-rewrite metadata for one gateway_keys row.

    No receipt -> ``{}`` (J0-equivalent: ordinary metadata is cleared). A
    recognized, well-formed receipt -> exactly ``{"clone_receipt":
    <projected>}``; every other metadata member is discarded. A malformed
    receipt fails the copy closed (raises).
    """
    metadata = _kr_metadata_object(raw)
    if metadata is None or _KR_RECEIPT_KEY not in metadata:
        return {}
    projected = _project_clone_receipt(metadata[_KR_RECEIPT_KEY], seed)
    return {_KR_RECEIPT_KEY: projected}


def _project_gateway_key_metadata(raw: object, seed: bytes) -> str:
    """KR converter entry: canonical JSON of the expected metadata."""
    return _canonical_json(_expected_kr_metadata(raw, seed))


def _is_projected_receipt_metadata(value: object) -> bool:
    """INDEPENDENT structural proof for a stored KR value (verifier side).

    Deliberately re-proves the shape from the stored value alone (not by
    re-running the converter): the stored metadata must be exactly one
    well-formed projected clone receipt - every member present with its
    remapped (per-copy) type, no unknown/raw nested member. Any raw
    source value, extra key, or wrong type fails this check.
    """
    if isinstance(value, (str, bytes)):
        try:
            parsed = json.loads(value)
        except ValueError:
            return False
    else:
        parsed = value
    if not isinstance(parsed, dict) or set(parsed) != {_KR_RECEIPT_KEY}:
        return False
    receipt = parsed[_KR_RECEIPT_KEY]
    if not isinstance(receipt, dict) or set(receipt) != _KR_ALL_FIELDS:
        return False
    for name in _KR_UUID_FIELDS + _KR_OPTIONAL_UUID_FIELDS:
        v = receipt[name]
        if v is not None and (
            not isinstance(v, str) or not _UUID_RE.fullmatch(v)
        ):
            return False
    for name in _KR_HEX64_FIELDS:
        v = receipt[name]
        if not isinstance(v, str) or not _HEX64_RE.fullmatch(v):
            return False
    for name in _KR_STR_FIELDS:
        v = receipt[name]
        if not isinstance(v, str) or not v.strip() or len(v) > _KR_STR_MAX_LEN:
            return False
    for name in _KR_OPTIONAL_STR_FIELDS:
        v = receipt[name]
        # Stored value must be exactly what the projection can emit:
        # None or one value in that member's producer acceptance set
        # (the same per-field law the projector enforces, re-proven
        # independently).
        if v is not None and not _kr_is_receipt_timestamp(
            v, allow_bare_date=name in _KR_BARE_DATE_FIELDS
        ):
            return False
    for name in _KR_BOOL_FIELDS:
        if not isinstance(receipt[name], bool):
            return False
    for name in _KR_INT_FIELDS:
        v = receipt[name]
        if v is not None and (isinstance(v, bool) or not isinstance(v, int)):
            return False
    if receipt[_KR_ENUM_FIELD] not in _KR_VALIDITY_MODES:
        return False
    if receipt[_KR_STATUS_FIELD] != _KR_STATUS_VALUE:
        return False
    return True


def _convert_value(
    action: str,
    value: object,
    *,
    seed: bytes,
    data: dict[str, object],
    maps: _IdentityMaps,
    table: str,
    column: str,
    row: asyncpg.Record,
    row_index: int,
) -> object:
    if action == U:
        if value is None:
            return None
        if not isinstance(value, _uuid.UUID):
            raise _unsupported_shape()
        return remap_uuid(seed, value)
    if action == S:
        if value is None:
            return None
        if not isinstance(value, str):
            raise _unsupported_shape()
        return remap_str_id(seed, value)
    if action == H:
        if value is None:
            return None
        if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
            raise _unsupported_shape()
        return remap_hex64(seed, column.encode("utf-8"), value)
    if action in (FTN, FN):
        item_kind = row[_FTN_KIND_COLUMN]
        if item_kind in _FTN_NULL_KINDS:
            return None
        if item_kind not in _FTN_FIXED_KINDS:
            raise _unsupported_shape()
        return data[_FTN_DATA_KEY if action == FTN else _FN_DATA_KEY]
    if action == N:
        return None
    if action == J0:
        return "{}"
    if action == JA:
        return "[]"
    if action == KR:
        # Clone-receipt projection: ordinary metadata -> {}; a recognized
        # well-formed receipt -> the closed typed projection. Malformed
        # receipts raise (fail the whole copy closed).
        return _project_gateway_key_metadata(value, seed)
    if action == JJ:
        if not _jj_is_valid(table, column, value):
            raise ds.DemoSnapshotError(
                ds.CODE_SANITIZE_FAILED,
                "Demo copy typed JSONB value failed its reviewed shape check.",
            )
        return value
    if action == RC:
        return _transform_route_capabilities(value, seed)
    if action == JU:
        return _remap_uuid_array(value, seed)
    if action == IP:
        ips = data["fictional_ips"]  # type: ignore[index]
        assert isinstance(ips, list)
        return ips[row_index % len(ips)]
    if action == UA:
        agents = data["user_agents"]  # type: ignore[index]
        assert isinstance(agents, list)
        return agents[0]
    if action.startswith("F:") or action.startswith("FC:"):
        return data[action.split(":", 1)[1]]
    if action in _E_ACTIONS:
        attr, ref_column = _E_BINDINGS[(table, column)]
        ref_value = row[ref_column]
        if ref_value is None:
            if (table, column) == ("email_deliveries", "recipient_email"):
                row_id = row["id"]
                if not isinstance(row_id, _uuid.UUID):
                    raise _unsupported_shape()
                return _orphan_recipient_email(remap_uuid(seed, row_id), data)
            return None
        mapping = getattr(maps, attr)
        key = str(ref_value)
        if key not in mapping:
            raise ds.DemoSnapshotError(
                ds.CODE_SANITIZE_FAILED,
                "Demo sanitization internal mapping miss.",
            )
        return mapping[key]
    raise _unsupported_shape()


# ---------------------------------------------------------------------------
# The single transactional sanitizer
# ---------------------------------------------------------------------------


async def _run_sanitizer_tx(
    conn: asyncpg.Connection,
    pre: dict[str, object],
    maps: _IdentityMaps,
    data: dict[str, object],
    seed: bytes,
    deadline: float,
) -> None:
    """Drop FKs, remap every non-preserved column, recreate byte-identical
    FKs, and commit. ANY error rolls the whole transaction back, so the
    copy is either fully sanitized or exactly as it was."""
    tables = pre["tables"]  # type: ignore[assignment]
    pk_map = pre["pk"]  # type: ignore[assignment]
    foreign_keys = pre["foreign_keys"]  # type: ignore[assignment]
    async with conn.transaction():
        for fk in foreign_keys:
            await conn.execute(
                f"ALTER TABLE public.{_q(fk['table_name'])} "
                f"DROP CONSTRAINT {_q(fk['conname'])}"
            )
            _ensure_before_deadline(deadline)
        for table in sorted(tables):
            _ensure_before_deadline(deadline)
            columns = tables[table]
            plan = _build_plan(table, list(pk_map[table]), columns)
            if not plan.set_cols:
                continue
            fetch_sql = (
                "SELECT "
                + ", ".join(_q(c) for c in plan.fetch_cols)
                + f" FROM public.{_q(table)} ORDER BY "
                + ", ".join(_q(c) for c in plan.pk)
            )
            row_count = int(
                await conn.fetchval(f"SELECT count(*) FROM public.{_q(table)}")
            )
            if row_count > _MAX_ROWS_PER_TABLE:
                raise ds.DemoSnapshotError(
                    ds.CODE_SANITIZE_FAILED,
                    "Demo copy table exceeded the bounded row budget.",
                )
            rows = await conn.fetch(fetch_sql)
            if len(rows) > _MAX_ROWS_PER_TABLE:
                raise ds.DemoSnapshotError(
                    ds.CODE_SANITIZE_FAILED,
                    "Demo copy table exceeded the bounded row budget.",
                )
            n_set = len(plan.set_cols)
            assignments = ", ".join(
                f"{_q(c)} = ${i + 1}" for i, c in enumerate(plan.set_cols)
            )
            where = " AND ".join(
                f"{_q(c)} = ${n_set + i + 1}" for i, c in enumerate(plan.pk)
            )
            update_sql = (
                f"UPDATE public.{_q(table)} SET {assignments} WHERE {where}"
            )
            for start in range(0, len(rows), _EXECUTE_CHUNK):
                chunk = rows[start : start + _EXECUTE_CHUNK]
                params: list[tuple[object, ...]] = []
                for local_index, row in enumerate(chunk):
                    values: list[object] = []
                    for c in plan.set_cols:
                        values.append(
                            _convert_value(
                                TABLE_POLICY[table][c],
                                row[c],
                                seed=seed,
                                data=data,
                                maps=maps,
                                table=table,
                                column=c,
                                row=row,
                                row_index=start + local_index,
                            )
                        )
                    values.extend(row[c] for c in plan.pk)
                    params.append(tuple(values))
                await conn.executemany(update_sql, params)
                _ensure_before_deadline(deadline)
        for fk in foreign_keys:
            await conn.execute(_fk_recreate_sql(fk))
            _ensure_before_deadline(deadline)


# ---------------------------------------------------------------------------
# Independent read-only verifier (separate connection, after commit)
# ---------------------------------------------------------------------------


_S_PATTERN = r"^demo[0-9a-f]{60}$"
_HEX64_PATTERN = r"^[0-9a-f]{64}$"


async def _column_violations(
    conn: asyncpg.Connection,
    table: str,
    column: str,
    action: str,
    data: dict[str, object],
    maps: _IdentityMaps | None = None,
) -> int:
    col = _q(column)
    tbl = f"public.{_q(table)}"
    if action == N:
        return int(await conn.fetchval(f"SELECT count(*) FROM {tbl} WHERE {col} IS NOT NULL"))
    if action == J0:
        return int(await conn.fetchval(f"SELECT count(*) FROM {tbl} WHERE {col} <> $1", "{}"))
    if action == JA:
        return int(await conn.fetchval(f"SELECT count(*) FROM {tbl} WHERE {col} <> $1", "[]"))
    if action == KR:
        # A stored value must be exactly {} OR one well-formed projected
        # clone receipt (independent structural proof; the exact per-row
        # content law is the keyed pre-state digest in _verify_clone_receipts).
        nonempty = await conn.fetch(
            f"SELECT {col} AS v FROM {tbl} WHERE {col} IS NOT NULL AND {col} <> $1",
            "{}",
        )
        _bad = [row for row in nonempty if not _is_projected_receipt_metadata(row["v"])]
        return len(_bad)
    if action.startswith("F:") or action.startswith("FC:"):
        value = str(data[action.split(":", 1)[1]])
        return int(await conn.fetchval(f"SELECT count(*) FROM {tbl} WHERE {col} <> $1", value))
    if action == S:
        # 224-s: shape only. Every stored value must match the remapped
        # demo[0-9a-f]{60} pattern (a raw value that happens to match is
        # still caught by the keyed pre-state multiset digest in
        # _run_verifier). The old blanket distinctness law was a false
        # positive: S columns such as
        # catalog_refresh_applications.operator_actor / db_actor repeat
        # naturally across applies, so the SAME remapped value may
        # legitimately recur. Distinctness is re-checked in _run_verifier
        # ONLY where the reviewed schema declares a single-column
        # UNIQUE/PK on the column.
        return int(
            await conn.fetchval(
                f"SELECT count(*) FROM {tbl} "
                f"WHERE {col} IS NOT NULL AND {col} !~ $1",
                _S_PATTERN,
            )
        )
    if action == H:
        # Shape only. The raw value already matches the same 64-hex
        # pattern, so shape cannot prove remapping, and the schema's
        # unique law is the COMPOSITE (gateway_key_id, item_kind, hmac)
        # constraint — a raw HMAC may legitimately recur across keys, so
        # no global distinctness rule is imposed here. Exact per-copy
        # value law is proven by the keyed pre-state aggregate in
        # _run_verifier (a per-column multiset proof; it does not prove
        # row-level placement of individual values).
        return int(
            await conn.fetchval(
                f"SELECT count(*) FROM {tbl} "
                f"WHERE {col} IS NOT NULL AND {col} !~ $1",
                _HEX64_PATTERN,
            )
        )
    if action in (FTN, FN):
        value = str(data[_FTN_DATA_KEY if action == FTN else _FN_DATA_KEY])
        return int(
            await conn.fetchval(
                f"SELECT count(*) FROM {tbl} WHERE "
                f"(({_q(_FTN_KIND_COLUMN)} = ANY($1::text[])) "
                f"AND {col} IS DISTINCT FROM $2) "
                f"OR (({_q(_FTN_KIND_COLUMN)} = ANY($3::text[])) "
                f"AND {col} IS NOT NULL)",
                sorted(_FTN_FIXED_KINDS),
                value,
                sorted(_FTN_NULL_KINDS),
            )
        )
    if action == U:
        # U columns are uuid-typed, so the exact SQL type (and hence the
        # UUID shape) is already re-proved by the catalog signature check;
        # a per-value shape check here would be redundant. The per-copy
        # remap law for U columns is proven in _run_verifier by the keyed
        # pre-state multiset digests (repeated raw FK values keep the same
        # per-copy mapping) plus declared-uniqueness re-checks ONLY where
        # the reviewed schema declares a single-column UNIQUE/PK. The old
        # blanket distinctness check wrongly rejected legitimate repeated
        # FK values (e.g. two gateway keys of the same owner).
        return 0
    if action == JJ:
        bad = int(
            await conn.fetchval(f"SELECT count(*) FROM {tbl} WHERE {col} IS NOT NULL")
        )
        if not bad:
            return 0
        # Re-prove every stored value against its reviewed typed shape.
        values = [
            row["v"]
            for row in await conn.fetch(f"SELECT {col} AS v FROM {tbl} WHERE {col} IS NOT NULL")
        ]
        return sum(1 for v in values if not _jj_is_valid(table, column, v))
    if action == RC:
        rows = await conn.fetch(
            f"SELECT {col} AS v FROM {tbl} WHERE {col} IS NOT NULL"
        )
        if not rows:
            return 0
        # Compaction ids must link to COPIED route ids (remapped), so the
        # verifier re-proves them against the copied route id set.
        route_ids = frozenset(
            str(row["id"])
            for row in await conn.fetch("SELECT id FROM public.model_routes")
        )
        return sum(
            1 for row in rows if not _verify_route_capabilities(row["v"], route_ids)
        )
    if action == JU:
        values = [
            row["v"]
            for row in await conn.fetch(f"SELECT {col} AS v FROM {tbl} WHERE {col} IS NOT NULL")
        ]
        return sum(1 for v in values if not _ju_is_safe(v))
    if action == IP:
        # The IP columns are typed inet in the reviewed catalog; the
        # converter writes bare hosts (stored as /32). Compare TYPED inet
        # values, not rendered text: inet::text renders a host address
        # with an explicit /32 suffix that would never string-match the
        # bare fictional list, and a typed comparison also rejects an
        # unexpected network prefix (a host() comparison would not).
        ips = data["fictional_ips"]
        return int(
            await conn.fetchval(
                f"SELECT count(*) FROM {tbl} WHERE {col} IS NOT NULL "
                f"AND {col} <> ALL($1::inet[])",
                [str(x) for x in ips],
            )
        )
    if action == UA:
        agents = data["user_agents"]
        return int(
            await conn.fetchval(
                f"SELECT count(*) FROM {tbl} WHERE {col} IS NOT NULL AND {col} <> $1",
                str(agents[0]),
            )
        )
    if action in _E_ACTIONS:
        if maps is None:
            raise RuntimeError("E_* verification requires the per-copy maps")
        attr, _ref = _E_BINDINGS[(table, column)]
        allowed = frozenset(getattr(maps, attr).values())
        if (table, column) == ("email_deliveries", "recipient_email"):
            # Linked rows must carry EXACTLY their own owner's sanitized
            # email: set membership alone would let owner A's delivery
            # pass with owner B's fake address. FK integrity (recreated in
            # the transaction) guarantees the owner row exists.
            linked_bad = int(
                await conn.fetchval(
                    f"SELECT count(*) FROM {tbl} e "
                    "JOIN public.owners o ON o.id = e.owner_id "
                    f"WHERE e.{col} IS NOT NULL "
                    f"AND e.{col}::text <> o.email::text"
                )
            )
            orphan_rows = [
                row
                for row in await conn.fetch(
                    f"SELECT id, {col} AS v FROM {tbl} "
                    f"WHERE owner_id IS NULL AND {col} IS NOT NULL"
                )
            ]
            orphan_bad = sum(
                1
                for row in orphan_rows
                if row["v"] != _orphan_recipient_email(row["id"], data)
            )
            return linked_bad + orphan_bad
        return int(
            await conn.fetchval(
                f"SELECT count(*) FROM {tbl} WHERE {col} IS NOT NULL AND {col}::text <> ALL($1)",
                sorted(allowed),
            )
        )
    return 0


async def _verify_clone_receipts(
    conn: asyncpg.Connection,
    pre: dict[str, object],
    seed: bytes,
    deadline: float,
) -> None:
    """224-r: independently re-prove the per-row clone-receipt law.

    Runs on a separate read-only connection AFTER commit:
    - the SET of stored non-empty ``gateway_keys.metadata`` receipts exactly
      equals the pre-state expectation set (no missing and no extra rows);
    - every stored receipt's keyed digest (computed from the STORED value)
      equals the pre-state expectation projected from the RAW source receipt
      before the rewrite, so an adversarial mutation of any single projected
      field fails publication;
    - link consistency: the receipt's target id equals the containing row id
      and its source id is a real copied ``gateway_keys.id`` (no dangling or
      cross-copy links).
    """
    verify_failed = ds.CODE_SANITIZE_VERIFY_FAILED
    _ensure_before_deadline(deadline)
    kr_expected = pre.get("kr_expected") or {}
    copied_ids = frozenset(
        str(row["id"])
        for row in await conn.fetch("SELECT id FROM public.gateway_keys")
    )
    stored_rows = await conn.fetch(
        "SELECT id::text AS id, metadata AS m FROM public.gateway_keys "
        "WHERE metadata IS NOT NULL AND metadata <> '{}'::jsonb"
    )
    stored_ids: set[str] = set()
    for row in stored_rows:
        _ensure_before_deadline(deadline)
        rid = row["id"]
        stored_ids.add(rid)
        expected_digest = kr_expected.get(rid)
        if expected_digest is None:
            raise ds.DemoSnapshotError(
                verify_failed,
                "Demo copy has a clone receipt with no pre-state expectation.",
            )
        try:
            parsed = json.loads(row["m"])
        except ValueError:
            raise ds.DemoSnapshotError(
                verify_failed,
                "Demo copy stored clone receipt is not valid JSON.",
            ) from None
        if not isinstance(parsed, dict):
            raise ds.DemoSnapshotError(
                verify_failed,
                "Demo copy stored clone receipt is not a JSON object.",
            )
        if _kr_digest(seed, rid, _canonical_json(parsed)) != expected_digest:
            raise ds.DemoSnapshotError(
                verify_failed,
                "Demo copy stored clone receipt does not match the expected per-copy projection.",
            )
        receipt = parsed.get(_KR_RECEIPT_KEY)
        if not isinstance(receipt, dict):
            raise ds.DemoSnapshotError(
                verify_failed,
                "Demo copy stored clone receipt is missing its receipt member.",
            )
        if receipt.get("target_gateway_key_id") != rid:
            raise ds.DemoSnapshotError(
                verify_failed,
                "Demo copy clone receipt target does not match its key row.",
            )
        if receipt.get("source_gateway_key_id") not in copied_ids:
            raise ds.DemoSnapshotError(
                verify_failed,
                "Demo copy clone receipt source link is dangling or cross-copy.",
            )
    if stored_ids != set(kr_expected.keys()):
        raise ds.DemoSnapshotError(
            verify_failed,
            "Demo copy clone receipt set does not match the pre-state expectation.",
        )


async def _run_verifier(
    conn: asyncpg.Connection,
    pre: dict[str, object],
    data: dict[str, object],
    seed: bytes,
    deadline: float,
) -> None:
    """Re-prove, read-only and independently: catalog law, constraint law,
    FK inventory, row counts, preserved checksums, masked changes and the
    policy-driven exact credential/value invalidation. The same absolute
    deadline that bounds the sanitizer transaction also bounds this phase
    (per-statement and command timeouts additionally bound the waits)."""
    verify_failed = ds.CODE_SANITIZE_VERIFY_FAILED
    _ensure_before_deadline(deadline)
    inventory = await _inventory_catalog(conn)
    _check_catalog(inventory)  # re-proves the COMPLETE constraint set too

    tables = pre["tables"]  # type: ignore[assignment]
    stats = await _table_stats(  # type: ignore[arg-type]
        conn,
        tables,
        {t: int(pre["stats"][t]["count"]) for t in tables},  # type: ignore[index]
        deadline,
    )
    for table in sorted(tables):
        _ensure_before_deadline(deadline)
        expected = pre["stats"][table]  # type: ignore[index]
        actual = stats[table]
        if actual["count"] != expected["count"]:
            raise ds.DemoSnapshotError(
                verify_failed,
                "Demo copy row count changed during sanitization.",
            )
        if actual["preserved_md5"] != expected["preserved_md5"]:
            raise ds.DemoSnapshotError(
                verify_failed,
                "Demo copy preserved values changed during sanitization.",
            )
        if (
            expected["masked_nonnull_rows"] > 0  # type: ignore[index]
            and actual["masked_md5"] == expected["masked_md5"]
        ):
            raise ds.DemoSnapshotError(
                verify_failed,
                "Demo copy masked values did not change as required.",
            )

    maps = build_identity_maps(seed, data, **pre["entity_ids"])  # type: ignore[arg-type]
    for table in sorted(tables):
        _ensure_before_deadline(deadline)
        for column, action in TABLE_POLICY[table].items():
            if action == P:
                continue
            violations = await _column_violations(
                conn, table, column, action, data, maps=maps
            )
            if violations:
                raise ds.DemoSnapshotError(
                    verify_failed,
                    "Demo copy credential or fixed-value invalidation incomplete.",
                )

    # Exact per-copy H remap law: recompute the keyed multiset digest
    # from the STORED values and require equality with the pre-state
    # expectation derived from the raw values before the rewrite.
    # Stored values are hashed as-is (no second remap): the pre-state
    # side already projected raw values onto the expected value space.
    h_expected = pre["h_expected"]  # type: ignore[assignment]
    for table in sorted(tables):
        for column in sorted(h_expected.get(table, {})):
            _ensure_before_deadline(deadline)
            rows = await conn.fetch(
                f"SELECT {_q(column)} AS v FROM public.{_q(table)} "
                f"WHERE {_q(column)} IS NOT NULL"
            )
            if (
                _h_column_digest(
                    seed, column, [str(r["v"]) for r in rows]
                )
                != h_expected[table][column]
            ):
                raise ds.DemoSnapshotError(
                    verify_failed,
                    "Demo copy H-remapped values do not match the expected per-copy remap.",
                )

    # 224-r exact per-copy U remap law: recompute the keyed multiset
    # digest from the STORED values and require equality with the
    # pre-state expectation derived from the raw values before the
    # rewrite. Repeated raw FK values (e.g. two gateway keys of one
    # owner) must appear under the SAME per-copy remapped value; a raw
    # (un-remapped) value or any other substitution breaks equality.
    # Uniqueness is re-checked ONLY where the reviewed schema declares a
    # single-column UNIQUE/PK on that column - the old blanket
    # distinctness law was a false positive for repeated FK values.
    u_expected = pre["u_expected"]  # type: ignore[assignment]
    declared_unique = _declared_unique_single_columns(inventory["constraints"])
    for table in sorted(u_expected):
        for column in sorted(u_expected[table]):
            _ensure_before_deadline(deadline)
            rows = await conn.fetch(
                f"SELECT {_q(column)} AS v FROM public.{_q(table)} "
                f"WHERE {_q(column)} IS NOT NULL"
            )
            if (
                _u_column_digest(
                    seed, table, column, [str(r["v"]) for r in rows]
                )
                != u_expected[table][column]
            ):
                raise ds.DemoSnapshotError(
                    verify_failed,
                    "Demo copy U-remapped values do not match the expected per-copy remap.",
                )
            if column in declared_unique.get(table, frozenset()):
                dup = int(
                    await conn.fetchval(
                        f"SELECT count(*) - count(DISTINCT {_q(column)}) "
                        f"FROM public.{_q(table)} WHERE {_q(column)} IS NOT NULL"
                    )
                )
                if dup:
                    raise ds.DemoSnapshotError(
                        verify_failed,
                        "Demo copy U column violates a declared uniqueness constraint.",
                    )

    # 224-s exact per-copy S remap law: recompute the keyed multiset
    # digest from the STORED values and require equality with the
    # pre-state expectation derived from the raw values before the
    # rewrite. Repeated raw values (e.g. the same operator_actor /
    # db_actor across two catalog applies) must appear under the SAME
    # per-copy remapped value; a raw (un-remapped) value or any other
    # substitution breaks equality. Uniqueness is re-checked ONLY where
    # the reviewed schema declares a single-column UNIQUE/PK on that
    # column - the old blanket distinctness law was a false positive for
    # naturally repeating text fields.
    s_expected = pre["s_expected"]  # type: ignore[assignment]
    for table in sorted(s_expected):
        for column in sorted(s_expected[table]):
            _ensure_before_deadline(deadline)
            rows = await conn.fetch(
                f"SELECT {_q(column)} AS v FROM public.{_q(table)} "
                f"WHERE {_q(column)} IS NOT NULL"
            )
            if (
                _s_column_digest(
                    seed, table, column, [str(r["v"]) for r in rows]
                )
                != s_expected[table][column]
            ):
                raise ds.DemoSnapshotError(
                    verify_failed,
                    "Demo copy S-remapped values do not match the expected per-copy remap.",
                )
            if column in declared_unique.get(table, frozenset()):
                dup = int(
                    await conn.fetchval(
                        f"SELECT count(*) - count(DISTINCT {_q(column)}) "
                        f"FROM public.{_q(table)} WHERE {_q(column)} IS NOT NULL"
                    )
                )
                if dup:
                    raise ds.DemoSnapshotError(
                        verify_failed,
                        "Demo copy S column violates a declared uniqueness constraint.",
                    )

    # 224-r exact per-row clone-receipt law: recompute the keyed digest of
    # every stored receipt from the STORED value and require equality with
    # the pre-state expectation projected from the RAW source receipt, plus
    # link consistency on a separate connection.
    await _verify_clone_receipts(conn, pre, seed, deadline)

    public_connect = await conn.fetchval(
        "SELECT count(*) FROM pg_database d "
        "CROSS JOIN LATERAL aclexplode("
        "COALESCE(d.datacl, acldefault('d', d.datdba))) a "
        "WHERE d.datname = current_database() "
        "AND a.grantee = 0 AND a.privilege_type = 'CONNECT'"
    )
    if int(public_connect) > 0:
        raise ds.DemoSnapshotError(
            verify_failed,
            "Demo copy still grants CONNECT to PUBLIC.",
        )
    # A NULL datacl is the DEFAULT database ACL, which includes PUBLIC
    # CONNECT: acldefault above makes that case fail closed too. An
    # explicitly restricted copy (REVOKE CONNECT FROM PUBLIC, grant to the
    # target user only) is the only passing form.


# ---------------------------------------------------------------------------
# Per-copy orchestration and the fenced worker entry point
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SanitizeCopyResult:
    state: str
    failure_code: str | None
    job_id: str


@dataclass(frozen=True, slots=True)
class SanitizeCopiesResult:
    state: str
    failure_code: str | None
    copies_sanitized: int
    copies_failed: int
    elapsed_ms: int


SANITIZE_STATE_SANITIZED = "SANITIZED"


def _read_passfile_text(pgpassfile: Path) -> str:
    """Read the credential file through ONE bound, non-following handle.

    Direct asyncpg access does not inherit libpq's credential-file
    contract, so the same restrictive boundary is enforced here: a
    regular (non-symlink) owner-only 0600 file. The check and the read
    use the SAME ``os.open(..., O_NOFOLLOW)`` file descriptor so a
    final-component symlink swap between check and read cannot bypass
    it. Any deviation is a safe finite misconfiguration; the path and
    any password never render.
    """
    try:
        fd = os.open(
            str(pgpassfile),
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
    except OSError:
        raise ds.DemoSnapshotError(
            ds.CODE_MISCONFIGURED,
            "Demo snapshot worker cannot read its credential file.",
        ) from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or (st.st_mode & 0o077) != 0:
            raise ds.DemoSnapshotError(
                ds.CODE_MISCONFIGURED,
                "Demo snapshot worker credential file is not an owner-only regular file.",
            ) from None
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 8192)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(fd)
    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError:
        raise ds.DemoSnapshotError(
            ds.CODE_MISCONFIGURED,
            "Demo snapshot worker cannot read its credential file.",
        ) from None


def _target_password(config: ds.DemoSnapshotConfig) -> str:
    raw = _read_passfile_text(config.pgpassfile)
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.count(":") < 4:
            continue
        host, port, _db, user, password = line.split(":", 4)
        if (
            host in ("*", config.target_host)
            and port in ("*", str(config.target_port))
            and user in ("*", config.target_user)
            and password
        ):
            return password
    raise ds.DemoSnapshotError(
        ds.CODE_MISCONFIGURED,
        "Demo snapshot worker has no usable target credential.",
    )


async def _connect_copy(
    config: ds.DemoSnapshotConfig,
    target_db: str,
    *,
    readonly: bool = False,
    statement_timeout_ms: int | None = None,
) -> asyncpg.Connection:
    server_settings = {"TimeZone": "UTC"}
    if readonly:
        server_settings["default_transaction_read_only"] = "on"
    # asyncpg.connect() has no statement_timeout keyword; it is a session
    # GUC, so it is pinned through server_settings. Callers with a
    # tighter finite budget (e.g. the 223 combined link gate) may pass a
    # bounded override derived from their remaining deadline.
    if statement_timeout_ms is None:
        server_settings["statement_timeout"] = str(_STATEMENT_TIMEOUT_MS)
    elif statement_timeout_ms < 100:
        raise ds.DemoSnapshotError(
            ds.CODE_MISCONFIGURED,
            "The demo copy statement budget is below its finite floor."
        )
    else:
        server_settings["statement_timeout"] = str(statement_timeout_ms)
    return await asyncpg.connect(
        host=config.target_host,
        port=config.target_port,
        user=config.target_user,
        password=_target_password(config),
        database=target_db,
        ssl=False,
        server_settings=server_settings,
        command_timeout=_COMMAND_TIMEOUT_S,
        timeout=_COMMAND_TIMEOUT_S,
    )


async def _close_quiet(conn: asyncpg.Connection) -> None:
    try:
        await conn.close()
    except Exception:
        pass


def _record_failure(
    job_dir: Path, manifest: ds.SnapshotManifest, code: str
) -> SanitizeCopyResult:
    # A failed sanitization never promotes: the copy stays RAW_UNVERIFIED
    # and inspectable (the private pre-state file, when present, is kept).
    manifest.state = ds.STATE_RAW_UNVERIFIED
    manifest.failure_code = code
    try:
        ds._write_manifest(job_dir, manifest)
    except OSError:
        pass
    return SanitizeCopyResult(SANITIZE_STATE_FAILED, code, manifest.job_id)


async def _sanitize_copy_async(
    config: ds.DemoSnapshotConfig,
    job_dir: Path,
    manifest: ds.SnapshotManifest,
    deadline: float,
) -> SanitizeCopyResult:
    data = load_demo_identities()
    _require_data_keys(data)

    seed = manifest.job_id.encode("utf-8")

    conn = await _connect_copy(config, manifest.target_db)
    try:
        inventory = await _inventory_catalog(conn)
        _check_catalog(inventory)
        pre = await _capture_prestate(conn, inventory, seed, deadline)
    except ds.DemoSnapshotError as exc:
        return _record_failure(job_dir, manifest, exc.code)
    except Exception:
        return _record_failure(job_dir, manifest, ds.CODE_UNEXPECTED)
    finally:
        await _close_quiet(conn)

    ds._atomic_write_private(
        job_dir / _PRESTATE_NAME,
        (json.dumps(pre, sort_keys=True) + "\n").encode("utf-8"),
    )

    maps = build_identity_maps(seed, data, **pre["entity_ids"])  # type: ignore[arg-type]

    conn = await _connect_copy(config, manifest.target_db)
    try:
        await _run_sanitizer_tx(conn, pre, maps, data, seed, deadline)
    except ds.DemoSnapshotError as exc:
        return _record_failure(job_dir, manifest, exc.code)
    except Exception:
        return _record_failure(job_dir, manifest, ds.CODE_UNEXPECTED)
    finally:
        await _close_quiet(conn)

    # The transaction committed. Only an INDEPENDENT read-only verification
    # may promote the copy.
    vconn = await _connect_copy(config, manifest.target_db, readonly=True)
    try:
        await _run_verifier(vconn, pre, data, seed, deadline)
    except ds.DemoSnapshotError as exc:
        return _record_failure(job_dir, manifest, exc.code)
    except Exception:
        return _record_failure(job_dir, manifest, ds.CODE_SANITIZE_VERIFY_FAILED)
    finally:
        await _close_quiet(vconn)

    manifest.state = ds.STATE_DB_SANITIZED_UNPUBLISHED
    manifest.failure_code = None
    try:
        ds._write_manifest(job_dir, manifest)
    except OSError:
        return _record_failure(job_dir, manifest, ds.CODE_UNEXPECTED)
    return SanitizeCopyResult(SANITIZE_STATE_PROMOTED, None, manifest.job_id)


def sanitize_copies(
    config: ds.DemoSnapshotConfig,
    *,
    job_id: str | None = None,
) -> SanitizeCopiesResult:
    """Fenced worker entry: sanitize every RAW_UNVERIFIED copy.

    Idempotent: already-sanitized copies are skipped, and a failed copy
    stays RAW_UNVERIFIED with a safe finite code so the operator can
    inspect and re-invoke.

    ``job_id`` (224-b exact worker): sanitize EXACTLY that one custody
    job (addressed by its closed ``snap-<32 hex>`` name, never by
    directory order, timestamps or target database). A missing,
    inconsistent or unexpected-state exact job is a safe finite failure
    (``EXACT_COPY_UNAVAILABLE``); an already-sanitized exact job is an
    idempotent no-op success. Unrelated pre-existing copies are never
    touched or promoted.
    """
    ds._validate_custody_dir(config.custody_dir)
    fence_fd = ds._acquire_fence(config.custody_dir)
    started = time.monotonic()
    try:
        eligible: list[tuple[Path, ds.SnapshotManifest]] = []
        if job_id is not None:
            eligible, error, already_done = _select_exact_sanitize_job(
                config, job_id
            )
            if error is not None:
                return SanitizeCopiesResult(
                    SANITIZE_STATE_FAILED, error, 0, 1,
                    int((time.monotonic() - started) * 1000),
                )
            if already_done:
                # Exact job already sanitized: idempotent no-op success
                # (the worker's success contract requires SANITIZED).
                return SanitizeCopiesResult(
                    SANITIZE_STATE_SANITIZED, None, 0, 0,
                    int((time.monotonic() - started) * 1000),
                )
        else:
            for job_dir in ds._list_job_dirs(config.custody_dir):
                manifest = ds._read_manifest(job_dir)
                if manifest is not None and manifest.state == ds.STATE_RAW_UNVERIFIED:
                    eligible.append((job_dir, manifest))
        if not eligible:
            return SanitizeCopiesResult(
                SANITIZE_STATE_SKIPPED, None, 0, 0,
                int((time.monotonic() - started) * 1000),
            )
        sanitized = 0
        failed = 0
        first_code: str | None = None
        for job_dir, manifest in eligible:
            deadline = time.monotonic() + config.max_elapsed_seconds
            try:
                result = asyncio.run(
                    _sanitize_copy_async(config, job_dir, manifest, deadline)
                )
            except ds.DemoSnapshotError as exc:
                result = SanitizeCopyResult(SANITIZE_STATE_FAILED, exc.code, manifest.job_id)
            except Exception:
                result = SanitizeCopyResult(
                    SANITIZE_STATE_FAILED, ds.CODE_UNEXPECTED, manifest.job_id
                )
            if result.state == SANITIZE_STATE_PROMOTED:
                sanitized += 1
            else:
                failed += 1
                first_code = first_code or result.failure_code
        state = (
            SANITIZE_STATE_SANITIZED
            if failed == 0
            else SANITIZE_STATE_FAILED
        )
        return SanitizeCopiesResult(
            state,
            first_code if failed else None,
            sanitized,
            failed,
            int((time.monotonic() - started) * 1000),
        )
    finally:
        ds._release_fence(fence_fd)


def _select_exact_sanitize_job(
    config: ds.DemoSnapshotConfig,
    job_id: str,
) -> tuple[list[tuple[Path, ds.SnapshotManifest]], str | None, bool]:
    """Resolve EXACTLY one custody job for the 224-b worker (no scan).

    Returns ``(targets, error_code, already_done)``: zero or one target
    and a safe finite error code when the exact job is missing,
    inconsistent or in an unexpected state. An already-sanitized
    (``DB_SANITIZED_UNPUBLISHED``) exact job yields an empty success with
    ``already_done`` (idempotent no-op, still reported as ``SANITIZED``
    so the worker's success contract holds). The job is addressed ONLY by
    its closed ``snap-<32 hex>`` name under the validated custody root;
    the manifest's own job id must agree.
    """
    if not isinstance(job_id, str) or not re.fullmatch(r"snap-[0-9a-f]{32}", job_id):
        return [], ds.CODE_EXACT_COPY_UNAVAILABLE, False
    job_dir = config.custody_dir / job_id
    manifest = ds._read_manifest(job_dir)
    if manifest is None or manifest.job_id != job_id:
        return [], ds.CODE_EXACT_COPY_UNAVAILABLE, False
    if manifest.state == ds.STATE_RAW_UNVERIFIED:
        return [(job_dir, manifest)], None, False
    if manifest.state == ds.STATE_DB_SANITIZED_UNPUBLISHED:
        return [], None, True
    return [], ds.CODE_EXACT_COPY_UNAVAILABLE, False
