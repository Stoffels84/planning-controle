"""v0.28: optionele beperking van opeenvolgende GEWERKTE weekends.

Een weekend is gewerkt wanneer ten minste één dienst op zaterdag of zondag
begint. Het weekend wordt geïdentificeerd door de bijbehorende zaterdag.
Alleen gepubliceerde aangrenzende maanden gelden als vaste historie.
Geen wettelijke of sectorale arbeidsnorm: waarde is een proefinstelling.
"""
from __future__ import annotations

from datetime import date, timedelta

from policy_v06 import saturday_for

MAX_STREAK_SETTING = 4


def validate_weekend_streak(value) -> bool:
    return value is None or (type(value) is int and 1 <= value <= MAX_STREAK_SETTING)


def weekend_saturdays(day_strings) -> set[date]:
    """Converteert startdatums in weekends, zonder dubbeltelling za + zo."""
    days = {date.fromisoformat(str(d)) for d in day_strings}
    return {saturday_for(d) for d in days if d.weekday() >= 5}


def sliding_windows(weekends: set[date], maximum: int) -> list[tuple[date, ...]]:
    """Alle mogelijke opeenvolgende (maximum + 1)-weekendvensters.

    Geen vensters buiten het bekende datumbereik; dit voorkomt verzonnen
    historische weekenden. Missing publication history stays unknown.
    """
    if not validate_weekend_streak(maximum) or maximum is None:
        raise ValueError("Ongeldige maximale weekendreeks.")
    if not weekends:
        return []
    first = min(weekends)
    last = max(weekends)
    result = []
    cursor = first - timedelta(weeks=maximum)
    while cursor <= last:
        window = tuple(cursor + timedelta(weeks=i) for i in range(maximum + 1))
        if any(sat in weekends for sat in window):
            result.append(window)
        cursor += timedelta(weeks=1)
    return result


def violating_weekend_streaks(current_dates, adjacent_dates, maximum: int) -> list[tuple[date, ...]]:
    """Overtredingen waarbij minstens één IN DE HUIDIGE MAAND gewerkt weekend zit.

    Zaterdag in buurmaand en zondag in huidige maand behoren tot hetzelfde
    weekend. Historie uit niet-gepubliceerde maanden is niet bekend.
    """
    current = weekend_saturdays(current_dates)
    if maximum is None:
        return []
    history = weekend_saturdays(adjacent_dates)
    all_saturdays = current | history
    return [window for window in sliding_windows(all_saturdays, maximum)
            if any(sat in current for sat in window)
            and all(sat in all_saturdays for sat in window)]
