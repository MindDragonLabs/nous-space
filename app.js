(function () {
  "use strict";

  var VIEWS = ["dashboard", "issues", "prs", "contributors", "search", "info"];
  var RELOAD_MS = 5 * 60 * 1000;
  var DATA = {};
  var built = Object.create(null);

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
      btn.classList.toggle("active", normalizeView(btn.getAttribute("data-view")) === view);
    });
    var titles = {
      dashboard: "NOUS SPACE — Hermes Agent Maintainer Dashboard",
      issues: "Issues — Nous Space",
      prs: "Pull requests — Nous Space",
      contributors: "Contributors — Nous Space",
      search: "Search the Hermes ecosystem — Nous Space",
      info: "About this dashboard — Nous Space"
    };
    var descriptions = {
      dashboard: "Live Hermes Agent dashboard: maintainer merge lane, open issues, pull request queues, contributors, and ecosystem search.",
      issues: "Search the most recently updated open issues in NousResearch/hermes-agent.",
      prs: "Review queues for the most recently updated open Hermes Agent pull requests.",
      contributors: "Hermes Agent contributors ranked by commits, with this week and recent reviews.",
      search: "Search Nous Research Hermes repositories, issues, pull requests, releases, and people.",
      info: "How the Nous Space green and blue strips are scoped, and when the page refreshes."
    };
    document.title = titles[view] || titles.dashboard;
    var desc = document.getElementById("meta-desc");
    if (desc) desc.setAttribute("content", descriptions[view] || descriptions.dashboard);
    ensureRendered(view);
  }

  function ensureRendered(view) {
    if (view === "dashboard" || built[view]) return;
    var panel = viewPanel(view);
    if (!panel) return;
    if (!panel.querySelector(".tab-page")) {
      if (view === "issues") renderIssues(panel);
      else if (view === "prs") renderPrs(panel);
      else if (view === "contributors") renderContribs(panel);
      else if (view === "search") renderSearch(panel);
      else if (view === "info") renderInfo(panel);
    }
    built[view] = true;
  }

  function chip(label, on) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip" + (on ? " is-on" : "");
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
    article.appendChild(link);
    return { article: article, link: link };
  }

  function commentText(value) {
    var n = Number(value) || 0;
    return n === 1 ? "1 comment" : n + " comments";
  }

  function issueHit(doc, query) {
    var hit = linkedHit(doc);
    if (doc.number != null && doc.number !== "") addText(hit.link, "#" + doc.number);
    var title = document.createElement("span");
    title.innerHTML = highlight(doc.title || "", query);
    hit.link.appendChild(title);
    var labels = Array.isArray(doc.displayLabels) ? doc.displayLabels : [];
    labels.forEach(function (name) { addText(hit.link, name); });
    addText(hit.link, doc.author);
    addText(hit.link, doc.ago);
    addText(hit.link, commentText(doc.comments));
    return hit.article;
  }

  function statusWord(doc) {
    if (doc.queue === "needs-review") return "Needs review";
    if (doc.queue === "approved") return "Approved";
    if (doc.queue === "changes") return "Changes";
    if (doc.queue === "draft" || doc.draft === true) return "Draft";
    return doc.state || "open";
  }

  function prHit(doc, query) {
    var hit = linkedHit(doc);
    if (doc.number != null && doc.number !== "") addText(hit.link, "#" + doc.number);
    var title = document.createElement("span");
    title.innerHTML = highlight(doc.title || "", query);
    hit.link.appendChild(title);
    addText(hit.link, statusWord(doc));
    var ciOk = doc.ci_ok == null ? 0 : doc.ci_ok;
    var ciTotal = doc.ci_total == null ? 0 : doc.ci_total;
    addText(hit.link, ciOk + "/" + ciTotal + (doc.ci ? " " + doc.ci : ""));
    var diff = document.createElement("span");
    var added = document.createElement("span");
    added.className = "add";
    added.textContent = "+" + (Number(doc.additions) || 0);
    var removed = document.createElement("span");
    removed.className = "del";
    removed.textContent = "-" + (Number(doc.deletions) || 0);
    diff.append(added, document.createTextNode(" "), removed);
    hit.link.appendChild(diff);
    addText(hit.link, doc.author);
    addText(hit.link, doc.ago);
    return hit.article;
  }

  function avatarUrl(url) {
    var value = String(url || "");
    if (!value) return "";
    return value.indexOf("?") === -1 ? value + "?s=64" : value + "&s=64";
  }

  function contribHit(doc, rank, max) {
    var hit = linkedHit(doc);
    addText(hit.link, String(rank));
    var src = avatarUrl(doc.avatar_url);
    if (src) {
      var img = document.createElement("img");
      img.alt = "";
      img.src = src;
      hit.link.appendChild(img);
    }
    addText(hit.link, doc.login || doc.title || "");
    var meter = el("span", "contrib-meter");
    var pct = Math.round(((Number(doc.contributions) || 0) / max) * 100);
    meter.style.setProperty("--w", pct + "%");
    meter.appendChild(document.createElement("span"));
    hit.link.appendChild(meter);
    addText(hit.link, String(Number(doc.contributions) || 0));
    addText(hit.link, (Number(doc.week_commits) || 0) + " this week");
    addText(hit.link, (Number(doc.reviews) || 0) + " reviews");
    if (doc.new === true) {
      var badge = el("span", "contrib-new");
      badge.textContent = "new";
      hit.link.appendChild(badge);
    }
    return hit.article;
  }

  function searchHit(doc, query) {
    var hit = linkedHit(doc);
    addText(hit.link, doc.kind);
    addText(hit.link, doc.repo);
    var title = document.createElement("span");
    title.innerHTML = highlight(doc.title || "", query);
    hit.link.appendChild(title);
    addText(hit.link, doc.author);
    addText(hit.link, doc.ago || doc.updated_at || "");
    return hit.article;
  }

  function renderIssues(panel) {
    var items = asList(DATA.issues);
    var page = el("div", "tab-page");
    var heading = el("h2");
    heading.textContent = "Issues";
    var counts = el("p");
    counts.textContent = formatCount(countOf(DATA.issues, "total_open")) + " open / " +
      formatCount(countOf(DATA.issues, "total_closed")) + " closed";
    var note = el("p", "tab-note");
    note.textContent = "searching the " + scannedCount(DATA.issues, items) + " most recently updated open issues";
    var input = document.createElement("input");
    input.id = "issue-q";
    input.type = "search";
    input.placeholder = "Search issues";
    var filters = el("div");
    filters.setAttribute("data-chip-group", "filter");
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
    sorts.setAttribute("data-chip-group", "sort");
    [["Newest", "newest"], ["Oldest", "oldest"], ["Most commented", "comments"]].forEach(function (spec, index) {
      var btn = chip(spec[0], index === 0);
      btn.setAttribute("data-sort", spec[1]);
      sorts.appendChild(btn);
    });
    var list = el("div", "hit-list");
    list.id = "issue-hits";
    page.append(heading, counts, note, input, filters, sorts, list);
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
    var counts = el("p");
    counts.textContent = formatCount(countOf(DATA.pull_requests, "total_open")) + " open · " +
      formatCount(countOf(DATA.pull_requests, "total_closed")) + " closed";
    var note = el("p", "tab-note");
    note.textContent = "queues from the " + scannedCount(DATA.pull_requests, items) +
      " most recently updated open pull requests";
    var input = document.createElement("input");
    input.id = "pr-q";
    input.type = "search";
    input.placeholder = "Search pull requests";
    var queues = { all: items.length, "needs-review": 0, approved: 0, changes: 0, draft: 0 };
    items.forEach(function (pr) {
      if (queues[pr.queue] != null) queues[pr.queue] += 1;
    });
    var filters = el("div");
    filters.setAttribute("data-chip-group", "queue");
    [
      ["All", "all"],
      ["Needs review", "needs-review"],
      ["Approved", "approved"],
      ["Changes", "changes"],
      ["Draft", "draft"],
    ].forEach(function (spec, index) {
      var btn = chip(spec[0] + " " + queues[spec[1]], index === 0);
      btn.setAttribute("data-queue", spec[1]);
      filters.appendChild(btn);
    });
    var list = el("div", "hit-list");
    list.id = "pr-hits";
    page.append(heading, counts, note, input, filters, list);
    panel.appendChild(page);
    input.addEventListener("input", paintPrs);
    paintPrs();
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
    var input = document.createElement("input");
    input.id = "contrib-q";
    input.type = "search";
    input.placeholder = "Search contributors";
    var filters = el("div");
    filters.setAttribute("data-chip-group", "filter");
    var all = chip("All", true);
    all.setAttribute("data-filter", "all");
    var newer = chip("New", false);
    newer.setAttribute("data-filter", "new");
    filters.append(all, newer);
    var list = el("div", "hit-list");
    list.id = "contrib-hits";
    page.append(heading, input, filters, list);
    panel.appendChild(page);
    input.addEventListener("input", paintContribs);
    paintContribs();
  }

  function paintContribs() {
    var list = document.getElementById("contrib-hits");
    var input = document.getElementById("contrib-q");
    var api = window.NousSearch;
    if (!list || !input || !api) return;
    var filterBtn = selected("contributors", "filter");
    var onlyNew = filterBtn && filterBtn.getAttribute("data-filter") === "new";
    var rows = people().filter(function (person) { return !onlyNew || person.new === true; });
    var shown;
    if (queryIsBlank(input.value)) {
      shown = rows.slice().sort(function (a, b) {
        return (Number(b.contributions) || 0) - (Number(a.contributions) || 0);
      });
    } else {
      var docs = rows.map(contribDoc);
      shown = api.searchDocs(docs, input.value, docs.length).hits.map(function (hit) { return hit.doc; });
    }
    var max = 0;
    shown.forEach(function (row) {
      var n = Number(row.contributions) || 0;
      if (n > max) max = n;
    });
    if (!max) max = 1;
    list.replaceChildren.apply(list, shown.map(function (doc, index) {
      return contribHit(doc, index + 1, max);
    }));
  }

  function ecosystemDocs() {
    var docs = [];
    var seen = new Set();
    function push(doc) {
      if (!doc || typeof doc !== "object") return;
      var url = doc.url ? String(doc.url) : "";
      if (url) {
        if (seen.has(url)) return;
        seen.add(url);
      }
      docs.push(doc);
    }
    (Array.isArray(DATA.ecosystem) ? DATA.ecosystem : []).forEach(function (item) {
      push(Object.assign({}, item, { ts: toTs(item.ts != null && item.ts !== "" ? item.ts : item.updated_at) }));
    });
    people().forEach(function (person) { push(contribDoc(person)); });
    asList(DATA.issues).forEach(function (issue) { push(issueDoc(issue)); });
    asList(DATA.pull_requests).forEach(function (pr) { push(prDoc(pr)); });
    return docs;
  }

  function renderSearch(panel) {
    var page = el("div", "tab-page");
    var heading = el("h2");
    heading.textContent = "Search";
    var input = document.createElement("input");
    input.id = "search-q";
    input.type = "search";
    input.placeholder = "Search the Hermes ecosystem";
    var eco = document.getElementById("eco-q");
    if (eco) input.value = eco.value;
    var meta = el("p", "result-meta");
    meta.id = "search-meta";
    var list = el("div", "hit-list");
    list.id = "search-hits";
    page.append(heading, input, meta, list);
    panel.appendChild(page);
    input.addEventListener("input", function () {
      var ecoInput = document.getElementById("eco-q");
      if (ecoInput && ecoInput.value !== input.value) ecoInput.value = input.value;
      paintSearch();
    });
    paintSearch();
  }

  function paintSearch() {
    var input = document.getElementById("search-q");
    var list = document.getElementById("search-hits");
    var meta = document.getElementById("search-meta");
    var api = window.NousSearch;
    if (!input || !list || !meta || !api) return;
    if (queryIsBlank(input.value)) {
      meta.textContent = "Search repos, issues, pull requests, discussions, releases, and people across Nous Research Hermes.";
      list.replaceChildren();
      return;
    }
    var found = api.searchDocs(ecosystemDocs(), input.value, 40);
    meta.textContent = found.total + (found.total === 1 ? " match" : " matches");
    list.replaceChildren.apply(list, found.hits.map(function (hit) { return searchHit(hit.doc, input.value); }));
  }

  function renderInfo(panel) {
    var page = el("div", "tab-page");
    var heading = el("h2");
    heading.textContent = "Info";
    var green = el("p");
    green.textContent = "The green strip shows open pull requests the maintainer is involved in, ranked by merge likelihood.";
    var blue = el("p");
    blue.textContent = "The blue strip shows pull requests merged to main by or authored by the maintainer.";
    var linkRow = el("p");
    var repoUrl = DATA.repo_url || (DATA.repo ? "https://github.com/" + DATA.repo : "");
    if (repoUrl) {
      var link = document.createElement("a");
      link.href = repoUrl;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = DATA.repo || repoUrl;
      linkRow.appendChild(link);
    }
    var stamp = el("p");
    stamp.id = "freshness-detail";
    stamp.textContent = DATA.generated ? String(DATA.generated) : "";
    var refresh = el("p");
    refresh.textContent = "refreshes every 5 minutes";
    page.append(heading, green, blue, linkRow, stamp, refresh);
    panel.appendChild(page);
  }

  function bindEco() {
    var form = document.getElementById("eco-search");
    var eco = document.getElementById("eco-q");
    if (eco) {
      eco.addEventListener("input", function () {
        var search = document.getElementById("search-q");
        if (search && search.value !== eco.value) search.value = eco.value;
        if (viewFromHash() === "search") paintSearch();
      });
    }
    if (!form) return;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var ecoInput = document.getElementById("eco-q");
      var value = ecoInput ? ecoInput.value : "";
      showView("search", false);
      var search = document.getElementById("search-q");
      if (search && search.value !== value) search.value = value;
      paintSearch();
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
    var delta = Date.now() - t;
    var min = delta <= 0 ? 0 : Math.floor(delta / 60000);
    node.textContent = "updated " + min + "m ago";
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

  function boot() {
    DATA = loadData();
    document.addEventListener("click", function (event) {
      var nav = event.target.closest("[data-view]");
      if (nav) {
        event.preventDefault();
        showView(nav.getAttribute("data-view") || "dashboard", false);
        return;
      }
      if (event.target.closest(".hn-title")) {
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
      group.querySelectorAll("button.chip").forEach(function (node) { node.classList.remove("is-on"); });
      button.classList.add("is-on");
      var view = viewFromHash();
      if (view === "issues") paintIssues();
      else if (view === "prs") paintPrs();
      else if (view === "contributors") paintContribs();
    });
    window.addEventListener("hashchange", function () { showView(viewFromHash(), true); });
    bindEco();
    paintFreshness();
    setInterval(paintFreshness, 30000);
    syncNavHeight();
    window.addEventListener("resize", syncNavHeight);
    scheduleReload();
    showView(viewFromHash(), true);
    bindNews();
    var storyMatch = String(location.hash || "").match(/^#story\/(pr|issue)\/(\d+)$/);
    if (storyMatch) {
      var storyRow = document.querySelector(
        '#hn-scroll .hn-row[data-kind="' + storyMatch[1] + '"][data-number="' + storyMatch[2] + '"]'
      );
      if (storyRow) openDiscussion(storyRow);
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

  function bindNews() {
    rememberNews();
    setInterval(function () {
      var disc = document.getElementById("hn-discussion");
      if (disc && !disc.hidden) return;
      fetch("/news.json?t=" + Date.now(), { cache: "no-store" }).then(function (response) {
        if (!response.ok) return null;
        return response.json();
      }).then(function (payload) {
        if (!payload || !Array.isArray(payload.items) || !payload.items.length) return;
        if (payload.generated) {
          DATA.generated = payload.generated;
          paintFreshness();
        }
        var newest = payload.items[0];
        var key = (newest.kind === "issue" ? "issue" : "pr") + ":" + newest.number;
        if (seenNews[key] && payload.items.length === document.querySelectorAll("#hn-scroll .hn-row").length) return;
        paintNews(payload.items);
      }).catch(function () {});
    }, 45000);
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

  function openDiscussion(row) {
    if (!row) return;
    var news = document.getElementById("news");
    var disc = document.getElementById("hn-discussion");
    var scroll = document.getElementById("hn-scroll");
    var head = document.querySelector("#news .hn-head");
    if (!news || !disc) return;
    var token = ++discToken;
    var kind = row.getAttribute("data-kind") === "issue" ? "issue" : "pr";
    var number = row.getAttribute("data-number");
    history.replaceState(null, "", location.pathname + location.search + "#story/" + kind + "/" + number);
    var repo = news.getAttribute("data-repo") || "NousResearch/hermes-agent";
    var title = row.querySelector(".hn-title");
    var maintainer = title && title.classList.contains("is-maintainer");
    if (scroll) scroll.hidden = true;
    if (head) head.hidden = true;
    disc.hidden = false;
    disc.innerHTML = '<div class="disc"><button type="button" class="disc-back">← list</button><p class="disc-num">loading #' +
      escapeHtml(number) + "</p></div>";
    fetch("/api/github?kind=" + encodeURIComponent(kind) + "&number=" + encodeURIComponent(number), { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error(String(response.status));
        return response.json();
      })
      .then(function (payload) {
      if (token !== discToken) return;
      var item = (payload && payload.item) || {};
      var comments = Array.isArray(payload && payload.comments) ? payload.comments : [];
      var who = ((item.user || {}).login) || "";
      var blue = maintainer || who === (DATA.maintainer || "") ? " is-maintainer" : "";
      var commentHtml = comments.map(function (comment) {
        var login = ((comment.user || {}).login) || "";
        var mark = login && login === (DATA.maintainer || "") ? " is-maintainer" : "";
        return '<article class="disc-comment"><p class="disc-by"><span class="' + mark.trim() + '">' +
          escapeHtml(login) + "</span> " + escapeHtml(comment.created_at || "") + "</p><div class=\"disc-text\">" +
          renderBody(comment.body || "", comment.body_html) + "</div></article>";
      }).join("");
      if (!commentHtml) commentHtml = '<p class="hn-meta">No comments yet.</p>';
      if (payload && payload.truncated) commentHtml += '<p class="hn-meta">Showing the latest comments. Older ones are on GitHub.</p>';
      disc.innerHTML = '<div class="disc"><button type="button" class="disc-back">← list</button>' +
        '<h2 class="disc-title' + blue + '">' + escapeHtml(item.title || (title ? title.textContent : "")) + "</h2>" +
        '<p class="disc-num">#' + escapeHtml(String(item.number || number)) + " · " + escapeHtml(who) + "</p>" +
        '<div class="disc-body">' + renderBody(item.body || "", item.body_html) + "</div>" +
        "<h3>discussion</h3>" + commentHtml +
        '<p class="hn-meta"><a href="' + escapeHtml(item.html_url || row.getAttribute("data-url") || "#") +
        '" target="_blank" rel="noopener">Open on GitHub</a></p>' +
        forumBox(kind, number) + "</div>";
      loadForum(disc, kind, number);
    }).catch(function () {
      if (token !== discToken) return;
      disc.innerHTML = '<div class="disc"><button type="button" class="disc-back">← list</button>' +
        '<h2 class="disc-title' + (maintainer ? " is-maintainer" : "") + '">' +
        escapeHtml(title ? title.textContent : "") + "</h2>" +
        '<p class="disc-num">#' + escapeHtml(number) + "</p>" +
        '<p class="hn-meta">GitHub details are unavailable right now.</p>' +
        forumBox(kind, number) + "</div>";
      loadForum(disc, kind, number);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
