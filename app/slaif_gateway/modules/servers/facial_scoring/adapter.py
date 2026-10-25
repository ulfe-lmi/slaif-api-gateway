"""Deprecated import aliases; all behavior and identities come from profile data."""

from slaif_gateway.modules.servers.completion_service.adapter import (
    CompletionServiceAdapter, DEFAULT_SCORE_TYPE,
)
from slaif_gateway.modules.servers.completion_service.profiles import load_default_profile

FacialScoringAdapter = CompletionServiceAdapter
FACIAL_SCORING_DEFAULT_SCORE_TYPE = DEFAULT_SCORE_TYPE
FACIAL_SCORING_MODULE_ID = load_default_profile().module_id
FACIAL_SCORING_PUBLIC_MODEL = load_default_profile().public_model
FACIAL_SCORING_SCORE_PATH = load_default_profile().upstream_path

__all__ = [
    "FACIAL_SCORING_DEFAULT_SCORE_TYPE", "FACIAL_SCORING_MODULE_ID",
    "FACIAL_SCORING_PUBLIC_MODEL", "FACIAL_SCORING_SCORE_PATH", "FacialScoringAdapter",
]
