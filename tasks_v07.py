"""Taakcatalogus en behoeftevalidatie voor de fictieve controleursplanning.

Drie werkwijzen:
  embedded: binnen de dienst en blijft meetellen voor de reguliere bezetting;
  released: binnen de dienst, maar tijdelijk NIET beschikbaar voor die bezetting;
  standalone: een afzonderlijke daginzet, zonder dienstnummer.

Bestaande v0.7-taakblokken zonder 'mode' blijven 'embedded'.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
import re

TIME = re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d\Z')
MODES = {
    'embedded': 'Binnen dienst — telt mee in bezetting',
    'released': 'Binnen dienst — tijdelijke vrijstelling',
    'standalone': 'Zelfstandige opdracht — vervangt gewone dienst',
}
CATEGORIES = ('Vroeg', 'Dag', 'Laat', 'Nacht')


def need_mode(need: dict) -> str:
    return need.get('mode', 'embedded')


def standalone_code(index: int) -> str:
    return f'__ZELFSTANDIGE_TAAK_{index}'


def task_catalog(data: dict) -> list[dict]:
    return data.get('tasks', [])


def task_requirements(data: dict) -> list[dict]:
    return data.get('task_needs', [])


def task_bounds(day: str, start: str, end: str, shift_start: str) -> tuple[datetime, datetime]:
    """Relativeer een tijdvak aan de start van zijn ouderdienst (nacht mogelijk)."""
    sh = datetime.fromisoformat(f'{day}T{shift_start}')
    a = datetime.fromisoformat(f'{day}T{start}')
    b = datetime.fromisoformat(f'{day}T{end}')
    if a < sh:
        a += timedelta(days=1)
    if b <= a:
        b += timedelta(days=1)
    return a, b


def standalone_bounds(day: str, start: str, end: str) -> tuple[datetime, datetime]:
    a = datetime.fromisoformat(f'{day}T{start}')
    b = datetime.fromisoformat(f'{day}T{end}')
    if b <= a:
        b += timedelta(days=1)
    return a, b


def validate_tasks(data: dict) -> list[str]:
    errors: list[str] = []
    definitions = task_catalog(data)
    needs = task_requirements(data)
    if not isinstance(definitions, list) or len(definitions) > 250:
        return ['Ongeldige takencatalogus (maximaal 250 taken).']
    if not isinstance(needs, list) or len(needs) > 2000:
        return ['Ongeldige taakbehoefte (maximaal 2000 regels).']
    ids = [t.get('id') for t in definitions if isinstance(t, dict)]
    if len(ids) != len(set(ids)):
        errors.append('Taakcodes moeten uniek zijn.')
    lookup = {}
    for t in definitions:
        if not isinstance(t, dict):
            errors.append('Ongeldige taakdefinitie.')
            continue
        tid = t.get('id', '')
        if not isinstance(tid, str) or not 1 <= len(tid.strip()) <= 40:
            errors.append('Een taakcode moet 1–40 tekens bevatten.')
        if not isinstance(t.get('name'), str) or not 1 <= len(t['name'].strip()) <= 120:
            errors.append(f'Taak {tid}: ongeldige omschrijving.')
        if not isinstance(t.get('qualification', ''), str) or len(t.get('qualification', '')) > 64:
            errors.append(f'Taak {tid}: ongeldige kwalificatie.')
        if type(t.get('active', True)) is not bool:
            errors.append(f'Taak {tid}: actief moet aan of uit zijn.')
        if t.get('category', 'Dag') not in CATEGORIES:
            errors.append(f'Taak {tid}: ongeldige dienstcategorie.')
        lookup[tid] = t
    shift_map = {s['id']: s for s in data.get('shifts', [])}
    demand = {(r['date'], r['shift_id']) for r in data.get('demand', []) if r['required'] > 0}
    seen = set()
    for n in needs:
        if not isinstance(n, dict):
            errors.append('Ongeldige taakbehoefte.')
            continue
        tid, sid, day = n.get('task_id'), n.get('shift_id'), n.get('date')
        mode = need_mode(n)
        if mode not in MODES:
            errors.append(f'Taak {tid}: onbekende planningsvorm.')
            continue
        if tid not in lookup or not lookup[tid].get('active', True):
            errors.append(f'Onbekende of inactieve taak: {tid}.')
        if mode != 'standalone' and ((day, sid) not in demand or sid not in shift_map):
            errors.append(f'Taak {tid}: gekoppelde dienst {sid} is niet ingepland op {day}.')
            continue
        if mode == 'standalone' and sid not in (None, ''):
            errors.append(f'Taak {tid}: zelfstandige opdracht mag geen dienstnummer hebben.')
        key = (day, sid, tid, mode, n.get('start'), n.get('end'))
        if key in seen:
            errors.append(f'Dubbele taakbehoefte: {tid} op {day}.')
        seen.add(key)
        required = n.get('required')
        if type(required) is not int or not 1 <= required <= 30:
            errors.append(f'Taak {tid}: aantal medewerkers moet 1–30 zijn.')
        if not TIME.fullmatch(str(n.get('start', ''))) or not TIME.fullmatch(str(n.get('end', ''))):
            errors.append(f'Taak {tid}: ongeldige uren.')
            continue
        try:
            day_obj = date.fromisoformat(day)
            if (day_obj.year, day_obj.month) != (int(data['year']), int(data['month'])):
                errors.append(f'Taak {tid}: valt buiten planningsmaand.')
            if mode == 'standalone':
                a, b = standalone_bounds(day, n['start'], n['end'])
            else:
                shift = shift_map[sid]
                sa = datetime.fromisoformat(f'{day}T{shift["start"]}')
                sb = datetime.fromisoformat(f'{day}T{shift["end"]}')
                if sb <= sa:
                    sb += timedelta(days=1)
                a, b = task_bounds(day, n['start'], n['end'], shift['start'])
                if not (sa <= a < b <= sb):
                    errors.append(f'Taak {tid}: tijdsblok ligt niet volledig binnen dienst {sid}.')
            if not 0 < (b-a).total_seconds() <= 16 * 3600:
                errors.append(f'Taak {tid}: duur moet tussen 0 en 16 uur liggen.')
        except (ValueError, TypeError, KeyError):
            errors.append(f'Taak {tid}: ongeldige datum of diensturen.')
    known = set(ids)
    for e in data.get('employees', []):
        quals = e.get('qualifications', [])
        if (not isinstance(quals, list) or len(quals) > 100 or
                any(not isinstance(q, str) or not 1 <= len(q) <= 64 for q in quals) or
                len(quals) != len(set(quals))):
            errors.append(f"Controleur {e.get('id', '?')}: ongeldige qualifications.")
        blocked = e.get('blocked_tasks', [])
        if (not isinstance(blocked, list) or len(blocked) != len(set(blocked)) or
                any(not isinstance(q, str) or q not in known for q in blocked)):
            errors.append(f"Controleur {e.get('id', '?')}: ongeldige blocked_tasks.")
    return errors
