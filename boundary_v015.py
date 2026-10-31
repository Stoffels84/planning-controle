"""Lees alleen GEPUBLICEERDE aangrenzende planningen voor harde maandgrensregels.

Een maand zonder gepubliceerde buur kan niet als aantoonbaar veilig worden
beoordeeld. De bron-IDs worden met elk nieuw concept opgeslagen, zodat een
wijziging voor publicatie wordt opgemerkt.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

CATEGORIES = {"Vroeg", "Dag", "Laat", "Nacht"}


def adjacent_months(year: int, month: int) -> dict[str, tuple[int, int]]:
    current = date(year, month, 1)
    prev = current - timedelta(days=1)
    next_ = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return {"previous": (prev.year, prev.month), "next": (next_.year, next_.month)}


def published_boundary_context(engine, year: int, month: int) -> dict:
    """Vraagt de nieuwste gepubliceerde planversie per direct aangrenzende maand.

    Geen globale sessie- of database-update. De rijen bevatten de historische
    werkelijke begin- en einduren uit de PUBLICATIE, niet uit huidige catalogus.
    """
    import store

    sources = {"previous": None, "next": None}
    rows = []
    neighbours = adjacent_months(year, month)
    for side, (y, m) in neighbours.items():
        plan = store.load_plan(engine, y, m, published_only=True)
        if plan is None:
            continue
        sources[side] = plan["id"]
        for row in plan["payload"].get("assignments", []):
            rows.append({
                "employee_id": str(row["Personeelsnr"]),
                "date": str(row["Datum"]),
                "category": str(row["Categorie"]),
                "start": str(row["Begin"]),
                "end": str(row["Einde"]),
                "source": side,
            })
    return {"sources": sources, "assignments": rows}


def with_boundary_context(data: dict, context: dict) -> dict:
    state = deepcopy(data)
    state["_boundary_assignments"] = deepcopy(context["assignments"])
    state["_boundary_sources"] = deepcopy(context["sources"])
    return state


def validate_boundary_rows(data: dict) -> list[str]:
    """Afgeknipte bronrijen zijn onveilig; niet stilzwijgend negeren."""
    errors = []
    neighbours = adjacent_months(int(data["year"]), int(data["month"]))
    valid_periods = {side: (y, m) for side, (y, m) in neighbours.items()}
    for index, row in enumerate(data.get("_boundary_assignments", []), 1):
        try:
            day = date.fromisoformat(row["date"])
            side = row["source"]
            if (day.year, day.month) != valid_periods[side]:
                raise ValueError("datum valt buiten de bronmaand")
            if row["category"] not in CATEGORIES:
                raise ValueError("onbekende categorie")
            for k in ("start", "end"):
                h, m = map(int, row[k].split(":"))
                if not 0 <= h < 24 or not 0 <= m < 60:
                    raise ValueError("ongeldige tijd")
            if not row["employee_id"]:
                raise ValueError("personeelsnummer ontbreekt")
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            errors.append(f"Gepubliceerde grensdienst #{index} kan niet worden gecontroleerd: {exc}")
    return errors
