"""v0.26.2 — veilige, beperkte aanpassing van de dienstencatalogus per maand.

De volledige maandvalidator kan historische, reeds opgeslagen activiteiten
afkeuren. Een zuivere dienstwijziging mag die activiteiten niet onbedoeld
verwijderen of veranderen; verdere planning vereist nog steeds herstel.
"""
from __future__ import annotations

from copy import deepcopy

from catalog import sync_required, validate_shift


def apply_month_shift(data: dict, entry: dict, original_id: str | None = None) -> dict:
    """Bewerk uitsluitend één dienst en synchroniseer haar vaste maandbezetting.

    Alle andere velden, expliciet ook hour_credits en verlofblokkeringen,
    blijven byte-voor-byte qua inhoud behouden in een deep copy.
    """
    if not isinstance(entry, dict):
        raise ValueError("Ongeldige dienstdefinitie.")
    allowed = {"id", "name", "category", "start", "end", "required",
               "location", "start_location", "end_location", "active"}
    if set(entry) - allowed:
        raise ValueError("De dienstwijziging bevat onbekende velden.")
    problems = validate_shift(entry)
    if problems:
        raise ValueError(" ".join(problems))
    code = entry["id"]
    if original_id is not None and (not isinstance(original_id, str) or original_id != code):
        raise ValueError("Een bestaand dienstnummer mag niet worden veranderd.")
    if not isinstance(data.get("shifts"), list) or not isinstance(data.get("demand"), list):
        raise ValueError("De maandgegevens bevatten geen geldige dienstencatalogus.")
    existing = [s for s in data["shifts"] if isinstance(s, dict) and s.get("id") == code]
    if original_id is None and existing:
        raise ValueError("Dit dienstnummer bestaat al.")
    if original_id is not None and len(existing) != 1:
        raise ValueError("Het geselecteerde dienstnummer bestaat niet of is dubbel.")
    if not entry.get("active", True) and any(r.get("shift_id") == code for r in data["demand"]):
        raise ValueError("Deze dienst staat nog in de maandbehoefte. Verwijder hem daar eerst voordat je hem deactiveert.")

    updated = deepcopy(data)
    if original_id is None:
        updated["shifts"].append(deepcopy(entry))
    else:
        updated["shifts"] = [dict(s, **entry) if s["id"] == code else s for s in updated["shifts"]]
        sync_required(updated, code, int(entry["required"]))
    return updated
