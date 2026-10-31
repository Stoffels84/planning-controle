# Controleursplanning v0.22 — gericht heroptimaliseren met vaste diensten

> **Testversie met uitsluitend fictieve gegevens.** Niet vrijgegeven voor operationele beslissingen of echte personeelsgegevens. De arbeidsregels en beveiliging vereisen afzonderlijke beoordeling voor productiegebruik.

## Nieuw in v0.22

Onder **Planning** staat bij een bestaand berekend rooster een extra onderdeel:
**🔒 Diensten vastzetten en overige heroptimaliseren (v0.22)**.

- Kies in de tabel met bestaande toewijzingen via de kolom **Vastzetten** welke combinatie van **datum, dienstnummer en controleur** beslist behouden moet blijven.
- Optioneel kun je **één extra dienst handmatig vastzetten**. Kies hiervoor een datum/dienstnummer uit de actuele maandbehoefte en een actieve controleur. Na elke berekening kun je op basis van het nieuwe resultaat desgewenst nog een extra dienst vastzetten.
- De Google OR-Tools-solver houdt alle vastgezette toewijzingen **hard** aan en herberekent de **niet-vastgezette** diensten. Ook de andere harde regels blijven verplicht: rust, individuele onbeschikbaarheid, maxima, afwezigheden, taken en gepubliceerde aangrenzende maanden.
- Het resultaat wordt opgeslagen als een **nieuw concept**. De bronversie, en zeker een eventuele gepubliceerde planning, wordt **niet overschreven**. Publiceren blijft een afzonderlijke actie met bevestiging.
- In de resultaten staat een vergelijking met de vorige versie: het aantal vastgezette, behouden, nieuwe en weggevallen reguliere diensttoewijzingen.
- Als de keuze niet mogelijk is of de solver binnen de rekentijd geen geldige planning vindt, **wordt geen nieuw concept opgeslagen**.

**Bewuste beperkingen:** zelfstandige taken kunnen niet direct individueel vastgezet worden; hun toewijzing wordt opnieuw door de solver bepaald. De huidige interface ondersteunt één bijkomende handmatige toewijzing per herberekening. Er is geen voorziening om gepubliceerde plannen rechtstreeks in-place te wijzigen. Voor geheel opnieuw plannen zonder vaste diensten blijft de knop **Bereken maandplanning** bestaan.

### Wat controleert de app?

1. Elke vastgezette dienst bestaat in de maandbehoefte van de actieve maand.
2. Het gekozen personeelsnummer hoort bij een actieve controleur.
3. Geen dubbele vastzettingen, geen twee diensten op dezelfde dag voor dezelfde controleur, en niet meer reguliere vastzettingen dan de gewone dienstbezetting.
4. De solver controleert of de gekozen personeels-/dienstcombinatie werkelijk inzetbaar is en of de totale planning aan alle harde regels voldoet.
5. Concepten met een verouderde werkruimterevisie of gewijzigde aangrenzende gepubliceerde maand kunnen niet als basis voor gerichte heroptimalisatie gebruikt worden. Eerst opnieuw berekenen.
6. Na berekening controleert de app dat **iedere vastgezette dienst daadwerkelijk in het resultaat staat**, voordat er een nieuw concept opgeslagen wordt.

## Installatie op GitHub + Streamlit

1. Maak eerst een back-up van je PostgreSQL-database en bewaar de **werkende v0.21 GitHub-commit** als herstelpunt.
2. Pak `controleursplanning-github-streamlit-v022.zip` uit.
3. Upload **alle bestanden** naar de root van dezelfde private GitHub-repository. **Nieuw:** `locks_v022.py`; **aangepast:** `app.py`, `planner.py` en `README.md`. De andere bestaande modules en tests worden volledig meegeleverd.
4. Commit de wijzigingen en herstart/open de bestaande Streamlit Community Cloud-app.
5. Laat `DATABASE_URL`, andere Streamlit Secrets en de bestaande PostgreSQL-database ongemoeid. **Er is geen databasemigratie en geen nieuwe tabel nodig.**

De huidige bestandsstructuur blijft `app.py` als Streamlit-hoofdscript, de maandplanning in PostgreSQL en de bestaande Google OR-Tools-berekening in `planner.py`.

## Testprocedure op Streamlit

1. Meld je aan als fictieve beheerder/planner, selecteer een aangemaakte maand met diensten, en open **Planning**.
2. Als er nog geen rooster bestaat, klik **Bereken maandplanning**. Noteer één of twee toegewezen medewerkers en hun diensten.
3. Open **Diensten vastzetten en overige heroptimaliseren**. Vink bij een bestaande dienst **Vastzetten** aan. Klik op **Heroptimaliseer met vaste toewijzingen** en bevestig de handeling.
4. Bekijk het **nieuwe concept**. De vastgezette combinatie van datum, dienstnummer en controleur moet exact gelijk zijn. Niet-vastgezette toewijzingen mogen gewijzigd zijn, maar hoeven niet noodzakelijk anders te worden.
5. Probeer daarna een **extra manuele toewijzing** te kiezen en te heroptimaliseren. De solver kan hierdoor een andere controleur op een eerdere dienst zetten. Bij een tegenstrijdige combinatie moet de app weigeren, zonder vorige concepten te wijzigen.
6. Als je met een **gepubliceerde versie** begon: controleer dat de eerdere publicatie in **Publicatiebeheer** en het persoonlijke portaal beschikbaar blijft, totdat je expliciet het nieuwe concept publiceert.
7. Wijzig eventueel de maandbehoefte: een verouderde bronplanning moet nu eerst opnieuw berekend worden voordat je er vaste toewijzingen uit kunt overnemen.

### Automatische tests

```bash
pip install -r requirements.txt
pytest -q
```

In de bestandsbouwomgeving: **179 tests geslaagd; 10 solver-/integratietestmodules overgeslagen** omdat Google OR-Tools daar niet geïnstalleerd kon worden. De nieuwe CP-SAT-tests zijn opgenomen in `tests/test_v022_solver.py`, maar moeten nog draaien in een omgeving met OR-Tools. De Streamlit-interactie moet nog in de echte testapp getest worden.

## Bestaande functies blijven behouden

Onder andere: maandwerkruimtes, maandbehoefte kopiëren, individuele voorkeuren, verlofaanvragen en (gedeeltelijke) intrekking, diensten ruilen met goedkeuring, taken en kwalificaties, regels over maandgrenzen, meldingen in de webapp, publicatiebeheer, rapportage en eerlijkheidsanalyse, alternatieve optimalisatieprofielen, v0.21 haalbaarheidsdiagnose en Excel-export.

**Belangrijk:** het vastzetten van één of meerdere diensten is geen vrijstelling van arbeidsregels. Een tegenstrijdige combinatie wordt afgekeurd of resulteert in een onhaalbaar planningsprobleem. Controleer resultaten altijd handmatig; deze toepassing is nog geen gevalideerd roostersysteem voor De Lijn.
