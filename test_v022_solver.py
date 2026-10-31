"""CP-SAT-integratietests. Worden overgeslagen zolang OR-Tools niet is geïnstalleerd."""
import pytest
pytest.importorskip('ortools')

from demo_data import build_demo
from planner import solve_month


def scenario():
    data = build_demo(2026, 11)
    data['employees'] = [e for e in data['employees'] if e['id'] in ('DEMO001', 'DEMO002', 'DEMO003')]
    for e in data['employees']:
        e['blocked_categories'] = []
        e['blocked_weekdays'] = []
        e['blocked_shifts'] = []
        e['max_month_hours'] = 176
    data['shifts'] = [s for s in data['shifts'] if s['id'] in ('V101', 'D201')]
    data['shifts'][0]['required'] = 1
    data['shifts'][1]['required'] = 1
    data['demand'] = [{'date': '2026-11-03', 'shift_id': 'V101', 'required': 1},
                      {'date': '2026-11-04', 'shift_id': 'D201', 'required': 1}]
    data['preferences'] = []
    data['settings']['time_limit_seconds'] = 5
    return data


def lock(day, sid, eid):
    return {'Datum': day, 'Dienstnummer': sid, 'Personeelsnr': eid}


def test_partial_lock_is_hard_and_other_day_is_free_to_assign():
    d = scenario()
    locks = [lock('2026-11-03', 'V101', 'DEMO001')]
    plan = solve_month(d, locked_assignments=locks)
    assert plan.status in ('OPTIMAL', 'FEASIBLE')
    assert any(all(row.get(k) == v for k, v in locks[0].items()) for row in plan.assignments)
    assert plan.summary['assigned'] == 2


def test_ineligible_fixed_person_refused():
    d = scenario()
    d['employees'][0]['blocked_shifts'] = ['V101']
    with pytest.raises(ValueError, match='niet inzetbaar'):
        solve_month(d, locked_assignments=[lock('2026-11-03', 'V101', 'DEMO001')])


def test_swap_full_lock_still_does_not_allow_partial_lock():
    d = scenario()
    with pytest.raises(ValueError, match='niet worden gecombineerd'):
        solve_month(d, fixed_plan={'assignments': [], 'task_assignments': []},
                    locked_assignments=[])


def test_conflicting_locks_keep_result_infeasible():
    d = scenario()
    # Dezelfde persoon twee opeenvolgende dagen kan bij extra rustregels niet.
    d['settings']['min_rest_hours'] = 40
    result = solve_month(d, locked_assignments=[lock('2026-11-03', 'V101', 'DEMO001'),
                                              lock('2026-11-04', 'D201', 'DEMO001')])
    assert result.status not in ('OPTIMAL', 'FEASIBLE')
