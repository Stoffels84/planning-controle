# Controleursplanning v0.3 — GitHub + Streamlit + OR-Tools

**UITSLUITEND PROEFVERSIE MET FICTIEVE GEGEVENS.** Niet goedgekeurd voor echte controleurs van De Lijn of operationele, arbeidsrechtelijke roosters.

Dit is een **in-place uitbreiding van v0.2.1** (met wachtwoordherstel). Je bestaande PostgreSQL-database en accounts worden behouden; er is geen nieuwe database of herstelcode nodig.

## Nieuw in v0.3

- **Controleursprofielen:** personeelnummer, naam, team/werkgebied, arbeidspercentage, maximale maanduren, actief/inactief.
- **Harde inzetbaarheidsregels per controleur:** verboden dienstcategorieën, afzonderlijke dienstnummers, weekdagen, maximaal opeenvolgende werkdagen en **tijdelijke onbeschikbare periodes**. De datumblokkeringen worden ook gehandhaafd wanneer een nachtdienst over middernacht loopt.
- **Zachte wens:** voorkeurscategorie blijft bewaard, net als bestaande voorkeuren voor vrije dagen.
- **Dienstenbeheer:** unieke dienstnummers, categorie, vaste begin-/einduren, vaste bezetting, actief/inactief, **begin- en eindlocatie**.
- **Vaste bezetting synchroniseren:** een wijziging van de standaardbezetting van een dienstnummer wordt in de **huidige actieve maandbehoefte** overgenomen.
- **Veilige controles:** ongeldige tijden, overlappende onbeschikbare periodes, onbekende dienstnummers en het deactiveren van een dienst die nog nodig is worden geweigerd.
- **OR-Tools blijft de basis:** de nieuwe onbeschikbare periodes worden effectief afgedwongen. Begin- en eindlocaties worden in de planning en Excel-export opgenomen, maar **verplaatsingstijden worden nog niet geoptimaliseerd**.

## Bijwerken vanuit je werkende v0.2.1

1. **Controleer eerst of je kunt inloggen op v0.2.1.** Verwijder eventueel de oude `ADMIN_RECOVERY_KEY` uit Streamlit Secrets als je dat nog niet gedaan had.
2. Maak op GitHub bij voorkeur een **tag of release** van je huidige werkende versie als herstelpunt. Maak daarnaast een back-up via de beheerinterface van je databaseprovider. De ZIP is geen databaseback-up.
3. Pak `controleursplanning-github-streamlit-v03.zip` uit.
4. Upload **alle bestanden en mappen uit de ZIP** naar de hoofdmap van je **bestaande private** GitHub-repository. Vervang bestaande bestanden en **voeg het nieuwe bestand `catalog.py` toe**. Verwijder `store.py`, `planner.py`, `demo_data.py`, `.streamlit/` of de map `tests/` niet.
5. Streamlit Community Cloud start doorgaans opnieuw met de nieuwe commit. Open dezelfde app als voordien.
6. **Laat `DATABASE_URL` in Streamlit Secrets exact ongewijzigd.** Je hoeft géén nieuwe Secrets of accounts aan te maken. Verander geen bestaand beheerderswachtwoord en voer geen nieuwe bootstrap-instelling in.
7. Meld je aan met je **bestaande** personeelsnummer en wachtwoord. Kijk in **Controleurs**, **Diensten**, **Maandbehoefte** en **Planning**.

### Praktische test zonder echte gegevens

1. Kies een fictieve controleur, bijvoorbeeld `DEMO001`.
2. Ga naar **Controleurs → Tijdelijke onbeschikbaarheid** en blokkeer een paar datums in de actieve maand. Let op: overlappende periodes worden geweigerd.
3. Open **Diensten**, kies een dienstnummer en wijzig de vaste bezetting of de begin-/eindlocatie.
4. Controleer in **Maandbehoefte** of de gewijzigde vaste bezetting automatisch is doorgevoerd.
5. Ga naar **Planning**, bereken opnieuw en controleer of de geblokkeerde controleur tijdens zijn afwezigheid niet is toegewezen. Bekijk ook de locatiekolommen en download de Excel-export.
6. Test met een tweede, fictief account dat een controleur enkel zijn eigen voorkeuren en gepubliceerde eigen planning kan bekijken.

## Wat gebeurt er met oude data?

De PostgreSQL-tabellen uit v0.2.1 blijven bestaan. Nieuwe profielvelden staan in de **bestaande JSON-werkruimte**. Oudere controleurs/diensten krijgen bij het *lezen* achterwaarts compatibele standaardwaarden; ze worden pas opgeslagen als je de betreffende invoer opslaat. De oude accountgegevens en wachtwoordhashes worden niet gewijzigd. Reeds bewaarde planningsversies blijven beschikbaar.

**Let op:** bij het wijzigen van een dienstdefinitie of inzetbaarheidsregel moet je **opnieuw berekenen**; oudere versies worden niet stilzwijgend herberekend. Eerdere planversies zijn historisch, niet automatisch geschikt voor opnieuw publiceren.

## Belangrijke beperkingen die we nog moeten bouwen

- Nog geen volledig individueel arbeidsregime met netto uren, urenoverdracht of vaste rustdagcycli.
- Team is voorlopig alleen een **profielveld**; geen afzonderlijke teamplanning of uitwisseling tussen teams.
- Begin- en eindlocatie zijn **informatief**; reistijden, verplaatsingstijden en dienstovergangen op maat zijn nog niet verwerkt.
- Nog geen formele aanvraag- en goedkeuringsstroom voor profielwijzigingen, ruilen, verlof, taken, nacht-/weekendrotatie of volledige historiek van eerlijkheidscores.
- Nog geen professioneel beheer van alle rollen, automatische back-ups, SSO/MFA, privacy-audit, verifieerbare compliance of herstelbeleid.
- Het actieve werkblad bevat maar **één maand tegelijk**. De knop *Andere testmaand starten* maakt nieuwe fictieve gegevens aan. Exporteer de oude demo vooraf als JSON.
- Permanente opslag is alleen actief als `DATABASE_URL` geconfigureerd is. Zonder database werkt de app in vluchtige demomodus.

**Voor de hele gratis Streamlit-app geldt:** geen echte persoonsgegevens of operationele roosterbeslissingen zonder goedkeuring van De Lijn, adequate beveiliging, hostingtoets en bevestigde arbeids- en rustregelvalidatie.

## Bestanden

| Bestand | Betekenis |
|---|---|
| `app.py` | Streamlit-interface met accounts, beheerschermen en maandplanning |
| `catalog.py` | Nieuwe achterwaarts compatibele profiel- en dienstregels |
| `planner.py` | OR-Tools-planningsmotor met harde blokkering van periodes |
| `store.py` | Bestaande PostgreSQL-datalaag, accounts en herstelcodevoorziening (ongewijzigd) |
| `demo_data.py` | Fictieve controlegegevens |
| `requirements.txt` | Benodigde bibliotheken |
| `tests/` | Tests voor database, profielregels, demo en solver |

## Lokaal testen (Windows)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
streamlit run app.py
```

Wanneer `pytest` ontbreekt: `python -m pip install pytest` (alleen voor ontwikkeltests).

In deze voorbereidingsomgeving zijn de SQLAlchemy-, account-, profiel- en migratietests uitgevoerd. De solver/UI zijn op syntaxis gecontroleerd, maar een live OR-Tools-run is hier niet mogelijk omdat `ortools` en `streamlit` niet geïnstalleerd kunnen worden. Een complete end-to-endtest moet daarom plaatsvinden op jouw Streamlit-omgeving.
