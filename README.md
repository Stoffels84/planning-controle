# Controleursplanning v0.9.1 — concrete dienstvoorkeur per dag

**Proefversie, uitsluitend met fictieve gegevens.** Voortbouwend op werkende v0.9. Bestaande PostgreSQL-database, accounts, opgeslagen plannen en OR-Tools-regels worden behouden. Gebruik nooit ongetoetste arbeidsregels of een openbare testomgeving voor echte personeelsgegevens.

## Nieuw: dagelijks dienstnummer kiezen

Op **Mijn voorkeuren** (controleur) en **Voorkeuren** (planner/beheerder) zie je nu eerst een maandoverzicht, gegroepeerd per kalenderweek. Voor iedere dag kan de controleur kiezen tussen:

- **Geen voorkeur**: de planner kiest een dienst of rustdag volgens overige regels.
- **Liefst vrij**: een zachte vrijwens; geen goedgekeurd verlof.
- **Een concreet dienstnummer**, bijvoorbeeld `V101 · 06:00–14:00` of `D201 · 09:00–17:00`.

De lijst bevat **uitsluitend de diensten die de beheerder voor die specifieke datum in `Maandbehoefte` heeft ingepland**, dus niet alle mogelijke diensten uit de catalogus. Er wordt niet alleen op categorie ‘vroeg’ of ‘laat’ gekozen. Je kunt per dag ook een prioriteit `Laag`, `Normaal` of `Hoog` instellen. Bewaar alle dagwensen in één keer met **Alle dienstwensen voor deze maand opslaan**. Ongewijzigde dagen hebben standaard `Geen voorkeur`; bestaande vrije-dag-wensen worden in hetzelfde overzicht geladen.

**Zachte wens, geen vaste toewijzing.** In de planningsmotor krijgt een voorkeur voor datum + dienstnummer een strafscore wanneer precies die combinatie niet aan de medewerker wordt toegewezen, óók als de medewerker die dag niet werkt. De solver respecteert altijd de harde rust-, inzetbaarheids- en bezettingsvoorwaarden. Een selectie kan dus niet gegarandeerd worden.

Bestaande andere voorkeuren (zoals wekelijks liefst vrij en ongewenste overgangen) blijven beschikbaar onder **Overige voorkeuren (optioneel)**. Voor controleurs zijn de oude algemene categorie- en dienstnummerkeuzes niet meer als nieuwe optie zichtbaar: de voorkeur voor een specifiek dienstnummer geef je per datum op. Reeds bestaande algemene voorkeuren blijven behouden en zijn onder de overige voorkeuren nog verwijderbaar. De planner kan die nog beheren.

Voor een dienstnummer dat later uit de `Maandbehoefte` wordt gehaald, verschijnt een waarschuwing in het voorkeurenportaal. Een gebruiker kan dan een andere dienst kiezen of de vervallen voorkeur wissen. De vergelijking van alternatieve planningen toont voortaan ook **Dagelijkse dienstwensen ingewilligd/gemist**. Verouderde wensen tellen niet mee.

## Installatie bovenop je werkende v0.9

1. Maak eerst een GitHub-herstelpunt van v0.9 en een **back-up van de PostgreSQL-database**.
2. Pak `controleursplanning-github-streamlit-v091.zip` uit en upload de volledige inhoud naar de hoofdmap van je **bestaande private GitHub-repository**. Vervang de gewijzigde bestanden.
3. **Nieuw bestand: `daily_v091.py`**. Verder gewijzigd: `app.py`, `extras.py`, `planner.py`, `optimization_v09.py` en `README.md`. `requirements.txt` blijft ongewijzigd.
4. Laat `DATABASE_URL`, alle andere Streamlit Secrets en de bestaande PostgreSQL-database **ongewijzigd**. Een databasemigratie is niet nodig omdat de wensen in de bestaande JSON-werkruimte opgeslagen worden.
5. Laat Streamlit de bijgewerkte repository openen of herstart de applicatie indien nodig.

## Praktische test

1. Log in met een **fictief controleursaccount**. Open **Mijn voorkeuren**.
2. Ga naar een weekdag waarop meerdere diensten beschikbaar zijn; kies bijvoorbeeld `V102` in plaats van `V101`. Geef die wens prioriteit **Hoog**.
3. Kies op een andere datum **Liefst vrij**. Klik onderaan op **Alle dienstwensen voor deze maand opslaan**.
4. Open het scherm opnieuw: alle gekozen dienstnummers en prioriteiten moeten bewaard zijn.
5. Log in als beheerder. Controleer dezelfde medewerker onder **Voorkeuren**. Klik **Bereken maandplanning**.
6. In **Optimalisatie vergelijken** verschijnen ook de aantallen ingewilligde en gemiste dagelijkse dienstwensen. Controleer of de persoonlijke keuze als *zachte voorkeur* wordt meegewogen. Een dienst kan alleen worden toegewezen wanneer alle harde regels dit toestaan.
7. Verwijder voor één testdatum een dienst uit **Maandbehoefte** en controleer dat de oude wens als verouderd wordt gesignaleerd en kan worden vervangen.

Let op: gebruikers kunnen alleen wensen kiezen voor de **actieve demonstratiemaand**. Beheer van afzonderlijke maandarchieven, indiendeadlines en de volledige operationele bedrijfsregels volgen later.

## Technische controles

- `57 passed, 7 skipped` in de beschikbare ontwikkelomgeving (pytest). De overgeslagen testmodules vereisen **Google OR-Tools**, dat in deze container niet geïnstalleerd is.
- De Streamlit-UI en de daadwerkelijke OR-Tools-berekening moeten op de online proefapp getest worden.
- Geen databasemigratie, geen verandering aan wachtwoorden of accounts; opgeslagen wensen blijven gekoppeld aan het bestaande personeelsnummer.

Volledige test lokaal met geïnstalleerde afhankelijkheden:

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
```
