"""Nieuwe profiel-/dienstenregels van v0.3 zonder externe solver."""
from datetime import date, datetime

import pytest

from catalog import (is_unavailable, is_unavailable_during, new_employee, profile, shift_details,
                     sync_required, validate_employee, validate_periods, validate_shift)
from demo_data import build_demo
from store import add_account, get_engine, initialize, load_workspace, save_workspace


def test_old_profiles_get_read_only_defaults():
    employee = build_demo(2026, 11)["employees"][0]
    before = dict(employee)
    extended = profile(employee)
    assert extended["team"] == "Demoteam"
    assert extended["blocked_periods"] == []
    assert employee == before  # Oude PostgreSQL-record wordt niet ongemerkt gewijzigd.
    shift = build_demo(2026, 11)["shifts"][0]
    expanded = shift_details(shift)
    assert expanded["start_location"] == "Demo Gent"
    assert expanded["end_location"] == "Demo Gent"


def test_date_block_restricts_only_inclusive_interval():
    employee = new_employee("DEMO999", "Test 999", "Demoteam", 80, 140)
    employee["blocked_periods"] = [{"start": "2026-11-10", "end": "2026-11-15"}]
    assert not is_unavailable(employee, date(2026, 11, 9))
    assert is_unavailable(employee, date(2026, 11, 10))
    assert is_unavailable(employee, date(2026, 11, 15))
    assert not is_unavailable(employee, date(2026, 11, 16))
    assert validate_employee(employee, {"V101"}) == []


def test_bad_and_overlapping_periods_rejected():
    assert validate_periods([{"start": "2026-12-01", "end": "2026-11-30"}])
    assert validate_periods([{"start": "2026-11-02", "end": "2026-11-04"},
                             {"start": "2026-11-04", "end": "2026-11-06"}])
    assert validate_periods([{"start": "not a date", "end": "2026-11-06"}])


def test_shift_validation_and_requirement_sync():
    state = build_demo(2026, 11)
    shift = shift_details(state["shifts"][0])
    shift["required"] = 3
    shift["start_location"] = "Demo start"
    shift["end_location"] = "Demo einde"
    assert validate_shift(shift) == []
    shift["end"] = "25:30"
    assert validate_shift(shift)
    shift["end"] = "14:00"
    state["shifts"][0] = shift
    sync_required(state, shift["id"], 3)
    assert all(r["required"] == 3 for r in state["demand"] if r["shift_id"] == shift["id"])
    assert all(r["required"] == 1 for r in state["demand"] if r["shift_id"] == "V102")


def test_old_workspace_and_account_preserved_on_version_upgrade(tmp_path):
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path / 'safe_upgrade.db'}")
    initialize(engine, "TESTADMIN", "zeer-sterk-testwachtwoord-123")
    original, revision = load_workspace(engine)
    original["employees"][0]["team"] = "Testteam Zuid"
    original["employees"][0]["blocked_periods"] = [{"start":"2026-11-07", "end":"2026-11-08"}]
    original["shifts"][0]["start_location"] = "Demo A"
    original["shifts"][0]["end_location"] = "Demo B"
    new_revision = save_workspace(engine, original, revision, "TESTADMIN", "v0.3 bijwerking")
    assert new_revision == revision + 1
    updated, rev2 = load_workspace(engine)
    assert updated["employees"][0]["team"] == "Testteam Zuid"
    assert updated["shifts"][0]["start_location"] == "Demo A"
    assert len(updated["employees"]) == 16
    assert rev2 == new_revision


def test_night_shift_touches_blocked_next_day():
    employee = new_employee("DEMO999", "Test 999", "Demoteam", 100, 176)
    employee["blocked_periods"] = [{"start": "2026-11-11", "end": "2026-11-11"}]
    assert is_unavailable_during(employee, datetime(2026, 11, 10, 22), datetime(2026, 11, 11, 6))
    assert not is_unavailable_during(employee, datetime(2026, 11, 10, 14), datetime(2026, 11, 11, 0))
