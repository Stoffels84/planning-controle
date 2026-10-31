"""Database-integratie voor de eerste aanvraagworkflow. FICTIEVE data."""
from datetime import date
from pathlib import Path

import pytest

from demo_data import build_demo
from requests_v010 import leave_days, absence_credit
from store import (get_engine, initialize, add_account, request_leave,
                   list_leave_requests, withdraw_leave_request,
                   decide_leave_request, load_workspace, save_workspace,
                   save_plan, publish_plan, load_plan, ConflictError)


def db_with_users(tmp_path: Path):
    db = get_engine(f"sqlite+pysqlite:///{tmp_path / 'requests.sqlite'}")
    initialize(db, "TESTADMIN", "VoorbeeldSterkWachtwoord2026!")
    add_account(db, "DEMO001", "Fictieve controleur 1", "controleur", "VoorbeeldSterkWachtwoord0001!", "TESTADMIN")
    add_account(db, "DEMO002", "Fictieve controleur 2", "controleur", "VoorbeeldSterkWachtwoord0002!", "TESTADMIN")
    add_account(db, "TESTPLANNER", "Fictieve planner", "planner", "VoorbeeldSterkWachtwoord0003!", "TESTADMIN")
    return db


def in_month(db, day=4):
    w, _ = load_workspace(db)
    return date(w['year'], w['month'], day)


def test_controller_can_submit_and_only_see_own_requests(tmp_path):
    db = db_with_users(tmp_path)
    day = in_month(db)
    req_id = request_leave(db, 'DEMO001', day, day)
    own = list_leave_requests(db, 'DEMO001')
    assert len(own) == 1 and own[0]['id'] == req_id and own[0]['status'] == 'pending'
    assert list_leave_requests(db, 'DEMO002') == []
    assert len(list_leave_requests(db, 'TESTPLANNER')) == 1
    assert len(list_leave_requests(db, 'TESTADMIN')) == 1
    with pytest.raises(ValueError):
        request_leave(db, 'TESTADMIN', day, day)
    with pytest.raises(ValueError):
        withdraw_leave_request(db, req_id, 'DEMO002')
    with pytest.raises(ValueError):
        decide_leave_request(db, req_id, 'DEMO001', True)
    # Een aanvraag blokkeert nog niets voordat goedkeuring verleend is.
    payload, rev = load_workspace(db)
    assert rev == 1
    assert not any(r['employee_id'] == 'DEMO001' and r['date'] == day.isoformat()
                   for r in payload.get('hour_credits', []))


def test_approve_adds_blocking_credit_atomically(tmp_path):
    db = db_with_users(tmp_path)
    start, end = in_month(db, 5), in_month(db, 7)
    req_id = request_leave(db, 'DEMO001', start, end)
    result = decide_leave_request(db, req_id, 'TESTPLANNER', True, 7.6)
    assert result['status'] == 'approved'
    payload, revision = load_workspace(db)
    assert revision == 2
    credits = [r for r in payload['hour_credits'] if r['employee_id'] == 'DEMO001']
    assert len(credits) == 3
    assert {r['date'] for r in credits} == {in_month(db, d).isoformat() for d in (5,6,7)}
    assert all(r['type'] == 'Verlof' and r['hours'] == 7.6 for r in credits)
    with pytest.raises(ValueError):
        decide_leave_request(db, req_id, 'TESTADMIN', True, 0)
    with pytest.raises(ValueError):
        withdraw_leave_request(db, req_id, 'DEMO001')
    # Een gewone werkruimte-update mag een goedgekeurde verlofdag niet wissen.
    changed = dict(payload)
    changed['hour_credits'] = []
    with pytest.raises(ValueError, match='goedgekeurde verlofdag'):
        save_workspace(db, changed, revision, 'TESTADMIN', 'Onterecht verwijderen')
    after, rev_after = load_workspace(db)
    assert after == payload and rev_after == revision


def test_reject_and_withdraw_never_change_workspace(tmp_path):
    db = db_with_users(tmp_path)
    day = in_month(db)
    request_id = request_leave(db, 'DEMO001', day, day)
    withdraw_leave_request(db, request_id, 'DEMO001')
    with pytest.raises(ValueError):
        withdraw_leave_request(db, request_id, 'DEMO001')
    other = request_leave(db, 'DEMO001', day, day)
    decide_leave_request(db, other, 'TESTADMIN', False)
    assert list_leave_requests(db, 'DEMO001')[0]['status'] == 'rejected'
    w, rev = load_workspace(db)
    assert rev == 1 and not w.get('hour_credits')


def test_duplicate_and_existing_activity_rejected(tmp_path):
    db = db_with_users(tmp_path)
    a, b = in_month(db, 10), in_month(db, 12)
    request_leave(db, 'DEMO001', a, b)
    with pytest.raises(ValueError, match='openstaande'):
        request_leave(db, 'DEMO001', b, b)
    # Een gelijktijdige registratie die na aanvraag gebeurt, mag niet overschreven worden.
    payload, revision = load_workspace(db)
    payload['hour_credits'] = [absence_credit('DEMO001', a, 7.6)]
    save_workspace(db, payload, revision, 'TESTADMIN', 'Activiteit reeds aanwezig')
    pending = list_leave_requests(db, 'DEMO001')[0]
    with pytest.raises(ValueError, match='activiteit'):
        decide_leave_request(db, pending['id'], 'TESTADMIN', True, 8)
    assert list_leave_requests(db, 'DEMO001')[0]['status'] == 'pending'
    _, next_rev = load_workspace(db)
    assert next_rev == revision+1


def test_wrong_month_and_invalid_hours(tmp_path):
    db = db_with_users(tmp_path)
    day = in_month(db, 15)
    with pytest.raises(ValueError):
        request_leave(db, 'DEMO001', date(2035, 1, 1), date(2035, 1, 2))
    with pytest.raises(ValueError):
        request_leave(db, 'DEMO001', in_month(db,16), day)
    req_id = request_leave(db, 'DEMO001', day, day)
    with pytest.raises(ValueError):
        decide_leave_request(db, req_id, 'TESTADMIN', True, 17.0)
    assert list_leave_requests(db, 'DEMO001')[0]['status'] == 'pending'


def test_approved_leave_keeps_published_plan_unchanged(tmp_path):
    db = db_with_users(tmp_path)
    state, revision = load_workspace(db)
    result = {'status': 'FEASIBLE', 'assignments': [], 'open_positions': [],
              'summary': {'required': 0, 'assigned': 0, 'open': 0}}
    plan_id = save_plan(db, state, revision, result, 'TESTADMIN')
    publish_plan(db, plan_id, revision, 'TESTADMIN')
    req_id = request_leave(db, 'DEMO001', in_month(db, 5), in_month(db, 5))
    decide_leave_request(db, req_id, 'TESTADMIN', True, 0)
    published = load_plan(db, state['year'], state['month'], published_only=True)
    assert published['id'] == plan_id and published['revision'] == revision
    new_state, new_revision = load_workspace(db)
    assert new_revision == revision + 1
    assert new_state['hour_credits'][0]['type'] == 'Verlof'
    with pytest.raises(ConflictError):
        publish_plan(db, plan_id, new_revision, 'TESTADMIN')
