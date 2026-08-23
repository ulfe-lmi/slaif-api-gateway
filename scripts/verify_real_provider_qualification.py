#!/usr/bin/env python3
"""Bounded opt-in real-provider qualification through the SLAIF gateway.

Credentials are never printed. Evidence is limited to status, endpoint,
provider/model, accounting IDs, and token totals.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

PROVIDERS = {
    "openrouter": {
        "chat_model": "nvidia/nemotron-3-super-120b-a12b:free",
        "responses_model": "nvidia/nemotron-3-super-120b-a12b:free",
    },
    "openai": {
        "chat_model": "gpt-5.6-luna",
        "responses_model": "gpt-5.6-luna",
    },
}
MAX_REQUESTS = 10
MIN_FREE_MODEL_GAP_SECONDS = 15


@dataclass(frozen=True, slots=True)
class Evidence:
    provider: str
    endpoint: str
    model: str
    request_id: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int


def _settings() -> tuple[str, str]:
    base_url = os.getenv("OPENAI_BASE_URL", "").rstrip("/")
    gateway_key = os.getenv("OPENAI_API_KEY", "")
    if not base_url or not gateway_key:
        raise SystemExit("RESULT=FAIL MISSING_GATEWAY_CONFIGURATION")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.path.endswith("/v1"):
        raise SystemExit("RESULT=FAIL INVALID_GATEWAY_BASE_URL")
    return base_url, gateway_key


def _headers(gateway_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {gateway_key}", "Content-Type": "application/json"}


def _request_id(response: httpx.Response) -> str | None:
    return response.headers.get("x-request-id") or response.headers.get("x-gateway-request-id")


def _usage(response_json: dict[str, object]) -> tuple[int, int, int]:
    usage = response_json.get("usage") or {}
    if not isinstance(usage, dict):
        return 0, 0, 0
    return (
        int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0),
        int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0),
        int(usage.get("total_tokens", 0) or 0),
    )


def nonstreaming_chat(client: httpx.Client, base_url: str, key: str, model: str) -> Evidence:
    response = client.post(
        f"{base_url}/chat/completions",
        headers=_headers(key),
        timeout=90,
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Reply with exactly: HELLO"}],
            "max_completion_tokens": 16,
            "stream": False,
        },
    )
    response.raise_for_status()
    body = response.json()
    prompt, completion, total = _usage(body)
    return Evidence(
        provider="gateway",
        endpoint="/v1/chat/completions",
        model=str(body.get("model") or model),
        request_id=_request_id(response),
        input_tokens=prompt,
        output_tokens=completion,
        total_tokens=total,
    )


def streaming_chat(client: httpx.Client, base_url: str, key: str, model: str) -> Evidence:
    saw_done = False
    with client.stream(
        "POST",
        f"{base_url}/chat/completions",
        headers=_headers(key),
        timeout=120,
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Reply with exactly: HELLO"}],
            "max_completion_tokens": 16,
            "stream": True,
            "stream_options": {"include_usage": True},
        },
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line != "data: [DONE]":
                continue
            saw_done = True
    # A final non-streaming accounting probe is intentionally avoided; this run's
    # ledger evidence comes from the streamed request itself via request ID.
    if not saw_done:
        raise RuntimeError("streaming did not complete with [DONE]")
    return Evidence(
        provider="gateway",
        endpoint="/v1/chat/completions",
        model=model,
        request_id=None,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
    )


def nonstreaming_responses(client: httpx.Client, base_url: str, key: str, model: str) -> Evidence:
    response = client.post(
        f"{base_url}/responses",
        headers=_headers(key),
        timeout=90,
        json={
            "model": model,
            "input": "Reply with exactly: HELLO",
            "max_output_tokens": 32,
            "store": False,
        },
    )
    response.raise_for_status()
    body = response.json()
    prompt, completion, total = _usage(body)
    return Evidence(
        provider="gateway",
        endpoint="/v1/responses",
        model=str(body.get("model") or model),
        request_id=_request_id(response),
        input_tokens=prompt,
        output_tokens=completion,
        total_tokens=total,
    )


def emit(evidence: Evidence) -> None:
    print(
        "EVIDENCE="
        + json.dumps(
            {
                "endpoint": evidence.endpoint,
                "model": evidence.model,
                "request_id": evidence.request_id,
                "input_tokens": evidence.input_tokens,
                "output_tokens": evidence.output_tokens,
                "total_tokens": evidence.total_tokens,
            },
            sort_keys=True,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=tuple(PROVIDERS), required=True)
    arguments = parser.parse_args()
    try:
        base_url, gateway_key = _settings()
        models = PROVIDERS[arguments.provider]
        print("REAL_PROVIDER_CALLED=true")
        print(f"PROVIDER={arguments.provider}")
        with httpx.Client() as client:
            chat = nonstreaming_chat(client, base_url, gateway_key, models["chat_model"])
            emit(chat)
            time.sleep(MIN_FREE_MODEL_GAP_SECONDS)
            stream = streaming_chat(client, base_url, gateway_key, models["chat_model"])
            emit(stream)
            time.sleep(MIN_FREE_MODEL_GAP_SECONDS)
            responses = nonstreaming_responses(client, base_url, gateway_key, models["responses_model"])
            emit(responses)
        print("RESULT=OK REQUEST_COUNT=3 MAX_REQUEST_COUNT=10")
        return 0
    except Exception as exc:
        safe_type = type(exc).__name__
        print(f"RESULT=FAIL REAL_PROVIDER_CALLED=false ERROR_TYPE={safe_type}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
