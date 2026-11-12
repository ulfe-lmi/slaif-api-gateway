from __future__ import annotations

import csv
import json

import pytest

from slaif_gateway.services.provider_catalog_proposal import (
    CHAT_COMPLETIONS_ENDPOINT as CHAT, RESPONSES_ENDPOINT as RESP,
    OPENAI_MODELS_DOCS_URL, OPENAI_PRICING_DOCS_URL,
    OPENROUTER_MODELS_API_URL, OPENROUTER_MODELS_DOCS_MARKDOWN_URL,
    generate_provider_catalog_proposal,
)


def rows(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter='\t'))


def mock_sources(respx_mock, provider, *, missing_response=False):
    if provider == 'openai':
        respx_mock.get(OPENAI_PRICING_DOCS_URL).respond(200, text='''
| Model | Input | Cached input | Output |
| --- | --- | --- | --- |
| gpt-test-dual | $1 | $0.1 | $2 |
| gpt-test-response | $3 | $0.3 | $4 |
''')
        respx_mock.get(OPENAI_MODELS_DOCS_URL).respond(200, text='''
## gpt-test-dual
Endpoints: /v1/chat/completions, /v1/responses
Features: streaming, function calling, structured outputs
Context length: 32000
## gpt-test-response
Endpoints: /v1/responses
Features: streaming
Context length: 32000
''')
        return ['gpt-test-dual', 'gpt-test-response']
    models = []
    for suffix, endpoints in [('dual',[CHAT,RESP]), ('response',[RESP])]:
        models.append({
            'id':'vendor/test-'+suffix,
            'endpoints':[] if missing_response else ['/api'+e for e in endpoints],
            'architecture':{'input_modalities':['text'],'output_modalities':['text']},
            'pricing':{'prompt':'0.000001','completion':'0.000002'},
            'supported_parameters':['tools','structured_outputs'],
        })
    respx_mock.get(OPENROUTER_MODELS_API_URL).respond(200,json={'data':models})
    respx_mock.get(OPENROUTER_MODELS_DOCS_MARKDOWN_URL).respond(
        200,text='All pricing values are in USD per token/request/unit')
    return ['vendor/test-dual','vendor/test-response']


@pytest.mark.asyncio
@pytest.mark.parametrize('provider',['openai','openrouter'])
@pytest.mark.parametrize('scopes',[
    ('responses',),('chat_completions',),('chat_completions','responses'),
])
async def test_selected_endpoint_scopes_control_routes_and_pricing(tmp_path,respx_mock,provider,scopes):
    ids = mock_sources(respx_mock,provider)
    result = await generate_provider_catalog_proposal(
        provider_scope=provider,output_dir=tmp_path,endpoint_scopes=scopes,
        paired_ready_only=True,source_methods=('docs',),fetch_details_limit=0,
    )
    routes = rows(result.routes_proposal_path)
    pricing = rows(result.pricing_proposal_path)
    expected = set()
    if 'chat_completions' in scopes:
        expected.add((ids[0],CHAT))
    if 'responses' in scopes:
        expected.update((m,RESP) for m in ids)
    assert {(r['requested_model'],r['endpoint']) for r in routes} == expected
    assert {(r['model'],r['endpoint']) for r in pricing} == expected
    for route in routes:
        if route['endpoint'] == RESP:
            caps = json.loads(route['capabilities'])
            assert 'chat_completions' not in caps
            assert caps['responses']['text'] is True
            assert caps['responses']['stateless'] is True
            for key in ['storage','stored_responses','previous_response_id','background',
                        'image_input','custom_tools','codex_request_envelope','codex_client_tools']:
                assert caps['responses'].get(key,False) is False
    warnings = json.loads(result.warnings_path.read_text())['warnings']
    assert not any(w['code']=='future_endpoint' for w in warnings)


@pytest.mark.asyncio
async def test_openrouter_responses_requires_explicit_model_endpoint_evidence(tmp_path,respx_mock):
    mock_sources(respx_mock,'openrouter',missing_response=True)
    result=await generate_provider_catalog_proposal(
        provider_scope='openrouter',output_dir=tmp_path,endpoint_scopes=('responses',),
        paired_ready_only=True,fetch_details_limit=0,
    )
    assert rows(result.routes_proposal_path) == rows(result.pricing_proposal_path) == []
    warnings=json.loads(result.warnings_path.read_text())['warnings']
    assert any(w['code']=='endpoint_support_unconfirmed' for w in warnings)


@pytest.mark.asyncio
async def test_responses_package_contains_only_evidenced_response_pairs(tmp_path,respx_mock):
    ids=mock_sources(respx_mock,'openrouter')
    result=await generate_provider_catalog_proposal(
        provider_scope='openrouter',output_dir=tmp_path,endpoint_scopes=('responses',),
        paired_ready_only=True,fetch_details_limit=0,package_names=('openrouter-responses-text',),
    )
    package=tmp_path/'packages'/'openrouter-responses-text'
    assert {(r['requested_model'],r['endpoint']) for r in rows(package/'routes-proposal.tsv')} == {(m,RESP) for m in ids}
    assert {(r['model'],r['endpoint']) for r in rows(package/'pricing-proposal.tsv')} == {(m,RESP) for m in ids}
    assert result.route_rows_ready == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('provider',['openai','openrouter'])
async def test_responses_text_projection_is_independent_of_chat_only_filter(tmp_path,respx_mock,provider):
    ids=mock_sources(respx_mock,provider)
    if provider=='openai':
        respx_mock.get(OPENAI_MODELS_DOCS_URL).respond(200,text='''
## gpt-test-dual
Endpoints: /v1/responses
Features: streaming, image input
Context length: 32000
''')
    else:
        respx_mock.get(OPENROUTER_MODELS_API_URL).respond(200,json={'data':[{
            'id':ids[0], 'endpoints':['/api/v1/responses'],
            'architecture':{'input_modalities':['text','image'],'output_modalities':['text']},
            'pricing':{'prompt':'0.000001','completion':'0.000002'},
        }]})
    result=await generate_provider_catalog_proposal(
        provider_scope=provider,output_dir=tmp_path,endpoint_scopes=('responses',),
        paired_ready_only=True,ordinary_chat_only=True,fetch_details_limit=0,
    )
    routes=rows(result.routes_proposal_path)
    assert len(routes)==1
    assert routes[0]['endpoint']==RESP
    caps=json.loads(routes[0]['capabilities'])['responses']
    assert caps.get('image_input',False) is False
    assert caps.get('codex_client_tools',False) is False


@pytest.mark.asyncio
async def test_official_responses_model_needs_neither_gpt_name_nor_featured_index_entry(tmp_path,respx_mock):
    respx_mock.get(OPENAI_PRICING_DOCS_URL).respond(200,text='<html>Pricing</html>')
    respx_mock.get(OPENAI_MODELS_DOCS_URL).respond(200,text='<html>Featured models</html>')
    respx_mock.get(OPENAI_PRICING_DOCS_URL+'.md').respond(200,text='''
### Standard pricing data
| Model | Input | Cached input | Output |
| --- | --- | --- | --- |
| codex-test-plain | $1 | $0.1 | $2 |
''')
    respx_mock.get(OPENAI_MODELS_DOCS_URL+'.md').respond(200,text='# Models\n')
    respx_mock.get(OPENAI_MODELS_DOCS_URL+'/codex-test-plain.md').respond(200,text='''
# Plain model
Model ID: `codex-test-plain`
- Input modalities: text
- Output modalities: text
## Endpoints
| Endpoint | Route | Support |
| --- | --- | --- |
| Responses | `v1/responses` | Supported |
| Chat Completions | `v1/chat/completions` | Not supported |
''')
    result=await generate_provider_catalog_proposal(
        provider_scope='openai',output_dir=tmp_path,endpoint_scopes=('responses',),
        paired_ready_only=True,
    )
    assert {(r['requested_model'],r['endpoint']) for r in rows(result.routes_proposal_path)} == {('codex-test-plain',RESP)}
    assert {(r['model'],r['endpoint']) for r in rows(result.pricing_proposal_path)} == {('codex-test-plain',RESP)}


@pytest.mark.asyncio
async def test_both_providers_with_all_packages_keep_packages_openrouter_only(tmp_path,respx_mock):
    mock_sources(respx_mock,'openai')
    mock_sources(respx_mock,'openrouter')
    result=await generate_provider_catalog_proposal(
        provider_scope='all',output_dir=tmp_path,endpoint_scopes=('chat_completions','responses'),
        paired_ready_only=True,fetch_details_limit=0,all_packages=True,
    )
    assert {r['provider'] for r in rows(result.routes_proposal_path)} == {'openai','openrouter'}
    from slaif_gateway.services.provider_catalog_proposal import OPENROUTER_PACKAGE_ORDER
    for package in OPENROUTER_PACKAGE_ORDER:
        root=tmp_path/'packages'/package
        route_rows=rows(root/'routes-proposal.tsv')
        price_rows=rows(root/'pricing-proposal.tsv')
        assert route_rows and price_rows
        assert {r['provider'] for r in route_rows+price_rows} == {'openrouter'}
        assert {(r['requested_model'],r['endpoint']) for r in route_rows} == {(r['model'],r['endpoint']) for r in price_rows}
