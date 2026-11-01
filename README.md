# Controleursplanning v0.26.1 — herstel van afwijkende activiteiten

> Gerichte herstelversie bovenop v0.26. De maandgebonden dienstdefinities blijven behouden.

## Waarom deze correctie?

Bij het opslaan van een wijziging aan diensturen controleert de app ook de andere gegevens van de actieve maand. Als oudere activiteiten verwijzen naar een onbekende controleur of een datum buiten die maand, verschijnt `Gegevens niet opgeslagen: Activiteit ...` — ook wanneer de diensturen zelf correct zijn. Het weigeren van inconsistente gegevens is terecht; het oorspronkelijke scherm liet echter niet toe om **meerdere** ongeldige activiteiten veilig in één bewerking op te lossen.

## Nieuw in v0.26.1

- **Diensten** toont nu een gerichte waarschuwing met verwijzing naar het herstelgedeelte.
- In **Uren en activiteiten → Oude activiteiten controleren** zie je de precieze probleemregels (personeelsnummer, datum, uren, type en reden).
- Download **eerst een JSON-back-up** van alle activiteiten. Controleer of activiteiten terecht bij een andere maand horen of gelinkt moeten worden aan een bestaande controleur.
- Alleen na expliciete selectie én bevestiging kun je afwijkende activiteiten **samen** verwijderen. Er gebeurt niets automatisch.
- De normale datasetvalidatie en de **databasebescherming voor goedgekeurd verlof** blijven actief. Het verwijderen van beschermd verlof wordt geweigerd. Gepubliceerde planningversies worden niet aangepast.
- Wijzig je vervolgens een dienstuur, dan zou de blokkering verdwenen moeten zijn, op voorwaarde dat er geen andere ongeldige gegevens zijn.

**Let op:** deze versie verwijdert of verplaatst geen registraties zonder jouw beslissing. We hebben niet kunnen vaststellen waarom jouw acht specifieke activiteiten een ongeldige verwijzing kregen. Verwijder ze niet als het om nog geldig goedgekeurd verlof gaat. Herstel eerst de controleurregistratie of controleer of de activiteit in de juiste maand thuishoort.

## Installatie vanaf v0.26

1. Maak een databaseback-up en bewaar je laatste werkende GitHub-commit.
2. Voor een minimale update: **vervang `app.py` en voeg `activities_v0261.py` toe** op het hoogste niveau van de repository. Of upload het volledige ZIP-project.
3. Bewaar dezelfde Streamlit Secrets en database. Er is **geen nieuwe databasetabel** nodig.
4. Kies de getroffen maand. Open **Uren en activiteiten → Oude activiteiten controleren**, bewaar eerst het back-upbestand en inspecteer de acht registraties.
5. Verwijder uitsluitend onjuiste of elders reeds geregistreerde activiteiten met de uitdrukkelijke bevestiging. Ga daarna naar **Diensten** en wijzig het uur.
6. Controleer bij GitHub **Actions** of de volledige OR-Tools-testworkflow groen is.

## Tests v0.26.1

- **248 tests geslaagd, 12 overgeslagen** in de lokale omgeving; de overgeslagen solvertests vereisen OR-Tools en worden opnieuw via GitHub Actions gecontroleerd.
- Extra regressietests controleren gerichte detectie, niet-destructieve selectie, database-opslag, en bescherming van goedgekeurd verlof.
- De online Streamlit-interface moet nog in jouw app worden geverifieerd.

---

## Bestaande v0.26-functionaliteit


> **Proefversie — alleen fictieve persoonsgegevens.** Geen juridische, cao- of privacyvalidatie voor gebruik met echte personeelsgegevens. Maak **vóór installatie een volledige PostgreSQL-back-up** en bewaar de vorige werkende GitHub-commit.

## Wat is nieuw?

Tot v0.25 werd `shifts` bij het laden van elke maand vervangen door de ene **gedeelde** dienstencatalogus. Daardoor kon een aanpassing van bijvoorbeeld dienst V101 voor december onbedoeld ook de actuele dienstdienstdefinitie in november wijzigen.

**Vanaf v0.26 wordt voor elke bestaande planningsmaand een eigen snapshot van de dienstencatalogus opgeslagen** (in de bestaande JSON-werkruimte, zonder nieuwe SQL-tabellen). Een wijziging van diensturen, categorie, locaties, activiteit of vaste bezetting geldt voortaan **alleen voor de geselecteerde maand**.

- Het scherm **Diensten** toont expliciet welke maand je bewerkt.
- Een aanpassing van de **vaste bezetting** past de reeds ingevulde maandbehoefte van die maand aan.
- Alle maanden die al zijn aangemaakt, houden hun eigen dienstdefinities; aanpassingen werken niet achteraf door.
- Maak je een **nieuwe maand** aan, dan neemt deze de dienstdefinities over van de dichtstbijzijnde **eerdere aangemaakte maand**. Zo neemt januari automatisch de aangepaste decemberdiensten over wanneer je januari *nadat december is aangepast* aanmaakt.
- De bestaande functie **Maandbehoefte kopiëren** gebruikt de vaste bezetting van de **doelmaand**, niet van de bron- of globale catalogus.
- **Controleurs, taken, algemene instellingen en optimalisatieprofielen** blijven gedeeld tussen maanden, zoals in v0.25. Dat is een bewuste beperking van deze release.
- De onafhankelijke nacontrole van v0.25 blijft bestaan en gebruikt de diensten van de betreffende maand.

### Voorbeeld

| Maand | Dienst V101 | Verandering |
|---|---|---|
| November 2026 | 06:00–14:00 | Bewaard zoals voorheen |
| December 2026 | 07:15–15:15 | Kan in december worden gewijzigd |
| Januari 2027 | 07:15–15:15 | Wordt zo overgenomen als januari daarna wordt aangemaakt |

**Let op:** als januari al was aangemaakt vóórdat je december wijzigt, wordt januari **niet** automatisch bijgewerkt. Selecteer januari en pas de dienst daar afzonderlijk aan. Dat beschermt bestaande maandinvoer en planversies.

## Veilige overgang vanaf v0.25 of v0.25.1

1. Maak **eerst een databaseback-up** en noteer de werkende GitHub-commit.
2. Pak `controleursplanning-github-streamlit-v026.zip` uit en plaats de bestanden in de bestaande repository. Vervang vooral `app.py`, `store.py`, `months_v012.py`, `catalog.py`, de bijgewerkte tests en `.github/workflows/tests.yml`.
3. Laat bestaande **Streamlit Secrets**, `DATABASE_URL`, accounts, dienstbehoefte, voorkeuren en gepubliceerde plannen ongewijzigd.
4. Na de eerste start/het openen van de planningsmaanden worden alle bestaande maanden **één keer** vastgelegd met de toen geldende *gedeelde* dienstdefinities (`shift_catalog_v026`). Dit gebeurt in één database-transactie en **zonder nieuwe tabellen**. De oude `workspace`-tabel wordt niet gewist.
5. Open **Diensten** in november en december, vergelijk V101, wijzig bijvoorbeeld het beginuur in december en bewaar. Keer terug naar november en controleer dat die onveranderd is.
6. Maak een nieuwe, nog niet bestaande maand aan en controleer of deze de dienstdefinities van de dichtstbijzijnde eerdere maand overneemt.
7. Open **Actions** op GitHub. De workflow voert de volledige testset met **Google OR-Tools** uit. Het eerder gecorrigeerde `test_v023_solver.py` en de juiste workflows voor mogelijke platgemaakte testmappen zijn inbegrepen.

### Belangrijk bij bestaande, al aangemaakte maanden

De migratie kan niet reconstrueren welke diensturen een maand **vroeger** had als eerdere versies die in de gedeelde catalogus al hebben overschreven. Ze legt bij de overgang de **op dat moment geldende gedeelde catalogus** per maand vast. Gepubliceerde `planning_versions` blijven als afzonderlijke historische documenten bewaard; diensturen in reeds opgeslagen toewijzingen worden niet aangepast. Controleer historische dienstdefinities daarom na installatie met een back-up wanneer je vroeger de globale uren hebt gewijzigd.

## Testresultaten in deze ontwikkelomgeving

```bash
python -m pip install -r requirements.txt pytest
pytest -q -ra tests
```

- **242 tests geslaagd**.
- **12 tests overgeslagen** in deze omgeving, omdat OR-Tools hier niet beschikbaar is. De nieuwe solverintegratietest wordt via GitHub Actions **wel** uitgevoerd.
- Testgevallen voor maandisolatie, migratie, overerving, bestaande toekomstige maanden, gekopieerde maandbehoefte met de doelmaandbezetting, autorisaties, ongeldige diensturen, global employee sharing, historische publicatie, en blokkeringen van diensten uit andere maanden.
- Broncode syntax gecontroleerd; de Streamlit-schermwerking kan hier niet integraal worden getest. Er wordt geen gegarandeerde online compatibiliteit geclaimd vóór GitHub Actions en Streamlit slagen.

## Grenzen van v0.26

- **Dezelfde dienstdefinitie gedurende een volledige maand**. Wijzigingen *binnen* een maand (bv. diensturen per specifieke kalenderdag) zijn nog niet ondersteund.
- Een historische publicatie blijft bewaard, maar een **gewijzigd huidig maandrooster** vereist een nieuwe berekening, aparte validatie en publicatie.
- Personeelsprofielen en taken zijn nog gedeeltelijk globaal; roterende regimes, saldo-overdracht en reistijden moeten nog worden uitgewerkt.
- Het plannen van een reeks maanden blijft afzonderlijk; het model respecteert gepubliceerde maandgrenzen zoals in v0.25, maar niet alle nog niet gemodelleerde arbeidsregels.
- Geen achtergrondberekeningen. De Streamlit-browser dient tijdens lange optimalisaties open te blijven.
