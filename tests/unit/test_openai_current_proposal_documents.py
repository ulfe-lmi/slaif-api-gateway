from __future__ import annotations

import csv
import json

import pytest

from slaif_gateway.services.provider_catalog_proposal import (
    OPENAI_MODELS_API_URL, OPENAI_MODELS_DOCS_URL, OPENAI_PRICING_DOCS_URL,
    _parse_openai_pricing_docs, generate_provider_catalog_proposal,
)

PRICING = '''# Pricing
### Standard pricing data
| Model | Input | Cached input | Output |
| --- | --- | --- | --- |
| gpt-test-mini | $1.00 | $0.10 | $3.00 |
### Batch pricing data
| Model | Input | Cached input | Output |
| --- | --- | --- | --- |
| gpt-test-mini | $0.50 | $0.05 | $1.50 |
'''
INDEX = '- [Test mini](/api/docs/models/gpt-test-mini.md): Test model\n'
PAGE = '''# Test mini
Model ID: `gpt-test-mini`
- Input modalities: text, image
- Output modalities: text
- 100,000 context window
- 8,192 max output tokens
## Endpoints
| Endpoint | Route | Support |
| --- | --- | --- |
| Chat Completions | `v1/chat/completions` | Supported |
| Responses | `v1/responses` | Supported |
## Supported features
- streaming
- function_calling
- web_search
'''


def test_standard_prices_never_select_batch_prices():
    rows = _parse_openai_pricing_docs(text=PRICING, source_url='official', source_retrieved_at='2026-11-11')
    assert len(rows) == 1
    assert rows[0].input_price_per_1m == '1'
    assert rows[0].output_price_per_1m == '3'


@pytest.mark.asyncio
@pytest.mark.parametrize('api', [False, True])
@pytest.mark.parametrize('page_change,expected', [
    ('unchanged', 1), ('wrong_identity', 0), ('unsupported_chat', 0), ('deprecated', 0),
])
async def test_current_index_requires_page_backed_contract(tmp_path, respx_mock, monkeypatch, api, page_change, expected):
    monkeypatch.setenv('OPENAI_ADMIN_DISCOVERY_API_KEY', 'test-provider-credential')
    respx_mock.get(OPENAI_MODELS_DOCS_URL).respond(200, text='<html><body>Model index navigation</body></html>')
    respx_mock.get(OPENAI_PRICING_DOCS_URL).respond(200, text='<html><body>Pricing navigation</body></html>')
    respx_mock.get(OPENAI_MODELS_DOCS_URL+'.md').respond(200, text=INDEX)
    respx_mock.get(OPENAI_PRICING_DOCS_URL+'.md').respond(200, text=PRICING)
    page = PAGE
    if page_change == 'wrong_identity':
        page = page.replace('Model ID: `gpt-test-mini`', 'Model ID: `gpt-other-model`')
    if page_change == 'unsupported_chat':
        page = page.replace('`v1/chat/completions` | Supported', '`v1/chat/completions` | Not supported')
    if page_change == 'deprecated':
        page += '\nStatus: Deprecated\n'
    respx_mock.get(OPENAI_MODELS_DOCS_URL+'/gpt-test-mini.md').respond(200, text=page)
    if api:
        respx_mock.get(OPENAI_MODELS_API_URL).respond(200, json={'data':[{'id':'gpt-test-mini'}]})
    result = await generate_provider_catalog_proposal(
        provider_scope='openai', output_dir=tmp_path, paired_ready_only=True,
        source_methods=('docs', 'api') if api else ('docs',),
    )
    routes = list(csv.DictReader(result.routes_proposal_path.open(), delimiter='\t'))
    prices = list(csv.DictReader(result.pricing_proposal_path.open(), delimiter='\t'))
    assert len(routes) == len(prices) == expected
    if expected:
        assert '/api/docs/models/gpt-test-mini.md' in routes[0]['notes']
        assert prices[0]['input_price_per_1m'] == '1'
        caps = json.loads(routes[0]['capabilities'])
        assert caps['chat_completions'].get('hosted_web_search', False) is False
        assert caps['chat_completions'].get('chat_image_inputs', False) is False
