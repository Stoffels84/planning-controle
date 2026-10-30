"""Offline SQLite-tests voor de database- en rolregels van v0.2."""

import pytest
from pathlib import Path

from demo_data import build_demo
from store import (
    ConflictError, add_account, authenticate, change_password, get_engine,
    initialize, load_plan, load_workspace, lookup_account, publish_plan,
    reset_password, recover_admin_once, save_plan, save_workspace, set_account_state,
)


def setup_db(tmp_path: Path):
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path / 'test.sqlite3'}")
    initialize(engine, "TESTADMIN", "TijdelijkVoorbeeld2026!sterk")
    return engine


def test_bootstrap_login_password_change(tmp_path):
    db = setup_db(tmp_path)
    assert authenticate(db, "TESTADMIN", "verkeerd") is None
    a = authenticate(db, "TESTADMIN", "TijdelijkVoorbeeld2026!sterk")
    assert a["must_change_password"]
    old_stamp = a["auth_hash"]
    change_password(db, "TESTADMIN", "TijdelijkVoorbeeld2026!sterk", "EenAnderSterkWachtwoord2026!")
    assert authenticate(db, "TESTADMIN", "TijdelijkVoorbeeld2026!sterk") is None
    b = authenticate(db, "TESTADMIN", "EenAnderSterkWachtwoord2026!")
    assert b and not b["must_change_password"] and b["auth_hash"] != old_stamp
    initialize(db)  # opnieuw opstarten vereist geen bootstrapgeheim


def test_account_roles_and_permission_enforcement(tmp_path):
    db = setup_db(tmp_path)
    add_account(db, "DEMO001", "Testcontroleur", "controleur", "ControleurSterkWachtwoord1!", "TESTADMIN")
    account = authenticate(db, "DEMO001", "ControleurSterkWachtwoord1!")
    assert account["role"] == "controleur"
    with pytest.raises(ValueError):
        add_account(db, "EXTRA", "Planner", "planner", "ExtraSterkWachtwoord123!", "DEMO001")
    with pytest.raises(ValueError):
        set_account_state(db, "TESTADMIN", False, "TESTADMIN")
    with pytest.raises(ValueError):
        reset_password(db, "TESTADMIN", "AnderSterkWachtwoord1!", "DEMO001")
    set_account_state(db, "DEMO001", False, "TESTADMIN")
    assert authenticate(db, "DEMO001", "ControleurSterkWachtwoord1!") is None


def test_workspace_persistence_revision_and_controller_scope(tmp_path):
    db = setup_db(tmp_path)
    add_account(db, "DEMO001", "Testcontroleur", "controleur", "ControleurSterkWachtwoord1!", "TESTADMIN")
    payload, rev = load_workspace(db)
    assert rev == 1
    assert payload["year"] >= 2026
    updated = dict(payload)
    updated["preferences"] = [p for p in payload["preferences"] if p["employee_id"] != "DEMO001"]
    updated["preferences"].append({"employee_id": "DEMO001", "date": f"{payload['year']}-{payload['month']:02d}-02", "priority": 3})
    next_rev = save_workspace(db, updated, rev, "DEMO001", "Eigen vrijwens opgeslagen")
    assert next_rev == 2
    saved, stored_rev = load_workspace(db)
    assert saved["preferences"] == updated["preferences"]
    assert stored_rev == 2
    with pytest.raises(ConflictError):
        save_workspace(db, payload, rev, "TESTADMIN", "Oude wijziging")
    wrong = dict(saved)
    wrong["employees"] = []
    with pytest.raises(ValueError):
        save_workspace(db, wrong, stored_rev, "DEMO001", "Ongeoorloofde wijziging")


def test_planning_draft_and_explicit_publication(tmp_path):
    db = setup_db(tmp_path)
    payload, rev = load_workspace(db)
    result = {"status": "FEASIBLE", "assignments": [{"Personeelsnr": "DEMO001", "Datum": "2026-11-01"}],
              "open_positions": [], "summary": {"required": 1, "assigned": 1, "open": 0}}
    pid = save_plan(db, payload, rev, result, "TESTADMIN")
    assert load_plan(db, payload["year"], payload["month"], published_only=True) is None
    publish_plan(db, pid, rev, "TESTADMIN")
    published = load_plan(db, payload["year"], payload["month"], published_only=True)
    assert published["id"] == pid and published["published"]
    changed = dict(payload)
    changed["settings"] = {**payload["settings"], "min_rest_hours": 12}
    save_workspace(db, changed, rev, "TESTADMIN", "Instelling gewijzigd")
    with pytest.raises(ConflictError):
        publish_plan(db, pid, rev, "TESTADMIN")


def test_one_time_recovery_preserves_database(tmp_path):
    """Bestaande medewerker, voorkeuren en planning blijven behouden."""
    db = setup_db(tmp_path)
    add_account(db, "DEMO001", "Testcontroleur", "controleur", "ControleurSterkWachtwoord1!", "TESTADMIN")
    original, revision = load_workspace(db)
    old = authenticate(db, "TESTADMIN", "TijdelijkVoorbeeld2026!sterk")
    plan_id = save_plan(db, original, revision, {"status": "FEASIBLE", "assignments": [],
                   "open_positions": [], "summary": {"required": 0, "assigned": 0, "open": 0}}, "TESTADMIN")
    key = "een-geheim-dat-minstens-32-random-tekens-heeft-ABC123"

    with pytest.raises(ValueError, match="Herstelcode onjuist"):
        recover_admin_once(db, "TESTADMIN", "incorrect", "NogEenNieuwSterkWachtwoord2026!", key)
    with pytest.raises(ValueError, match="beheerdersaccount"):
        recover_admin_once(db, "DEMO001", key, "NogEenNieuwSterkWachtwoord2026!", key)

    recover_admin_once(db, "TESTADMIN", key, "NogEenNieuwSterkWachtwoord2026!", key)
    assert authenticate(db, "TESTADMIN", "TijdelijkVoorbeeld2026!sterk") is None
    new = authenticate(db, "TESTADMIN", "NogEenNieuwSterkWachtwoord2026!")
    assert new and not new["must_change_password"] and new["auth_hash"] != old["auth_hash"]
    assert lookup_account(db, "DEMO001") is not None
    assert load_workspace(db) == (original, revision)
    assert load_plan(db, original["year"], original["month"])["id"] == plan_id
    with pytest.raises(ValueError, match="al gebruikt"):
        recover_admin_once(db, "TESTADMIN", key, "DerdeSterkWachtwoord2026!!!", key)
    assert authenticate(db, "TESTADMIN", "NogEenNieuwSterkWachtwoord2026!")


def test_recovery_resets_lockout_without_wiping_other_data(tmp_path):
    db = setup_db(tmp_path)
    for _ in range(5):
        assert authenticate(db, "TESTADMIN", "fout") is None
    key = "een-geheel-nieuwe-lange-willekeurige-herstelcode"
    recover_admin_once(db, "TESTADMIN", key, "VolledigNieuwWachtwoord2026!", key)
    assert authenticate(db, "TESTADMIN", "VolledigNieuwWachtwoord2026!") is not None
