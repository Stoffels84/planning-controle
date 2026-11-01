"""V0.22 gegevensintegriteit en regressies zonder OR-Tools."""
from pathlib import Path
import ast
import pytest

from demo_data import build_demo
from locks_v022 import assignment_key, validate_locks, reoptimization_diff


def data():
    x = build_demo(2026, 11)
    x['demand'] = [{'date': '2026-11-03', 'shift_id': 'V101', 'required': 2},
                   {'date': '2026-11-04', 'shift_id': 'D201', 'required': 2}]
    return x


def lock(day='2026-11-03', shift='V101', employee='DEMO001'):
    return {'Datum': day, 'Dienstnummer': shift, 'Personeelsnr': employee}


def test_validate_single_lock_normalizes_only_identity_fields():
    d = data()
    actual = validate_locks(d, [dict(lock(), Controleur='Anders', VrijeTekst='niet bewaren')])
    assert actual == [lock()]
    assert assignment_key(actual[0]) == ('2026-11-03', 'V101', 'DEMO001')


def test_validate_locks_sorted_independently_of_input_order():
    d = data()
    assert validate_locks(d, [lock('2026-11-04', 'D201', 'DEMO003'), lock()]) == [lock(), lock('2026-11-04', 'D201', 'DEMO003')]


@pytest.mark.parametrize('rows, error', [
    ([lock(), lock()], 'meermaals'),
    ([lock(), lock('2026-11-03', 'V101', 'DEMO002'), lock('2026-11-03', 'V101', 'DEMO003')], 'meer vaste'),
    ([lock(), lock('2026-11-03', 'D201', 'DEMO001')], 'tweemaal'),
    ([lock('2026-11-05')], 'maandbehoefte'),
    ([lock(employee='EXTRA')], 'niet actief'),
    ([lock(day='2026-10-31')], 'buiten'),
    ([lock(shift='TAAK:ABC')], 'Zelfstandige taken'),
    ([{'Datum': '2026-11-03', 'Dienstnummer': 'V101'}], 'mist'),
])
def test_reject_invalid_locks(rows, error):
    dataset = data()
    if error == 'tweemaal':
        dataset['demand'].append({'date': '2026-11-03', 'shift_id': 'D201', 'required': 2})
    with pytest.raises(ValueError, match=error):
        validate_locks(dataset, rows)


def test_reject_lock_for_inactive_person():
    d = data()
    d['employees'][0]['active'] = False
    with pytest.raises(ValueError, match='niet actief'):
        validate_locks(d, [lock()])


def test_diff_only_compares_regular_assignments():
    previous = [dict(lock(), Soort='Reguliere dienst'),
                dict(lock('2026-11-04','D201','DEMO002'), Soort='Reguliere dienst'),
                {'Datum': '2026-11-04', 'Dienstnummer': 'TAAK:SCAN', 'Personeelsnr': 'DEMO009', 'Soort': 'Zelfstandige taak'}]
    current = [dict(lock(), Soort='Reguliere dienst'),
               dict(lock('2026-11-04','D201','DEMO004'), Soort='Reguliere dienst')]
    result = reoptimization_diff(previous, current, [lock()])
    assert result == {'vastgezet': 1, 'behouden': 1, 'nieuw': 1,
                      'weggevallen': 1, 'alle_vaste_behouden': True}


def test_diff_detects_lost_pin():
    assert not reoptimization_diff([lock()], [], [lock()])['alle_vaste_behouden']


def test_new_editor_integrates_solver_and_publication_without_changing_swap_verification():
    project = Path(__file__).resolve().parents[1]
    ui = (project / 'app.py').read_text(encoding='utf-8')
    solver = (project / 'planner.py').read_text(encoding='utf-8')
    tree = ast.parse(ui)
    ast.parse(solver)
    assert 'locked_assignments=compiled["locked"]' in ui
    assert 'store.save_plan(engine, data, st.session_state.workspace_revision' in ui
    assert '✏️ Handmatige roosterbewerking (v0.23)' in ui
    assert '🔍 Controleer wijzigingen en maak nieuw concept' in ui
    assert 'if fixed_plan is not None:' in solver
    assert 'if locked:' in solver
    assert 'model.add(possible[key] == 1)' in solver
    assert 'model.add(x[idx] == int(key in pinned))' in solver
    assert 'st.rerun()' in ui
