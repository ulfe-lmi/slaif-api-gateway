"""Objectives 224-k/224-l: demo-only catalog snapshot metadata, and the
bounded sanitized display-copy artifact download, from one verified copy.

A small, purpose-built router mounted by ``create_demo_app`` ONLY, and
BEFORE the normal catalog-refresh router, so the ONE exact path
``GET /admin/operations/catalog/`` is served by this handler in the
demo process while the normal router's custody-backed handler is
never reached for that path there. Every other catalog path (proposals,
collect, review, export-baseline, run/job artifacts, apply-status,
downloads, previews, verify) stays mounted as before and remains
default-denied by the central demo gate; every unsafe method on
``/admin`` remains the unchanged uniform 204 cut before body parsing
and dispatch.

224-l adds ONE more exact demo-only path,
``GET /admin/operations/catalog/artifact``: it downloads the
worker-published SANITIZED display copy of one already-captured
catalog artifact from this visitor's exact verified copy. The name
query value is a selector ONLY (never authorization, HMAC, replay,
apply or source-file authority); it must satisfy the same closed
remapped catalog name law as the 224-k index before ANY body query,
and the leaf is selected by one PARAMETERIZED exact logical-name
lookup. The read uses the gate's SAME request-local copy engine
(``get_sessionmaker_from_app`` on ``request.state.demo_admin``) in
one read-only transaction that re-verifies ``current_database()``
and ``transaction_read_only`` before the metadata lookup; kind,
byte count and SHA256 are checked first (the existing 32 MiB
catalog per-file maximum BEFORE any body fetch), and the bytea is
fetched and re-verified (exact length + SHA256) before the single
forced-attachment ``application/octet-stream`` response is built.
The body is a sanitized DISPLAY copy: no original seal, no apply
authority, never rendered inline, and no stored hash, DSN,
credential, source path or raw original ever appears in the public
response. Any missing row, invalid closed metadata, bound
violation, digest/size mismatch or driver failure is one fixed safe
refusal (404 for absence, 503 otherwise) with no input echo. What
this handler never touches: source public business tables, live
operator custody, the catalog seal, Redis, the worker filesystem,
provider network or provider credentials.

To be precise about credentials: reaching this handler first
required the gate's LIVE demo-control authorization (reads on the
demo control rows under the demo web role), and the index read
itself uses the operator's restricted SELECT-only copy-reader
credential against the verified target copy only. What this handler
never touches: source public business tables, live operator
custody, the catalog seal, Redis, the worker filesystem, provider
network or provider credentials. The page is built ONLY from the
gate-validated request-local demo state
(``request.state.demo_admin``) and its exact session target through
the existing per-request ``demo_display_reader_factory(...).read_index()``
seam; the reader's database-side read-only / current-database
checks remain authoritative.

Only closed remapped catalog names are presented (bounded areas,
remapped run/job ID shapes, bounded ASCII artifact segments - no dot
traversal, no download URL derived). Bounded kind/size and a finite
representable capture time are required; any invalid display index,
corrupt/unreadable index or unexpected shape renders the fixed safe
unavailable note (no raw DB value, path or traceback).
"""

from __future__ import annotations

import json
import math
import uuid
import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from sqlalchemy import text

from slaif_gateway.api.admin import templates
from slaif_gateway.services.admin_record_choices import load_choices
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services import demo_snapshot_files as dsf
from slaif_gateway.services.request_diagnostics import (
    is_known_incoming_secret_alias,
)
from slaif_gateway.web.formatting import format_number
from slaif_gateway.services.provider_catalog_proposal import OPENROUTER_PACKAGE_ORDER

router = APIRouter(prefix="/admin/operations/catalog", include_in_schema=False)

_MAX_INDEX_ROWS = 4096  # Existing DisplayReader/223 publication bound.
_MAX_CAPTURE_AT = 253_402_300_800.0  # Worker-published ceiling.
_JOB_ID = re.compile(r"[0-9a-f]{32}\Z")
_RUN_ID = re.compile(r"demo-run-[0-9a-f]{24}\Z")
_ARTIFACT_PART = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
_KIND = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_MAX_NAME_LEN = 200  # Worker display-name ceiling.
_SAFE_UNAVAILABLE = "The catalog snapshot index is unavailable for this demo session."
# 224-l: the existing 32 MiB catalog per-file maximum
# (DEMO_SNAPSHOT_FILES_MAX_FILE_BYTES default; the worker's bundle cap
# is tighter). Enforced BEFORE any body fetch.
_MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")
# 224-y: the bounded copied apply-record read law. The copied
# ``catalog_refresh_applications.run_id`` values are the sanitizer's
# S-remap (``demo`` + 60 lowercase hex); the 224-y run slug carries
# the first 24 hex of the SAME keyed digest, so the 96-bit slug
# prefix is the exact derived query prefix. A small bounded result
# plus ONE over-bound probe; any malformed row, more than one
# distinct full remapped run id, or an over-bound result is the
# fixed safe refusal. No-match is UNKNOWN/UNAVAILABLE, never
# "not applied" / "rolled back" (pre-upgrade copies stay safe).
_APPLY_RECORD_BOUND = 4
_S_MAPPED_TEXT = re.compile(r"demo[0-9a-f]{60}\Z")
_APPLY_MODE_VOCAB = frozenset({"bootstrap", "refresh"})
_APPLY_OUTCOME_VOCAB = frozenset({"committed"})
_ALIAS_WITHHELD = "withheld (credential-shaped alias)"
_SAFE_ARTIFACT_UNAVAILABLE = (
    "The catalog artifact is unavailable for this demo session."
)
# 224-m: the worker-published run content set (the closed seven sealed
# run CONTENT_FILES, never a directory scan) with their display kinds.
_RUN_DETAIL_FILES: tuple[tuple[str, str], ...] = (
    ("catalog-refresh.json", dsf.KIND_REFRESH_BUNDLE),
    ("catalog-baseline.json", dsf.KIND_BASELINE_DOC),
    ("routes-proposal.tsv", dsf.KIND_ROUTE_TSV),
    ("pricing-proposal.tsv", dsf.KIND_PRICING_TSV),
    ("fx-proposal.json", dsf.KIND_FX_JSON),
    ("validation.json", dsf.KIND_VALIDATION_JSON),
    ("REVIEW.html", dsf.KIND_REVIEW_HTML),
)
_MAX_DETAIL_LIST_ROWS = 4096
_SAFE_RUN_DETAIL_UNAVAILABLE = (
    "The catalog run detail is unavailable for this demo session."
)
# 224-n: the bounded captured-proposals page law.
_MAX_PROPOSAL_GROUPS = 100  # at most the 100 most-recently-captured jobs
_SAFE_PROPOSALS_UNAVAILABLE = (
    "The catalog proposals page is unavailable for this demo session."
)
# 224-o: the bounded captured complete-runs (collect) page law.
_MAX_RUN_GROUPS = 100  # at most the 100 most-recently-captured runs
_SAFE_COLLECT_UNAVAILABLE = (
    "The catalog collect page is unavailable for this demo session."
)
# 224-p: the demo-only review/export form pages and the bounded
# historical job-record page law. The worker's closed 1 MiB
# job-record ceiling (metadata AND body, cap-before-body).
_MAX_JOB_GROUPS = 100  # at most the 100 most-recently-captured records
_JOB_RECORD_BYTES = dsf._JOB_RECORD_MAX_BYTES  # 1 MiB
_SAFE_JOBS_UNAVAILABLE = (
    "The catalog job records page is unavailable for this demo session."
)
_SAFE_REVIEW_UNAVAILABLE = (
    "The catalog review page is unavailable for this demo session."
)
_SAFE_EXPORT_UNAVAILABLE = (
    "The catalog export page is unavailable for this demo session."
)


def _proposals_not_found() -> Response:
    return _safe_not_found()


def _proposals_unavailable() -> Response:
    return _safe_unavailable(_SAFE_PROPOSALS_UNAVAILABLE)


def _collect_not_found() -> Response:
    return _safe_not_found()


def _collect_unavailable() -> Response:
    return _safe_unavailable(_SAFE_COLLECT_UNAVAILABLE)


def _jobs_not_found() -> Response:
    return _safe_not_found()


def _jobs_unavailable() -> Response:
    return _safe_unavailable(_SAFE_JOBS_UNAVAILABLE)


def _review_not_found() -> Response:
    return _safe_not_found()


def _review_unavailable() -> Response:
    return _safe_unavailable(_SAFE_REVIEW_UNAVAILABLE)


def _export_not_found() -> Response:
    return _safe_not_found()


def _export_unavailable() -> Response:
    return _safe_unavailable(_SAFE_EXPORT_UNAVAILABLE)


def _project_complete_run_groups(rows: Any) -> list[dict[str, object]]:
    """Project the closed remapped ``catalog/runs/...`` leaves into
    bounded COMPLETE run groups (all acquisition paths).

    Every runs-area row must satisfy the SAME closed projection law as
    the 224-k index (name, kind shape, bounded size, finite
    representable capture time) PLUS the worker's closed seven-file law
    (``_RUN_FILE_KINDS``: exactly one top-level sealed run content file
    per name, with its exact worker-published kind). A group is
    COMPLETE only when all seven closed files are present exactly
    once; a partial group (1..6 files), any other runs-area shape, or
    a duplicate file row is a corrupt display index: ``ValueError``
    (the caller answers with the fixed safe 503, never a silent
    omission). Non-catalog (branding/profile) leaves share the table
    and are skipped, exactly as in the 224-k projection.
    """
    groups: dict[str, dict[str, object]] = {}
    for row in rows:
        name, kind, size, _sha, captured = row
        if not isinstance(name, str) or not name.startswith("catalog/"):
            continue
        try:
            area, demo_id, parts = _catalog_name_parts(name)
        except ValueError:
            raise ValueError("invalid display index") from None
        if area != "runs":
            continue
        if not isinstance(kind, str) or _KIND.fullmatch(kind) is None:
            raise ValueError("invalid catalog kind")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= 2**31:
            raise ValueError("invalid catalog size")
        if isinstance(captured, bool) or not isinstance(captured, (int, float)):
            raise ValueError("invalid capture time")
        captured_float = float(captured)
        if not math.isfinite(captured_float) or not 0 <= captured_float < _MAX_CAPTURE_AT:
            raise ValueError("invalid capture time")
        # The capture time must convert to a representable UTC
        # datetime (validity probe only; the group's own max is
        # rendered later).
        try:
            datetime.fromtimestamp(captured_float, tz=UTC)
        except (OverflowError, OSError, ValueError):
            raise ValueError("invalid capture time") from None
        # The worker's closed seven sealed-run content files: exactly
        # one top-level file per run leaf, no deeper shape exists.
        if len(parts) != 1:
            raise ValueError("invalid catalog file")
        filename = parts[0]
        expected_kind = dsf._RUN_FILE_KINDS.get(filename)
        if expected_kind is None or kind != expected_kind:
            raise ValueError("invalid catalog file")
        group = groups.get(demo_id)
        if group is None:
            group = {
                "run_id": demo_id,
                "files": {},
                "captured_max": captured_float,
                "total_bytes": 0,
            }
            groups[demo_id] = group
        if filename in group["files"]:
            raise ValueError("duplicate run file")
        group["files"][filename] = True
        group["captured_max"] = max(group["captured_max"], captured_float)
        group["total_bytes"] = int(group["total_bytes"]) + int(size)
    complete: list[dict[str, object]] = []
    for group in groups.values():
        # The COMPLETE law: all seven closed files, each exactly once.
        # A partial group is a fixed safe refusal, never omitted.
        if set(group["files"]) != {filename for filename, _k in _RUN_DETAIL_FILES}:
            raise ValueError("incomplete run group")
        best_captured = group["captured_max"]
        complete.append(
            {
                "run_id": group["run_id"],
                "file_count": len(_RUN_DETAIL_FILES),
                "total_bytes": group["total_bytes"],
                "captured_utc": datetime.fromtimestamp(
                    float(best_captured), tz=UTC
                ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "captured_sort": float(best_captured),
            }
        )
    ordered = sorted(
        complete, key=lambda g: (float(g["captured_sort"]), str(g["run_id"])),
        reverse=True,
    )
    # Most-recently-captured first (reverse); the 100-group bound is
    # stated on the page, never hidden.
    for index, group in enumerate(ordered):
        group["ordinal"] = index + 1
    return ordered[:_MAX_RUN_GROUPS]


def _project_proposal_groups(rows: Any) -> list[dict[str, object]]:
    """Project the closed remapped ``catalog/proposals/...`` leaves into
    bounded captured-job groups (never a directory scan).

    Every proposals-area row must satisfy the SAME closed projection law
    as the 224-k index (name, kind shape, bounded size, finite
    representable capture time) PLUS the worker's closed file law: one
    top-level ``_PROPOSAL_NAMES`` file, or one ``OPENROUTER_PACKAGE_ORDER``
    preset directory holding one ``_PACKAGE_FILE_NAMES`` file, each with
    its exact worker-published kind. Any other shape is a corrupt
    display index: ``ValueError`` (the caller answers with the fixed
    safe 503, no raw echo). Non-catalog (branding/profile) leaves share
    the table and are skipped, exactly as in the 224-k projection.
    """
    groups: dict[str, dict[str, object]] = {}
    for row in rows:
        name, kind, size, _sha, captured = row
        if not isinstance(name, str) or not name.startswith("catalog/"):
            continue
        try:
            area, demo_id, parts = _catalog_name_parts(name)
        except ValueError:
            raise ValueError("invalid display index") from None
        if area != "proposals":
            continue
        if not isinstance(kind, str) or _KIND.fullmatch(kind) is None:
            raise ValueError("invalid catalog kind")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= 2**31:
            raise ValueError("invalid catalog size")
        if isinstance(captured, bool) or not isinstance(captured, (int, float)):
            raise ValueError("invalid capture time")
        captured_float = float(captured)
        if not math.isfinite(captured_float) or not 0 <= captured_float < _MAX_CAPTURE_AT:
            raise ValueError("invalid capture time")
        try:
            dt = datetime.fromtimestamp(captured_float, tz=UTC)
        except (OverflowError, OSError, ValueError):
            raise ValueError("invalid capture time") from None
        # The worker's closed proposals file law: one top-level
        # ``_PROPOSAL_NAMES`` file, or a ``packages/<preset>/`` file with
        # the fixed product preset vocabulary; no other shape exists.
        if len(parts) == 1:
            expected_kind = dsf._PROPOSAL_KINDS.get(parts[0])
        elif (
            len(parts) == 3
            and parts[0] == "packages"
            and parts[1] in OPENROUTER_PACKAGE_ORDER
        ):
            expected_kind = dsf._PACKAGE_KINDS.get(parts[2])
        else:
            expected_kind = None
        if expected_kind is None or kind != expected_kind:
            raise ValueError("invalid catalog file")
        group = groups.get(demo_id)
        if group is None:
            group = {
                "job_id": demo_id,
                "captured_max": captured_float,
                "artifacts": [],
            }
            groups[demo_id] = group
        group["captured_max"] = max(group["captured_max"], captured_float)
        group["artifacts"].append(
            {
                "display": "/".join(parts),
                "name": name,
                "kind": kind,
                "byte_count": size,
                "captured_utc": dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "captured_sort": dt.isoformat(),
            }
        )
    for group in groups.values():
        rows_of_group = group["artifacts"]
        rows_of_group.sort(key=lambda a: str(a["display"]))
        best = max(rows_of_group, key=lambda a: str(a["captured_sort"]))
        group["captured_sort"] = str(best["captured_sort"])
        group["captured_utc"] = str(best["captured_utc"])
    ordered = sorted(
        groups.values(),
        key=lambda g: (str(g["captured_sort"]), str(g["job_id"])),
        reverse=True,
    )
    # Most-recently-captured first (reverse); the 100-group bound is
    # stated on the page, never hidden.
    for index, group in enumerate(ordered):
        group["ordinal"] = index + 1
    return ordered[:_MAX_PROPOSAL_GROUPS]


def _catalog_name_parts(name: str) -> tuple[str, str, tuple[str, ...]]:
    """The ONE closed remapped catalog name law (shared by the 224-k
    index projection and the 224-l artifact selector).

    Returns ``(area, demo_id, artifact_parts)`` for a valid name;
    raises ``ValueError`` for every non-catalog, unknown-area,
    traversal, source-like or overlong value.
    """
    if not isinstance(name, str) or not name.startswith("catalog/"):
        raise ValueError("not a catalog name")
    if len(name) > _MAX_NAME_LEN:
        raise ValueError("invalid catalog name")
    parts = name.split("/")
    if len(parts) < 3 or parts[1] not in ("runs", "jobs", "proposals", "uploads"):
        raise ValueError("invalid catalog name")
    area = parts[1]
    if area == "runs":
        valid = len(parts) >= 4 and _RUN_ID.fullmatch(parts[2]) is not None
        demo_id = parts[2]
        artifact_parts = parts[3:]
    elif area == "jobs":
        valid = (
            len(parts) == 3
            and parts[2].endswith(".json")
            and _JOB_ID.fullmatch(parts[2][:-5]) is not None
        )
        demo_id = parts[2][:-5]
        artifact_parts = [parts[2]]
    else:
        valid = len(parts) >= 4 and _JOB_ID.fullmatch(parts[2]) is not None
        demo_id = parts[2]
        artifact_parts = parts[3:]
    if not valid or not all(
        _ARTIFACT_PART.fullmatch(part) and part not in (".", "..") for part in artifact_parts
    ):
        raise ValueError("invalid catalog name")
    return area, demo_id, tuple(artifact_parts)


def _project_catalog_index(leaves: Any) -> list[dict[str, object]]:
    """Present only closed remapped catalog names, never source references."""
    if not isinstance(leaves, list) or len(leaves) > _MAX_INDEX_ROWS:
        raise ValueError("invalid display index")
    rows: list[dict[str, object]] = []
    for leaf in leaves:
        if not isinstance(leaf, dict):
            raise ValueError("invalid display leaf")
        name = leaf.get("logical_name")
        if not isinstance(name, str) or not name.startswith("catalog/"):
            # Branding/profile leaves share the verified target table.
            continue
        area, demo_id, artifact_parts = _catalog_name_parts(name)
        kind = leaf.get("kind")
        size = leaf.get("byte_count")
        captured = leaf.get("captured_at")
        if not isinstance(kind, str) or _KIND.fullmatch(kind) is None:
            raise ValueError("invalid catalog kind")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= 2**31:
            raise ValueError("invalid catalog size")
        if isinstance(captured, bool) or not isinstance(captured, (int, float)):
            raise ValueError("invalid capture time")
        captured_float = float(captured)
        if not math.isfinite(captured_float) or not 0 <= captured_float < _MAX_CAPTURE_AT:
            raise ValueError("invalid capture time")
        try:
            dt = datetime.fromtimestamp(captured_float, tz=UTC)
        except (OverflowError, OSError, ValueError):
            raise ValueError("invalid capture time") from None
        rows.append(
            {
                "area": area,
                "demo_id": demo_id,
                "artifact": "/".join(artifact_parts),
                # 224-l: the full remapped logical name is the artifact
                # link's bounded selector (never a source reference).
                "name": name,
                "kind": kind,
                "byte_count": size,
                "captured_utc": dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "captured_sort": dt.isoformat(),
            }
        )
    return rows


@router.get("/", response_class=HTMLResponse)
async def demo_catalog_index(request: Request) -> Response:
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return HTMLResponse(
            "Not Found", status_code=404, headers={"Cache-Control": "private, no-store"}
        )
    rows: list[dict[str, object]] | None
    try:
        reader = request.app.state.demo_display_reader_factory(
            request.app.state.demo_config, demo.target_db
        )
        rows = _project_catalog_index(await reader.read_index())
    except Exception:  # Safe fixed refusal; cancellation is not swallowed.
        rows = None
    response = templates.TemplateResponse(
        request,
        "operations/demo_catalog_index.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "catalog_rows": rows,
            "unavailable_note": _SAFE_UNAVAILABLE,
            "index_limit": _MAX_INDEX_ROWS,
        },
        status_code=503 if rows is None else 200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _safe_not_found() -> Response:
    """One fixed safe 404: no name, kind, hash or error value echoed.

    Carries nosniff with every other demo refusal (the gate
    normalizes the single cache header on every dynamic /admin
    response)."""
    return HTMLResponse(
        "Not Found",
        status_code=404,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _safe_unavailable(message: str) -> Response:
    """One fixed safe 503 for any invalid metadata, bound, digest/size
    mismatch or driver failure (no DSN, hash, path or traceback).

    Carries nosniff with every other demo refusal (the gate
    normalizes the single cache header on every dynamic /admin
    response)."""
    return HTMLResponse(
        message,
        status_code=503,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _artifact_not_found() -> Response:
    return _safe_not_found()


def _artifact_unavailable() -> Response:
    return _safe_unavailable(_SAFE_ARTIFACT_UNAVAILABLE)


def _run_detail_not_found() -> Response:
    return _safe_not_found()


def _run_detail_unavailable() -> Response:
    return _safe_unavailable(_SAFE_RUN_DETAIL_UNAVAILABLE)


async def _fetch_bounded_body(
    session: Any,
    name: str,
    kind: str,
    byte_count: int,
    stored_sha: str,
    cap: int = _MAX_ARTIFACT_BYTES,
) -> bytes | None:
    """The ONE bounded body fetch shared by 224-l/224-m.

    Re-asserts kind, byte count, SHA256 and the 32 MiB cap as BOUND
    parameters (the caller's metadata-validated per-file ``cap`` -
    default the 32 MiB catalog maximum, 224-p the worker's 1 MiB
    job-record ceiling) in a second parameterized query (no
    identifier interpolation), then re-verifies the exact length and
    SHA256 of the fetched bytes. Any mismatch or absent row yields
    ``None`` (the caller answers with its fixed safe 503); an
    incomplete/corrupt artifact is never returned.
    """
    body_row = (
        await session.execute(
            text(
                "SELECT body FROM demo_display.leaves "
                "WHERE logical_name = :name "
                "AND octet_length(body) <= :cap "
                "AND byte_count = :size "
                "AND sha256 = :digest "
                "AND kind = :kind"
            ),
            {
                "name": name,
                "cap": cap,
                "size": byte_count,
                "digest": stored_sha,
                "kind": kind,
            },
        )
    ).first()
    if body_row is None:
        return None
    body = bytes(body_row[0])
    if len(body) != byte_count or hashlib.sha256(body).hexdigest() != stored_sha:
        return None
    return body


@router.get("/artifact")
async def demo_catalog_artifact(request: Request) -> Response:
    """224-l: download ONE worker-published sanitized display copy.

    Exact path only; admitted through the central demo gate like the
    index. The gate has already re-validated the live demo-control
    session and bound this request to its exact verified, unexpired
    copy; this handler adds the name-law, metadata, bound and
    digest/size rechecks and serves the forced attachment.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _artifact_not_found()
    # Exactly ONE bounded `name` query value and no duplicate/unknown
    # query parameters (a selector, never authorization).
    pairs = list(request.query_params.multi_items())
    if len(pairs) != 1 or pairs[0][0] != "name":
        return _artifact_not_found()
    name = pairs[0][1]
    if not name or len(name) > _MAX_NAME_LEN:
        return _artifact_not_found()
    # The SAME 224-k closed remapped catalog name law, checked BEFORE
    # any body query: unknown, non-catalog, traversal, source-like or
    # overlong values get the fixed safe 404 without any echo.
    try:
        _catalog_name_parts(name)
    except ValueError:
        return _artifact_not_found()
    # The gate's SAME request-local copy engine (demo_mode seam): the
    # only copy binding this request may use; absent state fails
    # closed to the safe 503, never to an app-global factory.
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _artifact_unavailable()
    try:
        async with session_factory() as session, session.begin():
            # Independently re-verify, INSIDE this read-only
            # transaction, that the engine is bound to this session's
            # exact copy and the server holds it read-only.
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            if current != demo.target_db or read_only != "on":
                return _artifact_unavailable()
            # Metadata FIRST (parameterized exact logical-name lookup;
            # no SQL identifier interpolation, no pathname). The
            # database computes ``octet_length(body)`` so a corrupt
            # row that CLAIMS a small byte_count while storing an
            # oversized body is refused here, before ANY body bytes
            # are transferred.
            meta = (
                await session.execute(
                    text(
                        "SELECT kind, byte_count, sha256, "
                        "octet_length(body) AS actual_bytes "
                        "FROM demo_display.leaves "
                        "WHERE logical_name = :name"
                    ),
                    {"name": name},
                )
            ).first()
            if meta is None:
                return _artifact_not_found()
            kind, byte_count, stored_sha, actual_bytes = meta
            # Invalid closed kind/name/size/hash: fixed 503. The
            # existing 32 MiB catalog per-file maximum is enforced
            # BEFORE any body fetch (the worker's bundle cap is
            # tighter, so a healthy row always fits).
            if (
                not isinstance(kind, str)
                or _KIND.fullmatch(kind) is None
                or isinstance(byte_count, bool)
                or not isinstance(byte_count, int)
                or not 0 <= byte_count <= _MAX_ARTIFACT_BYTES
                or not isinstance(stored_sha, str)
                or _SHA256_HEX.fullmatch(stored_sha) is None
                or isinstance(actual_bytes, bool)
                or not isinstance(actual_bytes, int)
                or not 0 <= actual_bytes <= _MAX_ARTIFACT_BYTES
                # A corrupt/incomplete row whose stored body length
                # disagrees with its claimed byte_count is refused
                # here, before any body fetch.
                or actual_bytes != byte_count
            ):
                return _artifact_unavailable()
            # Body ONLY after the bound: the shared 224-l/224-m bounded
            # fetch re-asserts every checked condition server-side (bound
            # parameters only), so a concurrently modified or corrupt
            # row can never transfer unbounded bytes.
            body = await _fetch_bounded_body(
                session, name, kind, byte_count, stored_sha
            )
            if body is None:
                return _artifact_unavailable()
    except Exception:
        # Driver, connection or statement failure: one fixed safe
        # refusal. Cancellation is a BaseException and is not
        # swallowed.
        return _artifact_unavailable()
    # An incomplete/corrupt artifact must never be labeled complete:
    # exact byte count AND exact SHA256, or one fixed safe 503.
    if len(body) != byte_count or hashlib.sha256(body).hexdigest() != stored_sha:
        return _artifact_unavailable()
    # The name-law artifact parts are closed ASCII
    # ([A-Za-z0-9_.-]{1,100}); the basename is already a safe
    # attachment filename. Forced attachment: never inline, never
    # rendered as active content, even for REVIEW.html.
    basename = name.rsplit("/", 1)[-1]
    return Response(
        content=body,
        status_code=200,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f'attachment; filename="{basename}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
            "Cache-Control": "private, no-store",
        },
    )


# --- 224-m: demo-only copy-backed catalog run detail --------------------------


def _project_run_detail(doc: Any, run_id: str) -> dict[str, object]:
    """Project the bounded, already-sanitized ``demo-display-1`` /
    ``validation_json`` summary fields for ONE run.

    The document has ALREADY passed the worker-side typed re-verification
    (``dsf._verify_json_policy("validation_json", ...)``); this projection
    only routes it to the exact requested run and bounds the list rows
    the display may render. Every failure is ``ValueError`` (the handler
    answers with its fixed safe 503); nothing from the document is
    echoed in any error.
    """
    if not isinstance(doc, dict):
        raise ValueError("invalid run detail document")
    if doc.get("schema") != "demo-display-1" or doc.get("kind") != "validation_json":
        raise ValueError("invalid run detail document")
    # Route the run ID: the display body must belong to the EXACT run
    # the gate admitted (never another run's summary).
    if doc.get("run_id") != run_id:
        raise ValueError("invalid run detail document")
    for field in ("state", "generated_at", "policy_version"):
        if doc.get(field) is None:
            raise ValueError("invalid run detail document")
    for field in ("warnings", "dispositions", "price_comparisons"):
        rows = doc.get(field, [])
        if not isinstance(rows, list) or len(rows) > _MAX_DETAIL_LIST_ROWS:
            raise ValueError("invalid run detail document")
    counts = doc.get("counts")
    if not isinstance(counts, dict) or set(counts) != {"entries"}:
        raise ValueError("invalid run detail document")
    if isinstance(counts["entries"], bool) or not isinstance(
        counts["entries"], int
    ) or not 0 <= counts["entries"] <= 10**9:
        raise ValueError("invalid run detail document")
    per_provider = doc.get("per_provider")
    if not isinstance(per_provider, dict) or len(per_provider) > 64:
        raise ValueError("invalid run detail document")
    for provider, values in per_provider.items():
        if (
            not isinstance(provider, str)
            or len(provider) > 32
            or not isinstance(values, dict)
            or set(values) != {"total"}
            or isinstance(values["total"], bool)
            or not isinstance(values["total"], int)
            or not 0 <= values["total"] <= 10**9
        ):
            raise ValueError("invalid run detail document")
    return {
        "state": doc["state"],
        "generated_at": doc["generated_at"],
        "policy_version": doc["policy_version"],
        "counts_entries": counts["entries"],
        "per_provider": per_provider,
        "warnings": doc.get("warnings") or [],
        "dispositions": doc.get("dispositions") or [],
        "price_comparisons": doc.get("price_comparisons") or [],
    }


@router.get("/runs/{run_id}/", response_class=HTMLResponse)
async def demo_catalog_run_detail(request: Request, run_id: str) -> Response:
    """224-m: one captured run's sanitized validation summary + its
    captured artifact list, from this visitor's exact verified copy.

    Exact canonical shape only (gate-admitted): ``demo-run-`` plus 24
    lowercase hex and a required trailing slash. The read uses the
    gate's SAME request-local copy engine in one read-only transaction:
    independent ``current_database()`` / ``transaction_read_only``
    recheck, then a parameterized inventory of the EXACT seven
    worker-published run content files (never a directory scan), then
    the shared 224-l bounded body fetch for ``validation.json`` only.
    Missing run -> fixed 404; corrupt/incomplete rows, invalid typed
    projection or driver failure -> one fixed safe 503 with no raw
    echo. The page renders bounded sanitized fields only, as a
    HISTORICAL snapshot display with no original seal, live status or
    apply authority.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None or _RUN_ID.fullmatch(run_id) is None:
        return _run_detail_not_found()
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _run_detail_unavailable()
    names = {
        filename: f"catalog/runs/{run_id}/{filename}"
        for filename, _kind in _RUN_DETAIL_FILES
    }
    try:
        async with session_factory() as session, session.begin():
            # Independently re-verify, INSIDE this read-only
            # transaction, that the engine is bound to this session's
            # exact copy and the server holds it read-only.
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            if current != demo.target_db or read_only != "on":
                return _run_detail_unavailable()
            # Bounded inventory for EXACTLY this remapped run: the
            # closed seven worker-published content files, parameterized
            # (no wildcard, no pathname, no directory scan).
            params: dict[str, object] = {}
            placeholders: list[str] = []
            for index, full_name in enumerate(names.values()):
                params[f"n{index}"] = full_name
                placeholders.append(f":n{index}")
            rows = (
                await session.execute(
                    text(
                        "SELECT logical_name, kind, byte_count, sha256, "
                        "captured_at, octet_length(body) AS actual_bytes "
                        "FROM demo_display.leaves "
                        f"WHERE logical_name IN ({', '.join(placeholders)})"
                    ),
                    params,
                )
            ).all()
            if not rows:
                return _run_detail_not_found()
            # A partial run (1..6 of the seven files) is an incomplete
            # row set: one fixed safe 503, never a half-rendered page.
            if len(rows) != len(_RUN_DETAIL_FILES):
                return _run_detail_unavailable()
            kind_by_name = dict(_RUN_DETAIL_FILES)
            artifact_rows: list[dict[str, object]] = []
            validation_meta: tuple[str, int, str] | None = None
            for row in rows:
                logical_name, kind, byte_count, stored_sha, captured, actual = row
                filename = str(logical_name).rsplit("/", 1)[-1]
                if (
                    not isinstance(kind, str)
                    or kind != kind_by_name.get(filename)
                    or not isinstance(stored_sha, str)
                    or _SHA256_HEX.fullmatch(stored_sha) is None
                    or isinstance(byte_count, bool)
                    or not isinstance(byte_count, int)
                    or not 0 <= byte_count <= _MAX_ARTIFACT_BYTES
                    or isinstance(actual, bool)
                    or not isinstance(actual, int)
                    or actual != byte_count
                    or isinstance(captured, bool)
                    or not isinstance(captured, (int, float))
                ):
                    return _run_detail_unavailable()
                captured_float = float(captured)
                if not math.isfinite(
                    captured_float
                ) or not 0 <= captured_float < _MAX_CAPTURE_AT:
                    return _run_detail_unavailable()
                try:
                    dt = datetime.fromtimestamp(captured_float, tz=UTC)
                except (OverflowError, OSError, ValueError):
                    return _run_detail_unavailable()
                artifact_rows.append(
                    {
                        "name": filename,
                        "kind": kind,
                        "byte_count": byte_count,
                        "captured_utc": dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
                        "captured_sort": dt.isoformat(),
                        # The 224-l download selector: the full remapped
                        # logical name (closed charset, renders literally
                        # through urlencode).
                        "download_name": str(logical_name),
                    }
                )
                if filename == "validation.json":
                    validation_meta = (str(kind), int(byte_count), str(stored_sha))
            if validation_meta is None:
                return _run_detail_unavailable()
            # Load ONLY this run's validation.json sanitized DISPLAY
            # body through the shared 224-l bounded fetch (cap-before-
            # body, bound-parameter re-asserts, exact length + SHA256).
            body = await _fetch_bounded_body(
                session,
                names["validation.json"],
                validation_meta[0],
                validation_meta[1],
                validation_meta[2],
            )
            if body is None:
                return _run_detail_unavailable()
    except Exception:
        # Driver, connection or statement failure: one fixed safe
        # refusal. Cancellation is a BaseException and is not swallowed.
        return _run_detail_unavailable()

    # Re-prove the stored body against the worker's exact typed shape
    # spec for sanitized validation documents, then route it to this
    # run and project the bounded display fields.
    try:
        dsf._verify_json_policy(dsf.KIND_VALIDATION_JSON, body)
        doc = json.loads(body.decode("utf-8"))
        detail = _project_run_detail(doc, run_id)
    except Exception:
        # Invalid/unknown shape (or a validator defect): fixed safe 503,
        # no raw document value escapes.
        return _run_detail_unavailable()

    artifact_rows.sort(key=lambda r: (str(r["name"]),))
    response = templates.TemplateResponse(
        request,
        "operations/demo_catalog_run_detail.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "run_id": run_id,
            "detail": detail,
            "artifact_rows": artifact_rows,
        },
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


# --- 224-n: demo-only copy-backed captured proposals page ---------------------


@router.get("/proposals", response_class=HTMLResponse)
async def demo_catalog_proposals(request: Request) -> Response:
    """224-n: ONE captured-proposals page from this visitor's exact
    verified copy.

    Exact path only (gate-admitted). The page renders the familiar
    proposal form controls as an ILLUSTRATIVE demo-only form (fixed
    product option vocabularies, copy-backed model choices, submitting
    has NO effect - the gate's quiet 204 cut ends every unsafe method)
    plus a bounded, clearly HISTORICAL list of the captured
    ``catalog/proposals/<remapped-job-id>/...`` leaves: at most the 100
    most-recently-captured job groups, a native selection control that
    accepts only ONE canonical optional ``job`` value (unknown,
    duplicate or extra parameters refuse safely, never falling back to
    another job), and - for the selected job - the captured artifacts
    actually present (each linked through the exact 224-l forced
    download) plus, when a ``catalog/jobs/<same id>.json`` sanitized
    job record exists, its re-proved ``family=proposal`` status/times
    labeled historical at capture time. One read-only transaction on
    the gate's SAME request-local copy engine with the independent
    ``current_database()`` / ``transaction_read_only`` recheck; the job
    record body uses the shared 224-l metadata-first, 32 MiB cap-
    before-body, exact length + SHA256 fetch. Missing groups render an
    honest empty state (an empty list never implies a missing file
    source); any corrupt index row, corrupt job record or driver
    failure is one fixed safe refusal with no raw echo. The normal
    custody-backed handler, template and routes are unchanged.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _proposals_not_found()
    # Query law: ZERO parameters, or exactly ONE ``job=<32hex>`` value.
    # Duplicate, unknown, empty or overlong parameters refuse safely
    # (fixed 404, no echo, no fallback to another job).
    pairs = list(request.query_params.multi_items())
    job_param: str | None = None
    if pairs:
        if len(pairs) != 1 or pairs[0][0] != "job":
            return _proposals_not_found()
        candidate = pairs[0][1]
        if (
            not candidate
            or len(candidate) > _MAX_NAME_LEN
            or _JOB_ID.fullmatch(candidate) is None
        ):
            return _proposals_not_found()
        job_param = candidate
    # The gate's SAME request-local copy engine (demo_mode seam): the
    # only copy binding this request may use; absent state fails
    # closed to the safe 503, never to an app-global factory.
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _proposals_unavailable()
    model_options: list[Any]
    groups: list[dict[str, object]]
    selected: dict[str, object] | None
    job_status: dict[str, object] | None
    try:
        async with session_factory() as session, session.begin():
            # Independently re-verify, INSIDE this read-only
            # transaction, that the engine is bound to this session's
            # exact copy and the server holds it read-only.
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            if current != demo.target_db or read_only != "on":
                return _proposals_unavailable()
            # Copy-backed model choices (SELECT-only copy table; the
            # pure credential-shape guard still applies). A failed copy
            # query is a fixed safe refusal, never a silent dropdown.
            model_options = await load_choices(
                session, "catalog_upstream", selected=()
            )
            # Bounded METADATA inventory (no body transfer at all): the
            # LIMIT is a BOUND parameter, so even a corrupt copy can
            # never transfer more than the existing 4096-row display
            # bound plus one (the extra row proves the bound tripped).
            rows = (
                await session.execute(
                    text(
                        "SELECT logical_name, kind, byte_count, sha256, "
                        "captured_at FROM demo_display.leaves "
                        "LIMIT :limit"
                    ),
                    {"limit": _MAX_INDEX_ROWS + 1},
                )
            ).all()
            if (
                not isinstance(rows, (list, tuple))
                or len(rows) > _MAX_INDEX_ROWS
            ):
                return _proposals_unavailable()
            groups = _project_proposal_groups(list(rows))
            # Selection: an explicit job param must match a captured
            # group EXACTLY (no fallback); absent param shows the
            # most-recently-captured group (never "live").
            if job_param is not None:
                matches = [g for g in groups if g["job_id"] == job_param]
                if not matches:
                    return _proposals_not_found()
                selected = matches[0]
            else:
                selected = groups[0] if groups else None
            job_status = None
            if selected is not None:
                # The SAME copy may hold the job's sanitized record
                # (admin-visible job projection, worker-published).
                record_name = f"catalog/jobs/{selected['job_id']}.json"
                record_meta: tuple[str, int, str] | None = None
                for row in list(rows):
                    if row[0] != record_name:
                        continue
                    kind, size, stored_sha = row[1], row[2], row[3]
                    # The 32 MiB per-file maximum is enforced on the
                    # METADATA BEFORE any body fetch (cap-before-body);
                    # _fetch_bounded_body then re-asserts it in SQL.
                    if (
                        kind != dsf.KIND_JOB_RECORD
                        or isinstance(size, bool)
                        or not isinstance(size, int)
                        or not 0 <= size <= _MAX_ARTIFACT_BYTES
                        or not isinstance(stored_sha, str)
                        or _SHA256_HEX.fullmatch(stored_sha) is None
                    ):
                        return _proposals_unavailable()
                    record_meta = (str(kind), int(size), str(stored_sha))
                if record_meta is not None:
                    # Metadata-first, 32 MiB cap BEFORE body, exact
                    # length + SHA256 after: the shared 224-l fetch.
                    body = await _fetch_bounded_body(
                        session,
                        record_name,
                        record_meta[0],
                        record_meta[1],
                        record_meta[2],
                    )
                    if body is None:
                        return _proposals_unavailable()
                    # Re-prove the worker's exact typed job-record shape,
                    # then require family=proposal and the EXACT selected
                    # job id before anything renders.
                    dsf._verify_json_policy(dsf.KIND_JOB_RECORD, body)
                    doc = json.loads(body.decode("utf-8"))
                    if (
                        doc.get("family") != "proposal"
                        or doc.get("job_id") != selected["job_id"]
                    ):
                        return _proposals_unavailable()
                    job_status = {
                        "status": doc["status"],
                        "cancel_requested": bool(doc["cancel_requested"]),
                        "created_at": doc["created_at"],
                        "updated_at": doc["updated_at"],
                    }
    except Exception:
        # Driver, connection, statement or projection failure: one
        # fixed safe refusal. Cancellation is a BaseException and is
        # not swallowed.
        return _proposals_unavailable()

    response = templates.TemplateResponse(
        request,
        "catalog_refresh/proposals.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            # Demo context: the FAMILIAR form renders with fixed
            # product option vocabularies and copy-backed choices; the
            # demo banner labels it illustrative (no operational
            # effect). last_job stays None, so the NORMAL custody-backed
            # last-job section and its links never render in demo.
            "setup": {"state": "ready"},
            "errors": {},
            "currencies": ("USD", "EUR", "GBP", "CHF"),
            "endpoint_scopes": ("chat_completions", "responses"),
            "package_presets": OPENROUTER_PACKAGE_ORDER,
            "model_options": model_options,
            "last_job": None,
            "last_job_packages": None,
            "last_job_provider_scope": None,
            "job_refusal": None,
            "demo_admin": True,
            "demo_proposal_groups": groups,
            "demo_proposal_bound": _MAX_PROPOSAL_GROUPS,
            "demo_selected": selected,
            "demo_job_status": job_status,
        },
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


# --- 224-o: demo-only copy-backed collect page + captured runs ---------------


@router.get("/collect", response_class=HTMLResponse)
async def demo_catalog_collect(request: Request) -> Response:
    """224-o: ONE collect page from this visitor's exact verified copy.

    Exact path only (gate-admitted). The page renders the familiar
    collect form controls as ILLUSTRATIVE demo-only controls (fixed
    provider/mode vocabularies, copy-backed ``catalog_upstream``
    model-ID choices; live setup - DATABASE_URL and the research
    runner - is not available to this copy and is never inferred;
    submitting has NO effect - the gate's quiet 204 cut ends every
    unsafe method and no body is ever parsed) plus a bounded, clearly
    HISTORICAL list of at most the 100 most-recently-captured
    COMPLETE catalog run groups from the target-only display index
    (all acquisition paths - never attributed to the collect form):
    the worker's closed seven sealed-run content files per group,
    exact remapped run ID, kind/size/time metadata checked, no body
    transfer, each linked to the 224-m historical run-detail page
    (never the original custody). A partial run group (1..6 of the
    seven files), wrong kind/size/time or the server-side row bound
    is a fixed safe 503, never silently omitted; an empty run list
    proves neither that no collect job exists nor that live catalog
    storage is unconfigured (status-only jobs without captured
    complete runs are not listed). One read-only transaction on the
    gate's SAME request-local copy engine with the independent
    ``current_database()`` / ``transaction_read_only`` recheck and a
    BOUND inventory limit; the normal custody-backed collect handler,
    template and routes are unchanged.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _collect_not_found()
    # Query law: NO query parameters are defined for the demo collect
    # page; ANY parameter (including a normal-page `job` value)
    # refuses safely (fixed 404, no echo, no fallback).
    if request.query_params.multi_items():
        return _collect_not_found()
    # The gate's SAME request-local copy engine (demo_mode seam): the
    # only copy binding this request may use; absent state fails
    # closed to the safe 503, never to an app-global factory.
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _collect_unavailable()
    model_options: list[Any]
    run_groups: list[dict[str, object]]
    try:
        async with session_factory() as session, session.begin():
            # Independently re-verify, INSIDE this read-only
            # transaction, that the engine is bound to this session's
            # exact copy and the server holds it read-only.
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            if current != demo.target_db or read_only != "on":
                return _collect_unavailable()
            # Copy-backed model choices (SELECT-only copy table; the
            # pure credential-shape guard still applies). A failed
            # copy query is a fixed safe refusal, never a silent
            # empty dropdown.
            model_options = await load_choices(
                session, "catalog_upstream", selected=()
            )
            # Bounded METADATA inventory (no body transfer at all):
            # the LIMIT is a BOUND parameter, so even a corrupt copy
            # can never transfer more than the existing 4096-row
            # display bound plus one (the extra row proves the bound
            # tripped).
            rows = (
                await session.execute(
                    text(
                        "SELECT logical_name, kind, byte_count, sha256, "
                        "captured_at FROM demo_display.leaves "
                        "LIMIT :limit"
                    ),
                    {"limit": _MAX_INDEX_ROWS + 1},
                )
            ).all()
            if (
                not isinstance(rows, (list, tuple))
                or len(rows) > _MAX_INDEX_ROWS
            ):
                return _collect_unavailable()
            run_groups = _project_complete_run_groups(list(rows))
    except Exception:
        # Driver, connection, statement or projection failure: one
        # fixed safe refusal. Cancellation is a BaseException and is
        # not swallowed.
        return _collect_unavailable()

    response = templates.TemplateResponse(
        request,
        "catalog_refresh/collect.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            # Demo context: the FAMILIAR form renders with fixed
            # product option vocabularies and copy-backed choices;
            # the demo banner labels it illustrative (no operational
            # effect). last_job stays None, so the NORMAL custody-
            # backed last-job section never renders in demo.
            # `dispatched` must be defined (the template tests
            # `is not none`); live setup and the research runner are
            # NOT evaluated and NOT inferred for this copy.
            "setup": {"state": "ready"},
            "errors": {},
            "dispatched": None,
            "dispatch_note": None,
            "providers": ("openai", "openrouter"),
            "model_options": model_options,
            "last_job": None,
            "job_refusal": None,
            "live_db_available": False,
            "research_available": False,
            "demo_admin": True,
            "demo_run_groups": run_groups,
            "demo_run_bound": _MAX_RUN_GROUPS,
        },
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


# --- 224-p: demo-only review/export form pages + historical job records ---


def _closed_leaf_meta(size: Any, stored_sha: Any, captured: Any) -> bool:
    """The closed metadata law for ONE display leaf (shared by the
    224-p independent reference verification): exact closed kind is
    checked by the caller; here the bounded size, canonical SHA256 and
    finite representable capture time."""
    if (
        isinstance(size, bool)
        or not isinstance(size, int)
        or not 0 <= size <= _MAX_ARTIFACT_BYTES
        or not isinstance(stored_sha, str)
        or _SHA256_HEX.fullmatch(stored_sha) is None
        or isinstance(captured, bool)
        or not isinstance(captured, (int, float))
    ):
        return False
    captured_float = float(captured)
    if not math.isfinite(captured_float) or not 0 <= captured_float < _MAX_CAPTURE_AT:
        return False
    try:
        datetime.fromtimestamp(captured_float, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return False
    return True


def _project_job_records(rows: Any) -> list[dict[str, object]]:
    """Project the closed ``catalog/jobs/<remapped-32hex>.json`` leaves
    into bounded HISTORICAL job-record entries (every job family).

    Every jobs-area row must satisfy the SAME closed remapped name law
    as the 224-k index PLUS the exact worker-published ``job_record``
    kind, the worker's 1 MiB job-record ceiling, a canonical SHA256
    and a finite representable capture time. A duplicate record or any
    other jobs-area shape is a corrupt display index: ``ValueError``
    (the caller answers with the fixed safe 503, never a silent
    omission). The other display areas (runs/proposals/uploads) and
    the non-catalog leaves share the table and are skipped, exactly as
    in the 224-k projection. The result is sorted most-recently-
    captured first; the caller applies the 100-entry bound.
    """
    seen: set[str] = set()
    entries: list[dict[str, object]] = []
    for row in rows:
        name, kind, size, stored_sha, captured = row
        if not isinstance(name, str) or not name.startswith("catalog/"):
            continue
        try:
            area, demo_id, _parts = _catalog_name_parts(name)
        except ValueError:
            raise ValueError("invalid display index") from None
        if area != "jobs":
            continue
        if (
            not isinstance(kind, str)
            or kind != dsf.KIND_JOB_RECORD
            or not isinstance(stored_sha, str)
            or _SHA256_HEX.fullmatch(stored_sha) is None
            or isinstance(size, bool)
            or not isinstance(size, int)
            or not 0 <= size <= _JOB_RECORD_BYTES
        ):
            raise ValueError("invalid job record metadata")
        if not _closed_leaf_meta(size, stored_sha, captured):
            raise ValueError("invalid capture time")
        captured_float = float(captured)
        dt = datetime.fromtimestamp(captured_float, tz=UTC)
        if demo_id in seen:
            raise ValueError("duplicate job record")
        seen.add(demo_id)
        entries.append(
            {
                "job_id": demo_id,
                "kind": kind,
                "byte_count": size,
                "stored_sha": stored_sha,
                "captured_utc": dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "captured_sort": dt.isoformat(),
            }
        )
    entries.sort(key=lambda e: (str(e["captured_sort"]), str(e["job_id"])), reverse=True)
    return entries


def _job_reference_verified(
    rows: Any, job_id: str, run_id: Any, artifact_name: Any
) -> tuple[bool, bool]:
    """Independently verify, from the SAME bounded metadata inventory
    (never a body transfer), whether the selected record's remapped
    run / upload references have their captured target-only leaves.

    A run reference is verified only when ALL seven worker-published
    run content leaves exist with their exact kinds and closed
    metadata (so the exact 224-m run-detail page could render it); an
    upload reference is verified only when the exact
    ``catalog/uploads/<job>/<name>`` leaf exists with the expected
    closed kind and closed metadata (so the 224-l forced download is
    addressable). Anything else must render as plain text only.
    """
    run_ok = False
    if isinstance(run_id, str) and _RUN_ID.fullmatch(run_id) is not None:
        expected = {
            f"catalog/runs/{run_id}/{filename}": kind
            for filename, kind in _RUN_DETAIL_FILES
        }
        verified: set[str] = set()
        for row in rows:
            name = row[0]
            if not isinstance(name, str) or name not in expected:
                continue
            if row[1] == expected[name] and _closed_leaf_meta(row[2], row[3], row[4]):
                verified.add(name)
        run_ok = verified == set(expected)
    artifact_ok = False
    if isinstance(artifact_name, str):
        prefix, _, _suffix = artifact_name.partition("-")
        expected_kind = dsf._UPLOAD_KINDS.get(prefix)
        if expected_kind is not None:
            target = f"catalog/uploads/{job_id}/{artifact_name}"
            for row in rows:
                if (
                    row[0] == target
                    and row[1] == expected_kind
                    and _closed_leaf_meta(row[2], row[3], row[4])
                ):
                    artifact_ok = True
                    break
    return run_ok, artifact_ok


def _demo_form_context(demo: Any, **extra: Any) -> dict[str, object]:
    """The ONE shared demo form context: the FAMILIAR form renders with
    no operational effect - ``last_job``/``dispatched`` stay None so
    the NORMAL custody-backed last-job/status sections and their links
    never render, and ``demo_admin`` enables the narrow demo branches.
    Live setup, source custody and every job resolver are never
    evaluated for this copy."""
    context: dict[str, object] = {
        "admin": demo.session_context.admin_user,
        "csrf_token": demo.csrf_token,
        "setup": {"state": "ready"},
        "errors": {},
        "dispatched": None,
        "dispatch_note": None,
        "last_job": None,
        "job_refusal": None,
        "demo_admin": True,
    }
    context.update(extra)
    return context


async def _demo_copy_recheck(session_factory: Any, target_db: str) -> bool:
    """One SELECT-only/read-only transaction on the gate's SAME
    request-local copy engine with the independent
    ``current_database()`` / ``transaction_read_only`` recheck (the
    224-p form pages open it for the recheck alone)."""
    try:
        async with session_factory() as session, session.begin():
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            return current == target_db and read_only == "on"
    except Exception:
        return False


@router.get("/review", response_class=HTMLResponse)
async def demo_catalog_review(request: Request) -> Response:
    """224-p: ONE illustrative review page (exact path, gate-admitted).

    The familiar review form (bundle/baseline file inputs and the
    first-install checkbox, with their help) renders as an
    ILLUSTRATIVE demo-only form: submitting has NO effect (no bundle
    is sealed or reviewed, no baseline is imported, no provider or
    research is called), live setup (DATABASE_URL) and operator source
    custody are NOT available to this copy and are never inferred, and
    the form links the captured HISTORICAL job-record page. The
    normal custody-backed review handler, template behavior and
    routes are unchanged; the gate's quiet 204 cut ends every unsafe
    method (including ``/review/submit``) before any body is parsed.
    One SELECT-only/read-only copy transaction performs the
    independent binding recheck; any query string refuses with fixed
    404 BEFORE copy access.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _review_not_found()
    # Query law: NO query parameters are defined for the demo review
    # page; ANY parameter refuses safely (fixed 404, no echo).
    if request.query_params.multi_items():
        return _review_not_found()
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _review_unavailable()
    if not await _demo_copy_recheck(session_factory, demo.target_db):
        return _review_unavailable()
    response = templates.TemplateResponse(
        request,
        "catalog_refresh/review.html",
        _demo_form_context(demo),
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get("/export-baseline", response_class=HTMLResponse)
async def demo_catalog_export(request: Request) -> Response:
    """224-p: ONE illustrative export-baseline page (exact path,
    gate-admitted).

    The familiar export form (its export action description) renders
    as an ILLUSTRATIVE demo-only form: submitting has NO effect (no
    baseline is exported, no database is read or written), live setup
    (DATABASE_URL) is NOT available to this copy and the page never
    claims a configured or unconfigured database target, and the form
    links the captured HISTORICAL job-record page. The normal
    custody-backed export handler, template behavior and routes are
    unchanged; the gate's quiet 204 cut ends every unsafe method
    (including ``/export-baseline/submit``) before any body is parsed.
    One SELECT-only/read-only copy transaction performs the
    independent binding recheck; any query string refuses with fixed
    404 BEFORE copy access.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _export_not_found()
    # Query law: NO query parameters are defined for the demo export
    # page; ANY parameter refuses safely (fixed 404, no echo).
    if request.query_params.multi_items():
        return _export_not_found()
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _export_unavailable()
    if not await _demo_copy_recheck(session_factory, demo.target_db):
        return _export_unavailable()
    response = templates.TemplateResponse(
        request,
        "catalog_refresh/export.html",
        _demo_form_context(demo),
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get("/jobs/", response_class=HTMLResponse)
async def demo_catalog_jobs(request: Request) -> Response:
    """224-p: ONE bounded HISTORICAL job-record page (exact path with
    its REQUIRED trailing slash, gate-admitted).

    The page lists at most the 100 most-recently-captured
    ``catalog/jobs/<remapped-32hex>.json`` metadata rows from the
    target-only display index - covering EVERY captured job family
    (collect, supplied-bundle review, baseline export, proposals) and
    never attributed to any one demo form. The read runs in ONE
    SELECT-only/read-only transaction on the gate's SAME request-local
    copy engine with the independent ``current_database()`` /
    ``transaction_read_only`` recheck and a BOUND ``LIMIT :limit``
    inventory (transferring at most 4,097 metadata rows); no body is
    transferred while listing. The closed remapped name, exact
    ``job_record`` kind, 1 MiB metadata ceiling, canonical SHA256,
    finite representable capture time and duplicate/unknown jobs-area
    shape are checked before rendering (any violation is the fixed
    safe 503, never a silent omission).

    The optional selector is ZERO parameters or exactly ONE canonical
    ``job=<32hex>`` value chosen from the bounded list; duplicates,
    extra, unknown, missing/overlong or noncanonical values refuse
    fixed 404 BEFORE body transfer (structurally invalid values
    before copy access), never falling back to another job. Without a
    selector the most-recently-captured record is chosen. For ONLY
    the selected job the sanitized body is fetched from the SAME
    copy with the 1 MiB cap re-asserted before transfer, exact size +
    SHA256 re-checks, the existing 223 typed ``job_record``
    re-proof, and the body job ID required to equal the selected
    remapped ID. Only the sanitized family, HISTORICAL status (frozen
    at capture time - not live or actionable), created/updated/
    captured times, neutral progress, cancel-requested, dispatch and
    explicit ``error_code=None`` render; a remapped run/upload
    reference is linked only when its captured target-only leaf is
    independently verified (otherwise plain text). Corrupt body,
    mismatched ID/kind/SHA/size or read failure is the fixed safe
    503 with no raw echo. No original ID, source path or copy DB
    name ever renders.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _jobs_not_found()
    # Query law: ZERO parameters, or exactly ONE ``job=<32hex>``
    # value. Structurally invalid values refuse BEFORE any copy
    # access (fixed 404, no echo, no fallback to another job).
    pairs = list(request.query_params.multi_items())
    job_param: str | None = None
    if pairs:
        if len(pairs) != 1 or pairs[0][0] != "job":
            return _jobs_not_found()
        candidate = pairs[0][1]
        if (
            not candidate
            or len(candidate) > _MAX_NAME_LEN
            or _JOB_ID.fullmatch(candidate) is None
        ):
            return _jobs_not_found()
        job_param = candidate
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _jobs_unavailable()
    entries: list[dict[str, object]]
    all_rows: list[Any]
    try:
        async with session_factory() as session, session.begin():
            # Independently re-verify, INSIDE this read-only
            # transaction, that the engine is bound to this session's
            # exact copy and the server holds it read-only.
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            if current != demo.target_db or read_only != "on":
                return _jobs_unavailable()
            # Bounded METADATA inventory (no body transfer while
            # listing): the LIMIT is a BOUND parameter, so even a
            # corrupt copy can never transfer more than the existing
            # 4096-row display bound plus one.
            rows = (
                await session.execute(
                    text(
                        "SELECT logical_name, kind, byte_count, sha256, "
                        "captured_at FROM demo_display.leaves "
                        "LIMIT :limit"
                    ),
                    {"limit": _MAX_INDEX_ROWS + 1},
                )
            ).all()
            if (
                not isinstance(rows, (list, tuple))
                or len(rows) > _MAX_INDEX_ROWS
            ):
                return _jobs_unavailable()
            all_rows = list(rows)
            entries = _project_job_records(all_rows)
            selected: dict[str, object] | None
            shown = entries[:_MAX_JOB_GROUPS]
            if job_param is not None:
                # An explicit value must match a bounded-list record
                # EXACTLY (no fallback, no body transfer on a miss).
                matches = [e for e in shown if e["job_id"] == job_param]
                if not matches:
                    return _jobs_not_found()
                selected = matches[0]
            else:
                selected = shown[0] if shown else None
            job_detail: dict[str, object] | None = None
            if selected is not None:
                # Metadata-first: the 1 MiB ceiling was already
                # enforced on the metadata; the shared fetch then
                # re-asserts cap/size/SHA/kind as BOUND parameters
                # BEFORE any body transfer, and re-verifies the exact
                # length + SHA256 of the fetched bytes.
                body = await _fetch_bounded_body(
                    session,
                    f"catalog/jobs/{selected['job_id']}.json",
                    str(selected["kind"]),
                    int(selected["byte_count"]),
                    str(selected["stored_sha"]),
                    cap=_JOB_RECORD_BYTES,
                )
                if body is None:
                    return _jobs_unavailable()
                # Re-prove the worker's exact typed job-record shape
                # (existing 223 validator), then require the body job
                # ID to equal the selected remapped ID and the finite
                # family/status vocabularies.
                dsf._verify_json_policy(dsf.KIND_JOB_RECORD, body)
                doc = json.loads(body.decode("utf-8"))
                if (
                    doc.get("job_id") != selected["job_id"]
                    or doc.get("family") not in dsf._JOB_FAMILY_VOCAB
                    or doc.get("status") not in dsf._JOB_STATUS_VOCAB
                ):
                    return _jobs_unavailable()
                run_ok, artifact_ok = _job_reference_verified(
                    all_rows,
                    str(selected["job_id"]),
                    doc.get("run_id"),
                    doc.get("artifact_name"),
                )
                artifact_name = doc.get("artifact_name")
                job_detail = {
                    "family": doc["family"],
                    "status": doc["status"],
                    "created_at": doc["created_at"],
                    "updated_at": doc["updated_at"],
                    "progress": doc.get("progress") or "",
                    "cancel_requested": bool(doc.get("cancel_requested")),
                    "dispatch": doc.get("dispatch"),
                    "run_id": doc.get("run_id"),
                    "run_verified": run_ok,
                    "artifact_name": artifact_name,
                    "artifact_verified": artifact_ok,
                    "artifact_download_name": (
                        f"catalog/uploads/{selected['job_id']}/{artifact_name}"
                        if artifact_ok
                        else None
                    ),
                    "captured_utc": selected["captured_utc"],
                }
    except Exception:
        # Driver, connection, statement or projection failure: one
        # fixed safe refusal. Cancellation is a BaseException and is
        # not swallowed.
        return _jobs_unavailable()

    response = templates.TemplateResponse(
        request,
        "operations/demo_catalog_jobs.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "demo_job_entries": shown,
            "demo_job_bound": _MAX_JOB_GROUPS,
            "demo_selected": selected,
            "demo_job_detail": job_detail,
        },
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response

# --- 224-x: demo-only direct catalog artifact/package reads + apply-status ---


def _attachment_response(body: bytes, filename: str) -> Response:
    """The forced sanitized-display attachment (the 224-l wire law):
    octet-stream, attachment disposition, nosniff, CSP none and
    private no-store (the gate normalizes every admitted dynamic
    response to exactly this one cache header)."""
    return Response(
        content=body,
        status_code=200,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
            "Cache-Control": "private, no-store",
        },
    )


async def _copy_leaf_body(
    session: Any,
    logical_name: str,
    expected_kind: str,
) -> tuple[bytes | None, str]:
    """ONE bounded read of a closed worker-published display leaf
    (224-x).

    Runs on the CALLER's already-rechecked transaction. Metadata
    FIRST with the database-computed ``octet_length(body)`` (a
    corrupt row that claims a small byte_count while storing an
    oversized body is refused here, before ANY body bytes transfer),
    the EXACT closed kind, the existing 32 MiB per-file cap and the
    canonical SHA256; then the shared 224-l bounded body fetch
    re-asserts every condition as BOUND parameters and re-verifies
    the exact length + SHA256 of the fetched bytes. Returns
    ``(body, "ok")``, ``(None, "missing")`` or ``(None, "corrupt")``.
    No SQL identifier interpolation, no pathname, no source access.
    """
    meta = (
        await session.execute(
            text(
                "SELECT kind, byte_count, sha256, "
                "octet_length(body) AS actual_bytes "
                "FROM demo_display.leaves "
                "WHERE logical_name = :name"
            ),
            {"name": logical_name},
        )
    ).first()
    if meta is None:
        return None, "missing"
    kind, byte_count, stored_sha, actual_bytes = meta
    if (
        not isinstance(kind, str)
        or kind != expected_kind
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or not 0 <= byte_count <= _MAX_ARTIFACT_BYTES
        or not isinstance(stored_sha, str)
        or _SHA256_HEX.fullmatch(stored_sha) is None
        or isinstance(actual_bytes, bool)
        or not isinstance(actual_bytes, int)
        or not 0 <= actual_bytes <= _MAX_ARTIFACT_BYTES
        or actual_bytes != byte_count
    ):
        return None, "corrupt"
    body = await _fetch_bounded_body(
        session, logical_name, kind, byte_count, stored_sha
    )
    if body is None:
        return None, "corrupt"
    return body, "ok"


@router.get("/runs/{run_id}/artifact/{name}")
async def demo_catalog_run_artifact(
    request: Request, run_id: str, name: str
) -> Response:
    """224-x: download ONE captured run content file (closed name).

    Exact canonical shape only (gate-admitted, query-free): the seven
    worker-published run content files (the normal run-artifact
    route's closed set, intersected with the already-published
    sanitized leaf law). The read uses the gate's SAME request-local
    copy engine in one SELECT-only/read-only transaction with the
    independent ``current_database()`` / ``transaction_read_only``
    recheck, then the shared 224-x metadata-first bounded read for
    the exact ``catalog/runs/{run_id}/{name}`` leaf with its exact
    worker-published kind. Missing leaf -> fixed 404; corrupt row,
    bound violation, digest/size mismatch or driver failure -> the
    fixed safe 503 (never the bytes, never a partial artifact, never
    a source value). No source custody, seal key, live catalog root
    or filesystem/network read.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None or _RUN_ID.fullmatch(run_id) is None:
        return _run_detail_not_found()
    expected_kind = dict(_RUN_DETAIL_FILES).get(name)
    if expected_kind is None:
        return _run_detail_not_found()
    logical_name = f"catalog/runs/{run_id}/{name}"
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _run_detail_unavailable()
    try:
        async with session_factory() as session, session.begin():
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            if current != demo.target_db or read_only != "on":
                return _run_detail_unavailable()
            body, state = await _copy_leaf_body(
                session, logical_name, expected_kind
            )
    except Exception:
        # Driver, connection or statement failure: one fixed safe
        # refusal. Cancellation is a BaseException and is not
        # swallowed.
        return _run_detail_unavailable()
    if state == "missing":
        return _run_detail_not_found()
    if body is None:
        return _run_detail_unavailable()
    return _attachment_response(body, name)


@router.get("/jobs/{job_id}/artifact/{name}")
async def demo_catalog_job_artifact(
    request: Request, job_id: str, name: str
) -> Response:
    """224-x: download ONE captured job artifact (closed name).

    Exact canonical shape only (gate-admitted, query-free). The
    closed name set is the INTERSECTION of the normal job-artifact
    route's finite vocabulary and the published sanitized leaf law:
    one closed remapped upload name (``bundle`` / ``baseline`` /
    ``baseline-export`` plus a 32-hex keyed suffix, leaf
    ``catalog/uploads/{job_id}/{name}`` with the exact upload kind)
    or one of the six proposal files (leaf
    ``catalog/proposals/{job_id}/{name}`` with its exact worker-
    published kind). The read law is the same as the run-artifact
    GET (gate-bound engine, in-transaction recheck, metadata-first
    bounded read, forced sanitized attachment). Missing leaf ->
    fixed 404; anything corrupt -> the fixed safe 503.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None or _JOB_ID.fullmatch(job_id) is None:
        return _jobs_not_found()
    # Longest fixed prefix FIRST: ``baseline-export-<32hex>`` must
    # never be misread as ``baseline-<export-...>``.
    _upload_kind: str | None = None
    for _prefix in ("baseline-export", "baseline", "bundle"):
        if name.startswith(f"{_prefix}-"):
            _upload_kind = _prefix
            break
    if _upload_kind is not None:
        _suffix = name[len(_upload_kind) + 1 :]
        if (
            len(_suffix) != 32
            or not all(c in "0123456789abcdef" for c in _suffix)
        ):
            return _jobs_not_found()
        expected_kind = dsf._UPLOAD_KINDS.get(_upload_kind)
        logical_name = f"catalog/uploads/{job_id}/{name}"
    else:
        expected_kind = dsf._PROPOSAL_KINDS.get(name)
        logical_name = f"catalog/proposals/{job_id}/{name}"
    if expected_kind is None:
        return _jobs_not_found()
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _jobs_unavailable()
    try:
        async with session_factory() as session, session.begin():
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            if current != demo.target_db or read_only != "on":
                return _jobs_unavailable()
            body, state = await _copy_leaf_body(
                session, logical_name, expected_kind
            )
    except Exception:
        return _jobs_unavailable()
    if state == "missing":
        return _jobs_not_found()
    if body is None:
        return _jobs_unavailable()
    return _attachment_response(body, name)


@router.get("/jobs/{job_id}/package/{preset}/{name}")
async def demo_catalog_job_package_artifact(
    request: Request, job_id: str, preset: str, name: str
) -> Response:
    """224-x: download ONE captured generated package file (closed
    preset + closed file set).

    Exact canonical shape only (gate-admitted, query-free): the
    preset must be an EXACT member of the fixed product preset
    order and the name one of the five closed package files (the
    normal package route's finite vocabulary, intersected with the
    published sanitized leaf law; leaf
    ``catalog/proposals/{job_id}/packages/{preset}/{name}`` with the
    exact worker-published kind). Same read law as the other 224-x
    artifact GETs; missing leaf -> fixed 404, anything corrupt ->
    the fixed safe 503.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None or _JOB_ID.fullmatch(job_id) is None:
        return _jobs_not_found()
    if preset not in OPENROUTER_PACKAGE_ORDER:
        return _jobs_not_found()
    expected_kind = dsf._PACKAGE_KINDS.get(name)
    if expected_kind is None:
        return _jobs_not_found()
    logical_name = (
        f"catalog/proposals/{job_id}/packages/{preset}/{name}"
    )
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _jobs_unavailable()
    try:
        async with session_factory() as session, session.begin():
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            if current != demo.target_db or read_only != "on":
                return _jobs_unavailable()
            body, state = await _copy_leaf_body(
                session, logical_name, expected_kind
            )
    except Exception:
        return _jobs_unavailable()
    if state == "missing":
        return _jobs_not_found()
    if body is None:
        return _jobs_unavailable()
    return _attachment_response(body, name)


@router.get("/runs/{run_id}/apply-status", response_class=HTMLResponse)
async def demo_catalog_apply_status(
    request: Request, run_id: str
) -> Response:
    """224-y: frozen historical apply status for one captured run.

    Exact canonical shape only (gate-admitted, query-free). ONE
    SELECT-only/read-only transaction on the gate's SAME
    request-local copy engine with the independent
    ``current_database()`` / ``transaction_read_only`` recheck first
    verifies, with the SAME closed seven-file metadata-only
    inventory as the 224-m run detail, that the run exists in THIS
    copy (missing run -> fixed 404; a partial or kind-mismatched
    run -> the fixed safe 503).

    The copied ``catalog_refresh_applications`` rows are then
    queried ONLY by the derived 96-bit prefix of the
    already-sanitized ``run_id`` (the 224-y slug carries the first
    24 hex of the SAME keyed ``remap_str_id`` digest both
    producers share: one seed - ``manifest.job_id`` - and one
    canonical raw run id - the worker's ``bundle.run_id``, written
    as both the sealed run directory name and the application row).
    The query is parameterized with a small bounded LIMIT plus one
    over-bound probe; any malformed row, more than ONE distinct
    full remapped run id (collision or corruption) or an
    over-bound result is the fixed safe 503. For a unique full
    remapped run id, ONLY that id's typed, safe committed records
    are displayed as stored at DB snapshot time: the real copied
    counts and the record's OWN historical event times (UTC; the
    DB snapshot timestamp itself is not displayed) and no
    bundle/plan/receipt-HMAC identity values (seal/HMAC receipt
    authority is never presented). Every seven-file leaf's
    captured_at must be a finite representable worker time or the
    fixed safe 503 fires; the file capture time is stated
    separately when present and may differ from the record
    times. A no-match is UNKNOWN/UNAVAILABLE - never "not applied"
    or "rolled back" - which also keeps pre-upgrade active copies
    (old slug domain, no joinable value) safely unknown. Every
    displayed value (path slug, canonical time forms, raw and
    grouped count forms, and every record string) equal to a known
    incoming bearer/cookie/session/proxy alias makes the WHOLE page
    the fixed safe refusal, and a classifier failure is the fixed
    safe refusal (never a 500); no source run id, seed,
    seal/HMAC receipt authority, provider credential, copy
    locator or unbounded free text is ever shown. No source DB,
    live custody, seal key, network or DML; visible operational
    controls are clearly labeled quiet no-ops; the normal
    authoritative admin status is unchanged.
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None or _RUN_ID.fullmatch(run_id) is None:
        return _run_detail_not_found()
    expected = {
        f"catalog/runs/{run_id}/{filename}": kind
        for filename, kind in _RUN_DETAIL_FILES
    }
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _run_detail_unavailable()
    bundle_captured_at: float = 0.0
    app_rows: list = []
    try:
        async with session_factory() as session, session.begin():
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            if current != demo.target_db or read_only != "on":
                return _run_detail_unavailable()
            # The run must exist in THIS copy (the SAME closed
            # seven-file inventory as the 224-m run detail,
            # metadata only - no body transfer).
            params: dict[str, object] = {}
            placeholders: list[str] = []
            for index, full_name in enumerate(expected):
                params[f"n{index}"] = full_name
                placeholders.append(f":n{index}")
            rows = (
                await session.execute(
                    text(
                        "SELECT logical_name, kind, captured_at "
                        "FROM demo_display.leaves "
                        f"WHERE logical_name IN ({', '.join(placeholders)})"
                    ),
                    params,
                )
            ).all()
            present: dict[str, str] = {}
            for r in rows:
                if (
                    isinstance(r[0], str)
                    and r[0] in expected
                    and isinstance(r[1], str)
                    and expected[r[0]] == r[1]
                    and isinstance(r[2], (int, float))
                    and not isinstance(r[2], bool)
                    and math.isfinite(float(r[2]))
                    and 0 <= float(r[2]) < _MAX_CAPTURE_AT
                ):
                    present[str(r[0])] = str(r[1])
                else:
                    # A leaf that EXISTS in this copy but is
                    # corrupted (unknown name, bad kind, or a
                    # nonfinite / unrepresentable capture time)
                    # is the fixed safe refusal - never
                    # "not found", never a silent missing time.
                    return _run_detail_unavailable()
            if not present:
                return _run_detail_not_found()
            if set(present) != set(expected):
                # A partial run inventory: one fixed safe 503,
                # never a half page.
                return _run_detail_unavailable()
            bundle_row = next(
                (r for r in rows if r[0] == f"catalog/runs/{run_id}/catalog-refresh.json"),
                None,
            )
            assert bundle_row is not None
            bundle_captured_at = float(bundle_row[2])
            # 224-y: the bounded copied apply-record read by the
            # derived 96-bit prefix of the already-sanitized run_id
            # (bound parameter; small bound + one over-bound probe).
            app_rows = (
                await session.execute(
                    text(
                        "SELECT run_id, mode, outcome, effective_at, "
                        "created_at, operator_actor, db_actor, "
                        "admin_user_id, created_providers, created_routes, "
                        "created_pricing, created_fx, superseded_pricing, "
                        "superseded_fx "
                        "FROM public.catalog_refresh_applications "
                        "WHERE run_id LIKE 'demo' || :prefix || '%' "
                        "ORDER BY created_at NULLS LAST "
                        "LIMIT :limit"
                    ),
                    {
                        "prefix": run_id[len("demo-run-"):],
                        "limit": _APPLY_RECORD_BOUND + 1,
                    },
                )
            ).all()
    except Exception:
        # Driver, connection or statement failure: one fixed safe
        # refusal. Cancellation is a BaseException and is not
        # swallowed.
        return _run_detail_unavailable()

    if len(app_rows) > _APPLY_RECORD_BOUND:
        # The over-bound probe fired: corruption, never a list.
        return _run_detail_unavailable()

    prefix = run_id[len("demo-run-"):]
    records: list[dict[str, object]] = []
    full_ids: set[str] = set()
    for r in app_rows:
        (
            row_run_id, mode, outcome, effective_at, created_at,
            operator_actor, db_actor, admin_user_id,
            created_providers, created_routes, created_pricing,
            created_fx, superseded_pricing, superseded_fx,
        ) = r
        counts = (
            created_providers, created_routes, created_pricing,
            created_fx, superseded_pricing, superseded_fx,
        )
        if (
            not isinstance(row_run_id, str)
            or _S_MAPPED_TEXT.fullmatch(row_run_id) is None
            or not row_run_id.startswith("demo" + prefix)
            or not isinstance(mode, str) or mode not in _APPLY_MODE_VOCAB
            or not isinstance(outcome, str) or outcome not in _APPLY_OUTCOME_VOCAB
            or not isinstance(effective_at, datetime)
            or not isinstance(created_at, datetime)
            or not isinstance(operator_actor, str)
            or _S_MAPPED_TEXT.fullmatch(operator_actor) is None
            or not isinstance(db_actor, str)
            or _S_MAPPED_TEXT.fullmatch(db_actor) is None
            # admin_user_id is a NULLABLE column: CLI-applied records
            # may carry no admin identity; None renders as n/a.
            or (admin_user_id is not None
                and not isinstance(admin_user_id, uuid.UUID))
            or any(
                isinstance(v, bool) or not isinstance(v, int) or v < 0
                for v in counts
            )
        ):
            # One malformed row poisons the join: fixed safe 503.
            return _run_detail_unavailable()
        full_ids.add(row_run_id)
        records.append(
            {
                "run_id": row_run_id,
                "mode": mode,
                "outcome": outcome,
                "effective_at": effective_at,
                "created_at": created_at,
                "operator_actor": operator_actor,
                "db_actor": db_actor,
                "admin_user_id": (
                    str(admin_user_id) if admin_user_id is not None else None
                ),
                "created_providers": created_providers,
                "created_routes": created_routes,
                "created_pricing": created_pricing,
                "created_fx": created_fx,
                "superseded_pricing": superseded_pricing,
                "superseded_fx": superseded_fx,
            }
        )
    if len(full_ids) > 1:
        # More than one distinct full remapped run id shares the
        # 96-bit prefix: collision or corruption, never a display.
        return _run_detail_unavailable()

    try:
        # bundle_captured_at was range-checked finite and
        # representable; a conversion failure is still the fixed
        # safe refusal, never a silently missing time.
        file_captured_at = datetime.fromtimestamp(bundle_captured_at, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return _run_detail_unavailable()

    # 224-y output-alias law (whole page, fail closed): EVERY
    # dynamic value the template will display - the path slug, the
    # canonical datetime forms, the raw AND comma-grouped count
    # forms, and then each record string - is checked with the same
    # pure known-incoming-alias classifier. A match (or a classifier
    # error) is the whole-page fixed safe refusal: simpler than
    # partial formatting, and a known incoming cookie that is
    # slug-shaped, date-shaped or numeric can never be echoed. The
    # demo app's fixed neutral prefix tuple is used, never ambient
    # settings.
    try:
        alias_prefixes = tuple(
            request.app.state.settings.get_gateway_key_accepted_prefixes()
        )
        if not all(isinstance(x, str) for x in alias_prefixes):
            return _run_detail_unavailable()
    except Exception:
        return _run_detail_unavailable()

    def _is_alias(value: str) -> bool:
        try:
            return is_known_incoming_secret_alias(
                value, scope=request.scope, accepted_prefixes=alias_prefixes
            )
        except Exception:
            return True  # fail closed

    dynamic_values: list[str] = [run_id, str(file_captured_at)]
    for rec in records:
        dynamic_values.append(str(rec["effective_at"]))
        dynamic_values.append(str(rec["created_at"]))
        for v in (
            rec["created_providers"], rec["created_routes"],
            rec["created_pricing"], rec["created_fx"],
            rec["superseded_pricing"], rec["superseded_fx"],
        ):
            dynamic_values.append(str(v))
            formatted = format_number(v)
            if formatted is not None:
                dynamic_values.append(str(formatted))
    if any(_is_alias(v) for v in dynamic_values):
        return _run_detail_unavailable()

    demo_apply_records: list[dict[str, object]] | None = None
    if records:
        # A DISTINCT error sentinel: a classifier failure must be
        # refused, and can never be confused with the legitimate
        # NULL admin_user_id (which renders as n/a).
        _show_error = object()

        def _show(value: str | None):
            if value is None:
                return None
            try:
                if is_known_incoming_secret_alias(
                    value, scope=request.scope, accepted_prefixes=alias_prefixes
                ):
                    return _ALIAS_WITHHELD
            except Exception:
                # A classifier failure cannot be proven safe: mark
                # the fixed safe refusal, never a 500 or an echo.
                return _show_error
            return value

        masked: list[dict[str, object]] = []
        try:
            for rec in records:
                masked.append(
                    {
                        "run_id": _show(str(rec["run_id"])),
                        "mode": _show(str(rec["mode"])),
                        "outcome": _show(str(rec["outcome"])),
                        "operator_actor": _show(str(rec["operator_actor"])),
                        "db_actor": _show(str(rec["db_actor"])),
                        "admin_user_id": _show(rec["admin_user_id"]),
                        "effective_at": rec["effective_at"],
                        "created_at": rec["created_at"],
                        "created_providers": rec["created_providers"],
                        "created_routes": rec["created_routes"],
                        "created_pricing": rec["created_pricing"],
                        "created_fx": rec["created_fx"],
                        "superseded_pricing": rec["superseded_pricing"],
                        "superseded_fx": rec["superseded_fx"],
                    }
                )
        except Exception:
            return _run_detail_unavailable()
        for rec in masked:
            for key in (
                "run_id", "mode", "outcome", "operator_actor",
                "db_actor", "admin_user_id",
            ):
                if rec[key] is _show_error:
                    # A classifier failure on ANY displayed field
                    # (including a non-null admin user): one fixed
                    # safe refusal.
                    return _run_detail_unavailable()
        demo_apply_records = masked

    response = templates.TemplateResponse(
        request,
        "catalog_refresh/apply_result.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "detail": {"run_id": run_id},
            "apply_status_value": "",
            "apply_run_id": "",
            "apply_bundle_sha256": None,
            "apply_effective_at": None,
            "apply_counts": None,
            "apply_records": None,
            "apply_unconfirmed": True,
            "demo_admin": True,
            "demo_apply_run_id": run_id,
            "demo_apply_records": demo_apply_records,
            "demo_file_captured_at": file_captured_at,
        },
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response
