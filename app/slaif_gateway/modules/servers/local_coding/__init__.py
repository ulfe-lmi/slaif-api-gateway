"""Static Local Coding server-module contract and adapter."""

from slaif_gateway.modules.servers.local_coding.contract import (
    LOCAL_CODING_SERVER_MODULE_ID,
    LOCAL_CODING_SERVER_MODULE_VERSION,
    LocalCodingRouteContract,
    parse_local_coding_route_contract,
)

__all__ = [
    "LOCAL_CODING_SERVER_MODULE_ID",
    "LOCAL_CODING_SERVER_MODULE_VERSION",
    "LocalCodingRouteContract",
    "parse_local_coding_route_contract",
]
