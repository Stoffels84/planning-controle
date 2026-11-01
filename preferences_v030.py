"""Maandgebonden indieningsvenster en maxima voor wensen (v0.30).

Pure functies. Geen Streamlit, geen database en geen mutatie van bestaande records.
0 als maximum betekent onbeperkt. Beheerders kunnen uitzonderingen beheren;
controleurs kunnen alleen binnen een open venster en de ingestelde quota opslaan.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo

from extras import PREFERENCE_TYPES, preference_type

POLICY_KEY = "preference_policy_v030"
PREFERENCE_KINDS = tuple(PREFERENCE_TYPES)


def belgian_today() -> date:
    return datetime.now(ZoneInfo("Europe/Brussels")).date()


def default_policy() -> dict:
    return {"open_from": None, "open_until": None, "limits": {}}


def policy_for(data: dict) -> dict:
    """Legacy maanden blijven onbeperkt open, zonder datamodelmigratie."""
    raw = data.get(POLICY_KEY)
    return raw if raw is not None else default_policy()


def validate_policy(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, dict) or set(raw) != {"open_from", "open_until", "limits"}:
        return ["Indieningsregels moeten een geldig venster en maxima bevatten."]
    errors = []
    dates = {}
    for field in ("open_from", "open_until"):
        value = raw[field]
        if value is None:
            dates[field] = None
        elif not isinstance(value, str):
            errors.append(f"Ongeldige datum voor {field}.")
        else:
            try:
                dt = date.fromisoformat(value)
                if dt.isoformat() != value:
                    raise ValueError()
                dates[field] = dt
            except ValueError:
                errors.append(f"Ongeldige datum voor {field}.")
    if not errors:
        a, b = dates["open_from"], dates["open_until"]
        if (a is None) != (b is None) or (a is not None and a > b):
            errors.append("Vul zowel begin als einde in, met het einde niet vóór het begin.")
    limits = raw["limits"]
    if not isinstance(limits, dict):
        errors.append("Voorkeursmaxima moeten een tabel zijn.")
    else:
        for kind, maximum in limits.items():
            if kind not in PREFERENCE_KINDS or type(maximum) is not int or not 0 <= maximum <= 31:
                errors.append(f"Ongeldig maximum voor voorkeurtype {kind} (0–31).")
    return errors


def is_open(raw: dict | None, today: date | None = None) -> bool:
    errors = validate_policy(raw)
    if errors:
        raise ValueError(" ".join(errors))
    policy = raw or default_policy()
    start, end = policy["open_from"], policy["open_until"]
    if start is None:
        return True
    check = today or belgian_today()
    return date.fromisoformat(start) <= check <= date.fromisoformat(end)


def counts_for(preferences: list[dict], employee_id: str) -> dict[str, int]:
    counted = Counter(preference_type(p) for p in preferences
                      if p.get("employee_id") == employee_id)
    return {kind: counted.get(kind, 0) for kind in PREFERENCE_KINDS}


def enforce_submission(raw: dict | None, employee_id: str, preferences: list[dict],
                       *, manager_override: bool = False, today: date | None = None) -> None:
    errors = validate_policy(raw)
    if errors:
        raise ValueError(" ".join(errors))
    if manager_override:
        return
    if not is_open(raw, today):
        raise ValueError("De indieningsperiode voor deze maand is gesloten. Vraag je planner om een wijziging.")
    limits = (raw or default_policy())["limits"]
    counted = counts_for(preferences, employee_id)
    for kind, limit in limits.items():
        if limit and counted[kind] > limit:
            raise ValueError(f"Maximum {limit} wensen van type '{PREFERENCE_TYPES[kind]}' voor deze maand. "
                             "Verwijder eerst een bestaande wens.")
