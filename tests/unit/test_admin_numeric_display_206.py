"""206-a admin numeric display contract.

Locale-stable, grouped, dot-decimal, exponent-free human readouts with
token quantities in millions (exact counts preserved in raw sort keys
and title/accessibility text), while machine-facing surfaces (sort
values, editable inputs, payloads) keep exact raw units. Covers the
pure formatter matrix and real template renders through the ASGI app
with the existing unit fake-session seams (keys list/detail, usage
detail, pricing list).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_activity import (
    AdminUsageDetail,
    AdminUsageListRow,
)
from slaif_gateway.schemas.admin_keys import AdminKeyDetail
from slaif_gateway.schemas.admin_catalog import (
    AdminPricingRuleDetail,
    AdminPricingRuleListRow,
)
from slaif_gateway.services.admin_session_service import AdminSessionContext
from slaif_gateway.web.formatting import (
    format_input_decimal,
    format_number,
    format_raw_decimal,
    format_tokens_m,
)

from test_admin_table_rows_194 import _client as keys_client
from test_admin_table_rows_194 import _key
from test_admin_table_rows_194 import _tbody_rows


# ---------------------------------------------------------------------------
# Pure formatter matrix
# ---------------------------------------------------------------------------


class TestFormatNumber:
    def test_exponent_zeroes_render_plain_zero(self) -> None:
        assert format_number(Decimal("0E-9")) == "0"
        assert format_number(Decimal("-0E-9")) == "0"
        assert format_number("0E-9") == "0"
        assert format_number("-0E-9") == "0"
        assert format_number(Decimal("-0.000000001")) == "-0.000000001"

    def test_true_one_e9_is_not_zero(self) -> None:
        assert format_number(Decimal("1E-9")) == "0.000000001"
        assert format_number(-Decimal("1E-9")) == "-0.000000001"

    def test_grouped_money_and_counts(self) -> None:
        assert format_number(937826734) == "937,826,734"
        assert format_number(Decimal("2.500000000")) == "2.5"
        assert format_number(Decimal("100.000000000")) == "100"
        assert format_number(Decimal("-1234567.890000000")) == "-1,234,567.89"
        assert format_number(1_000_000) == "1,000,000"
        assert format_number(10) == "10"
        assert format_number(0) == "0"

    def test_exact_64_bit_integers_no_float_roundtrip(self) -> None:
        assert format_number(2**53 + 1) == "9,007,199,254,740,993"
        assert format_number(2**63 - 1) == "9,223,372,036,854,775,807"
        assert format_number("-9223372036854775807") == "-9,223,372,036,854,775,807"

    def test_numeric_strings_render_exactly(self) -> None:
        assert format_number("10.00") == "10"
        assert format_number(" 7 ") == "7"
        assert format_number("937826734") == "937,826,734"

    def test_none_stays_none_for_template_labels(self) -> None:
        assert format_number(None) is None

    def test_non_quantities_pass_through_untouched(self) -> None:
        assert format_number("gpt-5.6-sol") == "gpt-5.6-sol"
        assert format_number("/v1/chat/completions") == "/v1/chat/completions"
        assert format_number("127.0.0.1") == "127.0.0.1"
        assert format_number(True) == "True"
        assert format_number(1.5) == "1.5"


class TestFormatTokensM:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, None),
            (0, "0"),
            (Decimal("0E-9"), "0"),
            (1, "0.000001"),
            (1000, "0.001"),
            (999999, "0.999999"),
            (1_000_000, "1"),
            (1_500_000, "1.5"),
            (937826734, "937.827"),
            (937826700, "937.827"),
            (937826749, "937.827"),
            # rounding boundary: 999,999,500 -> 999.9995 -> 1000 (half-up),
            # magnitude part still comma-grouped
            (999999500, "1,000"),
            (999999499, "999.999"),
            (-2_000_000, "-2"),
        ],
    )
    def test_m_conversion(self, value, expected) -> None:
        assert format_tokens_m(value) == expected

    def test_no_positive_value_rounds_to_zero(self) -> None:
        for value in (1, 10, 100, 999):
            assert format_tokens_m(value) not in ("0", "0.000")
        assert format_tokens_m(1) == "0.000001"

    def test_large_grouped_magnitude(self) -> None:
        assert format_tokens_m(1_234_567_890_123) == "1,234,567.89"

    def test_non_quantities_pass_through(self) -> None:
        assert format_tokens_m("n/a") == "n/a"


class TestFormatRawDecimal:
    def test_canonical_ungrouped_exact(self) -> None:
        assert format_raw_decimal(Decimal("0E-9")) == "0"
        assert format_raw_decimal(Decimal("-0E-9")) == "0"
        assert format_raw_decimal(Decimal("2.500000000")) == "2.5"
        assert format_raw_decimal(937826734) == "937826734"
        assert format_raw_decimal("0E-9") == "0"
        assert format_raw_decimal(None) is None
        assert format_raw_decimal(2**63 - 1) == "9223372036854775807"

    def test_never_groups_or_scales(self) -> None:
        assert "," not in format_raw_decimal(937826734)
        assert format_raw_decimal(Decimal("0.010000000")) == "0.01"


class TestFormatInputDecimal:
    def test_quantized_zero_renders_zero(self) -> None:
        assert format_input_decimal(Decimal("0E-9")) == "0"
        assert format_input_decimal(Decimal("-0E-9")) == "0"

    def test_zero_value_numeric_strings_render_zero(self) -> None:
        # Zero-valued valid numeric defaults (any representation) render
        # the plain 0: same value, same units, still a valid input.
        assert format_input_decimal("0E-9") == "0"
        assert format_input_decimal("-0E-9") == "0"
        assert format_input_decimal("0.000000000") == "0"
        assert format_input_decimal(" 0 ") == "0"
        assert format_input_decimal("0") == "0"

    def test_nonzero_keeps_exact_fixed_digits(self) -> None:
        assert format_input_decimal(Decimal("0.010000000")) == "0.010000000"
        assert format_input_decimal(Decimal("-1.500000000")) == "-1.500000000"
        assert format_input_decimal(Decimal("0")) == "0"

    def test_user_strings_pass_through_unchanged(self) -> None:
        # Redisplayed user input (valid or invalid) is never rewritten:
        # editable controls keep exact raw units and reject nothing here.
        assert format_input_decimal("1.5") == "1.5"
        assert format_input_decimal("abc") == "abc"
        assert format_input_decimal("  2.0") == "  2.0"
        assert format_input_decimal("") == ""
        assert format_input_decimal(None) is None


# ---------------------------------------------------------------------------
# Shared ASGI seams (unit fake session; no DB, no server)
# ---------------------------------------------------------------------------


class _FakeResult:
    def all(self):
        return []

    def first(self):
        return None

    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def begin(self):
        return self

    async def execute(self, *args, **kwargs):
        return _FakeResult()


class _FakeSessionmaker:
    def __call__(self):
        return _FakeSession()


def _login(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = create_app(
        Settings(
            APP_ENV="test",
            DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
            ADMIN_SESSION_SECRET="s" * 40,
            OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
            OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
        )
    )
    app.state.db_sessionmaker = _FakeSessionmaker()

    admin_user = AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="password-hash-never-render",
        role="admin",
        is_active=True,
    )
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="session-hash-never-render",
        csrf_token_hash="csrf-hash-never-render",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "rendered-csrf-token"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    client = TestClient(app)
    client.cookies.set("slaif_admin_session", "206-display-session")
    return client


def _cell(row_html: str, index: int) -> str:
    return re.findall(r"<td\b[^>]*>.*?(?=<td\b|$)", row_html, flags=re.DOTALL)[index - 1]


def _text(cell_html: str) -> str:
    return re.sub(r"<[^>]+>", "", cell_html).strip()


def _detail_key(**overrides) -> AdminKeyDetail:
    base = _key()
    return replace(base, **overrides) if overrides else base


# ---------------------------------------------------------------------------
# Keys list (reuses the 194 seam)
# ---------------------------------------------------------------------------


def test_keys_list_grouped_millions_and_exponent_zero(monkeypatch) -> None:
    big = _key(
        requests_used_total=937826734,
        tokens_used_total=937826734,
        cost_used_eur=Decimal("0E-9"),
        token_limit_total=999999500,
        request_limit_total=None,
    )
    small = _key(
        requests_used_total=7,
        tokens_used_total=1,
        cost_used_eur=Decimal("1E-9"),
        token_limit_total=1500,
        request_limit_total=900,
    )
    client = keys_client(monkeypatch, [big, small])
    html = client.get("/admin/keys").text
    rows = _tbody_rows(html)

    # Requests grouped; raw sort key unscaled and ungrouped.
    assert _text(_cell(rows[0], 8)) == "937,826,734"
    assert 'data-sort-value="937826734"' in _cell(rows[0], 8)
    # Tokens in M with the exact grouped count in the title.
    assert _text(_cell(rows[0], 9)) == "937.827M"
    assert 'data-sort-value="937826734"' in _cell(rows[0], 9)
    assert 'title="937,826,734"' in _cell(rows[0], 9)
    # A stored 9-dp zero cost renders 0 (never 0E-9, never hidden).
    assert _text(_cell(rows[0], 10)) == "0"
    assert 'data-sort-value="0"' in _cell(rows[0], 10)
    # Rounding boundary: 999,999,500 tokens -> 1,000M, exact count in title.
    assert _text(_cell(rows[0], 12)) == "1,000M"
    assert 'data-sort-value="999999500"' in _cell(rows[0], 12)
    assert 'title="999,999,500"' in _cell(rows[0], 12)
    # Missing limits keep their labels with an empty raw key.
    assert _text(_cell(rows[0], 11)) == "Unlimited"
    assert 'data-sort-value=""' in _cell(rows[0], 11)

    # The tiny true positive price 1E-9 is never displayed as free zero.
    assert _text(_cell(rows[1], 10)) == "0.000000001"
    assert _text(_cell(rows[1], 9)) == "0.000001M"
    assert 'data-sort-value="1"' in _cell(rows[1], 9)
    assert _text(_cell(rows[1], 12)) == "0.0015M"


# ---------------------------------------------------------------------------
# Keys detail: live-burn exponent zero + raw editable input
# ---------------------------------------------------------------------------


def test_keys_detail_live_burn_zero_readout_and_raw_input(monkeypatch) -> None:
    client = _login(monkeypatch)
    key = _detail_key(
        chat_streaming_live_burn_policy={
            "version": 1,
            "enabled": True,
            "cost_margin_eur": Decimal("0E-9"),
            "token_margin": 0,
        }
    )

    async def get_key_detail(self, gateway_key_id):
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    html = client.get(f"/admin/keys/{key.id}").text

    # Readout: the exponent zero is readable; the editable input keeps
    # the same valid raw value (0, not 0E-9) in the same units.
    assert "0E-9" not in html
    assert re.search(r"Cost margin EUR</dt>\s*<dd>0</dd>", html)
    assert 'name="chat_streaming_live_burn_cost_margin_eur" value="0"' in html


def test_keys_detail_live_burn_positive_margin_not_zeroed(monkeypatch) -> None:
    client = _login(monkeypatch)
    key = _detail_key(
        chat_streaming_live_burn_policy={
            "version": 1,
            "enabled": True,
            "cost_margin_eur": Decimal("1E-9"),
            "token_margin": 5,
        }
    )

    async def get_key_detail(self, gateway_key_id):
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    html = client.get(f"/admin/keys/{key.id}").text
    assert "0.000000001" in html
    assert 'value="0.000000001"' in html


# ---------------------------------------------------------------------------
# Usage detail: actual-zero preference, estimate fallback, n/a
# ---------------------------------------------------------------------------


def _usage(**overrides) -> AdminUsageDetail:
    base = AdminUsageListRow(
        id=uuid.uuid4(),
        request_id="req-206",
        gateway_key_id=uuid.uuid4(),
        key_public_id="pub-206",
        owner_id=None,
        owner_display_name=None,
        institution_id=None,
        cohort_id=None,
        endpoint="/v1/chat/completions",
        provider="openai",
        requested_model="gpt-test",
        resolved_model="gpt-test",
        streaming=False,
        success=True,
        accounting_status="finalized",
        http_status=200,
        prompt_tokens=937826734,
        completion_tokens=0,
        total_tokens=937826734,
        cached_tokens=0,
        reasoning_tokens=0,
        estimated_cost_eur=Decimal("7.750000000"),
        actual_cost_eur=Decimal("0E-9"),
        native_currency="EUR",
        latency_ms=20,
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        chat_live_burn=None,
    )
    row = replace(base, **overrides) if overrides else base
    return AdminUsageDetail(
        **asdict(row),
        client_request_id=None,
        quota_reservation_id=None,
        upstream_request_id=None,
        error_type=None,
        error_message=None,
        usage_summary='{"safe_counter": 1}',
        response_metadata_summary='{"safe": "safe"}',
    )


def _usage_page(monkeypatch, usage: AdminUsageDetail) -> str:
    client = _login(monkeypatch)

    async def get_usage_detail(self, usage_ledger_id):
        return usage

    monkeypatch.setattr(
        "slaif_gateway.services.admin_activity_dashboard.AdminActivityDashboardService.get_usage_detail",
        get_usage_detail,
    )
    return client.get(f"/admin/usage/{usage.id}").text


def test_usage_detail_actual_zero_cost_in_preference_to_estimate(monkeypatch) -> None:
    usage = _usage()
    page = _usage_page(monkeypatch, usage)

    # A present actual zero is displayed (not the estimate, not n/a).
    assert re.search(r"Cost EUR</dt><dd>0</dd>", page)
    assert "7.75" not in page
    # Token readouts in M with the exact grouped count in the title.
    assert 'title="937,826,734 tokens"' in page
    assert "937.827M" in page
    assert "0M" in page


def test_usage_detail_estimate_only_falls_back(monkeypatch) -> None:
    usage = _usage(actual_cost_eur=None)
    page = _usage_page(monkeypatch, usage)
    assert re.search(r"Cost EUR</dt><dd>7.75</dd>", page)


def test_usage_detail_neither_cost_is_na(monkeypatch) -> None:
    usage = _usage(actual_cost_eur=None, estimated_cost_eur=None)
    page = _usage_page(monkeypatch, usage)
    assert re.search(r"Cost EUR</dt><dd>n/a</dd>", page)


# ---------------------------------------------------------------------------
# Pricing list: 9-dp money readouts, zero, and missing labels
# ---------------------------------------------------------------------------


def _pricing_rule(**overrides) -> AdminPricingRuleDetail:
    base = AdminPricingRuleListRow(
        id=uuid.uuid4(),
        provider="openai",
        upstream_model="gpt-test",
        endpoint="/v1/chat/completions",
        currency="EUR",
        input_price_per_1m=Decimal("0.010000000"),
        cached_input_price_per_1m=None,
        output_price_per_1m=Decimal("0E-9"),
        reasoning_price_per_1m=None,
        request_price=None,
        enabled=True,
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_until=None,
        source_url=None,
        notes=None,
        pricing_metadata={},
        metadata_summary="None",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    row = replace(base, **overrides) if overrides else base
    return AdminPricingRuleDetail(**asdict(row), provider_config=None)


def test_pricing_list_money_display_zero_and_missing(monkeypatch) -> None:
    priced = _pricing_rule()
    missing = _pricing_rule(input_price_per_1m=None)
    client = _login(monkeypatch)

    async def list_pricing_rules(self, **kwargs):
        return [priced, missing]

    monkeypatch.setattr(
        "slaif_gateway.services.admin_catalog_dashboard.AdminCatalogDashboardService.list_pricing_rules",
        list_pricing_rules,
    )
    html = client.get("/admin/pricing").text

    # 9-dp money renders without padded zeros; a stored zero renders 0;
    # missing fields keep the n/a label; the raw sort key is canonical
    # and ungrouped (machine-facing, intentionally unformatted).
    assert "<div>input 0.01</div>" in html
    assert ">output 0</div>" in html
    assert "<div>input n/a</div>" in html
    assert "0E-9" not in html
    assert 'data-sort-value="0.010000000"' in html
