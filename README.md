# Controleursplanning v0.26.2 — diensturen wijzigen met oude activiteiten

> Gerichte correctie op v0.26.1. Uitsluitend fictieve gegevens. Gebruik dit project niet voor echte operationele personeelsplanning zonder de nodige juridische, privacy- en arbeidsregelvalidatie.

## Probleem

Bij sommige **niet-gepubliceerde** maanden zijn er eerder opgeslagen activiteiten die een andere maand noemen of verwijzen naar een niet langer bestaande controleur. De gewone opslagfunctie controleert de hele dataset. Daardoor wordt ook een zuivere wijziging van een dienstuur tegengehouden met `Activiteit 1: onbekende controleur of datum buiten planningsmaand` (soms meerdere activiteiten).

De publicatiestatus heeft hier geen directe invloed op. De maandspecifieke inhoud veroorzaakt het verschil.

## Correctie

- Het formulier **Diensten → Bestaande dienst wijzigen → Dienst bewaren** gebruikt bij een PostgreSQL-installatie de nieuwe serverfunctie `store.save_month_shift`.
- Die leest de actuele versie van de gekozen maand opnieuw in en past **uitsluitend die ene dienst** aan. Als de vaste bezetting wijzigt, worden de bijhorende `demand.required`-velden van **diezelfde maand** gelijkgezet.
- Historische en afwijkende activiteiten, andere diensten, voorkeuren en goedgekeurde verlofregistraties blijven volledig en ongewijzigd aanwezig.
- De bestaande beveiligingen voor rollen (alleen beheerder/planner), revisies, goedgekeurd verlof, maximum dienstduur, uurformaat en deactiveren met aanwezige maandbehoefte blijven actief.
- Andere reeds aangemaakte maanden en eerder gepubliceerde planningsversies wijzigen niet.
- Een afwijkende activiteit blijft zichtbaar via **Uren en activiteiten → Oude activiteiten controleren**. **Een nieuwe planning berekenen is nog niet toegestaan** zolang de volledige maandgegevens ongeldig zijn. De correctie omzeilt dus alleen de onnodige blokkade bij een *beperkte cataloguswijziging*, niet de planningsvalidatie.

De herstelknop uit v0.26.1 blijft bestaan. **Wis nooit automatisch of zonder controle een activiteit**, zeker niet bij goedgekeurd verlof.

## Installatie op v0.26.1

1. Maak een databaseback-up en bewaar de huidige werkende GitHub-commit.
2. Vervang de bestanden **`app.py`** en **`store.py`** in de hoofdmap van je repository.
3. Voeg **`shift_edit_v0262.py`** toe in diezelfde hoofdmap.
4. Klik op **Commit changes**; Streamlit start opnieuw. Je `DATABASE_URL` en Secrets blijven ongewijzigd.
5. Selecteer de niet-gepubliceerde maand met de fout, open **Diensten** en wijzig het begin- of einduur. Het opslaan mag de bestaande activiteiten niet aanpassen.
6. Ga naar **Uren en activiteiten** om de nog bestaande afwijkende activiteiten op basis van personeelsnummer en datum te onderzoeken. Herstel ze eerst correct voordat je opnieuw laat optimaliseren.
7. Controleer **GitHub Actions** op een groene uitvoering. Alle tests incl. OR-Tools draaien daar op een runner.

Er zijn **geen nieuwe databasetabellen en geen migraties** nodig. De oude, geplande en gepubliceerde planningen blijven bewaard.

## Teststatus

`pytest -q -ra tests`: **254 tests geslaagd en 12 overgeslagen** in de lokale omgeving (waar OR-Tools ontbreekt). De nieuwe tests dekken ongeldige activiteiten in een ongepubliceerde maand, ongewijzigd behoud van activiteiten en goedgekeurd verlof, toegangsrechten, gelijktijdige wijzigingen, invoervalidatie en maandafbakening.

De Streamlit UI en volledige OR-Tools-integratie moeten nog bij de gebruiker/GitHub Actions worden gecontroleerd.
