"""Bounded facial-scoring native server module."""

from slaif_gateway.modules.servers.facial_scoring.adapter import (
    FACIAL_SCORING_DEFAULT_SCORE_TYPE,
    FACIAL_SCORING_MODULE_ID,
    FACIAL_SCORING_PUBLIC_MODEL,
    FACIAL_SCORING_SCORE_PATH,
    FacialScoringAdapter,
)

__all__ = [
    "FACIAL_SCORING_DEFAULT_SCORE_TYPE",
    "FACIAL_SCORING_MODULE_ID",
    "FACIAL_SCORING_PUBLIC_MODEL",
    "FACIAL_SCORING_SCORE_PATH",
    "FacialScoringAdapter",
]
