"""Content-preserving masking for operator request-capture artifacts.

This module is a *pure* masker: it takes the original ordered request
headers, raw path/query bytes, raw body bytes, and the accepted gateway-key
prefixes, and returns masked bytes plus a safe recognition hint and metadata.

Design constraints (objective 191, R5):

* **Full-content-preserving**, not a generic content-dropping sanitizer.
  Non-secret bytes (prompts, instructions, schemas, tool arguments/results,
  IDs, session metadata, unknown fields, malformed input) are preserved
  exactly. Only values identified as incoming authentication secrets are
  replaced.
* Secrets are discovered *structurally* from known credential-bearing
  locations: credential headers (Authorization / Proxy-Authorization,
  cookies, and known credential headers such as ``X-API-Key``), known
  credential query parameters, and known credential JSON fields. Arbitrary
  prose that merely mentions a field word is never treated as a secret, and
  context identifiers (``session``/``session_id``/``nonce``/``signature``)
  are preserved, not masked.
* Each discovered secret is masked in every representation it may repeat in:
  raw bytes, percent-encoded (URL, any case/coverage), and JSON-escaped in
  any mix of raw/``\\uXXXX``/escaped-special forms (including escaped
  backslashes). Query values are masked by decoding first, so fully or
  partially percent-encoded copies cannot survive.
* Only a genuinely well-formed, sufficiently long gateway bearer (validated
  by the shared :func:`slaif_gateway.utils.crypto.parse_gateway_key_public_id`)
  receives a recognition hint: the accepted prefix plus the first eight
  public-ID characters plus a masked suffix. Short, malformed, or
  unrecognized credentials are replaced by a fixed token that reveals no
  segment.
* The masker never inspects server-side environment, provider, or key
  material; it only sees the incoming request bytes handed to it.
* If masking cannot be performed safely (pathological secret set, unsafe
  pattern, cap exceeded), it raises :class:`CaptureRedactionError` carrying
  no request content, so the caller can fail the capture while preserving
  ordinary application behavior.

No filesystem, HTTP, ASGI, or CLI behavior lives here.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from urllib.parse import quote_from_bytes, unquote_to_bytes

from slaif_gateway.utils.crypto import parse_gateway_key_public_id

__all__ = [
    "CaptureRedactionError",
    "CaptureRedactionResult",
    "CREDENTIAL_FIELD_NAMES",
    "CREDENTIAL_HEADER_NAMES",
    "build_capture_masker",
    "collect_incoming_secrets",
    "gateway_bearer_hint",
    "redact_capture_request",
]


class CaptureRedactionError(ValueError):
    """Masking could not be completed safely.

    The message is fixed and low-detail; it never contains request content.
    """

    def __init__(self, reason: str = "capture_redaction_unsafe") -> None:
        super().__init__(reason)
        self.reason = reason


# Context identifiers / session metadata. Values under these names are NOT
# authentication secrets and are preserved (never masked).
_IDENTIFIER_FIELD_NAMES: frozenset[str] = frozenset(
    {"session", "sessionid", "nonce", "signature", "sig"}
)

# Narrow, context-specific credential field names for query parameters and
# JSON fields. Matching is structural: a value is only a secret when its key
# normalizes to one of these names.
CREDENTIAL_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "apikey",
        "key",
        "token",
        "accesstoken",
        "refreshtoken",
        "authtoken",
        "idtoken",
        "apitoken",
        "sessiontoken",
        "password",
        "passwd",
        "secret",
        "clientsecret",
        "privatekey",
        "authorization",
        "auth",
        "credential",
        "credentials",
        "bearer",
    }
)

# Header names whose value is an incoming credential.
CREDENTIAL_HEADER_NAMES: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "x-api-key",
        "x-auth-token",
        "x-csrf-token",
        "x-csrftoken",
        "x-api-token",
        "x-access-token",
        "x-refresh-token",
        "x-auth",
        "apikey",
        "api-key",
        "token",
        "x-token",
    }
)

_FULLY_REDACTED = b"[REDACTED]"


# Safety caps so a pathological secret set cannot turn masking into an
# unbounded or unsafe operation. Exceeding them fails the capture safely.
_MAX_SECRET_VALUES = 256
_MAX_SECRET_BYTES = 65_536
_MAX_TOTAL_PATTERN_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class CaptureRedactionResult:
    """Masked request bytes plus safe masking metadata.

    ``path``/``query``/``body`` and each header name and value are the masked
    raw bytes. ``headers`` preserves the original order and names.
    ``recognized_hint`` is the display prefix for a recognized gateway bearer
    (or ``None``). ``notes`` are stable, content-free markers.
    """

    path: bytes
    query: bytes
    headers: tuple[tuple[str, bytes], ...]
    body: bytes
    body_complete: bool
    secrets_masked: int
    recognized_hint: str | None
    notes: tuple[str, ...]


def _normalize_field_name(name: object) -> str:
    if not isinstance(name, str):
        return ""
    return re.sub(r"[\s_\-]+", "", name).lower()


def gateway_bearer_hint(token: str, accepted_prefixes: Sequence[str]) -> str | None:
    """Return the recognition hint for a well-formed gateway bearer, else None.

    A hint is only produced when :func:`parse_gateway_key_public_id` accepts
    the token (valid accepted prefix, public ID, and a sufficiently long
    secret). The hint is the matched prefix, the first eight public-ID
    characters, and a masked suffix; it never discloses the full public ID or
    any secret segment.
    """
    if not isinstance(token, str) or not token:
        return None
    prefixes = [p for p in accepted_prefixes if isinstance(p, str) and p]
    if not prefixes:
        return None
    try:
        public_id = parse_gateway_key_public_id(token, prefixes)
    except ValueError:
        return None
    prefix = _best_matching_prefix(token, prefixes)
    if prefix is None or len(public_id) < 8:
        return None
    return f"{prefix}{public_id[:8]}\u2026***"


def _best_matching_prefix(key: str, prefixes: Sequence[str]) -> str | None:
    best: str | None = None
    for prefix in prefixes:
        if key.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix
    return best


def _percent_encoded(secret: bytes) -> bytes:
    return quote_from_bytes(secret, safe=b"").encode("ascii")


def _json_aware_pattern(text: str) -> bytes | None:
    """Return a bytes regex matching the secret in raw or any JSON-escaped mix.

    Each character may appear raw (UTF-8), as a ``\\uXXXX`` escape (or a
    surrogate pair for non-BMP), and ``"``/``\\`` also in their escaped forms.
    This covers all-ASCII, all-Unicode, and mixed escaping as well as escaped
    backslashes. The caller passes the secret's logical (decoded) string so
    non-ASCII values yield correct UTF-8-raw and ``\\u`` forms.
    """
    if not text:
        return None
    parts: list[bytes] = []
    for ch in text:
        cp = ord(ch)
        opts: list[bytes] = [ch.encode("utf-8")]
        if cp < 0x10000:
            opts.append(("\\u%04x" % cp).encode("ascii"))
        else:
            shifted = cp - 0x10000
            high = 0xD800 + (shifted >> 10)
            low = 0xDC00 + (shifted & 0x3FF)
            opts.append(("\\u%04x\\u%04x" % (high, low)).encode("ascii"))
        if ch == '"':
            opts.append(b'\\"')
        elif ch == "\\":
            opts.append(b"\\\\")
        elif ch == "/":
            opts.append(b"\\/")
        seen: set[bytes] = set()
        uniq: list[bytes] = []
        for option in opts:
            if option not in seen:
                seen.add(option)
                uniq.append(option)
        if len(uniq) == 1:
            parts.append(re.escape(uniq[0]))
        else:
            parts.append(b"(?:" + b"|".join(re.escape(o) for o in uniq) + b")")
    return b"".join(parts)


def _percent_aware_pattern(secret: bytes) -> bytes:
    """Return a bytes regex matching the secret raw or percent-encoded per byte.

    Each byte may appear raw or as ``%XX`` (upper or lower hex). This catches
    fully or partially percent-encoded copies, not only the normalized URL
    quote form (which leaves unreserved ASCII unencoded).
    """
    if not secret:
        return b""
    parts: list[bytes] = []
    for byte in secret:
        opts = [
            bytes([byte]),
            ("%%%02X" % byte).encode("ascii"),
            ("%%%02x" % byte).encode("ascii"),
        ]
        seen: set[bytes] = set()
        uniq: list[bytes] = []
        for option in opts:
            if option not in seen:
                seen.add(option)
                uniq.append(option)
        if len(uniq) == 1:
            parts.append(re.escape(uniq[0]))
        else:
            parts.append(b"(?:" + b"|".join(re.escape(o) for o in uniq) + b")")
    return b"".join(parts)


def _secret_patterns(secret: bytes) -> list[bytes]:
    """Return the byte-regex fragments that match any representation of secret.

    Covers the raw collected bytes, the logical string rendered as UTF-8-raw
    and/or JSON-escaped in any mix (so non-ASCII values match across header
    latin-1 and body UTF-8/``\\u`` forms), and the percent-encoded form.
    """
    patterns: list[bytes] = [re.escape(secret)]
    logical = secret.decode("latin-1")
    json_aware = _json_aware_pattern(logical)
    if json_aware is not None and json_aware not in patterns:
        patterns.append(json_aware)
    percent_aware = _percent_aware_pattern(secret)
    if percent_aware and percent_aware not in patterns:
        patterns.append(percent_aware)
    return patterns


def build_capture_masker(
    secrets: Sequence[tuple[bytes, bytes]],
) -> Callable[[bytes], bytes] | None:
    """Build a single-pass bytes masker for the given secret->replacement pairs.

    Each ``(secret, replacement)`` contributes raw, percent-encoded, and
    JSON-escaped (any mix) representations. Longer secrets are matched first
    so a secret that is a substring of another is not partially masked.
    Returns ``None`` when there is nothing to mask. Raises
    :class:`CaptureRedactionError` if the construction is unsafe.
    """
    entries: list[tuple[int, bytes, bytes]] = []
    for secret, replacement in secrets:
        if not isinstance(secret, (bytes, bytearray)) or not secret:
            continue
        secret = bytes(secret)
        if len(secret) > _MAX_SECRET_BYTES:
            raise CaptureRedactionError("capture_redaction_unsafe")
        if not isinstance(replacement, (bytes, bytearray)):
            raise CaptureRedactionError("capture_redaction_unsafe")
        replacement = bytes(replacement)
        patterns = _secret_patterns(secret)
        if not patterns:
            continue
        fragment = b"(?:" + b"|".join(patterns) + b")"
        entries.append((len(secret), fragment, replacement))
    if not entries:
        return None
    if len(entries) > _MAX_SECRET_VALUES:
        raise CaptureRedactionError("capture_redaction_unsafe")
    entries.sort(key=lambda entry: entry[0], reverse=True)
    full = b"|".join(fragment for _, fragment, _ in entries)
    if len(full) > _MAX_TOTAL_PATTERN_BYTES:
        raise CaptureRedactionError("capture_redaction_unsafe")
    try:
        pattern = re.compile(full)
        anchored = [
            re.compile(b"^" + fragment + b"$") for _, fragment, _ in entries
        ]
    except re.error as exc:
        raise CaptureRedactionError("capture_redaction_unsafe") from exc
    anchored_repl = list(zip(anchored, (repl for _, _, repl in entries)))

    def _sub(match: "re.Match[bytes]") -> bytes:
        data = match.group(0)
        for anchored_pattern, replacement in anchored_repl:
            if anchored_pattern.match(data):
                return replacement
        return data

    def _masker(data: bytes) -> bytes:
        return pattern.sub(_sub, data)

    return _masker


def _decode_query_value(value: bytes) -> list[bytes]:
    """Return candidate semantic decodings of a raw query value.

    Both percent-decoding and form decoding (``+`` as space) are tried so a
    secret copied into a query is recovered regardless of how it was encoded.
    """
    out: list[bytes] = []
    for decoded in (
        unquote_to_bytes(value.decode("latin-1")),
        unquote_to_bytes(value.replace(b"+", b" ").decode("latin-1")),
    ):
        if decoded and decoded not in out:
            out.append(decoded)
    return out


def _gateway_secret_suffix(token: str, accepted_prefixes: Sequence[str]) -> bytes | None:
    """Return the secret segment of a well-formed gateway bearer, else None.

    For ``<prefix><public_id>.<secret>`` the ``<secret>`` after the
    public-ID dot is itself an authentication secret and must be masked if it
    is copied elsewhere, independent of the full bearer.
    """
    if not isinstance(token, str) or not token:
        return None
    try:
        parse_gateway_key_public_id(token, accepted_prefixes)
    except ValueError:
        return None
    prefix = _best_matching_prefix(token, accepted_prefixes)
    if prefix is None:
        return None
    payload = token[len(prefix) :]
    if "." not in payload:
        return None
    secret = payload.partition(".")[2]
    if not secret:
        return None
    return secret.encode("latin-1", "replace")


def _mask_query(query: bytes, secret_to_repl: dict[bytes, bytes]) -> bytes:
    """Mask query *values* by decoding first, so any percent-encoding is caught.

    Every ``key=value`` pair whose percent-decoded value exactly matches a
    known secret is rewritten to the percent-encoded replacement. Names and
    the rest of the query are left for the byte masker.
    """
    if not query or not secret_to_repl:
        return query
    out: list[bytes] = []
    for pair in query.split(b"&"):
        if not pair:
            out.append(pair)
            continue
        name, sep, value = pair.partition(b"=")
        if not sep:
            out.append(pair)
            continue
        replacement: bytes | None = None
        for decoded in _decode_query_value(value):
            replacement = secret_to_repl.get(decoded)
            if replacement is not None:
                break
        if replacement is not None:
            out.append(name + b"=" + _percent_encoded(replacement))
        else:
            out.append(pair)
    return b"&".join(out)


def _basic_userinfo_secrets(value: bytes) -> list[bytes]:
    """Decode a Basic proxy-authorization credential into its secrets.

    ``value`` is the part after the ``Basic`` scheme. Returns the decoded
    ``user:password``, the password, and (when there is no password) the user,
    so any of them copied elsewhere is also masked.
    """
    try:
        decoded = base64.b64decode(value.strip(), validate=True)
    except (ValueError, TypeError):
        return []
    if not decoded:
        return []
    user, sep, password = decoded.partition(b":")
    out = [decoded]
    if password:
        out.append(password)
    elif user:
        out.append(user)
    return out


def _read_json_string(text: str, i: int) -> tuple[int, str]:
    """Read a JSON string starting at ``text[i] == '"'``; return (end, value)."""
    n = len(text)
    i += 1
    out: list[str] = []
    escapes = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
    while i < n:
        ch = text[i]
        if ch == "\\":
            if i + 1 >= n:
                break
            esc = text[i + 1]
            if esc == "u":
                hexdigits = text[i + 2 : i + 6]
                try:
                    out.append(chr(int(hexdigits, 16)))
                except ValueError:
                    out.append(esc)
                i += 6
                continue
            out.append(escapes.get(esc, esc))
            i += 2
            continue
        if ch == '"':
            return i + 1, "".join(out)
        out.append(ch)
        i += 1
    return n, "".join(out)


def _scan_credential_strings(text: str) -> list[str]:
    """Lexically collect credential string values from (possibly malformed) JSON.

    Works without parsing the whole document (so malformed bodies are handled
    and the original bytes are preserved). A string is treated as a key when
    it is followed by ``:``; the following value string is collected when the
    key normalizes to a credential field name.
    """
    found: list[str] = []
    i = 0
    n = len(text)
    current_key: str | None = None
    while i < n:
        ch = text[i]
        if ch in " \t\r\n,":
            i += 1
            continue
        if ch == '"':
            end, value = _read_json_string(text, i)
            k = end
            while k < n and text[k] in " \t\r\n":
                k += 1
            if k < n and text[k] == ":":
                current_key = _normalize_field_name(value)
                i = k
            else:
                if (
                    current_key in CREDENTIAL_FIELD_NAMES
                    and current_key not in _IDENTIFIER_FIELD_NAMES
                    and value.strip()
                ):
                    found.append(value)
                current_key = None
                i = end
            continue
        if ch == ":":
            i += 1
            continue
        if ch in "{[":
            i += 1
            continue
        if ch in "}]":
            current_key = None
            i += 1
            continue
        # A non-string value (number/true/false/null) ends any pending key.
        current_key = None
        while i < n and text[i] not in ",}] \t\r\n":
            i += 1
    return found


def _credential_values_from_body(body: bytes) -> tuple[list[bytes], str | None]:
    """Structurally discover credential string values in a (possibly malformed) body.

    Returns the discovered values and a note when the body was non-UTF-8
    (``"body_non_utf8"``). Discovery never reserializes the body; the caller
    masks the original bytes.
    """
    if not body:
        return [], None
    note: str | None = None
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("latin-1")
        note = "body_non_utf8"
    found = _scan_credential_strings(text)
    return [v.encode("utf-8") for v in found], note


def collect_incoming_secrets(
    *,
    query: bytes,
    headers: Sequence[tuple[str, bytes]],
    body: bytes,
    accepted_prefixes: Sequence[str],
) -> tuple[list[tuple[bytes, str | None]], tuple[str, ...], str | None]:
    """Collect known incoming auth secret values with their display hint.

    Returns ``(secrets, notes, recognized_hint)`` where ``secrets`` is a list
    of unique ``(secret_bytes, hint_or_None)`` in discovery order, ``notes``
    are stable discovery markers, and ``recognized_hint`` is the hint for the
    primary (Authorization) bearer when it is a recognized gateway key.
    """
    notes: list[str] = []
    seen: set[bytes] = set()
    secrets: list[tuple[bytes, str | None]] = []
    recognized_hint: str | None = None

    def _add(secret: bytes, *, primary: bool = False) -> None:
        nonlocal recognized_hint
        if not secret or secret in seen:
            return
        seen.add(secret)
        hint: str | None = gateway_bearer_hint(
            secret.decode("latin-1", "replace"), accepted_prefixes
        )
        if hint is not None and recognized_hint is None:
            recognized_hint = hint
        secrets.append((secret, hint))

    for name, value in headers:
        lname = name.lower()
        if lname in {"authorization", "proxy-authorization"}:
            text = value.decode("latin-1")
            parts = text.split(None, 1)
            scheme = parts[0].lower() if parts else ""
            if len(parts) == 2 and scheme in {"bearer", "basic", "digest", "token"}:
                credential = parts[1].strip().encode("latin-1", "replace")
            else:
                credential = value.strip()
            _add(credential, primary=(lname == "authorization"))
            if lname == "authorization":
                suffix = _gateway_secret_suffix(
                    credential.decode("latin-1", "replace"), accepted_prefixes
                )
                if suffix:
                    _add(suffix)
            if lname == "proxy-authorization" and scheme == "basic":
                for part in _basic_userinfo_secrets(credential):
                    _add(part)
        elif lname == "cookie":
            for chunk in value.decode("latin-1").split(";"):
                cookie_value = chunk.partition("=")[2].strip()
                if (
                    len(cookie_value) >= 2
                    and cookie_value[0] == cookie_value[-1]
                    and cookie_value[0] in {'"', "'"}
                ):
                    cookie_value = cookie_value[1:-1].strip()
                if cookie_value:
                    _add(cookie_value.encode("latin-1", "replace"))
        elif lname in CREDENTIAL_HEADER_NAMES:
            _add(value.strip())

    for pair in query.split(b"&"):
        if not pair:
            continue
        name, sep, value = pair.partition(b"=")
        if not sep:
            continue
        name_decoded = unquote_to_bytes(name.decode("latin-1")).decode("latin-1")
        if _normalize_field_name(name_decoded) not in CREDENTIAL_FIELD_NAMES:
            continue
        for decoded in _decode_query_value(value):
            _add(decoded)

    body_secrets, body_note = _credential_values_from_body(body)
    if body_note is not None:
        notes.append(body_note)
    for secret in body_secrets:
        _add(secret)

    return secrets, tuple(notes), recognized_hint


def redact_capture_request(
    *,
    path: bytes,
    query: bytes,
    headers: Sequence[tuple[str, bytes]],
    body: bytes,
    accepted_prefixes: Sequence[str],
    body_complete: bool = True,
) -> CaptureRedactionResult:
    """Mask one incoming request's original bytes, preserving non-secret content.

    ``headers`` is the ordered ``(name, raw_value_bytes)`` sequence. Returns a
    :class:`CaptureRedactionResult` with masked path/query/headers/body and
    safe metadata. Raises :class:`CaptureRedactionError` (no content) when
    masking cannot be completed safely.
    """
    path = bytes(path)
    query = bytes(query)
    body = bytes(body)
    headers = [
        (
            str(name),
            value.encode("latin-1") if isinstance(value, str) else bytes(value),
        )
        for name, value in headers
    ]

    secrets, notes, recognized_hint = collect_incoming_secrets(
        query=query,
        headers=headers,
        body=body,
        accepted_prefixes=accepted_prefixes,
    )

    secret_to_repl: dict[bytes, bytes] = {}
    pairs: list[tuple[bytes, bytes]] = []
    for secret, hint in secrets:
        replacement = hint.encode("utf-8") if hint is not None else _FULLY_REDACTED
        secret_to_repl[secret] = replacement
        pairs.append((secret, replacement))

    # Tier 1: encoding-agnostic masking of query values (catches fully/partially
    # percent-encoded copies). Tier 2: byte masking of path, query, header
    # names and values, and body (raw + percent + any JSON-escaped mix).
    masked_query = _mask_query(query, secret_to_repl)

    masker = build_capture_masker(pairs)

    masked_path = masker(path) if masker else path
    masked_query = masker(masked_query) if masker else masked_query
    masked_headers = tuple(
        (
            masker(name.encode("latin-1")).decode("latin-1") if masker else name,
            masker(value) if masker else value,
        )
        for name, value in headers
    )
    masked_body = masker(body) if masker else body

    return CaptureRedactionResult(
        path=masked_path,
        query=masked_query,
        headers=masked_headers,
        body=masked_body,
        body_complete=body_complete,
        secrets_masked=len(pairs),
        recognized_hint=recognized_hint,
        notes=tuple(notes),
    )
