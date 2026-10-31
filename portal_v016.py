"""Persoonlijke maand-/weekoverzichten v0.16, zonder Streamlit- of databaselogica.

Alleen de gegevens van de aangemelde controleur mogen aan de UI worden doorgegeven.
Een wens is altijd vrijblijvend. Een gepubliceerde toewijzing is afzonderlijke data.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
from itertools import groupby

from daily_v091 import days_in_month, current_daily_choices, shifts_by_day
from extras import preference_type

DAYS_NL = ("Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo")
PRIORITIES = {1: "Laag", 2: "Normaal", 3: "Hoog"}


def month_weeks(data: dict) -> list[dict]:
    """ISO-weken van de geselecteerde maand; geen dagen van andere maanden."""
    result = []
    for (iso_year, iso_week), group in groupby(days_in_month(data),
                                                 key=lambda d: (d.isocalendar().year, d.isocalendar().week)):
        days = list(group)
        result.append({"key": f"{iso_year}-{iso_week:02d}", "days": days,
                       "label": f"Week {iso_week} · {days[0]:%d/%m} – {days[-1]:%d/%m}"})
    return result


def preference_summary(data: dict, employee_id: str) -> dict:
    choices = current_daily_choices(data, employee_id)
    shift = sum(preference_type(p) == "daily_shift" for p in choices.values())
    free = sum(preference_type(p) == "free_day" for p in choices.values())
    return {"shift": shift, "free": free, "unselected": len(days_in_month(data)) - shift - free}


def week_choices(data: dict, employee_id: str, week_days: list[date]) -> dict[str, dict]:
    """Levert alleen keuzen voor de zichtbare week; vervallen diensten blijven herkenbaar."""
    old = current_daily_choices(data, employee_id)
    choices = {}
    for day in week_days:
        iso = day.isoformat()
        pref = old.get(iso, {})
        kind = preference_type(pref) if pref else ""
        choices[iso] = ({"kind": "shift", "shift_id": pref.get("shift_id", ""),
                         "priority": pref.get("priority", 2)} if kind == "daily_shift" else
                        {"kind": "free", "priority": pref.get("priority", 2)} if kind == "free_day" else
                        {"kind": "none", "priority": 2})
    return choices


def save_week_choices(data: dict, employee_id: str, week_days: list[date], choices: dict[str, dict]) -> dict:
    """Atomair de week vervangen, zonder andere weken of aanvullende wensen te wijzigen."""
    valid = {day.isoformat() for day in days_in_month(data)}
    expected = {day.isoformat() for day in week_days}
    if not expected or not expected <= valid or set(choices) != expected:
        raise ValueError("De weekkeuzes moeten precies overeenkomen met de gekozen week.")
    if employee_id not in {e["id"] for e in data["employees"]}:
        raise ValueError("Onbekende controleur.")
    available = shifts_by_day(data)
    replacement = []
    for day in sorted(expected):
        choice = choices[day]
        kind = choice.get("kind")
        if kind == "none":
            continue
        priority = choice.get("priority")
        if type(priority) is not int or priority not in PRIORITIES:
            raise ValueError(f"Ongeldige prioriteit op {day}.")
        if kind == "free":
            replacement.append({"employee_id": employee_id, "type": "free_day",
                                "date": day, "priority": priority})
        elif kind == "shift":
            sid = choice.get("shift_id")
            if sid not in {s["id"] for s in available.get(day, [])}:
                raise ValueError(f"Dienst {sid} is op {day} niet langer beschikbaar.")
            replacement.append({"employee_id": employee_id, "type": "daily_shift", "date": day,
                                "shift_id": sid, "priority": priority})
        else:
            raise ValueError(f"Onbekende keuze op {day}.")
    updated = deepcopy(data)
    updated["preferences"] = [
        p for p in data["preferences"]
        if not (p.get("employee_id") == employee_id and p.get("date") in expected
                and preference_type(p) in ("free_day", "daily_shift"))
    ] + replacement
    return updated


def own_published_assignments(published_payload: dict | None, employee_id: str) -> dict[str, list[dict]]:
    """Filter op personeelsnummer VOORDAT de records de pagina bereiken."""
    result = defaultdict(list)
    if not published_payload:
        return {}
    for item in published_payload.get("assignments", []):
        if item.get("Personeelsnr") == employee_id:
            result[item["Datum"]].append(item)
    return dict(result)


def personal_calendar(data: dict, employee_id: str, published_payload: dict | None = None) -> list[dict]:
    """Neutrale statusregels voor de maand; 'geen dienst' is niet automatisch rustdag."""
    prefs = current_daily_choices(data, employee_id)
    assigned = own_published_assignments(published_payload, employee_id)
    credits = {r["date"]: r["type"] for r in data.get("hour_credits", [])
               if r.get("employee_id") == employee_id}
    rows = []
    for day in days_in_month(data):
        iso = day.isoformat()
        pref = prefs.get(iso)
        kind = preference_type(pref) if pref else None
        if kind == "daily_shift":
            wish = f"Dienst {pref['shift_id']} ({PRIORITIES.get(pref.get('priority'), '?')})"
        elif kind == "free_day":
            wish = f"Liefst vrij ({PRIORITIES.get(pref.get('priority'), '?')})"
        else:
            wish = "Geen voorkeur"
        entries = assigned.get(iso, [])
        plan = ", ".join(f"{r['Dienstnummer']} · {r.get('Begin', '—')}–{r.get('Einde', '—')}"
                         for r in entries) if entries else "Geen dienst toegewezen" if published_payload else "Nog niet gepubliceerd"
        rows.append({"Datum": iso, "Dag": DAYS_NL[day.weekday()],
                     "Wens": wish, "Gepubliceerde planning": plan,
                     "Activiteit": credits.get(iso, "—"),
                     "Uren": round(sum(float(r.get("Uren", 0)) for r in entries), 2)})
    return rows
