#!/usr/bin/env python3
"""Build the Nous superfast index (SQLite FTS5).

Sources (all local, zero API calls):
  - backfill PRs   ~/.hermes/profiles/nous-pr-bot/scripts/merge_state/backfill/*.jsonl
  - live watch PRs  ~/.hermes/profiles/nous-pr-bot/scripts/nous_pr_state.json (open, newest)
  - removed ledger  ~/.hermes/profiles/nous-pr-bot/scripts/nous_pr_removed.jsonl (recent merges/closes)
  - ecosystem       merge_state/ecosystem/ecosystem.json (plugins + skills)
  - corpus docs     ~/Nous-Fleet/reviews/continuous/hermes-quality-program/ (charter, rubric, trends, verdicts)

Output: ./nous-index.db  (gitignored; rebuild is cheap: ~4s / 40k PRs)
"""
import glob
import json
import os
import re
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "nous-index.db")
HOME = os.path.expanduser("~")
PROFILE = os.path.join(HOME, ".hermes/profiles/nous-pr-bot/scripts")
HQ = os.path.join(HOME, "Nous-Fleet/reviews/continuous/hermes-quality-program")
BODY_CAP = 20000  # cap giant PR bodies


def clean(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        return " ".join(str(x) for x in v)
    return str(v)


def build():
    t0 = time.time()
    if os.path.exists(DB):
        os.remove(DB)
    db = sqlite3.connect(DB)
    db.executescript("""
    PRAGMA journal_mode=OFF;
    CREATE VIRTUAL TABLE prs USING fts5(
      number UNINDEXED, title, body, author UNINDEXED, labels,
      state UNINDEXED, merged_at UNINDEXED, url UNINDEXED,
      tokenize='porter unicode61');
    CREATE VIRTUAL TABLE issues USING fts5(
      number UNINDEXED, title, body, author UNINDEXED, labels,
      state UNINDEXED, url UNINDEXED,
      tokenize='porter unicode61');
    CREATE VIRTUAL TABLE ecosystem USING fts5(
      kind UNINDEXED, name, description, category UNINDEXED,
      repo UNINDEXED, url UNINDEXED, tokenize='porter unicode61');
    CREATE VIRTUAL TABLE docs USING fts5(
      path UNINDEXED, name, body, tokenize='porter unicode61');
    CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
    """)

    # 1) backfill PRs
    n_prs = 0
    files = sorted(glob.glob(os.path.join(PROFILE, "merge_state/backfill/*.jsonl")))
    batch = []
    for f in files:
        with open(f) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                batch.append((
                    str(r.get("number") or ""), r.get("title") or "",
                    clean(r.get("body"))[:BODY_CAP], clean(r.get("user")),
                    clean(r.get("labels")), clean(r.get("state")),
                    clean(r.get("merged_at")), r.get("html_url") or ""))
                if len(batch) >= 5000:
                    db.executemany("INSERT INTO prs VALUES (?,?,?,?,?,?,?,?)", batch)
                    n_prs += len(batch)
                    batch = []
    if batch:
        db.executemany("INSERT INTO prs VALUES (?,?,?,?,?,?,?,?)", batch)
        n_prs += len(batch)

    # 2) live watch PRs (newest; backfill hasn't reached them yet) — upsert by delete+insert
    n_live = 0
    st = os.path.join(PROFILE, "nous_pr_state.json")
    if os.path.exists(st):
        try:
            d = json.load(open(st))
            lo = d.get("last_output") or ""
            # parse the "#num | author (ROLE) | title | url" lines
            for m in re.finditer(r"^#(\d+) \| (\S+) \((\w+)\) \| (.*?) \| (https://\S+)$", lo, re.M):
                num, author, _role, title, url = m.groups()
                db.execute("DELETE FROM prs WHERE number=?", (num,))
                db.execute("INSERT INTO prs VALUES (?,?,?,?,?,?,?,?)",
                           (num, title, "", author, "", "OPEN", "", url))
                n_live += 1
        except Exception as e:
            print(f"warn: watch state parse: {e}", file=sys.stderr)

    # 3) removed ledger (recent merges/closes with titles)
    n_rem = 0
    rl = os.path.join(PROFILE, "nous_pr_removed.jsonl")
    if os.path.exists(rl):
        with open(rl) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                num = str(r.get("pr") or "")
                row = db.execute("SELECT number FROM prs WHERE number=?", (num,)).fetchone()
                if row:
                    # refresh state/title on a row we already have
                    db.execute("UPDATE prs SET state=?, title=? WHERE number=?",
                               (str(r.get("reason") or "").upper(), r.get("title") or "", num))
                else:
                    db.execute("INSERT INTO prs VALUES (?,?,?,?,?,?,?,?)",
                               (num, r.get("title") or "", "", r.get("author") or "",
                                "", str(r.get("reason") or "").upper(), r.get("ts") or "",
                                f"https://github.com/NousResearch/hermes-agent/pull/{num}"))
                n_rem += 1

    # 3b) issues backfill
    n_iss = 0
    iss_f = os.path.join(PROFILE, "merge_state/issues_backfill/issues.jsonl")
    if os.path.exists(iss_f):
        with open(iss_f) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                num = str(r.get("number") or "")
                if not num:
                    continue
                db.execute("INSERT INTO issues VALUES (?,?,?,?,?,?,?)", (
                    num, r.get("title") or "", r.get("body") or "",
                    r.get("user") or "",
                    ",".join(r.get("labels") or []),
                    str(r.get("state") or "").upper(),
                    f"https://github.com/NousResearch/hermes-agent/issues/{num}"))
                n_iss += 1

    # 4) ecosystem
    n_eco = 0
    eco_f = os.path.join(HERE, "ecosystem.json")
    if os.path.exists(eco_f):
        try:
            eco = json.load(open(eco_f))
        except Exception as e:
            eco = {}
            print(f"warn: ecosystem parse: {e}", file=sys.stderr)
        for kind, items in eco.items():
            if kind not in ("plugins", "skills", "mods", "mcp", "tools"):
                continue               # catalog categories only (free lane)
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                db.execute("INSERT INTO ecosystem VALUES (?,?,?,?,?,?)", (
                    kind, it.get("name") or it.get("id") or "",
                    clean(it.get("description") or it.get("summary")),
                    clean(it.get("category")), clean(it.get("repo") or it.get("source")),
                    clean(it.get("url") or it.get("html_url"))))
                n_eco += 1

    # 5) corpus docs
    n_docs = 0
    patterns = [os.path.join(HQ, "*.md"), os.path.join(HQ, "audits", "VERDICT-*.md")]
    for pat in patterns:
        for f in glob.glob(pat):
            try:
                body = open(f, errors="replace").read()[:100000]
            except OSError:
                continue
            db.execute("INSERT INTO docs VALUES (?,?,?)",
                       (f.replace(HOME, "~"), os.path.basename(f), body))
            n_docs += 1

    db.executescript("INSERT INTO prs(prs) VALUES('optimize');")
    db.execute("INSERT OR REPLACE INTO meta VALUES('built_at', ?)", (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),))
    db.execute("INSERT OR REPLACE INTO meta VALUES('counts', ?)",
               (json.dumps({"prs": n_prs, "live": n_live, "removed": n_rem,
                            "issues": n_iss, "ecosystem": n_eco, "docs": n_docs}),))
    db.commit()
    db.close()
    size = os.path.getsize(DB) / 1e6
    print(f"INDEX built in {time.time()-t0:.1f}s -> {DB} ({size:.0f} MB)")
    print(f"  prs {n_prs} (+{n_live} live, {n_rem} ledger-refreshed) · issues {n_iss} · ecosystem {n_eco} · docs {n_docs}")


if __name__ == "__main__":
    build()
