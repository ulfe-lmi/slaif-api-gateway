"""Runtime configuration for the SLAIF API Gateway."""

from __future__ import annotations

import base64
import os
import re
from decimal import Decimal
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MIN_PRODUCTION_SECRET_LENGTH = 32
_MIN_PROVIDER_SECRET_LENGTH = 20
_ONE_TIME_SECRET_KEY_BYTES = 32
_GATEWAY_PREFIX_PATTERN = re.compile(r"^sk-[a-z0-9-]+-$")
_PLACEHOLDER_SECRET_SUBSTRINGS = (
    "change-me",
    "changeme",
    "placeholder",
    "example",
    "dummy",
)
_SUPPORTED_CHAT_AUDIO_INPUT_FORMATS = frozenset({"wav", "mp3"})
_SUPPORTED_CHAT_AUDIO_OUTPUT_FORMATS = frozenset({"wav", "aac", "mp3", "flac", "opus", "pcm16"})
_SUPPORTED_CHAT_AUDIO_OUTPUT_VOICES = frozenset(
    {"alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "marin", "cedar"}
)
_SUPPORTED_AUDIO_SPEECH_RESPONSE_FORMATS = frozenset({"mp3", "opus", "aac", "flac", "wav", "pcm"})
_SUPPORTED_AUDIO_SPEECH_VOICES = frozenset(
    {
        "alloy",
        "ash",
        "ballad",
        "coral",
        "echo",
        "fable",
        "nova",
        "onyx",
        "sage",
        "shimmer",
        "verse",
        "marin",
        "cedar",
    }
)
_SUPPORTED_AUDIO_UPLOAD_EXTENSIONS = frozenset(
    {".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm"}
)
_SUPPORTED_AUDIO_UPLOAD_MIME_TYPES = frozenset(
    {
        "audio/flac",
        "audio/m4a",
        "audio/mp3",
        "audio/mp4",
        "audio/mpeg",
        "audio/mpga",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "application/octet-stream",
        "video/mp4",
    }
)
_SUPPORTED_AUDIO_TRANSCRIPTION_RESPONSE_FORMATS = frozenset(
    {"json", "text", "srt", "verbose_json", "vtt"}
)
_SUPPORTED_AUDIO_TRANSLATION_RESPONSE_FORMATS = frozenset(
    {"json", "text", "srt", "verbose_json", "vtt"}
)
_SUPPORTED_AUDIO_TRANSCRIPTION_INCLUDE_VALUES = frozenset({"logprobs"})
_SUPPORTED_AUDIO_TIMESTAMP_GRANULARITIES = frozenset({"word", "segment"})
_SUPPORTED_EMBEDDINGS_ENCODING_FORMATS = frozenset({"float", "base64"})


class Settings(BaseSettings):
    """Environment-backed application settings."""

    APP_ENV: str = "development"
    APP_BASE_URL: str = "http://localhost:8000"
    PUBLIC_BASE_URL: str = "http://localhost:8000/v1"

    DATABASE_URL: str | None = None
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT_SECONDS: float = 30
    DATABASE_POOL_RECYCLE_SECONDS: int = 1800
    DATABASE_POOL_PRE_PING: bool = True
    DATABASE_CONNECT_TIMEOUT_SECONDS: float = 10
    DATABASE_STATEMENT_TIMEOUT_MS: int | None = None
    REDIS_URL: str | None = None
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None
    ENABLE_REDIS_RATE_LIMITS: bool = False
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 2
    REDIS_SOCKET_TIMEOUT_SECONDS: float = 2
    DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE: int | None = None
    DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE: int | None = None
    DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS: int | None = None
    RATE_LIMIT_FAIL_CLOSED: bool | None = None
    RATE_LIMIT_CONCURRENCY_TTL_SECONDS: int = 300
    RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS: int = 30
    RATE_LIMIT_CONCURRENCY_TTL_GRACE_SECONDS: int = 30

    ACTIVE_HMAC_KEY_VERSION: str = "1"
    TOKEN_HMAC_SECRET_V1: str | None = None
    TOKEN_HMAC_SECRET: str | None = None
    ADMIN_SESSION_SECRET: str | None = None

    ONE_TIME_SECRET_ENCRYPTION_KEY: str | None = None
    ONE_TIME_SECRET_KEY_VERSION: str = "v1"

    OPENAI_UPSTREAM_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    OPENAI_ADMIN_DISCOVERY_API_KEY: str | None = None
    OPENAI_ASSISTED_CATALOG_MODEL: str = "gpt-5.5"

    ENABLE_OPENAI_PROVIDER: bool = True
    ENABLE_OPENROUTER_PROVIDER: bool = True
    ENABLE_ADMIN_DASHBOARD: bool = True
    ADMIN_SESSION_COOKIE_NAME: str = "slaif_admin_session"
    ADMIN_SESSION_COOKIE_SECURE: bool | None = None
    ADMIN_SESSION_COOKIE_HTTPONLY: bool = True
    ADMIN_SESSION_COOKIE_SAMESITE: str = "lax"
    ADMIN_SESSION_TTL_SECONDS: int = 28800
    ADMIN_LOGIN_CSRF_COOKIE_NAME: str = "slaif_admin_login_csrf"
    ADMIN_CSRF_TTL_SECONDS: int = 1800
    ADMIN_LOGIN_RATE_LIMIT_ENABLED: bool = True
    ADMIN_LOGIN_MAX_FAILED_ATTEMPTS: int = 5
    ADMIN_LOGIN_WINDOW_SECONDS: int = 900
    ADMIN_LOGIN_LOCKOUT_SECONDS: int = 900
    ENABLE_EMAIL_DELIVERY: bool = False
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 1025
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None
    SMTP_USE_TLS: bool = False
    SMTP_STARTTLS: bool = False
    SMTP_TIMEOUT_SECONDS: float = 10
    EMAIL_KEY_SECRET_MAX_AGE_SECONDS: int = 86400
    ENABLE_SCHEDULED_RECONCILIATION: bool = False
    RECONCILIATION_DRY_RUN: bool = True
    RECONCILIATION_INTERVAL_SECONDS: int = 300
    RECONCILIATION_EXPIRED_RESERVATION_LIMIT: int = 100
    RECONCILIATION_PROVIDER_COMPLETED_LIMIT: int = 100
    RECONCILIATION_EXPIRED_RESERVATION_OLDER_THAN_SECONDS: int = 0
    RECONCILIATION_PROVIDER_COMPLETED_OLDER_THAN_SECONDS: int = 0
    RECONCILIATION_AUTO_EXECUTE_EXPIRED_RESERVATIONS: bool = False
    RECONCILIATION_AUTO_EXECUTE_PROVIDER_COMPLETED: bool = False
    ENABLE_RECONCILIATION_ALERTS: bool = False
    RECONCILIATION_ALERT_WEBHOOK_URL: str | None = None
    RECONCILIATION_ALERT_WEBHOOK_TIMEOUT_SECONDS: float = 10
    RECONCILIATION_ALERT_MIN_EXPIRED_RESERVATIONS: int = 1
    RECONCILIATION_ALERT_MIN_PROVIDER_COMPLETED: int = 1
    RECONCILIATION_ALERT_INCLUDE_IDS: bool = False
    PRICING_IMPORT_MAX_BYTES: int = 1048576
    PRICING_IMPORT_MAX_ROWS: int = 1000
    ROUTE_IMPORT_MAX_BYTES: int = 1048576
    ROUTE_IMPORT_MAX_ROWS: int = 1000
    FX_IMPORT_MAX_BYTES: int = 1048576
    FX_IMPORT_MAX_ROWS: int = 1000
    KEY_IMPORT_MAX_BYTES: int = 1048576
    KEY_IMPORT_MAX_ROWS: int = 1000
    ADMIN_USAGE_EXPORT_MAX_ROWS: int = 10000
    ADMIN_AUDIT_EXPORT_MAX_ROWS: int = 10000
    ENABLE_METRICS: bool = True
    METRICS_REQUIRE_AUTH: bool | None = None
    METRICS_PUBLIC_IN_PRODUCTION: bool = False
    METRICS_ALLOWED_IPS: str | None = None
    READYZ_INCLUDE_DETAILS: bool | None = None
    REQUEST_ID_HEADER: str = "X-Request-ID"
    LOG_LEVEL: str = "INFO"
    STRUCTURED_LOGS: bool = True
    GATEWAY_KEY_PREFIX: str = "sk-slaif-"
    GATEWAY_KEY_ACCEPTED_PREFIXES: str | None = None
    DEFAULT_MAX_OUTPUT_TOKENS: int = 1024
    HARD_MAX_OUTPUT_TOKENS: int = 4096
    HARD_MAX_INPUT_TOKENS: int = 128000
    CHAT_MAX_CHOICES_PER_REQUEST: int = 4
    CHAT_MAX_MESSAGES_PER_REQUEST: int = 128
    CHAT_MAX_MESSAGE_CONTENT_BYTES: int = 262144
    CHAT_MAX_TEXT_PARTS_PER_MESSAGE: int = 64
    CHAT_MAX_IMAGES_PER_REQUEST: int = 8
    CHAT_MAX_IMAGES_PER_MESSAGE: int = 4
    CHAT_MAX_IMAGE_URL_BYTES: int = 4096
    CHAT_MAX_IMAGE_DATA_URL_BYTES: int = 10485760
    CHAT_ALLOW_IMAGE_DATA_URLS: bool = True
    CHAT_ALLOW_REMOTE_IMAGE_URLS: bool = True
    CHAT_MAX_FILES_PER_REQUEST: int = 4
    CHAT_MAX_FILES_PER_MESSAGE: int = 2
    CHAT_MAX_FILE_DATA_BYTES: int = 10485760
    CHAT_MAX_FILE_NAME_BYTES: int = 255
    CHAT_ALLOW_FILE_DATA_URLS: bool = False
    CHAT_ALLOW_FILE_IDS: bool = False
    CHAT_ALLOWED_FILE_MIME_TYPES: str = "application/pdf,text/plain,text/markdown,text/csv,application/json"
    CHAT_ALLOWED_FILE_EXTENSIONS: str = ".pdf,.txt,.md,.csv,.json"
    CHAT_MAX_AUDIO_INPUTS_PER_REQUEST: int = 4
    CHAT_MAX_AUDIO_INPUTS_PER_MESSAGE: int = 2
    CHAT_MAX_AUDIO_INPUT_DATA_BYTES: int = 10485760
    CHAT_ALLOWED_AUDIO_INPUT_FORMATS: str = "wav,mp3"
    CHAT_ALLOW_AUDIO_INPUT_DATA_URLS: bool = False
    CHAT_ALLOWED_AUDIO_OUTPUT_FORMATS: str = "wav,aac,mp3,flac,opus,pcm16"
    CHAT_ALLOWED_AUDIO_OUTPUT_VOICES: str = "alloy,ash,ballad,coral,echo,fable,nova,onyx,sage,shimmer,marin,cedar"
    CHAT_ALLOW_CUSTOM_AUDIO_OUTPUT_VOICES: bool = False
    CHAT_ALLOW_STREAMING_AUDIO_OUTPUT: bool = False
    CHAT_ALLOW_AUDIO_OUTPUT_WITH_N_CHOICES: bool = False
    AUDIO_SPEECH_ALLOWED_MODELS: str = "tts-1,tts-1-hd,gpt-4o-mini-tts,gpt-4o-mini-tts-2025-12-15"
    AUDIO_SPEECH_ALLOWED_RESPONSE_FORMATS: str = "mp3,opus,aac,flac,wav,pcm"
    AUDIO_SPEECH_ALLOWED_VOICES: str = "alloy,ash,ballad,coral,echo,fable,nova,onyx,sage,shimmer,verse,marin,cedar"
    AUDIO_SPEECH_MAX_INPUT_CHARS: int = 4096
    AUDIO_SPEECH_MAX_INSTRUCTIONS_BYTES: int = 8192
    AUDIO_TRANSCRIPTION_ALLOWED_MODELS: str = "gpt-4o-transcribe,gpt-4o-mini-transcribe,gpt-4o-mini-transcribe-2025-12-15,whisper-1,gpt-4o-transcribe-diarize"
    AUDIO_TRANSLATION_ALLOWED_MODELS: str = "whisper-1"
    AUDIO_UPLOAD_MAX_FILE_BYTES: int = 26214400
    AUDIO_UPLOAD_ALLOWED_EXTENSIONS: str = ".flac,.mp3,.mp4,.mpeg,.mpga,.m4a,.ogg,.wav,.webm"
    AUDIO_UPLOAD_ALLOWED_MIME_TYPES: str = "audio/flac,audio/m4a,audio/mp3,audio/mp4,audio/mpeg,audio/mpga,audio/ogg,audio/wav,audio/webm,application/octet-stream,video/mp4"
    AUDIO_UPLOAD_MAX_FILENAME_BYTES: int = 255
    AUDIO_TRANSCRIPTION_ALLOWED_RESPONSE_FORMATS: str = "json,text,srt,verbose_json,vtt"
    AUDIO_TRANSLATION_ALLOWED_RESPONSE_FORMATS: str = "json,text,srt,verbose_json,vtt"
    AUDIO_TRANSCRIPTION_ALLOWED_INCLUDE_VALUES: str = "logprobs"
    AUDIO_ALLOWED_TIMESTAMP_GRANULARITIES: str = "word,segment"
    AUDIO_TRANSCRIPTION_MAX_PROMPT_BYTES: int = 8192
    AUDIO_TRANSLATION_MAX_PROMPT_BYTES: int = 8192
    EMBEDDINGS_MAX_INPUT_ITEMS: int = 128
    EMBEDDINGS_MAX_TEXT_ITEM_BYTES: int = 262144
    EMBEDDINGS_MAX_TOTAL_INPUT_BYTES: int = 1048576
    EMBEDDINGS_MAX_TOKEN_ARRAY_LENGTH: int = 32768
    EMBEDDINGS_MAX_TOTAL_ESTIMATED_TOKENS: int = 262144
    EMBEDDINGS_MAX_DIMENSIONS: int = 3072
    EMBEDDINGS_MAX_USER_BYTES: int = 1024
    CHAT_MAX_TOOLS_PER_REQUEST: int = 64
    CHAT_MAX_CUSTOM_TOOLS_PER_REQUEST: int = 16
    CHAT_MAX_FUNCTIONS_PER_REQUEST: int = 64
    CHAT_MAX_SINGLE_TOOL_SCHEMA_BYTES: int = 65536
    CHAT_MAX_TOTAL_TOOL_SCHEMA_BYTES: int = 262144
    CHAT_MAX_CUSTOM_TOOL_FORMAT_BYTES: int = 65536
    CHAT_MAX_CUSTOM_TOOL_GRAMMAR_BYTES: int = 32768
    CHAT_MAX_RESPONSE_FORMAT_SCHEMA_BYTES: int = 65536
    CHAT_MAX_METADATA_BYTES: int = 16384
    CHAT_MAX_METADATA_KEYS: int = 32
    CHAT_MAX_STOP_SEQUENCES: int = 4
    CHAT_MAX_STOP_SEQUENCE_BYTES: int = 1024
    CHAT_MAX_USER_FIELD_BYTES: int = 1024
    CHAT_MAX_PREDICTION_BYTES: int = 65536
    CHAT_MAX_STREAM_OPTIONS_BYTES: int = 8192
    CHAT_MAX_LOGIT_BIAS_BYTES: int = 16384
    CHAT_MAX_TOOL_NAME_BYTES: int = 128
    CHAT_MAX_TOOL_DESCRIPTION_BYTES: int = 4096
    CHAT_MAX_CUSTOM_TOOL_NAME_BYTES: int = 128
    CHAT_MAX_CUSTOM_TOOL_DESCRIPTION_BYTES: int = 4096
    CHAT_MAX_METADATA_KEY_BYTES: int = 128
    CHAT_STREAMING_LIVE_BURN_ESTIMATE_MULTIPLIER: Decimal = Decimal("1.15")
    CHAT_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR: Decimal = Decimal("1000000")
    CHAT_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN: int = 1000000000
    RESPONSES_STREAMING_LIVE_BURN_ESTIMATE_MULTIPLIER: Decimal = Decimal("1.15")
    RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR: Decimal = Decimal("1000000")
    RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN: int = 1000000000
    RESPONSES_MAX_INPUT_TEXT_BYTES: int = 262144
    RESPONSES_MAX_INPUT_ITEMS: int = 128
    RESPONSES_MAX_INPUT_ITEM_TEXT_BYTES: int = 262144
    RESPONSES_MAX_TOTAL_INPUT_TEXT_BYTES: int = 1048576
    RESPONSES_MAX_TEXT_CONTENT_PARTS_PER_ITEM: int = 64
    RESPONSES_MAX_INSTRUCTIONS_BYTES: int = 65536
    RESPONSES_MAX_METADATA_BYTES: int = 16384
    RESPONSES_MAX_METADATA_KEYS: int = 32
    RESPONSES_MAX_STREAM_OPTIONS_BYTES: int = 8192
    RESPONSES_MAX_TEXT_FORMAT_BYTES: int = 65536
    RESPONSES_MAX_JSON_SCHEMA_BYTES: int = 65536
    RESPONSES_MAX_TEXT_FORMAT_NAME_BYTES: int = 64
    RESPONSES_MAX_TEXT_FORMAT_DESCRIPTION_BYTES: int = 4096
    RESPONSES_MAX_TOOLS_PER_REQUEST: int = 64
    RESPONSES_MAX_FUNCTION_TOOLS_PER_REQUEST: int = 64
    RESPONSES_MAX_CUSTOM_TOOLS_PER_REQUEST: int = 64
    RESPONSES_MAX_FUNCTION_TOOL_NAME_BYTES: int = 128
    RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES: int = 4096
    RESPONSES_MAX_SINGLE_FUNCTION_TOOL_SCHEMA_BYTES: int = 65536
    RESPONSES_MAX_TOTAL_FUNCTION_TOOL_SCHEMA_BYTES: int = 262144
    RESPONSES_MAX_FUNCTION_CALL_OUTPUT_BYTES: int = 262144
    RESPONSES_MAX_CUSTOM_TOOL_NAME_BYTES: int = 128
    RESPONSES_MAX_CUSTOM_TOOL_DESCRIPTION_BYTES: int = 4096
    RESPONSES_MAX_CUSTOM_TOOL_FORMAT_DEFINITION_BYTES: int = 65536
    RESPONSES_MAX_TOTAL_CUSTOM_TOOL_FORMAT_BYTES: int = 262144
    RESPONSES_MAX_CUSTOM_TOOL_CALL_OUTPUT_BYTES: int = 262144
    RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST: int = 16
    RESPONSES_MAX_IMAGE_URL_BYTES: int = 4096
    RESPONSES_MAX_IMAGE_DATA_URL_BYTES: int = 20971520
    RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES: int = 41943040
    RESPONSES_ALLOWED_IMAGE_MIME_TYPES: str = "image/png,image/jpeg,image/webp,image/gif"
    RESPONSES_MAX_FILE_PARTS_PER_REQUEST: int = 8
    RESPONSES_MAX_FILE_URL_BYTES: int = 4096
    RESPONSES_MAX_FILE_DATA_URL_BYTES: int = 26214400
    RESPONSES_MAX_TOTAL_FILE_DATA_URL_BYTES: int = 52428800
    RESPONSES_MAX_FILE_NAME_BYTES: int = 255
    RESPONSES_MAX_PREVIOUS_RESPONSE_ID_BYTES: int = 256
    RESPONSES_MAX_CONVERSATION_ID_BYTES: int = 256
    RESPONSES_COMPACT_DEFAULT_MAX_OUTPUT_TOKENS: int = 12000
    RESPONSES_COMPACT_HARD_MAX_OUTPUT_TOKENS: int = 24000
    RESPONSES_ALLOWED_FILE_MIME_TYPES: str = (
        "application/pdf,text/plain,text/markdown,text/csv,application/json,"
        "text/html,text/xml,application/xml"
    )
    RESPONSES_ALLOWED_FILE_EXTENSIONS: str = ".pdf,.txt,.md,.csv,.json,.html,.xml"
    CALIBRATION_KEYS_ENABLED: bool = True
    TRUSTED_CALIBRATION_MAX_REQUESTS: int = 10
    TRUSTED_CALIBRATION_MAX_VALID_DAYS: int = 7
    TRUSTED_CALIBRATION_ALLOW_UNKNOWN_HOSTED_TOOLS: bool = True
    TRUSTED_CALIBRATION_ALLOW_EXTERNAL_AUTHORITY: bool = False

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Enforce minimum secret requirements for production."""
        self._validate_gateway_key_prefix(self.GATEWAY_KEY_PREFIX)
        accepted_prefixes = self.get_gateway_key_accepted_prefixes()
        if self.get_gateway_key_prefix() not in accepted_prefixes:
            raise ValueError("GATEWAY_KEY_ACCEPTED_PREFIXES must include GATEWAY_KEY_PREFIX")

        if self.APP_ENV.lower() == "production":
            version = self.ACTIVE_HMAC_KEY_VERSION.strip()
            if not version:
                raise ValueError("ACTIVE_HMAC_KEY_VERSION is required when APP_ENV=production")

            active_secret = self.get_hmac_secret(version)
            self._validate_production_secret(
                f"TOKEN_HMAC_SECRET_V{version}",
                active_secret,
            )
            self._validate_production_secret("ADMIN_SESSION_SECRET", self.ADMIN_SESSION_SECRET)
            self._validate_required_encryption_key(
                "ONE_TIME_SECRET_ENCRYPTION_KEY",
                self.ONE_TIME_SECRET_ENCRYPTION_KEY,
            )
            self._validate_production_provider_secrets()
            self._validate_openai_api_key_boundary()

        if self.ONE_TIME_SECRET_ENCRYPTION_KEY:
            self._validate_encryption_key_shape(self.ONE_TIME_SECRET_ENCRYPTION_KEY)

        self._validate_request_caps()
        self._validate_calibration_settings()
        self._validate_request_id_header()
        self._validate_database_settings()
        self._validate_redis_rate_limit_settings()
        self._validate_admin_session_settings()
        self._validate_email_settings()
        self._validate_reconciliation_settings()
        return self

    def _validate_database_settings(self) -> None:
        if self.DATABASE_POOL_SIZE <= 0:
            raise ValueError("DATABASE_POOL_SIZE must be a positive integer")
        if self.DATABASE_MAX_OVERFLOW < 0:
            raise ValueError("DATABASE_MAX_OVERFLOW must be greater than or equal to 0")
        if self.DATABASE_POOL_TIMEOUT_SECONDS <= 0:
            raise ValueError("DATABASE_POOL_TIMEOUT_SECONDS must be a positive number")
        if self.DATABASE_POOL_RECYCLE_SECONDS <= 0:
            raise ValueError("DATABASE_POOL_RECYCLE_SECONDS must be a positive integer")
        if self.DATABASE_CONNECT_TIMEOUT_SECONDS <= 0:
            raise ValueError("DATABASE_CONNECT_TIMEOUT_SECONDS must be a positive number")
        if self.DATABASE_STATEMENT_TIMEOUT_MS is not None and self.DATABASE_STATEMENT_TIMEOUT_MS <= 0:
            raise ValueError("DATABASE_STATEMENT_TIMEOUT_MS must be a positive integer when set")

    def _validate_redis_rate_limit_settings(self) -> None:
        if self.ENABLE_REDIS_RATE_LIMITS and not self.REDIS_URL:
            raise ValueError("REDIS_URL is required when ENABLE_REDIS_RATE_LIMITS=true")

        if self.REDIS_CONNECT_TIMEOUT_SECONDS <= 0:
            raise ValueError("REDIS_CONNECT_TIMEOUT_SECONDS must be a positive number")
        if self.REDIS_SOCKET_TIMEOUT_SECONDS <= 0:
            raise ValueError("REDIS_SOCKET_TIMEOUT_SECONDS must be a positive number")

        for name in (
            "DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE",
            "DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE",
            "DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS",
            "RATE_LIMIT_CONCURRENCY_TTL_SECONDS",
            "RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS",
            "RATE_LIMIT_CONCURRENCY_TTL_GRACE_SECONDS",
        ):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be a positive integer when set")

        if self.RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS >= self.RATE_LIMIT_CONCURRENCY_TTL_SECONDS:
            raise ValueError(
                "RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS must be less than "
                "RATE_LIMIT_CONCURRENCY_TTL_SECONDS"
            )

    def _validate_email_settings(self) -> None:
        if self.SMTP_PORT <= 0:
            raise ValueError("SMTP_PORT must be a positive integer")
        if self.SMTP_TIMEOUT_SECONDS <= 0:
            raise ValueError("SMTP_TIMEOUT_SECONDS must be a positive number")
        if self.EMAIL_KEY_SECRET_MAX_AGE_SECONDS <= 0:
            raise ValueError("EMAIL_KEY_SECRET_MAX_AGE_SECONDS must be a positive integer")
        if self.ENABLE_EMAIL_DELIVERY:
            if not self.SMTP_HOST:
                raise ValueError("SMTP_HOST is required when ENABLE_EMAIL_DELIVERY=true")
            if not self.SMTP_FROM:
                raise ValueError("SMTP_FROM is required when ENABLE_EMAIL_DELIVERY=true")

    def _validate_reconciliation_settings(self) -> None:
        if self.RECONCILIATION_INTERVAL_SECONDS <= 0:
            raise ValueError("RECONCILIATION_INTERVAL_SECONDS must be a positive integer")
        if self.RECONCILIATION_EXPIRED_RESERVATION_LIMIT <= 0:
            raise ValueError("RECONCILIATION_EXPIRED_RESERVATION_LIMIT must be a positive integer")
        if self.RECONCILIATION_PROVIDER_COMPLETED_LIMIT <= 0:
            raise ValueError("RECONCILIATION_PROVIDER_COMPLETED_LIMIT must be a positive integer")
        if self.RECONCILIATION_EXPIRED_RESERVATION_OLDER_THAN_SECONDS < 0:
            raise ValueError(
                "RECONCILIATION_EXPIRED_RESERVATION_OLDER_THAN_SECONDS must be greater than or equal to 0"
            )
        if self.RECONCILIATION_PROVIDER_COMPLETED_OLDER_THAN_SECONDS < 0:
            raise ValueError(
                "RECONCILIATION_PROVIDER_COMPLETED_OLDER_THAN_SECONDS must be greater than or equal to 0"
            )
        if self.RECONCILIATION_ALERT_WEBHOOK_TIMEOUT_SECONDS <= 0:
            raise ValueError("RECONCILIATION_ALERT_WEBHOOK_TIMEOUT_SECONDS must be a positive number")
        if self.RECONCILIATION_ALERT_MIN_EXPIRED_RESERVATIONS < 0:
            raise ValueError(
                "RECONCILIATION_ALERT_MIN_EXPIRED_RESERVATIONS must be greater than or equal to 0"
            )
        if self.RECONCILIATION_ALERT_MIN_PROVIDER_COMPLETED < 0:
            raise ValueError(
                "RECONCILIATION_ALERT_MIN_PROVIDER_COMPLETED must be greater than or equal to 0"
            )
        if self.ENABLE_RECONCILIATION_ALERTS:
            if not self.RECONCILIATION_ALERT_WEBHOOK_URL:
                raise ValueError(
                    "RECONCILIATION_ALERT_WEBHOOK_URL is required when ENABLE_RECONCILIATION_ALERTS=true"
                )
            parsed = urlparse(self.RECONCILIATION_ALERT_WEBHOOK_URL)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("RECONCILIATION_ALERT_WEBHOOK_URL must be an http or https URL")
        if self.PRICING_IMPORT_MAX_BYTES <= 0:
            raise ValueError("PRICING_IMPORT_MAX_BYTES must be a positive integer")
        if self.PRICING_IMPORT_MAX_ROWS <= 0:
            raise ValueError("PRICING_IMPORT_MAX_ROWS must be a positive integer")
        if self.ROUTE_IMPORT_MAX_BYTES <= 0:
            raise ValueError("ROUTE_IMPORT_MAX_BYTES must be a positive integer")
        if self.ROUTE_IMPORT_MAX_ROWS <= 0:
            raise ValueError("ROUTE_IMPORT_MAX_ROWS must be a positive integer")
        if self.FX_IMPORT_MAX_BYTES <= 0:
            raise ValueError("FX_IMPORT_MAX_BYTES must be a positive integer")
        if self.FX_IMPORT_MAX_ROWS <= 0:
            raise ValueError("FX_IMPORT_MAX_ROWS must be a positive integer")
        if self.KEY_IMPORT_MAX_BYTES <= 0:
            raise ValueError("KEY_IMPORT_MAX_BYTES must be a positive integer")
        if self.KEY_IMPORT_MAX_ROWS <= 0:
            raise ValueError("KEY_IMPORT_MAX_ROWS must be a positive integer")
        if self.ADMIN_USAGE_EXPORT_MAX_ROWS <= 0:
            raise ValueError("ADMIN_USAGE_EXPORT_MAX_ROWS must be a positive integer")
        if self.ADMIN_AUDIT_EXPORT_MAX_ROWS <= 0:
            raise ValueError("ADMIN_AUDIT_EXPORT_MAX_ROWS must be a positive integer")

    def _validate_admin_session_settings(self) -> None:
        if self.ADMIN_SESSION_TTL_SECONDS <= 0:
            raise ValueError("ADMIN_SESSION_TTL_SECONDS must be a positive integer")
        if self.ADMIN_CSRF_TTL_SECONDS <= 0:
            raise ValueError("ADMIN_CSRF_TTL_SECONDS must be a positive integer")
        if self.ADMIN_LOGIN_MAX_FAILED_ATTEMPTS <= 0:
            raise ValueError("ADMIN_LOGIN_MAX_FAILED_ATTEMPTS must be a positive integer")
        if self.ADMIN_LOGIN_WINDOW_SECONDS <= 0:
            raise ValueError("ADMIN_LOGIN_WINDOW_SECONDS must be a positive integer")
        if self.ADMIN_LOGIN_LOCKOUT_SECONDS <= 0:
            raise ValueError("ADMIN_LOGIN_LOCKOUT_SECONDS must be a positive integer")

        if not self.ADMIN_SESSION_COOKIE_NAME.strip():
            raise ValueError("ADMIN_SESSION_COOKIE_NAME cannot be empty")
        if not self.ADMIN_LOGIN_CSRF_COOKIE_NAME.strip():
            raise ValueError("ADMIN_LOGIN_CSRF_COOKIE_NAME cannot be empty")
        self.ADMIN_SESSION_COOKIE_NAME = self.ADMIN_SESSION_COOKIE_NAME.strip()
        self.ADMIN_LOGIN_CSRF_COOKIE_NAME = self.ADMIN_LOGIN_CSRF_COOKIE_NAME.strip()

        same_site = self.ADMIN_SESSION_COOKIE_SAMESITE.strip().lower()
        if same_site not in {"lax", "strict", "none"}:
            raise ValueError("ADMIN_SESSION_COOKIE_SAMESITE must be one of: lax, strict, none")
        self.ADMIN_SESSION_COOKIE_SAMESITE = same_site

        if (
            self.APP_ENV.lower() == "production"
            and same_site == "none"
            and self.ADMIN_SESSION_COOKIE_SECURE is False
        ):
            raise ValueError("ADMIN_SESSION_COOKIE_SECURE must be true in production when SameSite=None")

    def _validate_request_caps(self) -> None:
        for name in (
            "DEFAULT_MAX_OUTPUT_TOKENS",
            "HARD_MAX_OUTPUT_TOKENS",
            "HARD_MAX_INPUT_TOKENS",
            "CHAT_MAX_CHOICES_PER_REQUEST",
            "CHAT_MAX_MESSAGES_PER_REQUEST",
            "CHAT_MAX_MESSAGE_CONTENT_BYTES",
            "CHAT_MAX_TEXT_PARTS_PER_MESSAGE",
            "CHAT_MAX_IMAGES_PER_REQUEST",
            "CHAT_MAX_IMAGES_PER_MESSAGE",
            "CHAT_MAX_IMAGE_URL_BYTES",
            "CHAT_MAX_IMAGE_DATA_URL_BYTES",
            "CHAT_MAX_FILES_PER_REQUEST",
            "CHAT_MAX_FILES_PER_MESSAGE",
            "CHAT_MAX_FILE_DATA_BYTES",
            "CHAT_MAX_FILE_NAME_BYTES",
            "CHAT_MAX_AUDIO_INPUTS_PER_REQUEST",
            "CHAT_MAX_AUDIO_INPUTS_PER_MESSAGE",
            "CHAT_MAX_AUDIO_INPUT_DATA_BYTES",
            "AUDIO_SPEECH_MAX_INPUT_CHARS",
            "AUDIO_SPEECH_MAX_INSTRUCTIONS_BYTES",
            "AUDIO_UPLOAD_MAX_FILE_BYTES",
            "AUDIO_UPLOAD_MAX_FILENAME_BYTES",
            "AUDIO_TRANSCRIPTION_MAX_PROMPT_BYTES",
            "AUDIO_TRANSLATION_MAX_PROMPT_BYTES",
            "EMBEDDINGS_MAX_INPUT_ITEMS",
            "EMBEDDINGS_MAX_TEXT_ITEM_BYTES",
            "EMBEDDINGS_MAX_TOTAL_INPUT_BYTES",
            "EMBEDDINGS_MAX_TOKEN_ARRAY_LENGTH",
            "EMBEDDINGS_MAX_TOTAL_ESTIMATED_TOKENS",
            "EMBEDDINGS_MAX_DIMENSIONS",
            "EMBEDDINGS_MAX_USER_BYTES",
            "CHAT_MAX_TOOLS_PER_REQUEST",
            "CHAT_MAX_CUSTOM_TOOLS_PER_REQUEST",
            "CHAT_MAX_FUNCTIONS_PER_REQUEST",
            "CHAT_MAX_SINGLE_TOOL_SCHEMA_BYTES",
            "CHAT_MAX_TOTAL_TOOL_SCHEMA_BYTES",
            "CHAT_MAX_CUSTOM_TOOL_FORMAT_BYTES",
            "CHAT_MAX_CUSTOM_TOOL_GRAMMAR_BYTES",
            "CHAT_MAX_RESPONSE_FORMAT_SCHEMA_BYTES",
            "CHAT_MAX_METADATA_BYTES",
            "CHAT_MAX_METADATA_KEYS",
            "CHAT_MAX_STOP_SEQUENCES",
            "CHAT_MAX_STOP_SEQUENCE_BYTES",
            "CHAT_MAX_USER_FIELD_BYTES",
            "CHAT_MAX_PREDICTION_BYTES",
            "CHAT_MAX_STREAM_OPTIONS_BYTES",
            "CHAT_MAX_LOGIT_BIAS_BYTES",
            "CHAT_MAX_TOOL_NAME_BYTES",
            "CHAT_MAX_TOOL_DESCRIPTION_BYTES",
            "CHAT_MAX_CUSTOM_TOOL_NAME_BYTES",
            "CHAT_MAX_CUSTOM_TOOL_DESCRIPTION_BYTES",
            "CHAT_MAX_METADATA_KEY_BYTES",
            "CHAT_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN",
            "RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN",
            "RESPONSES_MAX_INPUT_TEXT_BYTES",
            "RESPONSES_MAX_INPUT_ITEMS",
            "RESPONSES_MAX_INPUT_ITEM_TEXT_BYTES",
            "RESPONSES_MAX_TOTAL_INPUT_TEXT_BYTES",
            "RESPONSES_MAX_TEXT_CONTENT_PARTS_PER_ITEM",
            "RESPONSES_MAX_INSTRUCTIONS_BYTES",
            "RESPONSES_MAX_METADATA_BYTES",
            "RESPONSES_MAX_METADATA_KEYS",
            "RESPONSES_MAX_STREAM_OPTIONS_BYTES",
            "RESPONSES_MAX_TEXT_FORMAT_BYTES",
            "RESPONSES_MAX_JSON_SCHEMA_BYTES",
            "RESPONSES_MAX_TEXT_FORMAT_NAME_BYTES",
            "RESPONSES_MAX_TEXT_FORMAT_DESCRIPTION_BYTES",
            "RESPONSES_MAX_TOOLS_PER_REQUEST",
            "RESPONSES_MAX_FUNCTION_TOOLS_PER_REQUEST",
            "RESPONSES_MAX_CUSTOM_TOOLS_PER_REQUEST",
            "RESPONSES_MAX_FUNCTION_TOOL_NAME_BYTES",
            "RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES",
            "RESPONSES_MAX_SINGLE_FUNCTION_TOOL_SCHEMA_BYTES",
            "RESPONSES_MAX_TOTAL_FUNCTION_TOOL_SCHEMA_BYTES",
            "RESPONSES_MAX_FUNCTION_CALL_OUTPUT_BYTES",
            "RESPONSES_MAX_CUSTOM_TOOL_NAME_BYTES",
            "RESPONSES_MAX_CUSTOM_TOOL_DESCRIPTION_BYTES",
            "RESPONSES_MAX_CUSTOM_TOOL_FORMAT_DEFINITION_BYTES",
            "RESPONSES_MAX_TOTAL_CUSTOM_TOOL_FORMAT_BYTES",
            "RESPONSES_MAX_CUSTOM_TOOL_CALL_OUTPUT_BYTES",
            "RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST",
            "RESPONSES_MAX_IMAGE_URL_BYTES",
            "RESPONSES_MAX_IMAGE_DATA_URL_BYTES",
            "RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES",
            "RESPONSES_MAX_FILE_PARTS_PER_REQUEST",
            "RESPONSES_MAX_FILE_URL_BYTES",
            "RESPONSES_MAX_FILE_DATA_URL_BYTES",
            "RESPONSES_MAX_TOTAL_FILE_DATA_URL_BYTES",
            "RESPONSES_MAX_FILE_NAME_BYTES",
            "RESPONSES_MAX_PREVIOUS_RESPONSE_ID_BYTES",
            "RESPONSES_MAX_CONVERSATION_ID_BYTES",
            "RESPONSES_COMPACT_DEFAULT_MAX_OUTPUT_TOKENS",
            "RESPONSES_COMPACT_HARD_MAX_OUTPUT_TOKENS",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.DEFAULT_MAX_OUTPUT_TOKENS > self.HARD_MAX_OUTPUT_TOKENS:
            raise ValueError("DEFAULT_MAX_OUTPUT_TOKENS must be <= HARD_MAX_OUTPUT_TOKENS")
        if self.RESPONSES_COMPACT_DEFAULT_MAX_OUTPUT_TOKENS > self.RESPONSES_COMPACT_HARD_MAX_OUTPUT_TOKENS:
            raise ValueError(
                "RESPONSES_COMPACT_DEFAULT_MAX_OUTPUT_TOKENS must be <= "
                "RESPONSES_COMPACT_HARD_MAX_OUTPUT_TOKENS"
            )
        if self.CHAT_STREAMING_LIVE_BURN_ESTIMATE_MULTIPLIER <= 0:
            raise ValueError("CHAT_STREAMING_LIVE_BURN_ESTIMATE_MULTIPLIER must be positive")
        if self.CHAT_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR < 0:
            raise ValueError("CHAT_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR must be non-negative")
        _validate_audio_option_set(
            self.CHAT_ALLOWED_AUDIO_INPUT_FORMATS,
            allowed_values=_SUPPORTED_CHAT_AUDIO_INPUT_FORMATS,
            field_name="CHAT_ALLOWED_AUDIO_INPUT_FORMATS",
        )
        _validate_audio_option_set(
            self.CHAT_ALLOWED_AUDIO_OUTPUT_FORMATS,
            allowed_values=_SUPPORTED_CHAT_AUDIO_OUTPUT_FORMATS,
            field_name="CHAT_ALLOWED_AUDIO_OUTPUT_FORMATS",
        )
        _validate_audio_option_set(
            self.CHAT_ALLOWED_AUDIO_OUTPUT_VOICES,
            allowed_values=_SUPPORTED_CHAT_AUDIO_OUTPUT_VOICES,
            field_name="CHAT_ALLOWED_AUDIO_OUTPUT_VOICES",
        )
        _validate_audio_option_set(
            self.AUDIO_SPEECH_ALLOWED_RESPONSE_FORMATS,
            allowed_values=_SUPPORTED_AUDIO_SPEECH_RESPONSE_FORMATS,
            field_name="AUDIO_SPEECH_ALLOWED_RESPONSE_FORMATS",
        )
        _validate_audio_option_set(
            self.AUDIO_SPEECH_ALLOWED_VOICES,
            allowed_values=_SUPPORTED_AUDIO_SPEECH_VOICES,
            field_name="AUDIO_SPEECH_ALLOWED_VOICES",
        )
        _validate_audio_option_set(
            self.AUDIO_UPLOAD_ALLOWED_EXTENSIONS,
            allowed_values=_SUPPORTED_AUDIO_UPLOAD_EXTENSIONS,
            field_name="AUDIO_UPLOAD_ALLOWED_EXTENSIONS",
        )
        _validate_audio_option_set(
            self.AUDIO_UPLOAD_ALLOWED_MIME_TYPES,
            allowed_values=_SUPPORTED_AUDIO_UPLOAD_MIME_TYPES,
            field_name="AUDIO_UPLOAD_ALLOWED_MIME_TYPES",
        )
        _validate_audio_option_set(
            self.AUDIO_TRANSCRIPTION_ALLOWED_RESPONSE_FORMATS,
            allowed_values=_SUPPORTED_AUDIO_TRANSCRIPTION_RESPONSE_FORMATS,
            field_name="AUDIO_TRANSCRIPTION_ALLOWED_RESPONSE_FORMATS",
        )
        _validate_audio_option_set(
            self.AUDIO_TRANSLATION_ALLOWED_RESPONSE_FORMATS,
            allowed_values=_SUPPORTED_AUDIO_TRANSLATION_RESPONSE_FORMATS,
            field_name="AUDIO_TRANSLATION_ALLOWED_RESPONSE_FORMATS",
        )
        _validate_audio_option_set(
            self.AUDIO_TRANSCRIPTION_ALLOWED_INCLUDE_VALUES,
            allowed_values=_SUPPORTED_AUDIO_TRANSCRIPTION_INCLUDE_VALUES,
            field_name="AUDIO_TRANSCRIPTION_ALLOWED_INCLUDE_VALUES",
        )
        _validate_audio_option_set(
            self.AUDIO_ALLOWED_TIMESTAMP_GRANULARITIES,
            allowed_values=_SUPPORTED_AUDIO_TIMESTAMP_GRANULARITIES,
            field_name="AUDIO_ALLOWED_TIMESTAMP_GRANULARITIES",
        )
        _validate_nonempty_csv(self.AUDIO_SPEECH_ALLOWED_MODELS, field_name="AUDIO_SPEECH_ALLOWED_MODELS")
        _validate_nonempty_csv(
            self.AUDIO_TRANSCRIPTION_ALLOWED_MODELS,
            field_name="AUDIO_TRANSCRIPTION_ALLOWED_MODELS",
        )
        _validate_nonempty_csv(
            self.AUDIO_TRANSLATION_ALLOWED_MODELS,
            field_name="AUDIO_TRANSLATION_ALLOWED_MODELS",
        )
        if self.CHAT_ALLOW_AUDIO_INPUT_DATA_URLS:
            raise ValueError(
                "CHAT_ALLOW_AUDIO_INPUT_DATA_URLS is not supported until explicit Chat audio "
                "data-URL validation, accounting, and tests are implemented"
            )
        if self.CHAT_ALLOW_CUSTOM_AUDIO_OUTPUT_VOICES:
            raise ValueError(
                "CHAT_ALLOW_CUSTOM_AUDIO_OUTPUT_VOICES is not supported until custom audio-output "
                "voice policy and accounting are implemented"
            )
        if self.CHAT_ALLOW_STREAMING_AUDIO_OUTPUT:
            raise ValueError(
                "CHAT_ALLOW_STREAMING_AUDIO_OUTPUT is not supported until streaming audio "
                "live-burn accounting is implemented"
            )
        if self.CHAT_ALLOW_AUDIO_OUTPUT_WITH_N_CHOICES:
            raise ValueError(
                "CHAT_ALLOW_AUDIO_OUTPUT_WITH_N_CHOICES is not supported until non-streaming "
                "audio-output multi-choice accounting and response-shape handling are implemented"
            )
        if self.RESPONSES_STREAMING_LIVE_BURN_ESTIMATE_MULTIPLIER <= 0:
            raise ValueError("RESPONSES_STREAMING_LIVE_BURN_ESTIMATE_MULTIPLIER must be positive")
        if self.RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR < 0:
            raise ValueError(
                "RESPONSES_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR must be non-negative"
            )

    def _validate_calibration_settings(self) -> None:
        if self.TRUSTED_CALIBRATION_MAX_REQUESTS <= 0:
            raise ValueError("TRUSTED_CALIBRATION_MAX_REQUESTS must be a positive integer")
        if self.TRUSTED_CALIBRATION_MAX_VALID_DAYS <= 0:
            raise ValueError("TRUSTED_CALIBRATION_MAX_VALID_DAYS must be a positive integer")

    def _validate_request_id_header(self) -> None:
        header = self.REQUEST_ID_HEADER.strip()
        if not header:
            raise ValueError("REQUEST_ID_HEADER cannot be empty")
        if any(ch.isspace() for ch in header):
            raise ValueError("REQUEST_ID_HEADER cannot contain whitespace")
        if any(ord(ch) < 33 or ord(ch) == 127 for ch in header):
            raise ValueError("REQUEST_ID_HEADER cannot contain control characters")
        self.REQUEST_ID_HEADER = header

    @staticmethod
    def _validate_production_secret(name: str, value: str | None) -> None:
        if not value:
            raise ValueError(f"{name} is required when APP_ENV=production")

        if is_placeholder_secret(value):
            raise ValueError(f"{name} cannot contain placeholder text in production")

        if len(value) < _MIN_PRODUCTION_SECRET_LENGTH:
            raise ValueError(
                f"{name} must be at least {_MIN_PRODUCTION_SECRET_LENGTH} characters in production"
            )

    def _validate_production_provider_secrets(self) -> None:
        if self.ENABLE_OPENAI_PROVIDER:
            validate_provider_secret_present(
                "OPENAI_UPSTREAM_API_KEY",
                self.OPENAI_UPSTREAM_API_KEY,
            )
        if self.ENABLE_OPENROUTER_PROVIDER:
            validate_provider_secret_present(
                "OPENROUTER_API_KEY",
                self.OPENROUTER_API_KEY,
            )

    def _validate_openai_api_key_boundary(self) -> None:
        client_key = os.getenv("OPENAI_API_KEY")
        if not client_key:
            return
        if looks_like_real_upstream_openai_key(
            client_key,
            gateway_prefixes=self.get_gateway_key_accepted_prefixes(),
        ):
            raise ValueError(
                "OPENAI_API_KEY is reserved for clients; use OPENAI_UPSTREAM_API_KEY for "
                "the gateway's upstream OpenAI provider key"
            )

    @staticmethod
    def _validate_required_encryption_key(name: str, value: str | None) -> None:
        if not value:
            raise ValueError(f"{name} is required when APP_ENV=production")

    @staticmethod
    def _validate_encryption_key_shape(value: str) -> None:
        padding = "=" * (-len(value) % 4)
        try:
            key_bytes = base64.urlsafe_b64decode(value + padding)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                "ONE_TIME_SECRET_ENCRYPTION_KEY must be base64url-encoded 32-byte key material"
            ) from exc

        if len(key_bytes) != _ONE_TIME_SECRET_KEY_BYTES:
            raise ValueError("ONE_TIME_SECRET_ENCRYPTION_KEY must decode to exactly 32 bytes")

    @staticmethod
    def _validate_gateway_key_prefix(prefix: str) -> None:
        if not prefix:
            raise ValueError("Gateway key prefix cannot be empty")
        if any(ch.isspace() for ch in prefix):
            raise ValueError("Gateway key prefix cannot contain whitespace")
        if "." in prefix:
            raise ValueError("Gateway key prefix cannot contain '.'")
        if "/" in prefix or "\\" in prefix:
            raise ValueError("Gateway key prefix cannot contain slash characters")
        if '"' in prefix or "'" in prefix:
            raise ValueError("Gateway key prefix cannot contain quotes")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in prefix):
            raise ValueError("Gateway key prefix cannot contain control characters")
        if not _GATEWAY_PREFIX_PATTERN.fullmatch(prefix):
            raise ValueError(
                "Gateway key prefix must start with 'sk-', end with '-', and use lowercase "
                "ASCII letters, digits, and hyphens only"
            )

    def get_gateway_key_prefix(self) -> str:
        """Return active gateway key prefix after validation."""
        prefix = self.GATEWAY_KEY_PREFIX.strip()
        self._validate_gateway_key_prefix(prefix)
        return prefix

    def get_gateway_key_accepted_prefixes(self) -> tuple[str, ...]:
        """Return normalized accepted gateway key prefixes."""
        raw = self.GATEWAY_KEY_ACCEPTED_PREFIXES
        if raw is None:
            prefixes = (self.get_gateway_key_prefix(),)
        else:
            prefixes = tuple(item.strip() for item in raw.split(",") if item.strip())
            if not prefixes:
                raise ValueError("GATEWAY_KEY_ACCEPTED_PREFIXES cannot be empty")

        for prefix in prefixes:
            self._validate_gateway_key_prefix(prefix)

        if self.get_gateway_key_prefix() not in prefixes:
            raise ValueError("GATEWAY_KEY_ACCEPTED_PREFIXES must include GATEWAY_KEY_PREFIX")

        return prefixes

    def get_hmac_secret(self, version: str) -> str | None:
        """Return configured HMAC secret for the requested version."""
        normalized = version.strip()
        if not normalized:
            return None

        versioned_name = f"TOKEN_HMAC_SECRET_V{normalized}"
        versioned_secret = os.getenv(versioned_name) or getattr(self, versioned_name, None)
        if versioned_secret:
            return versioned_secret

        if self.APP_ENV.lower() != "production" and normalized == "1" and self.TOKEN_HMAC_SECRET:
            return self.TOKEN_HMAC_SECRET

        return None

    def get_active_hmac_secret(self) -> tuple[str, str]:
        """Return active HMAC version and secret."""
        version = self.ACTIVE_HMAC_KEY_VERSION.strip()
        if not version:
            raise ValueError("ACTIVE_HMAC_KEY_VERSION cannot be empty")

        secret = self.get_hmac_secret(version)
        if not secret:
            raise ValueError(f"TOKEN_HMAC_SECRET_V{version} is required for active HMAC version")
        return version, secret

    def metrics_require_auth(self) -> bool:
        """Return whether /metrics should require explicit exposure controls."""
        if self.METRICS_REQUIRE_AUTH is not None:
            return self.METRICS_REQUIRE_AUTH
        if self.APP_ENV.lower() == "production":
            return not self.METRICS_PUBLIC_IN_PRODUCTION
        return False

    def readyz_include_details(self) -> bool:
        """Return whether /readyz should expose detailed revision information."""
        if self.READYZ_INCLUDE_DETAILS is not None:
            return self.READYZ_INCLUDE_DETAILS
        return self.APP_ENV.lower() != "production"

    def get_metrics_allowed_ips(self) -> tuple[str, ...]:
        """Return normalized IP allowlist entries for /metrics."""
        if not self.METRICS_ALLOWED_IPS:
            return ()
        return tuple(item.strip() for item in self.METRICS_ALLOWED_IPS.split(",") if item.strip())

    def rate_limit_fail_closed(self) -> bool:
        """Return Redis rate-limit failure policy for the current environment."""
        if self.RATE_LIMIT_FAIL_CLOSED is not None:
            return self.RATE_LIMIT_FAIL_CLOSED
        return self.APP_ENV.lower() == "production"

    def admin_session_cookie_secure(self) -> bool:
        """Return whether admin session cookies should use Secure."""
        if self.ADMIN_SESSION_COOKIE_SECURE is not None:
            return self.ADMIN_SESSION_COOKIE_SECURE
        return self.APP_ENV.lower() == "production"

    def get_celery_broker_url(self) -> str | None:
        """Return Celery broker URL, defaulting to Redis when configured."""
        return self.CELERY_BROKER_URL or self.REDIS_URL


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


def is_placeholder_secret(value: str | None) -> bool:
    """Return whether a configured secret is an obvious placeholder."""
    if value is None:
        return False
    normalized = value.strip().lower()
    if not normalized:
        return True
    if normalized in {"test", "sk-test"}:
        return True
    if normalized.startswith("sk-test"):
        return True
    return any(placeholder in normalized for placeholder in _PLACEHOLDER_SECRET_SUBSTRINGS)


def validate_provider_secret_present(name: str, value: str | None) -> None:
    """Validate that an enabled production provider has plausible secret material."""
    if value is None or not value.strip():
        raise ValueError(f"{name} is required in production when the provider is enabled")
    if is_placeholder_secret(value):
        raise ValueError(f"{name} cannot contain placeholder text in production")
    if any(ch.isspace() for ch in value.strip()):
        raise ValueError(f"{name} cannot contain whitespace")
    if len(value.strip()) < _MIN_PROVIDER_SECRET_LENGTH:
        raise ValueError(
            f"{name} must be at least {_MIN_PROVIDER_SECRET_LENGTH} characters in production"
        )


def _validate_audio_option_set(
    raw_value: str,
    *,
    allowed_values: frozenset[str],
    field_name: str,
) -> None:
    parsed = {
        item.strip().lower()
        for item in raw_value.split(",")
        if item.strip()
    }
    if not parsed:
        raise ValueError(f"{field_name} must contain at least one supported value")
    unsupported = sorted(parsed - allowed_values)
    if unsupported:
        joined = ", ".join(unsupported)
        raise ValueError(f"{field_name} contains unsupported values: {joined}")


def _validate_nonempty_csv(raw_value: str, *, field_name: str) -> None:
    parsed = [item.strip() for item in raw_value.split(",") if item.strip()]
    if not parsed:
        raise ValueError(f"{field_name} must contain at least one supported value")


def looks_like_real_upstream_openai_key(
    value: str | None,
    *,
    gateway_prefixes: tuple[str, ...] = ("sk-slaif-",),
) -> bool:
    """Conservatively detect likely server-side provider keys in OPENAI_API_KEY."""
    if value is None:
        return False
    normalized = value.strip()
    if not normalized.startswith("sk-"):
        return False
    if is_placeholder_secret(normalized):
        return False
    if len(normalized) < _MIN_PROVIDER_SECRET_LENGTH:
        return False
    return not any(normalized.startswith(prefix) for prefix in gateway_prefixes)
