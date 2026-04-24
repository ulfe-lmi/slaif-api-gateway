"""Safety-focused unit tests for accounting repository modules."""

from __future__ import annotations

import inspect

from slaif_gateway.db.repositories import QuotaReservationsRepository, UsageLedgerRepository

FORBIDDEN_USAGE_PARAM_NAMES = {
    "prompt_content",
    "completion_content",
    "response_body",
    "plaintext_key",
    "api_key_plaintext",
    "secret_plaintext",
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
FORBIDDEN_QUOTA_TERMS = ("forward", "provider", "price", "pricing", "calculate", "cost_calc")


def _repo_method_names(repository_cls: type[object]) -> list[str]:
    return [
        name
        for name, member in inspect.getmembers(repository_cls, predicate=inspect.iscoroutinefunction)
        if not name.startswith("_")
    ]


def test_usage_repository_has_no_unsafe_parameter_names() -> None:
    for method_name in _repo_method_names(UsageLedgerRepository):
        signature = inspect.signature(getattr(UsageLedgerRepository, method_name))
        forbidden = set(signature.parameters).intersection(FORBIDDEN_USAGE_PARAM_NAMES)
        assert not forbidden, f"{method_name} exposes forbidden params: {forbidden}"


def test_accounting_repository_modules_do_not_import_runtime_layers() -> None:
    for repository_cls in (QuotaReservationsRepository, UsageLedgerRepository):
        source = inspect.getsource(inspect.getmodule(repository_cls))
        import_lines = [
            line.strip().lower()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            for term in FORBIDDEN_IMPORT_TERMS:
                assert term not in line, f"forbidden import term '{term}' in {repository_cls.__name__}: {line}"


def test_quota_repository_has_no_provider_forwarding_or_pricing_methods() -> None:
    method_names = _repo_method_names(QuotaReservationsRepository)
    for method_name in method_names:
        lowered = method_name.lower()
        assert not any(term in lowered for term in FORBIDDEN_QUOTA_TERMS)


def test_accounting_repositories_do_not_call_commit() -> None:
    for repository_cls in (QuotaReservationsRepository, UsageLedgerRepository):
        source = inspect.getsource(repository_cls)
        assert ".commit(" not in source
