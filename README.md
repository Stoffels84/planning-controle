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
