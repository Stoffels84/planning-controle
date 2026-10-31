"""Deze tests draaien op de echte Streamlit-server met OR-Tools geïnstalleerd."""
import pytest
pytest.importorskip('ortools')
from demo_data import build_demo
from planner import solve_month


def case():
    d = build_demo(2026, 11)
    d['employees'] = d['employees'][:3]
    d['demand'] = [{'date':'2026-11-02','shift_id':'V101','required':2}]
    d['preferences'] = []
    d['settings']['time_limit_seconds'] = 10
    d['tasks'] = [{'id':'T1','name':'Bijzondere testactie','qualification':'Q1',
                    'category':'Dag','active':True}]
    for e in d['employees']:
        e['qualifications'] = ['Q1']
        e['blocked_categories'] = []
        e['blocked_shifts'] = []
        e['blocked_weekdays'] = []
    return d


def test_release_needs_third_controller_for_full_coverage():
    d = case()
    d['task_needs'] = [{'date':'2026-11-02', 'shift_id':'V101', 'task_id':'T1',
                        'start':'07:00','end':'08:00','required':1,'mode':'released'}]
    out = solve_month(d)
    assert out.status in ('OPTIMAL','FEASIBLE')
    assert out.summary['assigned'] == 2
    assert out.summary['open'] == 0
    assert out.summary['task_assigned'] == 1
    assert out.summary['extra_regular_staffing'] == 1


def test_release_without_replacement_does_not_fake_coverage():
    d = case()
    d['employees'] = d['employees'][:2]
    d['task_needs'] = [{'date':'2026-11-02', 'shift_id':'V101', 'task_id':'T1',
                        'start':'07:00','end':'08:00','required':1,'mode':'released'}]
    out = solve_month(d)
    assert out.status in ('OPTIMAL','FEASIBLE')
    assert out.summary['open'] == 0
    assert out.summary['task_open'] == 1


def test_standalone_day_counts_in_hours_and_blocks_regular_shift():
    d = case()
    d['employees'] = d['employees'][:2]
    d['task_needs'] = [{'date':'2026-11-02','shift_id':None, 'task_id':'T1',
                        'start':'09:00','end':'17:00','required':1,'mode':'standalone'}]
    out = solve_month(d)
    assert out.status in ('OPTIMAL','FEASIBLE')
    assert out.summary['assigned'] == 2
    assert out.summary['task_open'] == 1
    assert sum(a['Uren'] for a in out.assignments) == 16


def test_standalone_without_base_shift_is_assigned():
    d = case()
    d['demand'] = []
    d['task_needs'] = [{'date':'2026-11-02','shift_id':None,'task_id':'T1',
                        'start':'09:00','end':'17:00','required':1,'mode':'standalone'}]
    out = solve_month(d)
    assert out.status in ('OPTIMAL','FEASIBLE')
    assert out.summary['required'] == 0
    assert out.summary['task_assigned'] == 1
    assert out.assignments[0]['Soort'] == 'Zelfstandige taak'
    assert out.assignments[0]['Uren'] == 8


def test_unqualified_staff_cannot_get_standalone():
    d = case()
    d['demand'] = []
    for e in d['employees']:
        e['qualifications'] = []
    d['task_needs'] = [{'date':'2026-11-02','shift_id':None,'task_id':'T1',
                        'start':'09:00','end':'17:00','required':1,'mode':'standalone'}]
    out = solve_month(d)
    assert out.summary['task_assigned'] == 0
    assert out.summary['task_open'] == 1
