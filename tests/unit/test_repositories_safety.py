"""Safety-focused unit tests for repository modules."""

from __future__ import annotations

import inspect

from slaif_gateway.db.repositories import (
    AdminSessionsRepository,
    AdminUsersRepository,
    AuditRepository,
    BackgroundJobsRepository,
    CohortsRepository,
    EmailDeliveriesRepository,
    GatewayKeysRepository,
    InstitutionsRepository,
    OneTimeSecretsRepository,
    OwnersRepository,
)

DISALLOWED_KEY_PARAM_NAMES = {
    "plaintext_key",
    "api_key_plaintext",
    "secret_plaintext",
    "raw_secret",
    "raw_key",
}
DISALLOWED_OTS_PARAM_NAMES = {
    "plaintext_key",
    "plaintext_secret",
    "secret_plaintext",
    "raw_secret",
    "raw_key",
    "api_key_plaintext",
}
DISALLOWED_IMPORT_TERMS = (
    "openai",
    "openrouter",
    "httpx",
    "aiosmtplib",
    "celery",
    "fastapi",
    "create_async_engine",
    "get_sessionmaker",
)
REPOSITORY_CLASSES = [
    InstitutionsRepository,
    CohortsRepository,
    OwnersRepository,
    AdminUsersRepository,
    AdminSessionsRepository,
    GatewayKeysRepository,
    AuditRepository,
    OneTimeSecretsRepository,
    EmailDeliveriesRepository,
    BackgroundJobsRepository,
]


def _repo_method_names(repository_cls: type[object]) -> list[str]:
    return [
        name
        for name, member in inspect.getmembers(repository_cls, predicate=inspect.iscoroutinefunction)
        if not name.startswith("_")
    ]


def test_keys_repository_has_no_plaintext_key_parameters() -> None:
    for method_name in _repo_method_names(GatewayKeysRepository):
        signature = inspect.signature(getattr(GatewayKeysRepository, method_name))
        forbidden = set(signature.parameters).intersection(DISALLOWED_KEY_PARAM_NAMES)
        assert not forbidden, f"{method_name} exposes forbidden key params: {forbidden}"


def test_one_time_secret_repository_has_no_plaintext_secret_parameters() -> None:
    for method_name in _repo_method_names(OneTimeSecretsRepository):
        signature = inspect.signature(getattr(OneTimeSecretsRepository, method_name))
        forbidden = set(signature.parameters).intersection(DISALLOWED_OTS_PARAM_NAMES)
        assert not forbidden, f"{method_name} exposes forbidden secret params: {forbidden}"


def test_repository_modules_do_not_import_runtime_layers() -> None:
    for repository_cls in REPOSITORY_CLASSES:
        source = inspect.getsource(inspect.getmodule(repository_cls))
        import_lines = [
            line.strip().lower()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            for term in DISALLOWED_IMPORT_TERMS:
                assert term not in line, f"forbidden import term '{term}' in {repository_cls.__name__}: {line}"


def test_repositories_accept_external_session_and_do_not_create_sessions() -> None:
    for repository_cls in REPOSITORY_CLASSES:
        init_signature = inspect.signature(repository_cls.__init__)
        assert "session" in init_signature.parameters


def test_repository_db_methods_are_async() -> None:
    for repository_cls in REPOSITORY_CLASSES:
        method_names = _repo_method_names(repository_cls)
        assert method_names, f"expected async methods on {repository_cls.__name__}"
