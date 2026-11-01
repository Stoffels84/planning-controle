"""Test dat de oude bediening verdween zonder de nieuwe solverfunctie weg te halen."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_old_v022_ui_is_removed():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'with st.expander("🔒 Diensten vastzetten en overige heroptimaliseren (v0.22)' not in source
    assert 'partial_reopt_v022_' not in source
    assert 'reopt_editor_v022_' not in source
    assert 'REOPT_V022:' not in source


def test_v023_editor_kept_and_reoptimization_dependency_available():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'with st.expander("✏️ Handmatige roosterbewerking (v0.23)"' in source
    assert 'compile_edits(data, plan.assignments, edits, preserve)' in source
    assert 'locked_assignments=compiled["locked"]' in source
    assert 'excluded_assignments=compiled["excluded"]' in source
    assert 'expected_latest_plan_id=plan_record["id"]' in source
    assert (ROOT / 'locks_v022.py').is_file()
    assert (ROOT / 'manual_v023.py').is_file()
    assert ast.parse(source)
