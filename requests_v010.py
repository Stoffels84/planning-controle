"""Basisregels voor verlofaanvragen — uitsluitend fictieve testgegevens.

Afwezigheden blokkeren een VOLLEDIGE kalenderdag. Geen geldige
verlof- of loonberekening, geen goedgekeurde bedrijfsworkflow.
"""
from __future__ import annotations

from datetime import date, timedelta

STATUS_LABELS = {
    'pending': 'In behandeling',
    'approved': 'Goedgekeurd',
    'rejected': 'Afgewezen',
    'withdrawn': 'Ingetrokken',
    'cancelled': 'Goedgekeurd verlof ingetrokken',
}


def leave_days(start: date, end: date, year: int, month: int) -> list[date]:
    """Validate a request in the active month, bounded to 31 dates."""
    if not isinstance(start, date) or not isinstance(end, date) or start > end:
        raise ValueError('De begin- en einddatum zijn ongeldig.')
    if (start.year, start.month) != (year, month) or (end.year, end.month) != (year, month):
        raise ValueError('Verlof aanvragen kan voorlopig alleen binnen de actieve planningsmaand.')
    dates = []
    cursor = start
    while cursor <= end:
        dates.append(cursor)
        cursor += timedelta(days=1)
    return dates


def absence_credit(employee_id: str, date_value: date, hours: float) -> dict:
    if not 0 <= hours <= 16:
        raise ValueError('Testuren moeten tussen 0 en 16 liggen.')
    return {'employee_id': employee_id, 'date': date_value.isoformat(),
            'type': 'Verlof', 'hours': float(hours)}
