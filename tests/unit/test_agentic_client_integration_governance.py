from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCTRINE = ROOT / "AGENTIC_CLIENT_INTEGRATION.md"


def _agentic_section() -> str:
    source = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    start = source.index("### Agentic client integrations")
    end = source.find("\n#### ", start)
    if end == -1:
        end = source.find("\n## ", start)
    return source[start : end if end != -1 else len(source)]


def test_agentic_client_contract_is_explicitly_adopted() -> None:
    assert DOCTRINE.is_file()
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "AGENTIC_CLIENT_INTEGRATION.md" in agents
    section = _agentic_section()
    for marker in (
        "authoritative",
        "Client modules are pure, static, non-authoritative",
        "must remain version-owned and default-false",
        "natural\ntwo-turn fake conformance",
        "Temporary production diagnostic hooks must be removed before acceptance",
    ):
        assert marker in section


def test_agentic_client_contract_links_resolve() -> None:
    expected = "../AGENTIC_CLIENT_INTEGRATION.md"
    for relative in (
        "docs/module-architecture.md",
        "docs/responses-compatibility.md",
        "docs/compatibility-matrix.md",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert expected in source
        assert (ROOT / relative).parent.joinpath(expected).resolve() == DOCTRINE
