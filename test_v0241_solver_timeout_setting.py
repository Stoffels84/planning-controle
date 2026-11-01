"""Regression: ordinary planner's configured timeout reaches the solver unchanged."""
import ast
from pathlib import Path

from catalog import validate_schedule_settings
from demo_data import build_demo

ROOT = Path(__file__).resolve().parents[1]


def _main_planner_time_control():
    tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    controls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != 'number_input' or not node.args:
            continue
        if isinstance(node.args[0], ast.Constant) and node.args[0].value == 'Maximale rekentijd (seconden)':
            controls.append(node)
    assert len(controls) == 1
    return controls[0]


def test_planner_input_accepts_up_to_one_hour():
    control = _main_planner_time_control()
    named = {item.arg: item.value for item in control.keywords}
    assert ast.literal_eval(named['min_value']) == 1
    assert ast.literal_eval(named['max_value']) == 3600
    assert ast.literal_eval(named['step']) == 30


def test_demo_uses_five_minute_default_for_new_demo_months():
    assert build_demo(2026, 11)['settings']['time_limit_seconds'] == 300


def test_settings_validate_full_hour_without_accepting_larger_values():
    settings = build_demo(2026, 11)['settings']
    settings['time_limit_seconds'] = 3600
    assert validate_schedule_settings(settings) == []
    settings['time_limit_seconds'] = 3601
    assert any('time_limit_seconds' in text for text in validate_schedule_settings(settings))


def test_solver_does_not_cap_normal_mode_at_120_seconds():
    tree = ast.parse((ROOT / 'planner.py').read_text(encoding='utf-8'))
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Attribute) and target.attr == 'max_time_in_seconds'
                     for target in node.targets)]
    assert len(calls) == 1
    text = ast.unparse(calls[0].value)
    assert 'settings[\'time_limit_seconds\']' in text
    assert '120' not in text
