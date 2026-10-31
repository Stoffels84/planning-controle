"""v0.17: maandkalender, persoonlijke aanvraagstatussen, gepubliceerde wijzigingen."""
from datetime import date
import pytest

from demo_data import build_demo
from portal_v017 import month_tiles, personal_publication_changes, personal_request_feed
from store import (add_account, get_engine, initialize, initialize_months,
                   list_month_workspaces, load_month_workspace, save_plan,
                   publish_plan, personal_published_versions, set_account_state)


def assignment(person, day, shift, start="08:00", end="16:00"):
    return {"Personeelsnr": person, "Datum": day, "Dienstnummer": shift,
            "Begin": start, "Einde": end, "Uren": 8}


def test_calendar_grid_has_exact_month_and_preference_not_published():
    state = build_demo(2026, 11)
    weeks = month_tiles(state, "DEMO001", None)
    assert len(weeks) == 6
    assert all(len(w) == 7 for w in weeks)
    actual = [t for w in weeks for t in w if t["in_month"]]
    assert len(actual) == 30
    assert actual[0]["date"] == "2026-11-01"
    assert all(t["category"] == "ongepubliceerd" for t in actual)
    assert all(t["primary"] == "Nog niet gepubliceerd" for t in actual)


def test_calendar_published_is_personal_and_pending_leave_does_not_remove_assignment():
    state = build_demo(2026, 11)
    payload = {"assignments": [assignment("DEMO001", "2026-11-02", "V101"),
                               assignment("DEMO002", "2026-11-02", "N401")]}
    leaves = [
        {"employee_id": "DEMO001", "start_date": "2026-11-02", "end_date": "2026-11-03", "status": "pending"},
        {"employee_id": "DEMO002", "start_date": "2026-11-04", "end_date": "2026-11-05", "status": "approved"},
    ]
    tiles = [t for week in month_tiles(state, "DEMO001", payload, leaves, {"2026-11-02"})
             for t in week if t["in_month"]]
    assigned = next(t for t in tiles if t["date"] == "2026-11-02")
    assert assigned["category"] == "dienst"
    assert "V101" in assigned["primary"]
    assert "N401" not in assigned["primary"]
    assert assigned["changed"]
    assert assigned["leave"] == ["In behandeling verlof"]
    assert next(t for t in tiles if t["date"] == "2026-11-04")["leave"] == []
    assert next(t for t in tiles if t["date"] == "2026-11-03")["category"] == "zonder_dienst"


def test_changes_compare_assignments_not_position_or_other_controller():
    previous = [assignment("DEMO001", "2026-11-03", "D201"),
                assignment("DEMO001", "2026-11-01", "V101"),
                assignment("DEMO002", "2026-11-02", "V101")]
    current = [assignment("DEMO002", "2026-11-02", "L301"),
               assignment("DEMO001", "2026-11-01", "V101"),
               assignment("DEMO001", "2026-11-04", "L301")]
    diff = personal_publication_changes(previous, current, "DEMO001")
    assert [d["Datum"] for d in diff] == ["2026-11-03", "2026-11-04"]
    assert diff[0]["Huidige publicatie"] == "Geen dienst toegewezen"
    assert diff[1]["Vorige publicatie"] == "Geen dienst toegewezen"
    assert "DEMO002" not in str(diff)
    assert personal_publication_changes(previous, list(reversed(previous)), "DEMO001") == []


def test_request_feed_hides_other_users_and_marks_accepted_swap_as_open():
    leave = [{"id": 1, "employee_id": "DEMO001", "start_date": "2026-11-03",
              "end_date": "2026-11-04", "status": "pending"},
             {"id": 2, "employee_id": "DEMO002", "start_date": "2026-11-03",
              "end_date": "2026-11-05", "status": "approved"}]
    swaps = [{"id": 3, "initiator_id": "DEMO002", "colleague_id": "DEMO001",
              "own_day": "2026-11-07", "their_day": "2026-11-10", "status": "accepted"},
             {"id": 4, "initiator_id": "DEMO002", "colleague_id": "DEMO003",
              "own_day": "2026-11-01", "their_day": "2026-11-02", "status": "pending"}]
    feed = personal_request_feed(leave, swaps, "DEMO001")
    assert (feed["total"], feed["open"]) == (2, 2)
    assert {r["Nummer"] for r in feed["items"]} == {1, 3}
    assert not any("DEMO002" in str(row) for row in feed["items"])


def test_read_only_published_versions_respect_roles_and_ignore_drafts(tmp_path):
    db = get_engine(f"sqlite+pysqlite:///{tmp_path/'v017.sqlite'}")
    initialize(db, "ROOT", "SterkTestWachtwoordVoorDeBeheerder2026!")
    initialize_months(db)
    add_account(db, "DEMO001", "A", "controleur", "ControleurWachtwoordTest123456!", "ROOT")
    add_account(db, "DEMO002", "B", "controleur", "ControleurWachtwoordTest123456!", "ROOT")
    record = list_month_workspaces(db)[0]
    year, month = record["year"], record["month"]
    state, rev = load_month_workspace(db, year, month)
    day = f"{year}-{month:02d}-02"
    def save(rows):
        return save_plan(db, state, rev, {"status": "FEASIBLE", "summary": {},
                         "assignments": rows, "open_positions": []}, "ROOT")
    p1 = save([assignment("DEMO001", day, "V101"), assignment("DEMO002", day, "N401")])
    publish_plan(db, p1, rev, "ROOT")
    draft = save([assignment("DEMO001", day, "D201")])
    early = personal_published_versions(db, year, month, "DEMO001")
    assert len(early) == 1 and early[0]["id"] == p1
    assert all(r["Personeelsnr"] == "DEMO001" for r in early[0]["assignments"])
    assert draft not in [r["id"] for r in early]
    p2 = save([assignment("DEMO001", day, "L301"), assignment("DEMO002", day, "N401")])
    publish_plan(db, p2, rev, "ROOT")
    after = personal_published_versions(db, year, month, "DEMO001")
    assert [v["id"] for v in after] == [p2, p1]
    diff = personal_publication_changes(after[1]["assignments"], after[0]["assignments"], "DEMO001")
    assert len(diff) == 1 and "L301" in diff[0]["Huidige publicatie"]
    with pytest.raises(ValueError, match="eigen"):
        personal_published_versions(db, year, month, "DEMO001", "DEMO002")
    with pytest.raises(ValueError, match="Ongeldig"):
        personal_published_versions(db, year, month, "ROOT", "DEMO001", 10)
    manager = personal_published_versions(db, year, month, "ROOT", "DEMO002")
    assert len(manager) == 2 and all(v["assignments"][0]["Personeelsnr"] == "DEMO002" for v in manager)
    set_account_state(db, "DEMO001", False, "ROOT")
    with pytest.raises(ValueError, match="rechten"):
        personal_published_versions(db, year, month, "DEMO001")
