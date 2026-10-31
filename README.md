# Controleursplanning v0.20 — gedeeltelijke intrekking van goedgekeurd verlof

> **Uitsluitend fictieve testgegevens.** Dit is een prototype, geen goedgekeurde toepassing voor echte personeelsgegevens of officiële verlofrechten. De arbeidsregels en beveiliging zijn nog niet volledig juridisch/operationeel gevalideerd.

## Nieuw ten opzichte van werkende v0.19.2

Bij een goedgekeurde meerdaagse verlofaanvraag kan de controleur **één of meer specifieke dagen** laten intrekken in plaats van verplicht de volledige aanvraag te laten vervallen.

- **Controleur → Mijn verlofaanvragen:** kies de oorspronkelijke goedgekeurde aanvraag, vink de **dagen die moeten vervallen** aan en vermeld een reden. Alle nog goedgekeurde dagen zijn standaard aangevinkt; verwijder de dagen die je juist wilt behouden. Tot een beheerder beslist, blijft de volledige goedgekeurde verlofblokkering ongewijzigd.
- **Beheerder/planner → Verlofaanvragen beheren:** ziet exact welke dagen de controleur wil intrekken; kan goedkeuren of weigeren. Alleen de gekozen datumregels verdwijnen uit de maandbehoefte/afwezigheidsregistratie bij goedkeuring.
- **Rechtstreeks door beheerder:** wanneer de controleur dit buiten de webapp vraagt, kunnen na verplichte bevestiging en reden eveneens **specifieke** goedgekeurde dagen worden vrijgegeven. Een bestaand openstaand verzoek moet via de goedkeuring daarvan afgehandeld worden.
- **Herhaling:** voor de overige nog goedgekeurde dagen van dezelfde oorspronkelijke aanvraag kan later opnieuw een intrekkingsverzoek ingediend worden. Zolang er ten minste één goedgekeurde dag overblijft, blijft de oorspronkelijke aanvraag de status 'goedgekeurd' houden, met in de schermen het label 'deels ingetrokken'. Pas na intrekking van alle dagen wordt de oorspronkelijke aanvraag 'ingetrokken'.
- **Historiek & rechten:** redenen, beslisser, oorspronkelijke verlofgoedkeuring, betrokken datums en persoonlijke meldingen blijven bewaard. Een controleur kan geen dagen van een collega wijzigen.
- **Veiligheid:** bestaande goedgekeurde dagen blijven beschermd tegen handmatig wissen; afwijkende datums, dubbele intrekkingen en ontbrekende urenregistraties worden geweigerd. Oude gepubliceerde roosters wijzigen niet automatisch; na goedkeuring stijgt de maandrevisie en moet een concept opnieuw berekend en gepubliceerd worden.
- **Compatibiliteit:** oude volledige intrekkingsverzoeken uit v0.18.1 blijven bruikbaar. De rapportagecorrectie uit v0.19.2 is behouden.

## Installatie / database

1. **Maak eerst een PostgreSQL-back-up** en bewaar de GitHub-commit van de werkende v0.19.2 als herstelpunt. Verwijder niets uit de database.
2. Download `controleursplanning-github-streamlit-v020.zip`. Pak uit en upload **alle bestanden** naar de root van dezelfde private GitHub-repository.
3. Commit de wijziging en laat Streamlit Community Cloud de app herstarten. Met name `store.py` en `app.py` zijn gewijzigd; het extra testbestand is `tests/test_v020_partial_leave.py`.
4. **Nieuwe tabel:** `leave_cancellation_selections`. Bij appstart wordt deze via de bestaande SQLAlchemy `create_all` automatisch aangemaakt. De tabellen `leave_requests`, `leave_cancellations`, accounts en planningsversies krijgen geen kolomwijzigingen, en bestaande records worden niet gewist. De PostgreSQL-databasegebruiker moet **CREATE TABLE**-rechten hebben.
5. Bestaande Streamlit Secrets, `DATABASE_URL`, accounts en planningsgegevens **niet aanpassen**.

Terugrollen naar v0.19.2 kan via de oude GitHub-commit; verwijder de nieuwe tabel **niet** zonder een doordacht migratieplan, anders gaat de datumselectiehistoriek verloren.

## Online testscenario

1. Maak met **fictieve accounts** een verlofaanvraag voor bijvoorbeeld **5 t/m 9 november** en laat de beheerder deze goedkeuren. Controleer dat vijf dagen geblokkeerd zijn.
2. Log in als controleur en open **Mijn verlofaanvragen**. Kies de aanvraag en selecteer uitsluitend **6 en 8 november** om in te trekken; vul een reden in. Verzenden moet een openstaand intrekkingsverzoek opleveren zonder de verlofblokkeringen aan te passen.
3. Log in als planner en keur het verzoek goed. In **Uren en activiteiten** blijven uitsluitend **5, 7 en 9 november** als verlof geregistreerd. De oorspronkelijke aanvraag moet 'Goedgekeurd (deels ingetrokken)' tonen.
4. Doe een tweede intrekkingsverzoek, bijvoorbeeld voor **7 november**. De eerder ingetrokken dagen mogen niet opnieuw selecteerbaar zijn. Na goedkeuring blijven alleen 5 en 9 november geblokkeerd.
5. Probeer een intrekking af te wijzen; de geselecteerde dagen moeten dan geblokkeerd blijven. Controleer ook de meldingen en de zichtbaarheid voor een andere fictieve controleur.
6. Controleer een reeds gepubliceerde planning: die blijft ongewijzigd, maar een oud concept mag na gewijzigde maandinvoer niet zonder herberekening opnieuw gepubliceerd worden.
7. Controleer dat **Rapportage en eerlijkheid** nog goed opent en dat de eerdere `DeltaGenerator`-weergavefout niet terugkomt.

## Teststatus en beperkingen

- **154 lokale automatische tests geslaagd**; **9 solvermodules overgeslagen** omdat OR-Tools in de lokale omgeving ontbreekt.
- De Streamlit-interface en het gebruik met een echte PostgreSQL-server zijn nog **niet online getest**; lokaal zijn SQLite-databasetests en Python-syntaxcontroles uitgevoerd.
- Dit systeem behandelt **volledige kalenderdagen**; halve verlofdagen, urenrekeningen, automatische verrekening van wettelijke verlofrechten en bedrijfsvalidatie zijn nog niet aanwezig.
- De nieuwe tabel is alleen additief; er is geen automatische verwijdering of herberekening van historische gepubliceerde roosters.

---

# Controleursplanning v0.19.2 — herstel weergavefout rapportage

> **Uitsluitend fictieve testgegevens.** Deze update corrigeert één specifieke Streamlit-weergavefout in de rapportage. Geen wijzigingen aan database, login, verlofprocedures, solver of gepubliceerde planningen.

## Waarom verscheen een grote tabel met `DeltaGenerator`?

In versie 0.19.1 stond bij de rapportagewaarschuwingen een conditionele expressie met een aanroep van `st.warning()` of `st.caption()`. Streamlit kan het geretourneerde `DeltaGenerator`-object door *magic rendering* als uitgebreide API-documentatie op het scherm tonen. Het is dus geen probleem met de PostgreSQL-database.

**Oplossing:** de enkele expressie is vervangen door normale `if`/`else`-instructies. De waarschuwing of toelichting wordt nog steeds getoond, maar het achterliggende object niet.

## Installatie boven op versie 0.19.1

1. Bewaar je huidige GitHub-commit als herstelpunt; maak uit voorzorg een back-up van je testdatabase.
2. Pak `controleursplanning-github-streamlit-v0192.zip` uit en upload alle bestanden in de hoofdmap van dezelfde private GitHub-repository. Voor deze fout volstaat technisch het vervangen van **`app.py`**.
3. Commit de wijziging en open de Streamlit-app opnieuw. **Je database, accounts, Streamlit Secrets en configuratie hoeven niet te worden gewijzigd.**
4. Kies een maand met een gepubliceerde fictieve planning, open **Rapportage en eerlijkheid** en controleer of de enorme `DeltaGenerator`-tabel verdwenen is. Controleer ook de cijfers en de Excel-export.

Als je daarna alsnog een **rode foutmelding** ziet, bekijk de Streamlit-logboeken voor `REPORT_V0191_FETCH` of `REPORT_V0191_BUILD`. Deze visuele fix lost geen eventuele afzonderlijke database-/rapportageberekeningsfouten op.

## Controle

- Extra tests: `tests/test_v0192_streamlit_magic_regression.py` bevestigt dat rapportagewaarschuwingen via normale `if`/`else`-statements lopen en dat er geen losse conditionele Streamlit-meldingsaanroepen meer voorkomen.
- Streamlit UI is hier niet online getest; de bestaande solvermodules vragen OR-Tools.

---

# Controleursplanning v0.19.1 — correctie rapportage

> **Uitsluitend fictieve testgegevens.** De exacte oorzaak van de fout op Streamlit Community Cloud kan zonder de serverlogboeken niet definitief worden bevestigd. Deze versie is een gerichte, defensieve correctie op v0.19; de planningsmotor verandert niet.

## Wat is gewijzigd?

- **Rapportage in afzonderlijke stappen:** fouten in het ophalen van gepubliceerde versies (`REPORT_V0191_FETCH`), berekenen (`REPORT_V0191_BUILD`), overzichtskaarten (`REPORT_V0191_METRICS`), individuele grafieken (`REPORT_V0191_CHART_PEOPLE` en `REPORT_V0191_CHART_CATEGORIES`) en export (`REPORT_V0191_EXCEL`) zijn apart te vinden in de Streamlit-logboeken.
- **Deelresultaten blijven staan:** een probleem bij een grafiek of Excel-export verbergt niet langer de rest van een berekend rapport.
- **Robuustere invoer:** een onleesbaar contractpercentage, ontbrekende voorkeuren of onvolledige historische records maken niet langer automatisch het volledige rapport onbruikbaar; waarschuwingen verduidelijken wat is weggelaten.
- **Eenvoudigere databasequery:** de periodecontrole gebruikt eenvoudige SQL-jaarfilters en een exacte controle per kalendermaand in Python. Alleen de nieuwste gepubliceerde versie per maand telt mee; concepten blijven uitgesloten.
- **Geen schemawijzigingen.** Database, accounts, verlofintrekkingen, berekening en publicatie blijven behouden.

## Installeren

1. Bewaar je huidige werkende GitHub-commit en maak een back-up van de PostgreSQL-testdatabase.
2. Pak `controleursplanning-github-streamlit-v0191.zip` uit.
3. Upload alle bestanden naar de root van je bestaande private GitHub-repository. Vooral `app.py`, `store.py` en `report_v019.py` zijn gewijzigd; het nieuwe testbestand is `tests/test_v0191_reporting_fix.py`.
4. Commit en laat Streamlit Community Cloud opnieuw opstarten. **De Streamlit Secrets of databasegegevens hoef je niet te wijzigen.**
5. Selecteer een maand met een gepubliceerde testplanning en open als beheerder **Rapportage en eerlijkheid**. Controleer dat de cijfers en Excel-export verschijnen.

### Als de fout toch terugkomt

Open **Manage app → Logs** in Streamlit Community Cloud. Zoek naar `REPORT_V0191_FETCH` of `REPORT_V0191_BUILD`. Stuur uitsluitend de technische foutsoort en tracebackregels mee, zonder wachtwoorden, database-URL, namen of personeelsgegevens. De foutcode vertelt nu welk onderdeel faalt.

## Tests

- **140 tests geslaagd.** Dit omvat controles voor ongeldige contractpercentages, onvolledige rapportagegegevens en een historisch venster over een jaargrens.
- **9 solvermodules overgeslagen** omdat OR-Tools hier niet geïnstalleerd is.
- Python-syntaxcontrole uitgevoerd. Het Streamlit-scherm en PostgreSQL-productiegedrag moeten nog worden bevestigd in jouw online testomgeving.

---

# Controleursplanning v0.19 — statistieken en indicatieve eerlijkheid

> **Testomgeving.** Gebruik uitsluitend fictieve personeelsgegevens. De cijfers zijn beschrijvend en vormen geen oordeel over individuele medewerkers, geschiktheid of naleving van arbeidsvoorwaarden.

## Nieuw in v0.19

De planner en beheerder vinden een nieuw onderdeel **Rapportage en eerlijkheid**.

- **Bezetting:** benodigde, toegewezen en openstaande reguliere dienstplaatsen uit de laatst gepubliceerde planningssamenvatting; bij geen benodigde plaatsen staat de bezettingsgraad op *onbekend / niet van toepassing*, niet op 100%.
- **Per controleur:** aantal diensten en zelfstandige taken, geplande uren, weekenddagen, gewerkte weekends en aantallen per dienstcategorie (Vroeg, Dag, Laat, Nacht).
- **Weekendverdeling:** indicatieve normalisatie naar 100% contract. Voorbeeld: 2 weekenddagen bij 50% contract wordt getoond als 4 per 100% contract. De *spreiding* is hoogste minus laagste genormaliseerde waarde onder actieve controleurs. Dit is geen rechtvaardigheids- of kwaliteitscijfer: beschikbaarheid, beperkingen en langdurige historische patronen tellen niet volledig mee.
- **Datumgebonden wensen:** uitsluitend specifiek gewenste vrije dagen of gewenste dienstnummers op een datum. Andere wenssoorten tellen niet mee. Er verschijnt geen respecteringspercentage bij gewijzigde invoer sinds publicatie.
- **Historiek:** selecteer 1, 2, 3, 6 of 12 maanden; per maand telt uitsluitend de laatst **gepubliceerde** versie, nooit een concept. Contractpercentages en namen komen voorlopig uit de *huidige* catalogus; wijzigingen daarvan kunnen historische vergelijkingen vertekenen.
- **Excel-export:** vijf tabbladen: Samenvatting, Per controleur, Categorieen, Maandhistoriek, Toelichting. Tekstvelden worden bij export beschermd tegen het als formule behandelen van ingevoerde tekst.

De rapportage **leest alleen**. De solver, publicaties, verlofprocedures, meldingen en bestaande tabellen zijn niet gewijzigd. Er is **geen databasemigratie** nodig.

## Installatie vanuit de werkende versie 0.18.1

1. Bewaar je huidige GitHub-commit als herstelpunt en maak een back-up van je PostgreSQL-testdatabase.
2. Pak `controleursplanning-github-streamlit-v019.zip` uit.
3. Upload de bestanden naar de hoofdmap van dezelfde private GitHub-repository. Vervang `app.py` en `store.py`, voeg het nieuwe `report_v019.py` toe. Laat alle andere bestaande bestanden uit het pakket op hun plaats staan.
4. Commit en laat Streamlit Community Cloud de app herstarten.
5. Laat `DATABASE_URL`, accounts en overige Streamlit Secrets **ongewijzigd**.

## Gerichte online test

1. Meld je als **beheerder/planner** aan, selecteer een maand met gepubliceerde testplanning en open **Rapportage en eerlijkheid**.
2. Vergelijk bezetting en planuren met het tabblad **Planning** en controleer bij een weekenddienst de teller van de betrokken fictieve controleur.
3. Kies 3 maanden in het historiekvenster. Controleer dat een nieuw concept de bestaande cijfers **niet** overschrijft; pas een nieuwe publicatie hoort de getoonde planning te wijzigen.
4. Download de Excel-export; controleer de vijf tabbladen en enkele personeelswaarden.
5. Meld je aan als fictieve **controleur**; het teamrapport hoort niet beschikbaar te zijn.
6. Wijzig als planner een fictieve voorkeur ná publicatie: het rapport blijft de oorspronkelijke gepubliceerde dienstinformatie tonen, met waarschuwing dat de huidige invoer nieuwer is en zonder verouderd wenspercentage.

## Teststatus

- **137 geautomatiseerde tests geslaagd**, waaronder 9 nieuwe rapportagetests.
- **9 OR-Tools-testmodules overgeslagen** wegens ontbrekende OR-Tools in deze ontwikkelomgeving. De solver is in v0.19 ongemoeid gelaten.
- Python-syntaxcontrole is geslaagd. De Streamlit-gebruikersinterface is nog niet op jouw hosting getest.

---

## Eerdere versies (archief)

# Controleursplanning v0.18.1 — goedgekeurd verlof gecontroleerd intrekken

> **Uitsluitend fictieve testgegevens.** Nog niet geschikt voor daadwerkelijke personeelsplanning bij De Lijn. Werkelijke arbeidsregels, beveiliging, privacy, back-ups en hosting zijn nog niet volledig gevalideerd.


## Nieuw in versie 0.18.1: intrekking van goedgekeurd verlof

In v0.18 kon een controleur enkel een **nog openstaande** verlofaanvraag intrekken. Deze versie maakt ook intrekking na goedkeuring mogelijk:

1. **Controleur vraagt intrekking aan** in **Mijn verlofaanvragen → Goedgekeurd verlof intrekken**, met een korte reden. De oorspronkelijke goedkeuring en volledige verlofblokkering blijven bestaan zolang een planner nog niet beslist heeft.
2. **Beheerder of planner** opent **Verlofaanvragen beheren → Goedgekeurd verlof intrekken** en keurt het intrekkingsverzoek goed of af. Bij afwijzing blijft het verlof van kracht.
3. Een beheerder/planner kan het goedgekeurde verlof **rechtstreeks intrekken** als de controleur daarom buiten de applicatie heeft gevraagd, mits verplichte reden en expliciete bevestiging. Deze handeling wordt geregistreerd.
4. Bij een goedgekeurde intrekking verdwijnen uitsluitend de test-**verlofblokkeringen** die aan de desbetreffende oorspronkelijke aanvraag gekoppeld zijn. De maandrevisie stijgt, zodat oude concepten niet zomaar publiceerbaar zijn.
5. **Gepubliceerde planningen worden nooit automatisch aangepast.** De beheerder moet een nieuwe planning berekenen, controleren en bewust publiceren. De controleur moet niet aannemen dat hij automatisch weer is ingepland.
6. De aanvraag, goedkeuring, intrekking, beslissing door wie, reden en meldingen blijven in de database bewaard. Controleurs zien alleen hun eigen intrekkingen.

**Beperking:** voorlopig wordt het **hele goedgekeurde verlof** ingetrokken, niet een selectie van dagen daaruit. Deelintrekking en de verwerking van officiële verlofrechten en arbeidsregels zijn nog niet ingebouwd.

### Installatie vanuit werkende versie 0.18

1. Bewaar de vorige GitHub-commit en maak eerst een **back-up** van de PostgreSQL-testdatabase.
2. Download het volledige pakket `controleursplanning-github-streamlit-v0181.zip` en upload de bestanden naar de hoofdmap van dezelfde private GitHub-repository. Vervang `store.py`, `app.py`, `requests_v010.py`, `portal_v017.py` en de README.
3. Wijzig **geen** `DATABASE_URL`, account of Streamlit Secret.
4. Bij het starten maakt SQLAlchemy automatisch **één nieuwe tabel** `leave_cancellations` aan. Bestaande tabellen blijven intact. Hiervoor heeft de databasegebruiker `CREATE TABLE`-rechten nodig.
5. Gebruik alleen fictieve accounts en proefplanning.

### Gericht testscenario

1. Vraag als fictieve controleur voor een paar dagen verlof aan en keur het goed als planner.
2. Open **Mijn verlofaanvragen**, vraag de intrekking van dit goedgekeurde verlof aan met een reden.
3. Controleer als planner in **Verlofaanvragen beheren** het verzoek. Keur het goed. Controleer dat de aanvraag nu de status **Goedgekeurd verlof ingetrokken** toont, de verlofregistraties zijn verwijderd en er een melding is.
4. Controleer dat de **reeds gepubliceerde** planning hetzelfde blijft. Bereken en publiceer een nieuwe versie als dat gewenst is.
5. Herhaal met een tweede goedgekeurde verlofaanvraag via de knop **rechtstreeks intrekken** als planner. Test ook een afgewezen verzoek en controleer dat de afwezigheid dan behouden blijft.
6. Controleer of een andere fictieve controleur geen toegang heeft tot deze intrekkingsgegevens.

### Tests v0.18.1

- **128 automatische tests geslaagd**, inclusief 12 nieuwe tests voor intrekkingen.
- **9 solver-testmodules overgeslagen** vanwege ontbrekende OR-Tools in de testomgeving.
- Python-syntaxcontrole geslaagd. De nieuwe Streamlit-schermen moeten nog in jouw hostingomgeving worden getest.

---

## Nieuw in versie 0.18

### Meldingen in de webapp

- Nieuw tabblad **Meldingen** voor planners, beheerders en controleurs.
- De linkerzijbalk toont het aantal **ongelezen meldingen**.
- Bij **eerste publicatie** van een maand krijgt ieder actief controleursaccount een melding dat zijn maandplanning beschikbaar is.
- Bij een **nieuwe publicatie** krijgen alleen controleurs van wie de diensttoewijzingen zijn veranderd een melding, inclusief het aantal gewijzigde dagen. Er worden **geen collega-roosters** meegestuurd.
- Bij **nieuwe verlofaanvragen** krijgen actieve planners en beheerders een melding; de aanvrager krijgt een melding bij goed- of afkeuring.
- Bij **ruilaanvragen** ontvangt de collega een melding; de aanvrager hoort het antwoord, planners krijgen een melding als beide controleurs akkoord zijn en beide betrokkenen krijgen de uiteindelijke beslissing.
- Meldingen worden op de server gekoppeld aan **één account**. Gebruikers kunnen alleen **hun eigen meldingen** als gelezen markeren.
- Meldingen worden **niet via e-mail, sms of push** verstuurd. Ze worden zichtbaar wanneer iemand in de webapp inlogt of een scherm opnieuw laadt.

### Zorgvuldiger publiceren

- Het tabblad **Publicatiebeheer** toont de laatste conceptversie en de laatste gepubliceerde versie van de geselecteerde maand.
- Bij **Planning → Controle vóór publicatie** verschijnen een overzicht van het aantal gewijzigde controleurs en eventuele openstaande dienstplaatsen.
- De beheerder moet een **expliciete bevestigingscheckbox** aanvinken voordat de publicatieknop actief wordt.
- Een **reeds gepubliceerde versie** kan niet nogmaals als dezelfde versie gepubliceerd worden.
- De eerdere controles op de actuele werkruimterevisie, geldige solverstatus en aangrenzende gepubliceerde maanden blijven behouden.
- Een gedeeltelijke planning kan nog steeds worden gepubliceerd als de beheerder dit uitdrukkelijk bevestigt; dit is **geen goedkeuring voor operationeel gebruik**.

### Bewuste beperking: geen automatische geplande publicatie

Het functioneel ontwerp voorziet ook publicatie op een vooraf gekozen tijdstip. Dat is **nog niet** geactiveerd. Streamlit Community Cloud kan in slaapstand gaan en heeft geen gegarandeerde scheduler. Een betrouwbare latere publicatie vereist een goedgekeurde, altijd actieve achtergrondworker of extern planningsmechanisme.

## Archief: installeren van versie 0.18 vanuit v0.17

1. Maak vooraf een **back-up van de PostgreSQL-testdatabase** en bewaar de werkende GitHub-commit van v0.17.
2. Pak `controleursplanning-github-streamlit-v018.zip` uit en upload de bestanden in de **hoofdmap** van dezelfde private GitHub-repository. Vervang bestaande bestanden, met name `app.py` en `store.py`.
3. **Laat** `DATABASE_URL`, alle andere Streamlit Secrets, de bestaande medewerkers en de database-inhoud **ongewijzigd**. Deel nooit secrets of wachtwoorden via GitHub.
4. Bij het opstarten maakt de applicatie automatisch de nieuwe tabel `inbox_notices` aan met SQLAlchemy `create_all`. Bestaande tabellen worden niet gewist of aangepast. De databasegebruiker moet wel tabellen mogen aanmaken.
5. Open de Streamlit-app, meld je aan met een fictief testaccount en controleer het nieuwe tabblad **Meldingen**.

## Aanbevolen testscenario

1. Log in als beheerder. Open **Publicatiebeheer** en bekijk het concept van een testmaand.
2. Ga naar **Planning**. Controleer het aantal open plaatsen, vink de bevestiging aan en publiceer een **nieuwe conceptversie**.
3. Log in als fictieve controleur. In **Meldingen** staat een bericht over de publicatie. Markeer het als gelezen.
4. Maak een nieuw concept dat alleen het rooster van één fictieve controleur verandert, valideer met de bestaande solver en publiceer. Alleen de betrokken controleur hoort een **roosterwijziging** te zien.
5. Vraag als controleur testverlof aan. Controleer als planner de melding en keur goed of af. Controleer vervolgens de persoonlijke beslissing in het controleursaccount.
6. Maak een test-ruilaanvraag en doorloop de akkoord- en goedkeuringsstappen. Controleer de meldingen van beide partijen.
7. Wissel tussen november en december om te controleren dat bestaande gepubliceerde maandplanningen behouden blijven.

Let op: meldingen ontstaan vanaf **versie 0.18**. Eerder uitgevoerde publicaties en beslissingen krijgen **niet retroactief** meldingen. De eerste nieuwe publicatie wordt als update behandeld wanneer er al een eerder gepubliceerde maandversie bestaat.

## Tests

Offline uitgevoerd met Python 3 en pytest:

- **116 tests geslaagd**.
- **9 solver-testmodules overgeslagen**: OR-Tools is in de ontwikkelomgeving niet beschikbaar. De bestaande solvercode is niet aangepast, maar de live-ervaring moet op jouw Streamlit-omgeving worden bevestigd.
- Syntaxcontrole van alle Python-bestanden geslaagd.

Lokaal opnieuw testen:

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
streamlit run app.py
```

Gebruik deze versie tot nader order alleen met fictieve gegevens. Geef echte bedrijfsgegevens pas vrij na een formele toetsing van privacy, toegangsbeheer, beveiliging, hosting en toepasselijke arbeidsregels.
