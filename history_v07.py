"""Historiek afgeleid uit daadwerkelijk gepubliceerde plannen (niet uit concepten).

Een weekenddag wordt geteld volgens de STARTdatum van de dienst, analoog v0.6.
De functie past de in de database bewaarde gegevens nooit aan.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from policy_v06 import saturday_for


def aggregate_history(plans: list[dict], employee_ids: list[str]) -> dict[str, dict]:
    """`plans`: één geselecteerde gepubliceerde versie per oudere kalendermaand."""
    dates = defaultdict(set)
    weekends = defaultdict(set)
    categories = defaultdict(lambda: defaultdict(int))
    for plan in plans:
        for row in plan.get('payload', {}).get('assignments', []):
            try:
                eid = str(row['Personeelsnr'])
                d = date.fromisoformat(row['Datum'])
                cat = str(row['Categorie'])
            except (ValueError, TypeError, KeyError):
                continue
            if eid not in employee_ids:
                continue
            categories[eid][cat] += 1
            if d.weekday() >= 5:
                dates[eid].add(d.isoformat())
                weekends[eid].add(saturday_for(d).isoformat())
    return {eid: {'weekend_days': len(dates[eid]),
                  'worked_weekends': len(weekends[eid]),
                  'categories': dict(categories[eid])} for eid in employee_ids}


def apply_published_history(data: dict, history: dict[str, dict]) -> dict:
    """Maakt uitsluitend een berekeningskopie; overschrijft oude handmatige baselines niet."""
    import copy
    work = copy.deepcopy(data)
    for e in work['employees']:
        e['historic_weekend_days'] = history.get(e['id'], {}).get('weekend_days', 0)
    return work
