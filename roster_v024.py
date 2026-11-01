"""v0.24 — alleen-lezen roostercontrole voor beheerders.

Maakt een week- of maandmatrix van een BEWAARDE planpayload.
Geen afgeleide gegevens worden teruggeschreven naar de werkruimte of planner.
"""
from __future__ import annotations

import calendar
import io
from collections import defaultdict
from datetime import date

WEEKDAYS = ("Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo")


def month_days(year: int, month: int) -> list[str]:
    if not 1 <= int(month) <= 12 or not 2000 <= int(year) <= 2100:
        raise ValueError("Ongeldige planningsmaand.")
    return [date(int(year), int(month), d).isoformat()
            for d in range(1, calendar.monthrange(int(year), int(month))[1] + 1)]


def week_windows(year: int, month: int) -> list[dict]:
    """Weekvensters zijn binnen de geselecteerde maand begrensd."""
    valid = set(month_days(year, month))
    windows = []
    for index, week in enumerate(calendar.Calendar(firstweekday=0).monthdatescalendar(year, month), 1):
        days = [day.isoformat() for day in week if day.isoformat() in valid]
        if days:
            first, last = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
            windows.append({"key": f"week-{index}", "label": f"Week {index} · {first:%d/%m}–{last:%d/%m}", "days": days})
    return windows


def _regular(row: dict) -> bool:
    return (row.get("Soort") != "Zelfstandige taak"
            and not str(row.get("Dienstnummer", "")).startswith("TAAK:"))


def _month_context(data: dict, plan: dict, selected_ids: list[str] | None,
                   days: list[str] | None) -> tuple[list[dict], list[str], dict]:
    valid_days = set(month_days(data["year"], data["month"]))
    selected_days = list(days) if days is not None else sorted(valid_days)
    if not selected_days or len(selected_days) != len(set(selected_days)) or any(d not in valid_days for d in selected_days):
        raise ValueError("Selecteer uitsluitend datums uit de actieve maand.")
    employees = data.get("employees", [])
    allowed = {str(e["id"]): e for e in employees}
    requested = list(selected_ids) if selected_ids is not None else sorted(allowed)
    if len(requested) != len(set(requested)) or any(eid not in allowed for eid in requested):
        raise ValueError("Ongeldige of dubbele controleurselectie.")
    personnel = sorted((allowed[eid] for eid in requested), key=lambda e: (str(e.get("name", "")).casefold(), str(e["id"])))
    payload = plan.get("payload", plan) if isinstance(plan, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    return personnel, selected_days, payload


def _label(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{WEEKDAYS[d.weekday()]} {d:%d/%m}"


def roster_grid(data: dict, plan: dict, selected_ids: list[str] | None = None,
                days: list[str] | None = None, show_times: bool = True) -> dict:
    """Alleen personeel uit de gedeelde catalogus, nooit onbekende IDs uit oude plannen.

    Reguliere diensten en zelfstandige taken worden zichtbaar onderscheiden.
    Twee opdrachten op dezelfde dag blijven beide leesbaar.
    """
    personnel, selected_days, payload = _month_context(data, plan, selected_ids, days)
    selected = {str(p["id"]) for p in personnel}
    valid_days = set(selected_days)
    by_slot: dict[tuple[str, str], list[str]] = defaultdict(list)
    task_count = 0
    regular_count = 0
    # De solver kan zelfstandige taken in beide lijsten opnemen.
    # Toon dezelfde taak nooit tweemaal op één dag.
    shown_standalone: set[tuple[str, str, str]] = set()
    for item in payload.get("assignments", []) or []:
        if not isinstance(item, dict):
            continue
        eid, iso = str(item.get("Personeelsnr", "")), str(item.get("Datum", ""))
        if eid not in selected or iso not in valid_days:
            continue
        code = str(item.get("Dienstnummer", "?"))
        if _regular(item):
            regular_count += 1
            shown = code
        else:
            task_count += 1
            shown = "Taak " + code.removeprefix("TAAK:")
            shown_standalone.add((eid, iso, code.removeprefix("TAAK:")))
        if show_times and item.get("Begin") and item.get("Einde"):
            shown += f" ({item['Begin']}–{item['Einde']})"
        by_slot[(eid, iso)].append(shown)
    for item in payload.get("task_assignments", []) or []:
        if not isinstance(item, dict):
            continue
        eid, iso = str(item.get("Personeelsnr", "")), str(item.get("Datum", ""))
        if eid not in selected or iso not in valid_days:
            continue
        code = str(item.get("Taakcode") or item.get("Taak") or "?")
        if (eid, iso, code) in shown_standalone:
            continue
        shown = f"Taak {code}"
        if show_times and item.get("Begin") and item.get("Einde"):
            shown += f" ({item['Begin']}–{item['Einde']})"
        task_count += 1
        by_slot[(eid, iso)].append(shown)
    cols = [_label(iso) for iso in selected_days]
    rows = []
    for p in personnel:
        eid = str(p["id"])
        row = {"Controleur": str(p.get("name", eid)), "Personeelsnr": eid}
        for iso, label in zip(selected_days, cols):
            row[label] = " / ".join(sorted(by_slot[(eid, iso)])) or "—"
        rows.append(row)
    return {"days": selected_days, "columns": cols, "rows": rows,
            "people": len(personnel), "regular_assignments": regular_count,
            "task_assignments": task_count}


def staffing_grid(data: dict, plan: dict, days: list[str] | None = None) -> list[dict]:
    """Behoefte versus bezetting uit reguliere diensten, zonder takentoewijzingen.

    Extra toewijzingen boven bezetting worden apart gerapporteerd (niet als negatieve vacatures).
    """
    _, selected_days, payload = _month_context(data, plan, [], days)
    permitted = set(selected_days)
    required: dict[tuple[str, str], int] = defaultdict(int)
    filled: dict[tuple[str, str], int] = defaultdict(int)
    for demand in data.get("demand", []):
        key = (str(demand.get("date")), str(demand.get("shift_id")))
        if key[0] in permitted:
            required[key] += max(0, int(demand.get("required", 0)))
    for row in payload.get("assignments", []) or []:
        if not isinstance(row, dict) or not _regular(row):
            continue
        key = (str(row.get("Datum")), str(row.get("Dienstnummer")))
        if key[0] in permitted and key in required:
            filled[key] += 1
    result = []
    for iso in selected_days:
        keys = [k for k in required if k[0] == iso]
        need = sum(required[k] for k in keys)
        actual = sum(min(required[k], filled[k]) for k in keys)
        extra = sum(max(0, filled[k] - required[k]) for k in keys)
        result.append({"Datum": iso, "Benodigd": need, "Ingevuld": actual,
                       "Open": max(0, need - actual), "Extra": extra})
    return result


def workbook_bytes(matrix: dict, coverage: list[dict]) -> bytes:
    """Excel-export van dezelfde selectie; neutraliseer formules in invoervelden."""
    import pandas as pd
    from report_v019 import safe_excel_rows
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(safe_excel_rows(matrix["rows"]),
                     columns=["Controleur", "Personeelsnr"] + matrix["columns"]).to_excel(
                         writer, index=False, sheet_name="Roostermatrix")
        pd.DataFrame(coverage, columns=["Datum", "Benodigd", "Ingevuld", "Open", "Extra"]).to_excel(
            writer, index=False, sheet_name="Bezetting")
    return output.getvalue()
