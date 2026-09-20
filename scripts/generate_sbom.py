#!/usr/bin/env python3
"""Generate the scoped release SBOM for slaif-api-gateway.

This is the documented release-SBOM mechanism for ``sbom/cyclonedx.json``.
It is stdlib-only and requires Python >= 3.12. Run it as:

    python scripts/generate_sbom.py

Two stages:

1. **Freeze.**  An ephemeral virtualenv is created in a fresh temporary
   directory (``python -m venv --clear <tmpdir>``), exactly the direct
   production dependencies parsed from ``[project] dependencies`` in
   ``pyproject.toml`` via ``tomllib`` (nothing is hardcoded) are
   installed into it, and ``pip freeze`` captures the exact transitive
   production graph.  The venv bootstrap distributions ``pip``,
   ``setuptools``, and ``wheel`` are removed from the freeze: they are
   virtualenv tooling, not project dependencies.  On pip failure the
   script prints the pip output and exits non-zero; it never forces
   resolution with ``--no-deps`` or similar.

2. **Emit.**  ``sbom/cyclonedx.json`` is written deterministically from
   the freeze as a flat CycloneDX 1.5 component list: ``bomFormat``
   ``CycloneDX``, ``specVersion`` ``1.5``, ``version`` 1, the generation
   time in ``metadata.timestamp``, the exact ``metadata.component``, the
   generator recorded in ``metadata.tools.components``, and one
   ``library`` component per freeze line, sorted by normalized name.
   The document carries no ``serialNumber`` and no ``dependencies``
   graph (flat component list, CycloneDX 1.5).

The only network interaction is ordinary PyPI package resolution during
the stage-1 install.  See ``docs/supply-chain.md`` for what the
generated artifact attests and what it does not.
"""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
SBOM_PATH = REPO_ROOT / "sbom" / "cyclonedx.json"
COMPONENT_NAME = "slaif-api-gateway"
GENERATOR_NAME = "slaif-generate-sbom"
GENERATOR_VERSION = "1.0"

# Venv bootstrap distributions that are virtualenv tooling rather than
# project dependencies; removed from the freeze (documented above and in
# docs/supply-chain.md).
BOOTSTRAP_DISTS = {"pip", "setuptools", "wheel"}

PEP503_RE = re.compile(r"[-_.]+")


def fail(message: str) -> None:
    print(f"generate_sbom: ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def normalize_name(name: str) -> str:
    """PEP 503 name normalization."""
    return PEP503_RE.sub("-", name).lower()


def load_project() -> tuple[str, list[str]]:
    try:
        with PYPROJECT_PATH.open("rb") as fh:
            project = tomllib.load(fh)["project"]
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        fail(f"cannot parse {PYPROJECT_PATH}: {exc}")
    version = str(project.get("version") or "").strip()
    if not version:
        fail("[project] version is missing from pyproject.toml")
    dependencies = project.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        fail("[project] dependencies must be a non-empty list")
    return version, [str(d).strip() for d in dependencies if str(d).strip()]


def venv_python(venv_dir: Path) -> Path:
    for candidate in (
        venv_dir / "bin" / "python",
        venv_dir / "Scripts" / "python.exe",
        venv_dir / "Scripts" / "python",
    ):
        if candidate.exists():
            return candidate
    fail(f"venv interpreter not found under {venv_dir}")


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def parse_freeze(freeze_output: str) -> tuple[int, list[tuple[str, str]]]:
    """Parse ``name==version`` lines; skip comments; drop bootstrap dists.

    Returns (count of raw ``name==version`` source lines, retained
    ``(name, version)`` entries after the documented bootstrap removal).
    """
    raw_lines = 0
    entries: list[tuple[str, str]] = []
    for raw_line in freeze_output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            fail(f"freeze entry without version: {line!r}")
        raw_lines += 1
        name, version = line.split("==", 1)
        name = name.strip()
        version = version.strip()
        if not name or not version:
            fail(f"malformed freeze entry: {line!r}")
        if normalize_name(name) in BOOTSTRAP_DISTS:
            # Documented venv bootstrap removal: pip/setuptools/wheel are
            # virtualenv tooling, not project dependencies.
            continue
        entries.append((name, version))
    return raw_lines, entries


def freeze_production_graph(dependencies: list[str]) -> list[tuple[str, str]]:
    """Stage 1: install exactly the direct production deps, then freeze."""
    tmp_root = Path(tempfile.mkdtemp(prefix="slaif-sbom-"))
    venv_dir = tmp_root / "venv"
    try:
        proc = run([sys.executable, "-m", "venv", "--clear", str(venv_dir)])
        if proc.returncode != 0:
            print(proc.stdout, file=sys.stderr, end="")
            print(proc.stderr, file=sys.stderr, end="")
            fail(f"python -m venv --clear exited {proc.returncode}")
        venv_py = venv_python(venv_dir)
        proc = run([str(venv_py), "-m", "pip", "install", *dependencies])
        if proc.returncode != 0:
            print(proc.stdout, file=sys.stderr, end="")
            print(proc.stderr, file=sys.stderr, end="")
            fail(
                "pip install failed; printing pip output and exiting non-zero "
                "(never forcing --no-deps or similar)"
            )
        proc = run([str(venv_py), "-m", "pip", "freeze"])
        if proc.returncode != 0:
            print(proc.stdout, file=sys.stderr, end="")
            print(proc.stderr, file=sys.stderr, end="")
            fail(f"pip freeze exited {proc.returncode}")
        raw_lines, entries = parse_freeze(proc.stdout)
        if not entries:
            fail("pip freeze produced no installable components")
        print(f"pip freeze source lines (name==version): {raw_lines}")
        removed = sorted(BOOTSTRAP_DISTS)
        print(
            "documented venv bootstrap removals: "
            + ", ".join(removed)
        )
        return entries
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def emit_sbom(version: str, entries: list[tuple[str, str]]) -> None:
    """Stage 2: write sbom/cyclonedx.json deterministically from the freeze."""
    components = [
        {
            "type": "library",
            "name": name,
            "version": entry_version,
            "purl": f"pkg:pypi/{normalize_name(name)}@{entry_version}",
        }
        for name, entry_version in sorted(
            entries, key=lambda item: (normalize_name(item[0]), item[0])
        )
    ]
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": GENERATOR_NAME,
                        "version": GENERATOR_VERSION,
                    },
                    {
                        "type": "library",
                        "name": "Python",
                        "version": platform.python_version(),
                    },
                ]
            },
            "component": {
                "name": COMPONENT_NAME,
                "version": version,
                "type": "application",
            },
        },
        "components": components,
    }
    SBOM_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SBOM_PATH.open("w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2)
        fh.write("\n")


def main() -> None:
    version, dependencies = load_project()
    print(f"direct production dependencies parsed from pyproject.toml: {len(dependencies)}")
    for dep in dependencies:
        print(f"  {dep}")
    entries = freeze_production_graph(dependencies)
    emit_sbom(version, entries)
    print(f"components written to {SBOM_PATH.relative_to(REPO_ROOT)}: {len(entries)}")
    print(f"SBOM_GENERATED components={len(entries)} version={version}")


if __name__ == "__main__":
    main()
