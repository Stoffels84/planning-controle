# Controleursplanning v0.15 — harde controles over maandgrenzen

**Testversie, uitsluitend voor fictieve gegevens.** Deze applicatie is niet juridisch gevalideerd voor echte arbeidsroosters of persoonsgegevens van De Lijn.

## Nieuw in v0.15

- Voor het maken van een maandplanning haalt het systeem de **laatste gepubliceerde** versies op van de direct **vorige en volgende** kalendermaand, indien aanwezig.
- OR-Tools controleert die vaste historische/naastliggende toewijzingen tegenover de nieuw te berekenen maand op:
  - overlappingen, minimumrust, specifieke rust per dienstovergang;
  - verboden opeenvolgingen van dienstcategorieën op aangrenzende kalenderdagen;
  - maximum aantal opeenvolgende werkdagen en maximum aaneengesloten diensten per categorie.
- Een nachtdienst die na middernacht eindigt wordt op basis van de werkelijke tijdstippen behandeld.
- Bij elk nieuw berekend concept worden IDs van de geraadpleegde aangrenzende publicaties opgeslagen. **Als een van de buurmaanden opnieuw wordt gepubliceerd vóórdat je het concept publiceert, blokkeert de applicatie de publicatie.** Ook het selecteren van een alternatief gebruikt die context.
- De validatie van onderlinge dienstwissels krijgt eveneens de huidige gepubliceerde buurmaanden mee.
- De database, dienstcatalogus en historische roosters blijven ongewijzigd. Er is **geen databasemigratie** nodig.

## Wat deze controle NIET garandeert

- Als een aangrenzende maand **nog geen gepubliceerde planning** heeft, bestaat er geen rooster om aan die kant te controleren. De app toont dit expliciet. Controleer opnieuw als de buurmaand wordt gepubliceerd.
- Een achteraf gewijzigde gepubliceerde maand **past de al gepubliceerde aangrenzende maand niet automatisch aan**. Controleer daarom steeds beide kanten na wijzigingen, zeker na een ruil of herpublicatie.
- De overige beperkingen uit het ontwerp (bijv. wettelijke afspraken, beschikbaarheid per tijdslot, echte verplaatsingstijden) zijn nog niet allemaal volledig gebouwd of gevalideerd.
- Een testwaarde van 11 uur minimumrust is geen uitspraak over de toepasselijke De Lijn-arbeidsregels.

## Update van v0.14.1

1. Maak eerst een herstelpunt van de werkende GitHub-commit en een back-up van je PostgreSQL-database.
2. Download de v0.15 ZIP en pak hem uit. Upload **alle bestanden uit het ZIP-project** naar de hoofdmap van je bestaande privérepository. Voeg vooral `boundary_v015.py` toe en vervang `app.py`, `planner.py` en `store.py`.
3. Bewaar je `DATABASE_URL`, accounts, wachtwoorden en overige Streamlit Secrets ongewijzigd. Geen nieuwe database of herstelcode nodig.
4. Wacht op de Streamlit-heruitrol, log in als testbeheerder en open **Planning**.
5. Controleer boven de berekenknop de vermelding van gepubliceerde voorgaande en volgende maand.

## Tests op Streamlit

**Scenario A — rust na nacht:** Publiceer een fictieve maand waarin een controleur op de laatste dag een nachtdienst van 22.00–06.00 uur heeft. Maak de volgende maand en plan dezelfde medewerker op de eerste dag voor een vroege dienst. Het systeem moet die combinatie uitsluiten en zo nodig een dienstplaats open laten.

**Scenario B — opeenvolgende dagen:** Stel een maximum van vijf opeenvolgende werkdagen in. Laat een fictieve controleur op de laatste vijf kalenderdagen van de vorige maand diensten uitvoeren, publiceer die maand en bereken de nieuwe maand. De eerste dag van de nieuwe maand mag niet opnieuw aan die controleur worden toegewezen.

**Scenario C — gewijzigde buurmaand:** Bereken in de nieuwe maand een concept. Publiceer dan een nieuw rooster voor de vorige maand. Het oude concept van de nieuwe maand moet als mogelijk verouderd verschijnen en mag niet meer als actueel gepubliceerd worden zonder herberekening.

**Opgelet:** scenario's A/B vereisen geschikte fictieve personeelsbezetting en tijdig gepubliceerde testmaanden. Een solver kan anders een lege plaats laten staan; dat is veilig gedrag.

## Ontwikkelaarstests

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
```

Hier lokaal: 97 automatische tests geslaagd, 9 solvertestmodules overgeslagen omdat OR-Tools in de ontwikkelomgeving ontbreekt. De solverregels moeten op de draaiende Streamlit-app alsnog getest worden.
