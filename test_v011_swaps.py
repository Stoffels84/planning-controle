"""V0.11: contract tests ruilworkflow (fictieve gegevens)."""
from copy import deepcopy
from datetime import date

import pytest

from store import (get_engine, initialize, add_account, load_workspace, save_plan,
                   publish_plan, load_plan, request_swap, list_swap_requests,
                   respond_swap, decide_swap, ConflictError, save_workspace)
from swap_v011 import make_swap_plan


def db_with_published_plan(tmp_path):
    db = get_engine(f"sqlite+pysqlite:///{tmp_path / 'swaps.sqlite'}")
    initialize(db, 'TESTADMIN', 'VoorbeeldSterkWachtwoord2026!')
    for i in (1, 2, 3):
        add_account(db, f'DEMO{i:03}', f'Testcontroleur {i:02}', 'controleur',
                    f'VeiligTestWachtwoord{i:04}!!', 'TESTADMIN')
    add_account(db, 'PLANNER', 'Testplanner', 'planner',
                'VeiligPlannerWachtwoord2026!!!', 'TESTADMIN')
    workspace, revision = load_workspace(db)
    y, m = workspace['year'], workspace['month']
    a, b = date(y, m, 3), date(y, m, 6)
    row = lambda d, code, person, name: {
        'Datum': d.isoformat(), 'Dienstnummer': code, 'Soort': 'Reguliere dienst',
        'Personeelsnr': person, 'Controleur': name, 'Categorie': 'Dag',
        'Begin': '09:00', 'Einde': '17:00', 'Beginlocatie': '', 'Eindlocatie': '', 'Uren': 8
    }
    result = {'status': 'FEASIBLE', 'assignments': [
        row(a, 'V101', 'DEMO001', 'Testcontroleur 01'),
        row(b, 'D201', 'DEMO002', 'Testcontroleur 02'),
        ], 'task_assignments': [], 'open_tasks': [], 'open_positions': [],
        'summary': {'required': 2, 'assigned': 2, 'open': 0, 'task_open': 0}}
    plan_id = save_plan(db, workspace, revision, result, 'TESTADMIN')
    publish_plan(db, plan_id, revision, 'TESTADMIN')
    return db, a, b, plan_id


def request(db, a, b):
    return request_swap(db, 'DEMO001', 'DEMO002', a, 'V101', b, 'D201')


def test_request_is_private_and_requires_colleague_approval(tmp_path):
    db, a, b, plan = db_with_published_plan(tmp_path)
    rid = request(db, a, b)
    assert [r['id'] for r in list_swap_requests(db, 'DEMO001')] == [rid]
    assert [r['id'] for r in list_swap_requests(db, 'DEMO002')] == [rid]
    assert list_swap_requests(db, 'DEMO003') == []
    with pytest.raises(ValueError):
        decide_swap(db, rid, 'TESTADMIN', True, validator=lambda *_: None)
    with pytest.raises(ValueError):
        respond_swap(db, rid, 'DEMO001', True)
    with pytest.raises(ValueError):
        respond_swap(db, rid, 'DEMO003', True)
    with pytest.raises(ValueError, match='in behandeling'):
        request(db, a, b)
    assert load_plan(db, a.year, a.month, published_only=True)['id'] == plan


def test_colleague_reject_and_initiator_withdraw(tmp_path):
    db, a, b, _ = db_with_published_plan(tmp_path)
    rid = request(db, a, b)
    respond_swap(db, rid, 'DEMO002', False)
    assert list_swap_requests(db, 'DEMO001')[0]['status'] == 'declined'
    with pytest.raises(ValueError):
        respond_swap(db, rid, 'DEMO002', True)
    second = request(db, a, b)
    respond_swap(db, second, 'DEMO001', False)
    assert list_swap_requests(db, 'DEMO002')[0]['status'] == 'withdrawn'


def test_approve_publishes_new_version_without_overwriting_old(tmp_path):
    db, a, b, original_id = db_with_published_plan(tmp_path)
    rid = request(db, a, b)
    respond_swap(db, rid, 'DEMO002', True)
    called = []
    result = decide_swap(db, rid, 'PLANNER', True, validator=lambda data, new, old: called.append((data, new, old)))
    assert called and result['status'] == 'approved'
    published = load_plan(db, a.year, a.month, published_only=True)
    assert published['id'] == result['new_plan_id'] != original_id
    by_code = {r['Dienstnummer']: r['Personeelsnr'] for r in published['payload']['assignments']}
    assert by_code == {'V101': 'DEMO002', 'D201': 'DEMO001'}
    assert load_workspace(db)[1] == 2  # oude concepten zijn niet meer publiceerbaar
    with pytest.raises(ValueError):
        decide_swap(db, rid, 'PLANNER', True, validator=lambda *_: None)
    with pytest.raises(ValueError):
        request(db, a, b)  # de oorspronkelijke dienst behoort nu aan de ander


def test_validator_failure_is_atomic(tmp_path):
    db, a, b, old_id = db_with_published_plan(tmp_path)
    rid = request(db, a, b)
    respond_swap(db, rid, 'DEMO002', True)
    def broken(*_):
        raise ValueError('Harde rustregel geschonden')
    with pytest.raises(ValueError, match='rustregel'):
        decide_swap(db, rid, 'TESTADMIN', True, validator=broken)
    assert load_plan(db, a.year, a.month, published_only=True)['id'] == old_id
    assert list_swap_requests(db, 'DEMO001')[0]['status'] == 'accepted'


def test_stale_plan_and_workspace_reject(tmp_path):
    db, a, b, old_id = db_with_published_plan(tmp_path)
    rid = request(db, a, b)
    respond_swap(db, rid, 'DEMO002', True)
    state, version = load_workspace(db)
    state['settings']['max_consecutive'] = 4
    save_workspace(db, state, version, 'TESTADMIN', 'Test wijziging')
    with pytest.raises(ConflictError):
        decide_swap(db, rid, 'TESTADMIN', True, validator=lambda *_: None)
    assert load_plan(db, a.year, a.month, published_only=True)['id'] == old_id


def test_wrong_target_and_tasks_are_protected(tmp_path):
    db, a, b, _ = db_with_published_plan(tmp_path)
    with pytest.raises(ValueError):
        request_swap(db, 'DEMO001', 'DEMO002', a, 'V101', b, 'N401')
    plan = load_plan(db, a.year, a.month, True)['payload']
    protected = deepcopy(plan)
    protected['task_assignments'] = [{
        'Datum': a.isoformat(), 'Dienstnummer': 'V101', 'Personeelsnr': 'DEMO001'}]
    with pytest.raises(ValueError, match='taken'):
        make_swap_plan(protected, 'DEMO001', 'DEMO002', a.isoformat(), 'V101', b.isoformat(), 'D201')


def test_no_unauthorised_request(tmp_path):
    db, a, b, _ = db_with_published_plan(tmp_path)
    with pytest.raises(ValueError):
        request_swap(db, 'TESTADMIN', 'DEMO002', a, 'V101', b, 'D201')
    with pytest.raises(ValueError):
        request_swap(db, 'DEMO001', 'DEMO001', a, 'V101', b, 'D201')
