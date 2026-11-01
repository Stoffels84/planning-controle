"""Uitsluitend verzonnen demonstratiegegevens. Gebruik nooit echte medewerkers in de demo."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

CATEGORIES = ("Vroeg", "Dag", "Laat", "Nacht")
WEEKDAYS = ("Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag")


def next_month(reference: date | None = None) -> tuple[int, int]:
    today = reference or date.today()
    first = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    return first.year, first.month


def build_demo(year: int | None = None, month: int | None = None) -> dict:
    if year is None or month is None:
        year, month = next_month()

    shifts = [
        {"id": "V101", "name": "Vroeg 1", "category": "Vroeg", "start": "06:00", "end": "14:00", "required": 2, "location": "Demo Gent", "active": True},
        {"id": "V102", "name": "Vroeg 2", "category": "Vroeg", "start": "07:00", "end": "15:00", "required": 1, "location": "Demo Gent", "active": True},
        {"id": "D201", "name": "Dag 1", "category": "Dag", "start": "09:00", "end": "17:00", "required": 2, "location": "Demo Gent", "active": True},
        {"id": "L301", "name": "Laat 1", "category": "Laat", "start": "14:00", "end": "22:00", "required": 2, "location": "Demo Gent", "active": True},
        {"id": "N401", "name": "Nacht 1", "category": "Nacht", "start": "22:00", "end": "06:00", "required": 1, "location": "Demo Gent", "active": True},
    ]
    employees = []
    for n in range(1, 17):
        employees.append(
            {
                "id": f"DEMO{n:03d}",
                "name": f"Testcontroleur {n:02d}",
                "contract_percent": 100 if n < 13 else 80,
                "max_month_hours": 176 if n < 13 else 140,
                "max_consecutive": None if n % 5 else 4,
                "blocked_categories": ["Nacht"] if n in (3, 6) else [],
                "blocked_shifts": [],
                "blocked_weekdays": [6] if n in (4, 8) else [],
                "preferred_category": ["Vroeg", "Dag", "Laat", "Nacht"][(n - 1) % 4],
                "active": True,
            }
        )

    demand = []
    _, length = calendar.monthrange(year, month)
    for day in range(1, length + 1):
        d = date(year, month, day)
        if d.weekday() < 5:
            codes = ["V101", "V102", "D201", "L301"]
            if d.weekday() in (1, 4):
                codes.append("N401")
        else:
            codes = ["V101", "D201"]
        for code in codes:
            sh = next(x for x in shifts if x["id"] == code)
            demand.append({"date": d.isoformat(), "shift_id": code, "required": sh["required"]})

    preferences = [
        {"employee_id": "DEMO001", "date": date(year, month, 6).isoformat(), "priority": 3},
        {"employee_id": "DEMO002", "date": date(year, month, 6).isoformat(), "priority": 2},
        {"employee_id": "DEMO003", "date": date(year, month, 13).isoformat(), "priority": 3},
    ]
    return {
        "schema_version": 1,
        "year": year,
        "month": month,
        "employees": employees,
        "shifts": shifts,
        "demand": demand,
        "preferences": preferences,
        "settings": {"min_rest_hours": 11, "max_consecutive": 5, "time_limit_seconds": 300,
                     "preference_weight": 25, "fairness_weight": 1},
    }
