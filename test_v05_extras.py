"""Pure tests for v0.5, without Streamlit or OR-Tools."""
from datetime import datetime

from catalog import new_employee, profile, validate_employee
from demo_data import build_demo
from extras import (preference_description, rest_blocked_during, summarize_hours,
                    validate_extras)


def test_old_profiles_and_workspace_remain_compatible():
    demo = build_demo(2026, 11)
    source = demo["employees"][0].copy()
    p = profile(source)
    assert source == demo["employees"][0]
    assert p["rest_mode"] == "automatic"
    assert p["fixed_rest_dates"] == []
    assert validate_extras(demo) == []
    assert validate_employee(source, {s["id"] for s in demo["shifts"]}) == []


def test_rest_day_config_and_overnight_overlap():
    e = new_employee("DEMO777", "Test", "Demo", 100, 180)
    e.update(rest_mode="mixed", fixed_rest_weekdays=[2], fixed_rest_dates=["2026-11-20"])
    assert validate_employee(e, set()) == []
    # Wednesday 11 Nov 2026, overnight into Thursday.
    assert rest_blocked_during(e, datetime(2026, 11, 10, 22), datetime(2026, 11, 11, 6), [])
    assert not rest_blocked_during(e, datetime(2026, 11, 9, 9), datetime(2026, 11, 9, 17), [])
    assert rest_blocked_during(e, datetime(2026, 11, 19, 22), datetime(2026, 11, 20, 6), [])
    e["rest_mode"] = "automatic"
    assert not rest_blocked_during(e, datetime(2026, 11, 19, 22), datetime(2026, 11, 20, 6), [])


def test_credit_blocks_entire_calendar_day_and_validates():
    demo = build_demo(2026, 11)
    e = profile(demo["employees"][0])
    credit = {"employee_id": e["id"], "date": "2026-11-12", "type": "Verlof", "hours": 7.6}
    demo["hour_credits"] = [credit]
    assert validate_extras(demo) == []
    assert rest_blocked_during(e, datetime(2026, 11, 11, 22), datetime(2026, 11, 12, 6), [credit])
    assert rest_blocked_during(e, datetime(2026, 11, 12, 10), datetime(2026, 11, 12, 18), [credit])
    demo["hour_credits"].append(credit)
    assert any("Dubbele activiteit" in error for error in validate_extras(demo))


def test_all_six_preference_types_and_priority():
    demo = build_demo(2026, 11)
    eid = demo["employees"][0]["id"]
    demo["preferences"] = [
        {"employee_id": eid, "type": "free_day", "date": "2026-11-10", "priority": 3},
        {"employee_id": eid, "type": "work_day", "date": "2026-11-11", "priority": 2},
        {"employee_id": eid, "type": "category", "category": "Laat", "direction": "avoid", "priority": 1},
        {"employee_id": eid, "type": "shift", "shift_id": "V101", "direction": "prefer", "priority": 2},
        {"employee_id": eid, "type": "weekly_free", "weekday": 4, "priority": 2},
        {"employee_id": eid, "type": "avoid_transition", "transition": "Laat>Vroeg", "priority": 3},
    ]
    assert validate_extras(demo) == []
    assert all(preference_description(p) for p in demo["preferences"])
    demo["preferences"][0]["priority"] = 10
    assert validate_extras(demo)


def test_hours_are_separated_and_not_legal_balance():
    e = new_employee("DEMO777", "Test", "Demo", 100, 180)
    e["target_month_hours"] = 160
    rows = summarize_hours([e], [{"Personeelsnr": "DEMO777", "Uren": 8.0}],
                           [{"employee_id": "DEMO777", "date": "2026-11-10", "hours": 7.6, "type": "Opleiding"}])
    assert rows[0]["Geplande uren"] == 8
    assert rows[0]["Geregistreerde uren"] == 7.6
    assert rows[0]["Totaal meegeteld"] == 15.6
    assert rows[0]["Afwijking streefuren"] == -144.4
