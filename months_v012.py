"""Pure hulpmiddelen voor kalendermaanden: maandinvoer gescheiden van gedeelde catalogus."""
from __future__ import annotations
from copy import deepcopy
from datetime import date

SHARED_KEYS = ("employees", "shifts", "tasks", "settings", "optimization_profiles")
MONTH_KEYS = ("demand", "preferences", "hour_credits", "task_needs")


def period_key(year: int, month: int) -> int:
    if type(year) is not int or type(month) is not int or not 2020 <= year <= 2100 or not 1 <= month <= 12:
        raise ValueError("Ongeldige kalendermaand.")
    return year * 100 + month


def shared_fields(payload: dict) -> dict:
    return {k: deepcopy(payload[k]) for k in SHARED_KEYS if k in payload}


def merge_shared(payload: dict, shared: dict) -> dict:
    combined = deepcopy(payload)
    for key in SHARED_KEYS:
        # v0.26: bestaande planningsmaanden beschikken over hun eigen
        # dienstencatalogus. Alleen legacy payloads zonder migratievlag
        # gebruiken nog de gedeelde lijst.
        if key == "shifts" and payload.get("shift_catalog_v026") is True:
            continue
        if key in shared:
            combined[key] = deepcopy(shared[key])
    return combined


def new_month_payload(year: int, month: int, source: dict) -> dict:
    """Start lege maand zonder fictieve dienstbehoefte, voorkeuren of verlofcredits."""
    period_key(year, month)
    result = deepcopy(source)
    result["year"], result["month"] = year, month
    for key in MONTH_KEYS:
        result[key] = []
    result["month_hour_regimes_v027"] = {}  # Iedere maand een eigen regime
    # Andere maand-specifieke velden krijgen geen oude inhoud mee.
    return result


def period_for_day(day: date) -> tuple[int, int]:
    return day.year, day.month
