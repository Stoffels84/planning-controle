"""Een heroptimalisatieconcept mag een publicatie niet overschrijven."""
from store import (get_engine, initialize, initialize_months, list_month_workspaces,
                   load_month_workspace, save_plan, load_plan, publish_plan,
                   publication_preview)


def test_reoptimization_is_new_draft_without_mutating_publication(tmp_path):
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path / 'reopt_v022.sqlite'}")
    initialize(engine, 'ROOT', 'EenBeheerdersWachtwoordVanVeertienTekens!')
    initialize_months(engine)
    item = list_month_workspaces(engine)[0]
    state, rev = load_month_workspace(engine, item['year'], item['month'])
    day = f"{item['year']}-{item['month']:02d}-03"
    source_row = {'Datum': day, 'Dienstnummer': 'V101', 'Personeelsnr': 'DEMO001'}
    replacement = {'Datum': day, 'Dienstnummer': 'V101', 'Personeelsnr': 'DEMO002'}
    base = {'status': 'FEASIBLE', 'summary': {'open': 0},
            'assignments': [source_row], 'open_positions': []}
    original_id = save_plan(engine, state, rev, base, 'ROOT')
    publish_plan(engine, original_id, rev, 'ROOT')
    after = {**base, 'assignments': [replacement],
             'summary': {'open': 0, 'reoptimized_from': original_id,
                         'locked_assignments': [replacement]}}
    concept_id = save_plan(engine, state, rev, after, 'ROOT')
    assert concept_id != original_id
    assert load_plan(engine, item['year'], item['month'])['id'] == concept_id
    assert load_plan(engine, item['year'], item['month'])['published'] is False
    published = load_plan(engine, item['year'], item['month'], published_only=True)
    assert published['id'] == original_id
    assert published['payload']['assignments'] == [source_row]
    preview = publication_preview(engine, concept_id, 'ROOT')
    assert preview['last_published_id'] == original_id
    assert preview['affected_controllers'] >= 0
