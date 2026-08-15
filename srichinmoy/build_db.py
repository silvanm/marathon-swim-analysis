"""Load the extracted per-year JSON files into a SQLite DB + a flat CSV.

Adds derived columns: finish_seconds, split_seconds, speed_kmh.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(add_completion=False)

BASE = Path(__file__).parent
RESULTS = BASE / "results"
DB = BASE / "marathon_swim.sqlite"
CSV = BASE / "marathon_swim.csv"

COLUMNS = [
    "year", "event_date", "event_name", "distance_km",
    "category_raw", "gender", "age_class", "wetsuit", "relay", "relay_team_name",
    "rank", "status", "last_name", "first_name", "year_of_birth", "age",
    "nationality", "home_city", "club", "start_number",
    "split_meilen", "split_seconds", "finish_time", "finish_seconds", "speed_kmh",
    "remark", "weather", "water_temp",
]

def to_seconds(value: Optional[str]) -> Optional[int]:
    """Parse the many printed time formats into seconds.

    The ranglists use at least a dozen spellings across the years — "8h 03m 35s",
    "3 h 39 min", "6 h 41:08", "5:51:41", "9:12" — plus occasional typos
    ("10h 26h 48s"). All of them are hours/minutes/seconds in that order, so we
    read the first three integers positionally instead of trusting the unit letters.
    """
    if not value:
        return None
    nums = [int(n) for n in re.findall(r"\d+", value)]
    if not nums:
        return None
    if len(nums) == 1:
        # A lone number is only meaningful with an explicit unit.
        if re.search(r"\d+\s*h", value, re.I):
            return nums[0] * 3600
        return None
    h, m, s = (nums + [0, 0])[:3]
    if m > 59 or s > 59:
        return None
    return h * 3600 + m * 60 + s


@app.command()
def main() -> None:
    rows = []
    for path in sorted(RESULTS.glob("*.json")):
        data = json.loads(path.read_text())
        dist = data.get("distance_km")
        for r in data["results"]:
            status = r.get("status")
            finish = to_seconds(r.get("finish_time"))
            split = to_seconds(r.get("split_meilen"))
            # A handful of DNF rows carry the Meilen split in the finish column
            # ("DNF ... 5h 39m, stopped at Meilen") — it is not a finish time.
            if status == "DNF" and finish is not None:
                if split is None:
                    split = finish
                finish = None
            # Only full-distance finishers get a speed. HC swimmers started at
            # Meilen, so their time covers a shorter course.
            speed = (
                round(dist / (finish / 3600), 4)
                if dist and finish and status == "FINISHED"
                else None
            )
            rows.append(
                {
                    "year": data["year"],
                    "event_date": data.get("event_date"),
                    "event_name": data.get("event_name"),
                    "distance_km": dist,
                    "weather": data.get("weather"),
                    "water_temp": data.get("water_temp"),
                    "split_seconds": split,
                    "finish_seconds": finish,
                    "speed_kmh": speed,
                    **{k: r.get(k) for k in (
                        "category_raw", "gender", "age_class", "wetsuit", "relay",
                        "relay_team_name", "rank", "status", "last_name", "first_name",
                        "year_of_birth", "age", "nationality", "home_city", "club",
                        "start_number", "split_meilen", "finish_time", "remark",
                    )},
                }
            )

    rows.sort(key=lambda r: (r["year"], r["category_raw"] or "", r["rank"] or 999))

    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)
    con.execute(f"""CREATE TABLE results (
        id INTEGER PRIMARY KEY,
        {", ".join(
            f"{c} INTEGER" if c in {
                'year', 'rank', 'year_of_birth', 'age', 'split_seconds',
                'finish_seconds', 'wetsuit', 'relay',
            } else f"{c} REAL" if c in {'distance_km', 'speed_kmh'}
            else f"{c} TEXT"
            for c in COLUMNS
        )}
    )""")
    con.executemany(
        f"INSERT INTO results ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))})",
        [tuple(r.get(c) for c in COLUMNS) for r in rows],
    )
    con.execute("CREATE INDEX idx_year ON results(year)")
    con.execute("CREATE INDEX idx_name ON results(last_name, first_name)")
    con.commit()

    with CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows({c: r.get(c) for c in COLUMNS} for r in rows)

    years = sorted({r["year"] for r in rows})
    typer.echo(f"{len(rows)} rows, {len(years)} years ({years[0]}–{years[-1]}) → {DB.name}, {CSV.name}")
    for y in years:
        n = sum(1 for r in rows if r["year"] == y)
        fin = sum(1 for r in rows if r["year"] == y and r["finish_seconds"])
        typer.echo(f"  {y}: {n:4d} rows, {fin:4d} with a finish time")


if __name__ == "__main__":
    app()
