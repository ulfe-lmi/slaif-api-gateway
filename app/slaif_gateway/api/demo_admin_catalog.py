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


def _proposals_not_found() -> Response:
    return _safe_not_found()


def _proposals_unavailable() -> Response:
    return _safe_unavailable(_SAFE_PROPOSALS_UNAVAILABLE)


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
    """One fixed safe 404: no name, kind, hash or error value echoed."""
    return HTMLResponse(
        "Not Found", status_code=404, headers={"Cache-Control": "private, no-store"}
    )


def _safe_unavailable(message: str) -> Response:
    """One fixed safe 503 for any invalid metadata, bound, digest/size
    mismatch or driver failure (no DSN, hash, path or traceback)."""
    return HTMLResponse(
        message, status_code=503, headers={"Cache-Control": "private, no-store"}
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
    session: Any, name: str, kind: str, byte_count: int, stored_sha: str
) -> bytes | None:
    """The ONE bounded body fetch shared by 224-l/224-m.

    Re-asserts kind, byte count, SHA256 and the 32 MiB cap as BOUND
    parameters in a second parameterized query (no identifier
    interpolation), then re-verifies the exact length and SHA256 of the
    fetched bytes. Any mismatch or absent row yields ``None`` (the
    caller answers with its fixed safe 503); an incomplete/corrupt
    artifact is never returned.
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
                "cap": _MAX_ARTIFACT_BYTES,
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
