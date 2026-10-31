"""Dashboard v0.14: read-only status, revision-safety, and authorization."""
from datetime import date
import pytest

from dashboard_v014 import summarize_month, summarize_requests, dashboard_warnings, dashboard_counts
from store import (get_engine, initialize, initialize_months, list_month_workspaces,
                   dashboard_month_snapshots, add_account, load_month_workspace,
                   create_month_workspace, save_plan, publish_plan)


def sample(revision=1, published=None, latest=None, with_demand=True):
    return {
        "year": 2026, "month": 11, "revision": revision,
        "workspace": {
            "demand": [{"date": "2026-11-02", "shift_id": "V101", "required": 2}] if with_demand else [],
            "task_needs": [], "preferences": [{"type": "day_off"}],
        },
        "published_plan": published, "latest_plan": latest,
    }


def plan(plan_id, revision, required=2, assigned=1, open_places=1):
    return {"id": plan_id, "revision": revision,
            "payload": {"summary": {"required": required, "assigned": assigned,
                                    "open": open_places}}}


def test_empty_and_preparation_and_concept():
    assert summarize_month(sample(with_demand=False))["status"] == "Leeg"
    assert summarize_month(sample())["status"] == "In voorbereiding"
    assert summarize_month(sample(latest=plan(1, 1)))["status"] == "Conceptplanning"
    assert summarize_month(sample(revision=2, latest=plan(1, 1)))["status"] == "Concept verouderd"


def test_published_is_authoritative_even_when_newer_concept():
    summary = summarize_month(sample(published=plan(5, 1, 2, 2, 0), latest=plan(6, 1, 2, 1, 1)))
    assert summary["status"] == "Gepubliceerd · nieuw concept"
    assert summary["plan_id"] == 5
    assert summary["assigned"] == 2 and summary["open"] == 0
    assert summary["coverage"] == 100.0


def test_stale_publication_warned_without_mixing_new_demand():
    summary = summarize_month(sample(revision=3, published=plan(5, 1, 2, 1, 1)))
    assert summary["status"] == "Gepubliceerd · invoer gewijzigd"
    assert summary["required_now"] == 2
    assert summary["coverage"] == 50.0
    assert any("gewijzigd" in t for t in dashboard_warnings(summary))
    counts = dashboard_counts([summary, summarize_month(sample(with_demand=False))])
    assert counts == {"months": 2, "published": 1, "outdated": 1, "without_demand": 1}


def test_no_plan_is_blank_instead_of_fake_zero_coverage():
    summary = summarize_month(sample())
    assert summary["assigned"] is None and summary["coverage"] is None
    assert "nog geen opgeslagen" in " ".join(dashboard_warnings(summary))


def test_requests_count_only_open_decisions_for_month():
    leaves = [
        {"status": "pending", "start_date": "2026-11-03", "end_date": "2026-11-03"},
        {"status": "approved", "start_date": "2026-11-04", "end_date": "2026-11-04"},
        {"status": "pending", "start_date": "2026-12-03", "end_date": "2026-12-03"},
    ]
    swaps = [
        {"status": "pending", "own_day": "2026-11-02", "their_day": "2026-11-10"},
        {"status": "accepted", "own_day": "2026-11-04", "their_day": "2026-11-12"},
        {"status": "approved", "own_day": "2026-11-03", "their_day": "2026-11-11"},
        {"status": "accepted", "own_day": "2026-12-03", "their_day": "2026-12-11"},
    ]
    assert summarize_requests(leaves, swaps, 2026, 11) == {
        "leave_pending": 1, "swaps_awaiting_colleague": 1, "swaps_awaiting_planner": 1}


def test_manager_only_and_month_records_are_separate(tmp_path):
    db = get_engine(f"sqlite+pysqlite:///{tmp_path/'dash.sqlite'}")
    initialize(db, "TESTADMIN", "TestWachtwoordSterkVoorbeeld_2026")
    initialize_months(db)
    source = list_month_workspaces(db)[0]
    year, month = source["year"], source["month"]
    other = (year + (month == 12), month % 12 + 1)
    create_month_workspace(db, *other, "TESTADMIN")
    add_account(db, "C001", "Testcontroleur", "controleur", "SterkTestWachtwoord2026!", "TESTADMIN")
    with pytest.raises(ValueError, match="Alleen"):
        dashboard_month_snapshots(db, "C001")
    values = dashboard_month_snapshots(db, "TESTADMIN")
    assert len(values) == 2
    assert values[0]["workspace"]["demand"]
    assert not values[1]["workspace"]["demand"]
    assert "employees" not in values[0]["workspace"]


def test_dashboard_reports_published_and_latest_separately(tmp_path):
    db = get_engine(f"sqlite+pysqlite:///{tmp_path/'dashplan.sqlite'}")
    initialize(db, "TESTADMIN", "TestWachtwoordSterkVoorbeeld_2026")
    initialize_months(db)
    m = list_month_workspaces(db)[0]
    year, month = m["year"], m["month"]
    state, rev = load_month_workspace(db, year, month)
    result = {"status": "FEASIBLE", "summary": {"required": 7, "assigned": 6, "open": 1},
              "assignments": [], "open_positions": []}
    first = save_plan(db, state, rev, result, "TESTADMIN")
    publish_plan(db, first, rev, "TESTADMIN")
    second = save_plan(db, state, rev, {**result, "summary": {"required": 7, "assigned": 7, "open": 0}}, "TESTADMIN")
    snapshot = dashboard_month_snapshots(db, "TESTADMIN")[0]
    assert snapshot["published_plan"]["id"] == first
    assert snapshot["latest_plan"]["id"] == second
    assert summarize_month(snapshot)["plan_id"] == first
