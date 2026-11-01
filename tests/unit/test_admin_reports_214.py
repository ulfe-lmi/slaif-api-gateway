"""214-a GUI reports and reviewed catalog tools (unit).

Fake-persistence ASGI/Jinja seams over the real admin app for router
logic (the shared services are faked only where a test needs router
behavior; the REAL shared strict plan schemas, the real HMAC
review-intent build/verify, the real pagination helpers, the real
cost-availability projection, and the real report-service bound law
run unpatched):

- pagination helper: cap+1 has_more honesty, continuing ordinals,
  allowlisted repeated-value navigation URLs;
- report service: cap+1 source-bound refusal (never a silent prefix),
  additive cost-availability projection (known zero vs all-missing vs
  partial), the stable grouping-key final tie-break on the new GUI
  result only, and the UNCHANGED CLI UsageSummaryRow JSON field set;
- reviewed pricing disable: SQL-bounded preview (no-match / overbound
  / exact), the fingerprint law (policy metadata bound; notes/
  updated_at/source_url/enabled deliberately not bound), apply
  all-enabled with the verbatim per-row audit reason, the honest
  repeat no-op, mixed/new/missing member staleness on both paths, and
  late-audit-failure propagation (caller transaction rolls back);
- compact signed plan: strict closed document, duplicate/count/cap/
  fingerprint-format refusals, the plan-self 128KiB byte gate SEPARATE
  from the wrapper envelope, purpose-bound actor/session tokens;
- safe JSON export DTO: exact raw machine units (Decimal exact
  string, UUID string, datetime ISO; no Decimal->float) and strict
  no-NaN serialization;
- router: auth/dashboard gates, validation 400s with direct safe
  report recovery links (no raw echo), source-bound and alias
  refusals, export confirm/reason/ceiling law, pricing preview/apply
  boundary behavior, FX missing/present states.

No database, no network, no credential loading. The native PG module
proves the real transaction/audit/preservation law; the browser module
proves the real operator flow.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse

from slaif_gateway.api import admin_reports
from slaif_gateway.api.admin_review_intent import (
    AdminReviewIntentError,
    REVIEW_INTENT_TTL_SECONDS,
    build_pricing_review_token,
    build_replay_review_token,
    verify_pricing_review_token,
    verify_replay_review_token,
)
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.schemas.key_configuration import (
    MAX_KEY_CONFIGURATION_REASON_LENGTH,
)
from slaif_gateway.schemas.usage import UsageExportRow, UsageReportFilters
from slaif_gateway.services.admin_session_service import AdminSessionContext
from slaif_gateway.services.pricing_rule_service import (
    PRICING_DISABLE_MAX_REVIEWED_ROWS,
    PRICING_DISABLE_PLAN_MAX_BYTES,
    PricingDisableApplyResult,
    PricingDisableDisplayRow,
    PricingDisableNoMatchError,
    PricingDisablePlan,
    PricingDisableReviewRow,
    PricingDisableScopeError,
    PricingDisableStaleError,
    PricingRuleService,
    parse_pricing_disable_plan_document,
    render_pricing_disable_plan,
)
from slaif_gateway.services.record_errors import RecordNotFoundError
from slaif_gateway.services.usage_report_service import (
    UsageReportService,
    UsageReportSourceBoundError,
)
from slaif_gateway.utils.admin_pagination import (
    MAX_ADMIN_PAGE_LIMIT,
    build_navigation_url,
    build_page,
    page_params,
)
from tests.unit.test_admin_key_actions_routes import _app, _settings

GUI_USAGE_REPORT_SOURCE_MAX_ROWS = admin_reports.GUI_USAGE_REPORT_SOURCE_MAX_ROWS

ADMIN_ID = uuid.UUID("aaaaaaaa-1000-4000-8000-000000000001")
OTHER_ADMIN_ID = uuid.UUID("99999999-1000-4000-8000-000000000009")
SESSION_ID = uuid.UUID("bbbbbbbb-1000-4000-8000-000000000002")
OTHER_SESSION_ID = uuid.UUID("88888888-1000-4000-8000-000000000008")
CSRF = "reports-csrf"
BASE = "/admin/reports"

# Accepted-prefix canary: starts with the default gateway-key prefix,
# so the REAL alias discovery flags it without any patching.
PREFIX_CANARY = "sk-slaif-canary-opaque"


def _now() -> datetime:
    return datetime.now(UTC)


def _admin_user() -> AdminUser:
    return AdminUser(
        id=ADMIN_ID,
        email="admin@example.org",
        display_name="Admin User",
        password_hash="argon2-hash",
        role="admin",
        is_active=True,
    )


def _admin_session(admin_user: AdminUser) -> AdminSession:
    session = AdminSession(
        id=SESSION_ID,
        admin_user_id=admin_user.id,
        session_token_hash="sha256:session",
        csrf_token_hash="sha256:csrf",
        expires_at=_now() + timedelta(hours=1),
    )
    session.admin_user = admin_user
    return session


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    app = _app(_settings())
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(
            admin_user=admin_user, admin_session=admin_session
        )

    def verify_session_csrf_token(self, admin_session, csrf_token):
        return csrf_token == CSRF

    async def refresh_csrf_token(self, admin_session_id=None):
        return CSRF

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        verify_session_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    test_client = TestClient(app)
    test_client.cookies.set("slaif_admin_session", "session-plaintext")
    return test_client


# ----------------------------------------------------------------------
# shared pagination helper
# ----------------------------------------------------------------------


def test_build_page_cap_plus_one_honesty() -> None:
    # A full page alone is NOT has_more.
    page = build_page(page_size=50, offset=0, row_count=50)
    assert page.has_more is False
    assert page.can_prev is False
    assert page.first_ordinal == 1
    # An overflow row fetched by cap+1 IS has_more.
    page = build_page(page_size=50, offset=0, row_count=51)
    assert page.has_more is True
    # Continuing ordinals across pages; prev/next offsets.
    page = build_page(page_size=25, offset=25, row_count=26)
    assert page.first_ordinal == 26
    assert page.can_prev is True
    assert page.prev_offset == 0
    assert page.next_offset == 50


def test_navigation_url_allowlisted_repeated_values() -> None:
    filters = [
        ("cohort_id", str(uuid.uuid4())),
        ("cohort_id", str(uuid.uuid4())),
        ("provider", "open router"),
    ]
    url = build_navigation_url(
        BASE + "/", page_params(limit=50, offset=25, filters=filters)
    )
    assert url.startswith(BASE + "/?")
    # Repeated values preserved in order; spaces percent-encoded.
    assert url.count("cohort_id=") == 2
    assert "provider=open+router" in url
    assert "limit=50" in url
    assert "offset=25" in url
    # No filters: bare base path.
    assert build_navigation_url(BASE + "/", page_params(limit=10, offset=0, filters=[])) == (
        f"{BASE}/?limit=10&offset=0"
    )


# ----------------------------------------------------------------------
# report service seams (real service, fake repository)
# ----------------------------------------------------------------------


def _ledger_row(
    *,
    provider: str = "prov-a",
    model: str = "model-a",
    success: bool | None = True,
    estimated: Decimal | None = Decimal("1.5"),
    actual: Decimal | None = None,
    created_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        provider=provider,
        requested_model=model,
        resolved_model=model,
        endpoint="/v1/chat/completions",
        streaming=True,
        success=success,
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        cached_tokens=0,
        reasoning_tokens=0,
        estimated_cost_eur=estimated,
        actual_cost_eur=actual,
        created_at=created_at or _now(),
        owner_id=None,
        cohort_id=None,
        cohort_name_snapshot=None,
        gateway_key_id=uuid.uuid4(),
        response_metadata=metadata,
    )


class _FakeUsageRepo:
    def __init__(self, rows: list[SimpleNamespace]):
        self.rows = rows
        self.limit_seen: int | None = None

    async def list_usage_records(self, *, limit: int | None = None, **kwargs):
        self.limit_seen = limit
        return list(self.rows[:limit]) if limit is not None else list(self.rows)


def test_report_source_bound_cap_plus_one_refusal() -> None:
    repo = _FakeUsageRepo([_ledger_row() for _ in range(4)])
    service = UsageReportService(usage_ledger_repository=repo)  # type: ignore[arg-type]
    # cap+1 fetch: bound 3 fetches 4.
    with pytest.raises(UsageReportSourceBoundError) as excinfo:
        import asyncio

        asyncio.run(
            service.summarize_usage_report(
                filters=UsageReportFilters(),
                group_by="provider",
                limit=None,
                max_source_rows=3,
            )
        )
    assert excinfo.value.matched_rows == 4
    assert excinfo.value.source_bound == 3
    assert repo.limit_seen == 4
    # Exactly the bound is accepted (no racing count).
    import asyncio

    report = asyncio.run(
        service.summarize_usage_report(
            filters=UsageReportFilters(),
            group_by="provider",
            limit=None,
            max_source_rows=4,
        )
    )
    assert report.source_row_count == 4


def test_report_availability_and_tiebreak() -> None:
    import asyncio

    now = _now()
    rows = [
        # group A: known zero for BOTH estimated and actual (all rows known,
        # coerced sums stay zero)
        _ledger_row(provider="prov-a", model="m1", estimated=Decimal("0"), actual=Decimal("0"), created_at=now),
        _ledger_row(provider="prov-a", model="m2", estimated=Decimal("0"), actual=Decimal("0"), created_at=now),
        # group B: all missing for BOTH
        _ledger_row(provider="prov-b", model="m1", estimated=None, actual=None, created_at=now),
        # group C: mixed for BOTH, with distinct known sums
        _ledger_row(provider="prov-c", model="m1", estimated=Decimal("2"), actual=Decimal("5"), created_at=now),
        _ledger_row(provider="prov-c", model="m2", estimated=None, actual=None, created_at=now),
    ]
    repo = _FakeUsageRepo(rows)
    service = UsageReportService(usage_ledger_repository=repo)  # type: ignore[arg-type]
    report = asyncio.run(
        service.summarize_usage_report(
            filters=UsageReportFilters(),
            group_by="provider",
            limit=None,
            max_source_rows=5,
        )
    )
    assert report.source_row_count == 5
    by_key = {row.grouping_key: row for row in report.rows}
    avail = {a.grouping_key: a for a in report.availability}
    # known zero: known==total for both fields, coerced sum stays zero
    assert by_key["prov-a"].estimated_cost_eur == Decimal("0")
    assert by_key["prov-a"].actual_cost_eur == Decimal("0")
    assert avail["prov-a"].row_count == 2
    assert avail["prov-a"].estimated_cost_known_count == 2
    assert avail["prov-a"].estimated_cost_missing_count == 0
    assert avail["prov-a"].actual_cost_known_count == 2
    assert avail["prov-a"].actual_cost_missing_count == 0
    # all missing: missing==total for both fields, sums coerce to zero
    assert by_key["prov-b"].estimated_cost_eur == Decimal("0")
    assert by_key["prov-b"].actual_cost_eur == Decimal("0")
    assert avail["prov-b"].estimated_cost_known_count == 0
    assert avail["prov-b"].estimated_cost_missing_count == 1
    assert avail["prov-b"].actual_cost_known_count == 0
    assert avail["prov-b"].actual_cost_missing_count == 1
    # mixed: partial known for both fields, distinct known sums
    assert by_key["prov-c"].estimated_cost_eur == Decimal("2")
    assert by_key["prov-c"].actual_cost_eur == Decimal("5")
    assert avail["prov-c"].estimated_cost_known_count == 1
    assert avail["prov-c"].estimated_cost_missing_count == 1
    assert avail["prov-c"].actual_cost_known_count == 1
    assert avail["prov-c"].actual_cost_missing_count == 1


def test_report_grouping_key_final_tiebreak() -> None:
    import asyncio

    now = _now()
    # Two groups with identical request_count and last_seen_at: the
    # grouping key is the deterministic final tie-break.
    rows = [
        _ledger_row(provider="zzz", model="m", created_at=now),
        _ledger_row(provider="aaa", model="m", created_at=now),
    ]
    repo = _FakeUsageRepo(rows)
    service = UsageReportService(usage_ledger_repository=repo)  # type: ignore[arg-type]
    report = asyncio.run(
        service.summarize_usage_report(
            filters=UsageReportFilters(), group_by="provider", limit=None
        )
    )
    keys = [row.grouping_key for row in report.rows]
    # reverse=True: descending key within the tie -> zzz before aaa
    assert keys == ["zzz", "aaa"]


def test_live_burn_source_bound_cap_plus_one() -> None:
    import asyncio

    rows = [
        _ledger_row(
            metadata={
                "streaming_live_burn_triggered": True,
                "streaming_live_burn_stop_reason": "tokens",
                "estimated_tokens_at_stop": 5,
            }
        )
    ] * 3
    repo = _FakeUsageRepo(rows)
    service = UsageReportService(usage_ledger_repository=repo)  # type: ignore[arg-type]
    with pytest.raises(UsageReportSourceBoundError):
        asyncio.run(
            service.summarize_chat_live_burn(
                filters=UsageReportFilters(), max_source_rows=2
            )
        )


def test_cli_usage_summary_row_json_field_set_unchanged() -> None:
    # The CLI consumes the summarize_usage rows through its real projection
    # (cli/usage.py::_row_dict, dataclasses.asdict); the 214-a additive
    # reporting must NOT change that projection's field set or the CLI's
    # uncapped default fetch path.
    from slaif_gateway.cli.usage import _row_dict

    now = _now()
    rows = [
        _ledger_row(
            provider="prov-a", model="m1",
            estimated=Decimal("1.5"), actual=Decimal("1.5"), created_at=now,
        ),
        _ledger_row(
            provider="prov-a", model="m2",
            estimated=Decimal("2.5"), actual=Decimal("0.5"), created_at=now,
        ),
        _ledger_row(
            provider="prov-b", model="m1",
            success=False, estimated=None, actual=None, created_at=now,
        ),
    ]
    repo = _FakeUsageRepo(rows)
    service = UsageReportService(usage_ledger_repository=repo)  # type: ignore[arg-type]
    import asyncio

    # CLI default path: no max_source_rows cap at all, so the repository
    # fetch must stay unbounded (limit=None).
    cli_rows = asyncio.run(
        service.summarize_usage(
            filters=UsageReportFilters(), group_by="provider", limit=None
        )
    )
    assert repo.limit_seen is None
    projected = [_row_dict(row) for row in cli_rows]
    assert [
        {
            "grouping_key": "prov-a",
            "grouping_label": "prov-a",
            "request_count": 2,
            "success_count": 2,
            "failure_count": 0,
            "prompt_tokens": 20,
            "completion_tokens": 40,
            "total_tokens": 60,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
            "estimated_cost_eur": Decimal("4.0"),
            "actual_cost_eur": Decimal("2.0"),
            "provider_reported_cost": None,
            "first_seen_at": now,
            "last_seen_at": now,
        },
        {
            "grouping_key": "prov-b",
            "grouping_label": "prov-b",
            "request_count": 1,
            "success_count": 0,
            "failure_count": 1,
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
            "estimated_cost_eur": Decimal("0"),
            "actual_cost_eur": Decimal("0"),
            "provider_reported_cost": None,
            "first_seen_at": now,
            "last_seen_at": now,
        },
    ] == projected


# ----------------------------------------------------------------------
# reviewed pricing disable: service seams (real service, fake repos)
# ----------------------------------------------------------------------


def _pricing_row(
    *,
    row_id: uuid.UUID | None = None,
    provider: str = "prov-a",
    model: str = "model-a",
    endpoint: str | None = None,
    currency: str = "USD",
    enabled: bool = True,
    metadata: dict[str, Any] | None = None,
    notes: str = "",
    updated_at: datetime | None = None,
    source_url: str | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    input_price: Decimal = Decimal("1"),
    output_price: Decimal = Decimal("2"),
) -> SimpleNamespace:
    return SimpleNamespace(
        id=row_id or uuid.uuid4(),
        provider=provider,
        upstream_model=model,
        endpoint=endpoint,
        currency=currency,
        enabled=enabled,
        pricing_metadata=metadata,
        notes=notes,
        updated_at=updated_at or _now(),
        source_url=source_url,
        valid_from=valid_from or _now(),
        valid_until=valid_until,
        input_price_per_1m=input_price,
        cached_input_price_per_1m=None,
        output_price_per_1m=output_price,
        reasoning_price_per_1m=None,
        request_price=None,
    )


class _FakePricingRepo:
    def __init__(
        self,
        *,
        enabled_rows: list[SimpleNamespace],
        locked_rows: list[SimpleNamespace] | None = None,
        set_enabled_exc: Exception | None = None,
    ):
        self.enabled_rows = enabled_rows
        self.locked_rows = locked_rows if locked_rows is not None else enabled_rows
        self.set_enabled_exc = set_enabled_exc
        self.disabled: list[uuid.UUID] = []
        self.enabled_limit_seen: int | None = None

    async def list_pricing_rules_for_provider_model(
        self, *, provider, upstream_model, endpoint, enabled_only=True, limit=None
    ):
        self.enabled_limit_seen = limit
        rows = [r for r in self.enabled_rows if r.enabled]
        return list(rows[:limit]) if limit is not None else list(rows)

    async def lock_pricing_rules_for_review(self, row_ids):
        by_id = {r.id: r for r in self.locked_rows}
        return [by_id[rid] for rid in row_ids if rid in by_id]

    async def set_pricing_rule_enabled(self, row_id, *, enabled):
        if self.set_enabled_exc is not None:
            raise self.set_enabled_exc
        self.disabled.append(row_id)
        return True


class _FakeAuditRepo:
    def __init__(self, add_exc: Exception | None = None):
        self.add_exc = add_exc
        self.entries: list[dict[str, Any]] = []

    async def add_audit_log(self, **kwargs):
        if self.add_exc is not None:
            raise self.add_exc
        self.entries.append(kwargs)


def _service(
    pricing: _FakePricingRepo, audit: _FakeAuditRepo
) -> PricingRuleService:
    return PricingRuleService(
        pricing_rules_repository=pricing,  # type: ignore[arg-type]
        audit_repository=audit,  # type: ignore[arg-type]
    )


def test_pricing_preview_no_match_and_overbound() -> None:
    import asyncio

    audit = _FakeAuditRepo()
    empty = _FakePricingRepo(enabled_rows=[])
    service = _service(empty, audit)
    with pytest.raises(PricingDisableNoMatchError):
        asyncio.run(service.preview_disable_model(provider="prov-a", model="model-a"))

    over = _FakePricingRepo(
        enabled_rows=[_pricing_row() for _ in range(4)],
    )
    service = _service(over, audit)
    with pytest.raises(PricingDisableScopeError) as excinfo:
        asyncio.run(
            service.preview_disable_model(
                provider="prov-a", model="model-a", max_rows=3
            )
        )
    assert excinfo.value.matched_rows == 4
    assert excinfo.value.max_rows == 3
    # cap+1 fetch through the existing query
    assert over.enabled_limit_seen == 4


def test_pricing_preview_exact_bounded_plan() -> None:
    import asyncio

    rows = [_pricing_row(row_id=uuid.UUID(int=i + 1)) for i in range(2)]
    rows[0].id = uuid.UUID(int=2)
    rows[1].id = uuid.UUID(int=1)  # stored unordered; plan must sort by id
    repo = _FakePricingRepo(enabled_rows=rows)
    plan = asyncio.run(
        _service(repo, _FakeAuditRepo()).preview_disable_model(
            provider="prov-a", model="model-a"
        )
    )
    assert plan.row_count == 2
    assert [str(r.pricing_rule_id) for r in plan.rows] == [
        str(uuid.UUID(int=1)),
        str(uuid.UUID(int=2)),
    ]
    assert all(len(r.fingerprint) == 64 for r in plan.rows)
    assert len(plan.display_rows) == 2
    assert plan.display_rows[0].provider == "prov-a"


def test_pricing_fingerprint_law() -> None:
    import asyncio

    base = _pricing_row(metadata={"policy": "x"})
    repo = _FakePricingRepo(enabled_rows=[base])
    plan = asyncio.run(
        _service(repo, _FakeAuditRepo()).preview_disable_model(
            provider="prov-a", model="model-a"
        )
    )

    def apply_fresh(row):
        repo2 = _FakePricingRepo(enabled_rows=[row])
        return _service(repo2, _FakeAuditRepo())

    # notes-only drift: NOT stale (notes excluded from the fingerprint)
    drifted = _replace_row(base, notes="edited notes")
    fresh = apply_fresh(drifted)
    _assert_apply_ok(fresh, plan, expect_disabled=1)

    # updated_at/source_url drift: NOT stale
    _assert_apply_ok(
        apply_fresh(_replace_row(base, updated_at=_now() + timedelta(hours=1))),
        plan,
        expect_disabled=1,
    )
    _assert_apply_ok(
        apply_fresh(_replace_row(base, source_url="https://example.org/new")),
        plan,
        expect_disabled=1,
    )
    # enabled flag alone: NOT stale (the repeat law evaluates it under
    # the locks - covered by the repeat no-op test).

    # policy metadata edit: STALE (the policy is bound privately)
    _assert_apply_stale(
        apply_fresh(_replace_row(base, pricing_metadata={"policy": "y"})), plan
    )
    # price/currency/validity edits: STALE
    _assert_apply_stale(
        apply_fresh(_replace_row(base, input_price_per_1m=Decimal("9"))), plan
    )
    _assert_apply_stale(
        apply_fresh(_replace_row(base, currency="EUR")), plan
    )
    _assert_apply_stale(
        apply_fresh(_replace_row(base, valid_until=_now() + timedelta(days=1))),
        plan,
    )
    # missing reviewed row: STALE
    _assert_apply_stale(
        _service(_FakePricingRepo(enabled_rows=[]), _FakeAuditRepo()), plan
    )


def _replace_row(row: SimpleNamespace, **changes) -> SimpleNamespace:
    data = {
        "id": row.id,
        "provider": row.provider,
        "upstream_model": row.upstream_model,
        "endpoint": row.endpoint,
        "currency": row.currency,
        "enabled": row.enabled,
        "pricing_metadata": row.pricing_metadata,
        "notes": row.notes,
        "updated_at": row.updated_at,
        "source_url": row.source_url,
        "valid_from": row.valid_from,
        "valid_until": row.valid_until,
        "input_price_per_1m": row.input_price_per_1m,
        "cached_input_price_per_1m": row.cached_input_price_per_1m,
        "output_price_per_1m": row.output_price_per_1m,
        "reasoning_price_per_1m": row.reasoning_price_per_1m,
        "request_price": row.request_price,
    }
    data.update(changes)
    return SimpleNamespace(**data)


def _assert_apply_ok(
    service: PricingRuleService, plan: PricingDisablePlan, *, expect_disabled: int
) -> None:
    import asyncio

    audit: _FakeAuditRepo = service._audit  # noqa: SLF001 - white-box seam check
    result = asyncio.run(
        service.apply_disable_model_reviewed(
            plan=plan, actor_admin_id=ADMIN_ID, reason="reviewed reason"
        )
    )
    assert result.disabled_count == expect_disabled
    assert result.already_disabled is False
    if expect_disabled:
        assert len(audit.entries) == expect_disabled
    else:
        assert audit.entries == []


def _assert_apply_stale(service: PricingRuleService, plan: PricingDisablePlan) -> None:
    import asyncio

    audit: _FakeAuditRepo = service._audit  # noqa: SLF001
    pricing: _FakePricingRepo = service._pricing  # noqa: SLF001
    with pytest.raises(PricingDisableStaleError):
        asyncio.run(
            service.apply_disable_model_reviewed(
                plan=plan, actor_admin_id=ADMIN_ID, reason="reviewed reason"
            )
        )
    # zero writes before the refusal
    assert pricing.disabled == []
    assert audit.entries == []


def test_pricing_apply_audit_actor_and_verbatim_reason() -> None:
    import asyncio

    row = _pricing_row()
    repo = _FakePricingRepo(enabled_rows=[row])
    audit = _FakeAuditRepo()
    plan = asyncio.run(
        _service(repo, audit).preview_disable_model(
            provider="prov-a", model="model-a"
        )
    )
    verbatim_reason = "  Disable for maintenance window  "
    result = asyncio.run(
        _service(repo, audit).apply_disable_model_reviewed(
            plan=plan, actor_admin_id=ADMIN_ID, reason=verbatim_reason
        )
    )
    assert result.disabled_count == 1
    assert result.already_disabled is False
    assert len(audit.entries) == 1
    entry = audit.entries[0]
    assert entry["action"] == "pricing_rule_disabled"
    assert entry["entity_type"] == "pricing_rule"
    assert entry["entity_id"] == row.id
    assert entry["admin_user_id"] == ADMIN_ID
    # the reviewed reason is stored VERBATIM (never trimmed)
    assert entry["note"] == verbatim_reason


def test_pricing_apply_repeat_honest_noop() -> None:
    import asyncio

    row = _pricing_row(enabled=False)
    repo = _FakePricingRepo(
        enabled_rows=[],  # no ENABLED member for the scope
        locked_rows=[row],  # the reviewed (disabled) row is still locked
    )
    audit = _FakeAuditRepo()
    # Build the plan facts from the disabled row (identity + fingerprint
    # law is the same; the preview normally only sees enabled rows).
    from slaif_gateway.services.pricing_rule_service import (
        _pricing_disable_row_facts,
        _pricing_disable_row_fingerprint,
    )

    facts = _pricing_disable_row_facts(row)
    svc = _service(repo, audit)
    plan = PricingDisablePlan(
        provider="prov-a",
        model="model-a",
        endpoint=None,
        row_count=1,
        rows=(
            PricingDisableReviewRow(
                pricing_rule_id=row.id,
                fingerprint=_pricing_disable_row_fingerprint(facts),
            ),
        ),
    )
    result = asyncio.run(
        svc.apply_disable_model_reviewed(
            plan=plan, actor_admin_id=ADMIN_ID, reason="repeat run"
        )
    )
    assert result.disabled_count == 0
    assert result.already_disabled is True
    # no second disable, no audit
    assert repo.disabled == []
    assert audit.entries == []


def test_pricing_apply_mixed_flags_stale() -> None:
    import asyncio

    # Both rows enabled at preview time -> the plan reviews BOTH.
    rows = [_pricing_row(), _pricing_row()]
    repo = _FakePricingRepo(enabled_rows=rows)
    plan = asyncio.run(
        _service(repo, _FakeAuditRepo()).preview_disable_model(
            provider="prov-a", model="model-a"
        )
    )
    assert plan.row_count == 2
    # After the preview, one row was disabled: mixed state under locks.
    repo.enabled_rows = [rows[0]]
    repo.locked_rows = [rows[0], _replace_row(rows[1], enabled=False)]
    _assert_apply_stale(_service(repo, _FakeAuditRepo()), plan)


def test_pricing_apply_new_member_stale_both_paths() -> None:
    import asyncio

    row = _pricing_row()
    new_row = _pricing_row()
    # all-enabled path: a NEWLY matching unreviewed enabled row appears.
    repo = _FakePricingRepo(enabled_rows=[row, new_row])
    plan = asyncio.run(
        _service(repo, _FakeAuditRepo()).preview_disable_model(
            provider="prov-a", model="model-a"
        )
    )
    # drop new_row from the plan: preview again without it
    repo2 = _FakePricingRepo(enabled_rows=[row])
    plan = asyncio.run(
        _service(repo2, _FakeAuditRepo()).preview_disable_model(
            provider="prov-a", model="model-a"
        )
    )
    # now at apply time the scope has the extra enabled member
    repo3 = _FakePricingRepo(enabled_rows=[row, new_row])
    repo3.locked_rows = [row]
    _assert_apply_stale(_service(repo3, _FakeAuditRepo()), plan)

    # repeat path: an enabled member exists (a re-enabled reviewed row
    # or a new insert) while every reviewed row is disabled.
    disabled_row = _replace_row(row, enabled=False)
    repo4 = _FakePricingRepo(enabled_rows=[new_row])
    repo4.locked_rows = [disabled_row]
    from slaif_gateway.services.pricing_rule_service import (
        _pricing_disable_row_facts,
        _pricing_disable_row_fingerprint,
    )

    repeat_plan = PricingDisablePlan(
        provider="prov-a",
        model="model-a",
        endpoint=None,
        row_count=1,
        rows=(
            PricingDisableReviewRow(
                pricing_rule_id=disabled_row.id,
                fingerprint=_pricing_disable_row_fingerprint(
                    _pricing_disable_row_facts(disabled_row)
                ),
            ),
        ),
    )
    _assert_apply_stale(_service(repo4, _FakeAuditRepo()), repeat_plan)


def test_pricing_apply_late_audit_failure_propagates() -> None:
    import asyncio

    row = _pricing_row()
    repo = _FakePricingRepo(enabled_rows=[row])
    plan = asyncio.run(
        _service(repo, _FakeAuditRepo()).preview_disable_model(
            provider="prov-a", model="model-a"
        )
    )
    late_fault = RuntimeError("audit backend down")
    audit = _FakeAuditRepo(add_exc=late_fault)
    service = _service(repo, audit)
    # The service must NOT swallow a late audit failure: the caller's
    # transaction is what rolls everything back.
    with pytest.raises(RuntimeError, match="audit backend down"):
        asyncio.run(
            service.apply_disable_model_reviewed(
                plan=plan, actor_admin_id=ADMIN_ID, reason="reason"
            )
        )
    # the disable write happened BEFORE the fault (the rollback is the
    # caller transaction's job, not the service's)
    assert repo.disabled == [row.id]
    assert audit.entries == []


# ----------------------------------------------------------------------
# compact signed plan document: strictness and the byte-bound law
# ----------------------------------------------------------------------


def _fp(seed: int) -> str:
    return hashlib.sha256(f"fp-{seed}".encode("utf-8")).hexdigest()


def test_pricing_plan_document_roundtrip_and_strictness() -> None:
    import asyncio

    rows = [_pricing_row(row_id=uuid.UUID(int=i + 1)) for i in range(3)]
    plan = asyncio.run(
        _service(_FakePricingRepo(enabled_rows=rows), _FakeAuditRepo()).preview_disable_model(
            provider="prov-a", model="model-a"
        )
    )
    document = render_pricing_disable_plan(plan)
    # compact shape: closed keys, identity + fingerprint ONLY (the safe
    # display facts are never duplicated into the signed rows)
    assert set(document) == {"provider", "model", "endpoint", "row_count", "rows"}
    assert all(set(item) == {"id", "fingerprint"} for item in document["rows"])
    reparsed = parse_pricing_disable_plan_document(document)
    assert reparsed.row_count == 3
    assert [r.pricing_rule_id for r in reparsed.rows] == [r.id for r in rows]
    assert [r.fingerprint for r in reparsed.rows] == [r.fingerprint for r in plan.rows]
    assert reparsed.display_rows == ()

    def _refused(mutator) -> None:
        doc = json.loads(json.dumps(document))
        mutator(doc)
        with pytest.raises(ValueError, match="missing or invalid"):
            parse_pricing_disable_plan_document(doc)

    # duplicate row ID
    _refused(lambda doc: doc["rows"].append(dict(doc["rows"][0])))
    # count mismatch (both directions)
    _refused(lambda doc: doc.__setitem__("row_count", 2))
    _refused(
        lambda doc: doc["rows"].append(
            {"id": str(uuid.uuid4()), "fingerprint": _fp(99)}
        )
    )
    # bad fingerprint format
    _refused(lambda doc: doc["rows"][0].__setitem__("fingerprint", "nope"))
    # unknown keys (top level and per row)
    _refused(lambda doc: doc.__setitem__("note", "x"))
    _refused(lambda doc: doc["rows"][0].__setitem__("note", "x"))
    # bool is not an int count
    _refused(lambda doc: doc.__setitem__("row_count", True))
    # non-UUID row id
    _refused(lambda doc: doc["rows"][0].__setitem__("id", "not-a-uuid"))
    # the bounded cap: 1001 rows is refused
    big = {
        "provider": "prov-a",
        "model": "model-a",
        "endpoint": None,
        "row_count": PRICING_DISABLE_MAX_REVIEWED_ROWS + 1,
        "rows": [
            {"id": str(uuid.UUID(int=i)), "fingerprint": _fp(i)}
            for i in range(PRICING_DISABLE_MAX_REVIEWED_ROWS + 1)
        ],
    }
    with pytest.raises(ValueError, match="missing or invalid"):
        parse_pricing_disable_plan_document(big)


def test_pricing_plan_self_byte_gate_separate_from_wrapper() -> None:
    from slaif_gateway.api.admin_review_intent import (
        PRICING_REVIEW_PLAN_MAX_BYTES,
        _PRICING_TOO_LARGE_MESSAGE,
        _canonical_json,
    )

    # A valid row count/shape within the 1000 cap; only the allowed scope
    # string (model) is enlarged so the PLAN's own canonical bytes exceed
    # its 128 KiB cap while the wrapper (+8192 reason envelope) still fits.
    rows = tuple(
        PricingDisableReviewRow(pricing_rule_id=uuid.UUID(int=i + 1), fingerprint=_fp(i))
        for i in range(5)
    )
    model = "m" * 131_000
    plan = PricingDisablePlan(
        provider="prov-a", model=model, endpoint=None, row_count=5, rows=rows
    )
    document = render_pricing_disable_plan(plan)
    # the plan itself parses cleanly (shape/row law is fine - this is a
    # SIZE refusal, not a format refusal)
    reparsed = parse_pricing_disable_plan_document(document)
    assert reparsed.row_count == 5
    plan_bytes = len(_canonical_json(document))
    assert PRICING_DISABLE_PLAN_MAX_BYTES < plan_bytes < PRICING_REVIEW_PLAN_MAX_BYTES
    with pytest.raises(AdminReviewIntentError) as excinfo:
        build_pricing_review_token(
            admin_session_secret=_settings().ADMIN_SESSION_SECRET,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
            review_document={"plan": document, "reason": "reviewed scope"},
        )
    assert excinfo.value.message == _PRICING_TOO_LARGE_MESSAGE


# ----------------------------------------------------------------------
# review-intent tokens: binding, purpose, expiry
# ----------------------------------------------------------------------


def _replay_token(secret: str) -> str:
    from slaif_gateway.schemas.codex_replay_maintenance import (
        REPLAY_MAINTENANCE_PLAN_SCHEMA_VERSION,
        ReplayExtendPlan,
        parse_replay_scope,
        render_replay_extend_plan,
    )

    plan = ReplayExtendPlan(
        schema_version=REPLAY_MAINTENANCE_PLAN_SCHEMA_VERSION,
        operation="extend",
        scope=parse_replay_scope(key_id=str(OTHER_ADMIN_ID)),
        created_from=None,
        created_until=None,
        ttl_seconds=31536000,
        configured_ttl_seconds=31536000,
        include_expired=False,
        previewed_at=_now(),
        selected_keys=1,
        eligible_references=1,
        exclusion_counts={},
        old_expiry_min=None,
        old_expiry_max=None,
        new_expiry_min=None,
        new_expiry_max=None,
        expected_source_fingerprint="1" * 64,
        expected_source_state_fingerprint="2" * 64,
        expected_post_state_fingerprint="3" * 64,
    )
    return build_replay_review_token(
        admin_session_secret=secret,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document={
            "plan": render_replay_extend_plan(plan),
            "reason": "replay purpose",
        },
    )


def test_pricing_review_token_binding_purpose_and_expiry() -> None:
    import asyncio

    from slaif_gateway.api.admin_review_intent import (
        _PRICING_EXPIRED_MESSAGE,
        _PRICING_NOT_AUTHENTIC_MESSAGE,
    )

    secret = _settings().ADMIN_SESSION_SECRET
    plan = asyncio.run(
        _service(_FakePricingRepo(enabled_rows=[_pricing_row()]), _FakeAuditRepo()).preview_disable_model(
            provider="prov-a", model="model-a"
        )
    )
    # the reviewed reason is NEVER trimmed (leading/trailing spaces kept)
    document = {
        "plan": render_pricing_disable_plan(plan),
        "reason": "  bounded review reason  ",
    }
    base = _now()
    token = build_pricing_review_token(
        admin_session_secret=secret,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document=document,
        now=base,
    )
    checked = verify_pricing_review_token(
        admin_session_secret=secret,
        token=token,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        now=base + timedelta(minutes=1),
    )
    assert checked == document

    def _expect(message: str, **overrides) -> None:
        args = dict(
            admin_session_secret=secret,
            token=token,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
        )
        args.update(overrides)
        with pytest.raises(AdminReviewIntentError) as excinfo:
            verify_pricing_review_token(**args)
        assert excinfo.value.message == message

    _expect(_PRICING_NOT_AUTHENTIC_MESSAGE, admin_user_id=OTHER_ADMIN_ID)
    _expect(_PRICING_NOT_AUTHENTIC_MESSAGE, admin_session_id=OTHER_SESSION_ID)
    _expect(
        _PRICING_EXPIRED_MESSAGE,
        now=base + timedelta(seconds=REVIEW_INTENT_TTL_SECONDS + 1),
    )
    # tampered payload bytes
    body, _, digest = token.rpartition(".")
    tampered = body[:-4] + ("AAAA" if body[-4:] != "AAAA" else "BBBB") + "." + digest
    # tampered payload: digest mismatch -> fixed not-authentic refusal
    _expect(_PRICING_NOT_AUTHENTIC_MESSAGE, token=tampered)

    # purpose separation: the replay verifier refuses a pricing token ...
    with pytest.raises(AdminReviewIntentError):
        verify_replay_review_token(
            admin_session_secret=secret,
            token=token,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
        )
    # ... and the pricing verifier refuses a real replay token.
    replay_token = _replay_token(secret)
    with pytest.raises(AdminReviewIntentError):
        verify_pricing_review_token(
            admin_session_secret=secret,
            token=replay_token,
            admin_user_id=ADMIN_ID,
            admin_session_id=SESSION_ID,
        )


# ----------------------------------------------------------------------
# safe export DTO serializer + display laws
# ----------------------------------------------------------------------


def test_json_default_exact_raw_units_and_strict_serialization() -> None:
    from slaif_gateway.api.admin_reports import _json_default

    now = datetime(2026, 1, 2, 3, 4, 5, 6, tzinfo=UTC)
    key_id = uuid.UUID(int=7)
    # exact raw machine units: Decimal EXACT string (never float), UUID
    # canonical string, datetime ISO-8601
    assert _json_default(Decimal("12.345")) == "12.345"
    assert _json_default(key_id) == str(key_id)
    assert _json_default(now) == now.isoformat()
    with pytest.raises(TypeError):
        _json_default(object())
    payload = {
        "estimated_cost_eur": Decimal("1.5"),
        "gateway_key_id": key_id,
        "created_at": now,
    }
    rendered = json.dumps(
        payload, allow_nan=False, sort_keys=True, default=_json_default
    )
    assert json.loads(rendered) == {
        "estimated_cost_eur": "1.5",
        "gateway_key_id": str(key_id),
        "created_at": now.isoformat(),
    }
    # strict: NaN is never serialized
    with pytest.raises(ValueError):
        json.dumps({"x": float("nan")}, allow_nan=False)


def test_cost_money_display_and_status_law() -> None:
    from slaif_gateway.api.admin_reports import (
        _cost_money_display,
        _cost_status,
    )

    # all rows missing -> numeric NOT rendered (unavailable, never 0)
    assert _cost_money_display(0, 3, Decimal("0")) == {
        "available": False,
        "value": None,
        "label": "unavailable",
    }
    # no rows at all
    assert _cost_money_display(0, 0, Decimal("0")) == {
        "available": False,
        "value": None,
        "label": "no rows",
    }
    # a genuine known zero stays zero (not withheld)
    assert _cost_money_display(3, 3, Decimal("0")) == {
        "available": True,
        "value": Decimal("0"),
        "label": "",
    }
    # partially known -> exact sum over known rows, labelled incomplete
    partial = _cost_money_display(2, 3, Decimal("7.5"))
    assert partial["available"] is True
    assert partial["value"] == Decimal("7.5")
    assert partial["label"] == "incomplete (partial; missing rows excluded)"
    # status counts follow the comma display convention
    assert _cost_status(2000, 2000) == "Complete (2,000 of 2,000 rows known)"
    assert _cost_status(0, 2000) == "No cost data (0 of 2,000 rows known)"
    assert _cost_status(500, 2000) == "Partial (500 of 2,000 rows known)"
    assert _cost_status(0, 0) == "No rows"


def test_recovery_allowlist_refuses_unknown_destination(monkeypatch) -> None:
    import slaif_gateway.api.admin_reports as mod

    captured: dict[str, object] = {}

    def fake_template_response(request, name, context, **kwargs):
        captured["name"] = name
        captured["context"] = context
        return HTMLResponse("ok")

    monkeypatch.setattr(mod.templates, "TemplateResponse", fake_template_response)
    # non-allowlisted destination is dropped (plain error page remains)
    mod._report_error(None, 400, "boom", recovery_href="/evil")
    assert captured["name"] == "reports/error.html"
    assert captured["context"]["recovery_href"] is None
    # allowlisted destinations pass through with their labels
    mod._report_error(None, 400, "boom", recovery_href="/admin/reports/pricing-disable")
    assert captured["context"]["recovery_href"] == "/admin/reports/pricing-disable"
    assert captured["context"]["recovery_label"] == "Back to the report"
    mod._report_error(
        None,
        400,
        "boom",
        recovery_href="/admin/pricing",
        recovery_label="Check the pricing rules",
    )
    assert captured["context"]["recovery_href"] == "/admin/pricing"
    assert captured["context"]["recovery_label"] == "Check the pricing rules"


# ----------------------------------------------------------------------
# router: gates, validation, refusals (fake-persistence app)
# ----------------------------------------------------------------------

REPORT_GET_ROUTES = (
    "/admin/reports/",
    "/admin/reports/live-burn",
    "/admin/reports/export",
    "/admin/reports/pricing-disable",
    "/admin/reports/fx-lookup",
)
REPORT_POST_ROUTES = (
    "/admin/reports/export",
    "/admin/reports/pricing-disable/preview",
    "/admin/reports/pricing-disable/apply",
)


def test_report_routes_require_auth() -> None:
    c = TestClient(_app(), follow_redirects=False)
    for path in REPORT_GET_ROUTES:
        r = c.get(path)
        assert r.status_code == 303
        assert r.headers["location"] == "/admin/login"
    for path in REPORT_POST_ROUTES:
        assert c.post(path, data={"csrf_token": CSRF}).status_code == 303


def test_dashboard_disabled_refuses_every_report_route() -> None:
    c = TestClient(
        _app(_settings(ENABLE_ADMIN_DASHBOARD=False)), follow_redirects=False
    )
    for path in REPORT_GET_ROUTES:
        assert c.get(path).status_code == 404
    for path in REPORT_POST_ROUTES:
        assert c.post(path, data={"csrf_token": CSRF}).status_code == 404


def _patch_usage_repo(monkeypatch, repo: _FakeUsageRepo) -> None:
    monkeypatch.setattr(
        "slaif_gateway.api.admin_reports.UsageLedgerRepository",
        lambda session: repo,
    )


def test_summary_validation_400_with_recovery(client) -> None:
    r = client.get("/admin/reports/", params={"group_by": "everything"})
    assert r.status_code == 400
    assert 'href="/admin/reports/"' in r.text
    r = client.get("/admin/reports/", params={"start_at": "not-a-time"})
    assert r.status_code == 400
    assert 'href="/admin/reports/"' in r.text
    # shared bounded pagination limit
    assert (
        client.get("/admin/reports/", params={"limit": MAX_ADMIN_PAGE_LIMIT + 1}).status_code
        == 422
    )


def test_summary_alias_scope_refused_no_echo(client) -> None:
    # accepted-prefix canary trips the REAL guard without patching
    r = client.get("/admin/reports/", params={"provider": PREFIX_CANARY})
    assert r.status_code == 400
    assert PREFIX_CANARY not in r.text
    assert 'href="/admin/reports/"' in r.text
    # cookie-valued incoming credential submitted as a UUID scope
    cookie_value = str(uuid.UUID(int=42))
    client.cookies.set("slaif_admin_session", cookie_value)
    r = client.get("/admin/reports/", params={"owner_id": cookie_value})
    assert r.status_code == 400
    assert cookie_value not in r.text


def test_summary_source_bound_refused(client, monkeypatch) -> None:
    # GUI ceiling + 1 rows: the service refuses BEFORE any rendering
    rows = [_ledger_row() for _ in range(GUI_USAGE_REPORT_SOURCE_MAX_ROWS + 1)]
    _patch_usage_repo(monkeypatch, _FakeUsageRepo(rows))
    r = client.get("/admin/reports/")
    assert r.status_code == 400
    # fixed safe message: the exact source limit, plain integer
    assert "bounded source limit of 10000" in r.text
    assert "Narrow the scope" in r.text
    # The refusal is recoverable WITHIN the page: the existing
    # report/filter form is rendered with the bound error - no result
    # rows, no empty "no groups" state, no completeness claim.
    assert 'action="/admin/reports/"' in r.text
    assert 'name="provider"' in r.text
    assert "No groups in the accepted scope" not in r.text
    assert "groups shown" not in r.text


def test_summary_pages_complete_groups_in_memory(client, monkeypatch) -> None:
    now = _now()
    rows = [
        _ledger_row(provider="prov-a", model="m1", created_at=now),
        _ledger_row(provider="prov-a", model="m2", created_at=now),
        _ledger_row(provider="prov-b", model="m1", created_at=now),
        _ledger_row(provider="prov-c", model="m1", created_at=now),
    ]
    repo = _FakeUsageRepo(rows)
    _patch_usage_repo(monkeypatch, repo)
    # the service runs over the COMPLETE bounded source set (cap+1 fetch)
    r = client.get(
        "/admin/reports/", params={"group_by": "provider", "limit": 2}
    )
    assert r.status_code == 200
    assert (
        repo.limit_seen == GUI_USAGE_REPORT_SOURCE_MAX_ROWS + 1
    )
    # 3 groups, page 1 shows 2 (prov-a first; prov-c beats prov-b on the
    # grouping-key final tie-break, reverse-sorted)
    assert "prov-a" in r.text
    assert "prov-c" in r.text
    assert ">prov-b<" not in r.text.replace("&gt;", ">")
    # next URL continues the offset and preserves the accepted group
    # scope (Jinja escapes attribute ampersands as &amp;: parse the
    # actual anchor href, do not weaken the escaping)
    hrefs = {html.unescape(href) for href in re.findall(r'href="([^"]+)"', r.text)}
    assert "/admin/reports/?group_by=provider&limit=2&offset=2" in hrefs
    # page 2: the remaining group, no further next
    r2 = client.get(
        "/admin/reports/",
        params={"group_by": "provider", "limit": 2, "offset": 2},
    )
    assert r2.status_code == 200
    assert "prov-b" in r2.text
    assert 'rel="next"' not in r2.text
    assert "rel=\"prev\"" in r2.text
    hrefs2 = {html.unescape(href) for href in re.findall(r'href="([^"]+)"', r2.text)}
    assert "/admin/reports/?group_by=provider&limit=2&offset=0" in hrefs2
    assert "/admin/reports/?group_by=provider&limit=2&offset=4" not in hrefs2


def test_live_burn_scope_and_bound(client, monkeypatch) -> None:
    rows = [
        _ledger_row(
            metadata={
                "streaming_live_burn_triggered": True,
                "streaming_live_burn_stop_reason": "tokens",
                "estimated_tokens_at_stop": 5,
            }
        )
        for _ in range(2)
    ]
    repo = _FakeUsageRepo(rows)
    _patch_usage_repo(monkeypatch, repo)
    r = client.get("/admin/reports/live-burn")
    assert r.status_code == 200
    assert repo.limit_seen == GUI_USAGE_REPORT_SOURCE_MAX_ROWS + 1
    # the source cap counts ALL matched ledger rows; only Chat telemetry
    # contributes to the aggregates
    assert "capped at" in r.text
    assert "10,000" in r.text
    assert "only Chat streaming" in r.text
    assert "contribute to the aggregates" in r.text


# ----------------------------------------------------------------------
# router: safe strict-JSON usage export
# ----------------------------------------------------------------------


def _export_row(
    *,
    provider: str = "prov-a",
    estimated: Decimal | None = Decimal("1.5"),
) -> UsageExportRow:
    return UsageExportRow(
        created_at=_now(),
        request_id="req-1",
        gateway_key_id=uuid.UUID(int=11),
        owner_id=None,
        cohort_id=None,
        provider=provider,
        requested_model="model-a",
        resolved_model="model-a",
        endpoint="/v1/chat/completions",
        streaming=True,
        success=True,
        accounting_status="final",
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        cached_tokens=0,
        reasoning_tokens=0,
        estimated_cost_eur=estimated,
        actual_cost_eur=None,
        native_currency="USD",
        upstream_request_id=None,
        chat_live_burn_triggered=False,
        chat_live_burn_stop_reason=None,
        chat_live_burn_estimated_tokens_at_stop=None,
        chat_live_burn_estimated_cost_eur_at_stop=None,
        chat_live_burn_cost_margin_eur=None,
        chat_live_burn_token_margin=None,
        chat_live_burn_final_provider_usage_available=None,
    )


class _FakeExportService:
    def __init__(self, rows: list[UsageExportRow]):
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    async def export_usage(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.rows)


def _patch_export(monkeypatch, rows: list[UsageExportRow]) -> _FakeExportService:
    fake = _FakeExportService(rows)
    monkeypatch.setattr(
        "slaif_gateway.api.admin_reports.UsageReportService",
        lambda **kwargs: fake,
    )
    return fake


class _FakeAuditCapture:
    def __init__(self):
        self.entries: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs):
        self.entries.append(kwargs)


def test_export_requires_confirm_reason_and_bound(client, monkeypatch) -> None:
    _patch_export(monkeypatch, [_export_row()])
    r = client.post("/admin/reports/export", data={"csrf_token": CSRF})
    assert r.status_code == 400
    assert "Confirm the JSON export" in r.text
    r = client.post(
        "/admin/reports/export",
        data={"csrf_token": CSRF, "confirm_export": "1"},
    )
    assert r.status_code == 400
    assert "Enter an audit reason" in r.text
    r = client.post(
        "/admin/reports/export",
        data={
            "csrf_token": CSRF,
            "confirm_export": "1",
            "reason": "x" * (MAX_KEY_CONFIGURATION_REASON_LENGTH + 1),
        },
    )
    assert r.status_code == 400
    assert "too long" in r.text


def test_export_overbound_refused_with_counts(client, monkeypatch) -> None:
    fake = _patch_export(monkeypatch, [_export_row() for _ in range(3)])
    r = client.post(
        "/admin/reports/export",
        data={
            "csrf_token": CSRF,
            "confirm_export": "1",
            "reason": "bounded review",
            "limit": "2",
        },
    )
    assert r.status_code == 400
    # cap+1 fetch through the existing bounded query
    assert fake.calls[0]["limit"] == 3
    assert "or more ledger rows" in r.text
    assert "No partial export was produced." in r.text
    assert 'href="/admin/reports/export"' in r.text


def test_export_strict_json_attachment_and_audit(client, monkeypatch) -> None:
    _patch_export(monkeypatch, [_export_row(), _export_row(estimated=Decimal("2.25"))])
    audit = _FakeAuditCapture()
    monkeypatch.setattr(
        "slaif_gateway.api.admin_reports.AuditRepository", lambda *a, **k: audit
    )
    r = client.post(
        "/admin/reports/export",
        data={
            "csrf_token": CSRF,
            "confirm_export": "1",
            "reason": "  quarterly review  ",
            "limit": "5",
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert "no-store" in r.headers.get("cache-control", "")
    assert r.headers["content-disposition"].startswith(
        'attachment; filename="usage-export-'
    )
    payload = r.json()
    assert set(payload) == {"generated_at", "scope", "rows"}
    assert payload["scope"]["limit"] == 5
    assert payload["scope"]["row_count"] == 2
    # exact raw machine units in the DTO (Decimal as exact string, never
    # a float; UUID canonical string)
    assert payload["rows"][0]["estimated_cost_eur"] == "1.5"
    assert payload["rows"][1]["estimated_cost_eur"] == "2.25"
    assert payload["rows"][0]["gateway_key_id"] == str(uuid.UUID(int=11))
    # the audit record persists the cleaned reason and the exact scope
    assert len(audit.entries) == 1
    entry = audit.entries[0]
    assert entry["action"] == "admin_usage_export_json"
    assert entry["note"] == "quarterly review"
    assert entry["new_values"]["row_count"] == 2


def test_export_dto_alias_refused_no_echo(client, monkeypatch) -> None:
    _patch_export(monkeypatch, [_export_row(provider=PREFIX_CANARY)])
    r = client.post(
        "/admin/reports/export",
        data={"csrf_token": CSRF, "confirm_export": "1", "reason": "r"},
    )
    assert r.status_code == 400
    assert PREFIX_CANARY not in r.text
    assert "known incoming authentication value" in r.text


def test_export_reason_alias_refused_no_echo(client, monkeypatch) -> None:
    _patch_export(monkeypatch, [_export_row()])
    r = client.post(
        "/admin/reports/export",
        data={
            "csrf_token": CSRF,
            "confirm_export": "1",
            "reason": PREFIX_CANARY,
        },
    )
    assert r.status_code == 400
    assert PREFIX_CANARY not in r.text


# ----------------------------------------------------------------------
# router: reviewed matching-model pricing disable
# ----------------------------------------------------------------------


class _FakePricingRouterService:
    def __init__(self):
        self.plan: PricingDisablePlan | None = None
        self.preview_exc: Exception | None = None
        self.apply_result: PricingDisableApplyResult | None = None
        self.apply_exc: Exception | None = None
        self.preview_calls: list[dict[str, object]] = []
        self.apply_calls: list[dict[str, object]] = []

    async def preview_disable_model(self, **kwargs):
        self.preview_calls.append(kwargs)
        if self.preview_exc is not None:
            raise self.preview_exc
        assert self.plan is not None
        return self.plan

    async def apply_disable_model_reviewed(self, **kwargs):
        self.apply_calls.append(kwargs)
        if self.apply_exc is not None:
            raise self.apply_exc
        assert self.apply_result is not None
        return self.apply_result


def _patch_pricing(
    monkeypatch, fake: _FakePricingRouterService | None = None
) -> _FakePricingRouterService:
    fake = fake or _FakePricingRouterService()
    monkeypatch.setattr(
        "slaif_gateway.api.admin_reports.PricingRuleService",
        lambda **kwargs: fake,
    )
    return fake


def _plan_for_rows(rows: list[SimpleNamespace]) -> PricingDisablePlan:
    from slaif_gateway.services import pricing_rule_service as prs

    plan_rows = tuple(
        PricingDisableReviewRow(
            pricing_rule_id=row.id,
            fingerprint=prs._pricing_disable_row_fingerprint(
                prs._pricing_disable_row_facts(row)
            ),
        )
        for row in rows
    )
    display = tuple(
        PricingDisableDisplayRow(
            pricing_rule_id=row.id,
            provider=row.provider,
            upstream_model=row.upstream_model,
            endpoint=row.endpoint,
            currency=row.currency,
            valid_from=row.valid_from,
            valid_until=row.valid_until,
            input_price_per_1m=row.input_price_per_1m,
            cached_input_price_per_1m=row.cached_input_price_per_1m,
            output_price_per_1m=row.output_price_per_1m,
            reasoning_price_per_1m=row.reasoning_price_per_1m,
            request_price=row.request_price,
        )
        for row in rows
    )
    return PricingDisablePlan(
        provider="prov-a",
        model="model-a",
        endpoint=None,
        row_count=len(rows),
        rows=plan_rows,
        display_rows=display,
    )


def test_pricing_preview_signs_token_bound_to_actor(client, monkeypatch) -> None:
    fake = _patch_pricing(monkeypatch)
    fake.plan = _plan_for_rows([_pricing_row()])
    reason = "  maintenance window  "
    r = client.post(
        "/admin/reports/pricing-disable/preview",
        data={"csrf_token": CSRF, "provider": "prov-a", "model": "model-a", "reason": reason},
    )
    assert r.status_code == 200
    match = re.search(r'name="review_token"[^>]*value="([^"]+)"', r.text)
    assert match is not None
    document = verify_pricing_review_token(
        admin_session_secret=_settings().ADMIN_SESSION_SECRET,
        token=match.group(1),
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
    )
    # the signed document is the compact plan + the VERBATIM reason
    assert document["plan"] == render_pricing_disable_plan(fake.plan)
    assert document["reason"] == reason
    # the scope reaches the shared service normalized
    assert fake.preview_calls[0]["provider"] == "prov-a"
    assert fake.preview_calls[0]["model"] == "model-a"
    assert fake.preview_calls[0]["endpoint"] is None


def test_pricing_preview_refusals(client, monkeypatch) -> None:
    fake = _patch_pricing(monkeypatch)
    fake.plan = _plan_for_rows([_pricing_row()])
    base = {"csrf_token": CSRF, "provider": "prov-a", "model": "model-a"}
    r = client.post(
        "/admin/reports/pricing-disable/preview", data={**base, "reason": "   "}
    )
    assert r.status_code == 400
    assert "nonblank audit reason" in r.text
    r = client.post(
        "/admin/reports/pricing-disable/preview",
        data={**base, "reason": "x" * (MAX_KEY_CONFIGURATION_REASON_LENGTH + 1)},
    )
    assert r.status_code == 400
    assert "too long" in r.text
    # alias reason: refused, never echoed
    r = client.post(
        "/admin/reports/pricing-disable/preview", data={**base, "reason": PREFIX_CANARY}
    )
    assert r.status_code == 400
    assert PREFIX_CANARY not in r.text
    # alias scope identifier: refused before the service call
    r = client.post(
        "/admin/reports/pricing-disable/preview",
        data={**base, "provider": PREFIX_CANARY, "reason": "r"},
    )
    assert r.status_code == 400
    assert PREFIX_CANARY not in r.text
    assert fake.preview_calls == []
    # shared-service no-match and overbound scope
    fake.preview_exc = PricingDisableNoMatchError()
    r = client.post(
        "/admin/reports/pricing-disable/preview", data={**base, "reason": "r"}
    )
    assert r.status_code == 400
    assert "No enabled pricing rows match" in r.text
    fake.preview_exc = PricingDisableScopeError(matched_rows=1001, max_rows=1000)
    r = client.post(
        "/admin/reports/pricing-disable/preview", data={**base, "reason": "r"}
    )
    assert r.status_code == 400
    assert "above the reviewed plan bound of 1000" in r.text


def _valid_pricing_token(reason: str = "  reviewed reason  ") -> str:
    plan = _plan_for_rows([_pricing_row()])
    return build_pricing_review_token(
        admin_session_secret=_settings().ADMIN_SESSION_SECRET,
        admin_user_id=ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document={
            "plan": render_pricing_disable_plan(plan),
            "reason": reason,
        },
    )


def test_pricing_apply_confirm_binding_and_outcome(client, monkeypatch) -> None:
    fake = _patch_pricing(monkeypatch)
    fake.apply_result = PricingDisableApplyResult(disabled_count=1, already_disabled=False)
    token = _valid_pricing_token()
    # confirmation required before the signed apply
    r = client.post(
        "/admin/reports/pricing-disable/apply",
        data={"csrf_token": CSRF, "review_token": token},
    )
    assert r.status_code == 400
    assert "Confirm the reviewed pricing disable" in r.text
    assert fake.apply_calls == []
    # a token signed for another admin is not valid for this one
    other = build_pricing_review_token(
        admin_session_secret=_settings().ADMIN_SESSION_SECRET,
        admin_user_id=OTHER_ADMIN_ID,
        admin_session_id=SESSION_ID,
        review_document={
            "plan": render_pricing_disable_plan(fake.plan or _plan_for_rows([_pricing_row()])),
            "reason": "other admin",
        },
    )
    r = client.post(
        "/admin/reports/pricing-disable/apply",
        data={"csrf_token": CSRF, "review_token": other, "confirm_apply": "1"},
    )
    assert r.status_code == 400
    assert "not valid for this signed-in admin" in r.text
    assert fake.apply_calls == []
    # happy path: the service receives the signed facts verbatim
    r = client.post(
        "/admin/reports/pricing-disable/apply",
        data={"csrf_token": CSRF, "review_token": token, "confirm_apply": "1"},
    )
    assert r.status_code == 200
    assert fake.apply_calls[0]["actor_admin_id"] == ADMIN_ID
    assert fake.apply_calls[0]["reason"] == "  reviewed reason  "
    assert "1" in r.text


def test_pricing_apply_stale_unconfirmed_and_alias_recheck(client, monkeypatch) -> None:
    fake = _patch_pricing(monkeypatch)
    token = _valid_pricing_token()
    # stale under the locks: fixed message + review-scope recovery
    fake.apply_exc = PricingDisableStaleError()
    r = client.post(
        "/admin/reports/pricing-disable/apply",
        data={"csrf_token": CSRF, "review_token": token, "confirm_apply": "1"},
    )
    assert r.status_code == 400
    assert "Preview the scope again" in r.text
    assert 'href="/admin/reports/pricing-disable"' in r.text
    # unconfirmed outcome: recovery points at pricing/audit state
    fake.apply_exc = RuntimeError("db gone")
    r = client.post(
        "/admin/reports/pricing-disable/apply",
        data={"csrf_token": CSRF, "review_token": token, "confirm_apply": "1"},
    )
    assert r.status_code == 400
    assert "UNCONFIRMED" in r.text
    assert 'href="/admin/pricing"' in r.text
    assert "Check the pricing rules" in r.text
    # the stale and unconfirmed attempts reached the service (and
    # failed there); no SUCCESSFUL apply happened
    assert len(fake.apply_calls) == 2
    # the signed review is re-checked against THIS request's known
    # aliases before any service call (reason canary)
    canary_token = _valid_pricing_token(reason=PREFIX_CANARY)
    fake.apply_exc = None
    fake.apply_result = PricingDisableApplyResult(disabled_count=1, already_disabled=False)
    r = client.post(
        "/admin/reports/pricing-disable/apply",
        data={"csrf_token": CSRF, "review_token": canary_token, "confirm_apply": "1"},
    )
    assert r.status_code == 400
    assert "can no longer be applied" in r.text
    assert PREFIX_CANARY not in r.text
    assert len(fake.apply_calls) == 2
    # a replay-purpose token is never a pricing review
    r = client.post(
        "/admin/reports/pricing-disable/apply",
        data={
            "csrf_token": CSRF,
            "review_token": _replay_token(_settings().ADMIN_SESSION_SECRET),
            "confirm_apply": "1",
        },
    )
    assert r.status_code == 400
    assert len(fake.apply_calls) == 2


# ----------------------------------------------------------------------
# router: effective FX lookup
# ----------------------------------------------------------------------


class _FakeFxService:
    def __init__(self, rate: object | None = None, exc: Exception | None = None):
        self.rate = rate
        self.exc = exc
        self.calls: list[dict[str, object]] = []

    async def latest_fx_rate(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return self.rate


def _patch_fx(monkeypatch, rate: object | None = None, exc: Exception | None = None):
    fake = _FakeFxService(rate, exc)
    monkeypatch.setattr(
        "slaif_gateway.api.admin_reports.FxRateService", lambda **kwargs: fake
    )
    return fake


def test_fx_missing_present_and_alias_source(client, monkeypatch) -> None:
    # honest missing state (never an inferred rate)
    fake = _patch_fx(monkeypatch, exc=RecordNotFoundError("FX rate"))
    r = client.get(
        "/admin/reports/fx-lookup",
        params={"base_currency": "EUR", "quote_currency": "USD"},
    )
    assert r.status_code == 200
    assert "No FX rate is effective for" in r.text
    assert fake.calls[0] == {"base_currency": "EUR", "quote_currency": "USD"}
    # present rate renders through the shared formatter
    rate = SimpleNamespace(
        base_currency="EUR",
        quote_currency="USD",
        rate=Decimal("1.08"),
        source="provider-feed",
        valid_from=_now(),
        valid_until=None,
    )
    _patch_fx(monkeypatch, rate=rate)
    r = client.get(
        "/admin/reports/fx-lookup",
        params={"base_currency": "EUR", "quote_currency": "USD"},
    )
    assert r.status_code == 200
    assert "1.08" in r.text
    # a known incoming alias in the rate source is withheld, not echoed
    aliased = SimpleNamespace(
        base_currency="EUR",
        quote_currency="USD",
        rate=Decimal("1.08"),
        source=PREFIX_CANARY,
        valid_from=_now(),
        valid_until=None,
    )
    _patch_fx(monkeypatch, rate=aliased)
    r = client.get(
        "/admin/reports/fx-lookup",
        params={"base_currency": "EUR", "quote_currency": "USD"},
    )
    assert r.status_code == 200
    assert "Withheld: matches a known credential value" in r.text
    assert PREFIX_CANARY not in r.text
    # same-currency and malformed codes are refused
    r = client.get(
        "/admin/reports/fx-lookup",
        params={"base_currency": "EUR", "quote_currency": "EUR"},
    )
    assert r.status_code == 400
    assert "must differ" in r.text
    r = client.get(
        "/admin/reports/fx-lookup",
        params={"base_currency": "EURO", "quote_currency": "USD"},
    )
    assert r.status_code == 400
    assert "3-letter" in r.text


# ----------------------------------------------------------------------
# 214-a: admin validation rejections never echo submitted values
# (api/errors.py safe projection; the /v1 branch stays OpenAI-shaped)
# ----------------------------------------------------------------------


def test_admin_validation_rejection_never_echoes_submitted_value(client) -> None:
    # OLD admin surface: /admin/keys with a credential-valued limit
    r = client.get("/admin/keys", params={"limit": PREFIX_CANARY})
    assert r.status_code == 422
    assert PREFIX_CANARY not in r.text
    detail = r.json()["detail"]
    assert isinstance(detail, list) and detail
    entry = detail[0]
    # detail array / loc / type structure preserved...
    assert entry["loc"] == ["query", "limit"]
    assert entry["type"] == "int_parsing"
    # ...the generated safe message stays (value-free vocabulary)...
    assert "integer" in entry["msg"]
    # ...while raw input/context/url are ALWAYS omitted
    assert "input" not in entry
    assert "ctx" not in entry
    assert "url" not in entry
    # NEW admin surface: /admin/reports/
    r = client.get("/admin/reports/", params={"limit": PREFIX_CANARY})
    assert r.status_code == 422
    assert PREFIX_CANARY not in r.text
    entry = r.json()["detail"][0]
    assert entry["loc"] == ["query", "limit"]
    assert entry["type"] == "int_parsing"
    assert "input" not in entry


def test_admin_validation_loc_long_credential_withheld_before_truncation() -> None:
    import asyncio

    from fastapi import Request
    from fastapi.exceptions import RequestValidationError

    from slaif_gateway.api.errors import request_validation_exception_handler

    # A long opaque incoming credential (cookie) appearing as a
    # validation LOCATION must be alias-checked on the ORIGINAL full
    # string BEFORE any truncation: neither the full value nor its
    # leading 128 chars may be exposed in the 422 body.
    long_secret = "opaque-" + "a1b2c3d4" * 20  # 165 chars
    exc = RequestValidationError(
        [
            {
                "type": "missing",
                "loc": ("body", long_secret, "field"),
                "msg": "Field required",
                "input": "irrelevant-value",
            }
        ]
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/admin/reports/export",
            "scheme": "http",
            "server": ("testserver", 80),
            "headers": [
                (b"host", b"testserver"),
                (b"cookie", f"slaif_admin_session={long_secret}".encode("latin-1")),
            ],
            "app": _app(_settings()),
        }
    )
    response = asyncio.run(request_validation_exception_handler(request, exc))
    assert response.status_code == 422
    body = response.body.decode("utf-8")
    assert long_secret not in body
    assert long_secret[:128] not in body
    entry = json.loads(body)["detail"][0]
    # the safe surrounding location parts survive the withholding
    assert entry["loc"] == ["body", "field"]
    assert entry["type"] == "missing"


def test_v1_validation_branch_unchanged_openai_shaped() -> None:
    import asyncio

    from fastapi import Request
    from fastapi.exceptions import RequestValidationError

    from slaif_gateway.api.errors import request_validation_exception_handler

    # the /v1 branch keeps the OpenAI-shaped rejection: no detail array,
    # no loc, and the raw input never leaves the handler
    exc = RequestValidationError(
        [
            {
                "type": "int_parsing",
                "loc": ("query", "limit"),
                "msg": "Input should be a valid integer",
                "input": PREFIX_CANARY,
            }
        ]
    )
    app = _app(_settings())
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/chat/completions",
            "scheme": "http",
            "server": ("testserver", 80),
            "headers": [(b"host", b"testserver")],
            "app": app,
        }
    )
    response = asyncio.run(request_validation_exception_handler(request, exc))
    assert response.status_code == 422
    body = json.loads(response.body)
    assert set(body) == {"error"}
    assert body["error"]["message"] == "Invalid request"
    assert body["error"]["code"] == "validation_error"
    assert PREFIX_CANARY not in response.body.decode("utf-8")
