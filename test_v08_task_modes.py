"""V0.8: achterwaartse compatibiliteit en validatie van nieuwe taakvormen."""
from copy import deepcopy
from demo_data import build_demo
from tasks_v07 import validate_tasks, need_mode, standalone_bounds, task_bounds


def base():
    d = build_demo(2026, 11)
    d['tasks'] = [{'id': 'ACTIE', 'name': 'Fictieve opdracht', 'qualification': '', 'active': True}]
    d['task_needs'] = []
    return d


def test_legacy_embedded_task_still_valid_and_keeps_default():
    d = base()
    d['task_needs'].append({'date':'2026-11-02', 'shift_id':'V101',
                            'task_id':'ACTIE','start':'07:00','end':'08:00','required':1})
    assert need_mode(d['task_needs'][0]) == 'embedded'
    assert validate_tasks(d) == []


def test_standalone_no_parent_shift_needed_even_without_demand():
    d = base()
    d['demand'] = []
    d['task_needs'] = [{'date':'2026-11-02', 'shift_id':None, 'task_id':'ACTIE',
                        'start':'09:00','end':'17:00','required':2,'mode':'standalone'}]
    assert validate_tasks(d) == []
    assert d['demand'] == []


def test_standalone_with_parent_shift_is_rejected():
    d = base()
    d['task_needs'] = [{'date':'2026-11-02', 'shift_id':'V101', 'task_id':'ACTIE',
                        'start':'09:00','end':'17:00','required':1,'mode':'standalone'}]
    assert any('geen dienstnummer' in err for err in validate_tasks(d))


def test_released_task_must_be_inside_parent_shift():
    d = base()
    d['task_needs'] = [{'date':'2026-11-02', 'shift_id':'V101', 'task_id':'ACTIE',
                        'start':'07:00','end':'08:00','required':1,'mode':'released'}]
    assert validate_tasks(d) == []
    d['task_needs'][0]['start'] = '15:00'
    d['task_needs'][0]['end'] = '16:00'
    assert validate_tasks(d)


def test_standalone_overnight_and_long_shift_rejected():
    d = base()
    d['task_needs'] = [{'date':'2026-11-03', 'shift_id':None, 'task_id':'ACTIE',
                        'start':'22:00','end':'06:00','required':1,'mode':'standalone'}]
    assert validate_tasks(d) == []
    a,b = standalone_bounds('2026-11-03','22:00','06:00')
    assert (b-a).total_seconds()/3600 == 8
    d['task_needs'][0]['end'] = '15:00'
    assert validate_tasks(d)


def test_existing_workspace_not_mutated_by_validation():
    d = base()
    d['task_needs'] = [{'date':'2026-11-02', 'shift_id':'V101', 'task_id':'ACTIE',
                        'start':'07:00','end':'08:00','required':1}]
    snapshot = deepcopy(d)
    assert validate_tasks(d) == []
    assert snapshot == d
