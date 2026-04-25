"""Safe service errors for bootstrap record management."""

from __future__ import annotations


class RecordServiceError(Exception):
    """Base class for safe bootstrap record service errors."""

    error_code = "record_error"
    safe_message = "Record operation failed"


class DuplicateRecordError(RecordServiceError):
    """Raised when a unique record already exists."""

    error_code = "duplicate_record"

    def __init__(self, entity: str, field: str) -> None:
        self.entity = entity
        self.field = field
        self.safe_message = f"{entity} with this {field} already exists"
        super().__init__(self.safe_message)


class RecordNotFoundError(RecordServiceError):
    """Raised when a requested record cannot be found."""

    error_code = "record_not_found"

    def __init__(self, entity: str) -> None:
        self.entity = entity
        self.safe_message = f"{entity} not found"
        super().__init__(self.safe_message)


class UnsupportedRecordOperationError(RecordServiceError):
    """Raised when the current authoritative schema cannot support an operation."""

    error_code = "unsupported_record_operation"

    def __init__(self, message: str) -> None:
        self.safe_message = message
        super().__init__(self.safe_message)
