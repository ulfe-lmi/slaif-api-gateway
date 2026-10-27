"""Strict, immutable upstream LLM profile snapshots; configuration is data only."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from slaif_gateway.modules.servers.local_coding.contract import parse_local_coding_route_contract
from slaif_gateway.providers.errors import ProviderConfigurationError

MODULE_ID = "configured-upstream-llm"
CAPABILITY_KEY = "upstream_llm"
_MAX_FILE_BYTES = 65536


class LLMProfile(BaseModel):
    """Finite protocol operations, with no expressions, templates, imports or URLs."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    revision: int = Field(ge=1, le=2147483647)
    instruction_placement: Literal["preserve", "leading_system_developer"]
    tool_encoding: Literal["preserve", "native_vllm"]

    @field_validator("revision", mode="before")
    @classmethod
    def integer_revision(cls, value):
        if type(value) is not int:
            raise ValueError("Revision must be an integer")
        return value

    @property
    def sha256(self) -> str:
        data = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _error() -> ProviderConfigurationError:
    return ProviderConfigurationError(error_code="upstream_llm_profile_invalid")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate profile field")
        result[key] = value
    return result


@lru_cache(maxsize=8)
def load_profiles(filename: str = "") -> Mapping[str, LLMProfile]:
    """Read one bounded regular file once; failure never falls back to defaults."""
    try:
        path = Path(filename) if filename else Path(__file__).parent / "profiles" / "defaults.json"
        if filename and (not path.is_absolute() or path.resolve() != path):
            raise ValueError("External profile path must be absolute without symlinks")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_size > _MAX_FILE_BYTES
                or (filename and info.st_mode & 0o022)
            ):
                raise ValueError("Unsafe profile file")
            data = source.read(_MAX_FILE_BYTES + 1)
        if len(data) > _MAX_FILE_BYTES:
            raise ValueError("Profile file exceeds limit")
        document = json.loads(data, object_pairs_hook=_unique_object)
        if (
            not isinstance(document, dict)
            or set(document) != {"schema_version", "profiles"}
            or type(document["schema_version"]) is not int
            or document["schema_version"] != 1
            or not isinstance(document["profiles"], list)
            or not 1 <= len(document["profiles"]) <= 32
        ):
            raise ValueError("Invalid profile document")
        profiles = {}
        for raw in document["profiles"]:
            profile = LLMProfile.model_validate(raw)
            if profile.profile_id in profiles:
                raise ValueError("Duplicate profile identity")
            profiles[profile.profile_id] = profile
        return MappingProxyType(profiles)
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        raise _error() from exc


_active_profiles = load_profiles()


def bootstrap_upstream_llm_profiles(filename: str = "") -> Mapping[str, LLMProfile]:
    """Bind one process snapshot at HTTP/CLI startup, before route selection."""
    global _active_profiles
    snapshot = load_profiles(filename)
    _active_profiles = snapshot
    return snapshot


def resolve_profile(capabilities: object) -> LLMProfile:
    """Route-owned exact identity, never a client-selected filename or behavior."""
    if not isinstance(capabilities, Mapping):
        raise _error()
    selector = capabilities.get(CAPABILITY_KEY)
    if (
        not isinstance(selector, Mapping)
        or set(selector) != {"version", "profile", "revision", "sha256"}
        or type(selector.get("version")) is not int
        or selector["version"] != 1
        or not isinstance(selector.get("profile"), str)
        or type(selector.get("revision")) is not int
        or not isinstance(selector.get("sha256"), str)
    ):
        raise _error()
    profile = _active_profiles.get(selector["profile"])
    if (
        profile is None
        or profile.revision != selector["revision"]
        or profile.sha256 != selector["sha256"]
    ):
        raise _error()
    return profile


def validate_route(capabilities: object) -> LLMProfile:
    """Keep the existing transport contract and reject conflicting selectors."""
    profile = resolve_profile(capabilities)
    if not isinstance(capabilities, Mapping) or any(
        field in capabilities
        for field in ("local_coding_vllm", "vllm_chat_video", "completion_service")
    ):
        raise _error()
    try:
        contract = parse_local_coding_route_contract(capabilities)
        if contract is None or (
            profile.tool_encoding == "native_vllm" and contract.identity_mode != "static"
        ):
            raise ValueError("Profile requires compatible transport")
    except (TypeError, ValueError) as exc:
        raise _error() from exc
    return profile
