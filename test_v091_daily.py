"""Dagelijkse dienstnummers: puur model, beveiliging, historie en vergelijking."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from daily_v091 import days_in_month, shifts_by_day, current_daily_choices, update_daily_choices
from demo_data import build_demo
from extras import preference_description, preference_identity, validate_extras
from optimization_v09 import DEFAULTS, compare_row


def test_available_services_are_specific_to_the_date():
    data = build_demo(2026, 11)
    availability = shifts_by_day(data)
    assert [s["id"] for s in availability["2026-11-02"]] == ["V101", "V102", "D201", "L301"]
    assert "N401" not in [s["id"] for s in availability["2026-11-02"]]
    assert [s["id"] for s in availability["2026-11-01"]] == ["V101", "D201"]
    assert len(days_in_month(data)) == 30


def make_choices(data, selected=None):
    all_dates = [day.isoformat() for day in days_in_month(data)]
    prefs = {day: {"kind": "none", "priority": 2} for day in all_dates}
    prefs.update(selected or {})
    return prefs


def test_save_one_shift_and_one_free_day_without_touching_other_people_or_preferences():
    d = build_demo(2026, 11)
    old = deepcopy(d)
    eid = "DEMO001"
    d["preferences"].append({"employee_id": eid, "type": "weekly_free", "weekday": 2, "priority": 3})
    choices = make_choices(d, {
        "2026-11-02": {"kind": "shift", "shift_id": "V102", "priority": 3},
        "2026-11-03": {"kind": "free", "priority": 2},
    })
    updated = update_daily_choices(d, eid, choices)
    assert d["preferences"] == old["preferences"] + [{"employee_id": eid, "type": "weekly_free", "weekday": 2, "priority": 3}]
    own = current_daily_choices(updated, eid)
    assert own["2026-11-02"]["shift_id"] == "V102"
    assert own["2026-11-02"]["priority"] == 3
    assert own["2026-11-03"]["type"] == "free_day"
    assert "2026-11-06" not in own  # oude vrije dag vervangen door geen voorkeur
    assert {p["employee_id"] for p in updated["preferences"]} >= {"DEMO002", eid}
    assert any(p.get("type") == "weekly_free" for p in updated["preferences"])
    assert validate_extras(updated) == []
    assert preference_description(own["2026-11-02"]) == "2026-11-02 — dienst V102"
    assert preference_identity(own["2026-11-02"]) == (eid, "daily_shift", "2026-11-02")


def test_day_replacement_is_idempotent():
    d = build_demo(2026, 11)
    choices = make_choices(d, {"2026-11-02": {"kind": "shift", "shift_id": "V101", "priority": 1}})
    a = update_daily_choices(d, "DEMO001", choices)
    b = update_daily_choices(a, "DEMO001", choices)
    assert a == b


def test_invalid_service_cannot_be_requested_for_the_wrong_day():
    d = build_demo(2026, 11)
    # V102 exists in the catalog but isn't needed on Sunday.
    invalid = make_choices(d, {"2026-11-01": {"kind": "shift", "shift_id": "V102", "priority": 3}})
    with pytest.raises(ValueError, match="niet beschikbaar"):
        update_daily_choices(d, "DEMO001", invalid)
    with pytest.raises(ValueError, match="iedere datum"):
        update_daily_choices(d, "DEMO001", {"2026-11-01": {"kind": "none"}})


def test_persisted_wish_can_survive_changes_to_demand_and_user_can_correct():
    d = build_demo(2026, 11)
    d = update_daily_choices(d, "DEMO001", make_choices(d, {
        "2026-11-02": {"kind": "shift", "shift_id": "V101", "priority": 2}}))
    d["demand"] = [r for r in d["demand"] if (r["date"], r["shift_id"]) != ("2026-11-02", "V101")]
    assert validate_extras(d) == []  # geen harde migratie/gegevensverlies bij gewijzigde behoeften
    d["shifts"] = [sh for sh in d["shifts"] if sh["id"] != "V101"]
    d["demand"] = [r for r in d["demand"] if r["shift_id"] != "V101"]
    assert validate_extras(d) == []  # ook na schrappen van dienstnummer
    d = update_daily_choices(d, "DEMO001", make_choices(d))
    assert "2026-11-02" not in current_daily_choices(d, "DEMO001")


def test_comparison_counts_exact_daily_service_and_excludes_removed_one():
    d = build_demo(2026, 11)
    d["preferences"] = [
        {"employee_id": "DEMO001", "type": "daily_shift", "date": "2026-11-02", "shift_id": "V101", "priority": 3},
        {"employee_id": "DEMO002", "type": "daily_shift", "date": "2026-11-02", "shift_id": "V102", "priority": 3},
    ]
    assignments = [{"Personeelsnr": "DEMO001", "Datum": "2026-11-02", "Dienstnummer": "V101", "Uren": 8}]
    plan = SimpleNamespace(status="FEASIBLE", assignments=assignments, task_assignments=[],
                           summary={"assigned": 1, "open": 0, "task_open": 0})
    result = compare_row(DEFAULTS[0], plan, d)
    assert result["Dagelijkse dienstwensen ingewilligd"] == 1
    assert result["Dagelijkse dienstwensen gemist"] == 1
    d["demand"] = [r for r in d["demand"] if (r["date"], r["shift_id"]) != ("2026-11-02", "V102")]
    result = compare_row(DEFAULTS[0], plan, d)
    assert result["Dagelijkse dienstwensen gemist"] == 0


def test_controller_can_persist_own_daily_choice_not_others_or_other_fields(tmp_path):
    from store import add_account, get_engine, initialize, load_workspace, save_workspace
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path / 'daily.sqlite3'}")
    initialize(engine, "ROOT", "EenLangTijdelijkWachtwoord2026!")
    add_account(engine, "DEMO001", "Testcontroleur", "controleur", "NieuwTestWachtwoord2026!", "ROOT")
    d, rev = load_workspace(engine)
    day, shs = next(iter(shifts_by_day(d).items()))
    saved = update_daily_choices(d, "DEMO001", make_choices(d, {
        day: {"kind": "shift", "shift_id": shs[0]["id"], "priority": 2}
    }))
    next_rev = save_workspace(engine, saved, rev, "DEMO001", "Eigen dagwens opgeslagen")
    loaded, _ = load_workspace(engine)
    assert next_rev > rev
    assert current_daily_choices(loaded, "DEMO001")
    illegal = deepcopy(loaded)
    illegal["settings"]["max_consecutive"] = 3
    with pytest.raises(ValueError, match="eigen voorkeuren"):
        save_workspace(engine, illegal, next_rev, "DEMO001", "Ongeoorloofde wijziging")
