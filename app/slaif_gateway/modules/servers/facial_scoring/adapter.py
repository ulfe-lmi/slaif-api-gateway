"""Compatibility imports; facial scoring uses the shared configured adapter."""

from slaif_gateway.modules.servers.completion_service.adapter import (
    FACIAL_SCORING_DEFAULT_SCORE_TYPE,
    FACIAL_SCORING_MODULE_ID,
    FACIAL_SCORING_PUBLIC_MODEL,
    FACIAL_SCORING_SCORE_PATH,
    CompletionServiceAdapter,
)

FacialScoringAdapter = CompletionServiceAdapter

__all__ = [
    "FACIAL_SCORING_DEFAULT_SCORE_TYPE", "FACIAL_SCORING_MODULE_ID",
    "FACIAL_SCORING_PUBLIC_MODEL", "FACIAL_SCORING_SCORE_PATH", "FacialScoringAdapter",
]
