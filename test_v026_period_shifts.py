"""v0.26: maandgebonden diensturen, geen historische regressie, toegangscontrole."""
from copy import deepcopy
from datetime import date
import pytest

from store import (get_engine, initialize, initialize_months, load_month_workspace,
                   save_month_workspace, create_month_workspace,
                   save_plan, publish_plan, load_plan, list_month_workspaces,
                   ConflictError, Account, SharedCatalog, MonthWorkspace, session_factory)
from months_v012 import period_key


def database(tmp_path):
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path/'period.sqlite'}")
    initialize(engine, 'ROOT', 'LangTestWachtwoord-2026-123!')
    initialize_months(engine)
    months = list_month_workspaces(engine)
    y, m = months[0]['year'], months[0]['month']
    return engine, (y, m)


def plus_month(y, m, distance=1):
    k = y * 12 + m - 1 + distance
    return (k // 12, k % 12 + 1)


def change_shift(state, shift_id='V101', start='07:15', end='15:15', required=1):
    for s in state['shifts']:
        if s['id'] == shift_id:
            s.update(start=start, end=end, required=required)
    for r in state['demand']:
        if r['shift_id'] == shift_id:
            r['required'] = required


def test_current_month_changes_do_not_rewrite_existing_other_month(tmp_path):
    db, original = database(tmp_path)
    next_ = plus_month(*original)
    create_month_workspace(db, *next_, 'ROOT')
    old, rev_old = load_month_workspace(db, *original)
    following, rev_next = load_month_workspace(db, *next_)
    assert following['shifts'] == old['shifts']
    assert old['shift_catalog_v026'] and following['shift_catalog_v026']
    change_shift(following)
    changed_rev = save_month_workspace(db, following, rev_next, 'ROOT', 'Maanddienst wijzigen')
    assert changed_rev == rev_next + 1
    reread_old, rev_read_old = load_month_workspace(db, *original)
    assert reread_old['shifts'] == old['shifts']
    assert rev_read_old == rev_old
    latest, _ = load_month_workspace(db, *next_)
    assert next(s for s in latest['shifts'] if s['id'] == 'V101')['start'] == '07:15'
    assert all(r["required"] == next(s["required"] for s in latest["shifts"] if s["id"] == r["shift_id"]) for r in latest["demand"])


def test_new_month_inherits_immediately_preceding_catalog_not_stale_global(tmp_path):
    db, original = database(tmp_path)
    later, latest = plus_month(*original), plus_month(*original, 2)
    create_month_workspace(db, *later, 'ROOT')
    dec, rev = load_month_workspace(db, *later)
    change_shift(dec, start='09:10', end='17:10')
    save_month_workspace(db, dec, rev, 'ROOT', 'Decemberuren')
    create_month_workspace(db, *latest, 'ROOT')
    jan, rev = load_month_workspace(db, *latest)
    assert next(s for s in jan['shifts'] if s['id'] == 'V101')['start'] == '09:10'
    # Wijzigingen in december achteraf veranderen januari niet.
    dec2, rev2 = load_month_workspace(db, *later)
    change_shift(dec2, start='10:00', end='18:00')
    save_month_workspace(db, dec2, rev2, 'ROOT', 'Achteraf december aangepast')
    jan2, janrev = load_month_workspace(db, *latest)
    assert jan2['shifts'] == jan['shifts'] and janrev == rev
    initial, _ = load_month_workspace(db, *original)
    assert next(s for s in initial['shifts'] if s['id'] == 'V101')['start'] == '06:00'


def test_existing_future_month_is_not_modified_when_predecessor_changes(tmp_path):
    db, original = database(tmp_path)
    later = plus_month(*original)
    after = plus_month(*original, 2)
    create_month_workspace(db, *later, 'ROOT')
    create_month_workspace(db, *after, 'ROOT')
    december, r = load_month_workspace(db, *later)
    january, rjan = load_month_workspace(db, *after)
    change_shift(december)
    save_month_workspace(db, december, r, 'ROOT', 'Diensturen aangepast')
    january_unchanged, rjan2 = load_month_workspace(db, *after)
    assert january_unchanged['shifts'] == january['shifts']
    assert rjan == rjan2


def test_copy_month_demand_uses_destination_required(tmp_path):
    from store import copy_month_workspace_demand
    db, original = database(tmp_path)
    later = plus_month(*original)
    create_month_workspace(db, *later, 'ROOT')
    target, rev = load_month_workspace(db, *later)
    change_shift(target, required=1)
    rev = save_month_workspace(db, target, rev, 'ROOT', 'Maandbezetting')
    copy_month_workspace_demand(db, *original, *later, rev, 'ROOT', mode='weekday')
    target_after, _ = load_month_workspace(db, *later)
    relevant = [r for r in target_after['demand'] if r['shift_id'] == 'V101']
    assert relevant and all(r['required'] == 1 for r in relevant)
    assert all(r["required"] == next(s["required"] for s in target_after["shifts"] if s["id"] == r["shift_id"]) for r in target_after["demand"])


def test_new_month_copy_uses_new_month_shift_definitions(tmp_path):
    db, original = database(tmp_path)
    dec = plus_month(*original)
    jan = plus_month(*original, 2)
    create_month_workspace(db, *dec, 'ROOT')
    dec_data, rev = load_month_workspace(db, *dec)
    change_shift(dec_data, required=1)
    save_month_workspace(db, dec_data, rev, 'ROOT', 'December')
    create_month_workspace(db, *jan, 'ROOT', source_period=original, copy_mode='weekday')
    january, _ = load_month_workspace(db, *jan)
    assert january['demand']
    assert all(r['required'] == 1 for r in january['demand'] if r['shift_id'] == 'V101')
    assert all(r["required"] == next(s["required"] for s in january["shifts"] if s["id"] == r["shift_id"]) for r in january["demand"])


def test_shared_employees_remain_global_but_shifts_do_not(tmp_path):
    db, original = database(tmp_path)
    later = plus_month(*original)
    create_month_workspace(db, *later, 'ROOT')
    a, ar = load_month_workspace(db, *original)
    b, br = load_month_workspace(db, *later)
    a['employees'][0]['name'] = 'Nieuwe demo-naam'
    save_month_workspace(db, a, ar, 'ROOT', 'Personeel gewijzigd')
    b_now, br_new = load_month_workspace(db, *later)
    assert b_now['employees'][0]['name'] == 'Nieuwe demo-naam'
    assert br_new == br + 1
    with pytest.raises(ConflictError):
        save_month_workspace(db, b, br, 'ROOT', 'Oude revisie')


def test_legacy_migration_freezes_effective_shared_catalog_without_revision_change(tmp_path):
    db, original = database(tmp_path)
    later = plus_month(*original)
    create_month_workspace(db, *later, 'ROOT')
    current, rev = load_month_workspace(db, *later)
    with session_factory(db).begin() as s:
        month_row = s.get(MonthWorkspace, period_key(*later))
        old = dict(month_row.payload)
        old.pop('shift_catalog_v026')
        old['shifts'] = []  # In v0.25 was dit verborgen achter global shared.
        month_row.payload = old
    migrated, migrated_revision = load_month_workspace(db, *later)
    assert migrated_revision == rev
    assert migrated['shift_catalog_v026'] is True
    assert migrated['shifts'] == current['shifts']


def test_month_edits_cannot_be_done_by_controlleur(tmp_path):
    from store import add_account
    db, original = database(tmp_path)
    add_account(db, 'TEST001', 'Testcontroleur', 'controleur',
                'HeelSterkWachtwoord-2026-456!', 'ROOT')
    month, rev = load_month_workspace(db, *original)
    change_shift(month)
    with pytest.raises(ValueError, match='alleen hun eigen voorkeuren'):
        save_month_workspace(db, month, rev, 'TEST001', 'Ongeoorloofde dienstwijziging')


def test_invalid_shift_catalog_is_rejected_server_side(tmp_path):
    db, original = database(tmp_path)
    month, rev = load_month_workspace(db, *original)
    month['shifts'][0]['start'] = '25:70'
    with pytest.raises(ValueError, match='Ongeldige maanddiensten'):
        save_month_workspace(db, month, rev, 'ROOT', 'Onjuiste diensturen')


def test_published_plan_records_remain_unchanged(tmp_path):
    db, original = database(tmp_path)
    old_state, rev = load_month_workspace(db, *original)
    fake = {'status':'FEASIBLE', 'assignments': [], 'open_positions': [],
            'summary':{'required': 0, 'assigned': 0, 'open': 0}}
    plan_id = save_plan(db, old_state, rev, fake, 'ROOT')
    publish_plan(db, plan_id, rev, 'ROOT')
    original_published = deepcopy(load_plan(db, *original, published_only=True))
    later = plus_month(*original)
    create_month_workspace(db, *later, 'ROOT')
    next_data, next_rev = load_month_workspace(db, *later)
    change_shift(next_data)
    save_month_workspace(db, next_data, next_rev, 'ROOT', 'Nieuwe diensturen')
    assert load_plan(db, *original, published_only=True) == original_published


def test_solver_uses_month_specific_definitions_when_available(tmp_path):
    pytest.importorskip('ortools')
    from planner import validate_dataset, solve_month
    db, original = database(tmp_path)
    next_ = plus_month(*original)
    create_month_workspace(db, *next_, 'ROOT', source_period=original)
    following, rev = load_month_workspace(db, *next_)
    change_shift(following, start='08:00', end='16:00', required=1)
    save_month_workspace(db, following, rev, 'ROOT', 'Aangepaste uren')
    following, rev = load_month_workspace(db, *next_)
    assert validate_dataset(following) == []
    # Kleine planning om de directe solver te testen, zonder maandoverschrijdende
    # wijzigingen aan historie.
    following['demand'] = [r for r in following['demand'] if r['shift_id'] == 'V101'][:1]
    following['preferences'] = []
    following['settings']['time_limit_seconds'] = 5
    plan = solve_month(following)
    assert plan.status in ('FEASIBLE', 'OPTIMAL')
    assert all(r['Begin'] == '08:00' and r['Einde'] == '16:00' for r in plan.assignments)


def test_employee_blocked_shift_from_other_month_does_not_invalidate_history(tmp_path):
    from catalog import validate_employee
    db, original = database(tmp_path)
    dec = plus_month(*original)
    create_month_workspace(db, *dec, 'ROOT')
    later, rev = load_month_workspace(db, *dec)
    later['shifts'].append({'id':'D999', 'name':'Nieuwe dienst', 'category':'Dag',
                            'start':'08:00', 'end':'16:00', 'required':1, 'active':True})
    later['employees'][0]['blocked_shifts'] = ['D999']
    save_month_workspace(db, later, rev, 'ROOT', 'Nieuwe dienst en beperking')
    historical, _ = load_month_workspace(db, *original)
    assert all(s['id'] != 'D999' for s in historical['shifts'])
    assert historical['employees'][0]['blocked_shifts'] == ['D999']
    assert validate_employee(historical['employees'][0], {s['id'] for s in historical['shifts']}) == []
