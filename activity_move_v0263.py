"""v0.26.3: eligibility checks for explicitly relocating a stray month activity.

Only ordinary, non-leave activity credits can be relocated; never guess a
missing employee ID, create a destination month or edit approved leave.
"""
from __future__ import annotations

from datetime import date

from extras import CREDIT_TYPES

# Absences require their own approval/audit procedures, not an ad-hoc move.
MOVEABLE_ACTIVITY_TYPES = frozenset(("Andere", "Opleiding", "Bijzondere opdracht"))


def activity_destination(item: dict, current_year: int, current_month: int) -> tuple[int, int] | None:
    if not isinstance(item, dict):
        return None
    raw = item.get("date")
    if not isinstance(raw, str):
        return None
    try:
        day = date.fromisoformat(raw)
    except ValueError:
        return None
    if day.isoformat() != raw or (day.year, day.month) == (current_year, current_month):
        return None
    return day.year, day.month


def validate_movable_activity(item: dict, employees: set[str],
                              current_year: int, current_month: int) -> tuple[int, int]:
    destination = activity_destination(item, current_year, current_month)
    if destination is None:
        raise ValueError("De gekozen registratie heeft geen geldige datum in een andere maand.")
    if item.get("employee_id") not in employees:
        raise ValueError("Onbekende controleur: herstel eerst het personeelsprofiel.")
    if item.get("type") not in MOVEABLE_ACTIVITY_TYPES:
        if item.get("type") in CREDIT_TYPES:
            raise ValueError("Afwezigheden en verlof mogen niet via deze functie worden verplaatst.")
        raise ValueError("Onbekend activiteitstype; controleer de registratie handmatig.")
    value = item.get("hours")
    if type(value) not in (int, float) or not 0 <= value <= 16:
        raise ValueError("De activiteit bevat ongeldige uren.")
    return destination
