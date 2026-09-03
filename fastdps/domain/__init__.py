"""Procurement domain constants and invariants."""

from fastdps.domain.lifecycle import (
    APPLICATION_TRANSITIONS,
    AWARD_TRANSITIONS,
    COMPETITION_TRANSITIONS,
    DPS_TRANSITIONS,
    require_transition,
)

__all__ = [
    "APPLICATION_TRANSITIONS",
    "AWARD_TRANSITIONS",
    "COMPETITION_TRANSITIONS",
    "DPS_TRANSITIONS",
    "require_transition",
]
