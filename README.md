# Controleursplanning — v0.4 (uitsluitend fictieve proefgegevens)

GitHub + Streamlit Community Cloud + Google OR-Tools + PostgreSQL. **Dit is geen gevalideerde personeelsplanningsapp voor De Lijn.** Alleen fictieve testmedewerkers en fictieve planningen gebruiken.

## Nieuw in versie 0.4

Deze versie bouwt voort op je werkende **v0.3** en behoudt de bestaande accounts, wachtwoordherstel, PostgreSQL-opslag, dienstenbeheer, voorkeuren en OR-Tools-motor.

### 1. Planningsregels (nieuw tabblad)

- **Maximum opeenvolgende diensten per categorie** instellen: Vroeg, Dag, Laat en Nacht (0 = geen extra categoriegrens).
- **Extra minimale rust per dienstovergang** instellen, bijvoorbeeld `Laat>Vroeg = 14 uur`. De strengste van algemene, individuele en overgangsrust geldt.
- **Verboden overgangen** instellen, bijvoorbeeld `Nacht>Dag`, voor twee opeenvolgende kalenderdagen. Deze zijn aanvullend op de tijdsgebonden rustcontroles.
- **Weging voor zachte streefuren** instellen (0 = uitgeschakeld). Bezetting blijft voorrang krijgen.

### 2. Controleurs > Profiel en beperkingen (uitgebreid)

- **Persoonlijke minimale rust** (0 = algemene regel, kan wettelijke/sectorale minima niet verlagen).
- **Persoonlijk maximum per categorie** (0 = algemene regel, indien ingesteld geldt de strengste grens).
- **Persoonlijk verboden dienstovergangen**.
- **Streefuren voor de actieve maand** (0 = geen streefdoel). Deze zijn een *zachte optimalisatiewens*; `Maximum in te plannen maanduren` blijft een harde bovengrens. Een arbeidsregime in procenten wordt nog niet automatisch naar maanduren omgerekend.

### 3. Solver

Google OR-Tools respecteert bovenstaande extra harde regels. De motor probeert optioneel de afwijking van individueel ingegeven maandstreefuren te verkleinen, maar **mag deze streefuren niet boven bezetting of harde arbeidsvoorwaarden stellen**. Een gedeeltelijke planning blijft mogelijk.

## Installatie: upgrade van v0.3 naar v0.4

1. Maak **eerst een GitHub-tag/release** van je huidige werkende versie en een afzonderlijke databaseback-up bij je databaseprovider. Een ZIP met code is **geen** back-up van PostgreSQL.
2. Download en pak het bestand `controleursplanning-github-streamlit-v04.zip` uit.
3. Open je bestaande **private** GitHub-repository `controleursplanning` en upload de bestanden uit de ZIP naar de **hoofdmap**. Vervang bestaande bestanden. De hoofdmap moet onder andere `app.py`, `catalog.py`, `planner.py`, `store.py`, `demo_data.py` en `requirements.txt` bevatten. Neem ook de map `tests/` mee.
4. Laat je bestaande **Streamlit Secrets onveranderd**, vooral `DATABASE_URL`. **Maak geen nieuwe database of accounts aan.** Verwijder de `ADMIN_RECOVERY_KEY` uit Secrets als deze nog aanwezig is na je eerdere wachtwoordherstel.
5. Open de app na de automatische heruitrol opnieuw en meld je aan met je bestaande beheerdersaccount.
6. Klik op het nieuwe tabblad **Planningsregels** en probeer eerst één fictieve regel uit.

**Geen database-migratie vereist:** nieuwe regels worden opgeslagen in de bestaande JSON-werkruimte in PostgreSQL. Oude medewerkers en dienstrecords krijgen alleen bij het lezen extra standaardwaarden. De bestaande accountwachtwoorden en planningsversies worden niet gewijzigd.

## Test het resultaat met fictieve gegevens

1. Maak een GitHub-herstelpunt en databaseback-up voordat je wijzigingen invoert.
2. Open **Planningsregels**. Zet `Max. Nacht` op `2`, sla op en bereken de planning opnieuw.
3. Open **Controleurs > Profiel en beperkingen**, kies `DEMO001`, zet de persoonlijke minimale rust op `12 uur` en `Max. Nacht` op `1`. Sla op en bereken opnieuw.
4. Controleer dat niemand meer dan twee nachtdiensten op **opeenvolgende kalenderdagen** krijgt en de gekozen controleur maximaal één. Het kan wel dat een controleur meerdere nachtdiensten in dezelfde maand uitvoert, zolang die niet direct opeenvolgen.
5. Test vervolgens bij **Planningsregels** extra rust `Laat>Vroeg = 14` en eventueel een verboden overgang `Nacht>Dag`. Bekijk of de planning verandert, rekening houdend met andere beperkingen en beschikbare controleurs.
6. Stel bij een fictieve medewerker `Streefuren` in en zet in Planningsregels de streefurenweging op bijvoorbeeld `1`. De totale benodigde bezetting krijgt altijd voorrang.
7. Controleer in de planningsresultaten de openstaande plaatsen. Als door de extra voorwaarden niet alles kan worden ingevuld, moeten die zichtbaar blijven; de harde regels mogen niet worden overtreden.

## Wat betekent 'opeenvolgend' in v0.4?

- **Maximum categorie-reeks:** achtereenvolgende **kalenderdagen** waarop iemand diensten uit *dezelfde* categorie heeft. Een dag zonder dienst van die categorie doorbreekt de reeks.
- **Verboden overgang:** twee toegekende diensten waarvan de geplande **begindatums** op opeenvolgende kalenderdagen liggen. Een tussengelegen vrije dag doorbreekt deze specifieke verbodsregel.
- **Minimale rust:** wordt op echte begin- en eindtijdstippen berekend, ook over middernacht; is niet beperkt tot één kalenderdag.
- **Eén dienst per kalenderdag:** blijft een aparte harde regel.

## Belangrijke grenzen van dit prototype

- Er is **nog geen koppeling met vorige/volgende maand** voor rust, cycli en doorlopende dienstreeksen. Een reeks die over een maandgrens loopt kan daardoor onjuist worden beoordeeld.
- Nog **geen** automatische uurverrekening van verlof, opleiding, ziekte, feestdagen of tijdssaldi. Maandstreefuren zijn slechts een zachte doelwaarde, geen juridisch correct te presteren uurrooster.
- Individuele maxima/minima per **totale hoeveelheid categorie-diensten per maand** en volledige weekendregels ontbreken nog.
- De concrete wettelijk/sectorale arbeids- en rustregels zijn **niet gevalideerd**. De waarden in de proefomgeving zijn illustratief.
- Nog geen operationeel goedgekeurde privacy-/beveiligingsinrichting, automatische externe back-ups of uitvoerige autorisatie per team; geen echte personeelsgegevens of echte roosters invoeren.
- Nog geen permanent draaiende achtergrondworker voor langlopende optimalisaties op gratis Streamlit-hosting.

## Bestandsoverzicht

| Bestand | Doel |
|---|---|
| `app.py` | Streamlit-interface, tabblad Planningsregels en uitgebreide controleurprofielen |
| `catalog.py` | Validatie en achterwaarts compatibele standaardwaarden |
| `planner.py` | OR-Tools-model en nieuwe harde/zachte planningsregels |
| `store.py` | Bestaande PostgreSQL-datalaag, accounts en audits (ongewijzigd) |
| `demo_data.py` | Uitsluitend fictieve voorbeeldgegevens |
| `tests/` | Database-, validatie-, integratie- en solvertests |

## Lokaal testen (Windows)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
streamlit run app.py
```

In de huidige ontwikkelomgeving zijn **18 tests geslaagd**. Twee testmodules met CP-SAT zijn **overgeslagen**, omdat OR-Tools hier niet is geïnstalleerd. De code is op Python-syntaxis gecontroleerd; de volledige Streamlit- en solverwerking moet nog op jouw geïnstalleerde omgeving worden getest. De eerdere v0.3-versie is daarom je terugvaloptie.
