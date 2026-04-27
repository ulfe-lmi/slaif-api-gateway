"""OpenAI-compatible error helpers and exception handlers."""

from fastapi import Request
from fastapi.exception_handlers import (
    http_exception_handler as fastapi_http_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from slaif_gateway.metrics import increment_auth_failure
from slaif_gateway.schemas.errors import OpenAIErrorDetail, OpenAIErrorResponse

_DEFAULT_ERROR_TYPES_BY_STATUS = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "invalid_request_error",
    422: "invalid_request_error",
    429: "rate_limit_error",
    500: "server_error",
}


def _default_error_type(status_code: int) -> str:
    return _DEFAULT_ERROR_TYPES_BY_STATUS.get(status_code, "server_error")


class OpenAICompatibleError(Exception):
    """Raised to produce OpenAI-shaped errors from /v1 handlers."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        error_type: str | None = None,
        code: str | None = None,
        param: str | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_type = error_type or _default_error_type(status_code)
        self.code = code
        self.param = param
        super().__init__(message)


def openai_error_response(
    *,
    message: str,
    status_code: int,
    error_type: str | None = None,
    code: str | None = None,
    param: str | None = None,
) -> JSONResponse:
    """Create OpenAI-compatible JSON error response."""
    payload = OpenAIErrorResponse(
        error=OpenAIErrorDetail(
            message=message,
            type=error_type or _default_error_type(status_code),
            param=param,
            code=code,
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


async def openai_compatible_error_handler(
    request: Request,
    exc: OpenAICompatibleError,
) -> JSONResponse:
    if exc.status_code == 401 or exc.error_type == "authentication_error":
        increment_auth_failure(exc.code)
    return openai_error_response(
        message=exc.message,
        status_code=exc.status_code,
        error_type=exc.error_type,
        code=exc.code,
        param=exc.param,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/v1"):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return openai_error_response(
            message=message,
            status_code=exc.status_code,
            code=str(exc.status_code),
        )

    return await fastapi_http_exception_handler(request, exc)


async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    if request.url.path.startswith("/v1"):
        return openai_error_response(
            message="Invalid request",
            status_code=422,
            code="validation_error",
        )

    return JSONResponse(status_code=422, content={"detail": exc.errors()})
