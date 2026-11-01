"""209-a GUI reviewed key batch: focused unit qualification.

Fake-persistence ASGI/Jinja seams over the real admin app: the batch
router's auth/CSRF, single-source input law (guided vs advanced document),
selection/status parsing, guided policy composition semantics (omit=null=
clear=zero per member), per-field list-mode vocabulary, the purpose-bound
batch review-intent token (cross-purpose/actor/session/expiry/tamper/
size), fixed safe error paths (no 500s, no generic try-again for known
refusals), credential-shape privacy (booleans only; the advanced document
is blanked before every rerender), readable review rendering (ordinal,
key links, grouped/M display vs ungrouped raw sort keys, field-specific
null labels, allow-all-state-aware empty lists), and full-1000 transport
round-trip. No database, no SMTP, no broker: KeyBatchService is faked at
the module seam; the core policy/transaction law stays authoritative.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.api import admin_review_intent as intent
from slaif_gateway.api import admin_key_batch as batch
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.schemas.key_batch import (
    KEY_BATCH_MAX_KEYS,
    KeyBatchError,
    KeyBatchPlan,
    KeyBatchPlanKey,
    key_batch_document_changes,
    parse_key_batch_plan,
    render_key_batch_plan,
)
from slaif_gateway.schemas.key_configuration import (
    KeyConfiguration,
    parse_key_configuration,
)
from slaif_gateway.services.admin_session_service import (
    AdminSessionContext,
    AdminSessionService,
)
from slaif_gateway.services.key_errors import (
    GatewayKeyNotFoundError,
    KeyManagementError,
)

from tests.unit.key_management_fakes import FakeGatewayKeyRow
from tests.unit.test_admin_key_actions_routes import _app, _settings
from tests.unit.test_admin_key_clone_208 import _plan_document as _clone_plan_document
from tests.unit.test_key_batch import _make_batch_service

# Synthetic values only; asserted as booleans, never echoed.
CANARY_PROVIDER = "sk-slaif-canary-" + "7" * 40
CANARY_PASSWORD = "canary-pw-" + "x" * 48
CANARY_KEY = "sk-slaif-canary-" + "9" * 40

COHORT_ID = uuid.uuid4()
K1 = uuid.uuid4()
K2 = uuid.uuid4()
EXCLUDED_K1 = uuid.uuid4()
KEYS_SORTED = tuple(sorted(str(k) for k in (K1, K2)))

PLAN_POLICY = {
    "schema_version": 1,
    "request_limit_total": None,
    "token_limit_total": 2000000,
}

FENCED_BLOCK = {"version": 1, "mode": "external_tool_fenced"}


def _make_plan(
    *,
    cohort_id: uuid.UUID | None = COHORT_ID,
    key_ids: tuple[str, ...] = KEYS_SORTED,
    statuses: tuple[str, ...] = ("active",),
    policy: dict[str, Any] | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    excluded: tuple[tuple[str, str], ...] = (),
) -> KeyBatchPlan:
    """A strict-conformant plan the real parser accepts."""
    before_doc = before or {
        "schema_version": 1,
        "request_limit_total": 1000,
        "token_limit_total": 5000000,
    }
    after_doc = after or {
        "schema_version": 1,
        "request_limit_total": None,
        "token_limit_total": 2000000,
    }
    keys = [
        KeyBatchPlanKey(
            key_id=kid,
            source_fingerprint="ab" * 32,
            post_fingerprint="cd" * 32,
            before=dict(before_doc),
            after=dict(after_doc),
            changes=key_batch_document_changes(before_doc, after_doc),
        )
        for kid in key_ids
    ]
    changed = sum(1 for key in keys if key.changes)
    return KeyBatchPlan(
        schema_version=1,
        operation="apply",
        selection_kind="cohort" if cohort_id else "keys",
        cohort_id=str(cohort_id) if cohort_id else None,
        key_ids=tuple(sorted(key_ids)),
        statuses=tuple(sorted(set(statuses))),
        policy=dict(policy or PLAN_POLICY),
        keys=tuple(keys),
        selected_count=len(keys),
        changed_count=changed,
        unchanged_count=len(keys) - changed,
        excluded_by_status=tuple(excluded),
        planned_at="2026-10-31T00:00:00+00:00",
    )


class _FakeBatchService:
    def __init__(
        self,
        *,
        plan: KeyBatchPlan | None = None,
        plan_error: BaseException | None = None,
        apply_result: Any | None = None,
        apply_error: BaseException | None = None,
    ) -> None:
        self.plan_calls: list[dict[str, Any]] = []
        self.apply_calls: list[dict[str, Any]] = []
        self._plan = plan
        self._plan_error = plan_error
        self._apply_result = apply_result
        self._apply_error = apply_error

    async def plan(self, **kwargs: Any) -> KeyBatchPlan:
        self.plan_calls.append(kwargs)
        if self._plan_error is not None:
            raise self._plan_error
        assert self._plan is not None
        return self._plan

    async def apply(self, **kwargs: Any) -> Any:
        self.apply_calls.append(kwargs)
        if self._apply_error is not None:
            raise self._apply_error
        assert self._apply_result is not None
        return self._apply_result


class _RowcountResult:
    rowcount = 1

    def all(self):
        return []

    def first(self):
        return None

    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self


class _RowcountSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    def begin(self) -> "_RowcountSession":
        return self

    async def execute(self, *args: Any, **kwargs: Any) -> _RowcountResult:
        return _RowcountResult()


class _RowcountSessionmaker:
    def __call__(self) -> _RowcountSession:
        return _RowcountSession()


def _batch_result(status: str = "applied") -> _FakeBatchResult:
    return _FakeBatchResult(
        status=status,
        selected_count=2,
        changed_count=2,
        unchanged_count=0,
        key_ids=KEYS_SORTED,
    )


class _FakeBatchResult:
    def __init__(self, **fields: Any) -> None:
        for name, value in fields.items():
            setattr(self, name, value)


@pytest.fixture()
def batch_client(monkeypatch):
    """Real app + stubbed auth; KeyBatchService swapped per test."""
    settings = _settings()
    app = _app(settings)
    app.state.db_sessionmaker = _RowcountSessionmaker()

    admin_user = AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="argon2-hash",
        role="admin",
        is_active=True,
    )
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="sha256:session",
        csrf_token_hash="sha256:csrf",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user

    async def validate_admin_session(self, **kwargs: Any) -> AdminSessionContext:
        return AdminSessionContext(
            admin_user=admin_user, admin_session=admin_session
        )

    def verify_session_csrf_token(self, admin_session_, csrf_token):
        return csrf_token == "dashboard-csrf"

    monkeypatch.setattr(
        AdminSessionService, "validate_admin_session", validate_admin_session
    )
    monkeypatch.setattr(
        AdminSessionService, "verify_session_csrf_token", verify_session_csrf_token
    )
    client = TestClient(app)
    client.cookies.set("slaif_admin_session", "session-plaintext")
    return SimpleNamespaceHolder(
        client=client,
        settings=settings,
        admin_user=admin_user,
        admin_session=admin_session,
        monkeypatch=monkeypatch,
    )


class SimpleNamespaceHolder:
    """Tiny namespace so fixtures can share state without SimpleNamespace
    import noise at call sites."""

    def __init__(self, **fields: Any) -> None:
        for name, value in fields.items():
            setattr(self, name, value)


def install_fake(
    env: SimpleNamespaceHolder,
    *,
    plan: KeyBatchPlan | None = None,
    plan_error: BaseException | None = None,
    apply_result: Any | None = None,
    apply_error: BaseException | None = None,
) -> _FakeBatchService:
    fake = _FakeBatchService(
        plan=plan,
        plan_error=plan_error,
        apply_result=apply_result,
        apply_error=apply_error,
    )
    env.monkeypatch.setattr(batch, "KeyBatchService", lambda **kw: fake)
    return fake


def plan_fields(
    *,
    input_mode: str = "guided",
    selection_kind: str = "cohort",
    cohort_id: str = str(COHORT_ID),
    key_ids: str = "",
    status_active: str | None = "true",
    status_suspended: str | None = None,
    status_revoked: str | None = None,
    **overrides: Any,
) -> dict[str, str]:
    fields: dict[str, str] = {
        "csrf_token": "dashboard-csrf",
        "input_mode": input_mode,
        "selection_kind": selection_kind,
        "cohort_id": cohort_id,
        "key_ids": key_ids,
        "cost_action": "unchanged",
        "cost_value": "",
        "token_action": "unchanged",
        "token_value": "",
        "request_action": "unchanged",
        "request_value": "",
        "rate_action_requests": "unchanged",
        "rate_value_requests": "",
        "rate_action_tokens": "unchanged",
        "rate_value_tokens": "",
        "rate_action_concurrency": "unchanged",
        "rate_value_concurrency": "",
        "rate_action_window": "unchanged",
        "rate_value_window": "",
        "providers_mode": "unchanged",
        "providers_value": "",
        "models_mode": "unchanged",
        "models_value": "",
        "endpoints_mode": "unchanged",
        "endpoints_value": "",
        "lazy_mode": "unchanged",
        "lazy_wait_seconds": "",
        "lazy_waiting": "",
        "live_burn_mode": "unchanged",
        "live_burn_cost_margin": "",
        "live_burn_token_margin": "",
        "configuration_json": "",
    }
    # Real browser behavior: an UNCHECKED status box submits nothing, so a
    # None member omits the key from the payload entirely. Explicit "" is
    # still available to parser-only cases that must exercise present-but-
    # empty values.
    for name, value in (
        ("status_active", status_active),
        ("status_suspended", status_suspended),
        ("status_revoked", status_revoked),
    ):
        if value is not None:
            fields[name] = value
    fields.update(overrides)
    return fields


def extract_token(html: str) -> str:
    match = re.search(r'name="batch_review_intent" value="([^"]+)"', html)
    assert match is not None, "review token input missing"
    return match.group(1)


# The bare default form is intentionally change-free (the input-source law
# refuses no-change plans); flow tests that must REACH the service compose
# one minimal policy change.
POLICY_CHANGE = {"cost_action": "set", "cost_value": "5.00"}

# ---------------------------------------------------------------------------
# Guided/advanced input source law (pure helper)
# ---------------------------------------------------------------------------


def test_advanced_document_request_limit_total_parses() -> None:
    # Root probe regression: advanced JSON quota must parse (per-tuple
    # unpacking fix); the service stays authoritative for validity.
    config = batch._parse_batch_input_source(
        plan_fields(
            input_mode="advanced",
            configuration_json='{"schema_version": 1, "request_limit_total": 2000}',
        ),
        _settings(),
    )
    assert config.request_limit_total == 2000
    assert config.has("cost_limit_eur") is False


def test_advanced_requires_nonempty_document() -> None:
    with pytest.raises(ValueError, match="configuration document"):
        batch._parse_batch_input_source(
            plan_fields(input_mode="advanced", configuration_json=""),
            _settings(),
        )


def test_advanced_refuses_empty_policy_document() -> None:
    with pytest.raises(ValueError, match="no key configuration change"):
        batch._parse_batch_input_source(
            plan_fields(
                input_mode="advanced",
                configuration_json='{"schema_version": 1}',
            ),
            _settings(),
        )


def test_advanced_refuses_nondefault_guided_controls() -> None:
    with pytest.raises(ValueError, match="configuration document"):
        batch._parse_batch_input_source(
            plan_fields(
                input_mode="advanced",
                configuration_json='{"schema_version": 1, "request_limit_total": 1}',
                request_action="set",
            ),
            _settings(),
        )


def test_advanced_refuses_blank_guided_value_fields() -> None:
    with pytest.raises(ValueError, match="configuration document"):
        batch._parse_batch_input_source(
            plan_fields(
                input_mode="advanced",
                configuration_json='{"schema_version": 1, "request_limit_total": 1}',
                cost_value="5",
            ),
            _settings(),
        )


def test_guided_refuses_nonblank_document() -> None:
    with pytest.raises(ValueError, match="configuration document blank"):
        batch._parse_batch_input_source(
            plan_fields(
                input_mode="guided",
                configuration_json='{"schema_version": 1, "request_limit_total": 1}',
            ),
            _settings(),
        )


def test_guided_refuses_empty_policy() -> None:
    with pytest.raises(ValueError, match="at least one policy change"):
        batch._parse_batch_input_source(
            plan_fields(),
            _settings(),
        )


# ---------------------------------------------------------------------------
# List-mode vocabulary (root probe regression)
# ---------------------------------------------------------------------------


def test_providers_mode_all_is_refused_not_crash() -> None:
    # Root probe regression: per-field finite vocabulary; "all" is not a
    # provider mode (previously an UnboundLocalError).
    with pytest.raises(ValueError, match="valid provider mode"):
        batch._parse_batch_input_source(
            plan_fields(providers_mode="all"),
            _settings(),
        )


def test_models_and_endpoints_refuse_unrestricted() -> None:
    for fields in (
        plan_fields(models_mode="unrestricted"),
        plan_fields(endpoints_mode="unrestricted"),
    ):
        with pytest.raises(ValueError):
            batch._parse_batch_input_source(
                fields, _settings()
            )


def test_providers_modes_compose_config() -> None:
    settings = _settings()
    unrestricted = batch._parse_batch_input_source(
        plan_fields(providers_mode="unrestricted"), settings
    )
    assert unrestricted.allowed_providers is None
    deny_all = batch._parse_batch_input_source(
        plan_fields(providers_mode="deny_all"), settings
    )
    assert deny_all.allowed_providers == []
    allow_list = batch._parse_batch_input_source(
        plan_fields(providers_mode="allow_list", providers_value="openai\nopenrouter"),
        settings,
    )
    assert allow_list.allowed_providers == ["openai", "openrouter"]


def test_models_all_sets_flag_with_empty_list() -> None:
    config = batch._parse_batch_input_source(
        plan_fields(models_mode="all"), _settings()
    )
    assert config.allow_all_models is True
    assert config.allowed_models == []


def test_models_deny_all_sends_empty_list_flag_false() -> None:
    config = batch._parse_batch_input_source(
        plan_fields(models_mode="deny_all"), _settings()
    )
    assert config.allow_all_models is False
    assert config.allowed_models == []


def test_endpoints_allow_list() -> None:
    config = batch._parse_batch_input_source(
        plan_fields(
            endpoints_mode="allow_list",
            endpoints_value="/v1/models,/v1/chat/completions",
        ),
        _settings(),
    )
    assert config.allow_all_endpoints is False
    assert config.allowed_endpoints == ["/v1/models", "/v1/chat/completions"]


def test_list_mode_with_value_mismatch_refused() -> None:
    with pytest.raises(ValueError, match="needs no list"):
        batch._parse_batch_input_source(
            plan_fields(
                providers_mode="deny_all", providers_value="openai"
            ),
            _settings(),
        )


def test_provider_credential_shape_refused() -> None:
    with pytest.raises(ValueError, match="credential"):
        batch._parse_batch_input_source(
            plan_fields(
                providers_mode="allow_list", providers_value=CANARY_PROVIDER
            ),
            _settings(),
        )


# ---------------------------------------------------------------------------
# Quota / rate member composition semantics
# ---------------------------------------------------------------------------


def test_quota_set_clear_unchanged_semantics() -> None:
    config = batch._parse_batch_input_source(
        plan_fields(
            cost_action="set",
            cost_value="12.34",
            token_action="clear",
            request_action="set",
            request_value="0",
        ),
        _settings(),
    )
    assert config.cost_limit_eur == Decimal("12.34")
    assert config.has("cost_limit_eur")
    assert config.token_limit_total is None
    assert config.request_limit_total == 0
    assert config.has("request_limit_total")


def test_quota_value_with_unchanged_refused() -> None:
    with pytest.raises(ValueError, match="leave its value blank"):
        batch._parse_batch_input_source(
            plan_fields(cost_action="unchanged", cost_value="5"),
            _settings(),
        )


def test_quota_invalid_value_refused() -> None:
    for raw in ("abc", "-1", "NaN", "Infinity"):
        with pytest.raises(ValueError):
            batch._parse_batch_input_source(
                plan_fields(cost_action="set", cost_value=raw),
                _settings(),
            )


def test_rate_member_mapping() -> None:
    config = batch._parse_batch_input_source(
        plan_fields(
            rate_action_requests="set",
            rate_value_requests="10",
            rate_action_tokens="clear",
            rate_action_window="set",
            rate_value_window="3600",
        ),
        _settings(),
    )
    assert config.rate_limit_policy == {
        "requests_per_minute": 10,
        "tokens_per_minute": None,
        "window_seconds": 3600,
    }
    assert config.has("rate_limit_policy")


def test_rate_all_unchanged_omits_block() -> None:
    config = batch._parse_batch_input_source(
        plan_fields(cost_action="clear"),
        _settings(),
    )
    assert config.has("rate_limit_policy") is False


def test_rate_all_cleared_clears_whole_block() -> None:
    config = batch._parse_batch_input_source(
        plan_fields(
            rate_action_requests="clear",
            rate_action_tokens="clear",
            rate_action_concurrency="clear",
            rate_action_window="clear",
        ),
        _settings(),
    )
    assert config.rate_limit_policy is None


def test_rate_zero_or_noninteger_refused() -> None:
    for raw in ("0", "2.5", "ten"):
        with pytest.raises(ValueError, match="positive whole numbers"):
            batch._parse_batch_input_source(
                plan_fields(rate_action_requests="set", rate_value_requests=raw),
                _settings(),
            )


def test_lazy_wait_requires_both_positive_values() -> None:
    with pytest.raises(ValueError, match="both a max wait"):
        batch._parse_batch_input_source(
            plan_fields(lazy_mode="wait", lazy_wait_seconds="30"),
            _settings(),
        )
    config = batch._parse_batch_input_source(
        plan_fields(
            lazy_mode="wait", lazy_wait_seconds="30", lazy_waiting="4"
        ),
        _settings(),
    )
    assert config.lazy_throttling_policy == {
        "mode": "wait",
        "max_wait_seconds": 30,
        "max_waiting_requests": 4,
    }


def test_lazy_reject_and_remove() -> None:
    reject = batch._parse_batch_input_source(
        plan_fields(lazy_mode="reject"), _settings()
    )
    assert reject.lazy_throttling_policy == {"mode": "reject"}
    removed = batch._parse_batch_input_source(
        plan_fields(lazy_mode="remove"), _settings()
    )
    assert removed.lazy_throttling_policy is None


# ---------------------------------------------------------------------------
# Selection and status parsing (pure helper)
# ---------------------------------------------------------------------------


def test_selection_cohort_only() -> None:
    selection = batch._parse_batch_selection(plan_fields())
    assert selection["kind"] == "cohort"
    assert selection["cohort_id"] == COHORT_ID
    assert selection["key_ids"] == ()


def test_selection_keys_basic() -> None:
    selection = batch._parse_batch_selection(
        plan_fields(selection_kind="keys", cohort_id="", key_ids=f"{K1}\n{K2}")
    )
    assert selection["kind"] == "keys"
    assert selection["cohort_id"] is None
    assert selection["key_ids"] == (K1, K2) or selection["key_ids"] == (K2, K1)


def test_selection_exactly_one_source() -> None:
    with pytest.raises(ValueError, match="clear the cohort field"):
        batch._parse_batch_selection(
            plan_fields(selection_kind="keys", key_ids=str(K1))
        )
    with pytest.raises(ValueError, match="clear the key list"):
        batch._parse_batch_selection(
            plan_fields(key_ids=str(K1))
        )


def test_selection_malformed_duplicate_overflow_refused() -> None:
    base = plan_fields(selection_kind="keys", cohort_id="")
    with pytest.raises(ValueError, match="invalid key identifier"):
        batch._parse_batch_selection({**base, "key_ids": "not-a-uuid"})
    with pytest.raises(ValueError, match="duplicate"):
        batch._parse_batch_selection(
            {**base, "key_ids": f"{K1}\n{K1}"}
        )
    overflow = "\n".join(str(uuid.uuid4()) for _ in range(KEY_BATCH_MAX_KEYS + 1))
    with pytest.raises(ValueError, match="bounded key count"):
        batch._parse_batch_selection({**base, "key_ids": overflow})


def test_selection_full_1000_accepted() -> None:
    ids = tuple(uuid.uuid4() for _ in range(KEY_BATCH_MAX_KEYS))
    selection = batch._parse_batch_selection(
        plan_fields(
            selection_kind="keys", cohort_id="", key_ids="\n".join(map(str, ids))
        )
    )
    assert len(selection["key_ids"]) == KEY_BATCH_MAX_KEYS


def test_statuses_parsing() -> None:
    assert batch._parse_batch_statuses(plan_fields()) == ("active",)
    assert (
        batch._parse_batch_statuses(
            plan_fields(status_active="", status_suspended="true")
        )
        == ("suspended",)
    )
    # Omitted keys (real unchecked boxes) and present-but-empty keys are
    # both refusals at the parser.
    omitted = {
        k: v for k, v in plan_fields().items() if not k.startswith("status_")
    }
    with pytest.raises(ValueError, match="at least one persisted status"):
        batch._parse_batch_statuses(omitted)
    with pytest.raises(ValueError, match="at least one persisted status"):
        batch._parse_batch_statuses(
            plan_fields(status_active="", status_suspended="", status_revoked="")
        )


# ---------------------------------------------------------------------------
# Fenced confirmation gate (explicit-input-only law)
# ---------------------------------------------------------------------------


def test_fenced_gate_explicit_policy_requires_confirmation() -> None:
    plan = _make_plan(policy={"schema_version": 1, "request_limit_total": 1, "external_tool_policy": dict(FENCED_BLOCK)})
    assert batch._batch_requires_fenced_confirmation(render_key_batch_plan(plan)) is True


def test_fenced_gate_retained_after_target_only_does_not() -> None:
    # Root correction: the shared law requires the fresh confirmation only
    # when the SUBMITTED configuration explicitly carries external_tool
    # policy; a retained fenced after-target (quota-only edit) does not.
    fenced_after = {
        "schema_version": 1,
        "request_limit_total": 2000,
        "external_tool_policy": dict(FENCED_BLOCK),
    }
    plan = _make_plan(
        policy={"schema_version": 1, "request_limit_total": 2000},
        before={"schema_version": 1, "request_limit_total": 1000, "external_tool_policy": dict(FENCED_BLOCK)},
        after=fenced_after,
    )
    assert batch._batch_requires_fenced_confirmation(render_key_batch_plan(plan)) is False


def test_fenced_gate_null_block_does_not() -> None:
    plan = _make_plan(
        policy={"schema_version": 1, "request_limit_total": 1, "external_tool_policy": None}
    )
    assert batch._batch_requires_fenced_confirmation(render_key_batch_plan(plan)) is False


# ---------------------------------------------------------------------------
# Batch review-intent token (purpose-bound, bounded, never echoed)
# ---------------------------------------------------------------------------


def test_batch_token_round_trip() -> None:
    admin_id = uuid.uuid4()
    session_id = uuid.uuid4()
    plan_doc = render_key_batch_plan(_make_plan())
    token = intent.build_batch_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=admin_id,
        admin_session_id=session_id,
        plan_document=plan_doc,
    )
    assert intent.verify_batch_review_token(
        admin_session_secret="s" * 40,
        token=token,
        admin_user_id=admin_id,
        admin_session_id=session_id,
    ) == plan_doc


def test_batch_token_wrong_secret_refused() -> None:
    admin_id = uuid.uuid4()
    session_id = uuid.uuid4()
    plan_doc = render_key_batch_plan(_make_plan())
    token = intent.build_batch_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=admin_id,
        admin_session_id=session_id,
        plan_document=plan_doc,
    )
    with pytest.raises(intent.AdminReviewIntentError) as excinfo:
        intent.verify_batch_review_token(
            admin_session_secret="t" * 40,
            token=token,
            admin_user_id=admin_id,
            admin_session_id=session_id,
        )
    assert excinfo.value.message == intent._BATCH_NOT_AUTHENTIC_MESSAGE
    assert token not in excinfo.value.message


def test_batch_token_cross_purpose_clone_token_refused() -> None:
    # A 208 clone-purpose token is never valid for a batch apply.
    # A VALID strict clone plan document (208 shared fixture) bound through
    # the clone-purpose builder: the batch verifier must refuse it.
    clone_doc = _clone_plan_document()
    admin_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token = intent.build_review_intent_token(
        admin_session_secret="s" * 40,
        admin_user_id=admin_id,
        admin_session_id=session_id,
        plan_document=clone_doc,
        delivery_mode="none",
    )
    with pytest.raises(intent.AdminReviewIntentError) as excinfo:
        intent.verify_batch_review_token(
            admin_session_secret="s" * 40,
            token=token,
            admin_user_id=admin_id,
            admin_session_id=session_id,
        )
    assert excinfo.value.message == intent._BATCH_NOT_AUTHENTIC_MESSAGE


def test_batch_token_wrong_actor_session_refused() -> None:
    plan_doc = render_key_batch_plan(_make_plan())
    token = intent.build_batch_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=uuid.uuid4(),
        admin_session_id=uuid.uuid4(),
        plan_document=plan_doc,
    )
    with pytest.raises(intent.AdminReviewIntentError):
        intent.verify_batch_review_token(
            admin_session_secret="s" * 40,
            token=token,
            admin_user_id=uuid.uuid4(),
            admin_session_id=uuid.uuid4(),
        )


def test_batch_token_expired_refused() -> None:
    plan_doc = render_key_batch_plan(_make_plan())
    admin_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token = intent.build_batch_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=admin_id,
        admin_session_id=session_id,
        plan_document=plan_doc,
        ttl_seconds=-1,
    )
    with pytest.raises(intent.AdminReviewIntentError) as excinfo:
        intent.verify_batch_review_token(
            admin_session_secret="s" * 40,
            token=token,
            admin_user_id=admin_id,
            admin_session_id=session_id,
        )
    assert "expired" in excinfo.value.message


def test_batch_token_tampered_refused() -> None:
    plan_doc = render_key_batch_plan(_make_plan())
    token = intent.build_batch_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=uuid.uuid4(),
        admin_session_id=uuid.uuid4(),
        plan_document=plan_doc,
    )
    body, dot, digest = token.rpartition(".")
    tampered = body[:-4] + ("AAAA" if body[-4:] != "AAAA" else "BBBB") + dot + digest
    with pytest.raises(intent.AdminReviewIntentError):
        intent.verify_batch_review_token(
            admin_session_secret="s" * 40,
            token=tampered,
            admin_user_id=uuid.uuid4(),
            admin_session_id=uuid.uuid4(),
        )


def test_batch_token_malformed_formats_refused() -> None:
    for bad in (None, "", "nodothere", "aaa", "...."):
        with pytest.raises(intent.AdminReviewIntentError):
            intent.verify_batch_review_token(
                admin_session_secret="s" * 40,
                token=bad,
                admin_user_id=uuid.uuid4(),
                admin_session_id=uuid.uuid4(),
            )


def test_batch_token_oversize_refused_fixed_message() -> None:
    with pytest.raises(intent.AdminReviewIntentError) as excinfo:
        intent.verify_batch_review_token(
            admin_session_secret="s" * 40,
            token="A" * (intent.MAX_REVIEW_INTENT_BATCH_TOKEN_CHARS + 1),
            admin_user_id=uuid.uuid4(),
            admin_session_id=uuid.uuid4(),
        )
    assert excinfo.value.message == intent._BATCH_INVALID_MESSAGE


def test_batch_token_oversize_plan_refused(monkeypatch) -> None:
    # The builder's decoded-plan bound fires with the fixed safe message.
    monkeypatch.setattr(intent, "KEY_BATCH_PLAN_MAX_BYTES", 10)
    with pytest.raises(intent.AdminReviewIntentError) as excinfo:
        intent.build_batch_review_token(
            admin_session_secret="s" * 40,
            admin_user_id=uuid.uuid4(),
            admin_session_id=uuid.uuid4(),
            plan_document=render_key_batch_plan(_make_plan()),
        )
    assert excinfo.value.message == intent._BATCH_TOO_LARGE_MESSAGE


# ---------------------------------------------------------------------------
# HTTP: form page + entry discoverability
# ---------------------------------------------------------------------------


def test_form_page_renders(batch_client) -> None:
    install_fake(batch_client, plan=_make_plan())
    response = batch_client.client.get("/admin/key-batch")
    assert response.status_code == 200
    text = response.text
    assert "Change Existing Keys" in text
    # Searchable record-choice controls with the documented kinds.
    assert 'data-kind="cohort"' in text
    assert 'data-kind="key"' in text
    assert 'data-kind="policy_provider"' in text
    assert 'data-kind="policy_model"' in text
    assert 'data-kind="endpoint"' in text
    # Batch-opt-in hydration cap on the key picker only.
    assert 'data-rc-hydrate-cap="100"' in text
    # The max_keys label is evaluated, not a literal template fragment.
    assert "{{ max_keys" not in text
    assert "1,000" in text
    # Each batch picker links its visible field to its OWN help span:
    # the id resolves exactly once and is referenced exactly once.
    for help_id in (
        "batch-help-cohort",
        "batch-help-keys",
        "batch-help-providers",
        "batch-help-models",
        "batch-help-endpoints",
    ):
        assert text.count(f'id="{help_id}"') == 1, f"help span {help_id} missing"
        assert text.count(f'aria-describedby="{help_id}"') == 1, (
            f"help {help_id} not linked from the visible field"
        )


def test_list_page_has_entry_link(batch_client) -> None:
    install_fake(batch_client, plan=_make_plan())
    response = batch_client.client.get("/admin/keys")
    assert response.status_code == 200
    assert 'href="/admin/key-batch"' in response.text
    assert "Change existing keys" in response.text


def test_unauthenticated_form_redirects(batch_client) -> None:
    install_fake(batch_client, plan=_make_plan())
    client = batch_client.client
    client.cookies.clear()
    response = client.get("/admin/key-batch", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


# ---------------------------------------------------------------------------
# HTTP: plan flow + review rendering
# ---------------------------------------------------------------------------


def test_plan_flow_review_rendering(batch_client) -> None:
    # Excluded entries are only legal for an EXPLICIT KEYS selection (the
    # strict parser refuses them on cohort selections); the excluded key is
    # outside the selected set and its status outside the filter.
    fake = install_fake(
        batch_client,
        plan=_make_plan(
            cohort_id=None,
            excluded=((str(EXCLUDED_K1), "suspended"),),
        ),
    )
    response = batch_client.client.post(
        "/admin/key-batch/plan",
        data=plan_fields(token_action="set", token_value="2000000", request_action="clear"),
    )
    assert response.status_code == 200
    token = extract_token(response.text)
    assert token
    text = response.text
    # No-store on the signed review state.
    assert "no-store" in response.headers.get("cache-control", "")
    # Readable review: ordinal, key links, grouped/M display, null labels.
    assert 'class="row-ordinal"' in text
    assert f'href="/admin/keys/{KEYS_SORTED[0]}"' in text
    assert "2M tokens (2,000,000 exact)" in text
    assert "Unlimited (null)" in text
    assert "1,000" in text  # grouped request before
    # Excluded entries render as real UUID/status, not dict keys.
    assert str(EXCLUDED_K1) in text
    assert "suspended" in text
    # The old bug unpacked the rendered dicts and printed the literal
    # key names <code>key_id</code>/<code>status</code> instead.
    assert "<code>key_id</code>" not in text
    assert "<code>status</code>" not in text
    # Raw plan JSON disclosure present.
    assert "Raw non-secret plan JSON" in text
    # The apply INPUTS (not just labels) carry linked meaningful help:
    # reason purpose + the stored 512-UTF-8-byte bound + fresh fenced
    # acknowledgement + ordinary-repeat semantics.
    assert text.count('id="batch-apply-help"') == 1
    # confirm + reason (no fenced box for this non-fenced plan).
    assert text.count('aria-describedby="batch-apply-help"') == 2
    assert "512 UTF-8 bytes" in text
    assert "fenced confirmation checkbox" in text
    # Service saw the composed configuration.
    call = fake.plan_calls[0]
    policy: KeyConfiguration = call["policy"]
    assert policy.token_limit_total == 2000000
    assert policy.request_limit_total is None
    assert policy.has("rate_limit_policy") is False
    assert call["statuses"] == ("active",)
    assert call["cohort_id"] == COHORT_ID
    assert call["key_ids"] == ()
    # Token binds this plan strictly.
    assert parse_key_batch_plan(intent.verify_batch_review_token(
        admin_session_secret=batch_client.settings.ADMIN_SESSION_SECRET,
        token=token,
        admin_user_id=batch_client.admin_user.id,
        admin_session_id=batch_client.admin_session.id,
    ))


def test_plan_key_selection_passes_uuids(batch_client) -> None:
    fake = install_fake(batch_client, plan=_make_plan())
    response = batch_client.client.post(
        "/admin/key-batch/plan",
        data=plan_fields(
            selection_kind="keys",
            cohort_id="",
            key_ids=f"{K1},{K2}",
            **POLICY_CHANGE,
        ),
    )
    assert response.status_code == 200
    call = fake.plan_calls[0]
    assert call["cohort_id"] is None
    assert set(call["key_ids"]) == {K1, K2}


def test_plan_suspended_only_status(batch_client) -> None:
    # Real browser payload: ONLY the checked box is present. An absent
    # status_active key must not be read as checked (the old Form(true)
    # default bug would pass if an explicit "" were posted instead).
    fake = install_fake(batch_client, plan=_make_plan())
    payload = plan_fields(
        status_active=None, status_suspended="true", **POLICY_CHANGE
    )
    assert "status_active" not in payload
    assert "status_revoked" not in payload
    response = batch_client.client.post(
        "/admin/key-batch/plan", data=payload
    )
    assert response.status_code == 200
    assert fake.plan_calls[0]["statuses"] == ("suspended",)


def test_plan_revoked_only_status(batch_client) -> None:
    fake = install_fake(batch_client, plan=_make_plan())
    payload = plan_fields(
        status_active=None, status_revoked="true", **POLICY_CHANGE
    )
    assert "status_active" not in payload
    assert "status_suspended" not in payload
    response = batch_client.client.post(
        "/admin/key-batch/plan", data=payload
    )
    assert response.status_code == 200
    assert fake.plan_calls[0]["statuses"] == ("revoked",)


def test_plan_no_status_refused_before_service(batch_client) -> None:
    fake = install_fake(batch_client, plan=_make_plan())
    payload = plan_fields(
        status_active=None,
        status_suspended=None,
        status_revoked=None,
        **POLICY_CHANGE,
    )
    assert "status_active" not in payload
    assert "status_suspended" not in payload
    assert "status_revoked" not in payload
    response = batch_client.client.post(
        "/admin/key-batch/plan", data=payload
    )
    assert response.status_code == 400
    assert "at least one persisted status" in response.text
    assert fake.plan_calls == []


def test_plan_invalid_csrf_refused_before_service(batch_client) -> None:
    fake = install_fake(batch_client, plan=_make_plan())
    response = batch_client.client.post(
        "/admin/key-batch/plan", data=plan_fields(csrf_token="wrong")
    )
    assert response.status_code == 400
    assert "Invalid CSRF token" in response.text
    assert fake.plan_calls == []


def test_plan_key_batch_error_actionable(batch_client) -> None:
    install_fake(
        batch_client,
        plan_error=KeyBatchError(
            "3 requested keys were not found.",
            error_code="key_batch_key_not_found",
        ),
    )
    response = batch_client.client.post(
        "/admin/key-batch/plan", data=plan_fields(**POLICY_CHANGE)
    )
    assert response.status_code == 400
    assert "3 requested keys were not found." in response.text
    assert "try again" not in response.text


def test_plan_key_management_error_safe_message(batch_client) -> None:
    install_fake(
        batch_client,
        plan_error=KeyManagementError(
            "A selected key does not allow the requested model."
        ),
    )
    response = batch_client.client.post(
        "/admin/key-batch/plan", data=plan_fields(**POLICY_CHANGE)
    )
    assert response.status_code == 400
    assert "does not allow the requested model" in response.text


def test_plan_gateway_key_not_found_is_404_free_refusal(batch_client) -> None:
    install_fake(
        batch_client,
        plan_error=GatewayKeyNotFoundError("key vanished"),
    )
    response = batch_client.client.post(
        "/admin/key-batch/plan", data=plan_fields(**POLICY_CHANGE)
    )
    assert response.status_code == 400


def test_plan_oversize_generated_plan_fixed_refusal(monkeypatch, batch_client) -> None:
    # A plan whose canonical bytes exceed the core budget is a fixed safe
    # refusal, never a 500.
    monkeypatch.setattr(intent, "KEY_BATCH_PLAN_MAX_BYTES", 10)
    install_fake(batch_client, plan=_make_plan())
    response = batch_client.client.post(
        "/admin/key-batch/plan", data=plan_fields(**POLICY_CHANGE)
    )
    assert response.status_code == 400
    assert intent._BATCH_TOO_LARGE_MESSAGE in response.text


def test_plan_provider_credential_canary_absent(batch_client) -> None:
    install_fake(batch_client, plan=_make_plan())
    response = batch_client.client.post(
        "/admin/key-batch/plan",
        data=plan_fields(providers_mode="allow_list", providers_value=CANARY_PROVIDER),
    )
    assert response.status_code == 400
    present = CANARY_PROVIDER in response.text
    assert present is False, "credential-shaped provider reflected"


def test_plan_advanced_password_canary_blanked_on_rerender(batch_client) -> None:
    # Root probe regression: an unknown-field JSON password is refused by
    # the strict parser and must NOT be redisplayed in the form.
    bad_doc = (
        '{"schema_version": 1, "request_limit_total": 5, '
        f'"password": "{CANARY_PASSWORD}"'
    )
    install_fake(
        batch_client,
        plan_error=KeyBatchError(
            "policy: The reviewed policy is not a valid version-1 "
            "configuration document.",
            error_code="key_batch_plan",
        ),
    )
    response = batch_client.client.post(
        "/admin/key-batch/plan",
        data=plan_fields(
            input_mode="advanced",
            configuration_json=bad_doc,
        ),
    )
    assert response.status_code == 400
    present = CANARY_PASSWORD in response.text
    assert present is False, "advanced document credential reflected"
    # Safe scope retained on the rerender.
    assert str(COHORT_ID) in response.text


def test_plan_guided_canary_credential_in_models_absent(batch_client) -> None:
    install_fake(batch_client, plan=_make_plan())
    response = batch_client.client.post(
        "/admin/key-batch/plan",
        data=plan_fields(models_mode="allow_list", models_value=CANARY_KEY),
    )
    assert response.status_code == 400
    present = CANARY_KEY in response.text
    assert present is False


# ---------------------------------------------------------------------------
# HTTP: apply flow
# ---------------------------------------------------------------------------


def test_apply_flow_result_and_token_not_retained(batch_client) -> None:
    install_fake(batch_client, plan=_make_plan())
    review = batch_client.client.post(
        "/admin/key-batch/plan",
        data=plan_fields(token_action="set", token_value="2000000"),
    )
    token = extract_token(review.text)
    fake = install_fake(
        batch_client,
        plan=_make_plan(),
        apply_result=_batch_result("applied"),
    )
    response = batch_client.client.post(
        "/admin/key-batch/apply",
        data={
            "csrf_token": "dashboard-csrf",
            "batch_review_intent": token,
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": "Batch quota reset for workshop cohort",
        },
    )
    assert response.status_code == 200
    assert "no-store" in response.headers.get("cache-control", "")
    text = response.text
    assert "applied" in text
    retained = token in text
    assert retained is False, "review token retained on result page"
    call = fake.apply_calls[0]
    assert call["reason"] == "Batch quota reset for workshop cohort"
    assert call["actor_admin_id"] == batch_client.admin_user.id
    assert call["confirm_external_tool_fenced"] is False
    assert call["plan"].key_ids == KEYS_SORTED


def test_apply_empty_token_fixed_refusal_no_500(batch_client) -> None:
    fake = install_fake(batch_client, plan=_make_plan())
    response = batch_client.client.post(
        "/admin/key-batch/apply",
        data={
            "csrf_token": "dashboard-csrf",
            "batch_review_intent": "",
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": "r",
        },
    )
    assert response.status_code == 400
    assert "missing or invalid" in response.text
    assert fake.apply_calls == []


def test_apply_garbage_token_fixed_refusal_no_500(batch_client) -> None:
    install_fake(batch_client, plan=_make_plan())
    response = batch_client.client.post(
        "/admin/key-batch/apply",
        data={
            "csrf_token": "dashboard-csrf",
            "batch_review_intent": "garbage-token",
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": "r",
        },
    )
    assert response.status_code == 400
    assert "missing or invalid" in response.text


def test_apply_non_ascii_digest_refused(batch_client) -> None:
    install_fake(batch_client, plan=_make_plan())
    response = batch_client.client.post(
        "/admin/key-batch/apply",
        data={
            "csrf_token": "dashboard-csrf",
            "batch_review_intent": "abc\u00e9." + "ab" * 32,
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": "r",
        },
    )
    assert response.status_code == 400
    assert "missing or invalid" in response.text


def test_apply_missing_confirmation_refused(batch_client) -> None:
    install_fake(batch_client, plan=_make_plan())
    review = batch_client.client.post(
        "/admin/key-batch/plan", data=plan_fields(**POLICY_CHANGE)
    )
    token = extract_token(review.text)
    fake = install_fake(
        batch_client, plan=_make_plan(), apply_result=_batch_result()
    )
    response = batch_client.client.post(
        "/admin/key-batch/apply",
        data={
            "csrf_token": "dashboard-csrf",
            "batch_review_intent": token,
            "confirm_apply": "",
            "confirm_external_tool_fenced": "",
            "reason": "r",
        },
    )
    assert response.status_code == 400
    assert "Confirm the reviewed key batch plan" in response.text
    assert fake.apply_calls == []


def test_apply_missing_reason_refused(batch_client) -> None:
    install_fake(batch_client, plan=_make_plan())
    review = batch_client.client.post(
        "/admin/key-batch/plan", data=plan_fields(**POLICY_CHANGE)
    )
    token = extract_token(review.text)
    fake = install_fake(
        batch_client, plan=_make_plan(), apply_result=_batch_result()
    )
    response = batch_client.client.post(
        "/admin/key-batch/apply",
        data={
            "csrf_token": "dashboard-csrf",
            "batch_review_intent": token,
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": "",
        },
    )
    assert response.status_code == 400
    assert "audit reason" in response.text
    assert fake.apply_calls == []


def test_apply_fenced_plan_requires_fresh_confirmation(batch_client) -> None:
    fenced_policy = {
        "schema_version": 1,
        "request_limit_total": 1,
        "external_tool_policy": dict(FENCED_BLOCK),
    }
    install_fake(batch_client, plan=_make_plan(policy=fenced_policy))
    review = batch_client.client.post(
        "/admin/key-batch/plan", data=plan_fields(**POLICY_CHANGE)
    )
    assert response_is_fenced_banner(review)
    # The fenced checkbox INPUT exists with its linked help reference
    # (confirm + fenced + reason all describe the same help paragraph).
    assert 'id="batch-confirm-fenced"' in review.text
    assert review.text.count('aria-describedby="batch-apply-help"') == 3
    token = extract_token(review.text)
    fake = install_fake(
        batch_client, plan=_make_plan(policy=fenced_policy),
        apply_result=_batch_result(),
    )
    response = batch_client.client.post(
        "/admin/key-batch/apply",
        data={
            "csrf_token": "dashboard-csrf",
            "batch_review_intent": token,
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": "r",
        },
    )
    assert response.status_code == 400
    assert "fenced external-tool confirmation" in response.text
    assert fake.apply_calls == []
    # With the fresh confirmation the apply proceeds.
    response = batch_client.client.post(
        "/admin/key-batch/apply",
        data={
            "csrf_token": "dashboard-csrf",
            "batch_review_intent": token,
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "true",
            "reason": "r",
        },
    )
    assert response.status_code == 200
    assert fake.apply_calls[0]["confirm_external_tool_fenced"] is True


def response_is_fenced_banner(response) -> bool:
    return "Fenced external-tool policy" in response.text


def test_apply_stale_refusal_zero_writes_surface_fixed_message(batch_client) -> None:
    install_fake(batch_client, plan=_make_plan())
    review = batch_client.client.post(
        "/admin/key-batch/plan", data=plan_fields(**POLICY_CHANGE)
    )
    token = extract_token(review.text)
    from slaif_gateway.schemas.key_batch import KeyBatchStaleError

    install_fake(
        batch_client,
        plan=_make_plan(),
        apply_error=KeyBatchStaleError(
            "The reviewed pre-state no longer matches the live keys.",
            error_code="key_batch_stale",
        ),
    )
    response = batch_client.client.post(
        "/admin/key-batch/apply",
        data={
            "csrf_token": "dashboard-csrf",
            "batch_review_intent": token,
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": "r",
        },
    )
    assert response.status_code == 400
    assert "no longer matches the live keys" in response.text


def test_apply_reason_canary_not_reflected(batch_client) -> None:
    install_fake(batch_client, plan=_make_plan())
    review = batch_client.client.post(
        "/admin/key-batch/plan", data=plan_fields(**POLICY_CHANGE)
    )
    token = extract_token(review.text)
    install_fake(batch_client, plan=_make_plan(), apply_result=_batch_result())
    response = batch_client.client.post(
        "/admin/key-batch/apply",
        data={
            "csrf_token": "dashboard-csrf",
            "batch_review_intent": token,
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": f"reset {CANARY_KEY} for workshop",
        },
    )
    assert response.status_code == 200
    present = CANARY_KEY in response.text
    assert present is False, "credential-shaped reason reflected"


# ---------------------------------------------------------------------------
# Readable review rendering (pure helpers)
# ---------------------------------------------------------------------------


def test_readable_money_string_zero() -> None:
    # Canonical money snapshots are STRINGS; 0E-9 must render 0.
    assert batch._batch_config_value_readable("cost_limit_eur", "0E-9") == "0 (zero)"
    assert (
        batch._batch_config_value_readable("cost_limit_eur", "12.345000000")
        == "12.345"
    )


def test_readable_token_string_grouped() -> None:
    assert (
        batch._batch_config_value_readable("token_limit_total", "5000000")
        == "5M tokens (5,000,000 exact)"
    )


def test_readable_rate_policy_token_member_m_tokens() -> None:
    # Display contract: the tokens-per-window member renders through the
    # shared M-token display with the exact count beside it, while the
    # request/window members keep plain grouped formatting and null
    # members keep the inherit label.
    text = batch._batch_rate_policy_readable(
        {
            "requests_per_minute": 100,
            "tokens_per_minute": 2_000_000,
            "max_concurrent_requests": 4,
            "window_seconds": 10,
        }
    )
    assert "requests per window: 100" in text
    assert "tokens per window: 2M tokens (2,000,000 exact)" in text
    assert "concurrent requests: 4" in text
    assert "window (seconds): 10" in text
    partial = batch._batch_rate_policy_readable(
        {"tokens_per_minute": None, "window_seconds": 60}
    )
    assert "tokens per window: inherit (null)" in partial
    assert "window (seconds): 60" in partial


def test_readable_null_labels() -> None:
    assert (
        batch._batch_config_value_readable("cost_limit_eur", None)
        == "Unlimited (null)"
    )
    assert (
        batch._batch_config_value_readable("allowed_providers", None)
        == "Unrestricted (null)"
    )
    assert (
        batch._batch_config_value_readable("rate_limit_policy", None)
        == "Cleared (null)"
    )
    assert (
        batch._batch_config_value_readable("lazy_throttling_policy", None)
        == "Removed (null) - deployment default applies"
    )


def test_readable_allow_all_empty_list_neutral() -> None:
    summary = batch._batch_policy_summary(
        {"schema_version": 1, "allow_all_models": True, "allowed_models": []}
    )
    assert summary["allow_all_models"] == "yes"
    assert summary["allowed_models"] == "empty list (the allow-all flag grants access)"
    deny = batch._batch_policy_summary(
        {"schema_version": 1, "allow_all_models": False, "allowed_models": []}
    )
    assert deny["allowed_models"] == "Deny all (empty list)"
    # A PARTIAL change document that omits the allow-all flag must not be
    # read as deny: the key's existing flag is preserved.
    partial = batch._batch_policy_summary(
        {"schema_version": 1, "allowed_models": []}
    )
    assert partial["allowed_models"] == (
        "empty list (the allow-all flag is not set by this change)"
    )
    partial_endpoints = batch._batch_policy_summary(
        {"schema_version": 1, "allowed_endpoints": []}
    )
    assert partial_endpoints["allowed_endpoints"] == (
        "empty list (the allow-all flag is not set by this change)"
    )
    # Providers keep deny-all semantics.
    providers = batch._batch_policy_summary(
        {"schema_version": 1, "allowed_providers": []}
    )
    assert providers["allowed_providers"] == "Deny all (empty list)"


def test_partial_policy_preserves_existing_allow_all_flag() -> None:
    # Core law (root probe): a partial policy {allowed_models: []} on a key
    # whose allow_all_models=True omits the flag and preserves the existing
    # flag in the after-document; the readable partial plan policy stays
    # neutral instead of claiming deny-all.
    cohort = uuid.uuid4()
    row = FakeGatewayKeyRow(
        cohort_id=cohort,
        status="active",
        allow_all_models=True,
        allowed_models=["legacy-model-a", "legacy-model-b"],
    )
    service, _, _, _ = _make_batch_service([row], cohort_id=cohort)
    plan = asyncio.run(
        service.plan(
            cohort_id=cohort,
            statuses=("active",),
            policy=parse_key_configuration(
                {"schema_version": 1, "allowed_models": []}
            ),
        )
    )
    assert plan.keys[0].after["allow_all_models"] is True
    assert plan.keys[0].after["allowed_models"] == []
    document = render_key_batch_plan(plan)
    summary = batch._batch_policy_summary(document["policy"])
    assert summary["allowed_models"] == (
        "empty list (the allow-all flag is not set by this change)"
    )


def test_quota_column_raw_keys_ungrouped_exact() -> None:
    # 64-bit adjacent counts: raw sort keys must be ungrouped exact
    # integers (grouped text would fall back to Number() and tie).
    a = 9007199254740993
    b = 9007199254740991
    text_a, raw_a = batch._batch_quota_column(
        {"request_limit_total": a}, "request_limit_total"
    )
    text_b, raw_b = batch._batch_quota_column(
        {"request_limit_total": b}, "request_limit_total"
    )
    assert text_a == "9,007,199,254,740,993"
    assert raw_a == str(a)
    assert raw_b == str(b)
    assert int(raw_a) > int(raw_b)


def test_quota_column_zero_null_missing() -> None:
    assert batch._batch_quota_column(
        {"token_limit_total": 0}, "token_limit_total"
    ) == ("0 (zero)", "0")
    text, raw = batch._batch_quota_column(
        {"request_limit_total": None}, "request_limit_total"
    )
    assert text == "Unlimited (null)"
    assert raw == ""
    text, raw = batch._batch_quota_column({}, "request_limit_total")
    assert text == "—"
    assert raw == ""


def test_quota_column_token_display() -> None:
    text, raw = batch._batch_quota_column(
        {"token_limit_total": 937826734}, "token_limit_total"
    )
    assert text == "937.827M tokens (937,826,734 exact)"
    assert raw == "937826734"


# ---------------------------------------------------------------------------
# Full-1000 transport round-trip
# ---------------------------------------------------------------------------


def _big_plan() -> KeyBatchPlan:
    ids = tuple(sorted(str(uuid.uuid4()) for _ in range(KEY_BATCH_MAX_KEYS)))
    before = {
        "schema_version": 1,
        "request_limit_total": 1000,
        "allowed_models": [f"model-token-{i:03d}" for i in range(60)],
    }
    after = {
        "schema_version": 1,
        "request_limit_total": 500,
        "allowed_models": [f"model-token-{i:03d}" for i in range(60, 120)],
    }
    keys = tuple(
        KeyBatchPlanKey(
            key_id=kid,
            source_fingerprint="ab" * 32,
            post_fingerprint="cd" * 32,
            before=dict(before),
            after=dict(after),
            changes=key_batch_document_changes(before, after),
        )
        for kid in ids
    )
    return KeyBatchPlan(
        schema_version=1,
        operation="apply",
        selection_kind="keys",
        cohort_id=None,
        key_ids=ids,
        statuses=("active",),
        policy={"schema_version": 1, "request_limit_total": 500},
        keys=keys,
        selected_count=len(keys),
        changed_count=len(keys),
        unchanged_count=0,
        excluded_by_status=(),
        planned_at="2026-10-31T00:00:00+00:00",
    )


def test_full_1000_plan_transport_round_trip(batch_client) -> None:
    plan = _big_plan()
    install_fake(batch_client, plan=plan, apply_result=None)
    response = batch_client.client.post(
        "/admin/key-batch/plan",
        data=plan_fields(
            selection_kind="keys",
            cohort_id="",
            key_ids="\n".join(plan.key_ids),
            request_action="set",
            request_value="500",
        ),
    )
    assert response.status_code == 200
    token = extract_token(response.text)
    # The token is bounded and strictly re-parses to the full plan.
    assert len(token) <= intent.MAX_REVIEW_INTENT_BATCH_TOKEN_CHARS
    document = intent.verify_batch_review_token(
        admin_session_secret=batch_client.settings.ADMIN_SESSION_SECRET,
        token=token,
        admin_user_id=batch_client.admin_user.id,
        admin_session_id=batch_client.admin_session.id,
    )
    parsed = parse_key_batch_plan(document)
    assert parsed.key_ids == plan.key_ids
    assert parsed.selected_count == KEY_BATCH_MAX_KEYS
    # The apply transport accepts the large body and reaches the service.
    fake = install_fake(
        batch_client, plan=plan, apply_result=_full_result(plan)
    )
    apply_response = batch_client.client.post(
        "/admin/key-batch/apply",
        data={
            "csrf_token": "dashboard-csrf",
            "batch_review_intent": token,
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": "Full-cohort workshop refresh",
        },
    )
    assert apply_response.status_code == 200
    assert len(fake.apply_calls) == 1
    # The service received the FULL strictly-parsed reviewed plan.
    applied = fake.apply_calls[0]["plan"]
    assert render_key_batch_plan(applied) == document
    assert list(applied.key_ids) == list(plan.key_ids)
    assert len(applied.key_ids) == KEY_BATCH_MAX_KEYS


def _full_result(plan: KeyBatchPlan) -> _FakeBatchResult:
    return _FakeBatchResult(
        status="applied",
        selected_count=len(plan.key_ids),
        changed_count=len(plan.key_ids),
        unchanged_count=0,
        key_ids=plan.key_ids,
    )


# ---------------------------------------------------------------------------
# Real-bound signed envelope (real Core plan, REAL 8 MiB bound: no
# monkeypatched limits)
# ---------------------------------------------------------------------------


def _fat_batch_plan(items_per_list: int) -> KeyBatchPlan:
    """Build a REAL reviewed 1000-key plan through Core + honest fakes.

    Every key carries individually bounded allow lists (<=100 items,
    <=256 chars each), so the rendered document size is a deterministic
    function of ``items_per_list``: 96 items lands just under the real
    8 MiB plan bound, 100 items just over it.
    """
    cohort = uuid.uuid4()
    rows = [
        FakeGatewayKeyRow(
            cohort_id=cohort,
            status="active",
            cost_limit_eur=Decimal("5.000000000"),
            token_limit_total=1000,
            request_limit_total=100,
            allowed_models=[f"m-{r:04d}-{i:04d}-" for i in range(items_per_list)],
            allow_all_models=False,
            allowed_endpoints=[
                f"/v1/e-{r:04d}-{i:04d}-" for i in range(items_per_list)
            ],
            allow_all_endpoints=False,
        )
        for r in range(KEY_BATCH_MAX_KEYS)
    ]
    service, _, _, _ = _make_batch_service(rows, cohort_id=cohort)
    return asyncio.run(
        service.plan(
            cohort_id=cohort,
            statuses=("active",),
            policy=parse_key_configuration(
                {"schema_version": 1, "request_limit_total": 2000}
            ),
        )
    )


def test_near_8mib_valid_envelope_through_app(batch_client) -> None:
    # A real Core 1000-key plan whose canonical document sits just under
    # the REAL 8 MiB bound must build, render, and round-trip a signed
    # envelope through the app's strict parse with the real token cap.
    plan = _fat_batch_plan(96)
    document = render_key_batch_plan(plan)
    canonical = len(intent._canonical_json(document))
    assert 7 * 1024 * 1024 < canonical < intent.KEY_BATCH_PLAN_MAX_BYTES
    install_fake(batch_client, plan=plan)
    response = batch_client.client.post(
        "/admin/key-batch/plan", data=plan_fields(**POLICY_CHANGE)
    )
    assert response.status_code == 200
    token = extract_token(response.text)
    assert len(token) <= intent.MAX_REVIEW_INTENT_BATCH_TOKEN_CHARS
    assert intent.verify_batch_review_token(
        admin_session_secret=batch_client.settings.ADMIN_SESSION_SECRET,
        token=token,
        admin_user_id=batch_client.admin_user.id,
        admin_session_id=batch_client.admin_session.id,
    ) == document
    # The SAME near-8MiB token must round-trip through the NORMAL
    # urlencoded APPLY form: the large incoming request body is parsed and
    # the FULL strictly-parsed plan reaches the service (the key transport
    # boundary, not just the outgoing token).
    fake = install_fake(batch_client, plan=plan, apply_result=_full_result(plan))
    apply_form = {
        "csrf_token": "dashboard-csrf",
        "batch_review_intent": token,
        "confirm_apply": "true",
        "confirm_external_tool_fenced": "",
        "reason": "Near-limit workshop refresh",
    }
    sent_body = urlencode(apply_form).encode("ascii")
    assert len(sent_body) > 10 * 1024 * 1024
    apply_response = batch_client.client.post(
        "/admin/key-batch/apply", data=apply_form
    )
    assert apply_response.status_code == 200
    assert len(fake.apply_calls) == 1
    applied = fake.apply_calls[0]["plan"]
    assert render_key_batch_plan(applied) == document
    assert list(applied.key_ids) == list(plan.key_ids)
    assert len(applied.key_ids) == KEY_BATCH_MAX_KEYS


def test_apply_form_field_over_bounded_size_fixed_refusal(batch_client) -> None:
    # A single urlencoded field above the bounded batch transport cap is a
    # fixed safe refusal BEFORE auth/service: no 500, no size echo, no
    # service call (Starlette's default 1 MiB per-field cap would refuse
    # the real ~10.67 MiB token otherwise).
    fake = install_fake(batch_client, plan=_make_plan(), apply_result=_batch_result())
    oversized = "A" * (
        batch._BATCH_FORM_MAX_PART_BYTES - len("batch_review_intent") + 1
    )
    response = batch_client.client.post(
        "/admin/key-batch/apply",
        data={
            "csrf_token": "dashboard-csrf",
            "batch_review_intent": oversized,
            "confirm_apply": "true",
            "confirm_external_tool_fenced": "",
            "reason": "r",
        },
    )
    assert response.status_code == 400
    assert batch._BATCH_FORM_TOO_LARGE_MESSAGE in response.text
    assert str(len(oversized)) not in response.text
    assert fake.apply_calls == []
    # The cap must cover the REAL largest envelope plus the field name.
    assert batch._BATCH_FORM_MAX_PART_BYTES > (
        intent.MAX_REVIEW_INTENT_BATCH_TOKEN_CHARS + len("batch_review_intent")
    )


def test_over_real_bound_envelope_refused_fixed_message() -> None:
    # Above the REAL 8 MiB plan bound (no monkeypatched limit): the builder
    # refuses with the fixed safe message and no size/plan detail.
    plan = _fat_batch_plan(100)
    document = render_key_batch_plan(plan)
    canonical = len(intent._canonical_json(document))
    assert canonical > intent.KEY_BATCH_PLAN_MAX_BYTES
    with pytest.raises(intent.AdminReviewIntentError) as excinfo:
        intent.build_batch_review_token(
            admin_session_secret="s" * 40,
            admin_user_id=uuid.uuid4(),
            admin_session_id=uuid.uuid4(),
            plan_document=document,
        )
    message = excinfo.value.message
    assert message == intent._BATCH_TOO_LARGE_MESSAGE
    assert str(canonical) not in message


# ---------------------------------------------------------------------------
# Shipped Nginx batch body allowance (structural config evidence)
# ---------------------------------------------------------------------------


def _nginx_location_blocks(text: str) -> dict[str, dict[str, list[str]]]:
    """Minimal flat parse of the shipped server configs.

    Returns ``{location spec: {directive: [values]}}`` for the directives
    this evidence checks (client_max_body_size, proxy_pass). The shipped
    configs are flat server/location blocks with no nested contexts inside
    a location, so line tracking is sufficient.
    """
    blocks: dict[str, dict[str, list[str]]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("location "):
            current = line.split("{", 1)[0].removeprefix("location").strip()
            blocks[current] = {}
            continue
        if line == "}":
            current = None
            continue
        if current is None or not line.endswith(";"):
            continue
        statement = line[:-1].strip()
        parts = statement.split(None, 1)
        if len(parts) == 2 and parts[0] in ("client_max_body_size", "proxy_pass"):
            blocks[current].setdefault(parts[0], []).append(parts[1].strip())
    return blocks


def test_shipped_nginx_batch_body_allowance() -> None:
    root = Path(__file__).resolve().parents[2]
    production_text = (root / "nginx" / "production.conf").read_text()
    deploy_text = (root / "deploy" / "nginx" / "slaif-api-gateway.conf").read_text()
    for name, text in (
        ("nginx/production.conf", production_text),
        ("deploy/nginx/slaif-api-gateway.conf", deploy_text),
    ):
        blocks = _nginx_location_blocks(text)
        batch_location = blocks.get("/admin/key-batch/")
        assert batch_location is not None, f"{name}: batch location missing"
        assert batch_location.get("client_max_body_size") == ["16m"]
        assert batch_location.get("proxy_pass"), f"{name}: batch must proxy"
        # No other admin location gains a body allowance; /v1/ unchanged.
        assert "client_max_body_size" not in (blocks.get("/admin/") or {})
        assert blocks.get("/v1/", {}).get("client_max_body_size") == ["128m"]
    # The deploy server default stays 10m (admin default preserved).
    assert "client_max_body_size 10m;" in deploy_text
    # The 16m allowance must cover the largest REAL envelope (token bound
    # plus headroom for the other small form fields).
    assert 16 * 1024 * 1024 > intent.MAX_REVIEW_INTENT_BATCH_TOKEN_CHARS + 64 * 1024
