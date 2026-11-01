"""v0.6: puur rekenbare PROEF-regels voor weekend, maandcategorieën en uren.

Geen officiële arbeidsrechtelijke normen, loonberekening of historische registratie.
Weekenddag = de startdatum van een dienst die op zaterdag of zondag start.
Een beschermd weekend blokkeert ook nachtdiensten die zaterdag/zondag overlappen.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from demo_data import CATEGORIES


def saturday_for(day: date) -> date:
    """Zaterdag van de week waartoe deze datum behoort (ook vanuit zondag)."""
    return day - timedelta(days=(day.weekday()-5) % 7)


def weekend_start_dates(year: int, month: int) -> list[str]:
    """Alle zaterdagen waarvan ten minste één weekenddag in de maand valt."""
    first = date(year, month, 1)
    after = (first + timedelta(days=32)).replace(day=1)
    saturdays = set()
    cursor = first
    while cursor < after:
        if cursor.weekday() >= 5:
            saturdays.add(saturday_for(cursor).isoformat())
        cursor += timedelta(days=1)
    return sorted(saturdays)


def touches_protected_weekend(employee: dict, start: datetime, end: datetime) -> bool:
    """Volle weekendbescherming: [za 00:00, ma 00:00) en elke overlap."""
    for iso in employee.get('protected_weekends', []):
        saturday = date.fromisoformat(iso)
        begin = datetime.combine(saturday, time.min)
        finish = begin + timedelta(days=2)
        if start < finish and end > begin:
            return True
    return False


def validate_v06_employee(employee: dict) -> list[str]:
    errors = []
    eid = employee.get('id', '?')
    from weekend_v028 import validate_weekend_streak
    if not validate_weekend_streak(employee.get("max_consecutive_worked_weekends")):
        errors.append(f"Controleur {eid}: maximum opeenvolgende weekends moet 1–4 zijn of leeg.")
    for name in ('max_weekend_days', 'max_worked_weekends'):
        val = employee.get(name)
        if val is not None and (type(val) is not int or not 0 <= val <= 10):
            errors.append(f'Controleur {eid}: {name} moet 0–10 zijn of leeg.')
    for name in ('max_month_categories', 'target_month_categories'):
        vals = employee.get(name, {})
        if not isinstance(vals, dict):
            errors.append(f'Controleur {eid}: {name} moet een categorie-tabel zijn.')
        else:
            for cat, val in vals.items():
                if cat not in CATEGORIES or type(val) is not int or not 0 <= val <= 31:
                    errors.append(f'Controleur {eid}: ongeldige {name} voor {cat}.')
    for name in ('opening_hour_balance',):
        val = employee.get(name, 0)
        if type(val) not in (int, float) or not -80 <= val <= 80:
            errors.append(f'Controleur {eid}: startsaldo moet tussen −80 en +80 uur liggen.')
    val = employee.get('historic_weekend_days', 0)
    if type(val) is not int or not 0 <= val <= 200:
        errors.append(f'Controleur {eid}: historische weekenddagen moeten 0–200 zijn.')
    protected = employee.get('protected_weekends', [])
    if (not isinstance(protected, list) or len(protected) > 60 or
            any(not isinstance(iso, str) for iso in protected) or
            len(protected) != len(set(protected))):
        errors.append(f'Controleur {eid}: ongeldige lijst beschermde weekends.')
    else:
        for iso in protected:
            try:
                if date.fromisoformat(iso).weekday() != 5:
                    errors.append(f'Controleur {eid}: beschermd weekend moet met zaterdag beginnen.')
            except (ValueError, TypeError):
                errors.append(f'Controleur {eid}: ongeldige weekenddatum.')
    for cat, target in employee.get('target_month_categories', {}).items():
        maximum = employee.get('max_month_categories', {}).get(cat)
        if maximum is not None and target > maximum:
            errors.append(f'Controleur {eid}: streefwaarde {cat} ligt boven het persoonlijke maximum.')
    return errors


def validate_v06_settings(settings: dict) -> list[str]:
    errors = []
    for field in ('max_month_categories',):
        values = settings.get(field, {})
        if not isinstance(values, dict):
            errors.append('Algemene maandcategoriegrenzen moeten een tabel zijn.')
        else:
            for cat, val in values.items():
                if cat not in CATEGORIES or type(val) is not int or not 0 <= val <= 31:
                    errors.append(f'Ongeldig algemeen maandmaximum: {cat}.')
    maximum = settings.get('max_weekend_days')
    if maximum is not None and (type(maximum) is not int or not 0 <= maximum <= 10):
        errors.append('Algemeen maximaal aantal weekenddagen moet 0–10 zijn of leeg.')
    mode = settings.get('use_opening_balance', False)
    if type(mode) is not bool:
        errors.append('Gebruik van startsaldo moet aan of uit zijn.')
    return errors


def hours_overview(employees: list[dict], assignments: list[dict], credits: list[dict], use_balance: bool) -> list[dict]:
    """Planningssimulatie, uitdrukkelijk GEEN officieel overdraagbaar urensaldo."""
    worked = defaultdict(float)
    credited = defaultdict(float)
    for row in assignments:
        worked[row['Personeelsnr']] += float(row['Uren'])
    for row in credits:
        credited[row['employee_id']] += float(row['hours'])
    output = []
    for employee in employees:
        eid = employee['id']
        planned = round(worked[eid], 2)
        credit = round(credited[eid], 2)
        target = float(employee.get('target_month_hours', 0))
        opening = float(employee.get('opening_hour_balance', 0)) if use_balance else 0.0
        output.append({'Personeelsnr': eid, 'Controleur': employee['name'],
                       'Planuren': planned, 'Activiteitscredits': credit,
                       'Streefuren (test)': target if target else None,
                       'Startsaldo (test)': round(opening, 2),
                       'Afwijking (test)': round(planned + credit - target, 2) if target else None,
                       'Eindsaldo (test)': round(opening + planned + credit - target, 2) if target else None})
    return output


def service_overview(employees: list[dict], assignments: list[dict]) -> list[dict]:
    counts = defaultdict(lambda: defaultdict(int))
    worked_weekends = defaultdict(set)
    for row in assignments:
        eid = row['Personeelsnr']
        cat = row['Categorie']
        day = date.fromisoformat(row['Datum'])
        counts[eid][cat] += 1
        if day.weekday() >= 5:
            counts[eid]['weekend_days'] += 1
            worked_weekends[eid].add(saturday_for(day).isoformat())
    rows = []
    for emp in employees:
        eid = emp['id']
        rows.append({'Personeelsnr': eid, 'Controleur': emp['name'],
                     **{cat: counts[eid][cat] for cat in CATEGORIES},
                     'Weekenddagen': counts[eid]['weekend_days'],
                     'Gewerkte weekends': len(worked_weekends[eid]),
                     'Historische weekenddagen (handmatig)': emp.get('historic_weekend_days', 0)})
    return rows
