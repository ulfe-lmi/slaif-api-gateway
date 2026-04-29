"""Safe domain errors for email and one-time secret delivery."""

from __future__ import annotations


class EmailError(Exception):
    """Base class for safe email-delivery errors."""

    error_code = "email_error"

    def __init__(self, message: str = "Email delivery failed") -> None:
        super().__init__(message)
        self.safe_message = message


class EmailDeliveryDisabledError(EmailError):
    """Raised when email delivery is disabled by configuration."""

    error_code = "email_delivery_disabled"


class SmtpConfigurationError(EmailError):
    """Raised when SMTP settings are incomplete or invalid."""

    error_code = "smtp_configuration_error"


class SmtpSendError(EmailError):
    """Raised when SMTP sending fails."""

    error_code = "smtp_send_error"


class EmailDeliveryNotSendableError(EmailError):
    """Raised when an email delivery is not safe to send."""

    error_code = "email_delivery_not_sendable"


class EmailDeliveryInProgressError(EmailDeliveryNotSendableError):
    """Raised when an email delivery is already in progress."""

    error_code = "email_delivery_in_progress"


class EmailDeliveryAmbiguousError(EmailDeliveryNotSendableError):
    """Raised when prior SMTP acceptance cannot be finalized safely."""

    error_code = "email_delivery_ambiguous"


class EmailDeliveryFinalizationError(EmailDeliveryAmbiguousError):
    """Raised when DB finalization fails after SMTP success."""

    error_code = "email_delivery_finalization_failed"


class EmailDeliveryAttemptStateError(EmailError):
    """Raised when the attempt state cannot be persisted safely."""

    error_code = "email_delivery_attempt_state_error"


class OneTimeSecretError(EmailError):
    """Base class for one-time secret consumption errors."""

    error_code = "one_time_secret_error"


class OneTimeSecretNotFoundError(OneTimeSecretError):
    """Raised when a referenced one-time secret does not exist."""

    error_code = "one_time_secret_not_found"


class OneTimeSecretExpiredError(OneTimeSecretError):
    """Raised when a one-time secret is expired."""

    error_code = "one_time_secret_expired"


class OneTimeSecretAlreadyConsumedError(OneTimeSecretError):
    """Raised when a one-time secret has already been consumed."""

    error_code = "one_time_secret_already_consumed"


class OneTimeSecretPurposeError(OneTimeSecretError):
    """Raised when a one-time secret is used for the wrong purpose."""

    error_code = "one_time_secret_wrong_purpose"
