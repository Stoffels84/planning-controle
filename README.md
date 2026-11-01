# Controleursplanning v0.27 — maandgebonden arbeidsregimes en indicatieve urenbalans

**TESTVERSIE — uitsluitend fictieve gegevens.** Dit is geen officiële uren-, loon-, overuren- of CAO-verrekening. Werkelijke rust- en arbeidsregels zijn niet extern gevalideerd. De resultaten mogen niet voor operationele personeelsbeslissingen worden gebruikt.

## Wat is toegevoegd?

1. **Nieuw beheerderscherm `Urenbalans`**. Per controleur kun je het **maximaal aantal planuren** en de **streefuren van de geselecteerde maand** instellen, onafhankelijk van andere maanden. Deze twee waarden vormen een maandgebonden uitzondering op het bestaande controleursprofiel. Een streefwaarde van nul schakelt de saldoformule voor die persoon uit.
2. **Indicatieve saldo-overdracht** op basis van uitsluitend de *laatst gepubliceerde* planningen van maximaal twaalf **aaneengesloten** vorige maanden. Het rapport telt reguliere toewijzingen, zelfstandige taakdiensten (eenmalig) en geregistreerde testuren. Conceptplanningen tellen niet mee.
3. **Berekening (in Planning)**: selecteer optioneel **'Automatisch indicatief startsaldo uit gepubliceerde vorige maanden meenemen (v0.27)'**. Dit gebruikt de berekende saldi uitsluitend voor de reeds bestaande **zachte urenstreefdoelen**; het introduceert geen extra harde werkurenverplichting.
4. **Bescherming bij wijzigingen**: bij een automatisch gebruikt historisch saldo worden de oorspronkelijke gepubliceerde plan-ID's en maandrevisies vastgelegd. Als een historische bron intussen verandert, wordt een verouderde berekening geweigerd en moet je opnieuw optimaliseren.
5. **Veiligheid**: maandregimes zijn server-side gevalideerd en enkel door een beheerder/planner te wijzigen. Het gedeelde controleursprofiel, eerdere maandregimes, bestaande gepubliceerde planningen, verlofaanvragen en de dienstcatalogus worden niet stilzwijgend aangepast.

## Berekeningswijze en beperkingen

`Eindsaldo (test) = Startsaldo + gepubliceerde planuren + geregistreerde testuren - maandstreefuren`.

- Het **eerste startsaldo** van een aaneengesloten historische reeks komt uit de **handmatig ingestelde `opening_hour_balance`** bij het profiel. Dat is het *beginpunt van een simulatie*, geen officieel geverifieerd saldo. Het wordt **één keer** gebruikt, niet in elke volgende maand opnieuw.
- De maand **direct vóór de geselecteerde maand moet gepubliceerd zijn**. Ontbreekt de vorige maand, of is een gepubliceerde bron verouderd tegenover de gewijzigde maandinvoer, dan berekent de app **geen** automatisch startsaldo.
- Voor een controleur die in een bronmaand ontbreekt of geen positieve streefuren heeft, is diens automatische startsaldo **niet beschikbaar**; de overige controleurs kunnen wel een saldo hebben.
- Maandstreefuren hoeven niet gelijk te zijn aan het contractpercentage; de gebruiker voert ze expliciet in. De app berekent **geen** wettelijke contract- of overurennormen en voert **geen automatische loonberekening** uit.
- Gegevens van maanden vóór v0.27 kunnen oude, niet per maand vastgelegde personeelsprofielen hebben. De app bewaakt revisies, maar een correcte historische basis moet nog steeds door een beheerder geverifieerd worden.
- Na uitgeschakelde automatische saldo-overdracht blijft de oude handmatige testbalans-functionaliteit beschikbaar; de bestaande planningsregels blijven gelden.

## Voorbeeld met fictieve gegevens

- November: streefuren 160, automatisch gepubliceerde planuren 152, geregistreerde testuren 8, startsaldo 0 → **eindsaldo 0 uur**.
- December: streefuren 160, startsaldo uit november 0, ingeplande uren bijvoorbeeld 148 en geregistreerde uren 8 → **projectie -4 uur**. Pas na publicatie van december kan deze als historische bron voor januari dienen.

## Installeren op GitHub/Streamlit

1. Maak een **PostgreSQL-back-up** en bewaar een werkende GitHub-commit van v0.26.4.
2. Upload **alle bestanden** uit het ZIP-bestand naar de *hoofdmap* van dezelfde repository. Vervang `app.py`, `store.py`, `months_v012.py` en voeg `hours_v027.py` toe, plus `tests/test_v027_hours.py` binnen de map `tests/`.
3. Controleer dat `activity_move_v0263.py` en `shift_edit_v0262.py` in de hoofdmap staan: die waren bij eerdere updates een aandachtspunt.
4. Gebruik dezelfde Streamlit Secrets (`DATABASE_URL` enzovoort). Er zijn **geen nieuwe databasetabellen of migraties** nodig.
5. Ga naar **GitHub Actions** en controleer de nieuwe testuitvoering. De OR-Tools-testmodules moeten daar ook slagen.

## Functionele test

1. Selecteer een niet-gepubliceerde testmaand. Open `Urenbalans`, kies een fictieve controleur, stel voor die maand een maximum van 160 uur en een streefwaarde van bijvoorbeeld 152 uur in en sla op.
2. Selecteer een andere maand en controleer of haar regime **niet is veranderd**.
3. Voor een betrouwbare saldo-overdracht: stel de streefuren van een eerdere testmaand **vóór publicatie** in, bereken/publiceer die maand en selecteer vervolgens de daaropvolgende maand.
4. Open het scherm `Urenbalans` in de volgende maand; controleer of de juiste gepubliceerde versie en de saldoformule verschijnen.
5. Open `Planning`, schakel de automatische testbalans expliciet in en bereken een concept. De gepubliceerde planning blijft ongewijzigd totdat je bewust publiceert.
6. Wijzig daarna de vorige maand: een eerder berekend concept dat die historische bron gebruikte, mag **niet zonder herberekening** gepubliceerd worden.

## Tests

- Lokaal: `python -m pytest -q -ra tests`.
- GitHub: de bestaande `.github/workflows/tests.yml` voert ook tests met OR-Tools uit. **De solver kan in onze lokale omgeving niet worden uitgevoerd**, dus pas de GitHub-testresultaten geven zekerheid over de volledige testreeks.

De volgende fase voor echte arbeidsregimes omvat expliciete referentieperioden, formele contracturen, afspraken over verrekening en officiële validatie. Deze versie biedt een goed controleerbare **testurenbalans**, niet de volledige formele administratie.
