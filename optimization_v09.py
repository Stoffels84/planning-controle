"""V0.9: opgeslagen optimalisatieprofielen en eerlijke vergelijking.

Geen externe dependencies, zodat configuratie/metingen apart getest kunnen worden.
De solver zelf blijft de gevalideerde (voor testdoeleinden) v0.8-code.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json

WEIGHT_KEYS = ("preference_weight", "fairness_weight", "hours_weight")
DEFAULTS = (
    {"id": "balanced", "name": "Evenwichtig", "team": "Alle teams",
     "preference_weight": 25, "fairness_weight": 1, "hours_weight": 0},
    {"id": "preferences", "name": "Voorkeuren centraal", "team": "Alle teams",
     "preference_weight": 75, "fairness_weight": 0, "hours_weight": 0},
    {"id": "fairness", "name": "Eerlijke verdeling", "team": "Alle teams",
     "preference_weight": 10, "fairness_weight": 3, "hours_weight": 0},
    {"id": "hours", "name": "Uren dichter bij streefwaarden", "team": "Alle teams",
     "preference_weight": 10, "fairness_weight": 1, "hours_weight": 2},
)


def validate_profiles(data: dict) -> list[str]:
    """Valideer optionele custom profielen; oudere werkruimtes blijven geldig."""
    profiles = data.get("optimization_profiles", [])
    if not isinstance(profiles, list) or len(profiles) > 20:
        return ["Gebruik maximaal 20 eigen optimalisatieprofielen."]
    errors: list[str] = []
    used = set()
    team_names = {e.get("team", "").strip() for e in data.get("employees", [])}
    team_names.add("Alle teams")
    for pos, p in enumerate(profiles, 1):
        if not isinstance(p, dict):
            errors.append(f"Profiel {pos} is ongeldig.")
            continue
        name = p.get("name")
        team = p.get("team", "Alle teams")
        if not isinstance(name, str) or not (2 <= len(name.strip()) <= 60):
            errors.append(f"Profiel {pos}: naam moet 2–60 tekens bevatten.")
        if not isinstance(team, str) or team not in team_names:
            errors.append(f"Profiel {pos}: onbekende teamnaam.")
        identity = (team, name.strip().casefold()) if isinstance(name, str) and isinstance(team, str) else None
        if identity in used:
            errors.append(f"Profiel {pos}: naam binnen dit team bestaat al.")
        used.add(identity)
        for key in WEIGHT_KEYS:
            v = p.get(key)
            if type(v) is not int or not (0 <= v <= 100):
                errors.append(f"Profiel {pos}: {key} moet een geheel getal van 0–100 zijn.")
        if all(p.get(k) == 0 for k in WEIGHT_KEYS):
            errors.append(f"Profiel {pos}: minstens één gewicht moet groter dan nul zijn.")
        time = p.get("time_limit_seconds")
        if time is not None and (type(time) is not int or not (1 <= time <= 3600)):
            errors.append(f"Profiel {pos}: rekentijd moet 1–3600 seconden zijn.")
    return errors


def options_for(data: dict) -> list[dict]:
    """Kopieën; nooit een origineel profiel in de werkruimte muteren."""
    profiles = [dict(x) for x in DEFAULTS]
    for i, p in enumerate(data.get("optimization_profiles", [])):
        profiles.append(dict(p, id=f"custom_{i}", name=p["name"]))
    return profiles


def with_profile(data: dict, profile: dict, time_limit: int | None = None) -> dict:
    """Dezelfde harde regels en personeelsgegevens, uitsluitend zachte gewichten wijzigen."""
    updated = deepcopy(data)
    settings = updated["settings"]
    for key in WEIGHT_KEYS:
        settings[key] = int(profile[key])
    if time_limit is not None:
        if type(time_limit) is not int or not 1 <= time_limit <= 3600:
            raise ValueError("Rekentijd moet een geheel getal tussen 1 en 3600 zijn.")
        settings["time_limit_seconds"] = time_limit
    return updated


def signature(data: dict, history: list[dict] | None = None) -> str:
    """Resultaten zijn ongeldig wanneer invoer of historische maandversies wijzigen."""
    raw = json.dumps({"workspace": data, "history": history or []}, ensure_ascii=False,
                     sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


def roster_signature(result) -> str:
    """Identieke toewijzingen herkennen, ook als scores/solve-status verschillen."""
    assigned = sorted((r["Datum"], str(r["Dienstnummer"]), r["Personeelsnr"])
                      for r in result.assignments)
    tasks = sorted((r["Datum"], r["Taakcode"], r["Personeelsnr"],
                    r["Begin"], r["Einde"]) for r in result.task_assignments)
    return sha256(json.dumps([assigned, tasks]).encode("utf-8")).hexdigest()


def compare_row(profile: dict, plan, data: dict) -> dict:
    """Model-onafhankelijke metriek (geen vergelijking van objective_value)."""
    counts = defaultdict(int)
    weekends = defaultdict(set)
    hours = defaultdict(float)
    assigned_days = defaultdict(set)
    by_emp_day = defaultdict(list)
    for r in plan.assignments:
        eid = r["Personeelsnr"]
        day = date.fromisoformat(r["Datum"])
        counts[eid] += 1
        hours[eid] += float(r["Uren"])
        assigned_days[eid].add(r["Datum"])
        by_emp_day[eid, r["Datum"]].append(r)
        if day.weekday() >= 5:
            weekends[eid].add(r["Datum"])
    wishes = [p for p in data.get("preferences", []) if p.get("type", "free_day") in ("free_day", "weekly_free")]
    free_days_met = free_days_missed = 0
    for p in wishes:
        eid = p["employee_id"]
        if p.get("type", "free_day") == "free_day":
            dates = [p["date"]]
        else:
            import calendar
            count = calendar.monthrange(int(data["year"]), int(data["month"]))[1]
            dates = [date(int(data["year"]), int(data["month"]), d).isoformat()
                     for d in range(1, count + 1)
                     if date(int(data["year"]), int(data["month"]), d).weekday() == p["weekday"]]
        for d in dates:
            if d in assigned_days[eid]:
                free_days_missed += 1
            else:
                free_days_met += 1
    # Daggebonden dienstwensen vergelijken op exact dienstnummer én datum.
    # Een wens voor een inmiddels geschrapte dienst telt niet mee in de cijfers.
    offered = {(req["date"], req["shift_id"]) for req in data.get("demand", []) if req["required"] > 0}
    daily_met = daily_missed = 0
    for p in data.get("preferences", []):
        if p.get("type") != "daily_shift" or (p.get("date"), p.get("shift_id")) not in offered:
            continue
        assignments = by_emp_day.get((p["employee_id"], p["date"]), [])
        if any(a["Dienstnummer"] == p["shift_id"] for a in assignments):
            daily_met += 1
        else:
            daily_missed += 1
    active = [e for e in data["employees"] if e.get("active", True)]
    normalized_weekends = [len(weekends[e["id"]]) / (float(e.get("contract_percent", 100)) / 100)
                           for e in active if float(e.get("contract_percent", 100)) > 0]
    weekend_range = (max(normalized_weekends) - min(normalized_weekends)) if normalized_weekends else 0.0
    hours_deviation = 0.0
    n_targets = 0
    credits = defaultdict(float)
    for credit in data.get("hour_credits", []):
        credits[credit["employee_id"]] += float(credit["hours"])
    use_balance = data["settings"].get("use_opening_balance", False)
    for e in active:
        target = float(e.get("target_month_hours", 0))
        if target > 0:
            opening = float(e.get("opening_hour_balance", 0)) if use_balance else 0
            hours_deviation += abs(target - (hours[e["id"]] + credits[e["id"]] + opening))
            n_targets += 1
    return {
        "Profiel": profile["name"],
        "Status": plan.status,
        "Diensten ingevuld": plan.summary.get("assigned", 0),
        "Open diensten": plan.summary.get("open"),
        "Open taken": plan.summary.get("task_open", 0),
        "Vrijwensen gerespecteerd": free_days_met,
        "Vrijwensen gemist": free_days_missed,
        "Dagelijkse dienstwensen ingewilligd": daily_met,
        "Dagelijkse dienstwensen gemist": daily_missed,
        "Weekendspreiding (FTE)": round(weekend_range, 2),
        "Urenafwijking (test, u)": round(hours_deviation, 1) if n_targets else None,
        "Rekentijd (s)": plan.summary.get("seconds"),
        "Verschillend rooster": roster_signature(plan)[:12],
    }
