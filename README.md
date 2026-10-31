# Controleursplanning v0.13 — Maandbehoefte kopiëren

**Uitsluitend voor fictieve testgegevens.** Deze release bouwt voort op de werkende v0.12 (GitHub + Streamlit + PostgreSQL + OR-Tools) en voegt een veilige kopieerfunctie toe voor **de maandelijkse dienstbehoefte**. Bestaande maandplanningen blijven bewaard.

## Nieuw in versie 0.13

Je kunt een nieuwe kalendermaand op twee manieren voorbereiden:

1. **Lege maand starten:** zoals in v0.12.
2. **Dienstbehoefte kopiëren:** de dienstnummers die op de dagen van een bestaande maand nodig waren worden naar de nieuwe maand gekopieerd, met de *actuele vaste bezetting* uit de gedeelde dienstencatalogus.

Kopieermethodes:

- **Overeenkomstige weekdag (standaard):** eerste maandag → eerste maandag, tweede maandag → tweede maandag, enzovoort. Wanneer een maand een vijfde weekdag heeft die niet in de bron voorkwam, neemt die extra dag het patroon van de **laatste overeenkomstige weekdag** uit de bron over. Diensten op een vijfde weekdag in de bron verdwijnen als de doelmaand geen vijfde overeenkomstige weekdag heeft.
- **Dezelfde kalenderdag:** bijvoorbeeld 6 november → 6 december. Een 31e verdwijnt als de doelmaand geen 31e heeft. Deze methode houdt **geen rekening met werkdagen of feestdagen**.

**Nooit meegekopieerd:** toegewezen controleurs, persoonlijke (dagelijkse) voorkeuren, verlof of andere afwezigheden, historische planningsversies, taakbehoeften en publicatiestatussen. Dit voorkomt dat een oude roosterindeling onterecht als de nieuwe maandplanning wordt beschouwd. De nieuwe maand wordt een concept en moet opnieuw berekend worden.

Je kunt ook een reeds aangemaakte **lege** kalendermaand vanuit het tabblad **Maandbehoefte** vullen. De kopieeractie is bewust geblokkeerd zodra er een dienstregel in de doelmaand bestaat of er al een planning voor die maand gepubliceerd is. Verwijder niet zomaar bestaande gegevens om de kopieerfunctie te forceren; wijzig de maandbehoefte in dat geval handmatig of importeer via Excel.

## Installatie op je bestaande project

1. Maak **eerst** een databaseback-up en noteer de werkende v0.12-commit in je private GitHub-repository.
2. Pak het v0.13-ZIP-bestand uit en upload **alle bestanden uit de ZIP** naar de hoofdmap van je bestaande repository. Vervang de eerdere bestanden. Voeg zeker de nieuwe module `month_copy_v013.py` toe naast `app.py`, `store.py` en `months_v012.py`.
3. Laat `DATABASE_URL` en andere Streamlit Secrets **ongewijzigd**. Controleer dat `ADMIN_RECOVERY_KEY` verwijderd is na een eventueel eerder wachtwoordherstel.
4. Na GitHub-commit zal Streamlit de app opnieuw uitrollen. Log in als beheerder of planner. Voor het kopiëren is een actieve PostgreSQL-verbinding nodig.

**Geen databasemigratie nodig.** De kopie wordt met de reeds bestaande `month_workspaces` en `shared_catalog`-tabellen uitgevoerd. De bronmaand wordt nooit gewijzigd. Het kopiëren van een nieuwe maand gebeurt in één databasetransactie: bij een fout ontstaat geen gedeeltelijk aangemaakte maand.

## Praktische proef: november → december

1. Kies links bij **Kalendermaand** de maand november met ingevulde fictieve dienstbehoefte.
2. Open **Nieuwe maand voorbereiden** en selecteer december. Kies **Maandbehoefte kopiëren**, bron **november**, en bijvoorbeeld **Overeenkomstige weekdag**.
3. Klik **Maand aanmaken**. In december zie je de overgenomen diensten. Controleer vooral dagen rond het maandbegin en een eventuele vijfde weekdag.
4. Ga naar **Mijn voorkeuren** als fictieve controleur: december hoort **geen** automatisch gekopieerde dagwensen van november te bevatten.
5. Wissel terug naar november en controleer dat de oorspronkelijke dienstbehoefte en de gepubliceerde planning intact zijn.
6. Test eventueel een nieuw aangemaakte, **lege** maand: onder **Maandbehoefte** kun je alsnog een bron selecteren, een voorbeeld van de overname bekijken en de diensten kopiëren.
7. Probeer de kopieeractie niet op een reeds ingevulde of gepubliceerde doelmaand: de app moet dit tegenhouden.

## Technische notities en beperkingen

- Nieuwe maandbehoefte gebruikt de **actuele** vereiste bezetting per dienstnummer. De kopie wordt geblokkeerd als de bron een dienst bevat die inmiddels onbekend of gedeactiveerd is. Pas eerst de dienstcatalogus aan en probeer opnieuw.
- Alleen gebruikers met de rol **admin** of **planner** mogen kopiëren; een controleur niet.
- Een bestaande doelmaand wordt alleen gewijzigd als de opgeslagen revisie nog overeenkomt. Bij een gelijktijdige wijziging moet de beheerder herladen.
- Nog **geen automatische controle op feestdagen of schoolvakanties**, en niet alle arbeids- en rustregels over maandgrenzen zijn geïmplementeerd. Controleer iedere maandbehoefte zorgvuldig vóór het berekenen.
- De OR-Tools-solver zelf is in deze release niet aangepast. Dit is een kopieerfunctie voor de invoer, niet een automatische kopie van het rooster.
- De applicatie is nog geen goedgekeurd personeels- of loonpakket. Gebruik uitsluitend fictieve gegevens totdat De Lijn de beveiliging, gegevensverwerking en arbeidsregels heeft gevalideerd.

## Geautomatiseerde tests

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
```

Bij het maken van deze release: **85 tests geslaagd, 8 tests overgeslagen**, omdat OR-Tools niet in de testomgeving geïnstalleerd is. De daadwerkelijke Streamlit-interactie test je op jouw online testapp.
