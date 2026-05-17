"""Shared key-purpose and capability-policy mode constants."""

from __future__ import annotations

KEY_PURPOSE_STANDARD = "standard"
KEY_PURPOSE_TRUSTED_CALIBRATION = "trusted_calibration"

CAPABILITY_POLICY_MODE_STANDARD = "standard"
CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY = "trusted_calibration_discovery"

KEY_PURPOSE_VALUES = frozenset({KEY_PURPOSE_STANDARD, KEY_PURPOSE_TRUSTED_CALIBRATION})
CAPABILITY_POLICY_MODE_VALUES = frozenset(
    {CAPABILITY_POLICY_MODE_STANDARD, CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY}
)


def is_trusted_calibration_key(*, key_purpose: str, capability_policy_mode: str) -> bool:
    return (
        key_purpose == KEY_PURPOSE_TRUSTED_CALIBRATION
        and capability_policy_mode == CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY
    )


def default_capability_policy_mode_for_purpose(key_purpose: str) -> str:
    if key_purpose == KEY_PURPOSE_TRUSTED_CALIBRATION:
        return CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY
    return CAPABILITY_POLICY_MODE_STANDARD
