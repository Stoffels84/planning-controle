# Controleursplanning v0.26.4 — administratief herstel verweesd TESTverlof

> Uitsluitend fictieve testgegevens. Gebruik de herstelprocedure nooit om geldige verlofrechten of echte personeelsgegevens te verwijderen. Valideer arbeidsregels en privacy voor productiegebruik.

## Waarom deze herstelversie?

In v0.26.3 kan de app acht oude verlofcredits van bijvoorbeeld fictief personeelsnummer `29076` signaleren als **onbekende controleur**. Omdat deze credits aan een **goedgekeurde verlofaanvraag** gekoppeld zijn, blokkeert de normale verwijderknop terecht. De reguliere intrekking door de beheerder vereist dat de controleur zelf een intrekking heeft gevraagd. Dat is geen correcte verklaring voor het opruimen van verweesde testgegevens.

V0.26.4 voegt een strikt afzonderlijke **administratieve herstelprocedure** toe voor zulke fictieve verweesde aanvragen.

## Wat doet de nieuwe herstelactie?

- Alleen een **actieve beheerder** ziet de hersteloptie. De medewerker moet volledig ontbreken uit de huidige controleurscatalogus.
- Alleen **nog goedgekeurde** verlofaanvragen in de actieve kalendermaand worden aangeboden.
- De beheerder maakt vooraf een back-up, vult een **verplichte reden** in en bevestigt expliciet dat het om achtergebleven fictieve testgegevens gaat.
- Een lopend intrekkingsverzoek moet eerst via de gewone verlofprocedure worden behandeld.
- De actie controleert dat **alle resterende verlofcredits exact overeenkomen** met de aanvraag. Bij een afwijking wordt niets veranderd.
- Uitsluitend de bijbehorende nog goedgekeurde credits worden in één transactie vrijgegeven. De oorspronkelijke aanvraag blijft bewaard, krijgt status `cancelled` en de administratieve correctie wordt vastgelegd in de intrekkingshistoriek en het auditlogboek.
- De huidige maandrevisie stijgt zodat oude concepten niet meer geldig zijn. **Reeds gepubliceerde planningen veranderen niet.**
- Er worden geen accounts en geen gewone activiteiten verwijderd.

## Installeren boven op v0.26.3

1. Bewaar de huidige werkende GitHub-commit én maak een PostgreSQL-databaseback-up.
2. Vervang `app.py` en `store.py` in de repository door de bestanden uit deze update.
3. Voeg `tests/test_v0264_orphan_leave.py` toe binnen de map `tests` (voor GitHub Actions).
4. Commit en controleer Streamlit Community Cloud en GitHub Actions.
5. **Database en Secrets blijven ongewijzigd**: geen migratie nodig.

## Herstel van de acht fictieve verlofdagen

1. Selecteer **december 2026** (de maand waarin de acht afwijkende registraties staan).
2. Open **Uren en activiteiten** → **Oude activiteiten controleren**.
3. Download **Back-up van alle activiteiten van deze maand (JSON)** en bewaar ook een databaseback-up.
4. Open **Goedgekeurd TESTverlof van verdwenen controleurs herstellen (v0.26.4)**.
5. Controleer of personeelsnummer `29076` vermeld staat, met de oorspronkelijke aanvraag en de resterende dagen 20–27 december.
6. Selecteer **die aanvraag**. Vul als reden in waarom het om achtergebleven testgegevens gaat (geen fictieve bewering dat de medewerker zelf intrekking vroeg).
7. Vink de bevestiging aan en kies **Fictief verweesd verlof administratief annuleren**.
8. Controleer of de acht afwijkende registraties verdwenen zijn en bereken de maand opnieuw.

**Als de aanvraag niet wordt aangeboden**, controleer of er een openstaand intrekkingsverzoek is en of het nummer toch in de controleurscatalogus voorkomt. Gebruik geen directe databasewijzigingen of omzeiling van de beveiliging.

## Testen

Voer in GitHub Actions de bestaande workflow uit. Die controleert ook de OR-Tools-tests.

Lokaal: `python -m pytest -q -ra tests`. De extra tests controleren de selectierechten, kalendermaand, revisieconflict, audittrail, historiek, dubbele aanvragen, onvolledige credits, het intact blijven van andere activiteiten en gepubliceerde planningen.
