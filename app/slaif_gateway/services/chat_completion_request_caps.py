"""Explicit caps and scalar validation for Chat Completions requests."""

from __future__ import annotations

import base64
import binascii
import math
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from slaif_gateway.config import Settings
from slaif_gateway.services.input_token_estimation import canonical_json_bytes
from slaif_gateway.services.policy_errors import RequestPolicyError

_REASONING_EFFORT_VALUES = frozenset({"minimal", "low", "medium", "high"})
_RESPONSE_FORMAT_TYPES = frozenset({"text", "json_object", "json_schema"})
_TOOL_CHOICE_MODES = frozenset({"none", "auto", "required"})
_CUSTOM_FORMAT_TYPES = frozenset({"text", "grammar"})
_CUSTOM_GRAMMAR_SYNTAXES = frozenset({"lark", "regex"})
_IMAGE_DETAIL_VALUES = frozenset({"auto", "low", "high"})
_IMAGE_DATA_URL_PREFIX = "data:"
_SUPPORTED_IMAGE_DATA_URL_MIME_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "image/gif"}
)
_FILE_DATA_URL_PREFIX = "data:"
_FILE_DATA_URL_BASE64_SUFFIX = ";base64"
_AUDIO_DATA_URL_PREFIX = "data:"
_AUDIO_OUTPUT_MODALITY_VALUES = frozenset({"text", "audio"})
_SUPPORTED_AUDIO_OUTPUT_MODALITIES = frozenset({"text", "audio"})
_BASE64_CHARS_RE = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")


class ChatCompletionRequestCapsError(RequestPolicyError):
    """Request-policy error for bounded Chat Completions field validation."""

    def __init__(self, safe_message: str, *, param: str, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(safe_message, param=param)


def enforce_chat_completion_request_caps(
    payload: Mapping[str, Any],
    *,
    settings: Settings,
) -> None:
    """Validate currently supported Chat Completions fields before forwarding.

    Error messages intentionally name only fields and limits. They never include
    raw messages, schemas, metadata values, tool arguments, or request bodies.
    """

    _validate_model(payload.get("model"))
    _validate_messages(payload.get("messages"), settings=settings)
    _validate_scalar_controls(payload, settings=settings)
    _validate_audio_output(payload, settings=settings)
    _validate_stop(payload.get("stop"), settings=settings)
    _validate_user(payload.get("user"), settings=settings)
    _validate_logit_bias(payload.get("logit_bias"), settings=settings)
    _validate_tools(payload.get("tools"), settings=settings)
    _validate_legacy_functions(payload.get("functions"), settings=settings)
    _validate_tool_choice(
        payload.get("tool_choice"),
        tools=payload.get("tools"),
        param="tool_choice",
        settings=settings,
    )
    if payload.get("stream") is True and _uses_custom_tools(payload):
        _raise(
            "stream",
            "chat_streaming_custom_tool_not_supported",
            "Streaming Chat Completions custom tools are not enabled by this gateway.",
        )
    _validate_function_choice(
        payload.get("function_call"),
        param="function_call",
        settings=settings,
    )
    _validate_response_format(payload.get("response_format"), settings=settings)
    _validate_metadata(payload.get("metadata"), settings=settings)
    _validate_prediction(payload.get("prediction"), settings=settings)
    _validate_stream_options(payload.get("stream_options"), settings=settings)


def _validate_model(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        _raise(
            "model",
            "chat_field_invalid_type",
            "The 'model' field must be a non-empty string.",
        )


def _validate_messages(value: Any, *, settings: Settings) -> None:
    if not isinstance(value, list):
        _raise(
            "messages",
            "invalid_messages",
            "The 'messages' field must be a non-empty list.",
        )
    if not value:
        _raise(
            "messages",
            "invalid_messages",
            "The 'messages' field must be a non-empty list.",
        )
    if len(value) > settings.CHAT_MAX_MESSAGES_PER_REQUEST:
        _raise(
            "messages",
            "chat_message_limit_exceeded",
            "The request includes too many Chat Completions messages.",
        )

    total_images = 0
    total_files = 0
    total_audio_inputs = 0
    for message_index, message in enumerate(value):
        if not isinstance(message, Mapping):
            _raise(
                "messages",
                "invalid_messages",
                "Each Chat Completions message must be an object.",
            )
        role = message.get("role")
        if not isinstance(role, str) or not role.strip():
            _raise(
                "messages",
                "invalid_messages",
                "Each Chat Completions message must include a non-empty string role.",
            )
        if role == "assistant" and "audio" in message:
            _raise(
                f"messages[{message_index}].audio",
                "chat_previous_audio_not_supported",
                "Assistant previous-audio references are not enabled by this gateway.",
            )
        _validate_message_content(
            message.get("content"),
            message_index=message_index,
            message_role=role,
            settings=settings,
            total_images_seen=total_images,
            total_files_seen=total_files,
            total_audio_inputs_seen=total_audio_inputs,
        )
        total_images += _count_image_parts(message.get("content"))
        if total_images > settings.CHAT_MAX_IMAGES_PER_REQUEST:
            _raise(
                "messages",
                "chat_image_count_exceeded",
                "The request includes too many Chat Completions image content parts.",
            )
        total_files += _count_file_parts(message.get("content"))
        if total_files > settings.CHAT_MAX_FILES_PER_REQUEST:
            _raise(
                "messages",
                "chat_file_count_exceeded",
                "The request includes too many Chat Completions file content parts.",
            )
        total_audio_inputs += _count_audio_input_parts(message.get("content"))
        if total_audio_inputs > settings.CHAT_MAX_AUDIO_INPUTS_PER_REQUEST:
            _raise(
                "messages",
                "chat_audio_count_exceeded",
                "The request includes too many Chat Completions audio input content parts.",
            )


def _validate_message_content(
    content: Any,
    *,
    message_index: int,
    message_role: str,
    settings: Settings,
    total_images_seen: int,
    total_files_seen: int,
    total_audio_inputs_seen: int,
) -> None:
    if content is None:
        return

    if isinstance(content, str):
        _validate_string_bytes(
            content,
            param=f"messages[{message_index}].content",
            max_bytes=settings.CHAT_MAX_MESSAGE_CONTENT_BYTES,
            error_code="chat_field_too_large",
            safe_message="A Chat Completions message content field exceeds the gateway size limit.",
        )
        return

    if not isinstance(content, list):
        _raise(
            f"messages[{message_index}].content",
            "chat_field_invalid_type",
            "Chat Completions message content must be a string, null, or a list of supported content parts.",
        )

    text_parts = 0
    image_parts = 0
    file_parts = 0
    audio_input_parts = 0
    total_text_bytes = 0
    for part_index, part in enumerate(content):
        if isinstance(part, str):
            text_parts += 1
            total_text_bytes += len(part.encode("utf-8"))
            continue
        if not isinstance(part, Mapping):
            _raise(
                f"messages[{message_index}].content[{part_index}]",
                "chat_field_invalid_type",
                "Chat Completions message content parts must be text strings or text objects.",
            )
        if part.get("type") != "text":
            if part.get("type") == "image_url":
                image_parts += 1
                _validate_image_part(
                    part,
                    message_index=message_index,
                    part_index=part_index,
                    message_role=message_role,
                    settings=settings,
                )
                if image_parts > settings.CHAT_MAX_IMAGES_PER_MESSAGE:
                    _raise(
                        f"messages[{message_index}].content",
                        "chat_image_count_exceeded",
                        "A Chat Completions message includes too many image content parts.",
                    )
                if total_images_seen + image_parts > settings.CHAT_MAX_IMAGES_PER_REQUEST:
                    _raise(
                        "messages",
                        "chat_image_count_exceeded",
                        "The request includes too many Chat Completions image content parts.",
                    )
                continue
            if part.get("type") == "file":
                file_parts += 1
                _validate_file_part(
                    part,
                    message_index=message_index,
                    part_index=part_index,
                    message_role=message_role,
                    settings=settings,
                )
                if file_parts > settings.CHAT_MAX_FILES_PER_MESSAGE:
                    _raise(
                        f"messages[{message_index}].content",
                        "chat_file_count_exceeded",
                        "A Chat Completions message includes too many file content parts.",
                    )
                if total_files_seen + file_parts > settings.CHAT_MAX_FILES_PER_REQUEST:
                    _raise(
                        "messages",
                        "chat_file_count_exceeded",
                        "The request includes too many Chat Completions file content parts.",
                    )
                continue
            if part.get("type") == "input_audio":
                audio_input_parts += 1
                _validate_audio_input_part(
                    part,
                    message_index=message_index,
                    part_index=part_index,
                    message_role=message_role,
                    settings=settings,
                )
                if audio_input_parts > settings.CHAT_MAX_AUDIO_INPUTS_PER_MESSAGE:
                    _raise(
                        f"messages[{message_index}].content",
                        "chat_audio_count_exceeded",
                        "A Chat Completions message includes too many audio input content parts.",
                    )
                if (
                    total_audio_inputs_seen + audio_input_parts
                    > settings.CHAT_MAX_AUDIO_INPUTS_PER_REQUEST
                ):
                    _raise(
                        "messages",
                        "chat_audio_count_exceeded",
                        "The request includes too many Chat Completions audio input content parts.",
                    )
                continue
            _raise(
                f"messages[{message_index}].content[{part_index}].type",
                "chat_field_invalid_type",
                (
                    "Chat Completions message content parts must be text, image_url, "
                    "file, or input_audio objects."
                ),
            )
        text = part.get("text")
        if not isinstance(text, str):
            _raise(
                f"messages[{message_index}].content[{part_index}].text",
                "chat_field_invalid_type",
                "Chat Completions text content parts must include string text.",
            )
        text_parts += 1
        total_text_bytes += len(text.encode("utf-8"))

    if text_parts > settings.CHAT_MAX_TEXT_PARTS_PER_MESSAGE:
        _raise(
            f"messages[{message_index}].content",
            "chat_field_too_many_items",
            "A Chat Completions message includes too many text content parts.",
        )
    if total_text_bytes > settings.CHAT_MAX_MESSAGE_CONTENT_BYTES:
        _raise(
            f"messages[{message_index}].content",
            "chat_field_too_large",
            "A Chat Completions message content field exceeds the gateway size limit.",
        )


def _validate_image_part(
    part: Mapping[str, Any],
    *,
    message_index: int,
    part_index: int,
    message_role: str,
    settings: Settings,
) -> None:
    param = f"messages[{message_index}].content[{part_index}]"
    if message_role != "user":
        _raise(
            f"{param}.type",
            "chat_image_part_invalid_shape",
            "Chat Completions image content parts are supported only on user messages.",
        )

    for key in part:
        if key not in {"type", "image_url"}:
            _raise(
                f"{param}.{key}",
                "chat_image_part_invalid_shape",
                "Image content parts may only include documented Chat Completions image fields.",
            )

    image_url = part.get("image_url")
    if not isinstance(image_url, Mapping):
        _raise(
            f"{param}.image_url",
            "chat_image_part_invalid_shape",
            "Chat Completions image content parts must include an image_url object.",
        )

    for key in image_url:
        if key not in {"url", "detail"}:
            _raise(
                f"{param}.image_url.{key}",
                "chat_image_part_invalid_shape",
                "Image URL objects may only include documented Chat Completions image fields.",
            )

    url = image_url.get("url")
    if not isinstance(url, str) or not url:
        _raise(
            f"{param}.image_url.url",
            "chat_image_url_invalid",
            "Chat Completions image URLs must be non-empty strings.",
        )

    detail = image_url.get("detail")
    if detail is not None and detail not in _IMAGE_DETAIL_VALUES:
        _raise(
            f"{param}.image_url.detail",
            "chat_image_detail_invalid",
            "Chat Completions image detail must be auto, low, or high.",
        )

    if url.startswith(_IMAGE_DATA_URL_PREFIX):
        _validate_image_data_url(url, param=f"{param}.image_url.url", settings=settings)
        return

    _validate_remote_image_url(url, param=f"{param}.image_url.url", settings=settings)


def _validate_image_data_url(value: str, *, param: str, settings: Settings) -> None:
    if not settings.CHAT_ALLOW_IMAGE_DATA_URLS:
        _raise(
            param,
            "chat_image_data_url_not_allowed",
            "Base64 image data URLs are not enabled by this gateway.",
        )

    _validate_string_bytes(
        value,
        param=param,
        max_bytes=settings.CHAT_MAX_IMAGE_DATA_URL_BYTES,
        error_code="chat_image_data_url_too_large",
        safe_message="An image data URL exceeds the gateway size limit.",
    )

    header, separator, encoded = value.partition(",")
    if not separator:
        _raise(param, "chat_image_url_invalid", "Image data URLs must be base64 data URLs.")
    if not header.endswith(";base64"):
        _raise(param, "chat_image_url_invalid", "Image data URLs must use base64 encoding.")

    mime_type = header[len(_IMAGE_DATA_URL_PREFIX) : -len(";base64")].lower()
    if mime_type not in _SUPPORTED_IMAGE_DATA_URL_MIME_TYPES:
        _raise(
            param,
            "chat_image_mime_not_supported",
            "The image data URL MIME type is not supported by this gateway.",
        )
    if not encoded:
        _raise(param, "chat_image_url_invalid", "Image data URLs must include base64 data.")

    try:
        base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ChatCompletionRequestCapsError(
            "Image data URLs must include valid base64 data.",
            param=param,
            error_code="chat_image_url_invalid",
        ) from exc


def _validate_remote_image_url(value: str, *, param: str, settings: Settings) -> None:
    if not settings.CHAT_ALLOW_REMOTE_IMAGE_URLS:
        _raise(
            param,
            "chat_image_url_invalid",
            "Remote image URLs are not enabled by this gateway.",
        )

    _validate_string_bytes(
        value,
        param=param,
        max_bytes=settings.CHAT_MAX_IMAGE_URL_BYTES,
        error_code="chat_image_url_too_large",
        safe_message="An image URL exceeds the gateway size limit.",
    )

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        _raise(param, "chat_image_url_invalid", "Image URLs must use http or https.")
    if parsed.username is not None or parsed.password is not None:
        _raise(
            param,
            "chat_image_url_invalid",
            "Image URLs must not include embedded credentials.",
        )


def _validate_file_part(
    part: Mapping[str, Any],
    *,
    message_index: int,
    part_index: int,
    message_role: str,
    settings: Settings,
) -> None:
    param = f"messages[{message_index}].content[{part_index}]"
    if message_role != "user":
        _raise(
            f"{param}.type",
            "chat_file_part_invalid_shape",
            "Chat Completions file content parts are supported only on user messages.",
        )

    for key in part:
        if key not in {"type", "file"}:
            _raise(
                f"{param}.{key}",
                "chat_file_part_invalid_shape",
                "File content parts may only include documented Chat Completions file fields.",
            )

    file_obj = part.get("file")
    if not isinstance(file_obj, Mapping):
        _raise(
            f"{param}.file",
            "chat_file_part_invalid_shape",
            "Chat Completions file content parts must include a file object.",
        )

    for key in file_obj:
        if key == "url":
            _raise(
                f"{param}.file.url",
                "chat_file_url_not_supported",
                "Chat Completions file URLs are not enabled by this gateway.",
            )
        if key not in {"file_data", "file_id", "filename"}:
            _raise(
                f"{param}.file.{key}",
                "chat_file_part_invalid_shape",
                "File objects may only include documented Chat Completions file fields.",
            )

    has_file_data = "file_data" in file_obj
    has_file_id = "file_id" in file_obj
    file_data = file_obj.get("file_data")
    file_id = file_obj.get("file_id")
    filename = file_obj.get("filename")

    if has_file_data and has_file_id:
        _raise(
            f"{param}.file",
            "chat_file_part_invalid_shape",
            "Chat Completions file inputs must not include both file_data and file_id.",
        )

    if has_file_id:
        if not isinstance(file_id, str) or not file_id:
            _raise(
                f"{param}.file.file_id",
                "chat_file_id_not_supported",
                "Chat Completions file IDs are not enabled by this gateway.",
            )
        if not settings.CHAT_ALLOW_FILE_IDS:
            _raise(
                f"{param}.file.file_id",
                "chat_file_id_not_supported",
                "Chat Completions file IDs are not enabled by this gateway.",
            )
        _raise(
            f"{param}.file.file_id",
            "chat_file_id_not_supported",
            "Chat Completions file IDs require a Files API ownership policy and are not enabled.",
        )

    if not isinstance(filename, str) or not filename:
        _raise(
            f"{param}.file.filename",
            "chat_file_name_invalid",
            "Inline Chat Completions file inputs must include a safe filename.",
        )
    _validate_filename(filename, param=f"{param}.file.filename", settings=settings)

    if not isinstance(file_data, str) or not file_data:
        _raise(
            f"{param}.file.file_data",
            "chat_file_data_invalid",
            "Inline Chat Completions file inputs must include base64 file_data.",
        )

    _validate_file_data(
        file_data,
        filename=filename,
        param=f"{param}.file.file_data",
        settings=settings,
    )


def _validate_filename(value: str, *, param: str, settings: Settings) -> None:
    _validate_string_bytes(
        value,
        param=param,
        max_bytes=settings.CHAT_MAX_FILE_NAME_BYTES,
        error_code="chat_file_name_too_large",
        safe_message="A Chat Completions file name exceeds the gateway size limit.",
    )
    stripped = value.strip()
    if stripped != value or stripped in {"", ".", ".."}:
        _raise(param, "chat_file_name_invalid", "Chat Completions file names must be safe.")
    if any(ch in value for ch in {"/", "\\", ":"}):
        _raise(param, "chat_file_name_invalid", "Chat Completions file names must be safe.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        _raise(param, "chat_file_name_invalid", "Chat Completions file names must be safe.")

    extension = _filename_extension(value)
    if extension not in _allowed_file_extensions(settings):
        _raise(
            param,
            "chat_file_mime_not_supported",
            "The Chat Completions file type is not supported by this gateway.",
        )


def _validate_file_data(
    value: str,
    *,
    filename: str,
    param: str,
    settings: Settings,
) -> None:
    if value.startswith(("http://", "https://")):
        _raise(
            param,
            "chat_file_url_not_supported",
            "Chat Completions file URLs are not enabled by this gateway.",
        )
    if value.startswith(_FILE_DATA_URL_PREFIX):
        _validate_file_data_url(value, filename=filename, param=param, settings=settings)
        return

    _validate_string_bytes(
        value,
        param=param,
        max_bytes=settings.CHAT_MAX_FILE_DATA_BYTES,
        error_code="chat_file_data_too_large",
        safe_message="A Chat Completions file payload exceeds the gateway size limit.",
    )
    _validate_base64_payload(
        value,
        param=param,
        error_code="chat_file_data_invalid",
        safe_message="Chat Completions file data must be valid base64.",
    )


def _validate_file_data_url(
    value: str,
    *,
    filename: str,
    param: str,
    settings: Settings,
) -> None:
    if not settings.CHAT_ALLOW_FILE_DATA_URLS:
        _raise(
            param,
            "chat_file_data_url_not_allowed",
            "File data URLs are not enabled by this gateway.",
        )

    _validate_string_bytes(
        value,
        param=param,
        max_bytes=settings.CHAT_MAX_FILE_DATA_BYTES,
        error_code="chat_file_data_too_large",
        safe_message="A Chat Completions file payload exceeds the gateway size limit.",
    )

    header, separator, encoded = value.partition(",")
    if not separator:
        _raise(param, "chat_file_data_invalid", "File data URLs must include base64 data.")
    if not header.endswith(_FILE_DATA_URL_BASE64_SUFFIX):
        _raise(param, "chat_file_data_invalid", "File data URLs must use base64 encoding.")

    mime_type = header[len(_FILE_DATA_URL_PREFIX) : -len(_FILE_DATA_URL_BASE64_SUFFIX)].lower()
    if mime_type not in _allowed_file_mime_types(settings):
        _raise(
            param,
            "chat_file_mime_not_supported",
            "The Chat Completions file MIME type is not supported by this gateway.",
        )
    if _filename_extension(filename) not in _allowed_file_extensions(settings):
        _raise(
            param,
            "chat_file_mime_not_supported",
            "The Chat Completions file type is not supported by this gateway.",
        )
    if not encoded:
        _raise(param, "chat_file_data_invalid", "File data URLs must include base64 data.")
    _validate_base64_payload(
        encoded,
        param=param,
        error_code="chat_file_data_invalid",
        safe_message="Chat Completions file data must be valid base64.",
    )


def _validate_audio_input_part(
    part: Mapping[str, Any],
    *,
    message_index: int,
    part_index: int,
    message_role: str,
    settings: Settings,
) -> None:
    param = f"messages[{message_index}].content[{part_index}]"
    if message_role != "user":
        _raise(
            f"{param}.type",
            "chat_audio_part_invalid_shape",
            "Chat Completions audio input content parts are supported only on user messages.",
        )

    for key in part:
        if key not in {"type", "input_audio"}:
            _raise(
                f"{param}.{key}",
                "chat_audio_part_invalid_shape",
                "Audio input content parts may only include documented Chat Completions audio fields.",
            )

    input_audio = part.get("input_audio")
    if not isinstance(input_audio, Mapping):
        _raise(
            f"{param}.input_audio",
            "chat_audio_part_invalid_shape",
            "Chat Completions audio input content parts must include an input_audio object.",
        )

    for key in input_audio:
        if key not in {"data", "format"}:
            _raise(
                f"{param}.input_audio.{key}",
                "chat_audio_part_invalid_shape",
                "Audio input objects may only include documented Chat Completions audio fields.",
            )

    data = input_audio.get("data")
    if not isinstance(data, str) or not data:
        _raise(
            f"{param}.input_audio.data",
            "chat_audio_data_invalid",
            "Chat Completions audio input must include base64 audio data.",
        )

    audio_format = input_audio.get("format")
    if not isinstance(audio_format, str) or not audio_format:
        _raise(
            f"{param}.input_audio.format",
            "chat_audio_format_invalid",
            "Chat Completions audio input must include an audio format.",
        )
    if audio_format not in _allowed_audio_input_formats(settings):
        _raise(
            f"{param}.input_audio.format",
            "chat_audio_format_not_supported",
            "The Chat Completions audio input format is not supported by this gateway.",
        )

    _validate_audio_input_data(
        data,
        param=f"{param}.input_audio.data",
        settings=settings,
    )


def _validate_audio_input_data(value: str, *, param: str, settings: Settings) -> None:
    if value.startswith(("http://", "https://")):
        _raise(
            param,
            "chat_audio_url_not_supported",
            "Chat Completions audio URLs are not enabled by this gateway.",
        )
    if value.startswith(_AUDIO_DATA_URL_PREFIX):
        _validate_audio_data_url(value, param=param, settings=settings)
        return

    _validate_string_bytes(
        value,
        param=param,
        max_bytes=settings.CHAT_MAX_AUDIO_INPUT_DATA_BYTES,
        error_code="chat_audio_data_too_large",
        safe_message="A Chat Completions audio input payload exceeds the gateway size limit.",
    )
    _validate_base64_payload(
        value,
        param=param,
        error_code="chat_audio_data_invalid",
        safe_message="Chat Completions audio input data must be valid base64.",
    )


def _validate_audio_data_url(value: str, *, param: str, settings: Settings) -> None:
    _ = settings
    _raise(
        param,
        "chat_audio_data_url_not_allowed",
        "Audio input data URLs are not enabled by this gateway.",
    )


def _validate_base64_payload(
    value: str,
    *,
    param: str,
    error_code: str,
    safe_message: str,
) -> None:
    normalized = "".join(value.split())
    if not normalized or len(normalized) % 4 != 0 or not _BASE64_CHARS_RE.fullmatch(normalized):
        _raise(param, error_code, safe_message)
    try:
        base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ChatCompletionRequestCapsError(
            safe_message,
            param=param,
            error_code=error_code,
        ) from exc


def _filename_extension(value: str) -> str:
    dot_index = value.rfind(".")
    if dot_index <= 0 or dot_index == len(value) - 1:
        return ""
    return value[dot_index:].lower()


def _allowed_file_extensions(settings: Settings) -> frozenset[str]:
    return frozenset(
        item.strip().lower()
        for item in settings.CHAT_ALLOWED_FILE_EXTENSIONS.split(",")
        if item.strip()
    )


def _allowed_file_mime_types(settings: Settings) -> frozenset[str]:
    return frozenset(
        item.strip().lower()
        for item in settings.CHAT_ALLOWED_FILE_MIME_TYPES.split(",")
        if item.strip()
    )


def _allowed_audio_input_formats(settings: Settings) -> frozenset[str]:
    return frozenset(
        item.strip().lower()
        for item in settings.CHAT_ALLOWED_AUDIO_INPUT_FORMATS.split(",")
        if item.strip()
    )


def _allowed_audio_output_formats(settings: Settings) -> frozenset[str]:
    return frozenset(
        item.strip().lower()
        for item in settings.CHAT_ALLOWED_AUDIO_OUTPUT_FORMATS.split(",")
        if item.strip()
    )


def _allowed_audio_output_voices(settings: Settings) -> frozenset[str]:
    return frozenset(
        item.strip().lower()
        for item in settings.CHAT_ALLOWED_AUDIO_OUTPUT_VOICES.split(",")
        if item.strip()
    )


def _validate_audio_output(payload: Mapping[str, Any], *, settings: Settings) -> None:
    modalities = payload.get("modalities")
    audio = payload.get("audio")

    audio_requested = False
    if modalities is not None:
        if not isinstance(modalities, list) or not modalities:
            _raise(
                "modalities",
                "chat_audio_modality_invalid",
                "Chat Completions modalities must be a non-empty list of strings.",
            )
        seen: set[str] = set()
        for index, item in enumerate(modalities):
            if not isinstance(item, str) or not item:
                _raise(
                    f"modalities[{index}]",
                    "chat_audio_modality_invalid",
                    "Chat Completions modalities must be strings.",
                )
            if item in seen:
                _raise(
                    f"modalities[{index}]",
                    "chat_audio_modality_invalid",
                    "Chat Completions modalities must not contain duplicates.",
                )
            seen.add(item)
            if item not in _AUDIO_OUTPUT_MODALITY_VALUES:
                _raise(
                    f"modalities[{index}]",
                    "chat_audio_modality_not_supported",
                    "Only text and audio Chat Completions modalities are recognized by this gateway.",
                )
        if "audio" in seen:
            audio_requested = True
            if seen != _SUPPORTED_AUDIO_OUTPUT_MODALITIES:
                _raise(
                    "modalities",
                    "chat_audio_modality_not_supported",
                    "Audio output requires Chat Completions modalities to be text and audio.",
                )

    if audio is not None and not audio_requested:
        _raise(
            "audio",
            "chat_audio_output_config_invalid",
            "Chat Completions audio output config requires modalities to request audio output.",
        )

    if not audio_requested:
        return

    if payload.get("stream") is True:
        _raise(
            "stream",
            "chat_streaming_audio_output_not_supported",
            "Streaming Chat Completions audio output is not supported by this gateway.",
        )

    n = payload.get("n")
    if (
        isinstance(n, int)
        and not isinstance(n, bool)
        and n > 1
        and not settings.CHAT_ALLOW_AUDIO_OUTPUT_WITH_N_CHOICES
    ):
        _raise(
            "n",
            "chat_audio_output_multiple_choices_not_supported",
            "Multiple Chat Completions choices with audio output are not enabled by this gateway.",
        )

    if not isinstance(audio, Mapping):
        _raise(
            "audio",
            "chat_audio_output_config_invalid",
            "Chat Completions audio output requires an audio config object.",
        )

    for key in audio:
        if key not in {"format", "voice"}:
            _raise(
                f"audio.{key}",
                "chat_audio_output_config_invalid",
                "Audio output config may only include documented Chat Completions audio fields.",
            )

    audio_format = audio.get("format")
    if not isinstance(audio_format, str) or not audio_format:
        _raise(
            "audio.format",
            "chat_audio_output_format_not_supported",
            "Chat Completions audio output must include a supported audio format.",
        )
    if audio_format not in _allowed_audio_output_formats(settings):
        _raise(
            "audio.format",
            "chat_audio_output_format_not_supported",
            "The Chat Completions audio output format is not supported by this gateway.",
        )

    voice = audio.get("voice")
    if isinstance(voice, Mapping):
        if not settings.CHAT_ALLOW_CUSTOM_AUDIO_OUTPUT_VOICES:
            _raise(
                "audio.voice",
                "chat_audio_output_custom_voice_not_supported",
                "Custom Chat Completions audio output voices are not enabled by this gateway.",
            )
        _raise(
            "audio.voice",
            "chat_audio_output_custom_voice_not_supported",
            "Custom Chat Completions audio output voices require a separate policy.",
        )
    if not isinstance(voice, str) or not voice:
        _raise(
            "audio.voice",
            "chat_audio_output_voice_not_supported",
            "Chat Completions audio output must include a supported voice.",
        )
    if voice not in _allowed_audio_output_voices(settings):
        _raise(
            "audio.voice",
            "chat_audio_output_voice_not_supported",
            "The Chat Completions audio output voice is not supported by this gateway.",
        )


def _count_image_parts(content: Any) -> int:
    if not isinstance(content, list):
        return 0
    return sum(
        1
        for part in content
        if isinstance(part, Mapping) and part.get("type") == "image_url"
    )


def _count_file_parts(content: Any) -> int:
    if not isinstance(content, list):
        return 0
    return sum(1 for part in content if isinstance(part, Mapping) and part.get("type") == "file")


def _count_audio_input_parts(content: Any) -> int:
    if not isinstance(content, list):
        return 0
    return sum(
        1
        for part in content
        if isinstance(part, Mapping) and part.get("type") == "input_audio"
    )


def _validate_scalar_controls(payload: Mapping[str, Any], *, settings: Settings) -> None:
    _validate_number_range(
        payload.get("temperature"),
        param="temperature",
        minimum=0,
        maximum=2,
    )
    _validate_number_range(payload.get("top_p"), param="top_p", minimum=0, maximum=1)
    _validate_number_range(
        payload.get("presence_penalty"),
        param="presence_penalty",
        minimum=-2,
        maximum=2,
    )
    _validate_number_range(
        payload.get("frequency_penalty"),
        param="frequency_penalty",
        minimum=-2,
        maximum=2,
    )
    _validate_bool(payload.get("stream"), param="stream")
    _validate_bool(payload.get("logprobs"), param="logprobs")
    _validate_bool(payload.get("parallel_tool_calls"), param="parallel_tool_calls")

    seed = payload.get("seed")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        _raise("seed", "chat_field_invalid_type", "The 'seed' field must be an integer.")

    top_logprobs = payload.get("top_logprobs")
    if top_logprobs is not None:
        if isinstance(top_logprobs, bool) or not isinstance(top_logprobs, int):
            _raise(
                "top_logprobs",
                "chat_field_invalid_type",
                "The 'top_logprobs' field must be an integer.",
            )
        if top_logprobs < 0 or top_logprobs > 20:
            _raise(
                "top_logprobs",
                "chat_field_value_out_of_range",
                "The 'top_logprobs' field must be between 0 and 20.",
            )
        if payload.get("logprobs") is not True:
            _raise(
                "top_logprobs",
                "chat_field_value_out_of_range",
                "The 'top_logprobs' field requires 'logprobs' to be true.",
            )

    n = payload.get("n")
    if n is not None:
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            _raise(
                "n",
                "chat_choice_count_invalid",
                "The 'n' field must be a positive integer.",
            )
        if n > settings.CHAT_MAX_CHOICES_PER_REQUEST:
            _raise(
                "n",
                "chat_choice_count_limit_exceeded",
                (
                    "The 'n' field exceeds the configured maximum number of "
                    "Chat Completions choices."
                ),
            )

    reasoning_effort = payload.get("reasoning_effort")
    if reasoning_effort is not None:
        if not isinstance(reasoning_effort, str) or reasoning_effort not in _REASONING_EFFORT_VALUES:
            _raise(
                "reasoning_effort",
                "chat_field_value_out_of_range",
                "The 'reasoning_effort' field must be one of: minimal, low, medium, high.",
            )


def _validate_number_range(
    value: Any,
    *,
    param: str,
    minimum: float,
    maximum: float,
) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int | float):
        _raise(param, "chat_field_invalid_type", f"The '{param}' field must be a number.")
    if not math.isfinite(float(value)) or value < minimum or value > maximum:
        _raise(
            param,
            "chat_field_value_out_of_range",
            f"The '{param}' field is outside the supported range.",
        )


def _validate_bool(value: Any, *, param: str) -> None:
    if value is not None and not isinstance(value, bool):
        _raise(param, "chat_field_invalid_type", f"The '{param}' field must be a boolean.")


def _validate_logit_bias(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        _raise(
            "logit_bias",
            "chat_field_invalid_type",
            "The 'logit_bias' field must be a JSON object.",
        )
    if _json_size(value, param="logit_bias") > settings.CHAT_MAX_LOGIT_BIAS_BYTES:
        _raise(
            "logit_bias",
            "chat_field_too_large",
            "The 'logit_bias' field exceeds the gateway size limit.",
        )
    for key, bias in value.items():
        if not isinstance(key, str):
            _raise(
                "logit_bias",
                "chat_field_invalid_type",
                "The 'logit_bias' field must use string token IDs as keys.",
            )
        if isinstance(bias, bool) or not isinstance(bias, int | float):
            _raise(
                "logit_bias",
                "chat_field_invalid_type",
                "The 'logit_bias' field values must be numbers.",
            )
        if not math.isfinite(float(bias)) or bias < -100 or bias > 100:
            _raise(
                "logit_bias",
                "chat_field_value_out_of_range",
                "The 'logit_bias' field values must be between -100 and 100.",
            )


def _validate_stop(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    sequences: list[str]
    if isinstance(value, str):
        sequences = [value]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        sequences = value
    else:
        _raise(
            "stop",
            "chat_field_invalid_type",
            "The 'stop' field must be a string or a list of strings.",
        )

    if len(sequences) > settings.CHAT_MAX_STOP_SEQUENCES:
        _raise(
            "stop",
            "chat_stop_sequence_limit_exceeded",
            "The 'stop' field includes too many stop sequences.",
        )
    for sequence in sequences:
        _validate_string_bytes(
            sequence,
            param="stop",
            max_bytes=settings.CHAT_MAX_STOP_SEQUENCE_BYTES,
            error_code="chat_field_too_large",
            safe_message="A stop sequence exceeds the gateway size limit.",
        )


def _validate_user(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        _raise("user", "chat_field_invalid_type", "The 'user' field must be a string.")
    _validate_string_bytes(
        value,
        param="user",
        max_bytes=settings.CHAT_MAX_USER_FIELD_BYTES,
        error_code="chat_field_too_large",
        safe_message="The 'user' field exceeds the gateway size limit.",
    )


def _validate_tools(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        _raise("tools", "chat_field_invalid_type", "The 'tools' field must be a list.")
    if len(value) > settings.CHAT_MAX_TOOLS_PER_REQUEST:
        _raise(
            "tools",
            "chat_tool_count_exceeded",
            "The request includes too many Chat Completions tools.",
        )
    total_schema_bytes = 0
    custom_tools = 0
    for index, tool in enumerate(value):
        if not isinstance(tool, Mapping):
            _raise(f"tools[{index}]", "chat_field_invalid_type", "Each tool must be an object.")
        tool_type = tool.get("type")
        if tool_type == "custom":
            custom_tools += 1
            _validate_custom_tool(tool, param_prefix=f"tools[{index}]", settings=settings)
            continue
        if tool_type != "function":
            continue
        function = tool.get("function")
        total_schema_bytes += _validate_function_definition(
            function,
            param_prefix=f"tools[{index}].function",
            settings=settings,
        )
    if custom_tools > settings.CHAT_MAX_CUSTOM_TOOLS_PER_REQUEST:
        _raise(
            "tools",
            "chat_custom_tool_count_exceeded",
            "The request includes too many Chat Completions custom tools.",
        )
    if total_schema_bytes > settings.CHAT_MAX_TOTAL_TOOL_SCHEMA_BYTES:
        _raise(
            "tools",
            "chat_tool_schema_too_large",
            "The total function-tool schema size exceeds the gateway size limit.",
        )


def _validate_legacy_functions(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        _raise(
            "functions",
            "chat_field_invalid_type",
            "The 'functions' field must be a list.",
        )
    if len(value) > settings.CHAT_MAX_FUNCTIONS_PER_REQUEST:
        _raise(
            "functions",
            "chat_tool_count_exceeded",
            "The request includes too many legacy Chat Completions functions.",
        )
    total_schema_bytes = 0
    for index, function in enumerate(value):
        total_schema_bytes += _validate_function_definition(
            function,
            param_prefix=f"functions[{index}]",
            settings=settings,
        )
    if total_schema_bytes > settings.CHAT_MAX_TOTAL_TOOL_SCHEMA_BYTES:
        _raise(
            "functions",
            "chat_tool_schema_too_large",
            "The total legacy function schema size exceeds the gateway size limit.",
        )


def _validate_function_definition(
    value: Any,
    *,
    param_prefix: str,
    settings: Settings,
) -> int:
    if not isinstance(value, Mapping):
        _raise(
            param_prefix,
            "chat_field_invalid_type",
            "Function tools must include a function object.",
        )
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        _raise(
            f"{param_prefix}.name",
            "chat_field_invalid_type",
            "Function tool names must be non-empty strings.",
        )
    _validate_string_bytes(
        name,
        param=f"{param_prefix}.name",
        max_bytes=settings.CHAT_MAX_TOOL_NAME_BYTES,
        error_code="chat_field_too_large",
        safe_message="A function tool name exceeds the gateway size limit.",
    )
    description = value.get("description")
    if description is not None:
        if not isinstance(description, str):
            _raise(
                f"{param_prefix}.description",
                "chat_field_invalid_type",
                "Function tool descriptions must be strings.",
            )
        _validate_string_bytes(
            description,
            param=f"{param_prefix}.description",
            max_bytes=settings.CHAT_MAX_TOOL_DESCRIPTION_BYTES,
            error_code="chat_field_too_large",
            safe_message="A function tool description exceeds the gateway size limit.",
        )
    parameters = value.get("parameters")
    if parameters is None:
        return 0
    if not isinstance(parameters, Mapping):
        _raise(
            f"{param_prefix}.parameters",
            "chat_field_invalid_type",
            "Function tool parameters must be a JSON object.",
        )
    size = _json_size(parameters, param=f"{param_prefix}.parameters")
    if size > settings.CHAT_MAX_SINGLE_TOOL_SCHEMA_BYTES:
        _raise(
            f"{param_prefix}.parameters",
            "chat_tool_schema_too_large",
            "A function tool schema exceeds the gateway size limit.",
        )
    return size


def _validate_custom_tool(
    value: Mapping[str, Any],
    *,
    param_prefix: str,
    settings: Settings,
) -> None:
    allowed_tool_keys = {"type", "custom"}
    for key in value:
        if key not in allowed_tool_keys:
            _raise(
                f"{param_prefix}.{key}",
                "chat_custom_tool_invalid_shape",
                "Custom tools may only include documented Chat Completions custom-tool fields.",
            )

    custom = value.get("custom")
    if not isinstance(custom, Mapping):
        _raise(
            f"{param_prefix}.custom",
            "chat_custom_tool_invalid_shape",
            "Custom tools must include a custom object.",
        )

    allowed_custom_keys = {"name", "description", "format"}
    for key in custom:
        if key not in allowed_custom_keys:
            _raise(
                f"{param_prefix}.custom.{key}",
                "chat_custom_tool_invalid_shape",
                "Custom tools may only include documented Chat Completions custom-tool fields.",
            )

    name = custom.get("name")
    if not isinstance(name, str) or not name.strip():
        _raise(
            f"{param_prefix}.custom.name",
            "chat_custom_tool_invalid_type",
            "Custom tool names must be non-empty strings.",
        )
    _validate_string_bytes(
        name,
        param=f"{param_prefix}.custom.name",
        max_bytes=settings.CHAT_MAX_CUSTOM_TOOL_NAME_BYTES,
        error_code="chat_custom_tool_too_large",
        safe_message="A custom tool name exceeds the gateway size limit.",
    )

    description = custom.get("description")
    if description is not None:
        if not isinstance(description, str):
            _raise(
                f"{param_prefix}.custom.description",
                "chat_custom_tool_invalid_type",
                "Custom tool descriptions must be strings.",
            )
        _validate_string_bytes(
            description,
            param=f"{param_prefix}.custom.description",
            max_bytes=settings.CHAT_MAX_CUSTOM_TOOL_DESCRIPTION_BYTES,
            error_code="chat_custom_tool_too_large",
            safe_message="A custom tool description exceeds the gateway size limit.",
        )

    custom_format = custom.get("format")
    if custom_format is not None:
        _validate_custom_tool_format(
            custom_format,
            param_prefix=f"{param_prefix}.custom.format",
            settings=settings,
        )


def _validate_custom_tool_format(
    value: Any,
    *,
    param_prefix: str,
    settings: Settings,
) -> None:
    if not isinstance(value, Mapping):
        _raise(
            param_prefix,
            "chat_custom_tool_invalid_shape",
            "Custom tool format must be an object.",
        )
    if _json_size(value, param=param_prefix) > settings.CHAT_MAX_CUSTOM_TOOL_FORMAT_BYTES:
        _raise(
            param_prefix,
            "chat_custom_tool_too_large",
            "A custom tool format exceeds the gateway size limit.",
        )

    format_type = value.get("type")
    if format_type not in _CUSTOM_FORMAT_TYPES:
        _raise(
            f"{param_prefix}.type",
            "chat_custom_tool_format_not_supported",
            "Custom tool format type is not supported by this gateway.",
        )

    if format_type == "text":
        if set(value) != {"type"}:
            _raise(
                param_prefix,
                "chat_custom_tool_invalid_shape",
                "Text custom tool format may only include documented fields.",
            )
        return

    allowed_format_keys = {"type", "grammar"}
    for key in value:
        if key not in allowed_format_keys:
            _raise(
                f"{param_prefix}.{key}",
                "chat_custom_tool_invalid_shape",
                "Grammar custom tool format may only include documented fields.",
            )

    grammar = value.get("grammar")
    if not isinstance(grammar, Mapping):
        _raise(
            f"{param_prefix}.grammar",
            "chat_custom_tool_invalid_shape",
            "Grammar custom tool format must include a grammar object.",
        )
    for key in grammar:
        if key not in {"definition", "syntax"}:
            _raise(
                f"{param_prefix}.grammar.{key}",
                "chat_custom_tool_invalid_shape",
                "Custom tool grammar may only include documented fields.",
            )
    syntax = grammar.get("syntax")
    if syntax not in _CUSTOM_GRAMMAR_SYNTAXES:
        _raise(
            f"{param_prefix}.grammar.syntax",
            "chat_custom_tool_format_not_supported",
            "Custom tool grammar syntax is not supported by this gateway.",
        )
    definition = grammar.get("definition")
    if not isinstance(definition, str):
        _raise(
            f"{param_prefix}.grammar.definition",
            "chat_custom_tool_invalid_type",
            "Custom tool grammar definition must be a string.",
        )
    _validate_string_bytes(
        definition,
        param=f"{param_prefix}.grammar.definition",
        max_bytes=settings.CHAT_MAX_CUSTOM_TOOL_GRAMMAR_BYTES,
        error_code="chat_custom_tool_grammar_too_large",
        safe_message="A custom tool grammar definition exceeds the gateway size limit.",
    )


def _validate_tool_choice(
    value: Any,
    *,
    tools: Any,
    param: str,
    settings: Settings,
) -> None:
    if value is None:
        return
    if isinstance(value, str):
        if value not in _TOOL_CHOICE_MODES:
            _raise(
                param,
                "chat_custom_tool_choice_invalid",
                "The 'tool_choice' field must be none, auto, required, or a supported tool choice object.",
            )
        return
    if not isinstance(value, Mapping):
        _raise(param, "chat_field_invalid_type", f"The '{param}' field must be a string or object.")

    choice_type = value.get("type")
    if choice_type == "function":
        _validate_function_choice(value, param=param, settings=settings)
        return
    if choice_type == "custom":
        _validate_custom_tool_choice(value, tools=tools, param=param, settings=settings)
        return
    if choice_type is not None:
        return

    _raise(
        param,
        "chat_custom_tool_choice_invalid",
        "The 'tool_choice' field must use a supported Chat Completions tool-choice shape.",
    )


def _validate_custom_tool_choice(
    value: Mapping[str, Any],
    *,
    tools: Any,
    param: str,
    settings: Settings,
) -> None:
    for key in value:
        if key not in {"type", "custom"}:
            _raise(
                f"{param}.{key}",
                "chat_custom_tool_choice_invalid",
                "Custom tool choice may only include documented fields.",
            )
    custom = value.get("custom")
    if not isinstance(custom, Mapping):
        _raise(
            f"{param}.custom",
            "chat_custom_tool_choice_invalid",
            "Custom tool choice must include a custom object.",
        )
    for key in custom:
        if key != "name":
            _raise(
                f"{param}.custom.{key}",
                "chat_custom_tool_choice_invalid",
                "Custom tool choice may only include documented fields.",
            )
    name = custom.get("name")
    if not isinstance(name, str) or not name.strip():
        _raise(
            f"{param}.custom.name",
            "chat_custom_tool_choice_invalid",
            "Custom tool choice names must be non-empty strings.",
        )
    _validate_string_bytes(
        name,
        param=f"{param}.custom.name",
        max_bytes=settings.CHAT_MAX_CUSTOM_TOOL_NAME_BYTES,
        error_code="chat_custom_tool_choice_invalid",
        safe_message="A custom tool choice name exceeds the gateway size limit.",
    )
    if name not in _declared_custom_tool_names(tools):
        _raise(
            f"{param}.custom.name",
            "chat_custom_tool_choice_invalid",
            "Custom tool choice must reference a declared custom tool.",
        )


def _declared_custom_tool_names(tools: Any) -> set[str]:
    names: set[str] = set()
    if not isinstance(tools, list):
        return names
    for tool in tools:
        if not isinstance(tool, Mapping) or tool.get("type") != "custom":
            continue
        custom = tool.get("custom")
        if not isinstance(custom, Mapping):
            continue
        name = custom.get("name")
        if isinstance(name, str):
            names.add(name)
    return names


def _uses_custom_tools(payload: Mapping[str, Any]) -> bool:
    tools = payload.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, Mapping) and tool.get("type") == "custom":
                return True
    tool_choice = payload.get("tool_choice")
    return isinstance(tool_choice, Mapping) and tool_choice.get("type") == "custom"


def _validate_function_choice(
    value: Any,
    *,
    param: str,
    settings: Settings,
) -> None:
    if value is None:
        return
    if isinstance(value, str):
        return
    if not isinstance(value, Mapping):
        _raise(param, "chat_field_invalid_type", f"The '{param}' field must be a string or object.")
    if _json_size(value, param=param) > settings.CHAT_MAX_SINGLE_TOOL_SCHEMA_BYTES:
        _raise(
            param,
            "chat_tool_schema_too_large",
            f"The '{param}' field exceeds the gateway size limit.",
        )
    function = value.get("function")
    if function is not None:
        if not isinstance(function, Mapping):
            _raise(
                f"{param}.function",
                "chat_field_invalid_type",
                f"The '{param}.function' field must be an object.",
            )
        name = function.get("name")
        if name is not None:
            if not isinstance(name, str) or not name.strip():
                _raise(
                    f"{param}.function.name",
                    "chat_field_invalid_type",
                    "Function choice names must be non-empty strings.",
                )
            _validate_string_bytes(
                name,
                param=f"{param}.function.name",
                max_bytes=settings.CHAT_MAX_TOOL_NAME_BYTES,
                error_code="chat_field_too_large",
                safe_message="A function choice name exceeds the gateway size limit.",
            )
    name = value.get("name")
    if name is not None:
        if not isinstance(name, str) or not name.strip():
            _raise(
                f"{param}.name",
                "chat_field_invalid_type",
                "Function choice names must be non-empty strings.",
            )
        _validate_string_bytes(
            name,
            param=f"{param}.name",
            max_bytes=settings.CHAT_MAX_TOOL_NAME_BYTES,
            error_code="chat_field_too_large",
            safe_message="A function choice name exceeds the gateway size limit.",
        )


def _validate_response_format(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        _raise(
            "response_format",
            "chat_field_invalid_type",
            "The 'response_format' field must be a JSON object.",
        )
    response_type = value.get("type")
    if response_type not in _RESPONSE_FORMAT_TYPES:
        _raise(
            "response_format.type",
            "chat_field_value_out_of_range",
            "The 'response_format.type' field must be text, json_object, or json_schema.",
        )
    if response_type == "json_schema":
        json_schema = value.get("json_schema")
        if not isinstance(json_schema, Mapping):
            _raise(
                "response_format.json_schema",
                "chat_field_invalid_type",
                "The 'response_format.json_schema' field must be a JSON object.",
            )
        if _json_size(json_schema, param="response_format.json_schema") > settings.CHAT_MAX_RESPONSE_FORMAT_SCHEMA_BYTES:
            _raise(
                "response_format.json_schema",
                "chat_response_format_schema_too_large",
                "The response format JSON schema exceeds the gateway size limit.",
            )


def _validate_metadata(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        _raise(
            "metadata",
            "chat_field_invalid_type",
            "The 'metadata' field must be a JSON object.",
        )
    if len(value) > settings.CHAT_MAX_METADATA_KEYS:
        _raise(
            "metadata",
            "chat_field_too_many_items",
            "The 'metadata' field includes too many keys.",
        )
    for key in value:
        if not isinstance(key, str):
            _raise(
                "metadata",
                "chat_field_invalid_type",
                "The 'metadata' field must use string keys.",
            )
        _validate_string_bytes(
            key,
            param="metadata",
            max_bytes=settings.CHAT_MAX_METADATA_KEY_BYTES,
            error_code="chat_field_too_large",
            safe_message="A metadata key exceeds the gateway size limit.",
        )
    if _json_size(value, param="metadata") > settings.CHAT_MAX_METADATA_BYTES:
        _raise(
            "metadata",
            "chat_metadata_too_large",
            "The 'metadata' field exceeds the gateway size limit.",
        )


def _validate_prediction(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        _raise(
            "prediction",
            "chat_field_invalid_type",
            "The 'prediction' field must be a JSON object.",
        )
    if _json_size(value, param="prediction") > settings.CHAT_MAX_PREDICTION_BYTES:
        _raise(
            "prediction",
            "chat_field_too_large",
            "The 'prediction' field exceeds the gateway size limit.",
        )


def _validate_stream_options(value: Any, *, settings: Settings) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        _raise(
            "stream_options",
            "invalid_stream_options",
            "The 'stream_options' field must be a JSON object.",
        )
    if _json_size(value, param="stream_options") > settings.CHAT_MAX_STREAM_OPTIONS_BYTES:
        _raise(
            "stream_options",
            "chat_field_too_large",
            "The 'stream_options' field exceeds the gateway size limit.",
        )


def _json_size(value: Any, *, param: str) -> int:
    try:
        return len(canonical_json_bytes(value))
    except ValueError as exc:
        raise ChatCompletionRequestCapsError(
            f"The '{param}' field must be JSON-serializable.",
            param=param,
            error_code="chat_field_invalid_type",
        ) from exc


def _validate_string_bytes(
    value: str,
    *,
    param: str,
    max_bytes: int,
    error_code: str,
    safe_message: str,
) -> None:
    if len(value.encode("utf-8")) > max_bytes:
        _raise(param, error_code, safe_message)


def _raise(param: str, error_code: str, safe_message: str) -> None:
    raise ChatCompletionRequestCapsError(
        safe_message,
        param=param,
        error_code=error_code,
    )
