from datetime import date

from demo_data import build_demo, next_month


def test_demo_generated_for_selected_month():
    demo = build_demo(2026, 11)
    assert len(demo["employees"]) == 16
    assert len(demo["demand"]) > 50
    assert all(r["date"].startswith("2026-11") for r in demo["demand"])
    assert {r["shift_id"] for r in demo["demand"]}.issubset({s["id"] for s in demo["shifts"]})


def test_next_month_rollover():
    assert next_month(date(2026, 12, 5)) == (2027, 1)
