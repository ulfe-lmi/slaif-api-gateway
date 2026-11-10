from __future__ import annotations

import json
import uuid
from pathlib import Path
from datetime import UTC, datetime
from decimal import Decimal

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
    ProviderCatalogPricingCandidate,
    ProviderCatalogProposalValidationError,
    ProviderCatalogProposalResult,
    ProposalFxCapture,
    _build_chat_capabilities,
    _openrouter_model_warnings,
    _confirm_openrouter_pricing_unit,
    _openrouter_pricing_candidate,
    _parse_openai_models_docs,
    _parse_openai_pricing_docs,
    _validate_generated_pricing_tsv,
    apply_proposal_fx,
    make_proposal_fx_capture,
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
                "input_modalities": ["text"],
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
            "id": "openai/gpt-test-image",
            "canonical_slug": "openai/gpt-test-image",
            "name": "GPT Test Image",
            "description": "Image-capable model that should be report-only in ordinary chat mode",
            "context_length": 128000,
            "architecture": {
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
            },
            "pricing": {
                "prompt": "0.000004",
                "completion": "0.000010",
            },
            "top_provider": {"context_length": 128000, "max_completion_tokens": 8192},
            "supported_parameters": [
                "tools",
                "response_format",
            ],
            "knowledge_cutoff": "2025-01",
            "expiration_date": None,
            "links": {},
        },
        {
            "id": "openrouter/owl-alpha",
            "canonical_slug": "openrouter/owl-alpha",
            "name": "OWL Alpha",
            "description": "Zero-price text model",
            "context_length": 128000,
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["text"],
            },
            "pricing": {
                "prompt": "0",
                "completion": "0",
            },
            "top_provider": {"context_length": 128000, "max_completion_tokens": 8192},
            "supported_parameters": ["tools"],
            "knowledge_cutoff": "2025-01",
            "expiration_date": None,
            "links": {},
        },
        {
            "id": "openai/gpt-test-audio-in",
            "canonical_slug": "openai/gpt-test-audio-in",
            "name": "GPT Test Audio In",
            "description": "Audio-input to text-output model",
            "context_length": 64000,
            "architecture": {
                "input_modalities": ["text", "audio"],
                "output_modalities": ["text"],
            },
            "pricing": {
                "prompt": "0.000003",
                "completion": "0.000009",
            },
            "top_provider": {"context_length": 64000, "max_completion_tokens": 4096},
            "supported_parameters": ["tools", "audio"],
            "knowledge_cutoff": "2025-01",
            "expiration_date": None,
            "links": {},
        },
        {
            "id": "openai/gpt-test-realtime",
            "canonical_slug": "openai/gpt-test-realtime",
            "name": "GPT Test Realtime",
            "description": "Realtime family model that should stay out of safe packages",
            "context_length": 64000,
            "architecture": {
                "input_modalities": ["text", "audio"],
                "output_modalities": ["text"],
            },
            "pricing": {
                "prompt": "0.000003",
                "completion": "0.000009",
            },
            "top_provider": {"context_length": 64000, "max_completion_tokens": 4096},
            "supported_parameters": ["tools", "audio"],
            "knowledge_cutoff": "2025-01",
            "expiration_date": None,
            "links": {},
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
        ordinary_chat_only=True,
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
    assert result.route_rows_ready == 2
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

    assert route_preview.valid_count == 2
    assert pricing_preview.valid_count == 1
    route_models = {row.requested_model for row in route_preview.rows}
    assert route_models == {"openai/gpt-test-mini", "openrouter/owl-alpha"}
    assert all(row.endpoint == CHAT_COMPLETIONS_ENDPOINT for row in route_preview.rows)
    pricing_row = pricing_preview.rows[0]
    assert pricing_row.model == "openai/gpt-test-mini"
    assert pricing_row.input_price_per_1m == "2"
    assert "sk-" not in result.normalized_path.read_text(encoding="utf-8")

    warnings_payload = json.loads(result.warnings_path.read_text(encoding="utf-8"))
    warning_codes = {item["code"] for item in warnings_payload["warnings"]}
    assert "search_specific_model" in warning_codes


@pytest.mark.asyncio
async def test_generate_openrouter_catalog_proposal_paired_ready_and_ordinary_chat_only(
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
        paired_ready_only=True,
        ordinary_chat_only=True,
    )

    assert result.route_rows_ready == 1
    assert result.pricing_rows_ready == 1

    route_tsv = result.routes_proposal_path.read_text(encoding="utf-8")
    pricing_tsv = result.pricing_proposal_path.read_text(encoding="utf-8")

    assert "openai/gpt-test-mini" in route_tsv
    assert "openai/gpt-test-mini" in pricing_tsv
    assert "openai/gpt-test-image" not in route_tsv
    assert "openai/gpt-test-image" not in pricing_tsv
    assert "openrouter/owl-alpha" not in route_tsv
    assert "openrouter/owl-alpha" not in pricing_tsv

    report_text = result.report_path.read_text(encoding="utf-8")
    assert "Paired ready only: yes" in report_text
    assert "Ordinary chat only: yes" in report_text


@pytest.mark.asyncio
async def test_generate_openrouter_catalog_proposal_can_opt_into_multimodal_candidates(
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
        ordinary_chat_only=False,
    )

    route_tsv = result.routes_proposal_path.read_text(encoding="utf-8")
    pricing_tsv = result.pricing_proposal_path.read_text(encoding="utf-8")
    assert "openai/gpt-test-image" in route_tsv
    assert "openai/gpt-test-image" in pricing_tsv


@pytest.mark.asyncio
async def test_generate_openrouter_catalog_proposal_writes_package_presets(
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
        return_value=httpx.Response(200, json={"data": {"max_completion_tokens": 8192}})
    )

    result = await generate_provider_catalog_proposal(
        provider_scope="openrouter",
        output_dir=tmp_path,
        fetch_details_limit=1,
        package_names=(
            "openrouter-chat-text",
            "openrouter-chat-image",
            "openrouter-chat-audio",
            "openrouter-chat-multimodal",
            "openrouter-responses-text",
        ),
    )

    assert result.package_index_path is not None
    assert result.package_index_markdown_path is not None
    assert result.package_index_path.exists()
    assert result.package_index_markdown_path.exists()

    packages_dir = tmp_path / "packages"
    chat_text = packages_dir / "openrouter-chat-text"
    chat_image = packages_dir / "openrouter-chat-image"
    chat_audio = packages_dir / "openrouter-chat-audio"
    chat_multimodal = packages_dir / "openrouter-chat-multimodal"
    responses_text = packages_dir / "openrouter-responses-text"

    for package_dir in (chat_text, chat_image, chat_audio, chat_multimodal, responses_text):
        assert (package_dir / "package-manifest.json").exists()
        assert (package_dir / "routes-proposal.tsv").exists()
        assert (package_dir / "pricing-proposal.tsv").exists()
        assert (package_dir / "model-review.md").exists()
        assert (package_dir / "package-report.md").exists()

    def route_keys(path: Path) -> set[tuple[str, str, str]]:
        rows = parse_route_import_tsv(path.read_text(encoding="utf-8"))
        return {(row["provider"], row["upstream_model"], row["endpoint"]) for row in rows}

    def pricing_keys(path: Path) -> set[tuple[str, str, str]]:
        rows = parse_pricing_import_tsv(path.read_text(encoding="utf-8"))
        return {(row["provider"], row["model"], row["endpoint"]) for row in rows}

    text_route_keys = route_keys(chat_text / "routes-proposal.tsv")
    image_route_keys = route_keys(chat_image / "routes-proposal.tsv")
    audio_route_keys = route_keys(chat_audio / "routes-proposal.tsv")
    multimodal_route_keys = route_keys(chat_multimodal / "routes-proposal.tsv")
    responses_route_keys = route_keys(responses_text / "routes-proposal.tsv")

    assert text_route_keys == pricing_keys(chat_text / "pricing-proposal.tsv")
    assert image_route_keys == pricing_keys(chat_image / "pricing-proposal.tsv")
    assert audio_route_keys == pricing_keys(chat_audio / "pricing-proposal.tsv")
    assert multimodal_route_keys == pricing_keys(chat_multimodal / "pricing-proposal.tsv")
    assert responses_route_keys == pricing_keys(responses_text / "pricing-proposal.tsv")

    assert text_route_keys <= image_route_keys
    assert image_route_keys <= audio_route_keys
    assert audio_route_keys <= multimodal_route_keys
    assert not text_route_keys <= responses_route_keys

    assert ("openrouter", "openai/gpt-test-mini", CHAT_COMPLETIONS_ENDPOINT) in text_route_keys
    assert ("openrouter", "openai/gpt-test-image", CHAT_COMPLETIONS_ENDPOINT) not in text_route_keys
    assert ("openrouter", "openai/gpt-test-image", CHAT_COMPLETIONS_ENDPOINT) in image_route_keys
    assert ("openrouter", "openai/gpt-test-audio-in", CHAT_COMPLETIONS_ENDPOINT) not in audio_route_keys
    assert ("openrouter", "openai/gpt-test-realtime", CHAT_COMPLETIONS_ENDPOINT) not in audio_route_keys
    assert len(responses_route_keys) == 0

    review_text = (chat_text / "model-review.md").read_text(encoding="utf-8")
    assert "<table>" in review_text
    assert "input USD per 1M" in review_text
    assert "—" in review_text
    assert "Authorization" not in review_text
    assert "sk-" not in review_text


@pytest.mark.asyncio
async def test_generate_openrouter_catalog_proposal_can_include_ambiguous_audio_package_rows(
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
        return_value=httpx.Response(200, json={"data": {"max_completion_tokens": 8192}})
    )

    await generate_provider_catalog_proposal(
        provider_scope="openrouter",
        output_dir=tmp_path,
        fetch_details_limit=1,
        package_names=("openrouter-chat-audio",),
        include_ambiguous_capabilities=True,
    )

    audio_keys = {
        (row["provider"], row["upstream_model"], row["endpoint"])
        for row in parse_route_import_tsv(
            (tmp_path / "packages" / "openrouter-chat-audio" / "routes-proposal.tsv").read_text(
                encoding="utf-8"
            )
        )
    }

    assert ("openrouter", "openai/gpt-test-audio-in", CHAT_COMPLETIONS_ENDPOINT) in audio_keys
    assert ("openrouter", "openai/gpt-test-realtime", CHAT_COMPLETIONS_ENDPOINT) not in audio_keys


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
    assert result.route_rows_ready == 0
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

    assert result.route_rows_ready == 1
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

    assert "gpt-5.5" not in route_tsv
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


OPENAI_TWO_CHAT_MODELS_DOC = """
## gpt-5.5
Endpoints: /v1/chat/completions
Features: streaming
Context length: 400000
Max output tokens: 16384

## gpt-5.6
Endpoints: /v1/chat/completions
Features: streaming
Context length: 256000
Max output tokens: 8192
"""


@pytest.mark.asyncio
async def test_generate_openai_honors_max_models_cap_with_honest_omission(
    tmp_path: Path,
    respx_mock,
) -> None:
    """The EXISTING public max_models cap is honored for OpenAI too
    (same-service argument, applied AFTER the include/exclude filtering):
    cap 1 of two eligible models keeps the deterministic sorted-first id
    and reports the omitted scope honestly in the warnings. A within-cap
    catalog keeps its current default output (no cap warning)."""
    respx_mock.get(OPENAI_PRICING_DOCS_URL).mock(
        return_value=httpx.Response(200, text="Pricing\n")
    )
    respx_mock.get(OPENAI_MODELS_DOCS_URL).mock(
        return_value=httpx.Response(200, text=OPENAI_TWO_CHAT_MODELS_DOC)
    )
    result = await generate_provider_catalog_proposal(
        provider_scope="openai",
        output_dir=tmp_path / "capped",
        source_methods=("docs",),
        endpoint_scopes=("chat_completions",),
        max_models=1,
    )
    normalized = json.loads(result.normalized_path.read_text(encoding="utf-8"))
    kept = {item["model_id"] for item in normalized["models"]}
    assert kept == {"gpt-5.5"}  # deterministic sorted-first within the cap
    warnings_payload = json.loads(result.warnings_path.read_text(encoding="utf-8"))
    cap_warnings = [
        item for item in warnings_payload["warnings"] if item["code"] == "model_cap_applied"
    ]
    assert len(cap_warnings) == 1
    assert "omitted 1" in cap_warnings[0]["message"]
    assert "gpt-5.6" in cap_warnings[0]["message"]
    assert "max_models=1" in cap_warnings[0]["message"]

    # legacy regression: within the cap, the default output is unchanged
    # (both models, no cap warning).
    result_full = await generate_provider_catalog_proposal(
        provider_scope="openai",
        output_dir=tmp_path / "within",
        source_methods=("docs",),
        endpoint_scopes=("chat_completions",),
    )
    normalized_full = json.loads(result_full.normalized_path.read_text(encoding="utf-8"))
    kept_full = {item["model_id"] for item in normalized_full["models"]}
    assert kept_full == {"gpt-5.5", "gpt-5.6"}
    warnings_full = json.loads(result_full.warnings_path.read_text(encoding="utf-8"))
    assert not any(
        item["code"] == "model_cap_applied" for item in warnings_full["warnings"]
    )


# --- FX conversion (human-approved real FX, one configured direct USD->target row) ---

FX_RATE_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def _fx_capture(**overrides) -> ProposalFxCapture:
    values = dict(
        target_currency="EUR",
        fx_rate_id=FX_RATE_ID,
        rate=Decimal("1.083"),
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=None,
        captured_at=datetime(2026, 6, 9, tzinfo=UTC),
    )
    values.update(overrides)
    return make_proposal_fx_capture(**values)


def _fx_candidate(**overrides) -> ProviderCatalogPricingCandidate:
    values = dict(
        provider="openrouter",
        model_id="openai/gpt-test-mini",
        endpoint=CHAT_COMPLETIONS_ENDPOINT,
        currency="USD",
        input_price_per_1m="2",
        cached_input_price_per_1m="1",
        output_price_per_1m="8",
        reasoning_price_per_1m="3",
        request_price="0.1",
        source_url=OPENROUTER_MODELS_API_URL,
        source_retrieved_at="2026-06-09T00:00:00Z",
        pricing_metadata={"pricing_unit": "usd_per_token"},
        notes="synthetic",
        confidence="high",
        ready_for_import=True,
    )
    values.update(overrides)
    return ProviderCatalogPricingCandidate(**values)


def test_make_proposal_fx_capture_valid_and_fail_closed() -> None:
    capture = _fx_capture()
    assert capture.base_currency == "USD"
    assert capture.target_currency == "EUR"  # normalized from "eur"-shaped input
    assert capture.fx_rate_id == str(FX_RATE_ID)
    assert capture.rate == "1.083"
    assert capture.valid_from == "2026-01-01T00:00:00Z"
    assert capture.valid_until is None
    assert capture.captured_at == "2026-06-09T00:00:00Z"
    # the uuid fact is canonical (string fact in, canonical UUID string out)
    assert _fx_capture(fx_rate_id=str(FX_RATE_ID)).fx_rate_id == str(FX_RATE_ID)

    bad_targets = ["US", "1US", "EU R"]
    for target in bad_targets:
        with pytest.raises(ValueError, match="3-letter"):
            _fx_capture(target_currency=target)
    for rate in (Decimal("0"), Decimal("-1"), Decimal("NaN")):
        with pytest.raises(ValueError, match="positive finite"):
            _fx_capture(rate=rate)
    with pytest.raises(ValueError, match="valid_from"):
        _fx_capture(valid_from=datetime(2026, 1, 1))
    # naive valid_until is refused BEFORE the window comparison (safe
    # ValueError, never a TypeError from an aware/naive compare)
    with pytest.raises(ValueError, match="valid_until"):
        _fx_capture(valid_until=datetime(2027, 1, 1))
    with pytest.raises(ValueError, match="empty"):
        _fx_capture(
            valid_until=datetime(2025, 12, 31, tzinfo=UTC)
        )
    with pytest.raises(ValueError, match="capture time"):
        _fx_capture(captured_at=datetime(2026, 6, 9))
    with pytest.raises(ValueError, match="not yet valid"):
        _fx_capture(captured_at=datetime(2025, 1, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="expired"):
        _fx_capture(
            valid_until=datetime(2026, 6, 9, tzinfo=UTC)
        )
    with pytest.raises(ValueError, match="UUID"):
        _fx_capture(fx_rate_id="not-a-uuid")


def test_convert_proposal_price_text_numeric_contract() -> None:
    from slaif_gateway.services.provider_catalog_proposal import (
        _convert_proposal_price_text,
    )

    assert _convert_proposal_price_text(None, Decimal("1.083")) is None
    assert _convert_proposal_price_text("0", Decimal("1.083")) == "0"
    # exact values
    assert _convert_proposal_price_text("2", Decimal("1.083")) == "2.166"
    assert _convert_proposal_price_text("0.5", Decimal("1.083")) == "0.5415"
    # the established 9-fraction contract round-trips at the quantum
    assert _convert_proposal_price_text("0.000000001", Decimal("1")) == "0.000000001"
    # ROUND_HALF_UP at the 9th fraction
    assert _convert_proposal_price_text("1", Decimal("1.0000000005")) == "1.000000001"
    # positive-to-zero underflow is refused (never a silent free price)
    with pytest.raises(ValueError, match="underflow"):
        _convert_proposal_price_text("0.000000001", Decimal("0.0000001"))
    # overflow beyond the Numeric(18,9) import bound is refused
    with pytest.raises(ValueError, match="overflow"):
        _convert_proposal_price_text("999999999.999999999", Decimal("2"))
    # contract violations are refused BEFORE arithmetic
    for bad in ("abc", "1e999", "-1", "1.2345678901"):
        with pytest.raises(ValueError):
            _convert_proposal_price_text(bad, Decimal("1.083"))


def test_apply_proposal_fx_identity_conversion_and_double_apply_refusal() -> None:
    candidate = _fx_candidate()
    # USD identity: None capture or USD->USD capture leave rows unchanged
    assert apply_proposal_fx([candidate], None) == [candidate]
    identity = _fx_capture(target_currency="USD")
    assert apply_proposal_fx([candidate], identity) == [candidate]

    converted = apply_proposal_fx([candidate], _fx_capture())
    assert len(converted) == 1
    row = converted[0]
    assert row.currency == "EUR"
    assert row.input_price_per_1m == "2.166"
    assert row.cached_input_price_per_1m == "1.083"
    assert row.output_price_per_1m == "8.664"
    assert row.reasoning_price_per_1m == "3.249"
    assert row.request_price == "0.1083"
    # original USD amounts + the applied FX facts are preserved
    assert row.pricing_metadata["source_currency"] == "USD"
    assert row.pricing_metadata["source_prices"] == {
        "input_price_per_1m": "2",
        "cached_input_price_per_1m": "1",
        "output_price_per_1m": "8",
        "reasoning_price_per_1m": "3",
        "request_price": "0.1",
    }
    assert row.pricing_metadata["fx"]["fx_rate_id"] == str(FX_RATE_ID)
    assert row.pricing_metadata["fx"]["rate"] == "1.083"
    # the OFFICIAL SOURCE unit is never relabeled
    assert row.pricing_metadata["pricing_unit"] == "usd_per_token"
    # missing/zero semantics preserved
    sparse = _fx_candidate(
        cached_input_price_per_1m=None, reasoning_price_per_1m=None, request_price="0"
    )
    sparse_row = apply_proposal_fx([sparse], _fx_capture())[0]
    assert sparse_row.cached_input_price_per_1m is None
    assert sparse_row.reasoning_price_per_1m is None
    assert sparse_row.request_price == "0"
    # double application is impossible, not silent
    with pytest.raises(ValueError, match="double application"):
        apply_proposal_fx([row], _fx_capture())


def _mock_openrouter(respx_mock) -> None:
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


@pytest.mark.asyncio
async def test_generate_openrouter_catalog_proposal_non_usd_fx_conversion(
    tmp_path: Path,
    respx_mock,
) -> None:
    """ONE captured configured USD->EUR rate converts EVERY monetary
    dimension before ANY writer; root and package artifacts agree and
    the strict import consumer accepts the converted output."""
    _mock_openrouter(respx_mock)
    result = await generate_provider_catalog_proposal(
        provider_scope="openrouter",
        output_dir=tmp_path,
        fetch_details_limit=1,
        currency="EUR",
        fx_capture=_fx_capture(),
        package_names=("openrouter-chat-text",),
    )
    assert result.pricing_rows_ready == 1

    # strict import consumer accepts the CONVERTED rows (EUR, converted)
    rows = parse_pricing_import_tsv(result.pricing_proposal_path.read_text(encoding="utf-8"))
    preview = validate_pricing_import_rows(rows, max_rows=10)
    assert preview.valid_count == 1
    row = preview.rows[0]
    assert row.currency == "EUR"
    assert row.input_price_per_1m == "2.166"
    assert row.cached_input_price_per_1m == "1.083"
    assert row.output_price_per_1m == "8.664"
    assert row.reasoning_price_per_1m == "3.249"
    assert row.request_price == "0"  # zero preserved, never scaled
    # the row metadata carries the source USD facts + the applied FX pair
    metadata = rows[0]["pricing_metadata"]
    assert '"source_currency":"USD"' in metadata
    assert '"source_prices"' in metadata
    assert '"fx_rate_id":"' + str(FX_RATE_ID) + '"' in metadata

    # root normalized JSON: fx fact + source amounts visible
    normalized = json.loads(result.normalized_path.read_text(encoding="utf-8"))
    assert normalized["fx"]["target_currency"] == "EUR"
    assert normalized["fx"]["rate"] == "1.083"
    assert normalized["fx"]["fx_rate_id"] == str(FX_RATE_ID)
    pricing_doc = normalized["pricing_candidates"][0]
    assert pricing_doc["currency"] == "EUR"
    assert pricing_doc["pricing_metadata"]["source_prices"]["input_price_per_1m"] == "2"
    assert pricing_doc["pricing_metadata"]["pricing_unit"] == "usd_per_token"

    # manifest agrees with the same capture (no double conversion)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["fx"] == normalized["fx"]

    # report states the applied conversion truthfully
    report = result.report_path.read_text(encoding="utf-8")
    assert "Output currency: EUR" in report
    assert "1.083" in report
    assert str(FX_RATE_ID) in report

    # the PACKAGE output is converted with the SAME capture
    package_dir = tmp_path / "packages" / "openrouter-chat-text"
    package_rows = parse_pricing_import_tsv(
        (package_dir / "pricing-proposal.tsv").read_text(encoding="utf-8")
    )
    package_preview = validate_pricing_import_rows(package_rows, max_rows=10)
    assert package_preview.valid_count == 1
    assert package_preview.rows[0].currency == "EUR"
    assert package_preview.rows[0].input_price_per_1m == "2.166"
    # the package review labels the DISPLAYED currency (not hardcoded USD)
    review = (package_dir / "model-review.md").read_text(encoding="utf-8")
    assert "input EUR per 1M" in review
    assert "input USD per 1M" not in review


@pytest.mark.asyncio
async def test_generate_openrouter_catalog_proposal_usd_keeps_native_and_fx_absent(
    tmp_path: Path,
    respx_mock,
) -> None:
    """USD output is the identity conversion: byte-identical native
    values, NO fx metadata anywhere, no capture (and no database)
    required."""
    _mock_openrouter(respx_mock)
    result = await generate_provider_catalog_proposal(
        provider_scope="openrouter",
        output_dir=tmp_path,
        fetch_details_limit=1,
    )
    rows = parse_pricing_import_tsv(result.pricing_proposal_path.read_text(encoding="utf-8"))
    assert rows[0]["currency"] == "USD"
    assert rows[0]["input_price_per_1m"] == "2"
    normalized = json.loads(result.normalized_path.read_text(encoding="utf-8"))
    assert normalized["fx"] is None
    assert normalized["pricing_candidates"][0]["pricing_metadata"].get("source_prices") is None
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["fx"] is None
    assert "Output currency:" not in result.report_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_generate_proposal_rejects_non_usd_without_capture_or_mismatched_capture(
    tmp_path: Path,
    respx_mock,
) -> None:
    """Non-USD without a capture (or with a mismatched capture) is
    refused BEFORE any directory/network work: no output directory is
    created and no source request is made (never silent relabeling)."""
    _mock_openrouter(respx_mock)
    out_dir = tmp_path / "out"
    with pytest.raises(ValueError, match="fx capture"):
        await generate_provider_catalog_proposal(
            provider_scope="openrouter",
            output_dir=out_dir,
            currency="EUR",
        )
    assert not out_dir.exists()
    # a capture for a DIFFERENT target currency is refused too
    with pytest.raises(ValueError, match="target does not match"):
        await generate_provider_catalog_proposal(
            provider_scope="openrouter",
            output_dir=tmp_path / "out2",
            currency="EUR",
            fx_capture=_fx_capture(target_currency="GBP"),
        )
    assert not (tmp_path / "out2").exists()


@pytest.mark.asyncio
async def test_generate_openai_assisted_non_usd_keeps_native_source_and_converts_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock,
) -> None:
    """The OpenAI-assisted seam receives NATIVE USD (never asked to
    invent or apply exchange rates); the requested non-USD output is
    produced by the ONE captured configured rate AFTER the assisted
    cross-check, with the source USD facts preserved."""
    monkeypatch.setenv(OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR, "admin-discovery-key")
    respx_mock.get(OPENAI_PRICING_DOCS_URL).mock(
        return_value=httpx.Response(200, text=OPENAI_PRICING_DOC_FIXTURE)
    )
    respx_mock.get(OPENAI_MODELS_DOCS_URL).mock(
        return_value=httpx.Response(200, text=OPENAI_MODELS_DOC_FIXTURE)
    )

    assisted_kwargs: dict[str, dict[str, object]] = {}

    async def fake_pricing_cross_check(**kwargs) -> OpenAIAssistedProposalTextResult:  # noqa: ANN003
        assisted_kwargs["pricing"] = kwargs
        return OpenAIAssistedProposalTextResult(
            proposal_type="pricing",
            tsv_text=(
                "provider\tmodel\tendpoint\tcurrency\tinput_price_per_1m\t"
                "cached_input_price_per_1m\toutput_price_per_1m\treasoning_price_per_1m\t"
                "request_price\tvalid_from\tsource_url\tsource_retrieved_at\tpricing_metadata\tnotes\n"
                "openai\tgpt-5.5\t/v1/chat/completions\tUSD\t5\t0.5\t15\t\t\t"
                "2026-06-09T00:00:00Z\thttps://developers.openai.com/api/docs/pricing\t"
                "2026-06-09T00:00:00Z\t{}\tsafe\n"
            ),
            row_count=1,
            warnings=(),
            source_urls=(OPENAI_PRICING_DOCS_URL, OPENAI_MODELS_DOCS_URL),
        )

    async def fake_route_cross_check(**kwargs) -> OpenAIAssistedProposalTextResult:  # noqa: ANN003
        assisted_kwargs["route"] = kwargs
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

    rate = Decimal("0.84")
    result = await generate_provider_catalog_proposal(
        provider_scope="openai",
        output_dir=tmp_path,
        source_methods=("docs", "assisted"),
        acknowledge_assisted_proposal_risk=True,
        currency="GBP",
        fx_capture=_fx_capture(target_currency="GBP", rate=rate),
    )
    # the assisted helpers were given the NATIVE source currency, not GBP
    assert assisted_kwargs["pricing"]["currency"] == "USD"
    assert "currency" not in assisted_kwargs["route"] or assisted_kwargs["route"].get("currency") == "USD"

    rows = parse_pricing_import_tsv(result.pricing_proposal_path.read_text(encoding="utf-8"))
    preview = validate_pricing_import_rows(rows, max_rows=10)
    assert preview.valid_count == 1
    row = preview.rows[0]
    # docs 5.00/0.50/15.00 USD per 1M converted with the ONE captured rate
    assert row.currency == "GBP"
    assert row.input_price_per_1m == "4.2"
    assert row.cached_input_price_per_1m == "0.42"
    assert row.output_price_per_1m == "12.6"
    # source USD facts preserved in the row metadata
    metadata = rows[0]["pricing_metadata"]
    assert '"source_currency":"USD"' in metadata
    assert '"input_price_per_1m":"5"' in metadata.replace(" ", "")
    normalized = json.loads(result.normalized_path.read_text(encoding="utf-8"))
    assert normalized["fx"]["target_currency"] == "GBP"
    assert normalized["fx"]["rate"] == "0.84"
