from __future__ import annotations

import inspect

from slaif_gateway.cli import email as email_cli
from slaif_gateway.services import email_delivery_service, email_service
from slaif_gateway.workers import tasks_email


def test_email_foundation_does_not_import_provider_clients() -> None:
    modules = (email_cli, email_delivery_service, email_service, tasks_email)

    for module in modules:
        source = inspect.getsource(module)
        assert "slaif_gateway.providers" not in source
        assert "OPENAI_UPSTREAM_API_KEY" not in source
        assert "OPENROUTER_API_KEY" not in source


def test_celery_task_source_does_not_accept_plaintext_key_payloads() -> None:
    source = inspect.getsource(tasks_email.send_pending_key_email_task.run)

    assert "plaintext_key" not in source
    assert "secret_value" not in source
    assert "key=" not in source
