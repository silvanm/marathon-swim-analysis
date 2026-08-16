"""Kennzahlen für den Forschungsbericht — alles frisch aus den Daten gerechnet.

Schreibt `report_data.json`, aus dem `build_report.py` die Grafiken zeichnet. Getrennt
gehalten, damit die Zahlen im PDF nachweislich aus `crossover.json` stammen und nicht aus
dem Fliesstext von RESEARCH.md abgeschrieben sind.

    .venv/bin/python srichinmoy/report_data.py
"""

from __future__ import annotations

import csv
import json
import math
import random
import sqlite3
import statistics as st
from collections import defaultdict
from pathlib import Path

import typer

BASE = Path(__file__).parent
DB = BASE / "marathon_swim.sqlite"
SST = BASE.parent.parent / "260812_channel_simulation" / "kanal_sst_monatsmittel.csv"

app = typer.Typer(add_completion=False)


# ── kleine Statistikwerkzeuge (keine Abhängigkeiten, damit das Skript überall läuft) ──

def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else 0.0


def ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Achsenabschnitt, Steigung."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((a - mx) ** 2 for a in xs)
    b = sum((a - mx) * (c - my) for a, c in zip(xs, ys)) / sxx
    return my - b * mx, b


def ols2(xs: list[tuple[float, float]], ys: list[float]) -> tuple[float, float, float]:
    """Zwei Merkmale, Normalgleichungen von Hand — a, b1, b2."""
    n = len(ys)
    m1 = sum(x[0] for x in xs) / n
    m2 = sum(x[1] for x in xs) / n
    my = sum(ys) / n
    s11 = sum((x[0] - m1) ** 2 for x in xs)
    s22 = sum((x[1] - m2) ** 2 for x in xs)
    s12 = sum((x[0] - m1) * (x[1] - m2) for x in xs)
    s1y = sum((x[0] - m1) * (y - my) for x, y in zip(xs, ys))
    s2y = sum((x[1] - m2) * (y - my) for x, y in zip(xs, ys))
    det = s11 * s22 - s12 * s12
    b1 = (s22 * s1y - s12 * s2y) / det
    b2 = (s11 * s2y - s12 * s1y) / det
    return my - b1 * m1 - b2 * m2, b1, b2


def boot_ci(xs: list[float], ys: list[float], stat, draws: int = 2000,
            seed: int = 7) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(xs)
    vals = []
    for _ in range(draws):
        idx = [rng.randrange(n) for _ in range(n)]
        try:
            vals.append(stat([xs[i] for i in idx], [ys[i] for i in idx]))
        except (ZeroDivisionError, ValueError):
            pass
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]


def sst_lookup() -> dict:
    """(Jahr, Monat) → Wassertemperatur; für Jahre vor 2015 das Monatsmittel aller Jahre."""
    by_year, mean = {}, {}
    for row in csv.DictReader(SST.open()):
        m = int(row["month"])
        vals = []
        for k, v in row.items():
            if k != "month" and v:
                by_year[(int(k), m)] = float(v)
                vals.append(float(v))
        mean[m] = sum(vals) / len(vals)
    return {"year": by_year, "mean": mean}


def sst_for(temps: dict, year: int, month: int | None) -> float | None:
    if not month:
        return None
    return temps["year"].get((year, month)) or temps["mean"][month]


# ── Hauptlauf ──

@app.command()
def main() -> None:
    pairs = json.loads((BASE / "crossover.json").read_text())["pairs"]
    model = json.loads((BASE / "crossover_model.json").read_text())
    temps = sst_lookup()

    con = sqlite3.connect(DB)
    for p in pairs:
        p["zh_h"] = p["zh_seconds"] / 3600
        p["ch_h"] = p["ch_seconds"] / 3600
        p["surcharge"] = p["ch_h"] - p["zh_h"]
        p["month"] = int(p["ch_date"][5:7]) if p.get("ch_date") else None
        p["sst"] = sst_for(temps, p["ch_year"], p["month"])
        # Alter und Startzahl wie in experiment_ml.py: das Alter über die Jahrgangskette,
        # die Startzahl nur bis zum gepaarten Jahr — ein prospektives Modell kennt keine
        # künftigen Starts.
        yob = (p["zh_yob"]
               or (p["zh_year"] - p["zh_age"] if p["zh_age"] else None)
               or (p["ch_year"] - p["ch_age"] if p["ch_age"] else None))
        p["age"] = p["zh_year"] - yob if yob else None
        p["n_prior"] = min(con.execute(
            "select count(*) from results where relay=0 and status='FINISHED' and wetsuit=0 "
            "and lower(last_name)=? and year<=?",
            (p["name"].split()[-1].lower(), p["zh_year"]),
        ).fetchone()[0], 5)

    m = model["model"]
    mu, sigma = m["mu"], m["sigma"]

    # 1 ── Streudiagramm: Punkte + Modellband
    scatter = [{"x": round(p["zh_h"], 4), "y": round(p["ch_h"], 4),
                "g": p["gender"], "n": p["name"]} for p in pairs]

    # 2 ── Verteilung des Aufschlags: Histogramm + Lognormal-Dichte
    sur = sorted(p["surcharge"] for p in pairs)
    width, top = 0.5, 10.0
    hist = [0] * int(top / width)
    for s in sur:
        hist[min(int(s / width), len(hist) - 1)] += 1
    density = []
    x = 0.05
    while x <= top:
        d = math.exp(-((math.log(x) - mu) ** 2) / (2 * sigma ** 2)) / (
            x * sigma * math.sqrt(2 * math.pi))
        density.append([round(x, 3), round(d * len(sur) * width, 4)])
        x += 0.05

    # 3 ── Abdeckung des 95-%-Bands je Tempoband
    lo, hi = m["lo95"], m["hi95"]
    bands = [("unter 8 h", 0, 8), ("8 – 9:30", 8, 9.5),
             ("9:30 – 11 h", 9.5, 11), ("über 11 h", 11, 99)]
    coverage = []
    for label, a, b in bands:
        grp = [p for p in pairs if a <= p["zh_h"] < b]
        inside = sum(1 for p in grp if lo <= p["surcharge"] <= hi)
        coverage.append({"label": label, "n": len(grp),
                         "covered": inside, "pct": 100 * inside / len(grp)})
    total_cov = sum(c["covered"] for c in coverage)

    # 4 ── Merkmalsprüfung: Korrelation mit dem Aufschlag, mit Bootstrap-KI
    def feature(label: str, get, subset=None) -> dict:
        rows = [p for p in (subset or pairs) if get(p) is not None]
        xs = [float(get(p)) for p in rows]
        ys = [p["surcharge"] for p in rows]
        r = pearson(xs, ys)
        ci = boot_ci(xs, ys, pearson)
        return {"label": label, "n": len(rows), "r": round(r, 4),
                "lo": round(ci[0], 4), "hi": round(ci[1], 4)}

    features = [
        feature("Tidenhub am Tag der Querung", lambda p: p.get("tide_spring")),
        feature("Saisonmitte |Monat − 8|", lambda p: abs(p["month"] - 8) if p["month"] else None),
        feature("Jahresabstand der Schwimmen", lambda p: p["gap_years"]),
        feature("Wassertemperatur (°C)", lambda p: p["sst"]),
        feature("Reihenfolge (See zuerst)", lambda p: 1 if p["zh_first"] else 0),
        feature("Zürichsee-Zeit", lambda p: p["zh_h"]),
        feature("Anzahl bisheriger Starts", lambda p: p["n_prior"]),
        feature("Jahr der Querung", lambda p: p["ch_year"]),
        feature("Geschlecht (weiblich)", lambda p: 1 if p["gender"] == "F" else 0),
        feature("Alter beim Schwimmen", lambda p: p["age"]),
    ]
    features.sort(key=lambda f: -abs(f["r"]))

    # 5 ── Tidenhub im Detail
    tp = [p for p in pairs if p.get("tide_spring")]
    ta, tb = ols([p["tide_spring"] for p in tp],
                 [math.log(p["surcharge"]) for p in tp])
    tide = {
        "n": len(tp), "a": round(ta, 4), "b": round(tb, 4),
        "points": [{"x": p["tide_spring"], "y": round(p["surcharge"], 3)} for p in tp],
        "steps": [{"label": lab, "f": f, "h": round(math.exp(ta + tb * f), 3)}
                  for lab, f in [("Nipptide", 0.45), ("Richtung Nipp", 0.60),
                                 ("Mitte", 0.80), ("Springtide", 1.00)]],
        "spread_min": round(60 * (math.exp(ta + tb * 1.0) - math.exp(ta + tb * 0.45))),
    }

    # 6 ── Monat: Median-Aufschlag, und was ohne Mai/Juni übrig bleibt
    by_month = defaultdict(list)
    for p in pairs:
        if p["month"]:
            by_month[p["month"]].append(p["surcharge"])
    names = {5: "Mai", 6: "Juni", 7: "Juli", 8: "August", 9: "September", 10: "Oktober"}
    months = [{"m": k, "label": names[k], "n": len(v), "median": round(st.median(v), 3)}
              for k, v in sorted(by_month.items())]
    late = [p for p in pairs if p["month"] and p["month"] >= 7]
    month_r = {
        "all": features[[f["label"] for f in features].index("Saisonmitte |Monat − 8|")]["r"],
        "without_may_june": round(pearson([abs(p["month"] - 8) for p in late],
                                          [p["surcharge"] for p in late]), 4),
        "n_dropped": len(pairs) - len(late) - 4,
    }

    # 7 ── Koeffizienten-KI: warum Tide gehalten hat und Temperatur nicht
    def slope(xs, ys):
        return ols(xs, ys)[1]

    # Gemeinsames Modell log(Aufschlag) ~ Tidenhub + Temperatur — so wurde entschieden.
    joint = [p for p in pairs if p.get("tide_spring") and p["sst"] is not None]
    jx = [(p["tide_spring"], p["sst"]) for p in joint]
    jy = [math.log(p["surcharge"]) for p in joint]
    coef = []
    for i, label in [(1, "Tidenhub"), (2, "Wassertemperatur")]:
        b = ols2(jx, jy)[i]
        ci = boot_ci(jx, jy, lambda a, c, i=i: ols2(a, c)[i])
        coef.append({"label": label, "b": round(b, 4),
                     "lo": round(ci[0], 4), "hi": round(ci[1], 4),
                     "excludes_zero": ci[0] > 0 or ci[1] < 0})
    coef_n = len(joint)

    # Spannweite der beiden Merkmale — die eigentliche Erklärung
    spread = []
    for label, get, unit in [("Tidenhub", lambda p: p.get("tide_spring"), ""),
                             ("Wassertemperatur", lambda p: p["sst"], " °C")]:
        vals = sorted(float(get(p)) for p in pairs if get(p) is not None)
        spread.append({"label": label, "min": round(vals[0], 2), "max": round(vals[-1], 2),
                       "ratio": round(vals[-1] / vals[0], 2), "unit": unit})

    # Belegstufen des Abgleichs direkt aus den Begründungstexten zählen
    grades = {"birth_year": 0, "gender_nat": 0, "manual": 0}
    for p_ in pairs:
        r = p_["grade_reason"]
        key = ("birth_year" if "Geburtsjahr" in r else
               "manual" if r.startswith("manuell geprüft") else "gender_nat")
        grades[key] += 1

    out = {
        "n": len(pairs),
        "model": m,
        "alternatives": sorted(model["alternatives"], key=lambda a: a["resid_sd"]),
        "scatter": scatter,
        "surcharge": {"hist": hist, "width": width, "density": density,
                      "min": round(sur[0], 3), "max": round(sur[-1], 3),
                      "median": round(st.median(sur), 3)},
        "coverage": {"bands": coverage, "total": total_cov,
                     "pct": round(100 * total_cov / len(pairs), 1)},
        "features": features,
        "tide": tide,
        "months": months,
        "month_r": month_r,
        "coef": coef, "coef_n": coef_n,
        "spread": spread,
        "funnel": [
            {"label": "Ergebnisse aus den PDFs 2002–2026", "v": 2015},
            {"label": "Namensgleiche in der Channel-DB", "v": 205},
            {"label": "nach Vergleichbarkeitsregeln", "v": 167},
            {"label": "nach Deduplizierung", "v": 163},
        ],
        "xgboost": [
            {"label": "konstanter Aufschlag", "mae": 1.218, "base": True},
            {"label": "OLS (nur Seezeit)", "mae": 1.245},
            {"label": "XGBoost, Ziel = Faktor", "mae": 1.329},
            {"label": "XGBoost, alle Merkmale", "mae": 1.347},
        ],
        "grades": grades,
    }
    (BASE / "report_data.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    typer.echo(f"n={len(pairs)} · Abdeckung {out['coverage']['pct']} % · "
               f"Tide b={tide['b']} · Merkmale {len(features)} → report_data.json")


if __name__ == "__main__":
    app()
