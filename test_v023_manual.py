"""v0.23 — pure handmatige wijzigingen, geen OR-Tools vereist."""
from pathlib import Path
import ast

import pytest
from demo_data import build_demo
from manual_v023 import compile_edits, edit_description, regular_assignments
from locks_v022 import assignment_key


def dataset():
    data = build_demo(2026, 11)
    data["demand"] = [
        {"date": "2026-11-03", "shift_id": "V101", "required": 2},
        {"date": "2026-11-04", "shift_id": "D201", "required": 2},
    ]
    return data


def row(day="2026-11-03", shift="V101", person="DEMO001"):
    return {"Datum": day, "Dienstnummer": shift, "Personeelsnr": person}


def original():
    return [dict(row(), Soort="Reguliere dienst"),
            dict(row("2026-11-04", "D201", "DEMO002"), Soort="Reguliere dienst"),
            dict(row("2026-11-03", "TAAK:TEST", "DEMO003"), Soort="Zelfstandige taak")]


def edit(kind, source=None, target=None):
    return {"kind": kind, "source": source, "target": target}


def keys(rows):
    return {assignment_key(r) for r in rows}


def test_regular_assignments_exclude_standalone():
    assert regular_assignments(original()) == [row(), row("2026-11-04", "D201", "DEMO002")]


def test_add_preserves_existing_by_default():
    result = compile_edits(dataset(), original(), [edit("add", target=row(person="DEMO004"))])
    assert keys(result["locked"]) == keys([row(), row(person="DEMO004"), row("2026-11-04", "D201", "DEMO002")])
    assert result["excluded"] == []
    assert result["original_preserved"] == 2


def test_add_without_preserve_only_locks_new():
    result = compile_edits(dataset(), original(), [edit("add", target=row(person="DEMO004"))], False)
    assert result["locked"] == [row(person="DEMO004")]
    assert result["original_preserved"] == 0


def test_remove_excludes_person_slot_but_keeps_other():
    result = compile_edits(dataset(), original(), [edit("remove", source=row())])
    assert result["excluded"] == [row()]
    assert result["locked"] == [row("2026-11-04", "D201", "DEMO002")]


def test_remove_without_preserve_locks_nothing():
    result = compile_edits(dataset(), original(), [edit("remove", source=row())], False)
    assert result["excluded"] == [row()]
    assert result["locked"] == []


def test_replace_forbids_old_and_locks_replacement():
    result = compile_edits(dataset(), original(), [edit("replace", source=row(), target=row(person="DEMO004"))])
    assert result["excluded"] == [row()]
    assert keys(result["locked"]) == keys([row(person="DEMO004"), row("2026-11-04", "D201", "DEMO002")])


def test_multiple_batched_operations():
    edits = [edit("replace", source=row(), target=row(person="DEMO004")),
             edit("remove", source=row("2026-11-04", "D201", "DEMO002")),
             edit("add", target=row("2026-11-04", "D201", "DEMO005"))]
    result = compile_edits(dataset(), original(), edits)
    assert result["edit_count"] == 3
    assert keys(result["locked"]) == keys([row(person="DEMO004"), row("2026-11-04", "D201", "DEMO005")])
    assert keys(result["excluded"]) == keys([row(), row("2026-11-04", "D201", "DEMO002")])


def test_keep_without_preserve_is_explicit_lock():
    result = compile_edits(dataset(), original(), [edit("keep", source=row())], False)
    assert result["locked"] == [row()]


@pytest.mark.parametrize("edits, match", [
    ([], "Zet eerst"),
    ([edit("nonsense")], "Onbekende"),
    ([edit("remove", source=row(person="DEMO004"))], "bestaat niet meer"),
    ([edit("add", target=row())], "bronrooster"),
    ([edit("replace", source=row(), target=row("2026-11-04", "D201", "DEMO004"))], "datum en dienstnummer"),
    ([edit("remove", source=row()), edit("keep", source=row())], "slechts één"),
    ([edit("add", target=row(person="DEMO004")), edit("add", target=row(person="DEMO004"))], "meermaals"),
    ([edit("add", target=row("2026-11-05", "V101", "DEMO004"))], "maandbehoefte"),
    ([edit("add", target=row(person="UNKNOWN"))], "niet actief"),
    ([edit("remove", source=row("2026-11-03", "TAAK:TEST", "DEMO003"))], "Zelfstandige"),
])
def test_invalid_actions_rejected(edits, match):
    with pytest.raises(ValueError, match=match):
        compile_edits(dataset(), original(), edits)


def test_two_pins_same_person_day_refused():
    edits = [edit("add", target=row("2026-11-03", "V101", "DEMO002")),
             edit("add", target=row("2026-11-03", "V101", "DEMO003"))]
    d = dataset()
    # Capaciteit 2, de oorspronkelijke personeelsbezetting telt ook mee.
    with pytest.raises(ValueError, match="meer vaste"):
        compile_edits(d, original(), edits)


def test_replacement_same_person_as_original_refused():
    with pytest.raises(ValueError, match="tegelijk verboden"):
        compile_edits(dataset(), original(), [edit("replace", source=row(), target=row())])


def test_edits_cannot_circumvent_invalid_data():
    with pytest.raises(ValueError, match="buiten"):
        compile_edits(dataset(), original(), [edit("add", target=row("2026-12-01", "V101", "DEMO004"))])


def test_invalid_preserve_flag():
    with pytest.raises(ValueError, match="Ongeldige keuze"):
        compile_edits(dataset(), original(), [edit("keep", source=row())], preserve_others="ja")


def test_descriptions():
    assert "Vervangen" in edit_description(edit("replace", source=row(), target=row(person="DEMO004")))
    assert "Verwijderen" in edit_description(edit("remove", source=row()))


def test_app_and_solver_have_v023_flow_and_no_direct_publication():
    project = Path(__file__).resolve().parents[1]
    ui = (project / "app.py").read_text(encoding="utf-8")
    solver = (project / "planner.py").read_text(encoding="utf-8")
    ast.parse(ui)
    ast.parse(solver)
    assert "Handmatige roosterbewerking (v0.23)" in ui
    assert "manual_v023_edits_" in ui
    assert 'excluded_assignments=compiled["excluded"]' in ui
    assert "store.save_plan(engine, data, st.session_state.workspace_revision" in ui
    assert "manual_edit_source" in ui
    assert "if excluded:" in solver
    assert "model.add(var == 0)" in solver
    assert "fixed_plan is not None" in solver
