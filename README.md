# Controleursplanning v0.2 — GitHub + Streamlit + OR-Tools

**Proefproject voor een personeelsplanning, uitsluitend met fictieve gegevens.**
Nog niet geschikt voor productiegebruik bij De Lijn, voor echte persoonsgegevens of als rechtsgeldige personeelsplanning.

## Nieuwe onderdelen in v0.2

- **Optionele gedeelde PostgreSQL-database.** Zonder `DATABASE_URL` blijft de oude lokale Streamlit-demomodus werken. Met de URL worden controleurs, diensten, vraag per datum, voorkeuren en instellingen in de database opgeslagen.
- **Personeelsnummer + wachtwoord.** Argon2-hashes, verplicht wijzigen van tijdelijk wachtwoord en tijdelijke vergrendeling na vijf mislukte aanmeldpogingen.
- **Drie vaste testrollen:** hoofdbeheerder, planner en controleur. Beheerders maken accounts handmatig aan. Controleurs zien alleen hun eigen wensen en (na publicatie) eigen diensttoewijzingen.
- **Wijzigingshistoriek en optimistische vergrendeling.** Bij gelijktijdige wijzigingen voorkomt een revisiecontrole dat data ongemerkt overschreven wordt.
- **Versies van berekende planningen in PostgreSQL.** Planners genereren een concept, publiceren die expliciet en controleurs zien alleen gepubliceerde resultaten.
- **De OR-Tools-solver uit v0.1 is ongewijzigd.** De overige uitgebreide afspraken uit het functioneel ontwerp zijn nog niet geïmplementeerd.

### Wat zit er nog niet in?

Instelbare rollen per afzonderlijke functie, goedkeuringen van personeelswijzigingen, zes volledige wenssoorten, verlof, ruilaanvragen, taakplanning, verplaatsingstijden, historische fairness, uitgewerkte planningversionering, automatische backups, onboarding/zelfservice en gevalideerde arbeids- en rustregels. Alleen de **vrijwensen** en een eenvoudige voorkeurscategorie beïnvloeden in deze versie de solver.

**Privacy:** deel geen echte namen, personeelsnummers, wachtwoorden, voorkeuren of roosters met de gratis proefapp. De fictieve testgegevens worden automatisch aangemaakt zodra je de database voor de eerste keer verbindt.

## Aan de slag in je bestaande GitHub-repository

1. **Bewaar je huidige v0.1 eerst** via GitHub (bijvoorbeeld een tag) en exporteer indien nodig je demo-JSON.
2. Pak de v0.2-ZIP uit en upload **de inhoud** naar de hoofddirectory van je bestaande privérepository. Vervang `app.py`, `requirements.txt` en `README.md`; voeg `store.py`, `tests/test_store.py` en `.streamlit/secrets.toml.example` toe. Verwijder de originele `planner.py` en `demo_data.py` niet — de bijgewerkte ZIP bevat ze ook.
3. Streamlit Community Cloud herbouwt je app vanuit GitHub. Je ziet **Controleursplanning v0.2**, maar zonder database draait de oude demomodus (zonder accounts).
4. **Voor de database-modus:** maak bij een afzonderlijke provider een *test*-PostgreSQL-database aan met een TLS-verbinding. Kies waar mogelijk een EU-datacenter, maar gebruik ook dan alleen fictieve gegevens. De gratis Community Cloud zelf kan de database niet vervangen.
5. Open Streamlit Community Cloud > je app > Settings > **Secrets**. Voeg de volgende instellingen toe (met je echte testdatabasegegevens, maar nooit naar GitHub):

   ```toml
   DATABASE_URL = "postgresql+psycopg://GEBRUIKER:URL_GECODEERD_WACHTWOORD@HOST:5432/DATABASE?sslmode=require"
   BOOTSTRAP_ADMIN_ID = "TESTADMIN"
   BOOTSTRAP_ADMIN_PASSWORD = "EEN-LANG-UNIEK-ADMIN-WACHTWOORD"
   ```

   Let op: bijzondere tekens in het *databasewachtwoord* moeten URL-gecodeerd zijn. De voorbeeldwaarden zijn geen werkende credentials. Gebruik een eigen, sterk testwachtwoord van minimaal 14 tekens.

6. Start de app opnieuw. Het systeem maakt de tabellen aan en creëert **één testbeheerder**. Meld je aan met de opgegeven ID en het eigen bootstrapwachtwoord. Je moet direct het wachtwoord wijzigen.
7. **Verwijder daarna `BOOTSTRAP_ADMIN_PASSWORD` en `BOOTSTRAP_ADMIN_ID` uit Secrets.** De beheerder staat nu (met gehasht wachtwoord) in de database.
8. Ga naar **Accounts**. Voeg voor bijvoorbeeld `DEMO001` een account aan met rol `controleur` en een nieuw tijdelijk wachtwoord. Test het in een tweede browser of privésessie. Je kunt ook een `planner`-account aanmaken.
9. Laat een controleur een vrijwens indienen. Bereken vervolgens als planner een planning en kies **Publiceer deze testplanning**. De controleur ziet dan alleen de eigen toegewezen diensten.

### Let op: bestaande demo-gegevens overzetten

De oude v0.1-Streamlit-sessiestaat migreert niet vanzelf naar PostgreSQL. De nieuwe database begint met **fictieve demo-inhoud**. Als je aangepaste fictieve v0.1-gegevens wilt bewaren: gebruik in v0.1 de knop **Bewaar demo als JSON**, en importeer het JSON-bestand in v0.2 via de sidebar met een beheerder- of planneraccount.

### Lokale installatie op Windows

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Zonder `DATABASE_URL` draait de demo. Voor een lokale databaseproef kun je de URL als omgevingsvariabele zetten, bijvoorbeeld met een eigen PostgreSQL-installatie. **Een lokale SQLite-file is niet geschikt voor persistente opslag op Streamlit Community Cloud** (het bestandssysteem kan verdwijnen). SQLite wordt in dit project uitsluitend gebruikt voor offline automatische tests.

### Testen

```bash
python -m pytest tests/test_store.py tests/test_demo_data.py
python -m pytest tests/test_planner.py
```

De planner-tests vereisen OR-Tools. Database-tests gebruiken een tijdelijke SQLite-testdatabase en geen echte persoonsgegevens.

## Veiligheidsgrenzen en beperkingen

- **Geen productiebeveiliging of security-audit.** Het is een demonstratie van aanmelding en rechten, geen goedgekeurde bedrijfsapplicatie. Ook sessiebeheer, passwordreset-procedures, multi-factor authenticatie, logging, GDPR, disaster recovery en onafhankelijke security-audit vragen nog aandacht.
- Op Streamlit Community Cloud kunnen processen in slaapstand gaan en kunnen zware OR-Tools-berekeningen uitvallen. Een aparte worker/queue is nog niet gebouwd.
- De dataset bevat nog **één actieve maand**. Bij wisselen van maand worden de demo-invoergegevens opnieuw gestart. Exporteer eerst je demo-JSON. Berekende planningversies staan wel afzonderlijk in de database.
- Publiceren is een prototypefunctie: er worden geen arbeidsrechtelijke controles buiten de bestaande proefregels uitgevoerd. Gepubliceerde testplanningen mogen niet als echte roosters worden gebruikt.
- De eigen account-ID moet overeenkomen met het `Personeelsnr` van de fictieve controleur voor toegang tot de persoonlijke planning.
- Back-ups van de database zijn nog **niet** ingericht. Dit moet bij je databaseprovider worden ingesteld en getest.
- Alle databasegeheimen horen in Streamlit Secrets, **nooit** in GitHub. `secrets.toml` en `.env` worden door `.gitignore` genegeerd.

## Bestandsstructuur

- `app.py` — Streamlit-interface, login en schermen.
- `store.py` — SQLAlchemy databasemodellen, wachtwoordhashes, accounts, revisies, audithistoriek en planningsversies.
- `planner.py` — ongewijzigde OR-Tools CP-SAT-planningsmotor uit v0.1.
- `demo_data.py` — uitsluitend fictieve data.
- `.streamlit/secrets.toml.example` — veilig configuratiesjabloon (zonder echte geheimen).
- `tests/` — model- en databasetests.
