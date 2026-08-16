"""Match Zürichsee marathon swimmers against the English Channel solo database.

Both sources identify people by name only — no birth date, no shared ID — so every pair
gets a confidence grade from the corroborating fields (gender, nationality) rather than a
plain yes/no. Grade C is written to a separate review file instead of being dropped.

Outputs: crossover.json (pairs + model input), crossover.csv, crossover_review.csv
"""

from __future__ import annotations

import csv
import datetime
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Optional

import openpyxl
import typer

app = typer.Typer(add_completion=False)

BASE = Path(__file__).parent
DB = BASE / "marathon_swim.sqlite"
XLSX = BASE.parent / "channel_swims.xlsx"
OUT_JSON = BASE / "crossover.json"
OUT_CSV = BASE / "crossover.csv"
OUT_REVIEW = BASE / "crossover_review.csv"

# Free-text nationality → country group. Both sources are hand-typed; the Zürichsee list
# even contains Swiss towns ("Wädenswil", "Elgg") in the nationality column.
NAT_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("GB", ("uk", "british", "britain", "england", "english", "scotland", "scottish",
            "wales", "welsh", "jersey", "guernsey", "gibraltar", "gb", "isle of man")),
    ("IE", ("ireland", "irish", "irland")),
    ("CH", ("swiss", "switzerland", "schweiz", "zurich", "zürich", "wadenswil", "wädenswil",
            "elgg", "erlenbach", "eschenbach", "steg", "st. gallen", "ch/", "ch ")),
    ("DE", ("german", "germany", "deutschland")),
    ("AT", ("austria", "austrian", "österreich", "osterreich")),
    ("US", ("usa", "america", "american", "united states")),
    ("AU", ("australia", "australian")),
    ("NZ", ("new zealand",)),
    ("ZA", ("south africa", "südafrika", "sudafrika", "south african")),
    ("CZ", ("czech", "tschechien", "czechoslovakia")),
    ("SK", ("slovak", "slovakia")),
    ("HU", ("hungary", "hungarian", "ungarn")),
    ("FR", ("france", "french", "frankreich")),
    ("IT", ("italy", "italian", "italia")),
    ("ES", ("spain", "spanish", "espana", "españa")),
    ("NL", ("netherland", "dutch", "holland")),
    ("BE", ("belgium", "belgian")),
    ("SE", ("sweden", "swedish")),
    ("NO", ("norway", "norwegian")),
    ("FI", ("finland", "finnish")),
    ("DK", ("denmark", "danish")),
    ("PL", ("poland", "polish")),
    ("RU", ("russia", "russian")),
    ("UA", ("ukraine", "ukrainian")),
    ("IN", ("india", "indian", "indien")),
    ("CA", ("canada", "canadian")),
    ("BR", ("brazil", "brasil", "brazilian")),
    ("AR", ("argentin",)),
    ("RO", ("romania", "romanian")),
    ("RS", ("serbia", "serbian", "yugoslavia")),
    ("HR", ("croatia", "croatian")),
    ("SI", ("slovenia", "slovenian")),
    ("GR", ("greece", "greek")),
    ("EG", ("egypt", "egyptian")),
    ("IL", ("israel", "israeli")),
    ("JP", ("japan", "japanese")),
    ("MY", ("malaysia", "malaysian")),
    ("MT", ("malta", "maltese")),
    ("LU", ("luxem",)),
    ("MD", ("moldova",)),
    ("EE", ("estonia",)),
    ("BG", ("bulgaria",)),
    ("EC", ("ecuador", "equador")),
    ("CL", ("chile",)),
    ("MX", ("mexic",)),
    ("PH", ("philippin",)),
    ("ZW", ("zimbabwe",)),
    ("TR", ("turkey", "turkish")),
]


def nat_groups(value: Optional[str]) -> set[str]:
    """Map a free-text nationality to a set of country groups (dual citizenship → 2 entries)."""
    if not value:
        return set()
    v = strip_accents(str(value).lower())
    return {code for code, keys in NAT_GROUPS if any(k in v for k in keys)}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))


def norm_name(s: Optional[str]) -> list[str]:
    if not s:
        return []
    s = strip_accents(str(s).lower())
    return re.sub(r"[^a-z ]", " ", s).split()


def name_keys(first: Optional[str], last: Optional[str]) -> set[tuple[str, str]]:
    """Candidate (first, last) keys: full first name and first token, for each surname variant."""
    f = norm_name(first)
    if not f or not last:
        return set()
    firsts = {" ".join(f), f[0]}
    keys = set()
    # "Smith [Jones]" — married and previous name are both valid surnames
    for part in re.split(r"[\[\]]", str(last)):
        l = norm_name(part)
        if l:
            keys |= {(fi, " ".join(l)) for fi in firsts}
    return keys


def hms(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


# ---------------------------------------------------------------- load sources
def load_channel() -> tuple[list[dict], dict[tuple[str, str], list[int]]]:
    ws = openpyxl.load_workbook(XLSX, read_only=True)["Solo Database"]
    rows = list(ws.iter_rows(values_only=True))
    idx = {h: i for i, h in enumerate(rows[0])}
    last_col = "Last Name\n[Previous Name]"

    swims, index = [], defaultdict(list)
    for r in rows[1:]:
        if str(r[idx["Swim Type"]]) != "Solo" or str(r[idx["# Ways"]]) != "1":
            continue
        t = r[idx["Time"]]
        if not isinstance(t, datetime.timedelta):
            continue                      # a dozen rows carry a text placeholder
        year = r[idx["Year"]]
        if not isinstance(year, int):
            continue
        age = r[idx["Age"]]
        rec = {
            "first": r[idx["First Name"]], "last": r[idx[last_col]],
            "name": str(r[idx["Full Name"]]
                        or f"{r[idx['First Name']]} {r[idx[last_col]]}").strip(),
            "year": year, "seconds": int(t.total_seconds()),
            "gender": str(r[idx["Gender"]] or ""),
            "nat": str(r[idx["Nationality when swam"]] or ""),
            "direction": str(r[idx["Direction"]] or ""),
            "date": (r[idx["Swim Depart Date"]].date().isoformat()
                     if isinstance(r[idx["Swim Depart Date"]], datetime.datetime) else None),
            "age": float(age) if isinstance(age, (int, float)) else None,
        }
        i = len(swims)
        swims.append(rec)
        for k in name_keys(rec["first"], rec["last"]):
            index[k].append(i)
    return swims, index


def load_zurich() -> tuple[list[dict], dict[tuple[str, str], list[int]]]:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    swims, index = [], defaultdict(list)
    for r in con.execute(
        "select * from results where relay=0 and status='FINISHED' "
        "and wetsuit=0 and finish_seconds is not null"
    ):
        rec = {
            "first": r["first_name"], "last": r["last_name"],
            "name": f"{r['first_name']} {r['last_name']}".strip(),
            "year": r["year"], "seconds": r["finish_seconds"],
            "gender": r["gender"], "nat": r["nationality"] or "",
            "club": r["club"] or "", "city": r["home_city"] or "",
            "yob": r["year_of_birth"], "age": r["age"], "speed": r["speed_kmh"],
        }
        i = len(swims)
        swims.append(rec)
        for k in name_keys(rec["first"], rec["last"]):
            index[k].append(i)
    return swims, index


# Documented manual decisions for cases the automatic rules cannot settle.
# Keyed by the normalised "first last" match key.
OVERRIDES: dict[str, tuple[str, str]] = {
    "bhakti sharma": ("A", "Geschlecht im Kanal-Datensatz falsch erfasst — Bhakti Sharma ist "
                           "Schwimmerin; beide Einträge Indien 2006"),
}


def birth_year(swim: dict, side: str) -> Optional[float]:
    """Implied year of birth, from an explicit birth year or from the age at the swim."""
    if side == "zh" and swim.get("yob"):
        return float(swim["yob"])
    if swim.get("age"):
        return swim["year"] - float(swim["age"])
    return None


def grade(zs: list[dict], cs: list[dict]) -> tuple[str, str]:
    """Confidence grade for a candidate person match, plus the reason.

    Year of birth is the strongest discriminator available: it is present on both sides for
    about four fifths of the candidates, and a coincidental name collision would almost
    certainly disagree. It therefore outranks nationality, which is unreliable in this
    population — international open-water swimmers are routinely dual nationals or expats.
    """
    zy = [b for b in (birth_year(s, "zh") for s in zs) if b]
    cy = [b for b in (birth_year(s, "ch") for s in cs) if b]
    if zy and cy:
        best = min(abs(a - b) for a in zy for b in cy)
        if best <= 2:
            return "A", f"Geburtsjahr stimmt überein (±{best:.0f} Jahre)"
        if best > 3:
            return "C", f"Geburtsjahr widersprüchlich ({best:.0f} Jahre auseinander)"

    zg = {s["gender"] for s in zs} - {"UNKNOWN", "MIXED"}
    cg = {s["gender"] for s in cs} - {""}
    if zg and cg and not (zg & cg):
        return "C", "Geschlecht widersprüchlich"

    zn = set().union(*(nat_groups(s["nat"]) for s in zs)) if zs else set()
    cn = set().union(*(nat_groups(s["nat"]) for s in cs)) if cs else set()
    if not zn or not cn:
        return "B", "Nur Name und Geschlecht, kein Geburtsjahr"
    if zn & cn:
        return "A", "Geschlecht und Nationalität stimmen überein"
    return "C", f"Nationalität widersprüchlich ({'/'.join(sorted(zn))} vs {'/'.join(sorted(cn))})"


@app.command()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    channel, c_index = load_channel()
    zurich, z_index = load_zurich()

    pairs = []
    for key in sorted(set(c_index) & set(z_index)):
        zs = [zurich[i] for i in z_index[key]]
        cs = [channel[i] for i in c_index[key]]
        g, why = grade(zs, cs)
        if " ".join(key) in OVERRIDES:
            g, why = OVERRIDES[" ".join(key)]
            why = "manuell geprüft: " + why

        # Pair the two swims closest in time; ties go to the earlier Channel crossing.
        z, c = min(
            ((z, c) for z in zs for c in cs),
            key=lambda p: (abs(p[0]["year"] - p[1]["year"]), p[1]["year"]),
        )
        pairs.append({
            "key": " ".join(key),
            "name": z["name"],
            "channel_name": c["name"],
            "grade": g,
            "grade_reason": why,
            "gender": (z["gender"] if z["gender"] in ("M", "F") else c["gender"]),
            "zh_year": z["year"], "zh_seconds": z["seconds"], "zh_speed": z["speed"],
            "zh_nat": z["nat"], "zh_club": z["club"], "zh_city": z["city"],
            "zh_yob": z["yob"], "zh_age": z["age"], "zh_swims": len(zs),
            "ch_year": c["year"], "ch_seconds": c["seconds"],
            "ch_nat": c["nat"], "ch_direction": c["direction"], "ch_age": c["age"],
            "ch_date": c["date"],
            "ch_swims": len(cs),
            "gap_years": abs(z["year"] - c["year"]),
            "zh_first": z["year"] <= c["year"],
            "ratio": round(c["seconds"] / z["seconds"], 4),
        })

    # A person with a double first name ("Anna-Carin") is found under both the full first
    # name and the first token, so the same swim pair can arrive twice. Keep one entry per
    # actual pair of swims, preferring the more specific key.
    best: dict[tuple, dict] = {}
    for p in pairs:
        ident = (p["name"], p["zh_year"], p["zh_seconds"], p["ch_year"], p["ch_seconds"])
        prev = best.get(ident)
        if prev is None or len(p["key"].split()) > len(prev["key"].split()):
            best[ident] = p
    duplicates = len(pairs) - len(best)
    pairs = sorted(best.values(), key=lambda p: p["key"])

    used = [p for p in pairs if p["grade"] in ("A", "B")]
    review = [p for p in pairs if p["grade"] == "C"]

    OUT_JSON.write_text(json.dumps({
        "generated_from": {"zurich_db": DB.name, "channel_xlsx": XLSX.name},
        "rules": {
            "zurich": "relay=0, status=FINISHED, wetsuit=0",
            "channel": "Swim Type=Solo, # Ways=1",
            "pairing": "kleinster Jahresabstand je Person",
            "grades_used": ["A", "B"],
        },
        "pairs": used,
        "review": review,
    }, ensure_ascii=False, indent=1))

    fields = list(pairs[0].keys()) if pairs else []
    for path, rows in ((OUT_CSV, used), (OUT_REVIEW, review)):
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, delimiter=";")
            w.writeheader()
            w.writerows(rows)

    by_grade = {g: sum(1 for p in pairs if p["grade"] == g) for g in "ABC"}
    typer.echo(f"Kandidaten gesamt: {len(pairs)}  →  A {by_grade['A']} · B {by_grade['B']} · C {by_grade['C']}")
    typer.echo(f"Doppeltreffer entfernt (Doppelvornamen): {duplicates}")
    typer.echo(f"Für die Auswertung verwendet (A+B): {len(used)}")
    gaps = sorted(p["gap_years"] for p in used)
    if gaps:
        typer.echo(f"Jahresabstand: Median {gaps[len(gaps) // 2]}, max {gaps[-1]}, "
                   f"≤3 Jahre bei {sum(1 for g in gaps if g <= 3)} Paaren")
    typer.echo(f"Zur Prüfung in {OUT_REVIEW.name}: {len(review)}")
    if verbose:
        for p in review:
            typer.echo(f"  C  {p['name']:32s} {p['grade_reason']}  "
                       f"ZH {p['zh_year']} / CH {p['ch_year']}")


if __name__ == "__main__":
    app()
