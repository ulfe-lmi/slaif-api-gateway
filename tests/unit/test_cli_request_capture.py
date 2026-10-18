"""Unit tests for the request-capture operator CLI (objective 191, R3/R7).

Covers the disabled-facility refusal, arm/status/stop/cleanup lifecycle with
explicit ``None``-default options, the bounded inspect reads, and the local
fixed error boundary: known store/CLI errors keep their fixed reasons while
any unexpected exception degrades to the generic ``command_failed`` without
echoing its content.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from slaif_gateway.cli import main as cli_main
from slaif_gateway.config import get_settings
from slaif_gateway.services.request_capture import CaptureStore

runner = CliRunner()


def setup_function() -> None:
    get_settings.cache_clear()


def teardown_function() -> None:
    get_settings.cache_clear()


def _enable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "captures"
    monkeypatch.setenv("REQUEST_CAPTURE_ENABLED", "true")
    monkeypatch.setenv("REQUEST_CAPTURE_DIR", str(root))
    get_settings.cache_clear()
    return root


def _invoke(args: list[str]) -> Any:
    return runner.invoke(cli_main.app, ["request-capture", *args])


def _stdout_json(result: Any) -> dict[str, Any]:
    return json.loads(result.output)


def test_arm_refused_when_facility_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REQUEST_CAPTURE_ENABLED", raising=False)
    get_settings.cache_clear()
    result = _invoke(["arm", "--endpoint", "/v1/responses"])
    assert result.exit_code == 1
    payload = _stdout_json(result)
    assert payload["error"]["message"].startswith("request capture is not enabled")


def test_arm_defaults_and_status_lifecycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _enable(monkeypatch, tmp_path)
    result = _invoke(["arm", "--endpoint", "/v1/responses"])
    assert result.exit_code == 0, result.output
    session = _stdout_json(result)
    assert session["session_id"].startswith("cap-")
    assert session["count"] == 1
    assert session["claimed"] == 0
    assert session["remaining"] == 1
    assert session["status"] == "active"
    assert session["key_uuid"] is None

    result = _invoke(["status"])
    assert result.exit_code == 0, result.output
    payload = _stdout_json(result)
    assert payload["storage_bytes_reserved"] == 0
    assert [s["session_id"] for s in payload["sessions"]] == [session["session_id"]]

    result = _invoke(["stop", "--session-id", session["session_id"]])
    assert result.exit_code == 0, result.output
    assert _stdout_json(result) == {"stopped": 1}

    result = _invoke(["status"])
    assert _stdout_json(result)["sessions"][0]["status"] == "stopped"


def test_arm_explicit_count_and_ttl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _enable(monkeypatch, tmp_path)
    result = _invoke(
        [
            "arm",
            "--endpoint",
            "/v1/responses",
            "--count",
            "3",
            "--ttl-seconds",
            "120",
        ]
    )
    assert result.exit_code == 0, result.output
    session = _stdout_json(result)
    assert session["count"] == 3
    assert session["status"] == "active"


def test_stop_rejects_malformed_session_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _enable(monkeypatch, tmp_path)
    result = _invoke(["stop", "--session-id", "../../etc/passwd"])
    assert result.exit_code == 1
    assert "invalid form" in _stdout_json(result)["error"]["message"]


def _publish_artifact(store: CaptureStore, endpoint: str, request_id: str) -> str:
    session = store.arm(endpoint=endpoint)
    store.claim(endpoint=endpoint, reserve_bytes=store.reservation_bytes())
    body = b'{"input":"synthetic-complete-body"}'
    capture = json.dumps(
        {
            "schema_version": 1,
            "request_id": request_id,
            "method": "POST",
            "path": base64.b64encode(b"/v1/responses").decode(),
            "query": "",
            "headers": [],
            "body": base64.b64encode(body).decode(),
            "body_complete": True,
            "incomplete_reason": None,
            "body_omitted_for_secret_safety": False,
            "body_bytes_observed": len(body),
            "body_bytes_buffered": len(body),
            "body_bytes_stored": len(body),
            "body_bytes_declared": len(body),
            "body_truncated": False,
            "body_disconnected": False,
            "secrets_masked": 0,
        }
    ).encode()
    record = json.dumps(
        {
            "schema_version": 1,
            "request_id": request_id,
            "endpoint": endpoint,
            "status_code": 200,
        }
    ).encode()
    store.write_artifact(
        session_id=session.session_id,
        request_id=request_id,
        capture=capture,
        record=record,
    )
    return session.session_id


def test_inspect_and_decode_roundtrip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _enable(monkeypatch, tmp_path)
    from slaif_gateway.services.request_capture import build_capture_facility

    store = build_capture_facility(get_settings())
    assert store is not None
    _publish_artifact(store, "/v1/responses", "gw-test-1")

    result = _invoke(["inspect", "--request-id", "gw-test-1"])
    assert result.exit_code == 0, result.output
    payload = _stdout_json(result)
    assert payload["capture"]["body_complete"] is True
    assert base64.b64decode(payload["capture"]["body"]) == b'{"input":"synthetic-complete-body"}'
    assert payload["record"]["endpoint"] == "/v1/responses"

    result = _invoke(["inspect", "--request-id", "gw-test-1", "--decode"])
    assert result.exit_code == 0, result.output
    decoded = _stdout_json(result)["capture"]
    # --decode retains the original base64 alongside the decoded text view.
    assert decoded["body"]["text"] == '{"input":"synthetic-complete-body"}'
    assert (
        base64.b64decode(decoded["body"]["base64"])
        == b'{"input":"synthetic-complete-body"}'
    )

    assert len(list(root.glob("captures/*/*.record.json"))) == 1


def test_inspect_missing_and_malformed_request_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _enable(monkeypatch, tmp_path)
    result = _invoke(["inspect", "--request-id", "gw-missing"])
    assert result.exit_code == 1
    assert "no capture artifact found" in _stdout_json(result)["error"]["message"]

    result = _invoke(["inspect", "--request-id", "../escape"])
    assert result.exit_code == 1
    assert "invalid form" in _stdout_json(result)["error"]["message"]


def test_cleanup_releases_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _enable(monkeypatch, tmp_path)
    from slaif_gateway.services.request_capture import build_capture_facility

    store = build_capture_facility(get_settings())
    assert store is not None
    session_id = _publish_artifact(store, "/v1/responses", "gw-test-2")
    assert store.storage_reserved() > 0

    result = _invoke(["cleanup", "--session-id", session_id])
    assert result.exit_code == 0, result.output
    assert _stdout_json(result)["artifacts_removed"] == 2
    assert store.storage_reserved() == 0
    assert not (root / "captures" / session_id).exists()


def test_unexpected_failure_uses_fixed_generic_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _enable(monkeypatch, tmp_path)
    canary = "PRIVATE-UNEXPECTED-ERROR-CANARY-9f31c2"

    def boom() -> CaptureStore:
        raise RuntimeError(canary)

    import slaif_gateway.cli.request_capture as cli_capture

    monkeypatch.setattr(cli_capture, "build_capture_facility", boom)
    result = _invoke(["status"])
    assert result.exit_code == 1
    payload = _stdout_json(result)
    assert payload == {"error": {"code": "command_failed", "message": "Command failed"}}
    assert canary not in result.output
    assert canary not in (result.stderr or "")


def test_known_store_error_keeps_fixed_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _enable(monkeypatch, tmp_path)
    from slaif_gateway.services.request_capture import build_capture_facility

    store = build_capture_facility(get_settings())
    assert store is not None
    store.arm(endpoint="/v1/responses", count=1)

    result = _invoke(["arm", "--endpoint", "no-slash"])
    assert result.exit_code == 1
    payload = _stdout_json(result)
    assert payload["error"]["message"] == "capture_endpoint_invalid"
