import re
from pathlib import Path

from fastapi.routing import APIRoute

from slaif_gateway.api.openai_compat import router
from slaif_gateway.services.key_policy_validation import IMPLEMENTED_CLIENT_ENDPOINTS
from slaif_gateway.services.external_tool_policy_contract import (
    ABSOLUTE_MAX_APPROVED_DESTINATIONS,
    ABSOLUTE_MAX_DISTINCT_CAPABILITIES,
    ABSOLUTE_MAX_PROVIDER_TOOL_CALLS,
    ABSOLUTE_MAX_PROVIDER_TOOL_DECLARATIONS,
    EXTERNAL_TOOL_FENCED,
    KNOWN_EXTERNAL_CAPABILITIES,
    STRICT_BOUNDED,
)
from slaif_gateway.services.responses_route_capabilities import KNOWN_RESPONSES_CAPABILITIES


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_MATRIX = REPO_ROOT / "docs" / "compatibility-matrix.md"
RESPONSES_COMPATIBILITY = REPO_ROOT / "docs" / "responses-compatibility.md"
RC2_FEATURE_SCOPE = REPO_ROOT / "docs" / "rc2-feature-scope.md"
REPORT_HEAD = "24431512a993df81f15de4e0268c40ad61e0ad57"
MERGE_COMMIT = "adaefdc45ddd13e172955c14e02cb6c97d49b629"
EXTERNAL_TOOL_CONTRACT_DOCS = (
    "AGENTS.md",
    "docs/accounting.md",
    "docs/beta-readiness.md",
    "docs/compatibility-matrix.md",
    "docs/configuration.md",
    "docs/database-schema.md",
    "docs/key-templates.md",
    "docs/openai-compatibility.md",
    "docs/product-scope.md",
    "docs/provider-forwarding-contract.md",
    "docs/rc-beta.md",
    "docs/responses-compatibility.md",
    "docs/security-model.md",
)


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


def test_beta_readiness_separates_historical_status_from_current_future_work() -> None:
    beta_readiness = _read("docs/beta-readiness.md")
    remaining_pre_ga = beta_readiness.split("## Remaining Pre-GA Items", maxsplit=1)[1]

    assert "Historical status (2026-05-01):" in beta_readiness
    assert "for the current implemented scope" not in beta_readiness
    assert "beyond the current implemented RC2 boundary" in remaining_pre_ga
    assert "separately scoped work" in remaining_pre_ga
    assert "Continue Responses API as scoped RC2 work" not in remaining_pre_ga
    assert "historical first RC-beta tag" in beta_readiness


def test_external_tool_contract_docs_use_both_modes_and_preserve_future_status() -> None:
    for relative_path in EXTERNAL_TOOL_CONTRACT_DOCS:
        content = _read(relative_path)
        assert STRICT_BOUNDED in content, relative_path
        assert EXTERNAL_TOOL_FENCED in content, relative_path
        assert re.search(r"deny-only|denies provider-hosted|denied", content, re.IGNORECASE), (
            relative_path
        )

        folded = content.casefold()
        for contradiction in (
            "external_tool_fenced is implemented",
            "external_tool_fenced is active",
            "hard quota means no request can overrun",
            "hard quota guarantees no request can overrun",
        ):
            assert contradiction not in folded, (relative_path, contradiction)


def test_external_tool_schema_and_taxonomy_match_the_pure_contract() -> None:
    schema = _read("docs/database-schema.md")

    for capability in KNOWN_EXTERNAL_CAPABILITIES:
        assert re.search(rf"(?<![A-Za-z0-9_]){re.escape(capability)}(?![A-Za-z0-9_])", schema), (
            capability
        )

    for key_field in (
        '"version": 1',
        '"mode": "strict_bounded"',
        '"allowed_capabilities": []',
        '"allowed_destination_ids": []',
        '"max_provider_tool_calls_per_request": 0',
        '"single_request_overrun_acknowledged": false',
    ):
        assert key_field in schema
    for route_field in (
        '"supported_capabilities": []',
        '"approved_destination_ids": []',
        '"call_limit_enforced": false',
        '"final_usage_required": false',
        '"final_cost_required": false',
    ):
        assert route_field in schema

    assert str(ABSOLUTE_MAX_DISTINCT_CAPABILITIES) in schema
    assert str(ABSOLUTE_MAX_APPROVED_DESTINATIONS) in schema
    assert str(ABSOLUTE_MAX_PROVIDER_TOOL_DECLARATIONS) in schema
    assert str(ABSOLUTE_MAX_PROVIDER_TOOL_CALLS) in schema
    assert "No column, table, constraint, or migration was added" in schema
    assert "gateway_keys.metadata.external_tool_policy" in schema
    assert "model_routes.capabilities.external_tools" in schema


def test_external_tool_fenced_promise_and_official_evidence_are_explicit() -> None:
    exact_fragments = (
        "one admitted provider-hosted external-tool request",
        "reject concurrent requests",
        "reject following requests after exhaustion",
        "blocking accounting hold",
        "missing, ambiguous, interrupted, or awaiting reconciliation",
    )
    for relative_path in (
        "AGENTS.md",
        "docs/accounting.md",
        "docs/product-scope.md",
    ):
        content = _read(relative_path)
        normalized = re.sub(r"\s+", " ", content)
        for fragment in exact_fragments:
            assert fragment in normalized, (relative_path, fragment)

    forwarding = _read("docs/provider-forwarding-contract.md")
    assert "https://developers.openai.com/api/docs/models/gpt-5.6-sol" in forwarding
    assert "https://developers.openai.com/api/docs/guides/tools-connectors-mcp" in forwarding
    assert "require_approval` can never lower" in forwarding


def test_external_tool_contract_is_wired_only_to_policy_surfaces_not_runtime_or_migrations() -> (
    None
):
    module_path = REPO_ROOT / "app/slaif_gateway/services/external_tool_policy_contract.py"
    allowed_consumers = {
        REPO_ROOT / "app/slaif_gateway/config.py",
        REPO_ROOT / "app/slaif_gateway/api/admin.py",
        REPO_ROOT / "app/slaif_gateway/cli/keys.py",
        REPO_ROOT / "app/slaif_gateway/cli/routes.py",
        REPO_ROOT / "app/slaif_gateway/cli/templates.py",
        REPO_ROOT / "app/slaif_gateway/services/admin_key_dashboard.py",
        REPO_ROOT / "app/slaif_gateway/services/auth_service.py",
        REPO_ROOT / "app/slaif_gateway/services/key_import.py",
        REPO_ROOT / "app/slaif_gateway/services/key_service.py",
        REPO_ROOT / "app/slaif_gateway/services/key_template_service.py",
        REPO_ROOT / "app/slaif_gateway/services/model_route_service.py",
        REPO_ROOT / "app/slaif_gateway/services/route_import.py",
    }
    for path in (REPO_ROOT / "app/slaif_gateway").rglob("*.py"):
        if path == module_path or path in allowed_consumers:
            continue
        assert "external_tool_policy_contract" not in path.read_text(encoding="utf-8"), path

    assert "EXTERNAL_TOOL_MAX_PROVIDER_TOOL_CALLS_PER_REQUEST=16" in _read(".env.example")
    assert "EXTERNAL_TOOL_MAX_PROVIDER_TOOL_CALLS_PER_REQUEST: int = 16" in _read(
        "app/slaif_gateway/config.py"
    )
    for path in (REPO_ROOT / "migrations/versions").glob("*.py"):
        assert "external_tool_policy" not in path.read_text(encoding="utf-8"), path


def test_external_tool_authority_docs_are_position_aware_without_granting_acceptance() -> None:
    for relative_path in (
        "AGENTS.md",
        "docs/database-schema.md",
        "docs/provider-forwarding-contract.md",
        "docs/security-model.md",
    ):
        content = _read(relative_path)
        normalized = re.sub(r"\s+", " ", content)
        assert "semantic" in normalized and "control positions" in normalized, relative_path
        assert "function parameters/JSON Schema" in normalized, relative_path
        assert "custom format/grammar" in normalized, relative_path
        assert "namespace" in normalized.casefold(), relative_path
        assert re.search(r"deny-only|grants no|does not make", normalized), relative_path

    forwarding = _read("docs/provider-forwarding-contract.md")
    assert "does not make a request valid or forwardable" in forwarding
