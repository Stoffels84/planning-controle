"""Offline regressietests: periodegrens, bronselectie en publicatiebescherming."""
from datetime import date
import pytest

from boundary_v015 import (adjacent_months, published_boundary_context,
                           with_boundary_context, validate_boundary_rows)
from store import (ConflictError, get_engine, initialize, initialize_months,
                   list_month_workspaces, create_month_workspace, load_month_workspace,
                   save_plan, publish_plan, load_plan)


def test_month_boundaries_and_validation():
    assert adjacent_months(2027, 1) == {"previous": (2026, 12), "next": (2027, 2)}
    good = {"year": 2026, "month": 12, "_boundary_assignments": [
        {"employee_id": "DEMO001", "date": "2026-11-30", "category": "Nacht",
         "start": "22:00", "end": "06:00", "source": "previous"}]}
    assert validate_boundary_rows(good) == []
    invalid = with_boundary_context(good, {"assignments": [{**good["_boundary_assignments"][0],
                                                           "date": "2026-12-01"}],
                                          "sources": {"previous": 9, "next": None}})
    assert validate_boundary_rows(invalid)
    assert good["_boundary_assignments"][0]["date"] == "2026-11-30"


def setup_months(tmp_path):
    engine = get_engine(f"sqlite+pysqlite:///{tmp_path/'boundaries.sqlite'}")
    initialize(engine, "TESTADMIN", "SterkNieuwTestWachtwoord2026!")
    initialize_months(engine)
    first = list_month_workspaces(engine)[0]
    prev = (first["year"], first["month"])
    nxt = adjacent_months(*prev)["next"]
    create_month_workspace(engine, *nxt, "TESTADMIN")
    return engine, prev, nxt


def save_sample(engine, year, month, *, marker=1, sources=None):
    state, rev = load_month_workspace(engine, year, month)
    result = {"status": "FEASIBLE", "summary": {"open": 0, "boundary_sources": sources} if sources is not None else {"open": 0},
              "assignments": [{"Personeelsnr": "DEMO001", "Datum": f"{year}-{month:02d}-01",
                               "Categorie": "Dag", "Begin": "08:00", "Einde": "16:00"}],
              "open_positions": [], "marker": marker}
    return save_plan(engine, state, rev, result, "TESTADMIN"), rev


def test_published_boundary_only_and_concept_excluded(tmp_path):
    db, prev, target = setup_months(tmp_path)
    draft, revision = save_sample(db, *prev)
    assert published_boundary_context(db, *target)["sources"]["previous"] is None
    publish_plan(db, draft, revision, "TESTADMIN")
    found = published_boundary_context(db, *target)
    assert found["sources"]["previous"] == draft
    assert found["sources"]["next"] is None
    assert found["assignments"][0]["date"] == f"{prev[0]}-{prev[1]:02d}-01"
    # Nieuw concept mag historische gepubliceerde versie niet overschrijven
    latest, _ = save_sample(db, *prev, marker=2)
    assert latest != draft
    assert published_boundary_context(db, *target)["sources"]["previous"] == draft


def test_changed_neighbour_blocks_publication(tmp_path):
    db, prev, target = setup_months(tmp_path)
    ctx = published_boundary_context(db, *target)
    p, rev = save_sample(db, *target, sources=ctx["sources"])
    old, oldrev = save_sample(db, *prev)
    publish_plan(db, old, oldrev, "TESTADMIN")
    with pytest.raises(ConflictError, match="aangrenzende"):
        publish_plan(db, p, rev, "TESTADMIN")
    # Nieuwe berekening met actuele buurmaand kan wel worden gepubliceerd
    context = published_boundary_context(db, *target)
    new, rev2 = save_sample(db, *target, sources=context["sources"])
    publish_plan(db, new, rev2, "TESTADMIN")
    assert load_plan(db, *target, published_only=True)["id"] == new
