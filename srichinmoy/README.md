# Sri Chinmoy Marathon Swim (Rapperswil – Zürich, 26 km) – Resultate

Quelle: https://ch.srichinmoyraces.org/z%C3%BCrichsee-schwimmen-marathon-swim
Jahresseiten: `.../previous-results/<jahr>`

## Deliverables

| Datei | Inhalt |
|---|---|
| `marathon_swim.sqlite` | Tabelle `results`, 2015 Zeilen, 2002–2026 |
| `marathon_swim.csv` | dieselben Daten flach als CSV |
| `results/<jahr>.json` | Rohextraktion pro Jahrgang (inkl. Wetter, Wassertemperatur, Token-Usage) |
| `explorer.html` | Auswertungsseite für die Ranglisten (Suche, Filter, Diagramme) |
| `crossover.csv` / `crossover.json` | 163 Personen mit Zürichsee- **und** Ärmelkanal-Zeit |
| `crossover_model.json` | Regressionsmodell für die Hochrechnung |
| `crossover.html` | Auswertungsseite zur Hochrechnung Zürichsee → Ärmelkanal |

## Struktur

- `raw/` – heruntergeladene HTML-Jahresseiten 1987–2026
- `pdf/` – alle verlinkten Resultat-PDFs (39 Dateien, 1987–2026)
- `txt/` – Textextraktion (pypdf) der PDFs mit Textlayer (nur als Referenz; Umlaute sind teilweise verstümmelt)
- `extract.py` – Claude-API-Extraktion: PDF als Document-Block → Structured Output nach JSON-Schema
- `build_db.py` – JSONs → SQLite + CSV, inkl. Zeit-Parsing und Geschwindigkeit
- `links.json`, `manifest.csv` – Mapping Jahr → Resultat-Links bzw. PDF-Inventar

## Abdeckung

Erfasst sind **2002–2026** (23 Jahrgänge) – alle PDFs mit Textlayer.

- **1987–2001**: reine Scans ohne Textlayer. PDFs liegen in `pdf/`, sind aber nicht extrahiert.
- **1997, 2020**: keine Veranstaltung, es existiert keine Jahresseite.
- **2023**: Rennen wegen Sturm (40–65 km/h) kurz nach dem Start abgebrochen – nur Startliste, keine Rangliste.
- **1999**: zusätzlich Resultate des Mini-Marathon Swim (2.6 km), nicht in der DB.

## Schema (`results`)

| Spalte | Bemerkung |
|---|---|
| `year`, `event_date`, `event_name`, `distance_km`, `weather`, `water_temp` | pro Veranstaltung |
| `category_raw` | Kategorie-Überschrift wie gedruckt |
| `gender` | `M` / `F` / `MIXED` / `UNKNOWN` |
| `age_class` | `MAIN` / `MASTERS` / `JUNIORS` / `OPEN` / `UNKNOWN` |
| `wetsuit`, `relay`, `relay_team_name` | Neopren- bzw. Staffel-Kategorien |
| `rank`, `status` | `status`: `FINISHED` / `DNF` / `DNS` / `HC` / `OTHER` |
| `last_name`, `first_name`, `year_of_birth`, `age`, `nationality`, `home_city`, `club`, `start_number` | Person |
| `split_meilen`, `split_seconds` | Zwischenzeit bei Meilen |
| `finish_time`, `finish_seconds` | Endzeit |
| `speed_kmh` | abgeleitet: `distance_km / (finish_seconds/3600)` |
| `remark` | Bemerkungsspalte der Rangliste |

Staffeln sind pro Schwimmer als eigene Zeile erfasst; alle Mitglieder eines Teams teilen
Rang, Zeit und `relay_team_name`.

## Datenqualität

- **2015 von 2015 Namen** gegen den PDF-Textlayer verifiziert (Abweichungen nur bei Umlauten,
  wo der Textlayer fehlerhaft ist und die Extraktion korrekt).
- Keine Endzeit ausserhalb 4–16 h, keine Zwischenzeit ≥ Endzeit.
- Geschwindigkeit Einzelstarter: min 1.72, ø 2.88, max 4.19 km/h.
- 1864 Zeilen `FINISHED`, 105 `DNF`, 16 `DNS`, 10 `HC`, 20 `OTHER`.
- Zeitformate variieren stark über die Jahre (`8h 03m 35s`, `3 h 39 min`, `6 h 41:08`,
  `5:51:41`, vereinzelt Tippfehler wie `10h 26h 48s`). Der Parser liest die ersten drei
  Zahlen positionell als h/m/s statt den Einheitsbuchstaben zu vertrauen.

## Verknüpfung mit dem Ärmelkanal

`match_channel.py` gleicht die Ranglisten gegen `../channel_swims.xlsx` ab (Channel Swimming
Solo Database, 3443 ratifizierte Solo-Querungen 1875–2025), `project.py` schätzt daraus das
Prognosemodell.

**Vergleichbarkeit** — nur Einzelstarts gegen Einzelstarts:
Zürichsee `relay=0`, `status='FINISHED'`, `wetsuit=0` (Kanalregeln verbieten Neopren);
Kanal `Swim Type='Solo'` und `# Ways=1`.

**Abgleich** über normalisierte Namen (Akzente und Interpunktion entfernt), mit beiden
Nachnamen aus `Last Name [Previous Name]` und sowohl vollem Vornamen als auch erstem Token.

**Konfidenz** — jedes Paar braucht eine Bestätigung über den Namen hinaus:

| Beleg | Paare |
|---|---|
| Geburtsjahr auf beiden Seiten, Abweichung ≤ 2 Jahre | 132 |
| Geschlecht und Nationalitätsgruppe stimmen überein | 30 |
| manuell geprüft (`OVERRIDES` in `match_channel.py`) | 1 |

Das Geburtsjahr schlägt die Nationalität, weil international startende Freiwasserschwimmer
häufig Doppelbürger oder Auswanderer sind — sieben Paare mit widersprüchlicher Nationalität
sind über das Geburtsjahr eindeutig bestätigt. Kein Paar beruht allein auf dem Namen.

**Paarung** bei Mehrfachstarts: pro Person das Paar mit dem kleinsten Jahresabstand
(Median 2 Jahre), damit vergleichbare Formzustände gegenübergestellt werden.

**Modell** (Stand 2026-08-15, n = 163) — **additiv, nicht multiplikativ**:

```
Kanalzeit = Zürichseezeit + Aufschlag
Aufschlag ~ LogNormal(mu = 1.360, sigma = 0.478)
          → Median 3:53 h,  95 % zwischen 1:31 und 9:58 h
```

Die Funktionsform ist getestet, nicht angenommen (`project.py compare`, Residual-SD in Stunden):

| Modell | Formel | Residual-SD |
|---|---|---|
| additiv (Steigung = 1) | `ZH + 4.25` | **1.644** |
| linear mit Achsenabschnitt | `3.63 + 1.066·ZH` | 1.647 |
| Potenzgesetz | `2.74·ZH^0.714` | 1.651 |
| proportional durch 0 | `1.447·ZH` | 1.733 |

Entscheidend ist nicht der minimale Fit-Unterschied, sondern dass der **Aufschlag nicht vom
Tempo abhängt**: Korrelation Aufschlag ↔ Seezeit = **+0.06**. Damit ist die Steigung
überflüssig, und die naheliegende Proportionalität durch den Nullpunkt wird von den Daten
verworfen. Der Aufschlag ist strikt positiv und rechtsschief, deshalb lognormal — das ergibt
ein asymmetrisches Prognoseband statt eines symmetrischen. Abdeckung: 158 von 163 Paaren
(97 %) im 95-%-Band.

Der *Faktor* Kanal/Zürichsee sinkt entsprechend mit langsameren Zeiten (1.58 bei unter 8 h,
1.30 bei über 11 h) — das ist die arithmetische Folge eines konstanten Aufschlags und kein
eigener Effekt. Geschlecht, Reihenfolge der beiden Schwimmen und Jahresabstand zeigten keinen
belastbaren Zusatzeffekt (Abweichung vom Median-Aufschlag jeweils < 0.2 h).

Schwächste Stelle: über 11 h Seezeit liegen nur 24 Paare vor, und ihre Kanalzeiten streuen
breiter als das Band abbildet (Abdeckung 83 %). Vermutlich Survivorship — langsame Querungen
werden häufiger abgebrochen, Abbrüche fehlen im Datensatz.

**Vorbehalt**: Die Channel-Datenbank enthält nur erfolgreiche Querungen. Die Hochrechnung gilt
unter der Bedingung, dass man ankommt, und sagt nichts über die Erfolgswahrscheinlichkeit.

## Reproduzieren

```bash
uv venv .venv && uv pip install --python .venv/bin/python anthropic typer pypdf pdfplumber
.venv/bin/python srichinmoy/extract.py            # ANTHROPIC_API_KEY nötig
.venv/bin/python srichinmoy/build_db.py
.venv/bin/python srichinmoy/match_channel.py -v   # braucht openpyxl
.venv/bin/python srichinmoy/project.py
```

`extract.py` überspringt Jahrgänge, für die bereits ein JSON existiert (`--force` überschreibt,
`--years 2010,2011` schränkt ein). Modell: `claude-sonnet-5` (die Jahrgänge 2002–2005, 2022 und
2025 wurden mit `claude-opus-5` extrahiert; kein Qualitätsunterschied feststellbar).

---
Erstellt: 2026-08-15
