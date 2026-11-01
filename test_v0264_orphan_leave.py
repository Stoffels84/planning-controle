"""v0.26.4 - regressies voor administratief herstel van fictief verweesd verlof."""
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

from activities_v0261 import invalid_activities
from months_v012 import period_key
from store import (
    Account, AuditEvent, ConflictError, LeaveCancellation, LeaveCancellationSelection,
    LeaveRequest, MonthWorkspace, SharedCatalog, add_account,
    archive_orphaned_approved_leave, decide_leave_request,
    get_engine, initialize, initialize_months, list_leave_requests,
    list_month_workspaces, list_orphaned_approved_leave, load_month_workspace,
    request_leave, request_leave_cancellation, session_factory,
)


def setup(tmp_path):
    db = get_engine(f"sqlite+pysqlite:///{tmp_path / 'orphan.sqlite'}")
    initialize(db, 'ROOT', 'VeiligFictiefTestWachtwoord2026!')
    initialize_months(db)
    item = list_month_workspaces(db)[0]
    year, month = item['year'], item['month']
    add_account(db, 'DEMO001', 'Fictief account', 'controleur',
                'TestAccountWachtwoord2026!', 'ROOT')
    rid = request_leave(db, 'DEMO001', date(year,month,20), date(year,month,27))
    decide_leave_request(db, rid, 'ROOT', True, 0)
    return db, year, month, rid


def orphan(db):
    with session_factory(db).begin() as s:
        row = s.get(SharedCatalog, 1)
        shared = deepcopy(row.payload)
        shared['employees'] = [item for item in shared['employees'] if item['id'] != 'DEMO001']
        row.payload = shared


def test_only_approved_missing_employee_is_listed(tmp_path):
    db, y, m, rid = setup(tmp_path)
    assert list_orphaned_approved_leave(db, 'ROOT', y, m) == []
    orphan(db)
    records = list_orphaned_approved_leave(db, 'ROOT', y, m)
    assert len(records) == 1
    assert records[0]['id'] == rid and records[0]['employee_id'] == 'DEMO001'
    assert len(records[0]['remaining_dates']) == 8
    assert records[0]['account_active'] is True


def test_admin_can_archive_orphan_without_losing_leave_history(tmp_path):
    db, y, m, rid = setup(tmp_path)
    orphan(db)
    state, revision = load_month_workspace(db, y, m)
    assert len(invalid_activities(state)) == 8
    marker = {'employee_id':'DEMO002', 'date':date(y,m,2).isoformat(),
              'type':'Andere', 'hours':4}
    with session_factory(db).begin() as s:
        row = s.get(MonthWorkspace, period_key(y,m))
        data = deepcopy(row.payload)
        data['hour_credits'].append(marker)
        row.payload = data
    result = archive_orphaned_approved_leave(
        db, rid, 'ROOT', 'Fictieve verwijderde medewerker, testverlof opruimen', revision)
    assert result == revision + 1
    cleaned, updated_rev = load_month_workspace(db, y, m)
    assert updated_rev == result
    assert cleaned['hour_credits'] == [marker]
    assert not invalid_activities(cleaned)
    with session_factory(db)() as s:
        leave = s.get(LeaveRequest, rid)
        assert leave.status == 'cancelled'
        assert leave.decided_by == 'ROOT' and leave.decided_at is not None
        cancel = s.query(LeaveCancellation).filter_by(leave_request_id=rid).one()
        assert cancel.status == 'approved' and 'Administratieve correctie' in cancel.reason
        selection = s.get(LeaveCancellationSelection, cancel.id)
        assert len(selection.days) == 8
        assert any('Administratieve annulering' in r.action for r in s.query(AuditEvent).all())


def test_normal_employee_cannot_be_archived(tmp_path):
    db, y, m, rid = setup(tmp_path)
    state, rev = load_month_workspace(db,y,m)
    with pytest.raises(ValueError, match='bestaat nog'):
        archive_orphaned_approved_leave(db,rid,'ROOT','Dit is geen verweesd verlof',rev)
    assert load_month_workspace(db,y,m) == (state,rev)


def test_permissions_reason_revision_replay(tmp_path):
    db, y, m, rid = setup(tmp_path)
    orphan(db)
    state, rev = load_month_workspace(db,y,m)
    with pytest.raises(ValueError, match='Alleen beheerders'):
        list_orphaned_approved_leave(db,'DEMO001',y,m)
    with pytest.raises(ValueError, match='Alleen beheerders'):
        archive_orphaned_approved_leave(db,rid,'DEMO001','Fictieve administratieve cleanup',rev)
    with pytest.raises(ValueError, match='reden'):
        archive_orphaned_approved_leave(db,rid,'ROOT','nee',rev)
    with pytest.raises(ValueError, match='maximaal'):
        archive_orphaned_approved_leave(db,rid,'ROOT','x'*301,rev)
    with pytest.raises(ConflictError):
        archive_orphaned_approved_leave(db,rid,'ROOT','Fictieve administratieve cleanup',rev+1)
    assert load_month_workspace(db,y,m) == (state,rev)
    archive_orphaned_approved_leave(db,rid,'ROOT','Fictieve administratieve cleanup',rev)
    with pytest.raises(ValueError, match='niet meer'):
        archive_orphaned_approved_leave(db,rid,'ROOT','Nogmaals hetzelfde proberen',rev+1)


def test_pending_cancel_is_not_bypassed(tmp_path):
    db,y,m,rid=setup(tmp_path)
    request_leave_cancellation(db,rid,'DEMO001','Deze vakantie vervalt')
    orphan(db)
    row=list_orphaned_approved_leave(db,'ROOT',y,m)[0]
    assert row['pending_cancellation']
    _,rev=load_month_workspace(db,y,m)
    with pytest.raises(ValueError,match='al een intrekkingsverzoek'):
        archive_orphaned_approved_leave(db,rid,'ROOT','Fictieve administratieve cleanup',rev)


def test_inconsistent_missing_credit_rolls_back(tmp_path):
    db,y,m,rid=setup(tmp_path)
    orphan(db)
    with session_factory(db).begin() as s:
        w=s.get(MonthWorkspace,period_key(y,m))
        payload=deepcopy(w.payload)
        payload['hour_credits']=payload['hour_credits'][1:]
        w.payload=payload
    state,rev=load_month_workspace(db,y,m)
    with pytest.raises(ValueError,match='gewijzigd'):
        archive_orphaned_approved_leave(db,rid,'ROOT','Fictieve administratieve cleanup',rev)
    assert load_month_workspace(db,y,m)==(state,rev)
    assert list_leave_requests(db,'ROOT')[0]['status']=='approved'


def test_ui_exposes_separate_safe_action():
    app=(Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf8')
    assert 'list_orphaned_approved_leave(' in app
    assert 'archive_orphaned_approved_leave(' in app
    assert 'ik heb gecontroleerd dat' in app.lower()


def test_published_roster_remains_unchanged(tmp_path):
    from datetime import datetime, timezone
    from store import PlanningVersion
    db,y,m,rid=setup(tmp_path)
    orphan(db)
    _,rev=load_month_workspace(db,y,m)
    original={'assignments':[{'Datum':date(y,m,20).isoformat(),
                              'Personeelsnr':'DEMO002','Dienstnummer':'V101'}],
              'unfilled':[]}
    with session_factory(db).begin() as s:
        pub=PlanningVersion(workspace_revision=rev,year=y,month=m,author='ROOT',
                            created_at=datetime.now(timezone.utc),
                            published_at=datetime.now(timezone.utc),
                            payload=deepcopy(original))
        s.add(pub)
        s.flush()
        pub_id=pub.id
    archive_orphaned_approved_leave(db,rid,'ROOT','Fictieve verweesde testgegevens corrigeren',rev)
    with session_factory(db)() as s:
        published=s.get(PlanningVersion,pub_id)
        assert published.payload==original
        assert published.published_at is not None
        assert published.workspace_revision==rev
