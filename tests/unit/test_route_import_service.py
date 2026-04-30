from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from slaif_gateway.services.route_import import (
    RouteImportProviderRef,
    build_route_import_execution_plan,
    classify_route_import_preview,
    execute_route_import_plan,
    parse_route_import_csv,
    parse_route_import_json,
    route_import_execution_result_to_dict,
    route_import_preview_to_dict,
    validate_route_import_rows,
)


def _provider_ref(**overrides) -> RouteImportProviderRef:
    values = {"id": uuid.uuid4(), "provider": "openai"}
    values.update(overrides)
    return RouteImportProviderRef(**values)


def _valid_row(**overrides) -> dict[str, object]:
    row = {
        "requested_model": "gpt-4.1-mini",
        "match_type": "exact",
        "endpoint": "chat.completions",
        "provider": "openai",
        "upstream_model": "gpt-4.1-mini",
        "priority": "10",
        "enabled": "true",
        "visible_in_models": "true",
        "supports_streaming": "true",
        "capabilities": '{"vision": false}',
        "notes": "safe note",
    }
    row.update(overrides)
    return row


def _preview(rows: list[dict[str, object]], *, providers=None, max_rows: int = 1000):
    return validate_route_import_rows(
        rows,
        provider_configs=providers or (_provider_ref(),),
        max_rows=max_rows,
    )


def test_valid_csv_and_json_parse() -> None:
    csv_rows = parse_route_import_csv(
        "requested_model,match_type,provider,upstream_model\n"
        "gpt-4.1-mini,exact,openai,gpt-4.1-mini\n"
    )
    json_rows = parse_route_import_json(
        '[{"requested_model":"gpt-4.1-mini","match_type":"exact",'
        '"provider":"openai","upstream_model":"gpt-4.1-mini"}]'
    )

    assert csv_rows[0]["requested_model"] == "gpt-4.1-mini"
    assert json_rows[0]["provider"] == "openai"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("unknown", "value", "unknown fields"),
        ("match_type", "regex", "match_type must be one of"),
        ("priority", "-1", "priority must be a non-negative integer"),
        ("requested_model", "", "requested_model is required"),
        ("upstream_model", "", "upstream_model is required"),
        ("endpoint", "https://example.test/v1/chat/completions", "endpoint must be a /v1 path"),
    ],
)
def test_invalid_rows_are_rejected(field: str, value: str, message: str) -> None:
    preview = _preview([_valid_row(**{field: value})])

    assert preview.invalid_count == 1
    assert message in preview.rows[0].errors[0]


def test_unknown_provider_reference_is_rejected() -> None:
    preview = _preview([_valid_row(provider="missing")])

    assert preview.invalid_count == 1
    assert "provider must reference an existing provider config" in preview.rows[0].errors[0]


def test_provider_config_id_reference_is_validated() -> None:
    provider = _provider_ref()
    preview = _preview(
        [_valid_row(provider="", provider_config_id=str(provider.id))],
        providers=(provider,),
    )

    assert preview.valid_count == 1
    assert preview.rows[0].provider == "openai"
    assert preview.rows[0].provider_config_id == provider.id


def test_secret_looking_capabilities_and_notes_are_rejected() -> None:
    metadata = _preview([_valid_row(capabilities='{"api_key":"sk-provider-secret"}')])
    notes = _preview([_valid_row(notes="Bearer provider-secret")])

    assert metadata.invalid_count == 1
    assert "capabilities must not contain secret-looking values" in metadata.rows[0].errors[0]
    assert notes.invalid_count == 1
    assert "notes must not contain secret-looking values" in notes.rows[0].errors[0]


def test_max_rows_enforced() -> None:
    with pytest.raises(ValueError, match="at most 1 rows"):
        _preview([_valid_row(), _valid_row(requested_model="gpt-4.1")], max_rows=1)


def test_duplicate_and_existing_classification() -> None:
    preview = _preview(
        [
            _valid_row(),
            _valid_row(),
            _valid_row(requested_model="gpt-new", upstream_model="gpt-new"),
            _valid_row(requested_model="gpt-update", upstream_model="gpt-update"),
            _valid_row(requested_model="gpt-conflict", upstream_model="gpt-conflict"),
        ]
    )
    classified = classify_route_import_preview(
        preview,
        existing_routes_by_row={
            1: [
                SimpleNamespace(
                    requested_model="gpt-4.1-mini",
                    match_type="exact",
                    endpoint="/v1/chat/completions",
                    provider="openai",
                    upstream_model="gpt-4.1-mini",
                    priority=10,
                    enabled=True,
                    visible_in_models=True,
                    supports_streaming=True,
                    capabilities={"vision": False},
                    notes="safe note",
                )
            ],
            4: [
                SimpleNamespace(
                    requested_model="gpt-update",
                    match_type="exact",
                    endpoint="/v1/chat/completions",
                    provider="openai",
                    upstream_model="gpt-update-v2",
                    priority=10,
                    enabled=True,
                    visible_in_models=True,
                    supports_streaming=True,
                    capabilities={},
                    notes=None,
                )
            ],
            5: [
                SimpleNamespace(
                    requested_model="gpt-conflict",
                    match_type="exact",
                    endpoint="/v1/chat/completions",
                    provider="openrouter",
                )
            ],
        },
    )

    assert [row.classification for row in classified.rows] == [
        "duplicate",
        "duplicate",
        "create",
        "update",
        "conflict",
    ]


def test_preview_dict_does_not_include_raw_content() -> None:
    preview = _preview([_valid_row(notes="<script>alert(1)</script>")])
    payload = route_import_preview_to_dict(preview)

    assert payload["rows"][0]["requested_model"] == "gpt-4.1-mini"
    assert "requested_model,match_type" not in str(payload)


def test_route_import_execution_plan_blocks_non_create_rows() -> None:
    preview = _preview(
        [
            _valid_row(),
            _valid_row(),
            _valid_row(requested_model="gpt-update", upstream_model="gpt-update"),
            _valid_row(requested_model="gpt-conflict", upstream_model="gpt-conflict"),
            _valid_row(provider="missing"),
        ]
    )
    classified = classify_route_import_preview(
        preview,
        existing_routes_by_row={
            3: [
                SimpleNamespace(
                    requested_model="gpt-update",
                    match_type="exact",
                    endpoint="/v1/chat/completions",
                    provider="openai",
                    upstream_model="gpt-update-v2",
                    priority=10,
                    enabled=True,
                    visible_in_models=True,
                    supports_streaming=True,
                    capabilities={},
                    notes=None,
                )
            ],
            4: [
                SimpleNamespace(
                    requested_model="gpt-conflict",
                    match_type="exact",
                    endpoint="/v1/chat/completions",
                    provider="openrouter",
                )
            ],
        },
    )

    plan = build_route_import_execution_plan(classified)

    assert plan.executable is False
    assert plan.executable_count == 1
    assert plan.blocked_count == 4
    error_text = "\n".join("\n".join(row.errors) for row in plan.rows)
    assert "duplicate rows are not supported" in error_text
    assert "update rows are not supported" in error_text
    assert "conflict rows are not supported" in error_text
    assert "provider must reference an existing provider config" in error_text


def test_route_import_execution_plan_executes_create_only_rows_without_raw_content() -> None:
    class FakeRouteService:
        def __init__(self) -> None:
            self.calls = []

        async def create_model_route(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(id=uuid.uuid4())

    preview = _preview([_valid_row(notes="<script>alert(1)</script>")])
    plan = build_route_import_execution_plan(preview)
    service = FakeRouteService()

    result = asyncio.run(
        execute_route_import_plan(
            plan,
            model_route_service=service,
            actor_admin_id=uuid.uuid4(),
            reason="route import",
        )
    )

    assert result.created_count == 1
    assert service.calls[0]["requested_model"] == "gpt-4.1-mini"
    assert service.calls[0]["endpoint"] == "/v1/chat/completions"
    assert service.calls[0]["reason"] == "route import"
    payload = route_import_execution_result_to_dict(result)
    assert "<script>alert(1)</script>" in str(payload)
    assert "requested_model,match_type" not in str(payload)
    assert "token_hash" not in str(payload)
    assert "encrypted_payload" not in str(payload)
    assert "nonce" not in str(payload)
    assert "password_hash" not in str(payload)
