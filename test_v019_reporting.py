"""v0.19: published-only descriptive reports and least-privilege access."""
from copy import deepcopy
from datetime import date
import pytest

from demo_data import build_demo
from report_v019 import build_report, safe_excel_rows
from store import (get_engine, initialize, initialize_months, add_account,
                   list_month_workspaces, load_month_workspace, save_plan,
                   publish_plan, report_published_window, create_month_workspace)


def row(eid: str, day: str, shift: str = 'V101', category: str = 'Vroeg', hours: float = 8):
    return {'Personeelsnr': eid, 'Datum': day, 'Dienstnummer': shift,
            'Categorie': category, 'Uren': hours}


def sample():
    data = build_demo(2026, 11)
    data['employees'] = [
        {'id': 'A', 'name': 'Ada', 'contract_percent': 100, 'active': True},
        {'id': 'B', 'name': 'Bo', 'contract_percent': 50, 'active': True},
    ]
    data['preferences'] = [
        {'employee_id': 'A', 'type': 'free_day', 'date': '2026-11-07', 'priority': 3},
        {'employee_id': 'A', 'type': 'daily_shift', 'date': '2026-11-08', 'shift_id': 'L301', 'priority': 2},
        {'employee_id': 'B', 'type': 'free_day', 'date': '2026-11-08', 'priority': 1},
        {'employee_id': 'B', 'type': 'weekly_free', 'weekday': 6, 'priority': 3},
    ]
    data['workspace_revision'] = 2
    published = {'id': 7, 'year': 2026, 'month': 11, 'revision': 2,
                 'payload': {'status': 'FEASIBLE',
                             'summary': {'required': 4, 'assigned': 3, 'open': 1},
                             'assignments': [row('A', '2026-11-07'), row('A', '2026-11-08', 'L301', 'Laat'),
                                             row('B', '2026-11-08', 'D201', 'Dag')]}}
    return data, published


def test_totals_contract_and_weekend_wishes():
    data, plan = sample()
    report = build_report(data, plan, [plan])
    assert report['summary']['Bezetting (%)'] == 75.0
    assert report['summary']['Dienstplaatsen open'] == 1
    assert report['summary']['Spreiding weekenddagen per 100% (indicatief)'] == 0
    persons = {p['Personeelsnr']: p for p in report['persons']}
    assert persons['A']['Weekenddagen'] == 2
    assert persons['A']['Weekenddagen per 100% contract (indicatief)'] == 2
    assert persons['B']['Weekenddagen'] == 1
    assert persons['B']['Weekenddagen per 100% contract (indicatief)'] == 2
    assert persons['A']['Gewerkte weekends'] == 1
    assert persons['A']['Datumgebonden wensen beoordeeld'] == 2
    assert persons['A']['Datumgebonden wensen gerespecteerd'] == 1
    assert persons['A']['Wensen gerespecteerd (%)'] == 50.0
    assert persons['B']['Datumgebonden wensen beoordeeld'] == 1
    assert persons['B']['Wensen gerespecteerd (%)'] == 0.0
    assert sum(c['Toewijzingen'] for c in report['categories']) == 3


def test_stale_published_plan_does_not_compare_current_preferences():
    data, plan = sample()
    data['workspace_revision'] = 3
    report = build_report(data, plan, [plan])
    assert report['persons'][0]['Wensen gerespecteerd (%)'] is None
    assert any('gewijzigd' in w for w in report['warnings'])
    assert report['summary']['Bezetting (%)'] == 75.0


def test_published_zero_demand_and_unknown_assignment():
    data, plan = sample()
    plan['payload']['summary'] = {'required': 0, 'assigned': 0, 'open': 0}
    plan['payload']['assignments'] = [row('UNLISTED', '2026-11-07')]
    report = build_report(data, plan, [plan])
    assert report['summary']['Bezetting (%)'] is None
    assert report['summary']['Toewijzingen incl. taken'] == 0
    assert any('niet meegerekend' in w for w in report['warnings'])


def test_history_only_selected_versions_and_unique_months():
    data, plan = sample()
    older = deepcopy(plan)
    older.update({'year': 2026, 'month': 10, 'id': 5})
    older['payload']['assignments'] = [row('B', '2026-10-31')]
    report = build_report(data, plan, [older, older, plan])
    assert len(report['history']) == 4
    assert {r['Maand'] for r in report['history']} == {'10/2026', '11/2026'}
    assert sum(r['Weekenddagen'] for r in report['history'] if r['Maand'] == '10/2026') == 1
    assert sum(r['Weekenddagen'] for r in report['history'] if r['Maand'] == '11/2026') == 3


def test_mismatching_month_is_rejected():
    data, plan = sample()
    plan['month'] = 12
    with pytest.raises(ValueError, match='actieve maand'):
        build_report(data, plan, [plan])


def make_db(tmp_path):
    db = get_engine(f'sqlite+pysqlite:///{tmp_path / "report.sqlite"}')
    initialize(db, 'ROOT', 'LangeTestWachtwoordMetMeerDanVeertien!')
    initialize_months(db)
    add_account(db, 'A', 'Ada', 'controleur', 'ControleurWachtwoordMetVeertien!', 'ROOT')
    add_account(db, 'PLAN', 'Planner', 'planner', 'PlannerWachtwoordMetVeertien!', 'ROOT')
    return db


def publish(db, y, m, sid='V101'):
    state, rev = load_month_workspace(db, y, m)
    rec = {'status': 'FEASIBLE', 'assignments': [row('A', date(y, m, 3).isoformat(), sid)],
           'summary': {'required': 1, 'assigned': 1, 'open': 0}, 'open_positions': []}
    pid = save_plan(db, state, rev, rec, 'ROOT')
    publish_plan(db, pid, rev, 'ROOT')
    return pid


def test_report_read_only_permission_and_latest_published_only(tmp_path):
    db = make_db(tmp_path)
    first = list_month_workspaces(db)[0]
    y, m = first['year'], first['month']
    with pytest.raises(ValueError, match='rechten'):
        report_published_window(db, 'A', y, m)
    assert report_published_window(db, 'ROOT', y, m) == []
    first_id = publish(db, y, m)
    state, rev = load_month_workspace(db, y, m)
    unpublished_id = save_plan(db, state, rev, {'status': 'FEASIBLE', 'assignments': [row('A', date(y,m,3).isoformat(), 'D201')], 'summary': {'required': 1,'assigned': 1,'open': 0}, 'open_positions': []}, 'ROOT')
    assert unpublished_id > first_id
    assert report_published_window(db, 'ROOT', y, m)[0]['id'] == first_id
    newer_id = publish(db, y, m, 'N401')
    selected = report_published_window(db, 'PLAN', y, m)
    assert len(selected) == 1 and selected[0]['id'] == newer_id
    assert selected[0]['payload']['assignments'][0]['Dienstnummer'] == 'N401'
    assert load_month_workspace(db, y, m)[1] == rev


def test_report_across_months_excludes_future_and_drafts(tmp_path):
    db = make_db(tmp_path)
    first = list_month_workspaces(db)[0]
    y, m = first['year'], first['month']
    y2, m2 = (y+1,1) if m == 12 else (y,m+1)
    create_month_workspace(db, y2, m2, 'ROOT')
    first_id = publish(db, y, m)
    other_id = publish(db, y2, m2)
    assert [p['id'] for p in report_published_window(db, 'ROOT', y2, m2, 2)] == [first_id, other_id]
    assert [p['id'] for p in report_published_window(db, 'ROOT', y, m, 2)] == [first_id]
    with pytest.raises(ValueError):
        report_published_window(db, 'ROOT', y, m, 13)


def test_old_record_without_payload_is_nonfatal():
    data, plan = sample()
    plan['payload'] = None
    report = build_report(data, plan, [plan])
    assert report['summary']['Bezetting (%)'] is None
    assert report['summary']['Toewijzingen incl. taken'] == 0


def test_excel_export_sanitizes_employee_input():
    import io
    import pandas as pd
    payload = safe_excel_rows([{'Controleur': '=HYPERLINK("https://evil.example", "klik")',
                                'Personeelsnr': '-INJ', 'Diensten': 3}])
    assert payload[0]['Controleur'].startswith("'=")
    assert payload[0]['Personeelsnr'] == "'-INJ"
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        pd.DataFrame(payload).to_excel(writer, sheet_name='Per controleur', index=False)
    from openpyxl import load_workbook
    sh = load_workbook(io.BytesIO(buf.getvalue())).active
    assert sh['A2'].data_type != 'f'
    assert sh['B2'].data_type != 'f'
    assert sh['C2'].value == 3
