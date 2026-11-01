"""v0.27 — maandgebonden proefregimes en indicatieve, controleerbare urenbalans.

Uitsluitend fictieve planningsuren: geen betaalde, wettelijke of werkelijke uren.
Alle overdrachten komen uitsluitend uit de laatst GEPUBLICEERDE versie per maand.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MAX_HISTORY = 12


def _hundredths(value) -> int:
    """Testuren veilig afronden op 0,01 u; float-fouten niet cumuleren."""
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Ongeldig urenaantal.") from None
    if not n.is_finite() or abs(n) > 100000:
        raise ValueError("Ongeldig urenaantal.")
    return int((n * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _hours(cents: int) -> float:
    return round(cents / 100, 2)


def previous_month(year: int, month: int) -> tuple[int, int]:
    if not 2020 <= year <= 2100 or not 1 <= month <= 12:
        raise ValueError("Ongeldige maand.")
    return (year - 1, 12) if month == 1 else (year, month - 1)


def validate_month_regimes(data: dict) -> list[str]:
    """Een override geldt alléén in deze kalendermaand, niet in de gedeelde catalogus."""
    values = data.get("month_hour_regimes_v027", {})
    employees = {p.get("id"): p for p in data.get("employees", []) if isinstance(p, dict)}
    if not isinstance(values, dict):
        return ["Maandelijkse urenregimes moeten een tabel zijn."]
    errors = []
    for eid, entry in values.items():
        if eid not in employees or not isinstance(entry, dict) or set(entry) != {"target_month_hours", "max_month_hours"}:
            errors.append(f"Onbekend of onvolledig urenregime: {eid}.")
            continue
        maximum, target = entry["max_month_hours"], entry["target_month_hours"]
        if type(maximum) not in (int, float) or type(target) not in (int, float):
            errors.append(f"{eid}: maanduren moeten getallen zijn.")
            continue
        try:
            mx, tg = _hundredths(maximum), _hundredths(target)
        except ValueError:
            errors.append(f"{eid}: ongeldige maanduren.")
            continue
        if not (100 <= mx <= 25000) or not (0 <= tg <= mx):
            errors.append(f"{eid}: maximaal 1–250 u en streefuren tussen 0 en het maximum.")
    return errors


def apply_month_regimes(data: dict) -> dict:
    errors = validate_month_regimes(data)
    if errors:
        raise ValueError(" ".join(errors))
    result = deepcopy(data)
    overrides = result.get("month_hour_regimes_v027", {})
    for employee in result.get("employees", []):
        if employee.get("id") in overrides:
            employee.update(overrides[employee["id"]])
    return result


def _published_totals(month_data: dict, plan: dict, employee_ids: set[str]) -> dict[str, int]:
    """Zelfstandige taken staan reeds in assignments; tel task_assignments niet nogmaals."""
    assignments = plan.get("assignments")
    if not isinstance(assignments, list) or plan.get("status") not in ("OPTIMAL", "FEASIBLE"):
        raise ValueError("Ongeldige gepubliceerde planning voor urenverrekening.")
    totals = {eid: 0 for eid in employee_ids}
    for row in assignments:
        if not isinstance(row, dict) or row.get("Personeelsnr") not in employee_ids:
            continue
        try:
            if not isinstance(row.get("Datum"), str):
                raise ValueError("Ongeldige datum")
            day = date.fromisoformat(row["Datum"])
            if (day.year, day.month) != (month_data["year"], month_data["month"]):
                raise ValueError("Datum buiten gepubliceerde maand")
            amount = _hundredths(row["Uren"])
        except (ValueError, TypeError, KeyError):
            raise ValueError("Gepubliceerde planuren bevatten ongeldige gegevens.") from None
        if not 0 <= amount <= 1600:
            raise ValueError("Gepubliceerde dienst met ongeldige uren.")
        totals[row["Personeelsnr"]] += amount
    return totals


def _registered_totals(month_data: dict, employee_ids: set[str]) -> dict[str, int]:
    totals = {eid: 0 for eid in employee_ids}
    for row in month_data.get("hour_credits", []):
        if not isinstance(row, dict) or row.get("employee_id") not in employee_ids:
            continue
        try:
            d = date.fromisoformat(row["date"])
            if (d.year, d.month) != (month_data["year"], month_data["month"]):
                raise ValueError("Credit buiten maand")
            amount = _hundredths(row["hours"])
        except (ValueError, TypeError, KeyError):
            raise ValueError("Ongeldige geregistreerde testuren in historische maand.") from None
        if not 0 <= amount <= 1600:
            raise ValueError("Geregistreerde uren buiten 0–16.")
        totals[row["employee_id"]] += amount
    return totals


def build_balance_preview(current: dict, history: list[dict]) -> dict:
    """Bereken het indicatieve startsaldo voor current vanuit een AANEENGESLOTEN reeks.

    history-rijen: {year, month, plan_id, revision, data, plan}. Als de vorige
    maand niet gepubliceerd is, verzin nooit een saldo. Bij een gat in oudere
    maanden start de simulatie opnieuw bij de oudste beschikbare aaneengesloten
    gepubliceerde maand met het expliciet ingestelde handmatige startsaldo.
    """
    current = apply_month_regimes(current)
    identities = {p["id"]: p for p in current.get("employees", [])}
    period = (current["year"], current["month"])
    prior = sorted((r for r in history if (r["year"], r["month"]) < period),
                   key=lambda x: (x["year"], x["month"]), reverse=True)
    chain = []
    cursor = previous_month(*period)
    seen = set()
    for r in prior:
        key = r["year"], r["month"]
        if key in seen:
            continue
        seen.add(key)
        if key == cursor and len(chain) < MAX_HISTORY:
            chain.append(r)
            cursor = previous_month(*cursor)
        elif key < cursor:
            break
    chain.reverse()
    warnings = []
    if any(row.get("plan_revision", row["revision"]) != row["revision"] for row in chain):
        warnings.append("Een eerdere gepubliceerde planning hoort bij verouderde maandgegevens. "
                        "Herbereken/publiceer die maand of corrigeer de historische uren vóór saldo-overdracht.")
        chain = []
    if not chain:
        warnings.append("De onmiddellijk vorige maand is niet gepubliceerd: geen automatisch startsaldo beschikbaar.")
    else:
        warnings.append("De reeks begint bij een handmatig TESTstartsaldo uit het controleursprofiel; "
                        "controleer deze basis vóór gebruik. Dit is geen officieel urensaldo.")
    state = {eid: _hundredths(emp.get("opening_hour_balance", 0)) for eid, emp in identities.items()}
    history_rows = []
    sources = []
    usable = {eid: True for eid in identities}
    for record in chain:
        historical = apply_month_regimes(record["data"])
        if (historical["year"], historical["month"]) != (record["year"], record["month"]):
            raise ValueError("Historische maandgegevens komen niet overeen met planversie.")
        hours = _published_totals(historical, record["plan"], set(identities))
        credits = _registered_totals(historical, set(identities))
        historical_people = {e["id"]: e for e in historical["employees"]}
        sources.append({"year": record["year"], "month": record["month"],
                        "plan_id": record["plan_id"], "revision": record["revision"]})
        for eid, person in identities.items():
            hp = historical_people.get(eid)
            if hp is None:
                usable[eid] = False
                continue
            target = _hundredths(hp.get("target_month_hours", 0))
            if target <= 0:
                usable[eid] = False
                continue
            opening = state[eid]
            closing = opening + hours[eid] + credits[eid] - target
            history_rows.append({"Maand": f"{record['month']:02d}/{record['year']}",
                                 "Personeelsnr": eid, "Controleur": person.get("name", eid),
                                 "Startsaldo": _hours(opening), "Planuren": _hours(hours[eid]),
                                 "Geregistreerde uren": _hours(credits[eid]),
                                 "Streefuren": _hours(target), "Eindsaldo": _hours(closing),
                                 "Planversie": record["plan_id"]})
            state[eid] = closing
    eligible = {eid: _hours(state[eid]) for eid, ok in usable.items() if ok and chain}
    missing = set(identities) - set(eligible)
    if missing and chain:
        warnings.append(f"Voor {len(missing)} controleur(s) ontbreekt een historische maand of streefuren; "
                        "geen automatisch saldo voor die personen.")
    rows = [{"Personeelsnr": eid, "Controleur": p.get("name", eid),
             "Arbeidsregime (%)": p.get("contract_percent"),
             "Maximaal deze maand": p.get("max_month_hours"),
             "Streefuren deze maand": p.get("target_month_hours"),
             "Automatisch startsaldo": eligible.get(eid)}
            for eid, p in identities.items()]
    return {"eligible": eligible, "rows": rows, "history": history_rows,
            "sources": sources, "warnings": warnings, "available": bool(eligible)}


def apply_balance_to_solver(data: dict, balances: dict[str, float]) -> dict:
    result = apply_month_regimes(data)
    if not balances:
        raise ValueError("Geen gevalideerd automatisch startsaldo beschikbaar.")
    for person in result["employees"]:
        # Gebruik geen ongerelateerde handmatige startsaldi voor mensen
        # voor wie geen gecontroleerd historisch saldo beschikbaar is.
        person["opening_hour_balance"] = balances.get(person["id"], 0.0)
    result["settings"]["use_opening_balance"] = True
    return result
