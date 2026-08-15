"""Assemble the two analysis pages into standalone HTML documents in docs/.

Each page is kept as separate sources under pages/<name>/ — shell.html for markup and CSS,
app.js for behaviour — and the data is embedded at build time as a JSON island. That keeps
the sources editable; the files in docs/ are build output and should not be hand-edited.

    .venv/bin/python srichinmoy/build_pages.py
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

BASE = Path(__file__).parent
PAGES = BASE / "pages"
DOCS = BASE.parent / "docs"
DB = BASE / "marathon_swim.sqlite"
MODEL = BASE / "crossover_model.json"

RESULT_COLS = [
    "year", "rank", "status", "last_name", "first_name", "year_of_birth", "age",
    "nationality", "home_city", "club", "gender", "age_class", "wetsuit", "relay",
    "relay_team_name", "split_seconds", "finish_seconds", "speed_kmh", "category_raw",
]

SKELETON = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<style>:root{{color-scheme:light dark}}html,body{{margin:0;padding:0}}</style>
</head>
<body>
<p style="font-family:system-ui,sans-serif;font-size:13px;padding:10px 20px 0;margin:0">
<a href="./" style="color:#0a6e9e;text-decoration:none">&larr; Übersicht</a>
</p>
{shell}
<script id="data" type="application/json">{data}</script>
<script>
{js}
</script>
</body>
</html>
"""


def explorer_data() -> dict:
    """Every result row, plus per-event metadata, as compact column/row arrays."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = []
    for r in con.execute(
        f"select {','.join(RESULT_COLS)} from results order by year, finish_seconds"
    ):
        rows.append([r[c] for c in RESULT_COLS])
    meta = {
        y: {"date": d, "dist": km, "weather": w, "temp": t}
        for y, d, km, w, t in con.execute(
            "select year, min(event_date), min(distance_km), min(weather), min(water_temp) "
            "from results group by 1"
        )
    }
    return {"cols": RESULT_COLS, "rows": rows, "meta": meta}


def crossover_data() -> dict:
    return json.loads(MODEL.read_text())


BUILDS = [
    ("explorer", explorer_data,
     "Ergebnisse des Sri Chinmoy Marathon-Schwimmens auf dem Zürichsee, 2002 bis 2026, "
     "durchsuchbar und filterbar."),
    ("crossover", crossover_data,
     "Hochrechnung von der Zürichsee-Zeit auf die Ärmelkanal-Zeit, basierend auf 167 "
     "Personen, die beide Strecken geschwommen sind."),
]


@app.command()
def main() -> None:
    DOCS.mkdir(exist_ok=True)
    for name, loader, description in BUILDS:
        src = PAGES / name
        shell = (src / "shell.html").read_text(encoding="utf-8")
        js = (src / "app.js").read_text(encoding="utf-8")

        m = re.search(r"<title>(.*?)</title>", shell, re.S)
        title = m.group(1).strip() if m else name
        shell = re.sub(r"<title>.*?</title>\s*", "", shell, count=1, flags=re.S)

        data = json.dumps(loader(), ensure_ascii=False, separators=(",", ":"))
        # A literal </script> inside the JSON island would close the tag early.
        data = data.replace("</", "<\\/")
        if "</script" in js:
            raise SystemExit(f"{name}: app.js enthält </script> — das bricht die Seite")

        out = DOCS / f"{name}.html"
        out.write_text(
            SKELETON.format(title=title, description=description, shell=shell, data=data, js=js),
            encoding="utf-8",
        )
        typer.echo(f"{name}: {round(len(out.read_bytes()) / 1024)} KB → docs/{name}.html")


if __name__ == "__main__":
    app()
