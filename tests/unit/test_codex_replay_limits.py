"""External replay budgets preserve content, metering and independent bounds."""

import copy
import json

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.codex_profile_data import (
    CodexProfileDataError, REPLAY_LIMIT_HARD_CAPS, parse_codex_profile_data,
)
from slaif_gateway.services.responses_request_policy import ResponsesRequestPolicy, ResponsesRequestPolicyError
from tests.unit.test_compatibility_presets import _document, _module


def _history(text):
    return {'model':'synthetic', 'max_output_tokens':20, 'input':[
        {'type':'message','role':'user','content':'Synthetic history.'} for _ in range(40)
    ]+[{'type':'reasoning','id':None,'summary':[],
        'content':[{'type':'reasoning_text','text':text}],'encrypted_content':None}]}


def _apply(text, document=None, settings=None):
    module = _module(document)
    body = _history(text)
    return ResponsesRequestPolicy(settings or Settings(),client_spec=module.policy_spec).apply(
        module.normalize_responses(body).body,
        allow_codex_request_envelope=True,allow_codex_client_tools=True,
        allow_codex_streaming_tool_events=True,
    )


def test_reproduces_exact_old_input40_failure_without_replay_settings():
    old = _document()
    old.pop('replay_limits')
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        _apply('x'*8193,old)
    assert exc.value.error_code == 'responses_codex_reasoning_visible_too_large'
    assert exc.value.param == 'input[40].content[0].text'


@pytest.mark.parametrize('size',[8193,65536,262144])
def test_long_reasoning_replay_is_preserved_and_metered(size):
    text = 'x'*size
    result = _apply(text)
    assert result.effective_body['input'][40]['content'][0]['text'] == text
    assert result.estimated_input_tokens > size//4


@pytest.mark.parametrize('text',['x'*262145,'ž'*131073])
def test_reasoning_part_budget_is_measured_in_utf8_bytes(text):
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        _apply(text)
    assert exc.value.error_code == 'responses_codex_reasoning_visible_too_large'


def test_operator_can_change_reasoning_limit_by_data_without_source_change():
    first = _document()
    second = copy.deepcopy(first)
    second['revision'] = str(int(first['revision'])+1)
    second['replay_limits']['max_reasoning_visible_part_bytes'] = 10000
    assert _module(first).fixture_sha256 != _module(second).fixture_sha256
    assert _apply('x'*12000,first).estimated_input_tokens > 3000
    with pytest.raises(ResponsesRequestPolicyError):
        _apply('x'*12000,second)


@pytest.mark.parametrize('name',sorted(REPLAY_LIMIT_HARD_CAPS))
@pytest.mark.parametrize('value',[True,0,-1,1.5,'100'])
def test_invalid_replay_budget_types_fail_closed(name,value):
    d = _document()
    d['replay_limits'][name] = value
    with pytest.raises(CodexProfileDataError):
        parse_codex_profile_data(json.dumps(d))


@pytest.mark.parametrize('name',sorted(REPLAY_LIMIT_HARD_CAPS))
def test_replay_budget_cannot_raise_engine_ceiling(name):
    d = _document()
    d['replay_limits'][name] = REPLAY_LIMIT_HARD_CAPS[name]+1
    with pytest.raises(CodexProfileDataError):
        _module(d)


def test_partial_unknown_and_inconsistent_budget_documents_fail_closed():
    for mutation in ('missing','unknown','inconsistent'):
        d = _document()
        if mutation == 'missing':
            d['replay_limits'].pop('max_compaction_item_bytes')
        elif mutation == 'unknown':
            d['replay_limits']['quota_override'] = 1000
        else:
            d['replay_limits']['max_reasoning_visible_bytes'] = 100
        with pytest.raises(CodexProfileDataError):
            _module(d)


def test_larger_replay_budget_keeps_global_input_byte_limit():
    with pytest.raises(ResponsesRequestPolicyError):
        _apply('x'*12000,settings=Settings(RESPONSES_MAX_TOTAL_INPUT_TEXT_BYTES=10000))
