#!/usr/bin/env python3
"""Structural validator for sbom/cyclonedx.json (stdlib only, Python >= 3.12).

Run as:

    python scripts/check_sbom.py

The SBOM is the script-generated release artifact of
``scripts/generate_sbom.py`` (see ``docs/supply-chain.md``).  This
validator checks structure only (it is not a vulnerability scan):

- ``bomFormat == "CycloneDX"`` and ``specVersion == "1.5"``
- ``metadata.component`` is ``slaif-api-gateway`` / non-empty version /
  ``application``
- ``metadata.tools.components`` is non-empty
- ``metadata.timestamp`` is parseable ISO 8601
- ``components`` is non-empty and every entry has ``type``, ``name``,
  ``version``, and a ``purl`` starting with ``pkg:pypi/``
- no duplicate component names (PEP 503 normalized)
- no dev/test/bootstrap package name from the exact exclusion list
  (``respx`` and ``openai`` are dev/test-only per
  ``pyproject [project.optional-dependencies] dev``)

On success prints exactly ``SBOM_CHECK=OK components=<n>`` and exits 0;
otherwise prints the failing assertions and exits non-zero.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SBOM_PATH = Path(__file__).resolve().parent.parent / "sbom" / "cyclonedx.json"

PEP503_RE = re.compile(r"[-_.]+")

# Exact exclusion list from the 176-a work order.
EXCLUDED = (
    "pip",
    "setuptools",
    "wheel",
    "pytest",
    "pytest-asyncio",
    "pytest-xdist",
    "playwright",
    "hypothesis",
    "ruff",
    "testcontainers",
    "respx",
    "openai",
)


def normalize_name(name: str) -> str:
    """PEP 503 name normalization."""
    return PEP503_RE.sub("-", name).lower()


def main() -> None:
    try:
        with SBOM_PATH.open("r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"SBOM_CHECK=FAIL cannot load {SBOM_PATH}: {exc}")
        sys.exit(1)

    failures: list[str] = []

    if doc.get("bomFormat") != "CycloneDX":
        failures.append(f'bomFormat must be "CycloneDX", got {doc.get("bomFormat")!r}')
    if doc.get("specVersion") != "1.5":
        failures.append(f'specVersion must be "1.5", got {doc.get("specVersion")!r}')

    metadata = doc.get("metadata")
    if not isinstance(metadata, dict):
        failures.append("metadata is missing or not an object")
        metadata = {}

    component = metadata.get("component")
    if not isinstance(component, dict):
        failures.append("metadata.component is missing or not an object")
        component = {}
    if component.get("name") != "slaif-api-gateway":
        failures.append(
            'metadata.component.name must be "slaif-api-gateway", '
            f"got {component.get('name')!r}"
        )
    if component.get("type") != "application":
        failures.append(
            'metadata.component.type must be "application", '
            f"got {component.get('type')!r}"
        )
    if not str(component.get("version") or "").strip():
        failures.append("metadata.component.version is empty")

    tools = metadata.get("tools")
    tools_components = tools.get("components") if isinstance(tools, dict) else None
    if not isinstance(tools_components, list) or not tools_components:
        failures.append("metadata.tools.components is missing or empty")

    timestamp = str(metadata.get("timestamp") or "")
    if not timestamp:
        failures.append("metadata.timestamp is missing or empty")
    else:
        try:
            datetime.fromisoformat(timestamp)
        except ValueError:
            failures.append(
                f"metadata.timestamp is not parseable ISO 8601: {timestamp!r}"
            )

    components = doc.get("components")
    if not isinstance(components, list) or not components:
        failures.append("components is missing, not a list, or empty")
        components = []

    seen: set[str] = set()
    excluded_normalized = {normalize_name(name) for name in EXCLUDED}
    for index, entry in enumerate(components):
        if not isinstance(entry, dict):
            failures.append(f"components[{index}] is not an object")
            continue
        if not entry.get("type"):
            failures.append(f"components[{index}] is missing type")
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            failures.append(f"components[{index}] is missing a string name")
            name = ""
        if not entry.get("version"):
            failures.append(f"components[{index}] ({name!r}) is missing version")
        purl = entry.get("purl")
        if not isinstance(purl, str) or not purl.startswith("pkg:pypi/"):
            failures.append(
                f"components[{index}] ({name!r}) purl must start with "
                f'"pkg:pypi/", got {purl!r}'
            )
        if name:
            key = normalize_name(name)
            if key in seen:
                failures.append(f"duplicate component name: {name!r}")
            seen.add(key)
            if key in excluded_normalized:
                failures.append(
                    f"excluded dev/test/bootstrap package present: {name!r}"
                )

    if failures:
        for failure in failures:
            print(f"SBOM_CHECK=FAIL {failure}")
        sys.exit(1)

    print(f"SBOM_CHECK=OK components={len(components)}")


if __name__ == "__main__":
    main()
