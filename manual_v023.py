"""v0.23 — sessiegebonden wachtrij voor handmatige roosterbewerkingen.

Geen publicatie, database-mutatie of vrijstelling van harde arbeidsregels:
alle wijzigingen worden vertaald naar vaste of verboden reguliere diensten
voor dezelfde OR-Tools-planner als v0.22.
"""
from __future__ import annotations

from locks_v022 import assignment_key, validate_locks

MAX_EDITS = 150
KINDS = {"add", "replace", "remove", "keep"}


def regular_assignments(rows: list[dict]) -> list[dict]:
    """Laat zelfstandige taken buiten handmatige reguliere dienstbewerkingen."""
    return [dict(zip(("Datum", "Dienstnummer", "Personeelsnr"), assignment_key(row)))
            for row in rows
            if row.get("Soort") != "Zelfstandige taak"
            and not str(row.get("Dienstnummer", "")).startswith("TAAK:")]


def _validated_single(data: dict, row: dict) -> dict:
    return validate_locks(data, [row])[0]


def compile_edits(data: dict, original: list[dict], edits: list[dict],
                  preserve_others: bool = True) -> dict:
    """Vertaal de hele wachtrij atomair naar locks/exclusions.

    `remove`: verbiedt de oude persoon/dienst, niet de volledige dienstplaats.
    `replace`: verbiedt oude combinatie en verplicht nieuwe combinatie.
    `add`/`keep`: verplichte combinaties.
    """
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
        raise ValueError(f"Zet eerst 1 tot {MAX_EDITS} wijzigingen klaar.")
    if not isinstance(preserve_others, bool):
        raise ValueError("Ongeldige keuze voor het behouden van andere diensten.")
    baseline = regular_assignments(original)
    original_keys = {assignment_key(r) for r in baseline}
    if len(original_keys) != len(baseline):
        raise ValueError("Het bronrooster bevat dubbele reguliere toewijzingen.")
    source_keys = set()
    target_keys = set()
    mandatory: list[dict] = []
    forbidden: list[dict] = []
    for edit in edits:
        if not isinstance(edit, dict) or edit.get("kind") not in KINDS:
            raise ValueError("Onbekende handmatige roosterbewerking.")
        kind = edit["kind"]
        source = edit.get("source")
        target = edit.get("target")
        if kind in ("remove", "replace", "keep"):
            source = _validated_single(data, source)
            key = assignment_key(source)
            if key not in original_keys:
                raise ValueError("De gekozen oorspronkelijke toewijzing bestaat niet meer in dit rooster.")
            if key in source_keys:
                raise ValueError("Een bestaande toewijzing kan slechts één keer worden bewerkt.")
            source_keys.add(key)
            if kind == "keep":
                mandatory.append(source)
                target_keys.add(key)
            else:
                forbidden.append(source)
        elif source is not None:
            raise ValueError("Een nieuwe dienst mag geen bron-toewijzing bevatten.")
        if kind in ("add", "replace"):
            target = _validated_single(data, target)
            target_key = assignment_key(target)
            if kind == "replace" and assignment_key(source)[:2] != target_key[:2]:
                raise ValueError("Bij vervangen blijft datum en dienstnummer hetzelfde.")
            if target_key in original_keys and kind == "add":
                raise ValueError("Deze dienst staat al in het bronrooster. Kies 'Behouden'.")
            if target_key in target_keys:
                raise ValueError("Dezelfde nieuwe toewijzing staat meermaals in de bewerkingslijst.")
            target_keys.add(target_key)
            mandatory.append(target)
        elif target is not None:
            raise ValueError("Deze bewerking mag geen nieuwe toewijzing bevatten.")
    excluded_keys = {assignment_key(r) for r in forbidden}
    if preserve_others:
        # Niet gewijzigde bron-toewijzingen worden expliciet vastgezet.
        for source in baseline:
            if assignment_key(source) not in source_keys:
                mandatory.append(source)
    locked = validate_locks(data, mandatory)
    locked_keys = {assignment_key(row) for row in locked}
    if excluded_keys & locked_keys:
        raise ValueError("Een dienst kan niet tegelijk verboden en vastgezet zijn. Controleer je wijzigingen.")
    excluded = sorted(forbidden, key=assignment_key)
    return {
        "locked": locked, "excluded": excluded,
        "edit_count": len(edits),
        "preserve_others": preserve_others,
        "original_preserved": sum(assignment_key(r) in original_keys for r in locked),
    }


def edit_description(edit: dict, people: dict[str, str] | None = None) -> str:
    """Korte samenvatting voor de controlelijst; uitsluitend weergave."""
    people = people or {}
    kind = edit["kind"]
    row = edit.get("source") or edit.get("target")
    day, shift, old = assignment_key(row)
    person = lambda eid: f"{people.get(eid, eid)} ({eid})"
    if kind == "add":
        return f"Toevoegen: {day} · {shift} → {person(old)}"
    if kind == "remove":
        return f"Verwijderen: {day} · {shift} · {person(old)}"
    if kind == "keep":
        return f"Behouden: {day} · {shift} · {person(old)}"
    new = assignment_key(edit["target"])[2]
    return f"Vervangen: {day} · {shift} · {person(old)} → {person(new)}"
