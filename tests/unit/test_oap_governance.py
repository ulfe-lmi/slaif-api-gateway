from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OAP_ROOT = REPO_ROOT / "oap"
ORDERS_DIR = OAP_ROOT / "orders"
ACTIVE_FILE = OAP_ROOT / "active"
AGENTS_FILE = REPO_ROOT / "AGENTS.md"
PROTOCOL_FILE = REPO_ROOT / "OAP-COMMUNICATION-coding-agent.md"


# 224-aa: ONE human-authorized exceptional identifier (2026-11-14,
# "Approving whatever you need to finish that work") for the CI repair
# round on objective 224. The exception is EXACTLY the identifier
# `224-aa`: `224-ab` and every other two-letter suffix are NOT
# accepted, and the normal `NNN-a`..`NNN-z` law is otherwise
# unchanged. No general change to future OAP identifiers.
_ACTIVE_IDENTIFIER_RE = re.compile(rb"(?:[0-9]{3}-[a-z]|224-aa)\n?")


def _active_identifier() -> str:
    payload = ACTIVE_FILE.read_bytes()
    assert _ACTIVE_IDENTIFIER_RE.fullmatch(payload)
    return payload.decode("ascii").removesuffix("\n")


def test_active_identifier_shape_law_with_224aa_exception() -> None:
    # Normal single-letter identifiers still pass...
    for ok in (b"000-a", b"013-b\n", b"224-z", b"999-z\n"):
        assert _ACTIVE_IDENTIFIER_RE.fullmatch(ok), ok
    # ...and the ONE human-authorized exception passes (with or
    # without the trailing newline)...
    for ok in (b"224-aa", b"224-aa\n"):
        assert _ACTIVE_IDENTIFIER_RE.fullmatch(ok), ok
    # ...while every other two-letter suffix, malformed number, or
    # extra byte stays refused.
    for bad in (
        b"224-ab", b"224-ab\n", b"224-az", b"225-aa", b"224-aaa",
        b"224-aa\n\n", b"22-aa", b"0224-a", b"224-a1", b"224-",
        b"224-aa ", b"",
    ):
        assert not _ACTIVE_IDENTIFIER_RE.fullmatch(bad), bad


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


_NEW_PR_DECLARATION_RE = re.compile(
    # The root-authored orders vary only in the header punctuation (the
    # 216 order is compact: "PR mode:CREATE_NEW_PR"); the declaration VALUE
    # is what the gate validates, not the whitespace after the colon.
    r"^PR mode: ?(?:CREATE_NEW_PR|`CREATE_NEW_PR`)$",
    re.MULTILINE,
)


def _declares_new_pr_mode(order_text: str) -> bool:
    """Return True only for an explicit standalone new-PR declaration.

    The durable protocol prescribes the declaration value, not the Markdown
    punctuation, so both the plain and the inline-code forms satisfy the
    initial-round gate.
    """
    return _NEW_PR_DECLARATION_RE.search(order_text) is not None


def test_initial_round_declares_new_pr_and_one_objective_one_pr() -> None:
    identifier, _order_path, order_text = _active_order()

    if identifier.endswith("-a"):
        protocol_text = PROTOCOL_FILE.read_text(encoding="utf-8")
        assert _declares_new_pr_mode(order_text)
        assert "`NNN-a` creates exactly one new PR for that numeric objective." in protocol_text


def test_new_pr_declaration_accepts_both_forms_and_rejects_informal_text() -> None:
    # Both explicit standalone declarations satisfy the initial-round gate.
    assert _declares_new_pr_mode(
        """Base: main at 0123456789abcdef0123456789abcdef01234567
PR mode: CREATE_NEW_PR
Branch: oap/185-lazy-throttling
"""
    )
    # The compact root-order punctuation (no space after the colon) is the
    # same explicit declaration.
    assert _declares_new_pr_mode(
        """Identifier:216-a
Numeric objective:216
PR mode:CREATE_NEW_PR
"""
    )
    assert _declares_new_pr_mode(
        """PR mode: `CREATE_NEW_PR`
"""
    )
    # Absent, amended, unknown, merely quoted prose, and malformed
    # declarations do not satisfy the gate.
    assert not _declares_new_pr_mode(
        """Base: main at 0123456789abcdef0123456789abcdef01234567
Branch: oap/185-lazy-throttling
"""
    )
    assert not _declares_new_pr_mode(
        """PR mode: AMEND_EXISTING_PR
"""
    )
    assert not _declares_new_pr_mode(
        """PR mode: UNKNOWN_MODE
"""
    )
    assert not _declares_new_pr_mode(
        'The header should declare "PR mode: CREATE_NEW_PR" per protocol.\n'
    )
    assert not _declares_new_pr_mode(
        """PR mode: CREATE_NEW_PR extra
"""
    )
    assert not _declares_new_pr_mode(
        """X PR mode: CREATE_NEW_PR
"""
    )
    assert not _declares_new_pr_mode(
        """PR-mode: CREATE_NEW_PR
"""
    )


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
