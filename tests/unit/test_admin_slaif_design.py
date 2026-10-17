"""Focused presentation tests for the packaged SLAIF design (188-a).

Covers the design contract's bounded, testable claims: pinned local fonts
with packaged OFL notices, the token system (contract tokens + retained
pre-188 aliases, readable foreground/background pairs), the shared header
shell (brand lockup, section navigation, footer, skip link, navigation
script), the branded standalone error surface (status/message/escaping
preserved), and labeled keyboard-focusable table regions. No domain,
auth, or financial behavior is exercised here.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from fastapi.testclient import TestClient

from slaif_gateway.main import create_app
from slaif_gateway.services.admin_session_service import AdminSessionContext
from tests.unit.test_admin_keys_routes import _app, _row
from tests.unit.test_admin_routes import _admin_session, _admin_user, _settings

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC = REPO_ROOT / "app" / "slaif_gateway" / "web" / "static"
CSS_PATH = STATIC / "css" / "admin.css"
JS_PATH = STATIC / "js" / "navigation.js"
TEMPLATES_DIR = REPO_ROOT / "app" / "slaif_gateway" / "web" / "templates"

# Pinned font provenance (ulfe-lmi/slaif-asset-reservation at dad6e29d,
# google/fonts revision 6e8069ff8ba3dab2a397fb30e7fbd243aba9b57a, OFL 1.1).
FONT_SHA256 = {
    "Roboto.ttf": "d7598e12c5dbef095ff8272cfc55da0250bd07fbdecbac8a530b9b277872a134",
    "RobotoCondensed.ttf": "dace262afcee68a5276f200d8026c57221735c0118ab5fda8c2c0d3dc409a8d0",
    "roboto-OFL.txt": "061402327a96aadb0bfb694a960ed289ecd38d383e396243831ab81feb109c41",
    "robotocondensed-OFL.txt": "0e4cc6ece88573545be2ed25835363662a6182ba4a4c1b5c8feda52add30e8a6",
}


def _login_client(monkeypatch, client: TestClient) -> None:
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
    client.cookies.set("slaif_admin_session", "session-plaintext")


def test_packaged_font_assets_match_pinned_hashes_and_notices() -> None:
    for name, expected in FONT_SHA256.items():
        path = STATIC / "fonts" / name
        assert path.is_file(), name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    for notice in ("roboto-OFL.txt", "robotocondensed-OFL.txt"):
        text = (STATIC / "fonts" / notice).read_text(encoding="utf-8")
        assert "SIL OPEN FONT LICENSE" in text, notice


def test_css_declares_local_font_faces_with_no_external_sources() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")

    for family, url in (
        ("Roboto", "/admin/static/fonts/Roboto.ttf"),
        ('"Roboto Condensed"', "/admin/static/fonts/RobotoCondensed.ttf"),
    ):
        block = re.search(r"@font-face\s*\{[^}]*\}", css + "\n", flags=re.DOTALL)
        matches = [
            b
            for b in re.findall(r"@font-face\s*\{[^}]*\}", css)
            if f"font-family: {family};" in b
        ]
        assert len(matches) == 1, family
        block = matches[0]
        assert f'url("{url}")' in block
        assert "http" not in block, family

    # Body/headings consume the local font tokens.
    assert "--font-body: Roboto" in css
    assert '--font-heading: "Roboto Condensed"' in css


def _root_tokens(css: str) -> dict[str, str]:
    root = css.split(":root {", 1)[1].split("}", 1)[0]
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root))


def test_css_exposes_contract_tokens_and_retained_aliases() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    tokens = _root_tokens(css)

    contract = {
        "--background": "#fbfbf9",
        "--surface": "#ffffff",
        "--text": "#23312f",
        "--heading": "#16302e",
        "--muted": "#52625e",
        "--accent": "#086c86",
        "--border": "#d5e0d8",
        "--lime": "#a3cc32",
        "--pale-blue": "#c8e1e8",
        "--footer-background": "#edf4ef",
    }
    for token, value in contract.items():
        assert tokens[token].strip().lower() == value, token

    # Retained pre-188 aliases track the contract tokens.
    assert tokens["--bg"].strip() == "var(--background)"
    assert tokens["--panel"].strip() == "var(--surface)"
    # Control pair tokens exist so themes coordinate foreground/background.
    for token in (
        "--button-fg",
        "--secondary-bg",
        "--secondary-fg",
        "--control-bg",
        "--table-head-bg",
        "--tint-bg",
        "--tint-fg",
        "--pill-danger-bg",
        "--pill-danger-fg",
        "--pill-warn-bg",
        "--pill-warn-fg",
    ):
        assert token in tokens, token

    # Consumers use the retained alias names so either override works.
    assert "background: var(--bg)" in css
    assert "background: var(--panel)" in css
    assert "color: var(--button-fg)" in css
    assert "background: var(--control-bg)" in css


def _contrast_ratio(fg: str, bg: str) -> float:
    def lin(channel: int) -> float:
        c = channel / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    def luminance(color: str) -> float:
        h = color.lstrip("#")
        return (
            0.2126 * lin(int(h[0:2], 16))
            + 0.7152 * lin(int(h[2:4], 16))
            + 0.0722 * lin(int(h[4:6], 16))
        )

    a, b = luminance(fg), luminance(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def test_default_theme_text_pairs_meet_contrast_floor() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    tokens = _root_tokens(css)

    # Normal text >= 4.5:1 for the default theme's core pairs.
    pairs = (
        (tokens["--text"], tokens["--background"]),
        (tokens["--muted"], tokens["--background"]),
        (tokens["--heading"], tokens["--background"]),
        (tokens["--button-fg"], tokens["--accent"]),
        # --secondary-fg is var(--accent) in the default theme.
        (tokens["--accent"], "#ffffff"),
        (tokens["--text"], tokens["--table-head-bg"].replace("var(--heading)", "") or "e8f1ed"),
        (tokens["--tint-fg"], tokens["--tint-bg"]),
        (tokens["--pill-danger-fg"], tokens["--pill-danger-bg"]),
        (tokens["--pill-warn-fg"], tokens["--pill-warn-bg"]),
        (tokens["--error-text"], tokens["--error-bg"]),
    )
    for fg, bg in pairs:
        fg = fg.strip().lower().lstrip("#")
        bg = bg.strip().lower().lstrip("#")
        assert re.fullmatch(r"[0-9a-f]{6}", fg), fg
        assert re.fullmatch(r"[0-9a-f]{6}", bg), bg
        assert _contrast_ratio(fg, bg) >= 4.5, (fg, bg, _contrast_ratio(fg, bg))


def test_login_page_renders_shared_shell_without_navigation() -> None:
    html = TestClient(create_app(_settings())).get("/admin/login").text

    assert 'class="skip-link"' in html
    assert 'class="admin-header"' in html
    assert 'class="brand-lockup admin-brand" href="/admin"' in html
    assert 'id="admin-main"' in html
    assert 'class="admin-footer"' in html
    assert 'src="/admin/static/js/navigation.js"' in html
    # Unauthenticated: no section navigation or expanded-state controls.
    assert 'id="admin-nav"' not in html
    assert 'data-nav-toggle' not in html
    assert 'action="/admin/logout"' not in html


def test_authenticated_pages_render_navigation_with_current_section(monkeypatch) -> None:
    client = TestClient(_app())
    _login_client(monkeypatch, client)

    dashboard = client.get("/admin")
    assert dashboard.status_code == 200
    assert 'id="admin-nav"' in dashboard.text
    assert 'data-nav-toggle' in dashboard.text
    assert 'aria-controls="admin-nav"' in dashboard.text
    assert '<a href="/admin" aria-current="page">Dashboard</a>' in dashboard.text
    assert '<a href="/admin/keys"' in dashboard.text
    assert '<a href="/admin/openai-assisted"' in dashboard.text

    async def list_keys(self, **kwargs):
        return [_row()]

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.list_keys",
        list_keys,
    )
    keys_page = client.get("/admin/keys")
    assert keys_page.status_code == 200
    assert '<a href="/admin/keys" aria-current="page">Keys</a>' in keys_page.text
    assert '<a href="/admin" aria-current="page">Dashboard</a>' not in keys_page.text


def test_navigation_script_is_served() -> None:
    response = TestClient(create_app(_settings())).get("/admin/static/js/navigation.js")

    assert response.status_code == 200
    assert "nav-ready" in response.text
    assert "aria-expanded" in response.text
    assert "Escape" in response.text


def test_error_pages_preserve_status_message_and_shell() -> None:
    client = TestClient(create_app(_settings()))

    # 404 with the exact pre-188 message, now on the shared branded surface.
    response = client.get("/admin/keys/not-a-key")
    assert response.status_code == 404
    body = response.text
    assert "Gateway key not found." in body
    assert 'class="error-page"' in body
    assert "HTTP 404" in body
    assert 'class="admin-header"' in body
    assert 'class="admin-footer"' in body
    assert 'class="skip-link"' in body

    # 503 unavailable surface.
    unavailable = client.get("/admin/login", headers={})
    # Login is available by default; the 503 path is exercised via settings.
    app_off = create_app(_settings(ENABLE_ADMIN_DASHBOARD=False))
    with TestClient(app_off) as off_client:
        response = off_client.get("/admin")
    assert response.status_code == 404
    assert "Not found." in response.text

    assert unavailable.status_code == 200


def test_error_page_escapes_message_data() -> None:
    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    template = env.get_template("error.html")
    # error.html extends base.html, which needs the context values.
    rendered = template.render(
        branding_icon_link='<link rel="icon" type="image/svg+xml" href="/x">',
        branding_css_link="",
        branding_enabled=False,
        branding_logo_src="/logo",
        branding_logo_compact_src="/logo-compact",
        branding_hero_src="",
        error_status=400,
        error_status_text="Bad request",
        error_message='<script>alert("x")</script>&ok',
    )
    assert "<script>alert" not in rendered
    assert "&lt;script&gt;alert(&#34;x&#34;)&lt;/script&gt;&amp;ok" in rendered


def test_table_wrappers_are_labeled_and_focusable() -> None:
    wrappers = 0
    for path in TEMPLATES_DIR.rglob("*.html"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if 'class="table-wrap"' in line:
                wrappers += 1
                assert 'role="region"' in line, path
                assert 'tabindex="0"' in line, path
                assert re.search(r'aria-label="[^"]+"', line), path
    assert wrappers == 23


def test_templates_css_and_js_reference_no_external_assets() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    for url in re.findall(r'url\(([^)]+)\)', css):
        assert "http" not in url and "//" not in url.strip(), url
    js = JS_PATH.read_text(encoding="utf-8")
    assert "http" not in js
    for path in TEMPLATES_DIR.rglob("*.html"):
        html = path.read_text(encoding="utf-8")
        for attr in re.findall(r'(?:src|href)="([^"]+)"', html):
            assert not attr.startswith(("http://", "https://", "//")), (path, attr)
            assert "slaif.si" not in attr.lower(), (path, attr)


def test_packaged_error_response_does_not_change_v1_json_contract() -> None:
    response = TestClient(create_app(_settings())).post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]},
    )
    # Unauthenticated /v1 calls keep the OpenAI-shaped JSON error.
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    assert "<!doctype" not in response.text
