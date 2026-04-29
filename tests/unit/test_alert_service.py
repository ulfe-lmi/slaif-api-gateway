from __future__ import annotations

import httpx
import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.alert_errors import AlertDeliveryError
from slaif_gateway.services.alert_service import (
    AlertService,
    build_reconciliation_alert_payload,
)


def _summary() -> dict[str, object]:
    return {
        "status": "success",
        "dry_run": True,
        "expired_reservations": {
            "candidate_count": 2,
            "reservation_ids": [
                "11111111-1111-1111-1111-111111111111",
                "22222222-2222-2222-2222-222222222222",
            ],
        },
        "provider_completed": {
            "candidate_count": 1,
            "usage_ledger_ids": ["33333333-3333-3333-3333-333333333333"],
            "reservation_ids": ["44444444-4444-4444-4444-444444444444"],
        },
        "ignored_secret_material": "Bearer sk-provider-secret-value-aaaaaaaaaaaa",
        "prompt": "sensitive prompt",
        "completion": "sensitive completion",
    }


def _settings(**overrides) -> Settings:
    return Settings(
        ENABLE_RECONCILIATION_ALERTS=True,
        RECONCILIATION_ALERT_WEBHOOK_URL="https://alerts.example/reconciliation",
        **overrides,
    )


def test_alert_payload_counts_only_by_default() -> None:
    payload = build_reconciliation_alert_payload(
        _summary(),
        settings=_settings(),
    )

    assert payload["event_type"] == "reconciliation_backlog"
    assert payload["expired_reservation_count"] == 2
    assert payload["provider_completed_recovery_count"] == 1
    assert "expired_reservation_ids" not in payload
    assert "provider_completed_usage_ledger_ids" not in payload
    serialized = str(payload)
    assert "sk-provider-secret-value" not in serialized
    assert "sensitive prompt" not in serialized
    assert "sensitive completion" not in serialized
    assert "token_hash" not in serialized
    assert "encrypted_payload" not in serialized
    assert "nonce" not in serialized


def test_alert_payload_includes_safe_ids_only_when_enabled() -> None:
    payload = build_reconciliation_alert_payload(
        _summary(),
        settings=_settings(),
        include_ids=True,
    )

    assert payload["expired_reservation_ids"] == [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    ]
    assert payload["provider_completed_usage_ledger_ids"] == [
        "33333333-3333-3333-3333-333333333333"
    ]
    serialized = str(payload)
    assert "sk-provider-secret-value" not in serialized
    assert "sensitive prompt" not in serialized


@pytest.mark.asyncio
async def test_alert_service_sends_mocked_webhook(respx_mock) -> None:
    route = respx_mock.post("https://alerts.example/reconciliation").mock(
        return_value=httpx.Response(202, json={"ok": True})
    )

    result = await AlertService().send_reconciliation_backlog_alert(
        _summary(),
        settings=_settings(),
    )

    assert route.called
    assert result.status == "sent"
    assert result.webhook_status_code == 202
    assert "alerts.example" not in str(result.to_payload())


@pytest.mark.asyncio
async def test_alert_service_skips_when_disabled(respx_mock) -> None:
    route = respx_mock.post("https://alerts.example/reconciliation").mock(
        return_value=httpx.Response(202, json={"ok": True})
    )

    result = await AlertService().send_reconciliation_backlog_alert(
        _summary(),
        settings=Settings(RECONCILIATION_ALERT_WEBHOOK_URL="https://alerts.example/reconciliation"),
    )

    assert not route.called
    assert result.status == "skipped"
    assert result.reason == "alerts_disabled"


@pytest.mark.asyncio
async def test_alert_service_skips_below_threshold(respx_mock) -> None:
    route = respx_mock.post("https://alerts.example/reconciliation").mock(
        return_value=httpx.Response(202, json={"ok": True})
    )

    result = await AlertService().send_reconciliation_backlog_alert(
        _summary(),
        settings=_settings(
            RECONCILIATION_ALERT_MIN_EXPIRED_RESERVATIONS=3,
            RECONCILIATION_ALERT_MIN_PROVIDER_COMPLETED=2,
        ),
    )

    assert not route.called
    assert result.status == "skipped"
    assert result.reason == "below_threshold"


@pytest.mark.asyncio
async def test_alert_service_non_2xx_error_is_safe(respx_mock) -> None:
    respx_mock.post("https://alerts.example/reconciliation").mock(
        return_value=httpx.Response(500, text="secret body")
    )

    with pytest.raises(AlertDeliveryError) as exc:
        await AlertService().send_reconciliation_backlog_alert(
            _summary(),
            settings=_settings(),
        )

    message = str(exc.value)
    assert message == "alert webhook returned HTTP 500"
    assert "https://alerts.example" not in message
    assert "secret body" not in message


@pytest.mark.asyncio
async def test_alert_service_timeout_error_is_safe(respx_mock) -> None:
    respx_mock.post("https://alerts.example/reconciliation").mock(
        side_effect=httpx.TimeoutException("timeout for https://alerts.example/reconciliation")
    )

    with pytest.raises(AlertDeliveryError) as exc:
        await AlertService().send_reconciliation_backlog_alert(
            _summary(),
            settings=_settings(),
        )

    message = str(exc.value)
    assert message == "alert webhook request timed out"
    assert "alerts.example" not in message
