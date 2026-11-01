"""v0.26.3: atomic transfer of a wrongly stored ordinary credit."""
from copy import deepcopy
from datetime import date

import pytest

from activity_move_v0263 import activity_destination, validate_movable_activity
from months_v012 import period_key
from store import (
    Account, ConflictError, MonthWorkspace, SharedCatalog, add_account,
    create_month_workspace, get_engine, initialize, initialize_months,
    list_month_workspaces, load_month_workspace, move_activity_to_correct_month,
    request_leave, decide_leave_request, session_factory,
)


def setup(tmp_path):
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path/'transfer.sqlite'}")
    initialize(engine, 'ROOT', 'FictieveVeiligeWachtwoord2026!')
    initialize_months(engine)
    src = list_month_workspaces(engine)[0]
    y, m = src['year'], src['month']
    key = y * 12 + m
    next_month = (key // 12, key % 12 + 1)
    create_month_workspace(engine, *next_month, 'ROOT')
    return engine, (y, m), next_month


def inject(db, month, activity):
    with session_factory(db).begin() as s:
        row = s.get(MonthWorkspace, period_key(*month))
        state = deepcopy(row.payload)
        state['hour_credits'] = list(state.get('hour_credits', [])) + [activity]
        row.payload = state


def ordinary(month, emp='DEMO001', kind='Andere'):
    return {'employee_id': emp, 'date': date(*month, 6).isoformat(),
            'type': kind, 'hours': 4}


def revision(db, month):
    return load_month_workspace(db, *month)[1]


def transfer(db, source, item_index=0, target=None, actor='ROOT', src_revision=None,
             dst_revision=None):
    if target is None:
        raise AssertionError('target needed')
    return move_activity_to_correct_month(db, *source, item_index,
        revision(db, source) if src_revision is None else src_revision,
        revision(db, target) if dst_revision is None else dst_revision, actor)


def test_relocates_correct_day_atomic_and_keeps_rest(tmp_path):
    db, first, second = setup(tmp_path)
    item = ordinary(second)
    valid = ordinary(first, 'DEMO002')
    inject(db, first, valid)
    inject(db, first, item)
    first_before, rev = load_month_workspace(db, *first)
    second_before, rev_dst = load_month_workspace(db, *second)
    result = transfer(db, first, item_index=len(first_before['hour_credits'])-1, target=second)
    assert result == (rev+1, rev_dst+1)
    source, _ = load_month_workspace(db, *first)
    target, _ = load_month_workspace(db, *second)
    assert source['hour_credits'] == [valid]
    assert target['hour_credits'] == second_before['hour_credits'] + [item]
    assert source['shifts'] == first_before['shifts']
    assert target['shifts'] == second_before['shifts']


def test_does_not_create_destination_month_or_lose_source(tmp_path):
    db, first, second = setup(tmp_path)
    missing = (first[0]+1, first[1])
    item = ordinary(missing)
    inject(db, first, item)
    with pytest.raises(ValueError, match='doelmaand'):
        transfer(db, first, target=second)
    assert load_month_workspace(db, *first)[0]['hour_credits'] == [item]


def test_duplicate_activity_in_destination_blocks_atomic(tmp_path):
    db, first, second = setup(tmp_path)
    item = ordinary(second)
    inject(db, first, item)
    inject(db, second, item)
    r1 = revision(db, first)
    r2 = revision(db, second)
    with pytest.raises(ValueError, match='al een activiteit'):
        transfer(db, first, target=second)
    assert revision(db, first) == r1 and revision(db, second) == r2
    assert load_month_workspace(db, *first)[0]['hour_credits'] == [item]


def test_leave_and_sickness_cannot_be_moved(tmp_path):
    db, first, second = setup(tmp_path)
    for kind in ('Verlof', 'Ziekte', 'Feestdag'):
        bad = ordinary(second, kind=kind)
        with pytest.raises(ValueError, match='Afwezigheden'):
            validate_movable_activity(bad, {'DEMO001'}, *first)
    inject(db, first, ordinary(second, kind='Verlof'))
    with pytest.raises(ValueError, match='Afwezigheden'):
        transfer(db, first, target=second)


def test_bad_employee_or_date_rejected(tmp_path):
    db, first, second = setup(tmp_path)
    for item in (ordinary(second, emp='VERDWENEN'),
                 dict(ordinary(second), date='geen datum'),
                 ordinary(first)):
        with pytest.raises(ValueError):
            validate_movable_activity(item, {'DEMO001'}, *first)
    assert activity_destination(ordinary(second), *first) == second
    assert activity_destination(ordinary(first), *first) is None


def test_permissions_concurrency_and_invalid_index(tmp_path):
    db, first, second = setup(tmp_path)
    inject(db, first, ordinary(second))
    add_account(db, 'DEMO001', 'Fictieve controleur', 'controleur',
                'FictieveVeiligWachtwoord2026!', 'ROOT')
    before_src = revision(db, first)
    before_dst = revision(db, second)
    with pytest.raises(ValueError, match='Alleen beheerders'):
        transfer(db, first, target=second, actor='DEMO001')
    with pytest.raises(ConflictError):
        transfer(db, first, target=second, dst_revision=before_dst + 2)
    with pytest.raises(ConflictError):
        transfer(db, first, target=second, src_revision=before_src + 2)
    for idx in (-1, 3, True):
        with pytest.raises(ValueError):
            transfer(db, first, target=second, item_index=idx)
    assert revision(db, first) == before_src
    assert revision(db, second) == before_dst


def test_approved_leave_in_target_preserved_and_not_moved(tmp_path):
    db, first, second = setup(tmp_path)
    add_account(db, 'DEMO001', 'Fictieve controleur', 'controleur',
                'FictieveVeiligWachtwoord2026!', 'ROOT')
    day = date(*second, 6)
    req = request_leave(db, 'DEMO001', day, day)
    decide_leave_request(db, req, 'ROOT', True, 7.6)
    item = ordinary(second)
    inject(db, first, item)
    before_src = revision(db, first)
    before_dst = revision(db, second)
    with pytest.raises(ValueError, match='al een activiteit'):
        transfer(db, first, target=second)
    assert revision(db, first) == before_src and revision(db, second) == before_dst


def test_new_module_available_for_streamlit():
    from pathlib import Path
    app = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8')
    assert 'move_activity_to_correct_month(' in app
    assert 'activity_move_v0263 import' in app
