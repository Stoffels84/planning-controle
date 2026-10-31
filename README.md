# Controleursplanning v0.18 — meldingen en publicatiebeheer

> **Uitsluitend fictieve testgegevens.** Nog niet geschikt voor daadwerkelijke personeelsplanning bij De Lijn. Werkelijke arbeidsregels, beveiliging, privacy, back-ups en hosting zijn nog niet volledig gevalideerd.

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

## Installeren vanaf de werkende v0.17

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
