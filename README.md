# Controleursplanning v0.17 — visuele kalender en aanvraagopvolging

> **Uitsluitend fictieve testgegevens.** Dit project is nog niet vrijgegeven voor echte personeelsgegevens of operationeel gebruik bij De Lijn. Arbeidsregels, privacy, hosting en back-ups moeten eerst formeel worden gevalideerd.

## Nieuw in versie 0.17

**Persoonlijk kalenderoverzicht**

- In **Mijn planning** kan een controleur wisselen tussen **Maandkalender**, **Weekkaarten** en **Tabel**.
- De kalender toont gepubliceerde diensten met concrete dienstnummers en uren. Wensen en geregistreerde activiteiten worden **afzonderlijk** weergegeven.
- Aanvragen in behandeling worden als zodanig aangeduid. Een vrijwens en een verlofaanvraag zijn **geen goedgekeurd verlof**.
- Op kleinere smartphones is **Weekkaarten** het overzichtelijkste alternatief voor de zevendelige maandkalender.
- Een dag zonder dienst wordt bewust **niet** als formele rustdag bestempeld.

**Mijn aanvragen & wijzigingen**

- Eén overzicht van eigen verlof- en ruilaanvragen, hun status en het aantal aanvragen dat nog in behandeling is.
- Voor aanvragen goedkeuren, intrekken, accepteren of afwijzen blijven de bestaande schermen **Mijn verlofaanvragen** en **Mijn ruilaanvragen** beschikbaar.
- Bij minstens twee gepubliceerde versies worden eigen wijzigingen per datum getoond, zoals `D201 → L301`, of van een dienst naar geen dienst. **Een conceptplanning telt niet mee.**

**Roosterwijzigingen voor planners en beheerders**

- Nieuw read-only scherm **Roosterwijzigingen** voor de geselecteerde maand en de geselecteerde controleur.
- De databaselaag voert een expliciete rolcontrole uit en geeft voor controleurs **uitsluitend eigen diensttoewijzingen** terug.
- Wijzigingen worden vergeleken tussen de **twee recentste gepubliceerde** versies; niet tegen elke conceptwijziging.
- Het scherm vergelijkt dienstnummers, begin- en eindtijd en uren, **niet** elke wijziging in taken, toelichtingen of urensaldi.

**Geen databasemigratie nodig.** De bestaande tabellen en de OR-Tools-planningsmotor blijven ongewijzigd. Nieuwe code bevat alleen leesfuncties in `store.py`, een visuele datamodule en Streamlit-schermen.

## Update vanaf de werkende v0.16

1. **Maak vóór de update een PostgreSQL-back-up en bewaar je werkende GitHub-commit van v0.16.**
2. Download `controleursplanning-github-streamlit-v017.zip`, pak het uit en upload de inhoud naar de **hoofdmap** van je bestaande privérepository, niet naar een submap.
3. Vervang met name `app.py` en `store.py` en voeg het nieuwe bestand `portal_v017.py` toe. De meegeleverde overige bestanden horen bij dezelfde versie.
4. Laat je `.streamlit`-instellingen en alle Streamlit Secrets, vooral `DATABASE_URL`, ongewijzigd. Voer **geen database-reset** uit.
5. Open de Streamlit-app nadat de nieuwe commit uitgerold is en meld je aan met een **fictief controleursaccount**.

## Online testen

1. Open een maand met een gepubliceerde planning en ga als controleur naar **Mijn planning**. Controleer of diensten in de maandkalender staan. Selecteer **Weekkaarten** en **Tabel**, en controleer of de gegevens gelijk zijn.
2. Log in als controleur en bekijk **Mijn aanvragen & wijzigingen**. Controleer of eigen verlof- en ruilaanvragen zichtbaar zijn, maar die van collega's niet.
3. Wijzig een testplanning en **publiceer** opnieuw via de bestaande, gecontroleerde publicatieworkflow. Vergelijk het wijzigingsoverzicht. Een nieuwe **conceptplanning zonder publicatie mag nog geen wijziging tonen**.
4. Log in als planner. Open **Roosterwijzigingen**, selecteer dezelfde controleur en vergelijk met zijn persoonlijke wijzigingen.
5. Wissel van maand en terug. De gegevens van de eerdere maand moeten ongewijzigd blijven.
6. Test de app ook op een smartphone. Gebruik indien nodig **Weekkaarten** in plaats van de zeven kolommen.

Bij maar één gepubliceerde planversie kan er geen vorige publicatie worden vergeleken. Dat is normaal.

## Techniek en controles

- `portal_v017.py` bevat zuivere functies voor de kalender, statusweergave, eigen aanvraagoverzichten en dagvergelijkingen.
- `store.personal_published_versions()` geeft maximaal twee **gepubliceerde** versies terug, met serverzijde gefilterde toewijzingen en toegangscontrole.
- `app.py` toont de vernieuwde schermen; bestaande invoer-, goedkeurings- en planningscode blijft verder behouden.
- `tests/test_v017_calendar.py` controleert kalenderdagen, geen datalekken, aanvraagstatussen, conceptuitsluiting, wijzigingen, rolrechten en databasefunctionaliteit.

**Offline testresultaat:** 111 tests geslaagd, 9 solver-testmodules overgeslagen (OR-Tools is niet geïnstalleerd in deze ontwikkelomgeving). De gebruikersinterface moet aanvullend op Streamlit Community Cloud getest worden.

Lokaal testen:

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
streamlit run app.py
```

De app mag nog steeds alleen met fictieve gegevens worden gebruikt totdat de toepasselijke arbeids- en privacyregels en hostinginfrastructuur goedgekeurd zijn.
