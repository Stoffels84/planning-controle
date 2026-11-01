# Controleursplanning v0.24 — roostercontrole voor beheerders

> **Proefversie — uitsluitend fictieve gegevens.** Niet geschikt voor echte persoonsgegevens of operationele inzet voordat de beveiliging, privacy en arbeidsregels afzonderlijk zijn gevalideerd.

## Wat is nieuw?

Voor beheerders en planners is er een nieuw onderdeel **Roostercontrole**. Dit is een **alleen-lezen** weergave van een bestaande, opgeslagen planning: de bestaande handmatige roosterbewerking uit versie 0.23 blijft ongewijzigd en is nog steeds te vinden onder **Planning**.

- Bekijk **de nieuwste bewaarde planversie** (concept of publicatie) of kies expliciet **de laatst gepubliceerde planning**.
- Bekijk een **weekmatrix of volledige maandmatrix** met controleurs in de rijen en datums in de kolommen. De standaardselectie is de eerste week waarin dienstbehoefte voorkomt.
- Filter op **team**, actieve controleurs en één of meerdere specifieke controleurs. **Uren tonen** kan afzonderlijk worden ingeschakeld.
- Reguliere diensten tonen het **dienstnummer**; bijzondere taken worden met **Taak** aangeduid. Verschillende werkzaamheden op één dag blijven zichtbaar. Een zelfstandige taak wordt niet dubbel getoond wanneer deze in meerdere solverlijsten staat.
- Bekijk **bezetting per dag**: benodigde plaatsen, reguliere invulling, openstaande plaatsen en extra inzet.
- Download de geselecteerde matrix en de bezettingscijfers naar **Excel** (tabbladen `Roostermatrix` en `Bezetting`). Geïmporteerde namen en codes worden tegen Excel-formule-injectie beschermd.
- Bij een oudere, niet meer actuele planversie verschijnt een waarschuwing. De bezettingscijfers gebruiken de huidige maandbehoefte en zijn in die situatie slechts indicatief.

**Let op:** de bezettingstabel blijft een overzicht van **alle controleurs**, ook als de roostermatrix op één team of persoon gefilterd is. Zo is het totaal niet misleidend afhankelijk van een filter. Een streepje (`—`) betekent **geen opdracht toegewezen**, niet noodzakelijk goedgekeurd verlof of een rustdag.

## Installatie vanaf v0.23.1

1. Maak een back-up van de PostgreSQL-database en bewaar je werkende GitHub-commit van v0.23.1 als herstelpunt.
2. Download `controleursplanning-github-streamlit-v024.zip` en pak het uit.
3. Upload alle projectbestanden naar de root van je bestaande **private GitHub-repository**. Wanneer je rechtstreeks van **exact v0.23.1** updatet, volstaan de bijgewerkte `app.py` en het nieuwe `roster_v024.py` (plus eventueel README/tests).
4. Commit en heropen de bestaande Streamlit-app. **Wijzig niets** aan `DATABASE_URL`, accounts, Secrets of je bestaande database.
5. Upload geen `__pycache__`, `.pytest_cache` of lokale secrets. Er is geen migratie of nieuw databasetabel nodig.

## Online testen met fictieve gegevens

1. Open als **beheerder of planner** een maand waarvoor al een conceptplanning of publicatie bestaat.
2. Klik **Roostercontrole**. Selecteer de nieuwste planversie. Controleer of elke controleur de juiste dienstnummers per dag heeft.
3. Filter op een specifiek **team** en daarna op één **controleur**. De roosterregels moeten veranderen, maar het **bezettingsoverzicht** niet.
4. Verander tussen weekweergave en volledige maand en activeer **Uren tonen**.
5. Kies **Laatste gepubliceerde planning** om die te vergelijken met het laatste concept. Nieuwe conceptwijzigingen mogen de gepubliceerde weergave niet veranderen.
6. Download de Excel-export en controleer `Roostermatrix` en `Bezetting`.
7. Open **Planning → Handmatige roosterbewerking (v0.23)**. Bewerk een fictieve dienst en maak een nieuw concept. Controleer in **Roostercontrole** hoe het concept afwijkt van de gepubliceerde versie.
8. Meld je als controleur aan. Het nieuwe tabblad **Roostercontrole** mag niet beschikbaar zijn. Controleurs gebruiken hun bestaande eigen portaal.

## Techniek en grenzen

- **Nieuwe module:** `roster_v024.py` met functies `month_days`, `week_windows`, `roster_grid`, `staffing_grid` en `workbook_bytes`.
- **Aanpassing:** `app.py` krijgt een extra beheerdersonderdeel en het bijgewerkte versienummer.
- **Geen wijzigingen** in `planner.py`, `store.py`, de solver, regels, database, autorisatiemodel of bestaande aanvragen.
- Roostercontrole ondersteunt oude planningsrecords met ontbrekende optionele velden. Onbekende, niet langer in de personeelscatalogus aanwezige medewerkers worden niet zomaar als extra controleur weergegeven.
- De matrix is **niet bewerkbaar** en vormt **geen formele toets van arbeidstijdregels**. Voor wijzigingen blijf je de bestaande solvergestuurde handmatige editor gebruiken.
- Bij afwijkende invoergegevens kunnen bezettingscijfers niet overeenkomen met de historische planningssamenvatting. De applicatie geeft daar een verouderingswaarschuwing voor.

## Tests

```bash
pip install -r requirements.txt
pytest -q
```

Bij het samenstellen: **218 geslaagd, 11 overgeslagen**. De overgeslagen modules bevatten integratietests die OR-Tools vereisen; de volledige onlinetest van de Streamlit-interface en solver gebeurt in jouw proefomgeving. De nieuwe tests staan in `tests/test_v024_roster.py`.

## Bestaande functionaliteiten

Alle functies uit v0.23.1 blijven bestaan: aparte maandwerkruimtes, kopiëren van maandbehoefte, personeels- en dienstencatalogus, dienstwensen, aanvragen en intrekkingen, taken, dienstwissels, meldingen, weekend-/maandgrenscontroles, planning en heroptimalisatie, handmatige roosterbewerking, publicaties, diagnoserapporten en Excel-export. De oude dubbele v0.22-bediening blijft verwijderd.
