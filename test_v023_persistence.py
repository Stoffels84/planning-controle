"""v0.23: een andere planner mag de bronversie niet ongemerkt vervangen."""
import pytest
from store import (get_engine, initialize, initialize_months, list_month_workspaces,
                   load_month_workspace, save_plan, load_plan, publish_plan, ConflictError)


def test_manual_edit_save_only_when_source_is_latest(tmp_path):
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path / 'v023.sqlite'}")
    initialize(engine, 'ROOT', 'EenBeheerdersWachtwoordVanVeertienTekens!')
    initialize_months(engine)
    item = list_month_workspaces(engine)[0]
    state, revision = load_month_workspace(engine, item['year'], item['month'])
    base = {'status': 'FEASIBLE', 'summary': {'open': 0}, 'assignments': [], 'open_positions': []}
    source = save_plan(engine, state, revision, base, 'ROOT')
    publish_plan(engine, source, revision, 'ROOT')
    edited = {**base, 'summary': {'open': 0, 'manual_edit_source': source}}
    new_id = save_plan(engine, state, revision, edited, 'ROOT', expected_latest_plan_id=source)
    assert new_id != source
    assert load_plan(engine, item['year'], item['month'], published_only=True)['id'] == source
    with pytest.raises(ConflictError, match='nieuwere planversie'):
        save_plan(engine, state, revision, edited, 'ROOT', expected_latest_plan_id=source)
    assert load_plan(engine, item['year'], item['month'])['id'] == new_id
