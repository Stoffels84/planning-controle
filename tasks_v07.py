"""v0.7: kleine gekwalificeerde taakplanning binnen een bestaande dienst.

Een taak telt hier mee binnen de oorspronkelijke dienstbezetting. Opdrachten die
bezetting verminderen, diensten vervangen of zelfstandige diensten vormen,
worden nog niet automatisch ingepland. Alle gegevens uitsluitend fictief.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
import re

TIME = re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d\Z')


def task_catalog(data: dict) -> list[dict]:
    return data.get('tasks', [])


def task_requirements(data: dict) -> list[dict]:
    return data.get('task_needs', [])


def task_bounds(day: str, start: str, end: str, shift_start: str) -> tuple[datetime, datetime]:
    d = date.fromisoformat(day)
    sh = datetime.fromisoformat(f'{day}T{shift_start}')
    a = datetime.fromisoformat(f'{day}T{start}')
    b = datetime.fromisoformat(f'{day}T{end}')
    if a < sh:
        a += timedelta(days=1)
    if b <= a:
        b += timedelta(days=1)
    return a, b


def validate_tasks(data: dict) -> list[str]:
    errors = []
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
        task_id = t.get('id', '')
        if not isinstance(task_id, str) or not 1 <= len(task_id.strip()) <= 40:
            errors.append('Een taakcode moet 1–40 tekens bevatten.')
        if not isinstance(t.get('name'), str) or not 1 <= len(t['name'].strip()) <= 120:
            errors.append(f'Taak {task_id}: ongeldige omschrijving.')
        if not isinstance(t.get('qualification', ''), str) or len(t.get('qualification', '')) > 64:
            errors.append(f'Taak {task_id}: ongeldige kwalificatie.')
        if type(t.get('active', True)) is not bool:
            errors.append(f'Taak {task_id}: actief moet aan of uit zijn.')
        lookup[task_id] = t
    shift_map = {s['id']:s for s in data.get('shifts', [])}
    demand = {(r['date'],r['shift_id']) for r in data.get('demand', [])}
    seen = set()
    for n in needs:
        if not isinstance(n, dict):
            errors.append('Ongeldige taakbehoefte.')
            continue
        tid, sid, day = n.get('task_id'), n.get('shift_id'), n.get('date')
        if tid not in lookup or not lookup[tid].get('active', True):
            errors.append(f'Onbekende of inactieve taak: {tid}.')
        if (day,sid) not in demand or sid not in shift_map:
            errors.append(f'Taak {tid}: gekoppelde dienst {sid} is niet ingepland op {day}.')
            continue
        key = (day, sid, tid)
        if key in seen:
            errors.append(f'Dubbele taakbehoefte: {tid} op {day} bij {sid}.')
        seen.add(key)
        required = n.get('required')
        if type(required) is not int or not 1 <= required <= 30:
            errors.append(f'Taak {tid}: aantal medewerkers moet 1–30 zijn.')
        if not TIME.fullmatch(str(n.get('start', ''))) or not TIME.fullmatch(str(n.get('end', ''))):
            errors.append(f'Taak {tid}: ongeldige uren.')
            continue
        try:
            d = date.fromisoformat(day)
            if (d.year, d.month) != (int(data['year']), int(data['month'])):
                errors.append(f'Taak {tid}: valt buiten planningsmaand.')
            shift = shift_map[sid]
            from datetime import datetime as dt
            # Identiek aan dienstgrenzen in planner, zonder circulaire import.
            shift_a = dt.fromisoformat(f'{day}T{shift["start"]}')
            shift_b = dt.fromisoformat(f'{day}T{shift["end"]}')
            if shift_b <= shift_a:
                shift_b += timedelta(days=1)
            a,b = task_bounds(day, n['start'], n['end'], shift['start'])
            if not (shift_a <= a < b <= shift_b):
                errors.append(f'Taak {tid}: tijdsblok ligt niet volledig binnen dienst {sid}.')
        except (ValueError, TypeError, KeyError):
            errors.append(f'Taak {tid}: ongeldige datum of diensturen.')
    taskids = set(ids)
    for e in data.get('employees', []):
        quals = e.get('qualifications', [])
        if (not isinstance(quals, list) or len(quals) > 100 or
                any(not isinstance(q, str) or not 1 <= len(q) <= 64 for q in quals) or
                len(quals) != len(set(quals))):
            errors.append(f"Controleur {e.get('id', '?')}: ongeldige qualifications.")
        blocked = e.get('blocked_tasks', [])
        if (not isinstance(blocked, list) or len(blocked) != len(set(blocked)) or
                any(not isinstance(q, str) or q not in taskids for q in blocked)):
            errors.append(f"Controleur {e.get('id', '?')}: ongeldige blocked_tasks.")
    return errors
