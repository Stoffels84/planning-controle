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
import store
import catalog

st.set_page_config(page_title="Controleursplanning | v0.3", page_icon="📅", layout="wide")


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


def plan_excel(plan) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(plan.assignments).to_excel(writer, index=False, sheet_name="Toewijzingen")
        pd.DataFrame(plan.open_positions).to_excel(writer, index=False, sheet_name="Open plaatsen")
        pd.DataFrame([plan.summary]).to_excel(writer, index=False, sheet_name="Samenvatting")
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
st.caption("Proefversie 0.3 • GitHub + Streamlit + Google OR-Tools")
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

screens = (["Overzicht", "Controleurs", "Diensten", "Maandbehoefte", "Voorkeuren", "Planning"]
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

**In v0.3:** uitgebreid controleurs- en dienstenbeheer met team, tijdelijke blokkeringen en begin-/eindlocatie. Sinds v0.2: aanmelden met personeelsnummer, afzonderlijke rollen, gedeelde PostgreSQL-gegevens, auditlog en conceptplanning/publicatie in testmodus. Zonder ingestelde DATABASE_URL blijft de oude demomodus beschikbaar.

**Nog niet gebouwd:** ruilaanvragen, taakbeheer, goedkeuringsstromen, wettelijke validatie, teams, controles over maandgrenzen en automatische back-ups. Deze onderdelen volgen in latere versies.""")

elif screen == "Controleurs":
    st.subheader("Controleursbeheer")
    st.caption("Profielen zijn gekoppeld aan het unieke personeelsnummer. Reeds aangemaakte profielen deactiveren we in plaats van ze te verwijderen.")
    records = [catalog.profile(e) for e in data["employees"]]
    st.dataframe(pd.DataFrame([{
        "Personeelsnr": e["id"], "Naam": e["name"], "Team": e["team"],
        "Regime %": e["contract_percent"], "Max. maanduren": e["max_month_hours"],
        "Verboden categorieën": ", ".join(e["blocked_categories"]),
        "Geblokkeerde periodes": len(e["blocked_periods"]), "Actief": e["active"]
    } for e in records]), use_container_width=True, hide_index=True)
    tab_add, tab_edit, tab_periods = st.tabs(["Nieuwe controleur", "Profiel en beperkingen", "Tijdelijke onbeschikbaarheid"])
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
                active = st.checkbox("Controleur actief", value=bool(emp["active"]))
                st.caption("Deze beperkingen zijn verplicht voor de solver. De voorkeur voor een dienstcategorie is een zachte wens.")
                if st.form_submit_button("Profiel bewaren"):
                    state = clone()
                    target = next(e for e in state["employees"] if e["id"] == selected_id)
                    target.update({"name": name.strip(), "team": team.strip(),
                                   "contract_percent": int(contract), "max_month_hours": int(max_hours),
                                   "preferred_category": preferred, "blocked_categories": blocked_cats,
                                   "blocked_shifts": blocked_shifts, "blocked_weekdays": blocked_weekdays,
                                   "max_consecutive": int(individual_limit) or None, "active": active})
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
    st.subheader("Zachte voorkeuren — gewenste vrije dagen")
    st.caption("Vrijwensen zijn GEEN goedgekeurde afwezigheden. De planner mag ervan afwijken.")
    st.dataframe(pd.DataFrame(data["preferences"]), hide_index=True, use_container_width=True)
    with st.form("add_pref"):
        a,b,c = st.columns(3)
        with a:
            eid = st.selectbox("Controleur", [e["id"] for e in data["employees"]],
                               format_func=lambda id_: next(e["name"] for e in data["employees"] if e["id"] == id_))
        with b:
            wished = st.date_input("Gewenste vrije dag", value=date(data["year"], data["month"], 1))
        with c:
            priority = st.select_slider("Prioriteit", options=[1,2,3], value=2,
                                        format_func=lambda x: {1:"Laag",2:"Normaal",3:"Hoog"}[x])
        if st.form_submit_button("Voorkeur opslaan"):
            if (wished.year, wished.month) != (data["year"], data["month"]):
                st.error("Kies een datum binnen de huidige planningsmaand.")
            else:
                state = clone()
                state["preferences"] = [p for p in state["preferences"] if (p["employee_id"], p["date"]) != (eid, wished.isoformat())]
                state["preferences"].append({"employee_id": eid, "date": wished.isoformat(), "priority": priority})
                replace_and_rerun(state)
    if data["preferences"]:
        with st.form("remove_pref"):
            idx = st.selectbox("Vrijwens verwijderen", range(len(data["preferences"])),
                               format_func=lambda x: f"{data['preferences'][x]['employee_id']} — {data['preferences'][x]['date']}")
            if st.form_submit_button("Verwijderen"):
                state = clone()
                state["preferences"].pop(idx)
                replace_and_rerun(state)
    st.info("Zes voorkeurtypes zijn in het functioneel ontwerp vastgelegd. Deze eerste versie ondersteunt gewenste vrije dagen en een voorkeurscategorie; de andere volgen later.")

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
            t1,t2 = st.tabs(["Ingeplande diensten", "Openstaande plaatsen"])
            with t1:
                assignments = pd.DataFrame(plan.assignments)
                st.dataframe(assignments, use_container_width=True, hide_index=True, height=440)
            with t2:
                st.dataframe(pd.DataFrame(plan.open_positions), use_container_width=True, hide_index=True)
                if plan.open_positions:
                    st.info("Probeer de bezetting, beschikbare medewerkers, inzetbaarheidsbeperkingen en rusttijden te controleren. Het model schendt geen ingestelde harde regels.")
            st.download_button("⬇️ Planning downloaden als Excel", data=plan_excel(plan),
                               file_name=f"controleursplanning_{data['year']}_{data['month']:02d}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        elif plan.summary["open"] is None:
            st.error("Er is binnen de rekentijd geen bruikbare oplossing gevonden. Probeer de rekentijd te verlengen.")


elif screen == "Mijn voorkeuren":
    st.subheader("Mijn voorkeuren — gewenste vrije dagen")
    st.caption("Dit zijn zachte wensen, geen goedgekeurde verlofdagen. Het systeem kan ervan afwijken.")
    eid = current_user["employee_id"]
    employee = next((e for e in data["employees"] if e["id"] == eid), None)
    if employee is None:
        st.error("Je account is nog niet gekoppeld aan een fictieve controleur. Vraag je testbeheerder om dit te controleren.")
    else:
        my_prefs = sorted([p for p in data["preferences"] if p["employee_id"] == eid], key=lambda p: p["date"])
        st.dataframe(pd.DataFrame(my_prefs, columns=["date", "priority"]), hide_index=True, use_container_width=True)
        with st.form("my_preference"):
            wished = st.date_input("Gewenste vrije dag", value=date(data["year"], data["month"], 1))
            priority = st.select_slider("Prioriteit", options=[1, 2, 3], value=2,
                                        format_func=lambda x: {1: "Laag", 2: "Normaal", 3: "Hoog"}[x])
            if st.form_submit_button("Voorkeur opslaan"):
                if (wished.year, wished.month) != (data["year"], data["month"]):
                    st.error("Kies een dag in de huidige planningsmaand.")
                else:
                    updated = clone()
                    updated["preferences"] = [p for p in updated["preferences"]
                                              if (p["employee_id"], p["date"]) != (eid, wished.isoformat())]
                    updated["preferences"].append({"employee_id": eid, "date": wished.isoformat(), "priority": int(priority)})
                    replace_and_rerun(updated)
        if my_prefs:
            target_date = st.selectbox("Vrijwens intrekken", [p["date"] for p in my_prefs])
            if st.button("Verwijder mijn voorkeur"):
                updated = clone()
                updated["preferences"] = [p for p in updated["preferences"]
                                          if (p["employee_id"], p["date"]) != (eid, target_date)]
                replace_and_rerun(updated)

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
