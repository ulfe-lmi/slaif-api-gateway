from __future__ import annotations

from slaif_gateway.metrics import increment_reconciliation_alert, prometheus_response_body


def test_reconciliation_alert_metrics_are_low_cardinality() -> None:
    increment_reconciliation_alert(status="success")
    increment_reconciliation_alert(status="failure")

    body = "\n".join(
        line
        for line in prometheus_response_body().decode().splitlines()
        if line.startswith("gateway_reconciliation_alert")
    )

    assert 'gateway_reconciliation_alerts_total{status="success"}' in body
    assert 'gateway_reconciliation_alerts_total{status="failure"}' in body
    assert "gateway_reconciliation_alert_failures_total" in body
    assert "webhook" not in body
    assert "reservation_id" not in body
    assert "usage_ledger_id" not in body
