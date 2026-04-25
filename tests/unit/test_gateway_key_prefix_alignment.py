from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.db.base import Base
from slaif_gateway.schemas.keys import CreateGatewayKeyInput
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.utils.crypto import parse_gateway_key_public_id
from slaif_gateway.utils.secrets import generate_secret_key


@dataclass
class _FakeGatewayKeyRow:
    id: uuid.UUID


@dataclass
class _FakeOneTimeSecretRow:
    id: uuid.UUID


class _FakeGatewayKeysRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create_gateway_key_record(self, **kwargs: object) -> _FakeGatewayKeyRow:
        self.calls.append(kwargs)
        return _FakeGatewayKeyRow(id=uuid.uuid4())


class _FakeOneTimeSecretsRepository:
    async def create_one_time_secret(self, **kwargs: object) -> _FakeOneTimeSecretRow:
        return _FakeOneTimeSecretRow(id=uuid.uuid4())


class _FakeAuditRepository:
    async def add_audit_log(self, **kwargs: object) -> None:
        return None


def test_settings_default_prefix_and_accepted_prefixes_align() -> None:
    settings = Settings()

    assert settings.get_gateway_key_prefix() == "sk-slaif-"
    assert "sk-slaif-" in settings.get_gateway_key_accepted_prefixes()


def test_gateway_key_model_default_prefix_uses_trailing_dash() -> None:
    gateway_keys_table = Base.metadata.tables["gateway_keys"]
    key_prefix_column = gateway_keys_table.columns["key_prefix"]

    assert key_prefix_column.default is not None
    assert key_prefix_column.default.arg == "sk-slaif-"
    assert key_prefix_column.server_default is not None
    assert "sk-slaif-" in str(key_prefix_column.server_default.arg)
    assert "'sk-slaif'" not in str(key_prefix_column.server_default.arg)


@pytest.mark.asyncio
async def test_generated_keys_and_persisted_key_prefix_use_configured_prefix() -> None:
    settings = Settings(
        ACTIVE_HMAC_KEY_VERSION="1",
        TOKEN_HMAC_SECRET_V1="h" * 48,
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        ONE_TIME_SECRET_KEY_VERSION="v1",
        GATEWAY_KEY_PREFIX="sk-classroom-",
        GATEWAY_KEY_ACCEPTED_PREFIXES="sk-classroom-,sk-slaif-",
    )
    keys_repo = _FakeGatewayKeysRepository()
    service = KeyService(
        settings=settings,
        gateway_keys_repository=keys_repo,
        one_time_secrets_repository=_FakeOneTimeSecretsRepository(),
        audit_repository=_FakeAuditRepository(),
    )

    payload = CreateGatewayKeyInput(
        owner_id=uuid.uuid4(),
        valid_from=datetime.now(UTC),
        valid_until=datetime.now(UTC) + timedelta(days=30),
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        allowed_models=[],
        allowed_endpoints=[],
        rate_limit_policy={},
    )

    result = await service.create_gateway_key(payload)

    assert result.plaintext_key.startswith("sk-classroom-")
    assert result.public_key_id == parse_gateway_key_public_id(
        result.plaintext_key,
        ("sk-classroom-", "sk-slaif-"),
    )
    assert keys_repo.calls[0]["key_prefix"] == "sk-classroom-"


def test_seed_script_uses_configured_prefix_without_stripping_dash() -> None:
    content = Path("scripts/seed_test_data.py").read_text()

    assert "settings.get_gateway_key_prefix()" in content
    assert "get_gateway_key_prefix().rstrip(\"-\")" not in content


def test_no_undashed_slaif_prefix_default_in_current_sources() -> None:
    checked_files = (
        Path("app/slaif_gateway/config.py"),
        Path("app/slaif_gateway/db/models.py"),
        Path("app/slaif_gateway/db/repositories/keys.py"),
        Path("app/slaif_gateway/services/key_service.py"),
        Path("scripts/seed_test_data.py"),
        Path("docs/database-schema.md"),
        Path("README.md"),
    )
    combined = "\n".join(path.read_text() for path in checked_files)

    assert "default=\"sk-slaif\"" not in combined
    assert "default 'sk-slaif'" not in combined


def test_sk_ulfe_mentions_are_limited_to_legacy_compatibility_context() -> None:
    matches: list[tuple[str, int, str]] = []
    for path in Path("tests").rglob("*.py"):
        for line_no, line in enumerate(path.read_text().splitlines(), start=1):
            if "sk-ulfe-" in line:
                matches.append((str(path), line_no, line))

    assert matches, "expected at least one legacy compatibility test mention"
    for file_path, _line_no, line in matches:
        if file_path.endswith("test_auth_service.py") or file_path.endswith(
            "test_v1_auth_dependency.py"
        ) or file_path.endswith("test_crypto_gateway_keys.py") or file_path.endswith(
            "test_config.py"
        ) or file_path.endswith(
            "test_gateway_key_prefix_alignment.py"
        ):
            continue
        raise AssertionError(json.dumps({"file": file_path, "line": line}))
