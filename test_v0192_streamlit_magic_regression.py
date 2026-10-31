"""Guard against a Streamlit magic-rendering regression in report warnings.

A standalone expression `st.warning(x) if cond else st.caption(x)` returns a
DeltaGenerator; Streamlit's magic processor can render that object as its
very long API help table rather than just showing the message.
"""
import ast
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app.py"


def _report_warning_loop():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        if not isinstance(node.target, ast.Name) or node.target.id != "warning":
            continue
        if not isinstance(node.iter, ast.Subscript):
            continue
        if not isinstance(node.iter.value, ast.Name) or node.iter.value.id != "report":
            continue
        if not isinstance(node.iter.slice, ast.Constant) or node.iter.slice.value != "warnings":
            continue
        return node
    raise AssertionError("De rapportagewaarschuwingenlus ontbreekt.")


def _streamlit_calls(node):
    return [
        call.func.attr
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "st"
    ]


def test_report_warnings_have_explicit_branch_not_magic_ternary():
    loop = _report_warning_loop()
    assert len(loop.body) == 1
    branch = loop.body[0]
    assert isinstance(branch, ast.If)
    assert "warning" in ast.unparse(branch.test)
    assert "gewijzigd" in ast.unparse(branch.test)
    assert "niet meegerekend" in ast.unparse(branch.test)
    assert _streamlit_calls(branch.body[0]) == ["warning"]
    assert _streamlit_calls(branch.orelse[0]) == ["caption"]
    assert not any(isinstance(n, ast.IfExp) for n in ast.walk(loop)), (
        "Geen losse conditionele expressie die DeltaGenerator laat weergeven."
    )


def test_no_top_level_magic_conditional_streamlit_message_rendering():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.IfExp):
            assert not any(name in {"warning", "caption", "error", "info", "success"}
                           for name in _streamlit_calls(node.value)), (
                "Gebruik 'if'/'else' voor Streamlit-meldingen, geen magische ternary."
            )
