"""OpenAI-compatible error helpers and exception handlers."""

from fastapi import Request
from fastapi.exception_handlers import (
    http_exception_handler as fastapi_http_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from typing import Any

from slaif_gateway.metrics import increment_auth_failure
from slaif_gateway.schemas.errors import OpenAIErrorDetail, OpenAIErrorResponse

_DEFAULT_ERROR_TYPES_BY_STATUS = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "invalid_request_error",
    405: "invalid_request_error",
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
        diagnostics_facts: dict[str, object] | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_type = error_type or _default_error_type(status_code)
        self.code = code
        self.param = param
        # Private typed observation facts (bounded, content-free) for the
        # diagnostics facility only.  Never part of the public error JSON.
        self.diagnostics_facts = diagnostics_facts
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


_MAX_PUBLIC_MESSAGE_CHARS = 1024


def _public_error_facts(
    *,
    error_code: str | None,
    error_param: str | None,
    error_message: str | None,
    status_code: int,
) -> dict[str, Any]:
    """Bounded facts for the PUBLIC response error of a local rejection.

    The human operator requires the response status, error code, param, and
    the precise public reason in the capture record.  These are kept distinct
    from the internal classifier ``reason_code``.
    """
    if error_message is not None:
        error_message = error_message[:_MAX_PUBLIC_MESSAGE_CHARS]
    return {
        "error_code": error_code,
        "error_param": error_param,
        "error_message": error_message,
        "status_code": int(status_code),
    }


def _record_local_error_facts(
    request: Request,
    facts: dict[str, Any],
    *,
    public: dict[str, Any] | None = None,
) -> None:
    """Attach bounded local-error facts to the capture diagnostic.

    Observation-only and best-effort: bounded, content-free, and it never
    changes the response.  The public response error (code/param/message/
    status) is always merged onto the recorded facts; when a more specific
    reason (e.g. the structured additional-tools taxonomy failure) has already
    been recorded on the scope, its internal classifier fields (source,
    reason code, indexes, counts, limits) are preserved unchanged.  ``facts``
    must never carry raw request content, ``input`` values, or exception
    objects.
    """
    try:
        from slaif_gateway.services.request_capture import (
            get_scope_capture_rejection,
            record_scope_capture_rejection,
        )

        scope = request.scope
        existing = get_scope_capture_rejection(scope)
        if existing is not None:
            merged = dict(existing)
            if public is not None:
                merged.update(public)
            record_scope_capture_rejection(scope, merged)
            return
        if public is not None:
            facts = {**public, **facts}
        record_scope_capture_rejection(scope, facts)
    except Exception:  # noqa: BLE001 - observability must never affect the response
        pass


def _record_local_rejection(request: Request, exc: OpenAICompatibleError) -> None:
    """Attach a generic local-rejection fact to the capture diagnostic."""
    _record_local_error_facts(
        request,
        {
            "source": "local_error",
            "reason_code": exc.code or "local_rejection",
            "param": exc.param,
            "status_code": exc.status_code,
        },
        public=_public_error_facts(
            error_code=exc.code,
            error_param=exc.param,
            error_message=exc.message,
            status_code=exc.status_code,
        ),
    )


_MAX_VALIDATION_FACTS = 10
_MAX_LOC_PARTS = 8


def _validation_rejection_facts(exc: RequestValidationError) -> dict[str, Any]:
    """Bounded, content-free parser/schema facts from a validation error.

    Keeps stable error types, sanitized locations, and line/column positions
    where the parser reports them.  Excludes ``input`` values, raw body
    bytes, and exception objects entirely.
    """
    errors = list(exc.errors())
    entries: list[dict[str, Any]] = []
    for error in errors[:_MAX_VALIDATION_FACTS]:
        if not isinstance(error, dict):
            continue
        entry: dict[str, Any] = {}
        loc: list[str | int] = []
        raw_loc = error.get("loc")
        if isinstance(raw_loc, (list, tuple)):
            for part in raw_loc[:_MAX_LOC_PARTS]:
                if isinstance(part, str):
                    loc.append(part[:128])
                elif isinstance(part, int) and not isinstance(part, bool):
                    loc.append(part)
        if loc:
            entry["loc"] = loc
        error_type = error.get("type")
        if isinstance(error_type, str) and error_type:
            entry["error_type"] = error_type[:64]
        ctx = error.get("ctx")
        if isinstance(ctx, dict):
            for key in ("line", "column", "pos"):
                value = ctx.get(key)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    entry[key] = value
            if error_type == "json_invalid":
                decoder_message = ctx.get("error")
                if isinstance(decoder_message, str) and decoder_message:
                    entry["json_error"] = decoder_message[:128]
        entries.append(entry)
    return {
        "source": "local_error",
        "reason_code": "request_validation",
        "status_code": 422,
        "count": len(errors),
        "errors": entries,
    }


def _http_error_rejection_facts(exc: StarletteHTTPException) -> dict[str, Any]:
    """Bounded, content-free facts for a generic HTTP exception."""
    return {
        "source": "local_error",
        "reason_code": "http_error",
        "status_code": int(exc.status_code),
    }


def _record_diagnostic_facts(request: Request, facts: object) -> None:
    """Merge private typed diagnostics facts onto the per-request scope.

    Observation-only, best-effort, and bounded to the known diagnostics
    fields (token estimates, ceiling limits).  Never changes the response.
    """
    try:
        from collections.abc import Mapping

        from slaif_gateway.services.request_diagnostics import (
            record_scope_diagnostics,
        )

        if not isinstance(facts, Mapping):
            return
        selected = {
            key: facts.get(key)
            for key in (
                "source",
                "estimated_input_tokens",
                "output_allowance_tokens",
                "context_window_tokens",
                "limits",
            )
        }
        record_scope_diagnostics(request.scope, **selected)
    except Exception:  # noqa: BLE001 - observability must never affect the response
        pass


async def openai_compatible_error_handler(
    request: Request,
    exc: OpenAICompatibleError,
) -> JSONResponse:
    _record_local_rejection(request, exc)
    _record_diagnostic_facts(request, exc.diagnostics_facts)
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
        _record_local_error_facts(
            request,
            _http_error_rejection_facts(exc),
            public=_public_error_facts(
                error_code=str(exc.status_code),
                error_param=None,
                error_message=message,
                status_code=exc.status_code,
            ),
        )
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
        _record_local_error_facts(
            request,
            _validation_rejection_facts(exc),
            public=_public_error_facts(
                error_code="validation_error",
                error_param=None,
                error_message="Invalid request",
                status_code=422,
            ),
        )
        return openai_error_response(
            message="Invalid request",
            status_code=422,
            code="validation_error",
        )

    return JSONResponse(status_code=422, content={"detail": exc.errors()})
