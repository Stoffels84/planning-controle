# Controleursplanning v0.10 — verlof aanvragen en goedkeuren

**Dit is een proefversie met fictieve gegevens, geen goedgekeurd personeelssysteem van De Lijn.** Deze update bouwt voort op v0.9.1: concrete dienstwensen per dag, bestaande PostgreSQL-accounts, historische planningen en OR-Tools blijven werken.

## Nieuw

- Controleurs openen **Mijn verlofaanvragen**, kiezen een begin- en einddatum binnen de actieve planningsmaand en dienen een aanvraag in. Ze kunnen een **openstaande** aanvraag zelf intrekken.
- Planners en beheerders openen **Verlofaanvragen beheren**, zien aanvragen van testcontroleurs en kunnen deze goedkeuren of afwijzen.
- Een aangevraagde dag is **niet** automatisch een vrije dag. Bij goedkeuring schrijft de applicatie voor iedere goedgekeurde kalenderdag een `Verlof`-registratie naar de gedeelde werkruimte. Die registratie blokkeert de volledige dag voor toekomstige OR-Tools-berekeningen, ook bij overlappende nachtdiensten.
- Goedkeurders kiezen voorlopig het aantal **testuren per dag** (0 tot 16). Dit is geen officieel verlofsaldo, geen loonberekening en geen rechtsgeldige urencredit.
- De aanvraag en de beslissing worden in een afzonderlijke PostgreSQL-tabel (`leave_requests`) opgeslagen; acties worden geaudit. Alleen de betreffende controleur ziet de eigen aanvragen; bevoegde planners en beheerders zien alle aanvragen.
- Een bestaande gepubliceerde planning **blijft ongewijzigd** na goedkeuring. De app toont wanneer de gepubliceerde planning uit een oudere werkruimteversie komt. De planner moet dan opnieuw berekenen, beoordelen en expliciet publiceren.
- Nog niet gebouwd: onderling ruilen, aanvraag van andere activiteitstypes, verwerken van verlofsaldi, wijzigen/intrekken van al goedgekeurd verlof, notificaties naar andere apparaten en officiële arbeids-/verlofregels.

## Update vanuit v0.9.1

1. Bewaar eerst je werkende GitHub-commit als herstelpunt en maak een **back-up** van PostgreSQL. Zonder back-up kun je bij problemen geen gegarandeerd herstel uitvoeren.
2. Pak `controleursplanning-github-streamlit-v010.zip` uit. Upload de bestanden naar dezelfde hoofdmap van je **bestaande private GitHub-repository**. Vervang de bestaande bestanden.
3. **Nieuwe bestanden**: `requests_v010.py` en `tests/test_v010_leave_requests.py`. **Gewijzigd**: `store.py`, `app.py` en deze `README.md`.
4. Laat bestaande `DATABASE_URL`, accountgegevens en Streamlit Secrets ongewijzigd. Je hoeft **geen nieuwe PostgreSQL-database** te maken. Bij het starten maakt SQLAlchemy automatisch uitsluitend de nieuwe tabel `leave_requests` aan, als die nog niet bestaat.
5. Open je Streamlit-app, meld je aan met je bestaande fictieve testaccount en test de stappen hieronder.

## Testscenario

1. Log in als fictieve controleur. Open **Mijn verlofaanvragen** en vraag één of twee dagen verlof aan. De status moet **In behandeling** zijn.
2. Log in als planner/beheerder. Open **Verlofaanvragen beheren** en keur die aanvraag goed. Kies bijvoorbeeld **7,6 testuren per dag**.
3. Kijk bij **Uren en activiteiten**: de goedgekeurde dagen staan als `Verlof` geregistreerd. Je kunt deze goedgekeurde dagen niet stilzwijgend wissen via de gewone werkruimte-opslag.
4. Bereken bij **Planning** een nieuw rooster. De betrokken fictieve controleur mag op die goedgekeurde dagen geen dienst krijgen. Dit moet op jouw Streamlit-hosting getest worden: de OR-Tools-omgeving ontbreekt in de lokale ontwikkelcontainer.
5. Open **Mijn planning** als controleur nadat verlof is goedgekeurd maar vóór een nieuwe publicatie. De app waarschuwt dat de eerdere gepubliceerde planning mogelijk verouderd is; de vorige versie wordt niet automatisch aangepast.
6. Test ook een tweede verlofaanvraag en **wijzig niets aan het wachtwoord** of de database-URL.

## Onderhoud / beperkingen

- Bewaar testwachtwoorden en de database-URL **uitsluitend in Streamlit Secrets**. Zet geen `secrets.toml` of echte personeelsgegevens in GitHub.
- De huidige aanvraagfunctie ondersteunt alleen datums binnen de **actieve maand**. Buiten de maand en voor meerdere maanden tegelijk plannen volgt later.
- `Verlof` blokkeert de volledige kalenderdag. Bij deeltijdse medewerkers, nachtdiensten en financiële urenverrekening zijn verdere gevalideerde regels nodig.
- Na goedkeuring kan verlof in deze proefversie **niet** eenvoudig worden ingetrokken. Gebruik dus fictieve gegevens en test voorzichtig. Later bouwen we een controleerbare annuleringsworkflow.
- Een wijziging in de werkruimte verhoogt de versie; andere ingelogde gebruikers moeten hun scherm laten verversen. We bewaken gelijktijdige wijzigingen via database-transacties en revisies.
- Dit is geen formele AVG-/beveiligingsaudit. Voor echte personeelsgegevens zijn goedgekeurde infrastructuur, autorisatiebeleid, bewaartermijnen en beveiligingscontroles nodig.

## Technische tests

In de ontwikkelomgeving: **63 geslaagd, 7 overgeslagen**; de overgeslagen modules vereisen Google OR-Tools. De nieuwe aanvraag-/databasetests zijn uitgevoerd met SQLite. Python-syntax is gecontroleerd. De Streamlit-UI en de solver moeten op jouw online omgeving worden getest.

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
```
