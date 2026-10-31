# Controleursplanning v0.9 — optimalisatieprofielen en vergelijking

**Proefversie met uitsluitend fictieve gegevens.** Opgebouwd vanaf v0.8, met behoud van de bestaande PostgreSQL-database, accounts, planning, taakvormen, rustdagen en OR-Tools-solver. Niet geschikt om zonder formele toetsing als operationele personeelsplanner bij De Lijn te gebruiken.

## Wat is nieuw?

In het beheerdersmenu staat **Optimalisatie vergelijken** met twee tabbladen:

1. **Eigen profielen beheren.** Naast vier vaste teststrategieën kun je maximaal twintig eigen profielen opslaan, elk met een naam, optioneel teamlabel en drie gewichten: voorkeuren, eerlijke verdeling en urenstreefwaarden. Profielen komen in de bestaande gedeelde PostgreSQL-werkruimte terecht en zijn via de bestaande toegangsrechten alleen door beheerder/planner te beheren.
2. **Alternatieven genereren.** Kies 1–4 profielen en een rekentijd per variant. De applicatie berekent elke variant achtereenvolgens met exact dezelfde personeels- en dienstgegevens. Optioneel kan eerdere gepubliceerde weekendhistoriek meegenomen worden. Daarna kun je de uitkomsten vergelijken en **één** alternatief expliciet als conceptplanning opslaan. Publiceren blijft een afzonderlijke actie in **Planning**.

Vergelijking toont consequent: ingevulde dienstplaatsen, openstaande dienstplaatsen, open taken, gerespecteerde/gemiste vrijwensen, spreiding van weekenddagen gecorrigeerd voor contractpercentage, de testafwijking van urenstreefdoelen en rekentijd. De **ruwe OR-Tools-doelfunctiewaarde vergelijken we niet** tussen profielen, omdat verschillende gewichten verschillende doelwaarden opleveren. Uitsluitend vroege/vrije dag- en terugkerende vrijwensen zitten in de vergelijkingskolommen; andere wenscategorieën worden *wel* door de solver meegewogen maar hebben nog geen aparte vergelijkingsindicator.

### Vier ingebouwde testprofielen

| Profiel | Voorkeuren | Eerlijkheid | Uren | Opmerking |
| --- | ---: | ---: | ---: | --- |
| Evenwichtig | 25 | 1 | 0 | Gebaseerd op bestaande testinstellingen |
| Voorkeuren centraal | 75 | 0 | 0 | Probeert vooral wensen te honoreren |
| Eerlijke verdeling | 10 | 3 | 0 | Legt nadruk op spreiding |
| Uren dichter bij streefwaarden | 10 | 1 | 2 | Alleen betekenisvol bij ingevulde urenstreefdoelen |

Dit zijn *voorbeeldgewichten*. In de bestaande solver zijn de interne ruwe strafscores nog niet over doeltypen genormaliseerd. Een gewicht 3 betekent dus **niet letterlijk** drie keer zoveel maatschappelijk belang als een gewicht 1. Deze nauwkeurigere kalibratie hoort bij een latere release.

**Teamlabels zijn nog geen aparte teamoptimalisatie.** In v0.9 kun je een profiel onder een teamlabel bewaren en daarop filteren, maar de gekozen gewichten gelden voor de complete gezamenlijke maandplanning. Gelijktijdig verschillende gewichten per team in één berekening is nog niet ingebouwd.

De solver is ongewijzigd voor harde voorwaarden (dienstbezetting, rust, inzetbaarheid, taakbevoegdheden, enzovoort). Veranderen van een profiel heeft daarop geen invloed. Verschillende profielen garanderen **geen verschillende roosters**; als twee berekeningen dezelfde toewijzingen opleveren, zie je dat eerlijk terug in het dashboard.

## Installatie bovenop de bestaande v0.8

1. Bewaar eerst een herstelpunt van je werkende v0.8 in GitHub en maak een **databaseback-up via je databaseprovider**.
2. Pak `controleursplanning-github-streamlit-v09.zip` uit. Plaats **alle bestanden** in de hoofdmap van je bestaande *private* GitHub-repository `controleursplanning`, waarbij bestaande bestanden worden vervangen. Voeg het **nieuwe bestand `optimization_v09.py`** toe.
3. Laat de Streamlit Secrets en `DATABASE_URL` ongewijzigd; je bestaande inloggegevens blijven werken. Verwijder een eventueel achtergebleven `ADMIN_RECOVERY_KEY`.
4. Open na de Streamlit-herstart het nieuwe onderdeel **Optimalisatie vergelijken**.
5. Je hoeft **geen nieuwe PostgreSQL-database en geen migratie** aan te maken: nieuwe eigen profielen gebruiken het bestaande JSON-werkruimteveld.

## Testscenario met fictieve medewerkers

1. Open **Optimalisatie vergelijken** en selecteer de drie standaardprofielen `Evenwichtig`, `Voorkeuren centraal` en `Eerlijke verdeling`.
2. Stel bijvoorbeeld `10 seconden` per profiel in en klik **Alternatieven berekenen**.
3. Controleer of drie resultaten verschijnen en of het aantal open dienstplaatsen/taken zichtbaar is. **OPTIMAL** en **FEASIBLE** zijn bruikbare solverstatussen; andere statussen zijn geen publiceerbare planning.
4. Voeg op het tabblad **Eigen profielen beheren** een profiel `Proef 1` toe. Controleer dat dit profiel na het opnieuw openen van de app nog beschikbaar is.
5. Kies een gevonden alternatief en klik **Gekozen alternatief als concept bewaren**. Open **Planning** en controleer of het juiste concept beschikbaar is. **Publiceer alleen als dat bewust de bedoeling is**.
6. Wijzig één fictieve voorkeur; oude alternatieven mogen dan niet nogmaals als actuele conceptplanning gekozen kunnen worden.

Als de testdata nauwelijks flexibiliteit toestaan, kunnen meerdere strategieën precies hetzelfde rooster opleveren; dat is geen bug.

## Technische controles

In de huidige ontwikkelomgeving zijn **50 tests geslaagd en 6 solver-testmodules overgeslagen**, omdat de `ortools`-installatie door netwerkproblemen niet kon plaatsvinden. De app en nieuwe Streamlit-schermen moeten dus nog live getest worden. Met Python 3.11+ en internettoegang kun je de volledige tests uitvoeren:

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
```

Alleen fictieve gegevens gebruiken; live personeelsgegevens vereisen goedgekeurde hosting, toegangsbeveiliging, back-ups en toetsing van arbeidstijd-/rustregels door De Lijn.
