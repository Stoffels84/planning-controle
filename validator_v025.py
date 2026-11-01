"""v0.25: onafhankelijke, OR-Tools-vrije nacontrole van de harde basisregels.

De berekende diensttoewijzingen worden opnieuw geanalyseerd zonder de solver.
Dit is een proefcontrole, geen wettelijk/CAO-conformiteitsattest.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from catalog import is_unavailable_during, profile, settings_with_defaults, transition_code
from extras import rest_blocked_during
from policy_v06 import saturday_for, touches_protected_weekend
from weekend_v028 import violating_weekend_streaks

CATEGORIES = ("Vroeg", "Dag", "Laat", "Nacht")
VERSION = 1


def _bounds(day: str, start: str, end: str):
    d = date.fromisoformat(day)
    h, m = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= eh < 24 and 0 <= em < 60):
        raise ValueError("ongeldig dienstuur")
    a = datetime.combine(d, time(hour=h, minute=m))
    minutes = ((eh * 60 + em) - (h * 60 + m)) % 1440 or 1440
    if minutes > 960:
        raise ValueError("dienst duurt langer dan 16 uur")
    return a, a + timedelta(minutes=minutes), minutes


def verify_plan(data: dict, result: dict, boundaries: list[dict] | None = None) -> dict:
    """Geeft onafhankelijke fouten en waarschuwingen terug; verandert geen invoer.

    Controleert enkel de door deze applicatie GEMODELLEERDE harde regels.
    Ook bij een foutieve solveruitkomst wordt geen werkrooster stilzwijgend goedgekeurd.
    """
    errors, warnings = [], []
    settings = settings_with_defaults(data["settings"])
    employees = {str(e["id"]): profile(e) for e in data["employees"]}
    shifts = {str(s["id"]): s for s in data["shifts"]}
    demand = {(str(r["date"]), str(r["shift_id"])): int(r["required"]) for r in data["demand"]}
    month = (int(data["year"]), int(data["month"]))
    assignments = result.get("assignments", [])
    if not isinstance(assignments, list):
        return {"version": VERSION, "passed": False, "errors": ["Toewijzingen zijn geen lijst."], "warnings": []}

    by_employee = defaultdict(list)
    counts = Counter()
    seen = set()
    regular_assigned = 0
    for i, row in enumerate(assignments, 1):
        try:
            eid = str(row["Personeelsnr"])
            day = str(row["Datum"])
            code = str(row["Dienstnummer"])
            if (date.fromisoformat(day).year, date.fromisoformat(day).month) != month:
                raise ValueError("buiten de planningsmaand")
            if (eid, day, code) in seen:
                raise ValueError("dubbele toewijzing")
            seen.add((eid, day, code))
            employee = employees.get(eid)
            if employee is None or not employee.get("active", True):
                raise ValueError("onbekende of inactieve controleur")
            if code.startswith("TAAK:"):
                # Zelfstandige taken: tellen voor werkdag, rust en uren, maar
                # niet voor de reguliere dienstbezetting.
                if row.get("Soort") != "Zelfstandige taak":
                    raise ValueError("onjuist type zelfstandige taak")
                category = str(row["Categorie"])
                begin, end, mins = _bounds(day, str(row["Begin"]), str(row["Einde"]))
            else:
                if (day, code) not in demand or code not in shifts:
                    raise ValueError("dienst bestaat niet in de maandbehoefte")
                shift = shifts[code]
                if not shift.get("active", True):
                    raise ValueError("dienst is inactief")
                category = str(shift["category"])
                begin, end, mins = _bounds(day, str(shift["start"]), str(shift["end"]))
                # De solveruitvoer moet de feitelijke uren/categorie bevatten.
                if (row.get("Begin"), row.get("Einde"), row.get("Categorie")) != (
                    shift["start"], shift["end"], shift["category"]
                ):
                    raise ValueError("diensturen of categorie wijken af van catalogus")
                counts[day, code] += 1
                regular_assigned += 1
            if category not in CATEGORIES:
                raise ValueError("onbekende dienstcategorie")
            if category in employee.get("blocked_categories", []):
                errors.append(f"{eid} op {day}: verboden categorie {category}.")
            if code in employee.get("blocked_shifts", []):
                errors.append(f"{eid} op {day}: verboden dienst {code}.")
            if date.fromisoformat(day).weekday() in employee.get("blocked_weekdays", []):
                errors.append(f"{eid} op {day}: verboden weekdag.")
            if is_unavailable_during(employee, begin, end):
                errors.append(f"{eid} op {day}: overlapt onbeschikbaarheid.")
            if rest_blocked_during(employee, begin, end, data.get("hour_credits", [])):
                errors.append(f"{eid} op {day}: overlapt vaste rustdag of geregistreerde afwezigheid.")
            if touches_protected_weekend(employee, begin, end):
                errors.append(f"{eid} op {day}: raakt een beschermd weekend.")
            by_employee[eid].append((date.fromisoformat(day), begin, end, category, mins))
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            errors.append(f"Toewijzing #{i}: {exc}.")

    # Reguliere bezetting: tijdelijke vrijstelling voor taken kan meer
    # toegewezen personen vereisen dan de standaardbezetting.
    released = {(str(n["date"]), str(n.get("shift_id"))) for n in data.get("task_needs", [])
                if n.get("mode") == "released"}
    for key, count in counts.items():
        if key not in released and count > demand[key]:
            errors.append(f"{key[0]} dienst {key[1]}: {count} toegewezen bij behoefte {demand[key]}.")

    # Vergelijk de zichtbare bezetting met de gerapporteerde open plaatsen.
    # Bij tijdelijke vrijstelling ('released' taak) kan een dienst terecht
    # meer personeel bevatten dan de normale vereiste bezetting.
    if "open_positions" in result:
        missing = Counter()
        for i, row in enumerate(result["open_positions"] or [], 1):
            try:
                key = (str(row["Datum"]), str(row["Dienstnummer"]))
                amount = row["Open plaatsen"]
                if key not in demand or type(amount) is not int or amount < 1:
                    raise ValueError("onbekende dienst of ongeldig aantal")
                if missing[key]:
                    raise ValueError("dubbele regel voor dezelfde dienst")
                missing[key] = amount
            except (KeyError, ValueError, TypeError) as exc:
                errors.append(f"Open plaats #{i}: {exc}.")
        for key, required in demand.items():
            open_count = missing[key]
            if open_count > required:
                errors.append(f"{key[0]} dienst {key[1]}: meer open plaatsen dan nodig.")
            if key not in released and counts[key] + open_count != required:
                errors.append(f"{key[0]} dienst {key[1]}: toewijzingen + open plaatsen "
                              f"({counts[key]} + {open_count}) verschillen van de behoefte ({required}).")
        summary = result.get("summary", {}) or {}
        if isinstance(summary, dict):
            expected_required = sum(demand.values())
            expected_open = sum(missing.values())
            expected_assigned = expected_required - expected_open
            for k, expected in (("required", expected_required), ("open", expected_open),
                                ("assigned", expected_assigned)):
                if summary.get(k) is not None and summary[k] != expected:
                    errors.append(f"Samenvatting: {k} is {summary[k]}, verwacht {expected}.")

    for eid, items in by_employee.items():
        employee = employees[eid]
        items.sort(key=lambda item: item[1])
        days = Counter(item[0] for item in items)
        for day, count in days.items():
            if count > 1:
                errors.append(f"{eid} op {day}: {count} diensten op dezelfde kalenderdag.")
        worked_minutes = sum(item[4] for item in items)
        if worked_minutes > int(float(employee["max_month_hours"]) * 60):
            errors.append(f"{eid}: maanduren overschrijden het individuele maximum.")
        limits = [v for v in (settings.get("max_weekend_days"), employee.get("max_weekend_days")) if v is not None]
        weekends = [d for d in days if d.weekday() >= 5]
        if limits and len(weekends) > min(limits):
            errors.append(f"{eid}: te veel weekenddagen.")
        if employee.get("max_worked_weekends") is not None:
            if len({saturday_for(d) for d in weekends}) > employee["max_worked_weekends"]:
                errors.append(f"{eid}: te veel gewerkte weekends.")
        for category in CATEGORIES:
            limit_list = [v for v in (settings.get("max_month_categories", {}).get(category),
                                      employee.get("max_month_categories", {}).get(category)) if v is not None]
            if limit_list and sum(int(item[3] == category) for item in items) > min(limit_list):
                errors.append(f"{eid}: maximum aantal diensten {category} overschreden.")

    # Adjacent published months are fixed constraints. They also count for
    # consecutive workdays/category series at the calendar month boundary.
    known_previous = set()
    known_next = set()
    for i, row in enumerate(boundaries or [], 1):
        try:
            eid = str(row["employee_id"])
            if eid not in employees:
                continue
            day = str(row["date"])
            d = date.fromisoformat(day)
            adjacent = (d.year, d.month) != month
            if not adjacent:
                raise ValueError("grensdienst valt binnen huidige maand")
            start, end, mins = _bounds(day, row["start"], row["end"])
            category = str(row["category"])
            if category not in CATEGORIES:
                raise ValueError("onbekende categorie")
            if d < date(*month, 1):
                known_previous.add(eid)
            else:
                known_next.add(eid)
            by_employee[eid].append((d, start, end, category, mins))
        except (KeyError, ValueError, TypeError) as exc:
            errors.append(f"Grensdienst #{i}: {exc}.")

    current_start = date(*month, 1)
    next_month = (current_start + timedelta(days=32)).replace(day=1)
    current_last = next_month - timedelta(days=1)
    for eid, rows in by_employee.items():
        emp = employees[eid]
        rows.sort(key=lambda item: item[1])
        for previous, following in zip(rows, rows[1:]):
            pday, ps, pe, pcat, _ = previous
            nday, ns, ne, ncat, _ = following
            if not (current_start <= pday <= current_last or current_start <= nday <= current_last):
                continue  # oude aangrenzende diensten zijn niet te wijzigen
            rest = max(float(settings["min_rest_hours"]), float(emp.get("min_rest_hours") or 0),
                       float(settings.get("transition_rest_hours", {}).get(transition_code(pcat, ncat), 0)))
            if ns < pe + timedelta(hours=rest):
                errors.append(f"{eid}: onvoldoende rust tussen {pday} en {nday}.")
            if (nday - pday).days == 1 and transition_code(pcat, ncat) in (
                set(settings.get("blocked_transitions", [])) | set(emp.get("blocked_transitions", []))
            ):
                errors.append(f"{eid}: verboden overgang {pcat}>{ncat} op {nday}.")
        # v0.28: onafhankelijke controle van weekendreeksen, inclusief
        # een gepubliceerd buurrooster als die maand beschikbaar is.
        streak_cap = emp.get("max_consecutive_worked_weekends")
        if streak_cap is not None:
            month_days = [item[0] for item in rows
                          if current_start <= item[0] <= current_last]
            adjacent_days = [item[0] for item in rows
                             if item[0] < current_start or item[0] > current_last]
            for window in violating_weekend_streaks(month_days, adjacent_days, streak_cap):
                errors.append(f"{eid}: meer dan {streak_cap} opeenvolgende gewerkte weekends "
                              f"vanaf {window[0]}.")
                break
        # Exacte kalenderdagvensters, ook over de maandgrens.
        days = {item[0] for item in rows}
        cat_days = defaultdict(set)
        for item in rows:
            cat_days[item[3]].add(item[0])
        checks = [(int(emp.get("max_consecutive") or settings["max_consecutive"]), days, "werkdagen")]
        for category in CATEGORIES:
            caps = [v for v in (settings.get("max_category_run", {}).get(category),
                                emp.get("max_category_run", {}).get(category)) if v is not None]
            if caps:
                checks.append((min(caps), cat_days[category], category))
        for maximum, dates, label in checks:
            for start in sorted(dates):
                window = [start + timedelta(days=i) for i in range(maximum + 1)]
                if all(d in dates for d in window) and any(current_start <= d <= current_last for d in window):
                    errors.append(f"{eid}: reeks {label} langer dan {maximum} dagen vanaf {start}.")
                    break
    return {"version": VERSION, "passed": not errors, "errors": errors,
            "warnings": warnings, "assignments_checked": len(assignments),
            "employees_checked": len(by_employee)}
