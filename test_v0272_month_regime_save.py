"""v0.27.2: maandregimes zijn geïsoleerde edits, ook bij historische fouten."""
from copy import deepcopy
from datetime import date

import pytest

from demo_data import build_demo
from store import (Account, SharedCatalog, MonthWorkspace, ConflictError,
                   get_engine, initialize, initialize_months, load_month_workspace,
                   list_month_workspaces, session_factory, add_account,
                   save_month_regime_v0272, request_leave, decide_leave_request)
from months_v012 import period_key
from extras import validate_extras


def setup(tmp_path):
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path/'regime_v0272.db'}")
    initialize(engine, 'ROOT', 'LangFictiefTestWachtwoord2026!')
    initialize_months(engine)
    item = list_month_workspaces(engine)[0]
    period = (item['year'], item['month'])
    return engine, period


def corrupt_other_data(engine, period):
    with session_factory(engine).begin() as session:
        record = session.get(MonthWorkspace, period_key(*period))
        payload = deepcopy(record.payload)
        # Oude benodigde bezetting is afwijkend van de vaste catalogus.
        for demand in payload['demand'][:3]:
            demand['required'] = 1 if demand['required'] != 1 else 2
        # Afwijkende activiteit van verwijderde controleur.
        payload.setdefault('hour_credits', []).append({
            'employee_id': 'VERDWENEN',
            'date': date(*period, 8).isoformat(),
            'type': 'Andere', 'hours': 3.0,
        })
        record.payload = payload


def test_regime_can_be_saved_despite_other_invalid_month_data(tmp_path):
    db, period = setup(tmp_path)
    corrupt_other_data(db, period)
    before, rev = load_month_workspace(db, *period)
    assert validate_extras(before)
    with session_factory(db)() as s:
        before_raw = deepcopy(s.get(MonthWorkspace, period_key(*period)).payload)
        shared_before = deepcopy(s.get(SharedCatalog, 1).payload)
    new_rev = save_month_regime_v0272(
        db, *period, rev, 'ROOT', 'DEMO001',
        {'max_month_hours': 160.0, 'target_month_hours': 154.0})
    after, read_rev = load_month_workspace(db, *period)
    assert new_rev == rev + 1 == read_rev
    assert after['month_hour_regimes_v027']['DEMO001']['target_month_hours'] == 154
    assert after['hour_credits'] == before['hour_credits']
    assert after['demand'] == before['demand']
    assert validate_extras(after)  # Historische fouten blijven zichtbaar voor latere validatie.
    with session_factory(db)() as s:
        stored = deepcopy(s.get(MonthWorkspace, period_key(*period)).payload)
        shared = deepcopy(s.get(SharedCatalog, 1).payload)
    assert shared == shared_before
    expected = deepcopy(before_raw)
    expected['month_hour_regimes_v027'] = {'DEMO001': {'max_month_hours': 160.0, 'target_month_hours': 154.0}}
    assert stored == expected  # Geen enkel ander veld mag aangepast zijn.


def test_reset_only_selected_regime_and_preserves_other_values(tmp_path):
    db, period = setup(tmp_path)
    _, rev = load_month_workspace(db, *period)
    rev = save_month_regime_v0272(db, *period, rev, 'ROOT', 'DEMO001',
                                  {'max_month_hours': 150, 'target_month_hours': 80})
    rev = save_month_regime_v0272(db, *period, rev, 'ROOT', 'DEMO002',
                                  {'max_month_hours': 125, 'target_month_hours': 75})
    rev = save_month_regime_v0272(db, *period, rev, 'ROOT', 'DEMO001', None)
    after, current_rev = load_month_workspace(db, *period)
    assert rev == current_rev
    assert after['month_hour_regimes_v027'] == {
        'DEMO002': {'max_month_hours': 125, 'target_month_hours': 75}}


def test_server_rejects_injection_invalid_access_and_stale_revision(tmp_path):
    db, period = setup(tmp_path)
    _, rev = load_month_workspace(db, *period)
    add_account(db, 'DEMO001', 'Testcontroleur', 'controleur',
                'FictiefTestWachtwoord2026!', 'ROOT')
    valid = {'max_month_hours': 160.0, 'target_month_hours': 154.0}
    for account in ('DEMO001', 'ONTBREKEND'):
        with pytest.raises(ValueError, match='Alleen planners en beheerders'):
            save_month_regime_v0272(db, *period, rev, account, 'DEMO001', valid)
    for eid, data in (
        ('VERDWENEN', valid),
        ('DEMO001', {'max_month_hours': 100, 'target_month_hours': 101}),
        ('DEMO001', {'max_month_hours': 100, 'target_month_hours': float('nan')}),
        ('DEMO001', {'max_month_hours': 100, 'target_month_hours': 90, 'extra': 1}),
    ):
        with pytest.raises(ValueError):
            save_month_regime_v0272(db, *period, rev, 'ROOT', eid, data)
    after_fail, check_rev = load_month_workspace(db, *period)
    assert check_rev == rev
    new_rev = save_month_regime_v0272(db, *period, rev, 'ROOT', 'DEMO001', valid)
    with pytest.raises(ConflictError):
        save_month_regime_v0272(db, *period, rev, 'ROOT', 'DEMO001', valid)
    assert new_rev == rev + 1


def test_approved_leave_not_touched_by_regime_save(tmp_path):
    db, period = setup(tmp_path)
    add_account(db, 'DEMO002', 'Testcontroleur', 'controleur',
                'FictiefTestWachtwoord2026!', 'ROOT')
    day = date(*period, 5)
    leave_id = request_leave(db, 'DEMO002', day, day)
    decide_leave_request(db, leave_id, 'ROOT', True, 7.6)
    before, rev = load_month_workspace(db, *period)
    assert any(x['employee_id']=='DEMO002' for x in before['hour_credits'])
    save_month_regime_v0272(db, *period, rev, 'ROOT', 'DEMO001',
                            {'max_month_hours': 160, 'target_month_hours': 152})
    after, _ = load_month_workspace(db, *period)
    assert before['hour_credits'] == after['hour_credits']


def test_ui_uses_isolated_storage_not_generic_replace_data():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / 'app.py').read_text()
    start = source.index('elif screen == "Urenbalans":')
    end = source.index('elif screen == "Weekend en maandgrenzen":', start)
    content = source[start:end]
    assert 'save_month_regime_and_rerun(eid,' in content
    assert 'replace_and_rerun(revised)' not in content
    assert 'store.save_month_regime_v0272(' in source
