"""Safe errors for external alert delivery."""

from __future__ import annotations


class AlertError(Exception):
    """Base class for safe alert errors."""

    def __init__(self, safe_message: str) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message


class AlertDeliveryError(AlertError):
    """Raised when a configured alert sink cannot be delivered."""
