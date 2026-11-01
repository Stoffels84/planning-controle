# Controleursplanning v0.24.1 — rekentijd tot 60 minuten

> **Proefversie — uitsluitend fictieve gegevens.** Niet geschikt voor echte persoonsgegevens of operationele inzet zonder afzonderlijke validatie van beveiliging, privacy en arbeidsregels.

## Wat is aangepast ten opzichte van v0.24?

In **Planning → Automatisch plannen met Google OR-Tools** had het invoerveld **Maximale rekentijd (seconden)** een bovengrens van **120 seconden**. Dat is nu **3.600 seconden (60 minuten)**. Deze waarde werd al geaccepteerd door de gegevensvalidatie en de gewone OR-Tools-planningsmotor; de wijziging zit in de gebruikersinterface.

- Het veld laat **1–3.600 seconden** toe, met stapjes van 30 seconden. Je kunt een precieze waarde rechtstreeks intypen.
- Nieuwe fictieve demogegevens beginnen met **300 seconden** als standaard. **Bestaande opgeslagen maanden en instellingen worden niet automatisch veranderd**: pas de waarde aan en klik **Instellingen opslaan**.
- Bij een lange rekentijd verschijnt een toelichting: **laat het browsertabblad geopend**. Streamlit Community Cloud biedt in deze app **geen gegarandeerde achtergrondberekening** als de sessie verdwijnt of de server herstart.
- De speciale solvercontrole voor dienstwissels behoudt de bestaande limiet van 15 seconden en wordt bewust niet gewijzigd.
- Er zijn **geen wijzigingen** aan database, accounts, meldingen, verlof, handmatige roosterbewerking, planversies of de solverlogica.

## Installatie als je v0.24 gebruikt

1. Bewaar je huidige GitHub-commit als herstelpunt; maak bij voorkeur een databaseback-up.
2. Vervang in je GitHub-repository **`app.py`** door het meegeleverde bestand. Dit is voldoende om de 120-secondenlimiet weg te nemen.
3. Vervang optioneel ook **`demo_data.py`** als je wilt dat *nieuwe fictieve demo-maanden* standaard 300 seconden krijgen in plaats van 10 seconden. Bestaande maanden blijven ongewijzigd.
4. Commit en herlaad je Streamlit-app. Wijzig je bestaande PostgreSQL-database en Streamlit Secrets niet.

Het ZIP-pakket bevat het **volledige project**, voor wie liever alle bestanden samen bijwerkt.

## Testprocedure

1. Open als beheerder **Planning** en kijk bij **Maximale rekentijd (seconden)**.
2. Voer **300**, **600** of **1.800** in, klik **Instellingen opslaan**, en herlaad het scherm.
3. Controleer of je gekozen getal bewaard blijft.
4. Voer met fictieve gegevens een planning uit met langere rekentijd en vergelijk de bezetting met de eerdere 120-secondenberekening.
5. Hou je browsertabblad open tijdens het rekenen. Een langere ingestelde rekentijd is een **bovengrens**, geen garantie dat de berekening zo lang loopt of altijd beter wordt.

## Tests

```bash
pip install -r requirements.txt
pytest -q
```

Bij het samenstellen van deze release: **222 tests geslaagd, 11 overgeslagen** (OR-Tools niet geïnstalleerd in de testomgeving). De Streamlit-interface en de solver met hoge limiet moeten nog in jouw online omgeving worden gecontroleerd. Nieuwe regressietests: `tests/test_v0241_solver_timeout_setting.py`.

## Verder

Alle functionaliteit van v0.24 blijft aanwezig. Er is **geen achtergrondtaak of autosave** toegevoegd: de gebruiker moet de applicatie openhouden tijdens een lange berekening en vervolgens het resultaat volgens het bestaande proces bewaren/publiceren.
