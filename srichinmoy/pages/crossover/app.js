(function () {
  "use strict";

  var D = JSON.parse(document.getElementById("data").textContent);
  var M = D.model;
  var PAIRS = D.pairs;

  var C_M = "var(--s1)", C_F = "var(--s2)";

  // ---------- formatting ----------
  function hm(hours) {
    if (hours == null || !isFinite(hours)) return "–";
    var s = Math.round(hours * 3600);
    return Math.floor(s / 3600) + ":" + String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  }
  function hms(sec) {
    return Math.floor(sec / 3600) + ":" + String(Math.floor((sec % 3600) / 60)).padStart(2, "0")
      + ":" + String(sec % 60).padStart(2, "0");
  }
  function num(v, d) { return v.toFixed(d).replace(".", ","); }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  // ---------- model ----------
  // Additive: the Channel costs a surcharge that does not depend on the lake time.
  // The surcharge is strictly positive and right-skewed, hence log-normal — which is why
  // the interval is asymmetric rather than a symmetric ± band.
  function fit(x) { return x + M.median; }
  function loBound(x) { return x + M.lo95; }
  function hiBound(x) { return x + M.hi95; }

  // ---------- calculator ----------
  var timeEl = document.getElementById("zh-time");
  var rangeEl = document.getElementById("zh-range");

  function parseTime(str) {
    var t = String(str).trim().replace(",", ".");
    // "9:30" and "9h30" are always hours and minutes.
    var m = t.match(/^(\d{1,2})\s*[:h]\s*(\d{1,2})$/i);
    if (m) return +m[1] + +m[2] / 60;
    // A dot is ambiguous: "9.5" means nine and a half, "9.30" means half past nine.
    // One digit after the dot is a fraction, two digits are minutes.
    m = t.match(/^(\d{1,2})\.(\d{1,2})$/);
    if (m) return m[2].length === 1 ? +m[1] + +m[2] / 10 : +m[1] + +m[2] / 60;
    m = t.match(/^(\d{1,2})\s*h?$/i);
    if (m) return +m[1];
    return null;
  }

  function renderCalc(hours) {
    var mid = fit(hours), lo = loBound(hours), hi = hiBound(hours);
    document.getElementById("out-mid").innerHTML =
      hm(mid) + " <span>erwartete Kanalzeit</span>";
    document.getElementById("out-range").textContent =
      "95 % der Vergleichbaren zwischen " + hm(lo) + " und " + hm(hi) + " h";

    var g = document.getElementById("gauge");
    g.querySelectorAll(".tick").forEach(function (n) { n.remove(); });
    g.querySelector(".mid").style.left = ((mid - lo) / (hi - lo) * 100) + "%";
    [[0, hm(lo)], [100, hm(hi)]].forEach(function (t) {
      var n = document.createElement("div");
      n.className = "tick";
      n.style.left = t[0] + "%";
      n.textContent = t[1];
      g.appendChild(n);
    });

    document.getElementById("calc-caption").textContent =
      "Rund " + hm(M.median) + " h Aufschlag auf deine Seezeit — das entspricht hier dem "
      + num(mid / hours, 2) + "-fachen, bei einer anderen Seezeit wäre der Faktor ein anderer, "
      + "der Aufschlag aber derselbe. Nach oben ist die Spanne länger als nach unten: "
      + "ungünstige Gezeiten kosten Stunden, schneller als das eigene Tempo geht es nicht.";

    drawMarker(hours);
  }

  function setFromHours(h, updateText) {
    h = Math.min(13.5, Math.max(6, h));
    rangeEl.value = Math.round(h * 60);
    if (updateText) timeEl.value = hm(h);
    renderCalc(h);
  }

  timeEl.addEventListener("input", function () {
    var h = parseTime(timeEl.value);
    if (h != null && h >= 4 && h <= 20) {
      rangeEl.value = Math.round(Math.min(13.5, Math.max(6, h)) * 60);
      renderCalc(h);
    }
  });
  timeEl.addEventListener("blur", function () {
    var h = parseTime(timeEl.value);
    setFromHours(h == null ? 9 : h, true);
  });
  rangeEl.addEventListener("input", function () {
    setFromHours(+rangeEl.value / 60, true);
  });

  // ---------- shared svg helpers ----------
  var NS = "http://www.w3.org/2000/svg";
  function el(name, attrs, text) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  var tip = document.getElementById("tip");
  function showTip(evt, html) {
    tip.innerHTML = html;
    tip.style.opacity = "1";
    var r = tip.getBoundingClientRect();
    tip.style.left = Math.min(evt.clientX + 14, window.innerWidth - r.width - 8) + "px";
    tip.style.top = Math.max(8, evt.clientY - r.height - 12) + "px";
  }
  function hideTip() { tip.style.opacity = "0"; }

  // ---------- scatter ----------
  var SC = { W: 760, H: 440, m: { l: 54, r: 16, t: 14, b: 46 } };
  var xLo = 6, xHi = 13.5, yLo = 7, yHi = 21;
  function sx(v) { return SC.m.l + (v - xLo) / (xHi - xLo) * (SC.W - SC.m.l - SC.m.r); }
  function sy(v) { return SC.m.t + (yHi - v) / (yHi - yLo) * (SC.H - SC.m.t - SC.m.b); }
  var marker = null;

  function drawScatter() {
    var svg = document.getElementById("scatter");
    svg.textContent = "";
    var iw = SC.W - SC.m.l - SC.m.r, ih = SC.H - SC.m.t - SC.m.b;

    var g = el("g", { class: "axis" });
    for (var yv = 8; yv <= yHi; yv += 2) {
      g.appendChild(el("line", { x1: SC.m.l, x2: SC.W - SC.m.r, y1: sy(yv), y2: sy(yv) }));
      g.appendChild(el("text", { x: SC.m.l - 8, y: sy(yv) + 3.5, "text-anchor": "end" }, yv + " h"));
    }
    for (var xv = 6; xv <= xHi; xv += 1) {
      g.appendChild(el("line", { x1: sx(xv), x2: sx(xv), y1: SC.m.t, y2: SC.m.t + ih,
        stroke: "var(--grid)" }));
      g.appendChild(el("text", { x: sx(xv), y: SC.H - SC.m.b + 16, "text-anchor": "middle" },
        xv + " h"));
    }
    g.appendChild(el("line", { class: "domain", x1: SC.m.l, x2: SC.W - SC.m.r,
      y1: SC.m.t + ih, y2: SC.m.t + ih }));
    svg.appendChild(g);
    svg.appendChild(el("text", { class: "axis-title", x: SC.m.l + iw / 2, y: SC.H - 6,
      "text-anchor": "middle" }, "Zürichsee 26 km"));
    svg.appendChild(el("text", { class: "axis-title", x: 12, y: SC.m.t + ih / 2,
      "text-anchor": "middle", transform: "rotate(-90 12 " + (SC.m.t + ih / 2) + ")" },
      "Ärmelkanal"));

    // prediction band — parallel to the diagonal, clipped to the plot area
    var defs = el("defs", null);
    var clip = el("clipPath", { id: "plotclip" });
    clip.appendChild(el("rect", { x: SC.m.l, y: SC.m.t, width: iw, height: ih }));
    defs.appendChild(clip);
    svg.appendChild(defs);
    svg.appendChild(el("path", {
      d: "M" + sx(xLo) + " " + sy(hiBound(xLo)) + "L" + sx(xHi) + " " + sy(hiBound(xHi))
        + "L" + sx(xHi) + " " + sy(loBound(xHi)) + "L" + sx(xLo) + " " + sy(loBound(xLo)) + "Z",
      fill: "var(--band)", stroke: "none", "clip-path": "url(#plotclip)"
    }));

    // identity line
    svg.appendChild(el("line", { x1: sx(xLo), y1: sy(xLo), x2: sx(xHi), y2: sy(xHi),
      stroke: "var(--ink-3)", "stroke-width": 2, "stroke-dasharray": "5 5", opacity: .7 }));

    // model line: identity shifted up by the median surcharge
    svg.appendChild(el("line", { x1: sx(xLo), y1: sy(fit(xLo)), x2: sx(xHi), y2: sy(fit(xHi)),
      stroke: "var(--ink-2)", "stroke-width": 2, "stroke-linecap": "round",
      "clip-path": "url(#plotclip)" }));

    PAIRS.forEach(function (p) {
      p._x = sx(p.zh_seconds / 3600);
      p._y = sy(p.ch_seconds / 3600);
      svg.appendChild(el("circle", {
        cx: p._x, cy: p._y, r: 4.2, fill: p.gender === "F" ? C_F : C_M,
        "fill-opacity": .72, stroke: "var(--surface)", "stroke-width": 1
      }));
    });

    marker = el("g", { opacity: 0, "pointer-events": "none" });
    marker.appendChild(el("line", { class: "mk-v", stroke: "var(--accent)", "stroke-width": 2 }));
    marker.appendChild(el("circle", { class: "mk-c", r: 6, fill: "none",
      stroke: "var(--accent)", "stroke-width": 2.5 }));
    svg.appendChild(marker);

    var hover = el("circle", { r: 7, fill: "none", stroke: "var(--ink)", "stroke-width": 2,
      opacity: 0, "pointer-events": "none" });
    svg.appendChild(hover);

    svg.onmousemove = function (evt) {
      var r = svg.getBoundingClientRect();
      var px = (evt.clientX - r.left) / r.width * SC.W;
      var py = (evt.clientY - r.top) / r.height * SC.H;
      var best = null, bd = 1e9;
      PAIRS.forEach(function (p) {
        var d = Math.pow(p._x - px, 2) + Math.pow(p._y - py, 2);
        if (d < bd) { bd = d; best = p; }
      });
      if (!best || bd > 500) { hover.setAttribute("opacity", 0); hideTip(); return; }
      hover.setAttribute("cx", best._x);
      hover.setAttribute("cy", best._y);
      hover.setAttribute("opacity", 1);
      showTip(evt, '<div class="t-name">' + esc(best.name) + "</div>" +
        '<div class="t-row">Zürichsee ' + best.zh_year + " · " + hms(best.zh_seconds) + "</div>" +
        '<div class="t-row">Kanal ' + best.ch_year + " · " + hms(best.ch_seconds) + "</div>" +
        '<div class="t-row">Faktor ' + num(best.ratio, 2) + "</div>");
    };
    svg.onmouseleave = function () { hover.setAttribute("opacity", 0); hideTip(); };

    document.getElementById("legend").innerHTML =
      '<span><i style="background:' + C_M + '"></i>Männer</span>' +
      '<span><i style="background:' + C_F + '"></i>Frauen</span>' +
      '<span><i class="line" style="background:var(--ink-2)"></i>Seezeit + ' +
        hm(M.median) + " h</span>" +
      '<span><i class="area" style="background:var(--band)"></i>95 % der Ergebnisse</span>' +
      '<span><i class="dash"></i>gleiche Zeit</span>';
  }

  function drawMarker(hours) {
    if (!marker) return;
    var x = Math.min(xHi, Math.max(xLo, hours));
    marker.querySelector(".mk-v").setAttribute("x1", sx(x));
    marker.querySelector(".mk-v").setAttribute("x2", sx(x));
    marker.querySelector(".mk-v").setAttribute("y1", sy(Math.min(yHi, hiBound(x))));
    marker.querySelector(".mk-v").setAttribute("y2", sy(loBound(x)));
    marker.querySelector(".mk-c").setAttribute("cx", sx(x));
    marker.querySelector(".mk-c").setAttribute("cy", sy(fit(x)));
    marker.setAttribute("opacity", 1);
  }

  // ---------- facts ----------
  function renderFacts() {
    var items = [
      ["Paare", String(M.n), "Personen mit beiden Zeiten"],
      ["Modell", "Seezeit + " + hm(M.median), "Median-Aufschlag für den Kanal"],
      ["Bandbreite", hm(M.lo95) + " – " + hm(M.hi95), "Aufschlag bei 95 % der Ergebnisse"],
      ["Aufschlag ↔ Tempo", num(M.corr_surcharge_vs_time, 2).replace("-", "−"),
        "Korrelation ≈ 0, also unabhängig vom Tempo"],
      ["Zusammenhang", "r = " + num(M.r, 2), "Seezeit gegen Kanalzeit"]
    ];
    document.getElementById("facts").innerHTML = items.map(function (it) {
      return '<div class="fact"><dt>' + esc(it[0]) + "</dt><dd>" + esc(it[1]) +
        "<small>" + esc(it[2]) + "</small></dd></div>";
    }).join("");
  }

  // ---------- surcharge by speed band ----------
  function renderBands() {
    var defs = [[0, 8, "unter 8 h"], [8, 9.5, "8 – 9:30"], [9.5, 11, "9:30 – 11 h"],
      [11, 99, "über 11 h"]];
    var rows = defs.map(function (d) {
      var sel = PAIRS.filter(function (p) {
        var h = p.zh_seconds / 3600;
        return h >= d[0] && h < d[1];
      });
      var sur = sel.map(function (p) { return p.surcharge; })
        .sort(function (a, b) { return a - b; });
      var rat = sel.map(function (p) { return p.ratio; })
        .sort(function (a, b) { return a - b; });
      return { label: d[2], n: sur.length,
        med: sur[sur.length >> 1],
        lo: sur[Math.floor(sur.length * 0.25)],
        hi: sur[Math.floor(sur.length * 0.75)],
        ratio: rat[rat.length >> 1] };
    });

    var svg = document.getElementById("bands");
    svg.textContent = "";
    var W = 760, H = 200, m = { l: 106, r: 96, t: 10, b: 34 };
    var iw = W - m.l - m.r;
    var lo = 0, hi = 8;
    function X(v) { return m.l + (v - lo) / (hi - lo) * iw; }

    var g = el("g", { class: "axis" });
    for (var v = 0; v <= hi + 1e-9; v += 1) {
      g.appendChild(el("line", { x1: X(v), x2: X(v), y1: m.t, y2: H - m.b }));
      g.appendChild(el("text", { x: X(v), y: H - m.b + 15, "text-anchor": "middle" },
        "+" + v + " h"));
    }
    g.appendChild(el("line", { class: "domain", x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b }));
    svg.appendChild(g);
    svg.appendChild(el("text", { class: "axis-title", x: m.l + iw / 2, y: H - 4,
      "text-anchor": "middle" }, "Aufschlag gegenüber der Seezeit"));

    // the model's median, as a reference the bars should all sit on
    svg.appendChild(el("line", { x1: X(M.median), x2: X(M.median), y1: m.t, y2: H - m.b,
      stroke: "var(--accent)", "stroke-width": 2, "stroke-dasharray": "4 4", opacity: .55 }));

    var rowH = (H - m.t - m.b) / rows.length;
    rows.forEach(function (r, i) {
      var cy = m.t + rowH * (i + 0.5);
      svg.appendChild(el("text", { x: m.l - 12, y: cy + 4, "text-anchor": "end",
        "font-size": 12.5, fill: "var(--ink-2)", "font-family": "var(--sans)" }, r.label));
      svg.appendChild(el("line", { x1: X(r.lo), x2: X(r.hi), y1: cy, y2: cy,
        stroke: "var(--band)", "stroke-width": 12, "stroke-linecap": "round" }));
      svg.appendChild(el("circle", { cx: X(r.med), cy: cy, r: 5.5, fill: "var(--accent)",
        stroke: "var(--surface)", "stroke-width": 1.5 }));
      svg.appendChild(el("text", { x: X(r.med), y: cy - 13, "text-anchor": "middle",
        "font-size": 11.5, fill: "var(--ink)", "font-family": "var(--mono)" },
        "+" + hm(r.med) + " h"));
      svg.appendChild(el("text", { x: W - m.r + 10, y: cy + 4, "font-size": 11.5,
        fill: "var(--ink-3)", "font-family": "var(--mono)" },
        "n=" + r.n + " · ×" + num(r.ratio, 2)));
    });
  }

  // ---------- table ----------
  var COLS = [
    { k: null, t: "#" },
    { k: "name", t: "Name" },
    { k: "zh_year", t: "See", cls: "num" },
    { k: "zh_seconds", t: "Zürichsee", cls: "num" },
    { k: "ch_year", t: "Kanal", cls: "num" },
    { k: "ch_seconds", t: "Ärmelkanal", cls: "num" },
    { k: "surcharge", t: "Aufschlag", cls: "num" },
    { k: "ratio", t: "Faktor", cls: "num" },
    { k: "gap_years", t: "Abstand", cls: "num" },
    { k: "zh_nat", t: "Nation" }
  ];
  var S = { q: "", gender: "all", gap: 99, order: "all" };
  var sortKey = "ratio", sortDir = 1, view = [];

  PAIRS.forEach(function (p) {
    // The source uses "N/A" as an empty club — don't render it as a value.
    if (/^(n\/a|na|-|\?)$/i.test((p.zh_club || "").trim())) p.zh_club = "";
    p.hay = (p.name + " " + p.zh_nat + " " + p.zh_club).toLowerCase();
  });

  function applyTable() {
    view = PAIRS.filter(function (p) {
      if (S.gender !== "all" && p.gender !== S.gender) return false;
      if (p.gap_years > S.gap) return false;
      if (S.order === "zh" && !p.zh_first) return false;
      if (S.order === "ch" && p.zh_first) return false;
      if (S.q && p.hay.indexOf(S.q) === -1) return false;
      return true;
    });
    view.sort(function (a, b) {
      var x = a[sortKey], y = b[sortKey];
      if (typeof x === "string") return sortDir * x.localeCompare(y, "de");
      return sortDir * (x - y);
    });
    renderRows();
  }

  function renderHead() {
    document.getElementById("thead-row").innerHTML = COLS.map(function (c) {
      if (!c.k) return '<th class="static" scope="col">#</th>';
      var active = sortKey === c.k;
      return '<th data-k="' + c.k + '" scope="col" aria-sort="' +
        (active ? (sortDir === 1 ? "ascending" : "descending") : "none") + '">' +
        esc(c.t) + (active ? " " + (sortDir === 1 ? "▲" : "▼") : "") + "</th>";
    }).join("");
    document.querySelectorAll("#thead-row th[data-k]").forEach(function (th) {
      th.addEventListener("click", function () {
        var k = th.dataset.k;
        if (sortKey === k) sortDir = -sortDir;
        else { sortKey = k; sortDir = (k === "name" || k === "zh_nat") ? 1 : 1; }
        renderHead(); applyTable();
      });
    });
  }

  function renderRows() {
    document.getElementById("tbody").innerHTML = view.map(function (p, i) {
      return "<tr>" +
        '<td class="num pos">' + (i + 1) + "</td>" +
        '<td><span class="dot" style="background:' + (p.gender === "F" ? C_F : C_M) + '"></span>' +
        '<span class="name">' + esc(p.name) + "</span>" +
        (p.zh_club ? '<div class="sub">' + esc(p.zh_club) + "</div>" : "") + "</td>" +
        '<td class="num">' + p.zh_year + "</td>" +
        '<td class="num">' + hms(p.zh_seconds) + "</td>" +
        '<td class="num">' + p.ch_year + "</td>" +
        '<td class="num">' + hms(p.ch_seconds) + "</td>" +
        '<td class="num">+' + hm(p.surcharge) + "</td>" +
        '<td class="num">' + num(p.ratio, 2) + "</td>" +
        '<td class="num">' + p.gap_years + "</td>" +
        "<td>" + esc(p.zh_nat) + "</td>" +
        "</tr>";
    }).join("");
    document.getElementById("shown").textContent = view.length + " von " + PAIRS.length + " Paaren";
  }

  document.getElementById("q").addEventListener("input", function (e) {
    S.q = e.target.value.trim().toLowerCase(); applyTable();
  });
  document.getElementById("f-gap").addEventListener("change", function (e) {
    S.gap = +e.target.value; applyTable();
  });
  [["f-gender", "gender"], ["f-order", "order"]].forEach(function (pair) {
    var box = document.getElementById(pair[0]);
    box.addEventListener("click", function (e) {
      var btn = e.target.closest("button");
      if (!btn) return;
      box.querySelectorAll("button").forEach(function (b) {
        b.setAttribute("aria-pressed", String(b === btn));
      });
      S[pair[1]] = btn.dataset.v;
      applyTable();
    });
  });

  document.getElementById("copy").addEventListener("click", function () {
    var head = ["Name", "Geschlecht", "Zuerichsee_Jahr", "Zuerichsee_Zeit", "Zuerichsee_s",
      "Kanal_Jahr", "Kanal_Zeit", "Kanal_s", "Aufschlag_h", "Faktor", "Abstand_Jahre",
      "Nation", "Club"];
    var lines = [head.join(";")].concat(view.map(function (p) {
      return [p.name, p.gender, p.zh_year, hms(p.zh_seconds), p.zh_seconds,
        p.ch_year, hms(p.ch_seconds), p.ch_seconds, num(p.surcharge, 3), num(p.ratio, 3),
        p.gap_years, p.zh_nat, p.zh_club].map(function (v) {
          v = v == null ? "" : String(v);
          return /[;"\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
        }).join(";");
    }));
    var note = document.getElementById("copied");
    function flash(msg) {
      note.textContent = msg; note.hidden = false;
      setTimeout(function () { note.hidden = true; }, 2600);
    }
    var text = lines.join("\n");
    (navigator.clipboard && navigator.clipboard.writeText
      ? navigator.clipboard.writeText(text) : Promise.reject())
      .then(function () { flash(view.length + " Zeilen kopiert."); },
            function () { flash("Die Zwischenablage ist hier gesperrt."); });
  });

  // ---------- go ----------
  drawScatter();
  renderFacts();
  renderBands();
  renderHead();
  applyTable();
  setFromHours(9, true);
})();
