"""Safety-focused unit tests for provider/routing/pricing/fx repositories."""

from __future__ import annotations

import inspect

from slaif_gateway.db.repositories import (
    FxRatesRepository,
    ModelRoutesRepository,
    PricingRulesRepository,
    ProviderConfigsRepository,
)

FORBIDDEN_PROVIDER_PARAM_NAMES = {
    "api_key",
    "api_key_plaintext",
    "secret",
    "secret_value",
    "provider_secret",
    "encrypted_api_key",
    "raw_secret",
    "raw_key",
}
FORBIDDEN_IMPORT_TERMS = (
    "fastapi",
    "openai",
    "openrouter",
    "aiosmtplib",
    "celery",
    "create_async_engine",
    "get_sessionmaker",
)
FORBIDDEN_PRICING_METHOD_TERMS = ("fetch", "call", "provider_api", "openai", "openrouter")
FORBIDDEN_FX_METHOD_TERMS = ("fetch", "http", "api", "provider", "openai", "openrouter")


def _repo_method_names(repository_cls: type[object]) -> list[str]:
    return [
        name
        for name, member in inspect.getmembers(repository_cls, predicate=inspect.iscoroutinefunction)
        if not name.startswith("_")
    ]


def test_provider_configs_repository_has_no_secret_parameter_names() -> None:
    for method_name in _repo_method_names(ProviderConfigsRepository):
        signature = inspect.signature(getattr(ProviderConfigsRepository, method_name))
        forbidden = set(signature.parameters).intersection(FORBIDDEN_PROVIDER_PARAM_NAMES)
        assert not forbidden, f"{method_name} exposes forbidden params: {forbidden}"


def test_repository_modules_do_not_import_runtime_layers() -> None:
    for repository_cls in (
        ProviderConfigsRepository,
        ModelRoutesRepository,
        PricingRulesRepository,
        FxRatesRepository,
    ):
        source = inspect.getsource(inspect.getmodule(repository_cls))
        import_lines = [
            line.strip().lower()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            for term in FORBIDDEN_IMPORT_TERMS:
                assert term not in line, f"forbidden import term '{term}' in {repository_cls.__name__}: {line}"


def test_pricing_repository_has_no_provider_api_call_methods() -> None:
    for method_name in _repo_method_names(PricingRulesRepository):
        lowered = method_name.lower()
        assert not any(term in lowered for term in FORBIDDEN_PRICING_METHOD_TERMS)


def test_fx_repository_has_no_external_api_call_methods() -> None:
    for method_name in _repo_method_names(FxRatesRepository):
        lowered = method_name.lower()
        assert not any(term in lowered for term in FORBIDDEN_FX_METHOD_TERMS)


def test_provider_pricing_repositories_do_not_call_commit() -> None:
    for repository_cls in (
        ProviderConfigsRepository,
        ModelRoutesRepository,
        PricingRulesRepository,
        FxRatesRepository,
    ):
        source = inspect.getsource(repository_cls)
        assert ".commit(" not in source
