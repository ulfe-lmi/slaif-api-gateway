"""Data-only dialect changes, immutable identities, and core authority boundaries."""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from slaif_gateway.cli.codex import app as codex_cli
from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.codex_0162 import Codex0162ResponsesClientModule
from slaif_gateway.modules.codex_profile_data import (
    CodexProfileDataError,
    list_codex_presets,
    load_codex_profile_file,
    parse_codex_profile_data,
    read_codex_preset,
)
from slaif_gateway.modules.compatibility_rules import CompatibilityRuleError, parse_dialect_rules
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    ResponsesRequestPolicyError,
)

ROOT = Path('app/slaif_gateway/modules/clients/profiles')


def _document():
    return json.loads(read_codex_preset('codex-0.163.0'))


def _module(document=None):
    return Codex0162ResponsesClientModule(parse_codex_profile_data(json.dumps(document or _document())))


def _apply(body, module=None, **gates):
    module = module or _module()
    options = dict(allow_codex_request_envelope=True, allow_codex_client_tools=True,
                   allow_codex_streaming_tool_events=True)
    options.update(gates)
    return ResponsesRequestPolicy(Settings(), client_spec=module.policy_spec).apply(
        module.normalize_responses(body).body, **options
    )


def _body(part=None):
    return {'model':'synthetic', 'max_output_tokens':20, 'input':[{
        'type':'message', 'role':'assistant', 'status':'completed',
        'content':[part or {'type':'output_text','text':'Synthetic answer.','annotations':[]}],
    }]}


def test_shipped_presets_validate_against_schema_and_loader():
    schema = json.loads(Path('app/slaif_gateway/resources/client-compatibility-preset.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    presets = list_codex_presets()
    assert {name for name, _, _ in presets} == {'codex-0.162.1','codex-0.163.0'}
    for _, path, profile in presets:
        validator.validate(json.loads(path.read_text()))
        assert profile.schema_version == 2


def test_annotations_and_status_are_data_not_source_flags():
    body = _body()
    result = _apply(body)
    assert result.effective_body['input'] == body['input']
    assert result.estimated_message_input_tokens > 0
    assert not hasattr(_module().policy_spec, 'allow_completed_assistant_message_status')


def test_new_optional_field_requires_only_a_file_change(tmp_path):
    first = _document()
    path = tmp_path/'operator.json'
    path.write_text(json.dumps(first))
    old = Codex0162ResponsesClientModule(load_codex_profile_file(path))
    body = _body()
    body['input'][0]['review_note'] = 'Synthetic metadata'
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(body, old)
    second = copy.deepcopy(first)
    second['revision'] = '12'
    second['dialect']['extensions']['message.assistant']['review_note'] = {
        'action':'preserve','value':{'kind':'string','minimum':0,'maximum':128}}
    path.write_text(json.dumps(second))
    new = Codex0162ResponsesClientModule(load_codex_profile_file(path))
    assert _apply(body,new).effective_body['input'] == body['input']
    assert new.fixture_sha256 != old.fixture_sha256
    # Existing instances are immutable bootstrap snapshots, never per-request reloads.
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(body,old)


def test_metadata_is_metered_as_model_input():
    body = _body()
    plain = _body({'type':'output_text','text':'Synthetic answer.'})
    assert _apply(body).estimated_input_tokens >= _apply(plain).estimated_input_tokens
    d = _document()
    d['dialect']['extensions']['part.output_text']['note'] = {
        'action':'preserve','value':{'kind':'string','minimum':0,'maximum':1024}}
    body['input'][0]['content'][0]['note'] = 'ž'*300
    assert _apply(body,_module(d)).estimated_input_tokens > _apply(plain).estimated_input_tokens + 100


@pytest.mark.parametrize('field,value',[('annotations',None),('annotations',[{}]),('annotations',{}),
                                      ('logprobs',[{}]),('logprobs',False)])
def test_empty_metadata_allowance_does_not_accept_other_values(field,value):
    body = _body()
    body['input'][0]['content'][0][field] = value
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        _apply(body)
    assert exc.value.param == 'input[0].content[0].'+field


@pytest.mark.parametrize('field',['id','type','content','call_id','encrypted_content','model',
                                'tools','authorization','max_output_tokens','foo_quota','secret'])
@pytest.mark.parametrize('scope',['request','message.assistant','part.output_text','item.function_call'])
def test_presets_cannot_override_core_or_authority_fields(field,scope):
    d = _document()
    d['dialect']['extensions'].setdefault(scope,{})[field] = {
        'action':'preserve','value':{'kind':'null'}}
    with pytest.raises(CodexProfileDataError):
        _module(d)


@pytest.mark.parametrize('gate',['allow_codex_request_envelope','allow_codex_client_tools',
                               'allow_codex_streaming_tool_events'])
def test_preset_rules_do_not_bypass_capability_gates(gate):
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(_body(),**{gate:False})


def test_ordinary_responses_remains_strict():
    with pytest.raises(ResponsesRequestPolicyError):
        ResponsesRequestPolicy(Settings()).apply(_body())


def test_only_empty_values_may_be_dropped():
    d = _document()
    rule = d['dialect']['extensions']['part.output_text']['annotations']
    rule['action'] = 'drop'
    accepted = _apply(_body(),_module(d)).effective_body['input'][0]['content'][0]
    assert 'annotations' not in accepted
    d['dialect']['extensions']['message.assistant']['status']['action'] = 'drop'
    with pytest.raises(CodexProfileDataError):
        _module(d)


def test_request_optional_fields_are_gated_and_metered():
    d = _document()
    d['dialect']['extensions']['request'] = {'client_note':{
        'action':'preserve','value':{'kind':'string','minimum':0,'maximum':512}}}
    module = _module(d)
    body = _body()
    body['client_note'] = 'x'*400
    result = _apply(body,module)
    assert result.effective_body['client_note'] == 'x'*400
    assert result.estimated_input_tokens > _apply(_body()).estimated_input_tokens + 90
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(body,module,allow_codex_client_tools=False)


def test_droppable_request_metadata_is_not_removed_before_core_gates():
    d = _document()
    d['dialect']['extensions']['request'] = {'client_note':{'action':'drop','value':{'kind':'null'}}}
    module = _module(d)
    body = _body()
    body['client_note'] = None
    assert 'client_note' in module.normalize_responses(body).body
    assert 'client_note' not in _apply(body,module).effective_body
    with pytest.raises(ResponsesRequestPolicyError):
        _apply(body,module,allow_codex_request_envelope=False)


def test_custom_tools_are_declared_in_data():
    d = _document()
    d['dialect']['custom_tools'] = [{'namespace':'functions','name':'synthetic_patch','type':'custom'}]
    spec = _module(d).policy_spec
    assert spec.custom_client_tools == frozenset({('functions','synthetic_patch','custom')})
    assert ('functions','apply_patch','custom') not in spec.custom_client_tools


def test_features_come_from_data_independently_of_revision():
    d = _document()
    d['revision'] = '900'
    d['dialect']['features'] = dict.fromkeys(d['dialect']['features'],False)
    spec = _module(d).policy_spec
    assert not spec.allow_schema_property_names
    assert not spec.allow_sparse_visible_reasoning
    assert not spec.allow_empty_visible_reasoning
    assert not spec.allow_sparse_function_events


@pytest.mark.parametrize('value',[{},None,True,[],{'eval':'danger'}, {'kind':'regex','pattern':'.*'},
                                {'kind':'array','max_items':65,'items':{'kind':'null'}}])
def test_malformed_or_executable_rule_documents_fail_safely(value):
    d = _document()
    d['dialect']['extensions']['message.assistant']['note'] = {'action':'preserve','value':value}
    with pytest.raises(CodexProfileDataError) as exc:
        _module(d)
    assert 'danger' not in str(exc.value)


def test_cli_exports_a_complete_validated_preset_without_overwrite(tmp_path):
    runner = CliRunner()
    result = runner.invoke(codex_cli,['presets','--json'])
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.output)['presets']) == 2
    target = tmp_path/'operator.json'
    assert runner.invoke(codex_cli,['export-preset','codex-0.163.0','--output',str(target)]).exit_code == 0
    assert load_codex_profile_file(target).cli_version == '0.163.0'
    assert target.stat().st_mode & 0o777 == 0o600
    before = target.read_bytes()
    assert runner.invoke(codex_cli,['export-preset','codex-0.162.1','--output',str(target)]).exit_code != 0
    assert target.read_bytes() == before


def test_scalar_types_do_not_confuse_booleans_with_integers():
    d = _document()['dialect']
    d['extensions'] = {'message.assistant':{'counter':{'action':'preserve','value':{'kind':'enum','values':[1]}}}}
    rules = parse_dialect_rules(d)
    with pytest.raises(CompatibilityRuleError):
        rules.split({'counter':True},'message.assistant')


def test_bounded_metadata_objects_arrays_and_finite_numbers_are_data_only():
    d = _document()
    d['dialect']['extensions']['part.output_text']['annotations']['value'] = {
        'kind':'array','max_items':1,'items':{'kind':'object','fields':{
            'label':{'required':True,'value':{'kind':'string','minimum':1,'maximum':32}},
            'score':{'required':False,'value':{'kind':'number','minimum':-1.0,'maximum':1.0}},
        }}}
    module = _module(d)
    body = _body()
    body['input'][0]['content'][0]['annotations'] = [{'label':'synthetic','score':0.5}]
    before = copy.deepcopy(body)
    assert _apply(body,module).effective_body['input'] == body['input']
    assert body == before
    for invalid in ([{'label':'synthetic','score':2.0}], [{'label':'synthetic','score':True}],
                    [{'label':'synthetic','extra':0}], [{'score':0.5}], [{}], [{},{}]):
        body['input'][0]['content'][0]['annotations'] = invalid
        with pytest.raises(ResponsesRequestPolicyError):
            _apply(body,module)


@pytest.mark.parametrize('field',['api_key','apikey','bearer','session_id','tenant_id',
                                'request_id','replay_hint','quota_override'])
def test_preset_metadata_cannot_become_credentials_or_identity(field):
    d = _document()
    d['dialect']['extensions']['request'] = {field:{'action':'preserve','value':{'kind':'null'}}}
    with pytest.raises(CodexProfileDataError):
        _module(d)


def test_rule_depth_and_total_node_budgets_are_fixed_by_the_engine():
    d = _document()
    rule = {'kind':'null'}
    for _ in range(8):
        rule = {'kind':'array','max_items':1,'items':rule}
    d['dialect']['extensions']['message.assistant']['note'] = {'action':'preserve','value':rule}
    with pytest.raises(CodexProfileDataError):
        _module(d)


def test_preserved_metadata_has_a_cumulative_request_budget():
    d = _document()
    d['dialect']['extensions']['message.assistant']['note'] = {
        'action':'preserve','value':{'kind':'string','minimum':0,'maximum':65536}}
    body = _body()
    body['input'][0]['note'] = 'x'*40000
    body['input'] *= 2
    with pytest.raises(ResponsesRequestPolicyError) as exc:
        _apply(body,_module(d))
    assert exc.value.error_code == 'responses_dialect_metadata_too_large'


def test_native_backend_codec_preserves_validated_metadata_without_new_authority():
    from slaif_gateway.modules.servers.local_coding_vllm.codec import VLLMToolCodec
    body = _apply(_body()).effective_body
    assert VLLMToolCodec(body).body['input'] == body['input']


@pytest.mark.parametrize('stage',[0,1,2])
def test_fake_conformance_producer_passes_the_actual_strict_sse_consumer(stage):
    from slaif_gateway.providers.streaming import (
        ResponsesStreamEventValidator, ResponsesStreamValidationProfile,
    )
    from tests.preset_conformance import synthetic_stream
    spec = _module().policy_spec
    validator = ResponsesStreamEventValidator(ResponsesStreamValidationProfile(
        codex_streaming_tool_events=True,
        declared_client_tools=frozenset({('functions','exec_command','function')}),
        custom_client_tools=spec.custom_client_tools,
        allow_sparse_function_events=spec.allow_sparse_function_events,
        allow_sparse_visible_reasoning=spec.allow_sparse_visible_reasoning,
    ))
    for event in synthetic_stream(stage):
        assert validator.validate(event), (stage,event['type'],event['sequence_number'])
