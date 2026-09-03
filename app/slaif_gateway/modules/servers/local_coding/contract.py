"""Pure, strict Local Coding route contract parsing."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

LOCAL_CODING_SERVER_MODULE_ID = "local-coding-v1"
LOCAL_CODING_SERVER_MODULE_VERSION = "1"
LOCAL_CODING_ROUTE_CAPABILITY_KEY = "local_coding"
LOCAL_CODING_TOOL_POLICY_VERSION = "responses-tool-policy-v1"
_SAFE_ROUTE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_LOCAL_V1_SIGNED_ROUTE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,255}$")
_ALLOWED_FIELDS = frozenset(
    {
        "contract_version",
        "route_name",
        "tool_policy_version",
        "identity_mode",
        "replay_mode",
        "deployment_mode",
        "max_body_bytes",
        "clock_skew_seconds",
        "replay_ttl_seconds",
        "nonce_min_length",
        "nonce_max_length",
    }
)
_REQUIRED_FIELDS = frozenset(
    {
        "contract_version",
        "route_name",
        "tool_policy_version",
        "identity_mode",
        "replay_mode",
        "deployment_mode",
    }
)


@dataclass(frozen=True, slots=True)
class LocalCodingRouteContract:
    contract_version: str
    route_name: str
    tool_policy_version: str
    identity_mode: str
    replay_mode: str
    deployment_mode: str
    max_body_bytes: int = 67_108_864
    clock_skew_seconds: int = 60
    replay_ttl_seconds: int = 120
    nonce_min_length: int = 16
    nonce_max_length: int = 128


def parse_local_coding_route_contract(
    capabilities: Mapping[str, object] | None,
) -> LocalCodingRouteContract | None:
    """Return the exact contract or ``None`` when the route is not Local Coding."""
    if not isinstance(capabilities, Mapping) or LOCAL_CODING_ROUTE_CAPABILITY_KEY not in capabilities:
        return None
    raw = capabilities.get(LOCAL_CODING_ROUTE_CAPABILITY_KEY)
    if (
        not isinstance(raw, Mapping)
        or not _REQUIRED_FIELDS.issubset(raw)
        or not set(raw).issubset(_ALLOWED_FIELDS)
    ):
        raise ValueError("Local Coding route contract is incomplete or contains unknown fields")
    if raw.get("contract_version") != LOCAL_CODING_SERVER_MODULE_ID:
        raise ValueError("Local Coding route contract version is unsupported")
    if raw.get("tool_policy_version") != LOCAL_CODING_TOOL_POLICY_VERSION:
        raise ValueError("Local Coding tool policy version is unsupported")
    route_name = raw.get("route_name")
    if not isinstance(route_name, str) or not _SAFE_ROUTE_NAME.fullmatch(route_name):
        raise ValueError("Local Coding route name is invalid")
    identity_mode = raw.get("identity_mode")
    if identity_mode not in {"static", "signed_identity_v1"}:
        raise ValueError("Local Coding identity mode is unsupported")
    if identity_mode == "signed_identity_v1" and _LOCAL_V1_SIGNED_ROUTE_NAME.fullmatch(route_name) is None:
        raise ValueError("Local Coding signed route name is invalid")
    if raw.get("replay_mode") != "process_local_ttl_lru":
        raise ValueError("Local Coding replay mode is unsupported")
    if raw.get("deployment_mode") != "single_worker":
        raise ValueError("Local Coding deployment mode is unsupported")

    values: dict[str, int] = {}
    bounds = {
        "max_body_bytes": (1, 268_435_456),
        "clock_skew_seconds": (1, 300),
        "replay_ttl_seconds": (1, 86_400),
        "nonce_min_length": (1, 128),
        "nonce_max_length": (1, 256),
    }
    for field, (minimum, maximum) in bounds.items():
        value = raw.get(field, LocalCodingRouteContract.__dataclass_fields__[field].default)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"Local Coding {field} is invalid")
        values[field] = value
    if values["replay_ttl_seconds"] < values["clock_skew_seconds"]:
        raise ValueError("Local Coding replay TTL must cover clock skew")
    if values["nonce_min_length"] > values["nonce_max_length"]:
        raise ValueError("Local Coding nonce bounds are invalid")
    return LocalCodingRouteContract(
        contract_version=LOCAL_CODING_SERVER_MODULE_ID,
        route_name=route_name,
        tool_policy_version=LOCAL_CODING_TOOL_POLICY_VERSION,
        identity_mode=identity_mode,
        replay_mode="process_local_ttl_lru",
        deployment_mode="single_worker",
        **values,
    )
