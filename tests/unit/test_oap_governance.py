from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
OAP_ROOT = REPO_ROOT / "oap"
ORDERS_DIR = OAP_ROOT / "orders"
ACTIVE_FILE = OAP_ROOT / "active"
AGENTS_FILE = REPO_ROOT / "AGENTS.md"
PROTOCOL_FILE = REPO_ROOT / "OAP-COMMUNICATION-coding-agent.md"
_ACTIVE_IDENTIFIER_RE = re.compile(rb"(?:[0-9]{3}-[a-z]|155-aa|155-ab|155-ac|155-ad|155-ae|155-af|155-ag|155-ah|155-ai|155-aj|155-ak)\n?")


def _active_identifier() -> str:
    payload = ACTIVE_FILE.read_bytes()
    assert _ACTIVE_IDENTIFIER_RE.fullmatch(payload)
    return payload.decode("ascii").removesuffix("\n")


@pytest.mark.parametrize(
    ("payload", "accepted"),
    [
        (b"001-a\n", True),
        (b"155-aa\n", True),
        (b"155-ab\n", True),
        (b"155-ac\n", True),
        (b"155-ad\n", True),
        (b"155-ae\n", True),
        (b"155-af\n", True),
        (b"155-ag\n", True),
        (b"155-ah\n", True),
        (b"155-ai\n", True),
        (b"155-aj\n", True),
        (b"155-ak\n", True),
        (b"156-aa\n", False),
        (b"155-abc\n", False),
        (b"155-ac-extra\n", False),
        (b"155-ad-extra\n", False),
        (b"155-ae-extra\n", False),
        (b"155-ae-\n", False),
        (b"155-af-extra\n", False),
        (b"155-ag-extra\n", False),
        (b"155-ah-extra\n", False),
        (b"155-aj-extra\n", False),
        (b"155-al\n", False),
    ],
)
def test_active_identifier_has_only_the_explicit_multiletter_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: bytes,
    accepted: bool,
) -> None:
    active = tmp_path / "active"
    active.write_bytes(payload)
    monkeypatch.setattr(sys.modules[__name__], "ACTIVE_FILE", active)
    if accepted:
                assert _active_identifier() in {"001-a", "155-aa", "155-ab", "155-ac", "155-ad", "155-ae", "155-af", "155-ag", "155-ah", "155-ai", "155-aj", "155-ak"}
    else:
        with pytest.raises(AssertionError):
            _active_identifier()


def _active_order() -> tuple[str, Path, str]:
    identifier = _active_identifier()
    matches = sorted(ORDERS_DIR.glob(f"{identifier}-*.md"))
    assert len(matches) == 1
    order_path = matches[0]
    return identifier, order_path, order_path.read_text(encoding="utf-8")


def test_required_oap_governance_files_exist() -> None:
    required_files = (
        AGENTS_FILE,
        PROTOCOL_FILE,
        OAP_ROOT / "README.md",
        ACTIVE_FILE,
        ORDERS_DIR / "README.md",
        OAP_ROOT / "reports" / "README.md",
    )

    assert all(path.is_file() for path in required_files)


def test_active_identifier_resolves_exactly_one_matching_order() -> None:
    identifier, order_path, order_text = _active_order()

    assert order_path.name.startswith(f"{identifier}-")
    assert order_text.splitlines()[0] == f"# OAP Work Order — {identifier}"


def test_initial_round_declares_new_pr_and_one_objective_one_pr() -> None:
    identifier, _order_path, order_text = _active_order()

    if identifier.endswith("-a"):
        protocol_text = PROTOCOL_FILE.read_text(encoding="utf-8")
        assert "PR mode: `CREATE_NEW_PR`" in order_text
        assert "`NNN-a` creates exactly one new PR for that numeric objective." in protocol_text


def test_coding_agent_is_never_merge_authority() -> None:
    agents_text = AGENTS_FILE.read_text(encoding="utf-8").lower()
    protocol_text = PROTOCOL_FILE.read_text(encoding="utf-8").lower()

    assert "coding agent never merges" in agents_text
    assert "never merge an oap pull request" in protocol_text
    assert "you must not merge under any circumstances" in protocol_text


def test_fifo_wire_payload_is_exact_ok_without_newline() -> None:
    protocol_text = PROTOCOL_FILE.read_text(encoding="utf-8")

    assert "only valid FIFO payload is exactly two ASCII bytes" in protocol_text
    assert "There is no newline and no metadata." in protocol_text
    assert "printf 'OK' > \"$RESPONSE_FIFO\"" in protocol_text


def test_report_publication_uses_implementation_head_and_self() -> None:
    protocol_text = PROTOCOL_FILE.read_text(encoding="utf-8")

    assert "Implementation head SHA: <literal 40-hex" in protocol_text
    assert "Report publication commit: SELF" in protocol_text
    assert "first parent must equal" in protocol_text


def test_project_local_state_is_ignored() -> None:
    ignore_entries = {
        line.strip()
        for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert ".codex/" in ignore_entries
    assert ".local-provider-catalog/" in ignore_entries


def test_strategic_directories_are_not_repository_transcript_content() -> None:
    for directory_name in ("handover", "workorders"):
        assert not (REPO_ROOT / directory_name).exists()
        assert not (OAP_ROOT / directory_name).exists()
