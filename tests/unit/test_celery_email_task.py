from __future__ import annotations

import inspect
import uuid

import pytest

from slaif_gateway.workers import tasks_email


def test_send_pending_key_email_task_signature_uses_ids_only() -> None:
    signature = inspect.signature(tasks_email.send_pending_key_email_task.run)

    assert list(signature.parameters) == [
        "one_time_secret_id",
        "email_delivery_id",
        "actor_admin_id",
    ]
    assert signature.parameters["one_time_secret_id"].annotation == "str"
    assert signature.parameters["email_delivery_id"].annotation == "str | None"
    assert "plaintext" not in str(signature).lower()
    assert "gateway_key" not in str(signature).lower()


def test_email_task_result_is_safe() -> None:
    result = tasks_email._safe_task_result(
        tasks_email.PendingKeyEmailResult(
            email_delivery_id=uuid.uuid4(),
            one_time_secret_id=uuid.uuid4(),
            gateway_key_id=uuid.uuid4(),
            owner_id=uuid.uuid4(),
            recipient_email="ada@example.org",
            status="sent",
            provider_message_id="<message@example.org>",
        )
    )

    serialized = str(result)
    assert "plaintext" not in serialized.lower()
    assert "sk-slaif-" not in serialized
    assert "ada@example.org" not in serialized


@pytest.mark.asyncio
async def test_email_task_opens_and_disposes_db_engine(monkeypatch) -> None:
    disposed = False
    seen: dict[str, object] = {}

    class FakeEngine:
        async def dispose(self):
            nonlocal disposed
            disposed = True

    class FakeTransaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def begin(self):
            return FakeTransaction()

    class FakeSessionFactory:
        def __call__(self):
            return FakeSession()

    class FakeService:
        def __init__(self, **kwargs):
            seen["service_kwargs"] = kwargs

        async def send_pending_key_email(self, **kwargs):
            seen["send_kwargs"] = kwargs
            return tasks_email.PendingKeyEmailResult(
                email_delivery_id=uuid.uuid4(),
                one_time_secret_id=kwargs["one_time_secret_id"],
                gateway_key_id=None,
                owner_id=None,
                recipient_email=None,
                status="sent",
            )

    monkeypatch.setattr(tasks_email, "create_engine_from_settings", lambda settings: FakeEngine())
    monkeypatch.setattr(tasks_email, "create_sessionmaker_from_engine", lambda engine: FakeSessionFactory())
    monkeypatch.setattr(tasks_email, "EmailDeliveryService", FakeService)

    secret_id = uuid.uuid4()
    result = await tasks_email._send_pending_key_email(
        settings=tasks_email.Settings(DATABASE_URL="postgresql+asyncpg://test/test"),
        one_time_secret_id=str(secret_id),
    )

    assert result["status"] == "sent"
    assert seen["send_kwargs"]["one_time_secret_id"] == secret_id
    assert disposed is True


def test_email_task_module_does_not_import_fastapi_routes_or_providers() -> None:
    source = inspect.getsource(tasks_email)

    forbidden = (
        "slaif_gateway.api",
        "slaif_gateway.providers",
        "OPENAI_UPSTREAM_API_KEY",
        "OPENROUTER_API_KEY",
    )
    for term in forbidden:
        assert term not in source
