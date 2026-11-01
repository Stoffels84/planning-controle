"""Controleursplanning: interactieve, uitsluitend fictieve proefversie."""
from __future__ import annotations

import io
import logging
import json
import os
from dataclasses import asdict
from datetime import date
import calendar
from itertools import groupby

import pandas as pd
import streamlit as st

from demo_data import CATEGORIES, WEEKDAYS, build_demo, next_month
from planner import PlanResult, solve_month, validate_dataset
from extras import (PREFERENCE_TYPES, CREDIT_TYPES, REST_MODES, preference_type,
                    preference_identity, preference_description, summarize_hours)
import store
import catalog
from policy_v06 import weekend_start_dates, hours_overview, service_overview
from weekend_v028 import MAX_STREAK_SETTING
from history_v07 import aggregate_history, apply_published_history
from tasks_v07 import validate_tasks, MODES, need_mode
from optimization_v09 import (WEIGHT_KEYS, DEFAULTS, options_for, with_profile,
                              compare_row, signature, validate_profiles, roster_signature)
from daily_v091 import days_in_month, shifts_by_day, current_daily_choices, update_daily_choices
from requests_v010 import STATUS_LABELS
from swap_v011 import regular_assignments
from month_copy_v013 import copy_month_demand_rows
from dashboard_v014 import summarize_month, summarize_requests, dashboard_warnings, dashboard_counts
from boundary_v015 import published_boundary_context, with_boundary_context
from portal_v016 import (month_weeks, preference_summary, week_choices, save_week_choices,
                         personal_calendar, own_published_assignments, DAYS_NL, PRIORITIES)
from portal_v017 import month_tiles, personal_publication_changes, personal_request_feed, WEEKDAYS as CALENDAR_DAYS
from report_v019 import build_report, safe_excel_rows
from diagnostics_v021 import analyze_month, explain_open_positions
from locks_v022 import assignment_key, reoptimization_diff
from manual_v023 import compile_edits, edit_description, regular_assignments, MAX_EDITS
from roster_v024 import week_windows, month_days, roster_grid, staffing_grid, workbook_bytes
from validator_v025 import verify_plan
from activities_v0261 import invalid_activities, remove_invalid_activities
from shift_edit_v0262 import apply_month_shift
from activity_move_v0263 import activity_destination, validate_movable_activity
from hours_v027 import (validate_month_regimes, apply_month_regimes,
                         build_balance_preview, apply_balance_to_solver)

st.set_page_config(page_title="Controleursplanning | v0.28", page_icon="📅", layout="wide")


def setting(name: str) -> str:
    """Staat omgevingsvariabelen en niet-gecommitte Streamlit Secrets toe."""
    value = os.getenv(name)
    if value:
        return value
    try:
        return str(st.secrets.get(name, ""))
    except (FileNotFoundError, OSError, KeyError):
        return ""


DATABASE_URL = setting("DATABASE_URL")
PERSISTENT = bool(DATABASE_URL)
engine = None
current_user = None

if PERSISTENT:
    @st.cache_resource(show_spinner=False)
    def connect_db(url: str):
        return store.get_engine(url)

    try:
        engine = connect_db(DATABASE_URL)
        store.initialize(engine, setting("BOOTSTRAP_ADMIN_ID"), setting("BOOTSTRAP_ADMIN_PASSWORD"))
    except store.SetupError as error:
        st.error(str(error))
        st.stop()
    except Exception:
        st.error("Databaseverbinding mislukt. Controleer DATABASE_URL en netwerktoegang in de Streamlit Secrets.")
        st.stop()

    signed_id = st.session_state.get("signed_id")
    if signed_id:
        current_user = store.lookup_account(engine, signed_id)
        if not current_user or not current_user["active"] or current_user["auth_hash"] != st.session_state.get("signed_hash"):
            st.session_state.clear()
            current_user = None

    if current_user is None:
        st.title("🔐 Controleursplanning")
        st.caption("Aanmelden met personeelsnummer en persoonlijk wachtwoord — TESTOMGEVING")
        with st.form("login", clear_on_submit=True):
            login_id = st.text_input("Personeelsnummer", max_chars=64).strip()
            login_password = st.text_input("Wachtwoord", type="password")
            submitted = st.form_submit_button("Aanmelden")
        if submitted:
            account = store.authenticate(engine, login_id, login_password)
            if account:
                st.session_state.clear()
                st.session_state.signed_id = account["employee_id"]
                st.session_state.signed_hash = account["auth_hash"]
                st.rerun()
            else:
                st.error("Aanmelden mislukt. Controleer je gegevens of probeer later opnieuw.")
        # Eenmalig herstel is uitsluitend beschikbaar wanneer de beheerder
        # zelf een lange willekeurige sleutel in de externe Secrets activeert.
        recovery_key = setting("ADMIN_RECOVERY_KEY")
        if recovery_key:
            with st.expander("🔑 Beheerderswachtwoord eenmalig herstellen"):
                st.caption("Alleen voor de beheerder van deze testomgeving. Deze herstelcode werkt slechts één keer.")
                with st.form("admin_recovery_form", clear_on_submit=True):
                    admin_id = st.text_input("Personeelsnummer van de beheerder", max_chars=64)
                    typed_key = st.text_input("Eenmalige herstelcode", type="password")
                    fresh_password = st.text_input("Nieuw wachtwoord (minimaal 14 tekens)", type="password")
                    confirm_password = st.text_input("Herhaal nieuw wachtwoord", type="password")
                    restore = st.form_submit_button("Beheerderswachtwoord herstellen")
                if restore:
                    try:
                        if fresh_password != confirm_password:
                            raise ValueError("De nieuwe wachtwoorden komen niet overeen.")
                        store.recover_admin_once(engine, admin_id.strip(), typed_key,
                                                 fresh_password, recovery_key)
                        st.success("Wachtwoord hersteld. Meld je hierboven aan met je nieuwe wachtwoord. Verwijder nu ADMIN_RECOVERY_KEY uit Streamlit Secrets.")
                    except ValueError as error:
                        st.error(str(error))
                    except Exception:
                        st.error("Herstel mislukt. Controleer de gegevens en de databaseverbinding.")
        st.info("Deze proefversie mag uitsluitend met fictieve gegevens worden gebruikt.")
        st.stop()

    if current_user["must_change_password"]:
        st.title("🔑 Wachtwoord wijzigen")
        st.info("Stel eerst een nieuw persoonlijk wachtwoord in.")
        with st.form("mandatory_password_change", clear_on_submit=True):
            old = st.text_input("Tijdelijk wachtwoord", type="password")
            fresh = st.text_input("Nieuw wachtwoord (minstens 14 tekens)", type="password")
            confirm = st.text_input("Herhaal nieuw wachtwoord", type="password")
            if st.form_submit_button("Wijzig wachtwoord"):
                try:
                    if fresh != confirm:
                        raise ValueError("De nieuwe wachtwoorden komen niet overeen.")
                    store.change_password(engine, current_user["employee_id"], old, fresh)
                    st.session_state.clear()
                    st.success("Wachtwoord gewijzigd. Meld je opnieuw aan.")
                except ValueError as error:
                    st.error(str(error))
        st.stop()



@st.cache_data
# Alleen voor een statisch Excel-sjabloon; GEEN planning of personeelsdata cachen.
def example_excel(year: int, month: int, rows: tuple[tuple[str, int], ...]) -> bytes:
    demo_day = date(year, month, 2).isoformat()
    frame = pd.DataFrame([
        {"datum": demo_day, "dienstnummer": sid, "aantal": required}
        for sid, required in rows
    ])
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Maandbehoefte")
    return buffer.getvalue()


def plan_excel(plan, state: dict, diagnosis: dict | None = None) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(plan.assignments).to_excel(writer, index=False, sheet_name="Toewijzingen")
        pd.DataFrame(plan.open_positions).to_excel(writer, index=False, sheet_name="Open plaatsen")
        pd.DataFrame([plan.summary]).to_excel(writer, index=False, sheet_name="Samenvatting")
        pd.DataFrame(hours_overview(state["employees"], plan.assignments,
                                    state.get("hour_credits", []),
                                    catalog.settings_with_defaults(state["settings"])["use_opening_balance"])).to_excel(
                                        writer, index=False, sheet_name="Urenoverzicht test")
        pd.DataFrame(service_overview(state["employees"], plan.assignments)).to_excel(
            writer, index=False, sheet_name="Dienstverdeling")
        pd.DataFrame(plan.task_assignments).to_excel(writer, index=False, sheet_name="Taaktoewijzingen")
        pd.DataFrame(plan.open_tasks).to_excel(writer, index=False, sheet_name="Open taken")
        if diagnosis is not None:
            pd.DataFrame(safe_excel_rows(diagnosis["slots"])).to_excel(writer, index=False, sheet_name="Haalbaarheid diensten")
            pd.DataFrame(safe_excel_rows(diagnosis["days"])).to_excel(writer, index=False, sheet_name="Haalbaarheid dagen")
            pd.DataFrame(safe_excel_rows(diagnosis["blockers"])).to_excel(writer, index=False, sheet_name="Blokkeringen indicatief")
            pd.DataFrame(safe_excel_rows(explain_open_positions(diagnosis, plan.open_positions))).to_excel(
                writer, index=False, sheet_name="Uitleg open plaatsen")
    return buffer.getvalue()


def replace_data(updated: dict) -> None:
    errors = validate_dataset(updated) + validate_month_regimes(updated)
    if errors:
        st.error("Gegevens niet opgeslagen: " + " ".join(errors))
        st.stop()
    if PERSISTENT:
        if (updated.get("year"), updated.get("month")) != tuple(st.session_state.active_period):
            st.error("Je kunt de planningsmaand niet wijzigen door een JSON-bestand te laden. Selecteer de maand links.")
            st.stop()
        try:
            new_revision = store.save_month_workspace(
                engine, updated, st.session_state.workspace_revision,
                current_user["employee_id"], "Projectgegevens aangepast"
            )
            st.session_state.workspace_revision = new_revision
        except (store.ConflictError, ValueError) as error:
            st.error(str(error))
            st.stop()
    st.session_state.project_data = updated
    st.session_state.pop("last_plan", None)
    st.session_state.pop("alternatives_v09", None)



def save_month_regime_and_rerun(employee_id: str, regime: dict | None) -> None:
    """Sla uitsluitend één maandregime op, niet het volledige oude werkblad."""
    current = clone()
    tentative = {"employees": [{"id": employee_id}],
                 "month_hour_regimes_v027": ({employee_id: regime} if regime is not None else {})}
    issues = validate_month_regimes(tentative)
    if issues:
        raise ValueError(" ".join(issues))
    if PERSISTENT:
        rev = store.save_month_regime_v0272(
            engine, int(current["year"]), int(current["month"]),
            int(st.session_state.workspace_revision), current_user["employee_id"],
            employee_id, regime,
        )
        refreshed, fresh_rev = store.load_month_workspace(
            engine, int(current["year"]), int(current["month"]))
        st.session_state.workspace_revision = fresh_rev
        st.session_state.project_data = refreshed
    else:
        values = current.setdefault("month_hour_regimes_v027", {})
        if regime is None:
            values.pop(employee_id, None)
        else:
            values[employee_id] = regime
        st.session_state.project_data = current
    st.session_state.pop("last_plan", None)
    st.session_state.pop("alternatives_v09", None)
    st.rerun()


def replace_and_rerun(updated: dict) -> None:
    replace_data(updated)
    st.rerun()


def clone() -> dict:
    # Bewust kopiëren: de sessie verandert pas na opslaan.
    return json.loads(json.dumps(st.session_state.project_data))


def to_iso(value) -> str:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value)[:10]).isoformat()



def render_daily_preferences(eid: str, scope: str) -> None:
    """Mobielvriendelijk: één week tegelijk invullen, alle andere weken behouden."""
    data = st.session_state.project_data
    weeks = month_weeks(data)
    available = shifts_by_day(data)
    old = current_daily_choices(data, eid)
    published_view = (store.load_plan(engine, data["year"], data["month"], published_only=True)
                      if PERSISTENT else None)
    published_by_date = own_published_assignments(published_view["payload"], eid) if published_view else {}
    counts = preference_summary(data, eid)
    st.markdown("### Dienstwensen per week")
    st.caption("Selecteer per dag een **concreet dienstnummer** uit de maandbehoefte, "
               "of kies **Liefst vrij**. Een wens is geen gegarandeerde toewijzing of goedgekeurd verlof.")
    c1, c2, c3 = st.columns(3)
    c1.metric("Dienstwensen", counts["shift"])
    c2.metric("Liefst vrij", counts["free"])
    c3.metric("Geen voorkeur", counts["unselected"])
    visible = st.selectbox("Week bewerken", weeks, format_func=lambda w: w["label"],
                           key=f"portal_week_{scope}_{eid}_{data['year']}_{data['month']}")
    days = visible["days"]
    pending = {}
    with st.form(f"portal_week_form_{scope}_{eid}_{data['year']}_{data['month']}_{visible['key']}"):
        for day in days:
            iso = day.isoformat()
            with st.container(border=True):
                st.markdown(f"**{WEEKDAYS[day.weekday()]} {day:%d/%m/%Y}**")
                if published_view:
                    today_published = published_by_date.get(iso, [])
                    st.caption("Gepubliceerd: " + (
                        ", ".join(str(r["Dienstnummer"]) + " · " + str(r.get("Begin", ""))
                                  + "–" + str(r.get("Einde", "")) for r in today_published)
                        if today_published else "Geen dienst toegewezen"))
                shifts = available.get(iso, [])
                by_id = {sh["id"]: sh for sh in shifts}
                options = [("none", ""), ("free", "")] + [("shift", sh["id"]) for sh in shifts]
                pref = old.get(iso, {})
                kind = preference_type(pref) if pref else ""
                wanted = (("shift", pref.get("shift_id", "")) if kind == "daily_shift"
                          else ("free", "") if kind == "free_day" else ("none", ""))
                if wanted not in options:
                    st.warning("De eerder gekozen dienst is niet meer beschikbaar. Kies een nieuwe dienst.")
                    wanted = ("none", "")
                def display(option, lookup=by_id):
                    typ, sid = option
                    if typ == "none":
                        return "— Geen voorkeur"
                    if typ == "free":
                        return "🏡 Liefst vrij"
                    shift = lookup[sid]
                    return f"{sid} · {shift['start']}–{shift['end']} · {shift['category']}"
                selected = st.selectbox("Gewenste dienst", options, index=options.index(wanted),
                                        format_func=display, key=f"daily_choice_{scope}_{eid}_{iso}")
                priority = st.selectbox("Belang van deze wens", [1, 2, 3],
                                         index=int(pref.get("priority", 2)) - 1,
                                         format_func=lambda value: PRIORITIES[value],
                                         key=f"daily_priority_{scope}_{eid}_{iso}")
                pending[iso] = {"kind": selected[0], "shift_id": selected[1], "priority": priority}
                if not shifts:
                    st.caption("Er staan vandaag geen diensten in de maandbehoefte. 'Liefst vrij' kan wel.")
                credits = [c for c in data.get("hour_credits", [])
                           if c.get("employee_id") == eid and c.get("date") == iso]
                if credits:
                    st.info("Er is een afwezigheid of activiteit geregistreerd op deze datum. "
                            "Een dienstwens heft deze registratie niet op.")
        submitted = st.form_submit_button("💾 Wensen voor deze week opslaan", use_container_width=True)
    if submitted:
        try:
            updated = save_week_choices(data, eid, days, pending)
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state[f"week_saved_{scope}_{eid}_{visible['key']}"] = True
            replace_and_rerun(updated)
    if st.session_state.pop(f"week_saved_{scope}_{eid}_{visible['key']}", False):
        st.success("De wensen van deze week zijn opgeslagen. Andere weken bleven ongewijzigd.")
    st.caption("Je kunt een andere week kiezen en die afzonderlijk bewaren. "
               "Niets wordt automatisch als verlofaanvraag ingediend.")
    with st.expander("Mijn volledige maandoverzicht bekijken"):
        if published_view and published_view["revision"] != st.session_state.workspace_revision:
            st.warning("De gepubliceerde planning kan verouderd zijn na wijzigingen in de invoer.")
        st.dataframe(pd.DataFrame(personal_calendar(data, eid, published_view["payload"] if published_view else None)), hide_index=True,
                     use_container_width=True, column_config={"Datum": "Datum", "Wens": "Voorkeur"})


def render_preferences(eid: str, scope: str) -> None:
    """Dagelijkse diensten bovenaan; bestaande overige voorkeuren blijven beschikbaar."""
    render_daily_preferences(eid, scope)
    data = st.session_state.project_data
    # Oude categorie-/algemene dienstwensen blijven bestaan, maar controleurs
    # gebruiken voor nieuwe dienstwensen nu het dagrooster hierboven.
    own = [p for p in data["preferences"] if p["employee_id"] == eid
           and preference_type(p) not in ("free_day", "daily_shift")]
    with st.expander("Overige voorkeuren (optioneel)"):
        if own:
            st.dataframe(pd.DataFrame([{"Type": PREFERENCE_TYPES[preference_type(p)],
                                       "Details": preference_description(p), "Prioriteit": p["priority"]}
                                      for p in own]), hide_index=True, use_container_width=True)
        else:
            st.info("Geen aanvullende voorkeuren geregistreerd voor deze maand.")
        if scope == "own":
            kinds = ["work_day", "weekly_free", "avoid_transition"]
        else:
            kinds = ["work_day", "category", "shift", "weekly_free", "avoid_transition"]
        kind = st.selectbox("Soort aanvullende voorkeur", kinds,
                            format_func=lambda x: PREFERENCE_TYPES[x], key="pref_kind_" + scope)
        with st.form("pref_form_" + scope + "_" + kind):
            pref = {"employee_id": eid, "type": kind}
            if kind == "work_day":
                d = st.date_input("Datum", date(data["year"], data["month"], 1))
                pref["date"] = d.isoformat()
            elif kind == "category":
                pref["category"] = st.selectbox("Categorie", CATEGORIES)
                pref["direction"] = st.radio("Wens", ["prefer", "avoid"], horizontal=True,
                                              format_func=lambda x: "Liefst" if x == "prefer" else "Vermijden")
            elif kind == "shift":
                pref["shift_id"] = st.selectbox("Dienstnummer", [s["id"] for s in data["shifts"]])
                pref["direction"] = st.radio("Wens", ["prefer", "avoid"], horizontal=True,
                                              format_func=lambda x: "Liefst" if x == "prefer" else "Vermijden")
            elif kind == "weekly_free":
                pref["weekday"] = st.selectbox("Weekdag", range(7), format_func=lambda x: WEEKDAYS[x])
            elif kind == "avoid_transition":
                pairs = [catalog.transition_code(a, b) for a in CATEGORIES for b in CATEGORIES]
                pref["transition"] = st.selectbox("Liever niet na elkaar", pairs)
            pref["priority"] = st.select_slider("Prioriteit", options=[1, 2, 3], value=2,
                                                  format_func=lambda x: {1: "Laag", 2: "Normaal", 3: "Hoog"}[x])
            if st.form_submit_button("Aanvullende voorkeur opslaan"):
                state = clone()
                state["preferences"] = [p for p in state["preferences"]
                                        if preference_identity(p) != preference_identity(pref)]
                state["preferences"].append(pref)
                replace_and_rerun(state)
        if own:
            chosen = st.selectbox("Aanvullende voorkeur intrekken", range(len(own)),
                                  format_func=lambda i: PREFERENCE_TYPES[preference_type(own[i])] + " — " + preference_description(own[i]),
                                  key="remove_pref_" + scope)
            if st.button("Verwijder geselecteerde aanvullende voorkeur", key="remove_button_" + scope):
                state = clone()
                key = preference_identity(own[chosen])
                state["preferences"] = [p for p in state["preferences"] if preference_identity(p) != key]
                replace_and_rerun(state)


def reset_month_ui_state() -> None:
    """Widgetstate wissen vóór Streamlit de widgets van de nieuwe maand opbouwt."""
    selected = st.session_state.get("active_period")
    keep = {"signed_id", "signed_hash", "active_period"}
    for key in list(st.session_state):
        if key not in keep:
            del st.session_state[key]
    st.session_state.loaded_period_v012 = selected


if PERSISTENT:
    try:
        month_overview = store.list_month_workspaces(engine)
    except Exception:
        st.error("De afzonderlijke maandwerkruimtes konden niet worden ingelezen. Controleer de database-logboeken.")
        st.stop()
    period_options = [(entry["year"], entry["month"]) for entry in month_overview]
    if not period_options:
        st.error("Geen planningsmaanden gevonden.")
        st.stop()
    requested_period = st.session_state.pop("switch_to_new_month_v012", None)
    if requested_period in period_options:
        # Voer de widgetwaardewijziging uit VOORDAT st.selectbox wordt gemaakt.
        st.session_state.active_period = requested_period
    if st.session_state.get("active_period") not in period_options:
        # Bij eerste opstart behoudt de migratie de maand van versie 0.11.
        st.session_state.active_period = period_options[0]
    if st.session_state.get("loaded_period_v012") != st.session_state.active_period:
        reset_month_ui_state()
    with st.sidebar:
        st.subheader("Kalendermaand")
        selected_period = st.selectbox(
            "Actieve planning", period_options, key="active_period", on_change=reset_month_ui_state,
            format_func=lambda item: f"{item[1]:02d}/{item[0]}" +
                (" · gepubliceerd" if any(m["year"] == item[0] and m["month"] == item[1]
                                         and m["published"] for m in month_overview) else " · concept"),
        )
        if current_user["role"] in ("admin", "planner"):
            with st.expander("➕ Nieuwe maand voorbereiden"):
                next_year = selected_period[0] + (1 if selected_period[1] == 12 else 0)
                next_month = 1 if selected_period[1] == 12 else selected_period[1] + 1
                new_period_date = st.date_input("Nieuwe kalendermaand", date(next_year, next_month, 1),
                                                format="DD/MM/YYYY")
                source_kind = st.radio("Startinhoud", ["Lege maand", "Maandbehoefte kopiëren"],
                                       key="new_month_content_v013")
                source_period = None
                copy_mode = "weekday"
                if source_kind == "Maandbehoefte kopiëren":
                    available_sources = [p for p in period_options if next((r["has_demand"]
                                        for r in month_overview if (r["year"], r["month"]) == p), False)]
                    if not available_sources:
                        st.warning("Er is nog geen maand met een ingevulde dienstbehoefte.")
                    else:
                        source_period = st.selectbox("Kopieer diensten uit", available_sources,
                            index=available_sources.index(selected_period) if selected_period in available_sources else 0,
                            format_func=lambda p: f"{p[1]:02d}/{p[0]}", key="new_month_source_v013")
                        copy_mode = st.selectbox("Kopieermethode",
                            ["weekday", "date"],
                            format_func=lambda v: "Zelfde weekdag (1e maandag → 1e maandag)" if v == "weekday"
                                                  else "Zelfde kalenderdag (1 → 1)",
                            key="new_month_mode_v013")
                        st.caption("Alleen dienstbehoefte; geen toewijzingen, voorkeuren of verlof. "
                                   "Een extra vijfde weekdag neemt het patroon van de laatste overeenkomstige bronweekdag over.")
                if st.button("Maand aanmaken", key="create_month_v012",
                             disabled=(source_kind == "Maandbehoefte kopiëren" and source_period is None)):
                    try:
                        chosen = (new_period_date.year, new_period_date.month)
                        store.create_month_workspace(engine, *chosen, current_user["employee_id"],
                             source_period=source_period if source_kind == "Maandbehoefte kopiëren" else None,
                             copy_mode=copy_mode)
                        st.session_state.switch_to_new_month_v012 = chosen
                        st.rerun()
                    except (ValueError, store.ConflictError) as error:
                        st.error(str(error))
        st.caption("Maandbehoefte, voorkeuren en afwezigheden zijn per maand gescheiden.")
    try:
        loaded, revision = store.load_month_workspace(engine, *selected_period)
    except Exception:
        st.error("De gekozen maand kon niet worden opgehaald.")
        st.stop()
    previous_revision = st.session_state.get("workspace_revision")
    st.session_state.project_data = loaded
    st.session_state.workspace_revision = revision
    if previous_revision is not None and previous_revision != revision:
        st.session_state.remote_change_notice = True
        for widget_key in list(st.session_state.keys()):
            if widget_key.startswith(("daily_choice_", "daily_priority_")):
                del st.session_state[widget_key]
        st.session_state.pop("last_plan", None)
        st.session_state.pop("alternatives_v09", None)
        st.rerun()
elif "project_data" not in st.session_state:
    st.session_state.project_data = build_demo()

data = st.session_state.project_data
is_manager = not PERSISTENT or current_user["role"] in ("admin", "planner")

st.title("📅 Controleursplanning")
st.caption("Proefversie 0.28 • Individuele weekendrotatie en urenbalans • GitHub + Streamlit + Google OR-Tools")
if st.session_state.pop("remote_change_notice", False):
    st.info("Een andere gebruiker heeft intussen gegevens opgeslagen. De nieuwste versie is geladen; controleer je invoer opnieuw.")
st.warning("**TESTVERSIE — uitsluitend fictieve gegevens.** Niet vrijgegeven voor echte personeelsgegevens of operationele beslissingen. Arbeidsregels zijn nog niet volledig gevalideerd.")

with st.sidebar:
    st.header("Proefproject")
    st.write(f"Planningsmaand: **{data['month']:02d}/{data['year']}**")
    if PERSISTENT:
        st.success("PostgreSQL — gedeelde testgegevens")
        st.caption(f"Aangemeld: {current_user['name']} ({current_user['role']})")
        if st.button("Afmelden", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    else:
        st.info("Demomodus zonder database: wijzigingen zijn alleen binnen deze sessie beschikbaar.")
    if is_manager:
        st.download_button("⬇️ Bewaar demo als JSON", data=json.dumps(data, ensure_ascii=False, indent=2),
                           file_name="controleursplanning-demo.json", mime="application/json", use_container_width=True)
        upload_state = st.file_uploader("Eerder bewaarde demo laden", type=["json"], key="json_upload")
        if st.button("JSON importeren", disabled=upload_state is None, use_container_width=True):
            try:
                if upload_state.size > 2 * 1024 * 1024:
                    raise ValueError("Maximaal 2 MB per JSON-bestand.")
                incoming = json.load(upload_state)
                problems = validate_dataset(incoming)
                if problems:
                    st.error("Import geweigerd: " + " ".join(problems))
                else:
                    replace_and_rerun(incoming)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                st.error(f"Kon gegevens niet laden: {exc}")
        if st.button("🔄 Fictieve voorbeeldgegevens herstellen", use_container_width=True):
            st.warning("Let op: de gedeelde controleurs en dienstcatalogus worden hierdoor ook voor andere maanden aangepast.")
            replace_and_rerun(build_demo(data["year"], data["month"]))
    st.divider()
    st.caption("Niet gekoppeld aan systemen van De Lijn.")

screens = (["Overzicht", "Controleurs", "Diensten", "Taken", "Maandbehoefte", "Voorkeuren", "Uren en activiteiten", "Urenbalans", "Planningsregels", "Weekend en maandgrenzen", "Planning", "Roostercontrole", "Optimalisatie vergelijken", "Rapportage en eerlijkheid"]
           if is_manager else ["Mijn planning", "Mijn voorkeuren", "Mijn aanvragen & wijzigingen"])
if PERSISTENT:
    screens += (["Verlofaanvragen beheren", "Ruilaanvragen beheren", "Roosterwijzigingen", "Publicatiebeheer"] if is_manager else ["Mijn verlofaanvragen", "Mijn ruilaanvragen"])
    screens += ["Meldingen"]
if PERSISTENT and current_user["role"] == "admin":
    screens += ["Accounts", "Historiek"]
if PERSISTENT:
    try:
        unread = sum(not n["read"] for n in store.notifications_for(engine, current_user["employee_id"]))
        with st.sidebar:
            st.caption(f"🔔 {unread} ongelezen melding(en). Open het tabblad Meldingen.")
    except Exception:
        st.warning("Meldingen konden niet worden geladen; de overige functies blijven beschikbaar.")
screen = st.radio("Onderdeel", screens, horizontal=True, label_visibility="collapsed")

if screen == "Overzicht":
    st.subheader("Beheerdersdashboard")
    a, b, c, d = st.columns(4)
    a.metric("Controleurs", sum(bool(e.get("active", True)) for e in data["employees"]))
    b.metric("Dienstnummers", len(data["shifts"]))
    c.metric("Dienstplaatsen deze maand", sum(r["required"] for r in data["demand"]))
    d.metric("Vrijwensen", len(data["preferences"]))
    st.caption(f"Takencatalogus: {len(data.get('tasks', []))} taken, {len(data.get('task_needs', []))} ingeplande taakblokken.")
    if PERSISTENT:
        st.markdown("### Planningstatus en opvolging")
        # Een fout in oude planversies of in het aanvraagoverzicht mag de
        # rest van de webapp en het gewone maandoverzicht niet blokkeren.
        overview_rows = []
        try:
            snapshots = store.dashboard_month_snapshots(engine, current_user["employee_id"])
            overview_rows = [summarize_month(snapshot) for snapshot in snapshots]
        except ValueError as error:
            logging.exception("DASHBOARD_V0141_MONTHS: ongeldige maandstatus of ontbrekende rechten")
            st.error(f"Maandstatus niet beschikbaar ({type(error).__name__}). "
                     "Bekijk de Streamlit-logboeken bij DASHBOARD_V0141_MONTHS.")
        except Exception as error:
            logging.exception("DASHBOARD_V0141_MONTHS: fout tijdens ophalen of samenvatten")
            st.error(f"Maandstatus niet beschikbaar ({type(error).__name__}). "
                     "Bekijk de Streamlit-logboeken bij DASHBOARD_V0141_MONTHS.")

        leave_requests, swap_requests = [], []
        leave_ok, swap_ok = True, True
        try:
            leave_requests = store.list_leave_requests(engine, current_user["employee_id"])
        except Exception as error:
            leave_ok = False
            logging.exception("DASHBOARD_V0141_LEAVE: verlofaanvragen konden niet worden opgehaald")
            st.warning(f"Verlofstatistieken tijdelijk niet beschikbaar ({type(error).__name__}). "
                       "Details: DASHBOARD_V0141_LEAVE in de logboeken.")
        try:
            swap_requests = store.list_swap_requests(engine, current_user["employee_id"])
        except Exception as error:
            swap_ok = False
            logging.exception("DASHBOARD_V0141_SWAP: ruilaanvragen konden niet worden opgehaald")
            st.warning(f"Ruilstatistieken tijdelijk niet beschikbaar ({type(error).__name__}). "
                       "Details: DASHBOARD_V0141_SWAP in de logboeken.")
        # Deze tellers zijn bij een ontbrekende bron onbekend, niet nul.
        requests_available = leave_ok and swap_ok
        if not overview_rows:
            st.info("Het bovenste maandoverzicht blijft beschikbaar. "
                    "De uitgebreide maandstatus wordt pas getoond zodra de rapportagequery weer slaagt.")
        if overview_rows:
            counts = dashboard_counts(overview_rows)
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Aangemaakte maanden", counts["months"])
            k2.metric("Maanden gepubliceerd", counts["published"])
            k3.metric("Verouderde planversies", counts["outdated"])
            k4.metric("Lege maanden", counts["without_demand"])

            years = sorted({r["year"] for r in overview_rows})
            year_filter = st.selectbox("Kalenderjaar", ["Alle jaren"] + years,
                                       key="dashboard_year_v014")
            selected_rows = [r for r in overview_rows if year_filter == "Alle jaren" or r["year"] == year_filter]
            formatted_rows = [{
                "Maand": r["period"], "Status": r["status"],
                "Dienstregels": r["demand_lines"], "Dienstplaatsen nodig": r["required_now"],
                "Taakplaatsen": r["task_places"], "Voorkeuren": r["preferences"],
                "Toegewezen (laatste bewaarde plan)": r["assigned"],
                "Open (laatste bewaarde plan)": r["open"],
                "Bezetting laatste plan (%)": r["coverage"],
                "Plan-ID": r["plan_id"],
            } for r in selected_rows]
            frame = pd.DataFrame(formatted_rows)
            st.dataframe(frame, hide_index=True, use_container_width=True)
            st.caption("De toewijzingen en bezettingsgraad komen uit het laatst gepubliceerde plan, "
                       "of uit het laatste concept als nog niets is gepubliceerd. "
                       "Bij gewijzigde invoer zijn deze cijfers mogelijk verouderd.")
            if selected_rows:
                selected = st.selectbox("Details bekijken voor maand", selected_rows,
                                        format_func=lambda r: f'{r["period"]} · {r["status"]}',
                                        index=next((i for i, r in enumerate(selected_rows)
                                            if (r["year"], r["month"]) == (data["year"], data["month"])), 0),
                                        key="dashboard_detail_v014")
                st.markdown(f'#### Aandachtspunten {selected["period"]}')
                warnings = dashboard_warnings(selected)
                for warning in warnings:
                    st.warning(warning)
                if not warnings:
                    st.success("Geen openstaande aandachtspunten in dit basisoverzicht. "
                               "Dit is geen volledige controle op wettelijke arbeidsregels.")
                if requests_available:
                    counts_requests = summarize_requests(leave_requests, swap_requests,
                                                           selected["year"], selected["month"])
                    r1, r2, r3 = st.columns(3)
                    r1.metric("Verlof wacht op beslissing", counts_requests["leave_pending"])
                    r2.metric("Ruil wacht op collega", counts_requests["swaps_awaiting_colleague"])
                    r3.metric("Ruil wacht op planner", counts_requests["swaps_awaiting_planner"])
                else:
                    st.info("Aanvraagstatistieken zijn niet volledig beschikbaar; geen nulwaarden aangenomen.")
                st.caption("Voor het behandelen van aanvragen gebruik je de afzonderlijke aanvraagtabbladen. "
                           "Om deze maand te bewerken selecteer je ze links bij Kalendermaand.")
            if len(selected_rows) > 1:
                st.markdown("#### Dienstplaatsen per maand")
                chart_data = pd.DataFrame([{
                    "Maand": r["period"], "Benodigd": r["required_now"]
                } for r in selected_rows]).set_index("Maand")
                st.bar_chart(chart_data, use_container_width=True)
            report_buffer = io.BytesIO()
            with pd.ExcelWriter(report_buffer, engine="openpyxl") as writer:
                frame.to_excel(writer, index=False, sheet_name="Maandoverzicht")
            st.download_button("⬇️ Exporteer dashboard naar Excel", report_buffer.getvalue(),
                               file_name="controleursplanning-dashboard-v014.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.caption("In de demomodus worden geen opgeslagen maanden of aanvragen uit de database geladen.")
    st.info("Begin bij **Controleurs** en **Diensten**. Pas daarna in **Maandbehoefte** de te plannen diensten aan en klik in **Planning** op 'Bereken planning'.")
    if "last_plan" in st.session_state:
        plan = st.session_state.last_plan
        st.write(f"Laatste berekening: **{plan.status}** — {plan.summary['assigned']} toegewezen, {plan.summary['open']} openstaande plaatsen.")
    st.markdown("""**Wat is in deze proefversie al mogelijk?**

- Fictieve controleurs toevoegen en inzetbaarheidsbeperkingen wijzigen.
- Dienstnummers met vaste uren, categorie en benodigde bezetting beheren.
- Per datum de dienstbehoefte invoeren of vanuit Excel importeren.
- Gewenste vrije dagen en voorkeurscategorieën registreren.
- Met OR-Tools een maandplanning berekenen, rekening houdend met beschikbare basisregels.
- Een gedeeltelijke planning met openstaande dienstplaatsen tonen en naar Excel exporteren.

**In v0.6:** weekendbescherming, instelbare weekend-/maandmaxima, streefaantallen per categorie en een proefberekening van urensaldo. **In v0.5:** vaste rustdagen per profiel, zes soorten zachte voorkeuren en testurenoverzicht. **In v0.4:** algemene en individuele dienstreeksen, dienstovergangen, aanvullende rustregels en zachte maandstreefuren. **In v0.3:** uitgebreid controleurs- en dienstenbeheer met team, tijdelijke blokkeringen en begin-/eindlocatie. Sinds v0.2: aanmelden met personeelsnummer, afzonderlijke rollen, gedeelde PostgreSQL-gegevens, auditlog en conceptplanning/publicatie in testmodus. Zonder ingestelde DATABASE_URL blijft de oude demomodus beschikbaar.

**In v0.7:** taaktoewijzing binnen bestaande diensten met kwalificatiecontrole en keuze om gepubliceerde weekendhistoriek mee te nemen.

**In v0.8:** tijdelijke vrijstellingen en zelfstandige taken. **In v0.9:** opgeslagen optimalisatieprofielen en meerdere planningsalternatieven. **In v0.9.1:** concrete dienstwensen per datum. **In v0.10:** verlof aanvragen, beoordelen en goedgekeurde dagen automatisch blokkeren voor toekomstige berekeningen. **Nog niet gebouwd:** uitgebreide ruilen met taken, volledige aanvragen- en goedkeuringsstromen, wettelijke validatie, zelfstandige teamplanning, regels over maandgrenzen en automatische back-ups.""")

elif screen == "Controleurs":
    st.subheader("Controleursbeheer")
    st.caption("Profielen zijn gekoppeld aan het unieke personeelsnummer. Reeds aangemaakte profielen deactiveren we in plaats van ze te verwijderen.")
    records = [catalog.profile(e) for e in data["employees"]]
    st.dataframe(pd.DataFrame([{
        "Personeelsnr": e["id"], "Naam": e["name"], "Team": e["team"],
        "Regime %": e["contract_percent"], "Max. maanduren": e["max_month_hours"],
        "Streefuren": e["target_month_hours"], "Pers. rust (uur)": e["min_rest_hours"],
        "Rustdagenregeling": REST_MODES[e["rest_mode"]],
        "Verboden categorieën": ", ".join(e["blocked_categories"]),
        "Geblokkeerde periodes": len(e["blocked_periods"]), "Actief": e["active"]
    } for e in records]), use_container_width=True, hide_index=True)
    tab_add, tab_edit, tab_periods, tab_rest = st.tabs(["Nieuwe controleur", "Profiel en beperkingen", "Tijdelijke onbeschikbaarheid", "Rustdagenregeling"])
    with tab_add:
        with st.form("create_emp", clear_on_submit=True):
            id_ = st.text_input("Uniek testpersoneelsnummer", placeholder="DEMO017", max_chars=64)
            name = st.text_input("Naam", placeholder="Testcontroleur 17", max_chars=160)
            team = st.text_input("Team / werkgebied", value="Demoteam", max_chars=80)
            c1, c2 = st.columns(2)
            with c1:
                contract = st.number_input("Arbeidsregime (%)", 1, 100, 100, key="new_contract")
            with c2:
                max_hours = st.number_input("Maximum in te plannen uren / maand", 1, 250, 176, key="new_max_hours")
            if st.form_submit_button("Controleur toevoegen"):
                state = clone()
                identifier = id_.strip()
                if identifier in {e["id"] for e in state["employees"]}:
                    st.error("Dit personeelsnummer bestaat al.")
                else:
                    candidate = catalog.new_employee(identifier, name, team, contract, max_hours)
                    issues = catalog.validate_employee(candidate, {s["id"] for s in data["shifts"]})
                    if issues:
                        for issue in issues:
                            st.error(issue)
                    else:
                        state["employees"].append(candidate)
                        replace_and_rerun(state)
    with tab_edit:
        if data["employees"]:
            selected_id = st.selectbox("Controleur kiezen", [e["id"] for e in data["employees"]],
                                       format_func=lambda i: next(e["name"] for e in data["employees"] if e["id"] == i),
                                       key="edit_employee_id")
            emp = catalog.profile(next(e for e in data["employees"] if e["id"] == selected_id))
            with st.form("edit_emp"):
                name = st.text_input("Naam", value=emp["name"], max_chars=160)
                team = st.text_input("Team / werkgebied", value=emp["team"], max_chars=80)
                col1, col2 = st.columns(2)
                with col1:
                    contract = st.number_input("Arbeidsregime (%)", 1, 100, int(emp["contract_percent"]))
                    max_hours = st.number_input("Maximum in te plannen maanduren", 1, 250, int(emp["max_month_hours"]))
                    target_hours = st.number_input("Streefuren in deze maand (0 = geen)", 0, int(emp["max_month_hours"]),
                                                  min(int(emp["target_month_hours"]), int(emp["max_month_hours"])))
                    preferred = st.selectbox("Zachte voorkeurscategorie", ["Geen", *CATEGORIES],
                                             index=["Geen", *CATEGORIES].index(emp["preferred_category"]))
                with col2:
                    blocked_cats = st.multiselect("Verboden dienstcategorieën", CATEGORIES,
                                                   default=emp["blocked_categories"])
                    blocked_shifts = st.multiselect("Verboden dienstnummers", [s["id"] for s in data["shifts"]],
                                                   default=emp["blocked_shifts"])
                    blocked_weekdays = st.multiselect("Niet beschikbaar op deze weekdagen", list(range(7)),
                                                      default=emp["blocked_weekdays"], format_func=lambda n: WEEKDAYS[n])
                individual_limit = st.number_input("Max. opeenvolgende werkdagen (0 = algemene regel)", 0, 7,
                                                   int(emp["max_consecutive"] or 0))
                custom_rest = st.number_input("Individuele minimale rust (uren, 0 = algemene regel)", 0, 48,
                                              int(emp["min_rest_hours"] or 0))
                st.markdown("**Maximaal opeenvolgende diensten per categorie**")
                max_runs = {}
                cols_runs = st.columns(4)
                for idx, category in enumerate(CATEGORIES):
                    with cols_runs[idx]:
                        run = st.number_input(category + " (0 = algemeen)", 0, 7,
                                              int(emp["max_category_run"].get(category, 0)),
                                              key="emp_run_" + selected_id + "_" + category)
                        if run:
                            max_runs[category] = int(run)
                all_pairs = [catalog.transition_code(a, b) for a in CATEGORIES for b in CATEGORIES]
                blocked_pairs = st.multiselect("Verboden overgangen voor deze controleur (aaneensluitende dagen)",
                                               all_pairs, default=emp["blocked_transitions"])
                st.markdown("**Taakbevoegdheden (v0.7)**")
                known_quals = sorted(({t.get("qualification", "") for t in data.get("tasks", []) if t.get("qualification", "")}) | set(emp.get("qualifications", [])))
                qualifications = st.multiselect("Behaalde taakbevoegdheden", known_quals,
                                                default=[q for q in emp.get("qualifications", []) if q in known_quals],
                                                help="Voeg een bevoegdheid eerst toe bij een taak in de takencatalogus.")
                blocked_tasks = st.multiselect("Individueel uitgesloten taken", [t["id"] for t in data.get("tasks", [])],
                                               default=emp.get("blocked_tasks", []))
                active = st.checkbox("Controleur actief", value=bool(emp["active"]))
                st.caption("Deze beperkingen zijn verplicht voor de solver. De voorkeur voor een dienstcategorie is een zachte wens.")
                if st.form_submit_button("Profiel bewaren"):
                    state = clone()
                    target = next(e for e in state["employees"] if e["id"] == selected_id)
                    target.update({"name": name.strip(), "team": team.strip(),
                                   "contract_percent": int(contract), "max_month_hours": int(max_hours),
                                   "preferred_category": preferred, "blocked_categories": blocked_cats,
                                   "blocked_shifts": blocked_shifts, "blocked_weekdays": blocked_weekdays,
                                   "max_consecutive": int(individual_limit) or None,
                                   "min_rest_hours": int(custom_rest) or None,
                                   "target_month_hours": int(target_hours),
                                   "max_category_run": max_runs,
                                   "blocked_transitions": blocked_pairs,
                                   "qualifications": qualifications, "blocked_tasks": blocked_tasks,
                                   "active": active})
                    replace_and_rerun(state)
    with tab_periods:
        if data["employees"]:
            selected_id = st.selectbox("Controleur", [e["id"] for e in data["employees"]],
                                       format_func=lambda i: next(e["name"] for e in data["employees"] if e["id"] == i),
                                       key="period_employee_id")
            emp = catalog.profile(next(e for e in data["employees"] if e["id"] == selected_id))
            st.caption("Harde, tijdelijke blokkering: de controleur mag op deze datums niet worden ingepland. Geen verwerking van verlofrechten of medische informatie.")
            periods = emp["blocked_periods"]
            if periods:
                st.dataframe(pd.DataFrame([{"Vanaf": p["start"], "Tot en met": p["end"]} for p in periods]),
                             use_container_width=True, hide_index=True)
            else:
                st.info("Voor deze testcontroleur zijn nog geen tijdelijke periodes geblokkeerd.")
            with st.form("add_period"):
                start_date = st.date_input("Vanaf", value=date(int(data["year"]), int(data["month"]), 1), key="period_start")
                end_date = st.date_input("Tot en met", value=date(int(data["year"]), int(data["month"]), 1), key="period_end")
                if st.form_submit_button("Onbeschikbare periode toevoegen"):
                    state = clone()
                    target = next(e for e in state["employees"] if e["id"] == selected_id)
                    combined = list(target.get("blocked_periods", [])) + [{"start": start_date.isoformat(), "end": end_date.isoformat()}]
                    issues = catalog.validate_periods(combined)
                    if issues:
                        for issue in issues:
                            st.error(issue)
                    else:
                        target["blocked_periods"] = sorted(combined, key=lambda p: (p["start"], p["end"]))
                        replace_and_rerun(state)
            if periods:
                to_remove = st.selectbox("Periode verwijderen", range(len(periods)),
                                         format_func=lambda i: f"{periods[i]['start']} t/m {periods[i]['end']}",
                                         key="remove_period")
                if st.button("Geselecteerde periode verwijderen", type="secondary"):
                    state = clone()
                    target = next(e for e in state["employees"] if e["id"] == selected_id)
                    target["blocked_periods"].pop(to_remove)
                    replace_and_rerun(state)


    with tab_rest:
        st.markdown("#### Individuele rustdagenregeling")
        st.caption("Vast en combinatie blokkeren expliciet aangeduide datums en weekdagen. "
                   "Automatisch legt geen extra vaste rustdagen op. Overige vrije dagen ontstaan "
                   "door de automatische dienstverdeling; er is nog geen volledige vaste werkcyclus.")
        chosen_rest = st.selectbox("Controleur voor rustdagen", [e["id"] for e in data["employees"]],
                                   format_func=lambda i: next(e["name"] for e in data["employees"] if e["id"] == i),
                                   key="rest_employee")
        rest_employee = catalog.profile(next(e for e in data["employees"] if e["id"] == chosen_rest))
        with st.form("rest_config"):
            rest_mode = st.radio("Methode", list(REST_MODES),
                                 index=list(REST_MODES).index(rest_employee["rest_mode"]),
                                 format_func=lambda m: REST_MODES[m], horizontal=True)
            rest_weekdays = st.multiselect("Vaste rustdagen per week", range(7),
                                           default=rest_employee["fixed_rest_weekdays"],
                                           format_func=lambda d: WEEKDAYS[d])
            if st.form_submit_button("Rustdagenregeling opslaan"):
                state = clone()
                emp0 = next(e for e in state["employees"] if e["id"] == chosen_rest)
                emp0["rest_mode"] = rest_mode
                emp0["fixed_rest_weekdays"] = rest_weekdays
                replace_and_rerun(state)
        st.markdown("**Vaste rustdatums**")
        rest_dates = rest_employee["fixed_rest_dates"]
        if rest_dates:
            st.write(", ".join(sorted(rest_dates)))
        with st.form("rest_date_add"):
            rest_date = st.date_input("Extra rustdatum", value=date(data["year"], data["month"], 1))
            if st.form_submit_button("Vaste rustdatum toevoegen"):
                state = clone()
                target = next(e for e in state["employees"] if e["id"] == chosen_rest)
                target["fixed_rest_dates"] = sorted(set(target.get("fixed_rest_dates", [])) | {rest_date.isoformat()})
                replace_and_rerun(state)
        if rest_dates:
            del_rest = st.selectbox("Rustdatum opheffen", sorted(rest_dates))
            if st.button("Geselecteerde rustdatum verwijderen"):
                state = clone()
                target = next(e for e in state["employees"] if e["id"] == chosen_rest)
                target["fixed_rest_dates"] = [d for d in target.get("fixed_rest_dates", []) if d != del_rest]
                replace_and_rerun(state)

elif screen == "Diensten":
    st.subheader("Dienstencatalogus per maand (v0.26.2)")
    if invalid_activities(data):
        st.warning(f"Er zijn {len(invalid_activities(data))} activiteiten met een onbekende controleur "
                   "of een datum buiten de actieve maand. Diensturen wijzigen kan nu veilig zonder "
                   "die activiteiten te wissen. Een nieuwe planning berekenen vereist wel herstel: "
                   "**Uren en activiteiten → Oude activiteiten controleren**.")
    st.info(f"Je bewerkt uitsluitend de diensten voor **{data['month']:02d}/{data['year']}**. "
            "Andere al aangemaakte maanden behouden hun eigen diensturen, categorieën en bezetting. "
            "Nieuwe maanden nemen de dienstdefinities van de meest recente voorafgaande maand over.")
    st.caption("Een dienstnummer heeft binnen deze maand vaste werkuren en een vast benodigd aantal controleurs. "
               "Een nachtdienst mag over middernacht lopen.")
    st.dataframe(pd.DataFrame([{
        "Dienstnummer": s["id"], "Omschrijving": s["name"], "Categorie": s["category"],
        "Begin": s["start"], "Einde": s["end"], "Bezetting": s["required"],
        "Beginlocatie": s["start_location"], "Eindlocatie": s["end_location"], "Actief": s["active"]
    } for s in (catalog.shift_details(sh) for sh in data["shifts"])]),
        hide_index=True, use_container_width=True)
    mode = st.radio("Bewerking", ["Bestaande dienst wijzigen", "Dienst toevoegen"], horizontal=True)
    selected = st.selectbox("Dienstnummer", [s["id"] for s in data["shifts"]]) if mode.startswith("Bestaande") and data["shifts"] else None
    sh = catalog.shift_details(next(s for s in data["shifts"] if s["id"] == selected)) if selected else None
    with st.form("shift_form"):
        code = st.text_input("Dienstnummer", value=sh["id"] if sh else "", disabled=bool(sh), max_chars=40)
        name = st.text_input("Omschrijving", value=sh["name"] if sh else "", max_chars=160)
        cat = st.selectbox("Dienstcategorie", CATEGORIES, index=CATEGORIES.index(sh["category"]) if sh else 0)
        col1, col2, col3 = st.columns(3)
        with col1:
            start = st.text_input("Beginuur (UU:MM)", value=sh["start"] if sh else "08:00")
        with col2:
            end = st.text_input("Einduur (UU:MM)", value=sh["end"] if sh else "16:00")
        with col3:
            required = st.number_input("Vaste bezetting", 0, 50, int(sh["required"]) if sh else 1)
        col4, col5 = st.columns(2)
        with col4:
            start_location = st.text_input("Beginlocatie", value=sh["start_location"] if sh else "Demo Gent", max_chars=120)
        with col5:
            end_location = st.text_input("Eindlocatie", value=sh["end_location"] if sh else "Demo Gent", max_chars=120)
        active = st.checkbox("Dienst actief", value=sh["active"] if sh else True)
        st.caption("Begin- en eindlocaties worden bewaard en getoond; verplaatsingstijden worden in deze versie nog niet berekend.")
        if st.form_submit_button("Dienst bewaren"):
            state = clone()
            entry = {"id": code.strip(), "name": name.strip(), "category": cat, "start": start.strip(),
                     "end": end.strip(), "required": int(required),
                     "location": start_location.strip(), "start_location": start_location.strip(),
                     "end_location": end_location.strip(), "active": active}
            issues = catalog.validate_shift(entry)
            if not sh and any(s["id"] == entry["id"] for s in state["shifts"]):
                issues.append("Dit dienstnummer bestaat al.")
            if not active and any(r["shift_id"] == entry["id"] for r in state["demand"]):
                issues.append("Deze dienst staat nog in de maandbehoefte. Verwijder hem daar eerst voordat je hem deactiveert.")
            if issues:
                for issue in issues:
                    st.error(issue)
            else:
                try:
                    if PERSISTENT:
                        # Beperk de mutatie server-side tot één dienst: bestaande
                        # afwijkende activiteiten blijven ongewijzigd bewaard.
                        store.save_month_shift(
                            engine, int(data["year"]), int(data["month"]),
                            st.session_state.workspace_revision, current_user["employee_id"],
                            entry, selected if sh else None)
                        st.session_state.pop("last_plan", None)
                        st.session_state.pop("alternatives_v09", None)
                        st.rerun()
                    else:
                        updated = apply_month_shift(state, entry, selected if sh else None)
                        replace_and_rerun(updated)
                except (ValueError, store.ConflictError) as error:
                    st.error(str(error))
    st.info("Wijzigingen gelden alleen voor deze maand. Een gewijzigde bezetting past de behoefte "
            "in deze maand aan. Bestaande gepubliceerde versies blijven historisch bewaard; "
            "bereken een nieuw concept om deze maand met de nieuwe diensturen te plannen. "
            "Let op: eerder aangemaakte toekomstige maanden worden niet automatisch bijgewerkt.")

elif screen == "Taken":
    st.subheader("Takencatalogus en taakbehoefte (v0.8)")
    st.info("Drie taakvormen: binnen de dienst en meetellen, tijdelijk vrijgesteld van reguliere bezetting, "
            "of een zelfstandige opdracht die die werkdag de gewone dienst vervangt. "
            "Bij tijdelijke vrijstelling kan OR-Tools een extra controleur op de dienst zetten.")
    tasks = data.get("tasks", [])
    needs = data.get("task_needs", [])
    t1, t2 = st.tabs(["Takencatalogus", "Taken per datum"])
    with t1:
        if tasks:
            st.dataframe(pd.DataFrame([{"Taakcode": t["id"], "Omschrijving": t["name"],
                                        "Bevoegdheid": t.get("qualification", "") or "Geen",
                                        "Categorie zelfstandige taak": t.get("category", "Dag"),
                                        "Actief": t.get("active", True)} for t in tasks]),
                         hide_index=True, use_container_width=True)
        with st.form("new_task", clear_on_submit=True):
            tid = st.text_input("Nieuwe taakcode", max_chars=40, placeholder="ACTIE01")
            tname = st.text_input("Omschrijving", max_chars=120, placeholder="Fictieve bijzondere controle")
            qual = st.text_input("Vereiste bevoegdheid (leeg = geen)", max_chars=64)
            category = st.selectbox("Categorie als zelfstandige opdracht", CATEGORIES, index=1)
            if st.form_submit_button("Taak toevoegen"):
                state = clone()
                state.setdefault("tasks", []).append({"id": tid.strip(), "name": tname.strip(),
                                                       "qualification": qual.strip(),
                                                       "category": category, "active": True})
                replace_and_rerun(state)
        if tasks:
            to_edit = st.selectbox("Taak aanpassen", [t["id"] for t in tasks])
            definition = next(t for t in tasks if t["id"] == to_edit)
            with st.form("edit_task"):
                edit_name = st.text_input("Naam", definition["name"], max_chars=120)
                edit_qual = st.text_input("Bevoegdheid", definition.get("qualification", ""), max_chars=64)
                edit_category = st.selectbox("Categorie zelfstandige opdracht", CATEGORIES,
                                             index=CATEGORIES.index(definition.get("category", "Dag")))
                edit_active = st.checkbox("Taak actief", definition.get("active", True))
                if st.form_submit_button("Taak aanpassen"):
                    state = clone()
                    target = next(t for t in state["tasks"] if t["id"] == to_edit)
                    target.update({"name": edit_name.strip(), "qualification": edit_qual.strip(),
                                   "category": edit_category, "active": edit_active})
                    replace_and_rerun(state)
    with t2:
        if needs:
            st.dataframe(pd.DataFrame(needs), hide_index=True, use_container_width=True)
        st.caption("Oude taakblokken zonder type blijven automatisch 'binnen dienst — telt mee'.")
        if not tasks:
            st.info("Voeg eerst een taak toe aan de takencatalogus.")
        else:
            mode = st.selectbox("Planningsvorm", list(MODES), format_func=lambda m: MODES[m],
                                key="task_mode_v08")
            import calendar
            if mode == "standalone":
                dates_available = [date(data["year"], data["month"], i).isoformat()
                                   for i in range(1, calendar.monthrange(data["year"], data["month"])[1] + 1)]
            else:
                dates_available = sorted({r["date"] for r in data["demand"] if r["required"] > 0})
            if not dates_available:
                st.warning("Er zijn geen actieve diensten om een taak aan te koppelen.")
            else:
                on_date = st.selectbox("Datum", dates_available, key="task_date_v08")
                shifts_today = [r["shift_id"] for r in data["demand"]
                                if r["date"] == on_date and r["required"] > 0]
                with st.form("add_task_need", clear_on_submit=True):
                    shid = None
                    if mode != "standalone":
                        shid = st.selectbox("Dienstnummer", shifts_today) if shifts_today else None
                    else:
                        st.caption("Deze opdracht heeft geen dienstnummer. De controleur krijgt die dag geen gewone dienst.")
                    active_tasks = [t["id"] for t in tasks if t.get("active", True)]
                    taskid = st.selectbox("Taak", active_tasks) if active_tasks else None
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        task_start = st.text_input("Begin (UU:MM)", value="09:00")
                    with col2:
                        task_end = st.text_input("Einde (UU:MM)", value="10:00")
                    with col3:
                        required_people = st.number_input("Aantal controleurs", 1, 30, 1)
                    if st.form_submit_button("Taakblok toevoegen", disabled=not (taskid and (mode == "standalone" or shid))):
                        state = clone()
                        state.setdefault("task_needs", []).append({"date": on_date, "shift_id": shid,
                                                                   "task_id": taskid, "mode": mode,
                                                                   "start": task_start.strip(), "end": task_end.strip(),
                                                                   "required": int(required_people)})
                        replace_and_rerun(state)
        if needs:
            choice = st.selectbox("Taakblok verwijderen", range(len(needs)),
                                  format_func=lambda i: f"{needs[i]['date']} | {needs[i].get('shift_id') or 'Zelfstandig'} | {needs[i]['task_id']} | {MODES.get(need_mode(needs[i]), '?')}")
            if st.button("Verwijder taakblok"):
                state = clone()
                state["task_needs"].pop(choice)
                replace_and_rerun(state)
        st.caption("Een tijdelijke vrijstelling vermindert de beschikbare dienstbezetting tijdens het tijdsblok. "
                   "Een zelfstandige taak telt voor uren en rust als een aparte daginzet. Open taakplaatsen worden gerapporteerd.")

elif screen == "Maandbehoefte":
    st.subheader("Welke dienstnummers zijn op welke dagen nodig?")
    month_start = date(int(data["year"]), int(data["month"]), 1)
    st.info("Je werkt nu in **" + f"{data['month']:02d}/{data['year']}" +
            "**. Je kunt een maand leeg starten of de dienstbehoefte uit een eerdere maand overnemen.")
    if PERSISTENT and is_manager and not data["demand"]:
        with st.expander("📋 Dienstbehoefte uit een andere maand overnemen"):
            previous_sources = [p for p in period_options if p != selected_period and next(
                (bool(r["has_demand"]) for r in month_overview if (r["year"], r["month"]) == p), False)]
            if not previous_sources:
                st.info("Er is nog geen andere maand met een ingevulde dienstbehoefte.")
            else:
                src = st.selectbox("Bronmaand", previous_sources,
                    format_func=lambda p: f"{p[1]:02d}/{p[0]}", key="existing_month_source_v013")
                mode = st.radio("Kopieermethode", ["weekday", "date"],
                    format_func=lambda v: "Overeenkomstige weekdag" if v == "weekday" else "Zelfde kalenderdag",
                    key="existing_month_mode_v013")
                try:
                    source_data, _ = store.load_month_workspace(engine, *src)
                    preview = copy_month_demand_rows(source_data, data["year"], data["month"],
                                                     data["shifts"], mode)
                    st.caption(f"{len(preview)} dienstregels worden overgenomen; bestaande voorkeuren, "
                               "afwezigheden en taakbehoeften blijven ongemoeid.")
                    if preview:
                        st.dataframe(pd.DataFrame(preview).head(12), hide_index=True,
                                     use_container_width=True)
                    if st.button("Kopieer deze dienstbehoefte", key="copy_into_existing_v013",
                                 disabled=not preview):
                        store.copy_month_workspace_demand(
                            engine, src[0], src[1], data["year"], data["month"],
                            st.session_state.workspace_revision, current_user["employee_id"], mode
                        )
                        st.rerun()
                except (ValueError, store.ConflictError) as error:
                    st.error(str(error))
    st.dataframe(pd.DataFrame(data["demand"]), hide_index=True, use_container_width=True, height=300)
    with st.form("demand_form"):
        a,b,c = st.columns(3)
        with a:
            day = st.date_input("Datum", value=month_start)
        with b:
            shift_id = st.selectbox("Dienstnummer", [s["id"] for s in data["shifts"] if s.get("active", True)])
        with c:
            action = st.selectbox("Actie", ["Dienst inplannen", "Dienst verwijderen"])
        st.caption("De vaste bezetting wordt overgenomen uit de dienstencatalogus.")
        if st.form_submit_button("Maandbehoefte aanpassen"):
            if (day.year, day.month) != (data["year"], data["month"]):
                st.error("Kies een datum binnen de huidige planningsmaand.")
            else:
                state = clone()
                state["demand"] = [r for r in state["demand"] if (r["date"], r["shift_id"]) != (day.isoformat(), shift_id)]
                if action == "Dienst inplannen":
                    fixed = next(s["required"] for s in data["shifts"] if s["id"] == shift_id)
                    state["demand"].append({"date": day.isoformat(), "shift_id": shift_id, "required": fixed})
                replace_and_rerun(state)
    st.divider()
    st.markdown("#### Excel-import")
    st.download_button("⬇️ Voorbeeld-Excel downloaden", data=example_excel(data["year"], data["month"], tuple((s["id"], s["required"]) for s in data["shifts"][:2])), file_name="sjabloon_maandbehoefte.xlsx")
    st.caption("Kolommen: **datum**, **dienstnummer**, **aantal**. Het aantal moet overeenkomen met de vaste dienstbezetting. Upload uitsluitend fictieve testgegevens.")
    excel_file = st.file_uploader("Excelbestand met maandbehoefte", type=["xlsx"])
    if st.button("Excel importeren", disabled=excel_file is None):
        try:
            frame = pd.read_excel(excel_file)
            if not {"datum", "dienstnummer", "aantal"}.issubset(frame.columns):
                raise ValueError("Kolommen datum, dienstnummer en aantal zijn verplicht.")
            rows = []
            for _, row in frame.iterrows():
                d = to_iso(row["datum"])
                sid = str(row["dienstnummer"]).strip()
                required = int(row["aantal"])
                if (date.fromisoformat(d).year, date.fromisoformat(d).month) != (data["year"], data["month"]):
                    raise ValueError(f"Datum {d} valt buiten de gekozen maand.")
                if sid not in {s["id"] for s in data["shifts"]}:
                    raise ValueError(f"Onbekend dienstnummer: {sid}")
                fixed = next(s["required"] for s in data["shifts"] if s["id"] == sid)
                if required != fixed:
                    raise ValueError(f"Dienst {sid} heeft vaste bezetting {fixed}, niet {required}. Wijzig de dienstencatalogus.")
                if any(r["date"] == d and r["shift_id"] == sid for r in rows):
                    raise ValueError(f"Dubbele combinatie datum/dienstnummer: {d} / {sid}")
                if required:
                    rows.append({"date": d, "shift_id": sid, "required": required})
            state = clone()
            state["demand"] = rows  # Bewust vervangen; import vormt de hele planningsmaand.
            replace_and_rerun(state)
        except Exception as exc:
            st.error(f"Excel kon niet ingelezen worden: {exc}")

elif screen == "Voorkeuren":
    st.subheader("Beheer van persoonlijke voorkeuren")
    st.caption("Dagelijks een concreet dienstnummer kiezen uit de maandbehoefte. Ook deze wensen zijn **zacht**: bezetting, rust en inzetbaarheid gaan altijd voor.")
    if data["employees"]:
        chosen_pref = st.selectbox("Controleur", [e["id"] for e in data["employees"]],
                                   format_func=lambda i: next(e["name"] for e in data["employees"] if e["id"] == i))
        render_preferences(chosen_pref, "manager")

elif screen == "Uren en activiteiten":
    st.subheader("Testregistratie van afwezigheden en bijzondere opdrachten")
    invalid = invalid_activities(data)
    if invalid:
        st.error(f"Er staan {len(invalid)} afwijkende activiteiten in deze maand. "
                 "Berekening van een nieuwe planning blijft geblokkeerd tot deze activiteiten zijn hersteld. "
                 "Diensturen kun je wel wijzigen.")
        with st.expander("Oude activiteiten controleren (v0.26.1)", expanded=True):
            st.caption("Bekijk eerst de controleur, datum en reden. Controleer of er goedgekeurd verlof "
                       "tussen staat. Verwijderen gebeurt nooit automatisch en wijzigt geen gepubliceerde planning.")
            st.dataframe(pd.DataFrame([{
                "Rij": r["index"] + 1, "Personeelsnr": r["employee_id"],
                "Datum": r["date"], "Type": r["type"], "Uren": r["hours"],
                "Probleem": r["reason"]
            } for r in invalid]), hide_index=True, use_container_width=True)
            st.download_button(
                "⬇️ Back-up van alle activiteiten van deze maand (JSON)",
                data=json.dumps(data.get("hour_credits", []), ensure_ascii=False, indent=2).encode("utf-8"),
                file_name=f"activiteiten_backup_{data['year']}_{data['month']:02d}.json",
                mime="application/json", key="download_invalid_activities_v0261")
            with st.form("clean_invalid_activities_v0261"):
                selected_invalid = st.multiselect(
                    "Afwijkende activiteiten die je wilt verwijderen",
                    [r["index"] for r in invalid],
                    format_func=lambda idx: next(
                        f"Rij {r['index'] + 1}: {r['employee_id']} — {r['date']} ({r['reason']})"
                        for r in invalid if r["index"] == idx))
                confirmed = st.checkbox(
                    "Ik heb de registraties nagekeken en een back-up bewaard. "
                    "Ik begrijp dat verwijderen van activiteiten invloed kan hebben op de planning.")
                clean_submitted = st.form_submit_button(
                    "Geselecteerde afwijkende activiteiten verwijderen")
            if clean_submitted:
                if not confirmed:
                    st.error("Bevestig eerst dat je de gegevens hebt gecontroleerd.")
                else:
                    try:
                        corrected = remove_invalid_activities(clone(), selected_invalid)
                        # Ook de database controleert nog op goedgekeurd verlof.
                        replace_and_rerun(corrected)
                    except ValueError as error:
                        st.error(str(error))
            # Verplaats alleen gewone activiteiten met geldige controleur en een
            # andere, reeds bestaande doelmaand. Nooit automatische verplaatsing.
            if PERSISTENT:
                months_for_move = store.list_month_workspaces(engine)
                revisions_for_move = {(m["year"], m["month"]): m["revision"] for m in months_for_move}
                known_ids_for_move = {e["id"] for e in data["employees"]}
                move_options = []
                for problem in invalid:
                    act = data["hour_credits"][problem["index"]]
                    try:
                        destination = validate_movable_activity(
                            act, known_ids_for_move, data["year"], data["month"])
                    except (ValueError, TypeError):
                        continue
                    if destination in revisions_for_move:
                        move_options.append((problem["index"], destination))
                if move_options:
                    st.markdown("**Activiteit veilig naar de juiste maand verplaatsen (v0.26.3)**")
                    st.caption("Alleen gewone activiteiten. Verlof, ziekte en onbekende controleurs "
                               "kunnen niet via deze knop worden verplaatst. Beide maanden blijven bewaard.")
                    with st.form("move_activity_v0263"):
                        chosen_move = st.selectbox(
                            "Kies een afwijkende activiteit",
                            list(range(len(move_options))),
                            format_func=lambda index: (
                                f"Rij {move_options[index][0] + 1}: "
                                f"{data['hour_credits'][move_options[index][0]]['employee_id']} "
                                f"op {data['hour_credits'][move_options[index][0]]['date']} "
                                f"→ {move_options[index][1][1]:02d}/{move_options[index][1][0]}"))
                        move_confirmed = st.checkbox(
                            "Ik heb de registratie gecontroleerd en de back-up gedownload. "
                            "Ik wil deze naar de vermelde maand verplaatsen.")
                        move_submit = st.form_submit_button("Activiteit naar juiste maand verplaatsen")
                    if move_submit:
                        if not move_confirmed:
                            st.error("Bevestig de verplaatsing eerst.")
                        else:
                            activity_index, move_target = move_options[chosen_move]
                            try:
                                new_source_rev, _ = store.move_activity_to_correct_month(
                                    engine, data["year"], data["month"], activity_index,
                                    st.session_state.workspace_revision,
                                    revisions_for_move[move_target], current_user["employee_id"])
                                fresh, revision = store.load_month_workspace(engine, data["year"], data["month"])
                                st.session_state.workspace_revision = revision
                                st.session_state.project_data = fresh
                                st.session_state.pop("last_plan", None)
                                st.session_state.pop("alternatives_v09", None)
                                st.rerun()
                            except (store.ConflictError, ValueError) as error:
                                st.error(str(error))
                else:
                    st.caption("Geen gewone activiteit die veilig naar een bestaande maand kan worden verplaatst. "
                               "Controleer onbekende controleurs en verlofregistraties afzonderlijk.")
            st.info("Controleer eerst of een afwijkende registratie bij een andere maand hoort. "
                    "Gebruik de verplaatsfunctie waar mogelijk; verwijder pas na een back-up en controle. "
                    "Goedgekeurd verlof vraagt altijd een afzonderlijke procedure.")
    # v0.26.4: afzonderlijke administratie van goedgekeurd TESTverlof
    # voor een controleur die niet meer in de personeelscatalogus bestaat.
    # Dit is NOOIT de gewone verwijder- of intrekkingsroute.
    if PERSISTENT and current_user["role"] == "admin":
        try:
            orphans = store.list_orphaned_approved_leave(
                engine, current_user["employee_id"], data["year"], data["month"])
        except (ValueError, store.ConflictError) as exc:
            orphans = []
            st.error(f"Controle verweesde verlofaanvragen niet beschikbaar: {exc}")
        if orphans:
            with st.expander("Goedgekeurd TESTverlof van verdwenen controleurs herstellen (v0.26.4)"):
                st.warning("Alleen voor achtergebleven FICTIEVE testregistraties. "
                           "Gebruik deze actie nooit om geldig verlof van een echte medewerker te schrappen. "
                           "De oorspronkelijke aanvraag en het auditspoor blijven behouden.")
                st.dataframe(pd.DataFrame([{
                    "Aanvraag": f"#{r['id']}", "Personeelsnr": r["employee_id"],
                    "Nog goedgekeurd": ", ".join(r["remaining_dates"]),
                    "Intrekking in behandeling": "Ja" if r["pending_cancellation"] else "Nee",
                    "Account nog actief": "Ja" if r["account_active"] else "Nee",
                } for r in orphans]), hide_index=True, use_container_width=True)
                st.caption("Bewaar eerst de JSON-back-up hierboven én een databaseback-up. "
                           "Een gepubliceerd rooster wordt niet aangepast. ")
                available_orphans = [r for r in orphans if not r["pending_cancellation"]]
                if available_orphans:
                    with st.form("archive_orphan_leave_v0264"):
                        selected_orphan_id = st.selectbox(
                            "Welke oorspronkelijke verlofaanvraag wil je administratief annuleren?",
                            [r["id"] for r in available_orphans],
                            format_func=lambda i: next(
                                f"#{r['id']} • {r['employee_id']} • {len(r['remaining_dates'])} dag(en)"
                                for r in available_orphans if r["id"] == i))
                        orphan_reason = st.text_area("Reden van administratieve correctie (verplicht)",
                                                     max_chars=300,
                                                     placeholder="Bijvoorbeeld: fictief testprofiel verwijderd; "
                                                                 "resterende goedkeuring administratief afsluiten")
                        orphan_confirm = st.checkbox(
                            "Ik heb gecontroleerd dat dit uitsluitend achtergebleven fictieve "
                            "testgegevens zijn en geen geldig verlof; ik heb back-ups bewaard.")
                        orphan_submit = st.form_submit_button("Fictief verweesd verlof administratief annuleren")
                    if orphan_submit:
                        if not orphan_confirm:
                            st.error("Bevestig eerst de controle van de testregistratie en back-ups.")
                        else:
                            try:
                                store.archive_orphaned_approved_leave(
                                    engine, selected_orphan_id, current_user["employee_id"],
                                    orphan_reason, st.session_state.workspace_revision)
                                fresh, revision = store.load_month_workspace(
                                    engine, data["year"], data["month"])
                                st.session_state.workspace_revision = revision
                                st.session_state.project_data = fresh
                                st.session_state.pop("last_plan", None)
                                st.session_state.pop("alternatives_v09", None)
                                st.rerun()
                            except (ValueError, store.ConflictError) as exc:
                                st.error(str(exc))
                else:
                    st.info("Alle verweesde aanvragen hebben nog een intrekkingsverzoek "
                            "in behandeling. Behandel dat via Verlofaanvragen beheren.")
    st.warning("Uren zijn planningscredits, geen officieel uren-/loon-/overurensaldo. "
               "Een registratie blokkeert de volledige betrokken kalenderdag voor reguliere diensten.")
    if data.get("hour_credits"):
        st.dataframe(pd.DataFrame(data["hour_credits"]), hide_index=True, use_container_width=True)
    with st.form("add_hour_credit"):
        c1, c2 = st.columns(2)
        with c1:
            credit_eid = st.selectbox("Controleur", [e["id"] for e in data["employees"]])
            credit_date = st.date_input("Datum activiteit", date(data["year"], data["month"], 1))
        with c2:
            credit_type = st.selectbox("Type", CREDIT_TYPES)
            credit_hours = st.number_input("Meegetelde uren", 0.0, 16.0, 7.6, step=0.1)
        if st.form_submit_button("Activiteit registreren / bestaande vervangen"):
            if (credit_date.year, credit_date.month) != (data["year"], data["month"]):
                st.error("De activiteit moet in de actieve maand vallen.")
            else:
                state = clone()
                state["hour_credits"] = [row for row in state.get("hour_credits", [])
                                         if (row["employee_id"], row["date"]) != (credit_eid, credit_date.isoformat())]
                state["hour_credits"].append({"employee_id": credit_eid, "date": credit_date.isoformat(),
                                              "type": credit_type, "hours": float(credit_hours)})
                replace_and_rerun(state)
    if data.get("hour_credits"):
        index = st.selectbox("Registratie verwijderen", range(len(data["hour_credits"])),
                             format_func=lambda i: f"{data['hour_credits'][i]['employee_id']} — {data['hour_credits'][i]['date']}")
        if st.button("Geselecteerde activiteit verwijderen"):
            state = clone()
            state["hour_credits"].pop(index)
            replace_and_rerun(state)
    st.divider()
    st.markdown("#### Urenoverzicht voor actieve testmaand")
    current_plan = st.session_state.get("last_plan")
    if PERSISTENT:
        saved_plan = store.load_plan(engine, data["year"], data["month"])
        if saved_plan:
            current_plan = PlanResult(**saved_plan["payload"])
            if saved_plan["revision"] != st.session_state.workspace_revision:
                st.warning("Het beschikbare rooster is gebaseerd op verouderde invoergegevens; bereken opnieuw.")
    if current_plan:
        st.dataframe(pd.DataFrame(hours_overview(data["employees"], current_plan.assignments,
                                 data.get("hour_credits", []),
                                 catalog.settings_with_defaults(data["settings"])["use_opening_balance"])),
                     hide_index=True, use_container_width=True)
    else:
        st.info("Bereken eerst een maandplanning om geplande en geregistreerde uren samen te zien.")

elif screen == "Planningsregels":
    st.subheader("Planningsregels: dienstreeksen en rusttijden")
    st.warning("Alle regels zijn PROEFINSTELLINGEN. De toepassing controleert nog niet of ze voldoen aan de arbeidsafspraken van De Lijn.")
    cfg = catalog.settings_with_defaults(data["settings"])
    with st.form("category_rules"):
        st.markdown("#### Algemene maximumreeksen")
        st.caption("0 = geen maximum voor die categorie. Het maximum opeenvolgende werkdagen blijft afzonderlijk gelden.")
        cols = st.columns(4)
        run_values = {}
        for idx, cat in enumerate(CATEGORIES):
            with cols[idx]:
                run_values[cat] = st.number_input("Max. " + cat, 0, 7,
                                                  int(cfg["max_category_run"].get(cat, 0)),
                                                  key="general_run_" + cat)
        st.markdown("#### Extra rust per dienstovergang")
        st.caption("De hoogste waarde van algemene rust, individuele rust en overgangsrust geldt. 0 = geen extra rust.")
        rest_values = {}
        for before in CATEGORIES:
            cols = st.columns(4)
            for idx, after in enumerate(CATEGORIES):
                code = catalog.transition_code(before, after)
                with cols[idx]:
                    rest_values[code] = st.number_input(code + " (uur)", 0, 48,
                                                        int(cfg["transition_rest_hours"].get(code, 0)),
                                                        key="rest_" + code)
        st.markdown("#### Verboden dienstovergangen")
        st.caption("Geldt alleen voor diensten op twee opeenvolgende kalenderdagen, boven op de rustregels.")
        transitions = [catalog.transition_code(a, b) for a in CATEGORIES for b in CATEGORIES]
        blocked = st.multiselect("Verboden combinaties", transitions, default=cfg["blocked_transitions"])
        weight = st.slider("Belang zachte maandstreefuren", 0, 100, int(cfg["hours_weight"]))
        if st.form_submit_button("Planningsregels opslaan"):
            state = clone()
            state["settings"].update({
                "max_category_run": {k: int(v) for k, v in run_values.items() if v},
                "transition_rest_hours": {k: int(v) for k, v in rest_values.items() if v},
                "blocked_transitions": list(blocked), "hours_weight": int(weight)
            })
            replace_and_rerun(state)
    st.info("Individuele uitzonderingen stel je in bij **Controleurs → Profiel en beperkingen**. Per categorie geldt de strengste maximumreeks.")

elif screen == "Urenbalans":
    st.subheader("🧮 Urenbalans en individuele maandregimes (v0.27.2)")
    st.warning("Uitsluitend indicatieve TESTUREN: geen officiële registratie van overuren, "
               "verlof, loon of arbeidsrechten. Controleer het startsaldo altijd zelf.")
    st.caption("Een maandregeling is onafhankelijk van de gedeelde controleurscatalogus en "
               "van de uurregeling in andere maanden. Alle saldi gebruiken uitsluitend "
               "gepubliceerde planningen, nooit concepten.")
    try:
        current_regimes = apply_month_regimes(data)
        history_rows = (store.published_hour_history_v027(
            engine, current_user["employee_id"], data["year"], data["month"])
            if PERSISTENT else [])
        balances = build_balance_preview(data, history_rows)
        if balances["warnings"]:
            for notice in balances["warnings"]:
                st.info(notice)
        st.dataframe(pd.DataFrame(balances["rows"]), hide_index=True, use_container_width=True)
        if balances["history"]:
            with st.expander("Gepubliceerde maandhistoriek en saldoformule"):
                st.caption("Eindsaldo = startsaldo + planuren + geregistreerde uren − streefuren. "
                           "Zelfstandige taken zijn niet dubbel meegeteld.")
                st.dataframe(pd.DataFrame(balances["history"]), hide_index=True,
                             use_container_width=True)
        else:
            st.caption("Nog geen aaneengesloten gepubliceerde voorgaande maanden beschikbaar.")
        st.divider()
        st.markdown("#### Maandgebonden urenregeling instellen")
        if data["employees"]:
            eid = st.selectbox("Controleur", [e["id"] for e in data["employees"]],
                               format_func=lambda x: next(e["name"] for e in data["employees"] if e["id"] == x),
                               key="v027_regime_employee")
            # v0.27.1: legacy/demo-profielen kunnen target_month_hours missen.
            # Dezelfde niet-destructieve defaults als de rest van de app gebruiken.
            employee = catalog.profile(next(e for e in current_regimes["employees"] if e["id"] == eid))
            global_profile = catalog.profile(next(e for e in data["employees"] if e["id"] == eid))
            with st.form("monthly_regime_v027"):
                max_h = st.number_input("Maximum planuren in deze maand", min_value=1.0,
                                        max_value=250.0, value=float(employee["max_month_hours"]), step=0.5)
                target_h = st.number_input("Streefuren in deze maand (0 = geen saldoformule)",
                                           min_value=0.0, max_value=250.0,
                                           value=float(employee["target_month_hours"]), step=0.5)
                st.caption(f"Gedeelde standaard: max. {global_profile['max_month_hours']} u, "
                           f"streef {global_profile['target_month_hours']} u. "
                           "Dit formulier wijzigt alleen de geselecteerde maand.")
                apply_button = st.form_submit_button("Maandregime bewaren")
            if apply_button:
                if target_h > max_h:
                    st.error("De streefuren mogen niet boven het maandmaximum liggen.")
                else:
                    save_month_regime_and_rerun(eid, {
                        "target_month_hours": float(target_h),
                        "max_month_hours": float(max_h),
                    })
            if eid in data.get("month_hour_regimes_v027", {}):
                if st.button("Persoonlijk maandregime terugzetten naar standaard", key="reset_regime_v027"):
                    save_month_regime_and_rerun(eid, None)
    except (ValueError, store.ConflictError) as error:
        st.error(f"Urenbalans niet beschikbaar: {error}")
    except Exception:
        logging.exception("HOURS_V027: maandrapport mislukt")
        st.error("Urenbalans tijdelijk niet beschikbaar. Bekijk HOURS_V027 in de Streamlit-logboeken.")

elif screen == "Weekend en maandgrenzen":
    st.subheader("Weekend- en maandgrenzen — proefregels")
    st.warning("Dit zijn configureerbare TESTREGELS, geen door De Lijn gevalideerde arbeidstijdregels. "
               "Historische weekenddagen en het startsaldo zijn handmatige testwaarden.")
    cfg = catalog.settings_with_defaults(data["settings"])
    with st.container(border=True):
        st.markdown("#### Algemene harde maxima")
        st.caption("Voor maandcategorieën betekent 0: geen algemeen maximum. Per controleur kan een strenger maximum gelden.")
        global_cats = {}
        cols = st.columns(4)
        for ix, cat in enumerate(CATEGORIES):
            with cols[ix]:
                global_cats[cat] = st.number_input("Maximum " + cat + " / maand", 0, 31,
                    int(cfg["max_month_categories"].get(cat, 0)), key="global_month_" + cat)
        has_weekend_limit = st.checkbox("Algemeen maximum weekenddagen activeren",
                                        value=cfg["max_weekend_days"] is not None)
        max_weekend = st.number_input("Maximaal aantal diensten op zaterdag/zondag (startdatum)", 0, 10,
                                     int(cfg["max_weekend_days"] or 0), disabled=not has_weekend_limit)
        balance_on = st.checkbox("Testsaldo meenemen bij het optimaliseren van streefuren",
                                 value=bool(cfg["use_opening_balance"]))
        st.caption("Als dit is ingeschakeld, vermindert een positief startsaldo de nog gewenste planuren. "
                   "Geen automatische verwerking in officiële loon- of urenregistratie.")
        if st.button("Algemene grenzen bewaren", key="save_global_v06"):
            new_state = clone()
            new_state["settings"].update({
                "max_month_categories": {cat: int(v) for cat, v in global_cats.items() if v},
                "max_weekend_days": int(max_weekend) if has_weekend_limit else None,
                "use_opening_balance": bool(balance_on),
            })
            replace_and_rerun(new_state)

    st.divider()
    st.markdown("#### Individueel weekend- en maandprofiel")
    if data["employees"]:
        selected = st.selectbox("Controleur", [e["id"] for e in data["employees"]],
                                format_func=lambda i: next(e["name"] for e in data["employees"] if e["id"] == i),
                                key="v06_employee")
        person = catalog.profile(next(e for e in data["employees"] if e["id"] == selected))
        weekends = weekend_start_dates(data["year"], data["month"])
        with st.container(border=True):
            c1, c2 = st.columns(2)
            with c1:
                limit_days = st.checkbox("Persoonlijk maximum weekenddagen activeren",
                        value=person["max_weekend_days"] is not None, key="v06_days_active_"+selected)
                weekend_days = st.number_input("Maximum weekenddagen", 0, 10,
                        int(person["max_weekend_days"] or 0), disabled=not limit_days,
                        key="v06_days_"+selected)
                limit_weekends = st.checkbox("Persoonlijk maximum gewerkte weekends activeren",
                        value=person["max_worked_weekends"] is not None, key="v06_weekends_active_"+selected)
                weekends_count = st.number_input("Maximum volledige/deels gewerkte weekends", 0, 6,
                        int(person["max_worked_weekends"] or 0), disabled=not limit_weekends,
                        key="v06_weekends_"+selected)
                protected = st.multiselect("Verplicht vrije weekends (zaterdag + zondag)", weekends,
                         default=[x for x in person["protected_weekends"] if x in weekends],
                         key="v06_protected_"+selected)
            with c2:
                history = st.number_input("Historische weekenddagen (handmatig, test)", 0, 200,
                          int(person["historic_weekend_days"]), key="v06_history_"+selected)
                opening = st.number_input("Startsaldo uren (test)", -80.0, 80.0,
                          float(person["opening_hour_balance"]), step=0.5,
                          key="v06_balance_"+selected)
                st.caption("Startsaldoberekening alleen geactiveerd als de algemene instelling aan staat. "
                           "Geen automatische overdracht vanuit eerdere maand.")
            st.markdown("**Persoonlijke maxima per dienstcategorie (0 = geen eigen maximum)**")
            cols2 = st.columns(4)
            person_max = {}
            for ix, cat in enumerate(CATEGORIES):
                with cols2[ix]:
                    person_max[cat] = st.number_input("Max. " + cat, 0, 31,
                           int(person["max_month_categories"].get(cat, 0)),
                           key="v06_max_"+selected+cat)
            st.markdown("**Gewenste aantallen per categorie (zacht; leeg = geen streefwaarde)**")
            cols3 = st.columns(4)
            person_targets = {}
            for ix, cat in enumerate(CATEGORIES):
                with cols3[ix]:
                    stored = person["target_month_categories"].get(cat)
                    raw = st.text_input("Streef " + cat, value=str(stored) if stored is not None else "",
                            help="Geef een geheel getal tussen 0 en 31, of laat leeg.",
                            key="v06_target_"+selected+cat)
                    person_targets[cat] = raw.strip()
            if st.button("Individuele instellingen bewaren", key="save_individual_v06"):
                try:
                    targets = {}
                    for cat, raw in person_targets.items():
                        if raw:
                            targets[cat] = int(raw)
                            if not 0 <= targets[cat] <= 31:
                                raise ValueError("Streefwaarde moet 0–31 zijn.")
                    new_state = clone()
                    target = next(e for e in new_state["employees"] if e["id"] == selected)
                    target.update({
                        "max_weekend_days": int(weekend_days) if limit_days else None,
                        "max_worked_weekends": int(weekends_count) if limit_weekends else None,
                        "protected_weekends": sorted(set([iso for iso in person["protected_weekends"] if iso not in weekends] + list(protected))),
                        "historic_weekend_days": int(history),
                        "opening_hour_balance": float(opening),
                        "max_month_categories": {cat: int(v) for cat, v in person_max.items() if v},
                        "target_month_categories": targets,
                    })
                    replace_and_rerun(new_state)
                except ValueError:
                    st.error("Streefwaarden moeten gehele getallen zijn van 0 tot 31.")
        st.markdown("#### Weekendrotatie (v0.28)")
        st.caption("Individuele harde regel: maximaal 1–4 **opeenvolgende gewerkte weekends**. "
                   "Zaterdag en zondag van hetzelfde weekend tellen samen als één. "
                   "Een gepubliceerd rooster van de vorige of volgende maand wordt meegenomen "
                   "als dat bestaat. Dit is een globale personeelsregel, voor alle maanden.")
        old_cap = person.get("max_consecutive_worked_weekends")
        cap_options = [None] + list(range(1, MAX_STREAK_SETTING + 1))
        cap = st.selectbox("Maximum opeenvolgende gewerkte weekends",
                           cap_options, index=cap_options.index(old_cap) if old_cap in cap_options else 0,
                           format_func=lambda v: "Geen maximum (uit)" if v is None else str(v),
                           key=f"v028_streak_{selected}_{data['year']}_{data['month']}")
        if st.button("Weekendrotatie bewaren", key="v028_save_streak"):
            try:
                if PERSISTENT:
                    store.save_weekend_streak_v028(
                        engine, int(data["year"]), int(data["month"]),
                        int(st.session_state.workspace_revision),
                        current_user["employee_id"], selected, cap)
                    fresh, rev = store.load_month_workspace(engine, int(data["year"]), int(data["month"]))
                    st.session_state.project_data, st.session_state.workspace_revision = fresh, rev
                else:
                    state = clone()
                    next(e for e in state["employees"] if e["id"] == selected)[
                        "max_consecutive_worked_weekends"] = cap
                    st.session_state.project_data = state
                st.session_state.pop("last_plan", None)
                st.session_state.pop("alternatives_v09", None)
                st.rerun()
            except (ValueError, store.ConflictError) as exc:
                st.error(str(exc))
    st.caption("Weekendgrenzen en historische dagtellingen tellen diensten op hun startdatum. "
               "Beschermde weekends blokkeren ook overlappende nachtdiensten.")

elif screen == "Roostercontrole":
    st.subheader("🗓️ Roostercontrole per controleur")
    st.caption("Alleen-lezen week- en maandoverzicht om de resultaten van de planning en "
               "handmatige wijzigingen na te kijken. Roosterbewerkingen gebeuren bij **Planning**.")
    version_options = ["Laatste bewaarde planning", "Laatste gepubliceerde planning"] if PERSISTENT else ["Laatste berekening (demo)"]
    version_choice = st.radio("Welke planning bekijken?", version_options, horizontal=True,
                              key="roster_version_v024")
    record = None
    plan_data = None
    if PERSISTENT:
        try:
            record = store.load_plan(engine, data["year"], data["month"],
                                     published_only=version_choice == "Laatste gepubliceerde planning")
        except Exception:
            logging.exception("ROSTER_V024_LOAD: rooster kon niet worden opgehaald")
            st.error("De gekozen planversie kon niet worden opgehaald. Bekijk ROSTER_V024_LOAD in de logboeken.")
        if record:
            plan_data = record.get("payload")
            st.caption(f"Planversie #{record['id']} · "
                       f"{'Gepubliceerd' if record['published'] else 'Concept'}")
            if record["revision"] != st.session_state.workspace_revision:
                st.warning("De invoergegevens zijn sinds deze planversie veranderd. "
                           "Het rooster is mogelijk niet meer actueel.")
    else:
        old_plan = st.session_state.get("last_plan")
        if old_plan is not None:
            plan_data = asdict(old_plan)
    if plan_data is None:
        st.info("Er is voor deze selectie nog geen bewaarde planning. Bereken eerst een planning "
                "of kies de gepubliceerde versie wanneer die beschikbaar is.")
    else:
        try:
            teams = sorted({str(p.get("team", "")).strip() for p in data["employees"]
                            if str(p.get("team", "")).strip()})
            col_team, col_days, col_times = st.columns([2, 3, 1])
            with col_team:
                chosen_team = st.selectbox("Team", ["Alle teams"] + teams,
                                           key="roster_team_v024")
            with col_days:
                weeks = week_windows(data["year"], data["month"])
                periods = [("month", "Volledige maand")] + [(w["key"], w["label"]) for w in weeks]
                first_needed_week = next((i for i, w in enumerate(weeks, 1)
                                         if any(r.get("date") in w["days"] for r in data.get("demand", []))), 0)
                period_selected = st.selectbox("Periode", periods,
                                               format_func=lambda x: x[1],
                                               index=first_needed_week,
                                               key="roster_period_v024")
            with col_times:
                show_hours = st.checkbox("Uren tonen", value=False,
                                         key="roster_hours_v024")
            team_people = [p for p in data["employees"] if
                           (chosen_team == "Alle teams" or str(p.get("team", "")).strip() == chosen_team)]
            active_only = st.checkbox("Alleen actieve controleurs", value=True,
                                      key="roster_active_v024")
            possible = [p for p in team_people if p.get("active", True) or not active_only]
            names = {str(p["id"]): str(p.get("name", p["id"])) for p in possible}
            chosen_ids = st.multiselect("Controleurs (leeg = iedereen binnen filter)",
                                        list(names), format_func=lambda eid: f"{names[eid]} ({eid})",
                                        key="roster_people_v024")
            chosen = chosen_ids or list(names)
            selected_days = (month_days(data["year"], data["month"])
                             if period_selected[0] == "month" else
                             next(w["days"] for w in weeks if w["key"] == period_selected[0]))
            matrix = roster_grid(data, plan_data, selected_ids=chosen,
                                 days=selected_days, show_times=show_hours)
            coverage = staffing_grid(data, plan_data, days=selected_days)
            a, b, c, d = st.columns(4)
            a.metric("Controleurs", matrix["people"])
            b.metric("Reguliere toewijzingen", matrix["regular_assignments"])
            c.metric("Open dienstplaatsen", sum(r["Open"] for r in coverage))
            d.metric("Extra toewijzingen", sum(r["Extra"] for r in coverage))
            st.caption("— = geen dienst toegewezen. Zelfstandige taken en activiteiten staan "
                       "als 'Taak' vermeld; ze tellen niet mee bij de reguliere dienstplaatsen. "
                       "Bezettingscijfers onderaan gelden voor alle controleurs, ook als je het rooster filtert.")
            st.dataframe(pd.DataFrame(matrix["rows"],
                                      columns=["Controleur", "Personeelsnr"] + matrix["columns"]),
                         hide_index=True, use_container_width=True, height=430)
            with st.expander("📊 Bezetting per dag", expanded=False):
                st.dataframe(pd.DataFrame(coverage), hide_index=True, use_container_width=True)
            st.download_button("⬇️ Download roostercontrole (Excel)",
                               workbook_bytes(matrix, coverage),
                               file_name=f"roostercontrole-{data['year']}-{data['month']:02d}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="roster_export_v024")
            st.info("Dit is een controleweergave, geen formele validatie van arbeidsregels. "
                    "Voor wijzigingen gebruik je **Planning → Handmatige roosterbewerking**.")
        except (ValueError, KeyError, TypeError) as error:
            st.error(f"Roosteroverzicht kon niet worden opgebouwd: {error}")
        except Exception:
            logging.exception("ROSTER_V024_RENDER: onverwachte fout")
            st.error("Roosteroverzicht niet beschikbaar. Bekijk ROSTER_V024_RENDER in de logboeken.")

elif screen == "Planning":
    st.subheader("Automatisch plannen met Google OR-Tools")
    st.caption("De instellingen hieronder zijn testwaarden, GEEN gevalideerde wettelijke of sectorale minima. Meerdere alternatieven vergelijken kan via het onderdeel **Optimalisatie vergelijken**.")
    with st.form("planner_settings"):
        col1,col2,col3 = st.columns(3)
        with col1:
            rest = st.number_input("Minimale rust tussen twee diensten (uur)", 0, 48,
                                   int(data["settings"]["min_rest_hours"]))
            max_consecutive = st.number_input("Max. opeenvolgende werkdagen", 1, 7,
                                              int(data["settings"]["max_consecutive"]))
        with col2:
            time_limit = st.number_input(
                "Maximale rekentijd (seconden)",
                min_value=1,
                max_value=3600,
                value=int(data["settings"]["time_limit_seconds"]),
                step=30,
                help="Maximum 3.600 seconden (60 minuten). Bewaar de instelling vóór je berekent. "
                     "Laat de browser open: Streamlit Community Cloud biedt geen gegarandeerde "
                     "achtergrondverwerking bij het sluiten van de sessie.",
            )
        with col3:
            pref_weight = st.slider("Belang voorkeuren", 0, 100, int(data["settings"]["preference_weight"]))
            fair_weight = st.slider("Belang eerlijke verdeling", 0, 100, int(data["settings"]["fairness_weight"]))
        if st.form_submit_button("Instellingen opslaan"):
            state = clone()
            state["settings"].update({"min_rest_hours": rest, "max_consecutive": max_consecutive,
                                       "time_limit_seconds": time_limit, "preference_weight": pref_weight,
                                       "fairness_weight": fair_weight})
            replace_and_rerun(state)
    if int(data["settings"]["time_limit_seconds"]) >= 600:
        st.caption("Bij lange berekeningen: laat dit browsertabblad open. "
                   "Een gesloten sessie of herstart van Streamlit kan de berekening onderbreken.")
    errors = validate_dataset(apply_month_regimes(data)) + validate_month_regimes(data)
    for error in errors:
        st.error(error)
    auto_history = st.checkbox("Gepubliceerde weekendhistoriek automatisch meewegen", value=PERSISTENT,
                               disabled=not PERSISTENT,
                               help="Vervangt tijdens de berekening de handmatig opgegeven weekendhistoriek. "
                                    "Alleen gepubliceerde eerdere maanden worden gelezen.")
    months_back = st.slider("Historische periode (maanden)", 1, 12, 3, disabled=not auto_history)
    past_plans = (store.published_plans_before(engine, data["year"], data["month"], months_back)
                  if PERSISTENT and auto_history else [])
    historic = aggregate_history(past_plans, [e["id"] for e in data["employees"]]) if auto_history else {}
    if auto_history:
        st.caption(f"Gevonden: {len(past_plans)} gepubliceerde voorgaande maandplanningen. "
                   "Zonder vorige gepubliceerde plannen telt de historische weekendscore als 0.")
        if past_plans:
            st.dataframe(pd.DataFrame([{"Personeelsnr": e["id"], "Controleur": e["name"],
                                        "Historische weekenddagen": historic[e["id"]]["weekend_days"],
                                        "Gewerkte weekends": historic[e["id"]]["worked_weekends"]}
                                       for e in data["employees"]]), hide_index=True, use_container_width=True)
    # v0.27 — alleen gepubliceerde maanden vormen een saldo-overdracht.
    hour_balance_preview = None
    if PERSISTENT:
        try:
            hour_history = store.published_hour_history_v027(
                engine, current_user["employee_id"], data["year"], data["month"])
            hour_balance_preview = build_balance_preview(data, hour_history)
        except Exception:
            logging.exception("HOURS_V027_PLAN: ophalen historische saldi mislukt")
            st.warning("Automatische testurenbalans tijdelijk niet beschikbaar.")
    auto_balance_v027 = st.checkbox(
        "Automatisch indicatief startsaldo uit gepubliceerde vorige maanden meenemen (v0.27)",
        value=False, disabled=not bool(hour_balance_preview and hour_balance_preview["available"]),
        key="plan_auto_balance_v027",
        help="Alleen voor het ZACHTE urendoel. Geen wettelijke of verplichte saldoverrekening.")
    if hour_balance_preview:
        for msg in hour_balance_preview["warnings"]:
            st.caption(msg)
        if auto_balance_v027:
            st.dataframe(pd.DataFrame(hour_balance_preview["rows"]),
                         hide_index=True, use_container_width=True)
            st.warning("Deze berekening gebruikt historische startsaldi vanaf handmatige testbasis. "
                       "Controleer ze voor je een planning publiceert.")

    boundary_context = (published_boundary_context(engine, data["year"], data["month"])
                        if PERSISTENT else {"sources": {"previous": None, "next": None}, "assignments": []})
    st.caption("Maandgrenscontrole: " + ", ".join(
        f"{label}: {'gepubliceerde versie #' + str(boundary_context['sources'][side]) if boundary_context['sources'][side] else 'nog geen gepubliceerd rooster'}"
        for side, label in (("previous", "vorige maand"), ("next", "volgende maand"))))
    if any(v is None for v in boundary_context["sources"].values()):
        st.info("Zonder gepubliceerde aangrenzende maand kunnen de rusttijden en dienstreeksen "
                "aan die kant nog niet definitief worden gecontroleerd. Herbereken later indien nodig.")
    # v0.21: indicatieve controle van individuele dienstgeschiktheid.
    # Dit is GEEN solver en mag geen harde planningsregels automatisch wijzigen.
    diagnosis = None
    if not errors:
        try:
            diagnosis = analyze_month(data, boundary_context["assignments"])
        except Exception:
            logging.exception("DIAG_V021: voorafgaande analyse mislukt")
            st.warning("De indicatieve haalbaarheidscontrole is tijdelijk niet beschikbaar. De bestaande berekening blijft beschikbaar.")
    with st.expander("🔎 Haalbaarheid vóór berekening (indicatief)", expanded=False):
        st.caption("Deze controle bekijkt individuele blokkeringen per dienst en de hoeveelheid unieke "
                   "kandidaten per kalenderdag. De volledige combinaties van rust, diensten, "
                   "uren, werkreeksen en taken worden uitsluitend door OR-Tools berekend. "
                   "Een dag zonder direct tekort is dus niet automatisch volledig planbaar.")
        if diagnosis is not None:
            overview = diagnosis["summary"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Actieve controleurs", overview["active_staff"])
            c2.metric("Benodigde dienstplaatsen", overview["service_places"])
            c3.metric("Direct tekort (minimum)", overview["direct_shortfall"])
            c4.metric("Dagen met direct capaciteitstekort", overview["days_with_shortfall"])
            if overview["direct_shortfall"] or overview["days_with_shortfall"]:
                st.warning("Er zijn directe capaciteitsknelpunten gevonden. Controleer eerst de "
                           "dienstbehoefte, beschikbaarheid en geldende harde beperkingen. "
                           "Dit is geen advies om rust- of arbeidsregels te versoepelen.")
            if diagnosis["slots"]:
                st.markdown("**Per dienstnummer**")
                st.dataframe(pd.DataFrame(diagnosis["slots"]), hide_index=True, use_container_width=True)
                st.markdown("**Capaciteit per kalenderdag**")
                st.dataframe(pd.DataFrame(diagnosis["days"]), hide_index=True, use_container_width=True)
                st.markdown("**Vaak voorkomende individuele blokkeringen**")
                st.dataframe(pd.DataFrame(diagnosis["blockers"]), hide_index=True, use_container_width=True)
            else:
                st.info("Er zijn nog geen dienstplaatsen ingevoerd in de geselecteerde maand.")
        else:
            st.info("De haalbaarheidscontrole is niet beschikbaar zolang de invoer fouten bevat.")
    if st.button("🚀 Bereken maandplanning", type="primary", disabled=bool(errors)):
        try:
            with st.spinner("OR-Tools zoekt een zo goed mogelijke planning…"):
                calculation_data = apply_month_regimes(
                    apply_published_history(data, historic) if auto_history else data)
                if auto_balance_v027:
                    calculation_data = apply_balance_to_solver(
                        calculation_data, hour_balance_preview["eligible"])
                calculation_data = with_boundary_context(calculation_data, boundary_context)
                candidate = solve_month(calculation_data)
                if candidate.status in ("OPTIMAL", "FEASIBLE"):
                    check = verify_plan(apply_month_regimes(data), asdict(candidate), boundary_context["assignments"])
                    if not check["passed"]:
                        raise ValueError("Onafhankelijke roostercontrole v0.25 afgekeurd: "
                                         + "; ".join(check["errors"][:5])
                                         + ". De onveilige berekening wordt niet opgeslagen.")
                    candidate.summary["validation_v025"] = check
                st.session_state.last_plan = candidate
                st.session_state.last_plan.summary.update({"boundary_sources": boundary_context["sources"],
                                                           "history_months": len(past_plans),
                                                           "history_lookback": months_back if auto_history else 0})
                if auto_balance_v027:
                    st.session_state.last_plan.summary["hour_sources_v027"] = hour_balance_preview["sources"]
                if PERSISTENT and st.session_state.last_plan.status in ("OPTIMAL", "FEASIBLE"):
                    st.session_state.last_plan_id = store.save_plan(
                        engine, data, st.session_state.workspace_revision,
                        asdict(st.session_state.last_plan), current_user["employee_id"]
                    )
        except (ValueError, store.ConflictError) as exc:
            st.error(f"De berekening kon niet worden uitgevoerd: {exc}")
        except Exception:
            st.error("De berekening of opslag is mislukt. Controleer de applicatielogs in je testomgeving.")
    plan_record = store.load_plan(engine, data["year"], data["month"]) if PERSISTENT else None
    if plan_record:
        plan = PlanResult(**plan_record["payload"])
        st.session_state.last_plan = plan
    if "last_plan" in st.session_state:
        plan = st.session_state.last_plan
        if plan_record and plan_record["revision"] != st.session_state.workspace_revision:
            st.warning("Deze conceptplanning is berekend met een oudere versie van de invoergegevens.")
        if plan_record and ((plan.summary or {}).get("boundary_sources") != boundary_context["sources"]):
            st.warning("De aangrenzende gepubliceerde maanden zijn gewijzigd of deze planning "
                       "is nog zonder maandgrenscontrole berekend. Bereken opnieuw vóór publicatie.")
        st.markdown(f"#### Resultaat: {plan.status}")
        # Onafhankelijke controle op ALLE geldige resultaten, ook oudere concepten.
        # Dit is een extra veiligheidsbarrière naast de CP-SAT-planningsregels.
        audit = None
        if plan.status in ("OPTIMAL", "FEASIBLE"):
            try:
                audit = verify_plan(data, asdict(plan), boundary_context["assignments"])
                with st.expander("🛡️ Onafhankelijke roostercontrole (v0.25)", expanded=not audit["passed"]):
                    if audit["passed"]:
                        st.success(f"Geen overtredingen aangetroffen in {audit['assignments_checked']} "
                                   "toewijzingen voor de gecontroleerde basisregels.")
                    else:
                        st.error(f"{len(audit['errors'])} overtreding(en) gevonden: dit rooster "
                                 "mag niet gepubliceerd worden.")
                        for text in audit["errors"][:30]:
                            st.write("• " + text)
                    st.caption("Dit is een softwarecontrole van de ingestelde proefregels, "
                               "geen wettelijke of CAO-validatie. Een ontbrekende aangrenzende "
                               "gepubliceerde maand kan niet mee gecontroleerd worden.")
            except (ValueError, KeyError, TypeError) as error:
                audit = {"passed": False, "errors": [str(error)]}
                st.error("De onafhankelijke roostercontrole is mislukt; publicatie is geblokkeerd. "
                         + str(error))
        if plan_record:
            st.caption(f"Versie #{plan_record['id']} • {'Gepubliceerd' if plan_record['published'] else 'Concept'} • Opgesteld door {plan_record['author']}")
            if not plan_record["published"] and plan_record["revision"] == st.session_state.workspace_revision:
                try:
                    preview = store.publication_preview(engine, plan_record["id"], current_user["employee_id"])
                    with st.expander("🔎 Controle vóór publicatie", expanded=True):
                        if preview["last_published_id"] is None:
                            st.info("Dit wordt de eerste publicatie van deze maand. Actieve controleurs krijgen een melding.")
                        else:
                            st.write(f"Vorige publicatie: #{preview['last_published_id']} · "
                                     f"Roosters van {preview['affected_controllers']} controleur(s) gewijzigd.")
                        open_count = preview.get("open_positions")
                        if open_count is not None and open_count > 0:
                            st.warning(f"Let op: {open_count} dienstplaats(en) zijn niet ingevuld. "
                                       "Een gedeeltelijke planning is niet automatisch operationeel geschikt.")
                        st.caption("De publicatie wordt niet automatisch verzonden naar e-mail; "
                                   "alleen meldingen in de webapp.")
                        confirmed = st.checkbox("Ik heb de maandplanning gecontroleerd en wil deze versie publiceren.",
                                                key=f"publish_confirm_v018_{plan_record['id']}")
                        if st.button("✅ Publiceer deze testplanning", disabled=not confirmed or not (audit and audit["passed"]),
                                     key=f"publish_v018_{plan_record['id']}"):
                            try:
                                store.publish_plan(engine, plan_record["id"], st.session_state.workspace_revision,
                                                   current_user["employee_id"])
                                st.success("Testplanning gepubliceerd. Betrokken controleurs ontvangen een melding.")
                                st.rerun()
                            except (ValueError, store.ConflictError) as error:
                                st.error(str(error))
                except ValueError as error:
                    st.error(f"Publicatievoorbeeld niet beschikbaar: {error}")
        # v0.23: meerdere handmatige wijzigingen samen bewaren in de SESSIE,
        # pas na solvervalidatie atomair als nieuwe conceptversie opslaan.
        if plan_record and PERSISTENT:
            with st.expander("✏️ Handmatige roosterbewerking (v0.23)", expanded=True):
                st.caption("Voeg meerdere wijzigingen toe aan een tijdelijke bewerkingslijst. "
                           "Niets wordt opgeslagen of gepubliceerd vóór de controle met de planner. "
                           "Een verwijderde toewijzing kan door een andere controleur worden ingevuld.")
                if plan_record["published"]:
                    st.info("Je vertrekt van een gepubliceerd rooster. Wijzigingen maken uitsluitend "
                            "een nieuw concept; de publicatie blijft ongewijzigd.")
                manual_current = plan_record["revision"] == st.session_state.workspace_revision
                manual_boundary_ok = (plan.summary or {}).get("boundary_sources") == boundary_context["sources"]
                if not manual_current or not manual_boundary_ok:
                    st.warning("De invoer of een aangrenzende gepubliceerde maand is gewijzigd. "
                               "Bereken eerst een nieuwe planning voordat je handmatig bewerkt.")
                else:
                    original_rows = regular_assignments(plan.assignments)
                    original_keys = sorted({assignment_key(r) for r in original_rows})
                    demand_slots = sorted({(r["date"], r["shift_id"]) for r in data["demand"]
                                           if int(r["required"]) > 0})
                    active_people = {e["id"]: e["name"] for e in data["employees"] if e.get("active", True)}
                    source_names = {assignment_key(r): r.get("Controleur", r["Personeelsnr"])
                                    for r in plan.assignments
                                    if r.get("Soort") != "Zelfstandige taak"
                                    and not str(r.get("Dienstnummer", "")).startswith("TAAK:")}
                    queue_key = f"manual_v023_edits_{data['year']}_{data['month']}_{plan_record['id']}"
                    edits = st.session_state.setdefault(queue_key, [])
                    modes = {
                        "Dienst toevoegen": "add",
                        "Dienst vervangen": "replace",
                        "Dienst verwijderen": "remove",
                        "Bestaande dienst behouden": "keep",
                    }
                    mode_label = st.radio("Welke bewerking wil je klaarzetten?", list(modes),
                                          horizontal=True, key=f"manual_v023_mode_{plan_record['id']}")
                    mode = modes[mode_label]
                    with st.form(f"manual_v023_add_form_{plan_record['id']}"):
                        selected_old = None
                        selected_slot = None
                        new_employee = None
                        if mode != "add":
                            selected_old = st.selectbox(
                                "Bestaande toewijzing", original_keys,
                                format_func=lambda k: f"{k[0]} · {k[1]} · {source_names.get(k, k[2])} ({k[2]})",
                                disabled=not original_keys)
                        else:
                            selected_slot = st.selectbox(
                                "Datum en dienstnummer", demand_slots,
                                format_func=lambda x: f"{x[0]} · {x[1]}", disabled=not demand_slots)
                        if mode in ("add", "replace"):
                            new_employee = st.selectbox(
                                "Controleur toewijzen", list(active_people),
                                format_func=lambda eid: f"{active_people[eid]} ({eid})",
                                disabled=not active_people)
                        queue_add = st.form_submit_button(
                            "➕ Zet bewerking op de lijst",
                            disabled=(len(edits) >= MAX_EDITS or
                                      (mode != "add" and not original_keys) or
                                      (mode == "add" and not demand_slots) or
                                      (mode in ("add", "replace") and not active_people)))
                    if queue_add:
                        try:
                            source = (dict(zip(("Datum", "Dienstnummer", "Personeelsnr"), selected_old))
                                      if selected_old is not None else None)
                            target = None
                            if mode in ("add", "replace"):
                                slot = selected_slot if mode == "add" else selected_old[:2]
                                target = {"Datum": slot[0], "Dienstnummer": slot[1],
                                          "Personeelsnr": new_employee}
                            if mode == "replace" and source["Personeelsnr"] == new_employee:
                                raise ValueError("Kies een andere controleur, of gebruik 'Behouden'.")
                            edits.append({"kind": mode, "source": source, "target": target})
                            st.rerun()
                        except ValueError as error:
                            st.error(str(error))
                    if edits:
                        st.markdown("**Klaargezette wijzigingen**")
                        st.dataframe(pd.DataFrame([
                            {"Nr.": i + 1, "Bewerking": edit_description(edit, active_people)}
                            for i, edit in enumerate(edits)]), hide_index=True, use_container_width=True)
                        undo_col, clear_col = st.columns(2)
                        with undo_col:
                            choice = st.selectbox("Bewerking terugdraaien", range(len(edits)),
                                                  format_func=lambda i: f"{i+1}. {edit_description(edits[i], active_people)}",
                                                  key=f"manual_v023_undo_{plan_record['id']}")
                            if st.button("↩️ Verwijder gekozen bewerking", key=f"manual_v023_remove_{plan_record['id']}"):
                                edits.pop(choice)
                                st.rerun()
                        with clear_col:
                            if st.button("🗑️ Wis volledige bewerkingslijst", key=f"manual_v023_clear_{plan_record['id']}"):
                                edits.clear()
                                st.rerun()
                        preserve = st.checkbox(
                            "Behoud alle andere bestaande reguliere toewijzingen (aanbevolen)",
                            value=True, key=f"manual_v023_preserve_{plan_record['id']}")
                        st.caption("Bij uitvinken mag de solver ook de niet-bewerkte diensten "
                                   "herschikken om een geldige planning te vinden. "
                                   "Bij verwijderen wordt alleen de oude persoon-dienstcombinatie verboden; "
                                   "de dienstplaats zelf blijft beschikbaar.")
                        compiled = None
                        try:
                            compiled = compile_edits(data, plan.assignments, edits, preserve)
                            st.success(f"Bewerkingslijst geldig: {compiled['edit_count']} wijziging(en), "
                                       f"{len(compiled['locked'])} vaste en {len(compiled['excluded'])} "
                                       "verboden toewijzing(en). De volledige arbeidsregels worden "
                                       "nog door de solver gecontroleerd.")
                        except ValueError as error:
                            st.warning(f"Bewerkingslijst nog niet uitvoerbaar: {error}")
                        ack = st.checkbox("Ik begrijp dat dit uitsluitend een nieuw concept maakt.",
                                          key=f"manual_v023_ack_{plan_record['id']}")
                        if st.button("🔍 Controleer wijzigingen en maak nieuw concept",
                                     type="primary", key=f"manual_v023_apply_{plan_record['id']}",
                                     disabled=not (compiled is not None and ack and not errors)):
                            try:
                                with st.spinner("Alle vaste en verboden toewijzingen en arbeidsregels controleren…"):
                                    calc_data = apply_published_history(data, historic) if auto_history else data
                                    calc_data = with_boundary_context(calc_data, boundary_context)
                                    new_plan = solve_month(
                                        calc_data,
                                        locked_assignments=compiled["locked"],
                                        excluded_assignments=compiled["excluded"])
                                    if new_plan.status not in ("OPTIMAL", "FEASIBLE"):
                                        raise ValueError("Geen geldige planning met deze wijzigingen. "
                                                         "De oorspronkelijke versie blijft bestaan.")
                                    changes = reoptimization_diff(plan.assignments, new_plan.assignments,
                                                                  compiled["locked"])
                                    if not changes["alle_vaste_behouden"]:
                                        raise ValueError("Niet alle vastgezette diensten staan in het nieuwe rooster.")
                                    actual_keys = {assignment_key(r) for r in regular_assignments(new_plan.assignments)}
                                    if any(assignment_key(r) in actual_keys for r in compiled["excluded"]):
                                        raise ValueError("Een verwijderde dienst is toch teruggekeerd.")
                                    check = verify_plan(data, asdict(new_plan), boundary_context["assignments"])
                                    if not check["passed"]:
                                        raise ValueError("De onafhankelijke roostercontrole is mislukt: "
                                                         + "; ".join(check["errors"][:5]))
                                    new_plan.summary["validation_v025"] = check
                                    new_plan.summary.update({
                                        "boundary_sources": boundary_context["sources"],
                                        "history_months": len(past_plans),
                                        "history_lookback": months_back if auto_history else 0,
                                        "locked_assignments": compiled["locked"],
                                        "excluded_assignments": compiled["excluded"],
                                        "manual_edits_v023": list(edits),
                                        "manual_edit_source": plan_record["id"],
                                        "manual_edit_count": compiled["edit_count"],
                                        "reoptimization_diff": changes,
                                    })
                                    store.save_plan(engine, data, st.session_state.workspace_revision,
                                                    asdict(new_plan), current_user["employee_id"],
                                                    expected_latest_plan_id=plan_record["id"])
                                edits.clear()
                                st.session_state.last_plan = new_plan
                                st.rerun()
                            except (ValueError, store.ConflictError) as error:
                                st.error(f"Handmatige roosterbewerking niet opgeslagen: {error}")
                            except Exception:
                                logging.exception("MANUAL_V023: handmatige roosterbewerking mislukt")
                                st.error("De roosterbewerking is mislukt. Je bestaande planning bleef behouden. "
                                         "Controleer de Streamlit-logboeken op MANUAL_V023.")
                    else:
                        st.info("Kies hierboven een bewerking en zet die op de lijst. Je kunt er "
                                "meerdere toevoegen voordat je de planner laat controleren.")

        # De oude v0.22-bediening is vervangen door de v0.23-editor hierboven.
        # Historische heroptimalisaties blijven zichtbaar in het versieoverzicht.
        details = (plan.summary or {}).get("reoptimization_diff")
        if details:
            source_plan = (plan.summary or {}).get("manual_edit_source") or (plan.summary or {}).get("reoptimized_from")
            st.caption(f"Bewerkt vanaf plan #{source_plan or '?'} · "
                       f"{details['vastgezet']} vast · {details['behouden']} behouden · "
                       f"{details['nieuw']} toegevoegd · {details['weggevallen']} weggevallen")
        a,b,c = st.columns(3)
        a.metric("Benodigde plaatsen", plan.summary["required"])
        b.metric("Toegewezen plaatsen", plan.summary["assigned"])
        c.metric("Openstaande plaatsen", plan.summary["open"] if plan.summary["open"] is not None else "Onbekend")
        if plan.summary.get("extra_regular_staffing"):
            st.caption(f"Extra medewerkers op diensten vanwege tijdelijke vrijstellingen: "
                       f"{plan.summary['extra_regular_staffing']} toewijzingen.")
        if plan.summary.get("task_required"):
            st.caption(f"Bijzondere taken: {plan.summary['task_assigned']} ingevuld, "
                       f"{plan.summary['task_open']} open van {plan.summary['task_required']} plaatsen.")
        if plan.summary.get("history_lookback"):
            st.caption(f"Weekendhistoriek: {plan.summary.get('history_months', 0)} eerder gepubliceerde maanden verwerkt.")
        if plan.summary.get("seconds") is not None:
            st.caption(f"Rekentijd: {plan.summary['seconds']} seconden | Solver: {plan.summary['solver']}")
        if plan.assignments or plan.open_positions or plan.task_assignments or plan.open_tasks:
            t1,t2,t3 = st.tabs(["Diensten en zelfstandige taken", "Openstaande plaatsen", "Urenoverzicht (test)"])
            with t1:
                assignments = pd.DataFrame(plan.assignments)
                st.dataframe(assignments, use_container_width=True, hide_index=True, height=440)
            with t2:
                st.dataframe(pd.DataFrame(plan.open_positions), use_container_width=True, hide_index=True)
                if plan.open_positions:
                    st.info("De onderstaande oorzaken zijn indicaties, geen solververklaring. "
                            "Ook dienstcombinaties, werkreeksen, urenlimieten en taken kunnen "
                            "ervoor zorgen dat een plaats openblijft.")
                    if diagnosis is not None:
                        if plan_record and plan_record["revision"] != st.session_state.workspace_revision:
                            st.warning("De diagnose gebruikt de huidige invoer, maar dit concept is ouder. "
                                       "Herbereken de planning voor een actuele vergelijking.")
                        st.dataframe(pd.DataFrame(explain_open_positions(diagnosis, plan.open_positions)),
                                     use_container_width=True, hide_index=True)
            with t3:
                st.dataframe(pd.DataFrame(hours_overview(data["employees"], plan.assignments,
                                       data.get("hour_credits", []),
                                       catalog.settings_with_defaults(data["settings"])["use_opening_balance"])),
                             hide_index=True, use_container_width=True)
                st.caption("Proefberekening van urensaldi; geen officiële urenverrekening.")
            st.markdown("#### Dienstverdeling en weekendwerk (test)")
            st.dataframe(pd.DataFrame(service_overview(data["employees"], plan.assignments)),
                         hide_index=True, use_container_width=True)
            if plan.task_assignments or plan.open_tasks:
                ta, tb = st.tabs(["Toegewezen taken", "Open taakplaatsen"])
                with ta:
                    st.dataframe(pd.DataFrame(plan.task_assignments), hide_index=True, use_container_width=True)
                with tb:
                    st.dataframe(pd.DataFrame(plan.open_tasks), hide_index=True, use_container_width=True)
            st.download_button("⬇️ Planning downloaden als Excel", data=plan_excel(plan, data, diagnosis),
                               file_name=f"controleursplanning_{data['year']}_{data['month']:02d}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        elif plan.summary["open"] is None:
            st.error("Er is binnen de rekentijd geen bruikbare oplossing gevonden. Probeer de rekentijd te verlengen.")


elif screen == "Rapportage en eerlijkheid":
    st.subheader("📊 Rapportage en roosterverdeling")
    st.caption("Alleen-lezen rapport over de laatst gepubliceerde planning van de actieve maand. "
               "Concepten tellen niet mee. Een verschil in cijfers is geen oordeel over medewerkers.")
    if not PERSISTENT:
        st.info("Rapportage is beschikbaar zodra je PostgreSQL gebruikt en een testplanning publiceert.")
    else:
        # Haal de gegevens in afzonderlijke stappen op. Een mislukte grafiek of
        # Excel-export mag niet het volledige rapport onzichtbaar maken.
        try:
            published = store.report_published_window(
                engine, current_user["employee_id"], int(data["year"]), int(data["month"]), months_back=1)
        except (ValueError, store.ConflictError) as error:
            st.error(str(error))
            published = None
        except Exception:
            logging.exception("REPORT_V0191_FETCH: gepubliceerde maand niet opgehaald")
            st.error("De gepubliceerde maand kon niet worden opgehaald. Bekijk REPORT_V0191_FETCH in de logboeken.")
            published = None

        if published == []:
            st.info("Voor deze maand is nog geen planning gepubliceerd. Publiceer eerst een testplanning.")
        elif published:
            selected_plan = published[-1]
            lookback = st.selectbox("Vergelijkingsperiode (inclusief geselecteerde maand)",
                                    [1, 2, 3, 6, 12], index=2,
                                    format_func=lambda v: f"{v} maand(en)",
                                    key="report_window_v019")
            try:
                history_versions = store.report_published_window(
                    engine, current_user["employee_id"], int(data["year"]), int(data["month"]),
                    months_back=int(lookback))
                report_data = dict(data, workspace_revision=st.session_state.get("workspace_revision"))
                report = build_report(report_data, selected_plan, history_versions)
            except (ValueError, store.ConflictError) as error:
                st.error(str(error))
                report = None
            except Exception:
                logging.exception("REPORT_V0191_BUILD: cijfers niet berekend")
                st.error("De rapportagecijfers konden niet worden berekend. Bekijk REPORT_V0191_BUILD in de logboeken.")
                report = None

            if report is not None:
                summary = report["summary"]
                try:
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Bezetting", f"{summary['Bezetting (%)']}%" if summary['Bezetting (%)'] is not None else "Onbekend")
                    m2.metric("Dienstplaatsen open", summary["Dienstplaatsen open"] if summary["Dienstplaatsen open"] is not None else "Onbekend")
                    m3.metric("Diensten en taken toegewezen", summary["Toewijzingen incl. taken"])
                    m4.metric("Spreiding weekenddagen per 100%", summary["Spreiding weekenddagen per 100% (indicatief)"]
                              if summary["Spreiding weekenddagen per 100% (indicatief)"] is not None else "—")
                except Exception:
                    logging.exception("REPORT_V0191_METRICS: overzichtskaarten niet getoond")
                    st.warning("De overzichtskaarten konden niet worden getoond. De gegevens staan ook in de Excel-export.")
                st.caption(f"Gepubliceerde versie #{selected_plan['id']}. "
                           "De indicatieve spreiding houdt niet automatisch rekening met alle individuele beperkingen.")
                for warning in report["warnings"]:
                    # Streamlit's magic rendering displays a returned DeltaGenerator
                    # from a bare conditional expression as an enormous help object.
                    # Use ordinary statements: Streamlit only renders the message.
                    if "gewijzigd" in warning or "niet meegerekend" in warning:
                        st.warning(warning)
                    else:
                        st.caption(warning)

                t_people, t_categories, t_history = st.tabs([
                    "Controleurs", "Dienstcategorieën", "Meerdere maanden"])
                with t_people:
                    st.dataframe(pd.DataFrame(report["persons"]), use_container_width=True, hide_index=True)
                    st.caption("Weekenddag = zaterdag of zondag waarop een dienst begint. "
                               "Bij gewijzigde invoer tonen we geen verouderd wenspercentage.")
                    try:
                        person_chart = pd.DataFrame([{
                            "Controleur": r["Controleur"],
                            "Weekenddagen per 100%": r["Weekenddagen per 100% contract (indicatief)"]}
                            for r in report["persons"] if r["Actief in catalogus"]
                            and r["Weekenddagen per 100% contract (indicatief)"] is not None])
                        if not person_chart.empty:
                            st.bar_chart(person_chart.set_index("Controleur"), use_container_width=True)
                    except Exception:
                        logging.exception("REPORT_V0191_CHART_PEOPLE: grafiek overgeslagen")
                        st.caption("De grafiek kon niet worden getoond; de tabel erboven blijft beschikbaar.")
                with t_categories:
                    st.dataframe(pd.DataFrame(report["categories"]), hide_index=True, use_container_width=True)
                    try:
                        category_frame = pd.DataFrame(report["categories"])
                        if not category_frame.empty:
                            st.bar_chart(category_frame.set_index("Categorie")[["Toewijzingen"]],
                                         use_container_width=True)
                    except Exception:
                        logging.exception("REPORT_V0191_CHART_CATEGORIES: grafiek overgeslagen")
                        st.caption("De categoriegrafiek kon niet worden getoond; de tabel blijft beschikbaar.")
                    st.caption("Reguliere bezetting komt uit de gepubliceerde planningssamenvatting.")
                with t_history:
                    if report["history"]:
                        st.dataframe(pd.DataFrame(report["history"]), hide_index=True, use_container_width=True)
                    else:
                        st.info("Geen eerdere gepubliceerde maanden in dit venster.")
                    st.caption("Historische maanden gebruiken de huidige namen en contractpercentages. "
                               "Een gewijzigd contract kan daardoor de vergelijking beïnvloeden.")

                try:
                    xlsx_buffer = io.BytesIO()
                    with pd.ExcelWriter(xlsx_buffer, engine="openpyxl") as writer:
                        pd.DataFrame(safe_excel_rows([summary])).to_excel(writer, sheet_name="Samenvatting", index=False)
                        pd.DataFrame(safe_excel_rows(report["persons"])).to_excel(writer, sheet_name="Per controleur", index=False)
                        pd.DataFrame(safe_excel_rows(report["categories"])).to_excel(writer, sheet_name="Categorieen", index=False)
                        pd.DataFrame(safe_excel_rows(report["history"])).to_excel(writer, sheet_name="Maandhistoriek", index=False)
                        pd.DataFrame(safe_excel_rows([{"Toelichting": v} for v in report["warnings"]])).to_excel(
                            writer, sheet_name="Toelichting", index=False)
                    st.download_button("⬇️ Download rapport als Excel", data=xlsx_buffer.getvalue(),
                                       file_name=f"controleursplanning_rapport_{data['year']}_{data['month']:02d}.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                except Exception:
                    logging.exception("REPORT_V0191_EXCEL: export niet beschikbaar")
                    st.warning("De Excel-export is tijdelijk niet beschikbaar. Het rapport hierboven blijft zichtbaar.")


elif screen == "Optimalisatie vergelijken":
    st.subheader("Alternatieve maandplanningen vergelijken")
    st.caption("Versie 0.9: kies een of meer optimalisatieprofielen. Elke variant gebruikt exact dezelfde "
               "dienstbehoefte, medewerkers, taken en harde voorwaarden. Alleen zachte gewichten verschillen.")
    st.info("Het teamlabel organiseert je profielen. In versie 0.9 wordt nog steeds de **hele gezamenlijke "
            "maandplanning** met één profiel tegelijk berekend; afzonderlijke gewichten binnen één "
            "berekening per team volgen later.")

    teams = sorted({str(e.get("team", "")).strip() for e in data["employees"] if str(e.get("team", "")).strip()})
    team_choices = ["Alle teams"] + [t for t in teams if t != "Alle teams"]
    tab_compare, tab_profiles = st.tabs(["Alternatieven genereren", "Eigen profielen beheren"])

    with tab_profiles:
        st.markdown("#### Eigen optimalisatieprofielen")
        st.caption("Standaardprofielen blijven beschikbaar. Eigen profielen worden opgeslagen in de bestaande PostgreSQL-werkruimte.")
        customs = data.get("optimization_profiles", [])
        if customs:
            st.dataframe(pd.DataFrame([{
                "Naam": p["name"], "Team": p.get("team", "Alle teams"),
                "Voorkeur": p["preference_weight"], "Eerlijkheid": p["fairness_weight"],
                "Uren": p["hours_weight"]
            } for p in customs]), hide_index=True, use_container_width=True)
        else:
            st.caption("Er zijn nog geen eigen profielen opgeslagen.")
        editing = st.selectbox("Profielbewerking", ["Nieuw profiel"] +
                               [f"{i + 1}. {p['name']} ({p.get('team', 'Alle teams')})" for i, p in enumerate(customs)],
                               key="v09_profile_edit_choice")
        existing_idx = 0 if editing == "Nieuw profiel" else int(editing.split(".", 1)[0])
        current_profile = None if existing_idx == 0 else customs[existing_idx - 1]
        # Een apart formulier per selectie maakt het wisselen van profielen voorspelbaar.
        with st.form(f"v09_edit_form_{existing_idx}"):
            name = st.text_input("Profielnaam", value=current_profile["name"] if current_profile else "Mijn profiel",
                                 max_chars=60)
            prev_team = current_profile.get("team", "Alle teams") if current_profile else "Alle teams"
            scope = st.selectbox("Teamlabel", team_choices,
                                 index=team_choices.index(prev_team) if prev_team in team_choices else 0)
            ca, cb, cc = st.columns(3)
            with ca:
                wp = st.slider("Voorkeuren", 0, 100, int(current_profile["preference_weight"]) if current_profile else 25)
            with cb:
                wf = st.slider("Eerlijkheid", 0, 100, int(current_profile["fairness_weight"]) if current_profile else 1)
            with cc:
                wh = st.slider("Urenstreefdoelen", 0, 100, int(current_profile["hours_weight"]) if current_profile else 0)
            save = st.form_submit_button("Profiel opslaan", type="primary")
        if save:
            candidate = {"name": name.strip(), "team": scope, "preference_weight": int(wp),
                         "fairness_weight": int(wf), "hours_weight": int(wh)}
            updated = clone()
            stored = list(updated.get("optimization_profiles", []))
            if existing_idx:
                stored[existing_idx - 1] = candidate
            else:
                stored.append(candidate)
            updated["optimization_profiles"] = stored
            problems = validate_profiles(updated)
            if problems:
                st.error(" ".join(problems))
            else:
                replace_and_rerun(updated)
        if current_profile and st.button("Geselecteerd eigen profiel verwijderen", key=f"v09_del_{existing_idx}"):
            updated = clone()
            updated["optimization_profiles"].pop(existing_idx - 1)
            replace_and_rerun(updated)

    with tab_compare:
        st.markdown("#### Vergelijkingsberekening")
        label_team = st.selectbox("Profielen tonen voor", team_choices, key="v09_scope")
        available = [p for p in options_for(data)
                     if p.get("team", "Alle teams") in ("Alle teams", label_team)]
        indices = {p["id"]: p for p in available}
        default_selection = [p["id"] for p in available[:3]]
        chosen_ids = st.multiselect("Kies maximaal 4 verschillende profielen", options=list(indices),
                                    default=default_selection,
                                    format_func=lambda v: indices[v]["name"] +
                                    (f" · {indices[v]['team']}" if indices[v].get("team") != "Alle teams" else ""),
                                    key="v09_selected_profiles")
        limit_seconds = st.number_input("Maximale rekentijd per alternatief (seconden)",
                                        min_value=1, max_value=3600,
                                        value=min(30, int(data["settings"].get("time_limit_seconds", 10))),
                                        key="v09_seconds")
        use_history = st.checkbox("Gepubliceerde weekendhistoriek meenemen", value=PERSISTENT,
                                  disabled=not PERSISTENT, key="v09_history")
        lookback = st.slider("Aantal historische maanden", 1, 12, 3,
                             disabled=not use_history, key="v09_lookback")
        historical = (store.published_plans_before(engine, data["year"], data["month"], lookback)
                      if PERSISTENT and use_history else [])
        historical_values = (aggregate_history(historical, [e["id"] for e in data["employees"]])
                             if use_history else {})
        calculation_data = apply_published_history(data, historical_values) if use_history else data
        boundary_context_alternatives = (published_boundary_context(engine, data["year"], data["month"])
                                         if PERSISTENT else {"sources": {"previous": None, "next": None}, "assignments": []})
        calculation_data = with_boundary_context(calculation_data, boundary_context_alternatives)
        fingerprint = signature(data, historical + [{"boundary_sources": boundary_context_alternatives["sources"]}])
        active_comparison = st.session_state.get("alternatives_v09")
        if active_comparison and active_comparison["fingerprint"] != fingerprint:
            st.session_state.pop("alternatives_v09", None)
            active_comparison = None
            st.warning("De invoer of historische planning is veranderd. Genereer de alternatieven opnieuw.")
        problems = validate_dataset(data)
        for problem in problems:
            st.error(problem)
        if len(chosen_ids) > 4:
            st.warning("Selecteer maximaal vier profielen tegelijk.")
        st.caption("Meerdere berekeningen kunnen samen langer duren. Resultaten worden niet automatisch gepubliceerd "
                   "of in de database bewaard; je kiest achteraf expliciet één conceptplanning.")
        can_start = (len(chosen_ids) in range(1, 5) and not problems)
        if st.button("🚀 Alternatieven berekenen", type="primary", disabled=not can_start):
            results = []
            progress = st.progress(0, text="Berekeningen voorbereiden…")
            for i, identity in enumerate(chosen_ids):
                target_profile = indices[identity]
                try:
                    with st.spinner(f"Optimaliseren: {target_profile['name']}…"):
                        variation = with_profile(calculation_data, target_profile, int(limit_seconds))
                        generated = solve_month(variation)
                    generated.summary.update({
                        "boundary_sources": boundary_context_alternatives["sources"],
                        "optimization_profile": target_profile["name"],
                        "optimization_weights": {k: target_profile[k] for k in WEIGHT_KEYS},
                        "history_months": len(historical),
                        "history_lookback": lookback if use_history else 0,
                    })
                    results.append({"profile": target_profile, "result": asdict(generated)})
                except (ValueError, OverflowError) as err:
                    st.error(f"Profiel {target_profile['name']}: {err}")
                except Exception:
                    st.error(f"Profiel {target_profile['name']}: berekening mislukt. Bekijk de Streamlit-logs.")
                progress.progress(round(100 * (i + 1) / len(chosen_ids)),
                                  text=f"{i + 1} van {len(chosen_ids)} berekeningen afgerond")
            st.session_state.alternatives_v09 = {"fingerprint": fingerprint, "items": results}
            active_comparison = st.session_state.alternatives_v09
        if active_comparison and active_comparison["items"]:
            items = active_comparison["items"]
            table = []
            for item in items:
                p = PlanResult(**item["result"])
                table.append(compare_row(item["profile"], p, calculation_data))
            st.markdown("#### Resultaten naast elkaar")
            st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True)
            unique_rosters = {roster_signature(PlanResult(**item["result"])) for item in items
                              if item["result"]["status"] in ("OPTIMAL", "FEASIBLE")}
            st.caption(f"Verschillende roosters gevonden: {len(unique_rosters)}. Gelijke roosters zijn mogelijk; "
                       "verschillende gewichten garanderen niet dat de toewijzingen verschillen.")
            st.caption("De vergelijkingswaarden hebben voor alle profielen dezelfde betekenis: "
                       "open dienstplaatsen, open taken, ingewilligde of gemiste vrijwensen, "
                       "spreiding van weekenddagen per contractpercentage en testurenafwijking. "
                       "Ruwe OR-Tools-doelscores worden bewust niet onderling vergeleken.")
            eligible_items = [item for item in items
                              if item["result"]["status"] in ("OPTIMAL", "FEASIBLE")]
            if eligible_items:
                selected_idx = st.selectbox("Kies de conceptplanning die je wilt bewaren", list(range(len(eligible_items))),
                                            format_func=lambda i: eligible_items[i]["profile"]["name"] +
                                            f" (open: {eligible_items[i]['result']['summary'].get('open', '?')})",
                                            key="v09_choice_to_save")
                if st.button("💾 Gekozen alternatief als concept bewaren", key="v09_confirm_plan"):
                    if st.session_state.alternatives_v09["fingerprint"] != signature(data, historical + [{"boundary_sources": boundary_context_alternatives["sources"]}]):
                        st.error("Invoer veranderd. Genereer de alternatieven opnieuw.")
                    else:
                        plan = PlanResult(**eligible_items[selected_idx]["result"])
                        try:
                            new_id = (store.save_plan(engine, data, st.session_state.workspace_revision,
                                                      asdict(plan), current_user["employee_id"])
                                      if PERSISTENT else None)
                        except (ValueError, store.ConflictError) as err:
                            st.error(f"Concept niet opgeslagen: {err}")
                        except Exception:
                            st.error("Concept niet opgeslagen. Controleer de databaselogs.")
                        else:
                            st.session_state.last_plan = plan
                            if new_id is not None:
                                st.session_state.last_plan_id = new_id
                            st.success("Conceptplanning bewaard. Open nu **Planning** om haar te bekijken "
                                       "en eventueel expliciet te publiceren.")
            else:
                st.warning("Geen bruikbare alternatieven gevonden. Verhoog eventueel de rekentijd of controleer de regels.")
        elif active_comparison:
            st.info("Geen resultaten berekend.")


elif screen == "Mijn verlofaanvragen":
    st.subheader("Mijn verlofaanvragen")
    st.caption("Vraag verlof aan voor de actieve testmaand. Dit is geen goedgekeurde vrije dag totdat een beheerder of planner akkoord gaat. Verlofsaldi worden niet gecontroleerd.")
    eid = current_user["employee_id"]
    requests = store.list_leave_requests(engine, eid)
    if requests:
        st.dataframe(pd.DataFrame([{
            "Nummer": r["id"], "Van": r["start_date"], "Tot": r["end_date"],
            "Status": ("Goedgekeurd (deels ingetrokken)" if r["status"] == "approved" and
                       len(r["remaining_dates"]) <
                       (date.fromisoformat(r["end_date"]) - date.fromisoformat(r["start_date"])).days + 1
                       else STATUS_LABELS[r["status"]]),
            "Resterende dagen": ", ".join(date.fromisoformat(d).strftime("%d/%m") for d in r["remaining_dates"]) if r["remaining_dates"] else "—",
            "Testuren/dag": r["hours_per_day"], "Beslist door": r["decided_by"] or "—"
        } for r in requests]), hide_index=True, use_container_width=True)
    else:
        st.info("Je hebt nog geen verlofaanvragen ingediend.")
    if any(e["id"] == eid and e.get("active", True) for e in data["employees"]):
        first = date(data["year"], data["month"], 1)
        last = date(data["year"], data["month"], calendar.monthrange(data["year"], data["month"])[1])
        with st.form("leave_request_v010", clear_on_submit=False):
            st.markdown("#### Nieuwe verlofaanvraag")
            a, b = st.columns(2)
            with a:
                start = st.date_input("Van", value=first, min_value=first, max_value=last)
            with b:
                end = st.date_input("Tot en met", value=first, min_value=first, max_value=last)
            if st.form_submit_button("Verlof aanvragen"):
                try:
                    request_id = store.request_leave(engine, eid, start, end)
                    st.session_state.leave_notice_v010 = f"Aanvraag #{request_id} ingediend. Je krijgt pas vrij na goedkeuring."
                    st.rerun()
                except (ValueError, store.ConflictError) as exc:
                    st.error(str(exc))
    if requests:
        pending = [r for r in requests if r["status"] == "pending"]
        if pending:
            chosen = st.selectbox("Openstaande aanvraag intrekken", [r["id"] for r in pending],
                                  format_func=lambda i: next(f"#{r['id']} • {r['start_date']} t/m {r['end_date']}"
                                                             for r in pending if r["id"] == i))
            if st.button("Aanvraag intrekken"):
                try:
                    store.withdraw_leave_request(engine, chosen, eid)
                    st.session_state.leave_notice_v010 = "Aanvraag ingetrokken."
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    approved_requests = [r for r in requests if r["status"] == "approved"]
    cancellation_rows = store.list_leave_cancellations(engine, eid)
    pending_cancel_ids = {r["leave_request_id"] for r in cancellation_rows if r["status"] == "pending"}
    cancellable = [r for r in approved_requests if r["id"] not in pending_cancel_ids]
    st.markdown("#### Goedgekeurd verlof gedeeltelijk of volledig intrekken")
    st.caption("Selecteer de dagen die je wilt intrekken. De beheerder moet je verzoek goedkeuren. "
               "Alle overige goedgekeurde verlofdagen blijven geblokkeerd en een gepubliceerd rooster wijzigt niet automatisch.")
    if cancellable:
        cancel_id = st.selectbox("Goedgekeurd verlof", [r["id"] for r in cancellable],
                                 format_func=lambda i: next(
                                     f"#{r['id']} • {r['start_date']} t/m {r['end_date']} "
                                     f"({len(r['remaining_dates'])} dagen beschikbaar)"
                                     for r in cancellable if r["id"] == i),
                                 key="cancel_select_v020")
        selected_leave = next(r for r in cancellable if r["id"] == cancel_id)
        remaining = [date.fromisoformat(d) for d in selected_leave["remaining_dates"]]
        with st.form(f"leave_cancel_request_v020_{cancel_id}"):
            selected_dates = st.multiselect("Welke dagen wil je intrekken?",
                                            options=remaining, default=remaining,
                                            format_func=lambda d: d.strftime("%d/%m/%Y"))
            reason = st.text_area("Reden voor de intrekking", max_chars=400,
                                  placeholder="Bijvoorbeeld: mijn verlof is voor deze dagen niet nodig")
            if st.form_submit_button("Intrekking aanvragen"):
                try:
                    store.request_leave_cancellation(engine, cancel_id, eid, reason, days=selected_dates)
                    st.session_state.leave_notice_v010 = "Intrekkingsverzoek verzonden naar de beheerder."
                    st.rerun()
                except (ValueError, store.ConflictError) as exc:
                    st.error(str(exc))
    elif approved_requests:
        st.info("Voor je goedgekeurde verlof staat al een intrekkingsverzoek open.")
    if cancellation_rows:
        st.markdown("**Mijn intrekkingsverzoeken**")
        cancel_status = {"pending": "In behandeling", "approved": "Goedgekeurd",
                         "rejected": "Afgewezen"}
        st.dataframe(pd.DataFrame([{
            "Verzoek": r["id"], "Verlof": r["leave_request_id"],
            "Geselecteerde dagen": ", ".join(date.fromisoformat(d).strftime("%d/%m") for d in r["selected_dates"]),
            "Status": cancel_status.get(r["status"], r["status"]),
            "Beslist door": r["decided_by"] or "—"
        } for r in cancellation_rows]), hide_index=True, use_container_width=True)
    if st.session_state.pop("leave_notice_v010", None):
        st.success("Je aanvraag is verwerkt. Controleer de status hierboven.")

elif screen == "Verlofaanvragen beheren":
    st.subheader("Verlofaanvragen beheren")
    st.caption("Goedkeuring registreert een VOLLEDIGE afwezigheidsdag en blokkeert de controleur bij de volgende berekening. Reeds gepubliceerde maandplanningen worden NIET stilzwijgend aangepast.")
    rows = store.list_leave_requests(engine, current_user["employee_id"])
    if rows:
        employee_names = {e["id"]: e["name"] for e in data["employees"]}
        st.dataframe(pd.DataFrame([{
            "Nummer": r["id"], "Controleur": employee_names.get(r["employee_id"], r["employee_id"]),
            "Van": r["start_date"], "Tot": r["end_date"],
            "Status": ("Goedgekeurd (deels ingetrokken)" if r["status"] == "approved" and
                       len(r["remaining_dates"]) <
                       (date.fromisoformat(r["end_date"]) - date.fromisoformat(r["start_date"])).days + 1
                       else STATUS_LABELS[r["status"]]),
            "Resterende dagen": ", ".join(date.fromisoformat(d).strftime("%d/%m") for d in r["remaining_dates"]) if r["remaining_dates"] else "—",
            "Testuren/dag": r["hours_per_day"], "Beslist door": r["decided_by"] or "—"
        } for r in rows]), hide_index=True, use_container_width=True)
        pending = [r for r in rows if r["status"] == "pending"]
        if pending:
            target_id = st.selectbox("Aanvraag behandelen", [r["id"] for r in pending],
                format_func=lambda i: next(f"#{r['id']} • {r['employee_id']} • {r['start_date']} t/m {r['end_date']}"
                                           for r in pending if r["id"] == i))
            hours = st.number_input("Testuren per goedgekeurde verlofdag (geen officiële urenverrekening)",
                                    min_value=0.0, max_value=16.0, value=0.0, step=0.1)
            a, b = st.columns(2)
            if a.button("✅ Goedkeuren", type="primary"):
                try:
                    store.decide_leave_request(engine, target_id, current_user["employee_id"], True, hours)
                    st.session_state.leave_manager_notice_v010 = "Verlof goedgekeurd. Bereken en publiceer de planning opnieuw indien nodig."
                    st.rerun()
                except (ValueError, store.ConflictError) as exc:
                    st.error(str(exc))
            if b.button("Afwijzen"):
                try:
                    store.decide_leave_request(engine, target_id, current_user["employee_id"], False)
                    st.session_state.leave_manager_notice_v010 = "Aanvraag afgewezen."
                    st.rerun()
                except (ValueError, store.ConflictError) as exc:
                    st.error(str(exc))
        else:
            st.success("Geen openstaande aanvragen.")
    else:
        st.info("Er zijn nog geen aanvragen ingediend.")
    st.markdown("#### Goedgekeurd verlof geheel of gedeeltelijk intrekken")
    cancels = store.list_leave_cancellations(engine, current_user["employee_id"])
    pending_cancels = [r for r in cancels if r["status"] == "pending"]
    if pending_cancels:
        st.dataframe(pd.DataFrame([{
            "Verzoek": r["id"], "Verlof": r["leave_request_id"],
            "Controleur": r["employee_id"], "Van": r["start_date"],
            "Tot": r["end_date"],
            "In te trekken dagen": ", ".join(r["selected_dates"]),
            "Reden": r["reason"]
        } for r in pending_cancels]), hide_index=True, use_container_width=True)
        target_cancel = st.selectbox("Intrekkingsverzoek behandelen",
                                      [r["id"] for r in pending_cancels],
                                      format_func=lambda i: f"Intrekkingsverzoek #{i}")
        left, right = st.columns(2)
        if left.button("✅ Intrekking goedkeuren", key="approve_leave_cancel_v0181"):
            try:
                store.decide_leave_cancellation(engine, target_cancel, current_user["employee_id"], True)
                st.session_state.leave_manager_notice_v010 = (
                    "Verlofblokkering verwijderd. Controleer en publiceer de maandplanning opnieuw.")
                st.rerun()
            except (ValueError, store.ConflictError) as exc:
                st.error(str(exc))
        if right.button("Intrekking afwijzen", key="reject_leave_cancel_v0181"):
            try:
                store.decide_leave_cancellation(engine, target_cancel, current_user["employee_id"], False)
                st.session_state.leave_manager_notice_v010 = "Intrekking afgewezen; het verlof blijft behouden."
                st.rerun()
            except (ValueError, store.ConflictError) as exc:
                st.error(str(exc))
    else:
        st.caption("Geen intrekkingsverzoeken die op een beslissing wachten.")
    st.markdown("**Rechtstreeks intrekken door beheerder/planner**")
    st.caption("Gebruik dit uitsluitend wanneer de controleur de intrekking buiten de webapp gevraagd heeft. "
               "De reden en je beslissing worden geregistreerd.")
    pending_leave_ids = {r["leave_request_id"] for r in pending_cancels}
    approved_leave_rows = [r for r in rows if r["status"] == "approved"
                           and r["id"] not in pending_leave_ids]
    if approved_leave_rows:
        selected_leave = st.selectbox("Goedgekeurde verlofaanvraag",
                                      [r["id"] for r in approved_leave_rows],
                                      format_func=lambda i: next(
                                          f"#{r['id']} • {r['employee_id']} • {r['start_date']} t/m {r['end_date']}"
                                          for r in approved_leave_rows if r["id"] == i),
                                      key="manager_leave_select_v020")
        selected_row = next(r for r in approved_leave_rows if r["id"] == selected_leave)
        remaining = [date.fromisoformat(d) for d in selected_row["remaining_dates"]]
        with st.form(f"manager_revoke_leave_v020_{selected_leave}"):
            selected_dates = st.multiselect("Welke goedgekeurde dagen intrekken?",
                                            options=remaining, default=remaining,
                                            format_func=lambda d: d.strftime("%d/%m/%Y"))
            admin_reason = st.text_area("Reden / verwijzing naar verzoek controleur", max_chars=400)
            confirm_cancel = st.checkbox("Ik bevestig dat de betrokken controleur om deze intrekking heeft gevraagd.")
            if st.form_submit_button("Geselecteerde verlofdagen intrekken", disabled=not confirm_cancel):
                try:
                    store.revoke_approved_leave(engine, selected_leave,
                                               current_user["employee_id"], admin_reason,
                                               days=selected_dates)
                    st.session_state.leave_manager_notice_v010 = (
                        "Geselecteerde verlofdagen vrijgegeven. Controleer en publiceer de maand opnieuw.")
                    st.rerun()
                except (ValueError, store.ConflictError) as exc:
                    st.error(str(exc))
    info = st.session_state.pop("leave_manager_notice_v010", None)
    if info:
        st.success(info)
    published = store.load_plan(engine, data["year"], data["month"], published_only=True)
    if published and published["revision"] != st.session_state.workspace_revision:
        st.warning("Er is een gepubliceerde planning uit een oudere invoerversie. Bereken en publiceer een nieuwe planning voordat je die als actueel beschouwt.")

elif screen == "Mijn ruilaanvragen":
    st.subheader("Mijn dienst-ruilaanvragen")
    eid = current_user["employee_id"]
    rows = store.list_swap_requests(engine, eid)
    labels = {"pending": "Wacht op collega", "accepted": "Wacht op planner",
              "declined": "Afgewezen door collega", "withdrawn": "Ingetrokken",
              "rejected": "Afgewezen door planner", "approved": "Goedgekeurd en gepubliceerd"}
    if rows:
        st.dataframe(pd.DataFrame([{
            "Aanvraag": r["id"], "Eigenaar": r["initiator_id"], "Collega": r["colleague_id"],
            "Oorspronkelijk": f'{r["own_day"]} · {r["own_shift"]}',
            "Ruilpartner": f'{r["their_day"]} · {r["their_shift"]}',
            "Status": labels.get(r["status"], r["status"])
        } for r in rows]), hide_index=True, use_container_width=True)
        incoming = [r for r in rows if r["status"] == "pending" and r["colleague_id"] == eid]
        outgoing = [r for r in rows if r["status"] == "pending" and r["initiator_id"] == eid]
        if incoming:
            st.markdown("#### Ruilvoorstel van collega")
            chosen = st.selectbox("Aanvraag beantwoorden", incoming, format_func=lambda r:
                f'#{r["id"]}: {r["own_day"]} {r["own_shift"]} ↔ {r["their_day"]} {r["their_shift"]}')
            left,right = st.columns(2)
            if left.button("Akkoord met voorgestelde ruil", type="primary"):
                try:
                    store.respond_swap(engine, chosen["id"], eid, True)
                    st.rerun()
                except (ValueError, store.ConflictError) as exc:
                    st.error(str(exc))
            if right.button("Voorstel afwijzen"):
                try:
                    store.respond_swap(engine, chosen["id"], eid, False)
                    st.rerun()
                except (ValueError, store.ConflictError) as exc:
                    st.error(str(exc))
        if outgoing:
            chosen = st.selectbox("Eigen openstaand voorstel intrekken", outgoing,
                format_func=lambda r: f'#{r["id"]}: {r["own_day"]} {r["own_shift"]}')
            if st.button("Voorstel intrekken"):
                try:
                    store.respond_swap(engine, chosen["id"], eid, False)
                    st.rerun()
                except (ValueError, store.ConflictError) as exc:
                    st.error(str(exc))
    else:
        st.info("Je hebt nog geen ruilaanvragen.")
    published = store.load_plan(engine, data["year"], data["month"], published_only=True)
    if not published or published["revision"] != st.session_state.workspace_revision:
        st.warning("Voor nieuwe aanvragen is een actuele gepubliceerde maandplanning nodig.")
    else:
        own = [r for r in regular_assignments(published["payload"]) if r["Personeelsnr"] == eid]
        if not own:
            st.info("Er zijn geen eigen reguliere diensten beschikbaar voor een ruil.")
        else:
            st.markdown("#### Nieuwe ruil aanvragen")
            st.caption("Je geeft het personeelsnummer en een concrete dienst van je collega op. Alleen de collega kan het voorstel accepteren; daarna beslist de planner.")
            with st.container():
                own_row = st.selectbox("Mijn dienst om te ruilen", own,
                    format_func=lambda r: f'{r["Datum"]} · {r["Dienstnummer"]} ({r["Begin"]}–{r["Einde"]})')
                colleague = st.text_input("Personeelsnummer van de collega", max_chars=64)
                first = date(data["year"], data["month"], 1)
                last = date(data["year"], data["month"], calendar.monthrange(data["year"],data["month"])[1])
                their_day = st.date_input("Datum van zijn/haar dienst", value=first, min_value=first, max_value=last)
                possible = sorted({str(r["shift_id"]) for r in data["demand"] if r["date"] == their_day.isoformat()})
                their_shift = st.selectbox("Dienstnummer van de collega", possible or ["—"], disabled=not possible)
                submit = st.button("Ruilvoorstel versturen", disabled=not possible)
            if submit:
                try:
                    store.request_swap(engine, eid, colleague.strip(), date.fromisoformat(own_row["Datum"]),
                                       str(own_row["Dienstnummer"]), their_day, their_shift)
                    st.success("Ruilaanvraag ingediend. De collega moet eerst akkoord gaan.")
                    st.rerun()
                except (ValueError, store.ConflictError) as exc:
                    st.error(str(exc))

elif screen == "Ruilaanvragen beheren":
    st.subheader("Ruilaanvragen beoordelen")
    st.caption("Alleen aanvragen met wederzijds akkoord kunnen worden goedgekeurd. Voor publicatie controleert OR-Tools het VOLLEDIGE aangepaste rooster met vaste toewijzingen.")
    requests = store.list_swap_requests(engine, current_user["employee_id"])
    if requests:
        st.dataframe(pd.DataFrame([{
            "Nummer": r["id"], "Controleur": r["initiator_id"], "Collega": r["colleague_id"],
            "Dienst A": f'{r["own_day"]} · {r["own_shift"]}',
            "Dienst B": f'{r["their_day"]} · {r["their_shift"]}',
            "Status": r["status"], "Nieuwe versie": r["new_plan_id"] or "—"
        } for r in requests]), hide_index=True, use_container_width=True)
        accepted = [r for r in requests if r["status"] == "accepted"]
        if accepted:
            chosen = st.selectbox("Ruil beoordelen", accepted, format_func=lambda r:
                f'#{r["id"]}: {r["initiator_id"]} ↔ {r["colleague_id"]}')
            left,right = st.columns(2)
            if left.button("Goedkeuren en publiceren", type="primary"):
                try:
                    with st.spinner("OR-Tools controleert het volledige rooster (max. 15 seconden)…"):
                        result = store.decide_swap(engine, chosen["id"], current_user["employee_id"], True)
                    st.success(f'Ruil goedgekeurd. Nieuwe gepubliceerde planversie #{result["new_plan_id"]}.')
                    st.rerun()
                except (ValueError, store.ConflictError) as exc:
                    st.error(str(exc))
                except Exception:
                    st.error("De volledige solververificatie kon niet worden voltooid; de planning is niet aangepast.")
            if right.button("Ruil weigeren"):
                try:
                    store.decide_swap(engine, chosen["id"], current_user["employee_id"], False)
                    st.rerun()
                except (ValueError, store.ConflictError) as exc:
                    st.error(str(exc))
        else:
            st.info("Er zijn geen ruilaanvragen die op goedkeuring wachten.")
    else:
        st.info("Er zijn nog geen ruilaanvragen.")

elif screen == "Mijn voorkeuren":
    st.subheader("Mijn persoonlijke voorkeuren")
    eid = current_user["employee_id"]
    if not any(e["id"] == eid for e in data["employees"]):
        st.error("Je account is nog niet gekoppeld aan een fictieve controleur.")
    else:
        render_preferences(eid, "own")

elif screen == "Mijn planning":
    st.subheader("Mijn gepubliceerde maandplanning")
    eid = current_user["employee_id"]
    published = store.load_plan(engine, data["year"], data["month"], published_only=True)
    if not published:
        st.info("Voor deze maand is nog geen planning gepubliceerd. Je kunt je dienstwensen wel invullen bij **Mijn voorkeuren**.")
        # De voorkeurenkalender is bruikbaar voordat er een officiële planning is.
        weeks = month_tiles(data, eid, None)
        view = "Weekkaarten"
        changes = []
    else:
        if published["revision"] != st.session_state.workspace_revision:
            st.warning("De gepubliceerde planning kan verouderd zijn na wijzigingen of goedgekeurd verlof. "
                       "Vraag de planner naar de actuele stand.")
        versions = store.personal_published_versions(engine, data["year"], data["month"], eid)
        changes = (personal_publication_changes(versions[1]["assignments"], versions[0]["assignments"], eid)
                   if len(versions) > 1 else [])
        own = own_published_assignments(published["payload"], eid)
        assigned = [r for day_rows in own.values() for r in day_rows]
        total_hours = round(sum(float(r.get("Uren", 0)) for r in assigned), 2)
        st.caption(f"Gepubliceerde testversie #{published['id']} · {data['month']:02d}/{data['year']}")
        a, b, c, d = st.columns(4)
        a.metric("Diensten/taken", len(assigned))
        b.metric("Geplande uren", f"{total_hours:g} u")
        c.metric("Dagen zonder toewijzing", len(days_in_month(data)) - len(own))
        d.metric("Wijzigingen sinds vorige publicatie", len(changes))
        st.caption("Een dag zonder dienst is niet automatisch een formele rust- of verlofdag.")
        view = st.radio("Weergave", ["Maandkalender", "Weekkaarten", "Tabel"], horizontal=True,
                        key=f"calendar_view_v017_{eid}_{data['year']}_{data['month']}")
        leave_requests = store.list_leave_requests(engine, eid)
        weeks = month_tiles(data, eid, published["payload"], leave_requests,
                            {c["Datum"] for c in changes})

    if view == "Maandkalender":
        st.caption("🟢 Toegewezen dienst · 🟠 Gewijzigd sinds vorige publicatie · 🟣 Activiteit · 🏠 Vrijwens is geen goedgekeurd verlof")
        columns = st.columns(7)
        for col, name in zip(columns, CALENDAR_DAYS):
            col.markdown(f"**{name}**")
        for week in weeks:
            columns = st.columns(7)
            for col, tile in zip(columns, week):
                with col:
                    if not tile["in_month"]:
                        st.caption(" ")
                        continue
                    with st.container(border=True):
                        st.markdown(f"**{tile['day']:02d}**" + (" 🟠" if tile["changed"] else ""))
                        if tile["category"] == "dienst":
                            st.markdown("🟢 " + tile["primary"])
                        elif tile["category"] == "activiteit":
                            st.markdown("🟣 " + tile["primary"])
                        else:
                            st.caption(tile["primary"])
                        for leave in tile["leave"]:
                            st.caption(leave)
                        if tile["wish"] != "Geen voorkeur":
                            st.caption("Wens: " + tile["wish"])
    elif view == "Weekkaarten":
        selected_week = st.selectbox("Bekijk een week", range(len(weeks)),
                                    format_func=lambda i: (f"Week {i + 1}: "
                                                           f"{next(t['date'] for t in weeks[i] if t['in_month'])}"),
                                    key=f"calendar_week_v017_{eid}_{data['year']}_{data['month']}")
        for tile in weeks[selected_week]:
            if not tile["in_month"]:
                continue
            with st.container(border=True):
                st.markdown(f"**{tile['weekday']} {tile['date']}**" + (" 🟠 Gewijzigd" if tile["changed"] else ""))
                st.write(tile["primary"])
                st.caption("Mijn voorkeur: " + tile["wish"])
                if tile["leave"]:
                    st.caption("Aanvragen: " + ", ".join(tile["leave"]))
    else:
        st.dataframe(pd.DataFrame(personal_calendar(data, eid, published["payload"] if published else None)),
                     hide_index=True, use_container_width=True)

    if published:
        if len(versions) > 1:
            with st.expander(f"Roosterwijzigingen sinds vorige publicatie ({len(changes)})"):
                if changes:
                    st.dataframe(pd.DataFrame(changes), use_container_width=True, hide_index=True)
                else:
                    st.success("Je diensttoewijzingen zijn niet veranderd sinds de vorige publicatie.")
        else:
            st.caption("Dit is de eerste gepubliceerde versie van deze maand.")
        rows = personal_calendar(data, eid, published["payload"])
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="Mijn maand")
        st.download_button("⬇️ Mijn eigen maandrooster downloaden (Excel)", data=buffer.getvalue(),
                           file_name=f"mijn_planning_{data['year']}_{data['month']:02d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

elif screen == "Mijn aanvragen & wijzigingen":
    st.subheader("Mijn aanvragen en roosterwijzigingen")
    eid = current_user["employee_id"]
    leave = store.list_leave_requests(engine, eid)
    swaps = store.list_swap_requests(engine, eid)
    feed = personal_request_feed(leave, swaps, eid)
    a, b = st.columns(2)
    a.metric("Aanvragen in totaal", feed["total"])
    b.metric("Nog in behandeling", feed["open"])
    if feed["items"]:
        st.dataframe(pd.DataFrame(feed["items"]), hide_index=True, use_container_width=True)
    else:
        st.info("Je hebt nog geen aanvragen ingediend of ontvangen.")
    st.caption("Een aanvraag in behandeling is geen goedgekeurd verlof of uitgevoerde ruil. "
               "Gebruik de bestaande onderdelen **Mijn verlofaanvragen** en **Mijn ruilaanvragen** om acties uit te voeren.")
    versions = store.personal_published_versions(engine, data["year"], data["month"], eid)
    if len(versions) >= 2:
        changes = personal_publication_changes(versions[1]["assignments"], versions[0]["assignments"], eid)
        st.markdown("#### Wijzigingen aan mijn gepubliceerde diensten")
        if changes:
            st.dataframe(pd.DataFrame(changes), use_container_width=True, hide_index=True)
        else:
            st.success("Geen wijzigingen aan jouw diensten tussen de laatste twee publicaties.")
    elif versions:
        st.info("Er is voor deze maand nog maar één gepubliceerde versie. Er zijn nog geen eerdere publicaties om mee te vergelijken.")
    else:
        st.info("Deze maand heeft nog geen gepubliceerde planning.")

elif screen == "Roosterwijzigingen":
    st.subheader("Gepubliceerde roosterwijzigingen")
    st.caption("Vergelijk de laatste twee gepubliceerde versies. Concepten tellen niet mee.")
    people = sorted(data["employees"], key=lambda e: (e.get("name", ""), e["id"]))
    if people:
        person_id = st.selectbox("Selecteer een controleur", [p["id"] for p in people],
                                 format_func=lambda x: next(p["name"] for p in people if p["id"] == x),
                                 key=f"changed_employee_v017_{data['year']}_{data['month']}")
        versions = store.personal_published_versions(engine, data["year"], data["month"],
                                                       current_user["employee_id"], person_id)
        if len(versions) < 2:
            st.info("Nog geen twee gepubliceerde versies voor deze maand beschikbaar.")
        else:
            changes = personal_publication_changes(versions[1]["assignments"], versions[0]["assignments"], person_id)
            st.metric("Gewijzigde kalenderdagen", len(changes))
            if changes:
                st.dataframe(pd.DataFrame(changes), hide_index=True, use_container_width=True)
            else:
                st.success("Geen wijzigingen in de diensttoewijzingen van deze controleur.")
    else:
        st.info("Voeg eerst fictieve controleurs toe.")


elif screen == "Meldingen" and PERSISTENT:
    st.subheader("🔔 Mijn meldingen")
    eid = current_user["employee_id"]
    items = store.notifications_for(engine, eid, limit=100)
    unread_count = sum(not item["read"] for item in items)
    st.caption(f"{unread_count} ongelezen · meldingen worden uitsluitend binnen de webapp getoond.")
    if unread_count and st.button("Alles als gelezen markeren"):
        store.mark_all_notices_read(engine, eid)
        st.rerun()
    if not items:
        st.info("Je hebt momenteel geen meldingen.")
    for notice in items:
        with st.container(border=True):
            st.markdown(("**🔵 " if not notice["read"] else "**") + notice["title"] + "**")
            st.caption(notice["created_at"] + " UTC")
            st.write(notice["body"])
            if not notice["read"] and st.button("Markeer als gelezen", key=f"read_notice_{notice['id']}"):
                store.mark_notice_read(engine, notice["id"], eid)
                st.rerun()

elif screen == "Publicatiebeheer" and PERSISTENT and is_manager:
    st.subheader("Publicatiebeheer")
    st.caption("Overzicht van de geselecteerde kalendermaand. Een concept wordt pas zichtbaar "
               "voor controleurs nadat je het bij Planning expliciet publiceert.")
    current = store.load_plan(engine, data["year"], data["month"])
    published = store.load_plan(engine, data["year"], data["month"], published_only=True)
    a, b = st.columns(2)
    a.metric("Laatste opgeslagen versie", f"#{current['id']}" if current else "Geen")
    b.metric("Laatste publicatie", f"#{published['id']}" if published else "Niet gepubliceerd")
    if current and not current["published"]:
        try:
            preview = store.publication_preview(engine, current["id"], current_user["employee_id"])
            st.write(f"Concept #{current['id']} · status: {preview['status']}")
            st.write(f"Aantal controleurs met gewijzigde diensten: {preview['affected_controllers']}")
            if preview["open_positions"] is not None:
                st.write(f"Openstaande dienstplaatsen: {preview['open_positions']}")
            if current["revision"] != st.session_state.workspace_revision:
                st.warning("Het concept is verouderd. Bereken de planning opnieuw.")
            st.info("Ga naar Planning → Controle vóór publicatie om dit concept gecontroleerd te publiceren.")
        except ValueError as exc:
            st.error(str(exc))
    elif published:
        st.success("Deze maand heeft een gepubliceerde planning.")
    else:
        st.info("Nog geen berekende planning beschikbaar voor deze maand.")
    st.caption("Publicatie op een toekomstige datum is nog niet geautomatiseerd. "
               "Gratis Streamlit-hosting garandeert geen continu actief achtergrondproces.")

elif screen == "Accounts":
    st.subheader("Accounts beheren — alleen hoofdbeheerder")
    accounts = store.list_accounts(engine)
    st.dataframe(pd.DataFrame(accounts), hide_index=True, use_container_width=True)
    with st.form("new_account", clear_on_submit=True):
        st.markdown("#### Nieuw testaccount")
        eid = st.text_input("Personeelsnummer", max_chars=64)
        name = st.text_input("Weergavenaam", max_chars=160)
        role = st.selectbox("Rol", ["controleur", "planner", "admin"])
        password = st.text_input("Tijdelijk wachtwoord (minstens 14 tekens)", type="password")
        if st.form_submit_button("Account aanmaken"):
            try:
                if role == "controleur" and eid.strip() not in {e["id"] for e in data["employees"]}:
                    raise ValueError("Voeg deze testcontroleur eerst toe bij 'Controleurs'.")
                store.add_account(engine, eid, name, role, password, current_user["employee_id"])
                st.success("Testaccount aangemaakt. Geef het tijdelijke wachtwoord uitsluitend via een veilig kanaal door.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    st.divider()
    with st.form("manage_account"):
        eid = st.selectbox("Bestaand account", [a["employee_id"] for a in accounts])
        selected = next(a for a in accounts if a["employee_id"] == eid)
        enabled = st.checkbox("Account actief", value=selected["active"])
        new_password = st.text_input("Nieuw tijdelijk wachtwoord (optioneel)", type="password")
        if st.form_submit_button("Accountinstellingen opslaan"):
            try:
                if enabled != selected["active"]:
                    store.set_account_state(engine, eid, enabled, current_user["employee_id"])
                if new_password:
                    store.reset_password(engine, eid, new_password, current_user["employee_id"])
                st.success("Accountinstellingen opgeslagen.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

elif screen == "Historiek":
    st.subheader("Wijzigingshistoriek")
    st.caption("Beknopt auditlog. Dit is nog geen volledig forensisch bedrijfslog.")
    st.dataframe(pd.DataFrame(store.recent_audit(engine)), use_container_width=True, hide_index=True)
