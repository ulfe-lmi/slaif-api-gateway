from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest

from slaif_gateway.services.openai_assisted_catalog import OpenAIAssistedProposalTextResult
from slaif_gateway.services.pricing_import import parse_pricing_import_tsv, validate_pricing_import_rows
from slaif_gateway.services.provider_catalog_proposal import (
    CHAT_COMPLETIONS_ENDPOINT,
    OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR,
    OPENAI_MODELS_API_URL,
    OPENAI_MODELS_DOCS_URL,
    OPENAI_PRICING_DOCS_URL,
    OPENROUTER_MODELS_API_URL,
    OPENROUTER_MODELS_DOCS_MARKDOWN_URL,
    ProviderCatalogProposalValidationError,
    ProviderCatalogProposalResult,
    _build_chat_capabilities,
    _openrouter_model_warnings,
    _confirm_openrouter_pricing_unit,
    _openrouter_pricing_candidate,
    _parse_openai_models_docs,
    _parse_openai_pricing_docs,
    _validate_generated_pricing_tsv,
    generate_provider_catalog_proposal,
)
from slaif_gateway.services.route_import import (
    RouteImportProviderRef,
    parse_route_import_tsv,
    validate_route_import_rows,
)


OPENROUTER_MODELS_FIXTURE = {
    "data": [
        {
            "id": "openai/gpt-test-mini",
            "canonical_slug": "openai/gpt-test-mini",
            "name": "GPT Test Mini",
            "description": "Safe text model",
            "context_length": 128000,
            "architecture": {
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
            },
            "pricing": {
                "prompt": "0.000002",
                "completion": "0.000008",
                "input_cache_read": "0.000001",
                "internal_reasoning": "0.000003",
                "request": "0",
            },
            "top_provider": {"context_length": 128000, "max_completion_tokens": 8192},
            "supported_parameters": [
                "tools",
                "response_format",
                "structured_outputs",
                "logprobs",
            ],
            "knowledge_cutoff": "2025-01",
            "expiration_date": None,
            "links": {"details": "/api/v1/models/openai/gpt-test-mini/endpoints"},
        },
        {
            "id": "openai/gpt-search-test",
            "canonical_slug": "openai/gpt-search-test",
            "name": "GPT Search Test",
            "description": "Search-specific model",
            "context_length": 128000,
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text"],
            },
            "pricing": {"prompt": "0.000004", "completion": "0.00001"},
            "top_provider": {"context_length": 128000, "max_completion_tokens": 4096},
            "supported_parameters": ["web_search_options"],
            "knowledge_cutoff": None,
            "expiration_date": None,
            "links": {},
        },
    ]
}

OPENAI_PRICING_DOC_FIXTURE = """
| Model | Input | Cached input | Output |
| --- | --- | --- | --- |
| gpt-5.5 | $5.00 | $0.50 | $15.00 |
| gpt-5-search-test | $4.00 | $0.40 | $12.00 |
"""

OPENAI_PRICING_DOC_WITH_NOISE_FIXTURE = """
Pricing
API
ChatGPT
Codex
1M
400K
| Model | Input | Cached input | Output |
| --- | --- | --- | --- |
| AGENTS.md | $1.00 | $0.10 | $2.00 |
| API | $1.00 | $0.10 | $2.00 |
| Image | $10.00 |  |  |
| Audio | $3.00 |  |  |
| Embeddings | $0.20 |  |  |
| gpt-5.5 | $5.00 | $0.50 | $15.00 |
| gpt-5.6 | $6.00 | $0.60 |  |
| text-embedding-3-small | $0.02 |  |  |
"""

OPENAI_MODELS_DOC_FIXTURE = """
## gpt-5.5
Endpoints: /v1/chat/completions, /v1/responses
Features: streaming, function calling, structured outputs, logprobs, image input
Context length: 400000
Max output tokens: 16384
Knowledge cutoff: 2025-01

## gpt-5-search-test
Endpoints: /v1/chat/completions
Features: streaming, web_search, hosted_tools
Context length: 128000
Max output tokens: 8192
"""

OPENAI_MODELS_DOC_WITH_NOISE_FIXTURE = """
AGENTS.md
API
AWS
Actions
Pricing
ChatGPT
Codex
Image
Audio
Embeddings

## gpt-5.5
Endpoints: /v1/chat/completions, /v1/responses
Features: streaming, function calling, structured outputs, logprobs, image input
Context length: 400000
Max output tokens: 16384
Knowledge cutoff: 2025-01

## gpt-5.6
Endpoints: /v1/chat/completions
Features: streaming, function calling
Context length: 256000
Max output tokens: 8192

## text-embedding-3-small
Endpoints: /v1/embeddings
Features: embeddings
Context length: 8192
"""


def test_openrouter_pricing_unit_confirmation_and_conversion() -> None:
    assert _confirm_openrouter_pricing_unit(
        "All pricing values are in USD per token/request/unit."
    )

    candidate, warnings = _openrouter_pricing_candidate(
        model_id="openai/gpt-test-mini",
        pricing={
            "prompt": "0.000002",
            "completion": "0.000008",
            "input_cache_read": "0.000001",
            "internal_reasoning": "0.000003",
            "request": "0",
        },
        currency="USD",
        source_url=OPENROUTER_MODELS_API_URL,
        source_retrieved_at="2026-06-09T00:00:00Z",
        unit_confirmed=True,
        confidence="high",
        model_warnings=(),
        allow_zero_prices=False,
    )

    assert candidate is not None
    assert candidate.input_price_per_1m == "2"
    assert candidate.cached_input_price_per_1m == "1"
    assert candidate.output_price_per_1m == "8"
    assert candidate.reasoning_price_per_1m == "3"
    assert candidate.ready_for_import is True
    assert warnings == ()


def test_openrouter_zero_price_rows_are_report_only_by_default_and_opt_in_ready() -> None:
    candidate, warnings = _openrouter_pricing_candidate(
        model_id="openrouter/owl-alpha",
        pricing={
            "prompt": "0",
            "completion": "0",
        },
        currency="USD",
        source_url=OPENROUTER_MODELS_API_URL,
        source_retrieved_at="2026-06-09T00:00:00Z",
        unit_confirmed=True,
        confidence="high",
        model_warnings=(),
        allow_zero_prices=False,
    )

    assert candidate is not None
    assert candidate.ready_for_import is False
    assert candidate.pricing_metadata["zero_price_requires_review"] is True
    assert "zero_price_requires_review" in warnings

    opt_in_candidate, _ = _openrouter_pricing_candidate(
        model_id="openrouter/owl-alpha",
        pricing={
            "prompt": "0",
            "completion": "0",
        },
        currency="USD",
        source_url=OPENROUTER_MODELS_API_URL,
        source_retrieved_at="2026-06-09T00:00:00Z",
        unit_confirmed=True,
        confidence="high",
        model_warnings=(),
        allow_zero_prices=True,
    )

    assert opt_in_candidate is not None
    assert opt_in_candidate.ready_for_import is True
    assert opt_in_candidate.pricing_metadata["operator_review_required"] is True


def test_openrouter_negative_price_rows_remain_not_ready() -> None:
    candidate, warnings = _openrouter_pricing_candidate(
        model_id="openrouter/fusion",
        pricing={
            "prompt": "-0.000001",
            "completion": "0.000001",
        },
        currency="USD",
        source_url=OPENROUTER_MODELS_API_URL,
        source_retrieved_at="2026-06-09T00:00:00Z",
        unit_confirmed=True,
        confidence="high",
        model_warnings=(),
        allow_zero_prices=False,
    )

    assert candidate is None
    assert "negative_or_invalid_price" in warnings


def test_generated_pricing_tsv_validation_rejects_joined_source_url_and_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "pricing-proposal.tsv"
    path.write_text(
        "provider\tmodel\tendpoint\tcurrency\tinput_price_per_1m\tcached_input_price_per_1m\t"
        "output_price_per_1m\treasoning_price_per_1m\trequest_price\tvalid_from\tsource_url\t"
        "source_retrieved_at\tpricing_metadata\tnotes\n"
        "openrouter\topenai/gpt-test-mini\t/v1/chat/completions\tUSD\t2\t1\t8\t3\t0\t"
        "2026-06-09T00:00:00Z\thttps://openrouter.ai/api/v1/models 2026-06-09T00:00:00Z\t"
        "2026-06-09T00:00:00Z\t{\"operator_review_required\":true}\tsafe\n",
        encoding="utf-8",
    )

    with pytest.raises(ProviderCatalogProposalValidationError, match="source_url"):
        _validate_generated_pricing_tsv(path, ())


def test_chat_capability_mapping_stays_conservative_for_ambiguous_modalities() -> None:
    capabilities = _build_chat_capabilities(
        supported_parameters=("tools", "structured_outputs"),
        input_modalities=("text", "image", "file", "audio"),
        output_modalities=("text", "audio"),
        supports_streaming=True,
        provider="openrouter",
        supports_cached_input_usage=False,
    )
    chat = capabilities["chat_completions"]

    assert chat["chat_function_tools"] is True
    assert chat["chat_structured_outputs"] is True
    assert chat["chat_image_inputs"] is True
    assert chat["chat_file_inputs"] is False
    assert chat["chat_audio_inputs"] is False
    assert chat["chat_audio_outputs"] is False
    assert chat["hosted_web_search"] is False
    assert chat["hosted_file_search"] is False
    assert chat["hosted_code_interpreter"] is False
    assert chat["hosted_computer_use"] is False
    assert chat["hosted_image_generation"] is False
    assert chat["hosted_tool_search"] is False
    assert chat["external_mcp_connectors"] is False


def test_openrouter_model_warnings_flag_ambiguous_file_audio_capabilities() -> None:
    warnings = _openrouter_model_warnings(
        model_id="openrouter/audio-file-test",
        supported_parameters=("tools",),
        input_modalities=("text", "file", "audio"),
        output_modalities=("text",),
        expiration_date=None,
    )

    assert "ambiguous_capability" in warnings


def test_openai_docs_parsers_extract_pricing_and_model_features() -> None:
    pricing = _parse_openai_pricing_docs(
        text=OPENAI_PRICING_DOC_FIXTURE,
        source_url=OPENAI_PRICING_DOCS_URL,
        source_retrieved_at="2026-06-09T00:00:00Z",
    )
    models = _parse_openai_models_docs(
        text=OPENAI_MODELS_DOC_FIXTURE,
        source_url=OPENAI_MODELS_DOCS_URL,
    )

    assert pricing[0].model_id == "gpt-5.5"
    assert pricing[0].input_price_per_1m == "5"
    assert pricing[0].cached_input_price_per_1m == "0.5"
    assert pricing[0].output_price_per_1m == "15"
    assert models["gpt-5.5"].endpoints == ("/v1/chat/completions", "/v1/responses")
    assert "streaming" in models["gpt-5.5"].features
    assert "function calling" in models["gpt-5.5"].features
    assert models["gpt-5.5"].context_length == 400000
    assert models["gpt-5.5"].max_output_tokens == 16384


def test_openai_docs_parsers_reject_navigation_tokens_and_unsupported_categories() -> None:
    pricing = _parse_openai_pricing_docs(
        text=OPENAI_PRICING_DOC_WITH_NOISE_FIXTURE,
        source_url=OPENAI_PRICING_DOCS_URL,
        source_retrieved_at="2026-06-10T00:00:00Z",
    )
    models = _parse_openai_models_docs(
        text=OPENAI_MODELS_DOC_WITH_NOISE_FIXTURE,
        source_url=OPENAI_MODELS_DOCS_URL,
    )

    pricing_model_ids = {record.model_id for record in pricing}
    assert pricing_model_ids == {"gpt-5.5", "gpt-5.6", "text-embedding-3-small"}
    assert "AGENTS.md" not in pricing_model_ids
    assert "API" not in pricing_model_ids
    assert "Image" not in pricing_model_ids

    assert set(models) == {"gpt-5.5", "gpt-5.6", "text-embedding-3-small"}
    assert "API" not in models
    assert "ChatGPT" not in models
    assert "Codex" not in models


@pytest.mark.asyncio
async def test_generate_openrouter_catalog_proposal_outputs_safe_tsv_files(
    tmp_path: Path,
    respx_mock,
) -> None:
    respx_mock.get(OPENROUTER_MODELS_DOCS_MARKDOWN_URL).mock(
        return_value=httpx.Response(
            200,
            text="All pricing values are in USD per token/request/unit.",
            headers={"content-type": "text/markdown"},
        )
    )
    respx_mock.get(OPENROUTER_MODELS_API_URL).mock(
        return_value=httpx.Response(200, json=OPENROUTER_MODELS_FIXTURE)
    )
    respx_mock.get("https://openrouter.ai/api/v1/models/openai/gpt-test-mini/endpoints").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"max_completion_tokens": 8192}},
        )
    )

    result = await generate_provider_catalog_proposal(
        provider_scope="openrouter",
        output_dir=tmp_path,
        fetch_details_limit=1,
    )

    assert isinstance(result, ProviderCatalogProposalResult)
    assert result.route_rows_ready == 1
    assert result.pricing_rows_ready == 1
    assert result.manifest_path.exists()
    assert result.normalized_path.exists()
    assert result.report_path.exists()
    assert result.warnings_path.exists()

    route_preview = validate_route_import_rows(
        parse_route_import_tsv(result.routes_proposal_path.read_text(encoding="utf-8")),
        provider_configs=(RouteImportProviderRef(id=uuid.uuid4(), provider="openrouter"),),
        max_rows=10,
    )
    pricing_preview = validate_pricing_import_rows(
        parse_pricing_import_tsv(result.pricing_proposal_path.read_text(encoding="utf-8")),
        max_rows=10,
    )

    assert route_preview.valid_count == 1
    assert pricing_preview.valid_count == 1
    route_row = route_preview.rows[0]
    assert route_row.requested_model == "openai/gpt-test-mini"
    assert route_row.endpoint == CHAT_COMPLETIONS_ENDPOINT
    pricing_row = pricing_preview.rows[0]
    assert pricing_row.model == "openai/gpt-test-mini"
    assert pricing_row.input_price_per_1m == "2"
    assert "sk-" not in result.normalized_path.read_text(encoding="utf-8")

    warnings_payload = json.loads(result.warnings_path.read_text(encoding="utf-8"))
    warning_codes = {item["code"] for item in warnings_payload["warnings"]}
    assert "search_specific_model" in warning_codes


@pytest.mark.asyncio
async def test_generate_openai_catalog_proposal_compares_docs_api_and_assisted_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock,
) -> None:
    monkeypatch.setenv(OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR, "admin-discovery-key")
    respx_mock.get(OPENAI_PRICING_DOCS_URL).mock(
        return_value=httpx.Response(200, text=OPENAI_PRICING_DOC_FIXTURE)
    )
    respx_mock.get(OPENAI_MODELS_DOCS_URL).mock(
        return_value=httpx.Response(200, text=OPENAI_MODELS_DOC_FIXTURE)
    )
    respx_mock.get(OPENAI_MODELS_API_URL).mock(
        return_value=httpx.Response(200, json={"data": [{"id": "gpt-5.5"}]})
    )

    async def fake_pricing_cross_check(**kwargs) -> OpenAIAssistedProposalTextResult:  # noqa: ANN003
        return OpenAIAssistedProposalTextResult(
            proposal_type="pricing",
            tsv_text=(
                "provider\tmodel\tendpoint\tcurrency\tinput_price_per_1m\t"
                "cached_input_price_per_1m\toutput_price_per_1m\treasoning_price_per_1m\t"
                "request_price\tvalid_from\tsource_url\tsource_retrieved_at\tpricing_metadata\tnotes\n"
                "openai\tgpt-5.5\t/v1/chat/completions\tUSD\t6\t0.5\t15\t\t\t"
                "2026-06-09T00:00:00Z\thttps://developers.openai.com/api/docs/pricing\t"
                "2026-06-09T00:00:00Z\t{}\tsafe\n"
            ),
            row_count=1,
            warnings=(),
            source_urls=(OPENAI_PRICING_DOCS_URL, OPENAI_MODELS_DOCS_URL),
        )

    async def fake_route_cross_check(**kwargs) -> OpenAIAssistedProposalTextResult:  # noqa: ANN003
        return OpenAIAssistedProposalTextResult(
            proposal_type="route",
            tsv_text=(
                "requested_model\tmatch_type\tendpoint\tprovider\tupstream_model\tpriority\t"
                "enabled\tvisible_in_models\tsupports_streaming\tcapabilities\tnotes\n"
                "gpt-5.5\texact\t/v1/chat/completions\topenai\tgpt-5.5\t100\ttrue\ttrue\ttrue\t{}\tsafe\n"
            ),
            row_count=1,
            warnings=(),
            source_urls=(OPENAI_MODELS_DOCS_URL,),
        )

    monkeypatch.setattr(
        "slaif_gateway.services.provider_catalog_proposal.generate_openai_pricing_proposal_text",
        fake_pricing_cross_check,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.provider_catalog_proposal.generate_openai_route_proposal_text",
        fake_route_cross_check,
    )

    result = await generate_provider_catalog_proposal(
        provider_scope="openai",
        output_dir=tmp_path,
        include_api_models=True,
        source_methods=("docs", "api", "assisted"),
        acknowledge_assisted_proposal_risk=True,
    )

    warnings_payload = json.loads(result.warnings_path.read_text(encoding="utf-8"))
    warning_codes = {item["code"] for item in warnings_payload["warnings"]}
    assert "pricing_disagreement" in warning_codes
    assert "model_missing_from_api" in warning_codes
    assert "search_specific_model" in warning_codes
    assert result.pricing_rows_ready == 0
    assert result.route_rows_ready == 1
    assert "admin-discovery-key" not in result.manifest_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_generate_openai_docs_only_catalog_skips_noise_and_incomplete_chat_pricing(
    tmp_path: Path,
    respx_mock,
) -> None:
    respx_mock.get(OPENAI_PRICING_DOCS_URL).mock(
        return_value=httpx.Response(200, text=OPENAI_PRICING_DOC_WITH_NOISE_FIXTURE)
    )
    respx_mock.get(OPENAI_MODELS_DOCS_URL).mock(
        return_value=httpx.Response(200, text=OPENAI_MODELS_DOC_WITH_NOISE_FIXTURE)
    )

    result = await generate_provider_catalog_proposal(
        provider_scope="openai",
        output_dir=tmp_path,
        source_methods=("docs",),
        endpoint_scopes=("chat_completions",),
    )

    assert result.route_rows_ready == 2
    assert result.pricing_rows_ready == 1

    route_tsv = result.routes_proposal_path.read_text(encoding="utf-8")
    pricing_tsv = result.pricing_proposal_path.read_text(encoding="utf-8")

    for bad_token in {
        "1M",
        "400K",
        "AGENTS.md",
        "API",
        "AWS",
        "Actions",
        "Pricing",
        "ChatGPT",
        "Codex",
        "Image",
        "Audio",
        "Embeddings",
        "Files",
    }:
        assert bad_token not in route_tsv
        assert bad_token not in pricing_tsv

    assert "gpt-5.5" in route_tsv
    assert "gpt-5.6" in route_tsv
    assert "gpt-5.5" in pricing_tsv
    assert "gpt-5.6" not in pricing_tsv
    assert "text-embedding-3-small" not in route_tsv
    assert "text-embedding-3-small" not in pricing_tsv

    warnings_payload = json.loads(result.warnings_path.read_text(encoding="utf-8"))
    warning_codes = {item["code"] for item in warnings_payload["warnings"]}
    assert "missing_pricing" in warning_codes
    assert "unsupported_modality" in warning_codes


@pytest.mark.asyncio
async def test_generate_openai_docs_only_catalog_succeeds_with_zero_ready_rows(
    tmp_path: Path,
    respx_mock,
) -> None:
    respx_mock.get(OPENAI_PRICING_DOCS_URL).mock(
        return_value=httpx.Response(
            200,
            text="""
Pricing
API
ChatGPT
| Model | Input | Cached input | Output |
| --- | --- | --- | --- |
| Image | $10.00 |  |  |
| Audio | $3.00 |  |  |
| Embeddings | $0.20 |  |  |
""",
        )
    )
    respx_mock.get(OPENAI_MODELS_DOCS_URL).mock(
        return_value=httpx.Response(
            200,
            text="""
AGENTS.md
API
Pricing
ChatGPT
Codex
Image
Audio
Embeddings
""",
        )
    )

    result = await generate_provider_catalog_proposal(
        provider_scope="openai",
        output_dir=tmp_path,
        source_methods=("docs",),
        endpoint_scopes=("chat_completions",),
    )

    assert result.route_rows_ready == 0
    assert result.pricing_rows_ready == 0
    assert result.routes_proposal_path.read_text(encoding="utf-8").strip().splitlines() == [
        "requested_model\tmatch_type\tendpoint\tprovider\tupstream_model\tpriority\tenabled\tvisible_in_models\tsupports_streaming\tcapabilities\tnotes"
    ]
    assert result.pricing_proposal_path.read_text(encoding="utf-8").strip().splitlines() == [
        "provider\tmodel\tendpoint\tcurrency\tinput_price_per_1m\tcached_input_price_per_1m\toutput_price_per_1m\treasoning_price_per_1m\trequest_price\tvalid_from\tsource_url\tsource_retrieved_at\tpricing_metadata\tnotes"
    ]


def test_provider_catalog_skill_exists_and_is_repo_local() -> None:
    skill_path = Path("agents/skills/provider-catalog-proposal/SKILL.md")
    assert skill_path.exists()
    assert skill_path.read_text(encoding="utf-8").lower().count("proposal-only") >= 1
    assert not Path(".codex/skills/provider-catalog-proposal/SKILL.md").exists()
