"""Daggebonden dienstwensen voor controleurs (v0.9.1).

Voorkeuren zijn zacht: de solver mag ervan afwijken. Alleen dienstnummers
uit de maandbehoefte op de gekozen datum kunnen worden aangevraagd.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from copy import deepcopy
from datetime import date

from extras import preference_type


def days_in_month(data: dict) -> list[date]:
    year, month = int(data["year"]), int(data["month"])
    return [date(year, month, i) for i in range(1, calendar.monthrange(year, month)[1] + 1)]


def shifts_by_day(data: dict) -> dict[str, list[dict]]:
    """Diensten die op de datum daadwerkelijk vereist zijn, niet de hele catalogus."""
    catalog = {s["id"]: s for s in data["shifts"] if s.get("active", True)}
    result = defaultdict(list)
    for request in data["demand"]:
        shift = catalog.get(request["shift_id"])
        if shift and request.get("required", 0) > 0:
            result[request["date"]].append(shift)
    return {day: sorted(shifts, key=lambda sh: (sh["start"], sh["id"]))
            for day, shifts in result.items()}


def current_daily_choices(data: dict, employee_id: str) -> dict[str, dict]:
    """Oude vrijwensen en nieuwe dagwensen verschijnen in hetzelfde maandoverzicht."""
    out = {}
    for p in data.get("preferences", []):
        if p.get("employee_id") == employee_id and preference_type(p) in ("free_day", "daily_shift"):
            out[p["date"]] = p
    return out


def update_daily_choices(data: dict, employee_id: str, choices: dict[str, dict]) -> dict:
    """Vervang alleen eigen daggebonden wensen; behoud alle andere voorkeuren.

    choices: {"YYYY-MM-DD": {"kind": "none"|"free"|"shift",
                             "shift_id": "..." (enkel bij shift), "priority": 1..3}}
    """
    available = shifts_by_day(data)
    valid_dates = {day.isoformat() for day in days_in_month(data)}
    if set(choices) != valid_dates:
        raise ValueError("Geef voor iedere datum van de planningsmaand een keuze op.")
    if employee_id not in {e["id"] for e in data["employees"]}:
        raise ValueError("Onbekende controleur.")

    updated = deepcopy(data)
    updated["preferences"] = [
        p for p in data["preferences"]
        if not (p.get("employee_id") == employee_id and
                preference_type(p) in ("free_day", "daily_shift") and
                p.get("date") in valid_dates)
    ]
    for day in sorted(choices):
        choice = choices[day]
        kind = choice.get("kind")
        if kind == "none":
            continue
        priority = choice.get("priority")
        if type(priority) is not int or priority not in (1, 2, 3):
            raise ValueError(f"Ongeldige prioriteit op {day}.")
        if kind == "free":
            entry = {"employee_id": employee_id, "type": "free_day",
                     "date": day, "priority": priority}
        elif kind == "shift":
            shift_id = choice.get("shift_id")
            if shift_id not in {s["id"] for s in available.get(day, [])}:
                raise ValueError(f"Dienst {shift_id} is op {day} niet beschikbaar in de maandbehoefte.")
            entry = {"employee_id": employee_id, "type": "daily_shift",
                     "date": day, "shift_id": shift_id, "priority": priority}
        else:
            raise ValueError(f"Onbekende keuze op {day}.")
        updated["preferences"].append(entry)
    return updated
