"""v0.18: meldingen blijven per account, transactief en herhaalveilig."""
import pytest
from datetime import date

from store import (
    add_account, get_engine, initialize, initialize_months,
    load_month_workspace, list_month_workspaces, save_plan,
    publish_plan, publication_preview, notifications_for,
    mark_notice_read, mark_all_notices_read, set_account_state,
    request_leave, decide_leave_request,
)


def make_db(tmp_path):
    db = get_engine(f"sqlite+pysqlite:///{tmp_path/'v018.sqlite'}")
    initialize(db, "ROOT", "EenBeheerdersWachtwoordVanVeertienTekens!")
    initialize_months(db)
    for num in ("DEMO001", "DEMO002", "DEMO003"):
        add_account(db, num, num, "controleur", "FictiefWachtwoordVan14Tekens!", "ROOT")
    return db


def assignment(person, day, shift):
    return {"Personeelsnr": person, "Datum": day, "Dienstnummer": shift,
            "Begin": "08:00", "Einde": "16:00", "Uren": 8}


def setup_month(db):
    r = list_month_workspaces(db)[0]
    state, rev = load_month_workspace(db, r["year"], r["month"])
    day = f"{r['year']}-{r['month']:02d}-03"
    return state, rev, day


def save(db, state, rev, rows):
    return save_plan(db, state, rev, {"status": "FEASIBLE", "summary": {"open": 0},
                                      "assignments": rows, "open_positions": []}, "ROOT")


def test_publication_notifications_first_and_changed_only(tmp_path):
    db = make_db(tmp_path)
    state, rev, day = setup_month(db)
    p1 = save(db, state, rev, [assignment("DEMO001", day, "V101"),
                               assignment("DEMO002", day, "L301")])
    preview = publication_preview(db, p1, "ROOT")
    assert preview["last_published_id"] is None
    assert preview["open_positions"] == 0
    with pytest.raises(ValueError, match="rechten"):
        publication_preview(db, p1, "DEMO001")
    assert notifications_for(db, "DEMO001") == []
    publish_plan(db, p1, rev, "ROOT")
    for employee in ("DEMO001", "DEMO002", "DEMO003"):
        inbox = notifications_for(db, employee)
        assert len(inbox) == 1 and not inbox[0]["read"]
        assert "gepubliceerd" in inbox[0]["title"]
    with pytest.raises(ValueError, match="al gepubliceerd"):
        publish_plan(db, p1, rev, "ROOT")
    assert len(notifications_for(db, "DEMO001")) == 1
    p2 = save(db, state, rev, [assignment("DEMO001", day, "D201"),
                               assignment("DEMO002", day, "L301")])
    preview = publication_preview(db, p2, "ROOT")
    assert preview["last_published_id"] == p1
    assert preview["affected_controllers"] == 1
    publish_plan(db, p2, rev, "ROOT")
    assert len(notifications_for(db, "DEMO001")) == 2
    assert len(notifications_for(db, "DEMO002")) == 1
    assert len(notifications_for(db, "DEMO003")) == 1
    assert "gewijzigd" in notifications_for(db, "DEMO001")[0]["body"]


def test_read_permissions_and_mark_all(tmp_path):
    db = make_db(tmp_path)
    state, rev, day = setup_month(db)
    pid = save(db, state, rev, [assignment("DEMO001", day, "V101")])
    publish_plan(db, pid, rev, "ROOT")
    n = notifications_for(db, "DEMO001")[0]
    with pytest.raises(ValueError, match="niet beschikbaar"):
        mark_notice_read(db, n["id"], "DEMO002")
    with pytest.raises(ValueError, match="niet beschikbaar"):
        mark_notice_read(db, n["id"], "ROOT")
    assert notifications_for(db, "DEMO001")[0]["read"] is False
    mark_notice_read(db, n["id"], "DEMO001")
    mark_notice_read(db, n["id"], "DEMO001")
    assert notifications_for(db, "DEMO001")[0]["read"] is True
    mark_all_notices_read(db, "DEMO002")
    assert notifications_for(db, "DEMO002")[0]["read"] is True
    with pytest.raises(ValueError, match="limiet"):
        notifications_for(db, "ROOT", limit=999)
    set_account_state(db, "DEMO001", False, "ROOT")
    with pytest.raises(ValueError, match="rechten"):
        notifications_for(db, "DEMO001")


def test_leave_decision_creates_only_owner_notice(tmp_path):
    db = make_db(tmp_path)
    state, rev, day = setup_month(db)
    req_id = request_leave(db, "DEMO001", date.fromisoformat(day), date.fromisoformat(day))
    assert notifications_for(db, "DEMO001") == []
    result = decide_leave_request(db, req_id, "ROOT", approve=False)
    assert result["status"] == "rejected"
    assert "afgewezen" in notifications_for(db, "DEMO001")[0]["body"]
    assert notifications_for(db, "DEMO002") == []
    with pytest.raises(ValueError):
        decide_leave_request(db, req_id, "ROOT", approve=False)
    assert len(notifications_for(db, "DEMO001")) == 1


def test_leave_request_notifies_manager_not_other_controllers(tmp_path):
    db = make_db(tmp_path)
    _, _, day = setup_month(db)
    request_leave(db, "DEMO001", date.fromisoformat(day), date.fromisoformat(day))
    assert len(notifications_for(db, "ROOT")) == 1
    assert "verlofaanvraag" in notifications_for(db, "ROOT")[0]["title"].lower()
    assert notifications_for(db, "DEMO002") == []


def test_swap_notification_lifecycle(tmp_path):
    from store import request_swap, respond_swap, decide_swap
    db = make_db(tmp_path)
    state, rev, day = setup_month(db)
    other_day = day[:8] + "06"
    first = {**assignment("DEMO001", day, "V101"), "Soort": "Reguliere dienst", "Controleur": "Fictieve controleur"}
    second = {**assignment("DEMO002", other_day, "D201"), "Soort": "Reguliere dienst", "Controleur": "Fictieve controleur"}
    plan = save(db, state, rev, [first, second])
    publish_plan(db, plan, rev, "ROOT")
    rid = request_swap(db, "DEMO001", "DEMO002", date.fromisoformat(day), "V101",
                       date.fromisoformat(other_day), "D201")
    assert any(f"#{rid}" in n["body"] for n in notifications_for(db, "DEMO002"))
    respond_swap(db, rid, "DEMO002", True)
    assert any("collega akkoord" in n["body"] for n in notifications_for(db, "DEMO001"))
    assert any("klaar voor beoordeling" in n["title"].lower()
               for n in notifications_for(db, "ROOT"))
    decide_swap(db, rid, "ROOT", False)
    for eid in ("DEMO001", "DEMO002"):
        assert any("afgewezen" in n["body"] for n in notifications_for(db, eid))
