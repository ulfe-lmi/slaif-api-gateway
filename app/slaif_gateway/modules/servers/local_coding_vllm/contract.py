"""Explicit static-bearer contract for native vLLM Responses."""

from collections.abc import Mapping
from dataclasses import replace

from slaif_gateway.modules.servers.local_coding.contract import (
    LOCAL_CODING_SERVER_MODULE_ID,
    LocalCodingRouteContract,
    parse_local_coding_route_contract,
)

VLLM_SERVER_MODULE_ID = "local-coding-vLLM"
VLLM_ROUTE_CAPABILITY_KEY = "local_coding_vllm"


def parse_vllm_route_contract(
    capabilities: Mapping[str, object] | None,
) -> LocalCodingRouteContract | None:
    if not isinstance(capabilities, Mapping) or VLLM_ROUTE_CAPABILITY_KEY not in capabilities:
        return None
    if "local_coding" in capabilities:
        raise ValueError("Native vLLM and Local Coding contracts are mutually exclusive")
    raw = capabilities[VLLM_ROUTE_CAPABILITY_KEY]
    if not isinstance(raw, Mapping) or raw.get("contract_version") != VLLM_SERVER_MODULE_ID:
        raise ValueError("Native vLLM contract version is unsupported")
    if raw.get("identity_mode") != "static":
        raise ValueError("Native vLLM requires static bearer authentication")
    legacy = dict(raw, contract_version=LOCAL_CODING_SERVER_MODULE_ID)
    contract = parse_local_coding_route_contract({"local_coding": legacy})
    assert contract is not None
    return replace(contract, contract_version=VLLM_SERVER_MODULE_ID)
