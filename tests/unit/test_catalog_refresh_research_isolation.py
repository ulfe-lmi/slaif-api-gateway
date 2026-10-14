"""183-a focused bounds/config/refusal tests for the research execution
adapter (parent side only: no Docker daemon, no network). The real
enforced-boundary behavior is qualified by
tests/integration/test_catalog_refresh_research_codex.py."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from slaif_gateway.services.catalog_refresh import research_isolation as iso


# --- parent-side pure checks ---------------------------------------------------


def test_verify_cli_binary_shapes(tmp_path: Path) -> None:
    with pytest.raises(iso._BoundaryUnavailable) as excinfo:
        iso.verify_cli_binary(str(tmp_path / "absent"))
    assert excinfo.value.code == "cli_unavailable"

    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    with pytest.raises(iso._BoundaryUnavailable) as excinfo:
        iso.verify_cli_binary(str(empty))
    assert excinfo.value.code == "cli_unbounded"

    real = tmp_path / "codex"
    real.write_bytes(b"\x7fELF-fake-bytes")
    assert iso.verify_cli_binary(str(real)) == hashlib.sha256(b"\x7fELF-fake-bytes").hexdigest()


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://api.example.test", ("api.example.test", 443)),
        ("https://api.example.test:8443/v1", ("api.example.test", 8443)),
        ("http://synthetic.test:9911/v1", ("synthetic.test", 9911)),
        ("http://synthetic.test", ("synthetic.test", 80)),
    ],
)
def test_upstream_target_from_url(url: str, expected: tuple[str, int]) -> None:
    assert iso._upstream_target_from_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "api.example.test",  # no scheme
        "https://",  # empty host
        "https://[::1]",  # bracketed host
        "https://x:99999",  # port out of range
        "https://x :1",  # whitespace
    ],
)
def test_upstream_target_from_url_refuses_malformed(url: str) -> None:
    with pytest.raises(ValueError):
        iso._upstream_target_from_url(url)


def test_write_relay_assets_mock_mode(tmp_path: Path) -> None:
    assets, log_dir = iso.write_relay_assets(
        tmp_path,
        model="syn-model",
        mode="mock",
        canned_result_json='{"schema":"slaif-research-output/1","task":"openrouter_models_api","models":[]}',
        tool_sequence_sse=b"block-a@@SLAIF_MOCK_TURN@@block-b",
        body_markers={"evidence_read": "synthetic-marker-183"},
    )
    assert (assets / "relay.py").stat().st_mode & 0o777 == 0o500
    assert (assets / "canned.sse").stat().st_mode & 0o777 == 0o400
    assert (assets / "tool-sequence.sse").stat().st_mode & 0o777 == 0o400
    markers = json.loads((assets / "body-markers.json").read_text())
    assert markers == {"evidence_read": "synthetic-marker-183"}
    assert (assets / "body-markers.json").stat().st_mode & 0o777 == 0o400
    assert log_dir.is_dir()
    # the mock assets never carry a credential
    assert not (assets / "upstream-key").exists()


def test_write_relay_assets_forward_mode_keeps_key_private(tmp_path: Path) -> None:
    assets, _log_dir = iso.write_relay_assets(
        tmp_path,
        model="syn-model",
        mode="forward",
        canned_result_json=None,
        upstream_key="synthetic-operator-key",
    )
    key_file = assets / "upstream-key"
    assert key_file.read_text() == "synthetic-operator-key"
    assert key_file.stat().st_mode & 0o777 == 0o400
    assert not (assets / "canned.sse").exists()


def test_env_allowlists_are_exact() -> None:
    base = frozenset({"PATH", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256"})
    assert iso._IMAGE_ENV_NAMES == base
    assert iso._RESEARCHER_ENV_ALLOW == base | {
        "HOME", "CODEX_HOME", "LANG", "PYTHONUNBUFFERED", "SLAIF_RESEARCH_API_KEY",
    }
    assert iso._PROBE_ENV_ALLOW == base
    assert {
        "SLAIF_RELAY_TASK_KEY", "SLAIF_RELAY_MODEL", "SLAIF_RELAY_MODE",
        "SLAIF_RELAY_LOG", "SLAIF_RELAY_CANNED_SSE", "SLAIF_RELAY_UPSTREAM_BASE",
        "SLAIF_RELAY_UPSTREAM_KEY_FILE", "SLAIF_RELAY_ALLOW_HTTP",
        "SLAIF_RELAY_TOOL_SEQUENCE", "SLAIF_RELAY_MARKERS_FILE",
    } <= iso._RELAY_ENV_ALLOW


# --- execute_task refusal paths (Docker control plane stand-in) -----------------


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


def _cli(tmp_path: Path) -> str:
    cli = tmp_path / "codex"
    cli.write_bytes(b"\x7fELF-fake-bytes")
    return str(cli)


def test_execute_task_refuses_without_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(iso.shutil, "which", lambda _name: None)
    outcome = iso.execute_task(_ws(tmp_path), task_name="t", models_json="[]",
                               evidence_path=tmp_path / "e.json", agent_md=tmp_path / "a.md",
                               output_schema=tmp_path / "s.json", cli_bin=_cli(tmp_path),
                               cli_sha256="0" * 64, model_name="m", mode="mock")
    assert outcome.status == "unavailable"
    assert outcome.failure_code == "docker_cli_missing"
    assert outcome.cleanup_errors == ()


def test_execute_task_refuses_daemon_down(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(iso.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(iso, "_docker_ok", lambda *a, **k: False)
    outcome = iso.execute_task(_ws(tmp_path), task_name="t", models_json="[]",
                               evidence_path=tmp_path / "e.json", agent_md=tmp_path / "a.md",
                               output_schema=tmp_path / "s.json", cli_bin=_cli(tmp_path),
                               cli_sha256="0" * 64, model_name="m", mode="mock")
    assert outcome.failure_code == "docker_daemon_unavailable"


def test_execute_task_refuses_cli_sha_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(iso.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(iso, "_docker_ok", lambda *a, **k: True)
    outcome = iso.execute_task(_ws(tmp_path), task_name="t", models_json="[]",
                               evidence_path=tmp_path / "e.json", agent_md=tmp_path / "a.md",
                               output_schema=tmp_path / "s.json", cli_bin=_cli(tmp_path),
                               cli_sha256="f" * 64,  # wrong identity
                               model_name="m", mode="mock")
    assert outcome.failure_code == "cli_sha256_mismatch"


def test_execute_task_refuses_workspace_in_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(iso.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(iso, "_docker_ok", lambda *a, **k: True)
    cli = _cli(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    ws = repo / "ws"
    ws.mkdir()
    outcome = iso.execute_task(ws, task_name="t", models_json="[]",
                               evidence_path=tmp_path / "e.json", agent_md=tmp_path / "a.md",
                               output_schema=tmp_path / "s.json", cli_bin=cli,
                               cli_sha256=hashlib.sha256(b"\x7fELF-fake-bytes").hexdigest(),
                               model_name="m", mode="mock", repo_root=repo)
    assert outcome.failure_code == "workspace_in_repo"


def test_execute_task_refuses_http_upstream_without_explicit_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(iso.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(iso, "_docker_ok", lambda *a, **k: True)
    cli = _cli(tmp_path)
    outcome = iso.execute_task(_ws(tmp_path), task_name="t", models_json="[]",
                               evidence_path=tmp_path / "e.json", agent_md=tmp_path / "a.md",
                               output_schema=tmp_path / "s.json", cli_bin=cli,
                               cli_sha256=hashlib.sha256(b"\x7fELF-fake-bytes").hexdigest(),
                               model_name="m", mode="forward",
                               upstream_base="http://synthetic.test:9911/v1",
                               upstream_key="synthetic-operator-key")
    assert outcome.failure_code == "upstream_scheme_unverified"
