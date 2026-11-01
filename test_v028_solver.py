from test_v028_weekend_rotation import state, history
from validator_v025 import verify_plan
import pytest

pytest.importorskip('ortools')
from planner import solve_month


def test_solver_limits_consecutive_weekends_but_not_alternating_weekends():
    data = state()
    data['settings']['time_limit_seconds'] = 10
    result = solve_month(data)
    # 7 en 21 november zijn niet opeenvolgende weekends.
    assert result.summary['assigned'] == 2
    assert {r['Datum'] for r in result.assignments} == {'2026-11-07','2026-11-21'}
    assert verify_plan(data, vars(result))['passed']


def test_solver_respects_previous_published_weekend_and_shared_weekend():
    data = state()
    data['demand'] = [{'date':d,'shift_id':'D201','required':1}
                      for d in ['2026-11-01','2026-11-07']]
    data['_boundary_assignments'] = [history('2026-10-31')]
    data['settings']['min_rest_hours'] = 0
    # zondag 1/11 valt in het al gewerkte weekend 31/10; za 7/11 niet.
    result = solve_month(data)
    assert result.summary['assigned'] == 1
    assert result.assignments[0]['Datum'] == '2026-11-01'
    assert verify_plan(data, vars(result), data['_boundary_assignments'])['passed']


def test_solver_next_month_boundary_blocked():
    data = state()
    data['demand'] = [{'date':'2026-11-28','shift_id':'D201','required':1}]
    data['_boundary_assignments'] = [history('2026-12-05', 'next')]
    assert solve_month(data).summary['assigned'] == 0
