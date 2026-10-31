"""Wordt uitgevoerd zodra OR-Tools in de omgeving beschikbaar is."""
import pytest
pytest.importorskip('ortools')
from demo_data import build_demo
from planner import solve_month


def tiny_case():
    d = build_demo(2026, 11)
    d['employees'] = d['employees'][:2]
    d['demand'] = [{'date':'2026-11-02','shift_id':'V101','required':2}]
    d['preferences'] = []
    d['settings']['time_limit_seconds'] = 10
    d['tasks'] = [{'id':'T1','name':'Controle-demo','qualification':'Q1','active':True}]
    d['task_needs'] = [{'date':'2026-11-02','shift_id':'V101','task_id':'T1',
                        'start':'08:00','end':'09:00','required':1}]
    return d


def test_qualified_task_assigns_only_qualified_controller():
    d = tiny_case()
    d['employees'][0]['qualifications'] = ['Q1']
    out = solve_month(d)
    assert out.status in ('OPTIMAL','FEASIBLE')
    assert out.summary['task_assigned'] == 1
    assert out.task_assignments[0]['Personeelsnr'] == d['employees'][0]['id']


def test_no_qualification_reports_open_task_not_fake_staffing():
    d = tiny_case()
    out = solve_month(d)
    assert out.summary['task_assigned'] == 0
    assert out.summary['task_open'] == 1
    assert out.summary['required'] == out.summary['assigned'] + out.summary['open']


def test_simultaneous_tasks_cannot_be_doubly_assigned():
    d = tiny_case()
    d['demand'][0]['required'] = 2
    d['employees'][0]['qualifications'] = ['Q1']
    d['tasks'].append({'id':'T2','name':'Tweede taak','qualification':'Q1','active':True})
    d['task_needs'].append({'date':'2026-11-02','shift_id':'V101','task_id':'T2',
                            'start':'08:30','end':'09:30','required':1})
    out = solve_month(d)
    assert out.summary['task_assigned'] == 1
    assert out.summary['task_open'] == 1
