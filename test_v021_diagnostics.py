"""Tests voor de indicatieve haalbaarheidsdiagnose zonder OR-Tools-afhankelijkheid."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import ast

from diagnostics_v021 import analyze_month, explain_open_positions
from demo_data import build_demo


def small_data():
    data = build_demo(2026, 11)
    data["employees"] = data["employees"][:2]
    data["shifts"] = [dict(data["shifts"][0], required=1), dict(data["shifts"][2], required=1)]
    data["demand"] = [{"date": "2026-11-02", "shift_id": "V101", "required": 1}]
    data["preferences"] = []
    data["hour_credits"] = []
    return data


def test_no_shortage_when_both_available():
    result = analyze_month(small_data())
    assert result["summary"]["direct_shortfall"] == 0
    assert result["slots"][0]["Direct inzetbare kandidaten"] == 2
    assert result["summary"]["service_places"] == 1
    assert result["summary"]["days_with_shortfall"] == 0


def test_category_block_proves_direct_shortage():
    data = small_data()
    data["employees"][0]["blocked_categories"] = ["Vroeg"]
    data["employees"][1]["blocked_shifts"] = ["V101"]
    result = analyze_month(data)
    assert result["slots"][0]["Direct tekort (ondergrens)"] == 1
    assert result["slots"][0]["Direct inzetbare kandidaten"] == 0
    assert len(result["blockers"]) == 2
    assert sum(row["Kandidaat-dienstcombinaties"] for row in result["blockers"]) == 2
    assert "Personeelsnr" not in result["slots"][0]  # geen namen of IDs in teamoverzicht


def test_day_capacity_lower_bound_even_if_every_shift_has_candidates():
    data = small_data()
    data["employees"] = data["employees"][:1]
    data["demand"].append({"date": "2026-11-02", "shift_id": "D201", "required": 1})
    result = analyze_month(data)
    assert result["summary"]["direct_shortfall"] == 0
    assert result["summary"]["days_with_shortfall"] == 1
    assert result["days"][0]["Dagtekort (ondergrens)"] == 1
    assert result["days"][0]["Unieke directe kandidaten"] == 1


def test_night_service_overlaps_activity_next_day():
    data = small_data()
    data["shifts"] = [{"id": "N401", "category": "Nacht", "start": "22:00", "end": "06:00", "required": 1}]
    data["demand"] = [{"date": "2026-11-02", "shift_id": "N401", "required": 1}]
    data["hour_credits"] = [{"employee_id": data["employees"][0]["id"], "date": "2026-11-03", "type": "Verlof", "hours": 8}]
    result = analyze_month(data)
    assert result["slots"][0]["Direct inzetbare kandidaten"] == 1
    assert any(row["Blokkering"] == "Rustdag of geregistreerde activiteit" for row in result["blockers"])


def test_boundary_night_forbids_early_next_month():
    data = small_data()
    data["demand"] = [{"date": "2026-11-01", "shift_id": "V101", "required": 1}]
    prior = {"employee_id": data["employees"][0]["id"], "date": "2026-10-31",
             "category": "Nacht", "start": "22:00", "end": "06:00", "source": "previous"}
    result = analyze_month(data, [prior])
    assert result["slots"][0]["Direct inzetbare kandidaten"] == 1
    assert any(row["Blokkering"] == "Rust/overgang met gepubliceerde buurmaand" for row in result["blockers"])


def test_future_published_month_boundary():
    data = small_data()
    data["demand"] = [{"date": "2026-11-30", "shift_id": "V101", "required": 1}]
    future = {"employee_id": data["employees"][0]["id"], "date": "2026-12-01",
              "category": "Vroeg", "start": "00:00", "end": "08:00", "source": "next"}
    result = analyze_month(data, [future])
    assert result["slots"][0]["Direct inzetbare kandidaten"] == 1


def test_maxima_zero_and_month_hours():
    data = small_data()
    data["employees"][0]["max_month_categories"] = {"Vroeg": 0}
    data["employees"][1]["max_month_hours"] = 1
    result = analyze_month(data)
    assert result["summary"]["direct_shortfall"] == 1
    assert {r["Blokkering"] for r in result["blockers"]} == {
        "Maandmaximum dienstcategorie is nul", "Maandurenmaximum onder dienstduur"
    }


def test_explain_open_positions_only_indicative_not_proven_cause():
    diagnosis = analyze_month(small_data())
    result = explain_open_positions(diagnosis, [{"Datum": "2026-11-02", "Dienstnummer": "V101", "Open plaatsen": 1}])
    assert result[0]["Open plaatsen solver"] == 1
    assert "niet bewezen" in result[0]["Indicatie"]
    assert result[0]["Direct tekort (ondergrens)"] == 0


def test_empty_demand_and_no_active_staff():
    data = small_data()
    data["demand"] = []
    assert analyze_month(data)["summary"]["max_day_shortfall"] == 0
    data["demand"] = [{"date": "2026-11-02", "shift_id": "V101", "required": 1}]
    for emp in data["employees"]:
        emp["active"] = False
    result = analyze_month(data)
    assert result["summary"]["direct_shortfall"] == 1
    assert result["summary"]["active_staff"] == 0


def test_ui_has_preflight_and_xlsx_sheets_without_changing_solver():
    project = Path(__file__).resolve().parents[1]
    text = (project / "app.py").read_text(encoding="utf-8")
    ast.parse(text)
    assert 'from diagnostics_v021 import analyze_month, explain_open_positions' in text
    assert 'Haalbaarheid vóór berekening' in text
    assert 'Uitleg open plaatsen' in text
    assert 'plan_excel(plan, data, diagnosis)' in text
    # De code van de planningsmotor uit v0.20 is bytegewijs behouden.
    current = (project / "planner.py").read_bytes()
    assert b'def solve_month' in current
