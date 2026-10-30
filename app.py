"""Controleursplanning: interactieve, uitsluitend fictieve proefversie."""
from __future__ import annotations

import io
import json
from datetime import date

import pandas as pd
import streamlit as st

from demo_data import CATEGORIES, WEEKDAYS, build_demo, next_month
from planner import solve_month, validate_dataset

st.set_page_config(page_title="Controleursplanning | Proefversie", page_icon="📅", layout="wide")


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


if "project_data" not in st.session_state:
    st.session_state.project_data = build_demo()

data = st.session_state.project_data

st.title("📅 Controleursplanning")
st.caption("De Lijn — zelfstandig demonstratieproject • GitHub + Streamlit + Google OR-Tools")
st.warning("**TESTVERSIE — uitsluitend fictieve gegevens.** Geen gebruikerslogin, geen gedeelde database en geen gevalideerde arbeidsregels. Vul hier geen echte personeelsgegevens in.")

with st.sidebar:
    st.header("Proefproject")
    st.write(f"Planningsmaand: **{data['month']:02d}/{data['year']}**")
    st.caption("Wijzigingen blijven alleen in deze Streamlit-sessie bestaan. Herstarten kan alles wissen.")
    st.download_button("⬇️ Bewaar demo als JSON", data=json.dumps(data, ensure_ascii=False, indent=2),
                       file_name="controleursplanning-demo.json", mime="application/json", use_container_width=True)
    upload_state = st.file_uploader("Eerder bewaarde demo laden", type=["json"], key="json_upload")
    if st.button("JSON importeren", disabled=upload_state is None, use_container_width=True):
        try:
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
    st.caption("Dit project is niet gekoppeld aan systemen van De Lijn.")

screen = st.radio("Onderdeel", ["Overzicht", "Controleurs", "Diensten", "Maandbehoefte", "Voorkeuren", "Planning"],
                  horizontal=True, label_visibility="collapsed")

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
    st.markdown("""**Wat is in deze eerste versie al echt mogelijk?**

- Fictieve controleurs toevoegen en inzetbaarheidsbeperkingen wijzigen.
- Dienstnummers met vaste uren, categorie en benodigde bezetting beheren.
- Per datum de dienstbehoefte invoeren of vanuit Excel importeren.
- Gewenste vrije dagen en voorkeurscategorieën registreren.
- Met OR-Tools een maandplanning berekenen, rekening houdend met beschikbare basisregels.
- Een gedeeltelijke planning met openstaande dienstplaatsen tonen en naar Excel exporteren.

**Nog niet gebouwd:** echte accounts, gedeelde database, publicatie, ruilaanvragen, taakbeheer, goedkeuringsstromen, wettelijke validatie, gescheiden teams, periode-overstijgende controles en back-upbeheer. Deze onderdelen volgen in latere versies.""")

elif screen == "Controleurs":
    st.subheader("Controleurs beheren")
    st.dataframe(pd.DataFrame([{"Personeelsnr": e["id"], "Naam": e["name"], "Regime %": e["contract_percent"],
                                 "Max. uren/maand": e["max_month_hours"], "Niet toegestaan": ", ".join(e["blocked_categories"]),
                                 "Voorkeur": e["preferred_category"], "Actief": e.get("active", True)}
                                for e in data["employees"]]), use_container_width=True, hide_index=True)
    tab_add, tab_edit = st.tabs(["Controleur toevoegen", "Profiel aanpassen"])
    with tab_add:
        with st.form("create_emp"):
            id_ = st.text_input("Uniek testpersoneelsnummer", placeholder="DEMO017")
            name = st.text_input("Naam", placeholder="Testcontroleur 17")
            col1, col2 = st.columns(2)
            with col1:
                contract = st.number_input("Arbeidsregime (%)", 1, 100, 100, key="new_contract")
            with col2:
                max_hours = st.number_input("Max. uren per maand", 1, 250, 176, key="new_max_hours")
            if st.form_submit_button("Toevoegen"):
                if not id_.strip() or not name.strip():
                    st.error("Vul een personeelsnummer en naam in.")
                elif any(e["id"] == id_.strip() for e in data["employees"]):
                    st.error("Dit personeelsnummer bestaat al.")
                else:
                    state = clone()
                    state["employees"].append({"id": id_.strip(), "name": name.strip(), "contract_percent": contract,
                                                "max_month_hours": int(max_hours), "max_consecutive": None,
                                                "blocked_categories": [], "blocked_shifts": [], "blocked_weekdays": [],
                                                "preferred_category": "Geen", "active": True})
                    replace_and_rerun(state)
    with tab_edit:
        if data["employees"]:
            selected_id = st.selectbox("Controleur", [e["id"] for e in data["employees"]],
                                       format_func=lambda i: next(e["name"] for e in data["employees"] if e["id"] == i))
            emp = next(e for e in data["employees"] if e["id"] == selected_id)
            with st.form("edit_emp"):
                name = st.text_input("Naam", value=emp["name"])
                col1, col2 = st.columns(2)
                with col1:
                    contract = st.number_input("Arbeidsregime (%)", 1, 100, int(emp["contract_percent"]))
                    max_hours = st.number_input("Max. uren per maand", 1, 250, int(emp["max_month_hours"]))
                    preferred = st.selectbox("Zachte voorkeurscategorie", ["Geen", *CATEGORIES],
                                             index=["Geen", *CATEGORIES].index(emp.get("preferred_category", "Geen")))
                with col2:
                    blocked_cats = st.multiselect("Verboden categorieën", CATEGORIES, default=emp.get("blocked_categories", []))
                    blocked_shift = st.multiselect("Verboden dienstnummers", [s["id"] for s in data["shifts"]],
                                                   default=[x for x in emp.get("blocked_shifts", []) if x in {s["id"] for s in data["shifts"]}])
                    weekdays = st.multiselect("Niet inzetbaar op", list(range(7)),
                                              default=emp.get("blocked_weekdays", []), format_func=lambda x: WEEKDAYS[x])
                limit = st.number_input("Individueel maximum opeenvolgende werkdagen (0 = algemeen)", 0, 7,
                                        int(emp.get("max_consecutive") or 0))
                active = st.checkbox("Actieve controleur", value=emp.get("active", True))
                if st.form_submit_button("Profiel opslaan"):
                    state = clone()
                    target = next(e for e in state["employees"] if e["id"] == selected_id)
                    target.update({"name": name, "contract_percent": contract, "max_month_hours": int(max_hours),
                                   "preferred_category": preferred, "blocked_categories": blocked_cats,
                                   "blocked_shifts": blocked_shift, "blocked_weekdays": weekdays,
                                   "max_consecutive": limit or None, "active": active})
                    replace_and_rerun(state)

elif screen == "Diensten":
    st.subheader("Dienstencatalogus")
    st.dataframe(pd.DataFrame(data["shifts"]), hide_index=True, use_container_width=True)
    st.caption("Een dienstnummer heeft vaste begin- en einduren. Een nachtdienst mag over middernacht lopen.")
    mode = st.radio("Bewerking", ["Bestaande dienst wijzigen", "Dienst toevoegen"], horizontal=True)
    selected = st.selectbox("Dienstnummer", [s["id"] for s in data["shifts"]]) if mode.startswith("Bestaande") and data["shifts"] else None
    sh = next((s for s in data["shifts"] if s["id"] == selected), None)
    with st.form("shift_form"):
        code = st.text_input("Dienstnummer", value=sh["id"] if sh else "", disabled=bool(sh))
        name = st.text_input("Omschrijving", value=sh["name"] if sh else "")
        cat = st.selectbox("Categorie", CATEGORIES, index=CATEGORIES.index(sh["category"]) if sh else 0)
        col1, col2, col3 = st.columns(3)
        with col1:
            start = st.text_input("Beginuur (UU:MM)", value=sh["start"] if sh else "08:00")
        with col2:
            end = st.text_input("Einduur (UU:MM)", value=sh["end"] if sh else "16:00")
        with col3:
            required = st.number_input("Standaard bezetting", 0, 50, int(sh["required"]) if sh else 1)
        location = st.text_input("Locatie", value=sh["location"] if sh else "Demo Gent")
        active = st.checkbox("Actief", value=sh.get("active", True) if sh else True)
        if st.form_submit_button("Dienst opslaan"):
            import re
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", end):
                st.error("Gebruik voor begin- en einduur het formaat UU:MM.")
            elif not code.strip() or not name.strip():
                st.error("Dienstnummer en omschrijving zijn verplicht.")
            elif not sh and any(s["id"] == code.strip() for s in data["shifts"]):
                st.error("Dit dienstnummer bestaat al.")
            else:
                state = clone()
                entry = {"id": code.strip(), "name": name.strip(), "category": cat, "start": start,
                         "end": end, "required": int(required), "location": location, "active": active}
                if sh:
                    state["shifts"] = [entry if s["id"] == selected else s for s in state["shifts"]]
                    for req in state["demand"]:
                        if req["shift_id"] == selected:
                            req["required"] = int(required)
                else:
                    state["shifts"].append(entry)
                replace_and_rerun(state)

elif screen == "Maandbehoefte":
    st.subheader("Welke dienstnummers zijn op welke dagen nodig?")
    month_start = date(int(data["year"]), int(data["month"]), 1)
    coly, colm = st.columns(2)
    with st.form("month_form"):
        with coly:
            year = st.number_input("Jaar", 2025, 2040, int(data["year"]))
        with colm:
            month = st.selectbox("Maand", range(1, 13), index=int(data["month"])-1)
        if st.form_submit_button("Andere maand starten (wist huidige maandbehoefte)"):
            if (year, month) != (data["year"], data["month"]):
                replace_and_rerun(build_demo(int(year), int(month)))
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
        except Exception as exc:
            st.error(f"De berekening kon niet worden uitgevoerd: {exc}")
    if "last_plan" in st.session_state:
        plan = st.session_state.last_plan
        st.markdown(f"#### Resultaat: {plan.status}")
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
