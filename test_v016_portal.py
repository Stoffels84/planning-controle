"""Regressietests voor het persoonlijke weekportaal en publicatieoverzicht."""

from copy import deepcopy
from datetime import date

import pytest

from demo_data import build_demo
from daily_v091 import shifts_by_day
from portal_v016 import (month_weeks, preference_summary, week_choices,
                         save_week_choices, personal_calendar, own_published_assignments)
from extras import validate_extras


def choice_for_week(data, week):
    return {d.isoformat(): {"kind": "none", "priority": 2} for d in week["days"]}


def test_week_grouping_is_complete_and_only_current_month():
    data = build_demo(2027, 1)
    weeks = month_weeks(data)
    assert sum(len(w["days"]) for w in weeks) == 31
    assert [d for w in weeks for d in w["days"]] == [date(2027, 1, day) for day in range(1, 32)]
    assert all(d.month == 1 for w in weeks for d in w["days"])
    assert len({w["key"] for w in weeks}) == len(weeks)
    assert weeks[0]["days"] == [date(2027, 1, 1), date(2027, 1, 2), date(2027, 1, 3)]


def test_save_one_week_keeps_other_week_and_other_employee_and_other_preferences():
    original = build_demo(2026, 11)
    original["preferences"].append({"employee_id": "DEMO001", "type": "weekly_free", "weekday": 2, "priority": 3})
    before = deepcopy(original)
    weeks = month_weeks(original)
    week1 = choice_for_week(original, weeks[0])
    available = shifts_by_day(original)
    first_day = weeks[0]["days"][0].isoformat()
    week1[first_day] = {"kind": "shift", "shift_id": available[first_day][0]["id"], "priority": 3}
    updated = save_week_choices(original, "DEMO001", weeks[0]["days"], week1)
    assert original == before  # source never mutated
    assert preference_summary(updated, "DEMO001")["shift"] == 1
    assert preference_summary(updated, "DEMO001")["unselected"] == 28  # demo bevat al een vrijwens op 6 november
    assert week_choices(updated, "DEMO001", weeks[0]["days"])[first_day] == week1[first_day]
    week2 = choice_for_week(updated, weeks[1])
    day2 = weeks[1]["days"][0].isoformat()
    week2[day2] = {"kind": "free", "priority": 1}
    again = save_week_choices(updated, "DEMO001", weeks[1]["days"], week2)
    assert preference_summary(again, "DEMO001")["shift"] == 1
    assert preference_summary(again, "DEMO001")["free"] == 1
    assert any(p.get("employee_id") == "DEMO002" for p in again["preferences"])
    assert any(p.get("employee_id") == "DEMO001" and p.get("type") == "weekly_free"
               for p in again["preferences"])
    assert validate_extras(again) == []


def test_reset_one_week_only_does_not_wipe_other_weeks():
    data = build_demo(2026, 11)
    weeks = month_weeks(data)
    one = choice_for_week(data, weeks[0])
    one[weeks[0]["days"][0].isoformat()] = {"kind": "free", "priority": 2}
    data = save_week_choices(data, "DEMO001", weeks[0]["days"], one)
    two = choice_for_week(data, weeks[1])
    two[weeks[1]["days"][0].isoformat()] = {"kind": "free", "priority": 2}
    data = save_week_choices(data, "DEMO001", weeks[1]["days"], two)
    data = save_week_choices(data, "DEMO001", weeks[0]["days"], choice_for_week(data, weeks[0]))
    assert preference_summary(data, "DEMO001")["free"] == 1
    assert week_choices(data, "DEMO001", weeks[1]["days"])[weeks[1]["days"][0].isoformat()]["kind"] == "free"


def test_invalid_outside_week_or_service_rejected():
    data = build_demo(2026, 11)
    one = month_weeks(data)[0]
    selected = choice_for_week(data, one)
    selected["2026-11-30"] = {"kind": "none", "priority": 2}
    with pytest.raises(ValueError, match="gekozen week"):
        save_week_choices(data, "DEMO001", one["days"], selected)
    selected.pop("2026-11-30")
    selected["2026-11-01"] = {"kind": "shift", "shift_id": "N401", "priority": 3}
    with pytest.raises(ValueError, match="niet langer beschikbaar"):
        save_week_choices(data, "DEMO001", one["days"], selected)
    with pytest.raises(ValueError, match="Onbekende controleur"):
        save_week_choices(data, "ONBEKEND", one["days"], choice_for_week(data, one))


def test_stale_service_in_other_week_can_be_corrected_without_losing_history():
    data = build_demo(2026, 11)
    data["preferences"].append({"employee_id": "DEMO001", "type": "daily_shift",
                                "date": "2026-11-20", "shift_id": "OLD999", "priority": 2})
    week = month_weeks(data)[0]
    data2 = save_week_choices(data, "DEMO001", week["days"], choice_for_week(data, week))
    assert any(p.get("shift_id") == "OLD999" for p in data2["preferences"])


def test_published_view_is_personal_and_wishes_are_not_assignments():
    data = build_demo(2026, 11)
    plan = {"assignments": [
        {"Datum": "2026-11-02", "Personeelsnr": "DEMO001", "Dienstnummer": "V101",
         "Begin": "06:00", "Einde": "14:00", "Uren": 8},
        {"Datum": "2026-11-02", "Personeelsnr": "DEMO002", "Dienstnummer": "N401",
         "Begin": "22:00", "Einde": "06:00", "Uren": 8},
    ]}
    own = own_published_assignments(plan, "DEMO001")
    assert len(own) == 1
    assert all(x["Personeelsnr"] == "DEMO001" for rows in own.values() for x in rows)
    rows = personal_calendar(data, "DEMO001", plan)
    day = next(r for r in rows if r["Datum"] == "2026-11-02")
    assert "V101" in day["Gepubliceerde planning"]
    assert "N401" not in day["Gepubliceerde planning"]
    assert day["Uren"] == 8
    assert next(r for r in rows if r["Datum"] == "2026-11-05")["Gepubliceerde planning"] == "Geen dienst toegewezen"
    assert personal_calendar(data, "DEMO001")[1]["Gepubliceerde planning"] == "Nog niet gepubliceerd"
    assert len(rows) == 30


def test_registered_activity_visible_but_not_a_guaranteed_free_day():
    data = build_demo(2026, 11)
    data["hour_credits"] = [{"employee_id": "DEMO001", "date": "2026-11-02", "type": "Verlof", "hours": 7.6},
                            {"employee_id": "DEMO002", "date": "2026-11-03", "type": "Ziekte", "hours": 7.6}]
    rows = personal_calendar(data, "DEMO001")
    assert rows[1]["Activiteit"] == "Verlof"
    assert rows[2]["Activiteit"] == "—"
    assert rows[1]["Gepubliceerde planning"] == "Nog niet gepubliceerd"


def test_database_persists_week_selection_without_touching_other_controller_or_month(tmp_path):
    from store import (get_engine, initialize, initialize_months, add_account,
                       load_month_workspace, save_month_workspace, create_month_workspace)
    db = get_engine(f"sqlite+pysqlite:///{tmp_path/'v016.sqlite3'}")
    initialize(db, "ROOT", "SterkBeheerderswachtwoordTest2026!")
    add_account(db, "DEMO001", "Testpersoon", "controleur", "NieuwSterkTestWachtwoord2026!", "ROOT")
    add_account(db, "DEMO002", "Collega", "controleur", "NogEenSterkTestWachtwoord2026!", "ROOT")
    initialize_months(db)
    from store import list_month_workspaces
    period = list_month_workspaces(db)[0]
    year, month = period["year"], period["month"]
    state, rev = load_month_workspace(db, year, month)
    week = month_weeks(state)[0]
    chosen = choice_for_week(state, week)
    first = week["days"][0].isoformat()
    chosen[first] = {"kind": "free", "priority": 3}
    new = save_week_choices(state, "DEMO001", week["days"], chosen)
    new_revision = save_month_workspace(db, new, rev, "DEMO001", "Eigen testwensen per week")
    restored, restored_revision = load_month_workspace(db, year, month)
    assert restored_revision == new_revision
    assert week_choices(restored, "DEMO001", week["days"])[first]["kind"] == "free"
    assert [p for p in restored["preferences"] if p["employee_id"] == "DEMO002"] == [
        p for p in state["preferences"] if p["employee_id"] == "DEMO002"]
    new_month = (year + 1, 1) if month == 12 else (year, month + 1)
    create_month_workspace(db, *new_month, "ROOT")
    second, _ = load_month_workspace(db, *new_month)
    assert second["preferences"] == []
    assert load_month_workspace(db, year, month)[0] == restored


def test_controller_cannot_edit_someone_elses_week(tmp_path):
    from store import get_engine, initialize, initialize_months, add_account, load_month_workspace, save_month_workspace
    db = get_engine(f"sqlite+pysqlite:///{tmp_path/'v016_permissions.sqlite3'}")
    initialize(db, "ROOT", "SterkBeheerderswachtwoordTest2026!")
    add_account(db, "DEMO001", "Testpersoon", "controleur", "NieuwSterkTestWachtwoord2026!", "ROOT")
    initialize_months(db)
    from store import list_month_workspaces
    period = list_month_workspaces(db)[0]
    state, rev = load_month_workspace(db, period["year"], period["month"])
    week = month_weeks(state)[0]
    choices = choice_for_week(state, week)
    choices[week["days"][0].isoformat()] = {"kind": "free", "priority": 3}
    forbidden = save_week_choices(state, "DEMO002", week["days"], choices)
    with pytest.raises(ValueError, match="alleen hun eigen voorkeuren"):
        save_month_workspace(db, forbidden, rev, "DEMO001", "Niet toegestaan")
