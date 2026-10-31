"""Defensive regression tests for a real v0.19 report failure on Streamlit."""
from copy import deepcopy
from datetime import date
from test_v019_reporting import sample, make_db, publish, row
from report_v019 import build_report
from store import create_month_workspace, report_published_window, list_month_workspaces


def test_bad_contracts_and_non_list_wishes_do_not_hide_report():
    data, published = sample()
    data['employees'][0]['contract_percent'] = 'abc%'
    data['preferences'] = None
    result = build_report(data, published, [published])
    assert result['summary']['Bezetting (%)'] == 75.0
    assert result['persons'][0]['Weekenddagen per 100% contract (indicatief)'] is None
    assert any('arbeidsregime' in warning for warning in result['warnings'])


def test_report_ignores_malformed_historical_items_and_employee_list():
    data, published = sample()
    result = build_report(data, published, [None, {}, published, published])
    assert len(result['history']) == 2
    data['employees'] = None
    result = build_report(data, published, [published])
    assert result['persons'] == []
    assert result['summary']['Toewijzingen incl. taken'] == 0


def test_published_window_exact_at_year_transition(tmp_path):
    db = make_db(tmp_path)
    first = list_month_workspaces(db)[0]
    yy, mm = first['year'], first['month']
    # Ensure the last month of a year can be compared with the first of the next.
    for y, m in ((2026, 11), (2026, 12), (2027, 1), (2027, 2)):
        if (y, m) != (yy, mm):
            try:
                create_month_workspace(db, y, m, 'ROOT')
            except ValueError as e:
                if 'bestaat al' not in str(e):
                    raise
        publish(db, y, m)
    rows = report_published_window(db, 'ROOT', 2027, 1, months_back=3)
    assert [(r['year'], r['month']) for r in rows] == [(2026, 11), (2026, 12), (2027, 1)]
    assert len(report_published_window(db, 'ROOT', 2027, 1, months_back=1)) == 1
    assert [(r['year'], r['month']) for r in report_published_window(db, 'ROOT', 2026, 12, months_back=2)] == [(2026, 11), (2026, 12)]
