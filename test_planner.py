"""Vereist `pip install -r requirements.txt`."""
from datetime import datetime

from demo_data import build_demo
from planner import get_slot_bounds, minutes_between, solve_month, validate_dataset


def test_overnight_shift_duration():
    assert minutes_between("22:00", "06:00") == 480
    start, end = get_slot_bounds("2026-11-10", {"start": "22:00", "end": "06:00"})
    assert end.date().isoformat() == "2026-11-11"
    assert end > start


def test_demo_is_valid():
    assert validate_dataset(build_demo(2026, 11)) == []


def test_partial_schedule_does_not_break_constraints():
    demo = build_demo(2026, 11)
    demo["employees"] = demo["employees"][:1]  # Bewust te weinig personeel
    demo["demand"] = demo["demand"][:3]
    demo["preferences"] = []
    demo["settings"]["time_limit_seconds"] = 5
    result = solve_month(demo)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.summary["required"] == result.summary["assigned"] + result.summary["open"]
    assert result.summary["open"] > 0
    assert len({(x["Datum"], x["Personeelsnr"]) for x in result.assignments}) == len(result.assignments)
