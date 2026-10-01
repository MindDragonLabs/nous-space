/* Unified search v2 — one search across PRs, issues, the ecosystem catalog,
 * the quality corpus, and repos/people. Loaded on demand by app.js.
 *
 * URL hash = shareable state:
 *   #search?q=…&lane=prs&state=merged&label=…&cat=mcp&from=YYYY-MM-DD&to=YYYY-MM-DD&cohort=YYYY-MM&cov=…
 * cov records the coverage the sharer saw (lane:browsable/total) so a reader
 * can tell when a lane has grown since the link was made.
 */
(function () {
  "use strict";

  var App = window.NousApp;
  var Search = window.NousSearch;
  if (!App || !Search) return;

  var LANES = ["prs", "issues", "ecosystem", "corpus", "other"];
  var LANE_NAME = { prs: "pull requests", issues: "issues", ecosystem: "ecosystem", corpus: "corpus", other: "repos & people" };
  var CAP_STEP = 50;
  var STATES = ["", "open", "merged", "closed"];
  var CATS = ["plugins", "skills", "mods", "mcp", "tools"];
  var DATED = { prs: true, issues: true };

  var st = { q: "", lane: "all", state: "", label: "", cat: "", from: "", to: "", cohort: "", cov: "" };
  var caps = {};
  var docs = { prs: [], issues: [], ecosystem: [], corpus: [], other: [] };
  var coverage = {};
  var insights = null;
  var root = null;
  var refs = {};
  var pending = 0;

  var esc = App.escapeHtml;

  function fmt(n) { return Number(n || 0).toLocaleString(); }

  function day(value) {
    var s = String(value || "");
    return /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : "";
  }

  // ── lanes ────────────────────────────────────────────────────────────────

  function buildPrs(archive) {
    var D = App.data();
    var byNum = new Map();
    function put(doc, rich) {
      var prev = byNum.get(doc.number);
      if (prev && !rich) return;
      byNum.set(doc.number, prev ? Object.assign({}, prev, doc) : doc);
    }
    (archive || []).forEach(function (r) {
      put({
        kind: "pr", lane: "prs", number: r.n, title: r.t || "", author: r.a || "", labels: [],
        state: r.s || "", date: r.m || "", merged_at: r.s === "merged" ? r.m || "" : "",
        ts: App.toTs(r.m), url: "https://github.com/" + (D.repo || "NousResearch/hermes-agent") + "/pull/" + r.n,
        repo: D.repo || ""
      }, false);
    });
    (Array.isArray(D.merged) ? D.merged : []).forEach(function (m) {
      put(Object.assign({}, m, { kind: "pr", lane: "prs", state: "merged", labels: [], date: day(m.merged_at),
        ts: App.toTs(m.merged_at), repo: D.repo || "" }), true);
    });
    (Array.isArray(D.lane_open) ? D.lane_open : []).forEach(function (p) {
      put(Object.assign({}, p, { kind: "pr", lane: "prs", state: "open", labels: [], date: day(p.created_at),
        ts: App.toTs(p.updated_at || p.created_at), repo: D.repo || "" }), true);
    });
    App.asList(D.pull_requests).forEach(function (p) {
      var doc = App.prDoc(p);
      doc.lane = "prs";
      doc.date = day(p.created_at || p.updated_at);
      put(doc, true);
    });
    docs.prs = Array.from(byNum.values());
    var total = (Number(D.pull_requests && D.pull_requests.total_open) || 0) +
      (Number(D.pull_requests && D.pull_requests.total_closed) || 0);
    coverage.prs = {
      have: docs.prs.length, total: total, partial: true,
      note: "1,000-PR archive + live lists; full history needs an API key"
    };
  }

  function buildIssues(lane) {
    var D = App.data();
    var byNum = new Map();
    var repo = D.repo || "NousResearch/hermes-agent";
    ((lane && lane.items) || []).forEach(function (r) {
      byNum.set(r[0], {
        kind: "issue", lane: "issues", number: r[0], title: r[1] || "", author: r[2] || "",
        state: r[3] === "o" ? "open" : "closed", labels: Array.isArray(r[4]) ? r[4] : [],
        url: "https://github.com/" + repo + "/issues/" + r[0], ts: 0, date: "", repo: repo
      });
    });
    App.asList(D.issues).forEach(function (issue) {
      var doc = App.issueDoc(issue);
      doc.lane = "issues";
      doc.date = day(issue.created_at || issue.updated_at);
      byNum.set(doc.number, Object.assign({}, byNum.get(doc.number) || {}, doc));
    });
    docs.issues = Array.from(byNum.values());
    var total = lane && lane.total ? lane.total :
      (Number(D.issues && D.issues.total_open) || 0) + (Number(D.issues && D.issues.total_closed) || 0);
    coverage.issues = {
      have: docs.issues.length, total: total, partial: true,
      note: "backfill in progress — " + fmt(lane ? lane.indexed : 0) + " indexed so far, plus the 100 most recently updated open issues"
    };
  }

  function buildEcosystem(shards) {
    var out = [];
    shards.forEach(function (shard) {
      (shard.items || []).forEach(function (it) {
        var owner = String(it.n || "").split("/")[0];
        out.push({
          kind: "ecosystem", lane: "ecosystem", category: shard.category, title: it.n || "", text: it.d || "",
          author: it.m || owner, labels: [shard.category, it.sub, it.l].filter(Boolean),
          url: it.u || "", stars: it.s, free: it.f, flags: it.fl || [], ts: 0, repo: it.n || ""
        });
      });
    });
    docs.ecosystem = out;
    coverage.ecosystem = { have: out.length, total: out.length, partial: false, note: "complete — free items only, by policy" };
  }

  function buildCorpus(corpus) {
    var names = (corpus && corpus.docs) || [];
    docs.corpus = names.map(function (name) {
      return { kind: "corpus", lane: "corpus", title: name, text: "quality program document", labels: ["corpus"], ts: 0, url: "" };
    });
    if (corpus) {
      docs.corpus.unshift({
        kind: "corpus", lane: "corpus", title: "Quality corpus — " + fmt(corpus.live_total) + " live entries",
        text: fmt(corpus.curated_total) + " curated · last batch +" + fmt(corpus.last_batch), labels: ["corpus"], ts: 0, url: ""
      });
    }
    coverage.corpus = {
      have: docs.corpus.length, total: corpus ? corpus.live_total : 0, partial: true, titlesOnly: true,
      note: "titles and counts only — corpus content needs an API key"
    };
  }

  function buildOther() {
    var D = App.data();
    var out = [];
    (Array.isArray(D.ecosystem) ? D.ecosystem : []).forEach(function (item) {
      if (item.kind === "pr" || item.kind === "issue") return;
      out.push(Object.assign({}, item, { lane: "other", ts: App.toTs(item.updated_at), labels: [item.kind].filter(Boolean) }));
    });
    App.asList(D.contributors).forEach(function (person) {
      var doc = App.contribDoc(person);
      doc.lane = "other";
      out.push(doc);
    });
    docs.other = out;
    coverage.other = { have: out.length, total: out.length, partial: false, note: "Hermes repos, releases and top contributors" };
  }

  function loadLanes() {
    var jobs = [
      ["prs", App.loadJSON("data/archive.json").then(function (a) { App.whenCatalog(function () { buildPrs(a.prs); repaint(); }); })],
      ["issues", App.loadJSON("data/search-issues.json").then(function (lane) { App.whenCatalog(function () { buildIssues(lane); repaint(); }); })],
      ["ecosystem", Promise.all(CATS.map(function (c) {
        return App.loadJSON("data/eco-" + c + ".json").catch(function () { return { category: c, items: [], failed: true }; });
      })).then(function (shards) {
        buildEcosystem(shards);
        var missing = shards.filter(function (sh) { return sh.failed; }).map(function (sh) { return sh.category; });
        if (missing.length) {
          coverage.ecosystem.partial = true;
          coverage.ecosystem.note += " (" + missing.join(", ") + " failed to load)";
        }
        repaint();
      })],
      ["corpus", App.loadJSON("data/corpus.json").then(function (c) { buildCorpus(c); repaint(); })],
      ["insights", App.loadJSON("data/insights.json").then(function (ins) { insights = ins; repaint(); })]
    ];
    App.whenCatalog(function () { buildOther(); repaint(); });
    pending = jobs.length;
    jobs.forEach(function (job) {
      job[1].catch(function () {
        if (job[0] !== "insights") coverage[job[0]] = { have: 0, total: 0, partial: true, failed: true, note: "could not load" };
        if (job[0] === "prs" || job[0] === "issues") App.whenCatalog(function () {
          if (job[0] === "prs") buildPrs([]);
          else buildIssues(null);
          coverage[job[0]].note += " (archive shard failed to load)";
          repaint();
        });
      }).then(function () { pending -= 1; repaint(); });
    });
  }

  // ── state <-> hash ───────────────────────────────────────────────────────

  function readHash() {
    var p = App.hashParams();
    st.q = p.get("q") || "";
    st.lane = LANES.indexOf(p.get("lane")) !== -1 ? p.get("lane") : "all";
    st.state = STATES.indexOf(p.get("state") || "") !== -1 ? p.get("state") || "" : "";
    st.label = p.get("label") || "";
    st.cat = CATS.indexOf(p.get("cat")) !== -1 ? p.get("cat") : "";
    st.from = day(p.get("from"));
    st.to = day(p.get("to"));
    st.cohort = /^\d{4}-\d{2}$/.test(p.get("cohort") || "") ? p.get("cohort") : "";
    st.cov = p.get("cov") || "";
    caps = {};
  }

  function covString() {
    return LANES.filter(function (lane) { return coverage[lane]; }).map(function (lane) {
      return lane + ":" + coverage[lane].have + "/" + coverage[lane].total;
    }).join(",");
  }

  function writeHash() {
    var p = new URLSearchParams();
    ["q", "lane", "state", "label", "cat", "from", "to", "cohort"].forEach(function (key) {
      var value = st[key];
      if (value && !(key === "lane" && value === "all")) p.set(key, value);
    });
    if (!pending) p.set("cov", covString());
    var qs = p.toString();
    var next = location.pathname + location.search + "#search" + (qs ? "?" + qs : "");
    if (location.pathname + location.search + location.hash !== next) history.replaceState(null, "", next);
  }

  // ── filtering + ranking ──────────────────────────────────────────────────

  function cohortAuthors() {
    if (!st.cohort || !insights) return null;
    var row = (insights.cohorts || []).filter(function (c) { return c.month === st.cohort; })[0];
    var set = new Set();
    (row ? row.authors : []).forEach(function (a) { set.add(String(a).toLowerCase()); });
    return set;
  }

  function laneApplies(lane) {
    if (st.lane !== "all" && st.lane !== lane) return false;
    if (st.state && !DATED[lane]) return false;
    if ((st.from || st.to) && !DATED[lane]) return false;
    if (st.cat && lane !== "ecosystem") return false;
    if (st.cohort && lane !== "prs") return false;
    return true;
  }

  function passes(doc, lane, cohort) {
    if (st.state && String(doc.state || "").toLowerCase() !== st.state) return false;
    if (st.label) {
      var want = st.label.toLowerCase();
      var labels = Array.isArray(doc.labels) ? doc.labels : [];
      if (!labels.some(function (l) { return String(l).toLowerCase().indexOf(want) !== -1; })) return false;
    }
    if (st.cat && doc.category !== st.cat) return false;
    if (st.from || st.to) {
      var d = doc.date || "";
      if (!d) return false;
      if (st.from && d < st.from) return false;
      if (st.to && d > st.to) return false;
    }
    if (cohort && (doc.state !== "merged" || !cohort.has(String(doc.author || "").toLowerCase()))) return false;
    return true;
  }

  function ranked(lane) {
    var cohort = cohortAuthors();
    var pool = (docs[lane] || []).filter(function (doc) { return passes(doc, lane, cohort); });
    if (App.queryIsBlank(st.q)) {
      return pool.slice().sort(function (a, b) {
        if (lane === "ecosystem") return (Number(b.stars) || 0) - (Number(a.stars) || 0);
        return (Number(b.ts) || 0) - (Number(a.ts) || 0) || (Number(b.number) || 0) - (Number(a.number) || 0);
      });
    }
    return Search.searchDocs(pool, st.q, pool.length).hits.map(function (hit) { return hit.doc; });
  }

  // Round-robin across lanes so no single lane can swamp the list.
  function interleave(perLane, lanes) {
    var out = [];
    var longest = 0;
    lanes.forEach(function (lane) { longest = Math.max(longest, perLane[lane].shown.length); });
    for (var i = 0; i < longest; i++) {
      lanes.forEach(function (lane) {
        var row = perLane[lane].shown[i];
        if (row) out.push(row);
      });
    }
    return out;
  }

  // ── render ───────────────────────────────────────────────────────────────

  function chipGroup(label, key, values, names) {
    return '<div role="group" aria-label="' + esc(label) + '"><span class="filter-label">' + esc(label) + "</span>" +
      values.map(function (value, i) {
        var on = st[key] === value;
        return '<button type="button" class="chip' + (on ? " is-on" : "") + '" aria-pressed="' + on + '" data-f="' + key +
          '" data-v="' + esc(value) + '">' + esc(names[i]) + "</button>";
      }).join("") + "</div>";
  }

  function topLabelValues() {
    var counts = new Map();
    docs.prs.concat(docs.issues).forEach(function (doc) {
      (doc.labels || []).forEach(function (l) { if (l) counts.set(l, (counts.get(l) || 0) + 1); });
    });
    return Array.from(counts.entries()).sort(function (a, b) { return b[1] - a[1]; }).slice(0, 8).map(function (e) { return e[0]; });
  }

  function renderFilters() {
    var labels = topLabelValues();
    if (st.label && labels.indexOf(st.label) === -1) labels.unshift(st.label);
    refs.filters.innerHTML =
      chipGroup("Lane", "lane", ["all"].concat(LANES), ["all"].concat(LANES.map(function (l) { return LANE_NAME[l]; }))) +
      chipGroup("State", "state", STATES, ["any", "open", "merged", "closed"]) +
      chipGroup("Label", "label", [""].concat(labels), ["any"].concat(labels)) +
      chipGroup("Category", "cat", [""].concat(CATS), ["any"].concat(CATS)) +
      '<div class="search-dates" role="group" aria-label="Date range"><span class="filter-label">Date</span>' +
      '<label>from <input type="date" data-f="from" value="' + esc(st.from) + '"></label>' +
      '<label>to <input type="date" data-f="to" value="' + esc(st.to) + '"></label>' +
      (st.cohort ? '<button type="button" class="chip is-on" aria-pressed="true" data-f="cohort" data-v="">cohort ' + esc(st.cohort) + " ×</button>" : "") +
      '<button type="button" class="chip" data-clear="1">clear filters</button></div>';
  }

  function coverageHtml(active) {
    var parts = active.map(function (lane) {
      var c = coverage[lane];
      if (!c) return '<span>' + esc(LANE_NAME[lane]) + ": loading…</span>";
      var cls = c.partial ? "cov-partial" : "cov-ok";
      var count = lane === "corpus"
        ? fmt(c.total) + " entries"
        : c.partial && c.total ? fmt(c.have) + " of " + fmt(c.total) : fmt(c.have);
      return '<span class="' + cls + '">' + esc(LANE_NAME[lane]) + ": " + count + (c.partial ? " — partial" : "") +
        ' <span class="sr-only">(</span><small>' + esc(c.note) + "</small><span class=\"sr-only\">)</span></span>";
    });
    var extra = "";
    if (st.cov && !pending && st.cov !== covString()) {
      extra = '<span class="cov-partial">Coverage has changed since this link was shared (then: ' + esc(st.cov.replace(/,/g, ", ")) + ").</span>";
    }
    if ((st.from || st.to) && insights) {
      var wk = (insights.weeks || []).filter(function (w) { return w.week === st.from; })[0];
      if (wk && wk.days_covered) {
        extra += '<span class="cov-partial">Week of ' + esc(wk.week) + ": " + fmt(wk.merged) + " merges counted on GitHub; " +
          fmt(wk.browsable) + " browsable here. Full records need an API key.</span>";
      }
    }
    if (st.cohort && insights) {
      var co = (insights.cohorts || []).filter(function (c) { return c.month === st.cohort; })[0];
      if (co) extra += "<span>Cohort " + esc(co.month) + ": " + fmt(co.firsts) + " first-time authors, " + fmt(co.returned) +
        " merged again. " + esc(insights.cohort_definition || "") + "</span>";
    }
    return parts.join("") + extra;
  }

  function hitHtml(doc) {
    var lane = doc.lane;
    var tag = '<span class="lane-tag lane-' + lane + '">' + esc(lane === "prs" ? "PR" : lane === "issues" ? "issue" : lane === "other" ? doc.kind || "repo" : lane) + "</span>";
    var title = '<span>' + App.highlight(doc.title || "", st.q) + "</span>";
    var bits = [];
    if (doc.number != null && doc.number !== "") bits.push("#" + doc.number);
    if (doc.state) bits.push(doc.state);
    if (doc.date) bits.push(doc.date);
    if (doc.author) bits.push(doc.author);
    if (lane === "ecosystem") {
      if (doc.category) bits.push(doc.category);
      if (doc.stars != null) bits.push("★ " + fmt(doc.stars));
      if (doc.free) bits.push("free ✓");
    }
    var meta = '<span class="hn-meta">' + esc(bits.join(" · ")) + "</span>";
    var text = doc.text && lane !== "prs" && lane !== "issues" ? '<span class="hn-meta">' + App.highlight(String(doc.text).slice(0, 200), st.q) + "</span>" : "";
    if (lane === "corpus" || !doc.url) {
      return '<article class="hit"><div class="hit-static">' + tag + title + meta + text + "</div></article>";
    }
    var drawer = doc.kind === "pr" || doc.kind === "issue"
      ? ' data-drawer="' + App.registerDoc(doc) + '" aria-haspopup="dialog"' : "";
    return '<article class="hit"><a href="' + esc(doc.url) + '" target="_blank" rel="noopener"' + drawer + ">" +
      tag + title + meta + text + "</a></article>";
  }

  function repaint() {
    if (!root) return;
    if (refs.input.value !== st.q) refs.input.value = st.q;
    renderFilters();
    var active = LANES.filter(laneApplies);
    refs.coverage.innerHTML = coverageHtml(active);
    var perLane = {};
    var total = 0;
    active.forEach(function (lane) {
      var all = ranked(lane);
      var cap = caps[lane] || CAP_STEP;
      perLane[lane] = { all: all, shown: all.slice(0, cap) };
      total += all.length;
    });
    var rows = interleave(perLane, active);
    refs.meta.textContent = (pending ? "Loading lanes… " : "") + fmt(total) + (total === 1 ? " match" : " matches") +
      (active.length > 1 ? " · lanes interleaved, first " + CAP_STEP + " per lane" : "") +
      (active.length ? "" : " · no lane fits these filters");
    refs.list.innerHTML = rows.map(hitHtml).join("") ||
      (pending ? "" : '<p class="tab-note">No matches. Partial lanes are listed above.</p>');
    refs.more.innerHTML = active.filter(function (lane) {
      return perLane[lane].all.length > perLane[lane].shown.length;
    }).map(function (lane) {
      var left = perLane[lane].all.length - perLane[lane].shown.length;
      return '<button type="button" class="chip" data-more="' + lane + '">Show ' + Math.min(CAP_STEP, left) + " more " +
        esc(LANE_NAME[lane]) + " (" + fmt(left) + " left)</button>";
    }).join("");
    writeHash();
  }

  function render(panel) {
    root = document.createElement("div");
    root.className = "tab-page";
    root.innerHTML =
      '<h2 id="search-h">Search</h2>' +
      '<p class="tab-note">One search across pull requests, issues, the free ecosystem catalog and the quality corpus. Field prefixes: <code>author:</code> <code>label:</code> <code>is:</code> <code>kind:</code> <code>#number</code>. The address bar keeps the query and filters, so links are shareable.</p>' +
      '<label class="sr-only" for="search-q">Search query</label>' +
      '<input id="search-q" type="search" autocomplete="off" placeholder="Search PRs, issues, ecosystem, corpus">' +
      '<div class="search-filters" id="search-filters"></div>' +
      '<div class="coverage" id="search-coverage" aria-live="polite"></div>' +
      '<div class="share-row"><p class="result-meta" id="search-meta" role="status"></p>' +
      '<button type="button" class="chip" id="search-share">Copy link</button><span id="search-shared" role="status"></span></div>' +
      '<div class="hit-list" id="search-hits"></div>' +
      '<div class="lane-more" id="search-more"></div>';
    panel.appendChild(root);
    refs = {
      input: root.querySelector("#search-q"),
      filters: root.querySelector("#search-filters"),
      coverage: root.querySelector("#search-coverage"),
      meta: root.querySelector("#search-meta"),
      list: root.querySelector("#search-hits"),
      more: root.querySelector("#search-more")
    };
    var timer = null;
    refs.input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        st.q = refs.input.value;
        caps = {};
        var top = document.getElementById("eco-q");
        if (top && top.value !== st.q) top.value = st.q;
        repaint();
      }, 120);
    });
    refs.filters.addEventListener("click", function (event) {
      var btn = event.target.closest("button");
      if (!btn) return;
      if (btn.hasAttribute("data-clear")) {
        st.lane = "all"; st.state = ""; st.label = ""; st.cat = ""; st.from = ""; st.to = ""; st.cohort = "";
      } else {
        var key = btn.getAttribute("data-f");
        if (!key) return;
        st[key] = btn.getAttribute("data-v") || "";
        if (key === "lane" && !st[key]) st.lane = "all";
      }
      caps = {};
      repaint();
      var again = refs.filters.querySelector('button[data-f="' + btn.getAttribute("data-f") + '"][data-v="' + (btn.getAttribute("data-v") || "") + '"]');
      if (again) again.focus();
    });
    refs.filters.addEventListener("change", function (event) {
      var input = event.target.closest("input[data-f]");
      if (!input) return;
      st[input.getAttribute("data-f")] = day(input.value);
      caps = {};
      repaint();
    });
    refs.more.addEventListener("click", function (event) {
      var btn = event.target.closest("button[data-more]");
      if (!btn) return;
      var lane = btn.getAttribute("data-more");
      caps[lane] = (caps[lane] || CAP_STEP) + CAP_STEP;
      repaint();
      var next = refs.more.querySelector('button[data-more="' + lane + '"]');
      if (next) next.focus();
    });
    root.querySelector("#search-share").addEventListener("click", function () {
      var note = root.querySelector("#search-shared");
      var url = location.href;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(function () { note.textContent = "Link copied."; }, function () { note.textContent = url; });
      } else {
        note.textContent = url;
      }
    });
    readHash();
    loadLanes();
    repaint();
  }

  function show() {
    if (!root) return;
    var before = JSON.stringify(st);
    readHash();
    if (JSON.stringify(st) !== before) repaint();
    var top = document.getElementById("eco-q");
    if (top && st.q && top.value !== st.q) top.value = st.q;
  }

  window.NousUnified = {
    setQuery: function (value) {
      st.q = String(value || "");
      caps = {};
      repaint();
    }
  };
  App.registerView("search", { render: render, show: show });
})();
