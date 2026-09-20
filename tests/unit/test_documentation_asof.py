"""Unit tests for the readiness-record as-of marker contract.

Covers the machine-auditable evidence boundary introduced in Objective 165:
non-archive documents claiming `current verification/readiness` authority, and
`docs/beta-readiness.md` itself, must carry exactly one valid
`<!-- readiness-record-as-of: <40-hex-sha> -->` marker whose SHA is bound to
the document prose.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_documentation.py"

_SPEC = importlib.util.spec_from_file_location("check_documentation", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_CHECKER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CHECKER)

PINNED_SHA = "8f2813bf745b90221da33a7cfaf40726c5b1b480"
OTHER_SHA = "a" * 40
CLAIM = "current verification/readiness"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _doc(title: str, body: str) -> str:
    return f"# {title}\n\n{body}\n"


def _build_tree(root: Path, docs: dict[str, str]) -> None:
    """Build a minimal navigation-consistent tree: root README links every doc."""
    links = "\n".join(f"- [{rel}]({rel})" for rel in sorted(docs))
    _write(root / "README.md", f"# Synthetic Root\n\n{links}\n")
    for rel, text in docs.items():
        _write(root / rel, text)


# --- Synthetic-tree behavior of the as-of rules -----------------------------


def test_claim_phrase_without_marker_fails(tmp_path: Path) -> None:
    _build_tree(tmp_path, {"docs/record.md": _doc("Record", f"This is a {CLAIM} summary.")})
    errors = _CHECKER.check(tmp_path)
    assert any(
        e.startswith("docs/record.md:") and "[asof-R1]" in e and "missing readiness-record-as-of marker" in e
        for e in errors
    ), errors


def test_claim_phrase_with_valid_marker_and_prose_sha_passes(tmp_path: Path) -> None:
    body = (
        f"Evidence pinned to main commit {PINNED_SHA}. "
        f"This is a {CLAIM} record for the named commit.\n"
        f"\n"
        f"<!-- readiness-record-as-of: {PINNED_SHA} -->\n"
    )
    _build_tree(tmp_path, {"docs/record.md": _doc("Record", body)})
    assert _CHECKER.check(tmp_path) == []


def test_two_valid_markers_fail(tmp_path: Path) -> None:
    body = (
        f"Evidence pinned to main commit {PINNED_SHA}. {CLAIM} record.\n"
        f"\n"
        f"<!-- readiness-record-as-of: {PINNED_SHA} -->\n"
        f"\n"
        f"<!-- readiness-record-as-of: {OTHER_SHA} -->\n"
    )
    _build_tree(tmp_path, {"docs/record.md": _doc("Record", body)})
    errors = _CHECKER.check(tmp_path)
    assert any(
        e.startswith("docs/record.md:") and "[asof-R1]" in e and "multiple readiness-record-as-of markers (2)" in e
        for e in errors
    ), errors


def test_marker_payload_not_40_hex_fails(tmp_path: Path) -> None:
    body = (
        f"{CLAIM} record for commit not-a-sha.\n"
        f"\n"
        f"<!-- readiness-record-as-of: not-a-sha -->\n"
    )
    _build_tree(tmp_path, {"docs/record.md": _doc("Record", body)})
    errors = _CHECKER.check(tmp_path)
    assert any(
        e.startswith("docs/record.md:") and "[asof-R1]" in e and "malformed readiness-record-as-of marker payload" in e
        for e in errors
    ), errors
    assert any(
        e.startswith("docs/record.md:") and "[asof-R1]" in e and "missing readiness-record-as-of marker" in e
        for e in errors
    ), errors


def test_marker_sha_absent_from_prose_fails(tmp_path: Path) -> None:
    body = (
        f"{CLAIM} record without naming its evidence boundary.\n"
        f"\n"
        f"<!-- readiness-record-as-of: {PINNED_SHA} -->\n"
    )
    _build_tree(tmp_path, {"docs/record.md": _doc("Record", body)})
    errors = _CHECKER.check(tmp_path)
    assert any(
        e.startswith("docs/record.md:")
        and "[asof-R1]" in e
        and f"readiness-record-as-of SHA {PINNED_SHA} not found in document prose" in e
        for e in errors
    ), errors


def test_archive_file_with_claim_and_no_marker_passes(tmp_path: Path) -> None:
    _build_tree(
        tmp_path,
        {"docs/verification/2026-08-24-audit.md": _doc("Audit", f"{CLAIM} owner row for the audit target.")},
    )
    assert _CHECKER.check(tmp_path) == []


def test_beta_readiness_without_marker_fails_under_r2(tmp_path: Path) -> None:
    _build_tree(
        tmp_path,
        {"docs/beta-readiness.md": _doc("RC-Beta Readiness Report", "Historical readiness evidence for a named commit.")},
    )
    errors = _CHECKER.check(tmp_path)
    assert any(
        e.startswith("docs/beta-readiness.md:")
        and "[asof-R2]" in e
        and "missing readiness-record-as-of marker" in e
        for e in errors
    ), errors


def test_file_without_claim_phrase_and_without_marker_passes(tmp_path: Path) -> None:
    _build_tree(tmp_path, {"docs/record.md": _doc("Record", "A dated record with no current-state claim.")})
    assert _CHECKER.check(tmp_path) == []


# --- Real-repository state at the PR head -----------------------------------


def test_front_door_rules_require_canonical_entry_point_links(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "# Root\n\nSee [QUICKSTART](QUICKSTART.md) only.\n")
    _write(tmp_path / "QUICKSTART.md", "# Quickstart\n\nboot\n")
    _write(tmp_path / "INSTALL.md", "# Install\n\ninstall\n")
    errors = _CHECKER.check(tmp_path)
    assert any("README.md: missing front-door link to INSTALL.md" in e for e in errors), errors

    _write(tmp_path / "docs" / "quickstart.md", "# Stub\n\nnothing here\n")
    errors = _CHECKER.check(tmp_path)
    assert any("docs/quickstart.md: stub missing pointer to ../QUICKSTART.md" in e for e in errors), errors
    assert any("docs/quickstart.md: stub missing pointer to ../INSTALL.md" in e for e in errors), errors
    assert any(
        "docs/quickstart.md: stub missing pointer to first-time-operator-guide.md" in e
        for e in errors
    ), errors


def test_front_door_rules_silent_when_entry_points_absent(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "# Root\n\nSee [docs/record.md](docs/record.md).\n")
    _write(tmp_path / "docs" / "record.md", "# Record\n\ndated record\n")
    assert _CHECKER.check(tmp_path) == []


def test_real_repository_passes_all_structure_and_asof_rules() -> None:
    assert _CHECKER.check() == []


def test_real_beta_readiness_has_single_pinned_marker_bound_to_prose() -> None:
    text = (ROOT / "docs" / "beta-readiness.md").read_text(encoding="utf-8")
    assert _CHECKER.AS_OF_MARKER_RE.findall(text) == [PINNED_SHA]
    # The SHA must occur beyond the machine marker itself (prose binding).
    assert text.count(PINNED_SHA) >= 2


def test_stale_current_authority_phrase_is_absent_from_checked_set() -> None:
    stale = "Current verification/readiness summary for merged code"
    for path in _CHECKER.MARKDOWN_FILES:
        assert stale not in path.read_text(encoding="utf-8"), path
