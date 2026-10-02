/* jsdom smoke test for the nous-space antislop run.
   Loads the built index.html + real app.js, mocks fetch, then clicks. */
const fs = require("fs");
const path = require("path");
let JSDOM;
try { ({ JSDOM } = require("jsdom")); }
catch (e) { ({ JSDOM } = require("/Users/jefferson/casax/repos/casa-frontend/node_modules/jsdom")); }

const ROOT = "/Users/jefferson/nous-space";
const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
const appjs = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");

const dom = new JSDOM(html, {
  url: "http://127.0.0.1:8791/",
  runScripts: "outside-only",
  pretendToBeVisual: true,
});
const { window } = dom;
const { document } = window;

// ── stubs ──────────────────────────────────────────────────────────────────
window.IntersectionObserver = class {
  constructor(cb) { this.cb = cb; }
  observe() {}
  disconnect() {}
};
window.scrollTo = () => {};
window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {} }));

const readJSON = (rel) => JSON.parse(fs.readFileSync(path.join(ROOT, rel), "utf8"));
window.fetch = (url) => {
  const u = String(url);
  const ok = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body), text: () => Promise.resolve(typeof body === "string" ? body : JSON.stringify(body)) });
  if (u.includes("/api/github")) {
    return ok({
      item: {
        number: 131272,
        title: "TEST PR TITLE — Supermemory migrates",
        user: { login: "teknium1" },
        state: "closed",
        merged_at: "2026-10-02T10:00:00Z",
        created_at: "2026-10-01T10:00:00Z",
        updated_at: "2026-10-02T10:00:00Z",
        body: "hello body",
        html_url: "https://github.com/NousResearch/hermes-agent/pull/131272",
        comments: 2,
        labels: [{ name: "bug" }],
      },
      comments: [],
    });
  }
  if (u.includes("news-head.json")) return ok(readJSON("data/news-head.json"));
  if (u.includes("archive6.json")) return ok(readJSON("data/archive6.json"));
  if (u.includes("catalog.json")) return ok(readJSON("data/catalog.json"));
  if (u.includes("/api/auth")) return ok({ user: null, clientId: "" });
  if (u.includes("/api/forum")) return ok({ comments: [], token: "t" });
  if (u.includes("arch-") && u.endsWith(".svg")) {
    return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(fs.readFileSync(path.join(ROOT, u.replace(/^\//, "")), "utf8")) });
  }
  return ok({});
};
window.NousSearch = {
  searchDocs: (docs) => ({ hits: docs.map((d) => ({ doc: d })) }),
  parseQuery: () => ({ tokens: [], fields: {} }),
};

// ── run the real app.js ────────────────────────────────────────────────────
window.eval(appjs);

const results = [];
function check(name, cond, extra) {
  results.push({ name, pass: !!cond, extra: extra || "" });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  await sleep(80);

  // 1. freshness: explicit date + timezone, never bare 4-digit minutes
  const fresh = document.getElementById("freshness");
  check("top bar freshness explicit", fresh && /updated .+,.+\d{1,2}:\d{2}/.test(fresh.textContent), fresh ? fresh.textContent : "missing");
  check("no '1241m ago' style", fresh && !/\d{3,}m ago/.test(fresh.textContent), fresh ? fresh.textContent : "");
  check("freshness has tz or UTC hint", fresh && (/\d{4} UTC/.test(fresh.title) || /UTC/.test(fresh.title)), fresh ? fresh.title : "");

  // 2. feed heading
  const feedH = document.querySelector("#news .hn-head h2");
  check("feed titled 'Recent commits to main'", feedH && feedH.textContent === "Recent commits to main", feedH && feedH.textContent);

  // 3. story links on blocks
  const storyLink = document.querySelector("a[data-story]");
  check("block links carry data-story", !!storyLink);

  // 4. click a block -> PR page (story) with the PR title, not "New"
  storyLink.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
  await sleep(60);
  const disc = document.getElementById("hn-discussion");
  const storyTitle = disc.querySelector(".disc-title");
  check("story open after block click", disc && !disc.hidden);
  check("story heading is the PR title", storyTitle && storyTitle.textContent.indexOf("TEST PR TITLE") !== -1, storyTitle && storyTitle.textContent);
  check("no 'New' above the story", !document.querySelector("#news .hn-head:not([hidden])") || document.querySelector("#news .hn-head").hidden);
  check("info grid rendered", !!disc.querySelector(".disc-info"));
  check("info grid has author", disc.querySelector(".disc-info") && disc.querySelector(".disc-info").textContent.indexOf("teknium1") !== -1);
  check("actions: GitHub + forum links", !!disc.querySelector(".disc-actions a.primary") && !!disc.querySelector(".disc-actions a[href^='#forum']"));
  check("dash-tail hidden while PR page open", document.getElementById("dash-tail").hidden);

  // 5. back button restores
  disc.querySelector(".disc-back").dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
  await sleep(20);
  check("back closes the PR page", disc.hidden && !document.getElementById("dash-tail").hidden);

  // 6. brand reset
  document.querySelector("a.brand#brand-home").dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
  await sleep(20);
  check("brand click resets view", document.querySelector('[data-view-panel="dashboard"]').hidden === false);

  // 7. feed row (PR number) opens the story too
  const row = document.querySelector("#hn-scroll .hn-row");
  if (row) {
    row.querySelector(".hn-num").dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
    await sleep(60);
    check("PR number click opens PR page", !document.getElementById("hn-discussion").hidden);
    document.querySelector(".disc-back").dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
    await sleep(10);
  }

  // 8. PRs page: queues + archive with sorts
  window.location.hash = "#prs";
  window.dispatchEvent(new window.Event("hashchange"));
  await sleep(60);
  const prsPanel = document.querySelector('[data-view-panel="prs"]');
  check("prs panel visible", !prsPanel.hidden);
  check("queue cards rendered", prsPanel.querySelectorAll(".queue-card").length >= 4);
  check("archive lives on PRs page", !!prsPanel.querySelector("#prarchive"));
  await sleep(60);
  const archSort = prsPanel.querySelector('[data-arch-sort="discussed"]');
  check("archive sort chips present", !!archSort && !!prsPanel.querySelector('[data-arch-sort="oldest"]'));
  const archList = document.getElementById("prarch-list");
  check("archive rows painted", archList && archList.querySelectorAll(".prs-row").length > 0, archList ? archList.querySelectorAll(".prs-row").length + " rows" : "none");

  // sort by discussed -> first row comments >= second row comments (or single row)
  if (archSort) {
    archSort.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
    await sleep(30);
    check("sort chip toggles", archSort.classList.contains("is-on"));
  }

  // 9. forum view
  window.location.hash = "#forum";
  window.dispatchEvent(new window.Event("hashchange"));
  await sleep(60);
  const forumPanel = document.querySelector('[data-view-panel="forum"]');
  check("forum panel visible", !forumPanel.hidden);
  check("forum has general category", !!forumPanel.querySelector(".forum-cat.is-on") && forumPanel.querySelector(".forum-cat.is-on").textContent === "general");
  const threads = forumPanel.querySelectorAll(".forum-thread");
  check("forum threads listed (PRs + issues)", threads.length > 0, threads.length + " threads");
  const kinds = [...threads].map((t) => t.getAttribute("data-kind"));
  check("forum covers both kinds", kinds.includes("pr") && kinds.includes("issue"), kinds.slice(0, 6).join(","));

  // 10. architecture view
  window.location.hash = "#arch";
  window.dispatchEvent(new window.Event("hashchange"));
  await sleep(60);
  const archPanel = document.querySelector('[data-view-panel="arch"]');
  check("arch panel visible", !archPanel.hidden);
  const versions = archPanel.querySelectorAll(".arch-version");
  check("per-release buttons present", versions.length >= 15, versions.length + " buttons");
  check("current diagram inline", !!archPanel.querySelector('[data-arch-svg="0"] svg'));
  const second = archPanel.querySelector('[data-arch="2"]');
  if (second) {
    second.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
    await sleep(60);
    check("release diagram lazy-loads", !!archPanel.querySelector('[data-arch-svg="2"] svg'));
  }

  // 11. docs page: curl builder + example + inquiry
  window.location.hash = "#docs";
  window.dispatchEvent(new window.Event("hashchange"));
  await sleep(60);
  const docsPanel = document.querySelector('[data-view-panel="docs"]');
  check("docs visible", !docsPanel.hidden);
  check("curl builder present", !!document.getElementById("curl-builder"));
  check("worked example present", docsPanel.textContent.indexOf("worked example") !== -1);
  check("inquiry button to hello@xenovira.com", !!docsPanel.querySelector('a.inquire-btn[href^="mailto:hello@xenovira.com"]'));

  // 12. issue page
  window.location.hash = "#issues";
  window.dispatchEvent(new window.Event("hashchange"));
  await sleep(60);
  const issuesPanel = document.querySelector('[data-view-panel="issues"]');
  check("issues panel visible", !issuesPanel.hidden);
  check("issue queue cards", issuesPanel.querySelectorAll(".queue-card").length >= 3);
  check("issue hit cards", issuesPanel.querySelectorAll(".hit-list.carded .hit").length > 0, issuesPanel.querySelectorAll(".hit").length + " hits");

  // 13. contributors page: card grid
  window.location.hash = "#contributors";
  window.dispatchEvent(new window.Event("hashchange"));
  await sleep(60);
  const contribPanel = document.querySelector('[data-view-panel="contributors"]');
  check("contributors visible", !contribPanel.hidden);
  check("contributor cards (not a plain list)", contribPanel.querySelectorAll(".contrib-card").length > 0, contribPanel.querySelectorAll(".contrib-card").length + " cards");

  // ── report ───────────────────────────────────────────────────────────────
  let pass = 0, fail = 0;
  for (const r of results) {
    if (r.pass) pass++; else fail++;
    console.log((r.pass ? "PASS " : "FAIL ") + r.name + (r.extra ? "   [" + r.extra + "]" : ""));
  }
  console.log("\n" + pass + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
})().catch((e) => {
  console.error("SMOKE CRASH:", e);
  process.exit(2);
});
