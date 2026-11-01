"""Deterministic local asset revision URLs for bundled admin assets (193-a).

The admin dashboard serves its bundled CSS/JS from the static mount at
``/admin/static``. Asset URLs were historically unversioned, so a browser
that cached an old component kept reusing it under the same asset identity
after a deployment. This module implements the small deterministic local
revision mechanism approved for Objective 193-a:

- a FIXED allowlist of logical asset names mapped to their static-relative
  paths (the names are literal constants, never request/user input, so this
  helper can never address an arbitrary filesystem path);
- a bounded content digest (sha256, first 16 hex chars) of the exact file
  bytes, appended as ``?v=<digest>``.

Changed bytes therefore produce a changed URL (stale browsers pick up the
new component on the next page load), while unchanged bytes produce a
stable URL. The digest covers file CONTENT ONLY: no filesystem paths,
environment values, or secret material appear in the URL. There is no
remote asset service, cache framework, service worker, database, or build
dependency; the normal static mount serves the query URLs unchanged.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_STATIC_ROOT = Path(__file__).resolve().parent / "static"

# Fixed allowlist: logical name -> static-relative path. New bundled assets
# must be added here explicitly (reported with the change); unknown names
# raise instead of being resolved against the filesystem.
_ASSETS: dict[str, str] = {
    "admin.css": "css/admin.css",
    "navigation.js": "js/navigation.js",
    "table-sort.js": "js/table-sort.js",
    "record-choices.js": "js/record-choices.js",
    "policy-selector.js": "js/policy-selector.js",
    "streaming-live-burn.js": "js/streaming-live-burn.js",
    "lazy-throttling.js": "js/lazy-throttling.js",
    "key-clone.js": "js/key-clone.js",
    "key-batch.js": "js/key-batch.js",
}


def content_revision(data: bytes) -> str:
    """Bounded deterministic revision tag for exact asset bytes."""
    return hashlib.sha256(data).hexdigest()[:16]


def asset_url(name: str) -> str:
    """Versioned URL for one bundled admin asset.

    Reads the bundled file on each call (no operator-style asset cache): a
    byte change changes the URL, identical bytes stay stable. Raises
    ``ValueError`` for unknown logical names and ``FileNotFoundError`` if a
    bundled asset is missing from the package (a packaging defect that must
    fail loudly rather than serve a stale unversioned URL).
    """
    try:
        rel = _ASSETS[name]
    except KeyError:
        raise ValueError(f"unknown admin asset: {name!r}") from None
    data = (_STATIC_ROOT / rel).read_bytes()
    return f"/admin/static/{rel}?v={content_revision(data)}"
