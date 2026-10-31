"""Zuivere unit-tests voor de v0.6-regels, zonder OR-Tools of Streamlit."""
from datetime import datetime

from catalog import new_employee, profile, settings_with_defaults, validate_employee, validate_schedule_settings
from demo_data import build_demo
from policy_v06 import (hours_overview, saturday_for, service_overview,
                         touches_protected_weekend, weekend_start_dates)
from store import get_engine, initialize, load_workspace, save_workspace


def test_v05_workspace_compatible_defaults():
    sample = build_demo(2026, 11)
    employee = sample['employees'][0]
    original = dict(employee)
    extended = profile(employee)
    assert extended['max_weekend_days'] is None
    assert extended['protected_weekends'] == []
    assert extended['opening_hour_balance'] == 0
    assert sample['employees'][0] == original
    assert settings_with_defaults(sample['settings'])['use_opening_balance'] is False
    assert validate_employee(extended, {s['id'] for s in sample['shifts']}) == []


def test_protected_weekend_overlaps_friday_night_and_saturday_sunday():
    employee = new_employee('X1','Test','Testteam',100,180)
    employee['protected_weekends'] = ['2026-11-14']
    assert touches_protected_weekend(employee, datetime(2026,11,13,22),datetime(2026,11,14,6))
    assert touches_protected_weekend(employee, datetime(2026,11,14,10),datetime(2026,11,14,18))
    assert touches_protected_weekend(employee, datetime(2026,11,15,22),datetime(2026,11,16,6))
    assert not touches_protected_weekend(employee, datetime(2026,11,13,16),datetime(2026,11,14))
    assert not touches_protected_weekend(employee, datetime(2026,11,16),datetime(2026,11,16,7))


def test_weekends_sunday_first_day_include_previous_month_saturday():
    assert weekend_start_dates(2026, 11)[0] == '2026-10-31'
    assert saturday_for(__import__('datetime').date(2026,11,1)).isoformat() == '2026-10-31'
    assert len(weekend_start_dates(2026, 11)) == 5


def test_employee_and_global_validations():
    sample = build_demo(2026,11)
    emp = new_employee('TEST1','Test','Demo',100,180)
    emp['max_month_categories'] = {'Nacht': 2}
    emp['target_month_categories'] = {'Nacht': 3}
    assert any('streefwaarde' in e.lower() for e in validate_employee(emp,set()))
    emp['target_month_categories'] = {'Nacht':2}
    emp['protected_weekends'] = ['2026-11-15']  # zondag, niet toegestaan
    assert any('zaterdag' in e.lower() for e in validate_employee(emp,set()))
    emp['protected_weekends'] = ['2026-11-14']
    assert validate_employee(emp, set()) == []
    cfg = sample['settings'] | {'max_weekend_days': -1}
    assert validate_schedule_settings(cfg)
    cfg['max_weekend_days'] = 0
    assert validate_schedule_settings(cfg) == []


def test_hours_balance_is_only_simulation_and_can_be_switched_off():
    emp = new_employee('T1','Test','Test',100,176)
    emp['target_month_hours'] = 160
    emp['opening_hour_balance'] = 5
    plan = [{'Personeelsnr':'T1','Uren': 8}]
    credits = [{'employee_id':'T1','hours':7.6}]
    on = hours_overview([emp],plan,credits,True)[0]
    off = hours_overview([emp],plan,credits,False)[0]
    assert on['Startsaldo (test)'] == 5
    assert on['Eindsaldo (test)'] == -139.4
    assert off['Eindsaldo (test)'] == -144.4


def test_service_counts_worked_weekends_by_start_day():
    emp = new_employee('T1','Test','Test',100,176)
    assignments = [{'Personeelsnr':'T1','Datum':'2026-11-14','Categorie':'Nacht'},
                   {'Personeelsnr':'T1','Datum':'2026-11-15','Categorie':'Dag'},
                   {'Personeelsnr':'T1','Datum':'2026-11-22','Categorie':'Vroeg'}]
    report = service_overview([emp],assignments)[0]
    assert report['Weekenddagen'] == 3
    assert report['Gewerkte weekends'] == 2
    assert report['Nacht'] == 1


def test_database_upgrade_does_not_drop_old_profiles(tmp_path):
    engine = get_engine(f'sqlite+pysqlite:///{tmp_path / "upgrade-v06.db"}')
    initialize(engine, 'ADMIN01', 'veilig-test-wachtwoord-heel-lang')
    state, revision = load_workspace(engine)
    eid = state['employees'][0]['id']
    state['employees'][0]['protected_weekends'] = ['2026-11-14']
    state['employees'][0]['max_month_categories'] = {'Nacht': 2}
    state['settings']['use_opening_balance'] = True
    revision2 = save_workspace(engine, state, revision, 'ADMIN01', 'v06-update')
    loaded, loaded_revision = load_workspace(engine)
    assert revision2 == loaded_revision
    assert loaded['employees'][0]['id'] == eid
    assert loaded['employees'][0]['max_month_categories']['Nacht'] == 2
    assert loaded['settings']['use_opening_balance'] is True
