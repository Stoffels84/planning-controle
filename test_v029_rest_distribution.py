"""v0.29: onafhankelijke rollende rustcontrole en veilige profielopslag."""
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

from catalog import profile, validate_employee
from demo_data import build_demo
from rest_v029 import validate_min_days_off, published_sides, windows_for_month, violating_windows
from store import (Account, ConflictError, MonthWorkspace, SharedCatalog,
                   add_account, create_month_workspace, get_engine, initialize,
                   initialize_months, list_month_workspaces, load_month_workspace,
                   save_min_rest_days_v029, session_factory)
from months_v012 import period_key
from validator_v025 import verify_plan


def month():
    data = build_demo(2026, 11)
    data['employees'] = [data['employees'][0]]
    data['employees'][0]['max_consecutive'] = 7
    data['employees'][0]['min_days_off_per_7'] = 2
    data['employees'][0]['blocked_weekdays'] = []
    data['employees'][0]['max_weekend_days'] = None
    data['employees'][0]['max_worked_weekends'] = None
    data['employees'][0]['max_consecutive_worked_weekends'] = None
    for shift in data['shifts']:
        if shift['id'] == 'D201':
            shift['required'] = 1
    data['demand'] = [{'date':f'2026-11-{day:02d}', 'shift_id':'D201', 'required':1}
                      for day in range(1, 8)]
    data['preferences'] = []
    return data


def row(day):
    return {'Datum':day, 'Personeelsnr':'DEMO001', 'Dienstnummer':'D201',
            'Categorie':'Dag', 'Begin':'09:00', 'Einde':'17:00'}


def boundary(day, side):
    return {'employee_id':'DEMO001', 'date':day, 'category':'Dag',
            'start':'09:00', 'end':'17:00', 'source':side}


def audit(data, days, historical=()):
    return verify_plan(data, {'assignments':[row(d) for d in days]}, list(historical))


def test_legacy_profile_has_rule_disabled_and_strict_validation():
    person = profile(month()['employees'][0])
    del person['min_days_off_per_7']
    assert validate_employee(person, {'D201'}) == []
    assert profile(person)['min_days_off_per_7'] is None
    for bad in (True, 0, 4, '2', 1.5, [], {}):
        person['min_days_off_per_7'] = bad
        assert any('vrije dagen per 7 dagen' in x for x in validate_employee(person, {'D201'}))
    assert all(validate_min_days_off(x) for x in (None, 1, 2, 3))


def test_complete_rolling_windows_month_and_no_invented_boundary():
    internal = list(windows_for_month(2026, 11))
    assert len(internal) == 24
    assert internal[0][0] == date(2026, 11, 1)
    assert internal[-1][-1] == date(2026, 11, 30)
    with_history = list(windows_for_month(2026, 11, {'previous', 'next'}))
    assert len(with_history) == 36
    assert with_history[0][0] == date(2026, 10, 26)
    assert with_history[-1][-1] == date(2026, 12, 6)
    assert not published_sides({})
    assert published_sides({'_boundary_sources':{'previous': None,'next':22}}) == {'next'}
    assert published_sides({}, [boundary('2026-10-30', 'previous')]) == {'previous'}


def test_independent_rejects_six_workdays_in_seven():
    data = month()
    days = [f'2026-11-{n:02d}' for n in range(1,7)]
    out = audit(data, days)
    assert not out['passed']
    assert any('minder dan 2 vrije dagen' in x for x in out['errors'])
    assert audit(data, days[:5])['passed']
    data['employees'][0]['min_days_off_per_7'] = None
    assert audit(data, days)['passed']


def test_independent_accepts_two_nonconsecutive_days_off():
    data = month()
    dates = ['2026-11-01', '2026-11-02','2026-11-04','2026-11-05','2026-11-07']
    assert audit(data, dates)['passed']


def test_previous_published_window_blocks_too_much_work():
    data = month()
    data['demand'] = [{'date':'2026-11-01','shift_id':'D201','required':1}]
    past = [boundary(f'2026-10-{d:02d}', 'previous') for d in range(27, 32)]
    assert not audit(data,['2026-11-01'],past)['passed']
    assert audit(data,[],past)['passed']
    # ZONDER voorafgaande publicatie mag een onzichtbare oktobermaand
    # nooit worden voorgesteld alsof die volledig bekend is.
    assert audit(data,['2026-11-01'])['passed']


def test_empty_published_neighbor_is_known_but_not_required():
    empty_known = {'_boundary_sources':{'previous':18, 'next':None}}
    assert len(list(windows_for_month(2026,11,published_sides(empty_known)))) == 30
    assert not violating_windows(2026,11, {'2026-11-01'}, set(), 2, {'previous'})


def test_next_published_window_blocks_last_day():
    data = month()
    data['demand'] = [{'date':'2026-11-30','shift_id':'D201','required':1}]
    future = [boundary(f'2026-12-{n:02d}', 'next') for n in range(1,6)]
    assert not audit(data,['2026-11-30'],future)['passed']
    assert audit(data, [], future)['passed']


def database(tmp_path):
    db = get_engine(f'sqlite+pysqlite:///{tmp_path/"v029.db"}')
    initialize(db,'ROOT','LangFictiefTestWachtwoord2026!')
    initialize_months(db)
    period = list_month_workspaces(db)[0]
    return db, (period['year'],period['month'])


def test_narrow_save_preserves_corrupt_month_data_and_revisions(tmp_path):
    db, period = database(tmp_path)
    next_ = (period[0]+1,1) if period[1]==12 else (period[0],period[1]+1)
    create_month_workspace(db,*next_,'ROOT')
    with session_factory(db).begin() as session:
        work = session.get(MonthWorkspace,period_key(*period))
        changed = deepcopy(work.payload)
        changed.setdefault('hour_credits', []).append({'employee_id':'NOEXISTS','date':date(*period,8).isoformat(),
                                        'type':'Andere','hours':0.0})
        work.payload = changed
    before, rev = load_month_workspace(db,*period)
    after_prev, prev_rev = load_month_workspace(db,*next_)
    with session_factory(db)() as session:
        shared_before = deepcopy(session.get(SharedCatalog,1).payload)
    newrev = save_min_rest_days_v029(db,*period,rev,'ROOT','DEMO001',2)
    assert newrev == rev+1
    after, updated = load_month_workspace(db,*period)
    following, nextrev = load_month_workspace(db,*next_)
    assert updated == newrev and nextrev == prev_rev+1
    assert after['demand'] == before['demand']
    assert after['hour_credits'] == before['hour_credits']
    assert following['employees'][0]['min_days_off_per_7'] == 2
    assert after['employees'][0]['min_days_off_per_7'] == 2
    with session_factory(db)() as session:
        shared_after = deepcopy(session.get(SharedCatalog,1).payload)
    shared_before['employees'][0]['min_days_off_per_7'] = 2
    assert shared_before == shared_after
    with pytest.raises(ConflictError):
        save_min_rest_days_v029(db,*period,rev,'ROOT','DEMO001',1)
    assert save_min_rest_days_v029(db,*period,newrev,'ROOT','DEMO001',2) == newrev


def test_save_access_invalid_and_nonexistent(tmp_path):
    db, period = database(tmp_path)
    _, rev = load_month_workspace(db,*period)
    add_account(db,'DEMO001','Testcontroleur','controleur','FictiefTestWachtwoord2026!','ROOT')
    with pytest.raises(ValueError,match='Alleen beheerders en planners'):
        save_min_rest_days_v029(db,*period,rev,'DEMO001','DEMO001',1)
    with pytest.raises(ValueError,match='niet gevonden'):
        save_min_rest_days_v029(db,*period,rev,'ROOT','ONTBREKEND',2)
    for invalid in (0,4,True,1.0,'2',[],{}):
        with pytest.raises(ValueError):
            save_min_rest_days_v029(db,*period,rev,'ROOT','DEMO001',invalid)
    with pytest.raises(ConflictError):
        save_min_rest_days_v029(db,*period,rev+1,'ROOT','DEMO001',2)


def test_ui_uses_isolated_save():
    app = (Path(__file__).resolve().parents[1]/'app.py').read_text()
    assert 'Individuele rustspreiding bewaren' in app
    assert 'store.save_min_rest_days_v029(' in app
    assert 'min_days_off_per_7' in app
