"""194-a admin table row-numbering / metric-column unit contract.

Renders the REAL keys list page through the ASGI app with the unit fake
session (no DB, no server): server-rendered ordinals for zero/one/many
rows, the fixed empty-state row with the correct colspan, the split
usage/quota metric cells with their typed raw sort keys (zero displays
``0``, ``None`` displays ``Unlimited`` with an empty raw key), and the
visible Rows selector bound to the GET filter form (presets plus a
preserved custom limit, no duplicate hidden limit field).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_keys import AdminKeyDetail
from slaif_gateway.services.admin_session_service import AdminSessionContext

from test_admin_keys_templates_safety import _FakeSessionmaker, _safe_key

SESSION_COOKIE = "194-row-ordinal-session"


def _client(monkeypatch, keys: list[AdminKeyDetail]) -> TestClient:
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
        ADMIN_SESSION_SECRET="admin-session-secret-must-not-render",
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    app = create_app(settings)
    app.state.db_sessionmaker = _FakeSessionmaker()
    admin_user = AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="password_hash_must_not_render",
        role="admin",
        is_active=True,
    )
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="session_hash_must_not_render",
        csrf_token_hash="csrf_hash_must_not_render",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "rendered-csrf-token"

    async def list_keys(self, **kwargs):
        return keys

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.list_keys",
        list_keys,
    )
    client = TestClient(app)
    client.cookies.set("slaif_admin_session", SESSION_COOKIE)
    return client


def _key(**overrides) -> AdminKeyDetail:
    base = _safe_key()
    return replace(base, **overrides) if overrides else base


def _tbody_rows(html: str) -> list[str]:

    tbody = html[html.index("<tbody>") : html.index("</tbody>")]
    return re.findall(r"<tr\b[^>]*>.*?</tr>", tbody, flags=re.DOTALL)


def test_keys_list_zero_rows_renders_fixed_empty_state(monkeypatch) -> None:
    client = _client(monkeypatch, [])
    html = client.get("/admin/keys").text
    rows = _tbody_rows(html)
    assert len(rows) == 1, rows
    assert "data-no-sort" in rows[0], rows[0]
    assert 'colspan="13"' in rows[0], rows[0]
    assert "No gateway keys found." in rows[0]
    # The empty state is never numbered and never carries an ordinal cell.
    assert "row-ordinal" not in rows[0]


def test_keys_list_one_and_many_rows_render_ssrd_ordinals(monkeypatch) -> None:
    client = _client(monkeypatch, [_key(), _key(), _key()])
    html = client.get("/admin/keys").text

    # Grouped thead: plain group row + complete leaf row (13 columns 1:1
    # with the body cells), first leaf header plain ordinal.
    thead = html[html.index("<thead>") : html.index("</thead>")]
    assert '<tr class="group-row">' in thead
    assert "Key details" in thead and ">Usage<" in thead and ">Quotas<" in thead
    leaf_rows = re.findall(r"<tr\b[^>]*>.*?</tr>", thead, flags=re.DOTALL)
    assert len(leaf_rows) == 2, thead
    leaf = leaf_rows[-1]
    leaf_ths = re.findall(r"<th\b[^>]*>", leaf)
    assert len(leaf_ths) == 13, leaf_ths
    assert "data-ordinal" in leaf_ths[0], leaf_ths[0]
    # The ordinal header is plain: no sort-type, no explicit mapping.
    assert "data-sort-type" not in leaf_ths[0]
    assert "data-col" not in thead

    rows = _tbody_rows(html)
    assert len(rows) == 3
    for i, row in enumerate(rows):
        tds = re.findall(r"<td\b[^>]*>.*?(?=<td\b|$)", row, flags=re.DOTALL)
        assert 'class="row-ordinal"' in tds[0], tds[0]
        assert re.match(rf"<td class=\"row-ordinal\">{i + 1}</td>\s*$", tds[0]), tds[0]

    one = _client(monkeypatch, [_key()])
    rows_one = _tbody_rows(one.get("/admin/keys").text)
    assert len(rows_one) == 1
    assert '<td class="row-ordinal">1</td>' in rows_one[0]


def test_keys_list_split_metric_cells_use_typed_raw_keys(monkeypatch) -> None:
    zeroed = _key(
        requests_used_total=0,
        tokens_used_total=0,
        cost_used_eur=Decimal("0"),
        request_limit_total=None,
        token_limit_total=None,
        cost_limit_eur=None,
    )
    populated = _key(
        requests_used_total=7,
        tokens_used_total=123,
        cost_used_eur=Decimal("2.500000000"),
        request_limit_total=900,
        token_limit_total=1500,
        cost_limit_eur=Decimal("100.000000000"),
    )
    client = _client(monkeypatch, [zeroed, populated])
    html = client.get("/admin/keys").text
    rows = _tbody_rows(html)

    def cell(row: str, index: int) -> str:
        # The index-th <td> block of the row (1-based).
        return re.findall(r"<td\b[^>]*>.*?(?=<td\b|$)", row, flags=re.DOTALL)[index - 1]

    def text(cell_html: str) -> str:
        return re.sub(r"<[^>]+>", "", cell_html).strip()

    # Usage cells: 0 displays "0" (a faithful actual zero, never
    # "Unlimited") with a typed raw key; the populated row shows the
    # decimal-rendered money value with the dec-filtered raw key.
    assert text(cell(rows[0], 8)) == "0"
    assert 'data-sort-value="0"' in cell(rows[0], 8)
    assert text(cell(rows[1], 8)) == "7"
    assert 'data-sort-value="7"' in cell(rows[1], 8)
    # 206-a: token readouts display millions (exact count stays in the
    # raw sort key and the title); the grouped money display keeps the
    # canonical ungrouped raw key.
    assert text(cell(rows[1], 9)) == "0.000123M"
    assert 'data-sort-value="123"' in cell(rows[1], 9)
    assert 'title="123"' in cell(rows[1], 9), cell(rows[1], 9)
    assert text(cell(rows[1], 10)) == "2.5", cell(rows[1], 10)
    assert 'data-sort-value="2.5"' in cell(rows[1], 10), cell(rows[1], 10)

    # Quota cells: None displays "Unlimited" with an EMPTY raw key (the
    # fixed script sorts it as missing, last in both directions); set
    # limits render their typed raw values.
    assert text(cell(rows[0], 11)) == "Unlimited"
    assert 'data-sort-value=""' in cell(rows[0], 11), cell(rows[0], 11)
    assert text(cell(rows[0], 12)) == "Unlimited"
    assert 'data-sort-value=""' in cell(rows[0], 12)
    assert text(cell(rows[1], 11)) == "900"
    assert 'data-sort-value="900"' in cell(rows[1], 11)
    # 206-a: token limit displays millions with the exact raw key/title.
    assert text(cell(rows[1], 12)) == "0.0015M"
    assert 'data-sort-value="1500"' in cell(rows[1], 12)
    assert 'title="1,500"' in cell(rows[1], 12), cell(rows[1], 12)
    assert text(cell(rows[1], 13)) == "100"
    assert 'data-sort-value="100"' in cell(rows[1], 13)


def test_keys_list_rows_selector_binds_to_filter_form(monkeypatch) -> None:
    client = _client(monkeypatch, [_key(), _key()])

    html = client.get("/admin/keys").text
    # Visible Rows selector: presets, bound to the GET filter form.
    assert '<select name="limit" id="keys-limit" form="keys-filter">' in html
    for preset in ("10", "25", "50", "100", "200"):
        assert f'<option value="{preset}"' in html
    assert '<option value="50" selected>50</option>' in html
    # No duplicate hidden limit field anywhere on the page.
    assert '<input type="hidden" name="limit"' not in html
    assert html.count('name="limit"') == 1
    # Displayed-row count text is the real rendered length.
    assert "2 rows shown" in html

    # A custom valid limit outside the presets is preserved as an
    # explicit selected option (not reset to a preset).
    custom = client.get("/admin/keys?limit=37").text
    assert '<option value="37" selected>37 (current)</option>' in custom
    assert '<option value="50" selected>' not in custom

# ---------------------------------------------------------------------------
# R6: the eleven GET-limit lists and their visible Rows selectors
# ---------------------------------------------------------------------------

TEMPLATES = Path(__file__).resolve().parents[2] / "app" / "slaif_gateway" / "web" / "templates"

# (template, filter form id, displayed-collection variable, GET route action,
#  has a SEPARATE CSV-export form with its own limit input)
ROWS_SELECTOR_PAGES = (
    ("owners/list.html", "owners-filter", "owners", "/admin/owners", False),
    ("institutions/list.html", "institutions-filter", "institutions", "/admin/institutions", False),
    ("cohorts/list.html", "cohorts-filter", "cohorts", "/admin/cohorts", False),
    ("providers/list.html", "providers-filter", "providers", "/admin/providers", False),
    ("routes/list.html", "routes-filter", "routes", "/admin/routes", False),
    ("pricing/list.html", "pricing-filter", "pricing_rules", "/admin/pricing", False),
    ("fx/list.html", "fx-filter", "fx_rates", "/admin/fx", False),
    ("usage/list.html", "usage-filter", "usage_rows", "/admin/usage", True),
    ("audit/list.html", "audit-filter", "audit_logs", "/admin/audit", True),
    ("email_deliveries/list.html", "email-deliveries-filter", "email_deliveries", "/admin/email-deliveries", False),
    ("keys/list.html", "keys-filter", "keys", "/admin/keys", False),
)


def test_all_eleven_get_limit_lists_have_bound_rows_selectors() -> None:
    """194-a R6 source law: EXACTLY the 11 GET-limit lists carry the
    visible Rows selector, and every one is correctly wired:

    - a GET filter form whose id matches the select's ``form`` attribute
      (form association, not a stray input);
    - the presets 10/25/50/100/200 plus the preserved ``N (current)``
      custom-limit option;
    - the displayed-row count is the REAL ``{{ <collection>|length }}``
      interpolation (this pins the 10-page literal-count bug class: a
      forgotten ``{{ }}`` renders the marker text, not a number);
    - no hidden duplicate limit field; the usage/audit CSV export forms
      keep their SEPARATE (visible, POST-form) limit input only.

    These controls are bounded numeric preset/custom selectors over the
    existing GET page limit — they are NOT database reference pickers
    and are classified separately from the 102-field known-reference
    inventory. The keys page is additionally real-rendered by
    ``test_keys_list_rows_selector_binds_to_filter_form`` and by the
    browser tests (custom limit 37 preserved).
    """
    problems: list[str] = []
    for template, form_id, var, action, has_export in ROWS_SELECTOR_PAGES:
        src = (TEMPLATES / template).read_text(encoding="utf-8")
        form = re.search(r"<form\b[^>]*id=\"" + re.escape(form_id) + r"\"[^>]*>", src, flags=re.DOTALL)
        if form is None or 'method="get"' not in form.group(0) or f'action="{action}"' not in form.group(0):
            problems.append(f"{template}: GET filter form {form_id!r} missing or misconfigured")
        select = re.search(r"<select\b[^>]*name=\"limit\"[^>]*>", src, flags=re.DOTALL)
        if select is None or f'form="{form_id}"' not in select.group(0):
            problems.append(f"{template}: limit select missing or not bound to {form_id!r}")
        elif 'id="' + form_id.split("-")[0] + '-limit"' not in select.group(0):
            problems.append(f"{template}: limit select lost its id: {select.group(0)}")
        if "(10, 25, 50, 100, 200)" not in src:
            problems.append(f"{template}: preset loop missing")
        if "{{ filters.limit }} (current)" not in src:
            problems.append(f"{template}: custom-current option missing")
        if "{{ " + var + "|length }} rows shown" not in src:
            problems.append(f"{template}: displayed count is not the real {{{var}|length}} interpolation")
        limit_inputs = re.findall(r"<input\b[^>]*name=\"limit\"[^>]*>", src, flags=re.DOTALL)
        if any('type="hidden"' in i for i in limit_inputs):
            problems.append(f"{template}: hidden duplicate limit field reintroduced")
        if len(limit_inputs) != (1 if has_export else 0):
            problems.append(f"{template}: expected {1 if has_export else 0} separate limit input(s), got {len(limit_inputs)}")
    assert problems == [], problems

    # Exactly these 11 routes accept the GET page limit (no new
    # query/pagination framework; the CSV export limits are separate
    # Form fields, not Query params).
    admin_src = (
        Path(__file__).resolve().parents[2] / "app" / "slaif_gateway" / "api" / "admin.py"
    ).read_text(encoding="utf-8")
    assert admin_src.count("limit: int = Query(") == len(ROWS_SELECTOR_PAGES)
