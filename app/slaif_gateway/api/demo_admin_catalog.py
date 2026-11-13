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

import math
import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from sqlalchemy import text

from slaif_gateway.api.admin import templates
from slaif_gateway.db.session import get_sessionmaker_from_app

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
_SAFE_ARTIFACT_UNAVAILABLE = (
    "The catalog artifact is unavailable for this demo session."
)


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


def _artifact_not_found() -> Response:
    """One fixed safe 404: no name, kind, hash or error value echoed."""
    return HTMLResponse(
        "Not Found", status_code=404, headers={"Cache-Control": "private, no-store"}
    )


def _artifact_unavailable() -> Response:
    """One fixed safe 503 for any invalid metadata, bound, digest/size
    mismatch or driver failure (no DSN, hash, path or traceback)."""
    return HTMLResponse(
        _SAFE_ARTIFACT_UNAVAILABLE,
        status_code=503,
        headers={"Cache-Control": "private, no-store"},
    )


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
            # Body ONLY after the bound: one parameterized fetch that
            # RE-asserts every checked condition server-side (bound
            # parameters only), so a concurrently modified or corrupt
            # row can never transfer unbounded bytes; a row that no
            # longer satisfies them simply does not match.
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
                        "cap": _MAX_ARTIFACT_BYTES,
                        "size": byte_count,
                        "digest": stored_sha,
                        "kind": kind,
                    },
                )
            ).first()
            if body_row is None:
                return _artifact_unavailable()
            body = bytes(body_row[0])
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
