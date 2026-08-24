from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.modules.clients.registry import (
    CLIENT_MODULE_REGISTRY,
    DEFAULT_CLIENT_MODULE,
    normalize_default_client_request,
)
from slaif_gateway.modules.contracts import ClientServerPair, ModuleSelectionError
from slaif_gateway.modules.servers.registry import (
    CLIENT_SERVER_COMPATIBILITY,
    FACIAL_SCORING_SERVER_MODULE_ID,
    SERVER_MODULE_REGISTRY,
    ensure_client_server_pair,
    resolve_server_module,
)
from slaif_gateway.providers.errors import ProviderConfigurationError

ROOT = Path(__file__).parents[2]


def test_default_client_module_returns_fresh_content_without_retention() -> None:
    body = {"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]}

    result = normalize_default_client_request("/v1/chat/completions", body)

    assert result.module_id == "openai-default"
    assert result.module_version == "1"
    assert result.body == body
    assert result.body is not body
    assert result.body["messages"] is not body["messages"]
    body["messages"][0]["content"] = "changed"
    assert result.body["messages"][0]["content"] == "hello"


def test_module_registries_are_literal_and_fail_closed() -> None:
    assert CLIENT_MODULE_REGISTRY["openai-default"] is DEFAULT_CLIENT_MODULE
    assert set(SERVER_MODULE_REGISTRY) == {
        "openai",
        "openrouter",
        "openai-compatible",
        "facial_scoring",
    }
    assert ClientServerPair("openai-default", FACIAL_SCORING_SERVER_MODULE_ID) in CLIENT_SERVER_COMPATIBILITY
    with pytest.raises(TypeError):
        CLIENT_MODULE_REGISTRY["dynamic"] = DEFAULT_CLIENT_MODULE  # type: ignore[index]
    with pytest.raises(ModuleSelectionError):
        normalize_default_client_request("/v1/embeddings", {})
    with pytest.raises(ProviderConfigurationError) as exc_info:
        ensure_client_server_pair("unknown-client", "openai")
    assert exc_info.value.error_code == "incompatible_module_pair"


def test_server_resolution_is_static_and_unknown_modules_fail_closed() -> None:
    assert resolve_server_module("openai", None).module_id == "openai"
    assert resolve_server_module("openrouter", "openrouter").module_id == "openrouter"
    assert resolve_server_module("local-model", "openai_compatible").module_id == "openai-compatible"
    assert resolve_server_module("facial_scoring", "module").module_id == "facial_scoring"
    with pytest.raises(ProviderConfigurationError) as exc_info:
        resolve_server_module("unreviewed", "module")
    assert exc_info.value.error_code == "unsupported_module"


def test_client_modules_have_no_gateway_authority_imports() -> None:
    forbidden_fragments = (
        "db",
        "redis",
        "httpx",
        "providers",
        "quota",
        "accounting",
        "pricing",
        "audit",
        "importlib",
    )
    client_root = ROOT / "app/slaif_gateway/modules/clients"
    for path in client_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = [
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ] + [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        assert not any(
            any(fragment in module.lower() for fragment in forbidden_fragments)
            for module in imported
        ), path


def test_facial_compatibility_path_is_only_a_reexport() -> None:
    tree = ast.parse(
        (ROOT / "app/slaif_gateway/modules/facial_scoring/adapter.py").read_text(
            encoding="utf-8"
        )
    )
    assert not any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))


def test_chat_create_entrypoint_calls_default_client_module(monkeypatch: pytest.MonkeyPatch) -> None:
    import slaif_gateway.services.chat_completion_gateway as gateway

    calls: list[tuple[str, dict[str, object]]] = []

    def normalize(endpoint: str, body: dict[str, object]) -> SimpleNamespace:
        calls.append((endpoint, body))
        raise RuntimeError("default client module called")

    monkeypatch.setattr(gateway, "normalize_default_client_request", normalize)
    payload = SimpleNamespace(model_dump=lambda **_: {"messages": []})
    with pytest.raises(RuntimeError, match="default client module called"):
        asyncio.run(
            gateway.handle_chat_completion(
                payload=payload,
                authenticated_key=SimpleNamespace(),
                settings=Settings(),
            )
        )
    assert calls == [("/v1/chat/completions", {"messages": []})]


def test_responses_create_entrypoint_calls_default_client_module(monkeypatch: pytest.MonkeyPatch) -> None:
    import slaif_gateway.services.responses_gateway as gateway

    calls: list[tuple[str, dict[str, object]]] = []

    def normalize(endpoint: str, body: dict[str, object]) -> SimpleNamespace:
        calls.append((endpoint, body))
        raise RuntimeError("default client module called")

    monkeypatch.setattr(gateway, "normalize_default_client_request", normalize)
    payload = SimpleNamespace(
        model_dump=lambda **_: {"input": "hello"},
        model_fields_set=set(),
    )
    with pytest.raises(RuntimeError, match="default client module called"):
        asyncio.run(
            gateway.handle_response_create(
                payload=payload,
                authenticated_key=SimpleNamespace(),
                settings=Settings(),
            )
        )
    assert calls == [("/v1/responses", {"input": "hello"})]
