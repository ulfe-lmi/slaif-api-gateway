"""Plain-text email rendering for gateway key delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class GatewayKeyEmailContext:
    """Safe rendering context for gateway key delivery emails."""

    owner_name: str
    owner_surname: str
    owner_email: str
    plaintext_gateway_key: str
    api_base_url: str
    valid_from: datetime
    valid_until: datetime
    institution_name: str | None = None
    cohort_name: str | None = None
    cost_limit_eur: Decimal | None = None
    token_limit_total: int | None = None
    request_limit_total: int | None = None
    rotation: bool = False


def gateway_key_email_subject(*, rotation: bool = False) -> str:
    """Return the subject line for key delivery."""
    if rotation:
        return "Your replacement SLAIF API Gateway key"
    return "Your SLAIF API Gateway key"


def render_gateway_key_email(context: GatewayKeyEmailContext) -> str:
    """Render a plain-text gateway key delivery email.

    The rendered body intentionally contains the plaintext gateway key because this
    is the one-time delivery channel. Callers must never log the returned body.
    """
    lines = [
        f"Hello {context.owner_name} {context.owner_surname},",
        "",
        "Your SLAIF API Gateway key is ready.",
        "",
        "Use the standard OpenAI-compatible environment variables:",
        "",
        "```bash",
        f'export OPENAI_API_KEY="{context.plaintext_gateway_key}"',
        f'export OPENAI_BASE_URL="{_normalize_base_url(context.api_base_url)}"',
        "```",
        "",
        "Then ordinary OpenAI client code works:",
        "",
        "```python",
        "from openai import OpenAI",
        "",
        "client = OpenAI()",
        "```",
        "",
        "Key details:",
        f"- Valid from: {context.valid_from.isoformat()}",
        f"- Valid until: {context.valid_until.isoformat()}",
    ]

    if context.institution_name:
        lines.append(f"- Institution: {context.institution_name}")
    if context.cohort_name:
        lines.append(f"- Cohort: {context.cohort_name}")
    if context.cost_limit_eur is not None:
        lines.append(f"- Cost limit EUR: {context.cost_limit_eur}")
    if context.token_limit_total is not None:
        lines.append(f"- Token limit: {context.token_limit_total}")
    if context.request_limit_total is not None:
        lines.append(f"- Request limit: {context.request_limit_total}")

    lines.extend(
        [
            "",
            "This key is shown only once. If it is lost, ask an administrator to rotate it.",
        ]
    )
    return "\n".join(lines)


def _normalize_base_url(value: str) -> str:
    stripped = value.rstrip("/")
    if stripped.endswith("/v1"):
        return stripped
    return f"{stripped}/v1"
