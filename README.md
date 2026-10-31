# Controleursplanning v0.8 — zelfstandige en tijdelijk vrijgestelde taken

**Testproject met fictieve gegevens.** Dit bouwt voort op v0.7, met behoud van accounts, PostgreSQL-opslag, bestaande voorkeuren, diensten en OR-Tools-planningslogica. Geen gevalideerde productieapplicatie voor De Lijn.

## Nieuwe mogelijkheden

In **Taken > Taken per datum** zijn nu drie planningsvormen beschikbaar:

| Planningsvorm | Gedrag |
|---|---|
| **Binnen dienst — telt mee in bezetting** | Gedrag van v0.7. Taak binnen de uren van een gewone dienst; controleur blijft meetellen voor de reguliere bezetting. |
| **Binnen dienst — tijdelijke vrijstelling** | Tijdens het taakblok telt de controleur *niet* mee voor de reguliere bezetting. De solver kan extra medewerkers op dezelfde dienst toewijzen om het vereiste aantal beschikbare controleurs te behouden. Indien dat niet lukt, blijft de taak open of meldt de planning een tekort; het systeem telt niemand dubbel mee. |
| **Zelfstandige opdracht — vervangt gewone dienst** | Opdracht heeft geen dienstnummer en kan op een willekeurige datum binnen de planningsmaand worden toegevoegd. De controleur kan op die kalenderdag geen gewone dienst krijgen. De opdracht telt mee voor uren, rusttijden en de ingestelde categoriegrenzen. |

Nieuwe taken kunnen een **dienstcategorie** krijgen (Vroeg, Dag, Laat of Nacht) om zelfstandige opdrachten mee te nemen in categorie- en dienstreeksregels. Bestaande taakdefinities zonder categorie krijgen standaard *Dag*; bestaande taakbehoeften zonder planningsvorm blijven **Binnen dienst — telt mee**. Eerder gepubliceerde planningen worden niet aangepast.

De taakresultaten tonen nu ook het type (`embedded`, `released` of `standalone`). In de planning staat bij **Reguliere diensten** het aantal effectief gedekte dienstplaatsen; extra medewerkers voor tijdelijke vrijstellingen zijn afzonderlijk zichtbaar. Een zelfstandige opdracht staat in het rooster als `TAAK:<code>` en verschijnt eveneens in het taakoeverzicht, maar **telt in het urenoverzicht slechts één keer**.

## Installatie op je bestaande GitHub + Streamlit

1. Bewaar v0.7 als GitHub-tag of branch en maak **een echte databaseback-up** bij je PostgreSQL-provider.
2. Pak `controleursplanning-github-streamlit-v08.zip` uit.
3. Upload de volledige inhoud naar de **hoofdmap van dezelfde private GitHub-repository**. Vervang de oude bestanden. Vooral `app.py`, `planner.py` en `tasks_v07.py` zijn bijgewerkt; de naam `tasks_v07.py` blijft bewust behouden voor compatibiliteit.
4. Laat `DATABASE_URL`, je bestaande gebruikersaccounts en overige Streamlit Secrets ongewijzigd. Laat geen herstelcode (`ADMIN_RECOVERY_KEY`) actief staan.
5. Open de app opnieuw. Bij deze uitbreiding is **geen databasemigratie** nodig: de nieuwe velden zitten in de bestaande werkruimte.

## Drie gerichte controles met fictieve gegevens

### Test 1 — Tijdelijke vrijstelling en reservebezetting

- Zorg dat een fictieve vroege dienst op een datum **2 controleurs vereist**.
- Zorg dat **minstens 3 geschikte, beschikbare** fictieve controleurs voor deze dienst in aanmerking komen (kwalificaties en andere voorwaarden zijn belangrijk).
- Maak onder **Taken** een taakblok binnen de diensturen met de planningsvorm **Binnen dienst — tijdelijke vrijstelling**, 1 controleur en een beperkte duur (bijvoorbeeld 10:00–11:00 bij 06:00–14:00).
- Bereken opnieuw. Als alle voorwaarden dat toelaten, kan de planning 3 medewerkers op de dienst zetten: 1 voor de taak en 2 beschikbaar voor de reguliere bezetting gedurende dat uur. Het dashboard meldt dan **extra medewerkers wegens tijdelijke vrijstelling**.
- Laat daarna hoogstens 2 geschikte medewerkers beschikbaar zijn en bereken opnieuw. Het systeem mag **niet** doen alsof een vrijgestelde medewerker gelijktijdig voor de gewone bezetting beschikbaar is. De taak kan open blijven.

### Test 2 — Zelfstandige opdracht

- Maak in **Taken > Taken per datum** een taakbehoefte met de planningsvorm **Zelfstandige opdracht**, bijvoorbeeld 09:00–17:00, 1 controleur. Er is geen dienstnummer nodig.
- Bereken. De taak verschijnt in **Toegewezen taken**, en als `TAAK:<code>` in **Diensten en zelfstandige taken**.
- Controleer dat de betrokken persoon op die datum geen tweede gewone dienst heeft en dat de 8 uur slechts eenmaal meetellen in het urenoverzicht.

### Test 3 — Oude data blijven geldig

- Controleer een eerder aangemaakte taak uit v0.7 zonder nieuw `mode`-veld. Die moet blijven functioneren alsof **Binnen dienst — telt mee** geselecteerd was.
- Controleer dat alle accounts, diensten, voorkeuren en historische plannen zichtbaar blijven.

## Grenzen van deze proefversie

- Een zelfstandige opdracht bezet één volledige kalenderdag qua toewijzing, ook wanneer ze maar enkele uren duurt. Twee korte zelfstandige opdrachten op dezelfde dag voor één controleur kunnen in deze versie dus niet gecombineerd worden.
- Tijdelijke vrijstellingen worden op basis van exacte tijdsblokken beoordeeld. De gerapporteerde open plaatsen per dienst zijn het **grootste bezettingstekort op enig moment** en niet het aantal cumulatieve ontbrekende medewerkeruren.
- Geen automatische goedkeuringsstromen of afstemming met feitelijke dienstprestaties bij De Lijn; geen gevalideerde wettelijke arbeidstijd- of rustcontrole over maandgrenzen.
- Nog geen automatische verplaatsingsberekening, taakverdeling over locaties, echte loon-/urensaldoregeling, achtergrondscheduler of productiebeveiliging. Uitsluitend fictieve testgegevens gebruiken.

## Teststatus

- Python-syntax: gecontroleerd.
- **42 lokale tests geslaagd; 6 solver-testmodules overgeslagen**, omdat OR-Tools hier niet geïnstalleerd kon worden.
- De nieuwe solvertests in `tests/test_v08_solver.py` moeten nog in de daadwerkelijke Streamlit/OR-Tools-omgeving uitgevoerd worden. De code is dus niet end-to-end bevestigd.

Commandoregel in een omgeving met de geïnstalleerde vereisten:

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
```

Publiceer geen echte personeelsgegevens op gratis testhosting zonder goedkeuring en passende technische/organisatorische bescherming.
