from __future__ import annotations

import csv
import json
import uuid

import httpx
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.services.openai_assisted_catalog import OPENAI_RESPONSES_URL
from slaif_gateway.services.pricing_import import parse_pricing_import_tsv, validate_pricing_import_rows
from slaif_gateway.services.route_import import (
    RouteImportProviderRef,
    parse_route_import_tsv,
    validate_route_import_rows,
)

runner = CliRunner()
_DISCOVERY_ENV = "OPENAI_ADMIN_DISCOVERY_API_KEY"
_FAKE_DISCOVERY_KEY = "admin-discovery-test-key"
_MODELS_URL = "https://platform.openai.com/docs/models/compare"
_PRICING_URL = "https://platform.openai.com/docs/pricing"


def _response_payload(rows: list[dict[str, object]], warnings: list[str] | None = None) -> dict[str, object]:
    return {"output_text": json.dumps({"rows": rows, "warnings": warnings or []})}


def _pricing_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "provider": "openai",
        "model": "gpt-5.5",
        "endpoint": "/v1/chat/completions",
        "currency": "USD",
        "input_price_per_1m": "5.00",
        "cached_input_price_per_1m": "0.50",
        "output_price_per_1m": "30.00",
        "reasoning_price_per_1m": None,
        "request_price": None,
        "valid_from": "2026-05-17T00:00:00Z",
        "source_url": _PRICING_URL,
        "source_urls": [_PRICING_URL, _MODELS_URL],
        "confidence": "0.83",
    }
    row.update(overrides)
    return row


def _route_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "requested_model": "gpt-5.5",
        "model_category": "chat",
        "endpoint": "/v1/chat/completions",
        "upstream_model": "gpt-5.5",
        "supports_streaming": True,
        "supported_endpoints": ["/v1/chat/completions", "/v1/responses"],
        "source_urls": [_MODELS_URL],
        "confidence": "0.81",
    }
    row.update(overrides)
    return row


def _mock_openai(respx_mock, rows: list[dict[str, object]], warnings: list[str] | None = None):
    return respx_mock.post(OPENAI_RESPONSES_URL).mock(
        return_value=httpx.Response(200, json=_response_payload(rows, warnings))
    )


def _read_tsv(path):
    return list(csv.DictReader(path.read_text(encoding="utf-8").splitlines(), delimiter="\t"))


def test_missing_acknowledgement_fails_without_output(tmp_path) -> None:
    output = tmp_path / "pricing.tsv"

    result = runner.invoke(app, ["openai-assisted", "pricing-proposal", "--output", str(output)])

    assert result.exit_code == 1
    assert "--acknowledge-llm-proposal-risk is required" in result.stderr
    assert not output.exists()


def test_missing_admin_discovery_key_fails_safely(tmp_path, monkeypatch) -> None:
    output = tmp_path / "pricing.tsv"
    monkeypatch.delenv(_DISCOVERY_ENV, raising=False)

    result = runner.invoke(
        app,
        [
            "openai-assisted",
            "pricing-proposal",
            "--output",
            str(output),
            "--acknowledge-llm-proposal-risk",
        ],
    )

    assert result.exit_code == 1
    assert f"{_DISCOVERY_ENV} is not configured" in result.stderr
    assert not output.exists()


def test_openai_api_key_env_var_is_rejected_for_admin_discovery(tmp_path, monkeypatch) -> None:
    output = tmp_path / "pricing.tsv"
    monkeypatch.setenv("OPENAI_API_KEY", "client-side-gateway-key-placeholder")

    result = runner.invoke(
        app,
        [
            "openai-assisted",
            "pricing-proposal",
            "--output",
            str(output),
            "--api-key-env-var",
            "OPENAI_API_KEY",
            "--acknowledge-llm-proposal-risk",
        ],
    )

    assert result.exit_code == 1
    assert "OPENAI_API_KEY is reserved for client gateway keys" in result.stderr
    assert not output.exists()


def test_fake_admin_discovery_key_is_not_printed(tmp_path, monkeypatch, respx_mock) -> None:
    output = tmp_path / "pricing.tsv"
    monkeypatch.setenv(_DISCOVERY_ENV, _FAKE_DISCOVERY_KEY)
    route = _mock_openai(respx_mock, [_pricing_row()])

    result = runner.invoke(
        app,
        [
            "openai-assisted",
            "pricing-proposal",
            "--output",
            str(output),
            "--acknowledge-llm-proposal-risk",
        ],
    )

    assert result.exit_code == 0
    assert route.called
    assert route.calls[0].request.headers["authorization"] == f"Bearer {_FAKE_DISCOVERY_KEY}"
    assert _FAKE_DISCOVERY_KEY not in result.stdout
    assert _FAKE_DISCOVERY_KEY not in result.stderr


def test_mocked_openai_valid_json_produces_pricing_tsv(tmp_path, monkeypatch, respx_mock) -> None:
    output = tmp_path / "pricing.tsv"
    monkeypatch.setenv(_DISCOVERY_ENV, _FAKE_DISCOVERY_KEY)
    _mock_openai(respx_mock, [_pricing_row(model="gpt-5.5"), _pricing_row(model="gpt-5.4")])

    result = runner.invoke(
        app,
        [
            "openai-assisted",
            "pricing-proposal",
            "--output",
            str(output),
            "--include-model",
            "gpt-5.*",
            "--acknowledge-llm-proposal-risk",
        ],
    )

    assert result.exit_code == 0
    assert "LLM-assisted proposal only" in result.stdout
    rows = _read_tsv(output)
    assert {row["model"] for row in rows} == {"gpt-5.5", "gpt-5.4"}
    assert rows[0]["endpoint"] == "chat.completions"
    metadata = json.loads(rows[0]["pricing_metadata"])
    assert metadata["source_type"] == "openai_llm_assisted"
    assert metadata["operator_review_required"] is True
    assert metadata["proposal_model"] == "gpt-5.5"
    assert rows[0]["source_retrieved_at"]
    preview = validate_pricing_import_rows(parse_pricing_import_tsv(output.read_text()), max_rows=10)
    assert preview.valid_count == 2
    assert preview.rows[0].pricing_metadata["source_retrieved_at"]


def test_mocked_openai_valid_json_produces_route_tsv(tmp_path, monkeypatch, respx_mock) -> None:
    output = tmp_path / "routes.tsv"
    monkeypatch.setenv(_DISCOVERY_ENV, _FAKE_DISCOVERY_KEY)
    _mock_openai(respx_mock, [_route_row()])

    result = runner.invoke(
        app,
        [
            "openai-assisted",
            "route-proposal",
            "--output",
            str(output),
            "--acknowledge-llm-proposal-risk",
        ],
    )

    assert result.exit_code == 0
    rows = _read_tsv(output)
    assert rows == [
        {
            "requested_model": "gpt-5.5",
            "match_type": "exact",
            "endpoint": "chat.completions",
            "provider": "openai",
            "upstream_model": "gpt-5.5",
            "priority": "100",
            "enabled": "true",
            "visible_in_models": "true",
            "supports_streaming": "true",
            "capabilities": rows[0]["capabilities"],
            "notes": "Endpoint compatibility is proposed from official OpenAI docs and requires admin review.",
        }
    ]
    capabilities = json.loads(rows[0]["capabilities"])
    assert capabilities["endpoint_compatibility"] == "v1/chat/completions"
    assert capabilities["chat_completions"]["chat_text"] is True
    assert capabilities["chat_completions"]["chat_streaming"] is True
    assert capabilities["chat_completions"]["hosted_web_search"] is False
    preview = validate_route_import_rows(
        parse_route_import_tsv(output.read_text()),
        provider_configs=(RouteImportProviderRef(id=uuid.uuid4(), provider="openai"),),
        max_rows=10,
    )
    assert preview.valid_count == 1


def test_invalid_json_fails_closed_and_writes_no_output(tmp_path, monkeypatch, respx_mock) -> None:
    output = tmp_path / "pricing.tsv"
    monkeypatch.setenv(_DISCOVERY_ENV, _FAKE_DISCOVERY_KEY)
    respx_mock.post(OPENAI_RESPONSES_URL).mock(
        return_value=httpx.Response(200, json={"output_text": "{not json"})
    )

    result = runner.invoke(
        app,
        [
            "openai-assisted",
            "pricing-proposal",
            "--output",
            str(output),
            "--acknowledge-llm-proposal-risk",
        ],
    )

    assert result.exit_code == 1
    assert "could not be parsed" in result.stderr
    assert not output.exists()


def test_route_proposal_excludes_unsupported_categories_and_gateway_endpoints(
    tmp_path,
    monkeypatch,
    respx_mock,
) -> None:
    output = tmp_path / "routes.tsv"
    monkeypatch.setenv(_DISCOVERY_ENV, _FAKE_DISCOVERY_KEY)
    _mock_openai(
        respx_mock,
        [
            _route_row(requested_model="gpt-5.5"),
            _route_row(
                requested_model="gpt-responses-only",
                model_category="responses_only",
                endpoint="/v1/responses",
                supported_endpoints=["/v1/responses"],
            ),
            _route_row(
                requested_model="text-embedding-3-small",
                model_category="embeddings_only",
                supported_endpoints=["/v1/embeddings"],
            ),
            _route_row(requested_model="gpt-image-1", model_category="image_only"),
            _route_row(requested_model="gpt-audio", model_category="audio_only"),
            _route_row(requested_model="omni-moderation-latest", model_category="moderation_only"),
            _route_row(requested_model="gpt-realtime", model_category="realtime_only"),
            _route_row(requested_model="batch-target", model_category="batch_only"),
            _route_row(requested_model="gpt-5-search-api", model_category="chat"),
            _route_row(
                requested_model="legacy-completion",
                model_category="chat",
                endpoint="/v1/completions",
                supported_endpoints=["/v1/completions"],
            ),
        ],
    )

    result = runner.invoke(
        app,
        [
            "openai-assisted",
            "route-proposal",
            "--output",
            str(output),
            "--acknowledge-llm-proposal-risk",
        ],
    )

    assert result.exit_code == 0
    text = output.read_text(encoding="utf-8")
    rows = _read_tsv(output)
    assert [row["requested_model"] for row in rows] == ["gpt-5.5"]
    assert "/v1/responses" not in text
    assert "/v1/completions" not in text
    assert "omitted unsupported model category" in result.stdout
    assert "omitted search-specific model requiring future hosted_web_search policy" in result.stdout


def test_output_refuses_overwrite_without_flag(tmp_path, monkeypatch, respx_mock) -> None:
    output = tmp_path / "pricing.tsv"
    output.write_text("existing", encoding="utf-8")
    monkeypatch.setenv(_DISCOVERY_ENV, _FAKE_DISCOVERY_KEY)
    route = respx_mock.post(OPENAI_RESPONSES_URL).mock(return_value=httpx.Response(500))

    result = runner.invoke(
        app,
        [
            "openai-assisted",
            "pricing-proposal",
            "--output",
            str(output),
            "--acknowledge-llm-proposal-risk",
        ],
    )

    assert result.exit_code == 1
    assert "already exists" in result.stderr
    assert output.read_text(encoding="utf-8") == "existing"
    assert not route.called


def test_json_output_is_machine_readable(tmp_path, monkeypatch, respx_mock) -> None:
    output = tmp_path / "pricing.tsv"
    monkeypatch.setenv(_DISCOVERY_ENV, _FAKE_DISCOVERY_KEY)
    _mock_openai(respx_mock, [_pricing_row()])

    result = runner.invoke(
        app,
        [
            "openai-assisted",
            "pricing-proposal",
            "--output",
            str(output),
            "--acknowledge-llm-proposal-risk",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mutated_metadata"] is False
    assert payload["row_count"] == 1
    assert "LLM-assisted proposal only" in payload["warning"]
    assert _FAKE_DISCOVERY_KEY not in result.stdout
