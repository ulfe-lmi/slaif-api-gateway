"""Objective 181 (I3, 181-i): bounded measured code identity for catalog
refresh execution.

The identity is a deterministic SHA-256 over the (logical name, file
content) pairs of a FIXED small set of owned catalog-refresh files
(including this helper itself), computed from source bytes at the
package root. It identifies the MEASURED source content of exactly that
set:

- it is NOT a whole-environment digest, NOT loaded-bytecode attestation,
  NOT a security boundary, and NOT a reproducibility promise;
- relocation of the tree or timestamp changes do NOT change it;
- changed bytes DO change it, even under an unchanged package version;
- unavailable or unsupported input (missing/non-regular/unreadable
  file, or a bound exceeded) yields the explicit ``unavailable`` marker
  — never a fabricated "known current" identity;
- no Git inspection, no environment/config traversal, no subprocess,
  no recursive scan: only the fixed relative paths below, resolved
  against the installed ``slaif_gateway`` package root (source checkout
  and wheel layouts both work).

The package VERSION is recorded separately in the existing tool
metadata (``tool``); the code identity is what makes two installations
with the same version and different bytes distinguishable.
"""

from __future__ import annotations

import hashlib
import os
import stat
from importlib.metadata import version as _package_version
from pathlib import Path

from slaif_gateway.schemas.catalog_refresh import (
    EXTRACTOR_ID,
    POLICY_VERSION,
    RENDERER_VERSION,
    SCHEMA_VERSION,
)

__all__ = [
    "CODE_IDENTITY_UNAVAILABLE",
    "IDENTITY_FILES",
    "IDENTITY_VERSION",
    "generator_versions",
    "measure_code_identity",
    "package_version",
    "tool_identity",
]

IDENTITY_VERSION = "1"
IDENTITY_PREFIX = f"catalog-ccid/v{IDENTITY_VERSION}:sha256:"
CODE_IDENTITY_UNAVAILABLE = "unavailable"

# The fixed, documented, owned relevant file set (logical names are the
# package-root-relative paths; order is fixed). Catalog/schema/CLI/
# parser/validator/renderer/sealing helpers plus this helper itself.
IDENTITY_FILES: tuple[str, ...] = (
    "cli/catalog_refresh.py",
    "schemas/catalog_refresh.py",
    "services/catalog_refresh/baseline.py",
    "services/catalog_refresh/bundle.py",
    "services/catalog_refresh/collection.py",
    "services/catalog_refresh/errors.py",
    "services/catalog_refresh/execution_identity.py",
    "services/catalog_refresh/filesystem.py",
    "services/catalog_refresh/policy.py",
    "services/catalog_refresh/rendering.py",
    "services/catalog_refresh/sealing.py",
    "services/catalog_refresh/source_evidence.py",
    "services/catalog_refresh/source_transport.py",
    "services/catalog_refresh/sources.py",
    "services/catalog_refresh/validation.py",
)

# Bounds on the measurement (fail closed to ``unavailable``).
MAX_IDENTITY_FILES = 32
MAX_IDENTITY_FILE_BYTES = 512 * 1024
MAX_IDENTITY_TOTAL_BYTES = 8 * 1024 * 1024
_READ_CHUNK = 64 * 1024


def _package_root() -> Path:
    """The installed ``slaif_gateway`` package root (source or wheel)."""
    return Path(__file__).resolve().parents[2]


def _read_bounded(path: Path, expected_size: int) -> bytes:
    """Read exactly ``expected_size`` bytes; a size change (shrink OR
    growth) or any I/O error raises (the caller reports the identity as
    unavailable). The one-byte EOF probe after the expected size is what
    detects growth between the stat and the read."""
    parts: list[bytes] = []
    total = 0
    with open(path, "rb") as handle:
        while total < expected_size:
            chunk = handle.read(min(_READ_CHUNK, expected_size - total))
            if not chunk:
                raise OSError("file shrank during identity measurement")
            parts.append(chunk)
            total += len(chunk)
        if handle.read(1):
            raise OSError("file grew during identity measurement")
    return b"".join(parts)


def measure_code_identity(root: Path | None = None) -> str:
    """Deterministic content identity of the fixed owned file set.

    Returns ``catalog-ccid/v<version>:sha256:<64 hex>`` on success, or
    the explicit ``unavailable`` marker when the set cannot be measured
    (missing/non-regular/unreadable file, size or aggregate bound
    exceeded, or any I/O error). The digest is over the fixed logical
    names and file bytes, so relocation and timestamps do not change
    it while any byte change does.
    """
    try:
        if root is None:
            root = _package_root()
        if len(IDENTITY_FILES) > MAX_IDENTITY_FILES:
            return CODE_IDENTITY_UNAVAILABLE
        digest = hashlib.sha256()
        total = 0
        for name in IDENTITY_FILES:
            path = root / name
            st = os.lstat(path)
            if not stat.S_ISREG(st.st_mode):
                return CODE_IDENTITY_UNAVAILABLE
            if st.st_size > MAX_IDENTITY_FILE_BYTES:
                return CODE_IDENTITY_UNAVAILABLE
            total += st.st_size
            if total > MAX_IDENTITY_TOTAL_BYTES:
                return CODE_IDENTITY_UNAVAILABLE
            content = _read_bounded(path, st.st_size)
            digest.update(name.encode("utf-8"))
            digest.update(b"\x00")
            digest.update(content)
        return IDENTITY_PREFIX + digest.hexdigest()
    except OSError:
        return CODE_IDENTITY_UNAVAILABLE


def package_version() -> str:
    """Installed package version; an uninstalled dev checkout is an
    honest ``0.0.0+local`` (the version alone is NOT exact source
    identity — the measured code identity is)."""
    try:
        return _package_version("slaif-api-gateway")
    except Exception:  # noqa: BLE001 - uninstalled dev checkouts
        return "0.0.0+local"


def tool_identity() -> tuple[str, str]:
    """(tool, code_revision) for the running code: the package version
    stays in the tool metadata; the code_revision is the measured fixed
    file-set identity (or the explicit unavailable marker)."""
    return f"slaif-gateway/{package_version()}", measure_code_identity()


def generator_versions() -> dict[str, object]:
    """The ACTUAL version set of the running code (181-i I2/I3).

    Runner-owned values for the authenticated execution context: the
    generating schema/renderer/policy contract versions and the
    registered extractor identity, taken from this code's own constants.
    They are never taken from the (supplied, historical) bundle
    declaration.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "renderer_version": RENDERER_VERSION,
        "policy_version": POLICY_VERSION,
        "extractor_version": EXTRACTOR_ID,
    }
