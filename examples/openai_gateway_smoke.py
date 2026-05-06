"""OpenAI-compatible smoke test for a local SLAIF gateway.

Set OPENAI_API_KEY to a gateway-issued key and OPENAI_BASE_URL to the gateway
base URL, for example http://localhost:8000/v1. This script intentionally uses
the official OpenAI client flow and never reads provider keys.
"""

from __future__ import annotations

import os

from openai import OpenAI


def main() -> None:
    model = os.getenv("SLAIF_SMOKE_MODEL", "gpt-4o-mini")
    client = OpenAI()

    print("Listing models visible to this gateway key...")
    models = client.models.list()
    print(models)

    print(f"Sending chat.completions request with model={model!r}...")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": (
                    "Say hello from SLAIF, print the joke of the day "
                    "(random joke about AI factories in EU) and print the value of pi."
                ),
            }
        ],
    )

    print(resp.choices[0].message.content)


if __name__ == "__main__":
    main()
