"""v0.28: zelfstandige weekends, grensweken en veilige opslag van rotatie."""
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

from catalog import profile, validate_employee
from demo_data import build_demo
from weekend_v028 import weekend_saturdays, sliding_windows, violating_weekend_streaks
from validator_v025 import verify_plan
from store import (Account, ConflictError, MonthWorkspace, SharedCatalog, add_account,
                   create_month_workspace, get_engine, initialize, initialize_months,
                   list_month_workspaces, load_month_workspace, save_weekend_streak_v028,
                   session_factory)
from months_v012 import period_key


def state():
    data = build_demo(2026, 11)
    data['employees'] = [data['employees'][0]]
    data['employees'][0]['blocked_weekdays'] = []
    data['employees'][0]['max_consecutive_worked_weekends'] = 1
    for s in data['shifts']:
        if s['id'] == 'D201':
            s['required'] = 1
    data['demand'] = [{'date': d, 'shift_id': 'D201', 'required': 1}
                      for d in ['2026-11-07','2026-11-14','2026-11-21']]
    data['preferences'] = []
    return data


def row(day):
    return {'Datum': day, 'Personeelsnr':'DEMO001', 'Dienstnummer':'D201',
            'Categorie':'Dag', 'Begin':'09:00', 'Einde':'17:00'}


def history(day, side='previous'):
    return {'employee_id':'DEMO001', 'date':day, 'category':'Dag',
            'start':'09:00', 'end':'17:00', 'source': side}


def audit(data, days, boundaries=()):
    return verify_plan(data, {'assignments':[row(d) for d in days]}, list(boundaries))


def test_window_recognizes_weekends_not_days():
    assert {d.isoformat() for d in weekend_saturdays(['2026-11-07','2026-11-08'])} == {'2026-11-07'}
    assert not violating_weekend_streaks(['2026-11-07', '2026-11-08'], [], 1)
    v = violating_weekend_streaks(['2026-11-07','2026-11-14'], [], 1)
    assert any(tuple(x.isoformat() for x in w) == ('2026-11-07','2026-11-14') for w in v)


def test_validation_rejects_invalid_cap_and_accepts_absent_legacy():
    person = profile(state()['employees'][0])
    assert person['max_consecutive_worked_weekends'] == 1
    person.pop('max_consecutive_worked_weekends')
    assert validate_employee(person, {'D201'}) == []
    for invalid in (0, 5, True, 1.0, '2', -1, [], {}):
        person['max_consecutive_worked_weekends'] = invalid
        assert any('opeenvolgende weekends' in v for v in validate_employee(person, {'D201'}))


def test_independent_validation_rejects_2_consecutive_weekends():
    data = state()
    assert audit(data, ['2026-11-07'])['passed']
    checked = audit(data, ['2026-11-07','2026-11-14'])
    assert not checked['passed']
    assert any('opeenvolgende gewerkte weekends' in e for e in checked['errors'])
    assert audit(data, ['2026-11-07','2026-11-21'])['passed']
    data['employees'][0]['max_consecutive_worked_weekends'] = None
    assert audit(data, ['2026-11-07','2026-11-14'])['passed']


def test_independent_validation_counts_boundary_as_worked_weekend():
    data = state()
    data['demand'] = [{'date':'2026-11-07','shift_id':'D201','required':1}]
    hist = [history('2026-10-31')]
    assert not audit(data,['2026-11-07'],hist)['passed']
    assert audit(data,[],hist)['passed']
    # 31 oktober en 1 november vormen hetzelfde weekend; niet dubbel tellen.
    data['demand'] = [{'date':'2026-11-01','shift_id':'D201','required':1}]
    assert audit(data,['2026-11-01'],hist)['passed']
    data['demand'] = [{'date':'2026-11-28','shift_id':'D201','required':1}]
    assert not audit(data,['2026-11-28'],[history('2026-12-05', 'next')])['passed']


def test_window_does_not_count_missing_gap_weekend():
    assert not violating_weekend_streaks(['2026-11-07','2026-11-21'],[],1)
    assert len(sliding_windows(weekend_saturdays(['2026-11-07']), 1)) >= 1


def test_narrow_store_preserves_corrupt_activities_and_all_published_data(tmp_path):
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path/'v028.db'}")
    initialize(engine, 'ROOT', 'LangFictiefTestWachtwoord2026!')
    initialize_months(engine)
    p = list_month_workspaces(engine)[0]
    year, month = p['year'], p['month']
    next_year, next_month = (year+1, 1) if month == 12 else (year,month+1)
    create_month_workspace(engine, next_year, next_month, 'ROOT')
    original, rev = load_month_workspace(engine, year, month)
    following, later_rev = load_month_workspace(engine,next_year,next_month)
    with session_factory(engine).begin() as s:
        work = s.get(MonthWorkspace,period_key(year,month))
        changed = deepcopy(work.payload)
        changed.setdefault('hour_credits', []).append({
            'employee_id':'MISSING', 'date':date(year,month,8).isoformat(),
            'type':'Andere', 'hours':0.0})
        work.payload=changed
    before, rev = load_month_workspace(engine,year,month)
    revised = save_weekend_streak_v028(engine,year,month,rev,'ROOT','DEMO001',2)
    assert revised == rev+1
    after, seen_rev = load_month_workspace(engine,year,month)
    assert seen_rev == revised
    assert after['employees'][0]['max_consecutive_worked_weekends'] == 2
    assert after['hour_credits'] == before['hour_credits']
    assert after['demand'] == before['demand']
    next_payload, next_revision = load_month_workspace(engine,next_year,next_month)
    assert next_revision == later_rev + 1
    assert next_payload['employees'][0]['max_consecutive_worked_weekends'] == 2
    with pytest.raises(ConflictError):
        save_weekend_streak_v028(engine,year,month,rev,'ROOT','DEMO001',1)
    # Verkeerde invoer en ontbrekende controleurs moeten veilig falen.
    for bad in (True, 0, 5, '1'):
        with pytest.raises(ValueError):
            save_weekend_streak_v028(engine,year,month,revised,'ROOT','DEMO001',bad)
    with pytest.raises(ValueError):
        save_weekend_streak_v028(engine,year,month,revised,'ROOT','VERDWENEN',2)
    add_account(engine,'DEMO001','Testcontroleur','controleur','FictiefTestWachtwoord2026!','ROOT')
    with pytest.raises(ValueError, match='Alleen beheerders en planners'):
        save_weekend_streak_v028(engine,year,month,revised,'DEMO001','DEMO001',1)
    # Geen wijziging = geen revision bump
    assert save_weekend_streak_v028(engine,year,month,revised,'ROOT','DEMO001',2) == revised


def test_ui_uses_narrow_save_and_hides_new_rule_until_enabled():
    app = (Path(__file__).resolve().parents[1] / 'app.py').read_text()
    assert 'store.save_weekend_streak_v028(' in app
    assert 'Geen maximum (uit)' in app
    assert 'Weekendrotatie bewaren' in app

