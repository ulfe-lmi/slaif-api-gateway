"""Pytest configuration for project tests."""

from __future__ import annotations

from collections.abc import Iterator
import logging
import sys

import pytest
import structlog


def _reset_logging_state() -> None:
    """Restore logging globals after tests that bind capture-owned streams."""
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.__stderr__,
        force=True,
    )


@pytest.fixture(autouse=True)
def isolate_logging_state() -> Iterator[None]:
    _reset_logging_state()
    yield
    _reset_logging_state()
