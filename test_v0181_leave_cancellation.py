"""Regressie v0.18.1 — intrekking reeds goedgekeurd verlof, uitsluitend fictieve data."""
from datetime import date
from copy import deepcopy

import pytest

from requests_v010 import absence_credit
from store import (
    get_engine, initialize, initialize_months, add_account, session_factory,
    LeaveRequest, LeaveCancellation, AuditEvent, request_leave,
    decide_leave_request, list_leave_requests, load_workspace,
    save_workspace, load_month_workspace, list_month_workspaces,
    create_month_workspace, save_plan, publish_plan, load_plan,
    notifications_for, list_leave_cancellations, request_leave_cancellation,
    decide_leave_cancellation, revoke_approved_leave, ConflictError,
)


def setup_db(tmp_path, migrate=True):
    db = get_engine(f"sqlite+pysqlite:///{tmp_path/'cancel.sqlite'}")
    initialize(db, "ROOT", "FictiefWachtwoordVoorTestomgeving2026!")
    add_account(db, "DEMO001", "Fictieve controleur", "controleur", "TestwachtwoordControleur0012026!", "ROOT")
    add_account(db, "DEMO002", "Andere controleur", "controleur", "TestwachtwoordControleur0022026!", "ROOT")
    add_account(db, "PLANNER", "Fictieve planner", "planner", "TestwachtwoordPlanner2026!", "ROOT")
    if migrate:
        initialize_months(db)
        p = list_month_workspaces(db)[0]
        y, m = p['year'], p['month']
        load = lambda: load_month_workspace(db, y, m)
    else:
        state, _ = load_workspace(db)
        y, m = state['year'], state['month']
        load = lambda: load_workspace(db)
    return db, y, m, load


def approved(db, y, m, first=5, last=7, hours=7.6):
    rid = request_leave(db, "DEMO001", date(y, m, first), date(y, m, last))
    decide_leave_request(db, rid, "ROOT", True, hours)
    return rid


def test_pending_cancel_preserves_approved_leave_and_credits(tmp_path):
    db, y, m, load = setup_db(tmp_path)
    rid = approved(db, y, m)
    state, revision = load()
    cid = request_leave_cancellation(db, rid, "DEMO001", "Mijn verlof is niet meer nodig")
    assert isinstance(cid, int)
    assert list_leave_requests(db, 'DEMO001')[0]['status'] == 'approved'
    assert load() == (state, revision)
    assert list_leave_cancellations(db, 'DEMO001')[0]['status'] == 'pending'
    assert list_leave_cancellations(db, 'DEMO002') == []
    assert list_leave_cancellations(db, 'ROOT')[0]['id'] == cid
    assert any('intrek' in n['title'].lower() or 'intrek' in n['body'].lower() for n in notifications_for(db, 'ROOT'))
    assert notifications_for(db, 'DEMO002') == []


def test_approval_removes_exact_credits_increases_revision_and_keeps_audit(tmp_path):
    db, y, m, load = setup_db(tmp_path)
    rid = approved(db, y, m)
    original, old_revision = load()
    assert len(original['hour_credits']) == 3
    cid = request_leave_cancellation(db, rid, 'DEMO001', 'Mijn vakantie vervalt')
    result = decide_leave_cancellation(db, cid, 'PLANNER', True)
    assert result['status'] == 'approved' and result['workspace_revision'] == old_revision+1
    current, rev = load()
    assert rev == old_revision+1 and current['hour_credits'] == []
    assert list_leave_requests(db, 'DEMO001')[0]['status'] == 'cancelled'
    assert list_leave_cancellations(db, 'DEMO001')[0]['decided_by'] == 'PLANNER'
    with session_factory(db)() as s:
        original_row = s.get(LeaveRequest, rid)
        assert original_row.decided_by == 'ROOT'
        assert original_row.hours_per_day == 7.6
        assert original_row.decided_at is not None
        assert s.get(LeaveCancellation, cid).status == 'approved'
        events = [e.action for e in s.query(AuditEvent).all()]
        assert any('ingetrokken' in e for e in events)
    assert any('goedgekeurd' in n['body'] for n in notifications_for(db, 'DEMO001'))


def test_rejection_does_not_remove_leave_and_employee_can_resubmit(tmp_path):
    db, y, m, load = setup_db(tmp_path)
    rid = approved(db, y, m)
    state, rev = load()
    cid = request_leave_cancellation(db, rid, 'DEMO001', 'Mijn verlof vervalt')
    assert decide_leave_cancellation(db, cid, 'ROOT', False)['status'] == 'rejected'
    assert load() == (state, rev)
    assert list_leave_requests(db, 'DEMO001')[0]['status'] == 'approved'
    cid2 = request_leave_cancellation(db, rid, 'DEMO001', 'Een nieuw verzoek')
    assert cid2 != cid
    assert any('afgewezen' in n['body'] for n in notifications_for(db, 'DEMO001'))


def test_authorization_idempotence_and_duplicate_rejection(tmp_path):
    db, y, m, load = setup_db(tmp_path)
    rid = approved(db, y, m)
    for actor in ('DEMO002', 'ROOT', 'PLANNER'):
        with pytest.raises(ValueError):
            request_leave_cancellation(db, rid, actor, 'Verlof mag weg')
    with pytest.raises(ValueError):
        request_leave_cancellation(db, rid, 'DEMO001', '   ')
    cid = request_leave_cancellation(db, rid, 'DEMO001', 'Verlof mag weg')
    with pytest.raises(ValueError):
        request_leave_cancellation(db, rid, 'DEMO001', 'Tweede verzoek')
    with pytest.raises(ValueError):
        decide_leave_cancellation(db, cid, 'DEMO001', True)
    with pytest.raises(ValueError):
        decide_leave_cancellation(db, cid+9000, 'ROOT', True)
    decide_leave_cancellation(db, cid, 'ROOT', True)
    with pytest.raises(ValueError):
        decide_leave_cancellation(db, cid, 'ROOT', True)
    with pytest.raises(ValueError):
        revoke_approved_leave(db, rid, 'ROOT', 'Nogmaals intrekken')
    with pytest.raises(ValueError):
        request_leave_cancellation(db, rid, 'DEMO001', 'Nogmaals intrekken')


def test_manual_manager_cancellation_requires_reason_and_notifies_owner(tmp_path):
    db, y, m, load = setup_db(tmp_path)
    rid = approved(db, y, m)
    with pytest.raises(ValueError):
        revoke_approved_leave(db, rid, 'DEMO001', 'Vraagt zelf')
    with pytest.raises(ValueError):
        revoke_approved_leave(db, rid, 'ROOT', 'a')
    result = revoke_approved_leave(db, rid, 'PLANNER', 'Controleur meldde dit telefonisch')
    assert result['status'] == 'approved'
    assert load()[0]['hour_credits'] == []
    rows = list_leave_cancellations(db, 'DEMO001')
    assert len(rows) == 1 and rows[0]['requested_by'] == 'PLANNER'
    assert rows[0]['reason'] == 'Controleur meldde dit telefonisch'
    assert rows[0]['decided_by'] == 'PLANNER'
    assert any('door de beheerder ingetrokken' in n['body'] for n in notifications_for(db, 'DEMO001'))


def test_direct_cancellation_of_pending_request_does_not_duplicate(tmp_path):
    db, y, m, load = setup_db(tmp_path)
    rid = approved(db, y, m)
    cid = request_leave_cancellation(db, rid, 'DEMO001', 'Verlof vervalt')
    result = revoke_approved_leave(db, rid, 'ROOT', 'Verzoek ontvangen, onmiddellijk verwerken')
    assert result['id'] == cid
    assert len(list_leave_cancellations(db, 'ROOT')) == 1


def test_other_activities_and_other_approved_leave_are_untouched(tmp_path):
    db, y, m, load = setup_db(tmp_path)
    rid = approved(db, y, m, first=5, last=5)
    other_leave = request_leave(db, 'DEMO001', date(y, m, 8), date(y, m, 8))
    decide_leave_request(db, other_leave, 'ROOT', True, 8)
    state, rev = load()
    state['hour_credits'].append({'employee_id': 'DEMO002', 'date':date(y,m,15).isoformat(),
                                  'type':'Verlof', 'hours':8.0})
    from store import save_month_workspace
    save_month_workspace(db, state, rev, 'ROOT', 'Andere activiteit')
    revoke_approved_leave(db, rid, 'ROOT', 'Eerste dag vervalt')
    current, _ = load()
    assert len(current['hour_credits']) == 2
    assert any(c['employee_id'] == 'DEMO002' for c in current['hour_credits'])
    assert any(c['date'] == date(y,m,8).isoformat() for c in current['hour_credits'])
    assert list_leave_requests(db, 'DEMO001')[0]['status'] == 'approved'


def test_published_plan_unchanged_but_old_draft_is_stale(tmp_path):
    db, y, m, load = setup_db(tmp_path)
    rid = approved(db, y, m, 5, 5)
    state, revision = load()
    result = {"status": "FEASIBLE", "summary": {"open": 0},
              "assignments": [], "open_positions": []}
    plan_id = save_plan(db, state, revision, result, 'ROOT')
    publish_plan(db, plan_id, revision, 'ROOT')
    revoke_approved_leave(db, rid, 'ROOT', 'Verlof niet meer nodig')
    unchanged = load_plan(db, y, m, published_only=True)
    assert unchanged['id'] == plan_id and unchanged['revision'] == revision
    assert load()[1] == revision+1
    with pytest.raises(ConflictError):
        publish_plan(db, plan_id, revision+1, 'ROOT')


def test_corrupt_credit_rejected_atomically(tmp_path):
    db, y, m, load = setup_db(tmp_path)
    rid = approved(db, y, m, 5, 5)
    cid = request_leave_cancellation(db, rid, 'DEMO001', 'Verlof niet meer nodig')
    # Simuleer inconsistente oudere database, buiten de beschermde editor om.
    from store import MonthWorkspace
    with session_factory(db).begin() as s:
        from months_v012 import period_key
        w = s.get(MonthWorkspace, period_key(y, m))
        data = deepcopy(w.payload)
        data['hour_credits'] = []
        w.payload = data
    with pytest.raises(ValueError, match='verlofregistratie'):
        decide_leave_cancellation(db, cid, 'ROOT', True)
    assert list_leave_requests(db, 'DEMO001')[0]['status'] == 'approved'
    assert list_leave_cancellations(db, 'DEMO001')[0]['status'] == 'pending'


def test_legacy_workspace_compatibility(tmp_path):
    db, y, m, load = setup_db(tmp_path, migrate=False)
    rid = approved(db, y, m)
    before_rev = load()[1]
    revoke_approved_leave(db, rid, 'ROOT', 'Verlof vervalt')
    assert load()[0]['hour_credits'] == []
    assert load()[1] == before_rev+1


def test_cross_month_cancellation_only_changes_target_month(tmp_path):
    db, y, m, load = setup_db(tmp_path)
    y2, m2 = (y+1, 1) if m == 12 else (y, m+1)
    create_month_workspace(db, y2, m2, 'ROOT')
    rid = request_leave(db, 'DEMO001', date(y2, m2, 3), date(y2, m2, 3))
    decide_leave_request(db, rid, 'ROOT', True, 7.6)
    first, firstrev = load()
    second, secondrev = load_month_workspace(db, y2, m2)
    revoke_approved_leave(db, rid, 'ROOT', 'Verlof niet meer nodig')
    assert load() == (first, firstrev)
    assert load_month_workspace(db, y2, m2)[0]['hour_credits'] == []
    assert load_month_workspace(db, y2, m2)[1] == secondrev+1


def test_statuses_are_available_for_portal(tmp_path):
    from requests_v010 import STATUS_LABELS
    from portal_v017 import LEAVE_STATUS, personal_request_feed
    assert STATUS_LABELS['cancelled'].startswith('Goedgekeurd')
    assert LEAVE_STATUS['cancelled'].startswith('Goedgekeurd')
    feed = personal_request_feed([{'employee_id':'DEMO001','id':2,'status':'cancelled',
                                   'start_date':'2030-01-02','end_date':'2030-01-02'}], [], 'DEMO001')
    assert 'ingetrokken' in feed['items'][0]['Status']
