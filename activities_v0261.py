"""v0.26.1 — audit van oude activiteiten die niet bij de actieve maand passen.

Herstel is altijd opt-in; nooit automatisch verwijderen/verplaatsen. Relevante
servercontroles voor goedgekeurd verlof blijven in store.save_month_workspace.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date


def invalid_activities(data: dict) -> list[dict]:
    """Detecteer uitsluitend registraties met onbekende controleur/ongeldige maand.

    Andere activiteiten blijven ongemoeid: de volledige datasetvalidator bepaalt
    of een gecorrigeerde maand uiteindelijk mag worden opgeslagen.
    """
    valid_ids = {e.get('id') for e in data.get('employees', []) if isinstance(e, dict)}
    year, month = int(data['year']), int(data['month'])
    found = []
    for index, item in enumerate(data.get('hour_credits', [])):
        reasons = []
        if not isinstance(item, dict):
            reasons.append('Ongeldige registratie')
            item = {}
        if item.get('employee_id') not in valid_ids:
            reasons.append('Onbekende controleur')
        try:
            d = date.fromisoformat(item['date'])
            if (d.year, d.month) != (year, month):
                reasons.append('Datum buiten actieve planningsmaand')
        except (KeyError, TypeError, ValueError):
            reasons.append('Ongeldige of ontbrekende datum')
        if reasons:
            found.append({
                'index': index,
                'employee_id': str(item.get('employee_id', '')),
                'date': str(item.get('date', '')),
                'type': str(item.get('type', '')),
                'hours': item.get('hours'),
                'reason': '; '.join(reasons),
            })
    return found


def remove_invalid_activities(data: dict, indexes: list[int]) -> dict:
    """Verwijder enkel uitdrukkelijk geselecteerde afwijkende rijen uit een kopie.

    De beller moet een expliciete beheerderbevestiging vragen, de volledige
    dataset valideren en atomair opslaan via de beveiligde store-functie.
    """
    if not indexes or any(type(i) is not int for i in indexes) or len(indexes) != len(set(indexes)):
        raise ValueError('Selecteer minstens één unieke afwijkende activiteit.')
    permissible = {row['index'] for row in invalid_activities(data)}
    if not set(indexes).issubset(permissible):
        raise ValueError('Alleen vastgestelde afwijkende activiteiten mogen zo worden verwijderd.')
    clean = deepcopy(data)
    selected = set(indexes)
    clean['hour_credits'] = [r for i, r in enumerate(clean.get('hour_credits', [])) if i not in selected]
    return clean
