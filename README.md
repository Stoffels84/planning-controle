# Controleursplanning v0.11 — Ruilaanvragen

**Uitsluitend fictieve testgegevens. Geen bedrijfsgereed rooster.** Bouwt voort op werkende v0.10, met behoud van de bestaande PostgreSQL-database, login, OR-Tools-model en verlofaanvragen.

## Nieuw

- Controleur opent **Mijn ruilaanvragen**, selecteert een eigen reguliere dienst uit de *actuele gepubliceerde planning*, vult het personeelsnummer van de collega in, en kiest diens datum en dienstnummer. Er is geen onbeperkte inzage in de volledige collega'splanning nodig.
- De collega ziet een inkomende aanvraag, en kan **akkoord gaan** of afwijzen. De aanvrager kan de nog niet bevestigde aanvraag intrekken.
- Daarna ziet de planner/beheerder de geaccepteerde aanvraag bij **Ruilaanvragen beheren**. Afkeuren verandert niets.
- Bij definitieve goedkeuring controleert **Google OR-Tools het complete bestaande maandrooster met alle oorspronkelijke personeels- en taaktoewijzingen vastgezet**, behalve de twee daadwerkelijk geruilde reguliere diensten. De solver controleert daarmee dezelfde harde regels als bij een normale berekening. Bij een mislukte controle of time-out vindt geen publicatie plaats.
- Een goedgekeurde ruil wordt **atomair als nieuwe gepubliceerde planversie opgeslagen**, zonder oude planningen te wijzigen. Beide controleurs zien hun bijgewerkte eigen rooster. Er is een auditgebeurtenis.
- Oude aanvragen worden bij een gewijzigde gepubliceerde planversie of databasewerkruimte **geweigerd**; maak een nieuwe aanvraag op basis van het nieuwe rooster.
- De ruil van diensten met al toegewezen specifieke taken wordt nog geweigerd: taken horen bij een persoon en vereisen afzonderlijke herplanning. Evenmin worden zelfstandige taaktoewijzingen geruild.

## Update vanuit v0.10

1. Maak een herstelpunt van de werkende GitHub-commit en maak een **echte PostgreSQL-back-up**.
2. Pak `controleursplanning-github-streamlit-v011.zip` uit en upload alles naar dezelfde *private* GitHub-repository.
3. **Nieuw bestand**: `swap_v011.py`; **gewijzigd**: `planner.py`, `store.py`, `app.py`, en de README. Voeg de nieuwe tests toe onder `tests/`.
4. Laat de bestaande `DATABASE_URL` en Secrets ongewijzigd. Bij het eerste starten maakt SQLAlchemy automatisch de nieuwe tabel `swap_requests` aan (voor deze toevoeging is geen databasemigratie nodig).
5. Gebruik **fictieve accounts en diensten**. Publiceer een actuele fictieve planning, log in als twee verschillende controleurs, dien een ruil in, laat de collega akkoord gaan, en log in als planner om goed te keuren.
6. Controleer in beide individuele roosters dat de nieuwe versie zichtbaar is en in Historiek dat de goedkeuring is geregistreerd.

## Grenzen en beveiliging

- Per aanvraag worden twee reguliere dienstplaatsen **voor dezelfde planningsmaand** omgewisseld, niet een dienst overgenomen.
- De originele planversie blijft staan, maar de workspace-revisie wordt verhoogd zodat oudere concepten niet opnieuw gepubliceerd kunnen worden; een ruil is alleen toegestaan als actuele werkruimte en gepubliceerde planversie identiek zijn aan het moment van indienen.
- Een reeds toegewezen specifieke taak op een van de geruilde diensten verhindert de ruil. Geen impliciete taakverschuiving.
- De solver krijgt maximaal 15 seconden om het volledige **vastgepinde** rooster te verifiëren. Bij timeout of ontbreken van een geldige oplossing wordt er niets gepubliceerd.
- Deze workflow ondersteunt nog geen geavanceerde bevoegdheden per team en is geen goedgekeurde HR- of arbeidstijdapp. Gebruik geen echte gegevens.
- Testaccounts hebben personeelsnummers die overeenkomen met het fictieve personeelsprofiel in het controleursbeheer.

## Tests

```
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
```

De echte solvervalidatie moet uitgevoerd worden in een omgeving waar OR-Tools geïnstalleerd is.
