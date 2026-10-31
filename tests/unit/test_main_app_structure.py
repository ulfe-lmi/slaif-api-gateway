from __future__ import annotations

import ast
import inspect

from fastapi.testclient import TestClient

import slaif_gateway.api.openai_compat as openai_compat_module
import slaif_gateway.main as main_module
import slaif_gateway.services.chat_completion_gateway as chat_gateway_module
from slaif_gateway.main import create_app


def test_health_routes_still_registered() -> None:
    client = TestClient(create_app())

    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 503


def test_v1_routes_still_registered_and_require_auth() -> None:
    client = TestClient(create_app())

    models_response = client.get("/v1/models")
    chat_response = client.post("/v1/chat/completions", json={"model": "gpt-test", "messages": []})

    assert models_response.status_code == 401
    assert chat_response.status_code == 401


def test_main_app_only_wires_app_and_routes() -> None:
    source = inspect.getsource(main_module)

    assert "include_router(health_router)" in source
    assert "include_router(openai_compat_router)" in source
    assert "forward_chat_completion" not in source
    assert "reserve_for_chat_completion" not in source
    # main is the composition root. Ordinary new router imports/includes
    # must pass these structural checks without any line ceiling change,
    # while business orchestration, data access, provider IO and inline
    # API handlers must remain in their own layers, never in main.
    violation = _main_structure_violation(ast.parse(source))
    assert violation is None, violation


def test_main_structure_guard_rejects_non_composition_shapes() -> None:
    negative_sources = (
        "from slaif_gateway import services\n",
        "import slaif_gateway.db.repositories\n",
        "def create_app():\n"
        "    def handler(request):\n"
        "        return 'x'\n"
        "    app = object()\n"
        "    app.add_api_route('/v1/x', handler)\n"
        "    return app\n",
        "def create_app():\n"
        "    def ws_handler(websocket):\n"
        "        pass\n"
        "    app = object()\n"
        "    app.add_api_websocket_route('/ws', ws_handler)\n"
        "    return app\n",
        "def create_app():\n"
        "    app = object()\n"
        "    @app.get('/v1/x')\n"
        "    def handler():\n"
        "        return 'x'\n"
        "    @app.websocket_route('/ws')\n"
        "    async def ws():\n"
        "        pass\n"
        "    return app\n",
        "def create_app():\n"
        "    other = object()\n"
        "    other.include_router(r)\n",
    )
    for source in negative_sources:
        violation = _main_structure_violation(ast.parse(source))
        assert violation is not None, f"guard accepted non-composition shape: {source!r}"

    positive_source = (
        "from slaif_gateway.api.health import router as health_router\n"
        "from slaif_gateway import metrics as metrics_module\n"
        "from slaif_gateway.config import Settings\n"
        "from unrelated_package import services\n"
        "def create_app(settings: Settings | None = None):\n"
        "    app = object()\n"
        "    metrics_module.cleanup()\n"
        "    app.include_router(health_router)\n"
        "    return app\n"
    )
    assert _main_structure_violation(ast.parse(positive_source)) is None


# First-party subpackages that own business orchestration, data access,
# background IO, or provider adapters. main may not import from these.
_MAIN_FORBIDDEN_FIRST_PARTY = frozenset({"services", "db", "workers", "providers"})

# FastAPI/Starlette route decorator methods plus Starlette's generic
# route/websocket_route forms. A function carrying one of these in main.py
# would be an inline API handler, not app composition.
_ROUTE_DECORATOR_METHODS = frozenset(
    {
        "get",
        "post",
        "put",
        "delete",
        "patch",
        "options",
        "head",
        "websocket",
        "api_route",
        "route",
        "websocket_route",
    }
)

# Direct handler-registration calls that must never appear in main.py;
# routes belong in router modules that main composes via include_router.
_HANDLER_REGISTRATION_METHODS = frozenset(
    {"add_api_route", "add_route", "add_websocket_route", "add_api_websocket_route"}
)


def _first_party_import_modules(tree: ast.Module) -> list[str]:
    """Qualified first-party module names referenced by main.py imports."""
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name != "*":
                    modules.append(f"{node.module}.{alias.name}")
    return [
        module
        for module in modules
        if module == "slaif_gateway" or module.startswith("slaif_gateway.")
    ]


def _main_structure_violation(tree: ast.Module) -> str | None:
    """Return the first main-as-composition violation, or None if clean."""
    for module in _first_party_import_modules(tree):
        parts = module.split(".")
        if len(parts) >= 2 and parts[1] in _MAIN_FORBIDDEN_FIRST_PARTY:
            return f"main.py must not import orchestration/data/IO layer {module!r}"
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _HANDLER_REGISTRATION_METHODS
        ):
            return f"main.py must not register handlers directly via {node.func.attr}"
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
        ):
            if not (
                isinstance(node.func.value, ast.Name) and node.func.value.id == "app"
            ):
                return "include_router must be called on the app instance in main.py"
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr in _ROUTE_DECORATOR_METHODS
                ):
                    return f"inline API handler {node.name!r} must not be defined in main.py"
    return None


def test_openai_compat_module_exposes_v1_routes() -> None:
    paths = {route.path for route in openai_compat_module.router.routes}

    assert "/v1/models" in paths
    assert "/v1/chat/completions" in paths


def test_chat_completion_gateway_contains_orchestration_logic() -> None:
    source = inspect.getsource(chat_gateway_module)

    assert "reserve_for_chat_completion" in source
    assert "forward_chat_completion" in source
    assert "finalize_successful_response" in source
