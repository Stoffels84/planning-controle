# Controleursplanning — v0.1 (demoversie)

GitHub + Streamlit + Google OR-Tools. **Alleen fictieve data.** Dit is geen productieapplicatie voor De Lijn.

## Wat werkt in v0.1?
- Controleurs toevoegen, wijzigen en (de)activeren.
- Dienstnummers, vaste uren, categorieën en standaardbezetting instellen.
- Maandbehoefte per datum en dienstnummer beheren, inclusief Excel-import; het bezettingsaantal volgt de dienstencatalogus.
- Gewenste vrije dagen met prioriteit en voorkeurscategorieën instellen.
- Automatische maandplanning met OR-Tools CP-SAT, inclusief gedeeltelijke oplossingen.
- Controle op 1 dienst per kalenderdag, overlap en instelbare minimale rust, maximum opeenvolgende werkdagen **binnen dezelfde maand**, maandelijkse urenlimiet en individuele uitgesloten diensten, categorieën en weekdagen.
- Een zachte afweging van wensen en een eenvoudige verdeling van diensten/weekenddiensten.
- Openstaande bezetting tonen en Excel-export van het resultaat.

## Lokale installatie (Windows)
Installeer Python 3.11. Open PowerShell in de projectmap:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Op macOS/Linux gebruik je `python3.11 -m venv .venv` en `source .venv/bin/activate`.

## Online plaatsen via GitHub + Streamlit Community Cloud
1. Maak een **privé**-repository `controleursplanning` op GitHub.
2. Upload de inhoud van deze map (bestanden zoals `app.py` moeten in de hoofddirectory staan).
3. Ga naar https://share.streamlit.io en kies **Create app**.
4. Selecteer je GitHub-repository en branch `main`.
5. Kies `app.py` als main file en stel zo mogelijk Python 3.11 in.
6. Deploy. Dependencies worden geïnstalleerd met `requirements.txt`.

De gratis Community Cloud is geschikt als **proefomgeving**, niet als goedgekeurde productieomgeving voor echte personeelsgegevens.

## Testdata bewaren
Bewerkingen worden alleen bewaard in je huidige Streamlit-sessie. Gebruik de download **Bewaar demo als JSON** om testinstellingen te exporteren en laad die later opnieuw. Bij een app-herstart verdwijnen anders de wijzigingen. JSON-bestanden met `*.json` staan in `.gitignore`.

## Excel-import maandbehoefte
Download het Excel-sjabloon in **Maandbehoefte**. Verwachte kolommen:

| datum | dienstnummer | aantal |
|---|---|---:|
| 2026-11-02 | V101 | 2 |
| 2026-11-02 | D201 | 2 |

De datum moet binnen de gekozen maand vallen. Het dienstnummer moet al bestaan. Het `aantal` moet exact gelijk zijn aan de vaste bezetting in de dienstencatalogus. Import **vervangt** de volledige maandbehoefte. Een niet-vermelde combinatie datum/dienst is niet ingepland.

## Nog NIET gebouwd / risico's
- **Geen echte login** met personeelsnummer en wachtwoord, geen rechtenmodel of auditlog.
- **Geen permanente gedeelde database**, geen automatische back-ups, geen realtime samenwerking.
- Nog geen gevalideerde De Lijn-arbeidstijdregels, wettelijke of sectorale controle; ingevoerde rustwaarden zijn slechts testparameters.
- **Geen checks over de maandgrenzen heen**: nacht-/rust-/werkreeksvoorschriften uit vorige/volgende maand worden nog niet meegenomen.
- Nog geen kwalificaties, tijdelijke uitzonderingen, feestdagen/verlof, taken, locaties/reistijden, ruilaanvragen, publicatie, historie, urenoverdracht, alternatieve planningen of PDF-export.
- Voorkeursafweging en eerlijkheidsscore zijn voorlopige demonstratiemodellen. In deze versie lopen ze niet mee met arbeidsregimes of historische resultaten.
- Voor controleurs kan een enkele dienst per kalenderdag ontoereikend zijn als gesplitste diensten voorkomen; de productversie moet dit modelleren.
- Dit model is nog niet op echte bedrijfsroosters getest en mag geen operationele beslissingen ondersteunen.

## Volgende ontwikkelstap
Eerst een echte database (PostgreSQL) en veilige gebruikersaccounts, daarna maandgrenscontroles, afzonderlijke kwalificaties/rustregels, taakbeheer en de uitgebreide optimalisatiestrategieën uit het functioneel ontwerp. Overleg voor echte personeelsgegevens met IT/privacyverantwoordelijken van De Lijn.

## Code
- `app.py`: schermen en invoer.
- `demo_data.py`: fictieve voorbeelddata.
- `planner.py`: de OR-Tools-planningsmotor.
- `tests/`: basiscontroles op demonstratiegegevens en tijdsberekeningen.
