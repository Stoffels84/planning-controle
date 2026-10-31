"""v0.19: read-only, descriptive fairness report for published test rosters.

No compliance judgement or employee ranking. Duty statistics use shift START dates.
Only the last published revision of each selected month may be used.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from demo_data import CATEGORIES
from policy_v06 import saturday_for


def _valid_assignments(plan: dict, known_ids: set[str]) -> tuple[list[dict], int]:
    payload = plan.get("payload", {})
    raw = payload.get("assignments", []) if isinstance(payload, dict) else []
    if not isinstance(raw, list):
        return [], 0
    valid, ignored = [], 0
    for row in raw:
        try:
            if not isinstance(row, dict) or str(row['Personeelsnr']) not in known_ids:
                ignored += 1
                continue
            day = date.fromisoformat(row['Datum'])
            code = str(row['Dienstnummer'])
            category = str(row['Categorie'])
            hours = float(row['Uren'])
            if category not in CATEGORIES or not code or not (0 <= hours <= 24):
                ignored += 1
                continue
            valid.append({**row, 'Datum': day.isoformat(), 'Uren': hours})
        except (ValueError, KeyError, TypeError, OverflowError):
            ignored += 1
    return valid, ignored


def _date_wishes(preferences: list[dict], employee_id: str, assigned: list[dict]) -> tuple[int, int]:
    """Check only exact-dated free_day/daily_shift wishes against published duties."""
    by_date = defaultdict(set)
    for r in assigned:
        by_date[r['Datum']].add(str(r['Dienstnummer']))
    total, met = 0, 0
    for p in preferences:
        if not isinstance(p, dict) or p.get('employee_id') != employee_id:
            continue
        typ = p.get('type', 'free_day')
        if typ == 'free_day' and isinstance(p.get('date'), str):
            total += 1
            met += int(not by_date.get(p['date']))
        elif typ == 'daily_shift' and isinstance(p.get('date'), str):
            total += 1
            met += int(str(p.get('shift_id', '')) in by_date.get(p['date'], set()))
    return total, met


def build_report(data: dict, selected: dict, published_window: list[dict]) -> dict:
    """Compute descriptive indicators without writing data or modifying source dicts.

    selected is last published version of active month; published_window contains
    at most one last published version per calendar month, including selected.
    """
    if selected.get('year') != data.get('year') or selected.get('month') != data.get('month'):
        raise ValueError('Het gepubliceerde rooster behoort niet tot de actieve maand.')
    employees = [e for e in data.get('employees', []) if isinstance(e, dict) and e.get('id')]
    identities = {str(e['id']): e for e in employees}
    if len(identities) != len(employees):
        raise ValueError('Dubbele personeelsnummers in de brongegevens.')
    assignments, ignored = _valid_assignments(selected, set(identities))
    warnings = []
    if ignored:
        warnings.append(f'{ignored} ongeldige of onbekende toewijzing(en) niet meegerekend.')
    stale = selected.get('revision') != data.get('workspace_revision') if data.get('workspace_revision') is not None else False
    # Callers that know the workspace revision should pass it explicitly in the data copy.
    if stale:
        warnings.append('Invoer gewijzigd sinds de publicatie: huidige profielen en voorkeuren kunnen afwijken van het gepubliceerde rooster.')

    by_person = defaultdict(list)
    for r in assignments:
        by_person[str(r['Personeelsnr'])].append(r)
    person_rows = []
    for eid, emp in sorted(identities.items(), key=lambda item: str(item[1].get('name', item[0])).casefold()):
        duty_rows = by_person[eid]
        dates = {r['Datum'] for r in duty_rows if date.fromisoformat(r['Datum']).weekday() >= 5}
        weekends = {saturday_for(date.fromisoformat(d)).isoformat() for d in dates}
        contract = float(emp.get('contract_percent') or 0)
        normalized = round(len(dates) * 100 / contract, 2) if 0 < contract <= 100 else None
        total_wishes, respected = _date_wishes(data.get('preferences', []), eid, duty_rows) if not stale else (0, 0)
        row = {
            'Personeelsnr': eid, 'Controleur': str(emp.get('name', eid)),
            'Actief in catalogus': bool(emp.get('active', True)),
            'Contract (%)': contract if contract else None,
            'Diensten en zelfstandige taken': len(duty_rows),
            'Planuren': round(sum(float(r['Uren']) for r in duty_rows), 2),
            'Weekenddagen': len(dates), 'Gewerkte weekends': len(weekends),
            'Weekenddagen per 100% contract (indicatief)': normalized,
        }
        row.update({c: sum(r['Categorie'] == c for r in duty_rows) for c in CATEGORIES})
        row['Datumgebonden wensen beoordeeld'] = total_wishes if not stale else None
        row['Datumgebonden wensen gerespecteerd'] = respected if not stale else None
        row['Wensen gerespecteerd (%)'] = (round(100 * respected / total_wishes, 1)
                                           if total_wishes and not stale else None)
        person_rows.append(row)

    selected_payload = selected.get('payload') if isinstance(selected.get('payload'), dict) else {}
    original_summary = selected_payload.get('summary', {})
    original_summary = original_summary if isinstance(original_summary, dict) else {}
    needed = original_summary.get('required')
    filled = original_summary.get('assigned')
    open_count = original_summary.get('open')
    if not isinstance(needed, int) or needed < 0 or not isinstance(filled, int) or filled < 0:
        needed, filled, open_count = None, None, None
        warnings.append('Betrouwbare bezettingscijfers ontbreken in deze gepubliceerde versie.')
    coverage = round(100 * filled / needed, 1) if needed else None
    normalized_vals = [r['Weekenddagen per 100% contract (indicatief)'] for r in person_rows
                       if r['Actief in catalogus'] and r['Weekenddagen per 100% contract (indicatief)'] is not None]
    spread = round(max(normalized_vals) - min(normalized_vals), 2) if len(normalized_vals) >= 2 else None
    categories = [{'Categorie': c,
                   'Toewijzingen': sum(r['Categorie'] == c for r in assignments)} for c in CATEGORIES]
    category_total = sum(c['Toewijzingen'] for c in categories)
    for r in categories:
        r['Aandeel (%)'] = round(100 * r['Toewijzingen'] / category_total, 1) if category_total else None

    history = []
    seen_months = set()
    for plan in sorted(published_window, key=lambda p: (p['year'], p['month'])):
        period = (plan['year'], plan['month'])
        if period in seen_months or period > (selected['year'], selected['month']):
            continue
        seen_months.add(period)
        records, omitted = _valid_assignments(plan, set(identities))
        if omitted:
            warnings.append(f'{period[1]:02d}/{period[0]}: {omitted} historische toewijzing(en) overgeslagen.')
        groups = defaultdict(list)
        for row in records:
            groups[str(row['Personeelsnr'])].append(row)
        for eid, emp in identities.items():
            rows = groups[eid]
            days = {r['Datum'] for r in rows if date.fromisoformat(r['Datum']).weekday() >= 5}
            contract = float(emp.get('contract_percent') or 0)
            history.append({'Maand': f'{period[1]:02d}/{period[0]}', 'Personeelsnr': eid,
                            'Controleur': str(emp.get('name', eid)),
                            'Diensten en taken': len(rows), 'Planuren': round(sum(r['Uren'] for r in rows), 2),
                            'Weekenddagen': len(days),
                            'Weekenddagen per 100% (indicatief)': round(len(days) * 100 / contract, 2)
                            if 0 < contract <= 100 else None})
    summary = {'Maand': f"{selected['month']:02d}/{selected['year']}",
               'Gepubliceerde versie': selected.get('id'),
               'Dienstplaatsen nodig': needed, 'Dienstplaatsen ingevuld': filled,
               'Dienstplaatsen open': open_count, 'Bezetting (%)': coverage,
               'Toewijzingen incl. taken': len(assignments),
               'Weekenddagen totaal': sum(r['Weekenddagen'] for r in person_rows),
               'Spreiding weekenddagen per 100% (indicatief)': spread,
               'Controleurs met norm': len(normalized_vals)}
    warnings.append('Indicatieve spreiding houdt geen rekening met individuele beschikbaarheid, kwalificaties, beschermde weekends of roosterhistoriek buiten het venster.')
    return {'summary': summary, 'persons': person_rows, 'categories': categories,
            'history': history, 'warnings': warnings}


def safe_excel_rows(rows: list[dict]) -> list[dict]:
    """Prevent CSV/Excel formula injection via employee names and identifiers."""
    return [
        {key: ("'" + value if isinstance(value, str) and
               value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value)
         for key, value in row.items()}
        for row in rows
    ]
