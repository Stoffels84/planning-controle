"""Regressietests voor de alleen-lezen managerroostermatrix."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import ast

import openpyxl
import pytest
from demo_data import build_demo
from roster_v024 import month_days, week_windows, roster_grid, staffing_grid, workbook_bytes


def fixture():
    data = build_demo(2026, 11)
    data['employees'] = [
        {'id':'A', 'name':'Ada', 'active':True, 'team':'Centrum'},
        {'id':'B', 'name':'Bram', 'active':True, 'team':'Buiten'},
        {'id':'C', 'name': '=HYPERLINK("https://example.invalid","test")', 'active':False},
    ]
    data['demand'] = [
        {'date':'2026-11-02','shift_id':'V101','required':2},
        {'date':'2026-11-02','shift_id':'D201','required':1},
        {'date':'2026-11-03','shift_id':'N401','required':1},
    ]
    payload = {'assignments':[
        {'Datum':'2026-11-02','Personeelsnr':'A','Dienstnummer':'V101', 'Soort':'Reguliere dienst', 'Begin':'06:00','Einde':'14:00'},
        {'Datum':'2026-11-02','Personeelsnr':'B','Dienstnummer':'V101', 'Soort':'Reguliere dienst', 'Begin':'06:00','Einde':'14:00'},
        {'Datum':'2026-11-02','Personeelsnr':'A','Dienstnummer':'D201', 'Soort':'Reguliere dienst'},
        {'Datum':'2026-11-03','Personeelsnr':'B','Dienstnummer':'TAAK:T01','Soort':'Zelfstandige taak'},
        {'Datum':'2026-11-02','Personeelsnr':'UNKNOWN','Dienstnummer':'N401','Soort':'Reguliere dienst'},
        {'Datum':'2026-12-02','Personeelsnr':'A','Dienstnummer':'V101','Soort':'Reguliere dienst'},
    ], 'task_assignments':[
        {'Datum':'2026-11-03','Personeelsnr':'B','Taakcode':'T01','Taak':'Fake standalone'},
        {'Datum':'2026-11-02','Personeelsnr':'A','Taakcode':'T02','Taak':'Blok', 'Begin':'12:00', 'Einde':'13:00'},
    ], 'summary':{'required':4, 'assigned':3, 'open':1}}
    return data, payload


def test_week_windows_november_and_leap():
    windows = week_windows(2026, 11)
    all_days = [d for w in windows for d in w['days']]
    assert all_days == month_days(2026, 11)
    assert windows[0]['days'][0] == '2026-11-01'
    assert windows[-1]['days'][-1] == '2026-11-30'
    assert len(month_days(2028, 2)) == 29
    assert len(month_days(2027, 2)) == 28


def test_grid_compiles_multi_shift_tasks_and_no_double_counting():
    data, payload = fixture()
    original = deepcopy((data, payload))
    grid = roster_grid(data, payload, selected_ids=['B','A'],
                       days=['2026-11-02','2026-11-03'])
    assert grid['people'] == 2
    assert grid['regular_assignments'] == 3
    assert grid['task_assignments'] == 2
    assert grid['columns'] == ['Ma 02/11','Di 03/11']
    ada, bram = grid['rows']
    assert ada['Personeelsnr'] == 'A'
    assert 'V101' in ada['Ma 02/11'] and 'D201' in ada['Ma 02/11']
    assert 'Taak T02' in ada['Ma 02/11']
    assert 'Taak T01' in bram['Di 03/11']
    assert bram['Di 03/11'].count('Taak T01') == 1
    assert (data, payload) == original


def test_grid_filters_staff_and_hides_legacy_unknowns():
    data, payload = fixture()
    result = roster_grid(data, payload, selected_ids=['B'],
                         days=['2026-11-02'], show_times=False)
    assert result['people'] == 1
    assert result['rows'][0]['Personeelsnr'] == 'B'
    assert result['rows'][0]['Ma 02/11'] == 'V101'
    assert result['regular_assignments'] == 1


def test_cover_all_staff_even_when_matrix_filtered():
    data, payload = fixture()
    rows = staffing_grid(data, payload, ['2026-11-02','2026-11-03'])
    assert rows == [
        {'Datum':'2026-11-02','Benodigd':3,'Ingevuld':3,'Open':0,'Extra':0},
        {'Datum':'2026-11-03','Benodigd':1,'Ingevuld':0,'Open':1,'Extra':0},
    ]


def test_overstaffing_not_negative_vacancies():
    data, payload = fixture()
    payload['assignments'].append({'Datum':'2026-11-02','Personeelsnr':'C','Dienstnummer':'V101','Soort':'Reguliere dienst'})
    rows = staffing_grid(data, payload, ['2026-11-02'])
    assert rows[0]['Ingevuld'] == 3
    assert rows[0]['Open'] == 0
    assert rows[0]['Extra'] == 1


@pytest.mark.parametrize('days,ids', [(['2026-12-01'],['A']), (['2026-11-02','2026-11-02'],['A']),
                                      (['2026-11-02'],['UNKNOWN']), (['2026-11-02'],['A','A'])])
def test_invalid_month_days_and_unknown_people_rejected(days, ids):
    data, payload = fixture()
    with pytest.raises(ValueError):
        roster_grid(data, payload, selected_ids=ids, days=days)


def test_empty_plan_record_is_friendly():
    data, _ = fixture()
    matrix = roster_grid(data, {'payload': None}, selected_ids=['A'], days=['2026-11-02'])
    assert matrix['rows'][0]['Ma 02/11'] == '—'


def test_export_is_valid_and_no_excel_formula_injection():
    data, payload = fixture()
    matrix = roster_grid(data, payload, selected_ids=['C'], days=['2026-11-02'])
    content = workbook_bytes(matrix, staffing_grid(data, payload, ['2026-11-02']))
    wb = openpyxl.load_workbook(BytesIO(content), read_only=False)
    assert wb.sheetnames == ['Roostermatrix','Bezetting']
    name = wb['Roostermatrix']['A2']
    assert name.data_type != 'f'
    assert name.value.startswith("'=")
    assert wb['Bezetting']['D2'].value == 0


def test_ui_is_manager_only_and_old_editor_not_duplicated():
    root = Path(__file__).resolve().parents[1]
    source = (root / 'app.py').read_text(encoding='utf-8')
    assert '"Planning", "Roostercontrole", "Optimalisatie vergelijken"' in source
    assert 'if is_manager else ["Mijn planning"' in source
    assert 'elif screen == "Roostercontrole":' in source
    assert 'with st.expander("✏️ Handmatige roosterbewerking (v0.23)"' in source
    assert 'partial_reopt_v022_' not in source
    assert ast.parse(source)
