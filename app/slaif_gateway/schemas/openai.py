"""Minimal OpenAI-compatible schemas used by /v1 endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class OpenAIModel(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int = 0
    owned_by: str = "slaif"


class OpenAIModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[OpenAIModel]


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[dict[str, Any]]
    stream: bool | None = False
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
