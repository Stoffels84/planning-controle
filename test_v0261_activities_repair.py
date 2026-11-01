"""v0.26.1: transparant herstel van verouderde activiteiten, zonder dataverlies."""
from copy import deepcopy
from datetime import date

import pytest

from activities_v0261 import invalid_activities, remove_invalid_activities
from demo_data import build_demo
from extras import validate_extras
from store import (get_engine, initialize, initialize_months, list_month_workspaces,
                   load_month_workspace, save_month_workspace, session_factory,
                   MonthWorkspace, SharedCatalog, add_account, request_leave, decide_leave_request)
from months_v012 import period_key


def demo():
    data = build_demo(2026, 11)
    data['hour_credits'] = [
        {'employee_id': 'DEMO001', 'date': '2026-11-03', 'type': 'Andere', 'hours': 4},
        {'employee_id': 'DEMO001', 'date': '2026-12-03', 'type': 'Andere', 'hours': 4},
        {'employee_id': 'OUDE_ID', 'date': '2026-11-04', 'type': 'Andere', 'hours': 3},
    ]
    return data


def setup(tmp_path):
    db = get_engine(f"sqlite+pysqlite:///{tmp_path / 'repair.sqlite'}")
    initialize(db, 'ROOT', 'FictieveVeiligeWachtwoord2026!')
    initialize_months(db)
    p = list_month_workspaces(db)[0]
    return db, p['year'], p['month']


def insert_legacy_invalid(db, y, m, credit):
    with session_factory(db).begin() as s:
        row = s.get(MonthWorkspace, period_key(y, m))
        updated = deepcopy(row.payload)
        updated.setdefault('hour_credits', []).append(credit)
        row.payload = updated


def test_detects_precise_invalid_rows_only():
    entries = invalid_activities(demo())
    assert [row['index'] for row in entries] == [1, 2]
    assert 'Datum buiten' in entries[0]['reason']
    assert 'Onbekende controleur' in entries[1]['reason']
    assert entries[0]['date'] == '2026-12-03'


def test_removes_only_selected_invalid_and_does_not_mutate_original():
    original = demo()
    partial = remove_invalid_activities(original, [1])
    assert len(partial['hour_credits']) == 2
    assert partial['hour_credits'][0] == original['hour_credits'][0]
    assert len(original['hour_credits']) == 3
    corrected = remove_invalid_activities(original, [1, 2])
    assert validate_extras(corrected) == []
    assert len(corrected['hour_credits']) == 1


def test_invalid_selection_rejected():
    original = demo()
    for indexes in ([], [0], [1, 1], [99], ['1']):
        with pytest.raises(ValueError):
            remove_invalid_activities(original, indexes)


def test_malformed_credit_displayed_without_crash():
    original = demo()
    original['hour_credits'].append({'employee_id': 'DEMO001', 'date': 'wat dan ook'})
    rows = invalid_activities(original)
    assert rows[-1]['index'] == 3
    assert 'Ongeldige' in rows[-1]['reason']


def test_legacy_bad_activities_can_be_repaired_with_store_protection(tmp_path):
    db, y, m = setup(tmp_path)
    good_date = date(y, m, 4).isoformat()
    invalid = {'employee_id': 'DEMO001', 'date': date(y, m, 4).replace(year=y+1).isoformat(),
               'type': 'Andere', 'hours': 4}
    good = {'employee_id': 'DEMO002', 'date': good_date, 'type': 'Andere', 'hours': 4}
    insert_legacy_invalid(db, y, m, invalid)
    insert_legacy_invalid(db, y, m, good)
    state, rev = load_month_workspace(db, y, m)
    problem = invalid_activities(state)
    assert len(problem) == 1
    repaired = remove_invalid_activities(state, [problem[0]['index']])
    repaired['shifts'][0]['start'] = '07:15'
    repaired['shifts'][0]['end'] = '15:15'
    assert validate_extras(repaired) == []
    save_month_workspace(db, repaired, rev, 'ROOT', 'Foutieve testactiviteit gecontroleerd')
    after, _ = load_month_workspace(db, y, m)
    assert after['hour_credits'] == [good]
    assert after['shifts'][0]['start'] == '07:15'


def test_approved_leave_cannot_be_removed_by_repair_even_if_person_is_unknown(tmp_path):
    db, y, m = setup(tmp_path)
    add_account(db, 'DEMO001', 'Fictieve controleur', 'controleur',
                'FictieveDemo001Wachtwoord2026!', 'ROOT')
    req = request_leave(db, 'DEMO001', date(y, m, 5), date(y, m, 5))
    decide_leave_request(db, req, 'ROOT', True, 7.6)
    # Simuleer legacy fout: globale medewerkerlijst verloor DEMO001, maar
    # goedgekeurd verlof staat nog in de maand. Verwijderen moet falen.
    with session_factory(db).begin() as s:
        shared = s.get(SharedCatalog, 1)
        payload = deepcopy(shared.payload)
        payload['employees'] = [e for e in payload['employees'] if e['id'] != 'DEMO001']
        shared.payload = payload
    current, revision = load_month_workspace(db, y, m)
    orphan = invalid_activities(current)
    assert len(orphan) == 1
    cleaned = remove_invalid_activities(current, [orphan[0]['index']])
    with pytest.raises(ValueError, match='goedgekeurde verlofdag'):
        save_month_workspace(db, cleaned, revision, 'ROOT', 'Onjuiste verwijdering')
    remaining, _ = load_month_workspace(db, y, m)
    assert remaining['hour_credits'] == current['hour_credits']
