"""v0.29: CP-SAT hard constraint (uitvoering via GitHub Actions)."""
import pytest
pytest.importorskip('ortools')
from planner import solve_month
from validator_v025 import verify_plan
from test_v029_rest_distribution import month, boundary


def test_solver_forces_two_free_days_each_seven():
    data = month()
    data['settings']['time_limit_seconds'] = 20
    result = solve_month(data)
    assert result.status in ('OPTIMAL','FEASIBLE')
    assert result.summary['assigned'] == 5
    assert verify_plan(data, vars(result))['passed']


def test_solver_respects_previous_published_days():
    data=month()
    data['demand']=[{'date':'2026-11-01','shift_id':'D201','required':1}]
    data['_boundary_assignments']=[boundary(f'2026-10-{i:02d}','previous') for i in range(27,32)]
    data['_boundary_sources']={'previous':31,'next':None}
    result=solve_month(data)
    assert result.summary['assigned']==0
    assert verify_plan(data,vars(result),data['_boundary_assignments'])['passed']


def test_solver_respects_next_published_days():
    data=month()
    data['demand']=[{'date':'2026-11-30','shift_id':'D201','required':1}]
    data['_boundary_assignments']=[boundary(f'2026-12-{i:02d}','next') for i in range(1,6)]
    data['_boundary_sources']={'previous':None,'next':32}
    result=solve_month(data)
    assert result.summary['assigned']==0
    assert verify_plan(data,vars(result),data['_boundary_assignments'])['passed']
