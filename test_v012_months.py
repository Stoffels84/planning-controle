"""v0.12 regressie: meerdere kalendermanden zonder wederzijds overschrijven."""
from copy import deepcopy
from datetime import date
import pytest
from demo_data import build_demo
from store import (get_engine, initialize, initialize_months, list_month_workspaces,
                   load_month_workspace, save_month_workspace, create_month_workspace,
                   add_account, request_leave, decide_leave_request, save_plan,
                   publish_plan, load_plan, ConflictError)


def setup(tmp_path):
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path/'multi.sqlite'}")
    initialize(engine, "TESTADMIN", "TestSterkWachtwoordVoorbeeld2026!")
    add_account(engine, "DEMO001", "Testpersoon", "controleur", "SterkWachtwoordControleur0001!", "TESTADMIN")
    initialize_months(engine)
    return engine


def original(db):
    entry = list_month_workspaces(db)[0]
    return entry['year'], entry['month']


def next_period(y,m):
    return (y+1,1) if m==12 else (y,m+1)


def test_migrates_legacy_no_loss_and_new_month_is_empty(tmp_path):
    db=setup(tmp_path)
    original_y, original_m = original(db)
    november, rev=load_month_workspace(db, original_y,original_m)
    assert rev==1 and len(november['demand'])>0
    y2,m2=next_period(original_y,original_m)
    create_month_workspace(db,y2,m2,'TESTADMIN')
    december, revision=load_month_workspace(db,y2,m2)
    assert revision==1 and december['year']==y2 and december['month']==m2
    assert december['demand']==[] and december['preferences']==[]
    assert december['hour_credits']==[] and december['task_needs']==[]
    assert december['employees']==november['employees']
    assert december['shifts']==november['shifts']
    original_again, oldrev=load_month_workspace(db,original_y,original_m)
    assert oldrev==1 and original_again==november
    assert len(list_month_workspaces(db))==2


def test_independent_preferences_and_demand(tmp_path):
    db=setup(tmp_path)
    y,m=original(db)
    y2,m2=next_period(y,m)
    create_month_workspace(db,y2,m2,'TESTADMIN')
    first,rev=load_month_workspace(db,y,m)
    other,rev2=load_month_workspace(db,y2,m2)
    other['preferences']=[{'employee_id':'DEMO001','date':date(y2,m2,3).isoformat(),'priority':3}]
    other['demand']=[{'date':date(y2,m2,2).isoformat(),'shift_id':'V101','required':2}]
    save_month_workspace(db,other,rev2,'TESTADMIN','Test maandwijziging')
    again,oldrev=load_month_workspace(db,y,m)
    assert oldrev==rev and again['demand']==first['demand'] and again['preferences']==first['preferences']
    december,_=load_month_workspace(db,y2,m2)
    assert december['preferences']==other['preferences'] and december['demand']==other['demand']


def test_global_employee_catalog_updates_all_months_and_rejects_old_revision(tmp_path):
    db=setup(tmp_path)
    y,m=original(db)
    y2,m2=next_period(y,m)
    create_month_workspace(db,y2,m2,'TESTADMIN')
    source,rev=load_month_workspace(db,y,m)
    other,rev2=load_month_workspace(db,y2,m2)
    source['employees'][0]['name']='Nieuwe testnaam'
    save_month_workspace(db,source,rev,'TESTADMIN','Naam aangepast')
    after,updated_rev=load_month_workspace(db,y2,m2)
    assert after['employees'][0]['name']=='Nieuwe testnaam'
    assert updated_rev==rev2+1
    with pytest.raises(ConflictError):
        save_month_workspace(db,other,rev2,'TESTADMIN','stale')


def test_published_first_month_survives_preparing_and_publishing_next(tmp_path):
    db=setup(tmp_path)
    y,m=original(db)
    a,rev=load_month_workspace(db,y,m)
    result={'status':'FEASIBLE','assignments':[], 'open_positions':[],
            'summary':{'required':0,'assigned':0,'open':0}}
    old_id=save_plan(db,a,rev,result,'TESTADMIN')
    publish_plan(db,old_id,rev,'TESTADMIN')
    y2,m2=next_period(y,m)
    create_month_workspace(db,y2,m2,'TESTADMIN')
    b, rev2=load_month_workspace(db,y2,m2)
    b['demand']=[{'date':date(y2,m2,3).isoformat(),'shift_id':'V101','required':2}]
    rev2=save_month_workspace(db,b,rev2,'TESTADMIN','Invoer volgende maand')
    b,_=load_month_workspace(db,y2,m2)
    new_id=save_plan(db,b,rev2,result,'TESTADMIN')
    publish_plan(db,new_id,rev2,'TESTADMIN')
    assert old_id!=new_id
    assert load_plan(db,y,m,True)['id']==old_id
    assert load_plan(db,y2,m2,True)['id']==new_id
    assert load_month_workspace(db,y,m)[0]['demand']==a['demand']


def test_leave_approval_scoped_to_correct_month(tmp_path):
    db=setup(tmp_path)
    y,m=original(db)
    y2,m2=next_period(y,m)
    create_month_workspace(db,y2,m2,'TESTADMIN')
    rid=request_leave(db,'DEMO001',date(y2,m2,4),date(y2,m2,4))
    decide_leave_request(db,rid,'TESTADMIN',True,7.6)
    second,_=load_month_workspace(db,y2,m2)
    first,_=load_month_workspace(db,y,m)
    assert any(c['date']==date(y2,m2,4).isoformat() for c in second['hour_credits'])
    assert not any(c['date']==date(y2,m2,4).isoformat() for c in first.get('hour_credits',[]))


def test_only_planners_can_create_months(tmp_path):
    db=setup(tmp_path)
    y,m=original(db)
    y2,m2=next_period(y,m)
    with pytest.raises(ValueError):
        create_month_workspace(db,y2,m2,'DEMO001')
    create_month_workspace(db,y2,m2,'TESTADMIN')
    with pytest.raises(ValueError):
        create_month_workspace(db,y2,m2,'TESTADMIN')
