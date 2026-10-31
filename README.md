# Controleursplanning v0.14 — Beheerdersdashboard

**Dit blijft een proefproject met uitsluitend fictieve gegevens.** De bestaande versie 0.13 blijft de basis. Versie 0.14 voegt een **alleen-lezen dashboard** toe; de planningsmotor, gebruikersaccounts, verlof/ruilen en de maandkopieerfunctie zijn niet gewijzigd.

## Nieuw in versie 0.14

In **Overzicht** ziet de planner of beheerder:

- Alle reeds aangemaakte kalendermaanden, inclusief filter op kalenderjaar.
- De status per maand: leeg, in voorbereiding, conceptplanning, gepubliceerd, gepubliceerd met nieuw concept of verouderde invoer.
- De huidige maandbehoefte (aantal dienstregels en vereiste dienstplaatsen), taakplaatsen en voorkeuren.
- De bezettingsgraad, openstaande plaatsen en toegewezen plaatsen uit de **laatst gepubliceerde planning**, of — als er geen publicatie is — het laatste opgeslagen concept.
- Een waarschuwing bij ontbrekende planning, openstaande plaatsen of gewijzigde invoer na de planberekening.
- Het aantal openstaande verlofaanvragen, ruilvoorstellen die wachten op de collega en ruilaanvragen die wachten op een beheerder (per gekozen maand).
- Een eenvoudige grafiek van benodigde dienstplaatsen per maand, plus Excel-export van het overzicht.

Dit dashboard **wijzigt niets** aan de maandplanningen of personeelsgegevens. Je blijft maanden openen met de bestaande kalendermaandkiezer in de zijbalk. Controleurs zien deze beheerdersinformatie niet.

**Belangrijk onderscheid:** een berekend rooster is niet per definitie gepubliceerd. Bij een nieuwer concept blijven de cijfers van de gepubliceerde planning leidend. Bij een verouderde publicatie wordt de revisieafwijking zichtbaar gemeld. De bezettingscijfers van een verouderd plan zijn **historische uitkomsten** en mogen niet gelezen worden als actuele bezetting. Het dashboard vergelijkt de revisies van maandinvoer; wijzigingen in een gedeelde catalogus die niet tot een nieuwe maandrevisie leiden, kunnen nog onopgemerkt blijven. Het is geen wettelijke arbeidscontrole of live dienstuitvoering.

## Installeren

1. Maak eerst een databaseback-up en bewaar de laatst werkende v0.13-commit op GitHub.
2. Pak het ZIP-bestand uit en upload **alle bestanden uit de ZIP** naar de hoofdmap van jouw bestaande privérepository.
3. Voeg zeker het nieuwe bestand `dashboard_v014.py` toe; de bestaande `app.py` en `store.py` worden ook bijgewerkt.
4. Laat `DATABASE_URL`, jouw beheerdersaccount en overige Streamlit Secrets ongewijzigd. Laat `ADMIN_RECOVERY_KEY` verwijderd.
5. Streamlit zal opnieuw uitrollen. Meld je aan als beheerder of planner en open **Overzicht**.

**Er is geen migratie of nieuwe database nodig.** De uitbreiding leest de huidige werkruimtes en planversies alleen uit. De opslagstructuur is ongewijzigd.

## Aanbevolen test op Streamlit

1. Controleer of november en december zichtbaar zijn in het overzicht. Verander van kalenderjaar met het filter als je meerdere jaren hebt.
2. Bekijk de status van je eerder **gepubliceerde** maand. Controleer of de bezettingsgraad van die planversie zichtbaar is.
3. Kijk bij een maand met dienstbehoefte maar zonder berekening: status **In voorbereiding**, bezettingsgraad blijft leeg in plaats van foutief 0%.
4. Selecteer een maand in de detailkeuze. Eventuele openstaande plaatsen en openstaande verlof-/ruilaanvragen moeten als aandachtspunt verschijnen.
5. Exporteer het Excel-overzicht, open het en controleer de cijfers.
6. Ga daarna naar **Planning** en controleer dat de OR-Tools-berekening en de bestaande kopieerfunctie van v0.13 nog werken.

## Grenzen van deze release

- Uitsluitend testgegevens; geen daadwerkelijke inzet of persoonsgegevens zonder beoordeling door De Lijn.
- Het dashboard toont opgeslagen berekeningen, geen actuele dienstuitvoering en geen continue voortgang van de solver.
- Bij gewijzigde maandinvoer kan de laatst gepubliceerde planning verouderd zijn; publicatie gebeurt nog steeds alleen via **Planning**.
- Reeds genoemde beperkingen op volledige arbeidsrechtelijke validatie, maandgrenscontroles, productiebeveiliging en back-ups blijven bestaan.

## Tests

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
```

Tijdens het samenstellen van versie 0.14: **92 tests geslaagd, 8 overgeslagen** omdat OR-Tools in deze testomgeving niet aanwezig was. De Streamlit-interface is in deze omgeving niet live getest; test de nieuwe dashboardweergave op je eigen Streamlit Community Cloud-app.
