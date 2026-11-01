# Controleursplanning v0.30 — indieningsperiodes en maxima voor voorkeuren

Versie 0.30 bouwt voort op de geteste **v0.29**. De voorkeurenmodule heeft nu **maandgebonden indieningsperiodes** en **maxima per voorkeurtype**. Er is geen nieuw databaseschema nodig. Rustspreiding, weekendrotatie, maandregimes, de OR-Tools-planningsmotor, verlofprocedures en eerder gepubliceerde planningen blijven intact.

## Nieuwe functies

- **Planners/beheerders:** ga naar **Voorkeuren → Indieningsperiode en maximumwensen (v0.30)**. Stel voor de actieve planningsmaand een begin- en einddatum in. De begin- en einddatum tellen mee; de applicatie gebruikt de **Belgische kalenderdatum** om het venster automatisch te openen of te sluiten.
- **Maximumwensen:** stel per controleur een afzonderlijk maximum in voor gewenste vrije dagen, dagelijkse concrete dienstnummers en de overige voorkeurtypes. **0 = onbeperkt**. 'Geen voorkeur' telt niet als wens. De limieten gelden voor de **totale maand**, niet per week.
- **Controleurs:** zien bij **Mijn voorkeuren** de indieningsperiode, de eventuele maxima en hoeveel wensen ze al gebruikten. Buiten de periode kunnen ze de voorkeuren nog bekijken maar niet opslaan.
- **Planners:** kunnen uitzonderingen namens een controleur invoeren, ook buiten de termijn of boven een ingestelde limiet. Dit is bewust een beheerdersbevoegdheid; de auditlog registreert de wijziging. Een wens blijft altijd een *zachte* voorkeur, geen gegarandeerde dienst en geen goedgekeurd verlof.
- **Bestaande maanden:** zonder ingestelde regels blijven wensen **onbeperkt open**. De beheerder moet zelf expliciet de periode en maxima activeren. Nieuwe maanden starten eveneens zonder beperkingen.
- **Gerichte opslag:** wijzigingen aan één controleurs voorkeuren worden opgeslagen zonder oudere bezettingsafwijkingen of activiteiten te veranderen. De bestaande volledige datasetvalidatie blijft wel gelden wanneer je een nieuwe planning wilt berekenen.

## Installatie

1. Bewaar de werkende v0.29 op GitHub en maak een PostgreSQL-back-up.
2. Pak `controleursplanning-github-streamlit-v030.zip` uit en upload de **volledige mapinhoud**, mét `.github/workflows` en `tests/`, naar de hoofdmap van de bestaande repository.
3. Zorg dat **`preferences_v030.py`** naast `app.py`, `store.py` en `portal_v016.py` staat. Vervang de bijgewerkte `app.py` en `store.py`.
4. Klik op **Commit changes**. Heropen Streamlit. Databaseverbinding, Secrets en bestaande planningen blijven behouden. Er is **geen databasemigratie**.
5. Kijk bij **GitHub → Actions** of de recente testworkflow groen is; alleen daar kunnen de OR-Tools-tests worden uitgevoerd.

## Korte test

1. Maak in een fictieve maand een indieningsperiode die **vandaag** omvat. Stel bijvoorbeeld maximaal **2 'liefst vrij'** en maximaal **3 concrete dienstwensen** in.
2. Log in als fictieve controleur. Vul twee vrijwensen in verschillende weken in: beide moeten bewaard blijven. Probeer daarna een derde: die moet met een duidelijke melding geweigerd worden. Een gewone dienstwens telt niet mee bij het maximum voor vrijwensen.
3. Sluit de indieningsperiode als planner (bijvoorbeeld einddatum gisteren). De controleur kan niets meer opslaan; de planner kan nog wel een uitzonderingswijziging doen.
4. Controleer of de andere maand zijn eigen voorkeuren en instellingen behoudt. De gepubliceerde planning verandert niet automatisch; na wijzigingen moet een concept opnieuw worden berekend en gepubliceerd.
5. Controleer GitHub Actions en probeer eventueel een extra voorkeur op te slaan in een oude maand met afwijkende activiteiten: die activiteiten mogen niet veranderen.

## Beperkingen en veiligheid

De indieningsperiode wordt bij **opslaan aan de serverzijde** gecontroleerd; er is geen achtergrondproces nodig om ze te openen/sluiten. De maxima zijn per voorkeurtype, niet gewogen naar prioriteit. Historisch reeds geregistreerde wensen worden **niet automatisch verwijderd** wanneer je het maximum verlaagt; de nieuwe limiet geldt bij een volgende controleurswijziging. Planners kunnen bewust uitzonderingen blijven bewaren. Eerdere op maat gemaakte voorkeuren blijven ondersteund.

Dit project is een **proefomgeving uitsluitend met fictieve gegevens**, nog niet gevalideerd voor echte personeelsgegevens of formele arbeidsregels.

**Lokale testreeks: 316 geslaagd, 14 overgeslagen (OR-Tools niet lokaal geïnstalleerd).** De GitHub Actions-tests en de nieuwe Streamlit-schermen moeten op jouw omgeving nog bevestigd worden.

---

## Eerdere versies en volledige technische handleiding

# Controleursplanning v0.29 — individuele rustspreiding per zeven dagen

Deze versie bouwt voort op de door de gebruiker geteste **v0.28**. Nieuwe functie: een optionele persoonlijke *harde* grens voor het minimum aantal vrije dagen in elk voortschrijdend tijdvak van zeven kalenderdagen. De bestaande weekendrotatie, maandregimes, verlofprocedures, taken, handmatige roosterbewerking en publicatie blijven behouden.

## Werking

Open als beheerder of planner **Weekend en maandgrenzen → Individueel weekend- en maandprofiel → Individuele rustspreiding (v0.29)**. Kies een controleur en stel *Uitgeschakeld*, *1*, *2* of *3* vrije dagen per zeven dagen in. **Standaard: uitgeschakeld**. Bij 2 betekent dit: maximaal 5 werkdagen in ieder overlappend 7-dagenvenster; de twee vrije dagen hoeven niet opeenvolgend te zijn.

Een dag telt als *gewerkt* wanneer een reguliere dienst of zelfstandige taak op die kalenderdatum **begint**. Een op vrijdag begonnen nachtdienst die zaterdag eindigt telt daarom voor deze proefregel als vrijdag. Dat is **niet** automatisch een volwaardige dagelijkse of wekelijkse rustperiode. De overige bestaande regels over feitelijke rusturen blijven daarnaast gelden.

Bij een volledig venster binnen de planningsmaand controleert CP-SAT de regel altijd. Een venster dat de maandgrens overschrijdt telt **uitsluitend wanneer de direct aangrenzende maand een gepubliceerde planning heeft**. Dat geldt ook als het aangrenzende gepubliceerde rooster geen diensten bevat. Ontbrekende publicaties worden nooit stilzwijgend als vrije dagen beschouwd. De onafhankelijke roostercontrole v0.25 controleert dezelfde vensters na berekening.

## Installatie — volledige versie

1. Bewaar de werkende GitHub-versie **v0.28** en maak een **PostgreSQL-back-up**.
2. Pak `controleursplanning-github-streamlit-v029.zip` uit en upload alle bestanden **met hun mapstructuur** naar de bestaande GitHub-repository. Vervang zeker `app.py`, `planner.py`, `catalog.py`, `store.py` en `validator_v025.py`. Voeg het **nieuwe bestand `rest_v029.py`** toe in de hoofdmap.
3. Plaats `tests/test_v029_rest_distribution.py` en `tests/test_v029_solver.py` in de map `tests/`; controleer ook de bestaande `.github/workflows/tests.yml`.
4. Klik op **Commit changes**. De Streamlit-app wordt opnieuw geladen. **Geen nieuwe tabellen of migratie**; Streamlit Secrets en database-URL blijven ongewijzigd.
5. Controleer de **recentste GitHub Actions-uitvoering**. De solvertests moeten daar met OR-Tools slagen; een groene uitvoering bewijst alleen dat de bestaande geautomatiseerde tests slagen, niet dat alle sectorregels volledig zijn gevalideerd.

## Testscenario

- Kies fictieve controleur A, zet het maximum opeenvolgende werkdagen tijdelijk op 7 en de minimumvrije dagen op **2**.
- Zet fictieve behoeften op zeven opeenvolgende kalenderdagen. Die controleur mag daar volgens deze proefregel **hoogstens vijf** diensten krijgen; twee vrije dagen mogen gespreid liggen.
- Test als gepubliceerde voorgaande maand diensten van **27 t/m 31 oktober**. Controleur A mag dan **1 november** niet werken als dat de regel voor zeven dagen zou doorbreken.
- Zet de persoonlijke minimumregeling weer op **Uitgeschakeld**; de eerdere beperkingen blijven onafhankelijk actief.
- Controleer dat opslaan lukt, ook als er in een andere sectie nog afwijkende oudere activiteiten staan. Zulke fouten worden **niet hersteld of verborgen** en moeten apart worden opgelost vóór herberekening.

## Veiligheid, validatie en beperkingen

De rustinstelling is een **globale persoonsregel** voor alle planningsmaanden (net als v0.28). Het wijzigen verhoogt de revisie van alle bestaande maanden, waardoor eerdere concepten opnieuw berekend moeten worden; reeds gepubliceerde planningen veranderen niet. De opslag is geïsoleerd met rolcontrole, optimistische revisiecontrole en auditlog en verandert geen diensturen, bezetting, verlofregistraties of andere gegevens.

Deze regel is **niet dezelfde** als een wettelijk voorgeschreven dagelijkse of wekelijkse rustperiode en is nog niet getoetst aan De Lijn-reglementen of CAO's. Het gebruik blijft beperkt tot **fictieve testgegevens**. Bij onbekende aangrenzende maand kan geen volledige garantie over de maandgrens gegeven worden.

**Lokale testreeks:** 307 tests geslaagd, 14 overgeslagen wegens ontbrekende OR-Tools. De nieuwe solver-integratietests zijn opgenomen voor **GitHub Actions** en moeten daar nog groen worden bevestigd. De UI moet nog in de Streamlit-omgeving getest worden.

---

## Eerdere functies en handleiding

# Controleursplanning v0.28 — weekendrotatie

Deze versie bouwt voort op de werkende **v0.27.2** en voegt één nieuwe, **optionele** harde rotatieregel toe. De bestaande solver, handmatige bewerkingen, maanduren, verlof, koppelingen en publicatie blijven aanwezig.

## Nieuwe instelling

In **Weekend en maandgrenzen → Individueel weekend- en maandprofiel → Weekendrotatie (v0.28)** kun je per controleur het maximum aantal **opeenvolgende gewerkte weekends** instellen op **1, 2, 3 of 4**. Standaard staat de regel op *Geen maximum (uit)*. Hiermee kun je bijvoorbeeld afdwingen dat een controleur hoogstens twee weekends achter elkaar werkt.

Een gewerkt weekend is een dienst (of zelfstandige taak) die op **zaterdag of zondag begint**; zaterdag én zondag van hetzelfde weekend tellen samen als één. Een op vrijdag begonnen nachtdienst telt volgens de bestaande startdatumdefinitie niet als weekenddienst voor de reekstelling. Verplicht vrije weekends blijven apart beschermd tegen overlap. Dit zijn **proefregels, geen gevalideerde De Lijn-arbeidsregels**.

De solver gebruikt voor het respecteren van de reeks de laatst **gepubliceerde planning van de onmiddellijk vorige en volgende maand**, voor zover beschikbaar. Zonder die publicatie kan de app nog geen volledige garantie over de maandgrens geven. De zelfstandige roostercontrole toetst dezelfde reeks na de berekening. Deze maximumreeks wordt opgeslagen als **globale instelling op het controleursprofiel** en geldt voor alle bestaande/nieuwe maanden. Aanpassing verhoogt alle maandrevisies, zodat eerdere concepten niet zonder herberekening gepubliceerd worden. Gepubliceerde versies blijven onveranderd.

## Installatie

1. Maak een herstelpunt van de werkende versie 0.27.2 en een **PostgreSQL-back-up**.
2. Pak `controleursplanning-github-streamlit-v028.zip` uit en upload **alle projectbestanden met hun mapstructuur** naar dezelfde GitHub-repository. Vervang zeker `app.py`, `store.py`, `planner.py`, `catalog.py`, `policy_v06.py`, `validator_v025.py` en voeg **`weekend_v028.py`** toe in dezelfde hoofdmap. Plaats beide nieuwe `test_v028_*` modules in de map `tests/`.
3. Laat de Streamlit Secrets (`DATABASE_URL` enzovoort) ongewijzigd. Er is **geen nieuwe databasetabel** vereist.
4. Controleer in GitHub Actions of `Alle tests, ook solver-integratie` slaagt. De OR-Tools-tests kunnen niet lokaal worden uitgevoerd in de ontwikkelomgeving.

## Testscenario

- Controleur A: maximum opeenvolgende gewerkte weekends = **1**.
- Voeg fictieve dienstbehoefte toe voor 7, 14 en 21 november 2026.
- De solver mag A niet in beide weekends van 7 en 14 november zetten; **7 en 21 november mogen wel**.
- Publiceer een vorige testmaand met werk op **31 oktober** en probeer A in te zetten op **7 november**. Dat moet worden voorkomen; **1 november** is hetzelfde weekend als 31 oktober en wordt niet dubbel geteld.
- Zet de instelling terug op *Geen maximum (uit)* en controleer of de overige, bestaande weekendregels blijven werken.
- Controleer dat `Weekendrotatie bewaren` ook slaagt als andere oude maandgegevens nog een bekende inconsistentie bevatten. Die overige fouten blijven zichtbaar en moeten vóór een nieuwe berekening hersteld zijn.

## Grenzen en veiligheid

De beschikbare gepubliceerde aangrenzende maanden worden meegenomen maar **niet-gepubliceerde of verder gelegen maanden** worden niet verondersteld bekend te zijn. De weekendrotatie alleen garandeert geen volledige arbeidsrechtelijke conformiteit. De instelling wordt gericht opgeslagen zonder oude verlofregistraties, diensten, bezetting of maandregimes te veranderen. Reeds gepubliceerde roosters wijzigen niet automatisch. Blijf alleen fictieve gegevens gebruiken tot alle eisen, regels, beveiliging en hosting zijn vrijgegeven.

---

## Eerdere functies en handleiding

# Controleursplanning v0.27.2 — maandregime opslaan zonder foutieve oude maandinvoer te wijzigen

**Gerichte herstelupdate voor v0.27.1.** Bij het opslaan van bijvoorbeeld 160 maximale planuren en 154 streefuren kreeg de gebruiker een groot aantal meldingen over `L301`, `V102` en een onbekende activiteit. De oorzaak was `replace_data`: die valideerde onbedoeld de **volledige** maand, hoewel alleen de urenregeling werd aangepast.

## Correctie

- De knop **Maandregime bewaren** en **Terugzetten naar standaard** gebruiken voortaan een **afzonderlijke server-side transactie** `save_month_regime_v0272` in `store.py`.
- Er mag uitsluitend één urenregime van de gekozen, bestaande controleur veranderen. **Dienstencatalogus, maandbehoefte, activiteiten, voorkeuren en goedgekeurd verlof blijven onaangeroerd**.
- De server controleert de rol van de gebruiker, de bestaande controleur, het toegestane aantal uren en de **maandrevisie** (bescherming tegen gelijktijdige wijzigingen). Elke geldige wijziging verhoogt de revisie en wordt geaudit; oude concepten mogen niet stilzwijgend gepubliceerd worden.
- De algemene gegevensvalidatie blijft verplicht bij het **berekenen** van een planning. Deze fix lost de achtergebleven bezettingsfouten en afwijkende activiteit **niet automatisch** op; ze verdwijnen dus ook niet ongemerkt.
- Geen nieuwe tabellen of databasewijzigingen en geen aanpassing aan Streamlit Secrets.

## Kleine update vanaf v0.27.1

1. Maak vooraf een databaseback-up en bewaar de huidige werkende GitHub-commit.
2. Vervang in de hoofdmap van je repository **`app.py` en `store.py`** door de bestanden uit de update.
3. Voeg voor de automatische controles **`tests/test_v0272_month_regime_save.py`** toe onder de bestaande map `tests/`.
4. Klik op **Commit changes**, heropen Streamlit en controleer dat GitHub Actions groen wordt.

## Functionele test

1. Kies dezelfde *niet-gepubliceerde* maand waarin de fout voorkwam, open **Urenbalans**, selecteer *Testcontroleur 01*, voer **160** maximale planuren en **154** streefuren in en klik **Maandregime bewaren**.
2. Herlaad de pagina. Beide waarden moeten behouden blijven en er mag **geen foutmelding over L301, V102 of activiteiten** verschijnen bij deze opslagactie.
3. Controleer dat een andere maand zijn eigen ureninstellingen behoudt. Controleer eventueel ook de knop **Persoonlijk maandregime terugzetten naar standaard**.
4. Controleer **GitHub Actions** voor de volledige OR-Tools-testreeks.

**Lokaal getest:** 290 tests geslaagd; 12 tests overgeslagen wegens ontbrekende OR-Tools. De nieuwe Streamlit-weergave en GitHub Actions moeten nog op jouw omgeving gecontroleerd worden.

**Let op:** voor het opnieuw berekenen van een maand moeten de reeds bestaande **bezettingsafwijkingen van L301 en V102** en eventuele ongeldige activiteiten nog apart hersteld worden. Gebruik deze update niet om veiligheidscontroles te omzeilen.

---

# Controleursplanning v0.27.1 — correctie Urenbalans

**Kleine herstelupdate boven op v0.27.** Het scherm **Urenbalans** kon vastlopen op oudere/fictieve controleursprofielen zonder het veld `target_month_hours`. Dat bleek direct reproduceerbaar met de bestaande demonstratiegegevens: bij het tonen van de streefuren ontstond een `KeyError`. De UI leest de waarden nu via `catalog.profile(...)`, dat ontbrekende velden in het geheugen aanvult met de bestaande standaardwaarde **0 streefuren**, zonder wijzigingen aan bestaande databaseprofielen.

**Bestaande v0.27-installatie bijwerken:** vervang uitsluitend `app.py` in de hoofdmap van je GitHub-repository en klik op **Commit changes**. In het ZIP-bestand voor de volledige installatie is ook `tests/test_v0271_legacy_hour_ui.py` toegevoegd voor regressietests. Er zijn geen nieuwe databasevelden, databasetabellen, Secrets of instellingen nodig.

**Controle:** open als beheerder **Urenbalans** bij een testmaand met `Testcontroleur 01`; beide invoervelden (*Maximum planuren* en *Streefuren*) moeten verschijnen. Sla voor een fictieve controleur een geldig maandregime op en kijk of dit na herladen behouden blijft. Controleer op GitHub **Actions** of de volledige testworkflow groen is.

**Lokaal uitgevoerd:** 285 tests geslaagd, 12 OR-Tools-gerelateerde tests overgeslagen omdat die bibliotheek in de lokale omgeving ontbreekt. Deze correctie is nog niet op jouw Streamlit-app getest.

---

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
