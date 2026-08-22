(function () {
  "use strict";

  var RAW = JSON.parse(document.getElementById("data").textContent);
  var C = {};
  RAW.cols.forEach(function (name, i) { C[name] = i; });

  var ALL = RAW.rows.map(function (r) {
    return {
      year: r[C.year], rank: r[C.rank], status: r[C.status],
      last: r[C.last_name] || "", first: r[C.first_name] || "",
      yob: r[C.year_of_birth], age: r[C.age],
      nat: r[C.nationality] || "", city: r[C.home_city] || "", club: r[C.club] || "",
      gender: r[C.gender], cls: r[C.age_class],
      suit: r[C.wetsuit], relay: r[C.relay], team: r[C.relay_team_name] || "",
      split: r[C.split_seconds], finish: r[C.finish_seconds], speed: r[C.speed_kmh],
      cat: r[C.category_raw] || ""
    };
  });
  ALL.forEach(function (d) {
    d.name = (d.first ? d.first + " " : "") + d.last;
    d.key = (d.last + "|" + d.first).toLowerCase();
    d.hay = (d.name + " " + d.club + " " + d.city + " " + d.nat + " " + d.team).toLowerCase();
    d.rows = [d];            // an entry always knows the source rows behind it
  });

  // ---------- relay teams ----------
  // The source has one row per relay swimmer: the team's rank and time repeat on each of them.
  // For a team ranking those rows are folded into a single entry. A name alone is not a team
  // identity — Club Batan de Natacion fielded two teams in 2003 — so the key carries category,
  // rank, status and time as well.
  function uniq(a) {
    var seen = {}, out = [];
    a.forEach(function (v) { if (v && !seen[v]) { seen[v] = 1; out.push(v); } });
    return out;
  }
  function firstNotNull(rows, k) {
    for (var i = 0; i < rows.length; i++) if (rows[i][k] != null) return rows[i][k];
    return null;
  }
  function makeTeam(rows) {
    var r = rows[0];
    var members = rows.map(function (d) { return d.name; }).filter(Boolean);
    // A handful of old rankings list a relay without its team name; then the surnames stand in.
    var label = r.team || (members.length
      ? uniq(rows.map(function (d) { return d.last; })).join(" / ")
      : "Staffel ohne Namen");
    var t = {
      year: r.year, rank: r.rank, status: r.status,
      last: label, first: "", name: label, team: r.team,
      yob: null, age: null,
      nat: uniq(rows.map(function (d) { return d.nat; })).join(", "),
      city: uniq(rows.map(function (d) { return d.city; })).join(", "),
      club: uniq(rows.map(function (d) { return d.club; })).join(", "),
      gender: r.gender, cls: r.cls, suit: r.suit, relay: 1,
      split: firstNotNull(rows, "split"), finish: firstNotNull(rows, "finish"),
      speed: firstNotNull(rows, "speed"), cat: r.cat,
      members: members, rows: rows, isTeam: true
    };
    t.key = "team|" + (r.team || label).toLowerCase();
    t.hay = (label + " " + members.join(" ") + " " + t.club + " " + t.city + " " +
             t.nat).toLowerCase();
    return t;
  }

  var SOLO = ALL.filter(function (d) { return !d.relay; });
  var TEAMS = (function () {
    var groups = {}, order = [];
    ALL.forEach(function (d) {
      if (!d.relay) return;
      var k = [d.year, d.cat, d.suit, d.status, d.rank, d.finish, d.team].join("\u00a6");
      if (!groups[k]) { groups[k] = []; order.push(k); }
      groups[k].push(d);
    });
    return order.map(function (k) { return makeTeam(groups[k]); });
  })();
  // The field a team is ranked against: teams that finished the full distance. Teams with a
  // time but outside the classification (HC, OTHER) are not part of it.
  var TEAMS_FIN = TEAMS.filter(function (t) {
    return t.finish != null && t.status === "FINISHED";
  });

  // Position of one entry in a field, counting only finishers: "3. von 449".
  function rankAmong(list, t) {
    var faster = 0, n = 0;
    list.forEach(function (o) {
      if (o.finish == null) return;
      n++;
      if (o.finish < t.finish) faster++;
    });
    return { pos: faster + 1, n: n };
  }
  function fmtRank(r) { return r ? r.pos + ". von " + fmtInt(r.n) : "–"; }

  var YEARS = Array.from(new Set(ALL.map(function (d) { return d.year; }))).sort();
  var Y_MIN = YEARS[0], Y_MAX = YEARS[YEARS.length - 1];

  // ---------- formatting ----------
  var nf = new Intl.NumberFormat("de-CH");
  function fmtInt(n) { return nf.format(n); }
  function fmtTime(s) {
    if (s == null) return "–";
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return h + ":" + String(m).padStart(2, "0") + ":" + String(x).padStart(2, "0");
  }
  function fmtHM(s) {
    if (s == null) return "–";
    return Math.floor(s / 3600) + ":" + String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  }
  function fmtSpeed(v) { return v == null ? "–" : v.toFixed(2).replace(".", ","); }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function catLabel(d) {
    var bits = [];
    bits.push(d.relay ? "Staffel" : d.gender === "F" ? "Frauen" : d.gender === "M" ? "Männer" : "Offen");
    if (d.cls === "MASTERS") bits.push("Masters");
    if (d.cls === "JUNIORS") bits.push("Junioren");
    if (d.suit) bits.push("Neopren");
    return bits.join(" · ");
  }
  function median(a) {
    if (!a.length) return null;
    var s = a.slice().sort(function (x, y) { return x - y; }), h = s.length >> 1;
    return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2;
  }

  // ---------- state ----------
  var S = { q: "", y1: Y_MIN, y2: Y_MAX, gender: "all", cls: "all", type: "all", suit: "all",
    status: "fin", teams: "team" };
  var sortKey = "finish", sortDir = 1, limit = 200;
  var view = [];

  function passes(d) {
    if (d.year < S.y1 || d.year > S.y2) return false;
    if (S.gender !== "all" && d.gender !== S.gender) return false;
    if (S.cls !== "all" && d.cls !== S.cls) return false;
    if (S.type === "solo" && d.relay) return false;
    if (S.type === "relay" && !d.relay) return false;
    if (S.suit !== "all" && String(d.suit) !== S.suit) return false;
    if (S.status === "fin" && d.status !== "FINISHED") return false;
    if (S.q && d.hay.indexOf(S.q) === -1) return false;
    return true;
  }

  // In team mode a relay counts once, so the ranking positions are team positions.
  function source() { return S.teams === "team" ? SOLO.concat(TEAMS) : ALL; }

  function apply() {
    view = source().filter(passes);
    sortView();
    renderStats();
    renderTimes();
    renderCounts();
    renderTable();
  }

  function sortView() {
    var k = sortKey, dir = sortDir;
    view.sort(function (a, b) {
      var x = a[k], y = b[k];
      var ax = x == null || x === "", ay = y == null || y === "";
      if (ax && ay) return a.year - b.year;
      if (ax) return 1;                       // blanks always last
      if (ay) return -1;
      if (typeof x === "string") return dir * x.localeCompare(y, "de") || a.year - b.year;
      return dir * (x - y) || a.year - b.year;
    });
  }

  // ---------- stats ----------
  function renderStats() {
    var fin = view.filter(function (d) { return d.finish != null; });
    var times = fin.map(function (d) { return d.finish; });
    var people = new Set();
    view.forEach(function (d) {
      d.rows.forEach(function (r) { if (r.last) people.add(r.key); });
    });
    var best = times.length ? Math.min.apply(null, times) : null;
    var bestRow = best == null ? null : fin.find(function (d) { return d.finish === best; });
    var yrs = new Set(view.map(function (d) { return d.year; }));
    var items = [
      [S.teams === "team" ? "Wertungen" : "Ergebnisse", fmtInt(view.length), ""],
      ["Personen", fmtInt(people.size), ""],
      ["Jahrgänge", fmtInt(yrs.size), ""],
      ["Schnellste Zeit", best == null ? "–" : fmtTime(best),
        bestRow ? bestRow.name + ", " + bestRow.year : ""],
      ["Median-Zeit", times.length ? fmtTime(Math.round(median(times))) : "–", ""],
      ["Ø Tempo", fin.length ? fmtSpeed(median(fin.map(function (d) { return d.speed; }).filter(function (v) { return v != null; }))) : "–", "km/h"]
    ];
    document.getElementById("stats").innerHTML = items.map(function (it) {
      return '<div class="stat"><dt>' + it[0] + "</dt><dd>" + esc(it[1]) +
        (it[2] ? "<small>" + esc(it[2]) + "</small>" : "") + "</dd></div>";
    }).join("");
  }

  // ---------- shared chart helpers ----------
  var SVGNS = "http://www.w3.org/2000/svg";
  function el(name, attrs, text) {
    var n = document.createElementNS(SVGNS, name);
    for (var k in attrs) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  function niceTicks(lo, hi, count) {
    var span = hi - lo || 1;
    var step = Math.pow(10, Math.floor(Math.log10(span / count)));
    var err = (span / count) / step;
    if (err >= 7.5) step *= 10; else if (err >= 3) step *= 5; else if (err >= 1.5) step *= 2;
    var out = [], v = Math.ceil(lo / step) * step;
    for (; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }
  function yearTicks(years) {
    if (years.length <= 8) return years.slice();
    var every = Math.ceil(years.length / 8);
    return years.filter(function (_, i) { return i % every === 0 || i === years.length - 1; });
  }

  var tip = document.getElementById("tip");
  function showTip(evt, html) {
    tip.innerHTML = html;
    tip.style.opacity = "1";
    var r = tip.getBoundingClientRect();
    var x = Math.min(evt.clientX + 14, window.innerWidth - r.width - 8);
    var y = Math.max(8, evt.clientY - r.height - 12);
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }
  function hideTip() { tip.style.opacity = "0"; }

  function legendFor(node, items) {
    node.innerHTML = items.map(function (it) {
      return '<span><i style="background:' + it[1] + '"></i>' + esc(it[0]) + "</span>";
    }).join("");
  }

  // ---------- chart 1: finish times per year ----------
  var C_SOLO = "var(--s1)", C_RELAY = "var(--s3)";
  var timePts = [];

  function renderTimes() {
    var svg = document.getElementById("chart-times");
    svg.textContent = "";
    timePts = [];
    var W = 720, H = 340, m = { l: 48, r: 14, t: 12, b: 30 };
    var iw = W - m.l - m.r, ih = H - m.t - m.b;
    var years = YEARS.filter(function (y) { return y >= S.y1 && y <= S.y2; });
    var pts = view.filter(function (d) { return d.finish != null; });

    if (!pts.length || !years.length) {
      svg.appendChild(el("text", { x: W / 2, y: H / 2, "text-anchor": "middle",
        fill: "var(--ink-3)", "font-size": 13 }, "Keine Finisher in dieser Auswahl"));
      legendFor(document.getElementById("legend-times"), []);
      return;
    }

    var lo = Math.min.apply(null, pts.map(function (d) { return d.finish; })) / 3600;
    var hi = Math.max.apply(null, pts.map(function (d) { return d.finish; })) / 3600;
    var pad = Math.max(0.2, (hi - lo) * 0.06);
    lo = Math.max(0, lo - pad); hi = hi + pad;

    var band = iw / years.length;
    function xOf(y) { return m.l + (years.indexOf(y) + 0.5) * band; }
    function yOf(h) { return m.t + (h - lo) / (hi - lo) * ih; }

    var g = el("g", { class: "axis" });
    niceTicks(lo, hi, 5).forEach(function (t) {
      var y = yOf(t);
      g.appendChild(el("line", { x1: m.l, x2: W - m.r, y1: y, y2: y }));
      g.appendChild(el("text", { x: m.l - 8, y: y + 3.5, "text-anchor": "end" }, t + " h"));
    });
    g.appendChild(el("line", { class: "domain", x1: m.l, x2: W - m.r, y1: m.t + ih, y2: m.t + ih }));
    yearTicks(years).forEach(function (y) {
      g.appendChild(el("text", { x: xOf(y), y: H - 10, "text-anchor": "middle" }, String(y)));
    });
    svg.appendChild(g);

    // dots — deterministic jitter so the picture is stable between renders
    var dots = el("g", null);
    pts.forEach(function (d, i) {
      var jw = Math.min(band * 0.62, 26);
      var j = (((i * 2654435761) % 1000) / 1000 - 0.5) * jw;
      var cx = xOf(d.year) + j, cy = yOf(d.finish / 3600);
      timePts.push({ x: cx, y: cy, d: d });
      dots.appendChild(el("circle", {
        cx: cx, cy: cy, r: 2.6, fill: d.relay ? C_RELAY : C_SOLO,
        "fill-opacity": 0.62, stroke: "var(--surface)", "stroke-width": 0.6
      }));
    });
    svg.appendChild(dots);

    // median line
    var med = years.map(function (y) {
      var v = pts.filter(function (d) { return d.year === y; }).map(function (d) { return d.finish; });
      return v.length ? { y: y, m: median(v) } : null;
    }).filter(Boolean);
    if (med.length > 1) {
      svg.appendChild(el("path", {
        d: med.map(function (p, i) { return (i ? "L" : "M") + xOf(p.y) + " " + yOf(p.m / 3600); }).join(" "),
        fill: "none", stroke: "var(--ink-2)", "stroke-width": 2, "stroke-linejoin": "round"
      }));
    }
    med.forEach(function (p) {
      svg.appendChild(el("circle", { cx: xOf(p.y), cy: yOf(p.m / 3600), r: 3.2,
        fill: "var(--ink-2)", stroke: "var(--surface)", "stroke-width": 1.6 }));
    });

    var hover = el("circle", { r: 5.4, fill: "none", stroke: "var(--ink)", "stroke-width": 1.6,
      opacity: 0, "pointer-events": "none" });
    svg.appendChild(hover);

    svg.onmousemove = function (evt) {
      var p = svgPoint(svg, evt, W, H), best = null, bd = 1e9;
      timePts.forEach(function (q) {
        var dx = q.x - p.x, dy = q.y - p.y, dist = dx * dx + dy * dy;
        if (dist < bd) { bd = dist; best = q; }
      });
      if (!best || bd > 400) { hover.setAttribute("opacity", 0); hideTip(); return; }
      hover.setAttribute("cx", best.x); hover.setAttribute("cy", best.y);
      hover.setAttribute("opacity", 1);
      var d = best.d;
      showTip(evt, '<div class="t-name">' + esc(d.name) +
        (!d.isTeam && d.relay && d.team ? " · " + esc(d.team) : "") + "</div>" +
        '<div class="t-row">' + d.year + " · " + fmtTime(d.finish) + " · " + fmtSpeed(d.speed) + " km/h</div>" +
        '<div class="t-row">' + esc(catLabel(d)) + (d.rank ? " · Rang " + d.rank : "") + "</div>");
    };
    svg.onmouseleave = function () { hover.setAttribute("opacity", 0); hideTip(); };

    legendFor(document.getElementById("legend-times"), [
      ["Einzel", "var(--s1)"], ["Staffel", "var(--s3)"], ["Median des Jahres", "var(--ink-2)"]
    ]);
  }

  function svgPoint(svg, evt, W, H) {
    var r = svg.getBoundingClientRect();
    return { x: (evt.clientX - r.left) / r.width * W, y: (evt.clientY - r.top) / r.height * H };
  }

  // ---------- chart 2: participants per year ----------
  function renderCounts() {
    var svg = document.getElementById("chart-count");
    svg.textContent = "";
    var W = 460, H = 340, m = { l: 38, r: 10, t: 12, b: 30 };
    var iw = W - m.l - m.r, ih = H - m.t - m.b;
    var years = YEARS.filter(function (y) { return y >= S.y1 && y <= S.y2; });
    var by = {};
    years.forEach(function (y) { by[y] = { solo: 0, relay: 0 }; });
    view.forEach(function (d) { if (by[d.year]) by[d.year][d.relay ? "relay" : "solo"]++; });
    var max = Math.max.apply(null, years.map(function (y) { return by[y].solo + by[y].relay; }).concat([1]));

    if (!years.length) return;
    var band = iw / years.length, bw = Math.min(band * 0.68, 22);
    function xOf(y) { return m.l + (years.indexOf(y) + 0.5) * band - bw / 2; }
    function hOf(n) { return n / max * ih; }

    var g = el("g", { class: "axis" });
    niceTicks(0, max, 4).forEach(function (t) {
      var y = m.t + ih - hOf(t);
      g.appendChild(el("line", { x1: m.l, x2: W - m.r, y1: y, y2: y }));
      g.appendChild(el("text", { x: m.l - 7, y: y + 3.5, "text-anchor": "end" }, String(t)));
    });
    g.appendChild(el("line", { class: "domain", x1: m.l, x2: W - m.r, y1: m.t + ih, y2: m.t + ih }));
    yearTicks(years).forEach(function (y) {
      g.appendChild(el("text", { x: xOf(y) + bw / 2, y: H - 10, "text-anchor": "middle" }, String(y)));
    });
    svg.appendChild(g);

    years.forEach(function (y) {
      var c = by[y], base = m.t + ih, x = xOf(y);
      var stack = [["solo", c.solo, "var(--s1)"], ["relay", c.relay, "var(--s3)"]];
      var acc = 0;
      stack.forEach(function (s) {
        if (!s[1]) return;
        var h = hOf(s[1]);
        var yTop = base - acc - h;
        svg.appendChild(el("rect", {
          x: x, y: yTop, width: bw, height: Math.max(1, h - (acc ? 2 : 0)), // 2px surface gap
          fill: s[2], rx: 2
        }));
        acc += h;
      });
      svg.appendChild(el("rect", {
        x: x - 2, y: m.t, width: bw + 4, height: ih, fill: "transparent",
        "data-year": y
      })).addEventListener("mousemove", function (evt) {
        showTip(evt, '<div class="t-name">' + y + "</div>" +
          '<div class="t-row">Einzel ' + c.solo + " · " +
          (S.teams === "team" ? "Teams " : "Staffelstarts ") + c.relay + "</div>" +
          '<div class="t-row">Total ' + (c.solo + c.relay) + "</div>");
      });
    });
    svg.onmouseleave = hideTip;

    legendFor(document.getElementById("legend-count"), [
      ["Einzel", "var(--s1)"],
      [S.teams === "team" ? "Staffelteams" : "Staffel-Starts", "var(--s3)"]
    ]);
  }

  // ---------- table ----------
  var COLS = [
    { k: null, t: "#", cls: "num" },        // position in the current sort, not sortable
    { k: "year", t: "Jahr", cls: "num" },
    { k: "rank", t: "Rang", cls: "num" },
    { k: "last", t: "Name" },
    { k: "cat", t: "Kategorie" },
    { k: "finish", t: "Endzeit", cls: "num" },
    { k: "speed", t: "km/h", cls: "num" },
    { k: "split", t: "Meilen", cls: "num" },
    { k: "nat", t: "Nation" },
    { k: "club", t: "Club / Team" }
  ];

  function renderHead() {
    document.getElementById("thead-row").innerHTML = COLS.map(function (c) {
      if (!c.k) return '<th scope="col" class="static" title="Position in dieser Auswahl">#</th>';
      var active = sortKey === c.k;
      return '<th data-k="' + c.k + '" scope="col" aria-sort="' +
        (active ? (sortDir === 1 ? "ascending" : "descending") : "none") + '">' +
        esc(c.t) + (active ? ' <span class="arrow">' + (sortDir === 1 ? "▲" : "▼") + "</span>" : "") + "</th>";
    }).join("");
    Array.prototype.forEach.call(document.querySelectorAll("#thead-row th[data-k]"), function (th) {
      th.addEventListener("click", function () {
        var k = th.dataset.k;
        if (sortKey === k) sortDir = -sortDir;
        else { sortKey = k; sortDir = (k === "last" || k === "nat" || k === "club" || k === "cat") ? 1 : (k === "speed" ? -1 : 1); }
        limit = 200;
        sortView(); renderHead(); renderTable();
      });
    });
  }

  function renderTable() {
    var body = document.getElementById("tbody");
    var rows = view.slice(0, limit);
    body.innerHTML = rows.map(function (d, i) {
      var status = d.status === "FINISHED" ? "" :
        ' <span class="pill ' + d.status.toLowerCase() + '">' + d.status + "</span>";
      return '<tr data-i="' + i + '" tabindex="0" role="button" aria-label="Historie von ' +
        esc(d.name) + '">' +
        '<td class="num pos">' + (i + 1) + "</td>" +
        '<td class="num">' + d.year + "</td>" +
        '<td class="num">' + (d.rank == null ? "" : d.rank) + "</td>" +
        "<td><span class=\"name\">" + esc(d.name) + "</span>" + status +
          (d.isTeam
            ? '<div class="sub">' + esc(d.members.join(" · ")) + "</div>"
            : d.relay && d.team ? '<div class="sub">' + esc(d.team) + "</div>" : "") + "</td>" +
        "<td>" + esc(catLabel(d)) + "</td>" +
        '<td class="num">' + fmtTime(d.finish) + "</td>" +
        '<td class="num">' + fmtSpeed(d.speed) + "</td>" +
        '<td class="num">' + fmtHM(d.split) + "</td>" +
        "<td>" + esc(d.nat) + "</td>" +
        "<td>" + esc(d.isTeam ? d.club : (d.club || d.team)) +
          (d.city ? '<div class="sub">' + esc(d.city) + "</div>" : "") + "</td>" +
        "</tr>";
    }).join("");
    Array.prototype.forEach.call(body.querySelectorAll("tr"), function (tr) {
      var open = function () { openDrawer(rows[+tr.dataset.i]); };
      tr.addEventListener("click", open);
      tr.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      });
    });
    document.getElementById("empty").hidden = view.length > 0;
    document.getElementById("more").hidden = view.length <= limit;
    document.getElementById("shown").textContent =
      fmtInt(Math.min(limit, view.length)) + " von " + fmtInt(view.length) + " Zeilen";
    document.getElementById("table-note").textContent = S.teams === "team"
      ? "Staffeln zählen als ein Team. Zeile anklicken für Historie und Platzierungen."
      : "Zeile anklicken für die vollständige Historie einer Person.";
  }

  // ---------- drawer ----------
  var drawer = document.getElementById("drawer");
  function openDrawer(d) {
    if (d.isTeam) return openTeamDrawer(d);
    return openPersonDrawer(d);
  }

  function openTeamDrawer(t) {
    var hist = TEAMS.filter(function (o) { return o.key === t.key; })
      .sort(function (a, b) { return a.year - b.year; });
    var fins = hist.filter(function (o) { return o.finish != null; });
    var best = fins.length ? Math.min.apply(null, fins.map(function (o) { return o.finish; })) : null;
    var maxT = fins.length ? Math.max.apply(null, fins.map(function (o) { return o.finish; })) : 1;
    var suitField = TEAMS_FIN.filter(function (o) { return o.suit === t.suit; });
    var yearField = TEAMS_FIN.filter(function (o) { return o.year === t.year; });

    document.getElementById("d-name").textContent = t.name;
    var kv = [
      ["Jahr", String(t.year)],
      ["Kategorie", catLabel(t)],
      ["Endzeit", fmtTime(t.finish) + (t.speed == null ? "" : "  ·  " + fmtSpeed(t.speed) + " km/h")],
      ["Rang in der Kategorie", t.rank == null ? "–" : String(t.rank)],
      ["Alle Staffeln 2002–2026", t.finish == null ? "–" : fmtRank(rankAmong(TEAMS_FIN, t))],
      [t.suit ? "Staffeln mit Neopren" : "Staffeln ohne Neopren",
        t.finish == null ? "–" : fmtRank(rankAmong(suitField, t))],
      ["Staffeln " + t.year, t.finish == null ? "–" : fmtRank(rankAmong(yearField, t))],
      ["Mitglieder", t.members.length ? t.members.join(", ") : "–"],
      ["Club", t.club || "–"]
    ];
    // Only worth showing when the current filters actually span more than this one team.
    var sel = view.filter(function (o) { return o.isTeam && o.finish != null; });
    if (t.finish != null && sel.length > 1) {
      kv.splice(7, 0, ["In dieser Auswahl", fmtRank(rankAmong(sel, t))]);
    }
    document.getElementById("d-body").innerHTML =
      '<dl class="kv">' + kv.map(function (p) {
        return "<dt>" + esc(p[0]) + "</dt><dd>" + esc(p[1]) + "</dd>";
      }).join("") + "</dl>" +
      (hist.length > 1
        ? '<p class="note" style="margin:18px 0 0;color:var(--ink-3);font-size:13px">' +
          "Alle Starts unter diesem Teamnamen</p>" +
          '<ul class="hist">' + hist.map(function (o) {
            var w = o.finish ? Math.round(o.finish / maxT * 100) : 0;
            return '<li><span class="y">' + o.year + "</span><span>" + esc(catLabel(o)) +
              (o.rank ? ' <span class="sub">Rang ' + o.rank + "</span>" : "") +
              '<div class="sub">' + esc(o.members.join(" · ")) + "</div>" +
              (o.finish ? '<div class="bars"><i style="width:' + w + '%"></i></div>' : "") +
              '</span><span class="num">' +
              (o.finish ? fmtTime(o.finish) + (o.finish === best && fins.length > 1 ? " ★" : "")
                        : '<span class="pill ' + o.status.toLowerCase() + '">' + o.status + "</span>") +
              "</span></li>";
          }).join("") + "</ul>"
        : "");
    drawer.hidden = false;
    document.getElementById("d-close").focus();
  }

  function openPersonDrawer(d) {
    var hist = ALL.filter(function (r) { return r.key === d.key; })
      .sort(function (a, b) { return a.year - b.year; });
    var fins = hist.filter(function (r) { return r.finish != null; });
    var best = fins.length ? Math.min.apply(null, fins.map(function (r) { return r.finish; })) : null;
    var maxT = fins.length ? Math.max.apply(null, fins.map(function (r) { return r.finish; })) : 1;

    document.getElementById("d-name").textContent = d.name;
    var kv = [
      ["Starts", String(hist.length)],
      ["Im Ziel", String(fins.length)],
      ["Beste Zeit", best == null ? "–" : fmtTime(best)],
      ["Jahrgang", d.yob ? String(d.yob) : (d.age ? "Alter " + d.age : "–")],
      ["Nation", d.nat || "–"],
      ["Club", d.club || d.team || "–"]
    ];
    document.getElementById("d-body").innerHTML =
      '<dl class="kv">' + kv.map(function (p) {
        return "<dt>" + esc(p[0]) + "</dt><dd>" + esc(p[1]) + "</dd>";
      }).join("") + "</dl>" +
      '<ul class="hist">' + hist.map(function (r) {
        var w = r.finish ? Math.round(r.finish / maxT * 100) : 0;
        return '<li><span class="y">' + r.year + "</span><span>" + esc(catLabel(r)) +
          (r.rank ? ' <span class="sub">Rang ' + r.rank + "</span>" : "") +
          (r.finish ? '<div class="bars"><i style="width:' + w + '%"></i></div>' : "") +
          '</span><span class="num">' +
          (r.finish ? fmtTime(r.finish) + (r.finish === best && fins.length > 1 ? " ★" : "")
                    : '<span class="pill ' + r.status.toLowerCase() + '">' + r.status + "</span>") +
          "</span></li>";
      }).join("") + "</ul>";
    drawer.hidden = false;
    document.getElementById("d-close").focus();
  }
  function closeDrawer() { drawer.hidden = true; }
  document.getElementById("d-close").addEventListener("click", closeDrawer);
  document.getElementById("scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeDrawer(); });

  // ---------- controls ----------
  function fillYears() {
    var a = document.getElementById("y1"), b = document.getElementById("y2");
    YEARS.forEach(function (y) {
      a.appendChild(new Option(y, y));
      b.appendChild(new Option(y, y));
    });
    a.value = Y_MIN; b.value = Y_MAX;
    a.addEventListener("change", function () {
      S.y1 = +a.value;
      if (S.y1 > S.y2) { S.y2 = S.y1; b.value = S.y2; }
      limit = 200; apply();
    });
    b.addEventListener("change", function () {
      S.y2 = +b.value;
      if (S.y2 < S.y1) { S.y1 = S.y2; a.value = S.y1; }
      limit = 200; apply();
    });
  }

  function segment(id, key) {
    var box = document.getElementById(id);
    box.addEventListener("click", function (e) {
      var btn = e.target.closest("button");
      if (!btn) return;
      Array.prototype.forEach.call(box.querySelectorAll("button"), function (b) {
        b.setAttribute("aria-pressed", String(b === btn));
      });
      S[key] = btn.dataset.v;
      limit = 200; apply();
    });
  }

  var clsEl = document.getElementById("f-class");
  clsEl.addEventListener("change", function () {
    S.cls = clsEl.value; limit = 200; apply();
  });

  var qEl = document.getElementById("q"), qTimer;
  qEl.addEventListener("input", function () {
    clearTimeout(qTimer);
    qTimer = setTimeout(function () { S.q = qEl.value.trim().toLowerCase(); limit = 200; apply(); }, 140);
  });

  document.getElementById("more").addEventListener("click", function () {
    limit += 200; renderTable();
  });

  document.getElementById("reset").addEventListener("click", function () {
    S = { q: "", y1: Y_MIN, y2: Y_MAX, gender: "all", cls: "all", type: "all", suit: "all",
      status: "fin", teams: "team" };
    qEl.value = "";
    clsEl.value = "all";
    document.getElementById("y1").value = Y_MIN;
    document.getElementById("y2").value = Y_MAX;
    [["f-gender", "all"], ["f-type", "all"], ["f-suit", "all"], ["f-status", "fin"],
     ["f-team", "team"]].forEach(function (p) {
      Array.prototype.forEach.call(document.querySelectorAll("#" + p[0] + " button"), function (b) {
        b.setAttribute("aria-pressed", String(b.dataset.v === p[1]));
      });
    });
    sortKey = "finish"; sortDir = 1; limit = 200;
    renderHead(); apply();
  });

  document.getElementById("copy").addEventListener("click", function () {
    var head = ["Pos", "Jahr", "Rang", "Status", "Nachname", "Vorname", "Kategorie", "Neopren",
      "Staffel", "Team", "Mitglieder", "Endzeit", "Sekunden", "km/h", "Meilen", "Nation", "Ort",
      "Club"];
    var lines = [head.join(";")].concat(view.map(function (d, i) {
      return [i + 1, d.year, d.rank == null ? "" : d.rank, d.status, d.last, d.first, catLabel(d),
        d.suit, d.relay, d.team, d.isTeam ? d.members.join("; ") : "",
        fmtTime(d.finish), d.finish == null ? "" : d.finish,
        d.speed == null ? "" : d.speed, fmtHM(d.split), d.nat, d.city, d.club]
        .map(function (v) {
          v = v == null ? "" : String(v);
          return /[;"\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
        }).join(";");
    }));
    var note = document.getElementById("copied");
    function flash(msg) {
      note.textContent = msg;
      note.hidden = false;
      setTimeout(function () { note.hidden = true; }, 2800);
    }
    var text = lines.join("\n");
    var done = navigator.clipboard && navigator.clipboard.writeText
      ? navigator.clipboard.writeText(text)
      : Promise.reject();
    done.then(function () {
      flash(fmtInt(view.length) + " Zeilen in die Zwischenablage kopiert.");
    }, function () {
      // Clipboard access can be blocked — fall back to a selectable textarea.
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.cssText = "position:fixed;left:-9999px;top:0";
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
      document.body.removeChild(ta);
      flash(ok ? fmtInt(view.length) + " Zeilen kopiert."
               : "Die Zwischenablage ist in diesem Kontext gesperrt.");
    });
  });

  fillYears();
  segment("f-gender", "gender");
  segment("f-type", "type");
  segment("f-suit", "suit");
  segment("f-status", "status");
  segment("f-team", "teams");
  renderHead();
  apply();
})();
