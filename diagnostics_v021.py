"""v0.21 — uitlegbare, uitsluitend indicatieve haalbaarheidscontrole.

Dit is geen tweede planningssolver. De regels die één medewerker voor één
specifieke dienst uitsluiten worden gecontroleerd met dezelfde helpers als in
planner.py. Dienstcombinaties, maandlimieten na eerdere toewijzingen, taken,
maximale werkreeksen en optimalisatie worden alleen door OR-Tools beoordeeld.

Geen rechten/toegang tot de database: de aanroeper verstrekt uitsluitend de
geautoriseerde werkruimte en de reeds opgehaalde gepubliceerde maandgrenzen.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from catalog import is_unavailable_during, profile, settings_with_defaults, transition_code
from extras import rest_blocked_during
from policy_v06 import touches_protected_weekend


LABELS = {
    "category": "Dienstcategorie uitgesloten",
    "shift": "Dienstnummer uitgesloten",
    "weekday": "Weekdag uitgesloten",
    "unavailable": "Afwezigheid of geblokkeerde periode",
    "rest_day": "Rustdag of geregistreerde activiteit",
    "protected_weekend": "Beschermd weekend",
    "boundary": "Rust/overgang met gepubliceerde buurmaand",
    "month_hours": "Maandurenmaximum onder dienstduur",
    "category_max": "Maandmaximum dienstcategorie is nul",
    "weekend_max": "Maximum weekenddagen/weekends is nul",
}


def _bounds(day: str, shift: dict) -> tuple[datetime, datetime]:
    d = date.fromisoformat(day)
    hours, minutes = [int(value) for value in shift["start"].split(":")]
    begin = datetime(d.year, d.month, d.day, hours, minutes)
    eh, em = [int(value) for value in shift["end"].split(":")]
    duration = (eh * 60 + em - (hours * 60 + minutes)) % (24 * 60) or 24 * 60
    return begin, begin + timedelta(minutes=duration)


def _boundary_blocks(emp: dict, day: str, shift: dict, context_rows: list[dict], settings: dict) -> bool:
    begin, end = _bounds(day, shift)
    current_day = date.fromisoformat(day)
    for past in context_rows:
        if past["employee_id"] != emp["id"]:
            continue
        earlier, earlier_end = _bounds(past["date"], past)
        historical_day = date.fromisoformat(past["date"])
        if earlier <= begin:
            prev_end = earlier_end
            prev_day, next_day = historical_day, current_day
            pair = transition_code(past["category"], shift["category"])
            later_start = begin
        else:
            prev_end = end
            prev_day, next_day = current_day, historical_day
            pair = transition_code(shift["category"], past["category"])
            later_start = earlier
        rest = max(float(settings["min_rest_hours"]),
                   float(emp.get("min_rest_hours") or 0),
                   float(settings["transition_rest_hours"].get(pair, 0)))
        if next_day == prev_day or later_start < prev_end + timedelta(hours=rest):
            return True
        if ((next_day - prev_day).days == 1
                and (pair in settings["blocked_transitions"]
                     or pair in emp.get("blocked_transitions", []))):
            return True
    return False


def _single_slot_block(emp: dict, day: str, shift: dict, data: dict,
                       settings: dict, boundary_rows: list[dict]) -> str | None:
    """Eén prioritaire blokkering per kandidaat; geen cumulatieve oorzaken."""
    begin, end = _bounds(day, shift)
    if shift["category"] in emp.get("blocked_categories", []):
        return "category"
    if shift["id"] in emp.get("blocked_shifts", []):
        return "shift"
    if date.fromisoformat(day).weekday() in emp.get("blocked_weekdays", []):
        return "weekday"
    if is_unavailable_during(emp, begin, end):
        return "unavailable"
    if rest_blocked_during(emp, begin, end, data.get("hour_credits", [])):
        return "rest_day"
    if touches_protected_weekend(emp, begin, end):
        return "protected_weekend"
    if _boundary_blocks(emp, day, shift, boundary_rows, settings):
        return "boundary"
    duration = (end - begin).total_seconds() / 3600
    if duration > float(emp["max_month_hours"]):
        return "month_hours"
    category = shift["category"]
    if (settings["max_month_categories"].get(category) == 0
            or emp.get("max_month_categories", {}).get(category) == 0):
        return "category_max"
    if date.fromisoformat(day).weekday() >= 5:
        if settings["max_weekend_days"] == 0 or emp.get("max_weekend_days") == 0 or emp.get("max_worked_weekends") == 0:
            return "weekend_max"
    return None


def analyze_month(data: dict, boundary_rows: list[dict] | None = None) -> dict:
    """Analyseert directe harde blokkeringen, plus een veilige dag-ondergrens.

    'Direct tekort' is een wiskundige ondergrens: wanneer minder individueel
    inzetbare kandidaten dan vereiste dienstplaatsen bestaan, kan geen solver
    de volledige dienst invullen. 'Dagtekort' geldt omdat een medewerker op
    dezelfde startdatum maximaal één dienst mag krijgen. Bij nul tekort is er
    GEEN garantie dat alle diensten in te plannen zijn.
    """
    settings = settings_with_defaults(data["settings"])
    employees = [profile(e) for e in data["employees"] if e.get("active", True)]
    shifts = {s["id"]: s for s in data["shifts"]}
    boundaries = boundary_rows if boundary_rows is not None else data.get("_boundary_assignments", [])
    slots = []
    days = defaultdict(lambda: {"required": 0, "candidate_ids": set()})
    blockers = Counter()
    total = 0
    direct_lower = 0
    for required in sorted(data["demand"], key=lambda r: (r["date"], r["shift_id"])):
        needed = int(required["required"])
        if needed <= 0:
            continue
        day = str(required["date"])
        shift = shifts[str(required["shift_id"])]
        reasons = Counter()
        available = set()
        for emp in employees:
            reason = _single_slot_block(emp, day, shift, data, settings, boundaries)
            if reason is None:
                available.add(emp["id"])
            else:
                reasons[reason] += 1
                blockers[reason] += 1
        minimum_open = max(0, needed - len(available))
        direct_lower += minimum_open
        total += needed
        days[day]["required"] += needed
        days[day]["candidate_ids"].update(available)
        important = (LABELS[reasons.most_common(1)[0][0]]
                     if reasons and reasons.most_common(1)[0][1] > 0 else "—")
        slots.append({
            "Datum": day, "Dienstnummer": shift["id"], "Categorie": shift["category"],
            "Benodigd": needed, "Direct inzetbare kandidaten": len(available),
            "Direct tekort (ondergrens)": minimum_open,
            "Aandachtspunt": ("Direct tekort" if minimum_open else "Combinaties nog te toetsen"),
            "Vaakste individuele blokkering": important,
        })
    daily = [
        {"Datum": day, "Benodigde dienstplaatsen": item["required"],
         "Unieke directe kandidaten": len(item["candidate_ids"]),
         "Dagtekort (ondergrens)": max(0, item["required"] - len(item["candidate_ids"]))}
        for day, item in sorted(days.items())
    ]
    by_reason = [
        {"Blokkering": LABELS[code], "Kandidaat-dienstcombinaties": amount}
        for code, amount in blockers.most_common()
    ]
    return {
        "slots": slots,
        "days": daily,
        "blockers": by_reason,
        "summary": {
            "service_places": total,
            "slots": len(slots),
            "direct_shortfall": direct_lower,
            "days_with_shortfall": sum(item["Dagtekort (ondergrens)"] > 0 for item in daily),
            "max_day_shortfall": max((item["Dagtekort (ondergrens)"] for item in daily), default=0),
            "active_staff": len(employees),
        },
    }


def explain_open_positions(diagnosis: dict, open_positions: list[dict]) -> list[dict]:
    """Koppelt werkelijk onvervulde posten aan indicatieve directe capaciteit."""
    by_key = {(s["Datum"], s["Dienstnummer"]): s for s in diagnosis["slots"]}
    result = []
    for row in open_positions:
        hint = by_key.get((str(row.get("Datum", "")), str(row.get("Dienstnummer", ""))))
        result.append({
            "Datum": row.get("Datum"), "Dienstnummer": row.get("Dienstnummer"),
            "Open plaatsen solver": row.get("Open plaatsen"),
            "Direct inzetbare kandidaten": hint["Direct inzetbare kandidaten"] if hint else None,
            "Direct tekort (ondergrens)": hint["Direct tekort (ondergrens)"] if hint else None,
            "Indicatie": ("Te weinig directe kandidaten" if hint and hint["Direct tekort (ondergrens)"] > 0
                         else "Mogelijke combinatie-, uren-, weekend- of taakbeperking; niet bewezen"),
        })
    return result
