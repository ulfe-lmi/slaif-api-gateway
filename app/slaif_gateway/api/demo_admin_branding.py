"""Objective 224-u: demo-only neutral branding asset endpoints.

A small, purpose-built router mounted by ``create_demo_app`` ONLY,
BEFORE the normal branding router, so the five exact paths
``GET /admin/branding/style.css``, ``/logo``, ``/logo-compact``,
``/favicon`` and ``/hero`` are served by these demo handlers in the
demo process while the normal handlers (which read the LIVE operator
branding directory from this process's settings) are never reached
for those paths there. Every other branding shape stays default-
denied by the central demo gate; every unsafe method on ``/admin``
remains the unchanged uniform 204 cut before body parsing and
dispatch.

The endpoints are TOTAL, before and after login:

* With a verified demo session, the handler applies the COMPLETE
  FINITE FIVE-SLOT COPY LAW inside one SELECT-only/read-only
  transaction on the gate's SAME request-local copy engine
  (``current_database()`` and ``transaction_read_only`` recheck).
  Every NEW worker-built copy publishes leaves for ALL FIVE fixed
  slots - a configured source always shows the neutral substitute
  after sanitization and an unconfigured source still gets the five
  neutral-substitute leaves - so the closed read law is one shape:
  EXACTLY five ``branding/<slot>`` leaves. ZERO leaves (a damaged or
  pre-upgrade copy) or a PARTIAL set (a damaged configured copy) is
  ONE fixed safe 503: the packaged fallback must never mask a
  corrupted configured leaf, and the private configured flag is not
  part of the display copy, so absence alone is never treated as
  unconfigured. For an intact five-slot copy, the closed metadata
  law (exact kind, nonnegative size under the reviewed 256 KiB slot
  maximum, canonical SHA-256, database-computed ``octet_length``
  equal to the claimed byte count) runs for EVERY present leaf
  BEFORE any body fetch; then the requested slot's bounded body
  fetch re-asserts every condition as BOUND parameters, the fetched
  bytes are re-verified (exact length + SHA-256) and re-proven
  against the 223 independent display policy - which for branding
  proves the stored bytes ARE the packaged neutral substitute.
* Before login (no demo session) ONLY the packaged neutral fallback
  is served: no database, no file, no settings and no live branding
  directory access of any kind.

No original brand bytes, source path, file name, host or operator
identity ever appear in a demo branding response, log or error; a
damaged or pre-upgrade copy (zero or a partial branding leaf set),
a bad copy binding or a corrupt leaf is one fixed safe 503 (never a
silent ambient-file, cross-copy or live-directory read; the
pre-login packaged fallback is the ONLY non-copy source of bytes).
Every response stays private no-store (the gate wrapper) and
carries nosniff.
"""

from __future__ import annotations

import hashlib
import re

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text

from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services import demo_snapshot_files as dsf
from slaif_gateway.web.branding import (
    STYLE_CSS,
    SLOTS,
    fallback_asset,
)

router = APIRouter(prefix="/admin/branding", include_in_schema=False)

# The reviewed per-slot display maximum (the worker enforces the same
# bound at capture; a healthy leaf always fits, so the cap is a pure
# corruption fence enforced BEFORE any body fetch).
_BRAND_SLOT_MAX_BYTES = 256 * 1024
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")

_SAFE_BRANDING_UNAVAILABLE = (
    "The requested demo page is not available right now. "
    "Please check back shortly."
)

_RESPONSE_HEADERS = {"X-Content-Type-Options": "nosniff"}


def _not_found() -> Response:
    return HTMLResponse(
        "Not Found", status_code=404, headers={"Cache-Control": "private, no-store"}
    )


def _unavailable() -> Response:
    return HTMLResponse(
        _SAFE_BRANDING_UNAVAILABLE,
        status_code=503,
        headers={"Cache-Control": "private, no-store"},
    )


def _package_fallback(slot: str) -> Response:
    """The fixed packaged neutral fallback (package default)."""
    data, content_type = fallback_asset(slot)
    return Response(
        data,
        media_type=content_type,
        headers={**_RESPONSE_HEADERS, "Cache-Control": "private, no-store"},
    )


async def _read_verified_leaf(
    request: Request, slot: str
) -> tuple[bytes, str] | bool:
    """One SELECT-only/read-only copy transaction for ONE slot.

    Returns the verified leaf ``(bytes, content_type)``, or
    ``False`` for ANY validation failure (one fixed safe 503, never
    a fallback): the copy does not carry the complete finite
    five-slot leaf set (zero leaves - damaged or pre-upgrade - or a
    partial set - damaged configured copy), a leaf breaks the closed
    metadata law, the requested body fails the bound/digest or the
    223 display policy.
    """
    demo = request.state.demo_admin
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return False
    slot_names = {s: f"branding/{s}" for s in SLOTS}
    try:
        async with session_factory() as session, session.begin():
            # Independently re-verify, INSIDE this read-only
            # transaction, that the engine is bound to this session's
            # exact copy and the server holds it read-only.
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            if current != demo.target_db or read_only != "on":
                return False
            # Metadata FIRST, for the COMPLETE finite five-slot
            # vocabulary (parameterized exact names; no SQL
            # identifier interpolation, no pathname). The database
            # computes ``octet_length(body)`` so a corrupt row that
            # CLAIMS a small byte_count while storing an oversized
            # body is refused here, before ANY body bytes are
            # transferred. At most five rows can match.
            params = {
                f"n{i}": slot_names[s] for i, s in enumerate(SLOTS)
            }
            rows = (
                await session.execute(
                    text(
                        "SELECT logical_name, kind, byte_count, sha256, "
                        "octet_length(body) AS actual_bytes "
                        "FROM demo_display.leaves "
                        "WHERE logical_name IN "
                        "(:n0, :n1, :n2, :n3, :n4)"
                    ),
                    params,
                )
            ).all()
            present = {str(r._mapping["logical_name"]) for r in rows}
            # The complete finite five-slot copy law (224-u): EVERY
            # new worker-built copy carries EXACTLY the five fixed
            # slot leaves - a configured source always shows the
            # neutral substitute after sanitization and an
            # unconfigured source still gets the five
            # neutral-substitute leaves. ZERO leaves (a damaged or
            # pre-upgrade copy) or a PARTIAL set (a damaged
            # configured copy) is a fixed safe refusal: the packaged
            # fallback must never mask a corrupted configured leaf,
            # and the private configured flag is not part of the
            # display copy, so absence alone is never treated as
            # unconfigured.
            if present != set(slot_names.values()):
                return False
            # Closed metadata law for EVERY present leaf BEFORE any
            # body fetch.
            meta: dict[str, tuple[int, str]] = {}
            for r in rows:
                m = r._mapping
                name = str(m["logical_name"])
                kind, byte_count, stored_sha, actual_bytes = (
                    m["kind"],
                    m["byte_count"],
                    m["sha256"],
                    m["actual_bytes"],
                )
                if (
                    kind != dsf.KIND_BRANDING
                    or isinstance(byte_count, bool)
                    or not isinstance(byte_count, int)
                    or not 0 <= byte_count <= _BRAND_SLOT_MAX_BYTES
                    or not isinstance(stored_sha, str)
                    or _SHA256_HEX.fullmatch(stored_sha) is None
                    or isinstance(actual_bytes, bool)
                    or not isinstance(actual_bytes, int)
                    or not 0 <= actual_bytes <= _BRAND_SLOT_MAX_BYTES
                    # A corrupt/incomplete row whose stored body
                    # length disagrees with its claimed byte_count is
                    # refused here, before any body fetch.
                    or actual_bytes != byte_count
                ):
                    return False
                meta[name] = (byte_count, stored_sha)
            # Body ONLY after the bound, for the REQUESTED slot: the
            # bounded fetch re-asserts kind, size, SHA256 and the cap
            # as BOUND parameters (no identifier interpolation), so a
            # concurrently modified or corrupt row can never transfer
            # unbounded bytes.
            name = f"branding/{slot}"
            byte_count, stored_sha = meta[name]
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
                        "cap": _BRAND_SLOT_MAX_BYTES,
                        "size": byte_count,
                        "digest": stored_sha,
                        "kind": dsf.KIND_BRANDING,
                    },
                )
            ).first()
            if body_row is None:
                return False
            fetched = bytes(body_row[0])
            if len(fetched) != byte_count or (
                hashlib.sha256(fetched).hexdigest() != stored_sha
            ):
                return False
            # Typed re-proof from BYTES (the 223 verifier law): the
            # stored body MUST be exactly the packaged neutral
            # substitute; any drift is a safe refusal.
            dsf._verify_leaf_policy(dsf.KIND_BRANDING, fetched, slot)
    except Exception:
        # Driver, connection or statement failure or a display-policy
        # violation: one fixed safe refusal. Cancellation is a
        # BaseException and is not swallowed.
        return False
    _data, content_type = fallback_asset(slot)
    return fetched, content_type


async def _serve(request: Request, slot: str) -> Response:
    """The total demo branding law for ONE fixed slot (see module)."""
    if slot not in SLOTS:  # fixed literal routes only; defense in depth
        return _not_found()
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        # Pre-login demo entry: neutral packaged fallback only (no
        # database, file, settings or live-directory access).
        return _package_fallback(slot)
    leaf = await _read_verified_leaf(request, slot)
    if leaf is False:
        # The copy does not carry the complete finite five-slot leaf
        # set (zero leaves - damaged or pre-upgrade - or a partial
        # set - damaged configured copy): one fixed safe 503, never
        # a silent ambient-file, cross-copy or live-directory read.
        return _unavailable()
    data, content_type = leaf
    return Response(
        data,
        media_type=content_type,
        headers={**_RESPONSE_HEADERS, "Cache-Control": "private, no-store"},
    )


@router.get("/style.css")
async def demo_branding_style_css(request: Request) -> Response:
    return await _serve(request, STYLE_CSS)


@router.get("/logo")
async def demo_branding_logo(request: Request) -> Response:
    return await _serve(request, "logo")


@router.get("/logo-compact")
async def demo_branding_logo_compact(request: Request) -> Response:
    return await _serve(request, "logo-compact")


@router.get("/favicon")
async def demo_branding_favicon(request: Request) -> Response:
    return await _serve(request, "favicon")


@router.get("/hero")
async def demo_branding_hero(request: Request) -> Response:
    return await _serve(request, "hero")
