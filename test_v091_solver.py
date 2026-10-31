"""Requires OR-Tools on deployment (optional locally)."""
import pytest
pytest.importorskip("ortools")
from demo_data import build_demo
from planner import solve_month


def test_specific_daily_shift_priority_beats_other_service():
    d = build_demo(2026, 11)
    d["employees"] = [d["employees"][0]]
    d["employees"][0].update(blocked_weekdays=[], blocked_categories=[], max_month_hours=8,
                               target_month_hours=0, blocked_shifts=[], preferred_category="Geen")
    d["shifts"] = [
        {"id": "D1", "name": "Dag 1", "category": "Dag", "start": "08:00", "end": "16:00", "required": 1},
        {"id": "D2", "name": "Dag 2", "category": "Dag", "start": "09:00", "end": "17:00", "required": 1},
    ]
    d["demand"] = [{"date": "2026-11-10", "shift_id": s["id"], "required": 1} for s in d["shifts"]]
    d["preferences"] = [{"employee_id": d["employees"][0]["id"], "type": "daily_shift",
                         "date": "2026-11-10", "shift_id": "D2", "priority": 3}]
    d["settings"].update(min_rest_hours=0, max_consecutive=7, preference_weight=25,
                         fairness_weight=0, time_limit_seconds=5)
    result = solve_month(d)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.summary["assigned"] == 1
    assert result.assignments[0]["Dienstnummer"] == "D2"
