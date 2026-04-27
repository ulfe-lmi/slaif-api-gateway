from __future__ import annotations

import pytest

from slaif_gateway.metrics import observe_provider_call, prometheus_response_body


async def _successful_call() -> str:
    return "ok"


async def _failing_call() -> str:
    raise RuntimeError("provider failed")


@pytest.mark.asyncio
async def test_provider_success_metric_is_recorded() -> None:
    result = await observe_provider_call(
        provider="openai",
        endpoint="chat.completions",
        call=_successful_call,
    )
    metrics = prometheus_response_body().decode()

    assert result == "ok"
    assert (
        'gateway_provider_requests_total{endpoint="chat.completions",provider="openai",status="success"}'
        in metrics
    )
    assert (
        'gateway_provider_request_duration_seconds_count{endpoint="chat.completions",provider="openai"}'
        in metrics
    )


@pytest.mark.asyncio
async def test_provider_error_metric_is_recorded() -> None:
    with pytest.raises(RuntimeError):
        await observe_provider_call(
            provider="openrouter",
            endpoint="chat.completions",
            call=_failing_call,
        )
    metrics = prometheus_response_body().decode()

    assert (
        'gateway_provider_requests_total{endpoint="chat.completions",provider="openrouter",status="error"}'
        in metrics
    )
