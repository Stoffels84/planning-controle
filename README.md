# Controleursplanning v0.12 — Meerdere kalendermaanden

**Testapplicatie met fictieve gegevens.** Voortbouwend op v0.11 (Streamlit, PostgreSQL en OR-Tools). Deze release introduceert **een werkruimte per kalendermaand** zonder oudere gepubliceerde planningen te overschrijven.

## Wat verandert er?

- In het **linkermenu** verschijnt **Kalendermaand**. Controleurs kunnen bestaande maanden selecteren om hun eigen voorkeuren of gepubliceerde planning te bekijken.
- De beheerder/planner kan met **Nieuwe maand voorbereiden** een volgende maand aanmaken, ook meerdere maanden vooruit.
- Een nieuwe maand krijgt automatisch de **bestaande controleurs, dienstcatalogus, taakcatalogus, algemene regels en opgeslagen optimalisatieprofielen**, maar begint **zonder** maandbehoefte, voorkeuren, activiteiten, taakbehoeften of verlofdagen.
- **November en december zijn onafhankelijk:** wijzigingen aan maandbehoefte, individuele voorkeuren en afwezigheden worden per kalendermaand bewaard. Eerdere concept- en gepubliceerde planningen blijven in `planning_versions` staan.
- Accounts blijven globaal geldig. Verlofaanvragen en ruilaanvragen worden aan de **maand van de betrokken dienst/datum** gekoppeld. De huidige verlofaanvragen ondersteunen één maand per aanvraag; voor meer maanden maak je afzonderlijke aanvragen.
- Bij een wijziging aan gedeelde controleurs, diensten, taken of instellingen geldt die voortaan voor **alle bewerkbare maanden**; opgeslagen gepubliceerde roosters zelf blijven ongewijzigd. Bestaande concepten kunnen hierdoor verouderd worden en een nieuwe berekening vereisen.
- Maandwissel wist de *lokale Streamlit-formulierstatus*, niet de databasegegevens. Daardoor blijven de invoervelden en berekende alternatieven van de vorige maand niet onbedoeld actief.

## Installatie op je bestaande GitHub + Streamlit-app

1. **Maak eerst een echte back-up van je PostgreSQL-database en noteer de werkende v0.11-commit.** Stop bij fouten; maak nooit een nieuwe database aan om deze update uit te voeren.
2. Download het ZIP-bestand van v0.12, pak het uit en upload de **inhoud** naar de hoofdmap van je private GitHub-repository. Het nieuwe bestand `months_v012.py` moet naast `app.py` en `store.py` staan.
3. Laat je Streamlit Secrets (`DATABASE_URL` en accounts) ongewijzigd; voeg geen wachtwoorden toe aan GitHub. Controleer dat een eventueel gebruikte `ADMIN_RECOVERY_KEY` al verwijderd is.
4. Herstart de Streamlit-app. Bij de **eerste start** maakt SQLAlchemy niet-destructief de tabellen `month_workspaces` en `shared_catalog` aan. De bestaande rij uit `workspace` wordt **gekopieerd** naar haar eigen maand. De oorspronkelijke `workspace`-rij en alle bestaande `planning_versions`, `accounts`, `leave_requests`, `swap_requests` en auditlogregels blijven intact.
5. Controleer eerst de **oorspronkelijke maand**, met maandbehoefte, voorkeuren en gepubliceerde planning. Maak pas daarna een volgende maand aan.

> **Let op:** `create_all` kan nieuwe tabellen aanmaken, maar is geen volwaardig migratieframework. Maak de back-up echt vóór de eerste opstart; herstel die bij een onverwachte fout in plaats van handmatig tabellen te verwijderen.

## Testplan met fictieve gegevens

1. Selecteer de bestaande maand (bijvoorbeeld november). Controleer de ingevoerde diensten en bestaande gepubliceerde planning.
2. Kies **Nieuwe maand voorbereiden**, selecteer december en klik op **Maand aanmaken**. De maand verschijnt als concept met lege dienstbehoefte. De controleurs en dienstcatalogus zijn wel aanwezig.
3. Voer voor december enkele dienstnummers in onder **Maandbehoefte** en sla op. Laat een fictieve controleur een dagelijkse dienstwens voor december ingeven.
4. Bereken een decemberconcept en publiceer het indien de solver een geschikte testplanning vindt.
5. Schakel links terug naar november: de oorspronkelijke maandbehoefte en gepubliceerde rooster moeten onveranderd zichtbaar zijn. Schakel weer naar december: de nieuwe maandinvoer moet er nog staan.
6. Test een verlofaanvraag voor december: goedkeuring mag alleen de decemberwerkruimte wijzigen.
7. Voeg in testmodus een extra fictief dienstnummer toe en controleer dat de dienstcatalogus ook in de andere maanden bijgewerkt is. Oude **gepubliceerde** roosters worden niet herschreven.

## Belangrijke grenzen

- De huidige planningsmotor controleert nog **niet** alle wettelijke/sectorale regels over maandgrenzen heen, bijvoorbeeld voor een nachtdienst op 30 november en een vroege dienst op 1 december. **Nog geen echte personeelsroosters publiceren voor gebruik.**
- Algemene regelinstellingen en personeelsprofielen zijn bewust **gedeeld** in v0.12; een volledige versiehistoriek van individuele arbeidsregimes of ingangsdatums moet later worden toegevoegd.
- Nieuwe maanden kopiëren **geen oude maandbehoefte**. De beheerder moet de nieuwe maandbehoefte importeren of invoeren.
- Deze versie bevat geen automatische back-upimplementatie en geen productiebeveiligingsaudit. Gebruik alleen fictieve testgegevens, tot expliciete bedrijfs- en privacygoedkeuring.
- Een eerdere publicatie blijft bewaard en kan nog bekeken worden, maar gewijzigde globale gegevens maken oudere concepten **verouderd**. Controleer voor elke publicatie de actuele invoer.

## Lokale tests

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
```

De bestaande SQLAlchemy- en maandtests kunnen zonder OR-Tools draaien. Solvertests vragen een werkende OR-Tools-installatie en moeten op de uiteindelijke doelomgeving worden uitgevoerd.
