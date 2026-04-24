"""OpenAI-compatible error response schemas."""

from pydantic import BaseModel


class OpenAIErrorDetail(BaseModel):
    message: str
    type: str
    param: str | None = None
    code: str | None = None


class OpenAIErrorResponse(BaseModel):
    error: OpenAIErrorDetail
