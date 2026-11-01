"""Strict, operator-owned data profiles for the shared native adapter."""

from __future__ import annotations

import json
import os
import re
import stat
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from slaif_gateway.providers.errors import ProviderConfigurationError

PROFILE_KEY = "completion_service"
MODULE_ID = "configured-completion"
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


def validate_pointer(value: str) -> str:
    if (
        not value.startswith("/")
        or len(value) > 256
        or len(value.split("/")) > 17
        or re.search(r"~(?![01])", value)
    ):
        raise ValueError("Invalid bounded JSON pointer")
    return value


class ImageOutput(BaseModel):
    """One inline image selected from a service response, without URL fetching."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    pointer: str
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    max_decoded_bytes: int = Field(default=16 * 1024 * 1024, gt=0, le=32 * 1024 * 1024)

    @field_validator("pointer")
    @classmethod
    def safe_pointer(cls, value):
        return validate_pointer(value)


class CompletionProfile(BaseModel):
    """Only reviewed transport/mapping primitives, never expressions or imports."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal[1]
    profile_id: str
    public_model: str = Field(min_length=1, max_length=128)
    upstream_model: str = Field(min_length=1, max_length=128)
    module_id: Literal["configured-completion"] = MODULE_ID
    upstream_path: str
    api_key_env_var: str
    auth_header: Literal["X-API-Key", "Authorization"]
    auth_prefix: Literal["", "Bearer "]
    request_mapping: Literal["multipart_image", "responses_image_yaml"]
    response_mapping: Literal["score_status", "responses_json_text", "json_fields"]
    image_media_types: list[Literal["image/png", "image/jpeg", "image/webp", "image/gif"]]
    max_image_data_url_bytes: int = Field(gt=0, le=28 * 1024 * 1024)
    max_yaml_bytes: int = Field(default=262144, gt=0, le=262144)
    max_response_bytes: int = Field(default=2 * 1024 * 1024, gt=0, le=64 * 1024 * 1024)
    text_pointer: str | None = None
    image_output: ImageOutput | None = None
    response_checks: dict[str, str | int | bool] = Field(default_factory=dict)
    response_array_lengths: dict[str, int] = Field(default_factory=dict)
    request_image_output: bool = False
    result_schema_version: str | None = None
    request_error_code: str = "completion_service_request_invalid"
    response_id_prefix: str = Field(default="chatcmpl-service-", pattern=r"^[A-Za-z0-9-]{1,32}$")

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Version must be an integer")
        return value

    @model_validator(mode="after")
    def safe_profile(self) -> CompletionProfile:
        if not _ID.fullmatch(self.profile_id):
            raise ValueError("Invalid profile ID")
        if not re.fullmatch(r"/v1/[a-z][a-z0-9_/-]{0,95}", self.upstream_path):
            raise ValueError("Upstream path must be a fixed API path")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", self.api_key_env_var):
            raise ValueError("Invalid credential reference")
        if self.api_key_env_var == "OPENAI_API_KEY":
            raise ValueError("Client credential cannot be an upstream credential")
        if (self.auth_header == "Authorization") != (self.auth_prefix == "Bearer "):
            raise ValueError("Invalid authentication mapping")
        if not self.image_media_types or len(set(self.image_media_types)) != len(
            self.image_media_types
        ):
            raise ValueError("Invalid image media types")
        if (
            self.request_mapping == "responses_image_yaml"
            and self.response_mapping == "score_status"
        ):
            raise ValueError("Incompatible request/response mappings")
        if self.response_mapping == "responses_json_text" and not self.result_schema_version:
            raise ValueError("JSON projection requires a schema version")
        if self.response_mapping == "json_fields":
            if self.text_pointer is None:
                raise ValueError("Field mapping requires a text pointer")
            validate_pointer(self.text_pointer)
        elif self.text_pointer is not None or self.image_output is not None:
            raise ValueError("Output field selectors require json_fields mapping")
        if self.request_image_output and (
            self.request_mapping != "responses_image_yaml" or self.image_output is None
        ):
            raise ValueError("Responses image request requires an image output mapping")
        for checks in (self.response_checks, self.response_array_lengths):
            if len(checks) > 16:
                raise ValueError("Too many response checks")
            for pointer in checks:
                validate_pointer(pointer)
        if any(type(n) is not int or n < 0 or n > 64 for n in self.response_array_lengths.values()):
            raise ValueError("Invalid response array bound")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", self.request_error_code):
            raise ValueError("Invalid error code")
        return self


def profile_id_from_capabilities(capabilities: object) -> str | None:
    if not isinstance(capabilities, dict) or PROFILE_KEY not in capabilities:
        return None
    value = capabilities[PROFILE_KEY]
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "profile"}
        or type(value.get("version")) is not int
        or value["version"] != 1
        or not isinstance(value.get("profile"), str)
        or not _ID.fullmatch(value["profile"])
    ):
        raise ProviderConfigurationError(error_code="completion_service_profile_invalid")
    return value["profile"]


def contained_child(root: str | Path, filename: str) -> str:
    """A validated single child of the trusted profile root, proven contained.

    ``filename`` must already have passed the profile ID law and been
    re-derived with ``os.path.basename`` (a single name; for a
    whitelisted stem the basename is the identity). Only the TRUSTED
    ROOT is canonicalized: ``os.path.realpath`` on the root resolves
    symlinks in the operator root's own ancestry (the caller already
    enforces the root's absolute/non-symlink law before this). The
    joined candidate is normalized and must remain inside the
    canonical root plus a separator. The final file is NEVER resolved
    or opened through its target: callers keep ``O_NOFOLLOW`` plus
    symlink/mode/size refusal on the last component, so a symlinked
    profile file - inside or outside the root - is refused.
    """
    canonical_root = os.path.realpath(os.fspath(root))
    candidate = os.path.normpath(os.path.join(canonical_root, filename))
    if candidate == canonical_root or not candidate.startswith(canonical_root + os.sep):
        raise ValueError("Profile filename escapes the profile root")
    return candidate


@lru_cache(maxsize=64)
def load_profile(profile_id: str, directory: str = "") -> CompletionProfile:
    """Load one bounded JSON file; route metadata cannot select a file path.

    The ID law rejects every path component BEFORE any I/O; the final
    join re-derives the single root-relative filename with
    ``os.path.basename`` so the by-construction boundary is explicit
    (for a whitelisted ID the basename is the identity), and the join
    is proven to stay inside the canonicalized trusted root
    (``contained_child``). The final file is never resolved: a
    symlinked profile is refused by ``O_NOFOLLOW``.
    """
    try:
        if not _ID.fullmatch(profile_id):
            raise ValueError("Invalid profile ID")
        root = Path(directory) if directory else Path(__file__).parent / "profiles"
        if directory and (not root.is_absolute() or root.is_symlink()):
            raise ValueError("Profile directory must be an absolute operator path")
        path = contained_child(root, os.path.basename(profile_id) + ".json")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_size > 65536
                or (directory and info.st_mode & 0o022)
            ):
                raise ValueError("Unsafe profile file")
            data = source.read(65537)
        profile = CompletionProfile.model_validate(json.loads(data))
        if profile.profile_id != profile_id:
            raise ValueError("Profile identity mismatch")
        return profile
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        raise ProviderConfigurationError(error_code="completion_service_profile_invalid") from exc


class ProfileBindings(BaseModel):
    """Data-only compatibility bindings; new routes normally select a profile explicitly."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal[1]
    default_profile: str
    providers: dict[str, str]

    @model_validator(mode="after")
    def safe_bindings(self):
        if not _ID.fullmatch(self.default_profile) or len(self.providers) > 256:
            raise ValueError("Invalid profile bindings")
        for provider, profile in self.providers.items():
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", provider) or not _ID.fullmatch(
                profile
            ):
                raise ValueError("Invalid profile binding")
        return self


@lru_cache(maxsize=1)
def load_bindings() -> ProfileBindings:
    path = Path(__file__).parent / "profiles" / "bindings.json"
    try:
        if path.stat().st_size > 65536:
            raise ValueError("Bindings exceed size limit")
        return ProfileBindings.model_validate(json.loads(path.read_bytes()))
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        raise ProviderConfigurationError(error_code="completion_service_profile_invalid") from exc


def resolve_profile_id(provider: str, capabilities: object) -> str:
    profile_id = profile_id_from_capabilities(capabilities) or load_bindings().providers.get(
        provider
    )
    if profile_id is None:
        raise ProviderConfigurationError(error_code="unsupported_module")
    return profile_id


def load_default_profile() -> CompletionProfile:
    return load_profile(load_bindings().default_profile)
