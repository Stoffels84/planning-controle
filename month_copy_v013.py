"""v0.13: maandbehoefte overnemen zonder roosters of wensen mee te kopiëren."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import calendar

COPY_MODES = ("weekday", "date")


def weekday_occurrences(year: int, month: int) -> dict[int, list[date]]:
    days = calendar.monthrange(year, month)[1]
    result: dict[int, list[date]] = defaultdict(list)
    for i in range(1, days + 1):
        day = date(year, month, i)
        result[day.weekday()].append(day)
    return result


def _translate_date(source_day: date, to_year: int, to_month: int, mode: str,
                    source_weekdays: dict[int, list[date]],
                    target_weekdays: dict[int, list[date]]) -> date | None:
    if mode == "date":
        if source_day.day > calendar.monthrange(to_year, to_month)[1]:
            return None
        return date(to_year, to_month, source_day.day)
    source_days = source_weekdays[source_day.weekday()]
    source_ordinal = source_days.index(source_day)
    target_days = target_weekdays[source_day.weekday()]
    if source_ordinal >= len(target_days):
        return None
    return target_days[source_ordinal]


def copy_month_demand_rows(source: dict, target_year: int, target_month: int,
                           shifts: list[dict], mode: str = "weekday") -> list[dict]:
    """Kopieer uitsluitend datum/dienstnummer/bezetting; geen voorkeuren, taken of roosters.

    weekday: 1e maandag -> 1e maandag enz. Indien de doelmaand een extra
             vijfde weekdag heeft, wordt het patroon van de laatste
             overeenkomstige weekdag van de bron herhaald.
    date: dezelfde dag van de maand; niet-bestaande datums vallen weg.

    Voor elke rij geldt de ACTUELE dienstbezetting uit de centrale catalogus.
    """
    if mode not in COPY_MODES:
        raise ValueError("Onbekende kopieermethode.")
    source_year, source_month = int(source["year"]), int(source["month"])
    date(source_year, source_month, 1)
    date(target_year, target_month, 1)
    if (source_year, source_month) == (target_year, target_month):
        raise ValueError("Kies een andere bronmaand dan de doelmaand.")
    catalog = {str(s["id"]): s for s in shifts if s.get("active", True)}
    source_weekdays = weekday_occurrences(source_year, source_month)
    target_weekdays = weekday_occurrences(target_year, target_month)
    # Per brondag zijn er 0, 1 of meer diensten. De bron kan bijvoorbeeld
    # een 5e maandag hebben terwijl het doel er slechts 4 heeft.
    by_day: dict[date, list[str]] = defaultdict(list)
    observed = set()
    for row in source.get("demand", []):
        src_day = date.fromisoformat(row["date"])
        sid = str(row["shift_id"])
        if (src_day.year, src_day.month) != (source_year, source_month):
            raise ValueError("De bron bevat een dienstdatum buiten de bronmaand.")
        if (src_day, sid) in observed:
            raise ValueError(f"Dubbele broninvoer: {src_day} / {sid}.")
        observed.add((src_day, sid))
        if sid not in catalog:
            raise ValueError(f"Dienst {sid} bestaat niet meer of is gedeactiveerd. Controleer eerst de dienstcatalogus.")
        by_day[src_day].append(sid)

    result: list[dict] = []
    if mode == "weekday":
        for weekday, target_days in target_weekdays.items():
            source_days = source_weekdays[weekday]
            for ordinal, dst_day in enumerate(target_days):
                # Soms heeft de doelmaand een 5e maandag, maar de bronmaand
                # slechts vier. Herhaal dan de laatste bron-maandag.
                source_day = source_days[min(ordinal, len(source_days) - 1)]
                for sid in by_day.get(source_day, []):
                    result.append({"date": dst_day.isoformat(), "shift_id": sid,
                                   "required": int(catalog[sid]["required"])})
    else:
        for src_day, services in sorted(by_day.items()):
            dst_day = _translate_date(src_day, target_year, target_month, mode,
                                      source_weekdays, target_weekdays)
            if dst_day is None:
                continue
            for sid in services:
                result.append({"date": dst_day.isoformat(), "shift_id": sid,
                               "required": int(catalog[sid]["required"])})
    result.sort(key=lambda r: (r["date"], r["shift_id"]))
    return result
