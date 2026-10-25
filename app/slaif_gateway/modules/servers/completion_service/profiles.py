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


class CompletionProfile(BaseModel):
    """Only reviewed transport/mapping primitives, never expressions or imports."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal[1]
    profile_id: str
    public_model: str = Field(min_length=1, max_length=128)
    upstream_model: str = Field(min_length=1, max_length=128)
    module_id: Literal["facial_scoring", "configured-completion"] = MODULE_ID
    upstream_path: str
    api_key_env_var: str
    auth_header: Literal["X-API-Key", "Authorization"]
    auth_prefix: Literal["", "Bearer "]
    request_mapping: Literal["multipart_image", "responses_image_yaml"]
    response_mapping: Literal["score_status", "responses_json_text"]
    image_media_types: list[Literal["image/png", "image/jpeg", "image/webp", "image/gif"]]
    max_image_data_url_bytes: int = Field(gt=0, le=28 * 1024 * 1024)
    max_yaml_bytes: int = Field(default=262144, gt=0, le=262144)
    max_response_bytes: int = Field(default=2 * 1024 * 1024, gt=0, le=16 * 1024 * 1024)
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
        if (self.request_mapping == "responses_image_yaml") != (
            self.response_mapping == "responses_json_text"
        ):
            raise ValueError("Incompatible request/response mappings")
        if self.response_mapping == "responses_json_text" and not self.result_schema_version:
            raise ValueError("JSON projection requires a schema version")
        if self.module_id == "facial_scoring" and (
            self.profile_id != "facial-scoring-v1"
            or self.public_model != "facial-manipulation-scoring"
            or self.upstream_model != self.public_model
            or self.request_mapping != "multipart_image"
            or self.api_key_env_var != "FACIAL_SCORING_API_KEY"
        ):
            raise ValueError("Legacy module identity cannot be reassigned")
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


@lru_cache(maxsize=64)
def load_profile(profile_id: str, directory: str = "") -> CompletionProfile:
    """Load one bounded JSON file; route metadata cannot select a file path."""
    try:
        if not _ID.fullmatch(profile_id):
            raise ValueError("Invalid profile ID")
        root = Path(directory) if directory else Path(__file__).parent / "profiles"
        if directory and (not root.is_absolute() or root.is_symlink()):
            raise ValueError("Profile directory must be an absolute operator path")
        path = root / (profile_id + ".json")
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
