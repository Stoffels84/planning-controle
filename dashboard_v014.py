"""Read-only dashboard summaries for multiple monthly workspaces.

No historical plan is silently reinterpreted as a current plan: the workspace
revision is explicitly compared to the revision used for calculation.
"""
from __future__ import annotations

from collections import Counter


def _whole(value: object) -> int:
    """Avoid summing malformed optional data into an aggregate."""
    return value if type(value) is int and value >= 0 else 0


def summarize_month(snapshot: dict) -> dict:
    payload = snapshot["workspace"]
    year, month = int(snapshot["year"]), int(snapshot["month"])
    revision = int(snapshot["revision"])
    concept = snapshot.get("latest_plan")
    published = snapshot.get("published_plan")
    plan = published or concept  # The published schedule is authoritative for display.
    demand = payload.get("demand") or []
    required_now = sum(_whole(r.get("required")) for r in demand if isinstance(r, dict))

    if published:
        up_to_date = published["revision"] == revision
        newer_draft = concept is not None and concept["id"] > published["id"]
        status = ("Gepubliceerd · invoer gewijzigd" if not up_to_date else
                  "Gepubliceerd · nieuw concept" if newer_draft else "Gepubliceerd")
    elif concept:
        up_to_date = concept["revision"] == revision
        status = "Conceptplanning" if up_to_date else "Concept verouderd"
    else:
        up_to_date = False
        status = "In voorbereiding" if demand else "Leeg"

    result = (plan or {}).get("payload", {})
    summary = result.get("summary", {}) if isinstance(result, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    has_plan_values = all(type(summary.get(k)) is int and summary[k] >= 0
                          for k in ("required", "assigned", "open"))
    computed_required = summary["required"] if has_plan_values else None
    assigned = summary["assigned"] if has_plan_values else None
    open_places = summary["open"] if has_plan_values else None
    coverage = round(100 * assigned / computed_required, 1) if has_plan_values and computed_required > 0 else (
        100.0 if has_plan_values and computed_required == 0 else None
    )
    return {
        "year": year, "month": month, "period": f"{month:02d}/{year}",
        "status": status, "input_revision": revision, "up_to_date": up_to_date,
        "demand_lines": len(demand), "required_now": required_now,
        "task_places": sum(_whole(t.get("required")) for t in (payload.get("task_needs") or []) if isinstance(t, dict)),
        "preferences": len(payload.get("preferences") or []),
        "assigned": assigned, "open": open_places, "coverage": coverage,
        "plan_id": plan["id"] if plan else None,
        "plan_kind": "Gepubliceerd" if published else "Concept" if concept else "Geen",
    }


def summarize_requests(leaves: list[dict], swaps: list[dict], year: int, month: int) -> dict:
    """Count outstanding requests relevant to the selected calendar month.

    Never include personnel names or absence explanations in KPI output.
    """
    prefix = f"{year:04d}-{month:02d}"
    leave_pending = sum(1 for r in leaves if r.get("status") == "pending" and (
        str(r.get("start_date", "")).startswith(prefix) or str(r.get("end_date", "")).startswith(prefix)
    ))
    month_swaps = [r for r in swaps if str(r.get("own_day", "")).startswith(prefix) or
                   str(r.get("their_day", "")).startswith(prefix)]
    return {
        "leave_pending": leave_pending,
        "swaps_awaiting_colleague": sum(r.get("status") == "pending" for r in month_swaps),
        "swaps_awaiting_planner": sum(r.get("status") == "accepted" for r in month_swaps),
    }


def dashboard_warnings(row: dict) -> list[str]:
    warnings = []
    if row["status"] in ("Gepubliceerd · invoer gewijzigd", "Concept verouderd"):
        warnings.append("De invoer is gewijzigd na de laatste berekende/gepubliceerde planversie. Herbereken en controleer vóór een nieuwe publicatie.")
    if row["status"] == "Gepubliceerd · nieuw concept":
        warnings.append("Er bestaat een nieuwer concept. De laatst gepubliceerde versie blijft voor controleurs zichtbaar.")
    if row["required_now"] and row["plan_id"] is None:
        warnings.append("Er is dienstbehoefte ingevoerd, maar er is nog geen opgeslagen planning.")
    if row["open"] is not None and row["open"] > 0:
        warnings.append(f"Laatste bewaarde planning: {row['open']} niet-ingevulde dienstplaatsen.")
    if not row["demand_lines"]:
        warnings.append("Voor deze maand is nog geen dienstbehoefte ingevoerd.")
    return warnings


def dashboard_counts(rows: list[dict]) -> dict:
    statuses = Counter(r["status"] for r in rows)
    return {
        "months": len(rows),
        "published": sum(s.startswith("Gepubliceerd") for s in (r["status"] for r in rows)),
        "outdated": statuses["Gepubliceerd · invoer gewijzigd"] + statuses["Concept verouderd"],
        "without_demand": statuses["Leeg"],
    }
