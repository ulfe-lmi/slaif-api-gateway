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
    assert f'src="{LOGO_SRC}"' in response.text
    assert f'alt="{LOGO_ALT}"' in response.text
    assert "auth-logo" in response.text


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
    assert f'src="{LOGO_SRC}"' in response.text
    assert f'alt="{LOGO_ALT}"' in response.text
    assert 'class="brand-lockup dashboard-brand-link" href="/admin"' in response.text


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
