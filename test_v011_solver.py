"""Integraal CP-SAT-verificatiepad: draait alleen als OR-Tools geïnstalleerd is."""
import pytest

pytest.importorskip('ortools')

from demo_data import build_demo
from planner import solve_month, validate_dataset
from swap_v011 import make_swap_plan, verify_swap_with_solver


def scenario():
    d = build_demo(2026, 11)
    d['employees'] = [e for e in d['employees'] if e['id'] in ('DEMO001', 'DEMO002')]
    for e in d['employees']:
        e['blocked_categories'] = []
        e['blocked_weekdays'] = []
        e['blocked_shifts'] = []
        e['max_month_hours'] = 160
    for shift in d['shifts']:
        if shift['id'] in ('V101', 'D201'):
            shift['required'] = 1
    d['demand'] = [{'date':'2026-11-03','shift_id':'V101','required':1},
                   {'date':'2026-11-06','shift_id':'D201','required':1}]
    d['preferences'] = []
    d['settings']['time_limit_seconds'] = 5
    return d


def row(day, shift, employee, name):
    return {'Datum':day, 'Dienstnummer':shift, 'Soort':'Reguliere dienst',
            'Personeelsnr': employee, 'Controleur':name, 'Categorie':'Dag',
            'Begin':'09:00', 'Einde':'17:00', 'Uren': 8}


def test_original_and_swap_both_solver_feasible():
    d = scenario()
    assert validate_dataset(d) == []
    result = {'status':'FEASIBLE', 'assignments':[
        row('2026-11-03','V101','DEMO001','Testcontroleur 01'),
        row('2026-11-06','D201','DEMO002','Testcontroleur 02')],
        'task_assignments':[], 'summary':{'open':0,'task_open':0}}
    new = make_swap_plan(result, 'DEMO001', 'DEMO002',
                         '2026-11-03','V101','2026-11-06','D201')
    verify_swap_with_solver(d, new, result)


def test_swap_blocked_by_eligibility():
    d = scenario()
    d['employees'][1]['blocked_shifts'] = ['V101']
    result = {'status':'FEASIBLE', 'assignments':[
        row('2026-11-03','V101','DEMO001','Testcontroleur 01'),
        row('2026-11-06','D201','DEMO002','Testcontroleur 02')],
        'task_assignments':[], 'summary':{'open':0,'task_open':0}}
    new = make_swap_plan(result, 'DEMO001', 'DEMO002',
                         '2026-11-03','V101','2026-11-06','D201')
    with pytest.raises(ValueError):
        verify_swap_with_solver(d, new, result)
