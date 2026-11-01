"""Regression: v0.27 Urenbalans crashed on missing target_month_hours."""
import ast
from pathlib import Path

from demo_data import build_demo
from hours_v027 import apply_month_regimes
import catalog

APP = Path(__file__).resolve().parents[1] / 'app.py'


def test_legacy_demo_missing_target_is_handled_by_profile_defaults():
    raw = build_demo(2026, 11)
    assert 'target_month_hours' not in raw['employees'][0]
    current = apply_month_regimes(raw)
    shown = catalog.profile(current['employees'][0])
    original = catalog.profile(raw['employees'][0])
    assert float(shown['max_month_hours']) == 176.0
    assert float(shown['target_month_hours']) == 0.0
    assert float(original['target_month_hours']) == 0.0
    assert 'target_month_hours' not in raw['employees'][0]  # no database mutation


def test_hour_balance_ui_uses_profile_defaults_before_reading_hours():
    tree = ast.parse(APP.read_text(encoding='utf-8'))
    # The Streamlit UI must wrap both current and global profiles in catalog.profile.
    assigned = {node.targets[0].id: node.value for node in ast.walk(tree)
                if isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ('employee', 'global_profile')}
    assert isinstance(assigned.get('employee'), ast.Call)
    assert isinstance(assigned.get('employee').func, ast.Attribute)
    assert assigned.get('employee').func.attr == 'profile'
    assert isinstance(assigned.get('global_profile'), ast.Call)
    assert isinstance(assigned.get('global_profile').func, ast.Attribute)
    assert assigned.get('global_profile').func.attr == 'profile'
