# Controleursplanning v0.6 — uitsluitend fictieve testgegevens

**Stack:** GitHub + Streamlit + Python + OR-Tools + PostgreSQL. Volledige voortzetting van v0.5, geen destructieve migratie. **Geen bedrijfsapplicatie**: het is een prototype, arbeidstijd- en sectorregels zijn niet juridisch gevalideerd.

## Nieuw in v0.6

### Weekend en maandgrenzen (nieuw tabblad)

- Centraal **maximum weekenddienst-dagen per maand** op basis van de startdatum (zaterdag of zondag), aan/uit instelbaar; individueel kunnen strengere maxima gelden.
- Per medewerker **maximum aantal gewerkte weekends**: een weekend telt één keer, ook wanneer iemand zowel zaterdag als zondag werkt. Een weekend dat begint in de vorige maand maar eindigt in de huidige maand wordt herkend.
- **Verplicht vrije weekends** instelbaar voor een individuele controleur. Het weekend loopt van zaterdag 00.00 tot maandag 00.00 uur. Dit blokkeert ook een overlappende nachtdienst van vrijdag op zaterdag of zondag op maandag.
- **Maximumaantal diensten per categorie, per kalendermaand**, zowel algemeen als per controleur, als harde grens. `0` in de interface betekent 'geen maximum' voor de categorie; de beperking 'geen Nachtdiensten' van het profiel blijft hiervoor geschikt.
- Per controleur **streefaantal vroege/dag/late/nachtdiensten** als zachte wens, niet als minimumgarantie. Leeg = geen streefwaarde; 0 = streef naar nul.
- Historische weekenddagen kunnen **handmatig** worden opgegeven om de zachte weekend-eerlijkheid meermaandsgericht te simuleren. De verdeling wordt ruw gecorrigeerd voor arbeidspercentage, maar is nog geen formeel eerlijkheidsmodel. **Automatische historische aggregatie wordt later gebouwd.**

### Uren (proefverrekening)

- Per medewerker een optioneel **startsaldoveld** van −80 tot +80 uur.
- De beheerder kan centraal de **simulatie van startsaldo** aan- of uitzetten. Als aan, kan de optimizer bij het zachte maandstreefdoel rekening houden met het startsaldo en eerder geregistreerde testcredits. Een positief saldo verlaagt de nagestreefde te plannen uren.
- In tabblad **Uren en activiteiten**, de berekende **Planning** en in de Excel-export verschijnt een apart overzicht met planuren, testcredits, start-, eind- en afwijkingssaldos.
- In Excel is er ook een nieuw tabblad **Dienstverdeling**, met toegewezen diensten per categorie en gewerkte weekenddagen.
- **Belangrijk:** dit is uitsluitend rekenkundige simulatie van een saldo, geen wettelijk correcte uren-, verlof-, ziekte-, feestdagen-, loon- of overurenadministratie. Er wordt **nog geen automatisch saldo uit vorige maanden** geladen of definitief doorgeschoven.

## Upgraden van v0.5 naar v0.6

1. Bewaar de huidige werkende v0.5 op GitHub als **tag/herstelpunt**. Maak bovendien via je PostgreSQL-provider een echte **databaseback-up**; een GitHub-codekopie bevat geen databasegegevens.
2. Pak `controleursplanning-github-streamlit-v06.zip` uit en upload de inhoud naar de **hoofdmap** van je bestaande **private** GitHub-repository. Overschrijf bestaande Pythonbestanden en voeg het **nieuwe `policy_v06.py`** en de nieuwe tests toe.
3. Laat de bestaande Streamlit Secrets, in het bijzonder `DATABASE_URL`, ongewijzigd. Zorg dat de eenmalige `ADMIN_RECOVERY_KEY` van je eerdere herstelactie verwijderd is.
4. Laat Streamlit opnieuw uitrollen. Log in met hetzelfde personeelsnummer en wachtwoord. Je bestaande gegevens blijven in dezelfde PostgreSQL-werkruimte; nieuwe velden krijgen terugwaarts compatibele standaardwaarden.
5. Test alleen met fictieve medewerkers, nooit met echte controleurs- of personeelsgegevens.

### Test A — bescherm een weekend

- Open **Weekend en maandgrenzen**. Kies een fictieve controleur en vink het weekend dat begint op een zaterdag in je planningsmaand aan.
- Klik **Individuele instellingen bewaren**, ga naar **Planning** en bereken opnieuw.
- Controleer dat deze persoon zaterdag en zondag niet is ingepland. Controleer óók dat een late vrijdag-nachtdienst die doorloopt tot zaterdag niet wordt toegewezen.

### Test B — maximum per categorie en weekend

- Stel in het nieuwe tabblad voor één fictieve controleur **max. nachtdiensten per maand = 1** in. Bereken opnieuw en controleer via **Dienstverdeling** dat het maximum wordt gerespecteerd.
- Stel vervolgens **max. weekenddagen = 1** in, en controleer dat de controleur maximaal één dienst krijgt waarvan de startdatum op zaterdag of zondag ligt.
- De solver mag daardoor **openstaande dienstplaatsen** tonen. Harde maxima worden niet genegeerd om de bezetting toch vol te maken.

### Test C — uurensaldo (rekenproef)

- Vul bij één fictieve medewerker in **Weekend en maandgrenzen** een startsaldo van `+5,0 uur` in.
- Vink centraal **Testsaldo meenemen bij het optimaliseren** aan en kijk of de resultaten in het urenoverzicht veranderen.
- Het rekenkundige eindsaldo is `startsaldo + planuren + activiteitscredits − streefuren`, alleen indien streefuren zijn ingesteld.
- Download de Excel-export en controleer de tabbladen **Urenoverzicht test** en **Dienstverdeling**.

## Technische opbouw

| Bestand | Inhoud |
|---|---|
| `app.py` | Bestaande webapp + nieuwe regel- en rapportschermen |
| `policy_v06.py` | Nieuwe zuivere weekend-, categorie-, validatie- en urensaldofuncties |
| `catalog.py` | Nieuwe velden met veilige defaults en validatie |
| `planner.py` | Nieuwe CP-SAT-beperkingen en zachte streefwaardes |
| `extras.py`, `store.py`, `demo_data.py` | Bestaande v0.5-modules, ongewijzigd |
| `tests/test_v06_policy.py` | Zuivere v0.6-tests |
| `tests/test_v06_solver.py` | OR-Tools-integratietests, alleen uitvoerbaar waar OR-Tools geïnstalleerd is |

## Teststatus van dit pakket

- Python-syntaxcontrole: geslaagd.
- `python -m pytest -q`: **30 geslaagd, 4 testmodules overgeslagen**, omdat OR-Tools niet kon worden geïnstalleerd in de uitvoeromgeving.
- Streamlit-app werd in deze omgeving niet met de browser getest. De solveruitbreidingen moeten op jouw Streamlit-omgeving getest worden voordat ze als werkend kunnen worden beschouwd.

### Optioneel lokaal testen (Windows)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
streamlit run app.py
```

## Bewuste beperkingen en volgende stappen

De v0.6-planningsmotor houdt nog niet automatisch rekening met werkelijk gepubliceerde weekendhistoriek, uren over meerdere maanden, volledige vaste werk-/rustcycli over de maandgrens, locatieverplaatsingstijden, bijzondere taaktoewijzingen of officiële sectorregels. Langdurige optimalisaties lopen nog in het Streamlit-proces en zijn geen afzonderlijke achtergrondtaken. Er is nog geen inzet voor echte personeelsgegevens toegestaan; authenticatie, gegevensbeheer en privacy moeten voor productie apart beoordeeld worden.
