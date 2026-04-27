"""Structured logging configuration for the gateway."""

from __future__ import annotations

import logging as stdlib_logging
from typing import Any

import structlog

from slaif_gateway.config import Settings
from slaif_gateway.utils.redaction import redact_mapping, redact_text


def configure_logging(settings: Settings) -> None:
    """Configure stdlib logging and structlog processors."""
    stdlib_logging.basicConfig(
        level=getattr(stdlib_logging, settings.LOG_LEVEL.upper(), stdlib_logging.INFO),
        format="%(message)s",
        force=True,
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _redact_event,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    if settings.STRUCTURED_LOGS:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(stdlib_logging, settings.LOG_LEVEL.upper(), stdlib_logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def _redact_event(logger: object, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Structlog processor that redacts sensitive values."""
    _ = (logger, method_name)
    return redact_mapping(event_dict)


def bind_request_id(request_id: str | None) -> None:
    """Bind request_id to structlog context for the current async context."""
    if request_id:
        structlog.contextvars.bind_contextvars(request_id=redact_text(request_id))


def clear_log_context() -> None:
    """Clear structlog context variables for the current async context."""
    structlog.contextvars.clear_contextvars()
