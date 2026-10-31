# Controleursplanning v0.16 — persoonlijk portaal

> **Proefversie: uitsluitend fictieve testgegevens.** Niet vrijgegeven voor echte persoonsgegevens of operationele personeelsplanning bij De Lijn. De toepasselijke arbeids- en privacyregels zijn nog niet volledig gevalideerd.

## Nieuw in v0.16

Deze update verbetert vooral de gebruikerservaring. De bestaande Google OR-Tools-planningsmotor, database, accounts en maandenscheiding blijven behouden.

### Mijn voorkeuren

- Controleurs kiezen **één week tegelijk** in plaats van een lang formulier met alle kalenderdagen.
- Voor iedere datum zijn uitsluitend de **dienstnummers uit de maandbehoefte van die datum** beschikbaar, met begin- en einduur en dienstcategorie.
- Alternatieven: **Liefst vrij** of **Geen voorkeur**.
- Iedere wens kan de prioriteit laag, normaal of hoog krijgen.
- Een week opslaan verandert **geen enkele andere week**, geen aanvullende voorkeuren en geen gegevens van collega's.
- Het scherm toont het aantal dienstwensen, vrijwensen en dagen zonder voorkeur.
- Bij reeds gepubliceerde plannen toont het formulier afzonderlijk de **gepubliceerde toewijzingen**. Een voorkeur wordt nooit als toegewezen dienst weergegeven.
- Een geregistreerde afwezigheid/activiteit wordt zichtbaar gemeld; een wens verandert deze registratie niet.
- Een afzonderlijk uitklapbaar maandoverzicht toont de gegevens van de controleur.

### Mijn planning

- Een **persoonlijk maandoverzicht** met wens, gepubliceerde dienst en eventueel geregistreerde activiteit.
- Een **weekkiezer** met één overzichtelijke kaart per kalenderdag.
- Kenniscijfers voor diensttoewijzingen, uren en dagen zonder toegewezen dienst.
- Excel-download van uitsluitend het **eigen** maandrooster.
- De bestaande waarschuwing bij een mogelijk verouderde publicatie blijft behouden.
- Een dag zonder geplande dienst betekent niet automatisch een formele rustdag.

### Beheerder

- De beheerder behoudt de toegang tot het voorkeurenscherm per controleur, nu met dezelfde weekweergave.
- Geen wijziging aan de hoofdbeheerderrechten, solver, maandbehoefte of database-indeling.

## Updaten vanaf v0.15

1. **Maak een back-up** van PostgreSQL en noteer of bewaar de laatste werkende GitHub-commit (`v0.15`).
2. Pak het v0.16-ZIP-bestand uit. Upload de bestanden **naar de hoofdmap** van je bestaande privérepository, niet in een nieuwe submap.
3. Vervang het bestaande `app.py` en voeg vooral `portal_v016.py` toe. Laat ook de overige meegeleverde projectbestanden in de update overeenkomen met dit ZIP-bestand.
4. Laat je bestaande `.streamlit`-instellingen en Streamlit Secrets, in het bijzonder `DATABASE_URL`, ongewijzigd. **Er is geen databasemigratie nodig.**
5. Laat Streamlit de app opnieuw uitrollen. Meld je aan met een fictief controleursaccount en open `Mijn voorkeuren`.

## Testscenario op Streamlit

1. Open **november** en log in als fictieve controleur.
2. Selecteer de eerste week, kies op een dag een concreet dienstnummer en op een andere dag `Liefst vrij`. Sla de week op.
3. Wissel naar de tweede week, sla een andere wens op en ga terug naar de eerste week. De oorspronkelijke keuzes moeten behouden zijn.
4. Laad de pagina opnieuw, meld je desnoods opnieuw aan en controleer of de keuzes nog bestaan.
5. Log als beheerder in en publiceer een fictieve maandplanning. Open daarna als controleur `Mijn planning`: het **gepubliceerde dienstnummer** moet apart staan van de **gewenste dienst**.
6. Download je eigen Excel-rooster. Controleer dat **geen collega's** worden opgenomen.
7. Wissel naar december en terug: de novembervoorkeuren blijven behouden.

**Opgelet:** de keuze voor `Liefst vrij` is een zachte voorkeur, **geen verlofaanvraag**. Goedgekeurd verlof loopt via de afzonderlijke aanvraagfunctie.

## Technische implementatie

- `portal_v016.py`: zuivere datamodelhelpers voor weekindeling, telling, veilig opslaan van een deelweek, persoonlijke kalenderweergave en filtering van gepubliceerde toewijzingen op personeelsnummer.
- `app.py`: vernieuwde Streamlit-weergave voor `Mijn voorkeuren`, `Voorkeuren` en `Mijn planning`.
- `tests/test_v016_portal.py`: automatische tests voor verschillende maanden, dienstbeschikbaarheid per datum, behoud van wensen, persoonsisolatie en PostgreSQL-compatibele opslag via een lokale SQLite-testdatabase.

`pytest`-resultaat in deze ontwikkelomgeving: **106 geslaagde tests, 9 overgeslagen solver-testmodules**. Google OR-Tools en Streamlit zijn hier niet geïnstalleerd; de nieuwe interface en een volledige solverrun moeten nog op jouw Streamlit Community Cloud getest worden.

### Lokaal draaien

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
streamlit run app.py
```

Gebruik voor de online proef uitsluitend fictieve gegevens. Publiceer nooit echte wachtwoorden of database-URL's in GitHub.
