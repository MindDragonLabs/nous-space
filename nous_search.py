#!/usr/bin/env python3
"""Query the Nous index. Usage:
  ./nous_search.py <query> [--table prs|ecosystem|docs] [--limit 10] [--all]
Examples:
  ./nous_search.py "plugin guard"
  ./nous_search.py "telemetry" --table prs --limit 5
  ./nous_search.py "analytics" --table ecosystem
  ./nous_search.py '"prompt cache"' --all     # AND-phrase across title+body
"""
import argparse
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "nous-index.db")

FMT = {
    "prs": ("number", "title", "author", "state", "merged_at", "url"),
    "ecosystem": ("kind", "name", "category", "url"),
    "docs": ("path", "name"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--table", default="prs", choices=list(FMT))
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--all", action="store_true", help="search every table")
    args = ap.parse_args()

    if not os.path.exists(DB):
        sys.exit(f"no index at {DB} — run ./build_index.py first")

    db = sqlite3.connect(DB)
    meta = dict(db.execute("SELECT k, v FROM meta").fetchall())
    tables = list(FMT) if args.all else [args.table]

    q = args.query
    for t in tables:
        cols = FMT[t]
        sel = ", ".join(cols)
        try:
            rows = db.execute(
                f"SELECT {sel} FROM {t} WHERE {t} MATCH ? ORDER BY rank LIMIT ?",
                (q, args.limit)).fetchall()
        except sqlite3.OperationalError as e:
            print(f"{t}: query error: {e}", file=sys.stderr)
            continue
        total = db.execute(f"SELECT count(*) FROM {t} WHERE {t} MATCH ?", (q,)).fetchone()[0]
        print(f"\n== {t}: {total} hits (showing {min(args.limit, len(rows))}) ==")
        for r in rows:
            if t == "prs":
                num, title, author, state, merged, url = r
                when = (merged or "")[:10]
                print(f"  #{num} [{state[:6]}] {title[:80]} — {author} {when}")
                print(f"        {url}")
            elif t == "ecosystem":
                kind, name, cat, url = r
                print(f"  [{kind}] {name} ({cat}) — {url}")
            else:
                print(f"  {r[1]} — {r[0]}")
    db.close()
    if meta.get("built_at"):
        print(f"\n(index built {meta['built_at']} · {meta.get('counts','')})", file=sys.stderr)


if __name__ == "__main__":
    main()
