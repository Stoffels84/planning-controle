# Controleursplanning v0.14.1 — Herstel beheerdersdashboard

Deze versie is een **gerichte correctie** op v0.14. Het kan voorkomen dat de eerste vier metrieken correct verschijnen, terwijl onder `Planningstatus en opvolging` een generieke foutmelding staat. De databaseverbinding werkt dan voor het hoofdscherm; de fout bevindt zich mogelijk in de extra dashboardquery of verwerking van oudere planresultaten.

## Wat is aangepast?

- Onvolledige of oudere resultaten zonder een bruikbare `summary` veroorzaken niet meteen een dashboardcrash. Onbekende plancijfers worden leeg gelaten, niet als nul weergegeven.
- De selectie van de nieuwste publicatie kan geen fout meer geven door een mix van tijdstempels met en zonder tijdzone.
- Opvragen van maandstatus, verlof en ruilen gebeurt afzonderlijk: een probleem in één onderdeel blokkeert de rest van het dashboard niet.
- Als een databron toch faalt, staat de technische traceback in de **Streamlit Community Cloud-logs** met één van de zoektermen `DASHBOARD_V0141_MONTHS`, `DASHBOARD_V0141_LEAVE` of `DASHBOARD_V0141_SWAP`. De interface toont alleen het type fout, geen database-URL of wachtwoorden.
- **Geen** databaseverwijdering, datamigratie of wijziging aan de OR-Tools-planningsmotor.

## Bijwerken via GitHub

1. Bewaar een herstelpunt van de werkende v0.13/v0.14-commit en maak een databaseback-up.
2. Upload **alle bestanden uit deze ZIP** naar de bestaande privérepository, zodat zowel `app.py`, `store.py` als `dashboard_v014.py` worden bijgewerkt.
3. Laat `DATABASE_URL`, gebruikersaccounts en overige Streamlit Secrets ongewijzigd. De herstelcode `ADMIN_RECOVERY_KEY` moet verwijderd blijven als hij al gebruikt werd.
4. Laat Streamlit de app opnieuw uitrollen en open **Overzicht → Planningstatus en opvolging**.
5. Controleer of de maanden, statussen en bezettingsgraad verschijnen en of bestaande planningen ongewijzigd zijn.

**Als het onderdeel nog niet laadt:** open https://share.streamlit.io, selecteer de app, klik op `Manage app` en open **Logs**. Zoek naar de regel `DASHBOARD_V0141_MONTHS`, `DASHBOARD_V0141_LEAVE` of `DASHBOARD_V0141_SWAP`. Deel alleen de foutsoort en relevante tracebackregels; verwijder eventuele database-URL's, tokens, wachtwoorden en personeelsgegevens. Daarmee kunnen we de exacte oorzaak oplossen. De huidige screenshot alleen toont die technische oorzaak niet.

## Status en beperkingen

Lokale syntaxcontrole en automatische tests zijn uitgevoerd op deze versie. De volledige Streamlit-interface en jouw PostgreSQL-database zijn niet toegankelijk in deze ontwikkelomgeving, dus deze correctie is nog niet op jouw hostingomgeving geverifieerd. Het is nog steeds een testapp voor fictieve gegevens, niet geschikt voor operationele personeelsplanning.

## Zelf tests uitvoeren

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
```
