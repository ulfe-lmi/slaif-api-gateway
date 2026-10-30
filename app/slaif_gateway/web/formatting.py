"""Locale-stable numeric display helpers for the admin GUI (objective 206).

Pure presentation only: these helpers never change values, never round
money, and never convert through ``float``. They render human-facing
read-only quantities (counts, token quantities, money, FX rates) with
comma thousands grouping, a decimal dot, and no scientific notation.

The admin templates apply them through the ``num`` / ``tokm`` / ``dec`` /
``inputnum`` / ``policysum`` / ``ratepolicy`` Jinja filters registered in
``app/slaif_gateway/api/admin.py``.
Machine-facing surfaces keep raw exact values: editable inputs, hidden
fields, submitted payloads, CSV/API/CLI/JSON, and ``data-sort-value`` sort
keys never use the grouped or million-scaled forms. ``format_raw_decimal``
is the canonical ungrouped exact decimal used for sort keys, and
``format_input_decimal`` is the raw representation for editable inputs
(it only normalizes the ``0E-9``/``-0E-9`` zero rendering of quantized
Decimals to ``0``; valid non-zero precision and user-typed strings pass
through unchanged).

Human-readable policy summaries that the safe DTOs expose only as
service-built strings (rate-limit ``req/min`` / ``tokens/min`` /
``concurrent`` / ``s window`` parts, the Chat live-burn summary, the lazy
throttling wait summary) are rendered by ``format_policy_summary`` through
a deliberately narrow grammar: each KNOWN finite producer form is matched
as a whole (or part-by-part) before any digit is touched, and anything
that does not match the exact known grammar passes through byte-for-byte
unchanged. There is no generic digit substitution on arbitrary text,
identifiers, notes, provider metadata, URLs, raw JSON, or code.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

__all__ = [
    "format_input_decimal",
    "format_number",
    "format_policy_summary",
    "format_rate_limit_policy",
    "format_raw_decimal",
    "format_tokens_m",
]

_MILLION = Decimal(1_000_000)
_M_TOKENS_QUANTUM = Decimal("0.001")

# Known finite grammar of the service-built human policy summaries
# (admin_key_dashboard._rate_limit_policy_summary, key_import
# rate_limit_summary, streaming_live_burn_surface_policy_summary,
# admin_key_dashboard._lazy_throttling_policy_summary). Only these exact
# shapes are ever transformed.
_RATE_SUMMARY_PART_RE = re.compile(
    r"^(?P<value>-?\d+) (?P<kind>req/min|tokens/min|concurrent)$"
)
_WINDOW_SUMMARY_PART_RE = re.compile(r"^(?P<value>\d+)s window$")
_LIVE_BURN_SUMMARY_RE = re.compile(
    r"^Chat live-burn: (?P<state>on|off)(?P<ignored> \(margins ignored\))?, "
    r"cost margin EUR (?P<cost>-?(?:0|[1-9]\d*)(?:\.\d+)?), "
    r"token margin (?P<tokens>-?\d+)$"
)
_LAZY_WAIT_SUMMARY_RE = re.compile(
    r"^Mode: wait; max wait: (?P<wait>\d+)s; max waiting per key: "
    r"(?P<waiting>\d+); applies to Chat Completions and Responses "
    r"before provider execution$"
)
_RATE_POLICY_PARTS = (
    ("requests_per_minute", "req/min"),
    ("tokens_per_minute", "tokens/min"),
    ("max_concurrent_requests", "concurrent"),
    ("window_seconds", "s window"),
)


def _as_decimal(value: object) -> Decimal | None:
    """Exact ``Decimal`` for int / Decimal / legitimate numeric strings.

    Returns ``None`` for anything that is not a quantity: booleans are not
    quantities here, floats are out of the admin display contract (read
    values are int, Decimal, or parsed numeric strings), and non-numeric
    strings (identifiers, versions, labels) pass through untouched by the
    callers.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    return None


def _fixed_exact(value: Decimal) -> str:
    """Fixed-point text with unnecessary fractional zeros stripped and a
    negative zero normalized to plain ``0``."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "-0":
        text = "0"
    return text


def _grouped(text: str) -> str:
    """Comma-group the integer part of a fixed-point text (sign kept)."""
    integer, dot, fraction = text.partition(".")
    grouped = f"{int(integer):,}"
    if integer.startswith("-") and not grouped.startswith("-"):
        grouped = f"-{grouped}"
    return grouped + (f".{fraction}" if dot else "")


def format_number(value: object) -> str | None:
    """Locale-stable grouped display of a finite numeric quantity.

    ``None`` maps to ``None`` so templates keep their own missing labels
    (``n/a``, ``Unlimited``, ``Unknown``). int / Decimal / legitimate
    numeric strings render EXACTLY (no float round-trip, so 64-bit counts
    and 9-dp money keep their low digits); unneeded fractional zeros are
    stripped; an actual zero (positive or negative, including ``0E-9``)
    renders ``0``; a true non-zero ``1E-9`` renders ``0.000000001`` (a
    small positive price is never replaced by a free zero). Anything that
    is not a quantity (identifiers, HTTP codes, ports, versions, dates,
    labels) passes through via ``str`` unchanged.
    """
    if value is None:
        return None
    number = _as_decimal(value)
    if number is None or not number.is_finite():
        return str(value)
    if number == 0:
        return "0"
    return _grouped(_fixed_exact(number))


def format_tokens_m(value: object) -> str | None:
    """A token quantity in millions of tokens (unit added by the template).

    ``None`` maps to ``None``. For |v| >= 1,000,000 the value is scaled by
    one million and quantized to 3 decimal places (ROUND_HALF_UP) with
    trailing zeros stripped: 1,500,000 -> ``1.5``, 937,826,734 ->
    ``937.827``. For |v| < 1,000,000 the division by one million is exact
    (a power-of-ten exponent shift), so no positive value ever rounds to
    zero: 1,000 -> ``0.001``, 1 -> ``0.000001``, 999,999 -> ``0.999999``.
    Zero renders ``0``. Non-quantities pass through via ``str``.

    The result carries NO unit label and NO comma/M interpretation of the
    underlying count: the exact count stays in the template ``title`` /
    accessibility text and in the raw sort key.
    """
    if value is None:
        return None
    number = _as_decimal(value)
    if number is None or not number.is_finite():
        return str(value)
    if number == 0:
        return "0"
    if abs(number) >= _MILLION:
        scaled = number.scaleb(-6).quantize(_M_TOKENS_QUANTUM, rounding=ROUND_HALF_UP)
        text = _fixed_exact(scaled)
    else:
        text = _fixed_exact(number.scaleb(-6))
    return _grouped(text)


def format_raw_decimal(value: object) -> str | None:
    """Canonical ungrouped, unscaled exact decimal (``data-sort-value``).

    No commas, no M scaling, no exponent notation: ``Decimal('0E-9')`` ->
    ``0``, ``Decimal('-0E-9')`` -> ``0``, ``Decimal('2.500000000')`` ->
    ``2.5``, ``937826734`` -> ``937826734``, ``"0E-9"`` -> ``0``. ``None``
    maps to ``None`` (templates render the empty raw key that the fixed
    sort script treats as missing). Non-quantities pass through via
    ``str``.
    """
    if value is None:
        return None
    number = _as_decimal(value)
    if number is None or not number.is_finite():
        return str(value)
    if number == 0:
        return "0"
    return _fixed_exact(number)


def format_input_decimal(value: object) -> str | None:
    """Raw editable-input representation.

    A zero-valued valid numeric default renders ``0``: a quantized
    Decimal zero (never ``0E-9``/``-0E-9``) and numeric strings whose
    value is exactly zero (``"0E-9"``, ``"0.000000000"``), because the
    normalized ``0`` is the same value in the same units and stays a
    valid input. Any other valid non-zero value keeps its exact digits
    (no grouping, no zero-stripping) so the redisplayed default stays a
    valid input of the same value and units. Non-numeric strings —
    including redisplayed invalid user input — pass through unchanged;
    ``None`` maps to ``None``.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return str(value)
        if value == 0:
            return "0"
        return format(value, "f")
    if isinstance(value, str):
        try:
            parsed = Decimal(value.strip())
        except InvalidOperation:
            return str(value)
        if parsed.is_finite() and parsed == 0:
            return "0"
        return str(value)
    return str(value)


def _rate_summary_part(part: str) -> str | None:
    """One part of the known rate-limit summary grammar, or ``None``.

    ``req/min`` and ``concurrent`` stay grouped counts; ``tokens/min`` is
    a token quantity and uses the accepted M display (the exact count is
    preserved by the caller in the ``title`` / accessibility text via the
    raw, untransformed service string).
    """
    match = _RATE_SUMMARY_PART_RE.fullmatch(part)
    if match:
        kind = match.group("kind")
        if kind == "tokens/min":
            return f"{format_tokens_m(Decimal(match.group('value')))}M tokens/min"
        return f"{format_number(Decimal(match.group('value')))} {kind}"
    match = _WINDOW_SUMMARY_PART_RE.fullmatch(part)
    if match:
        return f"{format_number(Decimal(match.group('value')))}s window"
    return None


def _format_rate_limit_summary(text: str) -> str | None:
    """Grouped/M rendering of the known rate-limit summary grammar.

    Returns ``None`` when the text is NOT the finite known grammar (the
    whole string must be a comma-joined list of exact parts, or the
    fixed empty labels).
    """
    if text in ("Default", "none"):
        return text
    parts = text.split(", ")
    rendered: list[str] = []
    for part in parts:
        item = _rate_summary_part(part)
        if item is None:
            return None
        rendered.append(item)
    return ", ".join(rendered)


def _format_live_burn_summary(text: str) -> str | None:
    """Grouped money + M token margin for the live-burn summary grammar."""
    match = _LIVE_BURN_SUMMARY_RE.fullmatch(text)
    if match is None:
        return None
    cost = format_number(Decimal(match.group("cost")))
    tokens = f"{format_tokens_m(Decimal(match.group('tokens')))}M"
    return (
        f"Chat live-burn: {match.group('state')}{match.group('ignored') or ''}, "
        f"cost margin EUR {cost}, token margin {tokens}"
    )


def _format_lazy_throttling_summary(text: str) -> str | None:
    """Grouped counts for the lazy-throttling wait summary grammar.

    The reject variant carries no digits and stays untouched.
    """
    match = _LAZY_WAIT_SUMMARY_RE.fullmatch(text)
    if match is None:
        return None
    wait = format_number(Decimal(match.group("wait")))
    waiting = format_number(Decimal(match.group("waiting")))
    return (
        f"Mode: wait; max wait: {wait}s; "
        f"max waiting per key: {waiting}; "
        "applies to Chat Completions and Responses before provider execution"
    )


def format_policy_summary(value: object) -> str | None:
    """Human-readable rendering of a service-built policy summary string.

    Pure presentation boundary: the known finite producer grammars (rate
    limit, Chat live-burn, lazy throttling wait) are matched exactly and
    only their numeric quantities are rendered with the accepted display
    rules (grouped counts; token quantities in M; 9-dp money with
    unneeded zeros stripped). Everything else — including arbitrary
    text, identifiers, notes, provider metadata, URLs, raw JSON, and
    code — passes through unchanged. ``None`` maps to ``None``.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    for transform in (
        _format_live_burn_summary,
        _format_rate_limit_summary,
        _format_lazy_throttling_summary,
    ):
        rendered = transform(value)
        if rendered is not None:
            return rendered
    return value


def format_rate_limit_policy(value: object) -> str | None:
    """Typed rate-limit policy dict in the known human summary grammar.

    Used where the template already has the typed policy dictionary
    (create-result) instead of a service-built string. Unknown value
    types or dicts without any known part fall back to the existing
    literal rendering (``str``) rather than inventing a display; an
    empty/missing policy maps to ``None`` so templates keep their own
    labels.
    """
    if value is None:
        return None
    if not isinstance(value, dict) or not value:
        return str(value)
    parts: list[str] = []
    for key, unit in _RATE_POLICY_PARTS:
        if key not in value:
            continue
        number = _as_decimal(value[key])
        if number is None or not number.is_finite():
            return str(value)
        if unit == "tokens/min":
            parts.append(f"{format_tokens_m(number)}M tokens/min")
        elif unit == "s window":
            parts.append(f"{format_number(number)}s window")
        else:
            parts.append(f"{format_number(number)} {unit}")
    return ", ".join(parts) if parts else str(value)
