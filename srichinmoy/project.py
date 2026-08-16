"""Fit the Zürichsee → Channel projection and write the model to crossover_model.json.

The model is additive, not multiplicative: the Channel costs a roughly constant surcharge on
top of the lake time, independent of how fast the swimmer is. See `compare` for the evidence.

    Kanalzeit = Zürichseezeit + Aufschlag,   Aufschlag ~ LogNormal(mu, sigma)

Deliberately dependency-free: OLS, correlations and the log-normal fit are a handful of lines
each, and adding numpy/scipy for that would be the only heavy dependency in the project.
"""

from __future__ import annotations

import json
import math
import statistics as st
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

BASE = Path(__file__).parent
PAIRS = BASE / "crossover.json"
OUT = BASE / "crossover_model.json"

Z95 = 1.959964
Z90 = 1.644854


def hm(hours: float) -> str:
    s = int(round(abs(hours) * 3600))
    return f"{'-' if hours < 0 else ''}{s // 3600}:{(s % 3600) // 60:02d}"


def corr(u: list[float], v: list[float]) -> float:
    mu, mv = st.mean(u), st.mean(v)
    return (sum((a - mu) * (b - mv) for a, b in zip(u, v))
            / math.sqrt(sum((a - mu) ** 2 for a in u) * sum((b - mv) ** 2 for b in v)))


def ols(x: list[float], y: list[float]) -> tuple[float, float, float]:
    """Intercept, slope, residual SD."""
    mx, my = st.mean(x), st.mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    b = sum((a - mx) * (bb - my) for a, bb in zip(x, y)) / sxx
    a = my - b * mx
    resid = [yy - (a + b * xx) for xx, yy in zip(x, y)]
    return a, b, math.sqrt(sum(r * r for r in resid) / (len(x) - 2))


def compare(x: list[float], y: list[float]) -> list[tuple[str, str, float]]:
    """Candidate functional forms, so the choice of an additive model is evidenced, not asserted."""
    n = len(x)
    out = []

    a, b, s = ols(x, y)
    out.append(("linear mit Achsenabschnitt", f"{a:.2f} + {b:.3f}·ZH", s))

    k = sum(a_ * b_ for a_, b_ in zip(x, y)) / sum(a_ * a_ for a_ in x)
    r = [yy - k * xx for xx, yy in zip(x, y)]
    out.append(("proportional (durch 0)", f"{k:.3f}·ZH", math.sqrt(sum(v * v for v in r) / (n - 1))))

    la, lb, _ = ols([math.log(v) for v in x], [math.log(v) for v in y])
    r = [yy - math.exp(la + lb * math.log(xx)) for xx, yy in zip(x, y)]
    out.append(("Potenzgesetz", f"{math.exp(la):.2f}·ZH^{lb:.3f}",
                math.sqrt(sum(v * v for v in r) / (n - 2))))

    off = [yy - xx for xx, yy in zip(x, y)]
    c = st.mean(off)
    out.append(("additiv (Steigung = 1)", f"ZH + {c:.2f}",
                math.sqrt(sum((v - c) ** 2 for v in off) / (n - 1))))
    return out


@app.command()
def main(max_gap: int = typer.Option(99, help="Nur Paare mit höchstens so vielen Jahren Abstand")) -> None:
    data = json.loads(PAIRS.read_text())
    pairs = [p for p in data["pairs"] if p["gap_years"] <= max_gap]

    x = [p["zh_seconds"] / 3600 for p in pairs]
    y = [p["ch_seconds"] / 3600 for p in pairs]
    off = [b - a for a, b in zip(x, y)]
    n = len(x)

    typer.echo(f"n = {n} Paare (Jahresabstand ≤ {max_gap})\n")
    typer.echo("Funktionsform — Residual-SD in Stunden, kleiner ist besser:")
    for label, formula, s in compare(x, y):
        typer.echo(f"  {label:28s} {formula:22s} {s:.3f}")
    typer.echo("")

    # The decisive test: does the surcharge depend on the lake time? If it does not, the
    # relationship is additive and a slope is not just unnecessary but misleading.
    typer.echo(f"Korrelation Aufschlag ↔ Seezeit: {corr(off, x):+.3f}  "
               f"→ {'kein Zusammenhang, additiv' if abs(corr(off, x)) < 0.15 else 'Zusammenhang vorhanden'}")
    typer.echo(f"Korrelation Seezeit ↔ Kanalzeit: {corr(x, y):+.3f}\n")

    # Surcharge is strictly positive and right-skewed → log-normal.
    logs = [math.log(v) for v in off]
    mu, sigma = st.mean(logs), st.stdev(logs)
    med = math.exp(mu)
    lo95, hi95 = math.exp(mu - Z95 * sigma), math.exp(mu + Z95 * sigma)
    lo90, hi90 = math.exp(mu - Z90 * sigma), math.exp(mu + Z90 * sigma)

    typer.echo(f"Aufschlag lognormal: Median {hm(med)} h, "
               f"90 % {hm(lo90)}–{hm(hi90)}, 95 % {hm(lo95)}–{hm(hi95)}")
    ins = sum(1 for v in off if lo95 <= v <= hi95)
    typer.echo(f"Abdeckung des 95-%-Bands: {ins}/{n} = {100 * ins / n:.0f} %\n")

    typer.echo("Hochrechnung:")
    for zh in (7, 8, 9, 10, 11, 12):
        typer.echo(f"  Zürichsee {zh:2d}:00  →  {hm(zh + med)}   "
                   f"(95 %: {hm(zh + lo95)} – {hm(zh + hi95)})")
    typer.echo("")

    typer.echo("Aufschlag nach Tempoband — die Konstanz ist der eigentliche Befund:")
    bands = []
    for a_, b_, lbl in ((0, 8, "unter 8 h"), (8, 9.5, "8 – 9:30"),
                        (9.5, 11, "9:30 – 11 h"), (11, 99, "über 11 h")):
        sel = [o for xx, o in zip(x, off) if a_ <= xx < b_]
        cov = sum(1 for o in sel if lo95 <= o <= hi95)
        bands.append({"label": lbl, "n": len(sel), "median": st.median(sel),
                      "ratio_median": st.median([(xx + o) / xx for xx, o in zip(x, off)
                                                 if a_ <= xx < b_])})
        typer.echo(f"  {lbl:12s} n={len(sel):3d}  Median {hm(st.median(sel))} h  "
                   f"im Band {100 * cov / len(sel):3.0f} %")
    typer.echo("")

    # --- tide ---------------------------------------------------------------
    # The one external variable that carries signal, and the only one a swimmer knows
    # in advance: the tidal range of the booked slot. Fitted on log(surcharge) so the
    # model stays multiplicative on the surcharge and the band stays asymmetric.
    tide_pairs = [p for p in pairs if p.get("tide_spring")]
    tide = None
    if len(tide_pairs) >= 50:
        tx = [p["tide_spring"] for p in tide_pairs]
        ty = [math.log((p["ch_seconds"] - p["zh_seconds"]) / 3600) for p in tide_pairs]
        ta, tb, ts = ols(tx, ty)
        tr = corr([p["ch_seconds"] / 3600 - p["zh_seconds"] / 3600 for p in tide_pairs], tx)
        tide = {"n": len(tide_pairs), "a": ta, "b": tb, "sigma": ts, "r": tr,
                "xmin": min(tx), "xmax": max(tx)}
        typer.echo(f"Tidenhub (n = {len(tide_pairs)}): Korrelation mit dem Aufschlag "
                   f"r = {tr:+.3f}")
        typer.echo(f"  log(Aufschlag) = {ta:.3f} + {tb:.3f} · Tidenfaktor   (Streuung {ts:.3f})")
        for f, lbl in ((0.45, "Nipptide"), (0.60, "Richtung Nipp"),
                       (0.80, "Mitte"), (1.00, "Springtide")):
            typer.echo(f"    {lbl:15s} Faktor {f:.2f}  →  Aufschlag {hm(math.exp(ta + tb * f))} h")
        typer.echo("")

    typer.echo("Nebenbefunde (Abweichung vom Median-Aufschlag):")
    for label, sel in (
        ("Frauen", [i for i, p in enumerate(pairs) if p["gender"] == "F"]),
        ("Männer", [i for i, p in enumerate(pairs) if p["gender"] == "M"]),
        ("Zürichsee zuerst", [i for i, p in enumerate(pairs) if p["zh_first"]]),
        ("Kanal zuerst", [i for i, p in enumerate(pairs) if not p["zh_first"]]),
    ):
        if len(sel) >= 15:
            v = [off[i] for i in sel]
            typer.echo(f"  {label:18s} n={len(v):3d}  Median {hm(st.median(v))} h "
                       f"({st.median(v) - med:+.2f} h)")

    OUT.write_text(json.dumps({
        "model": {
            "type": "additive_lognormal",
            "n": n,
            "mu": mu, "sigma": sigma,
            "median": med,
            "lo95": lo95, "hi95": hi95, "lo90": lo90, "hi90": hi90,
            "r": corr(x, y),
            "corr_surcharge_vs_time": corr(off, x),
            "xmin": min(x), "xmax": max(x),
        },
        "tide": tide,
        "alternatives": [{"label": l, "formula": f, "resid_sd": s} for l, f, s in compare(x, y)],
        "bands": bands,
        "pairs": [{
            "name": p["name"], "gender": p["gender"],
            "zh_year": p["zh_year"], "zh_seconds": p["zh_seconds"],
            "ch_year": p["ch_year"], "ch_seconds": p["ch_seconds"],
            "gap_years": p["gap_years"], "zh_first": p["zh_first"],
            "ratio": p["ratio"],
            "surcharge": round((p["ch_seconds"] - p["zh_seconds"]) / 3600, 4),
            "grade": p["grade"], "zh_nat": p["zh_nat"], "zh_club": p["zh_club"],
            "ch_date": p.get("ch_date"),
            "tide_spring": p.get("tide_spring"),
        } for p in pairs],
    }, ensure_ascii=False, indent=1))
    typer.echo(f"\n→ {OUT.name}")


if __name__ == "__main__":
    app()
