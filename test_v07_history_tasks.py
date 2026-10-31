"""Zuivere regressietests voor historiek en v0.7-taakinvoer."""
from copy import deepcopy

from demo_data import build_demo
from history_v07 import aggregate_history, apply_published_history
from tasks_v07 import validate_tasks
from store import (get_engine, initialize, load_workspace, save_workspace,
                   save_plan, publish_plan, published_plans_before)


def test_aggregate_history_skips_unknown_staff_and_deduplicates_weekend_days():
    plans = [dict(payload={'assignments': [
        {'Datum':'2026-09-05', 'Personeelsnr':'A', 'Categorie':'Dag'},
        {'Datum':'2026-09-05', 'Personeelsnr':'A', 'Categorie':'Dag'},
        {'Datum':'2026-09-06', 'Personeelsnr':'A', 'Categorie':'Laat'},
        {'Datum':'2026-09-12', 'Personeelsnr':'Z', 'Categorie':'Vroeg'},
    ]})]
    out = aggregate_history(plans, ['A', 'B'])
    assert out['A']['weekend_days'] == 2
    assert out['A']['worked_weekends'] == 1
    assert out['B']['weekend_days'] == 0


def test_history_is_only_in_calculation_copy():
    data = build_demo(2026, 11)
    data['employees'][0]['historic_weekend_days'] = 20
    snapshot = deepcopy(data)
    derived = apply_published_history(data, {'DEMO001':{'weekend_days':4}})
    assert derived['employees'][0]['historic_weekend_days'] == 4
    assert data == snapshot


def test_readonly_published_history_ignores_concepts_current_and_duplicates(tmp_path):
    engine = get_engine(f'sqlite+pysqlite:///{tmp_path / "v07hist.sqlite3"}')
    initialize(engine, 'ROOT', 'VoorbeeldWachtwoordLang123!')
    work, revision = load_workspace(engine)
    work['year'], work['month'] = 2026, 8
    revision = save_workspace(engine, work, revision, 'ROOT', 'Augustus')
    result = lambda dt: {'status':'OPTIMAL', 'assignments':[{'Datum':dt, 'Personeelsnr':'DEMO001','Categorie':'Dag'}],
                         'open_positions':[], 'summary':{'required':1, 'assigned':1, 'open':0}}
    v1 = save_plan(engine, work, revision, result('2026-08-01'), 'ROOT')
    publish_plan(engine, v1, revision, 'ROOT')
    # Concept in dezelfde maand mag de gepubliceerde versie niet vervangen.
    save_plan(engine, work, revision, result('2026-08-02'), 'ROOT')
    work['month'] = 9
    revision = save_workspace(engine, work, revision, 'ROOT', 'September')
    v2 = save_plan(engine, work, revision, result('2026-09-05'), 'ROOT')
    publish_plan(engine, v2, revision, 'ROOT')
    work['month'] = 10
    revision = save_workspace(engine, work, revision, 'ROOT', 'Oktober')
    save_plan(engine, work, revision, result('2026-10-03'), 'ROOT') # concept, niet tellen
    found = published_plans_before(engine, 2026, 11, months_back=3)
    assert [x['id'] for x in found] == [v1, v2]
    assert sum(x['payload']['assignments'][0]['Datum'] == '2026-10-03' for x in found) == 0
    assert published_plans_before(engine, 2026, 9, 1) == [found[0]]


def test_task_validation_rejects_outside_shift_and_wrong_qualification():
    data = build_demo(2026, 11)
    data['tasks'] = [{'id':'X1','name':'Fictieve taak','qualification':'Q1','active':True}]
    data['task_needs'] = [{'date':'2026-11-02','shift_id':'V101','task_id':'X1',
                           'start':'07:00','end':'08:00','required':1}]
    assert validate_tasks(data) == []
    data['task_needs'][0]['start'] = '22:00'
    assert validate_tasks(data)
    data['task_needs'][0]['start'] = '07:00'
    data['employees'][0]['qualifications'] = ['Q1']
    assert validate_tasks(data) == []
    data['employees'][0]['qualifications'] = ['']
    assert validate_tasks(data)


def test_task_validation_night_across_midnight():
    data = build_demo(2026, 11)
    data['tasks'] = [{'id':'X1','name':'Test nacht','qualification':'','active':True}]
    data['task_needs'] = [{'date':'2026-11-03','shift_id':'N401','task_id':'X1',
                           'start':'01:00','end':'02:00','required':1}]
    assert validate_tasks(data) == []
