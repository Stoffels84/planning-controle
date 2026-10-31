"""Voorbereiden en valideren van een ruil tussen twee gepubliceerde diensten.

Een ruil verandert uitsluitend twee PERSONEELStoewijzingen, niet de benodigde
bezetting, de diensturen, taken of de oorspronkelijke gepubliceerde versie.
Uitsluitend fictieve testgegevens.
"""
from __future__ import annotations
from copy import deepcopy


def regular_assignments(payload: dict) -> list[dict]:
    return [r for r in payload.get("assignments", [])
            if r.get("Soort", "Reguliere dienst") == "Reguliere dienst"
            and not str(r.get("Dienstnummer", "")).startswith("TAAK:")]


def _find(payload: dict, employee_id: str, day: str, shift_id: str) -> dict:
    matches = [r for r in regular_assignments(payload)
               if str(r["Personeelsnr"]) == employee_id and r["Datum"] == day
               and str(r["Dienstnummer"]) == str(shift_id)]
    if len(matches) != 1:
        raise ValueError("De aangevraagde dienst behoort niet (meer) tot de gepubliceerde planning.")
    return matches[0]


def make_swap_plan(published_payload: dict, initiator: str, colleague: str,
                   own_day: str, own_shift: str, their_day: str, their_shift: str) -> dict:
    if initiator == colleague or (own_day, str(own_shift)) == (their_day, str(their_shift)):
        raise ValueError("Kies twee verschillende controleurs en diensten.")
    result = deepcopy(published_payload)
    a = _find(result, initiator, own_day, own_shift)
    b = _find(result, colleague, their_day, their_shift)
    # Taken zijn expliciet aan personeelsnummers gekoppeld. Hun ruil is een
    # aparte workflow; daarom geen stilzwijgende herverdeling.
    for task in result.get("task_assignments", []):
        if ((task.get("Personeelsnr") == initiator and task.get("Datum") == own_day
             and str(task.get("Dienstnummer")) == str(own_shift)) or
            (task.get("Personeelsnr") == colleague and task.get("Datum") == their_day
             and str(task.get("Dienstnummer")) == str(their_shift))):
            raise ValueError("Een van deze diensten bevat toegewezen taken; deze ruil vereist handmatige herplanning.")
    a["Personeelsnr"], b["Personeelsnr"] = b["Personeelsnr"], a["Personeelsnr"]
    a["Controleur"], b["Controleur"] = b["Controleur"], a["Controleur"]
    return result


def verify_swap_with_solver(workspace: dict, candidate: dict, old_payload: dict) -> None:
    """Hercontroleer het VOLLEDIGE vastgepinde rooster met de bestaande CP-SAT-regels.

    Een timeout of ontbrekende solver geeft GEEN toestemming tot publicatie.
    """
    from planner import solve_month
    if candidate.get("status") not in ("FEASIBLE", "OPTIMAL"):
        raise ValueError("Alleen een eerder geldige gepubliceerde planning kan worden geruild.")
    result = solve_month(workspace, fixed_plan=candidate)
    if result.status not in ("FEASIBLE", "OPTIMAL"):
        raise ValueError("De voorgestelde ruil doorstaat de planningsregels niet (of de verificatie duurde te lang).")
    def sig(rows):
        return sorted((str(r["Datum"]), str(r["Dienstnummer"]), str(r["Personeelsnr"])) for r in rows)
    if sig(result.assignments) != sig(candidate["assignments"]):
        raise ValueError("De volledige toewijzingen konden niet ongewijzigd worden geverifieerd.")
    if result.summary.get("open", 0) > old_payload.get("summary", {}).get("open", 0):
        raise ValueError("Door de ruil ontstaan nieuwe openstaande dienstplaatsen.")
    if result.summary.get("task_open", 0) > old_payload.get("summary", {}).get("task_open", 0):
        raise ValueError("Door de ruil ontstaan extra openstaande taken.")
