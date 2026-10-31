"""Test profielopslag, isolatie, veilige vergelijking en oude werkruimte zonder v0.9-veld."""
from copy import deepcopy
from types import SimpleNamespace

from demo_data import build_demo
from optimization_v09 import (DEFAULTS, compare_row, options_for, roster_signature,
                              signature, validate_profiles, with_profile)


def test_legacy_workspace_works_without_profiles():
    data = build_demo(2026, 11)
    assert validate_profiles(data) == []
    assert len(options_for(data)) == len(DEFAULTS)


def test_custom_profiles_and_duplicate_rejected():
    data = build_demo(2026, 11)
    first = {"name": "Extra focus", "team": "Alle teams",
             "preference_weight": 25, "fairness_weight": 1, "hours_weight": 0}
    data["optimization_profiles"] = [first]
    assert validate_profiles(data) == []
    assert options_for(data)[-1]["name"] == "Extra focus"
    data["optimization_profiles"].append(dict(first, name="extra focus"))
    assert any("bestaat al" in message for message in validate_profiles(data))


def test_invalid_custom_weight_or_unknown_team_is_rejected():
    data = build_demo(2026, 11)
    data["optimization_profiles"] = [{"name": "Opslag", "team": "Onbekend",
                                      "preference_weight": 20, "fairness_weight": 101, "hours_weight": 0}]
    errors = validate_profiles(data)
    assert any("teamnaam" in m for m in errors)
    assert any("fairness_weight" in m for m in errors)


def test_profiles_only_change_soft_rules():
    data = build_demo(2026, 11)
    backup = deepcopy(data)
    before_hard = (data["settings"]["min_rest_hours"], data["settings"]["max_consecutive"])
    result = with_profile(data, DEFAULTS[2], time_limit=12)
    assert result["settings"]["preference_weight"] == DEFAULTS[2]["preference_weight"]
    assert (result["settings"]["min_rest_hours"], result["settings"]["max_consecutive"]) == before_hard
    assert result["demand"] == data["demand"]
    assert result["employees"] == data["employees"]
    assert data == backup


def test_fingerprint_catches_changed_workspace_and_published_history():
    data = build_demo(2026, 11)
    original = signature(data, [])
    data["settings"]["max_consecutive"] = 4
    assert signature(data, []) != original
    assert signature(data, [{"id": 2}]) != signature(data, [{"id": 3}])


def test_comparison_independent_of_solver_objective():
    data = build_demo(2026, 11)
    a = {"Datum": "2026-11-06", "Dienstnummer": "V101", "Personeelsnr": "DEMO001",
         "Uren": 8.0, "Categorie": "Vroeg"}
    p = SimpleNamespace(status="FEASIBLE", assignments=[a], task_assignments=[],
                        summary={"assigned": 1, "open": 3, "task_open": 1, "seconds": 1.2, "objective": 123456})
    row = compare_row(DEFAULTS[0], p, data)
    assert row["Open diensten"] == 3
    assert row["Open taken"] == 1
    assert "objective" not in row
    assert row["Vrijwensen gemist"] == 1
    p.summary["objective"] = -9090999
    assert compare_row(DEFAULTS[0], p, data) == row


def test_roster_signature_is_order_independent_and_includes_task_details():
    a = {"Datum": "2026-11-06", "Dienstnummer": "V101", "Personeelsnr": "DEMO001"}
    b = {"Datum": "2026-11-06", "Dienstnummer": "V102", "Personeelsnr": "DEMO002"}
    p = SimpleNamespace(assignments=[a, b], task_assignments=[])
    q = SimpleNamespace(assignments=[b, a], task_assignments=[])
    assert roster_signature(p) == roster_signature(q)
    q.task_assignments = [{"Datum": "2026-11-06", "Taakcode": "A", "Personeelsnr": "DEMO001",
                           "Begin": "10:00", "Einde": "11:00"}]
    assert roster_signature(p) != roster_signature(q)


def test_custom_profile_persists_without_migration(tmp_path):
    from store import get_engine, initialize, load_workspace, save_workspace
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path / 'v09.sqlite3'}")
    initialize(engine, "ROOT", "EenHeelLangFictiefWachtwoord123!")
    old, version = load_workspace(engine)
    old["optimization_profiles"] = [{"name": "Avondteam", "team": "Alle teams",
                                      "preference_weight": 40, "fairness_weight": 2,
                                      "hours_weight": 1}]
    new_version = save_workspace(engine, old, version, "ROOT", "Profiel toegevoegd")
    loaded, revision = load_workspace(engine)
    assert new_version == revision
    assert loaded["optimization_profiles"][0]["name"] == "Avondteam"
    assert validate_profiles(loaded) == []
