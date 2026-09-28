# PLAN.md — Nous Space: API + Ecosystem Directory + Dual-Browsing + Paged PRs

Date: 2026-09-28
Author: nous-pr-bot, for Jefferson
Status: PROPOSED — awaiting go per-phase
Context: decisions locked 2026-09-27 (CF serving, free tier = attribution/no-commercial,
Phase 0 corpus gate). Backfill running (40k/91k PRs on disk, ~Oct 2 finish).
Vercel constraint in force: public site frozen at 21:37Z; deploy = human-initiated release only.

---

## What exists today (verified this session)

| Surface | State |
|---|---|
| Site views | Dashboard (block strip + panels), Issues, PRs, Contributors, Search, Info |
| `llms.txt` | Hand-written, lists the six views, points to itself as machine index |
| `search.js` | Client-side, GitHub search proxy via `api/github.js`, field prefixes `author:/label:/repo:/is:/kind:` + `#N` |
| `ecosystem` data | 126 entries in state.json — but kinds are repo/issue/pr/release. **No plugin/skill data at all** |
| Plugin catalog (upstream) | **338 YAML entries** in `hermes-agent/plugin-catalog/` — name, repo, exact SHA pin, description, maintainer, tier, category, docs_url, capabilities. Admission = human-merged PR + 40-char SHA. This is a curated, trusted list |
| Optional skills (upstream) | **152 SKILL.md** files across 24 categories (autonomous-ai-agents, devops, security, mlops, …) |
| API | 4 Vercel functions (auth/session/github/forum). **No public data API** |
| Backfill corpus | `merge_state/backfill/prs.jsonl` — 91k target, growing 20k/day, 2.4KB/PR |

Key realization: the "awesome plugins/apps/tools/skills" content **already exists upstream** —
338 plugins + 152 skills, both human-curated with trust models (SHA pins for plugins,
category trees for skills). We do not need to author a directory; we need to **ingest,
index, and serve** theirs, plus cross-link to our corpus of how those tools' host PRs
were reviewed.

---

## Idea discussion (what you asked, what I recommend)

### 1. "Build out the API interface while backfilling"

Agreed — the backfill is pure download; the API can be built in parallel and go live
against the 40k PRs already on disk. The API does not wait for 91k.

Decisions already locked: Cloudflare Workers + R2, CoinGecko-shape tiers, corpus-depth
gating. What changes with the backfill: the corpus is no longer 1,117 labels — it will
be **91k PR records + ~16.5k merged with labels**. That makes the *PR metadata* the free
tier (counts, statistics) and the *labeled judgment* the paid tiers, exactly per plan.

API surface (v1, read-only, public during build):

```
GET /api/v1/overview              — repo stats + lane counts (free, cached 5m)
GET /api/v1/prs?state=&page=      — paged PR metadata (free tier sees 30d history)
GET /api/v1/prs/{number}          — one PR (free)
GET /api/v1/corpus/stats          — label taxonomy rollups (free = counts only)
GET /api/v1/corpus/entries        — labeled entries (paid: labels + lessons)
GET /api/v1/corpus/entry/{pr}     — one labeled entry (paid)
GET /api/v1/ecosystem/plugins     — 338 catalog entries, searchable (free)
GET /api/v1/ecosystem/skills      — 152 skills, category tree (free)
GET /api/v1/search?q=             — unified search (free, rate-limited)
GET /api/v1/usage                 — CoinGecko ApiUsage shape
```

Auth: API key header (`x-nous-key`), issued per tier. Free tier = attribution required,
no commercial license (per locked decision #3).

### 2. "Tab around awesome plugins, apps, tools, skills — searchable"

Agreed, and the data is free: fetch the 338 plugin YAMLs + 152 SKILL.md files into
`state.json`-style artifacts at refresh time (filesystem reads, same pattern as the
quality bridge — no new auth, no deploy churn). Add two site views:

- **Ecosystem → Plugins**: card grid, filter by tier/category/capability, search box,
  each card links to repo + docs_url + our review-corpus entries mentioning it
- **Ecosystem → Skills**: category tree sidebar, 152 skills, search, each links to
  the SKILL.md path on GitHub

Cross-linking is our unique angle nobody else has: "plugin X's host repo had N PRs
reviewed; here are the reusable lessons." That is the monetizable join.

### 3. "Entire website browsable by both AI and humans"

Today: one HTML page + a static `llms.txt`. Upgrade path:

- **`llms.txt` v2** — auto-generated at build time from state.json: every view, every
  ecosystem entry, corpus stats, API endpoints with examples. Machine index of truth.
- **JSON mirrors** — `nous.minddragonlabs.com/{view}.json` per view (prs.json,
  plugins.json, skills.json, corpus.json), linked from llms.txt. Agents fetch the JSON;
  humans get the HTML. Same data, two representations, zero duplication.
- **API = the programmatic mirror** — the CF API (item 1) serves the same shapes.
  The site's JSON mirrors and the API agree by construction (both generated from
  state.json).
- Schema.org + OpenGraph on the ecosystem cards so search engines and agents that
  crawl HTML also get structure.

### 4. "No giant PR page on home — last 1,000, pages of 100"

Agreed. Current home block strip renders ~35 cubes and PRs view lists ~50. With 91k
PRs on disk the old pattern would collapse. Change:

- Block strip stays as-is (visual identity, ~35 cubes) — it never showed all PRs.
- **PRs view becomes paged**: `/prs` serves the most recent 1,000, 100 per page,
  10 pages, page param in the hash (`#prs?p=3`). Older-than-1,000 = API territory
  (`/api/v1/prs?state=all&page=N`), which is the monetization funnel — free tier
  caps at 30d history anyway per the tier design.
- Same pagination for Issues view (currently 100 hard-coded).

---

## Build order (phases, each shippable alone)

### Phase A — Ecosystem ingest + site tabs (no API dependency)
1. `fetch_state.py`: ingest plugin-catalog YAMLs (via `gh api` at refresh, cached to
   disk) + optional-skills tree → `state.json: {plugins: [...], skills: [...]}`
2. `build.py`: two new sections (PLUGINS / SKILLS markers), card grid + search
   (reuse `search.js` patterns; client-side filter of the embedded catalog —
   338+152 entries ≈ 150KB, fine embedded)
3. `llms.txt` v2 auto-generated: all views + ecosystem + counts
4. Local-first per Vercel rule: all on :8791 immediately; public site gets it at the
   next human-initiated release deploy

### Phase B — Paged PRs view
5. `build.py`: PRs section renders page 1 (most recent 100 of last 1,000);
   `app.js` hash-paging `#prs?p=N`, 10 pages max, older → link to API
6. Issues view same treatment
7. JSON mirror `/prs.json` (last 1,000, paged server-side is NOT needed —
   one static file, client slices)

### Phase C — Cloudflare API v1 (runs parallel to A/B; live against partial corpus)
8. R2 bucket + `wrangler` project `nous-api`; CI = none (manual deploy, rare)
9. Workers: the 10 endpoints above; data = state.json artifacts + prs.jsonl
   chunked to R2 at refresh time (write path is a local script, not a deploy)
10. Key issuance + per-key rate limits; usage endpoint; attribution middleware
    (free tier responses carry `X-Nous-Attribution` header + link)
11. x402 lane deferred (per plan Phase 3) — structure the worker so the middleware
    slot exists

### Phase D — Corpus labeling (already queued from earlier decision)
12. Backfill completes (~Oct 2) → label merged PRs with free models (SWE-2/flash)
13. Versioned `corpus.jsonl` + provenance + license audit + redaction (Phase 0 gate)
14. Corpus endpoints move from skeleton to real; paid tiers become sellable

Dependencies: A and B are independent of each other and of C. C's ecosystem endpoints
land after A (data shape defined there). D gates only the paid corpus tier.

---

## Open questions (need your call)

1. **Plugin/skill freshness**: ingest at every 5m refresh (cheap, ~500 small files)
   or daily? Recommend: daily — catalogs change only via merged PRs.
2. **PR page depth on site**: confirm 1,000 × 100. Recommend yes; older = API.
3. **API host**: `api.nous.minddragonlabs.com` (subdomain, CF) vs
   `nous.minddragonlabs.com/api/v1`? Recommend subdomain — clean tiering, site
   stays frozen-static.
4. **Free-tier history window**: plan said 30 days free. With 91k on disk, maybe
   90 days free is the more generous acquisition funnel CoinGecko-style. Recommend
   keeping 30d — scarcity is the upsell.

---

## Cost check (this Mac, no Vercel)

- Refresh loop: already running local-only. Ecosystem ingest adds ~500 gh api calls
  once daily — trivially inside the 5k/h budget shared with backfill (600/h cap).
- CF Workers free tier: 100k req/day, 10ms CPU — enough for v1 launch traffic.
- R2 free tier: 10GB storage, 1M class-A ops/mo — corpus at ~250MB fits ~40x over.

No build minutes anywhere. Jefferson's bill untouched.
