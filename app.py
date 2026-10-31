"""Controleursplanning: interactieve, uitsluitend fictieve proefversie."""
from __future__ import annotations

import io
import json
import os
from dataclasses import asdict
from datetime import date

import pandas as pd
import streamlit as st

from demo_data import CATEGORIES, WEEKDAYS, build_demo, next_month
from planner import PlanResult, solve_month, validate_dataset
from extras import (PREFERENCE_TYPES, CREDIT_TYPES, REST_MODES, preference_type,
                    preference_identity, preference_description, summarize_hours)
import store
import catalog
from policy_v06 import weekend_start_dates, hours_overview, service_overview

st.set_page_config(page_title="Controleursplanning | v0.6", page_icon="📅", layout="wide")


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


def plan_excel(plan, state: dict) -> bytes:
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
    return buffer.getvalue()


def replace_data(updated: dict) -> None:
    errors = validate_dataset(updated)
    if errors:
        st.error("Gegevens niet opgeslagen: " + " ".join(errors))
        st.stop()
    if PERSISTENT:
        try:
            new_revision = store.save_workspace(
                engine, updated, st.session_state.workspace_revision,
                current_user["employee_id"], "Projectgegevens aangepast"
            )
            st.session_state.workspace_revision = new_revision
        except (store.ConflictError, ValueError) as error:
            st.error(str(error))
            st.stop()
    st.session_state.project_data = updated
    st.session_state.pop("last_plan", None)


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



def render_preferences(eid: str, scope: str) -> None:
    """Eén formulier voor beheerder of controleur; opslagrechten in store.py."""
    data = st.session_state.project_data
    own = [p for p in data["preferences"] if p["employee_id"] == eid]
    if own:
        st.dataframe(pd.DataFrame([{"Type": PREFERENCE_TYPES[preference_type(p)],
                                   "Details": preference_description(p), "Prioriteit": p["priority"]}
                                  for p in own]), hide_index=True, use_container_width=True)
    else:
        st.info("Nog geen persoonlijke wensen geregistreerd voor deze maand.")
    kind = st.selectbox("Soort voorkeur", list(PREFERENCE_TYPES),
                        format_func=lambda x: PREFERENCE_TYPES[x], key="pref_kind_" + scope)
    with st.form("pref_form_" + scope + "_" + kind):
        pref = {"employee_id": eid, "type": kind}
        if kind in ("free_day", "work_day"):
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
        if st.form_submit_button("Voorkeur opslaan"):
            state = clone()
            state["preferences"] = [p for p in state["preferences"]
                                    if preference_identity(p) != preference_identity(pref)]
            state["preferences"].append(pref)
            replace_and_rerun(state)
    if own:
        chosen = st.selectbox("Voorkeur intrekken", range(len(own)),
                              format_func=lambda i: PREFERENCE_TYPES[preference_type(own[i])] + " — " + preference_description(own[i]),
                              key="remove_pref_" + scope)
        if st.button("Verwijder geselecteerde voorkeur", key="remove_button_" + scope):
            state = clone()
            key = preference_identity(own[chosen])
            state["preferences"] = [p for p in state["preferences"] if preference_identity(p) != key]
            replace_and_rerun(state)


if PERSISTENT:
    try:
        loaded, revision = store.load_workspace(engine)
    except Exception:
        st.error("De gedeelde gegevens konden niet worden opgehaald.")
        st.stop()
    previous_revision = st.session_state.get("workspace_revision")
    st.session_state.project_data = loaded
    st.session_state.workspace_revision = revision
    if previous_revision is not None and previous_revision != revision:
        # Een gelijktijdige wijziging mag geen oude, net ingediende formuliervelden overschrijven.
        st.session_state.remote_change_notice = True
        st.rerun()
elif "project_data" not in st.session_state:
    st.session_state.project_data = build_demo()

data = st.session_state.project_data
is_manager = not PERSISTENT or current_user["role"] in ("admin", "planner")

st.title("📅 Controleursplanning")
st.caption("Proefversie 0.6 • GitHub + Streamlit + Google OR-Tools")
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
            replace_and_rerun(build_demo(data["year"], data["month"]))
    st.divider()
    st.caption("Niet gekoppeld aan systemen van De Lijn.")

screens = (["Overzicht", "Controleurs", "Diensten", "Maandbehoefte", "Voorkeuren", "Uren en activiteiten", "Planningsregels", "Weekend en maandgrenzen", "Planning"]
           if is_manager else ["Mijn planning", "Mijn voorkeuren"])
if PERSISTENT and current_user["role"] == "admin":
    screens += ["Accounts", "Historiek"]
screen = st.radio("Onderdeel", screens, horizontal=True, label_visibility="collapsed")

if screen == "Overzicht":
    st.subheader("Projectoverzicht")
    a, b, c, d = st.columns(4)
    a.metric("Controleurs", sum(bool(e.get("active", True)) for e in data["employees"]))
    b.metric("Dienstnummers", len(data["shifts"]))
    c.metric("Dienstplaatsen deze maand", sum(r["required"] for r in data["demand"]))
    d.metric("Vrijwensen", len(data["preferences"]))
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

**Nog niet gebouwd:** ruilaanvragen, taakbeheer, goedkeuringsstromen, wettelijke validatie, teams, controles over maandgrenzen en automatische back-ups. Deze onderdelen volgen in latere versies.""")

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
    st.subheader("Dienstencatalogus")
    st.caption("Een dienstnummer heeft vaste werkuren en een vast benodigd aantal controleurs. Een nachtdienst mag over middernacht lopen.")
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
                if sh:
                    state["shifts"] = [dict(existing, **entry) if existing["id"] == selected else existing for existing in state["shifts"]]
                    catalog.sync_required(state, selected, int(required))
                else:
                    state["shifts"].append(entry)
                replace_and_rerun(state)
    st.info("Bij wijziging van de vaste bezetting passen we de behoefte voor de actieve maand aan. Eerder opgeslagen planningsversies blijven bewaard als historisch resultaat; bereken een nieuwe conceptplanning om de gewijzigde diensturen te verwerken.")

elif screen == "Maandbehoefte":
    st.subheader("Welke dienstnummers zijn op welke dagen nodig?")
    month_start = date(int(data["year"]), int(data["month"]), 1)
    coly, colm = st.columns(2)
    with st.form("month_form"):
        with coly:
            year = st.number_input("Jaar", 2025, 2040, int(data["year"]))
        with colm:
            month = st.selectbox("Maand", range(1, 13), index=int(data["month"])-1)
        if st.form_submit_button("Andere testmaand starten (wist huidige demo-invoer)"):
            if (year, month) != (data["year"], data["month"]):
                replace_and_rerun(build_demo(int(year), int(month)))
    st.caption("Let op: in v0.3 is nog maar één testmaand tegelijk bewerkbaar. Exporteer eerst je JSON vóór je de maand wijzigt.")
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
    st.caption("Alle zes voorkeurtypes zijn **zachte** wensen. Ze mogen nooit verplichte bezetting, rust of inzetbaarheidsregels overrulen.")
    if data["employees"]:
        chosen_pref = st.selectbox("Controleur", [e["id"] for e in data["employees"]],
                                   format_func=lambda i: next(e["name"] for e in data["employees"] if e["id"] == i))
        render_preferences(chosen_pref, "manager")

elif screen == "Uren en activiteiten":
    st.subheader("Testregistratie van afwezigheden en bijzondere opdrachten")
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

elif screen == "Weekend en maandgrenzen":
    st.subheader("Weekend- en maandgrenzen — proefregels")
    st.warning("Dit zijn configureerbare TESTREGELS, geen door De Lijn gevalideerde arbeidstijdregels. "
               "Historische weekenddagen en het startsaldo zijn handmatige testwaarden.")
    cfg = catalog.settings_with_defaults(data["settings"])
    with st.form("global_v06"):
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
        if st.form_submit_button("Algemene grenzen bewaren"):
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
        with st.form("individual_v06"):
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
            if st.form_submit_button("Individuele instellingen bewaren"):
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
    st.caption("Weekendgrenzen en historische dagtellingen tellen diensten op hun startdatum. "
               "Beschermde weekends blokkeren ook overlappende nachtdiensten.")

elif screen == "Planning":
    st.subheader("Automatisch plannen met Google OR-Tools")
    st.caption("De instellingen hieronder zijn testwaarden, GEEN gevalideerde wettelijke of sectorale minima.")
    with st.form("planner_settings"):
        col1,col2,col3 = st.columns(3)
        with col1:
            rest = st.number_input("Minimale rust tussen twee diensten (uur)", 0, 48,
                                   int(data["settings"]["min_rest_hours"]))
            max_consecutive = st.number_input("Max. opeenvolgende werkdagen", 1, 7,
                                              int(data["settings"]["max_consecutive"]))
        with col2:
            time_limit = st.number_input("Maximale rekentijd (seconden)", 1, 120,
                                         int(data["settings"]["time_limit_seconds"]))
        with col3:
            pref_weight = st.slider("Belang voorkeuren", 0, 100, int(data["settings"]["preference_weight"]))
            fair_weight = st.slider("Belang eerlijke verdeling", 0, 100, int(data["settings"]["fairness_weight"]))
        if st.form_submit_button("Instellingen opslaan"):
            state = clone()
            state["settings"].update({"min_rest_hours": rest, "max_consecutive": max_consecutive,
                                       "time_limit_seconds": time_limit, "preference_weight": pref_weight,
                                       "fairness_weight": fair_weight})
            replace_and_rerun(state)
    errors = validate_dataset(data)
    for error in errors:
        st.error(error)
    if st.button("🚀 Bereken maandplanning", type="primary", disabled=bool(errors)):
        try:
            with st.spinner("OR-Tools zoekt een zo goed mogelijke planning…"):
                st.session_state.last_plan = solve_month(data)
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
        st.markdown(f"#### Resultaat: {plan.status}")
        if plan_record:
            st.caption(f"Versie #{plan_record['id']} • {'Gepubliceerd' if plan_record['published'] else 'Concept'} • Opgesteld door {plan_record['author']}")
            if not plan_record["published"] and plan_record["revision"] == st.session_state.workspace_revision:
                if st.button("✅ Publiceer deze testplanning"):
                    try:
                        store.publish_plan(engine, plan_record["id"], st.session_state.workspace_revision, current_user["employee_id"])
                        st.success("Testplanning gepubliceerd.")
                        st.rerun()
                    except (ValueError, store.ConflictError) as error:
                        st.error(str(error))
        a,b,c = st.columns(3)
        a.metric("Benodigde plaatsen", plan.summary["required"])
        b.metric("Toegewezen plaatsen", plan.summary["assigned"])
        c.metric("Openstaande plaatsen", plan.summary["open"] if plan.summary["open"] is not None else "Onbekend")
        if plan.summary.get("seconds") is not None:
            st.caption(f"Rekentijd: {plan.summary['seconds']} seconden | Solver: {plan.summary['solver']}")
        if plan.assignments or plan.open_positions:
            t1,t2,t3 = st.tabs(["Ingeplande diensten", "Openstaande plaatsen", "Urenoverzicht (test)"])
            with t1:
                assignments = pd.DataFrame(plan.assignments)
                st.dataframe(assignments, use_container_width=True, hide_index=True, height=440)
            with t2:
                st.dataframe(pd.DataFrame(plan.open_positions), use_container_width=True, hide_index=True)
                if plan.open_positions:
                    st.info("Probeer de bezetting, beschikbare medewerkers, inzetbaarheidsbeperkingen en rusttijden te controleren. Het model schendt geen ingestelde harde regels.")
            with t3:
                st.dataframe(pd.DataFrame(hours_overview(data["employees"], plan.assignments,
                                       data.get("hour_credits", []),
                                       catalog.settings_with_defaults(data["settings"])["use_opening_balance"])),
                             hide_index=True, use_container_width=True)
                st.caption("Proefberekening van urensaldi; geen officiële urenverrekening.")
            st.markdown("#### Dienstverdeling en weekendwerk (test)")
            st.dataframe(pd.DataFrame(service_overview(data["employees"], plan.assignments)),
                         hide_index=True, use_container_width=True)
            st.download_button("⬇️ Planning downloaden als Excel", data=plan_excel(plan, data),
                               file_name=f"controleursplanning_{data['year']}_{data['month']:02d}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        elif plan.summary["open"] is None:
            st.error("Er is binnen de rekentijd geen bruikbare oplossing gevonden. Probeer de rekentijd te verlengen.")


elif screen == "Mijn voorkeuren":
    st.subheader("Mijn persoonlijke voorkeuren")
    eid = current_user["employee_id"]
    if not any(e["id"] == eid for e in data["employees"]):
        st.error("Je account is nog niet gekoppeld aan een fictieve controleur.")
    else:
        render_preferences(eid, "own")

elif screen == "Mijn planning":
    st.subheader("Mijn gepubliceerde maandplanning")
    published = store.load_plan(engine, data["year"], data["month"], published_only=True)
    if not published:
        st.info("Er is nog geen testplanning voor deze maand gepubliceerd.")
    else:
        eid = current_user["employee_id"]
        own = [a for a in published["payload"]["assignments"] if a["Personeelsnr"] == eid]
        st.caption(f"Gepubliceerde testversie #{published['id']} • {data['month']:02d}/{data['year']}")
        st.dataframe(pd.DataFrame(own, columns=["Datum", "Dienstnummer", "Categorie", "Begin", "Einde", "Beginlocatie", "Eindlocatie", "Uren"]),
                     hide_index=True, use_container_width=True)
        if not own:
            st.info("Voor deze maand zijn nog geen diensten aan jouw testaccount toegewezen.")

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
