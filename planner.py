"""CP-SAT-proefmodel voor maandelijkse controleursplanning.

Dit is GEEN gevalideerde implementatie van de arbeidsregels van De Lijn.
Dekt o.a. bezetting, maandelijkse urenlimieten, individuele inzetbaarheid,
rust per dienstovergang, verboden overgangen, maximum categoriedienstreeksen,
zachte urenstreefdoelen en zachte wensen.
Niet gedekt: loon-/verlofsaldi, verplaatsingstijden,
weekendpatronen, aparte wettelijke toetsing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from itertools import combinations

from ortools.sat.python import cp_model

from catalog import (is_unavailable_during, profile, settings_with_defaults, transition_code,
                     validate_employee, validate_shift, validate_schedule_settings)
from extras import preference_type, rest_blocked_during, validate_extras
from policy_v06 import touches_protected_weekend, saturday_for
from tasks_v07 import task_bounds, validate_tasks, need_mode, standalone_code, standalone_bounds
from optimization_v09 import validate_profiles
from boundary_v015 import validate_boundary_rows
from locks_v022 import assignment_key, validate_locks
from manual_v023 import _validated_single


@dataclass
class PlanResult:
    status: str
    assignments: list[dict]
    open_positions: list[dict]
    summary: dict
    task_assignments: list[dict] = field(default_factory=list)
    open_tasks: list[dict] = field(default_factory=list)


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
    errors.extend(validate_tasks(data))
    errors.extend(validate_profiles(data))
    errors.extend(validate_boundary_rows(data))
    return errors


def solve_month(data: dict, fixed_plan: dict | None = None,
                locked_assignments: list[dict] | None = None,
                excluded_assignments: list[dict] | None = None) -> PlanResult:
    errors = validate_dataset(data)
    if errors:
        raise ValueError("\n".join(errors))
    if fixed_plan is not None and (locked_assignments is not None or excluded_assignments is not None):
        raise ValueError("Volledige ruilverificatie en gedeeltelijke vergrendeling mogen niet worden gecombineerd.")
    locked = validate_locks(data, locked_assignments or [])
    excluded = excluded_assignments or []
    if not isinstance(excluded, list) or len(excluded) > 500:
        raise ValueError("Er zijn te veel uitgesloten diensten.")
    excluded = [_validated_single(data, row) for row in excluded]
    if len({assignment_key(r) for r in excluded}) != len(excluded):
        raise ValueError("Dubbel uitgesloten diensttoewijzing.")
    if {assignment_key(r) for r in excluded} & {assignment_key(r) for r in locked}:
        raise ValueError("Een dienst kan niet tegelijk vastgezet en uitgesloten zijn.")

    employees = [profile(e) for e in data["employees"] if e.get("active", True)]
    shifts = {s["id"]: s for s in data["shifts"]}
    service_slots = [r for r in data["demand"] if r["required"] > 0]
    slots = list(service_slots)
    task_lookup = {t["id"]: t for t in data.get("tasks", [])}
    standalone_codes = {}
    # Zelfstandige taken werken als aparte 'dienst' in het solvermodel,
    # zonder dat ze een gewoon dienstnummer of een gewone dienstplaats krijgen.
    # Zo gelden dezelfde rust-, werkdag-, uren- en beschikbaarheidsregels.
    for ti, need in enumerate(data.get("task_needs", [])):
        if need_mode(need) != "standalone":
            continue
        code = standalone_code(ti)
        if code in shifts:
            raise ValueError("Intern taaknummer botst met een bestaand dienstnummer.")
        task = task_lookup[need["task_id"]]
        shifts[code] = {"id": code, "category": task.get("category", "Dag"),
                        "start": need["start"], "end": need["end"],
                        "name": task["name"], "active": True, "required": need["required"]}
        slots.append({"date": need["date"], "shift_id": code,
                      "required": need["required"], "_task_index": ti})
        standalone_codes[code] = ti
    slots.sort(key=lambda r: (r["date"], r["shift_id"]))
    needed = sum(r["required"] for r in slots)
    if not employees:
        service_missing = [{"Datum": r["date"], "Dienstnummer": r["shift_id"],
                            "Categorie": shifts[r["shift_id"]]["category"],
                            "Open plaatsen": r["required"]} for r in service_slots]
        task_missing = [{"Datum": n["date"], "Dienstnummer": n.get("shift_id") or "Zelfstandig",
                         "Taakcode": n["task_id"], "Taak": task_lookup[n["task_id"]]["name"],
                         "Soort": need_mode(n), "Open taakplaatsen": n["required"]}
                        for n in data.get("task_needs", [])]
        required = sum(r["required"] for r in service_slots)
        return PlanResult("Geen beschikbare controleurs", [], service_missing,
                          {"required": required, "assigned": 0, "open": required, "solver": "n.v.t.",
                           "task_required": sum(n["required"] for n in data.get("task_needs", [])),
                           "task_assigned": 0, "task_open": sum(n["required"] for n in data.get("task_needs", []))},
                          [], task_missing)
    if not slots:
        return PlanResult("Geen dienstbehoefte", [], [], {"required": 0, "assigned": 0, "open": 0, "solver": "n.v.t."})

    model = cp_model.CpModel()
    x: dict[tuple[int, int], cp_model.IntVar] = {}
    vacancy: dict[int, cp_model.IntVar] = {}
    staff_day = defaultdict(list)
    employee_vars = defaultdict(list)
    weekend_vars = defaultdict(list)
    worked_weekends = defaultdict(lambda: defaultdict(list))
    category_month_vars = defaultdict(list)
    pref_penalty_terms = []
    category_targets_penalty = []
    task_selected = {}
    task_open_vars = {}
    task_employee_intervals = defaultdict(list)
    eligible_by_slot = {}
    release_blocks = defaultdict(list)
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
            if touches_protected_weekend(emp, interval_start, interval_end):
                continue
            var = model.new_bool_var(f"x_{ei}_{ri}")
            x[ei, ri] = var
            eligible.append(var)
            all_assigned.append(var)
            staff_day[ei, req["date"]].append(var)
            employee_vars[ei].append((ri, var))
            category_month_vars[ei, sh["category"]].append(var)
            if d.weekday() >= 5:
                weekend_vars[ei].append(var)
                worked_weekends[ei][saturday_for(d).isoformat()].append(var)
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
        # Bezetting na taaktoewijzing vastleggen: tijdelijke vrijstellingen
        # kunnen extra personeel voor dezelfde dienst vereisen.
        eligible_by_slot[ri] = eligible

    for vars_today in staff_day.values():
        model.add(sum(vars_today) <= 1)

    # Taaktoewijzing: embedded telt mee, released verlaagt de operationele
    # dekking tijdelijk; standalone is een afzonderlijke daginzet.
    shift_slot = {(r["date"], r["shift_id"]): ri for ri, r in enumerate(slots)}
    for ti, need in enumerate(data.get("task_needs", [])):
        task = task_lookup[need["task_id"]]
        mode = need_mode(need)
        if mode == "standalone":
            ri = shift_slot[(need["date"], standalone_code(ti))]
            task_open_vars[ti] = vacancy[ri]
            for ei, employee in enumerate(employees):
                var = x.get((ei, ri))
                if var is None:
                    continue
                if task.get("qualification") and task["qualification"] not in employee.get("qualifications", []):
                    model.add(var == 0)
                elif task["id"] in employee.get("blocked_tasks", []):
                    model.add(var == 0)
                else:
                    task_selected[ti, ei] = var
            continue

        ri = shift_slot[(need["date"], need["shift_id"])]
        start, end = task_bounds(need["date"], need["start"], need["end"],
                                 shifts[need["shift_id"]]["start"])
        available = []
        for ei, employee in enumerate(employees):
            parent = x.get((ei, ri))
            if parent is None:
                continue
            required_qualification = task.get("qualification", "")
            if required_qualification and required_qualification not in employee.get("qualifications", []):
                continue
            if task["id"] in employee.get("blocked_tasks", []):
                continue
            assigned = model.new_bool_var(f"task_{ti}_{ei}")
            model.add(assigned <= parent)
            task_selected[ti, ei] = assigned
            task_employee_intervals[ei].append((start, end, assigned))
            available.append(assigned)
        opening = model.new_int_var(0, need["required"], f"task_open_{ti}")
        task_open_vars[ti] = opening
        model.add(sum(available) + opening == need["required"])
        if mode == "released":
            release_blocks[ri].append((start, end, available))

    for ei, blocks in task_employee_intervals.items():
        for (a, b, va), (c, d, vb) in combinations(blocks, 2):
            if a < d and c < b:
                model.add(va + vb <= 1)

    # Werkelijke minimale dienstbezetting per tijdvak. Wie tijdelijk een taak
    # buiten de reguliere bezetting uitvoert, wordt daar niet dubbel geteld.
    # Eén open-plaatsenwaarde per dienst = grootste tekort op enig tijdstip.
    for ri, req in enumerate(slots):
        people = sum(eligible_by_slot[ri])
        if "_task_index" in req:
            model.add(people + vacancy[ri] == req["required"])
            continue
        blocks = release_blocks.get(ri, [])
        if not blocks:
            model.add(people + vacancy[ri] == req["required"])
            continue
        # Extra inzet kan alleen nodig zijn als er ook daadwerkelijk iemand
        # tijdelijk vrijgesteld wordt voor een taak.
        model.add(people <= req["required"] + sum(v for _, _, vs in blocks for v in vs))
        parent_start, parent_end = get_slot_bounds(req["date"], shifts[req["shift_id"]])
        cuts = sorted({parent_start, parent_end, *(a for a, _, _ in blocks),
                       *(b for _, b, _ in blocks)})
        for a, b in zip(cuts, cuts[1:]):
            if a == b:
                continue
            currently_released = [v for x1, x2, vs in blocks if x1 < b and x2 > a for v in vs]
            model.add(people - sum(currently_released) + vacancy[ri] >= req["required"])

    # v0.15 — harde regels over de maandgrens. De gepubliceerde buurplannen
    # bevatten de EFFECTIEVE diensturen, niet de ondertussen gewijzigde catalogus.
    # Elk buurrooster is vast; alleen toekomstige toewijzingen zijn solverkeuzes.
    boundary_by_employee = defaultdict(list)
    for item in data.get("_boundary_assignments", []):
        boundary_by_employee[item["employee_id"]].append(item)
    for ei, emp in enumerate(employees):
        for past in boundary_by_employee[emp["id"]]:
            fixed_start, fixed_end = get_slot_bounds(past["date"], past)
            fixed_day = date.fromisoformat(past["date"])
            for ri, var in employee_vars[ei]:
                req = slots[ri]
                shift = shifts[req["shift_id"]]
                candidate_start, candidate_end = get_slot_bounds(req["date"], shift)
                candidate_day = date.fromisoformat(req["date"])
                if fixed_start <= candidate_start:
                    prev_start, prev_end = fixed_start, fixed_end
                    prev_day, next_day = fixed_day, candidate_day
                    prev_cat, next_cat = past["category"], shift["category"]
                else:
                    prev_start, prev_end = candidate_start, candidate_end
                    prev_day, next_day = candidate_day, fixed_day
                    prev_cat, next_cat = shift["category"], past["category"]
                pair = transition_code(prev_cat, next_cat)
                rest = max(float(settings["min_rest_hours"]),
                           float(emp["min_rest_hours"] or 0),
                           float(settings["transition_rest_hours"].get(pair, 0)))
                too_close = next_day == prev_day or max(candidate_start, fixed_start) < prev_end + timedelta(hours=rest)
                adjacent = (next_day - prev_day).days == 1
                if adjacent and (pair in settings["blocked_transitions"] or pair in emp["blocked_transitions"]):
                    too_close = True
                if too_close:
                    model.add(var == 0)

    # Daggebonden dienstwens: eenmalige bonus/penalty voor precies die datum
    # en dat dienstnummer. Niet alleen een straf voor 'de verkeerde dienst':
    # ook een volledige vrije dag geldt als niet-ingewilligde dienstwens.
    for ei, emp in enumerate(employees):
        for pref in preferences_by_employee[emp["id"]]:
            if preference_type(pref) != "daily_shift":
                continue
            matching_requests = [ri for ri, req in enumerate(slots)
                                 if "_task_index" not in req and
                                 req["date"] == pref["date"] and
                                 req["shift_id"] == pref["shift_id"]]
            if not matching_requests:
                # Een oud dienstnummer is inmiddels uit de maandbehoefte gehaald.
                # Deze verouderde wens mag de huidige berekening niet beïnvloeden.
                continue
            matching_assignments = [x[ei, ri] for ri in matching_requests if (ei, ri) in x]
            pref_penalty_terms.append(10 * int(pref["priority"]) * (1 - sum(matching_assignments)))

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

        # v0.6: maximum diensten per categorie/maand (hard) en streefwaarden (zacht).
        for cat in ("Vroeg", "Dag", "Laat", "Nacht"):
            month_count = sum(category_month_vars[ei, cat])
            bounds = [n for n in (settings["max_month_categories"].get(cat),
                                  emp["max_month_categories"].get(cat)) if n is not None]
            if bounds:
                model.add(month_count <= min(bounds))
            goal = emp["target_month_categories"].get(cat)
            if goal is not None:
                gap = model.new_int_var(0, 31, f"cat_target_{ei}_{cat}")
                model.add_abs_equality(gap, month_count - goal)
                category_targets_penalty.append(gap)

        weekend_maxima = [n for n in (settings["max_weekend_days"], emp["max_weekend_days"])
                          if n is not None]
        if weekend_maxima:
            model.add(sum(weekend_vars[ei]) <= min(weekend_maxima))
        if emp["max_worked_weekends"] is not None:
            weekend_used = []
            for saturday, assigned in worked_weekends[ei].items():
                worked = model.new_bool_var(f"worked_weekend_{ei}_{saturday}")
                model.add_max_equality(worked, assigned)
                weekend_used.append(worked)
            model.add(sum(weekend_used) <= emp["max_worked_weekends"])

    # v0.15 — opeenvolgende werkdagen en dienstcategorieën over de maandgrens.
    # Een kalenderdag met een gepubliceerde dienst telt als één gewerkte dag.
    # Er worden alleen vensters gecontroleerd die beide kanten van een grens
    # raken. Oude overtredingen in buurmaanden kunnen niet meer gewijzigd worden:
    # in dat geval verbieden we iedere extra toewijzing in het betrokken venster.
    month_first = date(int(data["year"]), int(data["month"]), 1)
    month_last = next_month - timedelta(days=1)
    for ei, emp in enumerate(employees):
        historical_days = defaultdict(set)
        for item in boundary_by_employee[emp["id"]]:
            historical_days[date.fromisoformat(item["date"])].add(item["category"])
        current_all = defaultdict(list)
        current_category = defaultdict(list)
        for ri, var in employee_vars[ei]:
            day = date.fromisoformat(slots[ri]["date"])
            current_all[day].append(var)
            current_category[day, shifts[slots[ri]["shift_id"]]["category"]].append(var)
        checks = [(int(emp.get("max_consecutive") or settings["max_consecutive"]), None)]
        for cat in ("Vroeg", "Dag", "Laat", "Nacht"):
            limits = [int(v) for v in (settings["max_category_run"].get(cat),
                                       emp["max_category_run"].get(cat)) if v is not None]
            if limits:
                checks.append((min(limits), cat))
        for limit, cat in checks:
            # Startdata binnen 7 dagen van de twee maandgrenzen; max_run <= 7.
            for boundary in (month_first, next_month):
                for offset in range(1, limit + 1):
                    window_start = boundary - timedelta(days=offset)
                    window = [window_start + timedelta(days=i) for i in range(limit + 1)]
                    if not any(d < month_first or d > month_last for d in window):
                        continue
                    history_count = sum(int(bool(historical_days.get(d)) if cat is None
                                            else cat in historical_days.get(d, set()))
                                        for d in window)
                    vars_current = [v for day in window
                                    for v in (current_all.get(day, []) if cat is None
                                              else current_category.get((day, cat), []))]
                    if vars_current:
                        model.add(sum(vars_current) <= max(0, limit - history_count))

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
        balance = float(emp.get("opening_hour_balance", 0)) if settings["use_opening_balance"] else 0.0
        target = int(round((float(emp.get("target_month_hours", 0)) - credits - balance) * 60))
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
    # Weekend-eerlijkheid: handmatig ingevoerde historische weekenddagen
    # meewegen, met ruwe normalisatie naar contractpercentage.
    normalized = []
    upper_rate = 1000  # contractpercentage minimaal 1
    for ei, emp in enumerate(employees):
        factor = round(1000 / int(emp["contract_percent"]))
        prior = int(emp.get("historic_weekend_days", 0))
        normalized.append((prior + sum(weekend_vars[ei])) * factor)
    total_normalized = sum(normalized)
    deviation_bound = max(1, staff_count * (200 + needed) * upper_rate)
    for ei in range(len(employees)):
        dev = model.new_int_var(0, deviation_bound, f"weekend_{ei}")
        model.add_abs_equality(dev, staff_count * normalized[ei] - total_normalized)
        fairness.append(dev)

    # v0.22 — alleen de UITDRUKKELIJK gekozen reguliere toewijzingen zijn hard.
    # Alle andere x-variabelen, inclusief niet-geselecteerde oorspronkelijke
    # toewijzingen, blijven volledig vrij voor de optimizer.
    if locked:
        requested = {assignment_key(r) for r in locked}
        possible = {(str(req["date"]), str(req["shift_id"]), emp["id"]): var
                    for (ei, ri), var in x.items()
                    for req, emp in ((slots[ri], employees[ei]),)
                    if "_task_index" not in req}
        unknown = requested - possible.keys()
        if unknown:
            d, sid, eid = sorted(unknown)[0]
            raise ValueError(f"Vaste dienst {sid} op {d} voor {eid} is niet inzetbaar volgens de huidige individuele regels.")
        for key in requested:
            model.add(possible[key] == 1)

    # v0.23 — een handmatig verwijderde toewijzing mag niet terugkomen.
    # De dienstplaats zelf blijft beschikbaar voor andere controleurs.
    if excluded:
        possible_exclusions = {(str(req["date"]), str(req["shift_id"]), emp["id"]): var
                               for (ei, ri), var in x.items()
                               for req, emp in ((slots[ri], employees[ei]),)
                               if "_task_index" not in req}
        for row in excluded:
            var = possible_exclusions.get(assignment_key(row))
            if var is not None:
                model.add(var == 0)

    # v0.11: controleer ruilen door het HELE gepubliceerde rooster vast te pinnen.
    # Dit gebruikt exact dezelfde harde constraints als de maandplanning.
    if fixed_plan is not None:
        fixed_people = [(str(r["Datum"]), str(r["Dienstnummer"]), str(r["Personeelsnr"]))
                        for r in fixed_plan.get("assignments", [])]
        if len(set(fixed_people)) != len(fixed_people):
            raise ValueError("Dubbele toewijzingen in te controleren rooster.")
        current_keys = {(str(req["date"]),
                         "TAAK:" + data["task_needs"][req["_task_index"]]["task_id"]
                         if "_task_index" in req else str(req["shift_id"]), emp["id"]): (ei, ri)
                        for ri, req in enumerate(slots) for ei, emp in enumerate(employees)
                        if (ei, ri) in x}
        if not set(fixed_people).issubset(current_keys):
            raise ValueError("De voorgestelde ruil bevat een ontoelaatbare diensttoewijzing.")
        pinned = set(fixed_people)
        for key, idx in current_keys.items():
            model.add(x[idx] == int(key in pinned))

        pinned_tasks = [(str(r["Datum"]), str(r["Dienstnummer"]), str(r["Taakcode"]),
                         str(r["Personeelsnr"])) for r in fixed_plan.get("task_assignments", [])]
        if len(set(pinned_tasks)) != len(pinned_tasks):
            raise ValueError("Ambigue dubbele taaktoewijzingen in te controleren rooster.")
        possible_tasks = {}
        for (ti, ei), v in task_selected.items():
            need = data["task_needs"][ti]
            key = (str(need["date"]), str(need.get("shift_id") or "Zelfstandig"),
                   str(need["task_id"]), employees[ei]["id"])
            if key in possible_tasks:
                raise ValueError("Dubbele taakbehoefte kan niet veilig worden vastgezet voor ruilverificatie.")
            possible_tasks[key] = v
        if not set(pinned_tasks).issubset(possible_tasks):
            raise ValueError("De gepubliceerde taaktoewijzingen zijn niet meer geldig.")
        for key, v in possible_tasks.items():
            model.add(v == int(key in set(pinned_tasks)))

    # Groot genoeg voor lexicografische voorrang van dekking boven zachte scores.
    # Bovenbound voor de zachte wensen en abs-afwijkingen bij het maximaal aantal posten.
    pref_weight = int(settings["preference_weight"])
    fair_weight = int(settings["fairness_weight"])
    hours_weight = int(settings["hours_weight"])
    # Voor dekking voorrang op ALLE zachte voorkeuren: ruime bovengrens
    # op gewenste werkdagen, categorieën, diensten en overgangswensen.
    preference_bound = 30 * max(1, len(data["preferences"])) * max(1, needed) + needed
    category_target_bound = 31 * staff_count * 4
    fairness_bound = staff_count * (staff_count * needed * 2 + deviation_bound)
    covering_cost = (1 + pref_weight * (preference_bound + category_target_bound)
                     + fair_weight * fairness_bound
                     + hours_weight * (60000 * staff_count))
    # Lexicografische voorrang: eerst dienstdekking, dan taakdekking,
    # daarna voorkeuren/eerlijkheid/uren. De taak is geen vervangende dienst.
    total_task_places = sum(r["required"] for r in data.get("task_needs", []))
    task_cost = covering_cost
    coverage_cost = (total_task_places + 1) * task_cost
    base_vacancies = [vacancy[ri] for ri, req in enumerate(slots) if "_task_index" not in req]
    model.minimize(coverage_cost * sum(base_vacancies)
                   + task_cost * sum(task_open_vars.values())
                   + pref_weight * (sum(pref_penalty_terms) + sum(category_targets_penalty))
                   + fair_weight * sum(fairness)
                   + hours_weight * sum(hours_deviations))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = min(15.0, float(settings["time_limit_seconds"])) if fixed_plan is not None else float(settings["time_limit_seconds"])
    if fixed_plan is not None:
        solver.parameters.stop_after_first_solution = True
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return PlanResult(status_name, [], [], {"required": sum(r["required"] for r in service_slots),
                                                        "assigned": 0, "open": None, "solver": status_name})

    assigned_rows = []
    open_rows = []
    regular_filled = 0
    extra_regular = 0
    for ri, req in enumerate(slots):
        sh = shifts[req["shift_id"]]
        is_standalone = "_task_index" in req
        assigned_here = 0
        for ei, emp in enumerate(employees):
            var = x.get((ei, ri))
            if var is not None and solver.value(var):
                assigned_here += 1
                assigned_rows.append({"Datum": req["date"],
                                      "Dienstnummer": ("TAAK:" + data["task_needs"][req["_task_index"]]["task_id"])
                                                       if is_standalone else sh["id"],
                                      "Soort": "Zelfstandige taak" if is_standalone else "Reguliere dienst",
                                      "Categorie": sh["category"], "Begin": sh["start"], "Einde": sh["end"],
                                      "Controleur": emp["name"], "Personeelsnr": emp["id"],
                                      "Beginlocatie": sh.get("start_location", sh.get("location", "")),
                                      "Eindlocatie": sh.get("end_location", sh.get("location", "")),
                                      "Uren": round(minutes_between(sh["start"], sh["end"]) / 60, 2)})
        vacant = solver.value(vacancy[ri])
        if not is_standalone:
            regular_filled += req["required"] - vacant
            extra_regular += max(0, assigned_here - req["required"])
            if vacant:
                open_rows.append({"Datum": req["date"], "Dienstnummer": sh["id"],
                                  "Categorie": sh["category"], "Open plaatsen": vacant})

    filled_tasks, missing_tasks = [], []
    for ti, need in enumerate(data.get("task_needs", [])):
        task = task_lookup[need["task_id"]]
        for ei, emp in enumerate(employees):
            var = task_selected.get((ti, ei))
            if var is not None and solver.value(var):
                filled_tasks.append({"Datum": need["date"], "Dienstnummer": need.get("shift_id") or "Zelfstandig",
                                     "Taakcode": task["id"], "Taak": task["name"],
                                     "Soort": need_mode(need),
                                     "Begin": need["start"], "Einde": need["end"],
                                     "Personeelsnr": emp["id"], "Controleur": emp["name"]})
        unfilled = solver.value(task_open_vars[ti])
        if unfilled:
            missing_tasks.append({"Datum": need["date"], "Dienstnummer": need.get("shift_id") or "Zelfstandig",
                                  "Taakcode": task["id"], "Taak": task["name"],
                                  "Soort": need_mode(need), "Open taakplaatsen": unfilled})

    required = sum(r["required"] for r in service_slots)
    regular_open = sum(r["Open plaatsen"] for r in open_rows)
    return PlanResult(status_name, assigned_rows, open_rows,
                      {"required": required, "assigned": regular_filled, "open": regular_open,
                       "extra_regular_staffing": extra_regular,
                       "solver": status_name, "seconds": round(solver.wall_time, 2),
                       "objective": round(solver.objective_value, 2),
                       "best_bound": round(solver.best_objective_bound, 2),
                       "task_required": sum(n["required"] for n in data.get("task_needs", [])),
                       "task_assigned": len(filled_tasks),
                       "task_open": sum(n["Open taakplaatsen"] for n in missing_tasks)},
                      filled_tasks, missing_tasks)
