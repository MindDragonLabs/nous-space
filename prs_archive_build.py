#!/usr/bin/env python3
"""Build the PR archive views: last 1,000 merged+open PRs, paged 100/page.

Phase B of PLAN.md — "no giant PR page; last 1,000 in pages of 100".

Source: state.json `merged` (maintainer-lane merges) plus the backfill
corpus (merge_state/backfill/prs.jsonl — every PR in the repo, all states).
The site view serves the most recent 1,000 merged PRs (by merged_at),
de-duplicated with the live `merged` list, plus live open PRs first.

Output: ~/nous-space/prs_archive.json — one static file the client slices.
Local-only; no deploy.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
BACKFILL = os.path.expanduser(
    "~/.hermes/profiles/nous-pr-bot/scripts/merge_state/backfill/prs.jsonl")
OUT = os.path.join(HERE, "prs_archive.json")

MAX_PRS = 1000


def main() -> int:
    state = json.load(open(STATE, encoding="utf-8"))

    # live open PRs (from the maintainer lane) go first — most actionable
    live_open = []
    for p in (state.get("pending") or []):
        if isinstance(p, dict):
            live_open.append({
                "n": p.get("number"),
                "t": p.get("title", ""),
                "a": p.get("author", ""),
                "s": "open",
                "m": "",
                "c": p.get("changedFiles", 0),
            })

    seen = {r["n"] for r in live_open}

    # backfill merged PRs, newest first
    merged = []
    if os.path.exists(BACKFILL):
        with open(BACKFILL, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("merged_at") and r.get("number") not in seen:
                    merged.append({
                        "n": r.get("number"),
                        "t": r.get("title", ""),
                        "a": r.get("user") or "",
                        "s": "merged",
                        "m": (r.get("merged_at") or "")[:10],
                        "c": r.get("changed_files"),
                    })
    merged.sort(key=lambda r: r.get("m") or "", reverse=True)

    # state.json merged lane (richer: live maintain data) — dedupe against backfill
    state_merged = []
    for m in (state.get("merged") or []):
        if isinstance(m, dict) and m.get("number") not in seen:
            state_merged.append({
                "n": m.get("number"),
                "t": m.get("title", ""),
                "a": m.get("author", ""),
                "s": "merged",
                "m": (m.get("merged_at") or "")[:10],
                "c": m.get("changedFiles"),
            })
            seen.add(m.get("number"))

    archive = live_open + state_merged + merged
    archive = archive[:MAX_PRS]

    payload = {
        "generated": state.get("generated", ""),
        "total": len(archive),
        "per_page": 100,
        "pages": max(1, -(-len(archive) // 100)),
        "prs": archive,
    }
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    os.replace(tmp, OUT)
    print(f"prs_archive.json: {len(archive)} PRs "
          f"({len(live_open)} open + {len(archive)-len(live_open)} merged), "
          f"{payload['pages']} pages of 100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
