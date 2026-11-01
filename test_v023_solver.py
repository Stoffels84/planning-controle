"""CP-SAT-tests: alleen als ortools aanwezig is."""
import pytest
pytest.importorskip('ortools')
from demo_data import build_demo
from planner import solve_month


def scenario():
    d = build_demo(2026, 11)
    d['employees'] = [e for e in d['employees'] if e['id'] in ('DEMO001', 'DEMO002', 'DEMO003')]
    for e in d['employees']:
        e['blocked_categories'] = []
        e['blocked_weekdays'] = []
        e['blocked_shifts'] = []
        e['max_month_hours'] = 176
    d['shifts'] = [s for s in d['shifts'] if s['id'] == 'V101']
    d['shifts'][0]['required'] = 1  # Zelfde vaste bezetting als in de testmaandbehoefte.
    d['demand'] = [{'date': '2026-11-03', 'shift_id': 'V101', 'required': 1}]
    d['preferences'] = []
    d['settings']['time_limit_seconds'] = 5
    return d


def row(eid):
    return {'Datum': '2026-11-03', 'Dienstnummer': 'V101', 'Personeelsnr': eid}


def test_exclusion_forbids_old_person_but_can_fill_with_another():
    plan = solve_month(scenario(), excluded_assignments=[row('DEMO001')])
    assert plan.status in ('FEASIBLE', 'OPTIMAL')
    assert not any(r['Personeelsnr'] == 'DEMO001' for r in plan.assignments)
    assert plan.summary['assigned'] == 1


def test_replacement_preserves_locked_candidate_and_forbids_old():
    plan = solve_month(scenario(), locked_assignments=[row('DEMO002')],
                       excluded_assignments=[row('DEMO001')])
    assert plan.status in ('FEASIBLE', 'OPTIMAL')
    assert plan.assignments[0]['Personeelsnr'] == 'DEMO002'


def test_conflicting_lock_exclusion_refused():
    with pytest.raises(ValueError, match='tegelijk vastgezet'):
        solve_month(scenario(), locked_assignments=[row('DEMO001')],
                    excluded_assignments=[row('DEMO001')])


def test_fixed_plan_cannot_combine_with_exclusion():
    with pytest.raises(ValueError, match='niet worden gecombineerd'):
        solve_month(scenario(), fixed_plan={'assignments': [], 'task_assignments': []},
                    excluded_assignments=[row('DEMO001')])
