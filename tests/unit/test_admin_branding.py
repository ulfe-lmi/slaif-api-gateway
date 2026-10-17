from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from slaif_gateway.services.admin_session_service import AdminSessionContext
from tests.unit.test_admin_routes import _admin_session, _admin_user, _app


REPO_ROOT = Path(__file__).resolve().parents[2]
LOGO_SRC = "/admin/static/img/slaif-logo.svg"
LOGO_ALT = "SLAIF Slovenian AI Factory"
SVG_PATH = REPO_ROOT / "app" / "slaif_gateway" / "web" / "static" / "img" / "slaif-logo.svg"
TEMPLATES_DIR = REPO_ROOT / "app" / "slaif_gateway" / "web" / "templates"


def test_admin_login_page_includes_local_slaif_logo() -> None:
    response = TestClient(_app()).get("/admin/login")

    assert response.status_code == 200
    # 188-a: the packaged identity lives in the shared header lockup.
    assert "admin-brand" in response.text
    assert f'src="{LOGO_SRC}"' in response.text
    assert f'alt="{LOGO_ALT}"' in response.text


def test_admin_dashboard_page_includes_linked_local_slaif_logo(monkeypatch) -> None:
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "dashboard-csrf"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    client = TestClient(_app())
    client.cookies.set("slaif_admin_session", "session-plaintext")

    response = client.get("/admin")

    assert response.status_code == 200
    # 188-a: the shared header lockup is the linked local logo surface.
    assert f'src="{LOGO_SRC}"' in response.text
    assert f'alt="{LOGO_ALT}"' in response.text
    assert 'class="brand-lockup admin-brand" href="/admin"' in response.text


def test_admin_static_logo_asset_is_served() -> None:
    response = TestClient(_app()).get(LOGO_SRC)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in response.content


def test_admin_templates_do_not_use_external_logo_or_image_urls() -> None:
    for template_path in TEMPLATES_DIR.rglob("*.html"):
        template = template_path.read_text(encoding="utf-8")
        assert not re.search(r"<img[^>]+src=[\"']https?://", template, flags=re.IGNORECASE), template_path
        assert "slaif.si" not in template.lower(), template_path
        assert "img/logos" not in template.lower(), template_path


def test_slaif_logo_svg_contains_no_unsafe_svg_content() -> None:
    svg = SVG_PATH.read_text(encoding="utf-8")
    svg_lower = svg.lower()

    assert "<script" not in svg_lower
    assert "foreignobject" not in svg_lower
    assert "javascript:" not in svg_lower
    assert not re.search(r"\son[a-z]+\s*=", svg, flags=re.IGNORECASE)
    assert "href=" not in svg_lower
    assert "xlink:href=" not in svg_lower
    assert not re.search(r"<image\b[^>]+(?:https?:|//|data:)", svg, flags=re.IGNORECASE)


# --- 187-a operator-branding render contract ---------------------------------

from tests.unit.test_admin_routes import _settings  # noqa: E402

CUSTOM = REPO_ROOT / "tests" / "fixtures" / "branding" / "custom"
FALLBACK = REPO_ROOT / "tests" / "fixtures" / "branding" / "fallback"
PACKAGED_ICON_LINK = f'<link rel="icon" type="image/svg+xml" href="{LOGO_SRC}">'


def _branded_client(branding_dir):
    return TestClient(_app(_settings(SLAIF_BRANDING_DIR=str(branding_dir))))


def test_login_render_disabled_is_packaged_default() -> None:
    html = TestClient(_app()).get("/admin/login").text

    assert f'src="{LOGO_SRC}"' in html
    assert PACKAGED_ICON_LINK in html
    assert "branding-active" not in html
    assert "brand-logo-compact" not in html
    assert "/admin/branding/style.css" not in html
    assert "auth-hero" not in html
    assert not re.search(r"<img[^>]+src=\"\"", html)


def test_login_render_enabled_uses_all_overrides() -> None:
    html = _branded_client(CUSTOM).get("/admin/login").text

    assert 'src="/admin/branding/logo"' in html
    assert 'src="/admin/branding/logo-compact"' in html
    assert "brand-lockup admin-brand branding-active" in html
    assert '<link rel="stylesheet" href="/admin/branding/style.css">' in html
    assert '<img class="auth-hero" src="/admin/branding/hero" alt="">' in html
    assert '<link rel="icon" type="image/png" href="/admin/branding/favicon">' in html
    # Operator CSS is loaded AFTER the packaged admin stylesheet.
    assert html.index("/admin/static/css/admin.css") < html.index("/admin/branding/style.css")
    assert not re.search(r"<img[^>]+src=\"\"", html)


def test_login_render_invalid_slot_falls_back_per_slot() -> None:
    html = _branded_client(FALLBACK).get("/admin/login").text

    assert "brand-lockup admin-brand branding-active" in html
    assert f'src="{LOGO_SRC}"' in html
    assert "brand-logo-compact" in html
    assert '/admin/branding/logo' not in html
    assert "/admin/branding/style.css" not in html
    assert "auth-hero" not in html
    assert PACKAGED_ICON_LINK in html


def test_login_render_compact_slot_falls_back_independently(tmp_path) -> None:
    target = tmp_path / "branding"
    target.mkdir()
    (target / "logo-compact.png").write_bytes((CUSTOM / "logo-compact.png").read_bytes())

    html = _branded_client(target).get("/admin/login").text

    assert f'src="{LOGO_SRC}"' in html
    assert 'src="/admin/branding/logo-compact"' in html
    assert PACKAGED_ICON_LINK in html


def test_dashboard_render_enabled_uses_overrides(monkeypatch) -> None:
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "dashboard-csrf"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    client = _branded_client(CUSTOM)
    client.cookies.set("slaif_admin_session", "session-plaintext")

    response = client.get("/admin")

    assert response.status_code == 200
    assert 'src="/admin/branding/logo"' in response.text
    assert "branding-active" in response.text
    assert PACKAGED_ICON_LINK not in response.text


def test_login_csrf_error_page_renders_with_branding() -> None:
    client = _branded_client(CUSTOM)
    login = client.get("/admin/login")

    assert login.status_code == 200
    response = client.post(
        "/admin/login",
        data={"email": "admin@example.org", "password": "wrong", "csrf_token": "invalid"},
    )

    assert response.status_code == 400
    assert "Your login form expired. Try again." in response.text
    assert 'src="/admin/branding/logo"' in response.text
    assert f'src="{LOGO_SRC}"' not in response.text
