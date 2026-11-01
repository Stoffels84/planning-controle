"""v0.30: beperkingen, bevoegdheden en gerichte opslag van voorkeuren."""
from copy import deepcopy
from datetime import date, timedelta

import pytest

import store
from demo_data import next_month
from months_v012 import period_key
from preferences_v030 import (default_policy, policy_for, validate_policy, is_open,
                               enforce_submission, counts_for, PREFERENCE_KINDS)


def setup(tmp_path):
    db = store.get_engine(f"sqlite+pysqlite:///{tmp_path/'pref030.db'}")
    store.initialize(db, 'ROOT', 'LangFictiefTestWachtwoord2026!')
    store.initialize_months(db)
    store.add_account(db, 'DEMO005', 'Fictieve controleur', 'controleur',
                      'LangFictiefTestWachtwoord2026!', 'ROOT')
    months = store.list_month_workspaces(db)
    y, m = months[0]['year'], months[0]['month']
    return db, (y, m)


def wish(period, day=5, typ='free_day'):
    y, m = period
    obj = {'employee_id': 'DEMO005', 'type': typ,
           'date': date(y, m, day).isoformat(), 'priority': 2}
    if typ == 'daily_shift':
        obj['shift_id'] = 'V101'
    return obj


def current_policy(today=None, **caps):
    now = today or date.today()
    return {'open_from': (now - timedelta(days=1)).isoformat(),
            'open_until': (now + timedelta(days=1)).isoformat(),
            'limits': caps}


def test_old_months_remain_open_without_quotas():
    assert policy_for({}) == default_policy()
    assert is_open(policy_for({}), date(2050, 1, 1))
    enforce_submission(None, 'A', [{'employee_id': 'A', 'type': 'free_day'}] * 15,
                       today=date(2050, 1, 1))


def test_reject_malformed_window_and_quotas():
    bad = [
        {'open_from': '2026-11-01', 'open_until': None, 'limits': {}},
        {'open_from': '2026-12-10', 'open_until': '2026-12-01', 'limits': {}},
        {'open_from': '2026-99-10', 'open_until': '2026-12-01', 'limits': {}},
        {'open_from': None, 'open_until': None, 'limits': {'free_day': -1}},
        {'open_from': None, 'open_until': None, 'limits': {'free_day': True}},
        {'open_from': None, 'open_until': None, 'limits': {'unknown': 2}},
        {'open_from': None, 'open_until': None, 'limits': {'daily_shift': 32}},
        {'open_from': None, 'open_until': None, 'limits': []},
    ]
    assert all(validate_policy(p) for p in bad)


def test_dates_inclusive_and_all_kinds_count_separately():
    today = date(2026, 11, 2)
    p = {'open_from': '2026-11-01', 'open_until': '2026-11-03',
         'limits': {'free_day': 1, 'daily_shift': 1}}
    assert is_open(p, date(2026, 11, 1))
    assert is_open(p, date(2026, 11, 3))
    assert not is_open(p, date(2026, 11, 4))
    prefs = [{'employee_id': 'A', 'type': 'free_day'},
             {'employee_id': 'A', 'type': 'daily_shift'},
             {'employee_id': 'B', 'type': 'free_day'}]
    assert counts_for(prefs, 'A')['free_day'] == 1
    assert counts_for(prefs, 'A')['daily_shift'] == 1
    enforce_submission(p, 'A', prefs, today=today)
    with pytest.raises(ValueError, match='Maximum 1'):
        enforce_submission(p, 'A', prefs + [{'employee_id': 'A', 'type': 'free_day'}], today=today)
    with pytest.raises(ValueError, match='gesloten'):
        enforce_submission(p, 'A', prefs, today=date(2026, 11, 4))
    enforce_submission(p, 'A', prefs * 3, manager_override=True, today=date(2026, 11, 4))
    assert len(PREFERENCE_KINDS) == 7


def test_manager_policy_update_changes_only_selected_month(tmp_path):
    db, period = setup(tmp_path)
    year, month = period
    next_year, next_month = (year + (month == 12), month % 12 + 1)
    store.create_month_workspace(db, next_year, next_month, 'ROOT')
    before, rev = store.load_month_workspace(db, year, month)
    other, other_rev = store.load_month_workspace(db, next_year, next_month)
    with store.session_factory(db)() as s:
        before_payload = deepcopy(s.get(store.MonthWorkspace, period_key(*period)).payload)
        before_global = deepcopy(s.get(store.SharedCatalog, 1).payload)
    policy = current_policy(free_day=2, daily_shift=4)
    newrev = store.save_preference_policy_v030(db, year, month, rev, 'ROOT', policy)
    after, checkrev = store.load_month_workspace(db, year, month)
    other_after, other_checkrev = store.load_month_workspace(db, next_year, next_month)
    assert newrev == checkrev == rev + 1
    assert after['preference_policy_v030'] == policy
    assert policy_for(other_after) == default_policy()
    assert other_checkrev == other_rev
    with store.session_factory(db)() as s:
        stored = deepcopy(s.get(store.MonthWorkspace, period_key(*period)).payload)
        assert s.get(store.SharedCatalog, 1).payload == before_global
    expected = before_payload | {'preference_policy_v030': policy}
    assert stored == expected
    with pytest.raises(store.ConflictError):
        store.save_preference_policy_v030(db, year, month, rev, 'ROOT', policy)
    for actor in ['DEMO005', 'INVALID']:
        with pytest.raises(ValueError, match='Alleen beheerders'):
            store.save_preference_policy_v030(db, year, month, newrev, actor, policy)


def test_only_own_preferences_and_no_other_changes(tmp_path):
    db, period = setup(tmp_path)
    state, rev = store.load_month_workspace(db, *period)
    before = deepcopy(state)
    first = wish(period, 7)
    newrev = store.save_employee_preferences_v030(db, *period, rev, 'DEMO005', 'DEMO005', [first])
    after, readrev = store.load_month_workspace(db, *period)
    assert newrev == readrev == rev + 1
    assert [p for p in after['preferences'] if p['employee_id'] == 'DEMO005'] == [first]
    assert [p for p in after['preferences'] if p['employee_id'] != 'DEMO005'] == [
        p for p in before['preferences'] if p['employee_id'] != 'DEMO005']
    for field in ('hour_credits', 'demand', 'shifts', 'employees', 'month_hour_regimes_v027'):
        assert after.get(field) == before.get(field)
    with pytest.raises(ValueError, match='eigen voorkeuren'):
        store.save_employee_preferences_v030(db, *period, newrev, 'DEMO005', 'DEMO006', [])
    with pytest.raises(ValueError, match='Alleen wensen'):
        store.save_employee_preferences_v030(db, *period, newrev, 'ROOT', 'DEMO005', [wish(period, 8) | {'employee_id':'DEMO006'}])
    with pytest.raises(store.ConflictError):
        store.save_employee_preferences_v030(db, *period, rev, 'DEMO005', 'DEMO005', [])


def test_quota_and_window_enforced_at_database_even_if_ui_bypassed(tmp_path, monkeypatch):
    db, period = setup(tmp_path)
    state, rev = store.load_month_workspace(db, *period)
    now = date(2026, 11, 2)
    monkeypatch.setattr(store, 'belgian_today', lambda: now)
    policy = {'open_from': '2026-11-01', 'open_until': '2026-11-03', 'limits': {'free_day': 1}}
    rev = store.save_preference_policy_v030(db, *period, rev, 'ROOT', policy)
    one = wish(period, 7)
    rev = store.save_employee_preferences_v030(db, *period, rev, 'DEMO005', 'DEMO005', [one])
    two = [one, wish(period, 8)]
    with pytest.raises(ValueError, match='Maximum 1'):
        store.save_employee_preferences_v030(db, *period, rev, 'DEMO005', 'DEMO005', two)
    monkeypatch.setattr(store, 'belgian_today', lambda: date(2026, 11, 4))
    with pytest.raises(ValueError, match='gesloten'):
        store.save_employee_preferences_v030(db, *period, rev, 'DEMO005', 'DEMO005', [])
    # Planner can override intentionally without changing the rule.
    rev = store.save_employee_preferences_v030(db, *period, rev, 'ROOT', 'DEMO005', two)
    got, _ = store.load_month_workspace(db, *period)
    assert len([p for p in got['preferences'] if p.get('employee_id') == 'DEMO005']) == 2
    assert got['preference_policy_v030'] == policy


def test_old_invalid_month_inputs_do_not_block_valid_personal_wishes(tmp_path):
    db, period = setup(tmp_path)
    with store.session_factory(db).begin() as sess:
        rec = sess.get(store.MonthWorkspace, period_key(*period))
        old = deepcopy(rec.payload)
        old['hour_credits'] = [{'employee_id':'UNKNOWN','date':'2026-11-19', 'type':'Andere','hours':1}]
        old['demand'][0]['required'] += 1
        rec.payload = old
    state, rev = store.load_month_workspace(db, *period)
    saved = store.save_employee_preferences_v030(db, *period, rev, 'DEMO005', 'DEMO005', [wish(period, 5)])
    after, _ = store.load_month_workspace(db, *period)
    assert saved == rev + 1
    assert after['hour_credits'] == state['hour_credits']
    assert after['demand'] == state['demand']


def test_invalid_dates_and_duplicate_preference_rejected(tmp_path):
    db, period = setup(tmp_path)
    _, rev = store.load_month_workspace(db, *period)
    first = wish(period, 7)
    for prefs in ([first, first], [wish(period, 7) | {'priority': 12}],
                  [wish(period, 7) | {'date': '2020-02-02'}]):
        with pytest.raises(ValueError):
            store.save_employee_preferences_v030(db, *period, rev, 'DEMO005', 'DEMO005', prefs)


def test_old_full_save_api_cannot_bypass_submission_policy(tmp_path, monkeypatch):
    db, period = setup(tmp_path)
    monkeypatch.setattr(store, 'belgian_today', lambda: date(2026, 11, 8))
    state, rev = store.load_month_workspace(db, *period)
    policy = {'open_from': '2026-11-01', 'open_until': '2026-11-02', 'limits': {}}
    rev = store.save_preference_policy_v030(db, *period, rev, 'ROOT', policy)
    state, rev = store.load_month_workspace(db, *period)
    state['preferences'].append(wish(period, 7))
    with pytest.raises(ValueError, match='gesloten'):
        store.save_month_workspace(db, state, rev, 'DEMO005', 'Oude API')
