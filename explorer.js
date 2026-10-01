/* Ecosystem explorer — faceted, client-side filtering over the free catalog
 * (plugins, skills, mods, MCP servers, tools). Loaded on demand by app.js.
 * Data: data/eco-<category>.json, emitted by build.py with build-time health
 * flags and link-check results (scripts/link_check.py).
 *
 * URL hash keeps the view shareable: #ecosystem?cat=mcp&q=voice&lic=mit&sort=stars&free=1
 */
(function () {
  "use strict";

  var App = window.NousApp;
  if (!App) return;

  var CATS = ["plugins", "skills", "mods", "mcp", "tools"];
  var PAGE = 48;
  var FLAG_TEXT = {
    "archived": ["archived", "The source marks this repository as archived."],
    "no-description": ["no description", "The catalog entry has no description."],
    "no-stars": ["no stars yet", "Zero GitHub stars when the catalog was built — a low-activity signal, not a judgement."],
    "dead-link": ["link unavailable", "The link checker got 404/410 (a link that worked before must fail twice). Timeouts, rate limits and server errors are never flagged."]
  };
  var esc = App.escapeHtml;

  var items = [];
  var loaded = 0;
  var st = { q: "", cat: "", lic: "", sort: "stars", free: false, hideFlagged: false };
  var shown = PAGE;
  var root = null;
  var refs = {};

  function fmt(n) { return Number(n || 0).toLocaleString(); }

  function readHash() {
    var p = App.hashParams();
    st.q = p.get("q") || "";
    st.cat = CATS.indexOf(p.get("cat")) !== -1 ? p.get("cat") : "";
    st.lic = p.get("lic") || "";
    st.sort = ["stars", "stars-asc", "name"].indexOf(p.get("sort")) !== -1 ? p.get("sort") : "stars";
    st.free = p.get("free") === "1";
    st.hideFlagged = p.get("clean") === "1";
  }

  function writeHash() {
    var p = new URLSearchParams();
    if (st.q) p.set("q", st.q);
    if (st.cat) p.set("cat", st.cat);
    if (st.lic) p.set("lic", st.lic);
    if (st.sort !== "stars") p.set("sort", st.sort);
    if (st.free) p.set("free", "1");
    if (st.hideFlagged) p.set("clean", "1");
    var qs = p.toString();
    var next = location.pathname + location.search + "#ecosystem" + (qs ? "?" + qs : "");
    if (location.pathname + location.search + location.hash !== next) history.replaceState(null, "", next);
  }

  function license(it) { return it.l || "unknown"; }

  function matches(it, skip) {
    if (skip !== "cat" && st.cat && it.cat !== st.cat) return false;
    if (skip !== "lic" && st.lic && license(it) !== st.lic) return false;
    if (st.free && !it.f) return false;
    if (st.hideFlagged && it.fl && it.fl.length) return false;
    if (st.q) {
      var hay = it.hay || (it.hay = [it.n, it.d, it.m, it.cat, it.sub, it.t, it.l].join(" ").toLowerCase());
      var words = st.q.toLowerCase().split(/\s+/).filter(Boolean);
      for (var i = 0; i < words.length; i++) if (hay.indexOf(words[i]) === -1) return false;
    }
    return true;
  }

  function sorted(rows) {
    var copy = rows.slice();
    copy.sort(function (a, b) {
      if (st.sort === "name") return a.n.toLowerCase() < b.n.toLowerCase() ? -1 : 1;
      var sa = a.s == null ? -1 : a.s;
      var sb = b.s == null ? -1 : b.s;
      return st.sort === "stars-asc" ? sa - sb : sb - sa;
    });
    return copy;
  }

  function counts(key, skip) {
    var map = new Map();
    items.forEach(function (it) {
      if (!matches(it, skip)) return;
      var k = key(it);
      map.set(k, (map.get(k) || 0) + 1);
    });
    return map;
  }

  function cardHtml(it) {
    var badges = [];
    if (it.f) badges.push('<span class="badge badge-free" title="Free and open — verified at ingest">free ✓</span>');
    if (it.src === "catalog" || it.src === "optional-skills") {
      badges.push('<span class="badge badge-official" title="Listed in the hermes-agent ' + esc(it.src === "catalog" ? "plugin-catalog" : "optional-skills") + ' directory">official list</span>');
    }
    (it.fl || []).forEach(function (flag) {
      var f = FLAG_TEXT[flag];
      if (f) badges.push('<span class="badge badge-flag" title="' + esc(f[1]) + '">' + esc(f[0]) + "</span>");
    });
    var meta = ['<span class="eco-chip">' + esc(it.cat) + "</span>"];
    if (it.sub) meta.push('<span class="eco-chip">' + esc(it.sub) + "</span>");
    if (it.t) meta.push('<span class="eco-chip">' + esc(it.t) + "</span>");
    meta.push('<span class="eco-chip">license: ' + esc(license(it)) + "</span>");
    if (it.s != null) meta.push('<span class="eco-stars" aria-label="' + fmt(it.s) + ' stars">★ ' + fmt(it.s) + "</span>");
    if (it.m) meta.push('<span class="eco-by">by ' + esc(it.m) + "</span>");
    var title = it.u
      ? '<a class="eco-title" href="' + esc(it.u) + '" target="_blank" rel="noopener">' + esc(it.n) + "</a>"
      : '<span class="eco-title">' + esc(it.n) + "</span>";
    return '<article class="eco-card">' + title +
      '<p class="eco-desc">' + esc(it.d || "No description.") + "</p>" +
      '<p class="eco-meta">' + meta.join("") + "</p>" +
      (badges.length ? '<p class="eco-meta">' + badges.join("") + "</p>" : "") + "</article>";
  }

  function chip(key, value, label, on) {
    return '<button type="button" class="chip' + (on ? " is-on" : "") + '" aria-pressed="' + on + '" data-k="' + key +
      '" data-v="' + esc(value) + '">' + label + "</button>";
  }

  function paint() {
    if (!root) return;
    if (refs.q.value !== st.q) refs.q.value = st.q;
    var catCounts = counts(function (it) { return it.cat; }, "cat");
    var allCat = 0;
    catCounts.forEach(function (n) { allCat += n; });
    refs.cats.innerHTML = '<span class="filter-label">Category</span>' + chip("cat", "", "all <span class=\"bar-count\">" + fmt(allCat) + "</span>", !st.cat) +
      CATS.map(function (c) {
        return chip("cat", c, esc(c) + ' <span class="bar-count">' + fmt(catCounts.get(c) || 0) + "</span>", st.cat === c);
      }).join("");
    var licCounts = counts(license, "lic");
    var lics = Array.from(licCounts.entries()).sort(function (a, b) { return b[1] - a[1]; });
    if (st.lic && !licCounts.has(st.lic)) lics.unshift([st.lic, 0]);
    refs.lic.innerHTML = '<option value="">any license</option>' + lics.map(function (pair) {
      return '<option value="' + esc(pair[0]) + '"' + (st.lic === pair[0] ? " selected" : "") + ">" + esc(pair[0]) + " (" + fmt(pair[1]) + ")</option>";
    }).join("");
    refs.sort.value = st.sort;
    refs.free.checked = st.free;
    refs.clean.checked = st.hideFlagged;

    var rows = sorted(items.filter(function (it) { return matches(it); }));
    refs.meta.textContent = (loaded < CATS.length ? "Loading " + loaded + " of " + CATS.length + " categories… " : "") +
      fmt(rows.length) + " of " + fmt(items.length) + " items";
    refs.list.innerHTML = rows.slice(0, shown).map(cardHtml).join("") ||
      (loaded < CATS.length ? "" : '<p class="eco-note">No matches.</p>');
    var left = rows.length - Math.min(shown, rows.length);
    refs.more.hidden = left <= 0;
    refs.more.textContent = "Show " + Math.min(PAGE, left) + " more (" + fmt(left) + " left)";
    writeHash();
  }

  function load() {
    CATS.forEach(function (cat) {
      App.loadJSON("data/eco-" + cat + ".json").then(function (shard) {
        (shard.items || []).forEach(function (it) {
          it.cat = cat;
          items.push(it);
        });
      }).catch(function () {
        refs.note.textContent = "Some categories could not load; showing what arrived.";
      }).then(function () {
        loaded += 1;
        paint();
      });
    });
  }

  function render(panel) {
    readHash();
    root = document.createElement("div");
    root.className = "tab-page";
    root.innerHTML =
      '<h2 id="eco-explorer-h">Ecosystem explorer</h2>' +
      '<p class="tab-note">Free Hermes plugins, skills, mods, MCP servers and tools. Everything filters in your browser. Health flags are neutral signals computed at build time.</p>' +
      '<label class="sr-only" for="eco-x-q">Filter the ecosystem</label>' +
      '<input id="eco-x-q" class="search-input" type="search" autocomplete="off" placeholder="Filter by name, description, maintainer, license…">' +
      '<div class="facets">' +
      '<div class="chips" role="group" aria-label="Category" id="eco-x-cats"></div>' +
      '<label>License <select id="eco-x-lic"></select></label>' +
      '<label>Sort <select id="eco-x-sort"><option value="stars">most stars</option><option value="stars-asc">fewest stars</option><option value="name">name</option></select></label>' +
      '<label><input type="checkbox" id="eco-x-free"> free-verified only</label>' +
      '<label><input type="checkbox" id="eco-x-clean"> hide flagged</label>' +
      "</div>" +
      '<p class="result-meta" id="eco-x-meta" role="status"></p>' +
      '<div class="eco-list" id="eco-x-list"></div>' +
      '<button type="button" class="chip more-btn" id="eco-x-more" hidden></button>' +
      '<p class="eco-note" id="eco-x-note">Badges: <strong>free ✓</strong> = free and open, verified at ingest · <strong>official list</strong> = in the hermes-agent plugin-catalog or optional-skills directory · dashed badges are health flags (no description, no stars yet, archived when the source says so, link unavailable after a 404/410). Paid items are excluded by policy. Machine mirror: <a href="/ecosystem.json">/ecosystem.json</a> · API: <a href="#docs">/api/v1/ecosystem/*</a>.</p>';
    panel.appendChild(root);
    refs = {
      q: root.querySelector("#eco-x-q"), cats: root.querySelector("#eco-x-cats"), lic: root.querySelector("#eco-x-lic"),
      sort: root.querySelector("#eco-x-sort"), free: root.querySelector("#eco-x-free"), clean: root.querySelector("#eco-x-clean"),
      meta: root.querySelector("#eco-x-meta"), list: root.querySelector("#eco-x-list"), more: root.querySelector("#eco-x-more"),
      note: root.querySelector("#eco-x-note")
    };
    var timer = null;
    refs.q.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () { st.q = refs.q.value.trim(); shown = PAGE; paint(); }, 80);
    });
    refs.cats.addEventListener("click", function (event) {
      var btn = event.target.closest("button[data-k]");
      if (!btn) return;
      st.cat = btn.getAttribute("data-v") || "";
      shown = PAGE;
      paint();
      var again = refs.cats.querySelector('button[data-v="' + st.cat + '"]');
      if (again) again.focus();
    });
    refs.lic.addEventListener("change", function () { st.lic = refs.lic.value; shown = PAGE; paint(); });
    refs.sort.addEventListener("change", function () { st.sort = refs.sort.value; paint(); });
    refs.free.addEventListener("change", function () { st.free = refs.free.checked; shown = PAGE; paint(); });
    refs.clean.addEventListener("change", function () { st.hideFlagged = refs.clean.checked; shown = PAGE; paint(); });
    refs.more.addEventListener("click", function () { shown += PAGE; paint(); });
    load();
    paint();
  }

  function show() {
    if (!root) return;
    var before = JSON.stringify(st);
    readHash();
    if (JSON.stringify(st) !== before) { shown = PAGE; paint(); }
  }

  App.registerView("ecosystem", { render: render, show: show });
})();
