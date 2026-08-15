# Marathon Swim Analysis — Zürichsee & Ärmelkanal

Alle Ranglisten des Sri Chinmoy Marathon-Schwimmens (Rapperswil–Zürich, 26 km) von 2002 bis
2026, aus den Original-PDFs des Veranstalters extrahiert, plus eine Verknüpfung mit der
Channel Swimming Solo Database.

**→ [Auswertungen ansehen](https://silvanm.github.io/marathon-swim-analysis/)**

| | |
|---|---|
| [Die Ranglisten](https://silvanm.github.io/marathon-swim-analysis/explorer.html) | 2015 Ergebnisse aus 23 Jahrgängen, durchsuchbar und filterbar |
| [Die Hochrechnung](https://silvanm.github.io/marathon-swim-analysis/crossover.html) | Was eine Zürichsee-Zeit über die Ärmelkanal-Zeit sagt |

## Der Befund

Der Ärmelkanal kostet keinen *Faktor* auf die Seezeit, sondern einen festen Aufschlag:

```
Kanalzeit = Zürichseezeit + 3:53 h        (95 %: +1:31 bis +9:58, n = 163)
```

Die Korrelation zwischen Aufschlag und Seezeit beträgt **+0,06** — er hängt praktisch nicht
vom Tempo ab. Vier Funktionsformen wurden getestet; die naheliegende Proportionalität durch
den Nullpunkt passt am schlechtesten. Details in [`srichinmoy/README.md`](srichinmoy/README.md).

## Aufbau

```
srichinmoy/
  extract.py        PDFs → strukturiertes JSON (Claude API, ein Aufruf pro Jahrgang)
  build_db.py       JSONs → SQLite + CSV, Zeit-Parsing und Geschwindigkeit
  match_channel.py  Namensabgleich mit der Channel-Datenbank, mit Konfidenzstufen
  project.py        Modellvergleich und Hochrechnung
  build_pages.py    Artifact-Seiten → eigenständige HTML-Dateien in docs/
  results/          Rohextraktion pro Jahrgang
  *.sqlite *.csv    abgeleitete Daten
docs/               GitHub Pages
```

## Selber laufen lassen

```bash
uv venv .venv
uv pip install --python .venv/bin/python anthropic typer pypdf openpyxl

.venv/bin/python srichinmoy/extract.py        # ANTHROPIC_API_KEY nötig, ~10 $ für alle Jahrgänge
.venv/bin/python srichinmoy/build_db.py
.venv/bin/python srichinmoy/match_channel.py -v
.venv/bin/python srichinmoy/project.py
```

Die abgeleiteten Daten liegen im Repository, die Extraktion muss also nur laufen, wenn ein
neuer Jahrgang dazukommt.

## Was nicht im Repository liegt

- **`channel_swims.xlsx`** — die Channel Swimming Solo Database gehört ihren Herausgebern und
  wird hier nicht weiterverbreitet. `match_channel.py` erwartet sie im Wurzelverzeichnis.
- **Die Original-PDFs und HTML-Seiten** (~22 MB). Die Bezugs-URLs stehen in
  `srichinmoy/links.json`.

## Daten und Personen

Die Ranglisten sind öffentlich publizierte Wettkampfergebnisse und enthalten Namen, Jahrgänge,
Wohnorte und Vereine. Sie sind hier maschinenlesbar aufbereitet, was die Auffindbarkeit erhöht.
Wer als betroffene Person die Entfernung eines Eintrags wünscht, eröffne bitte ein Issue.

## Lizenz

Code unter MIT. Die Wettkampfergebnisse selbst stammen vom Sri Chinmoy Marathon Team Schweiz
und stehen nicht unter dieser Lizenz.

---
Stand: 2026-08-15
