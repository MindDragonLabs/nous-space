# Nous News — AI news summaries, database-driven, zero recompile

**Status: PLAN ONLY — nothing implemented.**
Scope: a "news page about nous" carrying AI-written summaries of the last X hours of
major improvements, features and fixes — with special editions on major version
releases — while keeping Vercel builds at zero except deliberate site releases.

---

## 1. The constraint, restated

Content changes must never trigger a Vercel build. Builds happen only when **our site
architecture** changes (deliberate releases, like the antislop run). Everything that
changes on GitHub time (PRs, releases, summaries) must reach the page at runtime.

This is already how live numbers work today:

```
macmini refresh loop ──► state.json ──► push_kv.py ──► Cloudflare KV (nous-api-data)
                                                        │
browser ◄── static shell (Vercel) ◄── /api/v1/* rewrite ┴── Cloudflare Worker
```

`vercel.json` rewrites `/api/v1/:path*` to the Worker — no Vercel function invocations,
no builds. `push_kv.py` already pushes 4 data keys hourly. **News rides this exact
pipeline.** Vercel Blob (used by the forum) is the wrong store for this: every read
costs a serverless invocation. KV + Worker reads are effectively free (free tier:
100k reads/day; we would use a few hundred).

## 2. Three planes

| Plane | Where | Changes | Cost |
|---|---|---|---|
| **Generate** | macmini (read-only on GitHub) | every 6h + on release | cheap local model calls |
| **Store** | Cloudflare KV `nous-api-data` (extend existing namespace) | ~5 writes/day | free |
| **Deliver** | Worker `/api/v1/news` → static News view fetches at runtime | reads only | free |

Generation never posts to GitHub (read-only lane rule). It writes local artifacts and
KV only.

## 3. Content model — "editions"

Two kinds, one schema. Every bullet cites PR numbers from the window it summarizes.

```json
{
  "id": "digest-2026-10-02T12:00Z",          // or "release-v0.21.5"
  "kind": "rolling" | "release",
  "window": { "start": "…", "end": "…" },     // data-time anchored, not wall-clock
  "version": "v0.21.5",                      // release editions only
  "generated": "…", "model": "…",
  "headline": "…", "standfirst": "…",
  "sections": [
    { "category": "features",       "bullets": [ { "text": "…", "prs": [131272], "areas": ["memory"] } ] },
    { "category": "fixes",          "bullets": [ … ] },
    { "category": "improvements",   "bullets": [ … ] },
    { "category": "ecosystem",      "bullets": [ … ] }
  ],
  "stats": { "merged": 38, "features": 9, "fixes": 14, "authors": 12 },
  "sources": ["merge_corpus", "watch_ledger", "state.merged", "releases"],
  "supersedes": null
}
```

- **Rolling digests** — fixed windows (6h / 24h), generated on a schedule. The page's
  "last X hours" view filters the edition index client-side.
- **Release editions** — generated the moment a new **semantic version** (v0.x.y)
  appears in `state.releases` between refreshes. Lead story of the news page, pinned.
  Content: release tag/date, PRs merged since the previous version, what the release
  means in plain language. "Especially on major version releases" = these get top
  billing + their own archive row.

## 4. Generation pipeline (local, read-only)

Input — all already collected, no new scraping:

- `state.json` merged/fresh PR lists (titles, conventional-commit scopes, labels,
  diff stats, authors)
- `merge_state/merge_corpus.md` + the watch ledger (`nous_pr_removed.jsonl`)
- `state.releases` (tag/version/date)
- ecosystem catalog deltas (new plugins/skills since last edition)

Steps:

1. **Bucket deterministically** — `feat→features`, `fix→fixes`, `perf/docs/refactor→
   improvements`, catalog deltas → `ecosystem`; area = commit scope.
2. **Rank "major" mechanically** before any LLM call: multi-area, P1/P2 labels,
   salvage chains, large diffs, revert/re-land pairs. The LLM never decides importance
   from scratch.
3. **LLM summarize** — cheap model (Nous Portal free tier / `deepseek-v4.1-flash`,
   ~3–5k tokens per edition). Input is ONLY the bucketed titles/scopes/labels/stats —
   no free web. Output: headline, standfirst, bullets with PR citations.
4. **Mechanical citation gate** — every bullet must cite PR numbers that exist in the
   window set; uncited bullets are dropped (retry once, then drop). Stats block is
   generated deterministically and never passes through the LLM.
5. **Publish** — write edition JSON + append to `news/v1/index.json` in KV
   (idempotent: edition id derives from window-end data time; re-runs overwrite).

Cadence: 4 rolling digests/day + release-triggered editions. Budget: ~20–50k tokens/day
— noise against the <0.5M/day ceiling. Windows anchored on data time (like the
existing `news_stories`) so rebuilding is byte-idempotent.

Runs as a cron in the `nous-pr-bot` profile (existing conventions:
`deliver=bot-chat`, `attach_to_session=false`, pinned cheap model), separate from the
5-minute refresh loop so the hot path stays cheap.

## 5. Storage & API

KV keys (same namespace as today):

```
news/v1/index.json                 ordered edition metadata, newest first (cap ~200)
news/v1/editions/{id}.json         rolling digests
news/v1/releases/{version}.json    release editions
```

Worker routes (same tier/attribution/cache machinery as `/api/v1/overview`):

```
GET /api/v1/news                 → index + optional ?limit=&kind=&window=
GET /api/v1/news/latest          → freshest digest or pinned release edition
GET /api/v1/news/{id}            → one edition
```

Public tier (news is public), `X-Nous-Attribution` required like every route, edge
cached ~5 min. Optional: `GET /api/v1/news.feed.json` (JSON Feed) for RSS readers —
mirrors the existing `/feed.json` pattern.

## 6. Frontend — the News page (ships in one deliberate site release)

- New nav button **News** (newspaper icon) — own view, client-fetched. The view shell
  is static and empty at build time; **the build never touches news content.**
- Layout (newspaper feel, matches the site's design system):
  - **Masthead**: "NOUS NEWS" + the window the current view covers (explicit date +
    timezone — same antislop rules as the rest of the site).
  - **Lead story**: pinned release edition (or freshest digest when none).
  - **Window chips**: last 6h / 24h / 7d / all — client-side filter over the index.
  - **Category chips**: features / fixes / improvements / ecosystem.
  - **Edition cards**: headline, standfirst, bulleted sections. Each bullet's PR chip
    deep-links to the on-site PR page (`#story/pr/N`) — reuses the story work from the
    antislop run; stats footer per card.
  - **Release archive strip**: one row per release edition, linked to its edition page.
  - **Provenance footer**: "AI summary of public data; every bullet cites its PRs;
    generated <explicit date + tz> by <model>."
- Fetch: lazy on view open (`/api/v1/news`), cached in memory + localStorage with the
  Worker's cache headers. 45s poll optional (same as the feed).

## 7. "Version releases" — two different things, kept separate

| Trigger | Effect | Requires Vercel build? |
|---|---|---|
| New **Hermes Agent** version (v0.x.y tag) | auto-generates a release edition + news story | **No** — data only |
| New **site architecture** version (our deploy) | the deliberate release event itself | Yes, by definition |

Follow-up flagged (out of scope here): the per-release **architecture diagrams** are
generated at build time today, so a new Hermes release only gets its diagram at the
next site deploy. To make diagrams fully data-driven too: generate SVGs locally per
release and push them to KV as `arch/v1/{tag}.svg`, served via `/api/v1/arch/{tag}`
and lazy-loaded by the picker. Cheap, same pattern — recommend doing it in Phase 4.

## 8. Cost accounting

| Item | Volume | Cost |
|---|---|---|
| Vercel builds | 0 per news update (only deliberate site releases) | $0 |
| Vercel functions | 0 (news is served by the Worker via rewrites) | $0 |
| Cloudflare Worker | a few hundred reads/day (free: 100k/day) | $0 |
| Cloudflare KV | ~5–10 writes/day, tiny reads (free tier) | $0 |
| Summarizer LLM | 4–6 editions/day × ~4k tokens | ~20–50k tokens/day (free/cheap models) |
| macmini loop | one small python job per 6h | $0 |

## 9. Failure modes & honesty rules

- **No merges in window** → publish a one-line "quiet window" edition or skip; index
  never lies about coverage.
- **Summarizer failure** → keep the previous edition, mark `generated` stale in the
  index; the page shows the stamp (existing freshness rules).
- **Corrections** → append-only: new edition with `supersedes: <id>`; old one stays.
- **No invented claims**: citation gate (§4.4) + deterministic stats. If the model
  adds a fact not derivable from the window set, it is dropped.
- Editions carry `sources[]` so the provenance page can list them like other datasets.

## 10. Phased rollout

- **Phase 0 — decisions** (Jefferson): window cadence (default 6h), model (default
  deepseek-v4.1-flash), auto-publish vs. review-first (default: auto-publish, with a
  bot-chat preview line per edition), News nav placement (default: after Forum).
- **Phase 1 — generator** (local only): `news_writer.py` + schema + citation gate +
  tests against the last 7 days of real data; cron scheduled; editions land in a local
  `news/` store first (nothing public yet). Review output quality here.
- **Phase 2 — data layer**: `push_kv.py` extension (news keys), Worker `/api/v1/news`
  routes + index. Still no UI; verify with curl.
- **Phase 3 — UI + release**: News view, window/category chips, PR deep links, JSON
  Feed. Ships at the **next deliberate site release** (the single deploy in the whole
  feature).
- **Phase 4 — optional**: architecture diagrams to KV (§7), RSS polish, per-author
  spotlights from the contributors data.

## 11. Explicitly out of scope

- Anything that posts to, comments on, or reacts to GitHub (read-only lane).
- LLM calls at request time (summaries are pre-generated; serving is pure fetch).
- A separate database service (Postgres etc.) — KV + the local index are the database
  here; adding a server would cost more than it saves at this scale.

## 12. Why this is safe to build

Every load-bearing piece already exists and is proven: the KV push loop, the Worker's
tier/attribution/cache machinery, the rewrites, the PR-page deep links, the freshness
stamp conventions, and the corpus/ledger inputs. The new surface is one generator
script, three Worker routes, and one static view shell.
