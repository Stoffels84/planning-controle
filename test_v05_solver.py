"""Integration tests running only when OR-Tools is installed."""
import pytest
pytest.importorskip("ortools")

from demo_data import build_demo
from planner import solve_month, validate_dataset


def mini():
    data = build_demo(2026, 11)
    data["employees"] = [data["employees"][0]]
    data["employees"][0].update(blocked_weekdays=[], blocked_categories=[],
                                max_month_hours=200, target_month_hours=0,
                                blocked_periods=[], blocked_shifts=[])
    data["settings"].update(min_rest_hours=0, max_consecutive=7,
                            preference_weight=10, fairness_weight=0, hours_weight=0, time_limit_seconds=5)
    data["shifts"] = [{"id": "D1", "name": "Demo", "category": "Dag", "start": "08:00", "end": "16:00", "required": 1}]
    data["demand"] = [{"date": "2026-11-10", "shift_id": "D1", "required": 1}]
    data["preferences"] = []
    return data


def test_fixed_rest_day_is_hard():
    d = mini()
    assert solve_month(d).summary["assigned"] == 1
    d["employees"][0].update(rest_mode="fixed", fixed_rest_dates=["2026-11-10"])
    assert solve_month(d).summary["assigned"] == 0


def test_credited_day_blocks_assignment():
    d = mini()
    d["hour_credits"] = [{"employee_id": d["employees"][0]["id"], "date": "2026-11-10", "type": "Verlof", "hours": 7.6}]
    assert validate_dataset(d) == []
    assert solve_month(d).summary["assigned"] == 0


def test_desired_workday_prefers_the_correct_day():
    d = mini()
    d["demand"].append({"date": "2026-11-11", "shift_id": "D1", "required": 1})
    d["employees"][0]["max_month_hours"] = 8
    d["preferences"] = [{"employee_id": d["employees"][0]["id"], "type": "work_day", "date": "2026-11-11", "priority": 3}]
    result = solve_month(d)
    assert result.summary["assigned"] == 1
    assert result.assignments[0]["Datum"] == "2026-11-11"
