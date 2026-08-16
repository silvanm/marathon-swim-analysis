# Forschungsprotokoll: Was sagt eine Zürichsee-Zeit über den Ärmelkanal?

Was geprüft wurde, was gehalten hat und was nicht. Die verworfenen Ansätze stehen hier
vollständig drin — sie sind der teurere Teil der Arbeit und verschwinden sonst spurlos.

Stand: 2026-08-16 · n = 163 Personen mit beiden Zeiten

Dasselbe als gesetzter Bericht mit elf Abbildungen:
[`260816 Marathon-Swim | Forschungsprotokoll.pdf`](260816%20Marathon-Swim%20%7C%20Forschungsprotokoll.pdf)
(erzeugt mit `report_data.py` + `build_report.py`).

---

## 1. Die Frage

Der Zürichsee-Marathon (26 km) ist faktisch ein Vorbereitungsrennen für Kanal-Aspiranten.
Wenn genügend Personen beides geschwommen sind, lässt sich aus einer Seezeit die zu
erwartende Kanalzeit schätzen.

## 2. Der Datenweg

| Schritt | Ergebnis |
|---|---|
| PDFs der Ranglisten 2002–2026 extrahiert | 2015 Ergebnisse |
| Namensabgleich mit der Channel Solo Database (3443 Querungen) | 205 Namensgleiche |
| Vergleichbarkeit hergestellt (siehe unten) | 167 Paare |
| Doppelzählungen entfernt | **163 Paare** |

**Vergleichbarkeit** war der Schritt mit dem grössten Einfluss auf das Ergebnis. Ohne ihn
vergleicht man Äpfel mit Birnen:

- Zürichsee nur Einzelstarts — eine Staffel-Teilstrecke ist keine 26-km-Leistung.
- Zürichsee nur ohne Neopren — Kanalregeln verbieten ihn.
- Kanal nur einfache Querungen — Zwei- und Dreifachquerungen sind eine andere Disziplin.

**Paarung** bei Mehrfachstartern: das Paar mit dem kleinsten Jahresabstand (Median 2 Jahre).
Alternativen wären „Bestzeit gegen Bestzeit" (mischt teils 20 Jahre auseinanderliegende
Formzustände) oder alle Kombinationen (Vielstarter dominieren, Punkte nicht unabhängig).

## 3. Die Modellform — getestet, nicht angenommen

Die naheliegende Erwartung ist Proportionalität: Zeit = Strecke ÷ Tempo, der Kanal ist
länger, also müsste die Kanalzeit ein Vielfaches der Seezeit sein. **Das ist die einzige
Form, die die Daten klar verwerfen.**

| Modell | Formel | Residual-SD |
|---|---|---|
| **additiv (Steigung = 1)** | `ZH + 4.25` | **1.644** |
| linear mit Achsenabschnitt | `3.63 + 1.066·ZH` | 1.647 |
| Potenzgesetz | `2.74·ZH^0.714` | 1.651 |
| proportional durch 0 | `1.447·ZH` | 1.733 |

Der Fit-Unterschied zwischen den ersten drei ist irrelevant. Entscheidend ist eine andere
Zahl: **die Korrelation zwischen Aufschlag und Seezeit beträgt +0.058.** Der Aufschlag hängt
nicht vom Tempo ab, also ist eine Steigung nicht nur überflüssig, sondern irreführend.

Das Potenzgesetz sieht wie ein Konkurrenzmodell aus, ist aber keines: Eine additive Beziehung
erscheint im Log-Raum als Potenzgesetz mit Exponent x̄/(x̄+c) = 9.30/13.55 = **0.687**.
Gemessen wurden 0.714. Drei der vier Formen sagen dasselbe.

**Gewähltes Modell:**

```
Kanalzeit = Zürichseezeit + Aufschlag
Aufschlag ~ LogNormal(mu = 1.3586, sigma = 0.4800)
          → Median 3:53 h, 95 % zwischen 1:31 und 9:58 h
```

Lognormal, weil der Aufschlag strikt positiv (min 0:06, max 9:56) und rechtsschief ist.
Das ergibt ein asymmetrisches Band — realistischer als ein symmetrisches ±, denn nach unten
gibt es eine harte Grenze, nach oben nicht. Abdeckung: 158 von 163 Paaren (97 %) im
95-%-Band.

Der *Faktor* sinkt mit langsameren Zeiten (1.55 bei unter 8 h, 1.32 bei über 11 h). Das ist
die Arithmetik eines konstanten Aufschlags, kein eigener Effekt.

## 4. Geprüfte Merkmale

Zielgrösse ist immer der **Aufschlag in Stunden**, nie der Faktor — dazu Abschnitt 6.

| Merkmal | r mit dem Aufschlag | Urteil |
|---|---|---|
| **Tidenhub am Tag der Querung** | **+0.229** [+0.08, +0.37] | **übernommen** |
| Saisonmitte \|Monat − 8\| | +0.142 [−0.01, +0.29] | verworfen |
| Jahresabstand der beiden Schwimmen | −0.114 | verworfen |
| Wassertemperatur (°C) | −0.104 | verworfen |
| Reihenfolge (See zuerst?) | +0.102 | verworfen |
| Seezeit | +0.058 | verworfen (Begründung oben) |
| Anzahl Zürichsee-Starts | +0.041 | verworfen |
| Jahr der Querung | +0.032 | verworfen |
| Geschlecht | +0.024 | verworfen |
| Alter beim Schwimmen | −0.005 | verworfen |
| Richtung E→F / F→E | konstant | nicht prüfbar |

### 4.1 Tidenhub — das einzige Merkmal mit Signal

Aus dem Datum der Querung wird der Tidenhub in Dover berechnet (`tides.py`, harmonisches
M2+S2+N2-Modell, aus dem Channel-Simulator portiert). Richtung wie von der Physik verlangt:
mehr Hub → stärkere Ströme → längere Gezeiten-S-Kurve.

```
log(Aufschlag) = 0.863 + 0.719 · Tidenfaktor          n = 159, r = +0.229

  Nipptide      (0.45)  →  3:17 h        Mitte      (0.80)  →  4:13 h
  Richtung Nipp (0.60)  →  3:39 h        Springtide (1.00)  →  4:52 h
```

Kreuzvalidiert **−1.4 % MAE**, in 128 von 200 Folds besser. Der Gewinn ist klein, weil zwei
Drittel der Querungen ohnehin in Nippfenstern liegen — Piloten buchen die ruhigen Termine.
Für eine einzelne Planung ist der Effekt gross: rund **95 Minuten** zwischen Nipp und Spring.

Der praktische Wert liegt woanders als in der MAE: Das Tidenfenster ist die einzige geprüfte
Grösse, die man **vor der Buchung kennt**. Damit wird aus einer Prognose eine
Entscheidungshilfe.

*Risiko und Absicherung:* Die Konstanten sind auf 56 Dover-Hochwasser aus einem 29-Tage-Fenster
im August 2026 gefittet, angewendet werden sie ab 2002. Gegenprobe an 1272 Stichtagen
2002–2025: die Spring/Nipp-Einstufung widerspricht der unabhängig gerechneten Mondphase
dreimal (0.2 %). Sie hält, weil nur die Amplituden gefittet sind — die Frequenzen sind
astronomische Konstanten. Nodale Modulation (18.6 Jahre) ist nicht modelliert.

### 4.2 Monat der Querung — verworfen

| Monat | n | Median-Aufschlag |
|---|---|---|
| Juni | 5 | 5:08 |
| Juli | 39 | 3:49 |
| August | 63 | 3:52 |
| September | 45 | 4:04 |
| Oktober | 6 | 4:07 |

Juli bis Oktober sind praktisch identisch. Auffällig ist nur der Juni — auf fünf Querungen.
**Ohne Mai und Juni fällt die Korrelation von +0.142 auf +0.066.** Ein Effekt, der an sechs
von 159 Punkten hängt, ist keiner.

Kreuzvalidiert: −0.2 % allein; zusammen mit dem Tidenhub **schlechter** als der Tidenhub
allein (−1.3 % statt −1.4 %).

Selbst wenn der Juni-Effekt real wäre, liesse er sich nicht als Temperatureffekt lesen:
Frühsaison-Slots werden anders vergeben, und wer im Juni schwimmt, hat typischerweise weniger
Vorbereitung hinter sich. Aus diesen Daten nicht trennbar.

### 4.3 Wassertemperatur — verworfen, aber der knappste Fall

Quelle: `kanal_sst_monatsmittel.csv` (NASA JPL MUR SST, Monatsmittel 2015–2026); für ältere
Querungen das Monatsmittel über alle Jahre.

- Allein: r = −0.104, KI enthält 0, kreuzvalidiert **+0.1 %** — nutzlos.
- Zusammen mit dem Tidenhub: −2.1 % statt −1.4 %, in 68 % der Folds besser.
- Koeffizient: −4.6 % Aufschlag pro Grad wärmer — Richtung und Grössenordnung plausibel.

Entschieden hat der Bootstrap:

```
Temperatur-Koeffizient  −0.0477   95%-KI [−0.0967, +0.0317]   → enthält 0
```

Bei 2000 Ziehungen wechselt das Vorzeichen. Der kreuzvalidierte Gewinn von 32 Sekunden auf
einer 12-Stunden-Prognose trägt das nicht.

**Warum Tide funktioniert und Temperatur nicht**, obwohl beide physikalisch wirken: Der
Tidenhub variiert im Datensatz um Faktor 2.6 (0.40–1.05), die Wassertemperatur nur zwischen
11.6 und 19.8 °C, mit über 90 % der Querungen zwischen 15 und 18 °C. Eine Variable kann nur
erklären, was sie unterscheidet. Kälte wirkt am Kanal mit Sicherheit — aber vor allem über
**Abbrüche**, und die stehen nicht im Datensatz.

### 4.4 XGBoost — verworfen

Getestet mit Seezeit, Alter, Anzahl Starts, Geschlecht, Jahresabstand, Reihenfolge, Jahr und
Richtung. Bewertet auf der Kanalzeit in Stunden, 5-fach kreuzvalidiert, 20 Wiederholungen:

| Modell | MAE | vs. Basis |
|---|---|---|
| konstanter Aufschlag | **1.218** | Referenz |
| OLS (nur Seezeit) | 1.245 | +2.2 % |
| XGBoost, alle Merkmale | 1.347 | +10.6 % |
| XGBoost, Ziel = Faktor | 1.329 | +9.1 % |

Mit Hyperparameter-Suche über 81 Konfigurationen kommt XGBoost auf +3.9 % — es gewinnt also
auch dann nicht. Aufschlussreich ist *wie*: Die beste Konfiguration ist `depth=1, lr=0.02`,
also Entscheidungsstümpfe mit winziger Lernrate. Das Modell wird umso besser, je weniger es
lernen darf; im Grenzwert wäre es die Konstante. Die Suche hat nichts gefunden, sondern nur
den kürzesten Weg zurück zur Baseline.

Diese +3.9 % sind zudem geschönt: Die beste von 81 Konfigurationen wurde anhand derselben
CV-Zahl ausgewählt, gegen die sie verglichen wird. Sauber wäre nested CV. Für die
Schlussfolgerung egal, weil sie in die unbequeme Richtung zeigt.

Die Feature-Wichtigkeiten aus dem Trainingslauf (`zh_hours` 0.32, `zh_first` 0.15,
`female` 0.13) sehen nach Erkenntnis aus und sind keine — sie belohnen jeden Split, auch den
auf Rauschen.

## 5. Gefundene und behobene Fehler

Chronologisch, weil jeder davon das Ergebnis verändert hätte:

| Fehler | Wirkung | Behebung |
|---|---|---|
| Zeitformate variieren stark (`8h 03m 35s`, `3 h 39 min`, `6 h 41:08`, `5:51:41`, Tippfehler wie `10h 26h 48s`) | Jahrgang 2005 hatte 0 Endzeiten | Parser liest die ersten drei Zahlen positionell als h/m/s statt Einheitsbuchstaben zu trauen |
| 6 DNF-Zeilen trugen die Meilen-Zwischenzeit im Endzeit-Feld | Phantom-Finisher | gilt jetzt als Zwischenzeit |
| HC-Schwimmer starteten in Meilen, also kürzere Strecke | Spitzengeschwindigkeiten frei erfunden | keine km/h für HC |
| `speed_kmh` als TEXT in SQLite | Frontend brach beim Start | Spaltentypen korrigiert |
| Doppelvornamen doppelt gefunden (Anna-Carin unter „anna" *und* „anna carin") | n = 167 statt 163 | Deduplizierung auf das Schwimm-Paar |
| Fallzahlen im Markup hartkodiert | drifteten nach der Korrektur auseinander | kommen jetzt aus den Daten |

## 6. Methodische Festlegungen

**Bewertet wird in Stunden, nie im Faktor.** Der Faktor ist mechanisch `1 + Aufschlag/Seezeit`
— eine Identität, keine empirische Beziehung. Gibt man die Seezeit als Merkmal und sagt den
Faktor voraus, steckt das Merkmal im Nenner des Ziels; das Modell senkt seinen Fehler, indem
es eine Definition nachbaut. Zudem wird ein Faktorfehler beim Zurückrechnen mit der Seezeit
multipliziert: 0.05 kosten bei 7 h Seezeit 21 Minuten, bei 12 h aber 36. Ein auf den Faktor
optimiertes Modell vernachlässigt die langsamen Schwimmer systematisch.

**Kreuzvalidierung statt einzelnem Holdout.** Bei n = 163 lässt ein 80/20-Split 33 Zeilen zum
Bewerten. Über 15 Seeds schwankte die Baseline zwischen MAE 1.043 und 1.482, und in 2 von 15
Fällen hätte XGBoost gewonnen. Verwendet wird 5-fach × 20–40 Wiederholungen.

**Residual-SD 0 ist nicht das Ziel.** Ein tiefes, unreguliertes XGBoost erreicht 0.001 h im
Training und 1.978 kreuzvalidiert — es lernt die 163 Zeiten auswendig. Der konstante
Aufschlag ist das einzige Modell, das kreuzvalidiert minimal *besser* abschneidet als im
Training (1.643 gegen 1.658). Ziel ist das Niveau des echten Rauschens, keinen Millimeter
tiefer.

## 7. Belastbarkeit des Abgleichs

Kein Paar beruht allein auf dem Namen:

| Beleg | Paare |
|---|---|
| Geburtsjahr auf beiden Seiten, Abweichung ≤ 2 Jahre | 132 |
| Geschlecht und Nationalitätsgruppe stimmen überein | 30 |
| manuell geprüft und dokumentiert | 1 |

Das Geburtsjahr war der Glücksfall: Die Kanal-Datenbank führt das Alter beim Schwimmen, der
Zürichsee den Jahrgang. Bei 132 Paaren liess sich das gegenrechnen — **alle stimmen, kein
einziger Widerspruch.** Es schlägt die Nationalität, weil international startende
Freiwasserschwimmer häufig Doppelbürger oder Auswanderer sind; sieben Paare mit
widersprüchlicher Nationalität sind übers Geburtsjahr bestätigt.

Ein Fall brauchte eine Handentscheidung: **Bhakti Sharma** ist im Kanal-Datensatz als
männlich erfasst — ein Fehler der Quelle. Dokumentiert in `OVERRIDES` in `match_channel.py`,
nicht stillschweigend korrigiert.

## 8. Was offen bleibt

**Die grösste Einschränkung ist keine Rechenfrage:** Die Channel-Datenbank enthält nur
ratifizierte, erfolgreiche Querungen. Alle Aussagen gelten unter der Bedingung, dass man
ankommt. Über die Erfolgswahrscheinlichkeit — und damit über den vermutlich stärksten Effekt
von Kälte und Wetter — sagen diese Daten nichts.

**Schwächste Stelle im Modell:** über 11 h Seezeit liegen nur 24 Paare vor, und ihre
Kanalzeiten streuen breiter als das Band abbildet (Abdeckung dort 83 % statt 95 %).
Vermutlich Survivorship — langsame Querungen werden häufiger abgebrochen.

**Was tatsächlich helfen würde**, ist kein stärkerer Lerner, sondern Merkmale, die wir nicht
haben: Windstärke und -richtung am Tag der Querung, der Pilot und seine Routenwahl, das
Trainingsvolumen der Vorsaison, und vor allem die abgebrochenen Versuche.

**Nicht geprüft:** die Jahrgänge 1987–2001 (nur Scans ohne Textlayer, OCR nötig). Sie würden
den Datensatz um rund die Hälfte vergrössern und wären der billigste Weg zu mehr Fällen in
den dünn besetzten Randbereichen.

---

## Reproduzieren

```bash
.venv/bin/python srichinmoy/match_channel.py -v   # Abgleich, Konfidenzstufen
.venv/bin/python srichinmoy/tides.py annotate     # Tidenhub je Querung
.venv/bin/python srichinmoy/tides.py validate     # Rückextrapolation gegen den Mond
.venv/bin/python srichinmoy/project.py            # Formvergleich, Modell, Tide
.venv/bin/python srichinmoy/experiment_ml.py      # XGBoost-Gegenprobe
.venv/bin/python srichinmoy/report_data.py        # Kennzahlen für den Bericht
.venv/bin/python srichinmoy/build_report.py       # bebildertes PDF
```

---
Stand: 2026-08-16 · Commit 31c2df8
