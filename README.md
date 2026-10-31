# Controleursplanning v0.7 — weekendhistoriek en taakplanning (proefversie)

Dit is een **voortzetting van de werkende v0.6.2**, met behoud van inloggen, wachtwoordherstel, bestaande database, voorkeuren, maandgrenzen en OR-Tools. Alleen **fictieve gegevens** gebruiken. Geen gevalideerde productieapplicatie voor De Lijn.

## Wat is nieuw?

1. **Historische weekendspreiding:** onder **Planning** kan de beheerder ervoor kiezen om weekenddagen uit de **gepubliceerde** planningen van de vorige 1–12 kalendermaanden te gebruiken. Een conceptversie telt niet mee. Als een maand meerdere gepubliceerde versies heeft, telt alleen de laatst gepubliceerde versie. Historische gegevens worden **uitsluitend voor de berekening geladen**; de eerder handmatig ingevulde historie in het personeelsprofiel wordt niet overschreven. Een dienst op zaterdag en zondag telt als twee weekenddagen en één gewerkt weekend (startdatum is bepalend). Dit is een **eenvoudige** historische eerlijkheidsmaat, niet gecorrigeerd voor alle mogelijke dienst- en arbeidsregimes of tijd in dienst.
2. **Taken binnen bestaande diensten:** maak taken aan via het nieuwe tabblad **Taken**, eventueel met een verplichte bevoegdheid (kwalificatiecode). Leg vast op welke dag, bij welk dienstnummer, binnen welke uren en met hoeveel medewerkers een taak moet worden uitgevoerd. In **Controleurs > Profiel en beperkingen** kun je bevoegdheden en geblokkeerde taken beheren.
3. **Automatische taaktoewijzing met OR-Tools:** een taak kan alleen worden toegewezen aan iemand die op dat dienstnummer op die datum is ingepland, de vereiste bevoegdheid heeft en niet voor die taak geblokkeerd is. Eén controleur kan geen twee overlappende taakblokken krijgen. Bij onvoldoende geschikte controleurs toont het resultaat **open taakplaatsen** in plaats van de regels te overtreden.
4. **Nieuwe Excel-tabbladen:** `Taaktoewijzingen` en `Open taken`.

**Belangrijke beperking:** deze versie ondersteunt **uitsluitend taken die binnen een bestaande dienst plaatsvinden en de controleur laten meetellen voor de oorspronkelijke dienstbezetting**. Taken die een volledige dienst vervangen, die de reguliere bezetting verminderen of los van een dienst staan, zijn **nog niet ondersteund**. De planningsmotor houdt nog geen rekening met verplaatsingstijden en officiële arbeidsregelingen. Maak voor zulke taken voorlopig géén taakblok aan, omdat dit een onjuiste bezettingsinterpretatie zou geven.

## Installeren op bestaande GitHub + Streamlit

1. Bewaar de werkende v0.6.2 als GitHub-tag of branch én maak via de PostgreSQL-provider een echte databaseback-up.
2. Pak `controleursplanning-github-streamlit-v07.zip` uit. Upload **alle bestanden en mappen** naar de hoofdmap van je bestaande **private** GitHub-repository. Vervang oude bestanden; verwijder niet je andere eigen bestanden.
3. Nieuwe modules die zeker mee moeten: `history_v07.py` en `tasks_v07.py`. `app.py`, `planner.py`, `catalog.py` en `store.py` zijn ook gewijzigd. `requirements.txt` blijft gelijk.
4. Streamlit zal na de GitHub-commit opnieuw deployen. Laat `DATABASE_URL` en andere Secrets ongewijzigd. De oude database en accounts blijven bestaan. Er is **geen schema-migratie** nodig: taakgegevens worden in de bestaande JSON-werkruimte bewaard.
5. Log in met het bestaande beheerdersaccount. Verwijder `ADMIN_RECOVERY_KEY` uit Secrets als dat niet reeds gebeurd is. Gebruik uitsluitend verzonnen testgegevens.

## Vier eenvoudige tests

### Test 1 — taak en kwalificatie

- Open **Taken** en maak `DEMO_ACTIE` aan, met vereiste kwalificatie `TEST_KWAL`.
- Open **Controleurs > Profiel en beperkingen**, kies een fictieve controleur, en selecteer bij **Behaalde taakbevoegdheden** `TEST_KWAL`. Sla op.
- Open **Taken > Taken per datum**, kies een bestaande datum en een dienst die op die datum uitgevoerd wordt. Voeg één taakblok toe binnen de diensturen (voorbeeld: vroege dienst 06:00–14:00 → taak 10:00–11:00). Kies `DEMO_ACTIE` en `1` controleur.
- Ga naar **Planning**, klik **Bereken maandplanning**, en bekijk **Toegewezen taken** / **Open taakplaatsen**. Alleen een bevoegde én op de juiste dienst ingedeelde controleur mag de taak krijgen. Bij onvoldoende geschikte medewerkers blijft de taak open.

### Test 2 — onbevoegde medewerker

- Haal `TEST_KWAL` weg uit alle profielen en bereken opnieuw. De taak moet open blijven. Zorg dat je de wijziging hebt opgeslagen.

### Test 3 — gepubliceerde historie

- Publiceer een fictieve maandplanning, wijzig onder **Maandbehoefte** de actieve planningsmaand naar de volgende maand en bereken daar een nieuw rooster.
- Schakel bij **Planning** `Gepubliceerde weekendhistoriek automatisch meewegen` in en kies een venster van 3 maanden. Boven de knop verschijnen de gevonden oudere, gepubliceerde maanden en weekendtellingen.
- Conceptplanningen tellen niet mee. Na opnieuw publiceren van een herziene maand telt alleen die laatst gepubliceerde versie.

### Test 4 — behoud van bestaande gegevens

- Controleer dat accounts, bestaande diensten, voorkeuren en de PostgreSQL-verbinding onveranderd zijn.
- Herstel bij problemen de v0.6.2-GitHub-tag/branch. Als je al v0.7-taakvelden hebt opgeslagen, zullen ze door v0.6.2 niet worden gebruikt, maar blijven ze in de werkruimte staan.

## Technische bestanden

- `app.py`: nieuwe schermen en opties voor historische berekeningen.
- `history_v07.py`: pure historische aggregatie en berekeningskopie.
- `tasks_v07.py`: taakdefinities, tijdsblokken en validatie.
- `planner.py`: extra OR-Tools-variabelen voor taaktoewijzing en open taakplaatsen.
- `catalog.py`: kwalificaties en persoonlijke taakblokkeringen met terugwaarts compatibele standaardwaarden.
- `store.py`: read-only historische query op **gepubliceerde** planningversies.
- `tests/test_v07_history_tasks.py` en `tests/test_v07_solver.py`: regressietests.

## Teststatus en beperkingen

- Python-syntax: gecontroleerd.
- Offline: **36 tests geslaagd; 5 solvermodules overgeslagen** omdat OR-Tools in deze omgeving niet kon worden geïnstalleerd.
- **De nieuwe taaksolver is hier niet live met OR-Tools uitgevoerd.** Test de taaktoewijzing expliciet op Streamlit vóór verder gebruik.
- De proefversie ondersteunt nog geen pauzes, salarisadministratie, geldige werk-rustcycli over maandgrenzen, afzonderlijke optimalisatieworkers, goedkeuringsflows, automatische databaseback-ups of een volledige productiebeveiliging. Bedrijfsgebruik vereist toestemming, arbeidsrechtelijke validatie, beveiligingsreview en passende hosting.
