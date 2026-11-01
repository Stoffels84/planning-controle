# Controleursplanning v0.23.1 — opgeschoonde handmatige roosterbewerking

## Update vanuit v0.23

Deze kleine onderhoudsupdate verwijdert het verouderde uitklapmenu **Diensten vastzetten en overige heroptimaliseren (v0.22) — oude methode** uit **Planning**. Er is nu nog slechts één bediening: **Handmatige roosterbewerking (v0.23)**. Daarmee blijven meerdere diensten toevoegen, vervangen, verwijderen en behouden, met één gecontroleerde heroptimalisatie, beschikbaar.

Het bestand `locks_v022.py` blijft **verplicht**: de nieuwe editor en OR-Tools-planner gebruiken de onderliggende controle- en vergelijkingsfuncties. Ook de historische gegevens van eerdere heroptimalisaties blijven leesbaar. Dit pakket wijzigt **geen** database, planning, personeel of Streamlit Secrets.

**Installatie:** bewaar een herstelpunt van v0.23 en maak een databaseback-up. Pak het volledige ZIP-pakket uit en vervang in je GitHub-repository bij voorkeur **alle bestanden**, of uitsluitend `app.py` als je al exact v0.23 gebruikt. Upload geen `__pycache__` of lokale Secrets. Commit en herlaad Streamlit.

**Test:** open Planning met een berekende maand. Alleen **Handmatige roosterbewerking (v0.23)** mag verschijnen; het oude uitklapmenu niet. Test vervolgens een bestaande toewijzing behouden/vervangen en het maken van een nieuw concept. Controleer dat publicaties niet worden overschreven.

---

## Bestaande functionaliteit uit v0.23

> **Proefversie met uitsluitend fictieve gegevens.** Niet geschikt voor echte personeelsgegevens of operationele planningsbeslissingen zonder aparte veiligheids-, privacy- en arbeidsrechtelijke validatie.

## Nieuw in versie 0.23

Onder **Planning → ✏️ Handmatige roosterbewerking (v0.23)** kun je een lijst met wijzigingen maken **voordat** je de planner één keer laat herberekenen.

| Bewerking | Wat gebeurt er? |
|---|---|
| **Dienst toevoegen** | Kies datum en dienstnummer uit de actuele maandbehoefte en wijs een actieve controleur toe. Die nieuwe toewijzing moet behouden blijven in het nieuwe concept. |
| **Dienst vervangen** | Kies een bestaande toewijzing en een andere controleur. De oude combinatie wordt verboden; de nieuwe wordt verplicht. |
| **Dienst verwijderen** | Verwijder de bestaande combinatie van controleur, datum en dienst. Die combinatie mag niet automatisch terugkomen. **De dienstplaats blijft wel bestaan** en kan dus aan iemand anders worden toegewezen. |
| **Bestaande dienst behouden** | Verplicht dat een bestaande toewijzing in de nieuwe planning blijft staan. |

Je kunt **maximaal 150 wijzigingen** klaarzetten. Iedere wijziging verschijnt in een overzicht en kan afzonderlijk worden verwijderd. Je kunt ook de volledige bewerkingslijst wissen.

### Behoud van bestaande diensten

Standaard staat **Behoud alle andere bestaande reguliere toewijzingen** aan. Daardoor blijven ook de diensten die je niet aanpast, vastgezet. Als een wijziging daarmee botst (bv. de nieuwe controleur werkt al op een andere dienst op dezelfde dag), kun je de conflicterende toewijzing expliciet bewerken of de optie uitzetten. **Bij uitzetten mag de solver andere diensten herschikken.**

De hele bewerkingslijst wordt **vóór het opslaan** gecontroleerd op dubbele en tegengestelde wijzigingen, geldige dienstnummers, actieve controleurs, dienstbezetting en dubbele werkdagen. Daarna past **dezelfde OR-Tools-planner** alle harde beperkingen toe, waaronder rusttijden, maxima, afwezigheden, dienstcategorieën, taakregels en de regels over aangrenzende gepubliceerde maanden. Er is **geen manier om via handmatig wijzigen een harde regel te omzeilen**.

Bij succes wordt het resultaat als **nieuwe conceptplanning** opgeslagen, nooit over de vorige versie of publicatie heen. Publiceren vergt een aparte bevestiging van de planner. Als de planning niet haalbaar is, blijft de vorige versie ongewijzigd. Ook wanneer een andere planner intussen een nieuwere planversie heeft opgeslagen, weigert de toepassing het resultaat op de verouderde versie te baseren.

**Belangrijke beperkingen:**

- Alleen reguliere diensten uit de maandbehoefte kunnen handmatig worden bewerkt. Zelfstandige taken worden door de solver toegewezen.
- **Verwijderen** betekent *dezelfde controleur niet opnieuw op deze dienst*. Het betekent niet *de dienstplaats bewust onbezet laten* en het verwijdert het dienstnummer niet uit de maandbehoefte.
- De wachtrij met nog niet opgeslagen wijzigingen bestaat alleen in de huidige Streamlit-sessie. Vernieuw de browser niet voordat je klaar bent, want niet-toegepaste wijzigingen kunnen verloren gaan.
- Behoud je alle bestaande diensten, dan kan de herberekening onhaalbaar worden. Zet de behoud-optie uit indien een grotere herschikking nodig is; controleer de verschillen daarna zorgvuldig.
- Het oude v0.22-**bedieningspaneel** is verwijderd in v0.23.1. De interne hulpfuncties blijven in gebruik voor de nieuwe editor.
- Er wordt geen volledige handmatige vrije roostereditor gebruikt die arbeidsregels buiten de solver om kan wijzigen. Het definitieve rooster ontstaat steeds door een gecontroleerde herberekening.

## Installeren op je bestaande GitHub- en Streamlit-app

1. Maak een **back-up van de PostgreSQL-database** en bewaar de werkende GitHub-commit van **v0.23** als herstelpunt.
2. Pak `controleursplanning-github-streamlit-v0231.zip` uit.
3. Upload de **volledige inhoud** naar de root van je bestaande private GitHub-repository; overschrijf de bestanden uit de vorige versie. Voeg zeker het nieuwe bestand `manual_v023.py` toe. Ook `app.py`, `planner.py`, `store.py` en de tests zijn gewijzigd.
4. Commit de wijziging en open de bestaande Streamlit Community Cloud-app opnieuw.
5. **Laat je bestaande PostgreSQL-database, `DATABASE_URL` en andere Streamlit Secrets ongewijzigd.** Er zijn geen nieuwe tabellen of migraties nodig.

## Testen in jouw Streamlit-app

Test uitsluitend met fictieve controleurs en diensten.

1. Meld je aan als beheerder of planner; open een bestaande maand met een berekende planning. Kies **Planning → Handmatige roosterbewerking (v0.23)**.
2. **Vervangen:** kies een bestaande toewijzing, daarna een andere controleur en druk **Zet bewerking op de lijst**.
3. **Toevoegen:** kies een datum/dienstnummer uit de maandbehoefte en een controleur. Zet ook deze bewerking klaar.
4. **Verwijderen:** kies nog een oorspronkelijke toewijzing en zet de verwijdering klaar. Je moet nu drie wijzigingen in het overzicht zien.
5. Controleer of je een afzonderlijke wijziging weer van de lijst kunt verwijderen en opnieuw kunt toevoegen.
6. Laat **Behoud alle andere bestaande reguliere toewijzingen** ingeschakeld. Als de lijst een tegenstrijdigheid toont, corrigeer die. Je kunt voor een minder beperkte herberekening de behoud-optie uitzetten.
7. Bevestig en klik **Controleer wijzigingen en maak nieuw concept**. Controleer dat alle vereiste toewijzingen behouden zijn, verboden oude combinaties niet terugkomen en andere diensten de harde regels respecteren.
8. Controleer in **Publicatiebeheer** dat de bestaande gepubliceerde versie nog steeds intact is. Pas na een aparte bevestiging mag de nieuwe conceptversie gepubliceerd worden.
9. Controleer dat **het oude v0.22-onderdeel niet meer zichtbaar is**. Controleer dat **Bestaande dienst behouden** in de v0.23-editor nog werkt.
10. Test een onmogelijke combinatie, bijvoorbeeld twee vastgezette diensten op één dag voor dezelfde persoon; de app moet weigeren **zonder nieuwe versie te bewaren**.

## Automatische tests

```bash
pip install -r requirements.txt
pytest -q
```

Bij het samenstellen van **v0.23.1: 206 tests geslaagd; 11 tests overgeslagen**, omdat OR-Tools in de pakketomgeving niet beschikbaar is. De nieuwe integratietests voor `excluded_assignments` staan in `tests/test_v023_solver.py`; ze moeten nog uitgevoerd worden in de geïnstalleerde Streamlit-omgeving met OR-Tools. De nieuwe schermen zijn nog niet interactief in Streamlit getest.

## Versie en compatibiliteit

- Gebaseerd op de volledige **v0.23-broncode**; geen nieuw database- of Secrets-vereiste.
- Wijzigingen ten opzichte van v0.23: alleen `app.py`, `README.md` en regressietests. `planner.py`, `store.py`, `manual_v023.py` en `locks_v022.py` zijn ongewijzigd gebleven.
- Bestaande functionaliteit blijft behouden: maandwerkruimtes, maandbehoefte kopiëren, voorkeuren, verlof en gedeeltelijke intrekking, ruilen, taken, meldingen, publicatiebeheer, rapportage, diagnoses en Excel-export.
