"""Objective 224-k: demo-only catalog snapshot metadata from one verified copy.

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
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from slaif_gateway.api.admin import templates

router = APIRouter(prefix="/admin/operations/catalog", include_in_schema=False)

_MAX_INDEX_ROWS = 4096  # Existing DisplayReader/223 publication bound.
_MAX_CAPTURE_AT = 253_402_300_800.0  # Worker-published ceiling.
_JOB_ID = re.compile(r"[0-9a-f]{32}\Z")
_RUN_ID = re.compile(r"demo-run-[0-9a-f]{24}\Z")
_ARTIFACT_PART = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
_KIND = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_MAX_NAME_LEN = 200  # Worker display-name ceiling.
_SAFE_UNAVAILABLE = "The catalog snapshot index is unavailable for this demo session."


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
