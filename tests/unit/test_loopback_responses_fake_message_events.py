"""Producer-shape checks for the loopback fake assistant message events.

The task-owned loopback fake is the 228-c loopback upstream.  Its
assistant message lifecycle must carry the standard Responses stream
shape (assistant role, ``in_progress`` on added with empty content,
``completed`` on done with the output_text part) so the pinned native SDK
and the selected Gateway profile both consume it without any gateway
relaxation.

Fake producer evidence only: no network, provider, or database access.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


@pytest.fixture()
def fake_handler(tmp_path, monkeypatch):
    run = tmp_path / "fake-run"
    (run / "run").mkdir(parents=True)
    workspace = run / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("AGENT_RESP_FAKE_RUN", str(run))
    monkeypatch.setenv("AGENT_RESP_FAKE_WORKSPACE", str(workspace))
    prior_umask = os.umask(0o077)
    os.umask(prior_umask)
    for name in list(sys.modules):
        if name.startswith("verify_agent_chat.loopback_responses_fake"):
            del sys.modules[name]
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        module = importlib.import_module(
            "verify_agent_chat.loopback_responses_fake"
        )
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
        # The fake module sets os.umask(0o077) at import time; restore the
        # process umask so later tests are not polluted.
        os.umask(prior_umask)
    return module.Handler


def test_message_added_is_standard_assistant_shape(fake_handler) -> None:
    events, _next_seq, _items = fake_handler._message_events(
        object(), "resp_t", 1, "hi"
    )
    added = events[0]
    assert added["type"] == "response.output_item.added"
    assert added["output_index"] == 0
    item = added["item"]
    assert set(item) == {"type", "id", "status", "role", "content"}
    assert item["type"] == "message"
    assert item["status"] == "in_progress"
    assert item["role"] == "assistant"
    assert item["content"] == []
    assert item["id"].startswith("msg_fake_")


def test_message_done_carries_completed_assistant_text(fake_handler) -> None:
    events, next_seq, items = fake_handler._message_events(
        object(), "resp_t", 1, "hi"
    )
    delta = events[1]
    assert delta["type"] == "response.output_text.delta"
    assert delta["delta"] == "hi"
    done = events[2]
    assert done["type"] == "response.output_item.done"
    assert done["item"]["status"] == "completed"
    assert done["item"]["role"] == "assistant"
    assert done["item"]["content"] == [{"type": "output_text", "text": "hi"}]
    assert next_seq == 4
    assert items == [
        {
            "type": "message",
            "id": done["item"]["id"],
            "role": "assistant",
            "content": [{"type": "output_text", "text": "hi"}],
        }
    ]
