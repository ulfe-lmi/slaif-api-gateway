#!/usr/bin/env python3
"""Fail-closed preflight for the bounded Qwen3.8 Codex qualification gate."""

from __future__ import annotations

import ipaddress
import os
import sys
from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit

BASE_URL_ENV = "SLAIF_QWEN38_TEXT_BASE_URL"
API_KEY_ENV = "SLAIF_QWEN38_TEXT_API_KEY"


class VerificationError(RuntimeError):
    """A fixed, non-reflecting verifier failure."""


def validate_target_url(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise VerificationError("LAN target URL is invalid.")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise VerificationError("LAN target URL is invalid.")
    if parsed.query or parsed.fragment or parsed.path.rstrip("/") != "/v1":
        raise VerificationError("LAN target URL is invalid.")
    try:
        host = parsed.hostname
        address = ipaddress.ip_address(host or "")
    except ValueError as exc:
        raise VerificationError("LAN target URL must use a private numeric address.") from exc
    if not (address.is_private or address.is_loopback or address.is_link_local):
        raise VerificationError("LAN target URL is outside the private network boundary.")
    return value.rstrip("/")


def validate_environment(environment: Mapping[str, str]) -> str:
    base = environment.get(BASE_URL_ENV)
    key = environment.get(API_KEY_ENV)
    if not base and not key:
        return "live_target_absent"
    if not base or not key:
        raise VerificationError("LAN target configuration must provide both variables.")
    validate_target_url(base)
    if not isinstance(key, str) or not key or len(key) > 512 or any(ord(ch) < 33 for ch in key):
        raise VerificationError("LAN target credential is invalid.")
    return "live_target_present"


def parse_arguments(arguments: Sequence[str]) -> None:
    if arguments:
        raise VerificationError("Verifier accepts no arguments.")


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        parse_arguments(sys.argv[1:] if arguments is None else arguments)
        state = validate_environment(os.environ)
    except VerificationError:
        print("RESULT=FAIL\nLIVE_TARGET_PRESENT=false\nREAL_PROVIDER_CALLED=false")
        return 1
    if state == "live_target_absent":
        print("RESULT=LIVE_TARGET_ABSENT\nLIVE_TARGET_PRESENT=false\nREAL_PROVIDER_CALLED=false")
        return 0
    # The live LAN phase is deliberately a later continuation. Never claim
    # qualification or contact a target from this candidate-only round.
    print("RESULT=LIVE_TARGET_DEFERRED\nLIVE_TARGET_PRESENT=true\nREAL_PROVIDER_CALLED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
