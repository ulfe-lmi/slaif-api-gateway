from __future__ import annotations

from decimal import Decimal

import pytest

from slaif_gateway.metrics import (
    add_cost_eur,
    increment_provider_diagnostic_generated,
    increment_provider_http_error,
    observe_provider_call,
    prometheus_response_body,
    record_provider_call_result,
)


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


def test_streaming_provider_result_metric_is_recorded() -> None:
    record_provider_call_result(
        provider="openrouter",
        endpoint="chat.completions",
        status="success",
        duration_seconds=0.01,
    )
    metrics = prometheus_response_body().decode()

    assert (
        'gateway_provider_requests_total{endpoint="chat.completions",provider="openrouter",status="success"}'
        in metrics
    )


def test_provider_http_error_and_diagnostic_metrics_are_recorded() -> None:
    increment_provider_http_error(
        provider="openrouter",
        endpoint="chat.completions",
        upstream_status_code=429,
    )
    increment_provider_diagnostic_generated(provider="openrouter", endpoint="chat.completions")
    metrics = prometheus_response_body().decode()

    assert (
        'gateway_provider_http_errors_total{endpoint="chat.completions",provider="openrouter",status_class="4xx"}'
        in metrics
    )
    assert (
        'gateway_provider_diagnostics_generated_total{endpoint="chat.completions",provider="openrouter"}'
        in metrics
    )


def test_cost_metric_records_finalized_eur_cost() -> None:
    add_cost_eur(provider="openai", model="gpt-test-mini", cost_eur=Decimal("0.123"))
    add_cost_eur(provider="openai", model="gpt-test-mini", cost_eur=Decimal("0"))
    metrics = prometheus_response_body().decode()

    assert 'gateway_cost_eur_total{model="gpt-test-mini",provider="openai"}' in metrics
