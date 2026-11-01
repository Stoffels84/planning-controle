# Controleursplanning v0.25 — onafhankelijke basiscontrole

> **Proefapplicatie, uitsluitend fictieve testgegevens.** Niet geschikt voor echte personeelsgegevens of de operationele planning bij De Lijn voordat de juridische, arbeidsrechtelijke, beveiligings- en privacycontrole volledig is uitgevoerd.

## Waarom deze release?

Tot en met v0.24.1 werden veel harde voorwaarden tijdens de OR-Tools-optimalisatie verwerkt, maar er was geen **afzonderlijke, solver-onafhankelijke eindcontrole** vóór het bewaren en publiceren van een rooster. Dezelfde rekenfout of corrupte roosterdata konden dan in een planversie terechtkomen.

**v0.25 is de eerste validatiefase, niet de afsluiting van alle oorspronkelijke basisvoorwaarden.** De bestaande planningsmotor, handmatige roosterbewerking en databaseopbouw blijven behouden.

## Nieuw

- `validator_v025.py` controleert toegewezen diensten **zonder OR-Tools** op:
  - actieve/bestaande controleurs, geldige dienstnummers en datum binnen de maand;
  - meerdere diensten op dezelfde startdatum, dubbele toewijzingen en reguliere dienstbezetting;
  - harde onbeschikbaarheid, rustdagen, geregistreerde dagafwezigheden, verboden diensten/categorieën/weekdagen en beschermde weekends;
  - minimale rust tussen diensten, ook nachtdiensten die over middernacht of maandgrenzen lopen;
  - verboden overgangen tussen dienstcategorieën;
  - maximum aaneengesloten werkdagen en maximum categorie-reeksen, ook over een gekende maandgrens;
  - individuele maandurenlimiet, aantal weekenddagen, gewerkte weekends en maxima per dienstcategorie;
  - overeenstemming tussen diensttoewijzingen, openstaande plaatsen, maandbehoefte en samenvattende cijfers.
- Bij elke nieuwe automatische berekening en handmatige heroptimalisatie voert de app deze nacontrole uit **vóór het concept wordt opgeslagen**. Een vastgestelde overtreding leidt tot een duidelijke fout en het onveilige resultaat wordt niet bewaard.
- Onder **Planning → Onafhankelijke roostercontrole (v0.25)** toont de app de controle-uitkomst, ook bij oudere concepten. Een afgekeurd concept kan niet via de gebruikersinterface worden gepubliceerd.
- Nieuwe concepten krijgen een `validation_v025`-kenmerk. De database voert de onafhankelijke controle **opnieuw** uit bij hun opslag en vóór hun publicatie, ter beveiliging tegen gewijzigde roosterdata. Oude historische versies zonder dit kenmerk blijven leesbaar; bij publicatie vanuit de app worden ze wel zichtbaar beoordeeld.
- Nieuw GitHub Actions-bestand `.github/workflows/tests.yml` om na upload alle tests **inclusief OR-Tools** met Python 3.11 te draaien. De uitslag op GitHub moet nog gecontroleerd worden. Het GitHub-project heeft geen nieuwe Secrets nodig voor deze tests.

## Installeren over de werkende v0.24.1

1. Maak eerst een **PostgreSQL-back-up** en bewaar de vorige GitHub-commit als herstelpunt.
2. Download het volledige v0.25 ZIP-pakket, pak het lokaal uit en vervang/upload de projectbestanden op GitHub. Controleer vooral **`app.py`**, **`store.py`**, het nieuwe **`validator_v025.py`** en de nieuwe tests.
3. Upload ook `.github/workflows/tests.yml` als je automatische tests op GitHub wilt; verborgen mappen zijn niet altijd zichtbaar in de bestandskiezer.
4. Klik op **Commit changes**, laat Streamlit opnieuw starten en open **Planning**.
5. Kijk in je GitHub-repository bij het tabblad **Actions** of de testworkflow groen is. Bij fouten: open de tests en meld de exacte foutregels. GitHub Actions moet in je repository toegelaten zijn.

**Geen databasewijzigingen, nieuwe wachtwoorden of aanpassingen aan Streamlit Secrets nodig.** Bestaande gepubliceerde planningen worden niet automatisch gewijzigd.

## Testscenario's in Streamlit

1. Bereken met fictieve controleurs een maand. Controleer dat **Onafhankelijke roostercontrole (v0.25)** de toewijzingen telt en geen overtredingen meldt.
2. Maak een gedeeltelijk gevuld plan. Controleer dat toegewezen, benodigde en open plaatsen met elkaar overeenkomen.
3. Maak een concept met een manuele wijziging en controleer dat de nacontrole ook voor die versie wordt uitgevoerd.
4. Test een fictieve nachtdienst aan het einde van een maand en een vroege dienst aan het begin van de volgende **nadat de buurmaand is gepubliceerd**; de rustregels moeten gerespecteerd worden.
5. Ga naar GitHub **Actions** en controleer de testuitslag met echte OR-Tools. Onze lokale omgeving heeft deze bibliotheek niet.

## Technische tests

```bash
python -m pip install -r requirements.txt pytest
pytest -q
```

Bij het maken van deze versie: **231 tests geslaagd, 11 modules overgeslagen** wegens ontbrekende OR-Tools; syntaxcontrole en ZIP-integriteit afzonderlijk geverifieerd. De Streamlit-gebruikersinterface en GitHub Actions zijn nog niet online getest.

## Nog niet afgevinkt / belangrijk

- De testomgeving levert **geen attest van wettelijke conformiteit**. Arbeidsregels van De Lijn, CAO, verplaatsingstijd en uitzonderingen moeten nog expliciet gevalideerd worden.
- De huidige dienstencatalogus blijft globaal, niet per afzonderlijke periode.
- Automatische uur-/saldotransfers en de volledige individuele arbeidsregimes zijn nog niet uitgewerkt.
- Uitgebreide weekendrotaties, voorkeurquota, invoerperiodes, taakverdelingsregels en locatiegebonden reistijden ontbreken nog of zijn slechts gedeeltelijk geïmplementeerd.
- De onafhankelijke controle beoordeelt in deze fase **reguliere diensten en de basiswerkregels**. De volledige semantiek van ingebedde/vrijgestelde taakplaatsen en de rechtmatigheid van alle taaktoewijzingen is nog een volgende validatiefase.
- Een **niet-gepubliceerde** buurmaand kan per definitie nog niet meegenomen worden in grenscontrole. Na publicatie van een buurmaand kan herberekening nodig zijn.
- De solver kan binnen de rekentijd een **FEASIBLE** (niet bewezen optimale) oplossing vinden. Een geslaagde nacontrole bevestigt alleen de geïmplementeerde harde basisregels, niet dat het de best mogelijke bezetting is.
- Achtergrondberekeningen en automatische toekomstige publicatie worden niet toegevoegd in v0.25.

## Vervolg

Na bevestiging van de UI en een groene GitHub Actions-run zijn de volgende prioriteiten: onafhankelijk toetsen van de **taak-/kwalificatieregels**, per-periode dienstcatalogi en de ontbrekende uur-/weekend-/voorkeurenspecificaties.
