"""Regressie v0.13: veilige kopie van uitsluitend de maandbehoefte."""
from copy import deepcopy
from datetime import date
import pytest

from month_copy_v013 import copy_month_demand_rows
from store import (get_engine, initialize, initialize_months, load_month_workspace,
                   create_month_workspace, copy_month_workspace_demand,
                   add_account, save_month_workspace, save_plan, publish_plan,
                   ConflictError)

SHIFTS = [
    {"id": "V101", "required": 2, "active": True},
    {"id": "D201", "required": 3, "active": True},
]


def sample(month=11, year=2026):
    return {"year": year, "month": month,
            "demand": [
                {"date": "2026-11-02", "shift_id": "V101", "required": 1},
                {"date": "2026-11-03", "shift_id": "D201", "required": 2},
                {"date": "2026-11-09", "shift_id": "V101", "required": 1},
                {"date": "2026-11-30", "shift_id": "V101", "required": 1},
            ]}


def make_db(tmp_path):
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path/'v013.sqlite'}")
    initialize(engine, "TESTADMIN", "TestWachtwoordSterkVoorbeeld_2026")
    initialize_months(engine)
    source = (entry := __import__('store').list_month_workspaces(engine)[0])
    source_period = source["year"], source["month"]
    return engine, source_period


def next_month(pair):
    year, month = pair
    return (year + 1, 1) if month == 12 else (year, month + 1)


def test_copy_weekday_positions_and_current_occupancy():
    result = copy_month_demand_rows(sample(), 2026, 12, SHIFTS, "weekday")
    assert result == [
        {"date": "2026-12-01", "shift_id": "D201", "required": 3},
        {"date": "2026-12-07", "shift_id": "V101", "required": 2},
        {"date": "2026-12-14", "shift_id": "V101", "required": 2},
    ]  # 5e maandag november heeft geen overeenkomstige 5e maandag december.


def test_copy_same_calendar_day():
    rows = copy_month_demand_rows(sample(), 2026, 12, SHIFTS, "date")
    assert [r["date"] for r in rows] == ["2026-12-02", "2026-12-03", "2026-12-09", "2026-12-30"]


def test_copy_overflow_day_skips_nonexistent_day():
    src = {"year": 2026, "month": 12, "demand": [
        {"date": "2026-12-30", "shift_id": "V101", "required": 2},
        {"date": "2026-12-31", "shift_id": "D201", "required": 3},
    ]}
    assert copy_month_demand_rows(src, 2027, 2, SHIFTS, "date") == []


def test_rejects_unknown_inactive_and_duplicates():
    src = sample()
    with pytest.raises(ValueError, match="gedeactiveerd"):
        copy_month_demand_rows(src, 2026, 12, [{"id": "D201", "required": 2}], "weekday")
    src["demand"].append(deepcopy(src["demand"][0]))
    with pytest.raises(ValueError, match="Dubbele"):
        copy_month_demand_rows(src, 2026, 12, SHIFTS, "weekday")


def test_create_month_with_copy_keeps_source_unchanged(tmp_path):
    db, src = make_db(tmp_path)
    dst = next_month(src)
    original, rev = load_month_workspace(db, *src)
    create_month_workspace(db, *dst, "TESTADMIN", source_period=src, copy_mode="weekday")
    copied, rev2 = load_month_workspace(db, *dst)
    assert rev2 == 1 and copied["demand"]
    assert copied["preferences"] == []
    assert copied["hour_credits"] == []
    assert copied["task_needs"] == []
    assert all(date.fromisoformat(r["date"]).month == dst[1] for r in copied["demand"])
    assert load_month_workspace(db, *src) == (original, rev)


def test_copy_to_existing_empty_month_is_one_shot(tmp_path):
    db, src = make_db(tmp_path)
    dst = next_month(src)
    create_month_workspace(db, *dst, "TESTADMIN")
    data, rev = load_month_workspace(db, *dst)
    assert not data["demand"]
    next_rev = copy_month_workspace_demand(db, *src, *dst, rev, "TESTADMIN", "weekday")
    assert next_rev == rev + 1
    data2, _ = load_month_workspace(db, *dst)
    assert data2["demand"]
    with pytest.raises(ValueError, match="al dienstbehoefte"):
        copy_month_workspace_demand(db, *src, *dst, next_rev, "TESTADMIN", "weekday")


def test_reject_unauthorized_and_conflicting_copies(tmp_path):
    db, src = make_db(tmp_path)
    dst = next_month(src)
    add_account(db, "TESTK001", "Controleur", "controleur", "TestWachtwoordControleur2026!!", "TESTADMIN")
    with pytest.raises(ValueError, match="Alleen"):
        create_month_workspace(db, *dst, "TESTK001", source_period=src)
    create_month_workspace(db, *dst, "TESTADMIN")
    _, rev = load_month_workspace(db, *dst)
    with pytest.raises(ValueError, match="Alleen"):
        copy_month_workspace_demand(db, *src, *dst, rev, "TESTK001")
    with pytest.raises(ConflictError, match="veranderd"):
        copy_month_workspace_demand(db, *src, *dst, rev + 1, "TESTADMIN")


def test_published_destination_cannot_copy_even_if_empty(tmp_path):
    db, src = make_db(tmp_path)
    dst = next_month(src)
    create_month_workspace(db, *dst, "TESTADMIN")
    payload, rev = load_month_workspace(db, *dst)
    pid = save_plan(db, payload, rev, {"status": "FEASIBLE", "assignments": [], "open_positions": []}, "TESTADMIN")
    publish_plan(db, pid, rev, "TESTADMIN")
    with pytest.raises(ValueError, match="gepubliceerd"):
        copy_month_workspace_demand(db, *src, *dst, rev, "TESTADMIN")


def test_extra_fifth_weekday_repeats_last_source_weekday():
    src = {"year": 2026, "month": 11, "demand": [
        {"date": "2026-11-24", "shift_id": "V101", "required": 2},  # 4e dinsdag
    ]}
    out = copy_month_demand_rows(src, 2026, 12, SHIFTS, "weekday")
    assert [r["date"] for r in out] == ["2026-12-22", "2026-12-29"]
