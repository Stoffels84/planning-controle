# Controleursplanning — v0.5 (proefproject, fictieve gegevens)

Streamlit + GitHub + Google OR-Tools + PostgreSQL. **Geen productietoepassing.** Gebruik alleen fictieve medewerkers en fictieve planningen; de arbeidstijdregels zijn niet juridisch/sectoraal gevalideerd.

## Nieuwe onderdelen ten opzichte van werkende v0.4

### 1. Individuele rustdagen (Controleurs → Rustdagenregeling)
- Per controleur instelbaar: **Automatisch / Vast / Combinatie**.
- Bij **Vast** en **Combinatie** kunnen weekdagen en afzonderlijke datums als **verplicht vrij** worden aangeduid.
- Een dienst die een vaste rustdag ook maar gedeeltelijk overlapt (bv. een nachtdienst van de vorige dag) wordt geweigerd.
- **Automatisch** legt geen nieuwe vaste rustdagen op; OR-Tools laat dagen vrij die niet met een dienst worden gevuld.
- **Beperking:** de modi Vast en Combinatie behandelen **opgegeven rustdagen** als verplicht, maar vormen nog **geen volledige persoonlijke werk-/rustcyclus**. Het model garandeert niet dat alle niet-geblokkeerde dagen werkdagen worden. Arbeidsregimes blijven voorlopig gebaseerd op maxima en zachte maandstreefuren.

### 2. Zes soorten persoonlijke voorkeuren (Voorkeuren / Mijn voorkeuren)
1. Gewenste vrije dag (datum)
2. Gewenste werkdag (datum)
3. Voorkeur / vermijden van dienstcategorie (maandbreed)
4. Voorkeur / vermijden van dienstnummer (maandbreed)
5. Elke week een bepaalde weekdag liefst vrij
6. Liever geen bepaalde overgang tussen categorieën op opeenvolgende startdatums

Iedere wens heeft prioriteit **1–3** en is altijd *zacht*. Dekking en harde regels blijven vooropstaan. Controleurs kunnen uitsluitend hun eigen voorkeuren opslaan; planners beheren alle voorkeuren. Oudere vrije-dagwensen uit v0.4 blijven geldig.

**Beperkingen:** voorkeuren zijn momenteel niet beperkt door configureerbare maandmaxima of indienperiodes; exacte wensweging is een proefscore. De in v0.4 ingestelde algemene voorkeurscategorie per medewerker blijft bestaan en wordt ook meegewogen. De zes voorkeurtypes zijn niet hetzelfde als goedgekeurd verlof.

### 3. Testregistratie van uren en activiteiten (Uren en activiteiten)
- Beheerder/planner kan per kalenderdag voor een fictieve controleur **Verlof, Ziekte, Opleiding, Feestdag, Bijzondere opdracht, Andere** registreren, met meegetelde uren (0–16).
- Eén registratie per medewerker per datum. Elke geregistreerde dag blokkeert **de volledige kalenderdag** voor reguliere diensten, ook bij een overlappende nachtdienst.
- **Urenoverzicht** bij het tabblad Uren en activiteiten én bij een berekende planning: geplande diensturen + afzonderlijk meegetelde uren + afwijking t.o.v. zachte maandstreefuren.
- Excel-export van de planning bevat een extra tabblad **Urenoverzicht**.
- De zachte streefurenoptimalisatie houdt rekening met de geregistreerde uren.

**Belangrijk:** dit is **geen** officiële berekening van contracturen, betaalde ziekte, feestdagen, verlofrechten, overuren of overdraagbare urensaldi. De opgegeven uren zijn handmatige testwaarden; ook korte opdrachten blokkeren in deze versie de hele dag. `Max. maanduren` blijft een bovengrens voor **ingeplande diensten**, los van de geregistreerde credits.

## Upgraden van v0.4 naar v0.5

1. **Bewaar eerst een GitHub-tag/herstelpunt van v0.4** en maak bij je databaseprovider een **echte PostgreSQL-back-up**. Een ZIP-back-up van alleen de code is geen databaseback-up.
2. Pak `controleursplanning-github-streamlit-v05.zip` uit. Upload de **inhoud** naar de hoofdmap van je bestaande **private** GitHub-repository en vervang bestaande bestanden. **Voeg het nieuwe `extras.py` toe.** Neem ook `tests/` mee.
3. Laat alle bestaande **Streamlit Secrets**, inclusief `DATABASE_URL`, ongewijzigd. `ADMIN_RECOVERY_KEY` hoort verwijderd te zijn na het eerdere account-herstel.
4. Wacht op de gewone automatische heruitrol van Streamlit en meld je aan met je bestaande account. **Geen nieuwe database, geen migratie en geen accountreset vereist.** Nieuwe veldwaarden worden in dezelfde JSON-werkruimte opgeslagen; oude documenten behouden hun bestaande structuur totdat je iets wijzigt.
5. Gebruik alleen fictieve voorbeelden voor deze testversie.

### Testscenario A: verplichte rustdag

- Open **Controleurs → Rustdagenregeling**.
- Kies `DEMO001`, selecteer **Combinatie** en voeg een rustdatum toe die in de actieve maand een benodigde dienst bevat. Sla op.
- Bereken de maandplanning opnieuw. Controleer dat deze controleur op die kalenderdag **niet** ingepland is, ook niet met een nachtdienst die tot in die dag loopt.

### Testscenario B: de zes voorkeurtypes

- Maak via **Voorkeuren** zes verschillende zachte wensen voor een fictieve controleur; klik bij elk op **Voorkeur opslaan**.
- Controleer of de wensen onder het gekozen personeelsnummer verschijnen.
- Bereken opnieuw. Wensen mogen worden afgewezen als bezetting of harde rustregels dat vereisen; de solver beslist over het beste compromis.

### Testscenario C: urenoverzicht

- Registreer bij **Uren en activiteiten** een fictieve opleidingsdag met `7,6` uur.
- Controleer dat er geen reguliere dienst op die dag wordt toegekend en dat de uren in het overzicht verschijnen.
- Download de planning als Excel en open het tabblad **Urenoverzicht**.

## Bestanden

| Bestand | Wat doet het? |
|---|---|
| `app.py` | Streamlit-schermen, rollen, voorkeuren, rustdagen en urenoverzicht |
| `extras.py` | Nieuwe voorkeurtypes, rustdag/activiteitstoetsen, urenoptelling |
| `catalog.py` | Personeelsprofielen, achterwaarts compatibele defaults, validaties |
| `planner.py` | OR-Tools-toewijzing en nieuwe zachte/harde optimalisatieregels |
| `store.py` | Bestaande PostgreSQL-accounts en opslag (ongewijzigd) |
| `demo_data.py` | Fictieve testgegevens |
| `tests/` | Database-, validatie- en integratietests |

## Teststatus

- Syntaxcontrole met `python -m compileall`: **geslaagd**.
- `pytest`: **23 tests geslaagd, 3 modules overgeslagen**. OR-Tools was in de uitvoeromgeving niet geïnstalleerd en installatie via het pakketnetwerk was niet mogelijk. De nieuwe CP-SAT-integratietests moeten dus **op je Streamlit-omgeving of lokaal met de packages geïnstalleerd** uitgevoerd worden.
- De Streamlit-interface zelf is hier niet live gestart. Versioneer en test de update voor je verdergaat.

### Lokaal testen (Windows)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
streamlit run app.py
```

## Nog niet gebouwd

Volledige vaste werk-/rustcycli, maandgrenscontrole, officiële wettelijke uren- en saldoverrekening, verplaatsingstijden, bijzondere taakplanning, ruilaanvragen, automatische voorkeurdeadlines/maxima, betrouwbare achtergrondworkers, automatisch externe back-ups en bedrijfsbrede beveiligingsvalidatie. **Gebruik geen echte personeelsgegevens.**
