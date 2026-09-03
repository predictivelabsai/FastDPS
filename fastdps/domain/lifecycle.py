"""Explicit lifecycle transition rules for governed procurement records."""
from __future__ import annotations


DPS_TRANSITIONS = {
    "draft": {"published", "cancelled"},
    "published": {"closed", "cancelled"},
    "closed": {"archived"},
    "cancelled": {"draft", "archived"},
    "archived": set(),
}

APPLICATION_TRANSITIONS = {
    "draft": {"submitted", "withdrawn"},
    "submitted": {"under_review", "withdrawn"},
    "under_review": {"needs_clarification", "admitted", "rejected"},
    "needs_clarification": {"submitted", "withdrawn"},
    "admitted": {"suspended", "withdrawn"},
    "suspended": {"admitted", "rejected"},
    "rejected": {"submitted"},
    "withdrawn": set(),
}

COMPETITION_TRANSITIONS = {
    "draft": {"published", "cancelled"},
    "published": {"closed", "cancelled"},
    "closed": {"evaluation", "cancelled"},
    "evaluation": {"awarded", "cancelled"},
    "awarded": set(),
    "cancelled": set(),
}

AWARD_TRANSITIONS = {
    "draft": {"approved", "withdrawn"},
    "approved": {"published", "withdrawn"},
    "published": set(),
    "withdrawn": {"draft"},
}


def require_transition(transitions: dict[str, set[str]], current: str, target: str) -> None:
    if target not in transitions.get(current, set()):
        raise ValueError(f"Invalid transition from {current!r} to {target!r}")
