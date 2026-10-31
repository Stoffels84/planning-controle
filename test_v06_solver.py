"""Wordt uitgevoerd op Streamlit/lokaal met Google OR-Tools geïnstalleerd."""
import pytest
pytest.importorskip('ortools')

from demo_data import build_demo
from planner import solve_month


def setup(days, category='Dag', start='09:00', end='17:00'):
    data = build_demo(2026,11)
    one = data['employees'][0]
    one.update({'blocked_categories': [], 'blocked_weekdays':[], 'blocked_periods':[],
                'max_consecutive': None, 'max_month_hours': 240, 'target_month_hours':0,
                'rest_mode':'automatic', 'max_category_run':{}, 'blocked_transitions':[]})
    data['employees'] = [one]
    data['shifts'] = [{'id':'S1', 'name':'Test S1','category':category,
                       'start':start, 'end':end,'required':1,'active':True}]
    data['demand'] = [{'date':d,'shift_id':'S1','required':1} for d in days]
    data['preferences'] = []
    data['settings'].update({'min_rest_hours':0, 'max_consecutive':7,
                             'fairness_weight':0,'preference_weight':0,
                             'hours_weight':0,'time_limit_seconds':5})
    return data


def test_hard_max_weekend_days_and_month_category_count():
    data = setup(['2026-11-07','2026-11-08','2026-11-14'])
    assert solve_month(data).summary['assigned'] == 3
    data['settings']['max_weekend_days'] = 2
    assert solve_month(data).summary['assigned'] == 2
    data['employees'][0]['max_month_categories'] = {'Dag':1}
    assert solve_month(data).summary['assigned'] == 1


def test_count_distinct_worked_weekends():
    data = setup(['2026-11-07','2026-11-08','2026-11-14'])
    data['employees'][0]['max_worked_weekends'] = 1
    assert solve_month(data).summary['assigned'] == 2


def test_protected_weekend_blocks_friday_night():
    data = setup(['2026-11-13','2026-11-20'], category='Nacht', start='22:00', end='06:00')
    data['employees'][0]['protected_weekends'] = ['2026-11-14']
    result = solve_month(data)
    assert result.summary['assigned'] == 1
    assert result.assignments[0]['Datum'] == '2026-11-20'


def test_category_target_stays_soft():
    data = setup(['2026-11-10','2026-11-11'])
    data['employees'][0]['target_month_categories'] = {'Dag': 3}
    data['settings']['preference_weight'] = 1
    assert solve_month(data).summary['assigned'] == 2
