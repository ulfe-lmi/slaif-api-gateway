from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README_FILE = REPO_ROOT / "README.md"
PRODUCT_SCOPE_FILE = REPO_ROOT / "docs" / "product-scope.md"
def test_product_scope_exists_and_readme_preserves_brand_and_link() -> None:
    assert PRODUCT_SCOPE_FILE.is_file()

    readme = README_FILE.read_text(encoding="utf-8")
    assert readme.startswith('<div align="center">')
    assert 'href="https://www.slaif.si"' in readme
    assert 'src="https://slaif.si/img/logos/SLAIF_logo_ANG_barve.svg"' in readme
    assert 'alt="SLAIF"' in readme
    assert "docs/product-scope.md" in readme


def test_readme_and_scope_define_organizational_control_and_deployment_boundary() -> None:
    readme = README_FILE.read_text(encoding="utf-8").casefold()
    product_scope = PRODUCT_SCOPE_FILE.read_text(encoding="utf-8").casefold()

    for content in (readme, product_scope):
        assert "organizational ai access control plane" in content
        assert "one organization per deployment" in content
        assert "sme" in content or "institution" in content


def test_scope_defines_five_profiles_without_claiming_one_click_modes() -> None:
    product_scope = PRODUCT_SCOPE_FILE.read_text(encoding="utf-8")
    normalized_scope = " ".join(product_scope.replace("**", "").split())

    for profile in (
        "Workshop",
        "Organization",
        "Research",
        "Agent/Codex",
        "Trusted Evaluation",
    ):
        assert profile in product_scope

    assert "not five fully implemented one-click modes" in normalized_scope
    assert "separate tenants, or new RBAC roles" in product_scope


def test_scope_preserves_quota_tool_and_readiness_boundaries() -> None:
    product_scope = PRODUCT_SCOPE_FILE.read_text(encoding="utf-8")
    lowered = product_scope.casefold()
    normalized_scope = " ".join(product_scope.split())

    assert "PostgreSQL is authoritative for hard per-key quota/accounting state." in product_scope
    assert "Following requests are blocked once finalized counters exceed key limits." in normalized_scope
    assert "sole implemented opt-in is OpenAI Responses canonical `web_search`" in product_scope
    assert "Every key can prohibit external tools through the default `strict_bounded`" in (
        normalized_scope
    )
    assert "every other hosted family remain denied" in lowered

    for forbidden_positive_claim in (
        "slaif is enterprise-ready",
        "slaif is production-certified",
        "slaif has a compliance attestation",
        "slaif provides invoice-grade accounting",
    ):
        assert forbidden_positive_claim not in lowered

    for explicit_boundary in (
        "not enterprise-ready",
        "not production-certified",
        "no compliance attestation",
        "does not provide invoice-grade accounting",
    ):
        assert explicit_boundary in lowered
