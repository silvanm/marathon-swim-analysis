"""Does a gradient-boosted model beat the constant-surcharge baseline?

Honest comparison with repeated k-fold cross-validation. Two rules the experiment follows,
because breaking either produces a flattering but meaningless result:

1. Every model is scored on the **Channel time in hours** — the quantity anyone actually
   wants. Scoring on the ratio would reward a model for re-deriving the arithmetic identity
   ratio = 1 + surcharge / lake_time from a feature it was handed.
2. Everything fitted — including the baseline's median — is fitted **inside** each fold.
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics as st
from pathlib import Path

import numpy as np
import typer
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import RepeatedKFold
from xgboost import XGBRegressor

app = typer.Typer(add_completion=False)

BASE = Path(__file__).parent
PAIRS = BASE / "crossover.json"
DB = BASE / "marathon_swim.sqlite"

FEATURES = ["zh_hours", "age", "n_zh_swims", "female", "gap_years", "zh_first",
            "ch_year", "france_england"]


def build() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    pairs = json.loads(PAIRS.read_text())["pairs"]
    con = sqlite3.connect(DB)

    rows, y, zh = [], [], []
    for p in pairs:
        yob = (p["zh_yob"]
               or (p["zh_year"] - p["zh_age"] if p["zh_age"] else None)
               or (p["ch_year"] - p["ch_age"] if p["ch_age"] else None))
        # Count only swims up to the paired year: a prospective model cannot know how often
        # someone will race in the future.
        n_prior = con.execute(
            "select count(*) from results where relay=0 and status='FINISHED' and wetsuit=0 "
            "and lower(last_name)=? and year<=?",
            (p["name"].split()[-1].lower(), p["zh_year"]),
        ).fetchone()[0]
        rows.append([
            p["zh_seconds"] / 3600,
            p["zh_year"] - yob,
            min(n_prior, 5),
            1.0 if p["gender"] == "F" else 0.0,
            p["gap_years"],
            1.0 if p["zh_first"] else 0.0,
            p["ch_year"],
            1.0 if p["ch_direction"] == "F-E" else 0.0,
        ])
        y.append(p["ch_seconds"] / 3600)
        zh.append(p["zh_seconds"] / 3600)
    return np.array(rows, float), np.array(y, float), np.array(zh, float)


def scores(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float]:
    err = y_pred - y_true
    return float(np.abs(err).mean()), float(np.sqrt((err ** 2).mean()))


@app.command()
def main(repeats: int = 20, seed: int = 7) -> None:
    X, y, zh = build()
    n = len(y)
    typer.echo(f"n = {n}, Features = {FEATURES}\n")

    typer.echo("Univariat: Korrelation des Aufschlags mit jedem Feature")
    sur = y - zh
    for i, f in enumerate(FEATURES):
        col = X[:, i]
        if col.std() == 0:
            typer.echo(f"  {f:16s} konstant — kein Signal möglich")
            continue
        r = float(np.corrcoef(sur, col)[0, 1])
        typer.echo(f"  {f:16s} r = {r:+.3f}{'   ← nennenswert' if abs(r) > 0.2 else ''}")
    typer.echo("")

    models = {
        "Konstanter Aufschlag": None,
        "OLS (nur Seezeit)": "ols",
        "XGBoost (alle Features)": "xgb",
        "XGBoost, Ziel = Faktor": "xgb_ratio",
    }
    acc = {k: {"mae": [], "rmse": []} for k in models}

    cv = RepeatedKFold(n_splits=5, n_repeats=repeats, random_state=seed)
    for tr, te in cv.split(X):
        for name, kind in models.items():
            if kind is None:
                med = float(np.median(y[tr] - zh[tr]))
                pred = zh[te] + med
            elif kind == "ols":
                m = LinearRegression().fit(zh[tr].reshape(-1, 1), y[tr])
                pred = m.predict(zh[te].reshape(-1, 1))
            else:
                m = XGBRegressor(
                    n_estimators=300, max_depth=2, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8,
                    reg_lambda=2.0, min_child_weight=5,
                    random_state=0, verbosity=0,
                )
                if kind == "xgb":
                    m.fit(X[tr], y[tr])
                    pred = m.predict(X[te])
                else:
                    m.fit(X[tr], y[tr] / zh[tr])          # target: the ratio
                    pred = m.predict(X[te]) * zh[te]      # scored on hours regardless
            mae, rmse = scores(y[te], pred)
            acc[name]["mae"].append(mae)
            acc[name]["rmse"].append(rmse)

    typer.echo(f"Kreuzvalidierung: 5-fach, {repeats} Wiederholungen, "
               f"bewertet auf der Kanalzeit in Stunden\n")
    typer.echo(f"  {'Modell':26s} {'MAE':>8s} {'RMSE':>8s}")
    base = st.mean(acc["Konstanter Aufschlag"]["mae"])
    for name in models:
        mae = st.mean(acc[name]["mae"])
        rmse = st.mean(acc[name]["rmse"])
        delta = f"{(mae - base) / base * 100:+.1f} %" if name != "Konstanter Aufschlag" else "Referenz"
        typer.echo(f"  {name:26s} {mae:8.3f} {rmse:8.3f}   {delta}")
    typer.echo("")

    # What the boosted model leans on, trained once on everything (for inspection only).
    m = XGBRegressor(n_estimators=300, max_depth=2, learning_rate=0.05, subsample=0.8,
                     colsample_bytree=0.8, reg_lambda=2.0, min_child_weight=5,
                     random_state=0, verbosity=0).fit(X, y)
    imp = sorted(zip(FEATURES, m.feature_importances_), key=lambda t: -t[1])
    typer.echo("Feature-Wichtigkeit (auf allen Daten trainiert, nur zur Ansicht):")
    for f, v in imp:
        typer.echo(f"  {f:16s} {v:.3f}  {'█' * int(round(v * 40))}")


if __name__ == "__main__":
    app()
