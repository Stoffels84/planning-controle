"""V0.5: zachte wensen, vaste rustdagen en urenregistratie (fictieve testdata).

Geen loon-/overurenberekening: toegekende uren zijn uitsluitend planningscredits.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from demo_data import CATEGORIES

PREFERENCE_TYPES = {
    "free_day": "Gewenste vrije dag",
    "daily_shift": "Gewenst dienstnummer op datum",
    "work_day": "Gewenste werkdag",
    "category": "Dienstcategorie (liefst / vermijden)",
    "shift": "Dienstnummer (liefst / vermijden)",
    "weekly_free": "Wekelijks liefst vrij",
    "avoid_transition": "Dienstcombinatie liefst vermijden",
}
CREDIT_TYPES = ("Verlof", "Ziekte", "Opleiding", "Feestdag", "Bijzondere opdracht", "Andere")
REST_MODES = {"automatic": "Automatisch", "fixed": "Vast", "mixed": "Combinatie"}


def preference_type(p: dict) -> str:
    return p.get("type", "free_day")


def preference_identity(p: dict) -> tuple:
    kind = preference_type(p)
    key = {"free_day": (p.get("date"),), "daily_shift": (p.get("date"),), "work_day": (p.get("date"),),
           "category": (p.get("category"), p.get("direction")),
           "shift": (p.get("shift_id"), p.get("direction")),
           "weekly_free": (p.get("weekday"),),
           "avoid_transition": (p.get("transition"),)}.get(kind, ())
    return (p.get("employee_id"), kind, *key)


def preference_description(p: dict) -> str:
    kind = preference_type(p)
    if kind in ("free_day", "work_day"):
        return p.get("date", "")
    if kind == "daily_shift":
        return f"{p.get('date', '')} — dienst {p.get('shift_id', '')}"
    if kind == "category":
        return ("Liefst " if p.get("direction") == "prefer" else "Vermijd ") + p.get("category", "")
    if kind == "shift":
        return ("Liefst " if p.get("direction") == "prefer" else "Vermijd ") + p.get("shift_id", "")
    if kind == "weekly_free":
        return ("ma", "di", "wo", "do", "vr", "za", "zo")[p["weekday"]]
    if kind == "avoid_transition":
        return p.get("transition", "")
    return ""


def validate_extras(data: dict) -> list[str]:
    errors = []
    eids = {e["id"] for e in data["employees"]}
    shmap = {s["id"]: s for s in data["shifts"]}
    year, month = int(data["year"]), int(data["month"])
    seen = set()
    for i, p in enumerate(data.get("preferences", []), 1):
        kind = preference_type(p)
        if kind not in PREFERENCE_TYPES:
            errors.append(f"Voorkeur {i}: onbekend voorkeurtype.")
            continue
        if p.get("employee_id") not in eids or type(p.get("priority")) is not int or not 1 <= p["priority"] <= 3:
            errors.append(f"Voorkeur {i}: ongeldige controleur of prioriteit.")
        try:
            if kind in ("free_day", "work_day", "daily_shift"):
                d = date.fromisoformat(p["date"])
                if (d.year, d.month) != (year, month):
                    errors.append(f"Voorkeur {i}: datum buiten planningsmaand.")
                if kind == "daily_shift" and (not isinstance(p.get("shift_id"), str)
                                             or not p["shift_id"].strip()):
                    errors.append(f"Voorkeur {i}: ongeldig dienstnummer op datum.")
                # Eerder gekozen diensten mogen later verdwijnen uit de catalogus:
                # toon ze als verouderd in het formulier; blokkeer geen dienstbeheer.
            elif kind == "category":
                if p.get("category") not in CATEGORIES or p.get("direction") not in ("prefer", "avoid"):
                    errors.append(f"Voorkeur {i}: ongeldige categorie of richting.")
            elif kind == "shift":
                if p.get("shift_id") not in shmap or p.get("direction") not in ("prefer", "avoid"):
                    errors.append(f"Voorkeur {i}: ongeldig dienstnummer of richting.")
            elif kind == "weekly_free":
                if type(p.get("weekday")) is not int or not 0 <= p["weekday"] <= 6:
                    errors.append(f"Voorkeur {i}: ongeldige weekdag.")
            elif kind == "avoid_transition":
                if p.get("transition") not in {f"{a}>{b}" for a in CATEGORIES for b in CATEGORIES}:
                    errors.append(f"Voorkeur {i}: ongeldige dienstcombinatie.")
        except (KeyError, TypeError, ValueError):
            errors.append(f"Voorkeur {i}: ontbrekende of ongeldige waarde.")
        identity = preference_identity(p)
        if identity in seen:
            errors.append(f"Dubbele voorkeur bij {p.get('employee_id')}: {kind}.")
        seen.add(identity)
    credit_ids = set()
    if len(data.get("hour_credits", [])) > 3000:
        errors.append("Maximaal 3000 geregistreerde activiteiten per testmaand.")
    for i, credit in enumerate(data.get("hour_credits", []), 1):
        try:
            day = date.fromisoformat(credit["date"])
            ident = (credit["employee_id"], credit["date"])
            if credit["employee_id"] not in eids or (day.year, day.month) != (year, month):
                errors.append(f"Activiteit {i}: onbekende controleur of datum buiten planningsmaand.")
            if credit["type"] not in CREDIT_TYPES:
                errors.append(f"Activiteit {i}: onbekend activiteitstype.")
            if type(credit["hours"]) not in (int, float) or not 0 <= credit["hours"] <= 16:
                errors.append(f"Activiteit {i}: uren moeten tussen 0 en 16 liggen.")
            if ident in credit_ids:
                errors.append(f"Dubbele activiteit voor {ident[0]} op {ident[1]}.")
            credit_ids.add(ident)
        except (KeyError, ValueError, TypeError):
            errors.append(f"Activiteit {i}: ongeldige gegevens.")
    return errors


def rest_blocked_during(employee: dict, begin: datetime, end: datetime, credits: list[dict]) -> bool:
    """Bijkomende vaste rust of hele-dag-activiteiten blokkeren alle overlap.

    In 'automatic' modus leggen vaste rustinstellingen niets op. Nacht 22-06
    overlapt de volgende kalenderdag en is dan dus niet inzetbaar.
    """
    mode = employee.get("rest_mode", "automatic")
    weekdays = set(employee.get("fixed_rest_weekdays", [])) if mode in ("fixed", "mixed") else set()
    days = set(employee.get("fixed_rest_dates", [])) if mode in ("fixed", "mixed") else set()
    activity_days = {r["date"] for r in credits if r["employee_id"] == employee["id"]}
    cursor = begin.date()
    last_day = (end - timedelta(microseconds=1)).date()
    while cursor <= last_day:
        if cursor.weekday() in weekdays or cursor.isoformat() in days or cursor.isoformat() in activity_days:
            return True
        cursor += timedelta(days=1)
    return False


def summarize_hours(employees: list[dict], assignments: list[dict], credits: list[dict]) -> list[dict]:
    """Planuren en afzonderlijk geregistreerde credits; GEEN wettelijk urensaldo."""
    worked = defaultdict(float)
    credited = defaultdict(float)
    for row in assignments:
        worked[row["Personeelsnr"]] += float(row["Uren"])
    for row in credits:
        credited[row["employee_id"]] += float(row["hours"])
    result = []
    for e in employees:
        a = round(worked[e["id"]], 2)
        c = round(credited[e["id"]], 2)
        target = float(e.get("target_month_hours", 0))
        result.append({"Personeelsnr": e["id"], "Controleur": e["name"],
                       "Geplande uren": a, "Geregistreerde uren": c,
                       "Totaal meegeteld": round(a + c, 2),
                       "Streefuren": target if target else None,
                       "Afwijking streefuren": round(a + c - target, 2) if target else None})
    return result
