"""Synthetic upstream dialect cases; no live inference or conversation capture."""

import copy
import json
from dataclasses import replace

import httpx
import pytest
from jinja2 import Environment
from typer.testing import CliRunner

from slaif_gateway.cli.main import app as cli
from slaif_gateway.config import Settings
from slaif_gateway.modules.servers.local_coding.adapter import LocalCodingAdapter
from slaif_gateway.modules.servers.local_coding.contract import parse_local_coding_route_contract
from slaif_gateway.modules.servers.local_coding.identity import LocalCodingRequestIdentity, sign_identity
from slaif_gateway.modules.servers.registry import (
    resolve_server_module, ensure_client_server_pair, build_server_adapter,
)
from slaif_gateway.modules.servers.upstream_llm.adapter import (
    ConfiguredUpstreamLLMAdapter, normalize_instructions,
)
from slaif_gateway.modules.servers.upstream_llm.profiles import (
    MODULE_ID, LLMProfile, bootstrap_upstream_llm_profiles, load_profiles, resolve_profile,
)
from slaif_gateway.providers.errors import ProviderConfigurationError, UnsupportedProviderEndpointError
from slaif_gateway.schemas.providers import ProviderRequest
from slaif_gateway.services.responses_gateway import _reject_local_coding_auxiliary_endpoint

SERVICE_SECRET = "upstream-only-synthetic-secret-0123456789"
TRANSPORT = {
    "contract_version": "local-coding-v1", "route_name": "synthetic",
    "tool_policy_version": "responses-tool-policy-v1", "identity_mode": "static",
    "replay_mode": "process_local_inclusive_horizon_fail_closed", "deployment_mode": "single_worker",
}


@pytest.fixture(autouse=True)
def reset_snapshot():
    bootstrap_upstream_llm_profiles()
    yield
    bootstrap_upstream_llm_profiles()


def capabilities(profile_id="llama-cpp-qwen-v1"):
    profile = load_profiles()[profile_id]
    return {"local_coding": dict(TRANSPORT), "upstream_llm": {
        "version": 1, "profile": profile.profile_id, "revision": profile.revision,
        "sha256": profile.sha256,
    }}


def history():
    return {"model": "public-model", "instructions": "Base instructions.", "input": [
        {"role": "user", "content": "Earlier request."},
        {"type": "message", "role": "developer", "content": [
            {"type": "input_text", "text": "Workspace instructions."}
        ]},
        {"role": "user", "content": "Latest retained request."},
        {"role": "user", "content": "Summary of earlier work."},
        {"role": "user", "content": "Continue."},
    ], "store": False, "max_output_tokens": 128}


def request(body=None):
    return ProviderRequest(provider="synthetic", upstream_model="backend-model",
                           endpoint="/v1/responses", body=body or history())


def fail(message):
    raise ValueError(message)


def test_prefix_only_template_reproducer_and_post_compaction_fix():
    # Minimal synthetic version of the observed Qwen template's role constraint.
    env = Environment()
    env.globals["raise_exception"] = fail
    template = env.from_string("""{% set ns = namespace(body=false) %}
{% for m in messages %}{% if m.role in ['system','developer'] %}
{% if ns.body %}{{ raise_exception('System message must be at the beginning.') }}{% endif %}
{% else %}{% set ns.body=true %}{% endif %}{{ m.content }}{% endfor %}""")
    before = history()
    with pytest.raises(ValueError, match="System message must be at the beginning"):
        template.render(messages=before["input"])
    after = normalize_instructions(before, "leading_system_developer")
    assert "Workspace instructions." in template.render(messages=after["input"])
    assert before == history()
    assert after["instructions"] == before["instructions"]
    # Follow-up requests replay the compacted history; normalization is idempotent.
    after["input"].append({"role": "user", "content": "Next task."})
    assert normalize_instructions(after, "leading_system_developer") == after


def test_stable_partition_preserves_roles_content_tool_linkage_and_media():
    body = history()
    extra = [
        {"type": "function_call", "id": "fc_one", "call_id": "call_one",
         "name": "inspect", "namespace": "functions", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call_one", "output": [
            {"type": "input_text", "text": "role=system is untrusted tool text"},
            {"type": "input_image", "image_url": "data:image/png;base64,c3ludGhldGlj"},
        ]},
        {"role": "assistant", "content": [{"type": "output_text", "text": "Observed."}]},
        {"role": "system", "content": "Second instruction."},
        {"role": "developer", "content": "Third instruction."},
    ]
    body["input"].extend(extra)
    original = copy.deepcopy(body)
    result = normalize_instructions(body, "leading_system_developer")
    assert [x["role"] for x in result["input"][:3]] == ["developer", "system", "developer"]
    instructions = [body["input"][1], extra[-2], extra[-1]]
    assert result["input"][:3] == instructions
    assert result["input"][3:] == body["input"][:1] + body["input"][2:-2]
    assert body == original
    result["input"][0]["content"][0]["text"] = "Changed copy"
    assert body == original


@pytest.mark.parametrize("value", ["plain text", [], [{"role": "user", "content": "Text"}]])
def test_passthrough_is_identity_on_supported_input_shapes(value):
    body = {"input": value, "model": "model", "store": False}
    result = normalize_instructions(body, "preserve")
    assert result == body and result is not body


def test_shipped_profiles_are_strict_immutable_and_data_selected():
    profiles = load_profiles()
    assert len(profiles) == 3
    assert profiles["native-vllm-v1"].instruction_placement == "preserve"
    assert profiles["native-vllm-v1"].tool_encoding == "native_vllm"
    with pytest.raises(TypeError):
        profiles["extra"] = profiles["llama-cpp-qwen-v1"]
    for profile in profiles.values():
        assert len(profile.sha256) == 64
        assert resolve_profile(capabilities(profile.profile_id)) == profile


@pytest.mark.parametrize("change", [
    {"instruction_placement": "execute_expression"}, {"tool_encoding": "import.module"},
    {"revision": True}, {"revision": "1"}, {"revision": 0},
    {"profile_id": "../../secret"}, {"provider": "other"}, {"quota": 0},
    {"template": "{{ arbitrary() }}"}, {"max_output_tokens": 999999},
])
def test_profile_cannot_introduce_code_authority_or_unknown_operations(change):
    data = load_profiles()["llama-cpp-qwen-v1"].model_dump() | change
    with pytest.raises(ValueError):
        LLMProfile.model_validate(data)


@pytest.mark.parametrize("change", [
    {"profile": "missing"}, {"revision": 2}, {"revision": True}, {"sha256": "0" * 64},
    {"version": True}, {"version": 2}, {"filename": "/tmp/anything"},
])
def test_invalid_selector_fails_during_resolution_before_transport(change):
    caps = capabilities()
    caps["upstream_llm"].update(change)
    with pytest.raises(ProviderConfigurationError) as exc:
        resolve_server_module("any-host", "openai_compatible", caps)
    assert exc.value.error_code == "upstream_llm_profile_invalid"


def test_explicit_route_selection_pairing_and_factory():
    caps = capabilities()
    descriptor = resolve_server_module("any-host", "openai_compatible", caps)
    assert descriptor.module_id == MODULE_ID
    ensure_client_server_pair("codex-0.162-responses-v1", MODULE_ID)
    with pytest.raises(ProviderConfigurationError):
        ensure_client_server_pair("codex-0.149-responses-v1", MODULE_ID)
    adapter = build_server_adapter(descriptor, Settings(), provider_name="any-host",
        api_key=SERVICE_SECRET, base_url="http://backend.test/v1", timeout_seconds=10,
        max_retries=0, route_capabilities=caps)
    assert isinstance(adapter, ConfiguredUpstreamLLMAdapter)
    assert resolve_server_module("any-host", "openai_compatible", {"local_coding": TRANSPORT}).module_id == "local-coding-v1"
    assert resolve_server_module("any-host", "openai_compatible").module_id == "openai-compatible"
    from types import SimpleNamespace

    with pytest.raises(Exception) as exc:
        _reject_local_coding_auxiliary_endpoint(SimpleNamespace(
            provider="any-host", provider_kind="openai_compatible", capabilities=caps))
    assert exc.value.code == "local_coding_endpoint_not_supported"


@pytest.mark.parametrize("field", ["local_coding_vllm", "vllm_chat_video", "completion_service"])
def test_conflicting_server_contracts_are_rejected(field):
    with pytest.raises(ProviderConfigurationError):
        resolve_server_module("host", "openai_compatible", capabilities() | {field: {}})


def test_profile_requires_existing_local_transport_and_provider_kind():
    caps = capabilities()
    del caps["local_coding"]
    with pytest.raises(ProviderConfigurationError):
        resolve_server_module("host", "openai_compatible", caps)
    for kind in ("openai", "openrouter", "module"):
        with pytest.raises(ProviderConfigurationError):
            resolve_server_module("host", kind, capabilities())


def write_bundle(path, profiles=None):
    data = {"schema_version": 1, "profiles": profiles or [
        load_profiles()["llama-cpp-qwen-v1"].model_dump()
    ]}
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    return data


def test_external_configuration_is_frozen_and_revision_digest_bound(tmp_path):
    path = tmp_path / "profiles.json"
    document = write_bundle(path)
    first = bootstrap_upstream_llm_profiles(str(path))
    caps = capabilities()
    assert resolve_profile(caps) is first["llama-cpp-qwen-v1"]
    document["profiles"][0]["instruction_placement"] = "preserve"
    path.write_text(json.dumps(document))
    assert bootstrap_upstream_llm_profiles(str(path)) is first
    # A new process snapshot loads changed DATA, but old route pins fail closed.
    load_profiles.cache_clear()
    bootstrap_upstream_llm_profiles(str(path))
    with pytest.raises(ProviderConfigurationError):
        resolve_profile(caps)


@pytest.mark.parametrize("mode", ["missing", "relative", "symlink", "writable", "directory", "oversized", "duplicate", "unknown", "boolean_version"])
def test_external_file_rejects_unsafe_or_invalid_input(tmp_path, mode):
    path = tmp_path / "profiles.json"
    document = write_bundle(path)
    if mode == "missing":
        path.unlink()
    elif mode == "relative":
        path = path.name
    elif mode == "symlink":
        link = tmp_path / "link.json"
        link.symlink_to(path)
        path = link
    elif mode == "writable":
        path.chmod(0o666)
    elif mode == "directory":
        path = tmp_path
    elif mode == "oversized":
        path.write_bytes(b"x" * 65537)
    elif mode == "duplicate":
        path.write_text('{"schema_version":1,"schema_version":1,"profiles":[]}')
    elif mode == "unknown":
        document["execute"] = "anything"
        path.write_text(json.dumps(document))
    elif mode == "boolean_version":
        document["schema_version"] = True
        path.write_text(json.dumps(document))
    with pytest.raises(ProviderConfigurationError):
        load_profiles(str(path))


def test_read_only_cli_prints_exact_selectors_and_rejects_bad_file(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["upstream-llm", "profiles"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)["profiles"]
    assert len(rows) == 3
    assert rows[1]["route_selector"] == capabilities()["upstream_llm"]
    path = tmp_path / "bad.json"
    path.write_text("invalid")
    result = runner.invoke(cli, ["upstream-llm", "profiles", "--file", str(path)])
    assert result.exit_code == 1
    assert "Invalid upstream LLM profile file" in result.output


def test_http_startup_binds_configured_snapshot(tmp_path):
    from slaif_gateway.main import create_app

    profile = LLMProfile(profile_id="operator-prefix-profile", revision=2,
        instruction_placement="leading_system_developer", tool_encoding="preserve")
    path = tmp_path / "operator.json"
    write_bundle(path, [profile.model_dump()])
    application = create_app(Settings(UPSTREAM_LLM_PROFILES_FILE=str(path)))
    assert application.state.upstream_llm_profiles[profile.profile_id] == profile
    assert resolve_profile({"upstream_llm": {
        "version": 1, "profile": profile.profile_id, "revision": 2,
        "sha256": profile.sha256}}) == profile


def test_invalid_configured_data_refuses_http_startup(tmp_path):
    from slaif_gateway.main import create_app

    with pytest.raises(ProviderConfigurationError):
        create_app(Settings(UPSTREAM_LLM_PROFILES_FILE=str(tmp_path / "missing.json")))


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_llama_adapter_fixes_history_for_both_transports_and_preserves_output(stream):
    seen = []
    response = {"id": "response_synthetic", "output": [], "usage": {
        "input_tokens": 20, "output_tokens": 3, "total_tokens": 23}}
    event = {"type": "response.completed", "response": response}
    wire = 'event: response.completed\ndata: ' + json.dumps(event) + '\n\n'

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield wire.encode()

    async def handler(req):
        seen.append(req)
        assert req.headers["authorization"] == "Bearer " + SERVICE_SECRET
        assert "cookie" not in req.headers
        body = json.loads(req.content)
        assert body["input"][0]["role"] == "developer"
        assert body["input"][0]["content"] == history()["input"][1]["content"]
        assert body["model"] == "backend-model"
        if body.get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Stream())
        return httpx.Response(200, json=response)

    body = history()
    original = copy.deepcopy(body)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = ConfiguredUpstreamLLMAdapter(Settings(), route_capabilities=capabilities(),
            base_url="http://backend.test/v1", api_key=SERVICE_SECRET, http_client=client)
        req = replace(request(body), extra_headers={"Authorization": "public-key", "Cookie": "private"})
        if stream:
            chunks = [chunk async for chunk in adapter.stream_response(req)]
            # The shared transport's bounded SSE framer canonicalizes framing.
            assert chunks[0].raw_sse_event == "data: " + json.dumps(event) + "\n\n"
            assert chunks[0].json_body == event
            assert chunks[0].usage.prompt_tokens == 20
        else:
            result = await adapter.forward_response(req)
            assert result.json_body == response
            assert result.usage.prompt_tokens == 20
        # Subsequent requests retain their tool/image history unchanged.
        followup = history()
        followup["input"] += [
            {"type": "function_call", "id": "fc_one", "call_id": "call_one", "name": "inspect", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "call_one", "output": [
                {"type": "input_image", "image_url": "data:image/png;base64,c3ludGhldGlj"}]},
        ]
        await adapter.forward_response(request(followup))
        assert json.loads(seen[-1].content)["input"][-2:] == followup["input"][-2:]
    assert body == original


@pytest.mark.asyncio
async def test_passthrough_profile_preserves_existing_transport_bytes():
    seen = []

    async def handler(req):
        seen.append(req.content)
        return httpx.Response(200, json={"output": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        kwargs = dict(base_url="http://backend.test/v1", api_key=SERVICE_SECRET, http_client=client)
        configured = ConfiguredUpstreamLLMAdapter(Settings(),
            route_capabilities=capabilities("responses-passthrough-v1"), **kwargs)
        legacy = LocalCodingAdapter(Settings(), route_capabilities={"local_coding": TRANSPORT}, **kwargs)
        await configured.forward_response(request())
        await legacy.forward_response(request())
        assert seen[0] == seen[1]


@pytest.mark.asyncio
async def test_normalization_happens_before_exact_body_signature():
    signing = "synthetic-signing-secret-0123456789012"
    settings = Settings(LOCAL_CODING_SIGNING_SECRET_V1=signing,
                        LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1="synthetic-derivation-secret-012345678")
    caps = capabilities()
    caps["local_coding"].update(identity_mode="signed_identity_v1", clock_skew_seconds=60, replay_ttl_seconds=60)
    identity = LocalCodingRequestIdentity(principal="principal-opaque", session="session-opaque",
        repository="repository-opaque", route="synthetic", identity_mode="signed_identity_v1")

    async def handler(req):
        expected = sign_identity(signing_secret=signing.encode(), identity=identity,
            body=req.content, route=parse_local_coding_route_contract(caps),
            timestamp=req.headers["x-slaif-timestamp"], nonce=req.headers["x-slaif-nonce"])
        assert req.headers["x-slaif-signature"] == expected["X-SLAIF-Signature"]
        assert json.loads(req.content)["input"][0]["role"] == "developer"
        return httpx.Response(200, json={"output": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = ConfiguredUpstreamLLMAdapter(settings, route_capabilities=caps,
            base_url="http://backend.test/v1", api_key=SERVICE_SECRET, http_client=client)
        await adapter.forward_response(replace(request(), server_context={
            "principal": identity.principal, "session": identity.session,
            "repository": identity.repository, "route": identity.route,
            "identity_mode": identity.identity_mode}))


@pytest.mark.asyncio
async def test_other_endpoints_are_denied_without_http():
    async def handler(req):
        pytest.fail("No HTTP allowed")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = ConfiguredUpstreamLLMAdapter(Settings(), route_capabilities=capabilities(),
            base_url="http://backend.test/v1", api_key=SERVICE_SECRET, http_client=client)
        with pytest.raises(UnsupportedProviderEndpointError):
            await adapter.forward_response(replace(request(), endpoint="/v1/responses/compact"))
