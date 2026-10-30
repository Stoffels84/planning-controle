"""Compatibiliteit en v0.4-regels; geen Streamlit en OR-Tools nodig."""
from copy import deepcopy

from catalog import (new_employee, profile, settings_with_defaults,
                     transition_code, validate_employee, validate_schedule_settings)
from demo_data import build_demo
from store import get_engine, initialize, load_workspace, save_workspace


def test_legacy_profiles_and_settings_are_not_mutated():
    project = build_demo(2026, 11)
    before = deepcopy(project)
    employee = profile(project["employees"][0])
    settings = settings_with_defaults(project["settings"])
    assert employee["min_rest_hours"] is None
    assert employee["target_month_hours"] == 0
    assert employee["max_category_run"] == {}
    assert employee["blocked_transitions"] == []
    assert settings["transition_rest_hours"] == {}
    assert settings["hours_weight"] == 0
    assert project == before


def test_individual_rules_accept_valid_settings():
    employee = new_employee("DEMO099", "Testcontroleur", "Testteam", 80, 140)
    employee["min_rest_hours"] = 13
    employee["target_month_hours"] = 120
    employee["max_category_run"] = {"Nacht": 2}
    employee["blocked_transitions"] = [transition_code("Nacht", "Vroeg")]
    assert validate_employee(employee, {"N401"}) == []
    settings = settings_with_defaults(build_demo(2026, 11)["settings"])
    settings["transition_rest_hours"] = {"Laat>Vroeg": 14}
    settings["max_category_run"] = {"Nacht": 3}
    settings["blocked_transitions"] = ["Nacht>Dag"]
    settings["hours_weight"] = 3
    assert validate_schedule_settings(settings) == []


def test_invalid_rules_rejected():
    employee = new_employee("DEMO099", "Testcontroleur", "Testteam", 80, 140)
    employee["target_month_hours"] = 150
    assert validate_employee(employee, {"N401"})
    employee["target_month_hours"] = 100
    employee["max_category_run"] = {"Nacht": 8}
    assert validate_employee(employee, {"N401"})
    employee["max_category_run"] = {}
    employee["blocked_transitions"] = ["NietBestaand>Vroeg"]
    assert validate_employee(employee, {"N401"})
    settings = settings_with_defaults(build_demo(2026, 11)["settings"])
    settings["transition_rest_hours"] = {"Vroeg>Nacht": 100}
    assert validate_schedule_settings(settings)
    settings["transition_rest_hours"] = {}
    settings["max_category_run"] = {"NietBestaand": 2}
    assert validate_schedule_settings(settings)


def test_upgrade_keeps_persisted_records(tmp_path):
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path / 'upgrade.db'}")
    initialize(engine, "TESTADMIN", "VeiligTijdelijkWachtwoord123!")
    original, rev = load_workspace(engine)
    updated = deepcopy(original)
    updated["employees"][0].update({"min_rest_hours": 12, "target_month_hours": 150,
                                       "max_category_run": {"Nacht": 2},
                                       "blocked_transitions": ["Laat>Vroeg"]})
    updated["settings"].update({"max_category_run": {"Nacht": 2},
                                 "transition_rest_hours": {"Nacht>Dag": 18},
                                 "hours_weight": 1})
    next_rev = save_workspace(engine, updated, rev, "TESTADMIN", "v0.4 testinstellingen")
    loaded, version = load_workspace(engine)
    assert version == next_rev
    assert loaded == updated
    assert loaded["employees"][1] == original["employees"][1]
