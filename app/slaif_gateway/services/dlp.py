"""Bounded optional DLP/PII policy detectors with redacted findings only."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Action = Literal["block", "flag", "monitor"]


@dataclass(frozen=True, slots=True)
class DlpFinding:
    detector: str
    confidence: float


@dataclass(frozen=True, slots=True)
class DlpDecision:
    action: Action
    blocked: bool
    findings: tuple[DlpFinding, ...]


@dataclass(frozen=True, slots=True)
class DlpDetector:
    name: str
    pattern: re.Pattern[str]
    confidence: float


DEFAULT_DETECTORS: tuple[DlpDetector, ...] = (
    DlpDetector("email", re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I), 0.9),
    DlpDetector("phone", re.compile(r"\+?\d[\d\s().-]{7,}\d"), 0.6),
    DlpDetector("credit_card", re.compile(r"\b(?:\d[ -]*?){13,16}\b"), 0.8),
    DlpDetector("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), 0.85),
)


def scan(
    payload: str,
    *,
    action: Action,
    detectors: tuple[DlpDetector, ...] = DEFAULT_DETECTORS,
) -> DlpDecision:
    """Scan bounded text and return redacted findings without raw matches."""
    if not isinstance(payload, str):
        raise TypeError("DLP payload must be text")
    findings = tuple(
        DlpFinding(detector=detector.name, confidence=detector.confidence)
        for detector in detectors
        if detector.pattern.search(payload)
    )
    blocked = action == "block" and bool(findings)
    return DlpDecision(action=action, blocked=blocked, findings=findings)
