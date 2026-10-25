"""Focused tests for deterministic local asset revision URLs (193-a).

Covers the approved cache-identity contract for the bundled admin CSS/JS:
changed bytes produce a changed ``?v=`` URL, unchanged bytes stay stable,
the digest covers content only (no path/environment/secret material), the
fixed allowlist rejects unknown names instead of resolving arbitrary
filesystem paths, and the rendered admin pages reference the exact
versioned URLs that the normal static mount serves. No cache framework,
service worker, or database is involved.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from fastapi.testclient import TestClient

from slaif_gateway.main import create_app
from slaif_gateway.web import assets
from tests.unit.test_admin_routes import _settings

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC = REPO_ROOT / "app" / "slaif_gateway" / "web" / "static"

_EXPECTED_ASSETS = {
    "admin.css": "css/admin.css",
    "navigation.js": "js/navigation.js",
    "table-sort.js": "js/table-sort.js",
    "record-choices.js": "js/record-choices.js",
    "policy-selector.js": "js/policy-selector.js",
    "streaming-live-burn.js": "js/streaming-live-burn.js",
    "lazy-throttling.js": "js/lazy-throttling.js",
}


def _revision(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def test_content_revision_is_deterministic_and_sensitive() -> None:
    a = assets.content_revision(b"shared-bytes")
    b = assets.content_revision(b"shared-bytes")
    c = assets.content_revision(b"changed-bytes")
    assert a == b, "unchanged bytes must produce a stable revision"
    assert a != c, "changed bytes must produce a different revision"
    assert re.fullmatch(r"[0-9a-f]{16}", a), a


def test_asset_url_matches_exact_bundled_bytes() -> None:
    for name, rel in _EXPECTED_ASSETS.items():
        data = (STATIC / rel).read_bytes()
        assert assets.asset_url(name) == f"/admin/static/{rel}?v={_revision(data)}"


def test_asset_url_stable_for_same_bytes_and_changes_with_bytes(
    monkeypatch, tmp_path
) -> None:
    (tmp_path / "css").mkdir()
    # The logical name "admin.css" maps to css/admin.css, so the probe
    # file must live at that static-relative path.
    target = tmp_path / "css" / "admin.css"
    target.write_bytes(b"body{color:#111}")
    monkeypatch.setattr(assets, "_STATIC_ROOT", tmp_path)
    first = assets.asset_url("admin.css")
    assert assets.asset_url("admin.css") == first, "same bytes must stay stable"
    target.write_bytes(b"body{color:#222}")
    second = assets.asset_url("admin.css")
    assert second != first, "changed bytes must change the asset identity"
    target.write_bytes(b"body{color:#111}")
    assert assets.asset_url("admin.css") == first, "restored bytes restore the URL"


def test_unknown_asset_names_are_rejected() -> None:
    for bad in ("../../etc/passwd", "css/../js/navigation.js", "nope.css", ""):
        try:
            assets.asset_url(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unknown asset name accepted: {bad!r}")


def test_login_page_references_exact_versioned_urls_and_static_serves_them() -> None:
    client = TestClient(create_app(_settings()))
    html = client.get("/admin/login").text
    css_data = (STATIC / "css" / "admin.css").read_bytes()
    css_url = f"/admin/static/css/admin.css?v={_revision(css_data)}"
    assert f'href="{css_url}"' in html
    js_urls = {
        rel: f"/admin/static/{rel}?v={_revision((STATIC / rel).read_bytes())}"
        for rel in ("js/navigation.js", "js/table-sort.js", "js/record-choices.js")
    }
    for url in js_urls.values():
        assert f'src="{url}"' in html, url
    # The normal static mount serves the versioned URLs byte-for-byte.
    response = client.get(css_url)
    assert response.status_code == 200
    assert response.content == css_data
    for rel, url in js_urls.items():
        response = client.get(url)
        assert response.status_code == 200, url
        assert response.content == (STATIC / rel).read_bytes()
    # Unknown static names keep the normal 404 behavior (no arbitrary
    # filesystem reads through the asset helper or the static mount).
    assert client.get("/admin/static/nope.css").status_code == 404
