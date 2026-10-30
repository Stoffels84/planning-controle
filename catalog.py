"""Veilige, achterwaarts compatibele profiel- en dienstdefinities voor v0.3.

Alle velden leven in de bestaande Workspace.payload (JSON); geen destructieve
PostgreSQL-migratie nodig. De solver gebruikt de relevante harde beperkingen.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
import re

from demo_data import CATEGORIES

TIME_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d\Z")


def profile(employee: dict) -> dict:
    result = dict(employee)
    result.setdefault("team", "Demoteam")
    result.setdefault("blocked_periods", [])
    result.setdefault("blocked_weekdays", [])
    result.setdefault("blocked_categories", [])
    result.setdefault("blocked_shifts", [])
    result.setdefault("preferred_category", "Geen")
    result.setdefault("max_consecutive", None)
    result.setdefault("active", True)
    return result


def shift_details(shift: dict) -> dict:
    result = dict(shift)
    result.setdefault("location", "")
    result.setdefault("start_location", result.get("location") or "")
    result.setdefault("end_location", result.get("location") or "")
    result.setdefault("active", True)
    return result


def new_employee(identifier: str, name: str, team: str, contract_percent: int, max_month_hours: int) -> dict:
    return {
        "id": identifier.strip(), "name": name.strip(), "team": team.strip(),
        "contract_percent": int(contract_percent), "max_month_hours": int(max_month_hours),
        "max_consecutive": None, "blocked_categories": [], "blocked_shifts": [],
        "blocked_weekdays": [], "blocked_periods": [], "preferred_category": "Geen",
        "active": True,
    }


def validate_periods(periods: list[dict]) -> list[str]:
    errors = []
    ranges = []
    if not isinstance(periods, list) or len(periods) > 100:
        return ["Geef maximaal 100 onbeschikbare periodes per controleur op."]
    for i, item in enumerate(periods, 1):
        try:
            start = date.fromisoformat(item["start"])
            end = date.fromisoformat(item["end"])
            if start > end:
                errors.append(f"Periode {i}: begindatum valt na einddatum.")
            ranges.append((start, end))
        except (ValueError, TypeError, KeyError, AttributeError):
            errors.append(f"Periode {i}: ongeldige begin- of einddatum.")
    ranges.sort()
    for (_, last_end), (next_start, _) in zip(ranges, ranges[1:]):
        if next_start <= last_end:
            errors.append("Onbeschikbare periodes mogen niet overlappen.")
            break
    return errors


def validate_employee(employee: dict, known_shifts: set[str]) -> list[str]:
    e = profile(employee)
    errors = []
    key = e.get("id", "")
    if not isinstance(key, str) or not (1 <= len(key.strip()) <= 64):
        errors.append("Personeelsnummer moet 1 tot 64 tekens bevatten.")
    if not isinstance(e.get("name"), str) or not (1 <= len(e["name"].strip()) <= 160):
        errors.append(f"Controleur {key}: ongeldige naam.")
    if not isinstance(e["team"], str) or not (1 <= len(e["team"].strip()) <= 80):
        errors.append(f"Controleur {key}: team moet 1 tot 80 tekens bevatten.")
    if not isinstance(e.get("contract_percent"), int) or not (1 <= e["contract_percent"] <= 100):
        errors.append(f"Controleur {key}: arbeidspercentage buiten 1–100.")
    hours = e.get("max_month_hours")
    if not isinstance(hours, (int, float)) or isinstance(hours, bool) or not (1 <= hours <= 250):
        errors.append(f"Controleur {key}: maximaal 1–250 maanduren toegestaan.")
    consecutive = e.get("max_consecutive")
    if consecutive is not None and (not isinstance(consecutive, int) or not 1 <= consecutive <= 7):
        errors.append(f"Controleur {key}: ongeldig individueel maximum opeenvolgende werkdagen.")
    if not set(e["blocked_categories"]).issubset(CATEGORIES):
        errors.append(f"Controleur {key}: onbekende verboden dienstcategorie.")
    if not set(e["blocked_shifts"]).issubset(known_shifts):
        errors.append(f"Controleur {key}: onbekend verboden dienstnummer.")
    if not set(e["blocked_weekdays"]).issubset(set(range(7))):
        errors.append(f"Controleur {key}: ongeldige weekdagbeperking.")
    if e["preferred_category"] not in (*CATEGORIES, "Geen"):
        errors.append(f"Controleur {key}: ongeldige voorkeurscategorie.")
    errors.extend(f"Controleur {key}: {x}" for x in validate_periods(e["blocked_periods"]))
    return errors


def validate_shift(shift: dict) -> list[str]:
    s = shift_details(shift)
    errors = []
    sid = s.get("id", "")
    if not isinstance(sid, str) or not (1 <= len(sid.strip()) <= 40):
        errors.append("Dienstnummer moet 1–40 tekens bevatten.")
    if not isinstance(s.get("name"), str) or not (1 <= len(s["name"].strip()) <= 160):
        errors.append(f"Dienst {sid}: omschrijving ontbreekt of is te lang.")
    if s.get("category") not in CATEGORIES:
        errors.append(f"Dienst {sid}: ongeldige categorie.")
    if not TIME_RE.fullmatch(str(s.get("start", ""))) or not TIME_RE.fullmatch(str(s.get("end", ""))):
        errors.append(f"Dienst {sid}: gebruik uren als UU:MM.")
    else:
        start_min = int(s["start"][:2]) * 60 + int(s["start"][3:])
        end_min = int(s["end"][:2]) * 60 + int(s["end"][3:])
        duration = (end_min - start_min) % 1440 or 1440
        if duration > 16 * 60:
            errors.append(f"Dienst {sid}: langer dan 16 uur.")
    required = s.get("required")
    if not isinstance(required, int) or not 0 <= required <= 50:
        errors.append(f"Dienst {sid}: bezetting moet tussen 0 en 50 liggen.")
    for field in ("start_location", "end_location"):
        if not isinstance(s[field], str) or len(s[field]) > 120:
            errors.append(f"Dienst {sid}: ongeldige locatie.")
    return errors


def is_unavailable(employee: dict, day: date) -> bool:
    """Alleen harde individuele datumblokkeringen (geen zachte vrijwensen)."""
    e = profile(employee)
    return any(date.fromisoformat(p["start"]) <= day <= date.fromisoformat(p["end"])
               for p in e["blocked_periods"])


def is_unavailable_during(employee: dict, begin: datetime, end: datetime) -> bool:
    """Blokkeert ook een nachtdienst die over een onbeschikbare datum loopt.

    Tijdsintervallen zijn halfopen: [begin, einde). Een dienst die exact om
    middernacht eindigt, raakt de daaropvolgende vrije dag niet.
    """
    e = profile(employee)
    for p in e["blocked_periods"]:
        blocked_start = datetime.combine(date.fromisoformat(p["start"]), time.min)
        blocked_end = datetime.combine(date.fromisoformat(p["end"]) + timedelta(days=1), time.min)
        if begin < blocked_end and end > blocked_start:
            return True
    return False


def sync_required(state: dict, shift_id: str, required: int) -> None:
    """Vaste bezetting van dienstnummer doorvoeren naar deze actieve maand."""
    for row in state["demand"]:
        if row["shift_id"] == shift_id:
            row["required"] = required
