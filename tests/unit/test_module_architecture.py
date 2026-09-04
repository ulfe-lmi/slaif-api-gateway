from __future__ import annotations

import ast
import asyncio
import subprocess
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
        "local-coding-v1",
    }
    assert ClientServerPair("openai-default", FACIAL_SCORING_SERVER_MODULE_ID) in CLIENT_SERVER_COMPATIBILITY
    assert ClientServerPair("openai-default", "local-coding-v1") in CLIENT_SERVER_COMPATIBILITY
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


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    return imported


def _is_module_or_child(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


FORBIDDEN_SERVER_IMPORT_PREFIXES = (
    "importlib",
    "pkg_resources",
    "setuptools",
    "redis",
    "slaif_gateway.api.auth",
    "slaif_gateway.api.dependencies",
    "slaif_gateway.db",
    "slaif_gateway.cache",
    "slaif_gateway.services.accounting",
    "slaif_gateway.services.admin_session_service",
    "slaif_gateway.services.audit",
    "slaif_gateway.services.audit_service",
    "slaif_gateway.services.auth_service",
    "slaif_gateway.services.external_tool",
    "slaif_gateway.services.external_tool_fence",
    "slaif_gateway.services.external_tool_hold",
    "slaif_gateway.services.fx_service",
    "slaif_gateway.services.key",
    "slaif_gateway.services.key_service",
    "slaif_gateway.services.pricing",
    "slaif_gateway.services.quota",
    "slaif_gateway.services.quota_service",
    "slaif_gateway.services.rate_limit_service",
    "slaif_gateway.services.reconciliation",
    "slaif_gateway.services.reservation_reconciliation",
    "slaif_gateway.services.route_resolution",
)
FORBIDDEN_SERVER_DYNAMIC_CALLS = frozenset(
    {"__import__", "entry_points", "find_spec", "import_module"}
)


def _server_import_is_forbidden(module: str) -> bool:
    return any(
        _is_module_or_child(module, prefix)
        for prefix in FORBIDDEN_SERVER_IMPORT_PREFIXES
    )


@pytest.mark.parametrize(
    ("module", "forbidden"),
    [
        ("redis", True),
        ("redis.asyncio", True),
        ("slaif_gateway.api.dependencies", True),
        ("slaif_gateway.db", True),
        ("slaif_gateway.db.repositories.keys", True),
        ("slaif_gateway.services.auth_service", True),
        ("slaif_gateway.services.admin_session_service", True),
        ("slaif_gateway.services.accounting", True),
        ("slaif_gateway.services.quota_service", True),
        ("slaif_gateway.services.rate_limit_service", True),
        ("slaif_gateway.services.reservation_reconciliation", True),
        ("slaif_gateway.services.external_tool_fence", True),
        ("slaif_gateway.services.external_tool_hold", True),
        ("slaif_gateway.services.key_service", True),
        ("slaif_gateway.services.pricing", True),
        ("slaif_gateway.services.fx_service", True),
        ("slaif_gateway.services.audit_service", True),
        ("importlib", True),
        ("importlib.util", True),
        ("pkg_resources", True),
        ("httpx", False),
        ("slaif_gateway.providers.errors", False),
        ("slaif_gateway.providers.streaming", False),
        ("slaif_gateway.schemas.providers", False),
        ("slaif_gateway.config", False),
        ("slaif_gateway.modules.contracts", False),
        ("collections.abc", False),
    ],
)
def test_server_import_authority_predicate(module: str, forbidden: bool) -> None:
    assert _server_import_is_forbidden(module) is forbidden


def test_server_modules_have_no_gateway_authority_imports_or_dynamic_loading() -> None:
    server_root = ROOT / "app/slaif_gateway/modules/servers"
    for path in server_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(
            _server_import_is_forbidden(module)
            for module in _imported_modules(path)
        ), path
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function_name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else None
            )
            assert function_name not in FORBIDDEN_SERVER_DYNAMIC_CALLS, path


def test_default_client_helper_uses_registry_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    from slaif_gateway.modules.clients import registry

    calls: list[str] = []

    class _ObservedModule:
        def normalize(self, endpoint: str, body: dict[str, object]) -> SimpleNamespace:
            return SimpleNamespace(module_id="observed", endpoint=endpoint, body=body)

    def resolve(module_id: str) -> _ObservedModule:
        calls.append(module_id)
        return _ObservedModule()

    monkeypatch.setattr(registry, "get_client_module", resolve)
    result = registry.normalize_default_client_request("/v1/responses", {"input": "x"})

    assert calls == ["openai-default"]
    assert result.module_id == "observed"


def test_provider_factory_owns_server_registry_callsite() -> None:
    path = ROOT / "app/slaif_gateway/providers/factory.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules = _imported_modules(path)
    assert "slaif_gateway.modules.servers.registry" in imported_modules
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "slaif_gateway.modules.servers.registry"
        for alias in node.names
    }
    assert {"resolve_server_module", "ensure_client_server_pair", "build_server_adapter"}.issubset(
        imported_names
    )
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {"resolve_server_module", "ensure_client_server_pair", "build_server_adapter"}.issubset(
        called_names
    )
    forbidden_direct_construction = {
        "OpenAIProviderAdapter",
        "OpenRouterProviderAdapter",
        "OpenAICompatibleProviderAdapter",
        "FacialScoringAdapter",
        "get_module_adapter",
    }
    assert called_names.isdisjoint(forbidden_direct_construction)


def test_local_coding_server_is_responses_only_and_does_not_reuse_openai_transport() -> None:
    path = ROOT / "app/slaif_gateway/modules/servers/local_coding/adapter.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules = _imported_modules(path)
    assert "slaif_gateway.providers.openai" not in imported_modules
    assert "slaif_gateway.providers.base" in imported_modules
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert called_names.isdisjoint({"_post_json", "_stream_sse"})
    adapter_classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "LocalCodingAdapter"
    ]
    assert len(adapter_classes) == 1
    assert [
        base.id for base in adapter_classes[0].bases if isinstance(base, ast.Name)
    ] == ["ProviderAdapter"]


def test_ignored_cache_files_are_absent_from_git_diff() -> None:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        text=True,
    )
    assert all("__pycache__" not in path for path in output.split("\x00"))


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
