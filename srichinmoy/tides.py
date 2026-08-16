"""Tidal range at Dover for a given date — spring tides versus neaps.

Ported from the `ASTRO` module of the Channel Solo Simulator
(../260812_channel_simulation/app.js) so this repository stays self-contained.
The constants were fitted there by complex least squares to 56 published Dover high
waters (2026-08-15..2026-09-12); they are a *timing* fit, not Admiralty harmonic
constants, and the amplitudes absorb Z0 and the shallow-water distortion of Dover's curve.

Extrapolating a 29-day fit back to 2002 is the risky part, so it is checked: over 1272
sample dates from 2002 to 2025 the spring/neap classification contradicts an
independently computed moon phase exactly once (`--validate`). That holds because the
frequencies are astronomical constants — only the amplitudes were fitted. Nodal (18.6 y)
modulation is not modelled.

    .venv/bin/python srichinmoy/tides.py annotate   # adds spring/range/moon to crossover.json
    .venv/bin/python srichinmoy/tides.py validate
"""

from __future__ import annotations

import cmath
import datetime as dt
import json
import math
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

BASE = Path(__file__).parent
PAIRS = BASE / "crossover.json"

D2R = math.pi / 180
TIDE_EPOCH = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
W_M2 = 28.9841042 * D2R                      # rad/h

# [speed − wM2 (rad/h), complex coefficient]
PARTS = [
    ((28.9841042 - 28.9841042) * D2R, complex(-0.567310, 1.642265)),   # M2
    ((30.0000000 - 28.9841042) * D2R, complex(0.805192, -0.170592)),   # S2
    ((28.4397295 - 28.9841042) * D2R, complex(-0.239403, 0.259680)),   # N2
]
RANGE_A, RANGE_B, MEAN_SPRING_RANGE = 1.4104, 1.7609, 6.16
SYNODIC = 29.530588853


def _hours(when: dt.datetime) -> float:
    return (when - TIDE_EPOCH).total_seconds() / 3600


def envelope(t: float) -> complex:
    """Z(t) — the slowly varying complex amplitude riding on the M2 carrier."""
    return sum(c * cmath.exp(1j * dw * t) for dw, c in PARTS)


def hw_near(when: dt.datetime) -> float:
    """Hours since epoch of the high water nearest `when` (Newton on the phase)."""
    t = _hours(when)
    for _ in range(25):
        ph = W_M2 * t + cmath.phase(envelope(t))
        ph = (ph + math.pi) % (2 * math.pi) - math.pi
        t -= ph / W_M2
        if abs(ph) < 1e-11:
            break
    return t


def range_at(when: dt.datetime) -> float:
    """Tidal range in metres at Dover."""
    return RANGE_A + RANGE_B * abs(envelope(hw_near(when)))


def spring_factor(when: dt.datetime) -> float:
    """Stream-strength multiplier: 1.0 at mean springs, ~0.41 at mean neaps."""
    return max(0.35, min(1.15, range_at(when) / MEAN_SPRING_RANGE))


def moon_age(when: dt.datetime) -> float:
    """Days since new moon, from the mean elongation of Moon and Sun.

    Mean longitudes only — no evection or variation terms — so this runs up to about half a
    day off around the quarters. That is fine for its only job here: an independent check
    that the fitted tide model still lands springs near new and full moon when extrapolated
    back two decades. Do not use it to date a specific new moon.
    """
    d = (when - dt.datetime(2000, 1, 1, 12, tzinfo=dt.timezone.utc)).total_seconds() / 86400
    moon_lon = (218.3162 + 13.176396 * d) % 360
    sun_lon = (280.4665 + 0.98564736 * d) % 360
    return ((moon_lon - sun_lon) % 360) / 360 * SYNODIC


def label(factor: float) -> str:
    if factor < 0.55:
        return "neaps"
    if factor < 0.75:
        return "towards neaps"
    if factor < 0.92:
        return "mid-cycle"
    if factor < 1.02:
        return "springs"
    return "big springs"


@app.command()
def annotate() -> None:
    """Add spring factor, tidal range and moon age to every pair in crossover.json."""
    data = json.loads(PAIRS.read_text())
    n = 0
    for p in data["pairs"]:
        if not p.get("ch_date"):
            p["tide_spring"] = p["tide_range"] = p["moon_age"] = None
            continue
        when = dt.datetime.fromisoformat(p["ch_date"]).replace(
            hour=12, tzinfo=dt.timezone.utc)
        p["tide_spring"] = round(spring_factor(when), 4)
        p["tide_range"] = round(range_at(when), 3)
        p["moon_age"] = round(moon_age(when), 2)
        n += 1
    PAIRS.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    typer.echo(f"Tidenhub für {n} von {len(data['pairs'])} Paaren ergänzt → {PAIRS.name}")


@app.command()
def validate(start: int = 2002, end: int = 2025) -> None:
    """Check the back-extrapolation against the moon: springs follow new/full moon by 1–2 days."""
    checked = conflicts = 0
    for year in range(start, end + 1):
        for day in range(0, 365, 7):
            when = dt.datetime(year, 1, 1, 12, tzinfo=dt.timezone.utc) + dt.timedelta(days=day)
            age, f = moon_age(when), spring_factor(when)
            dist = min(abs(age - 1.5), abs(age - 16.3), abs(age - 31.0))
            expect = "spring" if dist < 3.7 else "neap" if dist > 5.5 else "mid"
            got = "spring" if f > 0.85 else "neap" if f < 0.62 else "mid"
            checked += 1
            if expect != "mid" and got != "mid" and expect != got:
                conflicts += 1
    typer.echo(f"{start}–{end}: {checked} Stichtage, {conflicts} Widersprüche zur Mondphase "
               f"({100 * conflicts / checked:.1f} %)")


@app.command()
def show(date: str) -> None:
    """Tidal state for one date, e.g. `show 2027-08-14`."""
    when = dt.datetime.fromisoformat(date).replace(hour=12, tzinfo=dt.timezone.utc)
    f = spring_factor(when)
    typer.echo(f"{date}: Hub {range_at(when):.2f} m · Faktor {f:.3f} · {label(f)} "
               f"· Mondalter {moon_age(when):.1f} d")


if __name__ == "__main__":
    app()
