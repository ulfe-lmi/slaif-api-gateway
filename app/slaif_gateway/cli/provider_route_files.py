"""Bounded, safe file helpers shared by the providers/routes CLI groups (199-a).

Two NON-secret file contracts:

* a capabilities file (``--capabilities-file``) — complete replacement
  capabilities for a model route;
* a route update plan file (``routes update --dry-run``/``--execute``).

File reads are bounded at cap+1 BEFORE any parsing (an oversized payload is
never fully materialized), and error messages use fixed safe vocabulary:
they never echo file bodies, paths, or operator-supplied values. Plan
writes are exclusive (never overwrite), restrictive (0600), and only
happen after the rendered plan strictly round-trips.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from slaif_gateway.schemas.provider_route_configuration import (
    CAPABILITIES_FILE_MAX_BYTES,
    ROUTE_PLAN_FILE_MAX_BYTES,
    ProviderRouteConfigError,
    RouteUpdatePlan,
    parse_capabilities_file,
    parse_route_update_plan_document,
    parse_route_update_plan_file,
    render_route_update_plan,
)


def read_bounded_file(path: Path | str, *, cap: int, label: str) -> bytes:
    """Read at most cap+1 bytes; refuse oversized files with a safe error."""
    try:
        with Path(path).open("rb") as handle:
            data = handle.read(cap + 1)
    except OSError as exc:
        raise typer.BadParameter(f"{label} is missing or unreadable.") from exc
    if len(data) > cap:
        raise typer.BadParameter(f"{label} exceeds the bounded size.")
    return data


def read_capabilities_file(path: Path | str) -> dict[str, object]:
    """Read and strictly validate one capabilities file (safe errors)."""
    data = read_bounded_file(
        path, cap=CAPABILITIES_FILE_MAX_BYTES, label="Capabilities file"
    )
    try:
        return parse_capabilities_file(data)
    except ProviderRouteConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc


def read_route_plan_file(path: Path | str) -> RouteUpdatePlan:
    """Read and strictly parse one route update plan file (safe errors)."""
    data = read_bounded_file(path, cap=ROUTE_PLAN_FILE_MAX_BYTES, label="Route plan file")
    try:
        return parse_route_update_plan_file(data)
    except ProviderRouteConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc


def write_route_plan_file(path: Path | str, plan: RouteUpdatePlan) -> None:
    """Write a reviewed NON-secret plan to a new 0600 file (no overwrite).

    The rendered document must strict-round-trip through the plan parser
    before anything is written.
    """
    document = render_route_update_plan(plan)
    parse_route_update_plan_document(document)  # strict round-trip gate
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    data = text.encode("utf-8")
    if len(data) > ROUTE_PLAN_FILE_MAX_BYTES:
        raise typer.BadParameter("Route plan exceeds the bounded file size.")
    try:
        fd = os.open(Path(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise typer.BadParameter("Route plan file already exists.") from exc
    except OSError as exc:
        raise typer.BadParameter("Could not create route plan file.") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
    except OSError as exc:
        raise typer.BadParameter("Could not write route plan file.") from exc
