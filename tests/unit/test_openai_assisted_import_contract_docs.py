from __future__ import annotations

from pathlib import Path


def test_openai_assisted_import_contract_stays_reviewed_and_local() -> None:
    content = Path("docs/pricing-catalog.md").read_text(encoding="utf-8")
    normalized = " ".join(content.split())

    assert "## OpenAI Assisted Pricing And Route Proposals" in content
    assert "LLM-generated proposal files are not authoritative" in content
    assert "No silent replacement of production pricing rows" in normalized
    assert "No direct mutation from a web fetch or LLM call" in normalized
    assert "calls OpenAI only when an operator explicitly runs it" in normalized
    assert "`OPENAI_API_KEY` remains reserved for client-side gateway-issued keys" in normalized
