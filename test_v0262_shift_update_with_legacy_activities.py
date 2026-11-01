"""v0.26.2: ongeldige historische activiteiten mogen een zuivere dienstwijziging niet blokkeren."""
from copy import deepcopy
from datetime import date

import pytest

from catalog import shift_details
from months_v012 import period_key
from activities_v0261 import invalid_activities
from extras import validate_extras
from shift_edit_v0262 import apply_month_shift
from store import (
    Account, ConflictError, MonthWorkspace, get_engine, initialize,
    initialize_months, list_month_workspaces, create_month_workspace,
    load_month_workspace, save_month_shift, session_factory, save_month_workspace,
    add_account, request_leave, decide_leave_request, load_plan,
)


def fixture_db(tmp_path):
    db = get_engine(f"sqlite+pysqlite:///{tmp_path / 'shiftfix.sqlite'}")
    initialize(db, 'ROOT', 'UitsluitendFictiefEnVeilig2026!')
    initialize_months(db)
    item = list_month_workspaces(db)[0]
    year, month = item['year'], item['month']
    next_key = year * 12 + month
    other = (next_key // 12, next_key % 12 + 1)
    create_month_workspace(db, *other, 'ROOT')
    return db, (year, month), other


def entry(state, code='V101', start='07:15', end='15:15', required=None):
    current = shift_details(next(s for s in state['shifts'] if s['id'] == code))
    return dict(current, start=start, end=end,
                required=current['required'] if required is None else required)


def inject_legacy(db, period, activities):
    with session_factory(db).begin() as s:
        record = s.get(MonthWorkspace, period_key(*period))
        payload = deepcopy(record.payload)
        payload['hour_credits'] = deepcopy(activities)
        record.payload = payload


def test_unpublished_month_hour_change_keeps_all_invalid_and_valid_credits(tmp_path):
    db, original, future = fixture_db(tmp_path)
    other_month = date(*original, 1).replace(year=original[0]+1).isoformat()
    invalid = [{'employee_id': 'DEMO001', 'date': other_month, 'type': 'Andere', 'hours': 4},
               {'employee_id': 'VERDWENEN', 'date': date(*original, 3).isoformat(), 'type': 'Andere', 'hours': 4}]
    valid = {'employee_id': 'DEMO002', 'date': date(*original, 4).isoformat(), 'type': 'Andere', 'hours': 7}
    inject_legacy(db, original, invalid + [valid])
    before, revision = load_month_workspace(db, *original)
    assert len(invalid_activities(before)) == 2
    assert validate_extras(before)
    new_rev = save_month_shift(db, *original, revision, 'ROOT', entry(before), 'V101')
    after, _ = load_month_workspace(db, *original)
    assert new_rev == revision + 1
    assert after['shifts'][0]['start'] == '07:15'
    assert after['hour_credits'] == before['hour_credits']  # geen automatische verwijdering
    assert after['preferences'] == before['preferences']
    assert validate_extras(after)  # solver blijft ongeldig totdat herstel plaatsvindt
    other, _ = load_month_workspace(db, *future)
    assert other['shifts'][0]['start'] == '06:00'


def test_changed_required_updates_only_same_month_demand(tmp_path):
    db, original, other = fixture_db(tmp_path)
    source, rev = load_month_workspace(db, *original)
    wanted = entry(source, required=3)
    save_month_shift(db, *original, rev, 'ROOT', wanted, 'V101')
    source2, _ = load_month_workspace(db, *original)
    assert all(row['required'] == 3 for row in source2['demand'] if row['shift_id'] == 'V101')
    other2, _ = load_month_workspace(db, *other)
    assert other2['shifts'][0]['required'] == 2


def test_authorization_revision_and_shift_id_enforced(tmp_path):
    db, original, _ = fixture_db(tmp_path)
    state, rev = load_month_workspace(db, *original)
    add_account(db, 'DEMO001', 'Fictieve controleur', 'controleur',
                'FictieveDemo001Wachtwoord2026!', 'ROOT')
    with pytest.raises(ValueError, match='mogen alleen hun eigen voorkeuren'):
        save_month_shift(db, *original, rev, 'DEMO001', entry(state), 'V101')
    with pytest.raises(ValueError, match='dienstnummer mag niet'):
        save_month_shift(db, *original, rev, 'ROOT', dict(entry(state), id='OTHER'), 'V101')
    changed_rev = save_month_shift(db, *original, rev, 'ROOT', entry(state), 'V101')
    with pytest.raises(ConflictError):
        save_month_shift(db, *original, rev, 'ROOT', entry(state, start='09:00'), 'V101')
    assert changed_rev == rev + 1


def test_bad_shift_refused_even_with_corrupted_old_credits(tmp_path):
    db, original, _ = fixture_db(tmp_path)
    inject_legacy(db, original, [{'employee_id': 'OUDE', 'date': '2020-01-01', 'type': 'Andere', 'hours': 2}])
    state, rev = load_month_workspace(db, *original)
    for proposed in (entry(state, start='24:99'), entry(state, start='04:00', end='23:00')):
        with pytest.raises(ValueError):
            save_month_shift(db, *original, rev, 'ROOT', proposed, 'V101')
    with pytest.raises(ValueError, match='maandbehoefte'):
        save_month_shift(db, *original, rev, 'ROOT', dict(entry(state), active=False), 'V101')
    still, revision = load_month_workspace(db, *original)
    assert revision == rev and still['hour_credits'] == state['hour_credits']


def test_approved_leave_is_preserved_with_invalid_other_credit(tmp_path):
    db, original, _ = fixture_db(tmp_path)
    add_account(db, 'DEMO002', 'Fictieve controleur', 'controleur',
                'FictieveDemo002Wachtwoord2026!', 'ROOT')
    approved_day = date(*original, 5)
    req = request_leave(db, 'DEMO002', approved_day, approved_day)
    decide_leave_request(db, req, 'ROOT', True, 7.6)
    current, rev = load_month_workspace(db, *original)
    assert any(a['employee_id']=='DEMO002' for a in current['hour_credits'])
    other_credit = {'employee_id': 'DEMO001', 'date': '2011-01-01', 'type': 'Andere', 'hours': 2}
    inject_legacy(db, original, current['hour_credits']+[other_credit])
    before, rev = load_month_workspace(db, *original)
    save_month_shift(db, *original, rev, 'ROOT', entry(before), 'V101')
    after, _ = load_month_workspace(db, *original)
    assert after['hour_credits'] == before['hour_credits']
    assert len(invalid_activities(after)) == 1


def test_pure_update_does_not_modify_source_dictionary():
    from demo_data import build_demo
    data = build_demo(2026, 11)
    data['hour_credits'] = [{'employee_id': 'X', 'date': '2000-01-01', 'type': 'Andere', 'hours': 6}]
    old = deepcopy(data)
    updated = apply_month_shift(data, entry(data), 'V101')
    assert data == old
    assert updated['hour_credits'] == old['hour_credits']
    assert updated['shifts'][0]['start'] == '07:15'
