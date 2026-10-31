"""v0.20 — gedeeltelijke intrekking met behoud van audit, rechten en maandgrenzen.

Alleen fictieve gegevens, SQLite-testdatabase; geen OR-Tools nodig.
"""
from datetime import date
from copy import deepcopy

import pytest
from sqlalchemy import delete

from store import (
    get_engine, initialize, initialize_months, add_account, session_factory,
    LeaveRequest, LeaveCancellation, LeaveCancellationSelection, request_leave,
    decide_leave_request, list_leave_requests, load_month_workspace,
    list_month_workspaces, save_month_workspace, create_month_workspace,
    save_plan, publish_plan, load_plan, notifications_for,
    list_leave_cancellations, request_leave_cancellation,
    decide_leave_cancellation, revoke_approved_leave, ConflictError,
)


def prepared(tmp_path):
    db = get_engine(f"sqlite+pysqlite:///{tmp_path/'partial_v020.sqlite'}")
    initialize(db, "ROOT", "FictiefWachtwoordVoorTestomgeving2026!")
    add_account(db, "DEMO001", "Controleur 1", "controleur", "TestwachtwoordControleur0012026!", "ROOT")
    add_account(db, "DEMO002", "Controleur 2", "controleur", "TestwachtwoordControleur0022026!", "ROOT")
    add_account(db, "PLANNER", "Fictieve planner", "planner", "TestwachtwoordPlanner2026!", "ROOT")
    initialize_months(db)
    month = list_month_workspaces(db)[0]
    year, m = month['year'], month['month']
    rid = request_leave(db, "DEMO001", date(year, m, 5), date(year, m, 9))
    decide_leave_request(db, rid, "ROOT", True, 7.6)
    return db, year, m, rid


def state(db, y, m):
    return load_month_workspace(db, y, m)


def remaining(db, rid):
    return next(r['remaining_dates'] for r in list_leave_requests(db, "ROOT") if r['id'] == rid)


def test_partial_request_does_not_change_approved_credits_before_decision(tmp_path):
    db, y, m, rid = prepared(tmp_path)
    old = state(db, y, m)
    cid = request_leave_cancellation(db, rid, "DEMO001", "Deze dagen hoef ik niet vrij",
                                     [date(y,m,6), date(y,m,8)])
    assert state(db, y, m) == old
    assert len(remaining(db, rid)) == 5
    selection = list_leave_cancellations(db, "ROOT")[0]
    assert selection['id'] == cid
    assert selection['selected_dates'] == [date(y,m,6).isoformat(), date(y,m,8).isoformat()]
    assert list_leave_cancellations(db, "DEMO002") == []


def test_partial_approval_removes_only_selected_days_and_keeps_leave_approved(tmp_path):
    db, y, m, rid = prepared(tmp_path)
    _, old_rev = state(db, y, m)
    cid = request_leave_cancellation(db, rid, "DEMO001", "Twee dagen annuleren",
                                     [date(y,m,8), date(y,m,6)])
    result = decide_leave_cancellation(db, cid, "PLANNER", True)
    assert result['workspace_revision'] == old_rev+1
    current, rev = state(db, y, m)
    assert rev == old_rev + 1
    assert [x['date'] for x in current['hour_credits']] == [date(y,m,n).isoformat() for n in (5,7,9)]
    assert remaining(db, rid) == [date(y,m,n).isoformat() for n in (5,7,9)]
    assert next(r['status'] for r in list_leave_requests(db, 'ROOT') if r['id'] == rid) == 'approved'
    with session_factory(db)() as s:
        leave = s.get(LeaveRequest, rid)
        assert leave.decided_by == 'ROOT' and leave.hours_per_day == 7.6
        selection = s.get(LeaveCancellationSelection, cid)
        assert selection.days == [date(y,m,6).isoformat(), date(y,m,8).isoformat()]
    assert any('2 dag(en)' in x['body'] for x in notifications_for(db, 'DEMO001'))


def test_multiple_partial_requests_then_full_last_remainder(tmp_path):
    db, y, m, rid = prepared(tmp_path)
    one = request_leave_cancellation(db, rid, 'DEMO001', 'Eerste deel', [date(y,m,6)])
    decide_leave_cancellation(db, one, 'ROOT', True)
    two = request_leave_cancellation(db, rid, 'DEMO001', 'Volgend deel', [date(y,m,8)])
    decide_leave_cancellation(db, two, 'ROOT', True)
    three = request_leave_cancellation(db, rid, 'DEMO001', 'Alle overige dagen')
    assert len(list_leave_cancellations(db, 'DEMO001')[0]['selected_dates']) == 3
    decide_leave_cancellation(db, three, 'ROOT', True)
    assert remaining(db, rid) == []
    assert state(db, y, m)[0]['hour_credits'] == []
    assert next(r['status'] for r in list_leave_requests(db, 'DEMO001') if r['id']==rid) == 'cancelled'
    assert len(list_leave_cancellations(db, 'DEMO001')) == 3


def test_rejection_leaves_all_dates_and_can_resubmit(tmp_path):
    db, y, m, rid = prepared(tmp_path)
    before = state(db,y,m)
    cid = request_leave_cancellation(db, rid, 'DEMO001', 'Dag intrekken', [date(y,m,7)])
    decide_leave_cancellation(db, cid, 'ROOT', False)
    assert state(db,y,m)==before
    assert len(remaining(db,rid))==5
    cid2=request_leave_cancellation(db,rid,'DEMO001','Nieuwe poging',[date(y,m,9)])
    assert cid2!=cid


def test_direct_manager_partial_and_other_employee_credits_preserved(tmp_path):
    db, y, m, rid = prepared(tmp_path)
    old,rev=state(db,y,m)
    old['hour_credits'].append({'employee_id':'DEMO002','date':date(y,m,3).isoformat(),
                                 'type':'Verlof','hours':8.0})
    save_month_workspace(db,old,rev,'ROOT','Onverwante afwezigheid')
    result = revoke_approved_leave(db,rid,'ROOT','Telefonische vraag voor 7 en 9',
                                   [date(y,m,7),date(y,m,9)])
    current,_=state(db,y,m)
    assert result['status']=='approved'
    assert {(c['employee_id'],c['date']) for c in current['hour_credits']} == {
        ('DEMO001',date(y,m,d).isoformat()) for d in (5,6,8)
    } | {('DEMO002',date(y,m,3).isoformat())}
    assert len(list_leave_cancellations(db,'DEMO001')) == 1


def test_protect_only_remaining_approved_days(tmp_path):
    db,y,m,rid=prepared(tmp_path)
    cid=request_leave_cancellation(db,rid,'DEMO001','Annuleer 6 en 7',[date(y,m,6), date(y,m,7)])
    decide_leave_cancellation(db,cid,'ROOT',True)
    current,rev=state(db,y,m)
    altered=deepcopy(current)
    # Oude geannuleerde dag mag als andere toegestane activiteit worden geregistreerd.
    altered['hour_credits'].append({'employee_id':'DEMO001','date':date(y,m,6).isoformat(),
                                     'type':'Verlof','hours':4.0})
    save_month_workspace(db,altered,rev,'ROOT','Andere activiteit nieuwe dag')
    modified,rev2=state(db,y,m)
    modified['hour_credits']=[c for c in modified['hour_credits'] if c['date']!=date(y,m,8).isoformat()]
    with pytest.raises(ValueError,match='goedgekeurde verlofdag'):
        save_month_workspace(db,modified,rev2,'ROOT','Probeer actieve verlofdag te verwijderen')


def test_can_request_new_leave_on_day_previously_cancelled(tmp_path):
    db,y,m,rid=prepared(tmp_path)
    cid=request_leave_cancellation(db,rid,'DEMO001','Een dag intrekken',[date(y,m,6)])
    decide_leave_cancellation(db,cid,'ROOT',True)
    new=request_leave(db,'DEMO001',date(y,m,6),date(y,m,6))
    decide_leave_request(db,new,'ROOT',True,4)
    assert remaining(db,rid) == [date(y,m,d).isoformat() for d in (5,7,8,9)]
    current,_=state(db,y,m)
    assert len(current['hour_credits'])==5
    with pytest.raises(ValueError):
        request_leave(db,'DEMO001',date(y,m,7),date(y,m,7))


def test_invalid_selection_authorization_pending_and_replay(tmp_path):
    db,y,m,rid=prepared(tmp_path)
    cases=([], [date(y,m,4)], [date(y,m,6), date(y,m,6)], ['2026-01-01'])
    for days in cases:
        with pytest.raises(ValueError):
            request_leave_cancellation(db,rid,'DEMO001','Afwijkende selectie', days)
    with pytest.raises(ValueError):
        request_leave_cancellation(db,rid,'DEMO002','Andermans dagen',[date(y,m,6)])
    cid=request_leave_cancellation(db,rid,'DEMO001','Een dag kiezen',[date(y,m,6)])
    with pytest.raises(ValueError):
        request_leave_cancellation(db,rid,'DEMO001','Dubbele aanvraag',[date(y,m,7)])
    with pytest.raises(ValueError):
        decide_leave_cancellation(db,cid,'DEMO001',True)
    with pytest.raises(ValueError,match='wijken af'):
        revoke_approved_leave(db,rid,'ROOT','Selectie is anders',[date(y,m,7)])
    decide_leave_cancellation(db,cid,'ROOT',True)
    with pytest.raises(ValueError):
        decide_leave_cancellation(db,cid,'ROOT',True)
    with pytest.raises(ValueError):
        request_leave_cancellation(db,rid,'DEMO001','Al ingetrokken',[date(y,m,6)])


def test_selection_preserved_on_credit_integrity_failure(tmp_path):
    db,y,m,rid=prepared(tmp_path)
    cid=request_leave_cancellation(db,rid,'DEMO001','Dagen annuleren',[date(y,m,6), date(y,m,8)])
    from store import MonthWorkspace
    from months_v012 import period_key
    with session_factory(db).begin() as s:
        w=s.get(MonthWorkspace,period_key(y,m))
        payload=deepcopy(w.payload)
        payload['hour_credits']=[e for e in payload['hour_credits'] if e['date']!=date(y,m,8).isoformat()]
        w.payload=payload
    before,rev=state(db,y,m)
    with pytest.raises(ValueError,match='verlofregistratie'):
        decide_leave_cancellation(db,cid,'ROOT',True)
    assert state(db,y,m)==(before,rev)
    assert len(remaining(db,rid))==5
    assert list_leave_cancellations(db,'ROOT')[0]['status']=='pending'


def test_published_plan_and_other_month_unchanged(tmp_path):
    db,y,m,rid=prepared(tmp_path)
    y2,m2=(y+1,1) if m==12 else (y,m+1)
    create_month_workspace(db,y2,m2,'ROOT')
    other_before=state(db,y2,m2)
    current,rev=state(db,y,m)
    planid=save_plan(db,current,rev,{'status':'FEASIBLE','summary':{'open':0},'assignments':[],
                                     'open_positions':[]},'ROOT')
    publish_plan(db,planid,rev,'ROOT')
    cid=request_leave_cancellation(db,rid,'DEMO001','Een dag intrekken',[date(y,m,6)])
    decide_leave_cancellation(db,cid,'ROOT',True)
    assert state(db,y2,m2)==other_before
    assert load_plan(db,y,m,published_only=True)['id']==planid
    with pytest.raises(ConflictError):
        publish_plan(db,planid,rev+1,'ROOT')


def test_legacy_pending_cancellation_without_selection_is_full(tmp_path):
    db,y,m,rid=prepared(tmp_path)
    cid=request_leave_cancellation(db,rid,'DEMO001','Verlof helemaal annuleren')
    with session_factory(db).begin() as s:
        s.execute(delete(LeaveCancellationSelection).where(LeaveCancellationSelection.cancellation_id==cid))
    decide_leave_cancellation(db,cid,'ROOT',True)
    assert state(db,y,m)[0]['hour_credits']==[]
    assert remaining(db,rid)==[]


def test_new_table_init_is_idempotent(tmp_path):
    db,y,m,rid=prepared(tmp_path)
    initialize(db)
    initialize(db)
    cid=request_leave_cancellation(db,rid,'DEMO001','Intrekking blijft werken',[date(y,m,6)])
    assert list_leave_cancellations(db,'ROOT')[0]['id']==cid
