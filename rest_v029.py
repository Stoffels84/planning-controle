"""v0.29: minimale vrije START-dagen per voortschrijdende 7 kalenderdagen.

Een dag is gewerkt als een dienst of zelfstandige taak op die datum begint.
De regel is proefmatig en niet gelijk aan wettelijke wekelijkse rust.
Onbekende aangrenzende maanden worden niet verondersteld vrij te zijn.
"""
from datetime import date, timedelta

WINDOW_DAYS = 7


def validate_min_days_off(value):
    return value is None or (type(value) is int and 1 <= value <= 3)


def windows_for_month(year: int, month: int, known_sides=()):
    """Volledige 7-daagse vensters met minstens één datum in deze maand.

    Vensters die een maandgrens overschrijden, tellen uitsluitend als het
    gepubliceerde buurrooster van die kant beschikbaar is. Lege publicaties
    gelden als bekende vrije dagen, maar een ontbrekende publicatie niet.
    """
    start = date(year, month, 1)
    end = (start + timedelta(days=32)).replace(day=1)  # exclusief
    sides = set(known_sides)
    for offset in range(-6, (end-start).days):
        first = start + timedelta(days=offset)
        last = first + timedelta(days=6)
        if first < start and "previous" not in sides:
            continue
        if last >= end and "next" not in sides:
            continue
        yield tuple(first + timedelta(days=i) for i in range(WINDOW_DAYS))


def published_sides(data: dict, boundaries=()):
    sources = data.get("_boundary_sources") or {}
    known = {side for side in ("previous", "next") if sources.get(side) is not None}
    # Tests en oudere code kunnen wel gepubliceerde rijen, maar niet de ID's
    # aanleveren. Zo'n rij is bewijs dat de betreffende bron bestaat.
    known.update(row.get("source") for row in boundaries if row.get("source") in ("previous", "next"))
    return known


def violating_windows(year, month, current_dates, historical_dates, minimum_days_off, known_sides=()):
    if not validate_min_days_off(minimum_days_off) or minimum_days_off is None:
        raise ValueError("Ongeldig minimum vrije dagen per zeven dagen.")
    worked = set(current_dates) | set(historical_dates)
    return [window for window in windows_for_month(year, month, known_sides)
            if sum(day in worked for day in window) > WINDOW_DAYS-minimum_days_off]
