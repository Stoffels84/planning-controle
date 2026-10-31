"""CP-SAT-proefmodel voor maandelijkse controleursplanning.

Dit is GEEN gevalideerde implementatie van de arbeidsregels van De Lijn.
Dekt o.a. bezetting, maandelijkse urenlimieten, individuele inzetbaarheid,
rust per dienstovergang, verboden overgangen, maximum categoriedienstreeksen,
zachte urenstreefdoelen en zachte wensen.
Niet gedekt: vorige/volgende maand, verlofsaldi, taken, verplaatsingen,
weekendpatronen, aparte wettelijke toetsing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import combinations

from ortools.sat.python import cp_model

from catalog import (is_unavailable_during, profile, settings_with_defaults, transition_code,
                     validate_employee, validate_shift, validate_schedule_settings)
from extras import preference_type, rest_blocked_during, validate_extras


@dataclass
class PlanResult:
    status: str
    assignments: list[dict]
    open_positions: list[dict]
    summary: dict


def minutes_between(start: str, end: str) -> int:
    sh, sm = (int(x) for x in start.split(":"))
    eh, em = (int(x) for x in end.split(":"))
    a, b = sh * 60 + sm, eh * 60 + em
    return (b - a) % (24 * 60) or (24 * 60)


def get_slot_bounds(day: str, shift: dict) -> tuple[datetime, datetime]:
    d = date.fromisoformat(day)
    sh, sm = (int(x) for x in shift["start"].split(":"))
    start = datetime(d.year, d.month, d.day, sh, sm)
    return start, start + timedelta(minutes=minutes_between(shift["start"], shift["end"]))


def validate_dataset(data: dict) -> list[str]:
    errors = []
    if not all(k in data for k in ("employees", "shifts", "demand", "settings", "year", "month", "preferences")):
        return ["Gegevensbestand mist verplichte onderdelen."]
    ids = [s["id"] for s in data["shifts"]]
    eids = [e["id"] for e in data["employees"]]
    if len(ids) != len(set(ids)) or len(eids) != len(set(eids)):
        errors.append("Dienstnummers en personeelsnummers moeten uniek zijn.")
    errors.extend(validate_schedule_settings(data["settings"]))
    shiftmap = {s["id"]: s for s in data["shifts"]}
    for s in data["shifts"]:
        errors.extend(validate_shift(s))
    for employee in data["employees"]:
        errors.extend(validate_employee(employee, set(ids)))
    reqkeys = []
    for s in data["shifts"]:
        try:
            if minutes_between(s["start"], s["end"]) > 16 * 60:
                errors.append(f"Dienst {s['id']} duurt langer dan 16 uur; controleer de uren.")
        except Exception:
            errors.append(f"Ongeldige uren voor dienst {s['id']}.")
    for r in data["demand"]:
        key = (r["date"], r["shift_id"])
        reqkeys.append(key)
        try:
            d = date.fromisoformat(r["date"])
            if (d.year, d.month) != (int(data["year"]), int(data["month"])):
                errors.append(f"Dienstbehoefte {r['date']} valt buiten de planningsmaand.")
        except ValueError:
            errors.append(f"Ongeldige datum: {r['date']}.")
        if r["shift_id"] not in shiftmap:
            errors.append(f"Onbekend dienstnummer: {r['shift_id']}.")
        else:
            if not shiftmap[r["shift_id"]].get("active", True):
                errors.append(f"Dienst {r['shift_id']} is niet actief. Verwijder deze uit de maandbehoefte of activeer de dienst.")
            if r["required"] != shiftmap[r["shift_id"]]["required"]:
                errors.append(f"Bezetting voor dienst {r['shift_id']} wijkt af van de vaste dienstbezetting. Pas het dienstenbeheer aan.")
        if not isinstance(r["required"], int) or r["required"] < 0:
            errors.append(f"Ongeldige vereiste bezetting voor {r['shift_id']}.")
    if len(reqkeys) != len(set(reqkeys)):
        errors.append("Dubbele dienstbehoeften (zelfde datum en dienstnummer).")
    for p in data["preferences"]:
        if p["employee_id"] not in eids:
            errors.append(f"Voorkeur verwijst naar onbekende controleur: {p['employee_id']}.")
    errors.extend(validate_extras(data))
    return errors


def solve_month(data: dict) -> PlanResult:
    errors = validate_dataset(data)
    if errors:
        raise ValueError("\n".join(errors))

    employees = [profile(e) for e in data["employees"] if e.get("active", True)]
    shifts = {s["id"]: s for s in data["shifts"]}
    slots = sorted([r for r in data["demand"] if r["required"] > 0], key=lambda r:(r["date"],r["shift_id"]))
    if not employees:
        return PlanResult("Geen beschikbare controleurs", [],
                          [{"Datum": r["date"], "Dienstnummer": r["shift_id"],
                            "Categorie": shifts[r["shift_id"]]["category"], "Open plaatsen": r["required"]} for r in slots],
                          {"required": sum(r["required"] for r in slots), "assigned": 0,
                           "open": sum(r["required"] for r in slots), "solver": "n.v.t."})
    if not slots:
        return PlanResult("Geen dienstbehoefte", [], [], {"required": 0, "assigned": 0, "open": 0, "solver": "n.v.t."})

    model = cp_model.CpModel()
    x: dict[tuple[int, int], cp_model.IntVar] = {}
    vacancy: dict[int, cp_model.IntVar] = {}
    staff_day = defaultdict(list)
    employee_vars = defaultdict(list)
    weekend_vars = defaultdict(list)
    pref_penalty_terms = []
    all_assigned = []
    settings = settings_with_defaults(data["settings"])

    preferences_by_employee = defaultdict(list)
    for pref in data["preferences"]:
        preferences_by_employee[pref["employee_id"]].append(pref)
    credit_entries = data.get("hour_credits", [])
    for ri, req in enumerate(slots):
        sh = shifts[req["shift_id"]]
        d = date.fromisoformat(req["date"])
        eligible = []
        interval_start, interval_end = get_slot_bounds(req["date"], sh)
        for ei, emp in enumerate(employees):
            if sh["category"] in emp.get("blocked_categories", []):
                continue
            if sh["id"] in emp.get("blocked_shifts", []):
                continue
            if d.weekday() in emp.get("blocked_weekdays", []):
                continue
            if is_unavailable_during(emp, interval_start, interval_end):
                continue
            if rest_blocked_during(emp, interval_start, interval_end, credit_entries):
                continue
            var = model.new_bool_var(f"x_{ei}_{ri}")
            x[ei, ri] = var
            eligible.append(var)
            all_assigned.append(var)
            staff_day[ei, req["date"]].append(var)
            employee_vars[ei].append((ri, var))
            if d.weekday() >= 5:
                weekend_vars[ei].append(var)
            for pref in preferences_by_employee[emp["id"]]:
                kind = preference_type(pref)
                priority = int(pref["priority"])
                if kind == "free_day" and pref["date"] == req["date"]:
                    pref_penalty_terms.append(10 * priority * var)
                elif kind == "weekly_free" and pref["weekday"] == d.weekday():
                    pref_penalty_terms.append(10 * priority * var)
                elif kind == "category":
                    match = sh["category"] == pref["category"]
                    if (pref["direction"] == "avoid" and match) or (pref["direction"] == "prefer" and not match):
                        pref_penalty_terms.append(3 * priority * var)
                elif kind == "shift":
                    match = sh["id"] == pref["shift_id"]
                    if (pref["direction"] == "avoid" and match) or (pref["direction"] == "prefer" and not match):
                        pref_penalty_terms.append(3 * priority * var)
            preferred_cat = emp.get("preferred_category", "Geen")
            if preferred_cat not in ("Geen", sh["category"]):
                pref_penalty_terms.append(var)

        open_var = model.new_int_var(0, req["required"], f"open_{ri}")
        vacancy[ri] = open_var
        model.add(sum(eligible) + open_var == req["required"])

    for vars_today in staff_day.values():
        model.add(sum(vars_today) <= 1)

    # Een gewenste werkdag is een zachte voorkeur: geen garantie op inzet.
    for ei, emp in enumerate(employees):
        for pref in preferences_by_employee[emp["id"]]:
            if preference_type(pref) == "work_day":
                assigned_that_day = sum(staff_day.get((ei, pref["date"]), []))
                pref_penalty_terms.append(10 * int(pref["priority"]) * (1 - assigned_that_day))

    # Rust en opeenvolging op werkelijke tijdstippen, ook als een dienst
    # over middernacht loopt. Overgangsverboden gelden voor aansluitende
    # KALENDERdagen; een vrije kalenderdag onderbreekt de dienstreeks.
    bounds = [get_slot_bounds(r["date"], shifts[r["shift_id"]]) for r in slots]
    for ei, items in employee_vars.items():
        emp = employees[ei]
        for (i, va), (j, vb) in combinations(items, 2):
            a_start, a_end = bounds[i]
            b_start, b_end = bounds[j]
            if (b_start, j) < (a_start, i):
                a_start, a_end, b_start, b_end = b_start, b_end, a_start, a_end
                prev_i, next_i = j, i
            else:
                prev_i, next_i = i, j
            c_prev = shifts[slots[prev_i]["shift_id"]]["category"]
            c_next = shifts[slots[next_i]["shift_id"]]["category"]
            pair = transition_code(c_prev, c_next)
            effective_rest = max(float(settings["min_rest_hours"]),
                                 float(emp["min_rest_hours"] or 0),
                                 float(settings["transition_rest_hours"].get(pair, 0)))
            forbidden = b_start < a_end + timedelta(hours=effective_rest)
            adjacent = (date.fromisoformat(slots[next_i]["date"]) -
                        date.fromisoformat(slots[prev_i]["date"])).days == 1
            if adjacent and (pair in settings["blocked_transitions"] or pair in emp["blocked_transitions"]):
                forbidden = True
            if forbidden:
                model.add(va + vb <= 1)
            if adjacent:
                for pref in preferences_by_employee[emp["id"]]:
                    if (preference_type(pref) == "avoid_transition"
                            and pref["transition"] == pair):
                        together = model.new_bool_var(f"wish_pair_{ei}_{i}_{j}_{pair}")
                        model.add(together <= va)
                        model.add(together <= vb)
                        model.add(together >= va + vb - 1)
                        pref_penalty_terms.append(10 * int(pref["priority"]) * together)

    first = date(int(data["year"]), int(data["month"]), 1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    days = [(first + timedelta(days=i)).isoformat() for i in range((next_month - first).days)]
    for ei, emp in enumerate(employees):
        # Max. aaneengesloten kalenderdagen met dezelfde categorie.
        # Alleen als elke dag van het venster die categorie krijgt, is
        # sprake van een overschreden reeks.
        for cat in ("Vroeg", "Dag", "Laat", "Nacht"):
            limits = [n for n in (settings["max_category_run"].get(cat),
                                   emp["max_category_run"].get(cat)) if n is not None]
            if not limits:
                continue
            max_run = min(limits)
            by_day = defaultdict(list)
            for ri, var in employee_vars[ei]:
                if shifts[slots[ri]["shift_id"]]["category"] == cat:
                    by_day[slots[ri]["date"]].append(var)
            for start_idx in range(max(0, len(days)-max_run)):
                window = days[start_idx:start_idx+max_run+1]
                model.add(sum(v for day in window for v in by_day.get(day, [])) <= max_run)
        limit = emp.get("max_consecutive") or int(settings["max_consecutive"])
        limit = int(limit)
        if limit <= 0:
            raise ValueError("Maximum opeenvolgende werkdagen moet groter dan nul zijn.")
        for start in range(0, max(0, len(days) - limit)):
            in_window = [v for day in days[start:start+limit+1] for v in staff_day.get((ei, day), [])]
            model.add(sum(in_window) <= limit)
        max_mins = int(emp["max_month_hours"] * 60)
        model.add(sum(minutes_between(shifts[slots[ri]["shift_id"]]["start"], shifts[slots[ri]["shift_id"]]["end"]) * var for ri, var in employee_vars[ei]) <= max_mins)

    # Eenvoudige spreiding: afwijking van gemiddelde aantal diensten + weekenddiensten.
    total = sum(all_assigned)
    fairness = []
    staff_count = len(employees)
    for ei in range(len(employees)):
        count = sum(var for _, var in employee_vars[ei])
        dev = model.new_int_var(0, len(slots) * staff_count * 20, f"diff_{ei}")
        model.add_abs_equality(dev, staff_count * count - total)
        fairness.append(dev)
    # Afwijking t.o.v. individueel zacht urendoel (minuten), nooit een
    # verplicht minimum. Hierdoor blijft gedeeltelijke planning mogelijk.
    hours_deviations = []
    for ei, emp in enumerate(employees):
        credits = sum(float(c["hours"]) for c in credit_entries if c["employee_id"] == emp["id"])
        target = int(round((float(emp.get("target_month_hours", 0)) - credits) * 60))
        if float(emp.get("target_month_hours", 0)) <= 0:
            continue
        # Geregistreerde uren verlagen het nog te plannen streefdoel,
        # maar veroorzaken geen automatische wettelijke urensaldo-overdracht.
        target = max(-15000, target)
        worked = sum(minutes_between(shifts[slots[ri]["shift_id"]]["start"],
                                     shifts[slots[ri]["shift_id"]]["end"]) * var
                     for ri, var in employee_vars[ei])
        deviation = model.new_int_var(0, 60000, f"hours_deviation_{ei}")
        model.add_abs_equality(deviation, worked - target)
        hours_deviations.append(deviation)
    total_weekends = sum(v for vals in weekend_vars.values() for v in vals)
    for ei in range(len(employees)):
        dev = model.new_int_var(0, len(slots) * staff_count * 20, f"weekend_{ei}")
        model.add_abs_equality(dev, staff_count * sum(weekend_vars[ei]) - total_weekends)
        fairness.append(dev)

    # Groot genoeg voor lexicografische voorrang van dekking boven zachte scores.
    # Bovenbound voor de zachte wensen en abs-afwijkingen bij het maximaal aantal posten.
    needed = sum(r["required"] for r in slots)
    pref_weight = int(settings["preference_weight"])
    fair_weight = int(settings["fairness_weight"])
    hours_weight = int(settings["hours_weight"])
    # Voor dekking voorrang op ALLE zachte voorkeuren: ruime bovengrens
    # op gewenste werkdagen, categorieën, diensten en overgangswensen.
    preference_bound = 30 * max(1, len(data["preferences"])) * max(1, needed) + needed
    covering_cost = (1 + pref_weight * preference_bound
                     + fair_weight * (2 * staff_count * staff_count * needed)
                     + hours_weight * (60000 * staff_count))
    model.minimize(covering_cost * sum(vacancy.values())
                   + pref_weight * sum(pref_penalty_terms)
                   + fair_weight * sum(fairness)
                   + hours_weight * sum(hours_deviations))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(settings["time_limit_seconds"])
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return PlanResult(status_name, [], [], {"required": sum(r["required"] for r in slots), "assigned": 0,
                                                        "open": None, "solver": status_name})

    assigned_rows = []
    open_rows = []
    for ri, req in enumerate(slots):
        sh = shifts[req["shift_id"]]
        for ei, emp in enumerate(employees):
            var = x.get((ei, ri))
            if var is not None and solver.value(var):
                assigned_rows.append({"Datum": req["date"], "Dienstnummer": sh["id"],
                                      "Categorie": sh["category"], "Begin": sh["start"], "Einde": sh["end"],
                                      "Controleur": emp["name"], "Personeelsnr": emp["id"],
                                      "Beginlocatie": sh.get("start_location", sh.get("location", "")),
                                      "Eindlocatie": sh.get("end_location", sh.get("location", "")),
                                      "Uren": round(minutes_between(sh["start"], sh["end"]) / 60, 2)})
        vacant = solver.value(vacancy[ri])
        if vacant:
            open_rows.append({"Datum": req["date"], "Dienstnummer": sh["id"], "Categorie": sh["category"], "Open plaatsen": vacant})

    required = sum(r["required"] for r in slots)
    return PlanResult(status_name, assigned_rows, open_rows,
                      {"required": required, "assigned": len(assigned_rows), "open": required - len(assigned_rows),
                       "solver": status_name, "seconds": round(solver.wall_time, 2),
                       "objective": round(solver.objective_value, 2),
                       "best_bound": round(solver.best_objective_bound, 2)})
