"""Gerichte CP-SAT-planningstests: worden live uitgevoerd waar OR-Tools geïnstalleerd is."""
from datetime import datetime

import pytest
pytest.importorskip("ortools")

from demo_data import build_demo
from planner import solve_month


def case(shifts, days):
    d = build_demo(2026, 11)
    d["employees"] = [d["employees"][0]]
    d["employees"][0].update({"blocked_categories": [], "blocked_weekdays": [],
                               "blocked_periods": [], "max_consecutive": None,
                               "max_month_hours": 200, "target_month_hours": 0,
                               "blocked_transitions": [], "max_category_run": {}})
    d["shifts"] = shifts
    d["demand"] = [{"date": day, "shift_id": sid, "required": 1} for day, sid in days]
    d["preferences"] = []
    d["settings"].update({"min_rest_hours": 0, "max_consecutive": 7,
                          "fairness_weight": 0, "preference_weight": 0,
                          "hours_weight": 0, "time_limit_seconds": 5})
    return d


def shift(sid, cat, begin, end):
    return {"id": sid, "name": sid, "category": cat, "start": begin, "end": end,
            "required": 1, "active": True, "location": "Demo"}


def test_individual_minimum_rest_reduces_assignments():
    d = case([shift("L301", "Laat", "16:00", "23:00"),
              shift("V101", "Vroeg", "05:00", "13:00")],
             [("2026-11-10", "L301"), ("2026-11-11", "V101")])
    assert solve_month(d).summary["assigned"] == 2  # basisrust = 0 (alleen test)
    d["employees"][0]["min_rest_hours"] = 11
    assert solve_month(d).summary["assigned"] == 1


def test_transition_minimum_rest_reduces_assignments():
    d = case([shift("L301", "Laat", "16:00", "23:00"),
              shift("V101", "Vroeg", "05:00", "13:00")],
             [("2026-11-10", "L301"), ("2026-11-11", "V101")])
    d["settings"]["transition_rest_hours"] = {"Laat>Vroeg": 10}
    assert solve_month(d).summary["assigned"] == 1


def test_global_and_personal_max_run():
    d = case([shift("N401", "Nacht", "21:00", "23:00")],
             [("2026-11-10", "N401"), ("2026-11-11", "N401"),
              ("2026-11-12", "N401")])
    assert solve_month(d).summary["assigned"] == 3
    d["settings"]["max_category_run"] = {"Nacht": 2}
    assert solve_month(d).summary["assigned"] == 2
    d["employees"][0]["max_category_run"] = {"Nacht": 1}
    assert solve_month(d).summary["assigned"] == 2  # Dag 10 en 12 mogen; 11 niet


def test_forbidden_transition_is_hard_rule():
    d = case([shift("D201", "Dag", "08:00", "12:00"),
              shift("L301", "Laat", "15:00", "19:00")],
             [("2026-11-10", "D201"), ("2026-11-11", "L301")])
    assert solve_month(d).summary["assigned"] == 2
    d["settings"]["blocked_transitions"] = ["Dag>Laat"]
    assert solve_month(d).summary["assigned"] == 1
