"""Image tool results reuse image validation, metering and capability detection."""

import copy

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0162 import codex_0162_lower_initial_additional_tools
from slaif_gateway.modules.servers.local_coding_vllm.codec import VLLMToolCodec
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy, ResponsesRequestPolicyError, responses_image_input_requested,
)
from tests.unit.test_compatibility_presets import _document, _module

IMAGE = {'type':'input_image','detail':'original',
         'image_url':'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aNTkAAAAASUVORK5CYII='}


def _body(part):
    return {'model':'synthetic','max_output_tokens':20,'input':[
        {'type':'additional_tools','role':'developer','tools':[{'type':'namespace','name':'functions','tools':[
            {'type':'function','name':'view_image','parameters':{'type':'object','properties':{}}}]}]},
        {'type':'function_call','id':'fc_synthetic','call_id':'call_synthetic','namespace':'functions',
         'name':'view_image','arguments':'{}','status':'completed'},
        {'type':'function_call_output','call_id':'call_synthetic','output':[part]},
    ]}


def _apply(part=IMAGE,document=None,settings=None,**gates):
    module = _module(document)
    options=dict(allow_codex_request_envelope=True,allow_codex_client_tools=True,
                 allow_codex_streaming_tool_events=True)
    options.update(gates)
    return ResponsesRequestPolicy(settings or Settings(),client_spec=module.policy_spec).apply(
        module.normalize_responses(_body(part)).body,**options)


def test_view_image_result_preserved_metered_and_detected_for_image_permissions():
    result=_apply()
    assert result.effective_body['input'][-1]['output']==[IMAGE]
    assert responses_image_input_requested(result.effective_body)
    assert result.estimated_non_message_input_tokens > 0
    assert VLLMToolCodec(codex_0162_lower_initial_additional_tools(result.effective_body)).body['input'][-1]['output']==[IMAGE]


def test_absent_preset_selector_keeps_frozen_text_only_contract():
    document=_document()
    document['dialect']['features'].pop('tool_output_images')
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        _apply(document=document)
    assert exc.value.error_code=='responses_codex_tool_roundtrip_invalid'


@pytest.mark.parametrize('gate',['allow_codex_request_envelope','allow_codex_client_tools',
                               'allow_codex_streaming_tool_events'])
def test_tool_result_images_keep_independent_codex_gates(gate):
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(**{gate:False})


@pytest.mark.parametrize('part',[{'type':'input_file','file_id':'file_synthetic'},
                               dict(IMAGE,image_url='file:///etc/passwd'),
                               dict(IMAGE,image_url='data:image/png;base64,not-base64!'),
                               dict(IMAGE,credential='forbidden')])
def test_tool_result_does_not_bypass_existing_image_validation(part):
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(part)


def test_tool_images_keep_decoded_image_budget():
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(settings=Settings(RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES=1))


def test_native_vllm_receives_explicit_default_image_detail():
    image=copy.deepcopy(IMAGE)
    image.pop('detail')
    wire=VLLMToolCodec(codex_0162_lower_initial_additional_tools(_apply(image).effective_body)).body
    assert wire['input'][-1]['output'][0]['detail']=='auto'
