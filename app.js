(function () {
  "use strict";

  var VIEWS = ["dashboard", "issues", "prs", "contributors", "forum", "search", "ecosystem", "arch", "triage", "docs", "info"];
  var RELOAD_MS = 5 * 60 * 1000;
  var DATA = {};
  var built = Object.create(null);
  // Views whose code loads on demand (deferred, not on the first-paint path).
  var LAZY = { search: "unified.js", ecosystem: "explorer.js" };
  var viewHooks = Object.create(null);
  var catalogReady = false;
  var catalogWaiters = [];

  function loadData() {
    var node = document.getElementById("nous-data");
    if (!node) return {};
    try {
      var parsed = JSON.parse(node.textContent || "");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (err) {
      return {};
    }
  }

  function asList(bucket) {
    if (Array.isArray(bucket)) return bucket;
    if (!bucket || typeof bucket !== "object") return [];
    if (Array.isArray(bucket.items)) return bucket.items;
    if (Array.isArray(bucket.recent)) return bucket.recent;
    if (Array.isArray(bucket.contributors)) return bucket.contributors;
    return [];
  }

  function countOf(bucket, key) {
    if (!bucket || typeof bucket !== "object") return 0;
    var n = Number(bucket[key]);
    return Number.isFinite(n) ? n : 0;
  }

  function scannedCount(bucket, items) {
    if (bucket && typeof bucket === "object" && bucket.scanned != null && bucket.scanned !== "") {
      var n = Number(bucket.scanned);
      if (Number.isFinite(n)) return n;
    }
    return items.length;
  }

  function toTs(value) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (!value) return 0;
    var t = Date.parse(String(value));
    return Number.isNaN(t) ? 0 : t;
  }

  function formatCount(value) {
    var n = Number(value);
    if (!Number.isFinite(n)) n = 0;
    return n.toLocaleString();
  }

  function el(tag, className) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    return node;
  }

  function addText(parent, value) {
    if (value == null || value === "") return;
    var span = document.createElement("span");
    span.textContent = String(value);
    parent.appendChild(span);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function escapeReg(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function highlight(text, rawQuery) {
    var source = String(text == null ? "" : text);
    var api = window.NousSearch;
    if (!api) return escapeHtml(source);
    var unique = Array.from(new Set(api.parseQuery(rawQuery || "").tokens.filter(Boolean)));
    unique.sort(function (a, b) { return b.length - a.length; });
    if (!unique.length) return escapeHtml(source);
    var re = new RegExp(unique.map(escapeReg).join("|"), "gi");
    var html = "";
    var last = 0;
    var match;
    while ((match = re.exec(source))) {
      html += escapeHtml(source.slice(last, match.index));
      html += "<mark>" + escapeHtml(match[0]) + "</mark>";
      last = match.index + match[0].length;
      if (match[0].length === 0) re.lastIndex += 1;
    }
    html += escapeHtml(source.slice(last));
    return html;
  }

  function queryIsBlank(raw) {
    var api = window.NousSearch;
    if (!api) return !String(raw || "").trim();
    var parsed = api.parseQuery(raw || "");
    var fields = parsed.fields;
    return !parsed.tokens.length && !fields.author && !fields.label && !fields.repo &&
      !fields.is && !fields.kind && (fields.number == null || fields.number === "");
  }

  function viewFromHash() {
    var raw = String(location.hash || "").replace(/^#/, "").split(/[/?]/)[0].toLowerCase();
    return VIEWS.indexOf(raw) === -1 ? "dashboard" : raw;
  }

  function normalizeView(name) {
    var value = String(name || "").toLowerCase();
    return VIEWS.indexOf(value) === -1 ? "dashboard" : value;
  }

  function viewPanel(name) {
    return document.querySelector('[data-view-panel="' + name + '"]') || document.getElementById("view-" + name);
  }

  function writeHash(view) {
    var base = location.pathname + location.search;
    var next = view === "dashboard" ? base : base + "#" + view;
    if (location.pathname + location.search + location.hash !== next) {
      history.replaceState(null, "", next);
    }
  }

  function showView(name, fromHash) {
    var view = normalizeView(name);
    if (!fromHash) writeHash(view);
    document.querySelectorAll("[data-view-panel]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-view-panel") !== view;
    });
    document.querySelectorAll("[data-view]").forEach(function (btn) {
      var on = normalizeView(btn.getAttribute("data-view")) === view;
      btn.classList.toggle("active", on);
      if (btn.classList.contains("nav-icon")) {
        if (on) btn.setAttribute("aria-current", "page");
        else btn.removeAttribute("aria-current");
      }
    });
    var titles = {
      dashboard: "NOUS SPACE — Hermes Agent Maintainer Dashboard",
      issues: "Issues — Nous Space",
      prs: "Pull requests — Nous Space",
      contributors: "Contributors — Nous Space",
      forum: "Forum — Nous Space",
      search: "Search the Hermes ecosystem — Nous Space",
      ecosystem: "Ecosystem explorer — Nous Space",
      arch: "System architecture — Nous Space",
      triage: "Awaiting first review — Nous Space",
      docs: "API docs — Nous Space",
      info: "About this dashboard — Nous Space"
    };
    var descriptions = {
      dashboard: "Live Hermes Agent dashboard: maintainer merge lane, open issues, pull request queues, contributors, and ecosystem search.",
      issues: "Search the most recently updated open issues in NousResearch/hermes-agent.",
      prs: "Review queues for the most recently updated open Hermes Agent pull requests, plus the 6-hour PR archive.",
      contributors: "Hermes Agent contributors ranked by commits, with this week and recent reviews.",
      forum: "Community forum: one general category for Hermes Agent pull requests and issues.",
      search: "One search across Hermes pull requests, issues, the free ecosystem catalog, and the quality corpus.",
      ecosystem: "Faceted explorer over the free Hermes ecosystem: plugins, skills, mods, MCP servers, and tools.",
      arch: "How Hermes Agent is put together at a high level, with a diagram per main version release.",
      triage: "Maintainer-lane pull requests open more than 30 days with no review decision yet.",
      docs: "Nous Space API v1: endpoints, the 6-hour public window, API keys, attribution, and a curl builder.",
      info: "How the Nous Space strips are scoped, where every dataset comes from, and how fresh it is."
    };
    document.title = titles[view] || titles.dashboard;
    var desc = document.getElementById("meta-desc");
    if (desc) desc.setAttribute("content", descriptions[view] || descriptions.dashboard);
    ensureRendered(view);
    if (viewHooks[view] && viewHooks[view].show) viewHooks[view].show(viewPanel(view));
  }

  function ensureRendered(view) {
    if (view === "dashboard" || built[view]) return;
    var panel = viewPanel(view);
    if (!panel) return;
    if (LAZY[view] && !viewHooks[view]) {
      built[view] = true;
      panel.setAttribute("aria-busy", "true");
      loadScript(LAZY[view]).then(function () {
        panel.removeAttribute("aria-busy");
        var hook = viewHooks[view];
        if (!hook) return;
        hook.render(panel);
        if (viewFromHash() === view && hook.show) hook.show(panel);
      }).catch(function () {
        panel.removeAttribute("aria-busy");
        var note = el("p", "tab-note");
        note.textContent = "This view could not load. Reload the page to try again.";
        panel.appendChild(note);
      });
      return;
    }
    if (!panel.querySelector(".tab-page")) {
      if (view === "issues") renderIssues(panel);
      else if (view === "prs") renderPrs(panel);
      else if (view === "contributors") renderContribs(panel);
      else if (view === "triage") renderTriage(panel);
      else if (view === "forum") renderForum(panel);
      else if (view === "arch") bindArchPicker(panel);
      else if (view === "docs") bindCurlBuilder();
      else if (view === "info") renderInfo(panel);
      else if (viewHooks[view]) viewHooks[view].render(panel);
    }
    built[view] = true;
  }

  function chip(label, on) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip" + (on ? " is-on" : "");
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.textContent = label;
    return btn;
  }

  function selected(view, groupName) {
    var panel = viewPanel(view);
    if (!panel) return null;
    var group = panel.querySelector('[data-chip-group="' + groupName + '"]');
    if (!group) return null;
    return group.querySelector("button.chip.is-on");
  }

  function issueLabels(issue) {
    if (Array.isArray(issue.all_labels)) return issue.all_labels;
    if (Array.isArray(issue.labels)) return issue.labels;
    return [];
  }

  function issueDoc(issue) {
    var labels = issueLabels(issue);
    var shown = Array.isArray(issue.labels) && issue.labels.length ? issue.labels : labels;
    return Object.assign({}, issue, {
      kind: "issue",
      title: issue.title || "",
      text: "",
      author: issue.author || "",
      labels: labels,
      displayLabels: shown,
      number: issue.number,
      state: "open",
      url: issue.url || "",
      ts: toTs(issue.updated_at),
      ago: issue.ago || "",
      comments: issue.comments,
      age_days: issue.age_days,
      unassigned: issue.unassigned,
      assignee: issue.assignee,
      repo: DATA.repo || issue.repo || "",
    });
  }

  function prDoc(pr) {
    return Object.assign({}, pr, {
      kind: "pr",
      title: pr.title || "",
      text: "",
      author: pr.author || "",
      labels: Array.isArray(pr.labels) ? pr.labels : [],
      number: pr.number,
      state: pr.state || "open",
      queue: pr.queue || "",
      ci: pr.ci || "",
      review: pr.review || "",
      url: pr.url || "",
      ts: toTs(pr.updated_at != null ? pr.updated_at : pr.ts),
      ago: pr.ago || "",
      repo: DATA.repo || pr.repo || "",
    });
  }

  function contribDoc(person) {
    return Object.assign({}, person, {
      kind: "contributor",
      title: person.login || "",
      author: person.login || "",
      text: person.contributions == null ? "" : String(person.contributions),
      url: person.html_url || "",
      repo: DATA.repo || "",
      ts: 0,
    });
  }

  function topLabels(items) {
    var counts = new Map();
    items.forEach(function (issue) {
      issueLabels(issue).forEach(function (name) {
        if (!name) return;
        var key = String(name);
        counts.set(key, (counts.get(key) || 0) + 1);
      });
    });
    return Array.from(counts.entries()).sort(function (a, b) {
      return b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);
    }).slice(0, 8).map(function (entry) { return entry[0]; });
  }

  function ageDays(doc) {
    var n = Number(doc.age_days);
    return Number.isFinite(n) ? n : 0;
  }

  function passIssue(doc, filter, value) {
    if (!filter || filter === "all") return true;
    if (filter === "unassigned") return doc.unassigned === true;
    if (filter === "label") return Array.isArray(doc.labels) && doc.labels.indexOf(value) !== -1;
    if (filter === "age" && value === "older") return ageDays(doc) >= 30;
    if (filter === "age") return ageDays(doc) < Number(value);
    return true;
  }

  function sortIssues(docs, mode) {
    var copy = docs.slice();
    copy.sort(function (a, b) {
      if (mode === "oldest") return (Number(a.ts) || 0) - (Number(b.ts) || 0);
      if (mode === "comments") {
        return (Number(b.comments) || 0) - (Number(a.comments) || 0) || (Number(b.ts) || 0) - (Number(a.ts) || 0);
      }
      return (Number(b.ts) || 0) - (Number(a.ts) || 0);
    });
    return copy;
  }

  function linkedHit(doc) {
    var article = el("article", "hit");
    var link = document.createElement("a");
    link.href = doc.url || "#";
    link.target = "_blank";
    link.rel = "noopener";
    if (doc.kind === "pr" || doc.kind === "issue") {
      link.setAttribute("data-drawer", registerDoc(doc));
      link.setAttribute("aria-haspopup", "dialog");
    }
    article.appendChild(link);
    return { article: article, link: link };
  }

  function commentText(value) {
    var n = Number(value) || 0;
    return n === 1 ? "1 comment" : n + " comments";
  }

  function chipEl(text, cls) {
    var s = document.createElement("span");
    s.className = "hit-chip" + (cls ? " " + cls : "");
    s.textContent = text;
    return s;
  }

  function hitLine1(hit, doc, query, badgeText, badgeCls) {
    var line1 = el("div", "hit-line1");
    var num = el("span", "h-num");
    num.textContent = "#" + doc.number;
    line1.appendChild(num);
    if (badgeText) line1.appendChild(chipEl(badgeText, badgeCls));
    var title = el("span", "h-title");
    title.innerHTML = highlight(doc.title || "", query);
    line1.appendChild(title);
    hit.link.appendChild(line1);
    return line1;
  }

  function hitLine2(hit) {
    var line2 = el("div", "hit-line2");
    hit.link.appendChild(line2);
    return line2;
  }

  function issueHit(doc, query) {
    var hit = linkedHit(doc);
    hit.article.classList.add("carded-hit");
    hitLine1(hit, doc, query, "issue", "c-blue");
    var line2 = hitLine2(hit);
    var labels = Array.isArray(doc.displayLabels) ? doc.displayLabels : [];
    labels.slice(0, 5).forEach(function (name) {
      line2.appendChild(chipEl(name, "c-purple"));
    });
    if (doc.assignee) line2.appendChild(chipEl("assigned: " + doc.assignee, ""));
    else if (doc.unassigned) line2.appendChild(chipEl("unassigned", "c-amber"));
    line2.appendChild(chipEl(commentText(doc.comments), "c-green"));
    var meta = el("span", "h-meta");
    meta.textContent = doc.author + " · " + (doc.ago || "");
    if (doc.age_days != null) meta.title = "open " + doc.age_days + " days";
    line2.appendChild(meta);
    return hit.article;
  }

  function statusWord(doc) {
    if (doc.queue === "needs-review") return "Needs review";
    if (doc.queue === "approved") return "Approved";
    if (doc.queue === "changes") return "Changes";
    if (doc.queue === "draft" || doc.draft === true) return "Draft";
    return doc.state || "open";
  }

  function statusCls(doc) {
    if (doc.queue === "approved") return "c-green";
    if (doc.queue === "changes") return "c-red";
    if (doc.queue === "draft" || doc.draft === true) return "c-purple";
    if (doc.queue === "needs-review") return "c-amber";
    return "c-blue";
  }

  function prHit(doc, query) {
    var hit = linkedHit(doc);
    hit.article.classList.add("carded-hit");
    hitLine1(hit, doc, query, statusWord(doc), statusCls(doc));
    var line2 = hitLine2(hit);
    var ciOk = doc.ci_ok == null ? 0 : doc.ci_ok;
    var ciTotal = doc.ci_total == null ? 0 : doc.ci_total;
    if (ciTotal) {
      var ciCls = doc.ci === "passing" ? "c-green" : doc.ci === "failing" ? "c-red" : "c-amber";
      line2.appendChild(chipEl("CI " + ciOk + "/" + ciTotal + (doc.ci ? " " + doc.ci : ""), ciCls));
    }
    var added = (Number(doc.additions) || 0);
    var removed = (Number(doc.deletions) || 0);
    if (added || removed) line2.appendChild(chipEl("+" + added + " −" + removed, ""));
    (Array.isArray(doc.labels) ? doc.labels : []).slice(0, 4).forEach(function (name) {
      line2.appendChild(chipEl(name, "c-purple"));
    });
    var meta = el("span", "h-meta");
    meta.textContent = doc.author + " · " + (doc.ago || "");
    line2.appendChild(meta);
    return hit.article;
  }

  function contribHit(doc, rank, max) {
    var hit = linkedHit(doc);
    hit.article.classList.add("carded-hit");
    var card = document.createElement("div");
    card.className = "contrib-card";
    var src = avatarUrl(doc.avatar_url);
    if (src) {
      var img = document.createElement("img");
      img.alt = "";
      img.src = src;
      img.loading = "lazy";
      card.appendChild(img);
    }
    var name = el("span", "cc-name");
    name.textContent = doc.login || doc.title || "";
    card.appendChild(name);
    var rankEl = el("span", "cc-rank");
    rankEl.textContent = "#" + rank + (doc.new === true ? " · new" : "");
    card.appendChild(rankEl);
    var count = el("span", "cc-count");
    count.textContent = String(Number(doc.contributions) || 0) + " contributions";
    card.appendChild(count);
    var meter = el("div", "cc-meter contrib-meter");
    var pct = Math.round(((Number(doc.contributions) || 0) / (max || 1)) * 100);
    meter.style.setProperty("--w", pct + "%");
    meter.appendChild(document.createElement("span"));
    card.appendChild(meter);
    var stats = el("div", "cc-stats");
    var week = document.createElement("span");
    week.innerHTML = "<b>" + (Number(doc.week_commits) || 0) + "</b> this week";
    var reviews = document.createElement("span");
    reviews.innerHTML = "<b>" + (Number(doc.reviews) || 0) + "</b> reviews";
    stats.append(week, reviews);
    card.appendChild(stats);
    hit.link.appendChild(card);
    return hit.article;
  }

  function avatarUrl(url) {
    var value = String(url || "");
    if (!value) return "";
    return value.indexOf("?") === -1 ? value + "?s=64" : value + "&s=64";
  }

  function renderIssues(panel) {
    var items = asList(DATA.issues);
    var page = el("div", "tab-page");
    var heading = el("h2");
    heading.textContent = "Issues";
    var openN = countOf(DATA.issues, "total_open");
    var closedN = countOf(DATA.issues, "total_closed");
    var counts = el("p");
    counts.textContent = formatCount(openN) + " open / " + formatCount(closedN) + " closed";
    var note = el("p");
    note.className = "tab-note";
    note.textContent = catalogReady
      ? "searching the " + scannedCount(DATA.issues, items) + " most recently updated open issues · click a row for details"
      : "showing the top " + items.length + " from the page snapshot — loading the full list…";
    var cards = el("div", "queue-cards");
    [["open", openN, "open now"], ["closed", closedN, "closed"], ["listed", items.length, "in this view"]].forEach(function (spec) {
      var card = document.createElement("div");
      card.className = "queue-card";
      var n = el("span", "qc-n");
      n.textContent = formatCount(spec[1]);
      var label = el("span", "qc-label");
      label.textContent = spec[2];
      card.append(n, label);
      cards.appendChild(card);
    });
    var input = document.createElement("input");
    input.id = "issue-q";
    input.type = "search";
    input.placeholder = "Search issues";
    input.setAttribute("aria-label", "Search issues");
    var filters = el("div");
    filters.setAttribute("data-chip-group", "filter");
    filters.setAttribute("role", "group");
    filters.setAttribute("aria-label", "Filter issues");
    [
      ["All", "all", ""],
      ["<1d", "age", "1"],
      ["<7d", "age", "7"],
      ["<30d", "age", "30"],
      ["older", "age", "older"],
      ["unassigned", "unassigned", ""],
    ].forEach(function (spec, index) {
      var btn = chip(spec[0], index === 0);
      btn.setAttribute("data-filter", spec[1]);
      if (spec[2]) btn.setAttribute("data-value", spec[2]);
      filters.appendChild(btn);
    });
    topLabels(items).forEach(function (name) {
      var btn = chip(name, false);
      btn.setAttribute("data-filter", "label");
      btn.setAttribute("data-value", name);
      filters.appendChild(btn);
    });
    var sorts = el("div");
    sorts.className = "chips";
    sorts.style.margin = "8px 0";
    sorts.setAttribute("data-chip-group", "sort");
    sorts.setAttribute("role", "group");
    sorts.setAttribute("aria-label", "Sort issues");
    [["Newest", "newest"], ["Oldest", "oldest"], ["Most commented", "comments"]].forEach(function (spec, index) {
      var btn = chip(spec[0], index === 0);
      btn.setAttribute("data-sort", spec[1]);
      sorts.appendChild(btn);
    });
    var list = el("div", "hit-list carded");
    list.id = "issue-hits";
    list.setAttribute("aria-live", "polite");
    page.append(heading, counts, note, cards, input, filters, sorts, list);
    panel.appendChild(page);
    input.addEventListener("input", paintIssues);
    paintIssues();
  }

  function paintIssues() {
    var list = document.getElementById("issue-hits");
    var input = document.getElementById("issue-q");
    var api = window.NousSearch;
    if (!list || !input || !api) return;
    var filterBtn = selected("issues", "filter");
    var sortBtn = selected("issues", "sort");
    var filter = filterBtn ? filterBtn.getAttribute("data-filter") : "all";
    var value = filterBtn ? (filterBtn.getAttribute("data-value") || "") : "";
    var sort = sortBtn ? (sortBtn.getAttribute("data-sort") || "newest") : "newest";
    var docs = asList(DATA.issues).map(issueDoc).filter(function (doc) {
      return passIssue(doc, filter, value);
    });
    var shown;
    if (queryIsBlank(input.value)) shown = sortIssues(docs, sort);
    else {
      var found = api.searchDocs(docs, input.value, docs.length);
      shown = found.hits.map(function (hit) { return hit.doc; });
      if (sort !== "newest") shown = sortIssues(shown, sort);
    }
    list.replaceChildren.apply(list, shown.map(function (doc) { return issueHit(doc, input.value); }));
  }

  function renderPrs(panel) {
    var items = asList(DATA.pull_requests);
    var page = el("div", "tab-page");
    var heading = el("h2");
    heading.textContent = "Pull requests";
    var openN = countOf(DATA.pull_requests, "total_open");
    var closedN = countOf(DATA.pull_requests, "total_closed");
    var counts = el("p");
    counts.textContent = formatCount(openN) + " open · " + formatCount(closedN) + " closed";
    var note = el("p");
    note.className = "tab-note";
    note.textContent = catalogReady
      ? "queues from the " + scannedCount(DATA.pull_requests, items) +
        " most recently updated open pull requests · click a row for details"
      : "showing the top " + items.length + " from the page snapshot — loading the full list…";
    var input = document.createElement("input");
    input.id = "pr-q";
    input.type = "search";
    input.placeholder = "Search pull requests";
    input.setAttribute("aria-label", "Search pull requests");
    var queues = { all: items.length, "needs-review": 0, approved: 0, changes: 0, draft: 0 };
    items.forEach(function (pr) {
      if (queues[pr.queue] != null) queues[pr.queue] += 1;
    });
    var cards = el("div", "queue-cards");
    [
      ["all", "All"], ["needs-review", "Needs review"], ["approved", "Approved"],
      ["changes", "Changes"], ["draft", "Draft"]
    ].forEach(function (spec, index) {
      var card = document.createElement("a");
      card.className = "queue-card" + (index === 0 ? " is-on" : "");
      card.href = "#prs";
      card.setAttribute("data-queue-card", spec[0]);
      var n = el("span", "qc-n");
      n.textContent = String(queues[spec[0]] != null ? queues[spec[0]] : 0);
      var label = el("span", "qc-label");
      label.textContent = spec[1];
      card.append(n, label);
      cards.appendChild(card);
    });
    var filters = el("div");
    filters.setAttribute("data-chip-group", "queue");
    filters.setAttribute("role", "group");
    filters.setAttribute("aria-label", "Review queue");
    [
      ["All", "all"], ["Needs review", "needs-review"], ["Approved", "approved"],
      ["Changes", "changes"], ["Draft", "draft"],
    ].forEach(function (spec, index) {
      var btn = chip(spec[0] + " " + queues[spec[1]], index === 0);
      btn.setAttribute("data-queue", spec[1]);
      filters.appendChild(btn);
    });
    var staleLink = el("p");
    staleLink.className = "tab-note";
    staleLink.innerHTML = 'Long-stalled review work: <a href="#triage">PRs awaiting a first review for 30+ days →</a>';
    var list = el("div", "hit-list carded");
    list.id = "pr-hits";
    page.append(heading, counts, note, cards, input, filters, staleLink, list);
    // the 6-hour PR archive lives on this page, under the queues
    var archive = panel.querySelector("#prarchive");
    if (archive) panel.insertBefore(page, archive);
    else panel.appendChild(page);
    input.addEventListener("input", paintPrs);
    cards.addEventListener("click", function (event) {
      var card = event.target.closest("a[data-queue-card]");
      if (!card) return;
      event.preventDefault();
      cards.querySelectorAll("a.queue-card").forEach(function (node) {
        node.classList.toggle("is-on", node === card);
      });
      var want = card.getAttribute("data-queue-card");
      filters.querySelectorAll("button.chip").forEach(function (btn) {
        var on = btn.getAttribute("data-queue") === want;
        btn.classList.toggle("is-on", on);
        btn.setAttribute("aria-pressed", on ? "true" : "false");
      });
      paintPrs();
    });
    filters.addEventListener("click", function (event) {
      var btn = event.target.closest("button.chip");
      if (!btn) return;
      var want = btn.getAttribute("data-queue");
      cards.querySelectorAll("a.queue-card").forEach(function (node) {
        node.classList.toggle("is-on", node.getAttribute("data-queue-card") === want);
      });
      setTimeout(paintPrs, 0);
    });
    paintPrs();
    initArchive();
  }

  function paintPrs() {
    var list = document.getElementById("pr-hits");
    var input = document.getElementById("pr-q");
    var api = window.NousSearch;
    if (!list || !input || !api) return;
    var queueBtn = selected("prs", "queue");
    var queue = queueBtn ? (queueBtn.getAttribute("data-queue") || "all") : "all";
    var docs = asList(DATA.pull_requests).map(prDoc).filter(function (doc) {
      return queue === "all" || doc.queue === queue;
    });
    var found = api.searchDocs(docs, input.value, docs.length);
    list.replaceChildren.apply(list, found.hits.map(function (hit) { return prHit(hit.doc, input.value); }));
  }

  function people() {
    return asList(DATA.contributors);
  }

  function renderContribs(panel) {
    var page = el("div", "tab-page");
    var heading = el("h2");
    heading.textContent = "Contributors";
    var note = el("p");
    note.className = "tab-note";
    note.textContent = "ranked by contributions · hover a card for the exact count";
    var input = document.createElement("input");
    input.id = "contrib-q";
    input.type = "search";
    input.placeholder = "Search contributors";
    input.setAttribute("aria-label", "Search contributors");
    var filters = el("div");
    filters.className = "chips";
    filters.style.margin = "8px 0";
    filters.setAttribute("data-chip-group", "filter");
    filters.setAttribute("role", "group");
    filters.setAttribute("aria-label", "Filter contributors");
    var all = chip("All", true);
    all.setAttribute("data-filter", "all");
    var newer = chip("New", false);
    newer.setAttribute("data-filter", "new");
    filters.append(all, newer);
    var list = el("div", "hit-list contrib-grid");
    list.id = "contrib-hits";
    page.append(heading, note, input, filters, list);
    panel.appendChild(page);
    input.addEventListener("input", paintContribs);
    paintContribs();
  }

  function paintContribs() {
    var list = document.getElementById("contrib-hits");
    var input = document.getElementById("contrib-q");
    if (!list || !input) return;
    var api = window.NousSearch;
    var filterBtn = selected("contributors", "filter");
    var filter = filterBtn ? filterBtn.getAttribute("data-filter") : "all";
    var docs = people().map(contribDoc).filter(function (doc) {
      return filter !== "new" || doc.new === true;
    });
    var shown = docs;
    if (api && !queryIsBlank(input.value)) {
      shown = api.searchDocs(docs, input.value, docs.length).hits.map(function (hit) { return hit.doc; });
    }
    var max = shown.reduce(function (best, doc) {
      var n = Number(doc.contributions) || 0;
      return n > best ? n : best;
    }, 1);
    list.replaceChildren.apply(list, shown.map(function (doc, index) {
      return contribHit(doc, index + 1, max);
    }));
  }

  function renderInfo(panel) {
    var page = el("div", "tab-page");
    page.setAttribute("aria-labelledby", "info-h");
    page.className = "tab-page info-copy";
    var heading = el("h2");
    heading.id = "info-h";
    heading.textContent = "Info";
    page.appendChild(heading);

    function card(title, paragraphs) {
      var box = el("div", "info-card");
      var h = el("h3");
      h.textContent = title;
      box.appendChild(h);
      paragraphs.forEach(function (text) {
        var p = el("p");
        p.textContent = text;
        box.appendChild(p);
      });
      return box;
    }

    var cards = el("div", "info-cards");
    cards.appendChild(card("What this is", [
      "Nous Space is a read-only community observatory for the Hermes Agent repository. It tracks what the maintainer lane is shipping, what is merging, and how the broader Hermes ecosystem is growing."
    ]));
    cards.appendChild(card("The strips", [
      "The green strip shows open pull requests the maintainer is involved in, ranked by merge likelihood. The blue strip shows pull requests merged to main by or authored by the maintainer.",
      "Click any block — or the author name under a merged block — to open that pull request\u2019s page here. The factors behind the green order are listed under the strip."
    ]));
    cards.appendChild(card("Data", [
      "Everything here comes from public GitHub data collected by an automated, strictly read-only watch lane: a full pull-request backfill (over 96,000 PRs), an issues backfill in progress, a live maintainer watch, and a merge corpus that feeds the quality program. The watcher never comments, reviews, or reacts on GitHub.",
      "The free ecosystem catalog indexes skills, plugins, mods, and other community add-ons. Free and open tools only."
    ]));
    cards.appendChild(card("Freshness", [
      "This page ships a small build-time snapshot. On load it asks the live API (/api/v1/overview) for newer numbers. Every panel carries a stamp with an explicit date and timezone: \u201cAPI <when>\u201d when the live API refreshed it, \u201csnapshot <when>\u201d for build-time data. Hover any stamp for the exact UTC instant."
    ]));
    page.appendChild(cards);

    var repoUrl = DATA.repo_url || (DATA.repo ? "https://github.com/" + DATA.repo : "");
    var links = el("div", "info-links");
    function addLink(href, label) {
      var a = document.createElement("a");
      a.href = href;
      if (/^https?:/.test(href)) {
        a.target = "_blank";
        a.rel = "noopener";
      }
      a.textContent = label;
      links.appendChild(a);
    }
    if (repoUrl) addLink(repoUrl, "Repository");
    addLink("#docs", "API docs");
    addLink("https://nous.minddragonlabs.com/api", "API index");
    addLink("#arch", "System architecture");
    addLink("/feed.json", "JSON Feed");
    addLink("/feed.xml", "Atom");
    addLink("#provenance", "Provenance & coverage");
    page.appendChild(links);

    var stamp = el("p");
    stamp.id = "freshness-detail";
    if (DATA.generated) {
      var t = Date.parse(String(DATA.generated));
      stamp.textContent = "Snapshot built " + (Number.isNaN(t) ? String(DATA.generated) : absLocal(t) + " (" + absUtc(t) + ")");
    } else {
      stamp.textContent = "";
    }
    page.appendChild(stamp);
    panel.insertBefore(page, panel.firstChild);
  }

  function bindEco() {
    var form = document.getElementById("eco-search");
    var eco = document.getElementById("eco-q");
    if (eco) {
      eco.addEventListener("input", function () {
        if (viewFromHash() === "search" && window.NousUnified) window.NousUnified.setQuery(eco.value);
      });
    }
    if (!form) return;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var value = eco ? eco.value.trim() : "";
      var next = "#search" + (value ? "?q=" + encodeURIComponent(value) : "");
      if (location.hash === next) showView("search", true);
      else location.hash = next;
    });
  }

  function paintFreshness() {
    var node = document.getElementById("freshness");
    if (!node) return;
    if (!DATA.generated) {
      node.textContent = "";
      return;
    }
    var t = Date.parse(String(DATA.generated));
    if (Number.isNaN(t)) {
      node.textContent = "";
      return;
    }
    node.textContent = "updated " + absLocal(t) + " · " + agoText(t);
    node.title = "Snapshot built " + absUtc(t) + " · " + absLocal(t) +
      " — hover the panel stamps for per-panel times.";
    paintAges();
  }

  function agoText(ts) {
    var min = Math.max(0, Math.round((Date.now() - ts) / 60000));
    if (min < 60) return min + "m ago";
    var hours = Math.round(min / 60);
    if (hours < 48) return hours + "h ago";
    return Math.round(hours / 24) + "d ago";
  }

  function paintAges() {
    document.querySelectorAll("#hn-scroll .hn-row[data-ts]").forEach(function (row) {
      var meta = row.querySelector(".hn-meta");
      var ts = Number(row.getAttribute("data-ts"));
      if (!meta || !ts) return;
      var lane = row.getAttribute("data-lane") || row.getAttribute("data-kind") || "pr";
      var label = lane === "merged" ? "merged" : (lane === "issue" ? "issue" : "pull request");
      var author = row.getAttribute("data-author") || "";
      var parts = [label];
      if (author) parts.push(author);
      parts.push(agoText(ts * 1000));
      meta.textContent = parts.join(" · ");
    });
  }

  function syncNavHeight() {
    var nav = document.querySelector("nav.topnav");
    if (!nav) return;
    document.documentElement.style.setProperty("--nav-h", nav.offsetHeight + "px");
  }

  function inputFocused() {
    var active = document.activeElement;
    if (!active) return false;
    var tag = active.tagName;
    return tag === "INPUT" || tag === "TEXTAREA";
  }

  function scheduleReload() {
    setTimeout(function () {
      var disc = document.getElementById("hn-discussion");
      var discussing = disc && !disc.hidden;
      var scroll = document.getElementById("hn-scroll");
      var reading = scroll && scroll.scrollTop > 80;
      if (viewFromHash() === "dashboard" && !inputFocused() && !discussing && !reading) {
        location.reload();
        return;
      }
      scheduleReload();
    }, RELOAD_MS);
  }

  // ── loading: deferred scripts + versioned data shards ─────────────────────

  var scriptPromises = Object.create(null);
  var jsonPromises = Object.create(null);

  function loadScript(src) {
    if (scriptPromises[src]) return scriptPromises[src];
    scriptPromises[src] = new Promise(function (resolve, reject) {
      var node = document.createElement("script");
      node.src = src + (DATA.v ? "?v=" + encodeURIComponent(DATA.v) : "");
      node.async = true;
      node.onload = function () { resolve(); };
      node.onerror = function () { delete scriptPromises[src]; reject(new Error(src)); };
      document.head.appendChild(node);
    });
    return scriptPromises[src];
  }

  function loadJSON(path) {
    if (jsonPromises[path]) return jsonPromises[path];
    var url = path + (DATA.v ? "?v=" + encodeURIComponent(DATA.v) : "");
    function get() {
      return fetch(url).then(function (response) {
        if (!response.ok) throw new Error(path + " " + response.status);
        return response.json();
      });
    }
    // one retry: static hosts occasionally reset a burst of parallel requests
    jsonPromises[path] = get().catch(function () {
      return new Promise(function (resolve) { setTimeout(resolve, 500); }).then(get);
    }).catch(function (err) {
      delete jsonPromises[path];
      throw err;
    });
    return jsonPromises[path];
  }

  function whenCatalog(cb) {
    if (catalogReady) cb();
    else catalogWaiters.push(cb);
  }

  // The embedded island is a tiny summary (counts + top rows). The full
  // working set arrives from data/catalog.json; views rebuild when it lands.
  function loadCatalog() {
    loadJSON("data/catalog.json").then(function (full) {
      if (!full || typeof full !== "object") return;
      var keep = { v: DATA.v, api: DATA.api, eco_counts: DATA.eco_counts };
      DATA = Object.assign({}, full, keep);
      catalogReady = true;
      rebuildViews(["issues", "prs", "contributors", "triage"]);
      var waiters = catalogWaiters.splice(0);
      waiters.forEach(function (cb) { try { cb(); } catch (err) { /* keep going */ } });
    }).catch(function () {
      catalogReady = true;
      DATA.catalogFailed = true;
      rebuildViews(["triage"]);
      catalogWaiters.splice(0).forEach(function (cb) { try { cb(); } catch (err) { /* keep going */ } });
    });
  }

  function rebuildViews(views) {
    var current = viewFromHash();
    views.forEach(function (view) {
      if (!built[view]) return;
      var panel = viewPanel(view);
      if (!panel) return;
      var input = panel.querySelector("input[type=search]");
      var value = input ? input.value : "";
      var page = panel.querySelector(".tab-page");
      if (page) page.remove();
      built[view] = false;
      if (view === current) {
        ensureRendered(view);
        var again = panel.querySelector("input[type=search]");
        if (again && value) {
          again.value = value;
          again.dispatchEvent(new Event("input"));
        }
      }
    });
  }

  // ── live data island: /api/v1/overview over the build-time snapshot ──────

  var API_ORIGIN = "https://nous.minddragonlabs.com";
  var LIVE = { state: "pending", apiTime: "", fetchedAt: 0 };

  function apiRequest(path) {
    // Same-origin on the production host (Vercel rewrites /api/v1 to the
    // worker) so the attribution header can be sent. Elsewhere use a simple
    // CORS GET: the worker does not answer preflight, so no custom headers.
    var sameOrigin = location.hostname === "nous.minddragonlabs.com";
    var url = (sameOrigin ? "" : API_ORIGIN) + "/api/v1" + path;
    var opts = sameOrigin ? { headers: { "X-Nous-Attribution": "nous-space-web" } } : {};
    var ctl = typeof AbortController === "function" ? new AbortController() : null;
    if (ctl) {
      opts.signal = ctl.signal;
      setTimeout(function () { ctl.abort(); }, 8000);
    }
    return fetch(url, opts);
  }

  function pathGet(obj, path) {
    return String(path).split(".").reduce(function (acc, key) {
      return acc && typeof acc === "object" ? acc[key] : undefined;
    }, obj);
  }

  function clock(ts) {
    var d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  // Absolute times always carry the date and the timezone name — never a
  // bare clock ("10:53am" of which day? which zone?). Hover titles repeat
  // the UTC instant so any two readers can compare exactly.
  function tzName(d) {
    try {
      var parts = new Intl.DateTimeFormat(undefined, { timeZoneName: "short" }).formatToParts(d);
      for (var i = 0; i < parts.length; i++) {
        if (parts[i].type === "timeZoneName") return parts[i].value;
      }
    } catch (e) {}
    return "";
  }

  function absLocal(ts) {
    var d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "";
    var date = d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
    var time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    var zone = tzName(d);
    return date + ", " + time + (zone ? " " + zone : "");
  }

  function absUtc(ts) {
    var d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "";
    return d.toISOString().slice(0, 16).replace("T", " ") + " UTC";
  }

  function paintStamps() {
    document.querySelectorAll(".fresh-stamp[data-built]").forEach(function (node) {
      var built = node.getAttribute("data-built");
      var api = node.hasAttribute("data-api-panel");
      var apiNewer = LIVE.state === "api" && api;
      node.classList.toggle("is-api", apiNewer);
      node.classList.toggle("is-stale", LIVE.state === "failed" && api);
      if (apiNewer) {
        node.textContent = "API " + absLocal(LIVE.fetchedAt);
        node.title = "Refreshed in your browser from /api/v1/overview at " + absUtc(LIVE.fetchedAt) +
          " (API data " + absUtc(LIVE.apiTime) + ")";
      } else {
        node.textContent = "snapshot " + absLocal(built);
        node.title = "Build-time snapshot " + absUtc(built) + " · " + absLocal(built) +
          (api && LIVE.state === "failed" ? " — live API unreachable, showing the snapshot" : "") +
          (api && LIVE.state === "older" ? " — the live API (" + absUtc(LIVE.apiTime) + ") is older than this snapshot" : "");
      }
    });
    var pill = document.getElementById("live-state");
    if (!pill) return;
    pill.classList.toggle("is-api", LIVE.state === "api");
    pill.classList.toggle("is-snapshot", LIVE.state !== "api" && LIVE.state !== "pending");
    if (LIVE.state === "api") pill.textContent = "live · API " + absLocal(LIVE.fetchedAt);
    else if (LIVE.state === "pending") pill.textContent = "checking API…";
    else pill.textContent = "snapshot " + absLocal(DATA.generated || "");
    pill.title = LIVE.state === "api"
      ? "Numbers on API-backed panels were refreshed from /api/v1/overview at " + absUtc(LIVE.fetchedAt)
      : LIVE.state === "older"
        ? "The live API data (" + absUtc(LIVE.apiTime) + ") is older than this page's snapshot, so the snapshot is shown"
        : "Showing the build-time snapshot (" + absUtc(DATA.generated || "") + " · " + absLocal(DATA.generated || "") + ")";
  }

  function applyOverview(overview) {
    var changed = 0;
    document.querySelectorAll("[data-api]").forEach(function (node) {
      var value = pathGet(overview, node.getAttribute("data-api"));
      if (value == null || value === "") return;
      var text = typeof value === "number" ? value.toLocaleString() : String(value);
      if (node.textContent.trim() !== text) {
        node.textContent = text;
        node.classList.remove("data-updated");
        void node.offsetWidth;
        node.classList.add("data-updated");
        changed += 1;
      }
    });
    if (overview.ecosystem && typeof overview.ecosystem === "object") {
      DATA.eco_counts = Object.assign({}, DATA.eco_counts || {}, overview.ecosystem);
    }
    return changed;
  }

  function fetchOverview() {
    LIVE.state = "pending";
    paintStamps();
    apiRequest("/overview").then(function (response) {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    }).then(function (overview) {
      LIVE.apiTime = String(overview.generated || "");
      LIVE.fetchedAt = Date.now();
      var apiTs = toTs(overview.generated);
      var snapTs = toTs(DATA.generated);
      // Never let an older API payload overwrite a newer build snapshot.
      if (apiTs && snapTs && apiTs < snapTs) {
        LIVE.state = "older";
      } else {
        LIVE.state = "api";
        LIVE.overview = overview;
        applyOverview(overview);
      }
      paintStamps();
    }).catch(function () {
      LIVE.state = "failed";
      paintStamps();
    });
  }

  // ── lazy detail drawer ───────────────────────────────────────────────────

  var docRegistry = new Map();
  var docSeq = 0;
  var drawerOpener = null;
  var drawerToken = 0;
  var PUBLIC_WINDOW_MS = 6 * 3600 * 1000;

  // Rows carry data-drawer="<key>"; the key maps back to the row's doc.
  function registerDoc(doc) {
    docSeq += 1;
    docRegistry.set(docSeq, doc);
    if (docRegistry.size > 8000) {
      var cut = docSeq - 6000;
      docRegistry.forEach(function (_doc, key) { if (key < cut) docRegistry.delete(key); });
    }
    return String(docSeq);
  }

  function lookupDoc(key) {
    return docRegistry.get(Number(key)) || null;
  }

  function latestTs(doc) {
    var best = 0;
    ["merged_at", "updated_at", "created_at", "ts"].forEach(function (key) {
      var t = toTs(doc[key]);
      if (t > best) best = t;
    });
    return best;
  }

  function dl(rows) {
    return "<dl>" + rows.filter(function (row) { return row[1] !== "" && row[1] != null; }).map(function (row) {
      return "<dt>" + escapeHtml(row[0]) + "</dt><dd>" + (row[2] ? row[1] : escapeHtml(row[1])) + "</dd>";
    }).join("") + "</dl>";
  }

  function drawerMeta(doc) {
    var labels = Array.isArray(doc.labels) ? doc.labels.filter(Boolean) : [];
    var labelHtml = labels.length
      ? '<span class="drawer-labels">' + labels.map(function (name) {
        return '<span class="badge">' + escapeHtml(name) + "</span>";
      }).join("") + "</span>"
      : "";
    var state = doc.state || "";
    if (doc.kind === "pr" && doc.draft) state = "draft";
    var review = doc.review ? String(doc.review).toLowerCase().replace(/_/g, " ") : "";
    var ci = doc.ci_total ? (doc.ci_ok || 0) + "/" + doc.ci_total + (doc.ci ? " " + doc.ci : "") : "";
    var diff = doc.additions != null || doc.deletions != null
      ? "+" + (Number(doc.additions) || 0) + " −" + (Number(doc.deletions) || 0) : "";
    return dl([
      ["type", doc.kind === "issue" ? "issue" : "pull request"],
      ["state", state],
      ["author", doc.author || ""],
      ["labels", labelHtml, true],
      ["review", review],
      ["checks", ci],
      ["diff", diff],
      ["created", doc.created_at ? String(doc.created_at).replace("T", " ").slice(0, 16) : ""],
      ["updated", doc.updated_at ? String(doc.updated_at).replace("T", " ").slice(0, 16) : ""],
      ["merged", doc.merged_at ? String(doc.merged_at).replace("T", " ").slice(0, 16) : (doc.date && state === "merged" ? doc.date : "")]
    ]) + (doc.url ? '<p><a href="' + escapeHtml(doc.url) + '" target="_blank" rel="noopener">Open on GitHub ↗</a></p>' : "");
  }

  function drawerNote(text) {
    return '<p class="drawer-note">' + escapeHtml(text) + "</p>";
  }

  function loadDrawerBody(doc, token) {
    var slot = document.getElementById("drawer-full");
    if (!slot) return;
    if (doc.kind !== "pr") {
      slot.innerHTML = drawerNote("The API serves pull-request records only. Read the full issue on GitHub.");
      return;
    }
    var ts = latestTs(doc);
    if (!ts || Date.now() - ts > PUBLIC_WINDOW_MS) {
      slot.innerHTML = drawerNote("Full body requires an API key: this record is older than the 6-hour public window. Metadata above; full text on GitHub.");
      return;
    }
    slot.innerHTML = '<p class="hn-meta">Loading the full body from the API…</p>';
    apiRequest("/prs/" + encodeURIComponent(doc.number)).then(function (response) {
      if (token !== drawerToken) return null;
      if (response.status === 401 || response.status === 403) {
        slot.innerHTML = drawerNote("Full body requires an API key. Read it on GitHub.");
        return null;
      }
      if (!response.ok) {
        slot.innerHTML = drawerNote("The API has no public record for #" + doc.number + " yet (HTTP " + response.status + "). Full body requires an API key once the record leaves the 6-hour window. Read it on GitHub.");
        return null;
      }
      return response.json();
    }).then(function (payload) {
      if (!payload || token !== drawerToken) return;
      var rec = payload.pr || payload.item || payload.record || payload;
      var body = rec.body || rec.summary || "";
      slot.innerHTML = body
        ? '<h3 class="sr-only">Body</h3><div class="disc-body">' + renderMarkdown(String(body)) + "</div>"
        : drawerNote("The API record has no body text.");
    }).catch(function () {
      if (token !== drawerToken) return;
      slot.innerHTML = drawerNote("The API is unreachable right now. Read it on GitHub.");
    });
  }

  function openDrawer(doc, opener) {
    var drawer = document.getElementById("drawer");
    var back = document.getElementById("drawer-backdrop");
    var body = document.getElementById("drawer-body");
    var title = document.getElementById("drawer-title");
    if (!drawer || !doc) return;
    drawerToken += 1;
    drawerOpener = opener || document.activeElement;
    title.textContent = (doc.number != null && doc.number !== "" ? "#" + doc.number + " " : "") + (doc.title || "");
    body.innerHTML = drawerMeta(doc) + '<div id="drawer-full"></div>';
    drawer.hidden = false;
    back.hidden = false;
    document.body.style.overflow = "hidden";
    var close = document.getElementById("drawer-close");
    if (close) close.focus();
    loadDrawerBody(doc, drawerToken);
  }

  function closeDrawer() {
    var drawer = document.getElementById("drawer");
    if (!drawer || drawer.hidden) return;
    drawerToken += 1;
    drawer.hidden = true;
    document.getElementById("drawer-backdrop").hidden = true;
    document.body.style.overflow = "";
    if (drawerOpener && document.contains(drawerOpener) && drawerOpener.focus) drawerOpener.focus();
    drawerOpener = null;
  }

  function trapDrawerFocus(event) {
    var drawer = document.getElementById("drawer");
    if (!drawer || drawer.hidden) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeDrawer();
      return;
    }
    if (event.key !== "Tab") return;
    var nodes = Array.prototype.filter.call(
      drawer.querySelectorAll('a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])'),
      function (node) { return node.offsetParent !== null || node === document.activeElement; }
    );
    if (!nodes.length) return;
    var first = nodes[0];
    var last = nodes[nodes.length - 1];
    if (!drawer.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function plainClick(event) {
    return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
  }

  // ── 06 / ARCHIVE panel (data/archive.json, loaded when scrolled near) ─────

  // ── PR archive: last 6 hours, sort options, lives on the PRs page ───────

  var ARCH6 = null;
  var ARCH6_LOADING = false;

  function initArchive() {
    var section = document.getElementById("prarchive");
    if (!section || section.getAttribute("data-bound")) return;
    section.setAttribute("data-bound", "1");
    var search = document.getElementById("prarch-search");
    if (search) {
      var timer = null;
      search.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(paintArchive, 150);
      });
    }
    if (ARCH6) {
      paintArchive();
      return;
    }
    if (ARCH6_LOADING) return;
    ARCH6_LOADING = true;
    loadJSON("data/archive6.json").then(function (payload) {
      ARCH6_LOADING = false;
      ARCH6 = Array.isArray(payload && payload.prs) ? payload.prs : [];
      paintArchive();
    }).catch(function () {
      ARCH6_LOADING = false;
      ARCH6 = [];
      paintArchive();
    });
  }

  function archiveDoc(row) {
    var repo = DATA.repo || "NousResearch/hermes-agent";
    return {
      kind: "pr", number: row.n, title: row.t || "", author: row.a || "",
      state: row.s || "", date: row.ts ? new Date(row.ts * 1000).toISOString() : "",
      merged_at: row.s === "merged" && row.ts ? new Date(row.ts * 1000).toISOString() : "",
      additions: row.add, deletions: row.del, comments: row.c,
      labels: [], url: row.url || ("https://github.com/" + repo + "/pull/" + row.n)
    };
  }

  function sortArchive(rows, mode) {
    var copy = rows.slice();
    copy.sort(function (a, b) {
      if (mode === "oldest") return (a.ts || 0) - (b.ts || 0);
      if (mode === "changed") return ((b.add || 0) + (b.del || 0)) - ((a.add || 0) + (a.del || 0)) || (b.ts || 0) - (a.ts || 0);
      if (mode === "discussed") return (b.c || 0) - (a.c || 0) || (b.ts || 0) - (a.ts || 0);
      return (b.ts || 0) - (a.ts || 0);
    });
    return copy;
  }

  function paintArchive() {
    var list = document.getElementById("prarch-list");
    if (!list) return;
    if (!ARCH6) {
      initArchive();
      return;
    }
    var search = document.getElementById("prarch-search");
    var q = (search ? search.value : "").toLowerCase().trim();
    var rows = ARCH6;
    if (q) {
      rows = rows.filter(function (r) {
        return ("#" + r.n + " " + r.t + " " + r.a).toLowerCase().indexOf(q) !== -1;
      });
    }
    var group = document.querySelector('[data-chip-group="arch-sort"]');
    var sortBtn = group ? group.querySelector("button.chip.is-on") : null;
    rows = sortArchive(rows, sortBtn ? sortBtn.getAttribute("data-arch-sort") : "newest");
    var count = document.getElementById("prarch-count");
    if (count) count.textContent = String(rows.length);
    list.innerHTML = rows.length ? rows.map(function (r) {
      var doc = archiveDoc(r);
      var when = r.ts ? absLocal(r.ts * 1000) : "";
      var diff = (r.add || r.del) ? '<span class="prs-diff"><span class="add">+' + (r.add || 0) +
        '</span> <span class="del">-' + (r.del || 0) + "</span></span>" : "";
      return '<div class="prs-row"><a class="prs-main" href="' + escapeHtml(doc.url) +
        '" data-drawer="' + registerDoc(doc) + '" aria-haspopup="dialog">' +
        '<span class="prs-num">#' + Number(r.n) + "</span>" +
        '<span class="prs-title">' + escapeHtml(r.t) + "</span>" +
        '<span class="prs-status ' + (r.s === "open" ? "prs-open" : "prs-approved") + '">' +
        escapeHtml(r.s) + "</span>" +
        '<span class="prs-author">' + escapeHtml(r.a) + "</span>" + diff +
        '<span class="prs-time" title="' + escapeHtml(when) + '">' + escapeHtml(agoText(r.ts * 1000)) + "</span></a></div>";
    }).join("") : '<p class="eco-note">No PRs in this window match. The 6-hour window is the free public tier — older records need an API key (see the API docs).</p>';
  }

  // ── awaiting first review (triage) ───────────────────────────────────────

  function hashParams() {
    var raw = String(location.hash || "");
    var at = raw.indexOf("?");
    return new URLSearchParams(at === -1 ? "" : raw.slice(at + 1));
  }

  var TRIAGE_LANES = [
    ["maintainer", "Maintainer lane"],
    ["authored", "Authored by the maintainer"],
    ["involving", "Involving the maintainer"],
    ["recent", "Recently updated (all authors)"]
  ];

  function laneSource() {
    var byNum = new Map();
    var stale = DATA.lane_stale && Array.isArray(DATA.lane_stale.rows) ? DATA.lane_stale.rows : [];
    stale.concat(Array.isArray(DATA.lane_open) ? DATA.lane_open : []).forEach(function (pr) {
      if (pr && pr.number != null) byNum.set(pr.number, pr);
    });
    return Array.from(byNum.values());
  }

  function triageCoverage(lane) {
    var totals = (DATA.lane_stale && DATA.lane_stale.totals) || {};
    var rows = (DATA.lane_stale && DATA.lane_stale.rows) || [];
    var maintainer = DATA.maintainer || "";
    function part(scope, label) {
      if (totals[scope] == null) return "";
      var have = rows.filter(function (r) { return (r.author === maintainer) === (scope === "authored"); }).length;
      return label + ": " + (have < totals[scope]
        ? have.toLocaleString() + " most recently updated of " + Number(totals[scope]).toLocaleString()
        : "all " + Number(totals[scope]).toLocaleString());
    }
    if (lane === "recent") return "Coverage: the 50 most recently updated open PRs (all authors).";
    var bits = [];
    if (lane !== "involving") bits.push(part("authored", "authored by the maintainer"));
    if (lane !== "authored") bits.push(part("involving", "involving the maintainer"));
    bits = bits.filter(Boolean);
    return bits.length ? "Coverage (older than 30 days, no review): " + bits.join(" · ") + "." : "";
  }

  function triageRows(lane, days) {
    var maintainer = DATA.maintainer || "";
    var source;
    if (lane === "recent") source = asList(DATA.pull_requests);
    else source = laneSource();
    if (lane === "authored") source = source.filter(function (pr) { return pr.author === maintainer; });
    if (lane === "involving") source = source.filter(function (pr) { return pr.author !== maintainer; });
    var cutoff = Date.now() - days * 86400000;
    return source.filter(function (pr) {
      var created = toTs(pr.created_at);
      var review = String(pr.review || "").toUpperCase();
      return created && created <= cutoff && !pr.draft && review !== "APPROVED" && review !== "CHANGES_REQUESTED";
    }).sort(function (a, b) { return toTs(a.created_at) - toTs(b.created_at); });
  }

  function renderTriage(panel) {
    var params = hashParams();
    var lane = params.get("lane") || "maintainer";
    if (!TRIAGE_LANES.some(function (pair) { return pair[0] === lane; })) lane = "maintainer";
    var days = Math.max(1, Math.min(365, Number(params.get("days")) || 30));
    var page = el("div", "tab-page");
    var heading = el("h2");
    heading.textContent = "Awaiting first review";
    var intro = el("p", "tab-note");
    intro.textContent = "Open pull requests older than " + days + " days with no review decision recorded yet. Drafts are excluded. Ages are computed in your browser from each PR's creation time, so this list does not go stale between builds.";
    var lanes = el("div", "chips");
    lanes.setAttribute("role", "group");
    lanes.setAttribute("aria-label", "Lane");
    TRIAGE_LANES.forEach(function (pair) {
      var a = document.createElement("a");
      a.className = "chip" + (pair[0] === lane ? " is-on" : "");
      a.href = "#triage?lane=" + pair[0] + "&days=" + days;
      a.textContent = pair[1];
      if (pair[0] === lane) a.setAttribute("aria-current", "true");
      lanes.appendChild(a);
    });
    var ages = el("div", "chips");
    ages.setAttribute("role", "group");
    ages.setAttribute("aria-label", "Minimum age");
    [30, 60, 90].forEach(function (d) {
      var a = document.createElement("a");
      a.className = "chip" + (d === days ? " is-on" : "");
      a.href = "#triage?lane=" + lane + "&days=" + d;
      a.textContent = ">" + d + " days";
      if (d === days) a.setAttribute("aria-current", "true");
      ages.appendChild(a);
    });
    var list = el("div", "hit-list");
    list.setAttribute("aria-live", "polite");
    page.append(heading, intro, lanes, ages, list);
    panel.appendChild(page);

    if (!catalogReady) {
      var wait = el("p", "tab-note");
      wait.textContent = "Loading the lane…";
      list.appendChild(wait);
      return;
    }
    var haveLane = lane === "recent" || laneSource().length > 0;
    if (lane !== "recent" && !(DATA.lane_stale && DATA.lane_stale.totals)) {
      var older = el("p", "triage-meta");
      older.textContent = "Older lane PRs arrive with the next data refresh; until then only the 30 newest lane PRs are visible, so this list may be empty.";
      list.appendChild(older);
    }
    var rows = triageRows(lane, days);
    var meta = el("p", "triage-meta");
    meta.textContent = !haveLane
      ? "The lane list arrives with the next data refresh (it needs PR creation times). Try “Recently updated” meanwhile."
      : rows.length + (rows.length === 1 ? " pull request" : " pull requests") + " · oldest first · data " + (DATA.generated || "");
    list.appendChild(meta);
    var cov = triageCoverage(lane);
    if (cov && haveLane) {
      var covNode = el("p", "triage-meta");
      covNode.textContent = cov;
      list.appendChild(covNode);
    }
    rows.forEach(function (pr) {
      var doc = prDoc(pr);
      var hit = linkedHit(doc);
      addText(hit.link, "#" + pr.number);
      addText(hit.link, pr.title);
      addText(hit.link, "open " + Math.floor((Date.now() - toTs(pr.created_at)) / 86400000) + " days");
      addText(hit.link, "no review decision yet");
      list.appendChild(hit.article);
    });
    if (haveLane && !rows.length) {
      var none = el("p", "tab-note");
      none.textContent = "Nothing in this lane has waited that long.";
      list.appendChild(none);
    }
  }

  viewHooks.triage = {
    show: function (panel) {
      var key = String(location.hash || "");
      if (panel && panel.getAttribute("data-hash") !== key) {
        panel.setAttribute("data-hash", key);
        var page = panel.querySelector(".tab-page");
        if (page) {
          page.remove();
          renderTriage(panel);
        }
      }
    }
  };

  // ── API docs: curl builder ───────────────────────────────────────────────

  function shellQuote(value) {
    return "'" + String(value).replace(/'/g, "'\\''") + "'";
  }

  function bindCurlBuilder() {
    var form = document.getElementById("curl-builder");
    if (!form || form.getAttribute("data-bound")) return;
    form.setAttribute("data-bound", "1");
    var endpoint = document.getElementById("cb-endpoint");
    var paramWrap = document.getElementById("cb-param-wrap");
    var paramLabel = document.getElementById("cb-param-label");
    var param = document.getElementById("cb-param");
    var attr = document.getElementById("cb-attr");
    var key = document.getElementById("cb-key");
    var out = document.getElementById("cb-out");
    var copied = document.getElementById("cb-copied");
    var summary = document.getElementById("cb-summary");
    var defaults = { number: "130141", q: "gateway", page: "1" };
    function paint() {
      var option = endpoint.options[endpoint.selectedIndex];
      var name = option ? option.getAttribute("data-param") : "";
      if (summary) summary.textContent = option ? (option.getAttribute("data-summary") || "") : "";
      paramWrap.hidden = !name;
      if (name && paramWrap.getAttribute("data-for") !== name) {
        paramWrap.setAttribute("data-for", name);
        paramLabel.textContent = name === "number" ? "PR number" : name === "q" ? "Query (q)" : "Page";
        param.value = defaults[name] || "";
      }
      var path = endpoint.value;
      var value = param.value.trim();
      if (name === "number") path = path.replace("{number}", encodeURIComponent(value || defaults.number));
      else if (name && value) path += "?" + name + "=" + encodeURIComponent(value);
      var parts = ["curl -sS", "-H " + shellQuote("X-Nous-Attribution: " + (attr.value.trim() || "my-app"))];
      if (key.checked) parts.push('-H "X-Nous-Api-Key: $NOUS_API_KEY"');
      parts.push(shellQuote("https://nous.minddragonlabs.com/api/v1" + path));
      out.textContent = parts.join(" ");
      copied.textContent = "";
    }
    form.addEventListener("input", paint);
    form.addEventListener("change", paint);
    form.addEventListener("submit", function (event) { event.preventDefault(); });
    document.getElementById("cb-copy").addEventListener("click", function () {
      var text = out.textContent;
      var done = function () { copied.textContent = "Copied."; };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { selectText(out); copied.textContent = "Selected — press Ctrl/Cmd+C."; });
      } else {
        selectText(out);
        copied.textContent = "Selected — press Ctrl/Cmd+C.";
      }
    });
    paint();
  }

  function selectText(node) {
    var range = document.createRange();
    range.selectNodeContents(node);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  // ── forum: its own section, one "general" category for PRs and issues ───

  function forumThreads() {
    var seen = {};
    var out = [];
    function add(kind, doc) {
      if (!doc || doc.number == null || doc.number === "") return;
      var key = kind + ":" + doc.number;
      if (seen[key]) return;
      seen[key] = true;
      out.push({
        kind: kind,
        number: doc.number,
        title: doc.title || "",
        author: doc.author || "",
        state: doc.state || (kind === "issue" ? "open" : "open"),
        ts: toTs(doc.updated_at != null ? doc.updated_at : (doc.created_at || doc.ts))
      });
    }
    asList(DATA.pull_requests).forEach(function (doc) { add("pr", doc); });
    asList(DATA.issues).forEach(function (doc) { add("issue", doc); });
    (Array.isArray(ARCH6) ? ARCH6 : []).forEach(function (r) {
      add("pr", { number: r.n, title: r.t, author: r.a, state: r.s, ts: r.ts });
    });
    out.sort(function (a, b) { return (b.ts || 0) - (a.ts || 0); });
    return out.slice(0, 120);
  }

  function paintForum() {
    var list = document.getElementById("forum-threads");
    if (!list) return;
    var kindBtn = document.querySelector('[data-chip-group="forum-kind"] .chip.is-on');
    var kind = kindBtn ? kindBtn.getAttribute("data-forum-kind") : "all";
    var search = document.getElementById("forum-q");
    var q = (search ? search.value : "").toLowerCase().trim();
    var rows = forumThreads().filter(function (t) {
      if (kind !== "all" && t.kind !== kind) return false;
      if (!q) return true;
      return ("#" + t.number + " " + t.title + " " + t.author).toLowerCase().indexOf(q) !== -1;
    });
    list.innerHTML = rows.length ? rows.map(function (t) {
      return '<article class="forum-thread" data-kind="' + t.kind + '" data-number="' + t.number + '">' +
        '<button type="button" class="forum-thread-head">' +
        '<span class="ft-num">#' + Number(t.number) + "</span>" +
        '<span class="ft-title">' + escapeHtml(t.title || "") + "</span>" +
        '<span class="ft-meta">' + (t.kind === "issue" ? "issue" : "pull request") +
        (t.author ? " · " + escapeHtml(t.author) : "") + (t.state ? " · " + escapeHtml(t.state) : "") +
        "</span></button>" +
        '<div class="forum-thread-body" hidden></div></article>';
    }).join("") : '<p class="eco-note">No threads match.</p>';
  }

  function forumThreadToggle(article) {
    var body = article.querySelector(".forum-thread-body");
    if (!body) return;
    if (!body.hidden && body.getAttribute("data-loaded")) {
      body.hidden = true;
      return;
    }
    body.hidden = false;
    if (body.getAttribute("data-loaded")) return;
    body.setAttribute("data-loaded", "1");
    var kind = article.getAttribute("data-kind") === "issue" ? "issue" : "pr";
    var number = article.getAttribute("data-number");
    body.innerHTML = forumBox(kind, number);
    loadForum(body, kind, number);
  }

  function renderForum(panel) {
    var page = el("div", "tab-page");
    var heading = el("h2");
    heading.textContent = "Forum";
    var note = el("p");
    note.className = "tab-note";
    note.textContent = "Community discussion on Hermes Agent pull requests and issues. " +
      "For now everything lives in one general category. Click a thread to read and comment — " +
      "Google sign-in required to post.";
    var cats = el("div");
    cats.className = "forum-cats";
    var general = el("button");
    general.type = "button";
    general.className = "forum-cat is-on";
    general.setAttribute("aria-pressed", "true");
    general.textContent = "general";
    var later = el("button");
    later.type = "button";
    later.className = "forum-cat";
    later.disabled = true;
    later.textContent = "more categories later";
    cats.append(general, later);
    var kinds = el("div");
    kinds.className = "chips";
    kinds.setAttribute("data-chip-group", "forum-kind");
    kinds.setAttribute("role", "group");
    kinds.setAttribute("aria-label", "Filter threads");
    [["all", "All"], ["pr", "Pull requests"], ["issue", "Issues"]].forEach(function (spec, index) {
      var btn = chip(spec[1], index === 0);
      btn.setAttribute("data-forum-kind", spec[0]);
      kinds.appendChild(btn);
    });
    var input = document.createElement("input");
    input.id = "forum-q";
    input.type = "search";
    input.placeholder = "Search threads — number, title, author…";
    input.setAttribute("aria-label", "Search forum threads");
    input.className = "search-input";
    var list = el("div");
    list.id = "forum-threads";
    list.className = "forum-page";
    list.setAttribute("aria-live", "polite");
    page.append(heading, note, cats, kinds, input, list);
    panel.appendChild(page);
    input.addEventListener("input", paintForum);
    kinds.addEventListener("click", function (event) {
      if (event.target.closest("button.chip")) setTimeout(paintForum, 0);
    });
    list.addEventListener("click", function (event) {
      var head = event.target.closest(".forum-thread-head");
      if (head) forumThreadToggle(head.closest(".forum-thread"));
    });
    paintForum();
    forumDeepLink();
    viewHooks.forum = { show: function () { forumDeepLink(); } };
  }

  // deep link from the PR page: #forum?kind=pr&number=123
  function forumDeepLink() {
    var params = hashParams();
    var dk = params.get("kind");
    var dn = params.get("number");
    if (!dn) return;
    var list = document.getElementById("forum-threads");
    if (!list) return;
    var target = list.querySelector('.forum-thread[data-kind="' + (dk === "issue" ? "issue" : "pr") +
      '"][data-number="' + dn + '"]');
    if (target) {
      forumThreadToggle(target);
      if (target.scrollIntoView) target.scrollIntoView({ block: "center" });
    }
  }

  // ── system architecture: switch between per-release diagrams ────────────

  function bindArchPicker(panel) {
    var picker = document.getElementById("arch-picker");
    if (!picker || picker.getAttribute("data-bound")) return;
    picker.setAttribute("data-bound", "1");
    picker.addEventListener("click", function (event) {
      var btn = event.target.closest("button[data-arch]");
      if (!btn) return;
      picker.querySelectorAll("button.arch-version").forEach(function (node) {
        var on = node === btn;
        node.classList.toggle("is-on", on);
        node.setAttribute("aria-pressed", on ? "true" : "false");
      });
      var key = btn.getAttribute("data-arch");
      document.querySelectorAll("[data-arch-svg]").forEach(function (svgWrap) {
        var on = svgWrap.getAttribute("data-arch-svg") === key;
        svgWrap.hidden = !on;
        if (!on) return;
        var src = svgWrap.getAttribute("data-arch-src");
        if (src && svgWrap.getAttribute("data-loaded") !== "1" && !svgWrap.querySelector("svg")) {
          fetch(src, { cache: "force-cache" }).then(function (r) {
            return r.ok ? r.text() : "";
          }).then(function (text) {
            if (text && text.indexOf("<svg") !== -1) {
              svgWrap.innerHTML = text;
              svgWrap.setAttribute("data-loaded", "1");
            }
          }).catch(function () {});
        }
      });
    });
  }

  window.NousApp = {
    data: function () { return DATA; },
    catalogReady: function () { return catalogReady; },
    whenCatalog: whenCatalog,
    loadJSON: loadJSON,
    loadScript: loadScript,
    registerView: function (name, hook) { viewHooks[name] = hook; },
    openDrawer: openDrawer,
    registerDoc: registerDoc,
    escapeHtml: escapeHtml,
    highlight: highlight,
    issueDoc: issueDoc,
    prDoc: prDoc,
    contribDoc: contribDoc,
    asList: asList,
    toTs: toTs,
    hashParams: hashParams,
    queryIsBlank: queryIsBlank
  };

  function boot() {
    DATA = loadData();
    document.addEventListener("click", function (event) {
      if (event.target.closest(".skip-link")) {
        event.preventDefault();
        var main = document.getElementById("main");
        if (main) main.focus();
        return;
      }
      if (event.target.closest("#drawer-close") || event.target.id === "drawer-backdrop") {
        closeDrawer();
        return;
      }
      var opener = event.target.closest("[data-drawer]");
      if (opener && plainClick(event)) {
        var doc = lookupDoc(opener.getAttribute("data-drawer"));
        if (doc) {
          event.preventDefault();
          openDrawer(doc, opener);
          return;
        }
      }
      var nav = event.target.closest("[data-view]");
      if (nav) {
        event.preventDefault();
        var navView = nav.getAttribute("data-view") || "dashboard";
        if (navView === "dashboard") {
          resetView();
          return;
        }
        showView(navView, false);
        return;
      }
      if (event.target.closest("#brand-home")) {
        event.preventDefault();
        resetView();
        return;
      }
      var storyLink = event.target.closest("a[data-story]");
      if (storyLink && plainClick(event)) {
        event.preventDefault();
        openStory(storyDocFromEl(storyLink));
        return;
      }
      if (event.target.closest(".hn-title")) {
        event.preventDefault();
        openDiscussion(event.target.closest(".hn-row"));
        return;
      }
      if (event.target.closest(".hn-num")) {
        event.preventDefault();
        openDiscussion(event.target.closest(".hn-row"));
        return;
      }
      if (event.target.closest(".disc-back")) {
        closeDiscussion();
        return;
      }
      var button = event.target.closest("button.chip");
      if (!button) return;
      var group = button.closest("[data-chip-group]");
      if (!group) return;
      group.querySelectorAll("button.chip").forEach(function (node) {
        node.classList.remove("is-on");
        node.setAttribute("aria-pressed", "false");
      });
      button.classList.add("is-on");
      button.setAttribute("aria-pressed", "true");
      var view = viewFromHash();
      if (view === "issues") paintIssues();
      else if (view === "prs") {
        if (button.hasAttribute("data-arch-sort")) paintArchive();
        else paintPrs();
      }
      else if (view === "contributors") paintContribs();
    });
    document.addEventListener("keydown", trapDrawerFocus);
    window.addEventListener("hashchange", function () {
      if (location.hash === "#main") {
        var main = document.getElementById("main");
        if (main) main.focus();
        return;
      }
      if (location.hash === "#provenance") {
        showView("info", true);
        var prov = document.getElementById("provenance");
        if (prov && prov.scrollIntoView) prov.scrollIntoView();
        return;
      }
      showView(viewFromHash(), true);
    });
    bindEco();
    paintFreshness();
    paintStamps();
    setInterval(paintFreshness, 30000);
    syncNavHeight();
    window.addEventListener("resize", syncNavHeight);
    scheduleReload();
    showView(location.hash === "#provenance" ? "info" : viewFromHash(), true);
    loadCatalog();
    fetchOverview();
    initArchive();
    bindNews();
    var storyMatch = String(location.hash || "").match(/^#story\/(pr|issue)\/(\d+)$/);
    if (storyMatch) {
      var storyRow = document.querySelector(
        '#hn-scroll .hn-row[data-kind="' + storyMatch[1] + '"][data-number="' + storyMatch[2] + '"]'
      );
      if (storyRow) openDiscussion(storyRow);
      else openStory({
        kind: storyMatch[1],
        number: storyMatch[2],
        title: "#" + storyMatch[2],
        lane: storyMatch[1] === "issue" ? "issue" : "pr",
        author: "",
        url: "https://github.com/" + (DATA.repo || "NousResearch/hermes-agent") +
          (storyMatch[1] === "issue" ? "/issues/" : "/pull/") + storyMatch[2],
        ts: 0,
        maintainer: false
      });
    }
  }

  var discToken = 0;

  var seenNews = {};

  function rememberNews() {
    document.querySelectorAll("#hn-scroll .hn-row").forEach(function (row) {
      seenNews[row.getAttribute("data-kind") + ":" + row.getAttribute("data-number")] = true;
    });
  }

  function storyHtml(item, rank, live) {
    var kind = item.kind === "issue" ? "issue" : "pr";
    var lane = item.lane || kind;
    var label = lane === "merged" ? "merged" : (kind === "issue" ? "issue" : "pull request");
    var meta = [label, item.author || "", item.ago || ""].filter(Boolean).join(" · ");
    var blue = item.maintainer ? " is-maintainer" : "";
    var fresh = live ? " hn-live" : "";
    return '<article class="hn-row' + fresh + '" data-kind="' + kind + '" data-number="' +
      Number(item.number) + '" data-url="' + escapeHtml(item.url || "#") + '" data-ts="' +
      Number(item.ts || 0) + '" data-lane="' + escapeHtml(lane) + '" data-author="' +
      escapeHtml(item.author || "") + '">' +
      '<span class="hn-rank">' + rank + '</span><div class="hn-main">' +
      '<button type="button" class="hn-title' + blue + '">' + escapeHtml(item.title || "") + '</button>' +
      '<p class="hn-num">#' + Number(item.number) + '</p>' +
      '<p class="hn-meta">' + escapeHtml(meta) + '</p></div></article>';
  }

  function paintNews(items) {
    var scroll = document.getElementById("hn-scroll");
    if (!scroll) return;
    var mark = null;
    if (scroll.scrollTop > 80) {
      var rows = scroll.querySelectorAll(".hn-row");
      var box = scroll.getBoundingClientRect();
      for (var i = 0; i < rows.length; i++) {
        var rowBox = rows[i].getBoundingClientRect();
        if (rowBox.bottom > box.top + 1) {
          mark = {
            key: rows[i].getAttribute("data-kind") + ":" + rows[i].getAttribute("data-number"),
            delta: rowBox.top - box.top
          };
          break;
        }
      }
    }
    scroll.innerHTML = items.map(function (item, index) {
      var key = (item.kind === "issue" ? "issue" : "pr") + ":" + item.number;
      var isNew = !seenNews[key];
      return storyHtml(item, index + 1, isNew);
    }).join("");
    items.forEach(function (item) {
      seenNews[(item.kind === "issue" ? "issue" : "pr") + ":" + item.number] = true;
    });
    if (mark) {
      var anchor = scroll.querySelector('.hn-row[data-kind="' + mark.key.split(":")[0] + '"][data-number="' + mark.key.split(":")[1] + '"]');
      if (anchor) {
        var shift = anchor.getBoundingClientRect().top - scroll.getBoundingClientRect().top;
        scroll.scrollTop += shift - mark.delta;
      }
    }
  }

  var newsAll = null;
  var newsLoadingAll = false;

  function newsKey(item) {
    return (item.kind === "issue" ? "issue" : "pr") + ":" + item.number;
  }

  function mergeNews(head) {
    if (!newsAll) return head;
    var seen = Object.create(null);
    var out = [];
    head.concat(newsAll).forEach(function (item) {
      var key = newsKey(item);
      if (seen[key]) return;
      seen[key] = true;
      out.push(item);
    });
    return out.slice(0, 2500);
  }

  function pollNews(force) {
    var disc = document.getElementById("hn-discussion");
    if (!force && disc && !disc.hidden) return;
    fetch("data/news-head.json?t=" + Date.now(), { cache: "no-store" }).then(function (response) {
      if (!response.ok) return null;
      return response.json();
    }).then(function (payload) {
      if (!payload || !Array.isArray(payload.items) || !payload.items.length) return;
      if (payload.generated) {
        DATA.generated = payload.generated;
        paintFreshness();
      }
      var items = mergeNews(payload.items);
      var newest = items[0];
      if (seenNews[newsKey(newest)] && items.length === document.querySelectorAll("#hn-scroll .hn-row").length) return;
      paintNews(items);
    }).catch(function () {});
  }

  function loadAllNews() {
    if (newsAll || newsLoadingAll) return;
    newsLoadingAll = true;
    fetch("/news.json", { cache: "no-cache" }).then(function (response) {
      if (!response.ok) throw new Error("news");
      return response.json();
    }).then(function (payload) {
      if (!payload || !Array.isArray(payload.items)) return;
      newsAll = payload.items;
      paintNews(newsAll);
    }).catch(function () {
      newsLoadingAll = false;
    });
  }

  function bindNews() {
    rememberNews();
    var scroll = document.getElementById("hn-scroll");
    if (scroll) {
      scroll.addEventListener("scroll", function () {
        if (scroll.scrollTop + scroll.clientHeight > scroll.scrollHeight - 600) loadAllNews();
      }, { passive: true });
    }
    setTimeout(function () { pollNews(false); }, 1500);
    setInterval(function () { pollNews(false); }, 45000);
  }

  function renderGithubHtml(html) {
    return String(html || "")
      .replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, "")
      .replace(/\son\w+\s*=\s*(['"]).*?\1/gi, "")
      .replace(/javascript:/gi, "");
  }

  function renderBody(source, html) {
    if (html) return renderGithubHtml(html);
    return renderMarkdown(source || "");
  }

  function renderMarkdown(source) {
    var text = escapeHtml(source || "");
    text = text.replace(/```([\s\S]*?)```/g, function (_all, code) {
      return '<pre class="disc-code">' + code + "</pre>";
    });
    text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, function (_all, label, href) {
      return '<a href="' + href + '" target="_blank" rel="noopener">' + label + "</a>";
    });
    return "<p>" + text.replace(/\n{2,}/g, "</p><p>").replace(/\n/g, "<br>") + "</p>";
  }

  function closeDiscussion() {
    discToken += 1;
    if (/^#story\//.test(location.hash || "")) {
      history.replaceState(null, "", location.pathname + location.search);
    }
    var disc = document.getElementById("hn-discussion");
    var scroll = document.getElementById("hn-scroll");
    var head = document.querySelector("#news .hn-head");
    if (disc) {
      disc.hidden = true;
      disc.innerHTML = "";
    }
    if (scroll) scroll.hidden = false;
    if (head) head.hidden = false;
    var tail = document.getElementById("dash-tail");
    if (tail) tail.hidden = false;
  }

  // ── the PR page (story) ─────────────────────────────────────────────────
  // Opened from a block, a block author, a feed row, or a #story/pr/N link.
  // The heading is the PR title, the info block is a badge grid, and the
  // sections below the feed hide while the page is open — no PR archive
  // under the PR.

  // The Nous Space brand and the 4-square dashboard button reset everything
  // back to the default view: no open story, no drawer, no leftover hash.
  function resetView() {
    closeDrawer();
    closeDiscussion();
    showView("dashboard", false);
    writeHash("dashboard");
    if (window.scrollTo) window.scrollTo({ top: 0, behavior: "auto" });
    var blockstrip = document.getElementById("blockstrip");
    if (blockstrip && blockstrip.scrollIntoView) blockstrip.scrollIntoView({ block: "nearest" });
  }

  function storyDocFromRow(row) {
    var titleNode = row.querySelector(".hn-title");
    return {
      kind: row.getAttribute("data-kind") === "issue" ? "issue" : "pr",
      number: row.getAttribute("data-number"),
      title: titleNode ? titleNode.textContent : "",
      lane: row.getAttribute("data-lane") || row.getAttribute("data-kind") || "pr",
      author: row.getAttribute("data-author") || "",
      url: row.getAttribute("data-url") || "",
      ts: Number(row.getAttribute("data-ts") || 0),
      maintainer: !!(titleNode && titleNode.classList.contains("is-maintainer"))
    };
  }

  function storyDocFromEl(node) {
    var kind = node.getAttribute("data-story") === "issue" ? "issue" : "pr";
    var number = node.getAttribute("data-number") || "";
    var title = node.getAttribute("title") || "";
    title = title.replace(/^#\d+\s*/, "");
    return {
      kind: kind,
      number: number,
      title: title,
      lane: node.classList.contains("p-green") ? "pr" : "merged",
      author: "",
      url: node.getAttribute("data-gh") || "",
      ts: 0,
      maintainer: false
    };
  }

  function fmtWhen(value) {
    if (!value) return "";
    var t = Date.parse(String(value));
    return Number.isNaN(t) ? String(value) : absLocal(t);
  }

  function storyInfoGrid(item, doc) {
    var who = ((item.user || {}).login) || doc.author || "";
    var mergedAt = item.merged_at || (item.pull_request && item.pull_request.merged_at) || "";
    var state = String(item.state || "").toLowerCase();
    if (mergedAt || doc.lane === "merged") state = "merged";
    if (item.draft) state = "draft";
    var badgeCls = state === "merged" ? "b-merged" : state === "closed" ? "b-closed" : "b-open";
    var labels = Array.isArray(item.labels) ? item.labels.map(function (l) {
      return typeof l === "string" ? l : (l && l.name) || "";
    }).filter(Boolean) : [];
    var pairs = [
      ["number", "#" + (item.number || doc.number || "")],
      ["kind", doc.kind === "issue" ? "issue" : "pull request"],
      ["author", who],
      ["state", '<span class="disc-badge ' + badgeCls + '">' + escapeHtml(state || "open") + "</span>"],
      ["opened", fmtWhen(item.created_at)],
      ["updated", fmtWhen(item.updated_at)]
    ];
    if (state === "merged") pairs.push(["merged", fmtWhen(mergedAt) || "—"]);
    if (item.comments != null) pairs.push(["comments", String(item.comments)]);
    if (labels.length) pairs.push(["labels", escapeHtml(labels.slice(0, 6).join(", "))]);
    return '<dl class="disc-info">' + pairs.map(function (pair) {
      return '<div class="disc-kv"><dt>' + escapeHtml(pair[0]) + "</dt><dd>" +
        (pair[0] === "state" ? pair[1] : escapeHtml(pair[1])) + "</dd></div>";
    }).join("") + "</dl>";
  }

  function storyActions(item, doc, kind, number) {
    var gh = item.html_url || doc.url || "#";
    return '<div class="disc-actions">' +
      '<a class="primary" href="' + escapeHtml(gh) + '" target="_blank" rel="noopener">Open on GitHub ↗</a>' +
      '<a href="#forum?kind=' + encodeURIComponent(kind) + "&number=" + encodeURIComponent(number) +
      '" data-forum-thread="' + encodeURIComponent(kind + ":" + number) + '">Discuss in the forum →</a>' +
      "</div>";
  }

  function openStory(doc, opener) {
    if (!doc || !doc.number) return;
    var news = document.getElementById("news");
    var disc = document.getElementById("hn-discussion");
    var scroll = document.getElementById("hn-scroll");
    var head = document.querySelector("#news .hn-head");
    if (!news || !disc) return;
    if (viewFromHash() !== "dashboard") showView("dashboard", false);
    var token = ++discToken;
    var kind = doc.kind === "issue" ? "issue" : "pr";
    var number = doc.number;
    history.replaceState(null, "", location.pathname + location.search + "#story/" + kind + "/" + number);
    if (scroll) scroll.hidden = true;
    if (head) head.hidden = true;
    var tail = document.getElementById("dash-tail");
    if (tail) tail.hidden = true;
    disc.hidden = false;
    disc.innerHTML = '<div class="disc"><button type="button" class="disc-back">← back to the feed</button>' +
      '<p class="disc-kicker">' + (kind === "issue" ? "issue" : "pull request") + "</p>" +
      '<h2 class="disc-title' + (doc.maintainer ? " is-maintainer" : "") + '">' + escapeHtml(doc.title || ("#" + number)) + "</h2>" +
      '<p class="disc-num">loading #' + escapeHtml(number) + "…</p></div>";
    disc.scrollIntoView && disc.scrollIntoView({ block: "nearest" });
    fetch("/api/github?kind=" + encodeURIComponent(kind) + "&number=" + encodeURIComponent(number), { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error(String(response.status));
        return response.json();
      })
      .then(function (payload) {
        if (token !== discToken) return;
        var item = (payload && payload.item) || {};
        var comments = Array.isArray(payload && payload.comments) ? payload.comments : [];
        var who = ((item.user || {}).login) || doc.author || "";
        var maintainer = doc.maintainer || who === (DATA.maintainer || "");
        var commentHtml = comments.map(function (comment) {
          var login = ((comment.user || {}).login) || "";
          var mark = login && login === (DATA.maintainer || "") ? " is-maintainer" : "";
          return '<article class="disc-comment"><p class="disc-by"><span class="' + mark.trim() + '">' +
            escapeHtml(login) + "</span> " + escapeHtml(fmtWhen(comment.created_at)) + '</p><div class="disc-text">' +
            renderBody(comment.body || "", comment.body_html) + "</div></article>";
        }).join("");
        if (!commentHtml) commentHtml = '<p class="hn-meta">No comments yet.</p>';
        if (payload && payload.truncated) commentHtml += '<p class="hn-meta">Showing the latest comments. Older ones are on GitHub.</p>';
        disc.innerHTML = '<div class="disc"><button type="button" class="disc-back">← back to the feed</button>' +
          '<p class="disc-kicker">' + (kind === "issue" ? "issue" : "pull request") + "</p>" +
          '<h2 class="disc-title' + (maintainer ? " is-maintainer" : "") + '">' +
          escapeHtml(item.title || doc.title || ("#" + number)) + "</h2>" +
          storyInfoGrid(item, doc) +
          storyActions(item, doc, kind, number) +
          '<div class="disc-body">' + renderBody(item.body || "", item.body_html) + "</div>" +
          "<h3>discussion</h3>" + commentHtml + "</div>";
      }).catch(function () {
        if (token !== discToken) return;
        disc.innerHTML = '<div class="disc"><button type="button" class="disc-back">← back to the feed</button>' +
          '<p class="disc-kicker">' + (kind === "issue" ? "issue" : "pull request") + "</p>" +
          '<h2 class="disc-title' + (doc.maintainer ? " is-maintainer" : "") + '">' +
          escapeHtml(doc.title || ("#" + number)) + "</h2>" +
          storyInfoGrid({}, doc) +
          '<p class="hn-meta">GitHub details are unavailable right now — the page above is the local snapshot.</p>' +
          '<div class="disc-actions"><a class="primary" href="' + escapeHtml(doc.url || "#") +
          '" target="_blank" rel="noopener">Open on GitHub ↗</a></div>' +
          "</div>";
      });
  }

  function openDiscussion(row) {
    if (!row) return;
    openStory(storyDocFromRow(row));
  }

  function forumBox(kind, number) {
    return '<section class="forum" data-kind="' + kind + '" data-number="' + number + '">' +
      "<h3>forum</h3><div class=\"forum-list\"></div>" +
      '<div class="forum-auth"></div>' +
      '<form class="forum-form" hidden><input class="hp" name="company" tabindex="-1" autocomplete="off" aria-hidden="true">' +
      '<textarea class="forum-text" name="text" maxlength="1000" required placeholder="comment"></textarea>' +
      '<button type="submit">add comment</button><p class="forum-note hn-meta"></p></form></section>';
  }

  function renderForumComments(list, comments) {
    if (!comments.length) {
      list.innerHTML = '<p class="hn-meta">No forum comments yet.</p>';
      return;
    }
    list.innerHTML = comments.map(function (comment) {
      return '<article class="disc-comment"><p class="disc-by">' + escapeHtml(comment.name) + " " +
        escapeHtml(comment.created || "") + '</p><div class="disc-text">' +
        renderMarkdown(comment.text || "") + "</div></article>";
    }).join("");
  }

  function mountGoogle(el, clientId, onSignedIn) {
    function draw() {
      if (!window.google || !google.accounts || !google.accounts.id) {
        setTimeout(draw, 200);
        return;
      }
      google.accounts.id.initialize({
        client_id: clientId,
        callback: function (response) {
          fetch("/api/auth", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ credential: response.credential })
          }).then(function (res) {
            if (!res.ok) throw new Error("signin");
            return res.json();
          }).then(function () { onSignedIn(); }).catch(function () {
            el.insertAdjacentHTML("beforeend", '<p class="hn-meta">Google sign-in failed.</p>');
          });
        }
      });
      el.innerHTML = "";
      google.accounts.id.renderButton(el, {
        theme: "filled_black",
        size: "medium",
        text: "signin_with",
        shape: "rectangular"
      });
    }
    draw();
  }

  function paintForumAuth(section, session, reload) {
    var auth = section.querySelector(".forum-auth");
    var form = section.querySelector(".forum-form");
    if (!session || !session.user) {
      form.hidden = true;
      if (!session || !session.clientId) {
        auth.innerHTML = '<p class="hn-meta">Google sign-in is not configured yet.</p>';
        return;
      }
      auth.innerHTML = "";
      var button = document.createElement("div");
      auth.appendChild(button);
      mountGoogle(button, session.clientId, reload);
      return;
    }
    auth.innerHTML = '<p class="forum-who">Signed in as ' + escapeHtml(session.user.name) +
      ' <button type="button" class="forum-out">sign out</button></p>';
    form.hidden = false;
    auth.querySelector(".forum-out").addEventListener("click", function () {
      fetch("/api/auth", { method: "DELETE" }).then(reload);
    });
  }

  function loadForum(disc, kind, number) {
    var section = disc.querySelector(".forum");
    if (!section) return;
    var list = section.querySelector(".forum-list");
    var form = section.querySelector(".forum-form");
    var note = section.querySelector(".forum-note");
    function reload() { loadForum(disc, kind, number); }
    fetch("/api/auth", { cache: "no-store" })
      .then(function (response) { return response.json(); })
      .then(function (session) { paintForumAuth(section, session, reload); })
      .catch(function () { paintForumAuth(section, null, reload); });
    fetch("/api/forum?kind=" + encodeURIComponent(kind) + "&number=" + encodeURIComponent(number), { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("load");
        return response.json();
      })
      .then(function (payload) {
        form.dataset.token = payload.token || "";
        form.dataset.ready = String(Date.now());
        renderForumComments(list, payload.comments || []);
      })
      .catch(function () {
        list.innerHTML = '<p class="hn-meta">Forum is unavailable.</p>';
      });
    if (form.dataset.bound) return;
    form.dataset.bound = "1";
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var waited = Date.now() - Number(form.dataset.ready || 0);
      if (waited < 4000) {
        note.textContent = "Read it for a moment, then comment.";
        return;
      }
      var text = form.querySelector(".forum-text").value;
      var company = form.querySelector(".hp").value;
      note.textContent = "";
      fetch("/api/forum", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: kind,
          number: number,
          text: text,
          company: company,
          token: form.dataset.token || ""
        })
      }).then(function (response) {
        return response.json().then(function (payload) {
          return { ok: response.ok, status: response.status, payload: payload };
        });
      }).then(function (result) {
        if (!result.ok) {
          note.textContent = (result.payload && result.payload.error) || "Could not post.";
          return;
        }
        form.querySelector(".forum-text").value = "";
        return fetch("/api/forum?kind=" + encodeURIComponent(kind) + "&number=" + encodeURIComponent(number), { cache: "no-store" })
          .then(function (response) { return response.json(); })
          .then(function (payload) {
            form.dataset.token = payload.token || form.dataset.token;
            renderForumComments(list, payload.comments || []);
          });
      }).catch(function () {
        note.textContent = "Could not post.";
      });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
