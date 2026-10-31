"""V0.22 — gecontroleerde deelvergrendeling voor heroptimalisatie.

Deze module bevat uitsluitend pure datafuncties. De CP-SAT-planner beslist of
alle harde regels met de gekozen vaste diensten verenigbaar zijn.
"""
from __future__ import annotations

from collections import Counter
from datetime import date

FIELDS = ("Datum", "Dienstnummer", "Personeelsnr")
MAX_LOCKS = 500


def assignment_key(row: dict) -> tuple[str, str, str]:
    if not isinstance(row, dict):
        raise ValueError("Een vaste toewijzing moet een gegevensrij zijn.")
    try:
        key = tuple(row[k] for k in FIELDS)
    except KeyError as exc:
        raise ValueError("Een vaste toewijzing mist datum, dienstnummer of personeelsnummer.") from exc
    if any(not isinstance(v, str) or not v.strip() or v != v.strip() for v in key):
        raise ValueError("Vaste toewijzingen hebben geldige, niet-lege tekstvelden nodig.")
    return key


def validate_locks(data: dict, rows: list[dict]) -> list[dict]:
    """Normaliseer en controleer integriteit, zonder inzetbaarheid te suggereren.

    Inzetbaarheid en gecombineerde harde arbeidsregels blijven volledig aan
    dezelfde OR-Tools-solver als een normale maandberekening overgelaten.
    """
    if not isinstance(rows, list) or len(rows) > MAX_LOCKS:
        raise ValueError(f"Kies maximaal {MAX_LOCKS} vaste diensttoewijzingen.")
    offered = {(r["date"], r["shift_id"]): int(r["required"])
               for r in data.get("demand", []) if int(r["required"]) > 0}
    active = {e["id"] for e in data.get("employees", []) if e.get("active", True)}
    seen: set[tuple[str, str, str]] = set()
    per_shift: Counter = Counter()
    per_person_day: set[tuple[str, str]] = set()
    normalized = []
    for row in rows:
        day, sid, employee_id = assignment_key(row)
        try:
            parsed = date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError(f"Ongeldige datum in vaste toewijzing: {day}.") from exc
        if (parsed.year, parsed.month) != (int(data["year"]), int(data["month"])):
            raise ValueError(f"Vaste dienst {sid} valt buiten de actieve planningsmaand.")
        if sid.startswith("TAAK:"):
            raise ValueError("Zelfstandige taken kunnen in v0.22 niet afzonderlijk vastgezet worden.")
        if (day, sid) not in offered:
            raise ValueError(f"Dienst {sid} op {day} komt niet voor in de actuele maandbehoefte.")
        if employee_id not in active:
            raise ValueError(f"Controleur {employee_id} is niet actief in de actuele maand.")
        key = (day, sid, employee_id)
        if key in seen:
            raise ValueError("Eenzelfde diensttoewijzing werd meermaals vastgezet.")
        seen.add(key)
        if (day, employee_id) in per_person_day:
            raise ValueError(f"Controleur {employee_id} is op {day} tweemaal vastgezet.")
        per_person_day.add((day, employee_id))
        per_shift[day, sid] += 1
        if per_shift[day, sid] > offered[day, sid]:
            raise ValueError(f"Er zijn meer vaste controleurs dan gewone dienstplaatsen voor {sid} op {day}.")
        normalized.append(dict(zip(FIELDS, key)))
    return sorted(normalized, key=lambda r: assignment_key(r))


def reoptimization_diff(previous: list[dict], current: list[dict], fixed: list[dict]) -> dict:
    """Objectief overzicht van behouden, toegevoegde en verdwenen reguliere diensten."""
    def keys(rows):
        return {assignment_key(row) for row in rows if row.get("Soort") != "Zelfstandige taak"
                and not str(row.get("Dienstnummer", "")).startswith("TAAK:")}
    before, after = keys(previous), keys(current)
    pinned = {assignment_key(row) for row in fixed}
    return {"vastgezet": len(pinned), "behouden": len(before & after),
            "nieuw": len(after - before), "weggevallen": len(before - after),
            "alle_vaste_behouden": pinned.issubset(after)}
