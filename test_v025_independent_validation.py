"""Regressietests voor onafhankelijke harde-roostercontrole, zonder OR-Tools."""
from copy import deepcopy

import pytest

from demo_data import build_demo
from validator_v025 import verify_plan


def simple(year=2026, month=11):
    data = build_demo(year, month)
    data["employees"] = [{**data["employees"][0], "blocked_categories": [],
                          "blocked_weekdays": [], "max_month_hours": 176,
                          "max_consecutive": None}]
    data["preferences"] = []
    data["demand"] = [{"date": f"{year}-{month:02d}-02", "shift_id": "D201", "required": 2},
                      {"date": f"{year}-{month:02d}-03", "shift_id": "D201", "required": 2}]
    return data


def assignment(day, code="D201", eid="DEMO001", begin="09:00", end="17:00", cat="Dag"):
    return {"Datum": day, "Dienstnummer": code, "Personeelsnr": eid,
            "Begin": begin, "Einde": end, "Categorie": cat, "Soort": "Reguliere dienst"}


def audit(data, rows, boundaries=None):
    return verify_plan(data, {"status": "FEASIBLE", "assignments": rows}, boundaries)


def test_valid_partial_roster_is_accepted():
    data = simple()
    result = audit(data, [assignment("2026-11-02"), assignment("2026-11-03")])
    assert result["passed"], result["errors"]
    assert result["assignments_checked"] == 2


def test_unknown_duty_and_duplicate_assignment_rejected():
    data = simple()
    rows = [assignment("2026-11-02"), assignment("2026-11-02")]
    assert "dubbele" in str(audit(data, rows)["errors"])
    assert not audit(data, [assignment("2026-11-02", "X")])["passed"]


def test_rest_calendar_absence_and_blocked_category():
    data = simple()
    data["employees"][0]["blocked_periods"] = [{"start": "2026-11-02", "end": "2026-11-02"}]
    assert "onbeschikbaarheid" in str(audit(data, [assignment("2026-11-02")])["errors"])
    data["employees"][0]["blocked_periods"] = []
    data["employees"][0]["blocked_categories"] = ["Dag"]
    assert "verboden categorie" in str(audit(data, [assignment("2026-11-02")])["errors"])
    data["employees"][0]["blocked_categories"] = []
    data["hour_credits"] = [{"employee_id": "DEMO001", "date": "2026-11-02",
                             "type": "Verlof", "hours": 8}]
    assert "afwezigheid" in str(audit(data, [assignment("2026-11-02")])["errors"])


def test_hours_maximum_and_consecutive_days():
    data = simple()
    data["employees"][0]["max_month_hours"] = 8
    assert "maanduren" in str(audit(data, [assignment("2026-11-02"), assignment("2026-11-03")])["errors"])
    data["employees"][0]["max_month_hours"] = 176
    data["employees"][0]["max_consecutive"] = 1
    assert "reeks werkdagen" in str(audit(data, [assignment("2026-11-02"), assignment("2026-11-03")])["errors"])


def test_prohibited_transition_and_rest_across_month():
    data = simple(year=2026, month=12)
    data["demand"] = [{"date": "2026-12-01", "shift_id": "V101", "required": 1}]
    prior = [{"employee_id": "DEMO001", "date": "2026-11-30", "category": "Nacht",
              "start": "22:00", "end": "06:00", "source": "previous"}]
    rows = [assignment("2026-12-01", code="V101", begin="06:00", end="14:00", cat="Vroeg")]
    assert "onvoldoende rust" in str(audit(data, rows, prior)["errors"])
    assert audit(data, rows)["passed"]


def test_max_weekends_and_category():
    data = simple()
    data["demand"] = [{"date": "2026-11-07", "shift_id": "D201", "required": 2},
                      {"date": "2026-11-08", "shift_id": "D201", "required": 2}]
    data["employees"][0]["max_weekend_days"] = 1
    result = audit(data, [assignment("2026-11-07"), assignment("2026-11-08")])
    assert "weekenddagen" in str(result["errors"])
    data["employees"][0]["max_weekend_days"] = None
    data["employees"][0]["max_month_categories"] = {"Dag": 1}
    assert "maximum aantal diensten Dag" in str(audit(data, [assignment("2026-11-07"), assignment("2026-11-08")])["errors"])


def test_v025_database_rechecks_marked_result_and_keeps_legacy(tmp_path):
    from store import get_engine, initialize, initialize_months, list_month_workspaces, load_month_workspace, save_plan, publish_plan
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path / 'validation_v025.sqlite'}")
    initialize(engine, "ROOT", "LangEnSterkTestWachtwoord987!")
    initialize_months(engine)
    first = list_month_workspaces(engine)[0]
    data, rev = load_month_workspace(engine, first["year"], first["month"])
    # De DB mag een onveilige nieuwe v0.25-berekening niet opslaan.
    d = next(r for r in data["demand"] if r["shift_id"] == "D201")
    bad = assignment(d["date"], eid="FOUTIEF")
    marked = {"status": "FEASIBLE", "assignments": [bad], "open_positions": [],
              "summary": {"validation_v025": {"passed": True}}}
    with pytest.raises(ValueError, match="onafhankelijke roostercontrole|Onafhankelijke roostercontrole"):
        save_plan(engine, data, rev, marked, "ROOT")
    # Historische niet-gemarkeerde plannen blijven bruikbaar zoals in v0.24.
    legacy = {"status": "FEASIBLE", "assignments": [], "open_positions": [], "summary": {"open": 0}}
    plan_id = save_plan(engine, data, rev, legacy, "ROOT")
    publish_plan(engine, plan_id, rev, "ROOT")


def test_open_places_and_summary_are_reconciled():
    data = simple()
    row = assignment("2026-11-02")
    valid = {"status": "FEASIBLE", "assignments": [row],
             "open_positions": [
                 {"Datum": "2026-11-02", "Dienstnummer": "D201", "Open plaatsen": 1},
                 {"Datum": "2026-11-03", "Dienstnummer": "D201", "Open plaatsen": 2}],
             "summary": {"required": 4, "assigned": 1, "open": 3}}
    assert verify_plan(data, valid)["passed"]
    fake = deepcopy(valid)
    fake["open_positions"][0]["Open plaatsen"] = 0
    assert not verify_plan(data, fake)["passed"]
    fake2 = deepcopy(valid)
    fake2["summary"]["assigned"] = 9
    assert "Samenvatting" in str(verify_plan(data, fake2)["errors"])


def test_v025_good_marked_plan_saved_then_tampered_plan_blocked_at_publication(tmp_path):
    """Twee onafhankelijke controles: bij opslag én vlak voor publicatie."""
    from store import (get_engine, initialize, initialize_months, list_month_workspaces,
                       load_month_workspace, save_plan, publish_plan, session_factory,
                       PlanningVersion)
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path / 'tamper.sqlite'}")
    initialize(engine, "ROOT", "SterkTestwachtwoordMetVoldoendeLengte123!")
    initialize_months(engine)
    item = list_month_workspaces(engine)[0]
    data, rev = load_month_workspace(engine, item["year"], item["month"])
    # Geldig *gedeeltelijk* plan: alles staat open (geen diensttoewijzingen).
    vacancies = [{"Datum": d["date"], "Dienstnummer": d["shift_id"],
                  "Open plaatsen": d["required"]} for d in data["demand"] if d["required"]]
    total = sum(row["required"] for row in data["demand"])
    plan = {"status": "FEASIBLE", "assignments": [], "open_positions": vacancies,
            "summary": {"required": total, "assigned": 0, "open": total,
                        "validation_v025": {"version": 1, "passed": True}}}
    assert verify_plan(data, plan)["passed"]
    version_id = save_plan(engine, data, rev, plan, "ROOT")
    # Simuleer nadien beschadiging van de opgeslagen gegevens.
    with session_factory(engine).begin() as session:
        version = session.get(PlanningVersion, version_id)
        version.payload = {**version.payload, "assignments": [assignment(
            vacancies[0]["Datum"], eid="NIET_BESTAAND")]}
    with pytest.raises(ValueError, match="roostercontrole"):
        publish_plan(engine, version_id, rev, "ROOT")
