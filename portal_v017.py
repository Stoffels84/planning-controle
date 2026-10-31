"""Persoonlijke kalender en controleerbare roosterwijzigingen voor v0.17.

Dit bestand bevat uitsluitend zuivere, niet-mutatieve functies. De database
filtert gepubliceerde planningsversies op de ingelogde controleur.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta

from portal_v016 import personal_calendar, own_published_assignments

WEEKDAYS = ("Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo")
LEAVE_STATUS = {
    "pending": "In behandeling", "approved": "Goedgekeurd",
    "rejected": "Afgewezen", "withdrawn": "Ingetrokken",
}
SWAP_STATUS = {
    "pending": "Wacht op collega", "accepted": "Wacht op planner",
    "approved": "Goedgekeurd", "declined": "Geweigerd door collega",
    "withdrawn": "Ingetrokken", "rejected": "Afgewezen door planner",
}


def month_tiles(data: dict, employee_id: str, published_payload: dict | None,
                own_leave_requests: list[dict] | None = None,
                changed_days: set[str] | None = None) -> list[list[dict]]:
    """Vaste ma-zo weken met lege vakken buiten de maand (geen andere maanden).

    Verlofaanvragen met status 'pending' zijn alleen meldingen, nooit rustdagen.
    """
    year, month = int(data["year"]), int(data["month"])
    days = {r["Datum"]: r for r in personal_calendar(data, employee_id, published_payload)}
    leaves_by_day: dict[str, list[str]] = defaultdict(list)
    for request in own_leave_requests or []:
        if request.get("employee_id") != employee_id:
            continue
        status = request.get("status")
        if status not in ("pending", "approved"):
            continue
        try:
            start = date.fromisoformat(str(request["start_date"]))
            end = date.fromisoformat(str(request["end_date"]))
        except (TypeError, ValueError, KeyError):
            continue
        if end < start or (end - start).days > 366:
            continue
        day = start
        while day <= end:
            if day.year == year and day.month == month:
                leaves_by_day[day.isoformat()].append(LEAVE_STATUS[status] + " verlof")
            day += timedelta(days=1)
    changed_days = changed_days or set()
    result = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        tiles = []
        for day in week:
            if day.month != month:
                tiles.append({"in_month": False, "day": day.day, "date": day.isoformat()})
                continue
            iso = day.isoformat()
            row = days[iso]
            published = row["Gepubliceerde planning"]
            has_assignment = published_payload is not None and published != "Geen dienst toegewezen"
            has_activity = row["Activiteit"] != "—"
            if has_assignment:
                primary, category = published, "dienst"
            elif has_activity:
                primary, category = "Activiteit: " + row["Activiteit"], "activiteit"
            elif published_payload is None:
                primary, category = "Nog niet gepubliceerd", "ongepubliceerd"
            else:
                primary, category = "Geen dienst toegewezen", "zonder_dienst"
            tiles.append({"in_month": True, "day": day.day, "date": iso,
                          "weekday": WEEKDAYS[day.weekday()], "primary": primary,
                          "category": category, "wish": row["Wens"],
                          "leave": leaves_by_day.get(iso, []),
                          "changed": iso in changed_days, "hours": row["Uren"]})
        result.append(tiles)
    return result


def _assignment_signature(assignment: dict) -> tuple:
    """Vergelijk dienstinhoud, niet volgorde, personeelsnamen of solver-metadata."""
    return (str(assignment.get("Dienstnummer", "")),
            str(assignment.get("Begin", "")),
            str(assignment.get("Einde", "")),
            str(assignment.get("Uren", "")))


def _describe_assignments(rows: list[dict]) -> str:
    if not rows:
        return "Geen dienst toegewezen"
    return ", ".join(f"{r.get('Dienstnummer', '?')} ({r.get('Begin', '—')}–{r.get('Einde', '—')})"
                     for r in sorted(rows, key=_assignment_signature))


def personal_publication_changes(previous_assignments: list[dict],
                                 current_assignments: list[dict],
                                 employee_id: str) -> list[dict]:
    """Verschillen tussen twee gepubliceerde versies, alleen voor employee_id.

    Lege lijst betekent *geen* roosterwijziging; concepten tellen nooit mee.
    """
    previous_by_day: dict[str, list[dict]] = defaultdict(list)
    current_by_day: dict[str, list[dict]] = defaultdict(list)
    for r in previous_assignments:
        if r.get("Personeelsnr") == employee_id:
            previous_by_day[str(r["Datum"])].append(r)
    for r in current_assignments:
        if r.get("Personeelsnr") == employee_id:
            current_by_day[str(r["Datum"])].append(r)
    result = []
    for day in sorted(previous_by_day.keys() | current_by_day.keys()):
        before, after = previous_by_day[day], current_by_day[day]
        if sorted(map(_assignment_signature, before)) == sorted(map(_assignment_signature, after)):
            continue
        result.append({"Datum": day, "Vorige publicatie": _describe_assignments(before),
                       "Huidige publicatie": _describe_assignments(after)})
    return result


def personal_request_feed(leave_requests: list[dict], swap_requests: list[dict],
                          employee_id: str) -> dict:
    """Samenvatting van uitsluitend eigen aanvragen; geen gevoelige collega-informatie."""
    rows = []
    for r in leave_requests:
        if r.get("employee_id") != employee_id:
            continue
        rows.append({"Soort": "Verlof", "Nummer": r.get("id"),
                     "Periode": f"{r.get('start_date', '')} t/m {r.get('end_date', '')}",
                     "Status": LEAVE_STATUS.get(r.get("status"), "Onbekend"),
                     "open": r.get("status") == "pending", "created": r.get("created_at", "")})
    for r in swap_requests:
        if employee_id not in (r.get("initiator_id"), r.get("colleague_id")):
            continue
        rows.append({"Soort": "Ruil", "Nummer": r.get("id"),
                     "Periode": f"{r.get('own_day', '')} ↔ {r.get('their_day', '')}",
                     "Status": SWAP_STATUS.get(r.get("status"), "Onbekend"),
                     "open": r.get("status") in ("pending", "accepted"),
                     "created": r.get("created_at", "")})
    rows.sort(key=lambda r: (str(r["created"]), str(r["Nummer"])), reverse=True)
    return {"total": len(rows), "open": sum(r["open"] for r in rows),
            "items": [{k: v for k, v in r.items() if k not in ("open", "created")} for r in rows]}
