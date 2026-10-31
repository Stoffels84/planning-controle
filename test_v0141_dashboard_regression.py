"""v0.14.1: oudere/misvormde samenvattingen blokkeren rapportage niet."""
from datetime import datetime, timezone

from dashboard_v014 import summarize_month
from store import (PlanningVersion, MonthWorkspace, get_engine, initialize,
                   initialize_months, session_factory, dashboard_month_snapshots,
                   list_month_workspaces)


def test_legacy_plan_without_dict_summary_does_not_crash_dashboard(tmp_path):
    db = get_engine(f"sqlite+pysqlite:///{tmp_path/'db.sqlite'}")
    initialize(db, "TESTADMIN", "TestWachtwoordSterkVoorbeeld_2026")
    initialize_months(db)
    month = list_month_workspaces(db)[0]
    with session_factory(db).begin() as session:
        session.add(PlanningVersion(
            year=month["year"], month=month["month"],
            workspace_revision=month["revision"], author="TESTADMIN",
            created_at=datetime.now(timezone.utc), published_at=None,
            payload={"status": "FEASIBLE", "summary": ["oud formaat"]},
        ))
    snapshots = dashboard_month_snapshots(db, "TESTADMIN")
    row = summarize_month(snapshots[0])
    assert row["status"] == "Conceptplanning"
    assert row["assigned"] is None and row["coverage"] is None


def test_missing_optional_month_lists_are_harmless_for_dashboard(tmp_path):
    db = get_engine(f"sqlite+pysqlite:///{tmp_path/'db2.sqlite'}")
    initialize(db, "TESTADMIN", "TestWachtwoordSterkVoorbeeld_2026")
    initialize_months(db)
    month = list_month_workspaces(db)[0]
    key = month["year"] * 100 + month["month"]
    with session_factory(db).begin() as session:
        m = session.get(MonthWorkspace, key)
        changed = dict(m.payload)
        changed.update({"demand": None, "task_needs": None, "preferences": None})
        m.payload = changed
    row = summarize_month(dashboard_month_snapshots(db, "TESTADMIN")[0])
    assert row["status"] == "Leeg"
    assert row["required_now"] == 0 and row["preferences"] == 0
