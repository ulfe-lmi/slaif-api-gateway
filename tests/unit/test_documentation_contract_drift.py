import re
from pathlib import Path

from fastapi.routing import APIRoute

from slaif_gateway.api.openai_compat import router
from slaif_gateway.services.key_policy_validation import IMPLEMENTED_CLIENT_ENDPOINTS
from slaif_gateway.services.responses_route_capabilities import KNOWN_RESPONSES_CAPABILITIES


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_MATRIX = REPO_ROOT / "docs" / "compatibility-matrix.md"
RESPONSES_COMPATIBILITY = REPO_ROOT / "docs" / "responses-compatibility.md"
RC2_FEATURE_SCOPE = REPO_ROOT / "docs" / "rc2-feature-scope.md"
REPORT_HEAD = "24431512a993df81f15de4e0268c40ad61e0ad57"
MERGE_COMMIT = "adaefdc45ddd13e172955c14e02cb6c97d49b629"


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _actual_v1_routes() -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in router.routes
        if isinstance(route, APIRoute) and route.path.startswith("/v1/")
        for method in route.methods
    }


def _registry_route(endpoint: str) -> tuple[str | None, str]:
    method, separator, path = endpoint.partition(" ")
    if separator and path.startswith("/v1/"):
        return method, path
    return None, endpoint


def _unique_table_row(content: str, label: str) -> str:
    prefix = f"| {label} |"
    matches = [line for line in content.splitlines() if line.startswith(prefix)]
    assert len(matches) == 1, f"expected one table row for {label!r}, found {len(matches)}"
    return matches[0]


def test_endpoint_registry_and_openai_compat_router_match_both_ways() -> None:
    actual_routes = _actual_v1_routes()

    for method, path in actual_routes:
        assert path in IMPLEMENTED_CLIENT_ENDPOINTS or (
            f"{method} {path}" in IMPLEMENTED_CLIENT_ENDPOINTS
        )

    for endpoint in IMPLEMENTED_CLIENT_ENDPOINTS:
        method, path = _registry_route(endpoint)
        if method is None:
            assert any(actual_path == path for _, actual_path in actual_routes)
        else:
            assert (method, path) in actual_routes

    assert "/v1/conversations" in IMPLEMENTED_CLIENT_ENDPOINTS
    assert "POST /v1/conversations" in IMPLEMENTED_CLIENT_ENDPOINTS
    assert ("POST", "/v1/conversations") in actual_routes


def test_endpoint_registry_is_named_in_current_endpoint_contracts() -> None:
    current_endpoint_contracts = "\n".join(
        (
            COMPATIBILITY_MATRIX.read_text(encoding="utf-8"),
            RESPONSES_COMPATIBILITY.read_text(encoding="utf-8"),
        )
    )

    for endpoint in IMPLEMENTED_CLIENT_ENDPOINTS:
        assert endpoint in current_endpoint_contracts


def test_responses_capability_vocabulary_is_named_in_its_contract() -> None:
    responses_contract = RESPONSES_COMPATIBILITY.read_text(encoding="utf-8")

    for capability in KNOWN_RESPONSES_CAPABILITIES:
        assert re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(capability)}(?![A-Za-z0-9_])",
            responses_contract,
        ), capability


def test_rc2_contract_marks_selected_current_endpoint_surfaces_implemented() -> None:
    rc2_contract = RC2_FEATURE_SCOPE.read_text(encoding="utf-8")
    implemented_rows = (
        "Responses streaming live-burn",
        "Conversations create/retrieve/update/delete",
        "Conversation items create/list/retrieve/delete",
        "`POST /v1/audio/speech`",
        "`POST /v1/audio/transcriptions`",
        "`POST /v1/audio/translations`",
        "`POST /v1/embeddings`",
        "Realtime audio",
    )

    rows = {label: _unique_table_row(rc2_contract, label) for label in implemented_rows}
    for label, row in rows.items():
        assert "`RC2_REQUIRED_IMPLEMENTED`" in row, label

    realtime_row = rows["Realtime audio"]
    assert "bounded WebRTC client-secret admission foundation" in realtime_row
    assert "`POST /v1/realtime/client_secrets`" in realtime_row


def test_key_templates_status_comes_from_compatibility_matrix() -> None:
    compatibility_contract = COMPATIBILITY_MATRIX.read_text(encoding="utf-8")
    key_templates_row = _unique_table_row(compatibility_contract, "Key templates")

    assert "Implemented for calibration-derived snapshots and single-key creation" in (
        key_templates_row
    )


def test_current_facing_docs_remove_only_the_stale_embeddings_sentence() -> None:
    stale_sentence = "Embeddings API is not implemented"

    for relative_path in (
        "docs/rc-beta.md",
        "docs/beta-readiness.md",
        "docs/security-model.md",
    ):
        assert stale_sentence not in _read(relative_path)

    assert stale_sentence in _read("docs/releases/v0.1.0-rc.1.md")


def test_objective_001_preserves_failure_and_later_github_outcome() -> None:
    evidence_paths = (
        "AGENTS.md",
        "docs/rc-beta.md",
        "docs/releases/README.md",
        "docs/verification/2026-08-17-current-main-baseline.md",
    )

    for relative_path in evidence_paths:
        evidence = _read(relative_path)
        assert "RESULT=FAIL" in evidence
        assert "PR #226" in evidence
        assert REPORT_HEAD in evidence
        assert "all ten" in evidence.casefold()
        assert MERGE_COMMIT in evidence


def test_live_burn_staged_acceptance_sections_are_explicitly_historical() -> None:
    live_burn_contract = _read("docs/streaming-live-burn-margin.md")

    assert "## Historical staged implementation acceptance record" in live_burn_contract
    assert "## 17. Historical documentation-only phase acceptance record" in live_burn_contract
    assert "## 18. Historical Chat Completions implementation acceptance record" in (
        live_burn_contract
    )
    assert "## 19. Historical bounded Responses implementation acceptance record" in (
        live_burn_contract
    )
