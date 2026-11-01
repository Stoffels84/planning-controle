"""v0.27 testurenregimes: geen loon-/cao-regels."""
from copy import deepcopy
from datetime import date

import pytest

from demo_data import build_demo
from hours_v027 import (apply_balance_to_solver, apply_month_regimes,
                        build_balance_preview, previous_month, validate_month_regimes)
from store import (Account, ConflictError, MonthWorkspace, PlanningVersion,
                   get_engine, initialize, initialize_months, load_month_workspace,
                   published_hour_history_v027, save_month_workspace,
                   session_factory)
from months_v012 import period_key


def sample(year, month):
    data = build_demo(year, month)
    data['employees'] = [{**data['employees'][0], 'target_month_hours': 160,
                          'opening_hour_balance': 4.0},
                         {**data['employees'][1], 'target_month_hours': 100,
                          'opening_hour_balance': 0.0}]
    data['hour_credits'] = []
    data['month_hour_regimes_v027'] = {}
    return data


def record(year, month, assignments, credits=None, plan_id=5, revision=1):
    data = sample(year, month)
    data['hour_credits'] = credits or []
    return {'year': year, 'month': month, 'data': data,
            'plan_id': plan_id, 'revision': revision, 'plan_revision': revision,
            'plan': {'status': 'FEASIBLE', 'assignments': assignments,
                     'task_assignments': [dict(x) for x in assignments]}}


def assignment(eid, year, month, hours, day=5, task=False):
    return {'Personeelsnr': eid, 'Datum': date(year, month, day).isoformat(),
            'Dienstnummer': 'TAAK:X' if task else 'V101', 'Uren': hours}


def test_regime_override_only_month_no_shared_mutation():
    november = sample(2026, 11)
    december = deepcopy(november)
    december['month'] = 12
    december['month_hour_regimes_v027'] = {'DEMO001': {'target_month_hours': 80.0,
                                                      'max_month_hours': 120.0}}
    changed = apply_month_regimes(december)
    assert changed['employees'][0]['target_month_hours'] == 80
    assert changed['employees'][0]['max_month_hours'] == 120
    assert november['employees'][0]['target_month_hours'] == 160
    assert december['employees'][0]['target_month_hours'] == 160


def test_invalid_month_profile_rejected():
    data = sample(2026, 11)
    invalid = [
        {'MISSING': {'target_month_hours': 20, 'max_month_hours': 50}},
        {'DEMO001': {'target_month_hours': 200, 'max_month_hours': 100}},
        {'DEMO001': {'target_month_hours': -3, 'max_month_hours': 100}},
        {'DEMO001': {'target_month_hours': 0, 'max_month_hours': 999}},
        {'DEMO001': {'target_month_hours': float('nan'), 'max_month_hours': 100}},
        {'DEMO001': {'target_month_hours': 20, 'max_month_hours': 100, 'opening_hour_balance': 5}},
    ]
    for profile in invalid:
        data['month_hour_regimes_v027'] = profile
        assert validate_month_regimes(data)
        with pytest.raises(ValueError):
            apply_month_regimes(data)


def test_published_month_credits_and_tasks_counted_once():
    current = sample(2026, 12)
    oct_nov = [record(2026, 11, [assignment('DEMO001', 2026, 11, 8),
                                  assignment('DEMO001', 2026, 11, 3.5, day=6, task=True)],
                     [{'employee_id': 'DEMO001', 'date': '2026-11-08', 'hours': 7.6}])]
    report = build_balance_preview(current, oct_nov)
    # 4 + (8 + 3.5) + 7.6 - 160 = -136.9
    assert report['eligible']['DEMO001'] == -136.9
    assert report['eligible']['DEMO002'] == -100.0
    assert report['history'][0]['Planuren'] == 11.5
    assert report['history'][0]['Geregistreerde uren'] == 7.6
    assert report['sources'][0]['plan_id'] == 5
    adjusted = apply_balance_to_solver(current, report['eligible'])
    assert adjusted['employees'][0]['opening_hour_balance'] == -136.9
    assert adjusted['settings']['use_opening_balance'] is True
    assert current['employees'][0]['opening_hour_balance'] == 4.0


def test_two_contiguous_months_roll_forward():
    prev = record(2026, 11, [assignment('DEMO001',2026,11,8,day=i) for i in range(1,11)], plan_id=7)
    older = record(2026, 10, [assignment('DEMO001',2026,10,9,day=i) for i in range(1,11)], plan_id=6)
    report = build_balance_preview(sample(2026,12), [prev,older])
    assert report['eligible']['DEMO001'] == 4+90-160+80-160
    assert [row['plan_id'] for row in report['sources']] == [6,7]


def test_no_prior_published_month_no_balance():
    report = build_balance_preview(sample(2026,12), [])
    assert not report['available'] and not report['eligible']
    assert 'niet gepubliceerd' in report['warnings'][0]
    with pytest.raises(ValueError):
        apply_balance_to_solver(sample(2026,12), {})


def test_missing_streefuren_disallows_one_employee_not_all():
    prev = record(2026,11,[assignment('DEMO001',2026,11,8)])
    prev['data']['employees'][1]['target_month_hours'] = 0
    result = build_balance_preview(sample(2026,12), [prev])
    assert 'DEMO001' in result['eligible'] and 'DEMO002' not in result['eligible']


def test_unpublished_gap_is_not_ignored():
    older = record(2026,10,[assignment('DEMO001',2026,10,90)])
    result = build_balance_preview(sample(2026,12), [older])
    assert not result['available']


def test_outdated_source_disables_carryover():
    prev = record(2026,11,[], revision=5)
    prev['plan_revision'] = 4
    result = build_balance_preview(sample(2026,12), [prev])
    assert not result['available']
    assert any('verouderde' in message for message in result['warnings'])


def setup_db(tmp_path):
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path/'test027.db'}")
    initialize(engine, 'ROOT', 'LangVeiligTestWachtwoord2026!')
    initialize_months(engine)
    return engine


def test_month_override_saved_isolated_and_secured(tmp_path):
    engine = setup_db(tmp_path)
    from store import list_month_workspaces
    item = list_month_workspaces(engine)[0]
    legacy, rev = load_month_workspace(engine, item['year'], item['month'])
    changed = deepcopy(legacy)
    changed['month_hour_regimes_v027'] = {'DEMO001': {'target_month_hours': 100, 'max_month_hours': 130}}
    rev2 = save_month_workspace(engine, changed, rev, 'ROOT', 'Maandregime instellen')
    actual, _ = load_month_workspace(engine, changed['year'], changed['month'])
    assert actual['month_hour_regimes_v027'] == changed['month_hour_regimes_v027']
    assert actual['employees'][0]['max_month_hours'] == legacy['employees'][0]['max_month_hours']
    with pytest.raises(ConflictError):
        save_month_workspace(engine, changed, rev, 'ROOT', 'Verouderd')


def test_server_rejects_unauthorized_or_invalid_month_regime(tmp_path):
    engine=setup_db(tmp_path)
    from store import list_month_workspaces
    row=list_month_workspaces(engine)[0]
    d,rev=load_month_workspace(engine,row['year'],row['month'])
    invalid=deepcopy(d)
    invalid['month_hour_regimes_v027']={'DEMO001':{'target_month_hours':200,'max_month_hours':100}}
    with pytest.raises(ValueError,match='DEMO001'):
        save_month_workspace(engine,invalid,rev,'ROOT','Invalid')
    from store import add_account
    add_account(engine,'DEMO001','Test','controleur','VeiligWachtwoordVoorTest2026!','ROOT')
    valid=deepcopy(d)
    valid['month_hour_regimes_v027']={'DEMO001':{'target_month_hours':100,'max_month_hours':150}}
    with pytest.raises(ValueError,match='uitsluitend|eigen voorkeuren'):
        save_month_workspace(engine,valid,rev,'DEMO001','No permission')


def test_source_republication_or_month_change_blocks_saved_hours(tmp_path):
    from store import _assert_hour_sources_v027, session_factory, SharedCatalog
    engine=setup_db(tmp_path)
    with session_factory(engine).begin() as s:
        # setup test month snapshots independently of global profile
        src=MonthWorkspace(period=202610,payload=sample(2026,10),revision=1)
        s.add(src)
        s.add(PlanningVersion(year=2026,month=10,workspace_revision=1,
                              author='ROOT',created_at=__import__('store').now(),
                              published_at=__import__('store').now(),
                              payload={'status':'FEASIBLE','assignments':[]}))
    with session_factory(engine)() as s:
        pub=s.query(PlanningVersion).filter_by(year=2026,month=10).first()
        source={'year':2026,'month':10,'plan_id':pub.id,'revision':1}
        _assert_hour_sources_v027(s,2026,11,{'summary':{'hour_sources_v027':[source]}})
    with session_factory(engine).begin() as s:
        s.get(MonthWorkspace,202610).revision += 1
    with session_factory(engine)() as s:
        with pytest.raises(ConflictError,match='gewijzigd'):
            _assert_hour_sources_v027(s,2026,11,{'summary':{'hour_sources_v027':[source]}})


def test_backend_reads_only_published_and_rejects_stale_month(tmp_path):
    from store import create_month_workspace, list_month_workspaces, now
    engine = setup_db(tmp_path)
    months = {(x['year'], x['month']) for x in list_month_workspaces(engine)}
    if (2026, 11) not in months:
        create_month_workspace(engine, 2026, 11, 'ROOT')
    nov, rev = load_month_workspace(engine, 2026, 11)
    nov['month_hour_regimes_v027'] = {
        'DEMO001': {'target_month_hours': 160.0, 'max_month_hours': 176.0}}
    revision = save_month_workspace(engine, nov, rev, 'ROOT', 'Fictieve novemberuren')
    with session_factory(engine).begin() as s:
        # Concept mag nooit worden meegeteld, ongeacht hoe recent het is.
        s.add(PlanningVersion(workspace_revision=revision, year=2026, month=11,
                              author='ROOT', created_at=now(), published_at=None,
                              payload={'status': 'FEASIBLE', 'assignments': [
                                  assignment('DEMO001', 2026, 11, 16)]}))
        s.add(PlanningVersion(workspace_revision=revision, year=2026, month=11,
                              author='ROOT', created_at=now(), published_at=now(),
                              payload={'status': 'FEASIBLE', 'assignments': [
                                  assignment('DEMO001', 2026, 11, 8)]}))
    history = published_hour_history_v027(engine, 'ROOT', 2026, 12)
    assert len(history) == 1
    assert history[0]['plan_revision'] == revision
    current, _ = load_month_workspace(engine, 2026, 12)
    preview = build_balance_preview(current, history)
    assert preview['eligible']['DEMO001'] == -152  # 0 + 8 - 160
    nov, rev = load_month_workspace(engine, 2026, 11)
    nov['month_hour_regimes_v027']['DEMO001']['max_month_hours'] = 170
    save_month_workspace(engine, nov, rev, 'ROOT', 'Fictieve correctie november')
    outdated = build_balance_preview(current, published_hour_history_v027(engine, 'ROOT', 2026, 12))
    assert not outdated['available']


def test_person_without_history_never_inherits_manual_balance():
    data = sample(2026, 12)
    adjusted = apply_balance_to_solver(data, {'DEMO001': 12.5})
    assert adjusted['employees'][0]['opening_hour_balance'] == 12.5
    assert adjusted['employees'][1]['opening_hour_balance'] == 0
