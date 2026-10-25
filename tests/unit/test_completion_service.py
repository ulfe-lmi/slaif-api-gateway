"""Shared completion engine qualification with synthetic upstreams only."""

from dataclasses import replace
import base64
import json
from types import SimpleNamespace

import httpx
import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.servers.completion_service.adapter import CompletionServiceAdapter
from slaif_gateway.modules.servers.completion_service.profiles import (
    load_profile,
    profile_id_from_capabilities,
)
from slaif_gateway.modules.servers.facial_scoring import FacialScoringAdapter
from slaif_gateway.providers.errors import (
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseParseError,
)
from slaif_gateway.providers.factory import get_provider_adapter
from slaif_gateway.schemas.providers import ProviderRequest


def request(**overrides):
    body = {
        "model": "zap-it-1",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                    {"type": "text", "text": "pipeline: sam2\n"},
                ],
            }
        ],
    }
    body.update(overrides)
    return ProviderRequest(
        provider="zap_it",
        upstream_model="zap-it-1",
        endpoint="chat.completions",
        body=body,
        request_id="synthetic-request",
    )


PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII="
)


def response(projection=None):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            projection or {"schema_version": "zap-it.public.v1", "objects": []}
                        ),
                    }
                ],
            },
            {"type": "image_generation_call", "status": "completed", "result": PNG_BASE64},
        ],
    }


def adapter(client, profile=None):
    return CompletionServiceAdapter(
        provider_name="zap_it",
        base_url="https://zap.test",
        api_key="upstream-only-secret",
        timeout_seconds=7,
        max_retries=0,
        http_client=client,
        profile=profile or load_profile("zap-it-v1"),
    )


def test_both_profiles_use_the_same_class_and_legacy_identity(monkeypatch):
    assert FacialScoringAdapter is CompletionServiceAdapter
    for provider, name, secret, caps in (
        ("facial_scoring", "facial-scoring-v1", "FACIAL_SCORING_API_KEY", {}),
        (
            "zap_it",
            "zap-it-v1",
            "ZAP_IT_API_KEY",
            {"completion_service": {"version": 1, "profile": "zap-it-v1"}},
        ),
    ):
        monkeypatch.setenv(secret, "synthetic-upstream-secret")
        a = get_provider_adapter(
            SimpleNamespace(
                provider=provider,
                provider_kind="module",
                capabilities=caps,
                provider_base_url="https://service.test",
                provider_api_key_env_var=secret,
                provider_timeout_seconds=30,
                provider_max_retries=0,
            ),
            Settings(),
        )
        assert type(a) is CompletionServiceAdapter
        assert a.profile.profile_id == name


@pytest.mark.asyncio
async def test_zap_translates_to_public_facade_with_isolated_auth_and_zero_usage():
    seen = []

    async def handler(req):
        seen.append(req)
        return httpx.Response(200, json=response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await adapter(client).forward_chat_completion(request())
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "https://zap.test/v1/responses"
    assert req.headers["authorization"] == "Bearer upstream-only-secret"
    assert "x-api-key" not in req.headers and "cookie" not in req.headers
    payload = json.loads(req.content)
    assert set(payload) == {"model", "input", "tools"}
    assert payload["tools"] == [{"type": "image_generation"}]
    parts = payload["input"][0]["content"]
    assert parts[0] == {
        "type": "input_image",
        "image_url": "data:image/png;base64,AAAA",
        "detail": "auto",
    }
    assert base64.b64decode(parts[1]["file_data"].split(",")[1]) == b"pipeline: sam2\n"
    assert parts[1]["filename"] == "task.yaml"
    assert (
        json.loads(result.json_body["choices"][0]["message"]["content"])["schema_version"]
        == "zap-it.public.v1"
    )
    assert result.usage.total_tokens == 0
    assert (
        result.json_body["choices"][0]["message"]["images"][0]["image_url"]["url"]
        == "data:image/png;base64," + PNG_BASE64
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "missing_yaml",
        "duplicate_yaml",
        "large_yaml",
        "multiple_messages",
        "gif",
        "remote",
        "tools",
        "stream",
        "wrong_model",
    ],
)
async def test_invalid_zap_request_never_reaches_upstream(change):
    calls = []

    async def handler(req):
        calls.append(req)
        return httpx.Response(200, json=response())

    req = request()
    body = req.body
    parts = body["messages"][0]["content"]
    if change == "missing_yaml":
        parts.pop()
    elif change == "duplicate_yaml":
        parts.append({"type": "text", "text": "other: true"})
    elif change == "large_yaml":
        parts[1]["text"] = "x" * 262145
    elif change == "multiple_messages":
        body["messages"] *= 2
    elif change == "gif":
        parts[0]["image_url"]["url"] = "data:image/gif;base64,AAAA"
    elif change == "remote":
        parts[0]["image_url"]["url"] = "https://private.test/image.png"
    elif change == "tools":
        body["tools"] = [{"type": "image_generation"}]
    elif change == "stream":
        body["stream"] = True
    elif change == "wrong_model":
        body["model"] = "other"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderRequestError) as exc:
            await adapter(client).forward_chat_completion(req)
    assert exc.value.status_code == 400
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"status": "in_progress", "output": []},
        response({"schema_version": "private.v1"}),
        {"status": "completed", "output": [{"type": "image_generation_call", "result": "private"}]},
        {"status": "completed", "output": [None]},
    ],
)
async def test_private_or_malformed_output_is_not_forwarded(payload):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as c:
        with pytest.raises(ProviderResponseParseError):
            await adapter(c).forward_chat_completion(request())


@pytest.mark.asyncio
async def test_oversized_success_and_error_bodies_are_bounded():
    profile = load_profile("zap-it-v1").model_copy(update={"max_response_bytes": 64})
    for status in (200, 500):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(status, content=b"x" * 65))
        ) as c:
            with pytest.raises(ProviderResponseParseError):
                await adapter(c, profile).forward_chat_completion(request())


@pytest.mark.asyncio
async def test_response_stream_stops_and_closes_at_limit():
    class Chunks(httpx.AsyncByteStream):
        count = 0
        closed = False

        async def __aiter__(self):
            for _ in range(10):
                self.count += 1
                yield b"x" * 32

        async def aclose(self):
            self.closed = True

    stream = Chunks()
    profile = load_profile("zap-it-v1").model_copy(update={"max_response_bytes": 64})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))
    ) as client:
        with pytest.raises(ProviderResponseParseError):
            await adapter(client, profile).forward_chat_completion(request())
    assert stream.count == 3
    assert stream.closed


@pytest.mark.asyncio
async def test_redirect_never_sends_backend_credential_to_another_origin():
    calls = []

    async def handler(req):
        calls.append(req)
        return httpx.Response(307, headers={"location": "https://untrusted.test/v1/responses"})

    from slaif_gateway.providers.errors import ProviderHTTPError

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as c:
        with pytest.raises(ProviderHTTPError):
            await adapter(c).forward_chat_completion(request())
    assert len(calls) == 1
    assert calls[0].url.host == "zap.test"


@pytest.mark.parametrize(
    "value",
    [
        {"profile": "../secret", "version": 1},
        {"profile": "zap-it-v1", "version": True},
        {"profile": "zap-it-v1", "version": 1, "url": "https://other.test"},
    ],
)
def test_route_metadata_cannot_select_paths_or_code(value):
    with pytest.raises(ProviderConfigurationError):
        profile_id_from_capabilities({"completion_service": value})


def test_external_profiles_reject_code_fields_and_writable_or_symlink_files(tmp_path):
    profile = load_profile("zap-it-v1").model_dump()
    path = tmp_path / "zap-it-v1.json"
    path.write_text(json.dumps({**profile, "python_class": "os.system"}))
    path.chmod(0o600)
    with pytest.raises(ProviderConfigurationError):
        load_profile("zap-it-v1", str(tmp_path))

    path.write_text(json.dumps(profile))
    path.chmod(0o666)
    with pytest.raises(ProviderConfigurationError):
        load_profile("zap-it-v1", str(tmp_path))
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(ProviderConfigurationError):
        load_profile("zap-it-v1", str(tmp_path))


@pytest.mark.asyncio
async def test_additional_route_uses_external_data_without_an_adapter_class(tmp_path, monkeypatch):
    profile = load_profile("zap-it-v1").model_dump()
    profile.update(
        profile_id="other-vision-v1",
        public_model="vision-alias",
        api_key_env_var="OTHER_VISION_API_KEY",
    )
    path = tmp_path / "other-vision-v1.json"
    path.write_text(json.dumps(profile))
    path.chmod(0o600)
    monkeypatch.setenv("OTHER_VISION_API_KEY", "other-backend-secret")
    a = get_provider_adapter(
        SimpleNamespace(
            provider="other-vision",
            provider_kind="module",
            capabilities={"completion_service": {"version": 1, "profile": "other-vision-v1"}},
            provider_base_url="https://other.test",
            provider_api_key_env_var="OTHER_VISION_API_KEY",
            provider_timeout_seconds=30,
            provider_max_retries=0,
        ),
        Settings(COMPLETION_SERVICE_PROFILE_DIR=str(tmp_path)),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response()))
    ) as client:
        a._http_client = client
        result = await a.forward_chat_completion(request())
    assert type(a) is CompletionServiceAdapter
    assert result.json_body["model"] == "vision-alias"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "media_type,data",
    [
        ("image/png", base64.b64decode(PNG_BASE64)),
        ("image/jpeg", b"\xff\xd8\xffsynthetic-header"),
        ("image/webp", b"RIFF\x08\x00\x00\x00WEBPsynthetic-header"),
    ],
)
async def test_unrelated_service_maps_plain_text_and_image_with_only_profile_data(
    tmp_path,
    monkeypatch,
    media_type,
    data,
):
    profile = {
        "version": 1,
        "profile_id": "renderer-v1",
        "public_model": "renderer",
        "upstream_model": "renderer",
        "upstream_path": "/v1/render",
        "api_key_env_var": "RENDERER_KEY",
        "auth_header": "X-API-Key",
        "auth_prefix": "",
        "request_mapping": "multipart_image",
        "response_mapping": "json_fields",
        "image_media_types": ["image/png"],
        "max_image_data_url_bytes": 1048576,
        "text_pointer": "/caption",
        "image_output": {
            "pointer": "/picture",
            "media_type": media_type,
            "max_decoded_bytes": 1024,
        },
    }
    p = tmp_path / "renderer-v1.json"
    p.write_text(json.dumps(profile))
    p.chmod(0o600)
    monkeypatch.setenv("RENDERER_KEY", "renderer-private-key")
    a = get_provider_adapter(
        SimpleNamespace(
            provider="unrelated-renderer",
            provider_kind="module",
            capabilities={"completion_service": {"version": 1, "profile": "renderer-v1"}},
            provider_base_url="https://renderer.test",
            provider_api_key_env_var="RENDERER_KEY",
            provider_timeout_seconds=30,
            provider_max_retries=0,
        ),
        Settings(COMPLETION_SERVICE_PROFILE_DIR=str(tmp_path)),
    )
    encoded = base64.b64encode(data).decode()

    async def handler(req):
        assert str(req.url) == "https://renderer.test/v1/render"
        assert b'name="image"' in req.content
        return httpx.Response(200, json={"caption": "Two objects", "picture": encoded})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        a._http_client = client
        result = await a.forward_chat_completion(
            replace(request(model="renderer"), upstream_model="renderer")
        )
    message = result.json_body["choices"][0]["message"]
    assert message["content"] == "Two objects"
    assert message["images"] == [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{encoded}",
            },
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    ["missing", "duplicate", "invalid_base64", "url", "wrong_mime", "oversize", "incomplete"],
)
async def test_image_output_failures_do_not_drop_images_or_leak_partial_text(failure):
    payload = response()
    profile = load_profile("zap-it-v1")
    if failure == "missing":
        payload["output"].pop()
    elif failure == "duplicate":
        payload["output"].append(payload["output"][1])
    elif failure == "invalid_base64":
        payload["output"][1]["result"] = "not-base64!"
    elif failure == "url":
        payload["output"][1]["result"] = "https://untrusted.test/picture.png"
    elif failure == "wrong_mime":
        payload["output"][1]["result"] = base64.b64encode(b"\xff\xd8\xffimage").decode()
    elif failure == "oversize":
        profile = profile.model_copy(
            update={
                "image_output": profile.image_output.model_copy(update={"max_decoded_bytes": 1}),
            }
        )
    elif failure == "incomplete":
        payload["output"][1]["status"] = "in_progress"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(ProviderResponseParseError):
            await adapter(client, profile).forward_chat_completion(request())


def test_service_identities_and_endpoints_are_not_literals_in_shared_routing_code():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    profile_root = root / "app/slaif_gateway/modules/servers/completion_service/profiles"
    names = set()
    for path in profile_root.glob("*.json"):
        data = json.loads(path.read_text())
        names.update(
            data[k]
            for k in (
                "profile_id",
                "public_model",
                "upstream_model",
                "upstream_path",
                "api_key_env_var",
                "result_schema_version",
            )
            if isinstance(data.get(k), str)
        )
        if "providers" in data:
            names.update(data["providers"])
    for path in (
        "modules/servers/completion_service/adapter.py",
        "modules/servers/completion_service/profiles.py",
        "modules/servers/registry.py",
        "providers/factory.py",
    ):
        tree = ast.parse((root / "app/slaif_gateway" / path).read_text())
        literals = {
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
        assert not literals & names, (path, literals & names)
