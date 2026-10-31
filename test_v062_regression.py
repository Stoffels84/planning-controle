"""Regression: 'needed' must be calculated before fairness bound evaluation."""
import ast
from pathlib import Path


def test_needed_assigned_before_deviation_bound():
    source = (Path(__file__).resolve().parents[1] / "planner.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    solve = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "solve_month")
    needed_defs = [node.lineno for node in ast.walk(solve)
                   if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "needed" for t in node.targets)]
    assert len(needed_defs) == 1
    uses = [node.lineno for node in ast.walk(solve)
            if isinstance(node, ast.Name) and node.id == "needed" and isinstance(node.ctx, ast.Load)]
    assert uses and min(uses) > needed_defs[0]
