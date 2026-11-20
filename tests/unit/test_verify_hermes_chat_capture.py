"""Pure helper regressions for scripts/verify_agent_chat/verify_hermes_chat_capture.py.

These tests exercise the verifier's decision helpers on synthetic
on-disk artifacts only. They do NOT start processes, open network
sockets, invoke clients or providers, or touch databases.
"""

import importlib.util
import json
import os

import pytest

REPO_ROOT = os.path.realpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
VERIFIER_PATH = os.path.join(
    REPO_ROOT, "scripts", "verify_agent_chat",
    "verify_hermes_chat_capture.py")

M0 = "SLAIF227-HERMES-MARK0-abcdef12"
M1 = "SLAIF227-HERMES-MARK1-12345678"
REASON = "SYN-REASONING-227-deadbeef"

PEER_OK = {
    "toolloop_verified": True,
    "all_calls_correlated_with_marker": True,
    "final_text_source": "correlated_tool_result",
    "calls_issued": 2,
    "correlated_calls": 2,
    "title_requests": 0,
    "summary_issued": False,
}
REPLAY_NONE = {"reasoning_requested": False, "replayed_in_journal": False,
               "requests_checked": 0}


@pytest.fixture(scope="module")
def vmod():
    assert os.path.isfile(VERIFIER_PATH)
    spec = importlib.util.spec_from_file_location(
        "vhcc_under_test", VERIFIER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_cli_log(path, *lines):
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def _tool_result_line(text):
    return json.dumps({"type": "assistant",
                       "message": {"role": "tool", "tool_call_id": "c1",
                                   "content": text}})


def _result_line(exit_code, text):
    return json.dumps({"type": "result", "exit_code": exit_code,
                       "text": text})


def _chat_post(body):
    return json.dumps({"method": "POST",
                       "path": "/v1/chat/completions",
                       "body": json.dumps(body)})


# ---------------------------------------------------------------------------
# cli_log_facts: structured terminal result, not "marker anywhere"
# ---------------------------------------------------------------------------


def test_toolloop_marker_in_tool_result_only_does_not_qualify(vmod, tmp_path):
    log = _write_cli_log(tmp_path / "cli.log",
                         _tool_result_line(M0 + " extra"))
    clif = vmod.cli_log_facts(log, "toolloop", [M0, M1], None)
    assert clif["present"] is True
    assert clif["marker_anywhere_in_log"] is True
    assert clif["terminal_result_present"] is False
    assert clif["terminal_exit_code"] is None
    assert clif["terminal_text_exact"] is False
    assert vmod.qualified_for("toolloop", True, 3, False,
                              "native_exit_zero", False, clif, True,
                              PEER_OK, REPLAY_NONE) is False


def test_toolloop_clean_terminal_result_qualifies(vmod, tmp_path):
    log = _write_cli_log(tmp_path / "cli.log",
                         _tool_result_line(M0),
                         _result_line(0, M0))
    clif = vmod.cli_log_facts(log, "toolloop", [M0, M1], None)
    assert clif["terminal_result_present"] is True
    assert clif["terminal_exit_code"] == 0
    assert clif["terminal_text_exact"] is True
    assert clif["stream_json_lines"] >= 2
    assert vmod.qualified_for("toolloop", True, 3, False,
                              "native_exit_zero", False, clif, True,
                              PEER_OK, REPLAY_NONE) is True


def test_toolloop_wrong_terminal_text_does_not_qualify(vmod, tmp_path):
    log = _write_cli_log(tmp_path / "cli.log", _result_line(0, "other text"))
    clif = vmod.cli_log_facts(log, "toolloop", [M0, M1], None)
    assert clif["terminal_result_present"] is True
    assert clif["terminal_text_exact"] is False
    assert vmod.qualified_for("toolloop", True, 3, False,
                              "native_exit_zero", False, clif, True,
                              PEER_OK, REPLAY_NONE) is False


def test_toolloop_never_qualifies_under_outer_watchdog(vmod, tmp_path):
    log = _write_cli_log(tmp_path / "cli.log", _result_line(0, M0))
    clif = vmod.cli_log_facts(log, "toolloop", [M0, M1], None)
    assert clif["terminal_text_exact"] is True
    assert vmod.qualified_for("toolloop", True, 3, False,
                              "outer_watchdog_cancel", False, clif, True,
                              PEER_OK, REPLAY_NONE) is False


def test_text_sentinel_without_terminal_result_does_not_qualify(vmod,
                                                                tmp_path):
    log = _write_cli_log(tmp_path / "cli.log",
                         json.dumps({"type": "assistant",
                                     "text": vmod.TEXT_SENTINEL}))
    clif = vmod.cli_log_facts(log, "text", [], None)
    assert clif["sentinel_present"] is True
    assert clif["terminal_result_present"] is False
    assert vmod.qualified_for("text", True, 1, False, "native_exit_zero",
                              False, clif, True, None, REPLAY_NONE) is False


def test_text_clean_terminal_result_qualifies(vmod, tmp_path):
    log = _write_cli_log(tmp_path / "cli.log",
                         _result_line(0, vmod.TEXT_SENTINEL))
    clif = vmod.cli_log_facts(log, "text", [], None)
    assert clif["terminal_text_exact"] is True
    assert vmod.qualified_for("text", True, 1, False, "native_exit_zero",
                              False, clif, True, None, REPLAY_NONE) is True


def test_toolloop_reasoning_requested_but_not_replayed(vmod, tmp_path):
    log = _write_cli_log(tmp_path / "cli.log", _result_line(0, M0))
    clif = vmod.cli_log_facts(log, "toolloop", [M0, M1], REASON)
    replay = {"reasoning_requested": True, "replayed_in_journal": False,
              "requests_checked": 1}
    assert vmod.qualified_for("toolloop", True, 3, False,
                              "native_exit_zero", False, clif, True,
                              PEER_OK, replay) is False


# ---------------------------------------------------------------------------
# finish(): core cleanup before deletion; qualified requires both
# ---------------------------------------------------------------------------


def _core_cleanup():
    return {"cli_stopped": True, "fake_terminated": True,
            "port_closed": True, "owned_runtime_absent": True}


def _make_run_root(tmp_path):
    run_root = tmp_path / "run"
    (run_root / "hermes-home").mkdir(parents=True)
    return str(run_root)


def test_finish_deletion_failure_yields_unqualified_and_retained_root(
        vmod, tmp_path, monkeypatch):
    run_root = _make_run_root(tmp_path)
    report = str(tmp_path / "report.json")
    result = {"run": "t", "errors": []}
    cleanup = _core_cleanup()

    def boom(path):
        raise OSError("denied")

    monkeypatch.setattr(vmod.shutil, "rmtree", boom)
    with pytest.raises(SystemExit) as exc:
        vmod.finish(result, run_root, report, True, cleanup,
                    "native_exit_zero", False)
    assert exc.value.code == 1
    assert cleanup["run_root_removed"] is False
    assert cleanup["run_root_retained"] is True
    assert cleanup["run_root_retained_reason"] == "remove_failed"
    assert result["qualified"] is False
    assert result["cleanup_verified"] is False
    assert os.path.isdir(run_root)
    assert os.path.isfile(os.path.join(run_root, "result.json"))
    assert os.path.isfile(report)


def test_finish_core_cleanup_failure_retains_root_without_deletion(
        vmod, tmp_path, monkeypatch):
    run_root = _make_run_root(tmp_path)
    report = str(tmp_path / "report.json")
    result = {"run": "t", "errors": []}
    cleanup = _core_cleanup()
    cleanup["owned_runtime_absent"] = False
    calls = []
    monkeypatch.setattr(vmod.shutil, "rmtree",
                        lambda path: calls.append(path))
    with pytest.raises(SystemExit) as exc:
        vmod.finish(result, run_root, report, True, cleanup,
                    "native_exit_zero", False)
    assert exc.value.code == 1
    assert calls == []  # never deleted under unverified live process
    assert cleanup.get("run_root_removed") is None
    assert cleanup["run_root_retained"] is True
    assert cleanup["run_root_retained_reason"] == "core_cleanup_unverified"
    assert result["qualified"] is False
    assert result["cleanup_verified"] is False
    assert os.path.isdir(run_root)
    assert os.path.isfile(os.path.join(run_root, "result.json"))


def test_finish_core_verified_removes_root_and_qualifies(vmod, tmp_path):
    run_root = _make_run_root(tmp_path)
    report = str(tmp_path / "report.json")
    result = {"run": "t", "errors": []}
    cleanup = _core_cleanup()
    with pytest.raises(SystemExit) as exc:
        vmod.finish(result, run_root, report, True, cleanup,
                    "native_exit_zero", False)
    assert exc.value.code == 0
    assert cleanup["run_root_removed"] is True
    assert result["qualified"] is True
    assert result["cleanup_verified"] is True
    assert not os.path.exists(run_root)
    assert os.path.isfile(report)


# ---------------------------------------------------------------------------
# current_run_log_evidence: new files discovered, old prefix excluded
# ---------------------------------------------------------------------------


def _make_home(tmp_path, name):
    home = tmp_path / name
    (home / "logs").mkdir(parents=True)
    return str(home)


def test_new_log_file_with_offsets_empty_is_detected(vmod, tmp_path):
    home = _make_home(tmp_path, "home-a")
    p = os.path.join(home, "logs", "errors.log")
    content = b"benign line\nError code: 500 one\nError code: 500 two\n"
    with open(p, "wb") as f:
        f.write(content)
    ev = vmod.current_run_log_evidence(home, {})
    assert "errors.log" in ev
    assert ev["errors.log"]["appended_bytes"] == len(content)
    assert ev["errors.log"]["event_lines"]["error_500"] == 2


def test_baseline_offset_excludes_old_prefix(vmod, tmp_path):
    home = _make_home(tmp_path, "home-b")
    p = os.path.join(home, "logs", "app.log")
    old = b"line0\nError code: 500 old\n"
    new = b"ReadTimeout hit\n"
    with open(p, "wb") as f:
        f.write(old + new)
    ev = vmod.current_run_log_evidence(home, {"logs/app.log": len(old)})
    assert "app.log" in ev
    assert ev["app.log"]["appended_bytes"] == len(new)
    assert ev["app.log"]["event_lines"]["sdk_timeout_exception"] == 1
    assert ev["app.log"]["event_lines"]["error_500"] == 0


# ---------------------------------------------------------------------------
# reasoning_replay_fact: journal assistant fields, first request never counts
# ---------------------------------------------------------------------------


def _write_journal(run_dir, *posts):
    with open(os.path.join(run_dir, "requests.jsonl"), "w") as f:
        for p in posts:
            f.write(p + "\n")


def test_reasoning_replayed_in_second_request(vmod, tmp_path):
    _write_journal(
        str(tmp_path),
        _chat_post({"model": "m", "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "reasoning": REASON}]}),
        _chat_post({"model": "m", "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "reasoning_content": REASON},
            {"role": "tool", "content": "x"}]}),
    )
    fact = vmod.reasoning_replay_fact(str(tmp_path), REASON)
    assert fact == {"reasoning_requested": True,
                    "replayed_in_journal": True,
                    "requests_checked": 1}


def test_reasoning_replay_absent_is_false(vmod, tmp_path):
    _write_journal(
        str(tmp_path),
        _chat_post({"model": "m", "messages": [
            {"role": "user", "content": "hi"}]}),
        _chat_post({"model": "m", "messages": [
            {"role": "assistant", "reasoning": "other-value"}]}),
    )
    fact = vmod.reasoning_replay_fact(str(tmp_path), REASON)
    assert fact["reasoning_requested"] is True
    assert fact["replayed_in_journal"] is False
    assert fact["requests_checked"] == 1


def test_reasoning_in_first_request_never_counts(vmod, tmp_path):
    _write_journal(
        str(tmp_path),
        _chat_post({"model": "m", "messages": [
            {"role": "assistant", "reasoning": REASON}]}),
    )
    fact = vmod.reasoning_replay_fact(str(tmp_path), REASON)
    assert fact["replayed_in_journal"] is False
    assert fact["requests_checked"] == 0


def test_reasoning_not_requested_is_neutral(vmod, tmp_path):
    fact = vmod.reasoning_replay_fact(str(tmp_path), None)
    assert fact == {"reasoning_requested": False,
                    "replayed_in_journal": False,
                    "requests_checked": 0}
