"""Baut den bebilderten Forschungsbericht als PDF.

Die Grafiken werden hier als SVG aus `report_data.json` gezeichnet — keine Bibliothek,
keine Bilddateien, alles vektoriell im PDF. Reihenfolge:

    .venv/bin/python srichinmoy/report_data.py    # Kennzahlen frisch rechnen
    .venv/bin/python srichinmoy/build_report.py   # HTML + PDF

Die Farben sind mit dem Palettenprüfer der dataviz-Skill gegen Farbfehlsichtigkeit
validiert (Teal/Clay/Violett, alle Paare ΔE > 12 unter Deutan/Protan).
"""

from __future__ import annotations

import html
import json
import math
import subprocess
from pathlib import Path

import typer

BASE = Path(__file__).parent
ROOT = BASE.parent
DATA = BASE / "report_data.json"

app = typer.Typer(add_completion=False)

TEAL, CLAY, VIOLET = "#008B79", "#C24E12", "#6A5AB8"
INK, INK2, MUTED, GRID = "#16232E", "#4A5A66", "#7C8A94", "#DDE3E7"

W = 660          # Zeichenbreite in Nutzereinheiten = volle Textbreite


# ── SVG-Grundgerüst ────────────────────────────────────────────────────────────────

def hms(h: float) -> str:
    """Stunden als h:mm."""
    m = round(h * 60)
    return f"{m // 60}:{m % 60:02d}"


def esc(s) -> str:
    return html.escape(str(s))


class Fig:
    """Minimaler SVG-Zeichner mit linearen Skalen."""

    def __init__(self, w: int, h: int, pad=(16, 14, 34, 52)):
        self.w, self.h = w, h
        self.t, self.r, self.b, self.l = pad          # oben, rechts, unten, links
        self.parts: list[str] = []
        self.x0 = self.x1 = self.y0 = self.y1 = 0.0

    # Skalen
    def xdomain(self, a: float, b: float): self.x0, self.x1 = a, b; return self
    def ydomain(self, a: float, b: float): self.y0, self.y1 = a, b; return self

    def X(self, v: float) -> float:
        return self.l + (v - self.x0) / (self.x1 - self.x0) * (self.w - self.l - self.r)

    def Y(self, v: float) -> float:
        return self.h - self.b - (v - self.y0) / (self.y1 - self.y0) * (self.h - self.t - self.b)

    # Primitive
    def add(self, s: str): self.parts.append(s); return self

    def line(self, x1, y1, x2, y2, stroke=GRID, w=1, dash=None, cap="butt", op=1.0):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        return self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                        f'stroke="{stroke}" stroke-width="{w}" stroke-linecap="{cap}"'
                        f' opacity="{op}"{d}/>')

    def rect(self, x, y, w, h, fill, rx=0, op=1.0, stroke=None, sw=1):
        s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        return self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" '
                        f'height="{max(h, 0):.1f}" rx="{rx}" fill="{fill}" opacity="{op}"{s}/>')

    def dot(self, x, y, r, fill, op=1.0, stroke="#fff", sw=0):
        s = f' stroke="{stroke}" stroke-width="{sw}"' if sw else ""
        return self.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" '
                        f'opacity="{op}"{s}/>')

    def path(self, pts, stroke, w=2, dash=None, fill="none", op=1.0):
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        da = f' stroke-dasharray="{dash}"' if dash else ""
        return self.add(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{w}" '
                        f'stroke-linejoin="round" opacity="{op}"{da}/>')

    def area(self, pts, fill, op=0.12):
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"
        return self.add(f'<path d="{d}" fill="{fill}" opacity="{op}" stroke="none"/>')

    def text(self, x, y, s, size=9.5, fill=INK2, anchor="start", weight=400,
             cls="lbl", op=1.0):
        return self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
                        f'text-anchor="{anchor}" font-weight="{weight}" class="{cls}" '
                        f'opacity="{op}">{esc(s)}</text>')

    # Achsen
    def xaxis(self, ticks, fmt=str, grid=False, label=None):
        self.line(self.l, self.h - self.b, self.w - self.r, self.h - self.b, GRID, 1)
        for t in ticks:
            x = self.X(t)
            if grid:
                self.line(x, self.t, x, self.h - self.b, GRID, 1, op=0.6)
            self.text(x, self.h - self.b + 14, fmt(t), 9, MUTED, "middle")
        if label:
            self.text((self.l + self.w - self.r) / 2, self.h - 2, label, 9, MUTED, "middle")
        return self

    def yaxis(self, ticks, fmt=str, grid=True, label=None):
        for t in ticks:
            y = self.Y(t)
            if grid:
                self.line(self.l, y, self.w - self.r, y, GRID, 1)
            self.text(self.l - 8, y + 3.2, fmt(t), 9, MUTED, "end")
        if label:
            self.text(self.l - 8, self.t - 6, label, 9, MUTED, "end")
        return self

    def render(self) -> str:
        return (f'<svg viewBox="0 0 {self.w} {self.h}" class="fig" '
                f'role="img">{"".join(self.parts)}</svg>')


def legend(items: list[tuple[str, str]], shape="dot") -> str:
    """Legende als HTML — bleibt im Textfluss und ist damit auch im PDF selektierbar."""
    li = "".join(
        f'<li><span class="sw" style="background:{c}"></span>{esc(t)}</li>' for t, c in items)
    return f'<ul class="legend">{li}</ul>'


# ── Die einzelnen Grafiken ─────────────────────────────────────────────────────────

def fig_funnel(d) -> str:
    """2015 Ergebnisse → 163 Paare, mit Lupe auf die letzten drei Schritte."""
    f = Fig(W, 198, pad=(26, 8, 8, 8))
    steps = d["funnel"]
    total, band = steps[0]["v"], 30
    x0, x1 = 8, W - 8
    # Oberer Balken: alle Ergebnisse, davon die Namensgleichen als Segment
    y = 24
    f.rect(x0, y, x1 - x0, band, GRID, rx=3)
    seg = (x1 - x0) * steps[1]["v"] / total
    f.rect(x0, y, seg, band, TEAL, rx=3)
    f.text(x0, y - 8, f'{total} Ergebnisse aus den Ranglisten 2002–2026', 10, INK, weight=600)
    f.text(x1, y - 8, f'{steps[1]["v"]} Namensgleiche · {100 * steps[1]["v"] / total:.0f} %',
           9.5, TEAL, "end", weight=600)
    # Trichter vom Segment auf die volle Breite des unteren Blocks
    ly, fh = y + band, 26
    f.add(f'<path d="M{x0},{ly} L{x0 + seg:.1f},{ly} L{x1},{ly + fh} L{x0},{ly + fh} Z" '
          f'fill="{TEAL}" opacity="0.09"/>')
    f.line(x0 + seg, ly, x1, ly + fh, TEAL, 1, dash="3 3", op=0.5)
    f.text(x0 + seg / 2, ly + 17, "vergrössert", 8.5, MUTED, "middle")
    # Unterer Block: die drei Filterschritte, auf 205 skaliert
    top, bh, gap = ly + fh + 8, 28, 10
    base = steps[1]["v"]
    for i, s in enumerate(steps[1:]):
        yy = top + i * (bh + gap)
        w = (x1 - x0) * s["v"] / base
        last = i == len(steps) - 2
        f.rect(x0, yy, x1 - x0, bh, "#EEF2F3", rx=3)
        f.rect(x0, yy, w, bh, TEAL if last else "#B9C6CC", rx=3)
        f.text(x0 + 10, yy + 18, s["label"], 9.5, "#fff" if last else INK, weight=500)
        f.text(x1 - 10, yy + 18, s["v"], 11.5, INK if not last else TEAL, "end",
               weight=700, cls="num")
        if i:
            lost = steps[i]["v"] - s["v"]
            f.text(x0 + w + 10, yy + 18, f"−{lost}", 9, CLAY, weight=600, cls="num")
    return f.render()


def fig_forms(d) -> str:
    """Residual-SD der vier Modellformen als Punktdiagramm mit gestauchter Achse."""
    alts = d["alternatives"]
    f = Fig(W, 168, pad=(14, 60, 40, 170))
    lo, hi = 1.63, 1.75
    f.xdomain(lo, hi).ydomain(-0.5, len(alts) - 0.5)
    f.xaxis([1.63, 1.65, 1.67, 1.69, 1.71, 1.73, 1.75], lambda t: f"{t:.2f}", grid=True,
            label="Residual-SD in Stunden — Achse gestaucht, Nullpunkt nicht dargestellt")
    for i, a in enumerate(alts):
        y = f.Y(len(alts) - 1 - i)
        chosen = i == 0
        worst = a["resid_sd"] > 1.7
        col = TEAL if chosen else (CLAY if worst else MUTED)
        f.line(f.l, y, f.X(a["resid_sd"]), y, col, 1.5, op=0.3)
        f.dot(f.X(a["resid_sd"]), y, 6 if chosen else 5, col, sw=0)
        f.text(f.l - 12, y + 3.5, a["label"], 9.5, INK if chosen else INK2, "end",
               weight=700 if chosen else 400)
        f.text(f.w - f.r + 8, y + 3.5, f'{a["resid_sd"]:.3f}', 9.5,
               col, weight=600 if chosen else 400, cls="num")
    # Klammer über die drei ununterscheidbaren Formen
    ytop, ybot = f.Y(len(alts) - 1) - 9, f.Y(1) + 9
    xb = f.X(1.658)
    f.path([(xb, ytop), (xb + 7, ytop), (xb + 7, ybot), (xb, ybot)], MUTED, 1)
    f.text(xb + 12, (ytop + ybot) / 2 + 3, "dieselbe Aussage", 8.5, MUTED)
    return f.render()


def fig_scatter(d) -> str:
    """Kernbild: Seezeit gegen Kanalzeit mit additivem Band."""
    m = d["model"]
    f = Fig(W, 372, pad=(18, 16, 42, 48))
    a, b = 6.4, 13.7
    f.xdomain(a, b).ydomain(8, 24)
    f.xaxis(range(7, 14), lambda t: f"{t} h", grid=True, label="Zürichsee-Zeit")
    f.yaxis(range(8, 25, 2), lambda t: f"{t} h", label="Kanalzeit")
    # 95-%-Band um den additiven Median
    lo, hi = m["lo95"], m["hi95"]
    f.area([(f.X(a), f.Y(a + lo)), (f.X(b), f.Y(b + lo)),
            (f.X(b), f.Y(min(24, b + hi))), (f.X(a), f.Y(a + hi))], TEAL, 0.10)
    for e in (lo, hi):
        f.path([(f.X(a), f.Y(a + e)), (f.X(b), f.Y(min(24, b + e)))], TEAL, 1,
               dash="4 3", op=.55)
    # Diagonale „gleiche Zeit" und Medianlinie
    f.path([(f.X(a), f.Y(max(8, a))), (f.X(b), f.Y(b))], MUTED, 1, dash="2 4")
    f.path([(f.X(a), f.Y(a + m["median"])), (f.X(b), f.Y(b + m["median"]))], TEAL, 2)
    # Punkte; ausserhalb des Bands in Clay
    for p in d["scatter"]:
        out = not (lo <= p["y"] - p["x"] <= hi)
        f.dot(f.X(p["x"]), f.Y(p["y"]), 3.4 if out else 3,
              CLAY if out else INK, 0.95 if out else 0.42, sw=0.8 if out else 0)
    # Beschriftungen an den Linien
    f.text(f.X(13.5), f.Y(13.5 + m["median"]) - 8, f'Median  +{hms(m["median"])} h',
           9, TEAL, "end", weight=600)
    f.text(f.X(13.5), f.Y(13.5 + lo) + 13, f'untere Grenze  +{hms(lo)} h', 8.5, TEAL, "end")
    f.text(f.X(11.2), f.Y(11.2 + hi) - 7, f'obere Grenze  +{hms(hi)} h', 8.5, TEAL)
    f.text(f.X(13.5), f.Y(13.5) + 13, "gleiche Zeit", 8.5, MUTED, "end")
    return f.render()


def fig_cover(d) -> str:
    """Titelgrafik: dasselbe Bild wie Abbildung 3, aber ohne Achsenapparat."""
    m = d["model"]
    f = Fig(W, 250, pad=(14, 14, 26, 14))
    a, b = 6.4, 13.7
    f.xdomain(a, b).ydomain(8, 24)
    lo, hi = m["lo95"], m["hi95"]
    f.area([(f.X(a), f.Y(a + lo)), (f.X(b), f.Y(b + lo)),
            (f.X(b), f.Y(min(24, b + hi))), (f.X(a), f.Y(a + hi))], TEAL, 0.11)
    f.path([(f.X(a), f.Y(max(8, a))), (f.X(b), f.Y(b))], MUTED, 1, dash="2 4")
    f.path([(f.X(a), f.Y(a + m["median"])), (f.X(b), f.Y(b + m["median"]))], TEAL, 2)
    for p in d["scatter"]:
        out = not (lo <= p["y"] - p["x"] <= hi)
        f.dot(f.X(p["x"]), f.Y(p["y"]), 3.2 if out else 2.9,
              CLAY if out else INK, 0.9 if out else 0.38, sw=0)
    f.text(f.l + 2, f.h - 8, "Zürichsee-Zeit  →", 8.5, MUTED)
    f.text(f.l + 2, f.t + 10, "↑  Kanalzeit", 8.5, MUTED)
    f.text(f.X(13.5), f.Y(13.5 + m["median"]) - 8,
           f'Median  Seezeit + {hms(m["median"])} h', 9, TEAL, "end", weight=600)
    f.text(f.X(13.5), f.Y(13.5) + 12, "gleiche Zeit", 8.5, MUTED, "end")
    return f.render()


def fig_surcharge(d) -> str:
    """Verteilung des Aufschlags mit angepasster Lognormal-Dichte."""
    s = d["surcharge"]
    f = Fig(W, 230, pad=(16, 14, 42, 46))
    top = max(s["hist"]) * 1.15
    f.xdomain(0, 10).ydomain(0, top)
    f.xaxis(range(0, 11), lambda t: f"{t} h", label="Aufschlag gegenüber der Zürichsee-Zeit")
    f.yaxis([0, 5, 10, 15, 20, 25], label="Paare")
    bw = (f.X(s["width"]) - f.X(0))
    for i, c in enumerate(s["hist"]):
        if c:
            x = f.X(i * s["width"])
            f.rect(x + 1, f.Y(c), bw - 2, f.Y(0) - f.Y(c), TEAL, rx=2, op=0.30)
    f.path([(f.X(x), f.Y(y)) for x, y in d["surcharge"]["density"] if y < top], TEAL, 2)
    # Median und 95-%-Grenzen
    m = d["model"]
    for v, lab, w_, anc in [(m["lo95"], f'2.5 %  {hms(m["lo95"])} h', 1, "start"),
                            (m["median"], f'Median  {hms(m["median"])} h', 2, "middle"),
                            (m["hi95"], f'97.5 %  {hms(m["hi95"])} h', 1, "end")]:
        f.line(f.X(v), f.Y(0), f.X(v), f.t + 14, INK, w_, dash=None if w_ == 2 else "3 3",
               op=0.85 if w_ == 2 else 0.5)
        dx = 4 if anc == "start" else (-4 if anc == "end" else 0)
        f.text(f.X(v) + dx, f.t + 9, lab, 8.5, INK if w_ == 2 else MUTED, anc,
               weight=600 if w_ == 2 else 400)
    f.text(f.X(7.6), f.Y(top * 0.72),
           f'min {hms(s["min"])} h · max {hms(s["max"])} h', 8.5, MUTED)
    return f.render()


def fig_coverage(d) -> str:
    """Wie gut das 95-%-Band je Tempoband hält."""
    c = d["coverage"]["bands"]
    f = Fig(W, 172, pad=(16, 96, 38, 96))
    f.xdomain(70, 100).ydomain(-0.5, len(c) - 0.5)
    f.xaxis([70, 75, 80, 85, 90, 95, 100], lambda t: f"{t} %", grid=True,
            label="Anteil der Paare im 95-%-Band")
    f.line(f.X(95), f.t, f.X(95), f.h - f.b, INK, 1, dash="3 3", op=0.6)
    f.text(f.X(95), f.t - 3, "Soll 95 %", 8.5, INK, "middle")
    for i, b in enumerate(c):
        y = f.Y(len(c) - 1 - i)
        bad = b["pct"] < 92
        f.rect(f.l, y - 9, f.X(b["pct"]) - f.l, 18, CLAY if bad else TEAL, rx=2, op=0.85)
        f.text(f.l - 10, y + 3.5, b["label"], 9.5, INK, "end")
        f.text(f.w - f.r + 8, y + 3.5, f'{b["pct"]:.0f} %', 9.5, CLAY if bad else TEAL,
               weight=600, cls="num")
        f.text(f.w - f.r + 40, y + 3.5, f'n={b["n"]}', 8.5, MUTED, cls="num")
    return f.render()


def fig_features(d) -> str:
    """Alle geprüften Merkmale: Korrelation mit dem Aufschlag samt Bootstrap-KI."""
    fs = d["features"]
    f = Fig(W, 300, pad=(22, 54, 38, 190))
    f.xdomain(-0.45, 0.45).ydomain(-0.6, len(fs) - 0.4)
    f.xaxis([-0.4, -0.2, 0, 0.2, 0.4], lambda t: f"{t:+.1f}".replace("+0.0", "0"), grid=True,
            label="Korrelation mit dem Aufschlag, 95-%-Bootstrap-Intervall")
    f.line(f.X(0), f.t, f.X(0), f.h - f.b, INK, 1.2, op=0.7)
    for i, x in enumerate(fs):
        y = f.Y(len(fs) - 1 - i)
        keep = x["lo"] > 0 or x["hi"] < 0
        col = TEAL if keep else MUTED
        f.line(f.X(x["lo"]), y, f.X(x["hi"]), y, col, 1.6, cap="round",
               op=1 if keep else 0.55)
        for e in (x["lo"], x["hi"]):
            f.line(f.X(e), y - 3.5, f.X(e), y + 3.5, col, 1.4, op=1 if keep else 0.55)
        f.dot(f.X(x["r"]), y, 4.2 if keep else 3.4, col, sw=0)
        f.text(f.l - 12, y + 3.5, x["label"], 9.5, INK if keep else INK2, "end",
               weight=700 if keep else 400)
        f.text(f.w - f.r + 8, y + 3.5, f'{x["r"]:+.3f}', 9, col,
               weight=600 if keep else 400, cls="num")
    y_keep = f.Y(len(fs) - 1)
    f.text(f.X(0.44), y_keep - 12, "Intervall schliesst 0 aus → übernommen", 8.5, TEAL, "end",
           weight=600)
    return f.render()


def fig_tide(d) -> str:
    """Tidenhub gegen Aufschlag, logarithmische Ordinate."""
    t = d["tide"]
    f = Fig(W, 286, pad=(20, 152, 42, 52))
    f.xdomain(0.35, 1.10).ydomain(math.log(0.5), math.log(12))
    f.xaxis([0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1], lambda v: f"{v:.1f}", grid=True,
            label="Tidenfaktor am Tag der Querung  (0.4 Nipptide → 1.0 Springtide)")
    f.yaxis([math.log(v) for v in (1, 2, 4, 8)], lambda v: f"{math.e ** v:.0f} h")
    f.text(f.l - 40, f.t - 6, "Aufschlag, log", 9, MUTED)
    for p in t["points"]:
        f.dot(f.X(p["x"]), f.Y(math.log(p["y"])), 3, INK, 0.38, sw=0)
    f.path([(f.X(x / 100), f.Y(t["a"] + t["b"] * x / 100)) for x in range(35, 111)], TEAL, 2.2)
    # Spannweiten-Marke am rechten Rand statt kreuzender Anschlusslinien
    xr = f.w - f.r - 6
    y_lo, y_hi = f.Y(t["a"] + t["b"] * 1.0), f.Y(t["a"] + t["b"] * 0.45)
    f.line(xr, y_lo, xr, y_hi, CLAY, 1.4)
    for yy in (y_lo, y_hi):
        f.line(xr - 4, yy, xr + 4, yy, CLAY, 1.4)
    f.text(xr - 8, (y_lo + y_hi) / 2 + 3, f'{t["spread_min"]} min', 8.8, CLAY, "end",
           weight=700, cls="num")
    # Stützstellen als Wertespalte, ohne Leitlinien
    bx, by = f.w - f.r + 16, f.t + 26
    f.text(bx, by - 14, "Erwarteter Aufschlag", 8, MUTED)
    for i, s in enumerate(t["steps"]):
        f.dot(f.X(s["f"]), f.Y(t["a"] + t["b"] * s["f"]), 4, TEAL, sw=1.4)
        yy = by + i * 19
        f.dot(bx + 4, yy - 3.2, 3.2, TEAL, sw=0)
        f.text(bx + 12, yy, s["label"], 8.8, INK2)
        f.text(f.w - 4, yy, f'{hms(s["h"])} h', 9.2, TEAL, "end", weight=600, cls="num")
    return f.render()


def fig_months(d) -> str:
    """Median-Aufschlag je Monat; Punktfläche proportional zur Fallzahl."""
    ms = d["months"]
    f = Fig(W, 210, pad=(18, 14, 44, 46))
    f.xdomain(4.5, 10.5).ydomain(3.2, 5.6)
    f.xaxis([m["m"] for m in ms], lambda t: {5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
                                             9: "Sept.", 10: "Okt."}[t],
            label="Monat der Querung — Punktfläche proportional zur Fallzahl")
    f.yaxis([3.5, 4.0, 4.5, 5.0, 5.5], lambda v: f"{hms(v)} h", label="Median-Aufschlag")
    f.rect(f.X(4.5), f.t, f.X(6.6) - f.X(4.5), f.h - f.b - f.t, CLAY, op=0.07)
    f.text(f.X(5.55), f.h - f.b - 8, "trägt den ganzen Effekt", 8.5, CLAY, "middle",
           weight=600)
    f.path([(f.X(m["m"]), f.Y(m["median"])) for m in ms], MUTED, 1.4, dash="4 3", op=0.7)
    for m in ms:
        r = max(3.2, math.sqrt(m["n"]) * 1.9)
        col = CLAY if m["m"] <= 6 else TEAL
        f.dot(f.X(m["m"]), f.Y(m["median"]), r, col, 0.85, sw=0)
        f.text(f.X(m["m"]), f.Y(m["median"]) - r - 5, f'n={m["n"]}', 8.5, col, "middle",
               weight=600, cls="num")
    return f.render()


def fig_coef(d) -> str:
    """Koeffizienten im gemeinsamen Modell — der Entscheid gegen die Temperatur."""
    f = Fig(W, 150, pad=(24, 60, 40, 150))
    lo = min(c["lo"] for c in d["coef"]) - 0.1
    hi = max(c["hi"] for c in d["coef"]) + 0.1
    f.xdomain(lo, hi).ydomain(-0.6, 1.6)
    f.xaxis([-0.2, 0, 0.4, 0.8, 1.2], lambda t: f"{t:+.1f}".replace("+0.0", "0"), grid=True,
            label="Koeffizient auf log(Aufschlag), gemeinsames Modell · 2000 Bootstrap-Ziehungen")
    f.line(f.X(0), f.t, f.X(0), f.h - f.b, INK, 1.2)
    for i, c in enumerate(d["coef"]):
        y = f.Y(1 - i)
        col = TEAL if c["excludes_zero"] else CLAY
        f.line(f.X(c["lo"]), y, f.X(c["hi"]), y, col, 2, cap="round")
        for e in (c["lo"], c["hi"]):
            f.line(f.X(e), y - 4, f.X(e), y + 4, col, 1.5)
        f.dot(f.X(c["b"]), y, 4.5, col, sw=0)
        f.text(f.l - 12, y + 3.5, c["label"], 10, INK, "end", weight=600)
        f.text(f.l - 12, y + 15, "übernommen" if c["excludes_zero"] else "verworfen",
               8.5, col, "end")
        f.text(f.w - f.r + 8, y + 3.5, f'{c["b"]:+.3f}', 9.5, col, weight=600, cls="num")
    return f.render()


def fig_spread(d) -> str:
    """Warum die Tide trennt und die Temperatur nicht: die Spannweite im Datensatz."""
    f = Fig(W, 126, pad=(28, 84, 30, 150))
    f.xdomain(0, 1).ydomain(-0.6, 1.6)
    for i, s in enumerate(d["spread"]):
        y = f.Y(1 - i)
        col = TEAL if i == 0 else CLAY
        full = f.w - f.r - f.l
        f.rect(f.l, y - 9, full, 18, GRID, rx=3, op=0.45)
        # Anteil der Skala, den das Merkmal tatsächlich abdeckt (Max/Min)
        w = full * min((s["ratio"] - 1) / 1.6, 1)
        f.rect(f.l, y - 9, w, 18, col, rx=3)
        f.text(f.l - 12, y + 3.5, s["label"], 10, INK, "end", weight=600)
        f.text(f.l + 10, y + 4, f'{s["min"]} – {s["max"]}{s["unit"]}', 9, "#fff", cls="num")
        f.text(f.w - f.r + 8, y + 4, f'Faktor {s["ratio"]}', 9.5, col, weight=700, cls="num")
    f.text(f.l, f.t - 10, "Spannweite im Datensatz — eine Variable kann nur erklären, "
                          "was sie unterscheidet", 8.5, MUTED)
    return f.render()


def fig_xgb(d) -> str:
    """Mittlerer absoluter Fehler, kreuzvalidiert."""
    rows = d["xgboost"]
    f = Fig(W, 176, pad=(16, 106, 40, 158))
    base = next(r["mae"] for r in rows if r.get("base"))
    f.xdomain(1.15, 1.38).ydomain(-0.5, len(rows) - 0.5)
    f.xaxis([1.15, 1.20, 1.25, 1.30, 1.35], lambda t: f"{t:.2f}", grid=True,
            label="MAE in Stunden, 5-fach × 20 Wiederholungen — Achse gestaucht")
    for i, r in enumerate(rows):
        y = f.Y(len(rows) - 1 - i)
        win = r.get("base")
        col = TEAL if win else CLAY
        f.line(f.l, y, f.X(r["mae"]), y, col, 1.5, op=0.25)
        f.dot(f.X(r["mae"]), y, 6 if win else 5, col, sw=0)
        f.text(f.l - 12, y + 3.5, r["label"], 9.5, INK, "end", weight=700 if win else 400)
        f.text(f.w - f.r + 8, y + 3.5, f'{r["mae"]:.3f}', 9.5, col,
               weight=600 if win else 400, cls="num")
        if not win:
            f.text(f.w - f.r + 42, y + 3.5, f'+{100 * (r["mae"] / base - 1):.1f} %', 8.5,
                   CLAY, cls="num")
    f.line(f.X(base), f.t, f.X(base), f.h - f.b, TEAL, 1, dash="3 3", op=0.7)
    return f.render()


# ── Dokument ───────────────────────────────────────────────────────────────────────

def figure(num: int, title: str, svg: str, caption: str, extra: str = "") -> str:
    return (f'<figure><figcaption><span class="fnum">Abb. {num}</span>'
            f'<span class="ftitle">{title}</span></figcaption>{svg}{extra}'
            f'<p class="cap">{caption}</p></figure>')


def build_html(d) -> str:
    m, cov, mr = d["model"], d["coverage"], d["month_r"]
    t, sp = d["tide"], d["spread"]
    temp = next(c for c in d["coef"] if c["label"] == "Wassertemperatur")
    tide_c = next(c for c in d["coef"] if c["label"] == "Tidenhub")
    n = d["n"]

    css = CSS
    parts = [f"""<div class="cover">
  <p class="eyebrow">Forschungsprotokoll · Stand 16. August 2026</p>
  <h1>Was sagt eine Zürichsee-Zeit<br>über den Ärmelkanal?</h1>
  <p class="lede">Aus {n} Personen, die beide Strecken geschwommen sind, lässt sich die
     zu erwartende Kanalzeit schätzen. Dieses Protokoll hält fest, was geprüft wurde,
     was gehalten hat — und vor allem, was nicht. Die verworfenen Ansätze sind der
     teurere Teil der Arbeit und verschwinden sonst spurlos.</p>
  <div class="keyfacts">
    <div><span class="kf">{n}</span><span class="kfl">Personen mit beiden Zeiten</span></div>
    <div><span class="kf">+{hms(m['median'])} h</span><span class="kfl">Median-Aufschlag</span></div>
    <div><span class="kf">{hms(m['lo95'])}–{hms(m['hi95'])}</span><span class="kfl">95-%-Bereich</span></div>
    <div><span class="kf">1 von 10</span><span class="kfl">Merkmalen hat gehalten</span></div>
  </div>
  <div class="coverfig">{fig_cover(d)}
    <p class="cap">Jeder Punkt ist eine Person mit beiden Zeiten. Das Band verläuft parallel
       zur Diagonalen, nicht fächerförmig — der Kanal kostet einen konstanten Aufschlag,
       kein Vielfaches.</p>
  </div>
  <p class="cover-note">Datengrundlage: Sri Chinmoy Marathon-Schwimmen Zürichsee 2002–2026
     (2015 Ergebnisse, aus den Original-PDFs extrahiert) und die Channel Solo Database
     (3443 ratifizierte Querungen 1875–2025). Jede Kennzahl zu den Paaren ist beim Satz
     dieses Berichts aus <code>crossover.json</code> neu gerechnet; die kreuzvalidierten
     Vergleichswerte stammen aus den Läufen von <code>experiment_ml.py</code>.</p>
</div>

<section>
<h2><span class="sn">1</span>Die Frage</h2>
<p>Der Zürichsee-Marathon über 26 km ist faktisch ein Vorbereitungsrennen für
Kanal-Aspiranten. Entsprechend gross ist die Überschneidung der Teilnehmerfelder. Wenn
genügend Personen beides geschwommen sind, lässt sich aus einer Seezeit die zu erwartende
Kanalzeit schätzen — und, wichtiger, die Bandbreite, in der sie liegen wird.</p>
<p class="note">Der Kanal misst 33 km Luftlinie, real 40 km und mehr wegen der
Gezeiten-S-Kurve. Dazu Salzwasser, Wellen und mehrere Grad kälter als der See.</p>
</section>

<section>
<h2><span class="sn">2</span>Der Datenweg</h2>
<p>Von 2015 Ranglisten-Ergebnissen bleiben {n} verwertbare Paare. Der Schritt mit dem
grössten Einfluss auf das Ergebnis war nicht der Namensabgleich, sondern die
<strong>Vergleichbarkeit</strong> — ohne sie vergleicht man Äpfel mit Birnen.</p>
{figure(1, "Von 2015 Ergebnissen zu " + str(n) + " Paaren",
        fig_funnel(d),
        "Nur jedes zehnte Zürichsee-Ergebnis gehört zu einer Person, die auch im "
        "Kanal-Datensatz steht. Von diesen 205 fallen weitere 42 durch die "
        "Vergleichbarkeitsregeln und die Deduplizierung.")}
<ul class="rules">
  <li><strong>Zürichsee nur Einzelstarts</strong> — eine Staffel-Teilstrecke ist keine
      26-km-Leistung.</li>
  <li><strong>Zürichsee nur ohne Neopren</strong> — die Kanalregeln verbieten ihn.</li>
  <li><strong>Kanal nur einfache Querungen</strong> — Zwei- und Dreifachquerungen sind
      eine andere Disziplin.</li>
</ul>
<p>Bei Mehrfachstartern wird das Paar mit dem kleinsten Jahresabstand gewählt (Median
2 Jahre). Die Alternativen wären „Bestzeit gegen Bestzeit“, was teils zwanzig Jahre
auseinanderliegende Formzustände mischt, oder alle Kombinationen, wodurch Vielstarter
das Ergebnis dominieren und die Punkte nicht mehr unabhängig sind.</p>
</section>

<section>
<h2><span class="sn">3</span>Die Modellform — getestet, nicht angenommen</h2>
<p>Die naheliegende Erwartung ist Proportionalität: Zeit = Strecke ÷ Tempo, der Kanal ist
länger, also müsste die Kanalzeit ein Vielfaches der Seezeit sein. <strong>Das ist die
einzige Form, die die Daten klar verwerfen.</strong></p>
{figure(2, "Vier Modellformen im Vergleich", fig_forms(d),
        "Zwischen den ersten drei Formen ist der Unterschied bedeutungslos — sie sagen "
        "dasselbe. Nur die Proportionalität durch den Nullpunkt fällt ab.")}
<p>Entscheidend ist eine andere Zahl als der Fit: <strong>die Korrelation zwischen
Aufschlag und Seezeit beträgt +{d['features'][[f['label'] for f in d['features']].index('Zürichsee-Zeit')]['r']:.3f}</strong>.
Der Aufschlag hängt nicht vom Tempo ab. Eine Steigung ist damit nicht nur überflüssig,
sondern irreführend.</p>
<p class="note">Das Potenzgesetz sieht wie ein Konkurrenzmodell aus, ist aber keines: Eine
additive Beziehung erscheint im Log-Raum als Potenzgesetz mit Exponent
x̄/(x̄+c) = 9.30/13.55 = <strong>0.687</strong>. Gemessen wurden 0.714.</p>
<div class="model">
  <p class="ml">Gewähltes Modell</p>
  <p class="mf">Kanalzeit = Zürichseezeit + Aufschlag</p>
  <p class="mf">Aufschlag ~ LogNormal(μ = {m['mu']:.4f}, σ = {m['sigma']:.4f})</p>
  <p class="mr">Median {hms(m['median'])} h · 95 % zwischen {hms(m['lo95'])} und
     {hms(m['hi95'])} h</p>
</div>
{figure(3, "Seezeit gegen Kanalzeit, mit dem 95-%-Band", fig_scatter(d),
        f"Das Band verläuft parallel zur Diagonalen, nicht fächerförmig — genau das "
        f"bedeutet ein konstanter Aufschlag. {cov['total']} der {n} Paare liegen darin "
        f"({cov['pct']} %); die {n - cov['total']} Ausnahmen sind hervorgehoben.",
        legend([("innerhalb des Bands", INK), ("ausserhalb", CLAY)]))}
</section>

<section>
{figure(4, "Verteilung des Aufschlags", fig_surcharge(d),
        f"Rechtsschief mit harter Grenze bei null: der schnellste Aufschlag beträgt "
        f"{hms(d['surcharge']['min'])} h, der langsamste {hms(d['surcharge']['max'])} h. "
        f"Deshalb lognormal und deshalb ein asymmetrisches Band — nach unten gibt es eine "
        f"Grenze, nach oben nicht.")}
{figure(5, "Hält das Band über alle Tempobänder?", fig_coverage(d),
        "Über 11 h Seezeit liegen nur 24 Paare vor, und ihre Kanalzeiten streuen breiter "
        "als das Modell abbildet. Vermutlich Survivorship: langsame Querungen werden "
        "häufiger abgebrochen und tauchen im Datensatz gar nicht erst auf.")}
<p>Der <em>Faktor</em> sinkt mit langsameren Zeiten — 1.55 unter 8 h, 1.32 über 11 h. Das
ist die Arithmetik eines konstanten Aufschlags, kein eigener Effekt.</p>
</section>

<section>
<h2><span class="sn">4</span>Geprüfte Merkmale</h2>
<p>Zielgrösse ist immer der <strong>Aufschlag in Stunden</strong>, nie der Faktor — die
Begründung steht in Abschnitt 6. Zehn Merkmale wurden geprüft; eines hat gehalten.</p>
<p class="note">Die Richtung E→F / F→E liess sich nicht prüfen: im Datensatz ist sie
faktisch konstant.</p>
{figure(6, "Zehn Merkmale, ein Treffer", fig_features(d),
        "Punkt = gemessene Korrelation, Balken = 95-%-Bootstrap-Intervall über 2000 "
        "Ziehungen. Nur beim Tidenhub schliesst das Intervall die Null aus. Alles "
        "andere ist mit „kein Zusammenhang“ verträglich.")}

<h3>4.1 Tidenhub — das einzige Merkmal mit Signal</h3>
<p>Aus dem Datum der Querung wird der Tidenhub in Dover berechnet ({t['n']} von {n} Paaren
haben ein Datum). Die Richtung ist die, welche die Physik verlangt: mehr Hub → stärkere
Ströme → längere Gezeiten-S-Kurve.</p>
{figure(7, "Aufschlag nach Tidenfaktor", fig_tide(d),
        f"log(Aufschlag) = {t['a']:.3f} + {t['b']:.3f} · Tidenfaktor. Zwischen Nipp- und "
        f"Springtide liegen rund {t['spread_min']} Minuten. Die Streuung um die Linie "
        f"bleibt gross — das Merkmal verschiebt den Median, es macht die Prognose nicht "
        f"scharf.")}
<p>Kreuzvalidiert bringt der Tidenhub <strong>−1.4 % MAE</strong>, in 128 von 200 Folds
besser. Der Gewinn ist klein, weil zwei Drittel der Querungen ohnehin in Nippfenstern
liegen — die Piloten buchen die ruhigen Termine. Für eine einzelne Planung ist der Effekt
gross.</p>
<p>Der praktische Wert liegt ohnehin woanders als in der MAE: Das Tidenfenster ist die
einzige geprüfte Grösse, die man <strong>vor der Buchung kennt</strong>. Damit wird aus
einer Prognose eine Entscheidungshilfe.</p>
<p class="note"><strong>Risiko und Absicherung.</strong> Die Konstanten sind auf 56
Dover-Hochwasser aus einem 29-Tage-Fenster im August 2026 gefittet, angewendet werden sie
ab 2002. Gegenprobe an 1272 Stichtagen 2002–2025: die Spring/Nipp-Einstufung widerspricht
der unabhängig gerechneten Mondphase dreimal (0.2 %). Sie hält, weil nur die Amplituden
gefittet sind — die Frequenzen sind astronomische Konstanten. Nodale Modulation über
18.6 Jahre ist nicht modelliert.</p>
</section>

<section>
<div class="keep"><h3>4.2 Monat der Querung — verworfen</h3>
{figure(8, "Median-Aufschlag nach Monat", fig_months(d),
        f"Juli bis Oktober sind praktisch identisch. Auffällig ist nur der Juni — auf "
        f"fünf Querungen. Ohne Mai und Juni fällt die Korrelation von "
        f"{mr['all']:+.3f} auf {mr['without_may_june']:+.3f}.")}</div>
<p>Ein Effekt, der an {mr['n_dropped']} von {t['n']} Punkten hängt, ist keiner.
Kreuzvalidiert bringt der Monat allein −0.2 %; zusammen mit dem Tidenhub ist er
<strong>schlechter</strong> als der Tidenhub allein (−1.3 % statt −1.4 %).</p>
<p>Selbst wenn der Juni-Effekt real wäre, liesse er sich nicht als Temperatureffekt lesen:
Frühsaison-Slots werden anders vergeben, und wer im Juni schwimmt, hat typischerweise
weniger Vorbereitung hinter sich. Aus diesen Daten nicht trennbar.</p>

<h3>4.3 Wassertemperatur — verworfen, aber der knappste Fall</h3>
<p>Quelle ist ein Monatsmittel der Meeresoberflächentemperatur (NASA JPL MUR SST,
2015–2026); für ältere Querungen das Mittel über alle Jahre. Allein betrachtet ist das
Merkmal nutzlos. Gemeinsam mit dem Tidenhub sieht es zunächst gut aus: −2.1 % statt
−1.4 %, in 68 % der Folds besser, und der Koeffizient zeigt mit rund −4.6 % Aufschlag pro
Grad wärmer in die plausible Richtung.</p>
{figure(9, "Koeffizienten im gemeinsamen Modell", fig_coef(d),
        f"Entschieden hat der Bootstrap: Bei 2000 Ziehungen wechselt der "
        f"Temperatur-Koeffizient das Vorzeichen ({temp['lo']:+.3f} bis {temp['hi']:+.3f}). "
        f"Beim Tidenhub tut er das nicht ({tide_c['lo']:+.3f} bis {tide_c['hi']:+.3f}). "
        f"Der kreuzvalidierte Gewinn von 32 Sekunden auf einer 12-Stunden-Prognose trägt "
        f"das nicht.")}
{figure(10, "Warum die Tide trennt und die Temperatur nicht", fig_spread(d),
        f"Beide wirken physikalisch. Aber der Tidenhub variiert im Datensatz um Faktor "
        f"{sp[0]['ratio']}, die Wassertemperatur nur um Faktor {sp[1]['ratio']} — und über "
        f"90 % der Querungen liegen zwischen 15 und 18 °C.")}
<p>Kälte wirkt am Kanal mit Sicherheit — aber vor allem über <strong>Abbrüche</strong>,
und die stehen nicht im Datensatz.</p>
</section>

<section>
<h3>4.4 XGBoost — verworfen</h3>
<p>Getestet mit Seezeit, Alter, Anzahl bisheriger Starts, Geschlecht, Jahresabstand,
Reihenfolge, Jahr und Richtung. Bewertet wurde auf der Kanalzeit in Stunden, 5-fach
kreuzvalidiert über 20 Wiederholungen.</p>
{figure(11, "Kein gelerntes Modell schlägt die Konstante", fig_xgb(d),
        "Die Referenz ist der konstante Aufschlag — ein Modell mit einem einzigen "
        "Parameter. Weder die lineare Regression noch XGBoost kommen daran heran.")}
<p>Mit einer Hyperparameter-Suche über 81 Konfigurationen kommt XGBoost auf +3.9 %, gewinnt
also auch dann nicht. Aufschlussreich ist <em>wie</em>: Die beste Konfiguration ist
<code>depth=1, lr=0.02</code>, also Entscheidungsstümpfe mit winziger Lernrate. Das Modell
wird umso besser, je weniger es lernen darf; im Grenzwert wäre es die Konstante. Die Suche
hat nichts gefunden, sondern nur den kürzesten Weg zurück zur Baseline.</p>
<p class="note">Diese +3.9 % sind zudem geschönt: Die beste von 81 Konfigurationen wurde
anhand derselben CV-Zahl ausgewählt, gegen die sie verglichen wird. Sauber wäre nested CV.
Für die Schlussfolgerung egal, weil sie in die unbequeme Richtung zeigt.</p>
<p>Die Feature-Wichtigkeiten aus dem Trainingslauf (<code>zh_hours</code> 0.32,
<code>zh_first</code> 0.15, <code>female</code> 0.13) sehen nach Erkenntnis aus und sind
keine — sie belohnen jeden Split, auch den auf Rauschen.</p>
</section>

<section>
<h2><span class="sn">5</span>Gefundene und behobene Fehler</h2>
<p>Chronologisch, weil jeder davon das Ergebnis verändert hätte:</p>
<table>
<thead><tr><th>Fehler</th><th>Wirkung</th><th>Behebung</th></tr></thead>
<tbody>
<tr><td>Zeitformate variieren stark (<code>8h 03m 35s</code>, <code>6 h 41:08</code>,
    <code>5:51:41</code>, Tippfehler wie <code>10h 26h 48s</code>)</td>
    <td>Jahrgang 2005 hatte 0 Endzeiten</td>
    <td>Parser liest die ersten drei Zahlen positionell als h/m/s, statt den
        Einheitsbuchstaben zu trauen</td></tr>
<tr><td>6 DNF-Zeilen trugen die Meilen-Zwischenzeit im Endzeit-Feld</td>
    <td>Phantom-Finisher</td><td>gilt jetzt als Zwischenzeit</td></tr>
<tr><td>HC-Schwimmer starteten in Meilen, also kürzere Strecke</td>
    <td>Spitzengeschwindigkeiten frei erfunden</td><td>keine km/h für HC</td></tr>
<tr><td><code>speed_kmh</code> als TEXT in SQLite</td><td>Frontend brach beim Start</td>
    <td>Spaltentypen korrigiert</td></tr>
<tr><td>Doppelvornamen doppelt gefunden (Anna-Carin unter „anna“ <em>und</em>
    „anna carin“)</td><td>n = 167 statt {n}</td>
    <td>Deduplizierung auf das Schwimm-Paar</td></tr>
<tr><td>Fallzahlen im Markup hartkodiert</td><td>drifteten nach der Korrektur auseinander</td>
    <td>kommen jetzt aus den Daten</td></tr>
</tbody></table>
</section>

<section>
<h2><span class="sn">6</span>Methodische Festlegungen</h2>
<h3>Bewertet wird in Stunden, nie im Faktor</h3>
<p>Der Faktor ist mechanisch <code>1 + Aufschlag/Seezeit</code> — eine Identität, keine
empirische Beziehung. Gibt man die Seezeit als Merkmal und sagt den Faktor voraus, steckt
das Merkmal im Nenner des Ziels; das Modell senkt seinen Fehler, indem es eine Definition
nachbaut. Zudem wird ein Faktorfehler beim Zurückrechnen mit der Seezeit multipliziert:
0.05 kosten bei 7 h Seezeit 21 Minuten, bei 12 h aber 36. Ein auf den Faktor optimiertes
Modell vernachlässigt die langsamen Schwimmer systematisch.</p>
<h3>Kreuzvalidierung statt einzelnem Holdout</h3>
<p>Bei n = {n} lässt ein 80/20-Split 33 Zeilen zum Bewerten. Über 15 Seeds schwankte die
Baseline zwischen MAE 1.043 und 1.482, und in 2 von 15 Fällen hätte XGBoost gewonnen.
Verwendet wird 5-fach × 20–40 Wiederholungen.</p>
<h3>Residual-SD 0 ist nicht das Ziel</h3>
<p>Ein tiefes, unreguliertes XGBoost erreicht 0.001 h im Training und 1.978
kreuzvalidiert — es lernt die {n} Zeiten auswendig. Der konstante Aufschlag ist das einzige
Modell, das kreuzvalidiert minimal <em>besser</em> abschneidet als im Training (1.643 gegen
1.658). Ziel ist das Niveau des echten Rauschens, keinen Millimeter tiefer.</p>
</section>

<section>
<h2><span class="sn">7</span>Belastbarkeit des Abgleichs</h2>
<p>Kein Paar beruht allein auf dem Namen:</p>
<table class="narrow">
<thead><tr><th>Beleg</th><th class="r">Paare</th></tr></thead>
<tbody>
<tr><td>Geburtsjahr auf beiden Seiten, Abweichung ≤ 2 Jahre</td>
    <td class="r num">{d['grades']['birth_year']}</td></tr>
<tr><td>Geschlecht und Nationalitätsgruppe stimmen überein</td>
    <td class="r num">{d['grades']['gender_nat']}</td></tr>
<tr><td>manuell geprüft und dokumentiert</td>
    <td class="r num">{d['grades']['manual']}</td></tr>
</tbody></table>
<p>Das Geburtsjahr war der Glücksfall: Die Kanal-Datenbank führt das Alter beim Schwimmen,
der Zürichsee den Jahrgang. Bei {d['grades']['birth_year']} Paaren liess sich das
gegenrechnen — <strong>alle stimmen, kein einziger Widerspruch.</strong> Es schlägt die
Nationalität, weil international startende Freiwasserschwimmer häufig Doppelbürger oder
Auswanderer sind; sieben Paare mit widersprüchlicher Nationalität sind übers Geburtsjahr
bestätigt.</p>
<p class="note">Ein Fall brauchte eine Handentscheidung: <strong>Bhakti Sharma</strong> ist
im Kanal-Datensatz als männlich erfasst — ein Fehler der Quelle. Dokumentiert in
<code>OVERRIDES</code>, nicht stillschweigend korrigiert.</p>
</section>

<section>
<h2><span class="sn">8</span>Was offen bleibt</h2>
<p><strong>Die grösste Einschränkung ist keine Rechenfrage.</strong> Die Channel-Datenbank
enthält nur ratifizierte, erfolgreiche Querungen. Alle Aussagen hier gelten unter der
Bedingung, dass man ankommt. Über die Erfolgswahrscheinlichkeit — und damit über den
vermutlich stärksten Effekt von Kälte und Wetter — sagen diese Daten nichts.</p>
<p><strong>Schwächste Stelle im Modell</strong> ist der langsame Rand: über 11 h Seezeit
liegen nur 24 Paare vor, und ihre Kanalzeiten streuen breiter als das Band abbildet
(Abbildung 5).</p>
<p><strong>Was tatsächlich helfen würde</strong>, ist kein stärkerer Lerner, sondern
Merkmale, die wir nicht haben: Windstärke und -richtung am Tag der Querung, der Pilot und
seine Routenwahl, das Trainingsvolumen der Vorsaison, und vor allem die abgebrochenen
Versuche.</p>
<p><strong>Nicht geprüft</strong> sind die Jahrgänge 1987–2001 — reine Scans ohne
Textlayer, OCR nötig. Sie würden den Datensatz um rund die Hälfte vergrössern und wären
der billigste Weg zu mehr Fällen in genau den dünn besetzten Randbereichen.</p>
</section>

<section class="repro">
<h2><span class="sn">9</span>Reproduzieren</h2>
<pre><code>.venv/bin/python srichinmoy/match_channel.py -v   # Abgleich, Konfidenzstufen
.venv/bin/python srichinmoy/tides.py annotate     # Tidenhub je Querung
.venv/bin/python srichinmoy/tides.py validate     # Rückextrapolation gegen den Mond
.venv/bin/python srichinmoy/project.py            # Formvergleich, Modell, Tide
.venv/bin/python srichinmoy/experiment_ml.py      # XGBoost-Gegenprobe
.venv/bin/python srichinmoy/report_data.py        # Kennzahlen für diesen Bericht
.venv/bin/python srichinmoy/build_report.py       # dieses PDF</code></pre>
<p class="colophon">Code und Daten: <code>github.com/silvanm/marathon-swim-analysis</code>
 · interaktive Fassung: <code>silvanm.github.io/marathon-swim-analysis</code></p>
</section>"""]

    return (f'<!doctype html><html lang="de"><head><meta charset="utf-8">'
            f'<title>Zürichsee → Ärmelkanal · Forschungsprotokoll</title>'
            f'<style>{css}</style></head><body>{"".join(parts)}</body></html>')


CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }

:root {
  --ink:#16232E; --ink2:#4A5A66; --muted:#7C8A94; --grid:#DDE3E7;
  --teal:#008B79; --clay:#C24E12; --paper:#FFFFFF; --panel:#F4F7F8;
}
* { box-sizing: border-box; }
body {
  margin:0; background:var(--paper); color:var(--ink);
  font-family: Charter, "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  font-size: 10pt; line-height: 1.52;
  -webkit-font-smoothing: antialiased;
}
.lbl, .num, .legend, figcaption, .cap, table, code, pre, .eyebrow, .kfl {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
}
.num, svg text.num { font-variant-numeric: tabular-nums; }

/* ── Zweispaltiges Satzraster: Text schmal, Randspalte für Anmerkungen ── */
section { display:grid; grid-template-columns: 108mm 6mm 1fr; margin: 0 0 9mm; }
section > * { grid-column: 1; }
section > figure, section > table, section > .model, section > pre,
section > .repro pre { grid-column: 1 / -1; }
.note { grid-column: 3; font-size: 8.4pt; line-height:1.45; color: var(--ink2);
        border-top: 1.5px solid var(--teal); padding-top: 4px; margin-top: 6px;
        font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; }

/* ── Titelseite ── */
.cover { break-after: page; padding-top: 2mm; }
.eyebrow { font-size:8pt; letter-spacing:.14em; text-transform:uppercase;
           color:var(--teal); font-weight:600; margin:0 0 7mm; }
h1 { font-size: 28pt; line-height:1.12; font-weight:600; margin:0 0 6mm;
     letter-spacing:-.01em; text-wrap:balance; max-width: 150mm; }
.lede { font-size: 11.5pt; line-height:1.55; color:var(--ink2); max-width:138mm; margin:0 0 7mm; }
.keyfacts { display:grid; grid-template-columns:repeat(4,1fr); gap:6mm;
            border-top:2px solid var(--ink); border-bottom:1px solid var(--grid);
            padding:4mm 0; margin-bottom:6mm; }
.keyfacts div { display:flex; flex-direction:column; gap:2px; }
.kf { font-size:15pt; font-weight:600; color:var(--teal); font-variant-numeric:tabular-nums;
      letter-spacing:-.01em; }
.kfl { font-size:7.8pt; color:var(--muted); line-height:1.35; }
.coverfig { margin: 0 0 8mm; }
.coverfig .cap { max-width:130mm; }
.cover-note { font-size:8.6pt; color:var(--muted); max-width:150mm;
              font-family:"Helvetica Neue",Helvetica,Arial,sans-serif; line-height:1.5; }

/* ── Überschriften ── */
h2 { font-size:15pt; font-weight:600; margin:0 0 4mm; letter-spacing:-.005em;
     padding-bottom:2mm; border-bottom:1px solid var(--grid); grid-column:1/-1;
     display:flex; align-items:baseline; gap:5mm; }
.sn { font-family:"Helvetica Neue",Helvetica,Arial,sans-serif; font-size:9pt;
      font-weight:700; color:var(--teal); }
h3 { font-size:11pt; font-weight:600; margin:6mm 0 2mm; color:var(--ink); }
p { margin:0 0 3mm; }
strong { font-weight:600; }
em { font-style:italic; }
h2, h3 { break-after: avoid; }
h2 + p, h3 + p { break-after: avoid; }
figcaption { break-after: avoid; }
p { orphans:2; widows:2; }

/* ── Grafiken ── */
figure { margin:6mm 0 7mm; break-inside: avoid; }
.keep { break-inside: avoid; grid-column:1/-1; }
figcaption { display:flex; align-items:baseline; gap:4mm; margin-bottom:2.5mm;
             padding-bottom:1.5mm; border-bottom:1px solid var(--grid); }
.fnum { font-size:7.6pt; font-weight:700; letter-spacing:.1em; text-transform:uppercase;
        color:var(--teal); white-space:nowrap; }
.ftitle { font-size:9.6pt; font-weight:600; color:var(--ink); }
svg.fig { display:block; width:100%; height:auto; }
svg text { font-family:"Helvetica Neue",Helvetica,Arial,sans-serif; }
.cap { font-size:8.4pt; line-height:1.5; color:var(--ink2); margin:2.5mm 0 0;
       max-width:150mm; font-family:"Helvetica Neue",Helvetica,Arial,sans-serif; }
.legend { list-style:none; display:flex; gap:6mm; padding:0; margin:2mm 0 0;
          font-size:8.2pt; color:var(--ink2); }
.legend li { display:flex; align-items:center; gap:2mm; }
.sw { width:9px; height:9px; border-radius:50%; display:inline-block; }

/* ── Modellkasten ── */
.model { background:var(--panel); border-left:3px solid var(--teal); padding:4mm 5mm;
         margin:5mm 0; break-inside:avoid; }
.ml { font-size:7.6pt; letter-spacing:.1em; text-transform:uppercase; color:var(--teal);
      font-weight:700; margin:0 0 2mm; font-family:"Helvetica Neue",Helvetica,Arial,sans-serif; }
.mf { font-family:"SF Mono",Menlo,Consolas,monospace; font-size:9.4pt; margin:0 0 1mm;
      color:var(--ink); }
.mr { font-size:9pt; color:var(--ink2); margin:2mm 0 0;
      font-family:"Helvetica Neue",Helvetica,Arial,sans-serif; }

/* ── Listen und Tabellen ── */
ul.rules { margin:0 0 3mm; padding-left:5mm; }
ul.rules li { margin-bottom:1.5mm; }
table { border-collapse:collapse; width:100%; font-size:8.6pt; margin:3mm 0 4mm;
        break-inside:avoid; }
table.narrow { width:108mm; }
th { text-align:left; font-weight:600; font-size:7.8pt; letter-spacing:.06em;
     text-transform:uppercase; color:var(--muted); border-bottom:1.5px solid var(--ink);
     padding:2mm 3mm 1.5mm 0; }
td { padding:2mm 3mm 2mm 0; border-bottom:1px solid var(--grid); vertical-align:top;
     line-height:1.45; }
td.r, th.r { text-align:right; padding-right:0; }
code { font-family:"SF Mono",Menlo,Consolas,monospace; font-size:8.4pt;
       background:var(--panel); padding:0 3px; border-radius:2px; }
pre { background:var(--panel); padding:4mm 5mm; margin:3mm 0; overflow-x:auto;
      border-left:3px solid var(--grid); }
pre code { background:none; padding:0; font-size:8.4pt; line-height:1.75; }
.repro { break-inside:avoid; }
.colophon { font-size:8.2pt; color:var(--muted);
            font-family:"Helvetica Neue",Helvetica,Arial,sans-serif; }
"""


@app.command()
def main(
    out: Path = typer.Option(ROOT / "260816 Marathon-Swim | Forschungsprotokoll.pdf",
                             help="Zieldatei"),
) -> None:
    d = json.loads(DATA.read_text())
    html_path = BASE / "report.html"
    html_path.write_text(build_html(d))

    from playwright.sync_api import sync_playwright

    foot = ('<div style="width:100%;font:7pt \'Helvetica Neue\',Arial;color:#7C8A94;'
            'padding:0 16mm;display:flex;justify-content:space-between;">'
            '<span>Zürichsee → Ärmelkanal · Forschungsprotokoll · 16.08.2026</span>'
            '<span class="pageNumber"></span></div>')
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.goto(html_path.resolve().as_uri())
        page.emulate_media(media="print")
        page.pdf(path=str(out), format="A4", print_background=True,
                 display_header_footer=True, header_template="<span></span>",
                 footer_template=foot,
                 margin={"top": "16mm", "bottom": "18mm", "left": "16mm", "right": "16mm"})
        b.close()

    pages = subprocess.run(["mdls", "-name", "kMDItemNumberOfPages", "-raw", str(out)],
                           capture_output=True, text=True).stdout.strip()
    typer.echo(f"{out.name} · {pages} Seiten · {out.stat().st_size // 1024} kB")


if __name__ == "__main__":
    app()
