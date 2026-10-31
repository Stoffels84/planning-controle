"""CP-SAT tests; overgeslagen als OR-Tools lokaal niet beschikbaar is."""
import pytest
pytest.importorskip('ortools')
from copy import deepcopy

from demo_data import build_demo
from planner import solve_month


def scenario(year, month, day, shift_id, boundaries):
    data = build_demo(year, month)
    data['employees'] = [data['employees'][0]]
    emp = data['employees'][0]
    emp['blocked_categories'] = []
    emp['blocked_shifts'] = []
    emp['blocked_weekdays'] = []
    emp['blocked_periods'] = []
    emp['max_month_hours'] = 200
    emp['max_consecutive'] = None
    data['preferences'] = []
    data['hour_credits'] = []
    data['task_needs'] = []
    for sh in data['shifts']:
        if sh['id'] == shift_id:
            sh['required'] = 1
    data['demand'] = [{'date': day, 'shift_id': shift_id, 'required': 1}]
    data['_boundary_assignments'] = [{**r, 'employee_id': emp['id']} for r in boundaries]
    data['settings']['time_limit_seconds'] = 5
    return data


def row(day, cat, start, end, side):
    return {'date': day, 'category': cat, 'start': start, 'end': end, 'source': side}


def test_previous_night_prohibits_early_next_month():
    data = scenario(2026, 12, '2026-12-01', 'V101',
                    [row('2026-11-30', 'Nacht', '22:00', '06:00', 'previous')])
    assert solve_month(data).summary['open'] == 1
    data['_boundary_assignments'] = []
    assert solve_month(data).summary['open'] == 0


def test_next_month_early_blocks_last_day_night():
    data = scenario(2026, 11, '2026-11-30', 'N401',
                    [row('2026-12-01', 'Vroeg', '06:00', '14:00', 'next')])
    assert solve_month(data).summary['open'] == 1


def test_workday_run_crosses_previous_month():
    rows = [row(f'2026-11-{n:02d}', 'Dag', '08:00', '16:00', 'previous')
            for n in range(26, 31)]
    data = scenario(2026, 12, '2026-12-01', 'D201', rows)
    data['settings']['max_consecutive'] = 5
    assert solve_month(data).summary['open'] == 1
    data['settings']['max_consecutive'] = 6
    assert solve_month(data).summary['open'] == 0


def test_category_run_crosses_next_month():
    data = scenario(2026, 11, '2026-11-30', 'V101', [
        row('2026-12-01', 'Vroeg', '06:00', '14:00', 'next'),
        row('2026-12-02', 'Vroeg', '06:00', '14:00', 'next'),
    ])
    data['settings']['max_category_run'] = {'Vroeg': 2}
    assert solve_month(data).summary['open'] == 1
